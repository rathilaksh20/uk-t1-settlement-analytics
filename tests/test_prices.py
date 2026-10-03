from datetime import date

from src.ingestion.load_prices import build_rows, scale_report, yahoo_symbol
from src.synthetic.trades import generate_trades, make_price_lookup, PLACEHOLDER_PRICE_GBP

T2I = {"HSBA": "GB0005405286", "BP.": "GB0007980591"}
I2T = {v: k for k, v in T2I.items()}


def test_yahoo_symbols():
    assert yahoo_symbol("HSBA") == "HSBA.L"
    assert yahoo_symbol("BP.") == "BP.L"
    assert yahoo_symbol("RR.") == "RR.L"


def test_pence_converted_to_pounds():
    rows, rej, dups = build_rows([{"ticker": "HSBA", "date": "2026-09-01", "close": "950.5", "volume": "1000"}], T2I)
    assert rows[0]["close_gbp"] == 9.505 and rows[0]["volume"] == 1000
    assert rej == [] and dups == 0


def test_bad_rows_rejected_and_duplicates_skipped():
    recs = [
        {"ticker": "HSBA", "date": "2026-09-01", "close": "950", "volume": "1"},
        {"ticker": "HSBA", "date": "2026-09-01", "close": "951", "volume": "1"},   # duplicate
        {"ticker": "NOPE", "date": "2026-09-01", "close": "100", "volume": "1"},   # unknown ticker
        {"ticker": "HSBA", "date": "garbage", "close": "100", "volume": "1"},      # bad date
        {"ticker": "HSBA", "date": "2026-09-02", "close": "-5", "volume": "1"},    # negative price
        {"ticker": "BP.", "date": "2026-09-02", "close": "420", "volume": ""},     # missing volume ok
    ]
    rows, rej, dups = build_rows(recs, T2I)
    assert len(rows) == 2 and len(rej) == 3 and dups == 1
    assert [r for r in rows if r["isin"] == T2I["BP."]][0]["volume"] is None


def test_scale_report_flags_pence_mistake():
    good, _, _ = build_rows([{"ticker": "HSBA", "date": "2026-09-01", "close": "950", "volume": "1"}], T2I)
    assert scale_report(good, I2T)[0][5] == ""
    bad = [dict(r, close_gbp=r["close_gbp"] * 100) for r in good]          # forgot the /100
    assert scale_report(bad, I2T)[0][5] == "CHECK SCALE"


def test_price_lookup_uses_latest_on_or_before():
    f = make_price_lookup([("HSBA", date(2026, 9, 1), 9.0), ("HSBA", date(2026, 9, 3), 9.6)])
    assert f("HSBA", date(2026, 9, 1)) == 9.0
    assert f("HSBA", date(2026, 9, 2)) == 9.0       # weekend/holiday: carry forward
    assert f("HSBA", date(2026, 9, 5)) == 9.6
    assert f("HSBA", date(2026, 8, 31)) is None     # nothing earlier
    assert f("XXXX", date(2026, 9, 1)) is None


def test_generator_uses_real_prices_when_given_else_placeholder():
    inst = [("INS_HSBA", "HSBA"), ("INS_AZN", "AZN")]
    cps = ["CP001", "CP002"]
    lookup = make_price_lookup([("HSBA", date(2026, 6, 1), 20.0)])      # HSBA only
    t = generate_trades(300, 5, inst, cps, set(), price_lookup=lookup)
    hsba = [x["price"] for x in t if x["instrument_id"] == "INS_HSBA"]
    azn = [x["price"] for x in t if x["instrument_id"] == "INS_AZN"]
    assert all(18.0 < p < 22.0 for p in hsba)                          # around the real 20.0
    assert all(PLACEHOLDER_PRICE_GBP["AZN"] * 0.9 < p < PLACEHOLDER_PRICE_GBP["AZN"] * 1.1 for p in azn)

    
def test_already_gbp_ticker_is_not_divided():
    recs = [{"ticker": "HSBA", "date": "2026-09-01", "close": "29.73", "volume": "1"}]
    pence_rows, _, _ = build_rows(recs, T2I)
    gbp_rows, _, _ = build_rows(recs, T2I, already_gbp={"HSBA"})
    assert pence_rows[0]["close_gbp"] == 0.2973
    assert gbp_rows[0]["close_gbp"] == 29.73