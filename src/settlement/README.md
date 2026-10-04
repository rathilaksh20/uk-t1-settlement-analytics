# UK T+1 Securities Settlement Risk & Operations Analytics

An end-to-end data project on the UK move from **T+2 to T+1 securities settlement (11 October 2027)**.
Real UK market inputs ground a **synthetic** post-trade operations layer. A rules engine flags trades at risk of
failing to settle, a simulator replays the same processing times under T+1, and a Streamlit dashboard shows where the
pressure lands.

> **All operational data is synthetic.** Failure rates here are outputs of an engineering simulation, not estimates for
> any real firm. Real inputs: UK bank holidays, Bank of England rates and London share prices.

## What it shows (seed 42, 20,000 trades)

| Scenario | Trades at risk | Notional at risk |
|---|---|---|
| T+2 baseline | 12.9% | £1,177m |
| T+1, strict cut-off | 33.6% | £2,675m |
| T+1, relaxed cut-off | 23.9% | £2,000m |
| T+1, strict, matching 30% faster | 27.2% | £2,277m |
| T+1, strict, all stages 25% faster | 24.8% | £2,051m |
| T+1, relaxed, matching 30% faster | 17.5% | £1,562m |

- **The cut-off assumption is worth about 10 points.** Strict cut-offs (matching and instruction finished by the close of
  the trade date) take at-risk trades from 12.9% to 33.6%. Relaxed cut-offs (09:00 and 10:00 on the settlement morning)
  give 23.9%. Both are shown because real firms' cut-offs differ.
- **Matching is the stage to fix.** Under strict cut-offs, speeding up matching by 30% cuts risk by 6.4 points, versus
  1.7 points for a 20% faster confirmation and 0.9 points for a 30% faster instruction stage.
- **Late-day trades carry the pressure.** About 90% of trades executed at 16:00 are at risk under strict T+1 cut-offs
  (about 60% under relaxed), versus about 27% under T+2.
- **Targeting beats broad effort.** Halving processing time for only the three worst counterparties does almost as much
  as speeding up all matching by 30%.
- **A single number would mislead.** If stage times are 20% better or worse than assumed, strict T+1 risk ranges from
  about 27% to 40%.

Results describe this synthetic process under stated assumptions. They are not estimates for any real firm.

## Dashboard

![Executive overview](docs/screenshots/overview.png)

![T+2 versus T+1 simulation](docs/screenshots/simulation.png)

Seven pages: executive overview, settlement operations (filterable trade table), exceptions, counterparties and time of
day, T+2 versus T+1 simulation (interactive what-if sliders), trade detail, and data and assumptions (live data-quality
checks).

## Architecture

`public data + synthetic generator -> ingestion/validation -> PostgreSQL -> rules engine -> exceptions -> SQL KPIs -> T+1 simulator -> Streamlit`

- **Data sources:** gov.uk bank holidays, Bank of England IADB (Bank Rate, SONIA, GBP/USD), Yahoo Finance prices via `yfinance`.
- **Causal synthetic layer:** hidden counterparty reliability and responsiveness drive confirmation, matching and
  instruction times. Trade size, time of day and operational shock days add pressure.
- **Rules engine:** every rule is checked, all flags are kept, and the highest-priority flag becomes the primary reason.
- **Simulator:** stage durations are drawn once and replayed under T+1 (common random numbers), so differences come from
  the shorter window, not randomness. Replaying T+2 reproduces the stored results exactly (0 mismatches in 20,000 trades).
- **Quality:** 15 automated data-quality checks, 71 unit tests, and every data load recorded in `ingestion_log` with a checksum.

## Project structure

```
src/
  ingestion/   load_calendar.py, load_boe.py, load_prices.py
  settlement/  dates.py, clock.py, rules.py, simulator.py, run_simulation.py
  synthetic/   trades.py, operations.py, build_operations.py, build_exceptions.py
  quality/     checks.py, run_checks.py
dashboard/     app.py, data.py, sim.py, views.py
database/      schema.sql, schema_ops.sql, queries/02_kpis.sql
tests/         unit tests for each module
```

## Run it locally

Requires Python 3.11+ and PostgreSQL. Create a database called `settlement_db` and put its connection string in a
`.env` file in the project root:

```
DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/settlement_db
```

Then, in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# run database\schema.sql and database\schema_ops.sql once in pgAdmin or psql
python src\seed_reference.py
python -m src.ingestion.load_calendar
python -m src.ingestion.load_boe
python -m src.ingestion.load_prices
python -m src.synthetic.trades --n 20000 --reset
python -m src.synthetic.build_operations
python -m src.synthetic.build_exceptions
python -m src.quality.run_checks
python -m src.settlement.run_simulation
streamlit run dashboard/app.py
```

If a share is quoted in pounds rather than pence on Yahoo (Compass Group was), reload with
`python -m src.ingestion.load_prices --from-file <raw csv> --already-gbp CPG`.

## Testing and quality

```powershell
python -m pytest -q
python -m src.quality.run_checks
```

## Data sources and licensing

| Source | Used for | Notes |
|---|---|---|
| gov.uk bank holidays | Business-day calendar | Open Government Licence |
| Bank of England statistical database | Bank Rate, SONIA, GBP/USD | See BoE re-use terms |
| Yahoo Finance via `yfinance` | Daily share prices | Unofficial wrapper, personal and educational use only; raw files are not committed |
| Generator in this repository | Trades, counterparties, stage times, positions, flags, exceptions | **Synthetic** |

## Limitations

- Synthetic operations: results illustrate mechanics, not real-world failure rates.
- The T+1 cut-offs are assumptions (strict and relaxed versions are shown).
- Funding shortfalls and reconciliation breaks are not time-driven in the model.
- The FCA Market Activity Reporter (a manual download) is not yet used to weight instrument volumes.

## Roadmap

- Explainable machine-learning risk model: time-based validation, a rules-only baseline, SHAP explanations.
- AWS deployment (S3, RDS, scheduled refresh) and CI.
