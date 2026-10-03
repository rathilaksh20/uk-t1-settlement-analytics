"""Deterministic settlement rules engine (T+2 deadlines for now).

evaluate() checks EVERY rule, returns all flags in priority order, and the
primary reason (highest priority flag) for display.
"""
from datetime import datetime, time

from src.settlement.clock import previous_business_day

PRIORITY = [
    "UNMATCHED",
    "INSTRUCTION_MISMATCH",
    "SECURITIES_SHORTFALL",
    "CASH_SHORTFALL",
    "LATE_CONFIRMATION",
    "RECONCILIATION_BREAK",
    "LATE_SETTLEMENT",
]


def deadlines(trade_dt, settle_date, holidays):
    """Internal cut-offs, expressed relative to trade date and settlement date."""
    prev_bd = previous_business_day(settle_date, holidays)
    return {
        "conf_deadline": datetime.combine(trade_dt.date(), time(18, 0)),
        "match_deadline": datetime.combine(prev_bd, time(12, 0)),
        "instr_deadline": datetime.combine(prev_bd, time(16, 0)),
        "settle_cutoff": datetime.combine(settle_date, time(12, 0)),
    }


def evaluate(r):
    """r: dict with t_conf, t_match, t_instr, the four deadlines, cash/securities
    required and available, and reconciliation_break (bool).
    Returns (flags_in_priority_order, primary_reason_or_None)."""
    raised = set()
    if r["t_match"] > r["match_deadline"]:
        raised.add("UNMATCHED")
    if r["t_instr"] > r["instr_deadline"]:
        raised.add("INSTRUCTION_MISMATCH")
    if r["securities_required"] > r["securities_available"]:
        raised.add("SECURITIES_SHORTFALL")
    if r["cash_required"] > r["cash_available"]:
        raised.add("CASH_SHORTFALL")
    if r["t_conf"] > r["conf_deadline"]:
        raised.add("LATE_CONFIRMATION")
    if r["reconciliation_break"]:
        raised.add("RECONCILIATION_BREAK")
    if max(r["t_match"], r["t_instr"]) > r["settle_cutoff"]:
        raised.add("LATE_SETTLEMENT")
    flags = [f for f in PRIORITY if f in raised]
    return flags, (flags[0] if flags else None)