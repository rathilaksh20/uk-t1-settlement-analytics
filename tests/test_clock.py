from datetime import date, datetime

from src.settlement.clock import add_business_hours, previous_business_day

HOL = {date(2026, 12, 25), date(2026, 12, 28)}


def test_same_day():
    assert add_business_hours(datetime(2026, 10, 1, 9, 0), 2, HOL) == datetime(2026, 10, 1, 11, 0)


def test_overflows_to_next_morning():
    # 17:00 + 2h: 1h left today, 1h next morning
    assert add_business_hours(datetime(2026, 10, 1, 17, 0), 2, HOL) == datetime(2026, 10, 2, 9, 0)


def test_friday_evening_rolls_to_monday():
    assert add_business_hours(datetime(2026, 10, 2, 17, 30), 1, HOL) == datetime(2026, 10, 5, 8, 30)


def test_start_before_open():
    assert add_business_hours(datetime(2026, 10, 1, 6, 0), 1, HOL) == datetime(2026, 10, 1, 9, 0)


def test_skips_christmas():
    assert add_business_hours(datetime(2026, 12, 24, 17, 0), 2, HOL) == datetime(2026, 12, 29, 9, 0)


def test_long_duration_spans_days():
    # 25 business hours = two full 10h days plus 5h
    assert add_business_hours(datetime(2026, 10, 1, 8, 0), 25, HOL) == datetime(2026, 10, 5, 13, 0)


def test_previous_business_day():
    assert previous_business_day(date(2026, 10, 5), HOL) == date(2026, 10, 2)
    assert previous_business_day(date(2026, 12, 29), HOL) == date(2026, 12, 24)