"""Working-time arithmetic: business days plus a 08:00 to 18:00 working window."""
from datetime import date, datetime, time, timedelta

from src.settlement.dates import add_business_days, is_business_day

DAY_START = time(8, 0)
DAY_END = time(18, 0)


def previous_business_day(d: date, holidays: set) -> date:
    d = d - timedelta(days=1)
    while not is_business_day(d, holidays):
        d -= timedelta(days=1)
    return d


def _next_window_start(d: date, holidays: set) -> datetime:
    return datetime.combine(add_business_days(d, 1, holidays), DAY_START)


def _roll_into_window(dt: datetime, holidays: set) -> datetime:
    d = dt.date()
    if not is_business_day(d, holidays):
        return _next_window_start(d, holidays)
    if dt.time() < DAY_START:
        return datetime.combine(d, DAY_START)
    if dt.time() >= DAY_END:
        return _next_window_start(d, holidays)
    return dt


def add_business_hours(start: datetime, hours: float, holidays: set) -> datetime:
    """Move forward by `hours` of working time (08:00 to 18:00, business days only)."""
    remaining = hours * 60.0
    cur = _roll_into_window(start, holidays)
    while True:
        end_of_day = datetime.combine(cur.date(), DAY_END)
        available = (end_of_day - cur).total_seconds() / 60.0
        if remaining <= available:
            return cur + timedelta(minutes=remaining)
        remaining -= available
        cur = _next_window_start(cur.date(), holidays)