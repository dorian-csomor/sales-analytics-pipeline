# Sales Analytics Pipeline: from operational database to management report

End-to-end analytics project for **Vireo Wholesale**, a fictional B2B distributor of office and
facility supplies selling in five Central European countries (4 currencies, 2023–2026).

```
┌──────────────────────┐    SQL     ┌─────────────────────────────┐          ┌──────────────────────┐        ┌──────────────┐
│ PostgreSQL  ops.*    │ ─────────▶ │ Python / pandas             │ ───────▶ │ PostgreSQL           │ ─────▶ │ Power BI     │
│ messy source system  │  extract   │ cleanse · validate · model  │   load   │ analytics.* (star)   │        │ mgmt report  │
└──────────────────────┘            └─────────────────────────────┘          └──────────────────────┘        └──────────────┘
                                         │ data quality log & report
                                         ▼
                                    etl.data_quality_log · reports/data_quality_report.md
```

> **About the data:** the source database is simulated but realistic. It was generated for this project
> and contains deliberately planted data quality problems and business patterns, similar to a real ERP.
> See [docs/source_data_design.md](docs/source_data_design.md).

## Highlights

- **21 data quality issues detected and handled**, each one logged with row counts and the action
  taken → [sample data quality report](reports/data_quality_report.md)
- Dates in **5 text formats**, **4 currencies** converted to EUR with monthly FX rates, purchase cost
  matched to the order date with an **as-of join**
- **Duplicate** orders, customers and products detected and merged
- **Star schema** with conformed dimensions and "Unknown" members: no fact rows are silently lost
- **Validation gate**: primary keys, foreign keys and value ranges are checked before anything is loaded,
  and the load runs in a single transaction
- **Unit tests** (pytest), logging, configuration via `.env`, run history in the database
- **BI-tool independent**: the analytics schema works with Power BI, Tableau, Excel or plain SQL. Switching the
  database to SQL Server means changing the connection URL.

## Project status

- [x] **Step 1:** Source database (schema, data generator, loader)
- [x] **Step 2:** ETL pipeline (SQL extraction, Python cleansing, star schema)
- [ ] **Step 3:** Power BI management report
- [ ] **Step 4:** Documentation & screenshots

## Tech stack

PostgreSQL · SQL · Python (pandas, SQLAlchemy, psycopg, pytest) · Power BI (DAX, star schema) · Git

## Data model (analytics schema)

| Table | Grain | Key columns |
|---|---|---|
| `fact_sales` | one order line (cancelled orders excluded) | quantity, gross/net sales, discount, cost, gross margin (EUR) |
| `fact_returns` | one return | quantity returned, return value (EUR), reason |
| `dim_date` | one day | year, quarter, month, week, weekday |
| `dim_customer` | one customer (duplicates merged) | segment, country, account owner, first/last order, cohort, status |
| `dim_product` | one product (duplicates merged) | SKU, category, supplier, list price |
| `dim_sales_rep` | one sales rep | territory, hire/termination date |

## Getting started

Requirements: Python 3.11+, PostgreSQL 14+.

```bash
# 1. virtual environment and packages
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt

# 2. database connection
copy .env.example .env            # Windows  (macOS/Linux: cp .env.example .env)
#    then open .env and set PGPASSWORD

# 3. create the source database
python scripts/generate_source_data.py
python scripts/setup_source_db.py

# 4. run the ETL pipeline
python run_pipeline.py

# optional
python run_pipeline.py --dry-run      # run everything except the database load
python run_pipeline.py --export-csv   # also write the star schema to data/analytics_csv/
python -m pytest                      # run the unit tests
```

## Repository structure

```
run_pipeline.py            entry point: extract → transform → validate → load
etl/
  config.py                settings and business rules
  extract.py               runs the SQL extraction queries
  cleaning.py              reusable cleansing helpers (unit tested)
  reference.py             mappings: countries, statuses, currencies, date formats
  transform.py             cleansing rules and star schema build
  validate.py              integrity checks before loading
  load.py                  transactional load into PostgreSQL
  quality.py               data quality log and report
database/
  source/                  source schema and load script
  extract/                 one SQL extraction query per source table
  profiling/               SQL used to profile the source before writing the rules
  analytics/               star schema DDL and ETL metadata tables
scripts/                   data generator and source database setup
tests/                     pytest unit tests
reports/                   data quality report (regenerated on every run)
docs/                      design notes
```
