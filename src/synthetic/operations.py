"""Causal operations model: counterparty profiles, stage timings, positions.

Everything here is SYNTHETIC. Hidden counterparty reliability and
responsiveness drive delays and breaks; they are stored in
counterparty_profile and must NOT be used as ML features.
"""
from datetime import datetime

import numpy as np

from src.settlement.clock import add_business_hours
from src.settlement.rules import deadlines, evaluate


def make_profiles(counterparty_ids, seed):
    rng = np.random.default_rng(seed + 1)
    out = {}
    for cp in counterparty_ids:
        out[cp] = {
            "reliability": float(np.clip(rng.beta(6, 2), 0.50, 0.99)),
            "responsiveness": float(np.clip(rng.beta(5, 2), 0.40, 0.99)),
        }
    return out


def pick_shock_days(business_days, seed, n=3):
    rng = np.random.default_rng(seed + 2)
    idx = rng.choice(len(business_days), size=n, replace=False)
    return {business_days[i] for i in idx}


def _lognorm(rng, median, sigma):
    return float(rng.lognormal(np.log(median), sigma))


def simulate_operations(trade, profile, rng, holidays, shock_days):
    """trade: dict with side, quantity, price, trade_datetime, settlement_date.
    Returns durations (business hours), positions and the evaluated outcome."""
    notional = trade["quantity"] * trade["price"]
    rel, resp = profile["reliability"], profile["responsiveness"]
    slow = 1.0 + (1.0 - resp) * 1.5
    size_factor = max(notional / 100_000.0, 0.05) ** 0.15
    shock = trade["trade_datetime"].date() in shock_days
    shock_mult = 2.0 if shock else 1.0

    conf_h = _lognorm(rng, 0.5, 0.7) * slow * size_factor * shock_mult

    match_h = _lognorm(rng, 1.5, 0.6) * slow * shock_mult
    p_break = 0.01 + 0.10 * (1.0 - rel) ** 1.5 * 2.0 + (0.01 if notional > 500_000 else 0.0)
    if rng.random() < p_break:
        match_h += _lognorm(rng, 12.0, 0.5)

    instr_h = _lognorm(rng, 1.0, 0.5) * shock_mult
    p_instr_err = 0.005 + 0.05 * (1.0 - rel)
    if rng.random() < p_instr_err:
        instr_h += _lognorm(rng, 18.0, 0.5)

    cash_req = sec_req = 0.0
    cash_av = sec_av = 0.0
    if trade["side"] == "BUY":
        cash_req = round(notional, 2)
        p_short = 0.02 + 0.06 * min(notional / 1_000_000.0, 1.0)
        ratio = rng.uniform(0.5, 0.98) if rng.random() < p_short else rng.uniform(1.0, 1.4)
        cash_av = round(cash_req * ratio, 2)
    else:
        sec_req = float(trade["quantity"])
        ratio = rng.uniform(0.5, 0.98) if rng.random() < 0.02 else rng.uniform(1.0, 1.4)
        sec_av = float(int(sec_req * ratio))

    recon_break = bool(rng.random() < 0.01)

    start = trade["trade_datetime"]
    t_conf = add_business_hours(start, conf_h, holidays)
    t_match = add_business_hours(t_conf, match_h, holidays)
    t_instr = add_business_hours(t_conf, instr_h, holidays)

    rec = {
        "t_conf": t_conf, "t_match": t_match, "t_instr": t_instr,
        **deadlines(start, trade["settlement_date"], holidays),
        "cash_required": cash_req, "cash_available": cash_av,
        "securities_required": sec_req, "securities_available": sec_av,
        "reconciliation_break": recon_break,
    }
    flags, primary = evaluate(rec)
    return {
        "conf_h": conf_h, "match_h": match_h, "instr_h": instr_h, "shock": shock,
        **rec, "flags": flags, "primary_reason": primary,
    }