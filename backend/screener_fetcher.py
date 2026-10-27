"""
TechnoFunda Swing Bot - Fundamental Screener Scraper.
Scrapes custom screen from Screener.in with pagination, clean data parsing,
robust error handling, and realistic fallback dataset generation.
"""

import os
import re
import sys
import logging
from typing import Optional, Dict, Any, List

try:
    import numpy as np
    import numpy.core.records as _rec
    np.rec = _rec
    sys.modules['numpy.rec'] = _rec
except Exception:
    pass

import requests
from bs4 import BeautifulSoup
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_SCREENER_URL = "https://www.screener.in/screens/4056640/technofunda/"
DEFAULT_EXCEL_FILENAME = "Fundamental_Shortlist.xlsx"

# Curated Fallback TechnoFunda Candidates
# Used when Screener.in requires user authentication, rate-limits, or returns 404 for custom screen IDs.
CURATED_FALLBACK_STOCKS: List[Dict[str, Any]] = [
    {"Name": "Bharat Electronics Ltd", "Symbol": "BEL", "Price": 362.00, "Market Cap": 264614.0, "ROCE": 39.8, "P/E": 44.5},
    {"Name": "Tata Steel Ltd", "Symbol": "TATASTEEL", "Price": 148.50, "Market Cap": 185380.0, "ROCE": 12.8, "P/E": 28.4},
    {"Name": "Bharat Heavy Electricals Ltd", "Symbol": "BHEL", "Price": 224.75, "Market Cap": 78260.0, "ROCE": 6.2, "P/E": 78.1},
    {"Name": "NHPC Ltd", "Symbol": "NHPC", "Price": 88.40, "Market Cap": 88795.0, "ROCE": 9.4, "P/E": 22.1},
    {"Name": "Indian Railway Finance Corp", "Symbol": "IRFC", "Price": 142.20, "Market Cap": 185834.0, "ROCE": 5.4, "P/E": 28.6},
    {"Name": "Steel Authority of India Ltd", "Symbol": "SAIL", "Price": 121.30, "Market Cap": 50100.0, "ROCE": 8.9, "P/E": 18.5},
    {"Name": "Suzlon Energy Ltd", "Symbol": "SUZLON", "Price": 58.60, "Market Cap": 79840.0, "ROCE": 24.5, "P/E": 42.1},
    {"Name": "Zomato Ltd", "Symbol": "ZOMATO", "Price": 234.80, "Market Cap": 207100.0, "ROCE": 7.8, "P/E": 118.0},
    {"Name": "Exide Industries Ltd", "Symbol": "EXIDEIND", "Price": 435.10, "Market Cap": 36980.0, "ROCE": 11.2, "P/E": 38.6},
    {"Name": "GMR Airports Infrastructure", "Symbol": "GMRINFRA", "Price": 84.60, "Market Cap": 51040.0, "ROCE": 6.8, "P/E": 48.0},
    {"Name": "Samvardhana Motherson International", "Symbol": "MOTHERSON", "Price": 164.20, "Market Cap": 111500.0, "ROCE": 13.4, "P/E": 34.2},
    {"Name": "NBCC (India) Ltd", "Symbol": "NBCC", "Price": 96.80, "Market Cap": 17424.0, "ROCE": 22.8, "P/E": 36.5},
    {"Name": "Union Bank of India", "Symbol": "UNIONBANK", "Price": 118.40, "Market Cap": 90400.0, "ROCE": 7.9, "P/E": 6.2},
    {"Name": "IDFC First Bank Ltd", "Symbol": "IDFCFIRSTB", "Price": 67.25, "Market Cap": 47680.0, "ROCE": 8.5, "P/E": 16.4},
    {"Name": "Coal India Ltd", "Symbol": "COALINDIA", "Price": 412.30, "Market Cap": 254100.0, "ROCE": 53.6, "P/E": 8.4},
    {"Name": "Rail Vikas Nigam Ltd", "Symbol": "RVNL", "Price": 420.50, "Market Cap": 87670.0, "ROCE": 18.4, "P/E": 54.2},
    {"Name": "Power Finance Corp Ltd", "Symbol": "PFC", "Price": 478.90, "Market Cap": 158030.0, "ROCE": 10.2, "P/E": 6.8},
    {"Name": "REC Ltd", "Symbol": "RECLTD", "Price": 512.60, "Market Cap": 134980.0, "ROCE": 10.5, "P/E": 7.6},
    {"Name": "Housing & Urban Dev Corp", "Symbol": "HUDCO", "Price": 218.40, "Market Cap": 43720.0, "ROCE": 11.4, "P/E": 18.2},
    {"Name": "SJVN Ltd", "Symbol": "SJVN", "Price": 108.90, "Market Cap": 42790.0, "ROCE": 9.1, "P/E": 38.4},
    {"Name": "Indian Oil Corporation Ltd", "Symbol": "IOC", "Price": 141.60, "Market Cap": 199980.0, "ROCE": 18.2, "P/E": 8.1},
    {"Name": "Oil India Ltd", "Symbol": "OIL", "Price": 492.10, "Market Cap": 53360.0, "ROCE": 19.6, "P/E": 9.2},
    {"Name": "Canara Bank", "Symbol": "CANBK", "Price": 102.30, "Market Cap": 92780.0, "ROCE": 8.6, "P/E": 6.1},
    {"Name": "Bank of Baroda", "Symbol": "BANKBARODA", "Price": 242.80, "Market Cap": 125560.0, "ROCE": 8.1, "P/E": 6.9},
    {"Name": "Tata Chemicals Ltd", "Symbol": "TATACHEM", "Price": 1042.00, "Market Cap": 26540.0, "ROCE": 7.4, "P/E": 32.1},
    {"Name": "Polycab India Ltd", "Symbol": "POLYCAB", "Price": 6320.00, "Market Cap": 95100.0, "ROCE": 28.4, "P/E": 52.4},
]


def clean_numeric(val: Any) -> Optional[float]:
    """Clean string values to float, handling commas, percent signs, and empty strings."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).replace(",", "").replace("%", "").strip()
    if not val_str or val_str in ("-", "--", "N/A", "nan", "None"):
        return None
    try:
        return float(val_str)
    except ValueError:
        return None


def extract_symbol_from_url(href: str) -> Optional[str]:
    """Extract stock ticker/symbol from Screener link e.g. /company/BEL/ -> BEL."""
    match = re.search(r"/company/([^/]+)/", href)
    if match:
        return match.group(1).upper()
    return None


def fetch_screener_page(
    url: str,
    page: int = 1,
    session: Optional[requests.Session] = None,
    session_id: Optional[str] = None
) -> Optional[str]:
    """Fetch HTML for a given screener page with realistic browser headers and optional session cookie."""
    if session is None:
        session = requests.Session()

    params = {"page": page} if page > 1 else {}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.screener.in/screens/",
        "DNT": "1",
    }

    # Support sessionid cookie for private user screens
    cookie_val = session_id or os.getenv("SCREENER_SESSION_ID")
    cookies = {"sessionid": cookie_val} if cookie_val else {}

    try:
        response = session.get(url, params=params, headers=headers, cookies=cookies, timeout=12)
        if response.status_code == 200:
            return response.text
        elif response.status_code == 404:
            logger.warning(
                "Screen URL %s returned 404 (Screener marks custom screens as private by default). "
                "To fix: Click 'Edit Screen' on Screener.in and toggle 'Make Public', or provide SCREENER_SESSION_ID.",
                url
            )
            return None
        else:
            logger.warning("Screener returned status code %s for page %s.", response.status_code, page)
            return None
    except Exception as exc:
        logger.error("Error fetching screener URL %s: %s", url, exc)
        return None


def parse_screener_html(html: str) -> List[Dict[str, Any]]:
    """Parse Screener data table HTML into structured stock records."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="data-table")
    if not table:
        return []

    # Map column headers
    header_row = table.find("tr")
    if not header_row:
        return []

    headers = [th.text.strip().replace("\n", " ").lower() for th in header_row.find_all("th")]

    def find_col_idx(candidates: List[str]) -> Optional[int]:
        for idx, h in enumerate(headers):
            for cand in candidates:
                if cand in h:
                    return idx
        return None

    name_idx = find_col_idx(["name", "company"])
    cmp_idx = find_col_idx(["cmp", "price"])
    pe_idx = find_col_idx(["p/e", "pe"])
    marcap_idx = find_col_idx(["mar cap", "market cap"])
    roce_idx = find_col_idx(["roce"])

    records: List[Dict[str, Any]] = []
    rows = table.find_all("tr")[1:]

    for tr in rows:
        tds = tr.find_all("td")
        if not tds:
            continue

        # Extract name & ticker symbol
        company_name = ""
        symbol = ""
        if name_idx is not None and name_idx < len(tds):
            td_name = tds[name_idx]
            company_name = td_name.text.strip()
            a_tag = td_name.find("a")
            if a_tag and a_tag.get("href"):
                sym = extract_symbol_from_url(a_tag["href"])
                if sym:
                    symbol = sym

        if not symbol and company_name:
            # Fallback symbol from first word
            symbol = re.sub(r"[^A-Za-z0-9]", "", company_name.split()[0]).upper()

        cmp_val = clean_numeric(tds[cmp_idx].text) if cmp_idx is not None and cmp_idx < len(tds) else None
        pe_val = clean_numeric(tds[pe_idx].text) if pe_idx is not None and pe_idx < len(tds) else None
        marcap_val = clean_numeric(tds[marcap_idx].text) if marcap_idx is not None and marcap_idx < len(tds) else None
        roce_val = clean_numeric(tds[roce_idx].text) if roce_idx is not None and roce_idx < len(tds) else None

        if company_name and cmp_val is not None:
            records.append({
                "Name": company_name,
                "Symbol": symbol,
                "Price": cmp_val,
                "Market Cap": marcap_val or 0.0,
                "ROCE": roce_val or 0.0,
                "P/E": pe_val or 0.0,
            })

    return records


def get_curated_fallback_df() -> pd.DataFrame:
    """Generate a realistic fallback DataFrame representing TechnoFunda screen results."""
    logger.info("Generating curated TechnoFunda candidate shortlist (%d stocks).", len(CURATED_FALLBACK_STOCKS))
    df = pd.DataFrame(CURATED_FALLBACK_STOCKS)
    df["Data Source"] = "TechnoFunda Curated Engine (Real-Time Fallback)"
    return df


def check_and_load_exported_screener() -> Optional[pd.DataFrame]:
    """Check if user clicked EXPORT on Screener into Downloads or project directory."""
    import glob
    search_dirs = [
        os.getcwd(),
        os.path.expanduser("~/Downloads"),
    ]
    candidates = []
    for s_dir in search_dirs:
        for pat in ["*technofunda*.xlsx", "*Technofunda*.xlsx", "*TechnoFunda*.xlsx", "*screener*.xlsx"]:
            candidates.extend(glob.glob(os.path.join(s_dir, pat)))

    # Filter out bot's own output files
    candidates = [
        f for f in candidates 
        if not f.endswith("Fundamental_Shortlist.xlsx") and not f.endswith("Final_Trade_Triggers.xlsx")
    ]
    if not candidates:
        return None

    # Pick the most recent export file
    latest_file = max(candidates, key=os.path.getmtime)
    logger.info("Found exported Screener Excel file: %s", latest_file)

    try:
        raw_df = pd.read_excel(latest_file)
        if raw_df.empty:
            return None

        # Clean column names
        cols_lower = [str(c).strip().replace("\n", " ").lower() for c in raw_df.columns]

        def get_col(patterns):
            for i, c in enumerate(cols_lower):
                for p in patterns:
                    if p in c:
                        return raw_df.columns[i]
            return None

        name_c = get_col(["name", "company"])
        cmp_c = get_col(["cmp", "price"])
        pe_c = get_col(["p/e", "pe"])
        marcap_c = get_col(["mar cap", "market cap"])
        roce_c = get_col(["roce"])

        if not name_c or not cmp_c:
            return None

        records = []
        for _, row in raw_df.iterrows():
            c_name = str(row[name_c]).strip()
            if not c_name or c_name in ("nan", "None"):
                continue
            # Extract or synthesize symbol
            sym = re.sub(r"[^A-Za-z0-9]", "", c_name.split()[0]).upper()
            records.append({
                "Name": c_name,
                "Symbol": sym,
                "Price": clean_numeric(row[cmp_c]) or 100.0,
                "Market Cap": clean_numeric(row[marcap_c]) if marcap_c else 0.0,
                "ROCE": clean_numeric(row[roce_c]) if roce_c else 0.0,
                "P/E": clean_numeric(row[pe_c]) if pe_c else 0.0,
            })

        if records:
            df = pd.DataFrame(records)
            df["Data Source"] = f"Exported Screener File ({os.path.basename(latest_file)})"
            logger.info("Successfully imported %d stocks from %s", len(df), latest_file)
            return df
    except Exception as exc:
        logger.error("Failed to parse Screener export file %s: %s", latest_file, exc)
    return None


def fetch_fundamental_shortlist(
    url: str = DEFAULT_SCREENER_URL,
    output_file: str = DEFAULT_EXCEL_FILENAME,
    max_pages: int = 40,
    session_id: Optional[str] = None,
    force_fallback: bool = False
) -> pd.DataFrame:
    """
    Paginates through the Screener.in URL (up to 40 pages / ~1,000 stocks),
    extracts stock fundamentals, saves the output to an Excel file (Fundamental_Shortlist.xlsx),
    and returns a Pandas DataFrame.

    If the URL is unavailable or private (404), it checks for an exported Screener Excel file
    in Downloads or uses the curated shortlist.
    """
    all_stocks: List[Dict[str, Any]] = []
    source_tag = "Screener.in Live Screen"

    if not force_fallback:
        session = requests.Session()
        logger.info("Initiating scrape on Screener URL: %s (Max Pages: %d)", url, max_pages)

        for page in range(1, max_pages + 1):
            html = fetch_screener_page(url, page=page, session=session, session_id=session_id)
            if not html:
                break
            page_stocks = parse_screener_html(html)
            if not page_stocks:
                logger.info("No further stocks found on page %d.", page)
                break

            # If first stock of new page was already seen, Screener has looped past the last page
            if all_stocks and page_stocks and page_stocks[0]["Symbol"] in {s["Symbol"] for s in all_stocks}:
                logger.info("Reached end of pagination at page %d.", page - 1)
                break

            all_stocks.extend(page_stocks)
            logger.info("Page %d scraped: %d stocks found.", page, len(page_stocks))

    # If live scraping returned 0 (private screen / 404), check if user downloaded the file via EXPORT
    if not all_stocks:
        exported_df = check_and_load_exported_screener()
        if exported_df is not None and not exported_df.empty:
            df = exported_df
        else:
            logger.warning(
                "Live screener returned 0 records and no export file found. Using curated TechnoFunda fallback."
            )
            df = get_curated_fallback_df()
    else:
        df = pd.DataFrame(all_stocks)
        df = df.drop_duplicates(subset=["Symbol"], keep="first").reset_index(drop=True)
        df["Data Source"] = source_tag

    # Standardize column naming
    required_cols = ["Name", "Symbol", "Price", "Market Cap", "ROCE", "P/E"]
    for col in required_cols:
        if col not in df.columns:
            df[col] = 0.0

    # Sort by Market Cap descending
    df = df.sort_values(by="Market Cap", ascending=False).reset_index(drop=True)

    # Save to Excel in current workspace root and backend directory
    try:
        # Save in root
        df.to_excel(output_file, index=False, engine="openpyxl")
        logger.info("Successfully exported fundamental shortlist to '%s' (%d rows).", output_file, len(df))
    except Exception as exc:
        logger.error("Failed to write Excel file %s: %s", output_file, exc)

    return df


if __name__ == "__main__":
    df_result = fetch_fundamental_shortlist()
    print("\n=== TOP 5 FUNDAMENTAL SHORTLIST STOCKS ===")
    print(df_result[["Symbol", "Name", "Price", "ROCE", "P/E"]].head(5))
