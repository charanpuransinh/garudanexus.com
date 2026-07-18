# Backtesting Scanner — Project Blueprint

## लक्ष्य (Goal)
एक interactive backtesting scanner जिसमें:
- 50+ indicators को checkbox से ON/OFF किया जा सके
- Timeframe चुना जा सके: 3min से लेकर 1 दिन, और 1 week तक
- Index / Stock अलग-अलग टॉगल हो सके
- Year range: 2018–2026
- Options data भी शामिल हो (strike, expiry, OI, IV, Greeks)
- हर टॉगल बदलते ही नया Accuracy/Win-Rate/Target-Hit% result दिखे
- मैनुअल (खुद की) strategy logic भी डाल सकें
- Auto-optimizer भी हो जो खुद अच्छा combination ढूंढे (overfitting से बचाकर)

## समस्या जो solve करनी है
पुराने attempts में हर बार दोबारा कोड लिखना पड़ता था और accuracy फिर भी 40% से कम आती थी।
मुख्य कारण अक्सर **overfitting** (एक ही data पर test करके अच्छा दिखने वाला combo चुन लेना) होता है।
इसलिए backtest engine में **Train/Test split (जैसे 2018–2023 train, 2024–2026 test)** जरूरी रखा जाएगा।

## System Architecture (6 Layers)

1. **Data Layer** — OHLCV + Options data (Parquet/DuckDB में स्टोर)
2. **Indicator Library** — हर indicator अलग function, parameters adjustable
3. **Strategy Layer** — मैनुअल logic (तुम्हारा) + UI से बने combinations, दोनों एक फॉर्मेट में
4. **Backtest Engine** — कोई भी strategy चलाकर Win rate, Accuracy, Target/SL hit %, Drawdown निकाले
5. **Optimizer (Auto)** — Grid search / Genetic algorithm, walk-forward validation के साथ, टॉप combos rank करके दे
6. **Dashboard (UI)** — Checkbox grid (50 indicators), Timeframe dropdown, Stock/Index toggle, Year slider, Run button, Result panel + chart

## Files की Final List

| फाइल | काम | Status |
|---|---|---|
| `config.py` | Settings: timeframe list, date range, symbols path | बनना बाकी |
| `universe.csv` | Index + Stock symbol lists (अलग कॉलम) | तुम्हें भरनी होगी |
| `data_fetcher.py` | OHLCV data डाउनलोड/update | बनना बाकी |
| `options_data_fetcher.py` | Options historical data (strike/expiry/OI/IV) | बनना बाकी — इसके लिए data source चाहिए (नीचे नोट देखें) |
| `indicators.py` | 50+ indicators library | **बना दिया — नीचे देखें** |
| `my_strategies.py` | तुम्हारा manual logic रखने की जगह | बनना बाकी |
| `rule_builder.py` | UI combinations से strategy बनाना | बनना बाकी |
| `backtest_core.py` | Backtest engine (train/test split सहित) | **बना दिया** |
| `optimizer.py` | Auto grid/genetic search, walk-forward scoring | **बना दिया** |
| `api_server.py` | FastAPI backend (`/api/backtest`, `/api/optimize`) | **बना दिया** |
| `dashboard.html` | Checkbox grid UI, live result panel, optimizer panel | **बना दिया** |
| `requirements.txt` | Dependencies | **बना दिया** |
| `README.md` | Setup/run instructions | बाद में |

## बाहरी मदद कहाँ चाहिए होगी (जो मैं नहीं दे सकता)
- **Options historical data**: फ्री सोर्स सीमित हैं। विकल्प:
  - NSE की bhavcopy archives (मुफ्त, पर raw/messy, खुद क्लीन करना पड़ेगा)
  - Paid vendors: TrueData, Global Datafeeds, Sensibull API, Kite Historical API (Zerodha) — इनमें से किसी की जरूरत पड़ेगी, अकाउंट/subscription तुम्हें खुद लेनी होगी
- **Broker API keys** (अगर live/historical data चाहिए) — Zerodha Kite, Upstox आदि — तुम्हारा अपना अकाउंट चाहिए होगा
- **GitHub repo**: तुम push करोगे जैसा प्लान बताया, मैं फाइलें बनाकर दूंगा

## अगला कदम
1. `indicators.py` — 50 indicators (हो गया)
2. `config.py` + `requirements.txt` (हो गया)
3. `backtest_core.py` — engine + train/test split (हो गया)
4. `my_strategies.py` / `rule_builder.py` (हो गया)
5. `optimizer.py` — grid + genetic search (हो गया)
6. `api_server.py` + `dashboard.html` — live interactive UI (हो गया)
7. **बाकी**: असली data लाना (`data_fetcher.py` चलाना), फिर Shoonya/Dhan/Fyers broker hook जोड़ना, फिर `options_data_fetcher.py` (data source तय होने पर)
