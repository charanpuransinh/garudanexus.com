"""
rule_builder.py
----------------
UI से टॉगल किए गए indicators + उनके condition (>, <, crosses_above, ...) को
एक combined boolean entry-signal में बदलता है। Dashboard हर checkbox change पर
यही function फिर से चलाकर नया accuracy दिखाएगा।

Rule format (JSON जैसा, UI से यही भेजा जाएगा):
[
    {"indicator": "RSI", "params": {"period": 14}, "op": "<", "value": 30},
    {"indicator": "EMA", "params": {"period": 20}, "op": "cross_above", "compare_to": {"indicator": "EMA", "params": {"period": 50}}},
    {"indicator": "VolumeSpike", "params": {}, "op": "is_true"},
]
सारी rules AND से मिलती हैं (default) — OR ग्रुप चाहिए तो rule_groups इस्तेमाल करो।
"""

import pandas as pd

import indicators as ind


def _resolve_series(rule: dict, df: pd.DataFrame) -> pd.Series:
    out = ind.compute(rule["indicator"], df, **rule.get("params", {}))
    if isinstance(out, pd.DataFrame):
        col = rule.get("column", out.columns[0])
        out = out[col]
    return out


def _apply_condition(series: pd.Series, rule: dict, df: pd.DataFrame) -> pd.Series:
    op = rule["op"]
    if op == "is_true":
        return series.astype(bool)
    if op == ">":
        return series > rule["value"]
    if op == "<":
        return series < rule["value"]
    if op == ">=":
        return series >= rule["value"]
    if op == "<=":
        return series <= rule["value"]
    if op in ("cross_above", "cross_below"):
        other = _resolve_series(rule["compare_to"], df)
        prev_diff = (series.shift(1) - other.shift(1))
        curr_diff = (series - other)
        if op == "cross_above":
            return (prev_diff <= 0) & (curr_diff > 0)
        return (prev_diff >= 0) & (curr_diff < 0)
    raise ValueError(f"अनजान operator: {op}")


def build_signal(df: pd.DataFrame, rules: list, rule_groups: list = None) -> pd.Series:
    """rules: AND से मिलने वाली list. rule_groups: [[rule,...], [rule,...]] — groups आपस में OR होते हैं,
    हर group के अंदर rules AND होते हैं। rule_groups दिया हो तो rules को ignore किया जाता है।"""
    if rule_groups:
        combined = pd.Series(False, index=df.index)
        for group in rule_groups:
            group_signal = pd.Series(True, index=df.index)
            for rule in group:
                series = _resolve_series(rule, df)
                group_signal &= _apply_condition(series, rule, df).fillna(False)
            combined |= group_signal
        return combined

    signal = pd.Series(True, index=df.index)
    for rule in rules:
        series = _resolve_series(rule, df)
        signal &= _apply_condition(series, rule, df).fillna(False)
    return signal


def toggled_indicators_to_default_rules(indicator_names: list) -> list:
    """Dashboard पर सिर्फ checkbox ON किया हो, condition ना दी हो — तो हर indicator का
    एक sensible default rule बना देता है (ताकि 'सिर्फ टॉगल करके तुरंत result' वाला UX काम करे)।"""
    defaults = {
        "RSI": {"op": "<", "value": 30},
        "StochRSI": {"op": "<", "value": 0.2},
        "WilliamsR": {"op": "<", "value": -80},
        "MFI": {"op": "<", "value": 20},
        "CCI": {"op": "<", "value": -100},
        "VolumeSpike": {"op": "is_true"},
        "PSARFlip": {"op": "is_true"},
        "HigherHighLowerLow": {"op": "is_true", "column": "higher_high"},
    }
    rules = []
    for name in indicator_names:
        base = {"indicator": name, "params": {}}
        base.update(defaults.get(name, {"op": ">", "value": 0}))  # fallback: >0 जैसे momentum-type
        rules.append(base)
    return rules
