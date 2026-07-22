"""
self_healing.py
-----------------
System खुद अपनी सेहत जांचता है — folders, data files, हर एक indicator,
backtest engine, और strategy sandbox — सब कुछ असल में चलाकर देखता है।
हर चीज़ को PASS (हरा) / WARN (पीला) / FAIL (लाल) मार्क देता है।

गुरुजी वाली बात: पहाड़ा खुद गलत हो तो बच्चों को क्या सिखाएगा — इसीलिए यह
"पहाड़ा" (यानी हर indicator, backtest engine, sandbox) पहले खुद जांचता है,
फिर ही किसी strategy को टेस्ट करने देता है।

क्या अपने-आप ठीक होता है (auto_fixed: true):
  - Missing data/results folders — बना दी जाती हैं
  - Corrupt / empty data फाइलें — हटा दी जाती हैं (ताकि खराब cache रास्ते में ना आए)
  - टूटा हुआ indicator — dashboard की list से अस्थायी रूप से हटा दिया जाता है
    (जब तक कोड में उसे कोई ठीक ना करे)

क्या सिर्फ पहचाना जाता है, अपने-आप ठीक नहीं होता (सिर्फ लाल निशान + बताता है क्या करना है):
  - असली market data सर्वर पर मौजूद ही नहीं (data_fetcher.py चलाना पड़ेगा — यह इंसान का काम है)
  - backtest_core.py या sandbox का लॉजिक ही गलत निकले (यह कोड की गलती है, खुद-ब-खुद ठीक
    करना खतरनाक है — गलत strategy को "पास" दिखा देना उससे भी बुरा है)

चलाना:
  - Dashboard से (लाइव, हर बार manual): GET /api/self_check
  - Terminal से (watchdog/cron के लिए, हर कुछ मिनट में अपने-आप): python self_healing.py
    हर run results/self_healing_log.json में history जोड़ती जाती है (आख़िरी 50 runs)।
    कोई FAIL मिले तो exit code 1 के साथ बंद होता है — pm2/cron उस पर अलर्ट भेज सकता है।
"""

import json
import time
import traceback
from datetime import datetime

import numpy as np
import pandas as pd

import backtest_core as bc
import config
import indicators as ind
import strategy_sandbox as sandbox

BROKEN_INDICATORS_FILE = config.RESULTS_DIR / "broken_indicators.json"
LOG_FILE = config.RESULTS_DIR / "self_healing_log.json"


def _sample_df(n: int = 3000) -> pd.DataFrame:
    """टेस्ट के लिए synthetic OHLCV डेटा बनाता है — असली market data से आज़ाद रहता है,
    इसलिए यह self-check तब भी चल सकता है जब data_fetcher.py कभी चला ही ना हो।

    ज़रूरी: config.TRAIN_TEST_SPLIT_DATE (2023-12-31) से पहले और बाद दोनों तरफ़ डेटा होना
    चाहिए — वरना check_backtest_engine() का train fold हमेशा खाली (0 trades) रहेगा और
    backtest engine का train-side logic कभी टेस्ट ही नहीं होगा (सिर्फ 0<=0<=100 वाला
    trivial PASS मिलता रहेगा, भले ही असली bug हो)। पहले 2018-01-01 से daily bars शुरू करना
    इसी वजह से ज़रूरी है।"""
    rng = np.random.default_rng(42)
    idx = pd.date_range("2018-01-01", periods=n, freq="1D")
    close = 100 + np.cumsum(rng.normal(0, 0.3, n))
    high = close + rng.random(n) * 0.5
    low = close - rng.random(n) * 0.5
    open_ = close + rng.normal(0, 0.1, n)
    volume = rng.integers(1000, 5000, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx
    )


def data_disk_usage() -> dict:
    """data/ folder कितना भारी हुआ — dashboard पर green/orange/red gauge दिखाने के लिए।
    असली disk size (du) नहीं, हर parquet फाइल का size जोड़कर हिसाब लगाता है — Windows/Termux
    दोनों पर बिना किसी extra shell-command (du) के काम करेगा।"""
    files = []
    total_bytes = 0
    if config.DATA_DIR.exists():
        for p in config.DATA_DIR.rglob("*"):
            if p.is_file():
                size = p.stat().st_size
                total_bytes += size
                files.append({"name": p.name, "mb": round(size / (1024 * 1024), 2)})

    total_mb = round(total_bytes / (1024 * 1024), 2)
    green_max = config.DATA_SIZE_GREEN_MB
    danger_at = config.DATA_SIZE_DANGER_MB

    if total_mb < green_max:
        zone = "green"
    elif total_mb < danger_at:
        zone = "orange"
    else:
        zone = "red"

    files.sort(key=lambda f: f["mb"], reverse=True)
    return {
        "total_mb": total_mb,
        "total_files": len(files),
        "zone": zone,
        "green_max_mb": green_max,
        "danger_at_mb": danger_at,
        # gauge को 0 से इतने तक स्केल करना है (danger line से थोड़ा आगे तक ताकि बार खाली ना लगे)
        "gauge_max_mb": max(danger_at * 1.3, total_mb * 1.1, 100),
        "top_files": files[:5],
    }


class SystemHealer:

    def __init__(self):
        self.checks = []
        self.df = _sample_df()

    def _record(self, name: str, status: str, detail: str, auto_fixed: bool = False):
        self.checks.append({"name": name, "status": status, "detail": detail, "auto_fixed": auto_fixed})

    # ---------------------------------------------------- 1. folders
    def check_dirs(self):
        try:
            missing = [d for d in (config.DATA_DIR, config.OPTIONS_DIR, config.RESULTS_DIR) if not d.exists()]
            for d in missing:
                d.mkdir(parents=True, exist_ok=True)
            if missing:
                self._record("Folders", "pass", f"{len(missing)} missing folder बनाई गईं", auto_fixed=True)
            else:
                self._record("Folders", "pass", "data/results folders ठीक हैं")
        except Exception as e:
            self._record("Folders", "fail", f"Folder बनाने में दिक्कत: {e}")

    # ---------------------------------------------------- 2. data files
    def check_data_files(self):
        try:
            uni = pd.read_csv(config.UNIVERSE_FILE)
        except Exception as e:
            self._record("Universe file", "fail", f"universe.csv पढ़ने में दिक्कत: {e}")
            return
        self._record("Universe file", "pass", f"{len(uni)} symbols मिले")

        problems, checked, auto_fixed_any = [], 0, False
        for _, row in uni.head(10).iterrows():          # sample काफ़ी है, पूरी list भारी I/O देगी
            safe = str(row["symbol"]).replace(" ", "_").replace("^", "")
            path = config.DATA_DIR / f"{safe}__{config.DEFAULT_TIMEFRAME}.parquet"
            checked += 1
            if not path.exists():
                problems.append(f"{row['symbol']} — data फाइल मौजूद नहीं")
                continue
            try:
                d = pd.read_parquet(path)
                if d.empty:
                    problems.append(f"{row['symbol']} — फाइल खाली मिली, हटा दी")
                    path.unlink(missing_ok=True)
                    auto_fixed_any = True
            except Exception as e:
                problems.append(f"{row['symbol']} — पढ़ने में error, हटा दी: {e}")
                path.unlink(missing_ok=True)
                auto_fixed_any = True

        if problems:
            self._record(
                "Data files", "warn",
                f"{len(problems)}/{checked} sample में समस्या — पहला: {problems[0]}. "
                f"Fix: python data_fetcher.py --symbol <NAME> चलाओ।",
                auto_fixed=auto_fixed_any,
            )
        else:
            self._record("Data files", "pass", f"{checked} sample data files ठीक मिलीं")

    # ---------------------------------------------------- 3. हर indicator चलाकर देखो
    def check_indicators(self):
        broken, total = [], len(ind.INDICATOR_REGISTRY)
        for name in ind.INDICATOR_REGISTRY:
            try:
                out = ind.compute(name, self.df)
                series = out.iloc[:, 0] if isinstance(out, pd.DataFrame) else out
                if series.isna().all():
                    broken.append({"name": name, "reason": "पूरा output NaN है"})
            except Exception as e:
                broken.append({"name": name, "reason": f"{type(e).__name__}: {e}"})

        if broken:
            auto_fixed = False
            try:
                with open(BROKEN_INDICATORS_FILE, "w", encoding="utf-8") as f:
                    json.dump([b["name"] for b in broken], f, ensure_ascii=False, indent=2)
                auto_fixed = True
            except Exception:
                pass
            names = ", ".join(b["name"] for b in broken[:5]) + ("..." if len(broken) > 5 else "")
            note = " — dashboard की list से अस्थायी रूप से हटा दिया गया" if auto_fixed else ""
            self._record("Indicators", "fail", f"{len(broken)}/{total} टूटे मिले: {names}{note}", auto_fixed=auto_fixed)
        else:
            if BROKEN_INDICATORS_FILE.exists():
                BROKEN_INDICATORS_FILE.unlink()
            self._record("Indicators", "pass", f"सारे {total} indicators सही चले")

    # ---------------------------------------------------- 4. backtest engine
    def check_backtest_engine(self):
        try:
            rsi = ind.compute("RSI", self.df, period=14)
            signal = rsi < 40
            result = bc.run_train_test(self.df, signal)
            train = result["train"]
            if not (0 <= train["win_rate_%"] <= 100):
                raise AssertionError(f"win-rate {train['win_rate_%']}% 0-100 range के बाहर है")
            self._record(
                "Backtest engine", "pass",
                f"sample strategy पर सही चला (train trades={train['trades']}, win-rate={train['win_rate_%']}%)",
            )
        except Exception as e:
            self._record("Backtest engine", "fail", f"backtest_core.py में दिक्कत: {type(e).__name__}: {e}")

    # ---------------------------------------------------- 5. sandbox — खुद अपनी सुरक्षा टेस्ट करता है
    def check_sandbox(self):
        good_code = "def my_strategy(df):\n    rsi = ind.compute('RSI', df, period=14)\n    return rsi < 35\n"
        bad_code = "import os\ndef my_strategy(df):\n    return df['close'] > 0\n"

        try:
            sig = sandbox.run_user_strategy(good_code, self.df, timeout_sec=10)
            if not isinstance(sig, pd.Series):
                raise AssertionError("signal pandas Series नहीं है")
            self._record("Sandbox — valid code", "pass", "सही strategy code ठीक चला")
        except Exception as e:
            self._record("Sandbox — valid code", "fail", f"सही code भी fail हो गया: {e}")

        try:
            sandbox.run_user_strategy(bad_code, self.df, timeout_sec=10)
            self._record("Sandbox — security", "fail", "⚠️ खतरनाक code (import os) ब्लॉक नहीं हुआ — यह गंभीर समस्या है")
        except sandbox.SandboxError:
            self._record("Sandbox — security", "pass", "खतरनाक code सही से ब्लॉक हुआ")
        except Exception as e:
            self._record("Sandbox — security", "warn", f"अनपेक्षित तरीके से fail हुआ: {e}")

    # ---------------------------------------------------- सब चलाओ
    def run_all(self) -> dict:
        self.checks = []
        t0 = time.time()
        for fn in (self.check_dirs, self.check_data_files, self.check_indicators,
                   self.check_backtest_engine, self.check_sandbox):
            try:
                fn()
            except Exception as e:
                self._record(fn.__name__, "fail", f"check खुद क्रैश हो गया: {e}\n{traceback.format_exc(limit=2)}")

        statuses = [c["status"] for c in self.checks]
        overall = "red" if "fail" in statuses else ("yellow" if "warn" in statuses else "green")

        report = {
            "timestamp": datetime.now().isoformat(),
            "duration_sec": round(time.time() - t0, 2),
            "overall": overall,
            "checks": self.checks,
        }
        self._save_log(report)
        return report

    def _save_log(self, report: dict):
        try:
            history = []
            if LOG_FILE.exists():
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
            history.append(report)
            history = history[-50:]
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2, default=str)
        except Exception:
            pass  # log सेव ना हो पाए तो भी report तो लौटेगी ही


if __name__ == "__main__":
    healer = SystemHealer()
    report = healer.run_all()
    icon = {"pass": "✅", "fail": "❌", "warn": "⚠️"}
    print(f"\n{'='*60}\nSelf-Check — {report['timestamp']}\n{'='*60}")
    for c in report["checks"]:
        fixed = " (खुद ठीक कर दिया)" if c["auto_fixed"] else ""
        print(f"{icon.get(c['status'], '?')} {c['name']}: {c['detail']}{fixed}")
    overall_icon = {"green": "🟢", "yellow": "🟡", "red": "🔴"}[report["overall"]]
    print(f"\n{overall_icon} OVERALL: {report['overall'].upper()}  ({report['duration_sec']}s)\n")
    if report["overall"] == "red":
        raise SystemExit(1)
