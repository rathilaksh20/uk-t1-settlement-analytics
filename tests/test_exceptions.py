from datetime import date, datetime

import numpy as np

from src.settlement.rules import deadlines
from src.synthetic.build_exceptions import build_exception, severity_for

HOL = set()
TRADE_DT = datetime(2026, 10, 1, 10, 0)
SETTLE = date(2026, 10, 5)
DL = deadlines(TRADE_DT, SETTLE, HOL)
EV = {"t_conf": datetime(2026, 10, 2, 8, 30),
      "t_match": datetime(2026, 10, 2, 14, 0),
      "t_instr": datetime(2026, 10, 2, 17, 0)}


def rng():
    return np.random.default_rng(1)


def test_severity_by_notional():
    assert severity_for("UNMATCHED", 50_000) == "LOW"
    assert severity_for("UNMATCHED", 200_000) == "MEDIUM"
    assert severity_for("UNMATCHED", 900_000) == "HIGH"


def test_severity_bumped_for_funding_flags():
    assert severity_for("CASH_SHORTFALL", 50_000) == "MEDIUM"
    assert severity_for("CASH_SHORTFALL", 900_000) == "HIGH"   # capped at HIGH


def test_unmatched_is_resolved_when_match_completes():
    e = build_exception("UNMATCHED", 1e5, EV, DL, rng(), HOL)
    assert e["created_at"] == DL["match_deadline"]
    assert e["resolved_at"] == EV["t_match"]
    assert e["resolution_status"] == "RESOLVED"


def test_late_confirmation_and_instruction_use_actual_completion():
    c = build_exception("LATE_CONFIRMATION", 1e5, EV, DL, rng(), HOL)
    i = build_exception("INSTRUCTION_MISMATCH", 1e5, EV, DL, rng(), HOL)
    assert c["resolved_at"] == EV["t_conf"] and c["created_at"] == DL["conf_deadline"]
    assert i["resolved_at"] == EV["t_instr"] and i["created_at"] == DL["instr_deadline"]


def test_resolved_never_before_created_and_open_has_no_end():
    r = np.random.default_rng(9)
    seen_open = False
    for flag in ("CASH_SHORTFALL", "SECURITIES_SHORTFALL", "RECONCILIATION_BREAK"):
        for _ in range(500):
            e = build_exception(flag, 2e5, EV, DL, r, HOL)
            if e["resolution_status"] == "OPEN":
                seen_open = True
                assert e["resolved_at"] is None
            else:
                assert e["resolved_at"] >= e["created_at"]
    assert seen_open


def test_unknown_flag_rejected():
    try:
        build_exception("NOPE", 1e5, EV, DL, rng(), HOL)
        assert False
    except ValueError:
        pass