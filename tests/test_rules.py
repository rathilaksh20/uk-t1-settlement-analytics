from datetime import date, datetime

from src.settlement.rules import deadlines, evaluate

HOL = set()
TRADE_DT = datetime(2026, 10, 1, 10, 0)   # Thursday
SETTLE = date(2026, 10, 5)                # T+2 (Monday)


def clean():
    d = deadlines(TRADE_DT, SETTLE, HOL)
    return {
        "t_conf": datetime(2026, 10, 1, 11, 0),
        "t_match": datetime(2026, 10, 1, 15, 0),
        "t_instr": datetime(2026, 10, 1, 12, 0),
        **d,
        "cash_required": 1000.0, "cash_available": 1500.0,
        "securities_required": 0.0, "securities_available": 0.0,
        "reconciliation_break": False,
    }


def test_deadlines_t2():
    d = deadlines(TRADE_DT, SETTLE, HOL)
    assert d["conf_deadline"] == datetime(2026, 10, 1, 18, 0)
    assert d["match_deadline"] == datetime(2026, 10, 2, 12, 0)
    assert d["instr_deadline"] == datetime(2026, 10, 2, 16, 0)
    assert d["settle_cutoff"] == datetime(2026, 10, 5, 12, 0)


def test_clean_trade_has_no_flags():
    assert evaluate(clean()) == ([], None)


def test_late_confirmation():
    r = clean(); r["t_conf"] = datetime(2026, 10, 2, 8, 30)
    assert evaluate(r) == (["LATE_CONFIRMATION"], "LATE_CONFIRMATION")


def test_unmatched():
    r = clean(); r["t_match"] = datetime(2026, 10, 2, 13, 0)
    assert evaluate(r)[0] == ["UNMATCHED"]


def test_instruction_mismatch():
    r = clean(); r["t_instr"] = datetime(2026, 10, 2, 17, 0)
    assert evaluate(r)[0] == ["INSTRUCTION_MISMATCH"]


def test_cash_shortfall():
    r = clean(); r["cash_available"] = 400.0
    assert evaluate(r)[0] == ["CASH_SHORTFALL"]


def test_securities_shortfall():
    r = clean(); r["cash_required"] = r["cash_available"] = 0.0
    r["securities_required"], r["securities_available"] = 500.0, 100.0
    assert evaluate(r)[0] == ["SECURITIES_SHORTFALL"]


def test_reconciliation_break():
    r = clean(); r["reconciliation_break"] = True
    assert evaluate(r)[0] == ["RECONCILIATION_BREAK"]


def test_late_settlement():
    r = clean(); r["t_instr"] = datetime(2026, 10, 5, 13, 0)
    assert "LATE_SETTLEMENT" in evaluate(r)[0]


def test_all_flags_kept_and_primary_is_highest_priority():
    r = clean()
    r["t_match"] = datetime(2026, 10, 2, 13, 0)      # UNMATCHED
    r["cash_available"] = 400.0                      # CASH_SHORTFALL
    r["t_conf"] = datetime(2026, 10, 2, 8, 30)       # LATE_CONFIRMATION
    flags, primary = evaluate(r)
    assert flags == ["UNMATCHED", "CASH_SHORTFALL", "LATE_CONFIRMATION"]
    assert primary == "UNMATCHED"