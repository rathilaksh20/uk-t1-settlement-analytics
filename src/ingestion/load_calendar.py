"""Load the UK business-day calendar from the gov.uk bank holidays JSON.

Run from the project root:  python -m src.ingestion.load_calendar
"""
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

URL = "https://www.gov.uk/bank-holidays.json"
RAW_DIR = Path("data/raw")
START = date(2025, 1, 1)

load_dotenv()
engine = create_engine(os.environ["DATABASE_URL"])


def main():
    resp = requests.get(URL, timeout=30)
    resp.raise_for_status()
    raw_bytes = resp.content

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    raw_path = RAW_DIR / f"bank_holidays_{stamp}.json"
    raw_path.write_bytes(raw_bytes)

    events = json.loads(raw_bytes)["england-and-wales"]["events"]
    holidays = {date.fromisoformat(e["date"]): e["title"] for e in events}

    # Only build the calendar up to the end of the last year the source covers,
    # so we never silently treat an uncovered holiday as a business day.
    end = date(max(holidays).year, 12, 31)

    rows = []
    d = START
    while d <= end:
        is_bd = d.weekday() < 5 and d not in holidays
        rows.append({"d": d, "bd": is_bd, "name": holidays.get(d)})
        d += timedelta(days=1)

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO business_calendar (calendar_date, is_business_day, holiday_name) "
                "VALUES (:d, :bd, :name) "
                "ON CONFLICT (calendar_date) DO UPDATE "
                "SET is_business_day = EXCLUDED.is_business_day, holiday_name = EXCLUDED.holiday_name"
            ),
            rows,
        )
        conn.execute(
            text(
                "INSERT INTO ingestion_log (source_id, source_url, retrieved_at, file_name, row_count, checksum, licence_note) "
                "VALUES ('D5', :url, :ts, :fn, :n, :cs, 'Open Government Licence')"
            ),
            {
                "url": URL,
                "ts": datetime.now(timezone.utc).replace(tzinfo=None),
                "fn": str(raw_path),
                "n": len(rows),
                "cs": hashlib.sha256(raw_bytes).hexdigest(),
            },
        )

    n_bd = sum(r["bd"] for r in rows)
    print(f"Calendar loaded {START} to {end}: {len(rows)} days, {n_bd} business days, {len(holidays)} holidays in source.")


if __name__ == "__main__":
    main()