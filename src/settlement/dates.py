from datetime import date, timedelta


def is_business_day(d: date, holidays: set) -> bool:
    """Monday to Friday, and not a UK bank holiday."""
    return d.weekday() < 5 and d not in holidays


def add_business_days(start: date, n: int, holidays: set) -> date:
    """Return the date n business days after start (n >= 0)."""
    if n < 0:
        raise ValueError("n must be zero or positive")
    d = start
    remaining = n
    while remaining > 0:
        d += timedelta(days=1)
        if is_business_day(d, holidays):
            remaining -= 1
    return d


def settlement_date(trade_date: date, cycle_days: int, holidays: set) -> date:
    """Settlement date for a trade: T+cycle_days in business days.
    If the trade date itself is not a business day, counting starts
    from the next business day."""
    d = trade_date
    while not is_business_day(d, holidays):
        d += timedelta(days=1)
    return add_business_days(d, cycle_days, holidays)