"""T+2 versus T+1 settlement simulator (all inputs are SYNTHETIC).

The stage durations sampled once by the operations model are REPLAYED under a
different settlement cycle. Because the same durations are reused, any change in
outcome is caused by the shorter window, not by random noise (common random numbers).

Cut-off rule for a cycle: start from the T+2 internal deadlines relative to the
settlement date, and keep each internal cut-off no earlier than the close of the
trade date. For T+2 the floor never binds, so results match the original rules engine.
"""
from collections import Counter
from datetime import datetime, time

from src.settlement.clock import add_business_hours
from src.settlement.dates import settlement_date
from src.settlement.rules import deadlines, evaluate


def cycle_deadlines(trade_dt, cycle_days, holidays, cutoff="strict"):
    """Return (settlement_date, deadlines dict) for a trade under a T+cycle_days cycle.

    cutoff (T+1 only): "strict"  = matching and instruction must finish by the close of the trade date;
                       "relaxed" = matching by 09:00 and instruction by 10:00 on the settlement morning."""
    trade_day = trade_dt.date()
    settle = settlement_date(trade_day, cycle_days, holidays)
    d = deadlines(trade_dt, settle, holidays)
    close_of_trade_day = d["conf_deadline"]
    d["match_deadline"] = max(d["match_deadline"], close_of_trade_day)
    d["instr_deadline"] = max(d["instr_deadline"], close_of_trade_day)
    if cycle_days == 1 and cutoff == "relaxed":
        d["match_deadline"] = datetime.combine(settle, time(9, 0))
        d["instr_deadline"] = datetime.combine(settle, time(10, 0))
    return settle, d


def replay_trade(t, cycle_days, holidays, levers=None):
    """t: dict with trade_datetime, counterparty_id, conf_h, match_h, instr_h,
    cash_required, cash_available, securities_required, securities_available,
    reconciliation_break. levers (all optional):
      all / confirmation / matching / instruction : multipliers on stage durations (0.8 = 20% faster)
      cp : {counterparty_id: multiplier} applied to that counterparty's confirmation and matching time
      cutoff : "strict" (default) or "relaxed", the T+1 cut-off assumption
    """
    lv = levers or {}
    base = lv.get("all", 1.0)
    cp_mult = lv.get("cp", {}).get(t["counterparty_id"], 1.0)
    conf_h = t["conf_h"] * base * lv.get("confirmation", 1.0) * cp_mult
    match_h = t["match_h"] * base * lv.get("matching", 1.0) * cp_mult
    instr_h = t["instr_h"] * base * lv.get("instruction", 1.0)

    start = t["trade_datetime"]
    settle, dl = cycle_deadlines(start, cycle_days, holidays, lv.get("cutoff", "strict"))
    t_conf = add_business_hours(start, conf_h, holidays)
    t_match = add_business_hours(t_conf, match_h, holidays)
    t_instr = add_business_hours(t_conf, instr_h, holidays)
    rec = {
        "t_conf": t_conf, "t_match": t_match, "t_instr": t_instr, **dl,
        "cash_required": t["cash_required"], "cash_available": t["cash_available"],
        "securities_required": t["securities_required"], "securities_available": t["securities_available"],
        "reconciliation_break": t["reconciliation_break"],
    }
    flags, primary = evaluate(rec)
    return {"settlement_date": settle, "flags": flags, "primary_reason": primary, "at_risk": bool(flags)}


def run_scenario(trades, cycle_days, holidays, levers=None):
    """Replay every trade. Returns {trade_id: result}."""
    return {t["trade_id"]: replay_trade(t, cycle_days, holidays, levers) for t in trades}


def summarise(results, notional_by_trade):
    n = len(results)
    at_risk = [tid for tid, r in results.items() if r["at_risk"]]
    flags = Counter(f for r in results.values() for f in r["flags"])
    return {
        "trades": n,
        "at_risk_trades": len(at_risk),
        "at_risk_pct": 100.0 * len(at_risk) / n if n else 0.0,
        "at_risk_notional": float(sum(notional_by_trade[tid] for tid in at_risk)),
        "flags": dict(flags),
    }


def find_breakeven_factor(trades, holidays, target_at_risk, cycle_days=1, step=0.05, base_levers=None):
    """Largest uniform duration multiplier (1.0 = no change) at which the T+cycle
    at-risk count is no higher than target_at_risk. None if unreachable."""
    f = 1.0
    while f >= 0.0 - 1e-9:
        res = run_scenario(trades, cycle_days, holidays, {**(base_levers or {}), "all": max(f, 0.0)})
        if sum(1 for r in res.values() if r["at_risk"]) <= target_at_risk:
            return round(f, 2)
        f -= step
    return None
