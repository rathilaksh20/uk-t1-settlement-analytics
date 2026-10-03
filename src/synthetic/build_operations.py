"""Build the operations layer for the trades already in the database:
counterparty profiles, stage durations, positions, events, flags and status.

Run from the project root:   python -m src.synthetic.build_operations --seed 42
All output is SYNTHETIC.
"""
import argparse
import os
from collections import Counter

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from src.synthetic.operations import make_profiles, pick_shock_days, simulate_operations
from src.synthetic.trades import business_days_between


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    load_dotenv()
    engine = create_engine(os.environ["DATABASE_URL"])

    with engine.begin() as conn:
        trades = conn.execute(text(
            "SELECT trade_id, counterparty_id, side, quantity, price, trade_datetime, settlement_date "
            "FROM trades ORDER BY trade_id")).mappings().all()
        if not trades:
            print("No trades found. Run: python -m src.synthetic.trades --n 1000 --reset")
            return
        cps = [r[0] for r in conn.execute(text("SELECT counterparty_id FROM counterparties ORDER BY 1"))]
        holidays = {r[0] for r in conn.execute(text(
            "SELECT calendar_date FROM business_calendar WHERE holiday_name IS NOT NULL"))}

        for t in ("settlement_flags", "settlement_events", "stage_durations",
                  "settlement_status", "counterparty_profile"):
            conn.execute(text(f"DELETE FROM {t}"))

        profiles = make_profiles(cps, args.seed)
        first = min(t["trade_datetime"] for t in trades).date()
        last = max(t["trade_datetime"] for t in trades).date()
        shock_days = pick_shock_days(business_days_between(first, last, holidays), args.seed)
        rng = np.random.default_rng(args.seed)

        status_rows, flag_rows, event_rows, dur_rows, trade_updates = [], [], [], [], []
        flag_counts = Counter()
        for tr in trades:
            trade = {
                "side": tr["side"], "quantity": float(tr["quantity"]), "price": float(tr["price"]),
                "trade_datetime": tr["trade_datetime"], "settlement_date": tr["settlement_date"],
            }
            o = simulate_operations(trade, profiles[tr["counterparty_id"]], rng, holidays, shock_days)
            tid = tr["trade_id"]
            flags = o["flags"]
            flag_counts.update(flags)

            status_rows.append({
                "trade_id": tid,
                "cash_required": o["cash_required"], "cash_available": o["cash_available"],
                "securities_required": o["securities_required"], "securities_available": o["securities_available"],
                "instruction_status": "INVALID" if "INSTRUCTION_MISMATCH" in flags else "VALID",
                "reconciliation_status": "BREAK" if "RECONCILIATION_BREAK" in flags else "RECONCILED",
                "settlement_status": "AT_RISK" if flags else "READY_TO_SETTLE",
                "primary_reason": o["primary_reason"],
            })
            flag_rows += [{"trade_id": tid, "flag_type": f} for f in flags]
            dur_rows.append({
                "trade_id": tid, "c": round(o["conf_h"], 3), "m": round(o["match_h"], 3),
                "i": round(o["instr_h"], 3), "s": o["shock"],
            })
            for etype, ts, deadline in (
                ("TRADE_CONFIRMED", o["t_conf"], o["conf_deadline"]),
                ("TRADE_MATCHED", o["t_match"], o["match_deadline"]),
                ("INSTRUCTION_SENT", o["t_instr"], o["instr_deadline"]),
            ):
                event_rows.append({"trade_id": tid, "etype": etype, "ts": ts,
                                   "st": "ON_TIME" if ts <= deadline else "LATE"})
            event_rows.append({"trade_id": tid, "etype": "TRADE_CREATED",
                               "ts": tr["trade_datetime"], "st": "DONE"})
            trade_updates.append({
                "trade_id": tid,
                "conf": "LATE_CONFIRMED" if "LATE_CONFIRMATION" in flags else "CONFIRMED",
                "match": "UNMATCHED" if "UNMATCHED" in flags else "MATCHED",
            })

        conn.execute(text(
            "INSERT INTO counterparty_profile (counterparty_id, reliability, responsiveness) "
            "VALUES (:cp, :rel, :resp)"),
            [{"cp": k, "rel": round(v["reliability"], 3), "resp": round(v["responsiveness"], 3)}
             for k, v in profiles.items()])
        conn.execute(text(
            "INSERT INTO settlement_status (trade_id, cash_required, cash_available, securities_required, "
            "securities_available, instruction_status, reconciliation_status, settlement_status, primary_reason) "
            "VALUES (:trade_id, :cash_required, :cash_available, :securities_required, :securities_available, "
            ":instruction_status, :reconciliation_status, :settlement_status, :primary_reason)"), status_rows)
        conn.execute(text(
            "INSERT INTO stage_durations (trade_id, confirmation_hours, matching_hours, instruction_hours, shock_day) "
            "VALUES (:trade_id, :c, :m, :i, :s)"), dur_rows)
        conn.execute(text(
            "INSERT INTO settlement_events (trade_id, event_type, event_timestamp, event_status) "
            "VALUES (:trade_id, :etype, :ts, :st)"), event_rows)
        if flag_rows:
            conn.execute(text(
                "INSERT INTO settlement_flags (trade_id, flag_type) VALUES (:trade_id, :flag_type)"), flag_rows)
        conn.execute(text(
            "UPDATE trades SET confirmation_status = :conf, matching_status = :match WHERE trade_id = :trade_id"),
            trade_updates)

    at_risk = sum(1 for r in status_rows if r["settlement_status"] == "AT_RISK")
    print(f"Processed {len(trades)} trades: {at_risk} AT_RISK ({100 * at_risk / len(trades):.1f}%).")
    for flag, n in flag_counts.most_common():
        print(f"  {flag:22s}{n:5d}")


if __name__ == "__main__":
    main()