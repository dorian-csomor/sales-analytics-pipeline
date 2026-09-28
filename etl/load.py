"""
Load layer: full refresh of the analytics schema in a single transaction.
If anything fails, the previous version of the star schema stays untouched.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

import pandas as pd
from sqlalchemy.engine import Connection, Engine

from .config import Settings

log = logging.getLogger(__name__)

LOAD_ORDER = ["dim_date", "dim_customer", "dim_product", "dim_sales_rep", "fact_sales", "fact_returns"]


def split_sql(script: str) -> list[str]:
    """Split a DDL script into statements (strips -- comments first)."""
    no_comments = re.sub(r"--[^\n]*", "", script)
    return [s.strip() for s in no_comments.split(";") if s.strip()]


def run_script(conn: Connection, path: Path) -> None:
    for statement in split_sql(path.read_text(encoding="utf-8")):
        conn.exec_driver_sql(statement)


def load_star_schema(engine: Engine, tables: dict[str, pd.DataFrame], cfg: Settings) -> None:
    with engine.begin() as conn:
        run_script(conn, cfg.analytics_ddl)
        for name in LOAD_ORDER:
            t0 = time.perf_counter()
            tables[name].to_sql(name, conn, schema="analytics", if_exists="append", index=False,
                                method="multi", chunksize=2000)
            log.info("Loaded analytics.%-15s %8d rows (%.1fs)", name, len(tables[name]), time.perf_counter() - t0)


def load_run_metadata(engine: Engine, cfg: Settings, dq_log: pd.DataFrame, run: dict) -> None:
    with engine.begin() as conn:
        run_script(conn, cfg.etl_metadata_ddl)
        dq_log.to_sql("data_quality_log", conn, schema="etl", if_exists="append", index=False)
        pd.DataFrame([run]).to_sql("pipeline_runs", conn, schema="etl", if_exists="append", index=False)


def export_csv(tables: dict[str, pd.DataFrame], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(folder / f"{name}.csv", index=False, encoding="utf-8")
    log.info("Star schema exported as CSV to %s", folder)
