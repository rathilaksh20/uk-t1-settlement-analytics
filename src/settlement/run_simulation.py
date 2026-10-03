"""Run the T+2 versus T+1 simulation on the trades in the database (SYNTHETIC).

    python -m src.settlement.run_simulation

Prerequisite: trades, build_operations and build_exceptions have been run.
Results are stored in simulation_runs / simulation_results and printed.
"""
import json
import os
from collections import Counter

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from src.settlement.simulator import find_breakeven_factor, run_scenario, summarise

DDL = [
    """CREATE TABLE IF NOT EXISTS simulation_runs (
        run_id BIGSERIAL PRIMARY KEY, scenario VARCHAR(60) NOT NULL, cycle_days SMALLINT NOT NULL,
        parameters JSONB NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT now(),
        trades INTEGER, at_risk_trades INTEGER, at_risk_pct NUMERIC(6,2), at_risk_notional NUMERIC(20,2))""",
    """CREATE TABLE IF NOT EXISTS simulation_results (
        run_id BIGINT NOT NULL REFERENCES simulation_runs(run_id) ON DELETE CASCADE,
        trade_id VARCHAR(30) NOT NULL REFERENCES trades(trade_id) ON DELETE CASCADE,
        settlement_date DATE NOT NULL, at_risk BOOLEAN NOT NULL,
        primary_reason VARCHAR(60), flags VARCHAR(300),
        PRIMARY KEY (run_id, trade_id))""",
]

LOAD_SQL = """
SELECT t.trade_id, t.counterparty_id, t.trade_datetime, t.trade_value,
       d.confirmation_hours, d.matching_hours, d.instruction_hours,
       s.cash_required, s.cash_available, s.securities_required, s.securities_available,
       s.reconciliation_status
FROM trades t
JOIN stage_durations d USING (trade_id)
JOIN settlement_status s USING (trade_id)
ORDER BY t.trade_id"""


def load_trades(conn):
    rows = conn.execute(text(LOAD_SQL)).mappings().all()
    trades = [{
        "trade_id": r["trade_id"], "counterparty_id": r["counterparty_id"],
        "trade_datetime": r["trade_datetime"], "notional": float(r["trade_value"]),
        "conf_h": float(r["confirmation_hours"]), "match_h": float(r["matching_hours"]),
        "instr_h": float(r["instruction_hours"]),
        "cash_required": float(r["cash_required"]), "cash_available": float(r["cash_available"]),
        "securities_required": float(r["securities_required"]),
        "securities_available": float(r["securities_available"]),
        "reconciliation_break": r["reconciliation_status"] == "BREAK",
    } for r in rows]
    return trades


def main():
    load_dotenv()
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        for ddl in DDL:
            conn.execute(text(ddl))
        trades = load_trades(conn)
        if not trades:
            raise SystemExit("No trades with operations data. Run trades, build_operations, build_exceptions first.")
        holidays = {r[0] for r in conn.execute(text(
            "SELECT calendar_date FROM business_calendar WHERE holiday_name IS NOT NULL"))}
        stored_flags = {}
        for tid, flag in conn.execute(text("SELECT trade_id, flag_type FROM settlement_flags")):
            stored_flags.setdefault(tid, set()).add(flag)

    notional = {t["trade_id"]: t["notional"] for t in trades}

    # Scenarios: name -> (cycle, levers)
    base2 = run_scenario(trades, 2, holidays)
    mismatches = sum(1 for t in trades if set(base2[t["trade_id"]]["flags"]) != stored_flags.get(t["trade_id"], set()))
    print(f"Baseline check: T+2 replay differs from stored results for {mismatches} of {len(trades)} trades.")

    as_is1 = run_scenario(trades, 1, holidays)
    cp_hits = Counter(t["counterparty_id"] for t in trades if as_is1[t["trade_id"]]["at_risk"])
    worst3 = [cp for cp, _ in cp_hits.most_common(3)]

    scenarios = [
        ("T2_baseline", 2, {}),
        ("T1_as_is", 1, {}),
        ("T1_confirmation_faster_20pct", 1, {"confirmation": 0.8}),
        ("T1_matching_faster_30pct", 1, {"matching": 0.7}),
        ("T1_instruction_faster_30pct", 1, {"instruction": 0.7}),
        ("T1_all_stages_faster_25pct", 1, {"all": 0.75}),
        ("T1_worst3_counterparties_halved", 1, {"cp": {cp: 0.5 for cp in worst3}}),
    ]
    for mult in (0.8, 0.9, 1.1, 1.2):
        scenarios.append((f"T1_sensitivity_durations_x{mult}", 1, {"all": mult}))

    summaries = {}
    with engine.begin() as conn:
        for name, cycle, levers in scenarios:
            res = base2 if name == "T2_baseline" else (as_is1 if name == "T1_as_is" else run_scenario(trades, cycle, holidays, levers))
            s = summarise(res, notional)
            summaries[name] = s
            conn.execute(text("DELETE FROM simulation_runs WHERE scenario = :n"), {"n": name})
            run_id = conn.execute(text(
                "INSERT INTO simulation_runs (scenario, cycle_days, parameters, trades, at_risk_trades, at_risk_pct, at_risk_notional) "
                "VALUES (:n, :c, CAST(:p AS JSONB), :t, :a, :pct, :nt) RETURNING run_id"),
                {"n": name, "c": cycle, "p": json.dumps(levers), "t": s["trades"], "a": s["at_risk_trades"],
                 "pct": round(s["at_risk_pct"], 2), "nt": round(s["at_risk_notional"], 2)}).scalar()
            conn.execute(text(
                "INSERT INTO simulation_results (run_id, trade_id, settlement_date, at_risk, primary_reason, flags) "
                "VALUES (:r, :tid, :sd, :ar, :pr, :fl)"),
                [{"r": run_id, "tid": tid, "sd": r["settlement_date"], "ar": r["at_risk"],
                  "pr": r["primary_reason"], "fl": ",".join(r["flags"])} for tid, r in res.items()])

    base = summaries["T2_baseline"]
    print(f"\n{'scenario':<36}{'at-risk':>8}{'%':>7}{'vs T+2':>9}{'GBP m at risk':>15}")
    for name, _, _ in scenarios:
        s = summaries[name]
        print(f"{name:<36}{s['at_risk_trades']:>8}{s['at_risk_pct']:>7.1f}"
              f"{s['at_risk_pct'] - base['at_risk_pct']:>+9.1f}{s['at_risk_notional'] / 1e6:>15.1f}")

    print("\nFlags by type (count of trades):")
    kinds = sorted({k for s in summaries.values() for k in s["flags"]})
    print(f"{'flag':<24}{'T+2':>8}{'T+1':>8}")
    for k in kinds:
        print(f"{k:<24}{base['flags'].get(k, 0):>8}{summaries['T1_as_is']['flags'].get(k, 0):>8}")

    f = find_breakeven_factor(trades, holidays, base["at_risk_trades"])
    if f is None:
        print("\nBreakeven: no uniform speed-up restores the T+2 level.")
    else:
        print(f"\nBreakeven: cutting every stage time to {f:.0%} of today's "
              f"(a {100 * (1 - f):.0f}% reduction) brings T+1 back to the T+2 at-risk level.")
    print(f"Worst 3 counterparties under T+1: {', '.join(worst3)}")


if __name__ == "__main__":
    main()