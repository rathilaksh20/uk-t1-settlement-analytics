"""Simulation helpers for the dashboard (cached)."""
import pandas as pd
import streamlit as st
from sqlalchemy import text

from dashboard.data import get_engine, run_query
from src.settlement.run_simulation import load_trades
from src.settlement.simulator import run_scenario


@st.cache_data(ttl=600, show_spinner="Loading trades for the simulator...")
def load_inputs():
    with get_engine().connect() as conn:
        trades = load_trades(conn)
        holidays = {r[0] for r in conn.execute(text(
            "SELECT calendar_date FROM business_calendar WHERE holiday_name IS NOT NULL"))}
    return trades, holidays


@st.cache_data(ttl=600, show_spinner="Running scenario...")
def scenario_frame(cycle_days, conf, match, instr, cutoff="strict"):
    """Per-trade outcome for a cycle and stage-time multipliers (1.0 = unchanged)."""
    trades, holidays = load_inputs()
    levers = {"confirmation": conf, "matching": match, "instruction": instr, "cutoff": cutoff}
    res = run_scenario(trades, cycle_days, holidays, levers)
    rows = [{"trade_id": t["trade_id"], "trade_datetime": t["trade_datetime"], "notional": t["notional"],
             "counterparty_id": t["counterparty_id"],
             "at_risk": res[t["trade_id"]]["at_risk"], "flags": res[t["trade_id"]]["flags"]} for t in trades]
    df = pd.DataFrame(rows)
    df["trade_day"] = pd.to_datetime(df["trade_datetime"]).dt.date
    df["hour"] = pd.to_datetime(df["trade_datetime"]).dt.hour
    return df


def sim_runs():
    try:
        return run_query("""SELECT scenario, cycle_days, trades, at_risk_trades, at_risk_pct::float8 AS at_risk_pct,
                                   at_risk_notional::float8 AS at_risk_notional
                            FROM simulation_runs ORDER BY run_id""")
    except Exception:
        return pd.DataFrame()
