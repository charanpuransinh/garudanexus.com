"""
news_fetcher.py
----------------
Market news headlines लाता है (free RSS sources — NSE/BSE announcements, Economic Times,
Moneycontrol) और चाहो तो Gemini से sentiment-score करवा सकते हो — तुम्हारे main backend में
`gemini_client.py` पहले से deployed है, वहीं से reuse हो सकता है (यहाँ standalone stub दिया है
ताकि इस repo के अंदर बिना main backend पर depend किए test हो सके)।

इस्तेमाल कहाँ होगा:
  - Backtest में एक नया "News Sentiment" filter जोड़ने के लिए (जैसे: बड़ी negative news वाले दिन
    trade स्किप करना) — rule_builder में indicator जैसे ही जोड़ सकते हो, बस df में एक news_sentiment
    column merge करना होगा।
  - Dashboard के "Command Center" (Niyantran Kaksh) वाले News box के लिए।

चलाओ (standalone टेस्ट):
    python news_fetcher.py --symbol RELIANCE
"""

import argparse
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import pandas as pd
import requests

# free, key-less RSS feeds — कोई paid news API key नहीं चाहिए इसके लिए
RSS_FEEDS = {
    "moneycontrol_markets": "https://www.moneycontrol.com/rss/marketreports.xml",
    "economictimes_markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "business_standard_markets": "https://www.business-standard.com/rss/markets-106.rss",
}


@dataclass
class NewsItem:
    title: str
    source: str
    published: Optional[str]
    link: str
    sentiment: Optional[str] = None   # "positive" / "negative" / "neutral" — Gemini से भरेगा
    sentiment_score: Optional[float] = None  # -1..+1


def _parse_rss(xml_text: str, source: str) -> List[NewsItem]:
    """खुद का lightweight RSS parser — कोई extra dependency (feedparser) नहीं चाहिए।
    requirements.txt में feedparser जोड़ना हो तो और साफ़ parsing हो सकती है, अभी regex काफी है।"""
    items = []
    for block in re.findall(r"<item>(.*?)</item>", xml_text, re.S):
        title_m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, re.S)
        link_m = re.search(r"<link>(.*?)</link>", block, re.S)
        date_m = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        title = title_m.group(1).strip() if title_m else ""
        link = link_m.group(1).strip() if link_m else ""
        published = date_m.group(1).strip() if date_m else None
        if title:
            items.append(NewsItem(title=title, source=source, published=published, link=link))
    return items


def fetch_market_news(timeout: int = 8) -> List[NewsItem]:
    """सारे RSS feeds से headlines इकट्ठा करता है। कोई एक feed fail हो तो बाकी चलते रहें
    (एक news source down होने से पूरा pipeline ना रुके)।"""
    all_items = []
    for source, url in RSS_FEEDS.items():
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            all_items.extend(_parse_rss(resp.text, source))
        except Exception as e:
            print(f"  ⚠️ {source} से news नहीं मिली: {e}")
    return all_items


def filter_for_symbol(items: List[NewsItem], symbol: str) -> List[NewsItem]:
    """headline में company/symbol नाम ढूंढता है — बहुत basic keyword match है,
    असली NER/company-alias mapping चाहिए हो तो Gemini से भी करवा सकते हो (नीचे score_with_gemini देखो)।"""
    key = symbol.replace("NIFTY", "Nifty").replace("_", " ").lower()
    return [it for it in items if key in it.title.lower()]


def score_with_gemini(items: List[NewsItem], gemini_client=None) -> List[NewsItem]:
    """तुम्हारे मौजूदा `gemini_client.py` (main backend, /root/trishul-pro/server/) से यहाँ इंस्टेंस
    पास करो तो हर headline को positive/negative/neutral + score मिल जाएगा।

    Backtester repo अकेले खड़ा हो सके, इसलिए gemini_client यहाँ import नहीं किया — caller अपने
    backend से client object बनाकर पास करे, जैसे:

        import sys; sys.path.append("/root/trishul-pro/server")
        from gemini_client import GeminiClient
        client = GeminiClient()
        scored = score_with_gemini(items, gemini_client=client)

    client ना दो तो यह function items को बिना sentiment के वैसे ही लौटा देता है (कोई crash नहीं)।
    """
    if gemini_client is None:
        return items
    for it in items:
        try:
            # असली backend में gemini_client का जो भी method structured JSON देता है वो यहाँ कॉल करो,
            # जैसे: result = gemini_client.classify_sentiment(it.title)
            result = gemini_client.classify_sentiment(it.title)  # noqa: यह method backend में बनाना/मैप करना होगा
            it.sentiment = result.get("sentiment")
            it.sentiment_score = result.get("score")
        except Exception as e:
            print(f"  ⚠️ sentiment fail for '{it.title[:40]}...': {e}")
    return items


def news_to_daily_signal(items: List[NewsItem], index: pd.DatetimeIndex) -> pd.Series:
    """Backtest df के साथ merge करने लायक daily sentiment series बनाता है —
    हर दिन का average sentiment_score, news ना हो उस दिन 0 (neutral)। rule_builder में इस्तेमाल
    करने के लिए df में एक कॉलम की तरह जोड़ सकते हो: df['news_sentiment'] = news_to_daily_signal(...)
    """
    if not items:
        return pd.Series(0.0, index=index)

    rows = []
    for it in items:
        if it.published and it.sentiment_score is not None:
            try:
                dt = pd.to_datetime(it.published, utc=True, errors="coerce")
                if pd.notna(dt):
                    rows.append({"date": dt.date(), "score": it.sentiment_score})
            except Exception:
                continue
    if not rows:
        return pd.Series(0.0, index=index)

    daily = pd.DataFrame(rows).groupby("date")["score"].mean()
    dates = pd.Series(index.date, index=index)
    return dates.map(daily).fillna(0.0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None, help="सिर्फ एक symbol की news filter करनी हो तो")
    args = parser.parse_args()

    print("Market news खींच रहा हूँ (free RSS feeds)...")
    items = fetch_market_news()
    print(f"कुल {len(items)} headlines मिलीं")

    if args.symbol:
        items = filter_for_symbol(items, args.symbol)
        print(f"'{args.symbol}' से जुड़ी {len(items)} headlines:")

    for it in items[:15]:
        print(f"  [{it.source}] {it.title}")

    print("\nSentiment scoring के लिए gemini_client पास करना होगा (देखो score_with_gemini() का docstring)।")
