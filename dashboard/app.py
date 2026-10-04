"""UK T+1 Settlement Risk dashboard.   Run from the project root:

    streamlit run dashboard/app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="UK T+1 Settlement Risk", page_icon="📊", layout="wide")

from dashboard import data, views  # noqa: E402

PAGES = {
    "Executive overview": lambda d1, d2: views.overview(d1, d2),
    "Settlement operations": lambda d1, d2: views.operations(d1, d2),
    "Exceptions": lambda d1, d2: views.exceptions(d1, d2),
    "Counterparties and time of day": lambda d1, d2: views.counterparties(d1, d2),
    "T+1 simulation": lambda d1, d2: views.simulation(d1, d2),
    "Trade detail": lambda d1, d2: views.trade_detail(),
    "Data and assumptions": lambda d1, d2: views.assumptions(),
}


def main():
    st.sidebar.title("UK T+1 Settlement Risk")
    st.sidebar.caption("Synthetic operations on real UK market inputs")
    page = st.sidebar.radio("Page", list(PAGES))
    try:
        lo, hi = data.date_bounds()
    except Exception as e:
        st.error(f"Could not read the database: {e}")
        st.stop()
    if lo is None:
        st.info("No trades yet. Run the build commands first (see the README).")
        st.stop()
    picked = st.sidebar.date_input("Trade date range", (lo, hi), min_value=lo, max_value=hi)
    d1, d2 = (picked[0], picked[1]) if isinstance(picked, (list, tuple)) and len(picked) == 2 else (lo, hi)
    PAGES[page](d1, d2)


main()
