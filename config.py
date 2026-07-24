"""
config.py
---------
सारे settings यहीं से control होंगे — UI के dropdown/slider इन्हीं values को दिखाएंगे।
कहीं और hardcode मत करना, यहीं बदलना।
"""

from pathlib import Path

# ---------- Paths ----------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"                 # OHLCV parquet files यहाँ स्टोर होंगे
OPTIONS_DIR = BASE_DIR / "data" / "options"   # options chain data
UNIVERSE_FILE = BASE_DIR / "universe.csv"
RESULTS_DIR = BASE_DIR / "results"

for d in (DATA_DIR, OPTIONS_DIR, RESULTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---------- Timeframes ----------
# key -> pandas resample rule
TIMEFRAMES = {
    "3min": "3min",
    "5min": "5min",
    "15min": "15min",
    "30min": "30min",
    "1hour": "1h",
    "1day": "1D",
    "1week": "1W",
}
DEFAULT_TIMEFRAME = "15min"

# ---------- Date range ----------
YEAR_MIN = 2018
YEAR_MAX = 2026
DEFAULT_YEAR_RANGE = (2018, 2026)

# Train/Test split — overfitting रोकने के लिए यही cutoff डिफ़ॉल्ट रहेगा
TRAIN_TEST_SPLIT_DATE = "2023-12-31"

# ---------- Instrument type ----------
INSTRUMENT_TYPES = ["INDEX", "STOCK"]

# ---------- Backtest defaults ----------
DEFAULT_TARGET_PCT = 1.0     # target % move
DEFAULT_SL_PCT = 0.5         # stoploss % move
DEFAULT_MAX_HOLD_BARS = 20   # कितने bars तक trade होल्ड करनी है अगर target/SL ना लगे

# ---------- Backtest realism: slippage, commission, position sizing (added 2026-07-24) ----------
DEFAULT_SLIPPAGE_PCT = 0.05      # हर entry/exit fill असली चाहे गए price से इतना % worse (trader के खिलाफ़)
DEFAULT_COMMISSION_PCT = 0.03    # round-trip (entry+exit) brokerage — return_pct से सीधा घटता है
DEFAULT_POSITION_CAPITAL_RS = 50000.0   # per-trade rupee allocation, total_pnl_rs निकालने के लिए

# ---------- Options data ----------
OPTIONS_GREEKS = ["delta", "gamma", "theta", "vega", "iv"]
OPTIONS_FIELDS = ["strike", "expiry", "oi", "oi_change", "iv", "ltp"] + OPTIONS_GREEKS

# ---------- Data disk-usage meter (dashboard के "System Health" tab वाला gauge) ----------
# data/ folder इतने MB तक हो तो हरा, इससे ज़्यादा-पर-danger से कम हो तो नारंगी,
# DATA_SIZE_DANGER_MB के आगे निकल जाए तो लाल (danger zone) — dashboard पर यही 3 रंग दिखेंगे
DATA_SIZE_GREEN_MB = 500
DATA_SIZE_DANGER_MB = 2000

# ---------- Data size gauge (dashboard "System Health" tab) ----------
DATA_SIZE_GREEN_MAX_MB = 500     # इससे कम -> हरा, ठीक है
DATA_SIZE_DANGER_AT_MB = 2000    # इससे ज़्यादा -> लाल, danger zone (बीच में नारंगी)

# ---------- System load indicator (dashboard's GREEN/YELLOW/RED status pill) ----------
# Combined CPU% + memory% (whichever is higher) drives the status:
#   <= LOAD_GREEN_MAX_PCT           -> green (normal)
#   LOAD_GREEN_MAX_PCT..YELLOW_MAX  -> yellow (getting close to capacity)
#   > LOAD_YELLOW_MAX_PCT           -> red (real load, backtest/optimizer runs will feel slow)
LOAD_GREEN_MAX_PCT = 60
LOAD_YELLOW_MAX_PCT = 85

# ---------- Optimizer ----------
OPTIMIZER_MAX_COMBO_SIZE = 5       # एक साथ ज़्यादा से ज़्यादा कितने indicators combine होंगे
OPTIMIZER_WALK_FORWARD_FOLDS = 4   # walk-forward validation folds
OPTIMIZER_POP_SIZE = 40            # genetic algorithm population
OPTIMIZER_GENERATIONS = 25
