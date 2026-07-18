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
from backtest_core import run_train_test

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
    return {
        "count": len(ind.INDICATOR_REGISTRY),
        "indicators": [
            {"name": n, "default_params": e["params"]}
            for n, e in ind.INDICATOR_REGISTRY.items()
        ],
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
