# Sales Analytics Pipeline: from operational database to management report

End-to-end analytics project for **Vireo Wholesale**, a fictional B2B distributor of office and
facility supplies selling in five Central European countries (4 currencies, 2023–2026).

![Executive overview](docs/screenshots/01_executive_overview.png)

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

## Key findings

The report answers one management question: **why did growth stall in 2025, and where should we act?**

| Finding | Evidence |
|---|---|
| **Growth stalled** | Net sales +15% in 2024, only +1% in 2025 (€14.2M) |
| **Romania lost ground after an account handover** | Romanian net sales −25% in 2025 after the key account manager left in March; active customers fell from 53 (2024) to 33 (2026, Jan–Aug) |
| **Tech Accessories: growth without profit** | Fastest-growing category (+12% in 2025), but gross margin fell from 31% to 15% after supplier price rises that weren't passed on |
| **A supplier quality problem** | Aurora Hygiene products are returned on 6.9% of order lines, 2–6x more than other suppliers; 3 out of 4 of its returns are defects |
| **Newer customers churn faster** | Two years after their first order, 62% of the 2024 cohort still buy vs 78% of the 2023 cohort; SMB retention (~82%) trails Enterprise and Mid-Market (90%+) |

## Highlights

**Data engineering**

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

**Power BI**

- 5-page management report on the star schema (Import mode, single-direction relationships, marked date table)
- **25+ DAX measures** in display folders: time intelligence with fair year-over-year comparison for the
  partial year 2026, gross margin in percentage points, customer retention, new and lapsed customers,
  cohort retention, line-based return rates
- **Cohort analysis**: share of each customer cohort still buying in later years
- **Data quality page** fed by the pipeline's own log, refreshed with every run
- Custom dark theme and icon navigation (in [`powerbi/`](powerbi/))

## Report pages

| Page | What it shows |
|---|---|
| **Executive overview** | KPIs, monthly sales vs prior year, growth by country and category, key findings |
| **Sales team & regions** | Net sales and growth by territory and rep; the Romania handover and its customer impact |
| **Products & margin** | Margin trend by category, gross margin by category, supplier return rates, top products |
| **Customers & retention** | Active, new and lapsed customers, retention by segment, cohort matrix, customer status |
| **Data quality** | Latest pipeline run and every data quality issue found and handled |

<details>
<summary><b>Screenshots</b></summary>

### Sales team & regions
![Sales team & regions](docs/screenshots/02_sales_team_regions.png)

### Products & margin
![Products & margin](docs/screenshots/03_products_margin.png)

### Customers & retention
![Customers & retention](docs/screenshots/04_customers_retention.png)

### Data quality
![Data quality](docs/screenshots/05_data_quality.png)

</details>

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

Requirements: Python 3.11+, PostgreSQL 14+, Power BI Desktop (for the report).

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

**5. Open the report:** open `powerbi/vireo_sales_report.pbix` in Power BI Desktop. It connects to the
`vireo` database on `localhost`. Enter your PostgreSQL credentials when asked, then click **Refresh**.

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
powerbi/
  vireo_sales_report.pbix  the Power BI report
  vireo_dark_theme.json    report theme
  icons/                   navigation icons
scripts/                   data generator and source database setup
tests/                     pytest unit tests
reports/                   data quality report (regenerated on every run)
docs/
  source_data_design.md    how the simulated source data was designed
  screenshots/             report screenshots
```
