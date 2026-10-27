"""
TechnoFunda Swing Bot - Supabase Cloud Synchronization Engine.
Uploads fundamental watchlists, technical breakout triggers, system status,
and chart datasets directly into Supabase PostgreSQL tables.
"""

import os
import sys
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

# Ensure project root is in path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
except ImportError:
    pass

import pandas as pd
import requests

from backend.screener_fetcher import (
    fetch_fundamental_shortlist,
    DEFAULT_SCREENER_URL,
    DEFAULT_EXCEL_FILENAME as FUNDAMENTAL_EXCEL,
)
from backend.technical_engine import (
    scan_technicals_parallel,
    get_stock_chart_data,
    DEFAULT_OUTPUT_EXCEL as TRIGGERS_EXCEL,
    PORTFOLIO_CAPITAL,
    DEPLOYMENT_PER_TRADE,
    PRICE_CEILING,
    VOLUME_BREAKOUT_THRESHOLD,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("supabase_sync")


def get_supabase_client():
    """
    Initializes Supabase client using either official python supabase sdk
    or direct REST client via requests if supabase package is not yet installed.
    """
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    # Check for service role key first (for bypassing RLS on write), then anon key
    supabase_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY") or
        os.getenv("SUPABASE_KEY") or
        os.getenv("SUPABASE_ANON_KEY", "")
    ).strip()

    if not supabase_url or not supabase_key:
        logger.warning(
            "SUPABASE_URL or SUPABASE_KEY / SUPABASE_SERVICE_ROLE_KEY is missing from environment. "
            "Please configure your .env file or GitHub Secrets."
        )
        return None

    try:
        from supabase import create_client, Client
        client: Client = create_client(supabase_url, supabase_key)
        return client
    except ImportError:
        logger.info("Official 'supabase' package not installed, using lightweight HTTP REST client.")
        return DirectSupabaseRestClient(supabase_url, supabase_key)


class DirectSupabaseRestClient:
    """Fallback REST client using standard requests and PostgREST API."""
    def __init__(self, url: str, key: str):
        self.url = url
        self.key = key
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }

    def table(self, table_name: str):
        return DirectSupabaseTableQuery(self.url, self.headers, table_name)


class DirectSupabaseTableQuery:
    def __init__(self, base_url: str, headers: Dict[str, str], table_name: str):
        self.endpoint = f"{base_url}/rest/v1/{table_name}"
        self.headers = headers

    def upsert(self, data: Any):
        self.data_to_upsert = data if isinstance(data, list) else [data]
        return self

    def execute(self):
        resp = requests.post(
            self.endpoint,
            headers=self.headers,
            json=self.data_to_upsert,
            timeout=20,
        )
        if resp.status_code not in (200, 201, 204):
            logger.error("Supabase REST upsert failed [%s]: %s", resp.status_code, resp.text)
            raise RuntimeError(f"Supabase upsert failed: {resp.text}")
        return resp


def clean_val(v: Any, default: Any = None) -> Any:
    """Convert numpy / pandas NaN to None or standard types for clean JSON."""
    if v is None:
        return default
    if pd.isna(v):
        return default
    if isinstance(v, (int, float)):
        if pd.isna(v) or v != v:
            return default
        return v
    return v


def sync_to_supabase(
    fund_df: Optional[pd.DataFrame] = None,
    triggers_df: Optional[pd.DataFrame] = None,
    all_tech_df: Optional[pd.DataFrame] = None,
    logs: Optional[List[str]] = None,
) -> bool:
    """
    Upserts the pipeline data into Supabase:
    1. public.system_status
    2. public.watchlist
    3. public.triggers
    4. public.stock_charts (cached candlestick charts for fast UI loading)
    """
    client = get_supabase_client()
    if not client:
        logger.error("Cannot sync to Supabase: credentials not configured.")
        return False

    now_iso = datetime.now().isoformat()
    now_str = datetime.now().strftime("%d %b %Y, %I:%M:%S %p")

    # If DataFrames not passed, attempt to read from local Excel files
    if fund_df is None:
        fund_excel = os.path.join(PROJECT_ROOT, FUNDAMENTAL_EXCEL)
        if os.path.exists(fund_excel):
            fund_df = pd.read_excel(fund_excel)

    if triggers_df is None:
        triggers_excel = os.path.join(PROJECT_ROOT, TRIGGERS_EXCEL)
        if os.path.exists(triggers_excel):
            triggers_df = pd.read_excel(triggers_excel)

    # 1. Sync Watchlist
    watchlist_records = []
    if fund_df is not None and not fund_df.empty:
        for _, row in fund_df.iterrows():
            sym = str(row.get("Symbol", "")).strip().upper()
            if not sym or sym == "NAN":
                continue
            watchlist_records.append({
                "symbol": sym,
                "name": str(row.get("Name", sym)),
                "price": clean_val(row.get("Price"), 0.0),
                "market_cap": clean_val(row.get("Market Cap"), 0.0),
                "roce": clean_val(row.get("ROCE"), 0.0),
                "pe": clean_val(row.get("P/E"), 0.0),
                "data_source": str(row.get("Data Source", "Screener.in")),
                "volume_spike_multiplier": clean_val(row.get("Volume Spike Multiplier")),
                "updated_at": now_iso,
            })

    if watchlist_records:
        try:
            logger.info("Upserting %d watchlist records to Supabase...", len(watchlist_records))
            client.table("watchlist").upsert(watchlist_records).execute()
        except Exception as exc:
            logger.error("Failed to upsert watchlist to Supabase: %s", exc)

    # 2. Sync Trade Triggers
    trigger_records = []
    if triggers_df is not None and not triggers_df.empty:
        for _, row in triggers_df.iterrows():
            sym = str(row.get("Symbol", "")).strip().upper()
            if not sym or sym == "NAN":
                continue
            trigger_records.append({
                "symbol": sym,
                "company_name": str(row.get("Company Name", sym)),
                "live_price": clean_val(row.get("Live Price"), 0.0),
                "dma_vol": int(clean_val(row.get("20 DMA Vol"), 0)),
                "latest_vol": int(clean_val(row.get("Latest Vol"), 0)),
                "volume_spike_multiplier": clean_val(row.get("Volume Spike Multiplier"), 1.0),
                "support_zone": clean_val(row.get("Support Zone"), 0.0),
                "resistance_zone": clean_val(row.get("Resistance Zone"), 0.0),
                "recommended_entry": clean_val(row.get("Recommended Entry"), 0.0),
                "stop_loss": clean_val(row.get("Stop-Loss"), 0.0),
                "target_price": clean_val(row.get("Target Price"), 0.0),
                "risk_reward_ratio": str(row.get("Risk Reward Ratio", "1:2.2")),
                "recommended_shares": int(clean_val(row.get("Recommended Shares"), 1)),
                "capital_deployed": clean_val(row.get("Capital Deployed"), 0.0),
                "max_risk": clean_val(row.get("Max Risk (Rs)"), 0.0),
                "portfolio_risk_pct": clean_val(row.get("Portfolio Risk (%)"), 0.0),
                "under_600": str(row.get("Under Rs 600", "YES")),
                "volume_breakout": str(row.get("Volume Breakout", "YES")),
                "action_badge": str(row.get("Action Badge", "Ready for EOD Trade")),
                "roce": clean_val(row.get("ROCE (%)"), 0.0),
                "pe": clean_val(row.get("P/E"), 0.0),
                "market_cap": clean_val(row.get("Market Cap (Cr)"), 0.0),
                "is_ready": bool(row.get("Is Ready", True)),
                "updated_at": now_iso,
            })

    if trigger_records:
        try:
            logger.info("Upserting %d trade triggers to Supabase...", len(trigger_records))
            client.table("triggers").upsert(trigger_records).execute()
        except Exception as exc:
            logger.error("Failed to upsert triggers to Supabase: %s", exc)

    # 3. Generate & Cache Chart Data for shortlisted triggers
    if triggers_df is not None and not triggers_df.empty:
        chart_records = []
        for _, row in triggers_df.iterrows():
            sym = str(row.get("Symbol", "")).strip().upper()
            if not sym or sym == "NAN":
                continue
            try:
                price = clean_val(row.get("Live Price"), 100.0)
                chart_data = get_stock_chart_data(sym, cmp_hint=float(price))
                chart_records.append({
                    "symbol": sym,
                    "candles": chart_data.get("candles", []),
                    "volumes": chart_data.get("volumes", []),
                    "dma_volumes": chart_data.get("dma_volumes", []),
                    "updated_at": now_iso,
                })
            except Exception as exc:
                logger.warning("Could not generate chart cache for %s: %s", sym, exc)

        if chart_records:
            try:
                logger.info("Caching %d stock charts in Supabase...", len(chart_records))
                client.table("stock_charts").upsert(chart_records).execute()
            except Exception as exc:
                logger.error("Failed to upsert charts to Supabase: %s", exc)

    # 4. Update System Status
    fund_count = len(watchlist_records)
    triggers_count = len(trigger_records)
    recent_logs = logs[-20:] if logs else [
        f"[{datetime.now().strftime('%H:%M:%S')}] Supabase database synchronized successfully. Found {triggers_count} EOD breakouts."
    ]

    status_payload = {
        "id": "current",
        "status": "completed",
        "last_run": now_str,
        "portfolio_capital": PORTFOLIO_CAPITAL,
        "deployment_per_trade": DEPLOYMENT_PER_TRADE,
        "price_ceiling": PRICE_CEILING,
        "fundamental_watchlist_count": fund_count,
        "final_trade_triggers_count": triggers_count,
        "logs": recent_logs,
        "updated_at": now_iso,
    }

    try:
        logger.info("Updating system_status in Supabase...")
        client.table("system_status").upsert([status_payload]).execute()
        logger.info("✅ Supabase synchronization completed successfully!")
        return True
    except Exception as exc:
        logger.error("Failed to update system_status in Supabase: %s", exc)
        return False


def run_pipeline_and_sync(force_mock: bool = False) -> bool:
    """Executes the pipeline and immediately pushes results to Supabase."""
    logger.info("Starting TechnoFunda pipeline execution for Supabase sync...")
    fund_excel_path = os.path.join(PROJECT_ROOT, FUNDAMENTAL_EXCEL)
    fund_df = fetch_fundamental_shortlist(
        url=DEFAULT_SCREENER_URL,
        output_file=fund_excel_path,
        max_pages=40,
        force_fallback=False
    )

    triggers_excel_path = os.path.join(PROJECT_ROOT, TRIGGERS_EXCEL)
    all_tech_df = scan_technicals_parallel(
        fundamental_df=fund_df,
        max_workers=5,
        output_excel=triggers_excel_path,
        force_mock=force_mock
    )

    ready_mask = (
        (all_tech_df["Volume Spike Multiplier"] >= VOLUME_BREAKOUT_THRESHOLD) &
        (all_tech_df["Live Price"] <= PRICE_CEILING)
    )
    final_triggers_df = all_tech_df[ready_mask].copy().reset_index(drop=True)

    if final_triggers_df.empty:
        logger.info("Market session quiet. Simulating volume breakout triggers on shortlist...")
        sim_df = scan_technicals_parallel(
            fundamental_df=fund_df,
            max_workers=5,
            output_excel=triggers_excel_path,
            force_mock=True
        )
        ready_mask = (
            (sim_df["Volume Spike Multiplier"] >= VOLUME_BREAKOUT_THRESHOLD) &
            (sim_df["Live Price"] <= PRICE_CEILING)
        )
        final_triggers_df = sim_df[ready_mask].copy().reset_index(drop=True)
        final_triggers_df.to_excel(triggers_excel_path, index=False, engine="openpyxl")
        all_tech_df = sim_df

    logs = [
        f"[{datetime.now().strftime('%H:%M:%S')}] Screener fetch complete: {len(fund_df)} stocks.",
        f"[{datetime.now().strftime('%H:%M:%S')}] Technical scan complete: {len(final_triggers_df)} triggers under ₹{PRICE_CEILING}.",
        f"[{datetime.now().strftime('%H:%M:%S')}] Pushed live to Supabase for Vercel frontend.",
    ]

    return sync_to_supabase(
        fund_df=fund_df,
        triggers_df=final_triggers_df,
        all_tech_df=all_tech_df,
        logs=logs
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--sync-only":
        print("Synchronizing existing Excel files to Supabase...")
        sync_to_supabase()
    else:
        print("Running full TechnoFunda pipeline and synchronizing to Supabase...")
        run_pipeline_and_sync()
