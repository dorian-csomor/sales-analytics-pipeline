"""
Create the Vireo Wholesale source database and load the generated CSV files.

Steps:
  1. creates the database named in .env (PGDATABASE) if it doesn't exist
  2. (re)creates the `ops` schema from database/source/01_create_source_schema.sql
  3. bulk-loads every CSV in data/source_csv/ with PostgreSQL COPY
  4. prints row counts so you can check the load

Usage:
    python scripts/setup_source_db.py
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
DDL_FILE = ROOT / "database" / "source" / "01_create_source_schema.sql"
CSV_DIR = ROOT / "data" / "source_csv"

# load order (reference tables first)
TABLES = ["sales_reps", "customers", "products", "product_cost_history",
          "fx_rates", "orders", "order_lines", "returns"]


def connection_params() -> dict:
    load_dotenv(ROOT / ".env")
    return dict(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD"),
    )


def ensure_database(params: dict, dbname: str) -> None:
    with psycopg.connect(**params, dbname="postgres", autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
            print(f"Created database '{dbname}'")


def load_csv(conn: psycopg.Connection, table: str) -> None:
    path = CSV_DIR / f"{table}.csv"
    with open(path, encoding="utf-8", newline="") as f:
        columns = next(csv.reader([f.readline()]))
        copy_sql = sql.SQL("COPY ops.{} ({}) FROM STDIN WITH (FORMAT csv)").format(
            sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, columns)))
        with conn.cursor() as cur, cur.copy(copy_sql) as copy:
            while chunk := f.read(1 << 20):
                copy.write(chunk)


def main() -> None:
    if not (CSV_DIR / "orders.csv").exists():
        raise SystemExit("No CSV files found. Run `python scripts/generate_source_data.py` first.")

    params = connection_params()
    dbname = os.getenv("PGDATABASE", "vireo")
    ensure_database(params, dbname)

    with psycopg.connect(**params, dbname=dbname) as conn:
        print("Creating schema 'ops' ...")
        conn.execute(DDL_FILE.read_text(encoding="utf-8"))
        for table in TABLES:
            load_csv(conn, table)
        conn.commit()

        print("\nLoaded tables:")
        for table in TABLES:
            n = conn.execute(sql.SQL("SELECT COUNT(*) FROM ops.{}").format(sql.Identifier(table))).fetchone()[0]
            print(f"  ops.{table:<22} {n:>8,} rows")
    print("\nSource database is ready.")


if __name__ == "__main__":
    main()
