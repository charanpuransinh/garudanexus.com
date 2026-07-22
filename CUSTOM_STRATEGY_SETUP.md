# नया क्या जुड़ा — और कहाँ रखना है

## 1. क्या-क्या बदला/जुड़ा

| फाइल | स्टेटस | काम |
|---|---|---|
| `strategy_sandbox.py` | 🆕 **नई फाइल** | पेस्ट किया कोड safe तरीके से चलाता है (अलग process, timeout, खतरनाक imports ब्लॉक) |
| `api_server.py` | ✏️ **बदली** | सिर्फ जोड़ा गया — `/api/custom_backtest` नया endpoint, कोई पुराना endpoint नहीं छेड़ा |
| `dashboard.html` | ✏️ **बदली** | 2 tabs अब — "Indicator Scanner" (पुराना) और "Custom Strategy Tester" (नया, code-paste box) |
| बाकी सारी फाइलें | ❌ बिल्कुल नहीं बदलीं | `backtest_core.py`, `indicators.py`, `config.py`, `data_fetcher.py`, वगैरह जस की तस |

**सर्वर टूटने की चिंता:** पुराने किसी endpoint या function को हाथ नहीं लगाया — सिर्फ नई चीज़ें ऊपर से जोड़ी हैं। मैंने सारी `.py` फाइलों को syntax-compile करके भी चेक कर लिया है, और नए sandbox module को असली strategy code, malicious code (जैसे `import os`), और infinite loop — तीनों पर टेस्ट करके देखा है, तीनों सही से handle हुए।

## 2. फोल्डर स्ट्रक्चर — कहाँ डालना है

आपके सर्वर पर जहाँ अभी `trading-bot/` फोल्डर है (जैसे `garudanexus.com/trading-bot/`), वहीं इन तीनों फाइलों को रखना है — **उसी लेवल पर जहाँ `api_server.py` और `dashboard.html` पहले से हैं**, किसी sub-folder में नहीं:

```
trading-bot/
├── api_server.py          ← बदली हुई (overwrite करो)
├── dashboard.html          ← बदली हुई (overwrite करो)
├── strategy_sandbox.py     ← नई (डालो)
├── backtest_core.py        ← मत छेड़ो
├── indicators.py           ← मत छेड़ो
├── config.py                ← मत छेड़ो
├── ... (बाकी सब वैसी की वैसी)
```

## 3. Deploy करने का तरीका (step-by-step)

1. **पहले backup लो** — सर्वर पर मौजूदा `api_server.py` और `dashboard.html` को कहीं और कॉपी कर लो (जैसे `api_server.py.bak`), ताकि कुछ गलत हो तो तुरंत वापस लगा सको।
2. तीनों नई/बदली फाइलें अपलोड करो (SCP/SFTP से, या GitHub से push-pull से — जैसा आप पहले करते आए हो)।
3. सर्वर पर app को restart करो:
   ```
   pm2 restart backtester-api
   ```
   (या जो भी कमांड आप पहले इस्तेमाल करते थे — README.md में लिखा तरीका वही है)
4. Browser में dashboard खोलो — ऊपर 2 tabs दिखेंगे: **"1 · Indicator Scanner"** (पुराना वाला) और **"2 · Custom Strategy Tester"** (नया)।
5. दूसरे tab में जाकर टेस्ट करो — डिफ़ॉल्ट रूप से एक sample strategy code पहले से भरा हुआ है, सीधे "Strategy Test करो" दबाकर देख सकते हो कि सब काम कर रहा है।

## 4. अगर कुछ गलत हो जाए (rollback)

अगर restart के बाद साइट ना खुले या error आए:
1. Backup ली हुई पुरानी `api_server.py` और `dashboard.html` वापस रख दो
2. `strategy_sandbox.py` को हटा दो (उसका इस्तेमाल सिर्फ नए endpoint में होता है, हटाने से पुराना कुछ नहीं टूटेगा)
3. सर्वर restart करो — साइट वापस पहले जैसी काम करने लगेगी

## 5. Custom Strategy Tester कैसे इस्तेमाल करें

- कोड इस पैटर्न में लिखो:
  ```python
  def my_strategy(df):
      rsi = ind.compute("RSI", df, period=14)
      ema20 = ind.compute("EMA", df, period=20)
      return (rsi < 30) & (df["close"] > ema20)
  ```
- सिर्फ `pd` (pandas), `np` (numpy), `ind` (आपकी indicators.py) इस्तेमाल हो सकते हैं — कुछ और import करने की कोशिश करोगे तो साफ़ error आएगा, सर्वर नहीं टूटेगा
- Result वही मिलेगा जो checkbox वाली strategy पर मिलता है — Train/Test win-rate, target-hit%, SL-hit%, timeout%, avg return, max drawdown, और overfit-check

## 6. ईमानदारी से एक सीमा बता दूं

`strategy_sandbox.py` एक code-level सुरक्षा है (खतरनाक imports/patterns रोकना + अलग process + timeout) — यह आपके अपने इस्तेमाल के लिए काफ़ी है। लेकिन अगर कभी यह dashboard पूरी तरह अनजान/public लोगों के लिए खोलना हो (जहाँ कोई भी बाहर वाला कोड पेस्ट कर सके), तो उसके लिए असली Docker-container-level isolation चाहिए होगा — वो अगला कदम होगा, अभी नहीं जोड़ा है।
