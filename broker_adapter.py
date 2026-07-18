"""
broker_adapter.py
------------------
तुम्हारे Trishul Pro Master वाले broker architecture से match करने के लिए:
  - Fyers, Dhan  -> DATA-FEED brokers (historical OHLCV, options chain) — यही backtester इस्तेमाल करेगा
  - Shoonya      -> ORDER-EXECUTION ONLY, यहाँ historical data fetch नहीं करते (connection dedicated रखने के लिए,
                    जैसा main backend में तय हुआ है) — इसलिए इस फाइल में सिर्फ placeholder है, इस्तेमाल मत करना
  - Kotak        -> अभी excluded, API pending

data_fetcher.py का fetch_from_broker() यहीं की functions को कॉल करेगा। असली API keys env vars से आएँगी —
कोई key यहाँ hardcode मत करना।

Env vars जो चाहिए होंगे (server पर set करना, इसी नाम से — main backend वाले नाम से मेल खाते हैं):
    FYERS_APP_ID, FYERS_ACCESS_TOKEN
    DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN
"""

import os
from datetime import datetime

import pandas as pd


class BrokerNotConfigured(Exception):
    """API key env var सेट नहीं है — caller को yfinance पर fallback करने का संकेत।"""


# ---------------------------------------------------------------- Fyers (DATA-FEED)
def fetch_fyers_historical(symbol: str, timeframe: str, start: str, end: str, exchange: str = "NSE") -> pd.DataFrame:
    """Fyers History API से OHLCV लाता है। असली production में यहाँ tumhare main backend
    वाला fyers_client (SDK: fyers-apiv3) reuse करना — यहाँ सिर्फ interface fix किया है ताकि
    data_fetcher.py बाकी pipeline बिना बदले चला सके।

    Resolution mapping Fyers docs के हिसाब से: 1,5,15,30,60 मिनट या D (day)।
    """
    app_id = os.environ.get("FYERS_APP_ID")
    token = os.environ.get("FYERS_ACCESS_TOKEN")
    if not app_id or not token:
        raise BrokerNotConfigured("FYERS_APP_ID / FYERS_ACCESS_TOKEN env var सेट नहीं है")

    resolution_map = {"3min": "3", "5min": "5", "15min": "15", "30min": "30",
                       "1hour": "60", "1day": "D", "1week": "D"}
    resolution = resolution_map.get(timeframe, "D")

    # TODO: असली call यहाँ आएगी, जैसे:
    #   from fyers_apiv3 import fyersModel
    #   fyers = fyersModel.FyersModel(client_id=app_id, token=token, is_async=False)
    #   data = {"symbol": f"{exchange}:{symbol}-EQ", "resolution": resolution,
    #           "date_format": "1", "range_from": start, "range_to": end, "cont_flag": "1"}
    #   resp = fyers.history(data)
    #   candles = resp["candles"]  # [ts, open, high, low, close, volume]
    raise NotImplementedError(
        "Fyers SDK call यहाँ भरो — main backend के fyers_client.py से पैटर्न कॉपी कर सकते हो"
    )


# ---------------------------------------------------------------- Dhan (DATA-FEED)
def fetch_dhan_historical(symbol: str, timeframe: str, start: str, end: str, security_id: str = None) -> pd.DataFrame:
    """Dhan Historical Data API से OHLCV लाता है (cross-verification के लिए Fyers के साथ इस्तेमाल होगा,
    जैसा तुम्हारे data-feed architecture में तय है)।"""
    client_id = os.environ.get("DHAN_CLIENT_ID")
    token = os.environ.get("DHAN_ACCESS_TOKEN")
    if not client_id or not token:
        raise BrokerNotConfigured("DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN env var सेट नहीं है")

    # TODO: असली Dhan REST call:
    #   POST https://api.dhan.co/charts/historical
    #   headers = {"access-token": token, "client-id": client_id}
    #   body = {"securityId": security_id, "exchangeSegment": "NSE_EQ", "instrument": "EQUITY",
    #           "fromDate": start, "toDate": end}
    raise NotImplementedError(
        "Dhan REST call यहाँ भरो — main backend के dhan_client.py से पैटर्न कॉपी कर सकते हो"
    )


# ---------------------------------------------------------------- Shoonya — जानबूझकर NOT IMPLEMENTED
def fetch_shoonya_historical(*args, **kwargs):
    """Shoonya सिर्फ ORDER EXECUTION के लिए है (तुम्हारे architecture में connection dedicated रखने
    के लिए data-feed वहाँ से नहीं लेते) — इसलिए यह function जानबूझकर काम नहीं करता।
    Historical data के लिए हमेशा fetch_fyers_historical / fetch_dhan_historical इस्तेमाल करो।"""
    raise BrokerNotConfigured(
        "Shoonya data-feed के लिए इस्तेमाल नहीं होता (architecture rule) — Fyers या Dhan इस्तेमाल करो"
    )


# ---------------------------------------------------------------- Kotak — pending
def fetch_kotak_historical(*args, **kwargs):
    raise BrokerNotConfigured("Kotak API अभी pending है (जैसा project में तय है)")


# ---------------------------------------------------------------- router
BROKER_FUNCS = {
    "fyers": fetch_fyers_historical,
    "dhan": fetch_dhan_historical,
    "shoonya": fetch_shoonya_historical,
    "kotak": fetch_kotak_historical,
}


def fetch(broker: str, **kwargs) -> pd.DataFrame:
    """data_fetcher.py यहीं से बुलाएगा: broker_adapter.fetch('fyers', symbol=..., ...)"""
    if broker not in BROKER_FUNCS:
        raise ValueError(f"अनजान broker: {broker}. विकल्प: {list(BROKER_FUNCS)}")
    return BROKER_FUNCS[broker](**kwargs)


def cross_verify(fyers_df: pd.DataFrame, dhan_df: pd.DataFrame, tolerance_pct: float = 0.1) -> dict:
    """तुम्हारे architecture में Fyers+Dhan दोनों cross-verify होते हैं — दोनों का close mismatch
    tolerance से ज़्यादा हो तो flag करता है (bad tick / broker glitch पकड़ने के लिए)।"""
    merged = pd.merge(
        fyers_df[["close"]].rename(columns={"close": "fyers_close"}),
        dhan_df[["close"]].rename(columns={"close": "dhan_close"}),
        left_index=True, right_index=True, how="inner",
    )
    if merged.empty:
        return {"matched_rows": 0, "mismatches": 0, "mismatch_pct": 0.0}

    diff_pct = 100 * (merged["fyers_close"] - merged["dhan_close"]).abs() / merged["fyers_close"]
    mismatches = int((diff_pct > tolerance_pct).sum())
    return {
        "matched_rows": len(merged),
        "mismatches": mismatches,
        "mismatch_pct": round(100 * mismatches / len(merged), 2),
        "flagged_timestamps": merged.index[diff_pct > tolerance_pct].tolist(),
    }
