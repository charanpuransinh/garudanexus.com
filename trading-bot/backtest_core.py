"""
backtest_core.py
-----------------
कोई भी strategy (entry signal) ले कर चलाता है और निकालता है:
  win_rate, accuracy, target_hit_pct, sl_hit_pct, avg_return, max_drawdown

Overfitting रोकने का तरीका: हर बार train और test दोनों पर अलग-अलग result मिलता है,
सिर्फ train वाला result देखकर strategy मत चुनना — असली भरोसा test वाले नंबर पर करना
(config.TRAIN_TEST_SPLIT_DATE डिफ़ॉल्ट cutoff है)।
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import config


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    total_trades: int
    win_rate: float          # % trades जो profit में बंद हुईं
    target_hit_pct: float    # % trades जिनमें target लगा
    sl_hit_pct: float        # % trades जिनमें stoploss लगा
    timeout_pct: float       # % trades जो max_hold_bars तक ना target ना SL — timeout पर बंद हुईं
    avg_return_pct: float
    max_drawdown_pct: float
    period_label: str = ""

    def summary(self) -> dict:
        return {
            "period": self.period_label,
            "trades": self.total_trades,
            "win_rate_%": round(self.win_rate, 2),
            "target_hit_%": round(self.target_hit_pct, 2),
            "sl_hit_%": round(self.sl_hit_pct, 2),
            "timeout_%": round(self.timeout_pct, 2),
            "avg_return_%": round(self.avg_return_pct, 3),
            "max_drawdown_%": round(self.max_drawdown_pct, 2),
        }


def _simulate_trades(df: pd.DataFrame, entry_signal: pd.Series,
                      target_pct: float, sl_pct: float, max_hold_bars: int) -> pd.DataFrame:
    """हर entry signal (True) से एक long trade खोलता है, target/SL/timeout में से जो पहले लगे उस पर बंद करता है।
    Signal boolean series होनी चाहिए, df के इंडेक्स जितनी लंबी।"""
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    n = len(df)
    entries = np.where(entry_signal.fillna(False).values)[0]

    records = []
    for i in entries:
        if i + 1 >= n:
            continue
        entry_price = close[i]
        target_price = entry_price * (1 + target_pct / 100)
        sl_price = entry_price * (1 - sl_pct / 100)

        outcome, exit_price, bars_held = "timeout", close[min(i + max_hold_bars, n - 1)], max_hold_bars
        for j in range(i + 1, min(i + 1 + max_hold_bars, n)):
            if high[j] >= target_price:
                outcome, exit_price, bars_held = "target", target_price, j - i
                break
            if low[j] <= sl_price:
                outcome, exit_price, bars_held = "sl", sl_price, j - i
                break

        ret_pct = 100 * (exit_price - entry_price) / entry_price
        records.append({
            "entry_time": df.index[i], "entry_price": entry_price,
            "exit_price": exit_price, "outcome": outcome,
            "bars_held": bars_held, "return_pct": ret_pct,
        })

    return pd.DataFrame(records)


def _max_drawdown(returns_pct: pd.Series) -> float:
    if returns_pct.empty:
        return 0.0
    equity = (1 + returns_pct / 100).cumprod()
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    return abs(drawdown.min()) * 100


def run_backtest(df: pd.DataFrame, entry_signal: pd.Series,
                  target_pct: float = config.DEFAULT_TARGET_PCT,
                  sl_pct: float = config.DEFAULT_SL_PCT,
                  max_hold_bars: int = config.DEFAULT_MAX_HOLD_BARS,
                  period_label: str = "") -> BacktestResult:
    trades = _simulate_trades(df, entry_signal, target_pct, sl_pct, max_hold_bars)
    total = len(trades)
    if total == 0:
        return BacktestResult(trades, 0, 0, 0, 0, 0, 0, 0, period_label)

    win_rate = 100 * (trades["return_pct"] > 0).mean()
    target_hit = 100 * (trades["outcome"] == "target").mean()
    sl_hit = 100 * (trades["outcome"] == "sl").mean()
    timeout = 100 * (trades["outcome"] == "timeout").mean()
    avg_ret = trades["return_pct"].mean()
    mdd = _max_drawdown(trades["return_pct"])

    return BacktestResult(trades, total, win_rate, target_hit, sl_hit, timeout, avg_ret, mdd, period_label)


def run_train_test(df: pd.DataFrame, entry_signal: pd.Series,
                    split_date: str = config.TRAIN_TEST_SPLIT_DATE, **kwargs) -> dict:
    """असली overfitting-सुरक्षा यहीं है — train पर strategy बनी, test पर नंबर सच्चे हैं या नहीं वो चेक होता है।
    Signal train काल में ज़्यादा दिखे और test में गायब हो जाए -> overfit होने का संकेत।"""
    split_ts = pd.Timestamp(split_date)
    train_mask = df.index <= split_ts
    test_mask = ~train_mask

    train_result = run_backtest(df[train_mask], entry_signal[train_mask], period_label="train", **kwargs)
    test_result = run_backtest(df[test_mask], entry_signal[test_mask], period_label="test", **kwargs)

    overfit_gap = train_result.win_rate - test_result.win_rate  # बड़ा positive gap = overfitting का संकेत
    return {
        "train": train_result.summary(),
        "test": test_result.summary(),
        "overfit_gap_win_rate_pts": round(overfit_gap, 2),
        "verdict": "⚠️ overfit जैसा लग रहा है" if overfit_gap > 15 else "ठीक लग रहा है",
    }


def walk_forward_folds(df: pd.DataFrame, entry_signal: pd.Series, n_folds: int = 4, **kwargs) -> list:
    """पूरी अवधि को n_folds बराबर हिस्सों में बाँटकर हर हिस्से पर अलग result — optimizer.py इसे इस्तेमाल करेगा।"""
    n = len(df)
    fold_size = n // n_folds
    results = []
    for f in range(n_folds):
        start, end = f * fold_size, (f + 1) * fold_size if f < n_folds - 1 else n
        fold_df = df.iloc[start:end]
        fold_signal = entry_signal.iloc[start:end]
        res = run_backtest(fold_df, fold_signal, period_label=f"fold_{f+1}", **kwargs)
        results.append(res.summary())
    return results
