"""Load Bank of England interest-rate series (source D4) into rates_daily.

    python -m src.ingestion.load_boe                     # download from the BoE
    python -m src.ingestion.load_boe --from-file x.csv   # load a CSV you downloaded by hand

Raw responses are saved unchanged under data/raw/boe/ and every load is
recorded in ingestion_log.
"""
import argparse
import hashlib
import io
import os
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

URL_BASE = "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
SERIES = {
    "IUDBEDR": "Official Bank Rate",
    "IUDSOIA": "SONIA",
    "XUDLUSS": "Spot exchange rate, US dollar into sterling",
}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; uk-t1-settlement-analytics portfolio project)"}
RAW_DIR = Path("data/raw/boe")

CREATE_TABLE = (
    "CREATE TABLE IF NOT EXISTS rates_daily ("
    "series_code VARCHAR(20) NOT NULL, obs_date DATE NOT NULL, value NUMERIC(14,6) NOT NULL, "
    "PRIMARY KEY (series_code, obs_date))"
)


def build_url(series_codes, date_from):
    d = f"{date_from.day:02d}/{MONTHS[date_from.month - 1]}/{date_from.year}"
    return (f"{URL_BASE}?csv.x=yes&Datefrom={d}&Dateto=now"
            f"&SeriesCodes={','.join(series_codes)}&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")


def parse_boe_csv(csv_text):
    """Return (rows, rejected, duplicates).
    rows: list of dicts {series_code, obs_date, value}. Empty cells are skipped
    silently (a series may have no observation on a given date); unparseable
    dates or values go to `rejected`."""
    df = pd.read_csv(io.StringIO(csv_text), dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    if "DATE" not in df.columns:
        raise ValueError("Unexpected CSV format (no DATE column). Starts with: " + csv_text[:200])

    rows, rejected, seen, duplicates = [], [], set(), 0
    for _, rec in df.iterrows():
        raw_date = str(rec["DATE"]).strip()
        parsed = pd.to_datetime(raw_date, format="%d %b %Y", errors="coerce")
        for code in df.columns:
            if code == "DATE":
                continue
            raw_val = str(rec[code]).strip()
            if raw_val == "":
                continue
            value = pd.to_numeric(raw_val, errors="coerce")
            if pd.isna(parsed) or pd.isna(value):
                rejected.append({"series_code": code, "raw_date": raw_date, "raw_value": raw_val})
                continue
            key = (code, parsed.date())
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            rows.append({"series_code": code, "obs_date": parsed.date(), "value": float(value)})
    return rows, rejected, duplicates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", default="2025-01-01")
    parser.add_argument("--series", default=",".join(SERIES))
    parser.add_argument("--from-file", help="load a CSV downloaded manually instead of calling the BoE")
    args = parser.parse_args()

    load_dotenv()
    engine = create_engine(os.environ["DATABASE_URL"])
    codes = [s.strip() for s in args.series.split(",") if s.strip()]

    if args.from_file:
        raw_bytes = Path(args.from_file).read_bytes()
        url = f"file:{args.from_file}"
    else:
        url = build_url(codes, date.fromisoformat(args.from_date))
        resp = requests.get(url, headers=HEADERS, timeout=60)
        if resp.status_code != 200:
            raise SystemExit(f"BoE returned HTTP {resp.status_code}. If this is 403, open the URL in a browser, "
                             f"save the CSV, and run again with --from-file.\nURL: {url}")
        raw_bytes = resp.content

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    raw_path = RAW_DIR / f"boe_{stamp}.csv"
    raw_path.write_bytes(raw_bytes)

    rows, rejected, duplicates = parse_boe_csv(raw_bytes.decode("utf-8-sig"))
    if not rows:
        raise SystemExit("No valid rows parsed. Check the series codes and the raw file: " + str(raw_path))

    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE))
        conn.execute(text(
            "INSERT INTO rates_daily (series_code, obs_date, value) VALUES (:series_code, :obs_date, :value) "
            "ON CONFLICT (series_code, obs_date) DO UPDATE SET value = EXCLUDED.value"), rows)
        conn.execute(text(
            "INSERT INTO ingestion_log (source_id, source_url, retrieved_at, file_name, row_count, checksum, licence_note) "
            "VALUES ('D4', :url, :ts, :fn, :n, :cs, :lic)"),
            {"url": url, "ts": datetime.now(timezone.utc).replace(tzinfo=None), "fn": str(raw_path),
             "n": len(rows), "cs": hashlib.sha256(raw_bytes).hexdigest(),
             "lic": "Bank of England statistical database; see BoE copyright and re-use terms"})

    by_series = {}
    for r in rows:
        by_series.setdefault(r["series_code"], []).append(r["obs_date"])
    for code, ds in sorted(by_series.items()):
        print(f"{code}: {len(ds)} rows, {min(ds)} to {max(ds)}")
    print(f"Loaded {len(rows)} rows. Rejected: {len(rejected)}. Duplicates skipped: {duplicates}. Raw file: {raw_path}")
    for r in rejected[:5]:
        print("  rejected:", r)
    missing = [c for c in codes if c not in by_series]
    if missing:
        print("WARNING: no data returned for:", ", ".join(missing), "(check the series code in the BoE database)")


if __name__ == "__main__":
    main()