# Self-Healing System — सेटअप और इस्तेमाल

## 1. क्या जुड़ा

| फाइल | स्टेटस | काम |
|---|---|---|
| `self_healing.py` | 🆕 नई फाइल | पूरा system चलाकर जांचता है — folders, data, 50 indicators, backtest engine, sandbox |
| `api_server.py` | ✏️ थोड़ा बदली | नया endpoint `/api/self_check` जोड़ा + `/api/indicators` अब टूटे indicator अपने-आप छुपा देता है |
| `dashboard.html` | ✏️ बदली | नया tab **"3 · System Health"** — "Self-Check चलाओ" बटन, हर हिस्सा 🟢/🟡/🔴 मार्क के साथ |

पुराना कुछ नहीं छेड़ा — सिर्फ ऊपर से जोड़ा है। सारी फाइलें syntax-compile करके और असल में चलाकर टेस्ट भी कर ली हैं।

## 2. यह क्या-क्या जांचता है (हर बटन दबाने पर)

1. **Folders** — data/results folder मौजूद हैं या नहीं (ना हों तो खुद बना देता है)
2. **Data files** — sample symbols का data मिलता है, empty/corrupt तो नहीं (corrupt मिले तो हटा देता है)
3. **Indicators** — सारे 50 indicators को असल में एक sample data पर चलाकर देखता है — कोई crash करे या पूरा NaN दे तो उसे "टूटा" मानकर dashboard की checkbox-list से अस्थायी रूप से हटा देता है (जब तक कोड में कोई उसे ठीक ना करे)
4. **Backtest engine** — एक जानी-पहचानी strategy (RSI<40) चला कर देखता है कि win-rate/trades sensible निकल रहे हैं या नहीं
5. **Sandbox** — दो टेस्ट: (क) सही strategy code सही से चले, (ख) `import os` जैसा खतरनाक code सही से ब्लॉक हो — यह अपनी ही सुरक्षा को दोबारा जांचता है हर बार

## 3. जो अपने-आप ठीक होता है, और जो नहीं (ईमानदारी से)

**अपने-आप ठीक होता है:**
- Missing folders बन जाती हैं
- Corrupt/empty data फाइल हट जाती है
- टूटा हुआ indicator dashboard से अस्थायी रूप से छुप जाता है

**अपने-आप ठीक नहीं होता, सिर्फ लाल/पीला निशान लगाकर बताता है:**
- असली market data ना हो — क्योंकि data लाना (broker API/internet चाहिए) यह खुद नहीं कर सकता, सिर्फ बताएगा `python data_fetcher.py` चलाओ
- अगर backtest engine या sandbox का लॉजिक ही गलत निकल जाए — यह कोड की गलती है, इसे अपने-आप "ठीक" करना खतरनाक होगा (गलत चीज़ को खुद सही मान लेना, फिर strategy को गलती से "पास" दिखाना — इससे नुकसान ज़्यादा है)। ऐसे में सिर्फ लाल निशान देगा, इंसान को देखना होगा

## 4. Dashboard से इस्तेमाल

Tab **"3 · System Health"** खोलो → **"Self-Check चलाओ"** दबाओ → कुछ ही सेकंड में हर हिस्सा हरा/पीला/लाल दिखेगा, साथ में क्या समस्या है और क्या करना है वो भी लिखा मिलेगा।

## 5. रोज़ाना अपने-आप चलाने के लिए (असली मायने में "self-healing")

सिर्फ dashboard पर बटन दबाना ही काफ़ी नहीं — असली फ़ायदा तब है जब यह अपने-आप, बिना आपके याद रखे, हर कुछ देर में चलता रहे। इसके 2 तरीके:

### तरीका A — cron (सीधा, ज़्यादातर सर्वर पर पहले से मौजूद)
```
crontab -e
```
यह लाइन जोड़ो (हर 15 मिनट पर चलेगा):
```
*/15 * * * * cd /path/to/trading-bot && /usr/bin/python3 self_healing.py >> /path/to/trading-bot/results/self_healing_cron.log 2>&1
```

### तरीका B — pm2 (अगर आप पहले से pm2 इस्तेमाल कर रहे हो api_server के लिए)
```
pm2 start self_healing.py --interpreter python3 --cron "*/15 * * * *" --no-autorestart --name self-healer
```

दोनों तरीकों में हर run की history `results/self_healing_log.json` में जुड़ती जाती है (आख़िरी 50 runs), तो पीछे मुड़कर देख सकते हो कब-कब क्या खराब हुआ।

## 6. Alert चाहिए तो (आगे का कदम, अभी शामिल नहीं)

अभी यह सिर्फ log फाइल में लिखता है और लाल होने पर exit code 1 देता है — यह code आपको Telegram/WhatsApp/Email पर तुरंत मैसेज नहीं भेजता। अगर वो चाहिए (जैसे "लाल निशान आते ही मुझे Telegram पर मैसेज आए"), तो बताना — वो अगला छोटा सा हिस्सा जोड़ देंगे (cron script में सिर्फ एक Telegram API call जोड़नी होगी)।
