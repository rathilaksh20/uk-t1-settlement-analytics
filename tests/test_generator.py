from datetime import date

from src.settlement.dates import is_business_day
from src.synthetic.trades import generate_trades, PLACEHOLDER_PRICE_GBP

INSTRUMENTS = [(f"INS_{t.strip('.')}", t) for t in PLACEHOLDER_PRICE_GBP]
CPS = [f"CP{i:03d}" for i in range(1, 16)]
HOLIDAYS = {date(2026, 8, 31)}  # August bank holiday


def make(n=500, seed=42):
    return generate_trades(n, seed, INSTRUMENTS, CPS, HOLIDAYS)


def test_count_and_unique_ids():
    t = make()
    assert len(t) == 500
    assert len({x["trade_id"] for x in t}) == 500


def test_same_seed_reproduces():
    assert make() == make()


def test_different_seed_differs():
    assert make(seed=1) != make(seed=2)


def test_values_valid():
    for x in make():
        assert x["quantity"] > 0 and x["quantity"] % 100 == 0
        assert x["price"] > 0
        assert x["side"] in ("BUY", "SELL")


def test_trade_days_are_business_days():
    for x in make():
        assert is_business_day(x["trade_datetime"].date(), HOLIDAYS)


def test_settlement_is_later_business_day():
    for x in make():
        td = x["trade_datetime"].date()
        assert x["settlement_date"] > td
        assert is_business_day(x["settlement_date"], HOLIDAYS)


def test_trading_hours():
    for x in make():
        h, m = x["trade_datetime"].hour, x["trade_datetime"].minute
        assert (8, 0) <= (h, m) < (16, 30)