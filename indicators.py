"""
indicators.py
-------------
50 इंडिकेटर — हर एक standalone function।
Input: df में कम-से-कम ये columns होने चाहिए -> open, high, low, close, volume (lowercase)
Output: pd.Series (single line indicator) या pd.DataFrame (multi-line जैसे MACD, Bollinger, Ichimoku)

नया indicator जोड़ना हो तो: 1) function लिखो  2) नीचे INDICATOR_REGISTRY में एंट्री डालो।
UI का checkbox grid इसी REGISTRY से बनता है, इसलिए यहीं की list ही "50 इंडिकेटर" की सच्चाई है।
"""

import numpy as np
import pandas as pd


# ---------------------------------------------------------------- helpers
def _tr(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    return pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


# ---------------------------------------------------------------- trend / MA family (1-7)
def SMA(df, period=20): return df["close"].rolling(period).mean()

def EMA(df, period=20): return _ema(df["close"], period)

def WMA(df, period=20):
    w = np.arange(1, period + 1)
    return df["close"].rolling(period).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)

def DEMA(df, period=20):
    e = _ema(df["close"], period)
    return 2 * e - _ema(e, period)

def TEMA(df, period=20):
    e1 = _ema(df["close"], period)
    e2 = _ema(e1, period)
    e3 = _ema(e2, period)
    return 3 * e1 - 3 * e2 + e3

def VWAP(df, reset_daily=True):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    if reset_daily and isinstance(df.index, pd.DatetimeIndex):
        day = df.index.date
        cum_pv = (tp * df["volume"]).groupby(day).cumsum()
        cum_v = df["volume"].groupby(day).cumsum()
    else:
        cum_pv = (tp * df["volume"]).cumsum()
        cum_v = df["volume"].cumsum()
    return cum_pv / cum_v.replace(0, np.nan)

def HullMA(df, period=20):
    half = max(int(period / 2), 1)
    sqrt_p = max(int(np.sqrt(period)), 1)
    wma_half = WMA(df, half)
    wma_full = WMA(df, period)
    raw = 2 * wma_half - wma_full
    return raw.rolling(sqrt_p).apply(lambda x: np.dot(x, np.arange(1, sqrt_p + 1)) / np.arange(1, sqrt_p + 1).sum(), raw=True)


# ---------------------------------------------------------------- momentum / oscillators (8-19)
def RSI(df, period=14):
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def Stochastic(df, k_period=14, d_period=3):
    low_k = df["low"].rolling(k_period).min()
    high_k = df["high"].rolling(k_period).max()
    k = 100 * (df["close"] - low_k) / (high_k - low_k).replace(0, np.nan)
    d = k.rolling(d_period).mean()
    return pd.DataFrame({"%K": k, "%D": d})

def StochRSI(df, period=14):
    rsi = RSI(df, period)
    low_rsi = rsi.rolling(period).min()
    high_rsi = rsi.rolling(period).max()
    return (rsi - low_rsi) / (high_rsi - low_rsi).replace(0, np.nan)

def MACD(df, fast=12, slow=26, signal=9):
    macd_line = _ema(df["close"], fast) - _ema(df["close"], slow)
    signal_line = _ema(macd_line, signal)
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": macd_line - signal_line})

def CCI(df, period=20):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    return (tp - sma) / (0.015 * mad.replace(0, np.nan))

def WilliamsR(df, period=14):
    high_p = df["high"].rolling(period).max()
    low_p = df["low"].rolling(period).min()
    return -100 * (high_p - df["close"]) / (high_p - low_p).replace(0, np.nan)

def MFI(df, period=14):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    mf = tp * df["volume"]
    pos_mf = mf.where(tp > tp.shift(1), 0).rolling(period).sum()
    neg_mf = mf.where(tp < tp.shift(1), 0).rolling(period).sum()
    ratio = pos_mf / neg_mf.replace(0, np.nan)
    return 100 - (100 / (1 + ratio))

def ROC(df, period=12): return 100 * (df["close"] - df["close"].shift(period)) / df["close"].shift(period)

def Momentum(df, period=10): return df["close"] - df["close"].shift(period)

def TSI(df, long=25, short=13):
    mom = df["close"].diff()
    ema1 = _ema(mom, long)
    ema2 = _ema(ema1, short)
    abs_ema1 = _ema(mom.abs(), long)
    abs_ema2 = _ema(abs_ema1, short)
    return 100 * ema2 / abs_ema2.replace(0, np.nan)

def UltimateOscillator(df, p1=7, p2=14, p3=28):
    prev_close = df["close"].shift(1)
    bp = df["close"] - pd.concat([df["low"], prev_close], axis=1).min(axis=1)
    tr = _tr(df)
    avg1 = bp.rolling(p1).sum() / tr.rolling(p1).sum()
    avg2 = bp.rolling(p2).sum() / tr.rolling(p2).sum()
    avg3 = bp.rolling(p3).sum() / tr.rolling(p3).sum()
    return 100 * (4 * avg1 + 2 * avg2 + avg3) / 7


# ---------------------------------------------------------------- trend strength / direction (20-25)
def ADX(df, period=14):
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = _tr(df).rolling(period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(period).mean() / tr.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(period).mean() / tr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.rolling(period).mean()

def AroonUp(df, period=25):
    return 100 * df["high"].rolling(period + 1).apply(lambda x: x.argmax(), raw=True) / period

def AroonDown(df, period=25):
    return 100 * df["low"].rolling(period + 1).apply(lambda x: x.argmin(), raw=True) / period

def DMI(df, period=14):
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = _tr(df).rolling(period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(period).mean() / tr.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(period).mean() / tr.replace(0, np.nan)
    return pd.DataFrame({"+DI": plus_di, "-DI": minus_di})

def ParabolicSAR(df, af_step=0.02, af_max=0.2):
    high, low = df["high"].values, df["low"].values
    sar = np.zeros(len(df)); trend = np.zeros(len(df)); ep = np.zeros(len(df)); af = np.zeros(len(df))
    trend[0] = 1; sar[0] = low[0]; ep[0] = high[0]; af[0] = af_step
    for i in range(1, len(df)):
        sar[i] = sar[i-1] + af[i-1] * (ep[i-1] - sar[i-1])
        if trend[i-1] == 1:
            trend[i] = 1 if low[i] > sar[i] else -1
        else:
            trend[i] = -1 if high[i] < sar[i] else 1
        if trend[i] == trend[i-1]:
            ep[i] = max(ep[i-1], high[i]) if trend[i] == 1 else min(ep[i-1], low[i])
            af[i] = min(af[i-1] + af_step, af_max) if ep[i] != ep[i-1] else af[i-1]
        else:
            ep[i] = high[i] if trend[i] == 1 else low[i]
            af[i] = af_step
            sar[i] = ep[i-1]
    return pd.Series(sar, index=df.index)

def SupertrendInd(df, period=10, multiplier=3.0):
    atr = _tr(df).rolling(period).mean()
    hl2 = (df["high"] + df["low"]) / 2
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr
    st = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=int)
    for i in range(len(df)):
        if i == 0:
            st.iloc[i] = upper.iloc[i]; direction.iloc[i] = 1
            continue
        if df["close"].iloc[i-1] > st.iloc[i-1]:
            st.iloc[i] = max(lower.iloc[i], st.iloc[i-1]) if direction.iloc[i-1] == 1 else lower.iloc[i]
            direction.iloc[i] = 1 if df["close"].iloc[i] > st.iloc[i] else -1
        else:
            st.iloc[i] = min(upper.iloc[i], st.iloc[i-1]) if direction.iloc[i-1] == -1 else upper.iloc[i]
            direction.iloc[i] = -1 if df["close"].iloc[i] < st.iloc[i] else 1
    return st


# ---------------------------------------------------------------- volatility / bands (26-30)
def BollingerBands(df, period=20, std_mult=2.0):
    mid = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    return pd.DataFrame({"upper": mid + std_mult * std, "mid": mid, "lower": mid - std_mult * std})

def KeltnerChannel(df, period=20, atr_mult=2.0):
    mid = _ema(df["close"], period)
    atr = _tr(df).rolling(period).mean()
    return pd.DataFrame({"upper": mid + atr_mult * atr, "mid": mid, "lower": mid - atr_mult * atr})

def DonchianChannel(df, period=20):
    return pd.DataFrame({"upper": df["high"].rolling(period).max(), "lower": df["low"].rolling(period).min()})

def ATR(df, period=14): return _tr(df).rolling(period).mean()

def StdDev(df, period=20): return df["close"].rolling(period).std()


# ---------------------------------------------------------------- volume family (31-35)
def OBV(df):
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum()

def VolumeSMA(df, period=20): return df["volume"].rolling(period).mean()

def VolumeSpike(df, period=20, mult=2.0):
    avg = df["volume"].rolling(period).mean()
    return df["volume"] > (mult * avg)

def CMF(df, period=20):
    mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / (df["high"] - df["low"]).replace(0, np.nan)
    mfv = mfm * df["volume"]
    return mfv.rolling(period).sum() / df["volume"].rolling(period).sum()

def ADLine(df):
    mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / (df["high"] - df["low"]).replace(0, np.nan)
    return (mfm * df["volume"]).fillna(0).cumsum()


# ---------------------------------------------------------------- more oscillators / structure (36-45)
def ForceIndex(df, period=13): return _ema(df["close"].diff() * df["volume"], period)

def PivotPoints(df):
    pivot = (df["high"].shift(1) + df["low"].shift(1) + df["close"].shift(1)) / 3
    r1 = 2 * pivot - df["low"].shift(1)
    s1 = 2 * pivot - df["high"].shift(1)
    return pd.DataFrame({"pivot": pivot, "r1": r1, "s1": s1})

def FibonacciRetrace(df, period=50):
    hi = df["high"].rolling(period).max()
    lo = df["low"].rolling(period).min()
    diff = hi - lo
    return pd.DataFrame({
        "0.236": hi - 0.236 * diff, "0.382": hi - 0.382 * diff,
        "0.5": hi - 0.5 * diff, "0.618": hi - 0.618 * diff,
    })

def Ichimoku(df, conv=9, base=26, span_b=52):
    conv_line = (df["high"].rolling(conv).max() + df["low"].rolling(conv).min()) / 2
    base_line = (df["high"].rolling(base).max() + df["low"].rolling(base).min()) / 2
    span_a = ((conv_line + base_line) / 2).shift(base)
    span_b_line = ((df["high"].rolling(span_b).max() + df["low"].rolling(span_b).min()) / 2).shift(base)
    return pd.DataFrame({"conversion": conv_line, "base": base_line, "span_a": span_a, "span_b": span_b_line})

def HeikinAshiTrend(df):
    ha_close = (df["open"] + df["high"] + df["low"] + df["close"]) / 4
    ha_open = ha_close.copy()
    for i in range(1, len(df)):
        ha_open.iloc[i] = (ha_open.iloc[i-1] + ha_close.iloc[i-1]) / 2
    return pd.Series(np.where(ha_close > ha_open, 1, -1), index=df.index)

def PSARFlip(df, af_step=0.02, af_max=0.2):
    sar = ParabolicSAR(df, af_step, af_max)
    trend = np.where(df["close"] > sar, 1, -1)
    return pd.Series(trend, index=df.index).diff().fillna(0) != 0

def TRIX(df, period=15):
    e1 = _ema(df["close"], period)
    e2 = _ema(e1, period)
    e3 = _ema(e2, period)
    return 100 * e3.pct_change()

def Vortex(df, period=14):
    vm_plus = (df["high"] - df["low"].shift(1)).abs().rolling(period).sum()
    vm_minus = (df["low"] - df["high"].shift(1)).abs().rolling(period).sum()
    tr_sum = _tr(df).rolling(period).sum()
    return pd.DataFrame({"VI+": vm_plus / tr_sum, "VI-": vm_minus / tr_sum})

def ElderRay(df, period=13):
    ema_line = _ema(df["close"], period)
    return pd.DataFrame({"bull_power": df["high"] - ema_line, "bear_power": df["low"] - ema_line})

def ChaikinOsc(df, fast=3, slow=10):
    ad = ADLine(df)
    return _ema(ad, fast) - _ema(ad, slow)


# ---------------------------------------------------------------- price structure (46-50)
def PriceChannel(df, period=20):
    return pd.DataFrame({"upper": df["close"].rolling(period).max(), "lower": df["close"].rolling(period).min()})

def RelativeVolume(df, period=20): return df["volume"] / df["volume"].rolling(period).mean()

def GapPercent(df): return 100 * (df["open"] - df["close"].shift(1)) / df["close"].shift(1)

def CandleBodyRatio(df):
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    return (df["close"] - df["open"]).abs() / rng

def HigherHighLowerLow(df, period=5):
    hh = df["high"] > df["high"].rolling(period).max().shift(1)
    ll = df["low"] < df["low"].rolling(period).min().shift(1)
    return pd.DataFrame({"higher_high": hh, "lower_low": ll})

def MarketProfile(df, bins=20):
    """हर bar के लिए उस दिन के price-range में volume किस bucket में सबसे ज़्यादा जमा हुआ (POC bucket index)."""
    def poc(group):
        prices = np.linspace(group["low"].min(), group["high"].max(), bins + 1)
        idx = np.digitize((group["high"] + group["low"]) / 2, prices) - 1
        vols = np.zeros(bins)
        for i, v in zip(idx, group["volume"]):
            if 0 <= i < bins:
                vols[i] += v
        return int(np.argmax(vols)) if vols.sum() > 0 else -1
    if isinstance(df.index, pd.DatetimeIndex):
        day = df.index.date
        values = df.groupby(day).apply(poc).reindex(day).values
        return pd.Series(values, index=df.index)
    return pd.Series(np.full(len(df), -1), index=df.index)


# ---------------------------------------------------------------- REGISTRY (UI checkbox grid इसी से बनता है)
INDICATOR_REGISTRY = {
    "SMA": {"func": SMA, "params": {"period": 20}},
    "EMA": {"func": EMA, "params": {"period": 20}},
    "WMA": {"func": WMA, "params": {"period": 20}},
    "DEMA": {"func": DEMA, "params": {"period": 20}},
    "TEMA": {"func": TEMA, "params": {"period": 20}},
    "VWAP": {"func": VWAP, "params": {"reset_daily": True}},
    "HullMA": {"func": HullMA, "params": {"period": 20}},
    "RSI": {"func": RSI, "params": {"period": 14}},
    "Stochastic": {"func": Stochastic, "params": {"k_period": 14, "d_period": 3}},
    "StochRSI": {"func": StochRSI, "params": {"period": 14}},
    "MACD": {"func": MACD, "params": {"fast": 12, "slow": 26, "signal": 9}},
    "CCI": {"func": CCI, "params": {"period": 20}},
    "WilliamsR": {"func": WilliamsR, "params": {"period": 14}},
    "MFI": {"func": MFI, "params": {"period": 14}},
    "ROC": {"func": ROC, "params": {"period": 12}},
    "Momentum": {"func": Momentum, "params": {"period": 10}},
    "TSI": {"func": TSI, "params": {"long": 25, "short": 13}},
    "UltimateOscillator": {"func": UltimateOscillator, "params": {"p1": 7, "p2": 14, "p3": 28}},
    "ADX": {"func": ADX, "params": {"period": 14}},
    "AroonUp": {"func": AroonUp, "params": {"period": 25}},
    "AroonDown": {"func": AroonDown, "params": {"period": 25}},
    "DMI": {"func": DMI, "params": {"period": 14}},
    "ParabolicSAR": {"func": ParabolicSAR, "params": {"af_step": 0.02, "af_max": 0.2}},
    "SupertrendInd": {"func": SupertrendInd, "params": {"period": 10, "multiplier": 3.0}},
    "BollingerBands": {"func": BollingerBands, "params": {"period": 20, "std_mult": 2.0}},
    "KeltnerChannel": {"func": KeltnerChannel, "params": {"period": 20, "atr_mult": 2.0}},
    "DonchianChannel": {"func": DonchianChannel, "params": {"period": 20}},
    "ATR": {"func": ATR, "params": {"period": 14}},
    "StdDev": {"func": StdDev, "params": {"period": 20}},
    "OBV": {"func": OBV, "params": {}},
    "VolumeSMA": {"func": VolumeSMA, "params": {"period": 20}},
    "VolumeSpike": {"func": VolumeSpike, "params": {"period": 20, "mult": 2.0}},
    "CMF": {"func": CMF, "params": {"period": 20}},
    "ADLine": {"func": ADLine, "params": {}},
    "ForceIndex": {"func": ForceIndex, "params": {"period": 13}},
    "PivotPoints": {"func": PivotPoints, "params": {}},
    "FibonacciRetrace": {"func": FibonacciRetrace, "params": {"period": 50}},
    "Ichimoku": {"func": Ichimoku, "params": {"conv": 9, "base": 26, "span_b": 52}},
    "HeikinAshiTrend": {"func": HeikinAshiTrend, "params": {}},
    "PSARFlip": {"func": PSARFlip, "params": {"af_step": 0.02, "af_max": 0.2}},
    "TRIX": {"func": TRIX, "params": {"period": 15}},
    "Vortex": {"func": Vortex, "params": {"period": 14}},
    "ElderRay": {"func": ElderRay, "params": {"period": 13}},
    "ChaikinOsc": {"func": ChaikinOsc, "params": {"fast": 3, "slow": 10}},
    "PriceChannel": {"func": PriceChannel, "params": {"period": 20}},
    "RelativeVolume": {"func": RelativeVolume, "params": {"period": 20}},
    "GapPercent": {"func": GapPercent, "params": {}},
    "CandleBodyRatio": {"func": CandleBodyRatio, "params": {}},
    "HigherHighLowerLow": {"func": HigherHighLowerLow, "params": {"period": 5}},
    "MarketProfile": {"func": MarketProfile, "params": {"bins": 20}},
}

assert len(INDICATOR_REGISTRY) == 50, "Registry में ठीक 50 indicators होने चाहिए"


def compute(name: str, df: pd.DataFrame, **override_params):
    """किसी भी registry नाम से indicator चला दो, params override कर सकते हो।"""
    entry = INDICATOR_REGISTRY[name]
    params = {**entry["params"], **override_params}
    return entry["func"](df, **params)
