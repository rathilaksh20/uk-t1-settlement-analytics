from datetime import date

import pytest

from src.ingestion.load_boe import build_url, parse_boe_csv

SAMPLE = """DATE,IUDBEDR,IUDSOIA
02 Jan 2026,3.75,3.7312
05 Jan 2026,3.75,3.7298
06 Jan 2026,3.75,
"""


def test_build_url_contains_required_parts():
    u = build_url(["IUDBEDR", "IUDSOIA"], date(2025, 1, 1))
    assert "SeriesCodes=IUDBEDR,IUDSOIA" in u
    assert "Datefrom=01/Jan/2025" in u
    assert "csv.x=yes" in u and "CSVF=TN" in u


def test_parse_good_rows_and_skip_empty_cells():
    rows, rejected, dups = parse_boe_csv(SAMPLE)
    assert rejected == [] and dups == 0
    assert len(rows) == 5                      # last SONIA cell is empty, so skipped
    assert {"series_code": "IUDBEDR", "obs_date": date(2026, 1, 2), "value": 3.75} in rows


def test_bad_value_and_bad_date_are_rejected_not_loaded():
    bad = "DATE,IUDBEDR\n02 Jan 2026,n/a\nnot a date,3.5\n05 Jan 2026,3.5\n"
    rows, rejected, _ = parse_boe_csv(bad)
    assert len(rows) == 1 and rows[0]["obs_date"] == date(2026, 1, 5)
    assert len(rejected) == 2


def test_duplicates_counted_once():
    dup = "DATE,IUDBEDR\n02 Jan 2026,3.75\n02 Jan 2026,3.75\n"
    rows, _, dups = parse_boe_csv(dup)
    assert len(rows) == 1 and dups == 1


def test_unexpected_format_raises():
    with pytest.raises(ValueError):
        parse_boe_csv("<html>Access denied</html>")