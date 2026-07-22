"""
garuda_validator.py
--------------------
तुम्हारी strategies (my_strategies.py) को check करता है — code में bug है या नहीं,
और backtest_core.py चला के train/test result से strategy अच्छी है या नहीं बताता है।

रखना कहाँ है: trading-bot repo में, बाकी फाइलों (config.py, indicators.py,
my_strategies.py, backtest_core.py) के साथ उसी folder में।

चलाना:
    python garuda_validator.py --strategy rsi_supertrend --symbol NIFTY --timeframe 15min
    python garuda_validator.py --all --symbol NIFTY --timeframe 15min
"""

import sys
import re
import json
import inspect
import argparse
from pathlib import Path
from datetime import datetime

import pandas as pd

import config
import my_strategies as strat
from backtest_core import run_train_test


class GarudaValidator:

    def __init__(self):
        self.results_dir = config.RESULTS_DIR / "garuda_validations"
        self.results_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------- L1: code check
    def check_code(self, strategy_func_or_source) -> dict:
        # Dashboard's Custom Strategy box passes the pasted source directly
        # (a str) — there's no importable function object for sandboxed
        # user code to run inspect.getsource() on. Registered strategies
        # (my_strategies.py, via validate()) still pass the function itself.
        source = strategy_func_or_source if isinstance(strategy_func_or_source, str) \
            else inspect.getsource(strategy_func_or_source)
        bugs = []
        score = 100

        if re.search(r'\.shift\s*\(\s*-', source):
            bugs.append({
                "severity": "CRITICAL",
                "issue": "Look-ahead bias",
                "detail": ".shift(-N) मिला — भविष्य का data इस्तेमाल हो रहा है",
                "fix": ".shift(+N) करो, negative नहीं"
            })
            score -= 30

        if "fillna" not in source and "dropna" not in source:
            bugs.append({
                "severity": "HIGH",
                "issue": "NaN handling नहीं है",
                "detail": "Indicator से आए NaN values संभाले नहीं गए",
                "fix": "इंडिकेटर के बाद .fillna() या .dropna() लगाओ"
            })
            score -= 15

        if re.search(r'if\s+\w+\s*[<>=]{1,2}\s*[0-9]{2,}', source):
            bugs.append({
                "severity": "MEDIUM",
                "issue": "Hard-coded threshold",
                "detail": "Values सीधे code में लिखे हैं, config.py में नहीं",
                "fix": "थ्रेशोल्ड्स को config.py या function params में रखो"
            })
            score -= 10

        if "backtest" in source.lower():
            bugs.append({
                "severity": "HIGH",
                "issue": "Backtest-only logic",
                "detail": "if backtest/is_backtest जैसी शर्त मिली — live में अलग बर्ताव करेगी",
                "fix": "यह condition हटाओ, live और backtest का कोड एक जैसा होना चाहिए"
            })
            score -= 15

        score = max(0, score)
        return {
            "score": score,
            "status": "PASS" if score >= 70 and not any(b["severity"] == "CRITICAL" for b in bugs) else "FAIL",
            "bugs": bugs,
        }

    # ---------------------------------------------------------- L2: backtest check
    def check_backtest(self, strategy_func, df: pd.DataFrame) -> dict:
        try:
            signal = strategy_func(df)
            result = run_train_test(
                df, signal,
                split_date=config.TRAIN_TEST_SPLIT_DATE,
                target_pct=config.DEFAULT_TARGET_PCT,
                sl_pct=config.DEFAULT_SL_PCT,
                max_hold_bars=config.DEFAULT_MAX_HOLD_BARS,
            )
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}
        return self.score_backtest_result(result)

    def score_backtest_result(self, result: dict) -> dict:
        """L2 की scoring logic — check_backtest() से निकाला (2026-07-22) ताकि Custom
        Strategy box का पहले से चला हुआ run_train_test() result (api_server.py का
        /api/custom_backtest) दोबारा backtest चलाए बिना यहीं स्कोर हो सके।"""
        train = result["train"]
        test = result["test"]
        overfit_gap = result["overfit_gap_win_rate_pts"]

        train_wr = train["win_rate_%"]
        test_wr = test["win_rate_%"]
        train_trades = train["trades"]
        max_dd = train["max_drawdown_%"]

        bugs = []
        score = 0

        if train_trades < 20:
            bugs.append({
                "severity": "HIGH",
                "issue": "बहुत कम trades",
                "detail": f"Train period में सिर्फ {train_trades} trades मिले (कम-से-कम 20 चाहिए)",
                "fix": "ज़्यादा data लो या entry condition ढीली करो"
            })

        if train_wr >= 50:
            score += 35
        elif train_wr >= 45:
            score += 25
        elif train_wr >= 40:
            score += 15
        else:
            bugs.append({
                "severity": "HIGH",
                "issue": "Win rate कम है",
                "detail": f"Train win rate सिर्फ {train_wr}% है (कम-से-कम 40% चाहिए)",
                "fix": "Strategy logic या parameters बदलो"
            })

        if max_dd <= 15:
            score += 25
        elif max_dd <= 25:
            score += 15
        else:
            bugs.append({
                "severity": "HIGH",
                "issue": "Drawdown ज़्यादा है",
                "detail": f"Max drawdown {max_dd}% है (15% से कम होना चाहिए)",
                "fix": "Risk management/SL tighten करो"
            })

        if overfit_gap > 15:
            bugs.append({
                "severity": "CRITICAL",
                "issue": "Overfitting का शक",
                "detail": f"Train win-rate {train_wr}% पर test सिर्फ {test_wr}% (gap {overfit_gap} pts)",
                "fix": "Strategy असली नहीं, सिर्फ train data पर fit हुई लगती है"
            })
        elif overfit_gap > 8:
            score += 15
        else:
            score += 25

        if test_wr >= 40:
            score += 15

        score = min(100, score)
        return {
            "status": "PASS" if score >= 60 and overfit_gap <= 15 else "FAIL",
            "score": score,
            "train": train,
            "test": test,
            "overfit_gap_pts": overfit_gap,
            "bugs": bugs,
        }

    # ---------------------------------------------------------- combined (custom/pasted code)
    def validate_custom(self, source: str, backtest_result: dict) -> dict:
        """validate() का हल्का version — dashboard के Custom Strategy box के लिए
        (2026-07-22)। backtest_result वही dict है जो /api/custom_backtest पहले ही
        run_train_test() से बना चुका है, इसलिए backtest दोबारा नहीं चलाना पड़ता। कोई
        JSON report डिस्क पर नहीं लिखता — validate()/validate_all() named/registered
        strategies के लिए हैं, यह हर dashboard क्लिक के लिए अस्थायी check है।"""
        l1 = self.check_code(source)
        l2 = self.score_backtest_result(backtest_result)

        has_critical = any(b["severity"] == "CRITICAL" for b in l1["bugs"])
        bt_failed = l2.get("status") == "FAIL"
        if l2.get("status") == "ERROR":
            bt_score = None
        else:
            bt_score = l2["score"]
            has_critical = has_critical or any(b["severity"] == "CRITICAL" for b in l2.get("bugs", []))

        if bt_score is not None:
            final_score = round(l1["score"] * 0.3 + bt_score * 0.7, 1)
        else:
            final_score = l1["score"]

        if has_critical or final_score < 40:
            verdict = "🔴 REJECTED"
        elif final_score < 60 or bt_failed:
            verdict = "🟡 CONDITIONAL"
        elif final_score < 80:
            verdict = "🟢 APPROVED"
        else:
            verdict = "🟢 EXCELLENT — APPROVED"

        return {
            "code_check": l1,
            "backtest_check": l2,
            "final_score": final_score,
            "verdict": verdict,
        }

    # ---------------------------------------------------------- combined
    def validate(self, strategy_name: str, symbol: str = "NIFTY", timeframe: str = None) -> dict:
        timeframe = timeframe or config.DEFAULT_TIMEFRAME
        print(f"\n{'='*70}")
        print(f"🔱 Validating: {strategy_name}  ({symbol} / {timeframe})")
        print(f"{'='*70}")

        if strategy_name not in strat.STRATEGY_REGISTRY:
            print(f"❌ '{strategy_name}' STRATEGY_REGISTRY में नहीं मिली")
            return {"strategy": strategy_name, "status": "ERROR", "error": "not found"}

        strategy_func = strat.STRATEGY_REGISTRY[strategy_name]
        result = {
            "strategy": strategy_name,
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp": datetime.now().isoformat(),
        }

        # L1
        print("📋 Code check...")
        l1 = self.check_code(strategy_func)
        result["code_check"] = l1
        icon = "✅" if l1["status"] == "PASS" else "❌"
        print(f"   {icon} Score {l1['score']}/100")
        for b in l1["bugs"]:
            print(f"      • [{b['severity']}] {b['issue']}: {b['detail']}")

        # L2 (data मिले तो)
        safe = symbol.replace(" ", "_").replace("^", "")
        data_path = config.DATA_DIR / f"{safe}__{timeframe}.parquet"
        if data_path.exists():
            print("📈 Backtest check (train/test)...")
            df = pd.read_parquet(data_path)
            l2 = self.check_backtest(strategy_func, df)
            result["backtest_check"] = l2
            if l2.get("status") == "ERROR":
                print(f"   ❌ Error: {l2['error']}")
            else:
                icon = "✅" if l2["status"] == "PASS" else "❌"
                print(f"   {icon} Score {l2['score']}/100 | "
                      f"Train WR {l2['train']['win_rate_%']}% | Test WR {l2['test']['win_rate_%']}% | "
                      f"Overfit gap {l2['overfit_gap_pts']} pts")
                for b in l2["bugs"]:
                    print(f"      • [{b['severity']}] {b['issue']}: {b['detail']}")
        else:
            print(f"⏭️  Backtest skipped — data नहीं मिला: {data_path}")
            result["backtest_check"] = {"status": "SKIP", "reason": f"{data_path} missing"}

        # Final verdict
        code_score = l1["score"]
        bt = result.get("backtest_check", {})
        bt_score = bt.get("score", 0) if bt.get("status") not in ("SKIP", "ERROR") else None

        has_critical = any(b["severity"] == "CRITICAL" for b in l1["bugs"])
        bt_failed = bt.get("status") == "FAIL"
        if bt_score is not None:
            has_critical = has_critical or any(b["severity"] == "CRITICAL" for b in bt.get("bugs", []))
            final_score = round(code_score * 0.3 + bt_score * 0.7, 1)
        else:
            final_score = code_score

        # bt_failed यहाँ ज़रूरी है: L2 अलग से FAIL हो चुका हो (जैसे 0 trades — तब overfit_gap भी 0
        # और drawdown भी 0% दिखेगा, जो weighted-average score को गलती से ऊपर खींच सकता है) तो सिर्फ
        # weighted final_score पर भरोसा करके APPROVED नहीं देना — L2 का असली FAIL verdict को override
        # करने देना गलत होगा (एक strategy जो कभी trade ही नहीं लेती उसे APPROVE नहीं करना चाहिए)।
        if has_critical or final_score < 40:
            verdict = "🔴 REJECTED"
        elif final_score < 60 or bt_failed:
            verdict = "🟡 CONDITIONAL"
        elif final_score < 80:
            verdict = "🟢 APPROVED"
        else:
            verdict = "🟢 EXCELLENT — APPROVED"

        result["final_score"] = final_score
        result["verdict"] = verdict

        print(f"\n{'='*70}")
        print(f"📊 FINAL: {final_score}/100  →  {verdict}")
        print(f"{'='*70}\n")

        out_file = self.results_dir / f"{strategy_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
        print(f"💾 Report: {out_file}\n")

        return result

    def validate_all(self, symbol: str = "NIFTY", timeframe: str = None):
        results = []
        for name in strat.STRATEGY_REGISTRY:
            results.append(self.validate(name, symbol, timeframe))
        approved = sum(1 for r in results if "APPROVED" in r.get("verdict", ""))
        print(f"\n🔱 कुल {len(results)} strategies | Approved: {approved} | Rejected/Conditional: {len(results)-approved}\n")
        return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Garuda Validator — Trishul Pro strategies check")
    parser.add_argument("--strategy", "-s", help="Strategy name (STRATEGY_REGISTRY में से)")
    parser.add_argument("--all", "-a", action="store_true", help="सारी strategies check करो")
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--timeframe", default=None)
    args = parser.parse_args()

    validator = GarudaValidator()

    if args.all:
        validator.validate_all(symbol=args.symbol, timeframe=args.timeframe)
    elif args.strategy:
        validator.validate(args.strategy, symbol=args.symbol, timeframe=args.timeframe)
    else:
        print("Usage:\n  python garuda_validator.py --strategy rsi_supertrend\n  python garuda_validator.py --all")
