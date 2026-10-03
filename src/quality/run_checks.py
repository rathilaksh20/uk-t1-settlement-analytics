"""Run all data-quality checks.

    python -m src.quality.run_checks

Prints a PASS/FAIL table and exits with code 1 if any CRITICAL check fails,
so it can also gate a CI pipeline.
"""
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from src.quality.checks import CHECKS, isin_is_valid


def run(engine):
    results = []
    with engine.connect() as conn:
        for name, severity, sql in CHECKS:
            results.append((name, severity, int(conn.execute(text(sql)).scalar())))
        bad_isins = [r[0] for r in conn.execute(text("SELECT isin FROM instruments")) if not isin_is_valid(r[0])]
        results.append(("instrument_isin_check_digits_valid", "critical", len(bad_isins)))
    return results


def main():
    load_dotenv()
    engine = create_engine(os.environ["DATABASE_URL"])
    results = run(engine)

    width = max(len(n) for n, _, _ in results)
    failed_critical = 0
    for name, severity, violations in results:
        status = "PASS" if violations == 0 else ("FAIL" if severity == "critical" else "WARN")
        if violations and severity == "critical":
            failed_critical += 1
        print(f"{status:5s} {name:<{width}}  violations={violations}  [{severity}]")

    total = len(results)
    print(f"\n{total - sum(1 for _, _, v in results if v)} of {total} checks passed.")
    if failed_critical:
        print(f"{failed_critical} CRITICAL check(s) failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()