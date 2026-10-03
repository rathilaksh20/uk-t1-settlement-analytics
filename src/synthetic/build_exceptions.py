"""Turn settlement flags into exception records (SYNTHETIC).

Run AFTER build_operations, from the project root:
    python -m src.synthetic.build_exceptions --seed 42

Resolution times are causal where possible: an unmatched trade is resolved when
the match actually completes, a late confirmation when confirmation completes,
and so on. Funding shortfalls and reconciliation breaks use sampled resolution
times, and a small share stay OPEN so ageing analysis has something to show.
"""
import argparse
import os
from collections import Counter
from datetime import timedelta

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from src.settlement.clock import add_business_hours
from src.settlement.rules import deadlines

SEVERITIES = ["LOW", "MEDIUM", "HIGH"]
BUMP_FLAGS = {"CASH_SHORTFALL", "SECURITIES_SHORTFALL", "LATE_SETTLEMENT"}


def severity_for(flag, notional):
    base = 0 if notional < 100_000 else (1 if notional < 500_000 else 2)
    bump = 1 if flag in BUMP_FLAGS else 0
    return SEVERITIES[min(2, base + bump)]


def build_exception(flag, notional, ev, dl, rng, holidays):
    """ev: dict with t_conf, t_match, t_instr. dl: deadlines dict.
    Returns a dict ready to insert into the exceptions table."""
    status = "RESOLVED"
    if flag == "UNMATCHED":
        created, resolved = dl["match_deadline"], ev["t_match"]
    elif flag == "LATE_CONFIRMATION":
        created, resolved = dl["conf_deadline"], ev["t_conf"]
    elif flag == "INSTRUCTION_MISMATCH":
        created, resolved = dl["instr_deadline"], ev["t_instr"]
    elif flag == "LATE_SETTLEMENT":
        created, resolved = dl["settle_cutoff"], max(ev["t_match"], ev["t_instr"])
    elif flag in ("CASH_SHORTFALL", "SECURITIES_SHORTFALL"):
        created = dl["match_deadline"] - timedelta(hours=3)          # pre-funding check
        hours = float(rng.lognormal(np.log(6.0), 0.7))
        resolved = add_business_hours(created, hours, holidays)
        if rng.random() < 0.04:
            status, resolved = "OPEN", None
    elif flag == "RECONCILIATION_BREAK":
        created = dl["settle_cutoff"] + timedelta(hours=4)           # post-settlement recon
        hours = float(rng.lognormal(np.log(30.0), 0.6))
        resolved = add_business_hours(created, hours, holidays)
        if rng.random() < 0.10:
            status, resolved = "OPEN", None
    else:
        raise ValueError(f"Unknown flag: {flag}")

    if resolved is not None:
        resolved = resolved.replace(microsecond=0)
    return {
        "exception_type": flag,
        "severity": severity_for(flag, notional),
        "created_at": created,
        "resolved_at": resolved,
        "resolution_status": status,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    load_dotenv()
    engine = create_engine(os.environ["DATABASE_URL"])

    with engine.begin() as conn:
        trades = {r["trade_id"]: r for r in conn.execute(text(
            "SELECT trade_id, quantity, price, trade_datetime, settlement_date FROM trades")).mappings()}
        flags = conn.execute(text(
            "SELECT trade_id, flag_type FROM settlement_flags ORDER BY trade_id, flag_type")).all()
        if not flags:
            print("No flags found. Run: python -m src.synthetic.build_operations --seed 42")
            return
        events = {}
        for r in conn.execute(text(
                "SELECT trade_id, event_type, event_timestamp FROM settlement_events "
                "WHERE event_type IN ('TRADE_CONFIRMED','TRADE_MATCHED','INSTRUCTION_SENT')")):
            events.setdefault(r[0], {})[r[1]] = r[2]
        holidays = {r[0] for r in conn.execute(text(
            "SELECT calendar_date FROM business_calendar WHERE holiday_name IS NOT NULL"))}

        conn.execute(text("DELETE FROM exceptions"))
        rng = np.random.default_rng(args.seed + 3)
        rows, by_type, by_sev = [], Counter(), Counter()
        for trade_id, flag in flags:
            t = trades[trade_id]
            ev = {"t_conf": events[trade_id]["TRADE_CONFIRMED"],
                  "t_match": events[trade_id]["TRADE_MATCHED"],
                  "t_instr": events[trade_id]["INSTRUCTION_SENT"]}
            dl = deadlines(t["trade_datetime"], t["settlement_date"], holidays)
            notional = float(t["quantity"]) * float(t["price"])
            exc = build_exception(flag, notional, ev, dl, rng, holidays)
            rows.append({"trade_id": trade_id, **exc})
            by_type[flag] += 1
            by_sev[exc["severity"]] += 1

        conn.execute(text(
            "INSERT INTO exceptions (trade_id, exception_type, severity, created_at, resolved_at, resolution_status) "
            "VALUES (:trade_id, :exception_type, :severity, :created_at, :resolved_at, :resolution_status)"), rows)

    n_open = sum(1 for r in rows if r["resolution_status"] == "OPEN")
    print(f"Created {len(rows)} exceptions ({n_open} still OPEN).")
    print("  by type:    ", dict(by_type.most_common()))
    print("  by severity:", dict(by_sev))


if __name__ == "__main__":
    main()