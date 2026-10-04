"""Dashboard pages. Every page shows the synthetic-data banner."""
import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard import data
from dashboard.sim import scenario_frame, sim_runs

BANNER = ("**Synthetic operational data. Not real bank data.** Real inputs: UK bank holidays, Bank of England rates "
          "and London share prices. Settlement operations, counterparties and outcomes are simulated.")
TEAL, NAVY, AMBER, GREY = "#0F766E", "#1F3864", "#B45309", "#94A3B8"


def banner():
    st.warning(BANNER, icon="⚠️")


def empty(df):
    if df is None or len(df) == 0:
        st.info("No data for the selected date range.")
        return True
    return False


def gbp_m(x):
    return f"£{x / 1e6:,.1f}m"


# ---------------------------------------------------------------- 1. Overview
def overview(d1, d2):
    st.header("Executive overview")
    banner()
    k = data.kpis(d1, d2)
    if k["trades"] == 0:
        st.info("No trades in the selected date range.")
        return
    c = st.columns(5)
    c[0].metric("Trades", f"{int(k['trades']):,}")
    c[1].metric("Notional", gbp_m(k["notional"]))
    c[2].metric("Ready to settle", f"{100 * (1 - k['at_risk'] / k['trades']):.1f}%")
    c[3].metric("At risk", f"{int(k['at_risk']):,}", f"{100 * k['at_risk'] / k['trades']:.1f}% of trades", delta_color="off", delta_arrow="off")
    c[4].metric("Notional at risk", gbp_m(k["at_risk_notional"]), f"{100 * k['at_risk_notional'] / k['notional']:.1f}% of value", delta_color="off", delta_arrow="off")

    exc = data.exceptions_df(d1, d2)
    resolved = exc[exc["resolution_status"] == "RESOLVED"]
    c2 = st.columns(3)
    c2[0].metric("Trades with an exception", f"{100 * k['with_exception'] / k['trades']:.1f}%")
    c2[1].metric("Median resolution time", f"{resolved['elapsed_hours'].median():.1f} h" if len(resolved) else "n/a")
    c2[2].metric("Open exceptions", f"{int((exc['resolution_status'] == 'OPEN').sum()):,}")

    left, right = st.columns([3, 2])
    d = data.daily(d1, d2)
    if not empty(d):
        d["rolling_7d"] = 100 * d["at_risk"].rolling(7, min_periods=1).sum() / d["trades"].rolling(7, min_periods=1).sum()
        d["daily_pct"] = 100 * d["at_risk"] / d["trades"]
        fig = px.line(d, x="trade_day", y=["daily_pct", "rolling_7d"],
                      labels={"value": "% of trades at risk", "trade_day": "", "variable": ""},
                      color_discrete_sequence=[GREY, TEAL], title="At-risk rate by trade day")
        names = {"daily_pct": "Daily", "rolling_7d": "7-day rolling"}
        fig.for_each_trace(lambda tr: tr.update(name=names[tr.name]))
        fig.data[0].update(line={"width": 1}, opacity=0.55)
        fig.data[1].update(line={"width": 3.5})
        fig.update_layout(legend={"orientation": "h", "y": -0.15})
        left.plotly_chart(fig)
    fm = data.flag_mix(d1, d2)
    if not empty(fm):
        fig = px.bar(fm, x="trades", y="flag_type", orientation="h", title="What is flagging trades",
                     labels={"flag_type": "", "trades": "Trades flagged"}, color_discrete_sequence=[NAVY])
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        right.plotly_chart(fig)
    st.caption("A trade can carry several flags, so flag counts can exceed the number of at-risk trades.")


# ---------------------------------------------------------------- 2. Operations
def operations(d1, d2):
    st.header("Settlement operations")
    banner()
    df = data.trades_table(d1, d2)
    if empty(df):
        return
    f = st.columns(4)
    status = f[0].selectbox("Status", ["All", "AT_RISK", "READY_TO_SETTLE"])
    cps = f[1].multiselect("Counterparty", sorted(df["counterparty"].unique()))
    tickers = f[2].multiselect("Instrument", sorted(df["ticker"].unique()))
    reasons = f[3].multiselect("Primary reason", sorted(df["primary_reason"].dropna().unique()))
    if status != "All":
        df = df[df["status"] == status]
    if cps:
        df = df[df["counterparty"].isin(cps)]
    if tickers:
        df = df[df["ticker"].isin(tickers)]
    if reasons:
        df = df[df["primary_reason"].isin(reasons)]
    st.write(f"**{len(df):,} trades** | notional {gbp_m(df['value_gbp'].sum())}")
    st.dataframe(df, hide_index=True, height=520)
    st.download_button("Download filtered trades (CSV)", df.to_csv(index=False).encode("utf-8"),
                       file_name="filtered_trades.csv", mime="text/csv")


# ---------------------------------------------------------------- 3. Exceptions
def exceptions(d1, d2):
    st.header("Exceptions")
    banner()
    ex = data.exceptions_df(d1, d2)
    if empty(ex):
        return
    left, right = st.columns(2)
    by = ex.groupby(["exception_type", "severity"]).size().reset_index(name="count")
    fig = px.bar(by, x="count", y="exception_type", color="severity", orientation="h", title="Exceptions by type and severity",
                 color_discrete_map={"HIGH": "#B91C1C", "MEDIUM": AMBER, "LOW": GREY},
                 labels={"exception_type": "", "count": "Exceptions"})
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    left.plotly_chart(fig)

    res = ex[ex["resolution_status"] == "RESOLVED"].copy()
    if len(res):
        fig = px.box(res, x="exception_type", y="elapsed_hours", title="Resolution time (elapsed hours)",
                     labels={"exception_type": "", "elapsed_hours": "Hours"}, color_discrete_sequence=[TEAL])
        right.plotly_chart(fig)
        st.caption("Elapsed wall-clock hours, so weekends are included.")

    st.subheader("Open exceptions and ageing")
    op = ex[ex["resolution_status"] == "OPEN"].copy()
    if len(op) == 0:
        st.success("No open exceptions in this range.")
    else:
        as_of = ex["created_at"].max()
        op["age_days"] = ((as_of - op["created_at"]).dt.total_seconds() / 86400).round(1)
        op["age_bucket"] = pd.cut(op["age_days"], [-1, 1, 2, 5, 1e9], labels=["0-1 days", "1-2 days", "2-5 days", "5+ days"])
        st.write(f"Ageing measured against the latest exception timestamp ({as_of:%Y-%m-%d %H:%M}).")
        st.dataframe(op[["exception_id", "trade_id", "exception_type", "severity", "counterparty", "created_at", "age_days", "age_bucket"]],
                     hide_index=True)


# ---------------------------------------------------------------- 4. Counterparties
def counterparties(d1, d2):
    st.header("Counterparties and instruments")
    banner()
    cp = data.counterparty_table(d1, d2)
    if empty(cp):
        return
    cp["at_risk_pct"] = 100 * cp["at_risk_trades"] / cp["trades"]
    cp["share_of_at_risk_value"] = 100 * cp["at_risk_value"] / cp["at_risk_value"].sum() if cp["at_risk_value"].sum() else 0
    cp = cp.sort_values("at_risk_value", ascending=False)
    ex = data.exceptions_df(d1, d2)
    if len(ex):
        top5 = ex["counterparty"].value_counts().head(5).sum() / len(ex) * 100
        st.metric("Share of exceptions from the top 5 counterparties", f"{top5:.1f}%")
    left, right = st.columns(2)
    fig = px.bar(cp.head(10), x="at_risk_value", y="counterparty", orientation="h", title="At-risk value by counterparty (top 10)",
                 labels={"at_risk_value": "At-risk notional (GBP)", "counterparty": ""}, color_discrete_sequence=[NAVY])
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    left.plotly_chart(fig)
    big = cp[cp["trades"] >= max(10, cp["trades"].median() / 2)]
    fig = px.scatter(big, x="trades", y="at_risk_pct", size="at_risk_value", hover_name="counterparty",
                     title="At-risk rate versus activity", labels={"trades": "Trades", "at_risk_pct": "% at risk"},
                     color_discrete_sequence=[TEAL])
    right.plotly_chart(fig)
    st.caption("Counterparties with few trades are noisy; the scatter hides the smallest ones.")
    st.dataframe(cp.round(1), hide_index=True)

    st.subheader("Time of day")
    h = data.hour_table(d1, d2)
    if not empty(h):
        h["at_risk_pct"] = 100 * h["at_risk"] / h["trades"]
        fig = px.bar(h, x="hour", y="at_risk_pct", title="At-risk rate by hour the trade was executed",
                     labels={"hour": "Hour of day", "at_risk_pct": "% at risk"}, color_discrete_sequence=[AMBER])
        st.plotly_chart(fig)
        st.caption("Late-day trades have less working time left before internal cut-offs.")


# ---------------------------------------------------------------- 5. T+1 simulation
def simulation(d1, d2):
    st.header("T+2 versus T+1 simulation")
    banner()
    st.write("The same stage durations are replayed under T+1 deadlines, so any difference comes from the shorter window. "
             "The result depends on **where the T+1 cut-offs sit**, so two assumptions are shown side by side:")
    st.markdown("- **Strict:** matching and instruction must finish by the close of the trade date.\n"
                "- **Relaxed:** matching by 09:00 and instruction by 10:00 on the settlement morning.")
    st.caption("Both describe this synthetic process, not any real firm.")

    st.subheader("What-if: speed up the stages")
    c = st.columns(4)
    conf = 1 - c[0].slider("Confirmation faster by (%)", 0, 60, 0, 5) / 100
    match = 1 - c[1].slider("Matching faster by (%)", 0, 60, 0, 5) / 100
    instr = 1 - c[2].slider("Instruction faster by (%)", 0, 60, 0, 5) / 100
    cut = c[3].selectbox("Apply levers under the T+1 cut-off", ["Strict", "Relaxed"]).lower()

    t2 = scenario_frame(2, 1.0, 1.0, 1.0)
    t1s = scenario_frame(1, 1.0, 1.0, 1.0, "strict")
    t1r = scenario_frame(1, 1.0, 1.0, 1.0, "relaxed")
    t1l = scenario_frame(1, conf, match, instr, cut)

    def window(df):
        return df[(df["trade_day"] >= d1) & (df["trade_day"] <= d2)]
    t2, t1s, t1r, t1l = window(t2), window(t1s), window(t1r), window(t1l)
    if empty(t2):
        return
    pct = lambda df: 100 * df["at_risk"].mean()
    m = st.columns(4)
    m[0].metric("T+2 baseline at risk", f"{pct(t2):.1f}%")
    m[1].metric("T+1 strict cut-off", f"{pct(t1s):.1f}%", f"{pct(t1s) - pct(t2):+.1f} pts vs T+2", delta_color="inverse")
    m[2].metric("T+1 relaxed cut-off", f"{pct(t1r):.1f}%", f"{pct(t1r) - pct(t2):+.1f} pts vs T+2", delta_color="inverse")
    m[3].metric(f"T+1 {cut} with your levers", f"{pct(t1l):.1f}%", f"{pct(t1l) - pct(t2):+.1f} pts vs T+2", delta_color="inverse")

    names = ["T+2", "T+1 strict", "T+1 relaxed", "T+1 with levers"]
    frames = [t2, t1s, t1r, t1l]
    colors = {"T+2": NAVY, "T+1 strict": AMBER, "T+1 relaxed": "#6D28D9", "T+1 with levers": TEAL}
    left, right = st.columns(2)

    def flag_counts(df, label):
        s = df["flags"].explode().dropna().value_counts().rename_axis("flag").reset_index(name="trades")
        s["scenario"] = label
        return s
    fc = pd.concat([flag_counts(f, n) for f, n in zip(frames, names)])
    if len(fc):
        fig = px.bar(fc, x="flag", y="trades", color="scenario", barmode="group", title="Flags by type",
                     color_discrete_map=colors, labels={"flag": "", "trades": "Trades"})
        left.plotly_chart(fig)

    def by_hour(df, label):
        g = df.groupby("hour")["at_risk"].mean().mul(100).reset_index(name="at_risk_pct")
        g["scenario"] = label
        return g
    hh = pd.concat([by_hour(f, n) for f, n in zip(frames, names)])
    fig = px.line(hh, x="hour", y="at_risk_pct", color="scenario", markers=True, title="At-risk rate by trade hour",
                  color_discrete_map=colors, labels={"hour": "Hour of day", "at_risk_pct": "% at risk"})
    right.plotly_chart(fig)
    st.caption("Under the strict cut-off, trades executed late in the day have almost no working time left, so risk climbs steeply. "
               "Funding shortfalls and reconciliation breaks are not time-driven, so they do not change between cycles.")

    st.subheader("Stored scenario runs")
    runs = sim_runs()
    if empty(runs):
        st.info("Run `python -m src.settlement.run_simulation` to store scenario results.")
    else:
        fig = px.bar(runs, x="at_risk_pct", y="scenario", orientation="h", color=runs["cycle_days"].map({2: "T+2", 1: "T+1"}),
                     title="At-risk % by scenario (all stored trades)", labels={"at_risk_pct": "% of trades at risk", "scenario": "", "color": ""},
                     color_discrete_map={"T+2": NAVY, "T+1": AMBER})
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=520)
        st.plotly_chart(fig)
        st.dataframe(runs.round(2), hide_index=True)


# ---------------------------------------------------------------- 6. Trade detail
def trade_detail():
    st.header("Trade detail")
    banner()
    ids = data.trade_ids()
    if not ids:
        st.info("No trades loaded.")
        return
    st.caption("At-risk trades are listed first.")
    tid = st.selectbox("Trade", ids)
    head, events, flags, excs = data.trade_detail(tid)
    if empty(head):
        return
    h = head.iloc[0]
    c = st.columns(4)
    c[0].metric("Instrument", h["ticker"], h["instrument_name"], delta_color="off", delta_arrow="off")
    c[1].metric("Side and size", f"{h['side']} {h['quantity']:,.0f}")
    c[2].metric("Value", f"£{h['value_gbp']:,.0f}", f"@ £{h['price']:,.2f}", delta_color="off", delta_arrow="off")
    c[3].metric("Status", h["status"].replace("_", " ").title(), h["primary_reason"] or "no flags", delta_color="off", delta_arrow="off")
    st.write(f"**Counterparty:** {h['counterparty']}  |  **Traded:** {h['trade_datetime']:%a %d %b %Y %H:%M}  |  "
             f"**Settles:** {h['settlement_date']:%a %d %b %Y}")

    left, right = st.columns(2)
    left.subheader("Event timeline")
    if len(events):
        fig = px.scatter(events, x="event_timestamp", y="event_type", color="event_status",
                         color_discrete_map={"ON_TIME": TEAL, "LATE": "#B91C1C", "DONE": GREY}, labels={"event_timestamp": "", "event_type": ""})
        fig.update_traces(marker_size=14)
        left.plotly_chart(fig)
        left.dataframe(events, hide_index=True)
    right.subheader("Checks and exceptions")
    if len(flags):
        right.write("**Flags raised:** " + ", ".join(flags["flag_type"]))
    else:
        right.success("No flags: ready to settle.")
    if len(excs):
        right.dataframe(excs, hide_index=True)
    right.write(f"**Cash:** needed £{h['cash_required']:,.0f}, available £{h['cash_available']:,.0f}  |  "
                f"**Securities:** needed {h['securities_required']:,.0f}, available {h['securities_available']:,.0f}")

    st.subheader("Under T+2 versus T+1")
    t2, t1 = scenario_frame(2, 1.0, 1.0, 1.0), scenario_frame(1, 1.0, 1.0, 1.0)
    r2, r1 = t2[t2["trade_id"] == tid].iloc[0], t1[t1["trade_id"] == tid].iloc[0]
    st.write(f"**T+2:** {'AT RISK: ' + ', '.join(r2['flags']) if r2['at_risk'] else 'ready to settle'}  |  "
             f"**T+1:** {'AT RISK: ' + ', '.join(r1['flags']) if r1['at_risk'] else 'ready to settle'}")


# ---------------------------------------------------------------- 7. Data and assumptions
def assumptions():
    st.header("Data, assumptions and quality")
    banner()
    st.subheader("Where the data comes from")
    st.markdown("""
| Source | Used for | Nature |
|---|---|---|
| gov.uk bank holidays | Business-day calendar | Real, Open Government Licence |
| Bank of England database | Bank Rate, SONIA, GBP/USD | Real |
| Yahoo Finance via yfinance | Daily share prices (converted from pence) | Real, personal/educational use |
| Generator in this repository | Trades, counterparties, stage times, positions, flags, exceptions | **Synthetic** |
""")
    latest = data.ingestion_latest()
    if len(latest):
        st.write("Latest load per source:")
        st.dataframe(latest, hide_index=True)
    st.dataframe(data.table_counts(), hide_index=True)

    st.subheader("Data-quality checks (live)")
    try:
        from src.quality.run_checks import run
        results = run(data.get_engine())
        q = pd.DataFrame(results, columns=["check", "severity", "violations"])
        q["status"] = q.apply(lambda r: "PASS" if r["violations"] == 0 else ("FAIL" if r["severity"] == "critical" else "WARN"), axis=1)
        st.write(f"**{int((q['violations'] == 0).sum())} of {len(q)} checks passed.**")
        st.dataframe(q, hide_index=True)
    except Exception as e:  # pragma: no cover
        st.error(f"Could not run quality checks: {e}")

    st.subheader("Simulation check (not a modelling input)")
    pc = data.profile_check()
    if len(pc):
        fig = px.scatter(pc, x="responsiveness", y="at_risk_pct", size="trades", hover_name="counterparty_id", color="reliability",
                         title="Hidden counterparty behaviour versus observed at-risk rate",
                         labels={"responsiveness": "Hidden responsiveness", "at_risk_pct": "% at risk"})
        st.plotly_chart(fig)
        st.caption("These hidden scores drive the simulation. They are shown only to validate it and must never be used as machine-learning features.")

    st.subheader("Key assumptions and limitations")
    st.markdown("""
- All operational outcomes are simulated. Failure rates are **not** estimates of any real firm's rates.
- Stage durations are drawn once and replayed unchanged under T+1, so differences come from the shorter window, not randomness.
- The T+1 cut-offs are assumptions. Strict: matching and instruction by the close of the trade date. Relaxed: by 09:00 and 10:00 on the settlement morning. Real firms differ.
- Funding shortfalls and reconciliation breaks are not time-driven in this model.
- Prices are real closing prices with a small intraday variation; trade sizes and counterparties are synthetic.
""")
