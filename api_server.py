"""
api_server.py
-------------
FastAPI backend — dashboard.html इसी से बात करता है। कोई भी checkbox/dropdown बदलने पर
frontend यहीं POST करता है, यहाँ से rule_builder + backtest_core चलकर live result वापस आता है।

चलाओ:
    pip install -r requirements.txt
    uvicorn api_server:app --host 0.0.0.0 --port 8090 --reload

फिर browser में http://<server-ip>:8090 खोलो — dashboard वहीं serve होगा।
DigitalOcean पर PM2 से चलाना हो तो: pm2 start "uvicorn api_server:app --host 0.0.0.0 --port 8090" --name backtester-api
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import pandas as pd
import psutil
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import indicators as ind
import my_strategies as strat
import optimizer as opt
import rule_builder as rb
import self_healing
import strategy_sandbox as sandbox
from backtest_core import run_train_test
from garuda_validator import GarudaValidator

_garuda_validator = GarudaValidator()

app = FastAPI(title="Trishul Backtesting Scanner API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- request/response models
class RuleIn(BaseModel):
    indicator: str
    params: dict = {}
    op: str
    value: Optional[float] = None
    compare_to: Optional[dict] = None
    column: Optional[str] = None


class BacktestRequest(BaseModel):
    symbol: str
    timeframe: str = config.DEFAULT_TIMEFRAME
    rules: List[RuleIn] = []
    toggled_indicators: List[str] = []   # सिर्फ checkbox ON किया हो, condition ना दी हो -> default rule बनेगा
    target_pct: float = config.DEFAULT_TARGET_PCT
    sl_pct: float = config.DEFAULT_SL_PCT
    max_hold_bars: int = config.DEFAULT_MAX_HOLD_BARS
    split_date: str = config.TRAIN_TEST_SPLIT_DATE
    # ---- added 2026-07-24: realism + position sizing ----
    slippage_pct: float = config.DEFAULT_SLIPPAGE_PCT
    commission_pct: float = config.DEFAULT_COMMISSION_PCT
    position_capital_rs: float = config.DEFAULT_POSITION_CAPITAL_RS


class CustomBacktestRequest(BaseModel):
    symbol: str
    timeframe: str = config.DEFAULT_TIMEFRAME
    code: str                              # यूज़र का पेस्ट किया Python code
    func_name: str = "my_strategy"         # code में यही नाम का function ढूंढा जाएगा
    target_pct: float = config.DEFAULT_TARGET_PCT
    sl_pct: float = config.DEFAULT_SL_PCT
    max_hold_bars: int = config.DEFAULT_MAX_HOLD_BARS
    split_date: str = config.TRAIN_TEST_SPLIT_DATE
    slippage_pct: float = config.DEFAULT_SLIPPAGE_PCT
    commission_pct: float = config.DEFAULT_COMMISSION_PCT
    position_capital_rs: float = config.DEFAULT_POSITION_CAPITAL_RS


class OptimizeRequest(BaseModel):
    symbol: str
    timeframe: str = config.DEFAULT_TIMEFRAME
    mode: str = "genetic"       # "grid" या "genetic"
    combo_size: int = 2         # grid mode के लिए
    indicator_pool: Optional[List[str]] = None
    top_n: int = 10


# ---- added 2026-07-24: batch scan / strategy library / correlation ----
class BatchBacktestRequest(BaseModel):
    symbols: List[str]
    timeframe: str = config.DEFAULT_TIMEFRAME
    toggled_indicators: List[str] = []
    rules: List[RuleIn] = []
    target_pct: float = config.DEFAULT_TARGET_PCT
    sl_pct: float = config.DEFAULT_SL_PCT
    max_hold_bars: int = config.DEFAULT_MAX_HOLD_BARS
    split_date: str = config.TRAIN_TEST_SPLIT_DATE
    slippage_pct: float = config.DEFAULT_SLIPPAGE_PCT
    commission_pct: float = config.DEFAULT_COMMISSION_PCT
    position_capital_rs: float = config.DEFAULT_POSITION_CAPITAL_RS


class SaveStrategyRequest(BaseModel):
    name: str
    code: str
    func_name: str = "my_strategy"
    target_pct: float = config.DEFAULT_TARGET_PCT
    sl_pct: float = config.DEFAULT_SL_PCT
    max_hold_bars: int = config.DEFAULT_MAX_HOLD_BARS
    split_date: str = config.TRAIN_TEST_SPLIT_DATE


class CorrelationRequest(BaseModel):
    symbol: str
    timeframe: str = config.DEFAULT_TIMEFRAME
    indicators: List[str]


# ---------------------------------------------------------------- data loading
def _load_df(symbol: str, timeframe: str) -> pd.DataFrame:
    # NIFTY-100 stocks' daily data now comes from the permanent, auto-updated
    # pipeline (data/stock_daily/<SYMBOL>.csv — 7yr, refreshed by the daily
    # cron, always real/never fabricated) instead of a one-off parquet the
    # user had to fetch manually via data_fetcher.py. Only "1day" is covered
    # by this pipeline — other timeframes and non-NIFTY-100 symbols (indices
    # etc.) still fall back to the original parquet convention below.
    if timeframe == "1day":
        stock_csv = config.DATA_DIR / "stock_daily" / f"{symbol}.csv"
        if stock_csv.exists():
            df = pd.read_csv(stock_csv, parse_dates=["date"])
            df = df.set_index("date").rename_axis("datetime")
            if df.empty:
                raise HTTPException(422, f"{symbol}/{timeframe} की stock_daily CSV खाली है")
            return df

    safe = symbol.replace(" ", "_").replace("^", "")
    path = config.DATA_DIR / f"{safe}__{timeframe}.parquet"
    if not path.exists():
        raise HTTPException(
            404,
            f"{symbol}/{timeframe} का data नहीं मिला — पहले चलाओ: "
            f"python data_fetcher.py --timeframe {timeframe} --symbol {symbol}",
        )
    df = pd.read_parquet(path)
    if df.empty:
        raise HTTPException(422, f"{symbol}/{timeframe} की parquet file खाली है")
    return df


# ---------------------------------------------------------------- meta routes (checkbox grid इन्हीं से बनता है)
@app.get("/api/indicators")
def list_indicators():
    broken = set()
    if self_healing.BROKEN_INDICATORS_FILE.exists():
        try:
            import json
            broken = set(json.loads(self_healing.BROKEN_INDICATORS_FILE.read_text(encoding="utf-8")))
        except Exception:
            broken = set()
    return {
        "count": len(ind.INDICATOR_REGISTRY) - len(broken),
        "indicators": [
            {"name": n, "default_params": e["params"]}
            for n, e in ind.INDICATOR_REGISTRY.items() if n not in broken
        ],
        "disabled_broken": sorted(broken),
    }


@app.get("/api/universe")
def list_universe():
    df = pd.read_csv(config.UNIVERSE_FILE)
    return df.to_dict(orient="records")


@app.get("/api/timeframes")
def list_timeframes():
    return {"timeframes": list(config.TIMEFRAMES), "default": config.DEFAULT_TIMEFRAME}


@app.get("/api/strategies")
def list_strategies():
    return {"strategies": list(strat.STRATEGY_REGISTRY)}


@app.get("/api/health")
def health():
    return {"status": "ok", "indicators": len(ind.INDICATOR_REGISTRY)}


@app.get("/api/system_load")
def system_load():
    """Real CPU/memory load status — GREEN/YELLOW/RED (added 2026-07-24,
    per explicit request: a previously-planned status indicator that
    wasn't found anywhere in the actual code). cpu_percent(interval=0.3)
    takes a short real sample rather than the instant (and often
    misleading) 0.0 you get from interval=None on the first call."""
    cpu_pct = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    mem_pct = mem.percent
    combined = max(cpu_pct, mem_pct)

    if combined <= config.LOAD_GREEN_MAX_PCT:
        status = "green"
    elif combined <= config.LOAD_YELLOW_MAX_PCT:
        status = "yellow"
    else:
        status = "red"

    return {
        "status": status,
        "cpu_percent": round(cpu_pct, 1),
        "memory_percent": round(mem_pct, 1),
        "memory_used_mb": round(mem.used / (1024 * 1024), 1),
        "memory_total_mb": round(mem.total / (1024 * 1024), 1),
        "combined_percent": round(combined, 1),
        "green_max_pct": config.LOAD_GREEN_MAX_PCT,
        "yellow_max_pct": config.LOAD_YELLOW_MAX_PCT,
    }


@app.get("/api/self_check")
def self_check():
    """पूरा system चलाकर जांचता है — folders, data, हर indicator, backtest engine, sandbox।
    जो अपने-आप ठीक हो सकता है वो कर देता है (auto_fixed:true), बाकी को लाल निशान देता है।"""
    healer = self_healing.SystemHealer()
    return healer.run_all()


@app.get("/api/data_size")
def data_size():
    """data/ folder (जिसमें data_fetcher.py parquet फाइलें डालता है) कितनी heavy हो गई —
    dashboard के 'System Health' tab वाला green/orange/red gauge इसी से भरता है।
    Zone: total_mb <= DATA_SIZE_GREEN_MAX_MB -> हरा, danger_at_mb तक -> नारंगी, उसके ऊपर -> लाल।"""
    file_sizes = []
    if config.DATA_DIR.exists():
        for root, _dirs, files in os.walk(config.DATA_DIR):
            for fname in files:
                fpath = Path(root) / fname
                try:
                    size_bytes = fpath.stat().st_size
                except OSError:
                    continue
                file_sizes.append((str(fpath.relative_to(config.DATA_DIR)), size_bytes))

    total_bytes = sum(sz for _, sz in file_sizes)
    total_mb = round(total_bytes / (1024 * 1024), 2)
    total_files = len(file_sizes)

    file_sizes.sort(key=lambda x: x[1], reverse=True)
    top_files = [
        {"name": name, "mb": round(sz / (1024 * 1024), 2)}
        for name, sz in file_sizes[:8]
    ]

    green_max = config.DATA_SIZE_GREEN_MAX_MB
    danger_at = config.DATA_SIZE_DANGER_AT_MB
    if total_mb <= green_max:
        zone = "green"
    elif total_mb <= danger_at:
        zone = "orange"
    else:
        zone = "red"

    gauge_max = max(danger_at * 1.5, total_mb * 1.1, 1.0)

    return {
        "total_mb": total_mb,
        "total_files": total_files,
        "zone": zone,
        "green_max_mb": green_max,
        "danger_at_mb": danger_at,
        "gauge_max_mb": round(gauge_max, 1),
        "top_files": top_files,
    }


# ---------------------------------------------------------------- backtest history (added 2026-07-24)
MAX_HISTORY_ENTRIES = 200


def _append_history(entry: dict):
    """हर /api/backtest और /api/custom_backtest रन history file में जुड़ जाता है ताकि
    dashboard का 'Backtest History' tab पिछले टेस्ट दिखा सके। History खराब/corrupt निकले
    तो खाली मान लेता है — backtest का असली रिजल्ट देना कभी इसकी वजह से नहीं रुकना चाहिए।"""
    history = []
    if config.BACKTEST_HISTORY_FILE.exists():
        try:
            history = json.loads(config.BACKTEST_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            history = []
    history.append(entry)
    history = history[-MAX_HISTORY_ENTRIES:]
    config.BACKTEST_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")


@app.get("/api/backtest_history")
def backtest_history():
    if not config.BACKTEST_HISTORY_FILE.exists():
        return {"history": []}
    try:
        history = json.loads(config.BACKTEST_HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        history = []
    return {"history": list(reversed(history))}   # नया सबसे ऊपर


# ---------------------------------------------------------------- core: backtest
@app.post("/api/backtest")
def backtest(req: BacktestRequest):
    df = _load_df(req.symbol, req.timeframe)

    if req.toggled_indicators and not req.rules:
        rules = rb.toggled_indicators_to_default_rules(req.toggled_indicators)
    else:
        rules = [r.dict(exclude_none=True) for r in req.rules]

    if not rules:
        raise HTTPException(400, "कम-से-कम एक indicator चुनो या rule दो")

    try:
        signal = rb.build_signal(df, rules)
    except Exception as e:
        raise HTTPException(400, f"rule चलाने में दिक्कत: {e}")

    result = run_train_test(
        df, signal, split_date=req.split_date,
        target_pct=req.target_pct, sl_pct=req.sl_pct, max_hold_bars=req.max_hold_bars,
        slippage_pct=req.slippage_pct, commission_pct=req.commission_pct,
        position_capital_rs=req.position_capital_rs,
    )
    result["rules_used"] = rules
    try:
        _append_history({
            "timestamp": datetime.now(timezone.utc).isoformat(), "kind": "scanner",
            "symbol": req.symbol, "timeframe": req.timeframe,
            "label": " + ".join(req.toggled_indicators) or "custom rules",
            "test": result["test"], "verdict": result["verdict"],
        })
    except Exception:
        pass
    return result


@app.post("/api/backtest/strategy/{name}")
def backtest_strategy(name: str, symbol: str, timeframe: str = config.DEFAULT_TIMEFRAME):
    if name not in strat.STRATEGY_REGISTRY:
        raise HTTPException(404, f"strategy '{name}' नहीं मिली")
    df = _load_df(symbol, timeframe)
    signal = strat.STRATEGY_REGISTRY[name](df)
    return run_train_test(df, signal)


# ---------------------------------------------------------------- custom strategy (code paste box)
@app.post("/api/custom_backtest")
def custom_backtest(req: CustomBacktestRequest):
    """Dashboard के 'Custom Strategy' textarea से यहीं आता है। code sandbox में चलता है,
    फिर वही run_train_test इंजन चलता है जो checkbox-वाली strategies के लिए चलता है —
    इसलिए win-rate/target/SL/drawdown/overfit-check सब एक जैसे भरोसेमंद फॉर्मेट में मिलते हैं।"""
    df = _load_df(req.symbol, req.timeframe)

    try:
        signal = sandbox.run_user_strategy(req.code, df, func_name=req.func_name)
    except sandbox.SandboxError as e:
        raise HTTPException(400, str(e))

    result = run_train_test(
        df, signal, split_date=req.split_date,
        target_pct=req.target_pct, sl_pct=req.sl_pct, max_hold_bars=req.max_hold_bars,
        slippage_pct=req.slippage_pct, commission_pct=req.commission_pct,
        position_capital_rs=req.position_capital_rs,
    )
    # Garuda verdict — best-effort (2026-07-22): reuses the train_test result
    # above instead of re-running the backtest. Never lets a validator bug
    # take down an otherwise-working custom backtest response.
    try:
        result["garuda_verdict"] = _garuda_validator.validate_custom(req.code, result)
    except Exception as e:
        result["garuda_verdict"] = {"final_score": None, "verdict": "N/A", "error": str(e)}
    try:
        _append_history({
            "timestamp": datetime.now(timezone.utc).isoformat(), "kind": "custom",
            "symbol": req.symbol, "timeframe": req.timeframe, "label": req.func_name,
            "test": result["test"], "verdict": result["verdict"],
        })
    except Exception:
        pass
    return result


# ---------------------------------------------------------------- optimizer
@app.post("/api/optimize")
def optimize(req: OptimizeRequest):
    df = _load_df(req.symbol, req.timeframe)
    if req.mode == "grid":
        pool = req.indicator_pool or ["RSI", "MFI", "CCI", "WilliamsR", "StochRSI",
                                       "VolumeSpike", "ADX", "MACD", "PSARFlip", "HigherHighLowerLow"]
        results = opt.grid_search(df, indicator_pool=pool, combo_size=req.combo_size, top_n=req.top_n)
    else:
        results = opt.genetic_search(df, indicator_pool=req.indicator_pool, top_n=req.top_n)
    return {"mode": req.mode, "results": [r.summary() for r in results]}


# ---------------------------------------------------------------- multi-symbol batch scan (added 2026-07-24)
@app.post("/api/batch_backtest")
def batch_backtest(req: BatchBacktestRequest):
    """एक ही indicator-combo को कई symbols पर एक साथ चलाता है — हर symbol का अलग
    train/test result मिलता है। कोई symbol data-missing या rule-error से fail हो
    तो पूरा batch नहीं रुकता, बस उस symbol के आगे error दिख जाता है।"""
    if req.toggled_indicators and not req.rules:
        rules = rb.toggled_indicators_to_default_rules(req.toggled_indicators)
    else:
        rules = [r.dict(exclude_none=True) for r in req.rules]
    if not rules:
        raise HTTPException(400, "कम-से-कम एक indicator चुनो या rule दो")

    results = []
    for symbol in req.symbols:
        try:
            df = _load_df(symbol, req.timeframe)
            signal = rb.build_signal(df, rules)
            res = run_train_test(
                df, signal, split_date=req.split_date,
                target_pct=req.target_pct, sl_pct=req.sl_pct, max_hold_bars=req.max_hold_bars,
                slippage_pct=req.slippage_pct, commission_pct=req.commission_pct,
                position_capital_rs=req.position_capital_rs,
            )
            results.append({"symbol": symbol, "status": "ok", **res})
        except HTTPException as e:
            results.append({"symbol": symbol, "status": "error", "error": str(e.detail)})
        except Exception as e:
            results.append({"symbol": symbol, "status": "error", "error": str(e)})

    ok_results = [r for r in results if r["status"] == "ok"]
    ok_results.sort(key=lambda r: r["test"]["win_rate_%"], reverse=True)
    error_results = [r for r in results if r["status"] != "ok"]
    return {"rules_used": rules, "results": ok_results + error_results}


# ---------------------------------------------------------------- saved strategy library (added 2026-07-24)
def _load_strategy_library() -> dict:
    if not config.STRATEGY_LIBRARY_FILE.exists():
        return {}
    try:
        return json.loads(config.STRATEGY_LIBRARY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


@app.get("/api/strategy_library")
def list_strategy_library():
    lib = _load_strategy_library()
    items = [{"name": name, **meta} for name, meta in lib.items()]
    items.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
    return {"strategies": items}


@app.post("/api/strategy_library")
def save_strategy_library(req: SaveStrategyRequest):
    if not req.name.strip():
        raise HTTPException(400, "strategy का नाम खाली नहीं हो सकता")
    lib = _load_strategy_library()
    lib[req.name] = {
        "code": req.code, "func_name": req.func_name,
        "target_pct": req.target_pct, "sl_pct": req.sl_pct,
        "max_hold_bars": req.max_hold_bars, "split_date": req.split_date,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    config.STRATEGY_LIBRARY_FILE.write_text(json.dumps(lib, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "saved", "name": req.name}


@app.delete("/api/strategy_library/{name}")
def delete_strategy_library(name: str):
    lib = _load_strategy_library()
    if name not in lib:
        raise HTTPException(404, f"'{name}' नाम की कोई saved strategy नहीं मिली")
    del lib[name]
    config.STRATEGY_LIBRARY_FILE.write_text(json.dumps(lib, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "deleted", "name": name}


# ---------------------------------------------------------------- indicator correlation check (added 2026-07-24)
@app.post("/api/indicator_correlation")
def indicator_correlation(req: CorrelationRequest):
    """असली data पर हर चुने हुए indicator को compute करके pairwise Pearson correlation
    निकालता है। >=0.85 वाले जोड़े 'high_correlation_pairs' में अलग से दिखाए जाते हैं —
    इतने ज़्यादा correlated indicators साथ चुनना ज़्यादातर एक ही जानकारी दो बार गिनना है।"""
    if len(req.indicators) < 2:
        raise HTTPException(400, "कम-से-कम 2 indicators चुनो correlation देखने के लिए")
    df = _load_df(req.symbol, req.timeframe)

    series_map = {}
    for name in req.indicators:
        if name not in ind.INDICATOR_REGISTRY:
            raise HTTPException(400, f"indicator '{name}' नहीं मिला")
        try:
            out = ind.compute(name, df)
        except Exception as e:
            raise HTTPException(400, f"'{name}' चलाने में दिक्कत: {e}")
        if isinstance(out, pd.DataFrame):
            out = out.iloc[:, 0]   # multi-column indicator (MACD आदि) -> पहला column लिया
        series_map[name] = out

    combined = pd.DataFrame(series_map).dropna()
    if combined.empty:
        raise HTTPException(422, "इन indicators का data overlap नहीं हुआ (सब NaN)")
    corr = combined.corr()

    cols = list(corr.columns)
    matrix = [
        {"indicator": row, **{col: round(float(corr.loc[row, col]), 3) for col in cols}}
        for row in cols
    ]
    high_pairs = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            val = float(corr.iloc[i, j])
            if abs(val) >= 0.85:
                high_pairs.append({"a": cols[i], "b": cols[j], "corr": round(val, 3)})
    high_pairs.sort(key=lambda p: abs(p["corr"]), reverse=True)

    return {"indicators": cols, "matrix": matrix, "high_correlation_pairs": high_pairs, "rows_used": len(combined)}


# ---------------------------------------------------------------- dashboard (static)
@app.get("/")
def dashboard():
    path = config.BASE_DIR / "dashboard.html"
    if not path.exists():
        raise HTTPException(404, "dashboard.html नहीं मिली")
    return FileResponse(str(path))


app.mount("/static", StaticFiles(directory=str(config.BASE_DIR)), name="static")
