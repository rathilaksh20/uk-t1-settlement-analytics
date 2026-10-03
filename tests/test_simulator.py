from datetime import date, datetime

import numpy as np

from src.settlement.simulator import (cycle_deadlines, replay_trade, run_scenario,
                                      summarise, find_breakeven_factor)
from src.synthetic.operations import make_profiles, simulate_operations
from src.synthetic.trades import generate_trades, PLACEHOLDER_PRICE_GBP

HOL = {date(2026, 8, 31)}
INST = [(f"INS_{t.strip('.')}", t) for t in PLACEHOLDER_PRICE_GBP]
CPS = [f"CP{i:03d}" for i in range(1, 16)]


def build_inputs(n=600, seed=3):
    """Run the operations model, then expose its durations the way the DB stores them."""
    trades = generate_trades(n, seed, INST, CPS, HOL)
    prof = make_profiles(CPS, seed)
    rng = np.random.default_rng(seed)
    out, stored = [], {}
    for t in trades:
        o = simulate_operations(t, prof[t["counterparty_id"]], rng, HOL, set())
        out.append({
            "trade_id": t["trade_id"], "counterparty_id": t["counterparty_id"],
            "trade_datetime": t["trade_datetime"], "conf_h": o["conf_h"], "match_h": o["match_h"],
            "instr_h": o["instr_h"], "cash_required": o["cash_required"], "cash_available": o["cash_available"],
            "securities_required": o["securities_required"], "securities_available": o["securities_available"],
            "reconciliation_break": "RECONCILIATION_BREAK" in o["flags"],
        })
        stored[t["trade_id"]] = o["flags"]
    return out, stored


def test_t2_replay_reproduces_original_flags_exactly():
    trades, stored = build_inputs()
    res = run_scenario(trades, 2, HOL)
    assert all(res[tid]["flags"] == flags for tid, flags in stored.items())


def test_cycle_deadlines_t2_vs_t1():
    start = datetime(2026, 10, 1, 10, 0)            # Thursday
    s2, d2 = cycle_deadlines(start, 2, set())
    s1, d1 = cycle_deadlines(start, 1, set())
    assert s2 == date(2026, 10, 5) and s1 == date(2026, 10, 2)
    assert d2["match_deadline"] == datetime(2026, 10, 2, 12, 0)
    assert d1["match_deadline"] == datetime(2026, 10, 1, 18, 0)     # floored at close of trade date
    assert d1["instr_deadline"] == datetime(2026, 10, 1, 18, 0)
    assert d1["settle_cutoff"] == datetime(2026, 10, 2, 12, 0)


def test_t1_never_has_fewer_flags_than_t2():
    trades, _ = build_inputs()
    r2, r1 = run_scenario(trades, 2, HOL), run_scenario(trades, 1, HOL)
    for tid in r2:
        assert set(r2[tid]["flags"]) <= set(r1[tid]["flags"])
    assert sum(r["at_risk"] for r in r1.values()) > sum(r["at_risk"] for r in r2.values())


def test_faster_stages_never_increase_risk():
    trades, _ = build_inputs()
    base = run_scenario(trades, 1, HOL)
    fast = run_scenario(trades, 1, HOL, {"all": 0.5})
    for tid in base:
        assert set(fast[tid]["flags"]) <= set(base[tid]["flags"])


def test_counterparty_lever_only_changes_that_counterparty():
    trades, _ = build_inputs()
    base = run_scenario(trades, 1, HOL)
    lev = run_scenario(trades, 1, HOL, {"cp": {"CP001": 0.2}})
    by_cp = {t["trade_id"]: t["counterparty_id"] for t in trades}
    for tid in base:
        if by_cp[tid] != "CP001":
            assert base[tid]["flags"] == lev[tid]["flags"]


def test_breakeven_restores_t2_level():
    trades, _ = build_inputs(n=300)
    t2 = sum(r["at_risk"] for r in run_scenario(trades, 2, HOL).values())
    f = find_breakeven_factor(trades, HOL, t2)
    assert f is not None and 0.0 <= f <= 1.0
    t1_at_f = sum(r["at_risk"] for r in run_scenario(trades, 1, HOL, {"all": f}).values())
    assert t1_at_f <= t2


def test_summarise():
    trades, _ = build_inputs(n=100)
    res = run_scenario(trades, 1, HOL)
    notional = {t["trade_id"]: 1000.0 for t in trades}
    s = summarise(res, notional)
    assert s["trades"] == 100 and s["at_risk_notional"] == 1000.0 * s["at_risk_trades"]