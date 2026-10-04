"""Data access for the dashboard. All queries are read-only and cached."""
import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

DATE_FILTER = "t.trade_datetime::date BETWEEN :d1 AND :d2"


@st.cache_resource
def get_engine():
    load_dotenv()
    return create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)


@st.cache_data(ttl=300, show_spinner=False)
def run_query(sql, params=None):
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def date_bounds():
    df = run_query("SELECT MIN(trade_datetime)::date AS lo, MAX(trade_datetime)::date AS hi FROM trades")
    return df["lo"].iloc[0], df["hi"].iloc[0]


def kpis(d1, d2):
    return run_query(f"""
        SELECT COUNT(*) AS trades,
               COALESCE(SUM(t.trade_value), 0)::float8 AS notional,
               COUNT(*) FILTER (WHERE s.settlement_status = 'AT_RISK') AS at_risk,
               COALESCE(SUM(t.trade_value) FILTER (WHERE s.settlement_status = 'AT_RISK'), 0)::float8 AS at_risk_notional,
               COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM exceptions e WHERE e.trade_id = t.trade_id)) AS with_exception
        FROM trades t JOIN settlement_status s USING (trade_id)
        WHERE {DATE_FILTER}""", {"d1": d1, "d2": d2}).iloc[0]


def daily(d1, d2):
    return run_query(f"""
        SELECT t.trade_datetime::date AS trade_day, COUNT(*) AS trades,
               COUNT(*) FILTER (WHERE s.settlement_status = 'AT_RISK') AS at_risk
        FROM trades t JOIN settlement_status s USING (trade_id)
        WHERE {DATE_FILTER} GROUP BY 1 ORDER BY 1""", {"d1": d1, "d2": d2})


def flag_mix(d1, d2):
    return run_query(f"""
        SELECT f.flag_type, COUNT(*) AS trades
        FROM settlement_flags f JOIN trades t USING (trade_id)
        WHERE {DATE_FILTER} GROUP BY 1 ORDER BY 2 DESC""", {"d1": d1, "d2": d2})


def trades_table(d1, d2):
    return run_query(f"""
        SELECT t.trade_id, i.ticker, c.counterparty_name AS counterparty, t.side,
               t.quantity::float8 AS quantity, t.price::float8 AS price, t.trade_value::float8 AS value_gbp,
               t.trade_datetime, t.settlement_date, s.settlement_status AS status, s.primary_reason,
               COALESCE((SELECT string_agg(f.flag_type, ', ' ORDER BY f.flag_type)
                         FROM settlement_flags f WHERE f.trade_id = t.trade_id), '') AS flags
        FROM trades t
        JOIN instruments i USING (instrument_id)
        JOIN counterparties c USING (counterparty_id)
        JOIN settlement_status s USING (trade_id)
        WHERE {DATE_FILTER} ORDER BY t.trade_datetime""", {"d1": d1, "d2": d2})


def exceptions_df(d1, d2):
    return run_query(f"""
        SELECT e.exception_id, e.trade_id, e.exception_type, e.severity, e.created_at, e.resolved_at,
               e.resolution_status, c.counterparty_name AS counterparty,
               EXTRACT(EPOCH FROM (e.resolved_at - e.created_at)) / 3600.0 AS elapsed_hours
        FROM exceptions e JOIN trades t USING (trade_id) JOIN counterparties c USING (counterparty_id)
        WHERE {DATE_FILTER} ORDER BY e.created_at""", {"d1": d1, "d2": d2})


def counterparty_table(d1, d2):
    return run_query(f"""
        SELECT c.counterparty_name AS counterparty, c.counterparty_type AS type, COUNT(*) AS trades,
               COUNT(*) FILTER (WHERE s.settlement_status = 'AT_RISK') AS at_risk_trades,
               COALESCE(SUM(t.trade_value) FILTER (WHERE s.settlement_status = 'AT_RISK'), 0)::float8 AS at_risk_value
        FROM trades t JOIN settlement_status s USING (trade_id) JOIN counterparties c USING (counterparty_id)
        WHERE {DATE_FILTER} GROUP BY 1, 2""", {"d1": d1, "d2": d2})


def hour_table(d1, d2):
    return run_query(f"""
        SELECT EXTRACT(HOUR FROM t.trade_datetime)::int AS hour, COUNT(*) AS trades,
               COUNT(*) FILTER (WHERE s.settlement_status = 'AT_RISK') AS at_risk
        FROM trades t JOIN settlement_status s USING (trade_id)
        WHERE {DATE_FILTER} GROUP BY 1 ORDER BY 1""", {"d1": d1, "d2": d2})


def trade_ids():
    return run_query("""
        SELECT t.trade_id FROM trades t JOIN settlement_status s USING (trade_id)
        ORDER BY (s.settlement_status = 'AT_RISK') DESC, t.trade_id""")["trade_id"].tolist()


def trade_detail(trade_id):
    p = {"id": trade_id}
    head = run_query("""
        SELECT t.trade_id, i.ticker, i.instrument_name, c.counterparty_name AS counterparty, t.side,
               t.quantity::float8 AS quantity, t.price::float8 AS price, t.trade_value::float8 AS value_gbp,
               t.trade_datetime, t.settlement_date, s.settlement_status AS status, s.primary_reason,
               s.cash_required::float8 AS cash_required, s.cash_available::float8 AS cash_available,
               s.securities_required::float8 AS securities_required, s.securities_available::float8 AS securities_available
        FROM trades t JOIN instruments i USING (instrument_id) JOIN counterparties c USING (counterparty_id)
        JOIN settlement_status s USING (trade_id) WHERE t.trade_id = :id""", p)
    events = run_query("""SELECT event_type, event_timestamp, event_status FROM settlement_events
                          WHERE trade_id = :id ORDER BY event_timestamp""", p)
    flags = run_query("SELECT flag_type FROM settlement_flags WHERE trade_id = :id ORDER BY 1", p)
    excs = run_query("""SELECT exception_type, severity, created_at, resolved_at, resolution_status
                        FROM exceptions WHERE trade_id = :id ORDER BY created_at""", p)
    return head, events, flags, excs


def ingestion_latest():
    return run_query("""
        SELECT DISTINCT ON (source_id) source_id, retrieved_at, row_count, licence_note
        FROM ingestion_log ORDER BY source_id, retrieved_at DESC""")


def table_counts():
    tables = ["instruments", "counterparties", "trades", "settlement_events", "settlement_flags",
              "exceptions", "business_calendar", "rates_daily", "market_prices_daily"]
    rows = []
    for t in tables:
        try:
            rows.append((t, int(run_query(f"SELECT COUNT(*) AS n FROM {t}")["n"].iloc[0])))
        except Exception:
            rows.append((t, None))
    return pd.DataFrame(rows, columns=["table", "rows"])


def profile_check():
    return run_query("""
        SELECT p.counterparty_id, p.reliability::float8 AS reliability, p.responsiveness::float8 AS responsiveness,
               COUNT(*) AS trades,
               100.0 * COUNT(*) FILTER (WHERE s.settlement_status = 'AT_RISK') / COUNT(*) AS at_risk_pct
        FROM counterparty_profile p JOIN trades t USING (counterparty_id) JOIN settlement_status s USING (trade_id)
        GROUP BY 1, 2, 3 ORDER BY at_risk_pct DESC""")
