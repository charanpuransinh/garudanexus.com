# Backtesting Scanner — Setup

## 1) Install
```bash
pip install -r requirements.txt
```

## 2) पहले synthetic data पर टेस्ट करो (कोई internet/broker key नहीं चाहिए)
```bash
python run_demo.py
```
अगर यह बिना error के numbers दिखा दे — पूरा pipeline (indicators → rules → backtest) सही जुड़ा है।

## 3) असली data लाओ

**Update (2026-07-24): daily/options data अब blocked नहीं है — नीचे "Permanent historical
data pipeline" section देखो, वहाँ real 7-साल stock OHLC + 3-साल options data already है और
daily cron से खुद-ब-खुद refresh होता रहता है।** नीचे वाला `data_fetcher.py` flow पुराना/
alternative तरीका है, ऊपर वाला pipeline प्राथमिकता (authoritative) source है।

```bash
python data_fetcher.py --timeframe 1day --years 2018 2026
```
- Daily/weekly data yfinance से मिल जाएगा (मुफ्त)।
- **Intraday (3min–1hour) के लिए दिक्कत**: yfinance सिर्फ पिछले ~60 दिन का intraday देता है।
  पुराना intraday history चाहिए तो Kite Historical API / TrueData / Global Datafeeds जैसा
  paid vendor चाहिए होगा — अपना account/API-key चाहिए, `data_fetcher.py` में
  `fetch_from_broker()` को उसके हिसाब से भरना।

## 4) अपनी strategy बनाओ या UI-style rules टेस्ट करो
```python
import pandas as pd, my_strategies as strat
from backtest_core import run_train_test

df = pd.read_parquet("data/RELIANCE__1day.parquet")
signal = strat.example_rsi_supertrend(df)
result = run_train_test(df, signal)
print(result)
```

## 5) असली interactive Dashboard चलाओ
```bash
uvicorn api_server:app --host 0.0.0.0 --port 8090 --reload
```
फिर browser में `http://<server-ip>:8090` खोलो। यही dashboard checkbox टॉगल होते ही live
Train/Test win-rate, target/SL hit%, drawdown दिखाता है — साथ ही Auto-Optimizer भी वहीं से चलता है।

DigitalOcean पर PM2 से permanently चलाना हो तो:
```bash
pm2 start "uvicorn api_server:app --host 0.0.0.0 --port 8090" --name backtester-api
```

## 6) Auto-Optimizer अकेले भी चला सकते हो (बिना server के)
```bash
python optimizer.py --symbol RELIANCE --timeframe 1day --mode genetic
```

## 7) Files का status
`index.html` खोलो — Build Ledger में हर फाइल का live status दिखता है।

## Permanent historical data pipeline (`data/`)

Real (never fabricated) historical market data, permanently committed to
this repo — not just kept on the server — so the strategy tester and any
future backtest work always has a ready, current, version-controlled
dataset to read from.

| Path | Contents | Source | Range |
|---|---|---|---|
| `data/nifty100_symbols.csv` | NIFTY-100 constituent list: `symbol,company_name,industry,isin` | NSE official (`niftyindices.com`) | current constituents |
| `data/stock_daily/<SYMBOL>.csv` | Daily OHLCV: `date,open,high,low,close,volume` | Yahoo Finance (`yfinance`, `<SYMBOL>.NS`) | 7 years, one file per NIFTY-100 stock |
| `data/options_expiry/<SYMBOL>.csv` | Strike-wise CE/PE daily data: `TradDt,TckrSymb,XpryDt,StrkPric,OptnTp,OpnPric,HghPric,LwPric,ClsPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,UndrlygPric` | NSE official UDiFF Common Bhavcopy Final (`nsearchives.nseindia.com`) | 3 years, one file per NIFTY-100 stock + NIFTY/BANKNIFTY |

**Known gap**: SENSEX has no file in `data/options_expiry/` — SENSEX is
BSE-listed, so it never appears in NSE's bhavcopy. A BSE-specific source
would be needed to cover it; not built.

**How it stays current**: `scripts/daily_data_update.sh` runs every
weekday at 19:00 IST via the server's crontab (well after both market
close and NSE's bhavcopy publish time). It re-runs both downloaders
(`scripts/download_stock_daily.py`, `scripts/download_options_expiry.py`
— both idempotent, safe to re-run any time), then auto-commits and
auto-pushes any changed data via `scripts/auto_commit_push.sh`. **No
manual step is needed** — every commit in this repo (from this cron or
anyone working here) is auto-pushed by the version-controlled
`scripts/hooks/post-commit` hook (see `scripts/setup_git_hooks.sh` — run
once per fresh clone to activate it: `bash scripts/setup_git_hooks.sh`).

For "as of when" freshness, check the latest commit touching `data/`:
`git log -1 --format=%cd -- data/`.

## अगला कदम (अभी बाकी)
- `options_data_fetcher.py` — data source तय होने के बाद (paid vendor चाहिए)
- `broker_adapter.py` में Fyers/Dhan के असली SDK/REST call भरना — env vars सेट करके:
  `FYERS_APP_ID`, `FYERS_ACCESS_TOKEN`, `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN`
  फिर `python data_fetcher.py --broker fyers --timeframe 1day` — configured ना हो तो अपने-आप yfinance पर fallback हो जाता है, कभी नहीं टूटेगा।
- `news_fetcher.py` — अभी free RSS से headlines लाता है बिना key के। Sentiment चाहिए तो
  main backend के `gemini_client.py` से client object बनाकर `score_with_gemini(items, gemini_client=client)`
  में पास करो — देखो फाइल के comments में पूरा उदाहरण।
- Shoonya सिर्फ order-execution के लिए रहेगा (जैसा architecture में तय है) — data-feed के लिए इस्तेमाल मत करना, `broker_adapter.py` में जानबूझकर block किया है।
