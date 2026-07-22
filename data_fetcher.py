"""
data_fetcher.py
----------------
OHLCV data डाउनलोड करके Parquet में स्टोर करता है, अगली बार सिर्फ नया data append करता है
(पूरा फिर से नहीं खींचता — resume/update दोनों संभालता है)।

डिफ़ॉल्ट source: yfinance (मुफ्त, पर intraday सिर्फ पिछले ~60 दिन देता है, इसलिए
पुराना intraday history चाहिए हो तो कोई paid vendor जोड़ना पड़ेगा — देखो PROJECT_BLUEPRINT.md)।
Broker API (Kite/Upstox) जोड़ना हो तो नीचे `fetch_from_broker()` भरना — बाकी pipeline वैसी ही रहेगी।

चलाने का तरीका:
    python data_fetcher.py --timeframe 1day --years 2018 2026
    python data_fetcher.py --timeframe 15min --symbol RELIANCE
"""

import argparse
from pathlib import Path

import pandas as pd

import config


# yfinance के लिए NSE symbols को ".NS" suffix चाहिए होता है
def _yf_symbol(row) -> str:
    if row["exchange"] == "NSE" and row["segment"] != "INDEX":
        return f"{row['symbol']}.NS"
    index_map = {
        "NIFTY 50": "^NSEI", "NIFTY BANK": "^NSEBANK",
        "SENSEX": "^BSESN",
    }
    return index_map.get(row["symbol"], row["symbol"])


def _parquet_path(symbol: str, timeframe: str) -> Path:
    safe = symbol.replace(" ", "_").replace("^", "")
    return config.DATA_DIR / f"{safe}__{timeframe}.parquet"


def fetch_from_broker(symbol: str, timeframe: str, start, end, broker: str = "fyers") -> pd.DataFrame:
    """broker_adapter.py के ज़रिए Fyers/Dhan से डेटा खींचता है (Shoonya/Kotak यहाँ नहीं चलेंगे —
    देखो broker_adapter.py के comments)। Broker configured नहीं है (env vars missing) या SDK call
    अभी नहीं भरी, तो BrokerNotConfigured/NotImplementedError उठेगा — caller (update_symbol) उसे
    पकड़कर yfinance पर fallback कर लेता है, तो pipeline कभी नहीं टूटता।"""
    import broker_adapter as ba
    return ba.fetch(broker, symbol=symbol, timeframe=timeframe, start=start, end=end)


def fetch_ohlcv(symbol: str, yf_symbol: str, timeframe: str, start: str, end: str) -> pd.DataFrame:
    import yfinance as yf

    interval_map = {"3min": "5m", "5min": "5m", "15min": "15m", "30min": "30m",
                     "1hour": "1h", "1day": "1d", "1week": "1wk"}
    interval = interval_map.get(timeframe, "1d")

    df = yf.download(yf_symbol, start=start, end=end, interval=interval, progress=False)
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        # नई yfinance versions single ticker पर भी (Price, Ticker) MultiIndex देती हैं —
        # flatten ना करें तो df["close"] जैसी हर जगह Series की जगह DataFrame मिलता है
        # और पूरी indicator pipeline चुपचाप टूट जाती है।
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    df.index.name = "datetime"
    return df


def update_symbol(symbol: str, yf_symbol: str, timeframe: str, year_start: int, year_end: int,
                   prefer_broker: str = None):
    path = _parquet_path(symbol, timeframe)
    start, end = f"{year_start}-01-01", f"{year_end}-12-31"

    if path.exists():
        existing = pd.read_parquet(path)
        last_date = existing.index.max()
        start = (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        if pd.Timestamp(start) >= pd.Timestamp(end):
            print(f"  {symbol}/{timeframe} पहले से up-to-date है।")
            return
    else:
        existing = pd.DataFrame()

    new_data = pd.DataFrame()
    if prefer_broker:
        try:
            new_data = fetch_from_broker(symbol, timeframe, start, end, broker=prefer_broker)
        except Exception as e:
            print(f"  {symbol}: {prefer_broker} से नहीं मिला ({e}) — yfinance पर fallback कर रहा हूँ")

    if new_data.empty:
        new_data = fetch_ohlcv(symbol, yf_symbol, timeframe, start, end)

    if new_data.empty:
        print(f"  {symbol}/{timeframe} — नया data नहीं मिला।")
        return

    combined = pd.concat([existing, new_data])
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    combined.to_parquet(path)
    print(f"  {symbol}/{timeframe} -> {len(combined)} rows स्टोर हो गईं ({path.name})")


def run(timeframe: str, year_range, symbol_filter=None, broker=None):
    universe = pd.read_csv(config.UNIVERSE_FILE)
    if symbol_filter:
        universe = universe[universe["symbol"] == symbol_filter]

    print(f"{len(universe)} symbols, timeframe={timeframe}, years={year_range}, broker={broker or 'yfinance'}")
    for _, row in universe.iterrows():
        yf_sym = _yf_symbol(row)
        try:
            update_symbol(row["symbol"], yf_sym, timeframe, year_range[0], year_range[1], prefer_broker=broker)
        except Exception as e:
            print(f"  ❌ {row['symbol']}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeframe", default=config.DEFAULT_TIMEFRAME, choices=list(config.TIMEFRAMES))
    parser.add_argument("--years", nargs=2, type=int, default=list(config.DEFAULT_YEAR_RANGE))
    parser.add_argument("--symbol", default=None, help="सिर्फ एक symbol update करना हो तो")
    parser.add_argument("--broker", default=None, choices=["fyers", "dhan"],
                         help="Env vars configured हों तो broker से डेटा लो, वरना yfinance पर auto-fallback")
    args = parser.parse_args()
    run(args.timeframe, tuple(args.years), args.symbol, args.broker)
