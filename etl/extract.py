"""Extract layer: runs the SQL files in database/extract/ against the source database."""

from __future__ import annotations

import logging
import time

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .config import Settings

log = logging.getLogger(__name__)


def read_sql_file(cfg: Settings, table: str) -> str:
    return (cfg.extract_sql_dir / f"{table}.sql").read_text(encoding="utf-8")


def extract_all(engine: Engine, cfg: Settings) -> dict[str, pd.DataFrame]:
    data = {}
    with engine.connect() as conn:
        for table in cfg.tables:
            t0 = time.perf_counter()
            data[table] = pd.read_sql(text(read_sql_file(cfg, table)), conn)
            log.info("Extracted %-22s %8d rows (%.1fs)", table, len(data[table]), time.perf_counter() - t0)
    return data
