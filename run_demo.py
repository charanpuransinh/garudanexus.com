"""
run_demo.py
-----------
असली data/broker API के बिना पूरा pipeline टेस्ट करने के लिए — synthetic OHLCV data बनाकर
indicators -> rule_builder -> backtest_core -> my_strategies सब एक साथ चला के दिखाता है।

चलाओ: python run_demo.py
अगर यह बिना error के नंबर दिखा दे, तो मतलब पूरा सिस्टम सही जुड़ा हुआ है —
असली data_fetcher.py से data आने के बाद बस df बदलना है, बाकी सब वैसे ही चलेगा।
"""

import numpy as np
import pandas as pd

import config
import indicators as ind
import my_strategies as strat
import rule_builder as rb
from backtest_core import run_train_test, walk_forward_folds


def make_synthetic_ohlcv(n=3000, start="2018-01-01", freq="1D", seed=42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=n, freq=freq)
    returns = rng.normal(0.0003, 0.012, n)
    close = 1000 * np.cumprod(1 + returns)
    high = close * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.004, n)))
    open_ = close * (1 + rng.normal(0, 0.003, n))
    volume = rng.integers(1_00_000, 20_00_000, n)
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=dates)
    df.index.name = "datetime"
    return df


def main():
    print("1) Synthetic data बना रहा हूँ...")
    df = make_synthetic_ohlcv()
    print(f"   {len(df)} rows, {df.index.min().date()} → {df.index.max().date()}\n")

    print(f"2) indicators.py — कुल {len(ind.INDICATOR_REGISTRY)} indicators registry में मिले।")
    sample = list(ind.INDICATOR_REGISTRY)[:5]
    for name in sample:
        out = ind.compute(name, df)
        shape = out.shape if hasattr(out, "shape") else len(out)
        print(f"   {name:20s} ✓ output shape/len = {shape}")
    print()

    print("3) my_strategies.py — हर manual strategy पर train/test backtest:")
    for name, fn in strat.STRATEGY_REGISTRY.items():
        signal = fn(df)
        result = run_train_test(df, signal)
        print(f"\n   ▶ {name}")
        print(f"     train: {result['train']}")
        print(f"     test : {result['test']}")
        print(f"     {result['verdict']} (gap = {result['overfit_gap_win_rate_pts']} pts)")
    print()

    print("4) rule_builder.py — UI checkbox जैसी दो conditions जोड़कर टेस्ट:")
    rules = [
        {"indicator": "RSI", "params": {"period": 14}, "op": "<", "value": 35},
        {"indicator": "VolumeSpike", "params": {"period": 20, "mult": 1.5}, "op": "is_true"},
    ]
    ui_signal = rb.build_signal(df, rules)
    result = run_train_test(df, ui_signal)
    print(f"   train: {result['train']}")
    print(f"   test : {result['test']}")
    print(f"   {result['verdict']}\n")

    print("5) walk-forward folds (optimizer इसी पर भरोसा करेगा):")
    folds = walk_forward_folds(df, ui_signal, n_folds=4)
    for f in folds:
        print(f"   {f}")

    print("\n✅ पूरा pipeline synthetic data पर चल गया — असली data आने पर सिर्फ df बदलना है।")


if __name__ == "__main__":
    main()
