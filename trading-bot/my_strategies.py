"""
my_strategies.py
------------------
यहाँ तुम्हारी अपनी (हाथ से सोची हुई) strategies रहेंगी।
हर strategy एक function है: df लेकर एक boolean entry-signal (pd.Series) लौटाए —
यही format rule_builder.py वाली UI strategies का भी है, इसलिए backtest_core.py दोनों
को बिना फ़र्क़ किए चला सकता है।

नई strategy जोड़ने का तरीका नीचे example देख कर करो, फिर STRATEGY_REGISTRY में जोड़ दो।
"""

import pandas as pd

import indicators as ind


def example_rsi_supertrend(df: pd.DataFrame) -> pd.Series:
    """उदाहरण: RSI oversold (<30) + Supertrend का trend ऊपर की तरफ हो तभी entry।"""
    rsi = ind.compute("RSI", df, period=14)
    st = ind.compute("SupertrendInd", df)
    uptrend = df["close"] > st
    return (rsi < 30) & uptrend


def example_ema_crossover_volume(df: pd.DataFrame) -> pd.Series:
    """उदाहरण: EMA20 EMA50 के ऊपर cross करे + उसी bar में volume spike भी हो।"""
    ema20 = ind.compute("EMA", df, period=20)
    ema50 = ind.compute("EMA", df, period=50)
    cross_above = (ema20.shift(1) <= ema50.shift(1)) & (ema20 > ema50)
    vol_spike = ind.compute("VolumeSpike", df)
    return cross_above & vol_spike


def example_bollinger_meanreversion(df: pd.DataFrame) -> pd.Series:
    """उदाहरण: close, lower Bollinger band से नीचे बंद हो (mean-reversion entry)।"""
    bb = ind.compute("BollingerBands", df, period=20, std_mult=2.0)
    return df["close"] < bb["lower"]


# --------------------------------------------------------------------
# 👇 अपनी strategy यहाँ नीचे जोड़ते जाओ, इस पैटर्न में:
#
# def my_new_strategy(df):
#     cond1 = ...
#     cond2 = ...
#     return cond1 & cond2
# --------------------------------------------------------------------


STRATEGY_REGISTRY = {
    "rsi_supertrend": example_rsi_supertrend,
    "ema_crossover_volume": example_ema_crossover_volume,
    "bollinger_meanreversion": example_bollinger_meanreversion,
}
