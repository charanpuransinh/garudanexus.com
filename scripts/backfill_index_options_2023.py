"""
backfill_index_options_2023.py — fills the 2023-07-25..2023-12-31 gap in
data/options_expiry/index_options/{NIFTY,BANKNIFTY}.csv.

Why the gap exists: NSE's current UDiFF Common Bhavcopy Final archive
(what download_options_expiry.py uses) only has files starting
2024-01-01 — every earlier date 404s there, which the main script's
holiday-skip logic silently (and wrongly) treated as "market holiday".
NSE's OLDER per-day bhavcopy archive (discontinued for new data, but
still serving old dates) DOES have this period — confirmed by hand:
02-Oct-2023 (Gandhi Jayanti, genuine holiday) 404s there too, but
25-Jul/01-Aug/15-Sep/01-Nov/01-Dec/29-Dec-2023 all return real data.

Old-format columns: INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,
OPEN,HIGH,LOW,CLOSE,SETTLE_PR,CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,
TIMESTAMP — no underlying-price column, so UndrlygPric is left blank
for these backfilled rows only (every other field maps directly).

Only NIFTY + BANKNIFTY (OPTIDX rows) — index options, not stock
options, per priority. Real data only — no fabricated rows.
"""
import csv
import io
import gzip
import zipfile
from pathlib import Path
from datetime import datetime, timedelta

import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent
_OUT_DIR = _REPO_ROOT / "data" / "options_expiry" / "index_options"

_OLD_URL = "https://nsearchives.nseindia.com/content/historical/DERIVATIVES/{yyyy}/{mon}/fo{ddmon}bhav.csv.zip"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

_OUT_COLUMNS = [
    "TradDt", "TckrSymb", "XpryDt", "StrkPric", "OptnTp",
    "OpnPric", "HghPric", "LwPric", "ClsPric", "SttlmPric",
    "OpnIntrst", "ChngInOpnIntrst", "TtlTradgVol", "UndrlygPric",
]
_SYMBOLS = ["NIFTY", "BANKNIFTY"]

START = datetime(2023, 7, 25)
END = datetime(2023, 12, 31)


def _path_for(symbol: str) -> Path:
    return _OUT_DIR / f"{symbol}.csv.gz"


def _existing_dates(symbol: str) -> set:
    path = _path_for(symbol)
    if not path.exists():
        return set()
    with gzip.open(path, "rt", newline="") as f:
        return {row["TradDt"] for row in csv.DictReader(f)}


def download_one_day(day: datetime) -> dict | None:
    ddmon = day.strftime("%d%b%Y").upper()
    mon = day.strftime("%b").upper()
    url = _OLD_URL.format(yyyy=day.year, mon=mon, ddmon=ddmon)
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    by_symbol: dict = {}
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        inner_name = z.namelist()[0]
        with z.open(inner_name) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            for row in reader:
                if row.get("INSTRUMENT") != "OPTIDX":
                    continue
                sym = row.get("SYMBOL")
                optn = row.get("OPTION_TYP")
                if sym not in _SYMBOLS or optn not in ("CE", "PE"):
                    continue
                xpry = datetime.strptime(row["EXPIRY_DT"], "%d-%b-%Y").strftime("%Y-%m-%d")
                out_row = {
                    "TradDt": day.strftime("%Y-%m-%d"),
                    "TckrSymb": sym,
                    "XpryDt": xpry,
                    "StrkPric": row["STRIKE_PR"],
                    "OptnTp": optn,
                    "OpnPric": row["OPEN"],
                    "HghPric": row["HIGH"],
                    "LwPric": row["LOW"],
                    "ClsPric": row["CLOSE"],
                    "SttlmPric": row["SETTLE_PR"],
                    "OpnIntrst": row["OPEN_INT"],
                    "ChngInOpnIntrst": row["CHG_IN_OI"],
                    "TtlTradgVol": row["CONTRACTS"],
                    "UndrlygPric": "",  # not present in this old format
                }
                by_symbol.setdefault(sym, []).append(out_row)
    return by_symbol


def merge_and_sort(symbol: str, new_rows: list):
    """Old (backfilled) rows must come BEFORE the existing 2024+ rows in
    the file — read what's there, prepend, sort by TradDt, rewrite."""
    path = _path_for(symbol)
    existing_rows = []
    if path.exists():
        with gzip.open(path, "rt", newline="") as f:
            existing_rows = list(csv.DictReader(f))
    all_rows = new_rows + existing_rows
    all_rows.sort(key=lambda r: (r["TradDt"], r["XpryDt"], r["StrkPric"], r["OptnTp"]))
    with gzip.open(path, "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_OUT_COLUMNS)
        w.writeheader()
        w.writerows(all_rows)


def main():
    existing = {sym: _existing_dates(sym) for sym in _SYMBOLS}
    pending = {sym: [] for sym in _SYMBOLS}

    day = START
    ok, holidays = 0, 0
    while day <= END:
        if day.weekday() >= 5:
            day += timedelta(days=1)
            continue
        trad_dt = day.strftime("%Y-%m-%d")
        if all(trad_dt in existing[sym] for sym in _SYMBOLS):
            day += timedelta(days=1)
            continue

        print(f"{day.strftime('%Y-%m-%d')}...", end=" ", flush=True)
        by_symbol = download_one_day(day)
        if by_symbol is None:
            print("no file (holiday)")
            holidays += 1
            day += timedelta(days=1)
            continue

        rows_written = 0
        for sym, rows in by_symbol.items():
            if trad_dt in existing[sym]:
                continue
            pending[sym].extend(rows)
            rows_written += len(rows)
        print(f"OK, {rows_written} rows")
        ok += 1
        day += timedelta(days=1)

    for sym in _SYMBOLS:
        if pending[sym]:
            merge_and_sort(sym, pending[sym])
            print(f"{sym}: merged {len(pending[sym])} backfilled rows")

    print(f"\nDone: {ok} days downloaded, {holidays} holidays skipped.")


if __name__ == "__main__":
    main()
