"""Pipeline settings. Connection details come from the .env file (never hard-coded)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    # database
    host: str = os.getenv("PGHOST", "localhost")
    port: str = os.getenv("PGPORT", "5432")
    database: str = os.getenv("PGDATABASE", "vireo")
    user: str = os.getenv("PGUSER", "postgres")
    password: str = os.getenv("PGPASSWORD", "")

    # folders
    extract_sql_dir: Path = ROOT / "database" / "extract"
    analytics_ddl: Path = ROOT / "database" / "analytics" / "01_create_analytics_schema.sql"
    etl_metadata_ddl: Path = ROOT / "database" / "analytics" / "02_create_etl_metadata.sql"
    log_dir: Path = ROOT / "logs"
    report_dir: Path = ROOT / "reports"

    # business rules
    reporting_currency: str = "EUR"
    earliest_valid_year: int = 2015
    lapsed_after_days: int = 180          # customer counts as lapsed after this many days without an order
    test_customer_pattern: str = r"\b(?:test|demo|do not use)\b"
    currency_mislabel_ratio: float = 20.0  # price this many times above list price => wrong currency
    tables: tuple = field(default=("sales_reps", "customers", "products", "product_cost_history",
                                   "fx_rates", "orders", "order_lines", "returns"))

    @property
    def sqlalchemy_url(self):
        """Connection URL object (safe for passwords with special characters)."""
        from sqlalchemy.engine import URL
        return URL.create("postgresql+psycopg", username=self.user, password=self.password,
                          host=self.host, port=int(self.port), database=self.database)


settings = Settings()
