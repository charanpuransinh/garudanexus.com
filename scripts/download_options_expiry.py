"""
download_options_expiry.py — NSE F&O historical options data (strike-wise
CE/PE, OI, OHLC premium, underlying price) for NIFTY/BANKNIFTY/SENSEX
indices + all NIFTY-100 stocks. Saves one CSV per symbol into
data/options_expiry/, appending new trading days.

Source: NSE's official UDiFF Common Bhavcopy Final format (the ONLY format
NSE has published since 2024-07-08, per NSE Circular No. 62424 — the older
per-symbol bhavcopy format was discontinued). One file per trading day,
covering ALL F&O instruments (index + stock options + futures) — this
script downloads the FULL daily file, filters to just our symbols +
options (CE/PE, not futures), and appends the filtered rows.

URL pattern: https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_YYYYMMDD_F_0000.csv.zip

Real data only — a date with no NSE file (market holiday, or genuinely
missing) is skipped and logged, never fabricated.
"""
import sys
import time
import csv
import io
import zipfile
from pathlib import Path
from datetime import datetime, timedelta

import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SYMBOL_LIST = _REPO_ROOT / "data" / "nifty100_symbols.csv"
_OUT_DIR = _REPO_ROOT / "data" / "options_expiry"
_OUT_DIR.mkdir(parents=True, exist_ok=True)

_UDIFF_URL = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{date}_F_0000.csv.zip"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

_OUR_INDEX_SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]

_OUT_COLUMNS = [
    "TradDt", "TckrSymb", "XpryDt", "StrkPric", "OptnTp",
    "OpnPric", "HghPric", "LwPric", "ClsPric", "SttlmPric",
    "OpnIntrst", "ChngInOpnIntrst", "TtlTradgVol", "UndrlygPric",
]


def load_stock_symbols() -> set:
    if not _SYMBOL_LIST.exists():
        raise FileNotFoundError(f"{_SYMBOL_LIST} missing")
    with open(_SYMBOL_LIST) as f:
        return {row["symbol"] for row in csv.DictReader(f)}


def _existing_dates_for(symbol: str) -> set:
    """Which TradDt values are already saved for this symbol — so a
    re-run only appends genuinely new days, never duplicates."""
    path = _OUT_DIR / f"{symbol}.csv"
    if not path.exists():
        return set()
    with open(path) as f:
        return {row["TradDt"] for row in csv.DictReader(f)}


def download_one_day(date_str: str, symbols: set) -> dict:
    """date_str: YYYYMMDD. Returns {symbol: [rows]} for rows matching our
    symbol set and OptnTp in (CE, PE) — futures and other symbols dropped."""
    url = _UDIFF_URL.format(date=date_str)
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    if resp.status_code == 404:
        return None  # genuinely no file for this date (holiday) — not an error
    resp.raise_for_status()

    by_symbol: dict = {}
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        inner_name = z.namelist()[0]
        with z.open(inner_name) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            for row in reader:
                sym = row.get("TckrSymb")
                optn = row.get("OptnTp")
                if sym not in symbols or optn not in ("CE", "PE"):
                    continue
                by_symbol.setdefault(sym, []).append({k: row.get(k) for k in _OUT_COLUMNS})
    return by_symbol


def append_rows(symbol: str, rows: list):
    path = _OUT_DIR / f"{symbol}.csv"
    write_header = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_OUT_COLUMNS)
        if write_header:
            w.writeheader()
        w.writerows(rows)


def main():
    if len(sys.argv) > 1:
        # Explicit date range: YYYYMMDD YYYYMMDD
        start = datetime.strptime(sys.argv[1], "%Y%m%d")
        end = datetime.strptime(sys.argv[2], "%Y%m%d") if len(sys.argv) > 2 else start
    else:
        end = datetime.now()
        start = end - timedelta(days=3 * 365)

    symbols = load_stock_symbols() | set(_OUR_INDEX_SYMBOLS)
    existing = {sym: _existing_dates_for(sym) for sym in symbols}

    day = start
    total_days_ok, total_days_skipped_holiday, total_days_skipped_existing = 0, 0, 0
    while day <= end:
        if day.weekday() >= 5:  # Saturday/Sunday — NSE never trades, skip without even trying
            day += timedelta(days=1)
            continue
        date_str = day.strftime("%Y%m%d")
        trad_dt_iso = day.strftime("%Y-%m-%d")

        # Skip only if EVERY symbol already has this date (partial coverage
        # from an interrupted earlier run still gets retried).
        if all(trad_dt_iso in existing.get(sym, set()) for sym in symbols):
            total_days_skipped_existing += 1
            day += timedelta(days=1)
            continue

        print(f"{date_str}...", end=" ", flush=True)
        try:
            by_symbol = download_one_day(date_str, symbols)
        except Exception as e:
            print(f"ERROR: {e}")
            day += timedelta(days=1)
            time.sleep(1)
            continue

        if by_symbol is None:
            print("no file (holiday)")
            total_days_skipped_holiday += 1
            day += timedelta(days=1)
            continue

        rows_written = 0
        for sym, rows in by_symbol.items():
            if trad_dt_iso in existing.get(sym, set()):
                continue
            append_rows(sym, rows)
            existing.setdefault(sym, set()).add(trad_dt_iso)
            rows_written += len(rows)
        print(f"OK, {len(by_symbol)} symbols, {rows_written} rows")
        total_days_ok += 1
        day += timedelta(days=1)
        time.sleep(1)  # be polite to NSE's archive server

    print(f"\nDone: {total_days_ok} days downloaded, "
          f"{total_days_skipped_holiday} holidays skipped, "
          f"{total_days_skipped_existing} already had data.")


if __name__ == "__main__":
    main()
