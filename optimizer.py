"""
optimizer.py
------------
Indicator combinations में से अच्छे entry-signal खुद ढूंढता है — overfitting से बचाने के लिए
walk-forward validation पर भरोसा करता है, सिर्फ एक बार के train/test winrate पर नहीं।

दो mode:
  1) grid_search()    -> छोटे combo-size (2-3 indicators) के लिए सारे combinations आज़माता है
                          (indicator_pool बड़ा हो तो बहुत slow — छोटे pool या combo_size=2 तक रखो)
  2) genetic_search()  -> बड़े indicator-pool (सारे 50) के लिए बिना सब combinations आज़माए,
                          evolution से अच्छे combo ढूंढता है (config.OPTIMIZER_* settings से control)

Scoring (overfit-resistant):
    score = mean(walk-forward fold win_rate) - 0.5 * std(fold win_rate) - overfit_gap
    - mean ऊँचा अच्छा
    - std ऊँचा मतलब fold-to-fold अस्थिर strategy -> penalty
    - overfit_gap = train winrate - test winrate (बड़ा gap = overfitting का संकेत) -> penalty
    - MIN_TRADES_PER_FOLD से कम trades वाले combo statistically भरोसे लायक नहीं, reject होते हैं

चलाओ (standalone टेस्ट के लिए):
    python optimizer.py --symbol RELIANCE --timeframe 1day --mode genetic
"""

import argparse
import itertools
import random
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

import config
import indicators as ind
import rule_builder as rb
from backtest_core import run_train_test, walk_forward_folds

MIN_TRADES_PER_FOLD = 5   # इससे कम trades वाला fold = noise, भरोसा नहीं
MIN_VALID_FOLDS = 2       # कम-से-कम इतने folds में MIN_TRADES_PER_FOLD पूरा होना चाहिए


@dataclass
class ComboResult:
    rules: list
    score: float
    mean_win_rate: float
    std_win_rate: float
    overfit_gap: float
    total_trades: int
    folds: list = field(default_factory=list)

    def label(self) -> str:
        parts = []
        for r in self.rules:
            val = f" {r['value']}" if "value" in r and r["value"] is not None else ""
            parts.append(f"{r['indicator']}{r['op']}{val}")
        return " AND ".join(parts)

    def summary(self) -> dict:
        return {
            "rules_label": self.label(),
            "rules": self.rules,
            "score": round(self.score, 3),
            "mean_win_rate_%": round(self.mean_win_rate, 2),
            "std_win_rate_pts": round(self.std_win_rate, 2),
            "overfit_gap_pts": round(self.overfit_gap, 2),
            "total_trades": self.total_trades,
        }


def _score_combo(df: pd.DataFrame, rules: list, n_folds: int, **bt_kwargs) -> Optional[ComboResult]:
    try:
        signal = rb.build_signal(df, rules)
    except Exception:
        return None
    if signal.sum() < MIN_TRADES_PER_FOLD * MIN_VALID_FOLDS:
        return None

    folds = walk_forward_folds(df, signal, n_folds=n_folds, **bt_kwargs)
    valid = [f for f in folds if f["trades"] >= MIN_TRADES_PER_FOLD]
    if len(valid) < MIN_VALID_FOLDS:
        return None

    win_rates = [f["win_rate_%"] for f in valid]
    tt = run_train_test(df, signal, **bt_kwargs)
    overfit_gap = max(0.0, tt["overfit_gap_win_rate_pts"])

    mean_wr = float(np.mean(win_rates))
    std_wr = float(np.std(win_rates))
    score = mean_wr - 0.5 * std_wr - overfit_gap
    total_trades = int(sum(f["trades"] for f in folds))

    return ComboResult(rules, score, mean_wr, std_wr, overfit_gap, total_trades, folds)


def grid_search(df: pd.DataFrame, indicator_pool: List[str] = None, combo_size: int = 2,
                 n_folds: int = config.OPTIMIZER_WALK_FORWARD_FOLDS, top_n: int = 10,
                 **bt_kwargs) -> List[ComboResult]:
    """indicator_pool में से combo_size जितने indicators इकट्ठे करके हर combination टेस्ट करता है।
    हर indicator का default rule rule_builder.toggled_indicators_to_default_rules() से आता है।
    Pool छोटा रखो (जैसे 10-15 indicators) वरना combinations बहुत ज़्यादा हो जाएंगे —
    combo_size=2 पर 15 indicators = 105 combos, combo_size=3 पर 455, वगैरह।"""
    pool = indicator_pool or list(ind.INDICATOR_REGISTRY)
    results = []
    for combo in itertools.combinations(pool, combo_size):
        rules = rb.toggled_indicators_to_default_rules(list(combo))
        res = _score_combo(df, rules, n_folds, **bt_kwargs)
        if res:
            results.append(res)
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_n]


def genetic_search(df: pd.DataFrame, indicator_pool: List[str] = None,
                    pop_size: int = config.OPTIMIZER_POP_SIZE,
                    generations: int = config.OPTIMIZER_GENERATIONS,
                    max_combo_size: int = config.OPTIMIZER_MAX_COMBO_SIZE,
                    n_folds: int = config.OPTIMIZER_WALK_FORWARD_FOLDS,
                    top_n: int = 10, seed: int = 42, **bt_kwargs) -> List[ComboResult]:
    """सारे 50 indicators के लिए grid search combinatorially असंभव है (C(50,3) = 19600+),
    इसलिए genetic algorithm: हर individual indicator-नामों का एक set (1 से max_combo_size तक)।
    हर generation में टॉप performers survive करते हैं, crossover + mutation से अगली generation बनती है।
    Walk-forward score ही fitness है — इसलिए overfit combo अपने-आप कम score पाकर बाहर हो जाते हैं।"""
    rng = random.Random(seed)
    pool = indicator_pool or list(ind.INDICATOR_REGISTRY)

    def random_individual():
        size = rng.randint(1, max_combo_size)
        return tuple(sorted(rng.sample(pool, size)))

    cache = {}

    def fitness(individual):
        if individual not in cache:
            rules = rb.toggled_indicators_to_default_rules(list(individual))
            cache[individual] = _score_combo(df, rules, n_folds, **bt_kwargs)
        res = cache[individual]
        return (res.score if res else -999.0), res

    population = [random_individual() for _ in range(pop_size)]
    hall_of_fame: List[ComboResult] = []

    for _ in range(generations):
        scored = sorted(((*fitness(ind_), ind_) for ind_ in population), key=lambda x: x[0], reverse=True)
        hall_of_fame.extend(res for _, res, _ in scored[:5] if res)

        survivors = [ind_ for _, _, ind_ in scored[:max(2, pop_size // 4)]]
        next_gen = list(survivors)
        while len(next_gen) < pop_size:
            p1, p2 = rng.sample(survivors, 2) if len(survivors) >= 2 else (survivors[0], survivors[0])
            pool_child = sorted(set(p1) | set(p2))
            size = min(max_combo_size, max(1, len(pool_child)))
            child = rng.sample(pool_child, size)
            if rng.random() < 0.3:  # mutation: एक indicator swap
                child[rng.randrange(len(child))] = rng.choice(pool)
            child = tuple(sorted(set(child))) or random_individual()
            next_gen.append(child)
        population = next_gen[:pop_size]

    unique = {res.label(): res for res in hall_of_fame}
    ranked = sorted(unique.values(), key=lambda r: r.score, reverse=True)
    return ranked[:top_n]


if __name__ == "__main__":
    from run_demo import make_synthetic_ohlcv

    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None, help="असली parquet से चलाना हो तो symbol दो")
    parser.add_argument("--timeframe", default=config.DEFAULT_TIMEFRAME)
    parser.add_argument("--mode", choices=["grid", "genetic"], default="genetic")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    if args.symbol:
        safe = args.symbol.replace(" ", "_").replace("^", "")
        path = config.DATA_DIR / f"{safe}__{args.timeframe}.parquet"
        df = pd.read_parquet(path)
        print(f"असली data: {args.symbol}/{args.timeframe}, {len(df)} rows")
    else:
        df = make_synthetic_ohlcv()
        print(f"Synthetic data (कोई --symbol नहीं दिया): {len(df)} rows")

    if args.mode == "grid":
        small_pool = ["RSI", "MFI", "CCI", "WilliamsR", "StochRSI", "VolumeSpike",
                      "ADX", "MACD", "PSARFlip", "HigherHighLowerLow"]
        results = grid_search(df, indicator_pool=small_pool, combo_size=2, top_n=args.top)
    else:
        results = genetic_search(df, top_n=args.top)

    print(f"\nटॉप {len(results)} combos ({args.mode} search):\n")
    for i, r in enumerate(results, 1):
        s = r.summary()
        print(f"{i:2d}. {s['rules_label']}")
        print(f"    score={s['score']}  win_rate={s['mean_win_rate_%']}%  "
              f"std={s['std_win_rate_pts']}pts  overfit_gap={s['overfit_gap_pts']}pts  "
              f"trades={s['total_trades']}")
