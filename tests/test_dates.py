from datetime import date
from src.settlement.dates import is_business_day, add_business_days, settlement_date

HOLIDAYS = {date(2026, 12, 25), date(2026, 12, 28)}  # Christmas Day and substitute Boxing Day


def test_weekend_is_not_business_day():
    assert not is_business_day(date(2026, 10, 3), HOLIDAYS)  # Saturday


def test_holiday_is_not_business_day():
    assert not is_business_day(date(2026, 12, 25), HOLIDAYS)


def test_t1_thursday_trade_settles_friday():
    assert settlement_date(date(2026, 10, 1), 1, HOLIDAYS) == date(2026, 10, 2)


def test_t1_friday_trade_settles_monday():
    assert settlement_date(date(2026, 10, 2), 1, HOLIDAYS) == date(2026, 10, 5)


def test_t2_thursday_trade_settles_monday():
    assert settlement_date(date(2026, 10, 1), 2, HOLIDAYS) == date(2026, 10, 5)


def test_t1_over_christmas():
    assert settlement_date(date(2026, 12, 24), 1, HOLIDAYS) == date(2026, 12, 29)


def test_t2_over_christmas():
    assert settlement_date(date(2026, 12, 23), 2, HOLIDAYS) == date(2026, 12, 29)


def test_weekend_trade_date_rolls_forward_first():
    # Saturday trade date counts from Monday
    assert settlement_date(date(2026, 10, 3), 1, HOLIDAYS) == date(2026, 10, 6)