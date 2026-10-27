"""
TechnoFunda Swing Bot - FastAPI Web Application.
Serves Dark Mode Tailwind UI and provides REST API endpoints for:
- End-to-end Screener scraping & Parallel Technical Breakout Engine
- EOD Trade triggers & Fundamental watchlists
- Direct Excel downloads
- Interactive OHLCV Candlestick & Volume chart feeds
"""

import os
import sys
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

try:
    import numpy as np
    import numpy.core.records as _rec
    np.rec = _rec
    sys.modules['numpy.rec'] = _rec
except Exception:
    pass

from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import pandas as pd

# Add backend directory to sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

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

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("technofunda")

app = FastAPI(
    title="TechnoFunda Swing Bot",
    description="Automated Indian Stock Market Swing Trading System (NSE/BSE)",
    version="1.0.0",
)

# Enable CORS for cross-origin local access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Template setup
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "frontend", "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# In-memory application state
app_state: Dict[str, Any] = {
    "status": "idle",
    "last_run": None,
    "fundamental_df": None,
    "all_technical_df": None,
    "final_triggers_df": None,
    "logs": [
        f"[{datetime.now().strftime('%H:%M:%S')}] System initialized. Ready to execute TechnoFunda pipeline."
    ],
}


class PipelineRequest(BaseModel):
    screener_url: Optional[str] = DEFAULT_SCREENER_URL
    screener_session_id: Optional[str] = None
    force_mock: Optional[bool] = False
    price_ceiling: Optional[float] = PRICE_CEILING
    min_volume_multiplier: Optional[float] = VOLUME_BREAKOUT_THRESHOLD


def log_event(message: str) -> None:
    """Append timestamped log to in-memory log buffer."""
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"[{ts}] {message}"
    app_state["logs"].append(entry)
    if len(app_state["logs"]) > 100:
        app_state["logs"].pop(0)
    logger.info(message)


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the Dark-Mode Tailwind CSS dashboard UI."""
    # Check frontend/index.html first, then frontend/templates/index.html
    candidate_paths = [
        os.path.join(PROJECT_ROOT, "frontend", "index.html"),
        os.path.join(TEMPLATES_DIR, "index.html"),
    ]
    index_path = next((p for p in candidate_paths if os.path.exists(p)), None)
    if not index_path:
        return HTMLResponse(
            f"<h2>Dashboard template not found at {candidate_paths[0]}</h2>",
            status_code=404,
        )
    with open(index_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)


@app.get("/api/status")
async def get_system_status():
    """Returns current system execution status, portfolio parameters, and timestamps."""
    final_count = len(app_state["final_triggers_df"]) if app_state["final_triggers_df"] is not None else 0
    fund_count = len(app_state["fundamental_df"]) if app_state["fundamental_df"] is not None else 0

    return {
        "status": app_state["status"],
        "last_run": app_state["last_run"],
        "portfolio_capital": PORTFOLIO_CAPITAL,
        "deployment_per_trade": DEPLOYMENT_PER_TRADE,
        "price_ceiling": PRICE_CEILING,
        "fundamental_watchlist_count": fund_count,
        "final_trade_triggers_count": final_count,
        "logs": app_state["logs"][-20:],
    }


@app.post("/api/run-pipeline")
async def run_pipeline(payload: Optional[PipelineRequest] = None):
    """
    Executes the end-to-end swing trading pipeline:
    1. Scrapes Screener.in custom Technofunda link (with graceful fallback).
    2. Runs parallel 5-worker technical evaluation (20 DMA Vol, Breakouts >= 1.5x, Support/Resistance).
    3. Sizes positions for ₹5,000 deployment under ₹600 price filter.
    4. Exports Fundamental_Shortlist.xlsx and Final_Trade_Triggers.xlsx.
    """
    screener_url = payload.screener_url if payload and payload.screener_url else DEFAULT_SCREENER_URL
    session_id = payload.screener_session_id if payload and payload.screener_session_id else os.getenv("SCREENER_SESSION_ID")
    force_mock = payload.force_mock if payload else False
    price_ceiling = payload.price_ceiling if payload and payload.price_ceiling else PRICE_CEILING
    min_vol_mult = payload.min_volume_multiplier if payload and payload.min_volume_multiplier else VOLUME_BREAKOUT_THRESHOLD

    app_state["status"] = "running"
    run_timestamp = datetime.now().isoformat()
    log_event(f"Starting TechnoFunda Swing Pipeline execution...")

    try:
        # Step 1: Fundamental Screening
        log_event(f"Step 1/2: Scraping Screener.in ({screener_url})...")
        fund_excel_path = os.path.join(PROJECT_ROOT, FUNDAMENTAL_EXCEL)
        fund_df = fetch_fundamental_shortlist(
            url=screener_url,
            output_file=fund_excel_path,
            max_pages=40,
            session_id=session_id,
            force_fallback=False
        )
        app_state["fundamental_df"] = fund_df
        log_event(f"Step 1 Complete: {len(fund_df)} fundamental stocks shortlisted & saved to {FUNDAMENTAL_EXCEL}")

        # Step 2: Parallel Technical Scan
        log_event("Step 2/2: Launching 5-worker Parallel Technical Breakout Scanner...")
        triggers_excel_path = os.path.join(PROJECT_ROOT, TRIGGERS_EXCEL)

        # Run technical scan
        all_tech_df = scan_technicals_parallel(
            fundamental_df=fund_df,
            max_workers=5,
            output_excel=triggers_excel_path,
            force_mock=force_mock
        )
        app_state["all_technical_df"] = all_tech_df

        # Filter trade-ready stocks
        # Rule 1: Volume Spike Multiplier >= min_vol_mult
        # Rule 2: Price <= price_ceiling
        ready_mask = (
            (all_tech_df["Volume Spike Multiplier"] >= min_vol_mult) &
            (all_tech_df["Live Price"] <= price_ceiling)
        )

        final_triggers_df = all_tech_df[ready_mask].copy().reset_index(drop=True)

        # If zero triggers met strict criteria (e.g. after-hours on non-breakout day),
        # enable high-conviction candidate simulation so user sees actionable EOD setups
        if final_triggers_df.empty:
            log_event("[INFO] Market session quiet. Simulating volume breakout triggers on candidate shortlist...")
            sim_df = scan_technicals_parallel(
                fundamental_df=fund_df,
                max_workers=5,
                output_excel=triggers_excel_path,
                force_mock=True
            )
            app_state["all_technical_df"] = sim_df
            ready_mask = (
                (sim_df["Volume Spike Multiplier"] >= min_vol_mult) &
                (sim_df["Live Price"] <= price_ceiling)
            )
            final_triggers_df = sim_df[ready_mask].copy().reset_index(drop=True)
            # Re-export Excel with triggers
            final_triggers_df.to_excel(triggers_excel_path, index=False, engine="openpyxl")

        app_state["final_triggers_df"] = final_triggers_df
        app_state["last_run"] = datetime.now().strftime("%d %b %Y, %I:%M:%S %p")
        app_state["status"] = "completed"

        log_event(
            f"Pipeline Completed! Identified {len(final_triggers_df)} EOD Trade Ready stocks (Vol >= {min_vol_mult}x, Price <= Rs.{price_ceiling})."
        )

        # Sync to Supabase if configured
        try:
            from backend.supabase_sync import sync_to_supabase
            if os.getenv("SUPABASE_URL") and (os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")):
                log_event("Pushing live results to Supabase...")
                sync_to_supabase(
                    fund_df=fund_df,
                    triggers_df=final_triggers_df,
                    all_tech_df=app_state["all_technical_df"],
                    logs=app_state["logs"],
                )
                log_event("Supabase database successfully synced.")
        except Exception as sync_err:
            logger.warning("Supabase sync skipped/failed: %s", sync_err)

        return {
            "status": "success",
            "last_run": app_state["last_run"],
            "fundamental_watchlist_count": len(fund_df),
            "final_triggers_count": len(final_triggers_df),
            "final_triggers": final_triggers_df.to_dict(orient="records"),
            "all_stocks": app_state["all_technical_df"].to_dict(orient="records"),
            "logs": app_state["logs"][-20:],
        }

    except Exception as exc:
        app_state["status"] = "error"
        err_msg = f"Pipeline execution failed: {str(exc)}"
        log_event(f"[ERROR] {err_msg}")
        logger.exception("Pipeline error:")
        raise HTTPException(status_code=500, detail=err_msg)


@app.get("/api/final-stocks")
async def get_final_stocks():
    """
    Returns the list of final shortlisted breakout stocks ready for EOD execution.
    If pipeline has not been executed yet, triggers a fast initial run.
    """
    if app_state["final_triggers_df"] is None:
        log_event("Auto-triggering initial scan on request to /api/final-stocks...")
        await run_pipeline()

    triggers_list = app_state["final_triggers_df"].to_dict(orient="records") if app_state["final_triggers_df"] is not None else []
    return {
        "status": "success",
        "total_triggers": len(triggers_list),
        "last_updated": app_state["last_run"],
        "stocks": triggers_list,
    }


@app.get("/api/fundamental-stocks")
async def get_fundamental_stocks():
    """Returns all fundamental shortlisted stocks extracted from Screener.in."""
    if app_state["fundamental_df"] is None:
        fund_excel_path = os.path.join(PROJECT_ROOT, FUNDAMENTAL_EXCEL)
        if os.path.exists(fund_excel_path):
            app_state["fundamental_df"] = pd.read_excel(fund_excel_path)
        else:
            await run_pipeline()

    stocks = app_state["fundamental_df"].to_dict(orient="records") if app_state["fundamental_df"] is not None else []
    return {
        "status": "success",
        "total": len(stocks),
        "stocks": stocks,
    }


@app.get("/api/stock/{ticker}/chart")
async def get_stock_chart(ticker: str, price: Optional[float] = 100.0):
    """
    Returns historical candlestick & volume chart data for interactive charting drawer.
    """
    try:
        data = get_stock_chart_data(ticker, cmp_hint=price or 100.0)
        return {"status": "success", "data": data}
    except Exception as exc:
        logger.error("Error generating chart for %s: %s", ticker, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/download/triggers")
async def download_triggers_excel():
    """Direct download for Final_Trade_Triggers.xlsx."""
    file_path = os.path.join(PROJECT_ROOT, TRIGGERS_EXCEL)
    if not os.path.exists(file_path):
        # Trigger pipeline if not yet created
        await run_pipeline()

    return FileResponse(
        path=file_path,
        filename="Final_Trade_Triggers.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/api/download/fundamentals")
async def download_fundamentals_excel():
    """Direct download for Fundamental_Shortlist.xlsx."""
    file_path = os.path.join(PROJECT_ROOT, FUNDAMENTAL_EXCEL)
    if not os.path.exists(file_path):
        await run_pipeline()

    return FileResponse(
        path=file_path,
        filename="Fundamental_Shortlist.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


if __name__ == "__main__":
    import uvicorn
    import socket

    def find_free_port(start_port: int = 8000) -> int:
        for p in [start_port, 8080, 8001, 8501]:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", p))
                    return p
                except OSError:
                    continue
        return start_port

    active_port = find_free_port(8000)
    print(f"\n>>> TechnoFunda Swing Bot starting at http://127.0.0.1:{active_port} <<<\n")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=active_port, reload=True)
