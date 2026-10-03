from src.quality.checks import CHECKS, isin_is_valid


def test_check_names_unique():
    names = [c[0] for c in CHECKS]
    assert len(names) == len(set(names))


def test_checks_are_read_only_selects_with_valid_severity():
    for name, severity, sql in CHECKS:
        assert sql.strip().upper().startswith("SELECT"), name
        assert severity in ("critical", "warning"), name
        for word in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER "):
            assert word not in sql.upper(), name


def test_valid_isins():
    for isin in ("GB0005405286", "GB00BP6MXD84", "JE00B4T3BW64"):
        assert isin_is_valid(isin)


def test_invalid_isins():
    assert not isin_is_valid("GB0005405287")   # wrong check digit
    assert not isin_is_valid("GB000540528")    # too short
    assert not isin_is_valid("GB0005405-86")   # not alphanumeric