from datetime import date, datetime

import numpy as np

from src.synthetic.operations import make_profiles, simulate_operations, pick_shock_days

HOL = {date(2026, 8, 31)}
CPS = [f"CP{i:03d}" for i in range(1, 6)]


def trade(hour=10, side="BUY"):
    return {"side": side, "quantity": 10_000.0, "price": 10.0,
            "trade_datetime": datetime(2026, 9, 2, hour, 0), "settlement_date": date(2026, 9, 4)}


def test_profiles_reproducible_and_in_range():
    a, b = make_profiles(CPS, 7), make_profiles(CPS, 7)
    assert a == b
    for p in a.values():
        assert 0.5 <= p["reliability"] <= 0.99
        assert 0.4 <= p["responsiveness"] <= 0.99


def test_same_seed_same_outcome():
    p = make_profiles(CPS, 7)["CP001"]
    a = simulate_operations(trade(), p, np.random.default_rng(1), HOL, set())
    b = simulate_operations(trade(), p, np.random.default_rng(1), HOL, set())
    assert a == b


def test_buy_needs_cash_sell_needs_securities():
    p = make_profiles(CPS, 7)["CP001"]
    buy = simulate_operations(trade(side="BUY"), p, np.random.default_rng(1), HOL, set())
    sell = simulate_operations(trade(side="SELL"), p, np.random.default_rng(1), HOL, set())
    assert buy["cash_required"] > 0 and buy["securities_required"] == 0
    assert sell["securities_required"] > 0 and sell["cash_required"] == 0


def test_timeline_order():
    p = make_profiles(CPS, 7)["CP001"]
    rng = np.random.default_rng(3)
    for _ in range(200):
        o = simulate_operations(trade(), p, rng, HOL, set())
        assert o["t_conf"] >= datetime(2026, 9, 2, 10, 0)
        assert o["t_match"] >= o["t_conf"] and o["t_instr"] >= o["t_conf"]


def test_late_trades_fail_more_than_morning_trades():
    p = make_profiles(CPS, 7)["CP001"]
    def rate(hour):
        rng = np.random.default_rng(11)
        return sum(bool(simulate_operations(trade(hour), p, rng, HOL, set())["flags"]) for _ in range(3000)) / 3000
    assert rate(16) > rate(9)


def test_shock_day_raises_failures():
    p = make_profiles(CPS, 7)["CP001"]
    def rate(shock):
        rng = np.random.default_rng(5)
        s = {date(2026, 9, 2)} if shock else set()
        return sum(bool(simulate_operations(trade(), p, rng, HOL, s)["flags"]) for _ in range(3000)) / 3000
    assert rate(True) > rate(False)


def test_pick_shock_days_reproducible():
    days = [date(2026, 9, d) for d in range(1, 29) if date(2026, 9, d).weekday() < 5]
    assert pick_shock_days(days, 4) == pick_shock_days(days, 4)
    assert len(pick_shock_days(days, 4)) == 3