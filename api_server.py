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

import os
from pathlib import Path
from typing import List, Optional

import pandas as pd
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


class CustomBacktestRequest(BaseModel):
    symbol: str
    timeframe: str = config.DEFAULT_TIMEFRAME
    code: str                              # यूज़र का पेस्ट किया Python code
    func_name: str = "my_strategy"         # code में यही नाम का function ढूंढा जाएगा
    target_pct: float = config.DEFAULT_TARGET_PCT
    sl_pct: float = config.DEFAULT_SL_PCT
    max_hold_bars: int = config.DEFAULT_MAX_HOLD_BARS
    split_date: str = config.TRAIN_TEST_SPLIT_DATE


class OptimizeRequest(BaseModel):
    symbol: str
    timeframe: str = config.DEFAULT_TIMEFRAME
    mode: str = "genetic"       # "grid" या "genetic"
    combo_size: int = 2         # grid mode के लिए
    indicator_pool: Optional[List[str]] = None
    top_n: int = 10


# ---------------------------------------------------------------- data loading
def _load_df(symbol: str, timeframe: str) -> pd.DataFrame:
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


@app.get("/api/data_size")
def data_size():
    """data/ folder कितना heavy हुआ — dashboard के green/orange/red gauge के लिए।"""
    return self_healing.data_disk_usage()


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
    )
    result["rules_used"] = rules
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
    )
    # Garuda verdict — best-effort (2026-07-22): reuses the train_test result
    # above instead of re-running the backtest. Never lets a validator bug
    # take down an otherwise-working custom backtest response.
    try:
        result["garuda_verdict"] = _garuda_validator.validate_custom(req.code, result)
    except Exception as e:
        result["garuda_verdict"] = {"final_score": None, "verdict": "N/A", "error": str(e)}
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


# ---------------------------------------------------------------- dashboard (static)
@app.get("/")
def dashboard():
    path = config.BASE_DIR / "dashboard.html"
    if not path.exists():
        raise HTTPException(404, "dashboard.html नहीं मिली")
    return FileResponse(str(path))


app.mount("/static", StaticFiles(directory=str(config.BASE_DIR)), name="static")
