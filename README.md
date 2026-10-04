# UK T+1 Securities Settlement Risk & Operations Analytics

An end-to-end data project on the UK move from **T+2 to T+1 settlement (11 October 2027)**.
Real UK market inputs ground a **synthetic** post-trade operations layer. A rules engine flags
trades at risk of failing to settle, a simulator replays the same processing times under T+1, and a
Streamlit dashboard shows where the pressure lands.

> **All operational data is synthetic.** Failure rates here are outputs of an engineering simulation,
> not estimates for any real firm. Real inputs: UK bank holidays, Bank of England rates, London share prices.

## What it shows (seed 42, 1,000 trades)

| Scenario | Trades at risk | Notional at risk |
|---|---|---|
| T+2 baseline | 14.1% | £53.6m |
| T+1, as is | 31.7% | £108.9m |
| T+1, matching 30% faster | 25.7% | £91.7m |
| T+1, all stages 25% faster | 23.9% | £82.9m |

- Under the stated cut-off assumption, T+1 more than doubles the share of trades at risk.
- The **matching** stage is the most sensitive: speeding it up helps far more than speeding up instruction.
- Late-day trades are the most exposed, because less working time remains before cut-offs.

The headline numbers depend on one assumption: under T+1, every internal cut-off moves one business day
earlier but never before the close of the trade date. Treat results as a description of this synthetic process.

## Architecture

`public data + synthetic generator -> ingestion/validation -> PostgreSQL -> rules engine -> exceptions -> SQL KPIs -> T+1 simulator -> Streamlit`

- **Data sources:** gov.uk bank holidays, Bank of England IADB (Bank Rate, SONIA, GBP/USD), Yahoo Finance prices via `yfinance`.
- **Causal synthetic layer:** hidden counterparty reliability and responsiveness drive confirmation, matching and
  instruction times; trade size, time of day and operational shock days add pressure.
- **Quality:** 15 automated data-quality checks, 68 unit tests, every load recorded in `ingestion_log`.
- **Simulator:** stage durations are drawn once and replayed under T+1 (common random numbers), so differences come
  from the shorter window, not randomness.

## Run it locally

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# create settlement_db in PostgreSQL, put DATABASE_URL in .env, then run database\schema.sql and database\schema_ops.sql
python src\seed_reference.py
python -m src.ingestion.load_calendar
python -m src.ingestion.load_boe
python -m src.ingestion.load_prices
python -m src.synthetic.trades --n 1000 --reset
python -m src.synthetic.build_operations
python -m src.synthetic.build_exceptions
python -m src.quality.run_checks
python -m src.settlement.run_simulation
streamlit run dashboard/app.py
```

## Limitations

- Synthetic operations: results illustrate mechanics, not real-world failure rates.
- Funding shortfalls and reconciliation breaks are not time-driven in the model.
- `yfinance` is an unofficial wrapper for personal/educational use; raw price files are not committed.
- The FCA Market Activity Reporter (manual download) is not yet used to weight instrument volumes.

## Screenshots

Add dashboard screenshots to `docs/screenshots/` and link them here.
