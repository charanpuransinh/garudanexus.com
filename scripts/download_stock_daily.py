"""
download_stock_daily.py — NIFTY 100 stocks, 7-year daily OHLC via Yahoo
Finance (yfinance). Saves one CSV per symbol into data/stock_daily/.

Real data only — no mock/placeholder rows. A symbol that genuinely fails
to download (delisted, renamed, Yahoo mismatch) is skipped and logged,
never filled with fake values.

Usage:
  python3 download_stock_daily.py                 # all NIFTY 100
  python3 download_stock_daily.py RELIANCE TCS     # just these symbols
"""
import sys
import time
import csv
from pathlib import Path

import yfinance as yf

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SYMBOL_LIST = _REPO_ROOT / "data" / "nifty100_symbols.csv"
_OUT_DIR = _REPO_ROOT / "data" / "stock_daily"
_OUT_DIR.mkdir(parents=True, exist_ok=True)

PERIOD = "7y"
INTERVAL = "1d"


def load_symbols() -> list:
    if not _SYMBOL_LIST.exists():
        raise FileNotFoundError(f"{_SYMBOL_LIST} missing — run build_nifty100_symbol_list.py first")
    with open(_SYMBOL_LIST) as f:
        return [row["symbol"] for row in csv.DictReader(f)]


def download_one(symbol: str) -> bool:
    yahoo_symbol = f"{symbol}.NS"
    try:
        df = yf.download(yahoo_symbol, period=PERIOD, interval=INTERVAL,
                          progress=False, auto_adjust=False)
    except Exception as e:
        print(f"  [FAIL] {symbol}: {e}")
        return False
    if df is None or df.empty:
        print(f"  [FAIL] {symbol}: no data returned")
        return False

    # yfinance returns a MultiIndex column (Price, Ticker) for a single-symbol
    # download in recent versions — flatten to plain OHLCV columns.
    if isinstance(df.columns, __import__("pandas").MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index()
    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
    df.columns = ["date", "open", "high", "low", "close", "volume"]
    out_path = _OUT_DIR / f"{symbol}.csv"
    df.to_csv(out_path, index=False)
    print(f"  [OK] {symbol}: {len(df)} rows -> {out_path.name} "
          f"({df['date'].min()} to {df['date'].max()})")
    return True


def main():
    symbols = sys.argv[1:] if len(sys.argv) > 1 else load_symbols()
    print(f"Downloading {len(symbols)} symbols, period={PERIOD}, interval={INTERVAL}")
    ok, failed = 0, []
    for i, sym in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] {sym}")
        if download_one(sym):
            ok += 1
        else:
            failed.append(sym)
        time.sleep(0.5)  # be polite to Yahoo's endpoint, avoid rate-limit blocks
    print(f"\nDone: {ok}/{len(symbols)} succeeded.")
    if failed:
        print(f"Failed ({len(failed)}): {failed}")


if __name__ == "__main__":
    main()
