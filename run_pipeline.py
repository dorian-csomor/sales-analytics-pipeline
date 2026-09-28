"""
Run the Vireo Wholesale ETL pipeline.

    extract (SQL)  ->  transform & cleanse (pandas)  ->  validate  ->  load (analytics star schema)

Usage:
    python run_pipeline.py                 # full run: extract, transform, validate, load
    python run_pipeline.py --dry-run       # everything except writing to the database
    python run_pipeline.py --export-csv    # also save the star schema as CSV files
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime

from sqlalchemy import create_engine

from etl.cleaning import now_run_id
from etl.config import ROOT, settings
from etl.extract import extract_all
from etl.load import export_csv, load_run_metadata, load_star_schema
from etl.quality import DataQualityLog
from etl.transform import transform
from etl.validate import validate


def setup_logging(run_id: str) -> logging.Logger:
    settings.log_dir.mkdir(exist_ok=True)
    fmt = "%(asctime)s  %(levelname)-7s  %(name)-14s  %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt, datefmt="%H:%M:%S",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(settings.log_dir / f"pipeline_{run_id}.log",
                                                      encoding="utf-8")])
    return logging.getLogger("pipeline")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="don't write to the database")
    parser.add_argument("--export-csv", action="store_true", help="also export the star schema to CSV")
    args = parser.parse_args()

    run_id = now_run_id()
    log = setup_logging(run_id)
    started = datetime.now()
    t0 = time.perf_counter()
    log.info("Pipeline run %s started", run_id)

    engine = create_engine(settings.sqlalchemy_url)
    dq = DataQualityLog(run_id)

    log.info("--- 1/4 Extract ---")
    raw = extract_all(engine, settings)

    log.info("--- 2/4 Transform ---")
    tables = transform(raw, dq, settings)

    log.info("--- 3/4 Validate ---")
    validate(tables)

    fs = tables["fact_sales"]
    summary = {
        "Source order lines": f"{len(raw['order_lines']):,}",
        "Sales lines loaded (fact_sales)": f"{len(fs):,}",
        "Returns loaded (fact_returns)": f"{len(tables['fact_returns']):,}",
        "Customers (dim_customer, excl. Unknown)": f"{len(tables['dim_customer']) - 1:,}",
        "Products (dim_product, excl. Unknown)": f"{len(tables['dim_product']) - 1:,}",
        "Net sales (EUR)": f"{fs['net_sales_eur'].sum():,.2f}",
        "Gross margin": f"{fs['gross_margin_eur'].sum() / fs['net_sales_eur'].sum():.1%}",
        "Issues logged": f"{sum(1 for e in dq.entries if e['rows_affected'])} checks with findings",
    }

    if args.export_csv:
        export_csv(tables, ROOT / "data" / "analytics_csv")

    if args.dry_run:
        log.info("--- 4/4 Load skipped (dry run) ---")
    else:
        log.info("--- 4/4 Load ---")
        load_star_schema(engine, tables, settings)

    finished = datetime.now()
    summary["Run time"] = f"{time.perf_counter() - t0:.1f} s"
    dq.write_report(settings.report_dir / "data_quality_report.md", summary)

    if not args.dry_run:
        load_run_metadata(engine, settings, dq.to_frame(), dict(
            run_id=run_id, started_at=started, finished_at=finished, status="success",
            fact_sales_rows=len(fs), fact_returns_rows=len(tables["fact_returns"]),
            net_sales_eur=round(float(fs["net_sales_eur"].sum()), 2)))

    log.info("Pipeline run %s finished in %.1fs", run_id, time.perf_counter() - t0)
    for k, v in summary.items():
        log.info("  %-42s %s", k, v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
