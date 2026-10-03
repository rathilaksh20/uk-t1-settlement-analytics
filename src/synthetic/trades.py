"""Synthetic trade generator, version 1.

Creates trade facts only (instrument, counterparty, side, quantity, price,
timestamp, settlement date). Confirmation and matching statuses are set to
PENDING here; the causal stage model fills them in the next step.

All data produced here is SYNTHETIC. Prices below are PLACEHOLDER levels
in GBP, to be replaced by real prices in Week 4.

Run from the project root:
    python -m src.synthetic.trades --n 1000 --reset
"""
import argparse
import os
from datetime import date, datetime, timedelta

import numpy as np

from src.settlement.dates import is_business_day, settlement_date

PLACEHOLDER_PRICE_GBP = {
    "HSBA": 9.5, "AZN": 105.0, "SHEL": 27.0, "BP.": 4.2, "BARC": 3.0,
    "LLOY": 0.7, "DGE": 20.0, "GSK": 15.0, "RIO": 50.0, "VOD": 0.7,
    "NG.": 11.0, "TSCO": 4.0, "BA.": 15.0, "GLEN": 4.0, "RKT": 50.0,
    "RR.": 8.0, "STAN": 15.0, "LGEN": 2.5, "CPG": 25.0,
}

START = date(2026, 7, 1)
END = date(2026, 9, 30)
MARKET_OPEN_MIN = 8 * 60          # 08:00
MARKET_CLOSE_MIN = 16 * 60 + 30   # 16:30


def business_days_between(start, end, holidays):
    days, d = [], start
    while d <= end:
        if is_business_day(d, holidays):
            days.append(d)
        d += timedelta(days=1)
    return days


def intraday_minute_weights():
    """U-shaped profile: busier near the open and the close."""
    minutes = np.arange(MARKET_OPEN_MIN, MARKET_CLOSE_MIN, 5)
    w = (1.0
         + 2.5 * np.exp(-((minutes - MARKET_OPEN_MIN) / 45.0) ** 2)
         + 2.0 * np.exp(-((minutes - MARKET_CLOSE_MIN) / 45.0) ** 2))
    return minutes, w / w.sum()


def generate_trades(n, seed, instruments, counterparty_ids, holidays,
                    start=START, end=END, cycle_days=2):
    """instruments: list of (instrument_id, ticker). Returns a list of dicts."""
    rng = np.random.default_rng(seed)
    days = business_days_between(start, end, holidays)
    minutes, minute_w = intraday_minute_weights()

    inst_w = rng.dirichlet(np.full(len(instruments), 3.0))
    cp_w = rng.dirichlet(np.full(len(counterparty_ids), 2.0))

    trades = []
    for i in range(1, n + 1):
        inst_id, ticker = instruments[rng.choice(len(instruments), p=inst_w)]
        cp_id = counterparty_ids[rng.choice(len(counterparty_ids), p=cp_w)]
        side = "BUY" if rng.random() < 0.5 else "SELL"

        # Heavy-tailed size, rounded to 100 shares, capped.
        qty = int(np.clip(rng.lognormal(mean=np.log(8000), sigma=1.0), 100, 500_000))
        qty = max(100, round(qty / 100) * 100)

        base = PLACEHOLDER_PRICE_GBP[ticker]
        price = round(base * float(rng.normal(1.0, 0.01)), 4)
        price = max(price, 0.01)

        trade_day = days[rng.integers(len(days))]
        minute = int(rng.choice(minutes, p=minute_w))
        trade_dt = datetime(trade_day.year, trade_day.month, trade_day.day,
                            minute // 60, minute % 60)

        trades.append({
            "trade_id": f"TRD{i:06d}",
            "instrument_id": inst_id,
            "counterparty_id": cp_id,
            "side": side,
            "quantity": qty,
            "price": price,
            "trade_currency": "GBP",
            "trade_datetime": trade_dt,
            "settlement_date": settlement_date(trade_day, cycle_days, holidays),
            "confirmation_status": "PENDING",
            "matching_status": "PENDING",
        })
    return trades


def main():
    from dotenv import load_dotenv
    from sqlalchemy import create_engine, text

    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--reset", action="store_true",
                        help="delete existing trades and dependent rows first")
    args = parser.parse_args()

    load_dotenv()
    engine = create_engine(os.environ["DATABASE_URL"])

    with engine.begin() as conn:
        existing = conn.execute(text("SELECT COUNT(*) FROM trades")).scalar()
        if existing and not args.reset:
            print(f"{existing} trades already exist. Use --reset to regenerate.")
            return
        if args.reset:
                        for t in ("exceptions", "settlement_flags", "settlement_events", "stage_durations","settlement_status", "trades"):
                            conn.execute(text(f"DELETE FROM {t}"))

        instruments = [tuple(r) for r in conn.execute(
            text("SELECT instrument_id, ticker FROM instruments ORDER BY 1"))]
        cps = [r[0] for r in conn.execute(
            text("SELECT counterparty_id FROM counterparties ORDER BY 1"))]
        holidays = {r[0] for r in conn.execute(text(
            "SELECT calendar_date FROM business_calendar WHERE holiday_name IS NOT NULL"))}

        trades = generate_trades(args.n, args.seed, instruments, cps, holidays)
        conn.execute(text(
            "INSERT INTO trades (trade_id, instrument_id, counterparty_id, side, quantity, price, "
            "trade_currency, trade_datetime, settlement_date, confirmation_status, matching_status) "
            "VALUES (:trade_id, :instrument_id, :counterparty_id, :side, :quantity, :price, "
            ":trade_currency, :trade_datetime, :settlement_date, :confirmation_status, :matching_status)"),
            trades)

    print(f"Inserted {len(trades)} synthetic trades (seed={args.seed}).")


if __name__ == "__main__":
    main()