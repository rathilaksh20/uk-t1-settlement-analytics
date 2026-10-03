"""Load daily share prices (source D3) into market_prices_daily.

    python -m src.ingestion.load_prices                      # download via yfinance
    python -m src.ingestion.load_prices --from-file p.csv    # load a CSV: ticker,date,close,volume

Yahoo quotes London shares in PENCE; this loader converts to pounds.
yfinance is an unofficial wrapper around Yahoo data: personal/educational use only,
do not redistribute. Raw downloads stay in data/raw/prices/ (git-ignored).
"""
import argparse
import hashlib
import os
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from src.synthetic.trades import PLACEHOLDER_PRICE_GBP

RAW_DIR = Path("data/raw/prices")
CREATE_TABLE = (
    "CREATE TABLE IF NOT EXISTS market_prices_daily ("
    "isin CHAR(12) NOT NULL, price_date DATE NOT NULL, close_gbp NUMERIC(14,4) NOT NULL, "
    "volume BIGINT, source VARCHAR(30) NOT NULL, PRIMARY KEY (isin, price_date))"
)


def yahoo_symbol(ticker):
    """HSBA -> HSBA.L ; BP. -> BP.L"""
    return ticker + "L" if ticker.endswith(".") else ticker + ".L"


def build_rows(records, ticker_to_isin, source="yahoo_via_yfinance", already_gbp=()):
    """records: dicts with ticker, date, close (pence), volume.
    Returns (rows, rejected, duplicates). Converts pence to pounds, except for
    tickers listed in already_gbp, which Yahoo quotes in pounds."""
    rows, rejected, seen, dups = [], [], set(), 0
    for r in records:
        isin = ticker_to_isin.get(r["ticker"])
        d = pd.to_datetime(r["date"], errors="coerce")
        close = pd.to_numeric(r["close"], errors="coerce")
        vol = pd.to_numeric(r.get("volume"), errors="coerce")
        if isin is None or pd.isna(d) or pd.isna(close) or close <= 0:
            rejected.append(r)
            continue
        key = (isin, d.date())
        if key in seen:
            dups += 1
            continue
        seen.add(key)
        divisor = 1.0 if r["ticker"] in already_gbp else 100.0
        rows.append({"isin": isin, "price_date": d.date(),
                     "close_gbp": round(float(close) / divisor, 4),
                     "volume": None if pd.isna(vol) else int(vol), "source": source})
    return rows, rejected, dups


def scale_report(rows, isin_to_ticker):
    """Compare median loaded price with the generator's placeholder level to catch
    pence/pounds mistakes. Returns list of (ticker, n, last_close, placeholder, ratio, flag)."""
    by = {}
    for r in rows:
        by.setdefault(r["isin"], []).append((r["price_date"], r["close_gbp"]))
    out = []
    for isin, vals in sorted(by.items(), key=lambda kv: isin_to_ticker[kv[0]]):
        t = isin_to_ticker[isin]
        vals.sort()
        prices = sorted(v for _, v in vals)
        median = prices[len(prices) // 2]
        ph = PLACEHOLDER_PRICE_GBP.get(t)
        ratio = median / ph if ph else None
        flag = "CHECK SCALE" if ratio is not None and not (0.2 <= ratio <= 5) else ""
        out.append((t, len(vals), vals[-1][1], ph, ratio, flag))
    return out


def fetch_yahoo(instruments, start):
    import yfinance as yf  # imported lazily so tests and other scripts do not need it
    records = []
    for ticker, _isin in instruments:
        sym = yahoo_symbol(ticker)
        df = yf.Ticker(sym).history(start=start, auto_adjust=False)
        if df is None or df.empty:
            print(f"WARNING: no data for {sym}")
            continue
        for ts, r in df.iterrows():
            records.append({"ticker": ticker, "date": ts.date().isoformat(),
                            "close": float(r["Close"]), "volume": int(r["Volume"])})
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", default="2026-06-01")
    parser.add_argument("--from-file")
    parser.add_argument("--already-gbp", default="")
    args = parser.parse_args()

    load_dotenv()
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        instruments = [(r[0], r[1]) for r in conn.execute(text("SELECT ticker, isin FROM instruments ORDER BY 1"))]
    ticker_to_isin = dict(instruments)
    isin_to_ticker = {v: k for k, v in instruments}

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    raw_path = RAW_DIR / f"prices_{stamp}.csv"
    if args.from_file:
        raw_bytes = Path(args.from_file).read_bytes()
        raw_path.write_bytes(raw_bytes)
        records = pd.read_csv(raw_path, dtype=str, keep_default_na=False).to_dict("records")
        url = f"file:{args.from_file}"
    else:
        records = fetch_yahoo(instruments, args.from_date)
        if not records:
            raise SystemExit("No price data downloaded. Yahoo may be blocking or rate-limiting; "
                             "wait and retry, or load a CSV with --from-file (ticker,date,close,volume).")
        pd.DataFrame(records).to_csv(raw_path, index=False)
        raw_bytes = raw_path.read_bytes()
        url = "yfinance:" + ",".join(yahoo_symbol(t) for t, _ in instruments[:3]) + ",..."

    already = {t.strip() for t in args.already_gbp.split(",") if t.strip()}
    rows, rejected, dups = build_rows(records, ticker_to_isin, already_gbp=already)
    if not rows:
        raise SystemExit("No valid price rows. Check the raw file: " + str(raw_path))

    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE))
        conn.execute(text(
            "INSERT INTO market_prices_daily (isin, price_date, close_gbp, volume, source) "
            "VALUES (:isin, :price_date, :close_gbp, :volume, :source) "
            "ON CONFLICT (isin, price_date) DO UPDATE SET close_gbp = EXCLUDED.close_gbp, volume = EXCLUDED.volume"), rows)
        conn.execute(text(
            "INSERT INTO ingestion_log (source_id, source_url, retrieved_at, file_name, row_count, checksum, licence_note) "
            "VALUES ('D3', :url, :ts, :fn, :n, :cs, :lic)"),
            {"url": url, "ts": datetime.now(timezone.utc).replace(tzinfo=None), "fn": str(raw_path),
             "n": len(rows), "cs": hashlib.sha256(raw_bytes).hexdigest(),
             "lic": "Yahoo Finance via yfinance: personal/educational use, no redistribution"})

    print(f"{'ticker':<6}{'rows':>6}{'last_close_gbp':>16}{'placeholder':>13}{'ratio':>8}  note")
    for t, n, last, ph, ratio, flag in scale_report(rows, isin_to_ticker):
        print(f"{t:<6}{n:>6}{last:>16.4f}{(ph or 0):>13.2f}{(ratio or 0):>8.2f}  {flag}")
    print(f"Loaded {len(rows)} price rows. Rejected: {len(rejected)}. Duplicates skipped: {dups}. Raw file: {raw_path}")
    missing = [t for t, i in instruments if i not in {r['isin'] for r in rows}]
    if missing:
        print("WARNING: no prices loaded for:", ", ".join(missing))


if __name__ == "__main__":
    main()