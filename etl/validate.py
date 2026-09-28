"""
Output validation: the pipeline refuses to load a star schema that breaks
basic integrity rules. Any failure stops the run before the database is touched.
"""

from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

PRIMARY_KEYS = {
    "dim_date": "date_key", "dim_customer": "customer_key", "dim_product": "product_key",
    "dim_sales_rep": "rep_key", "fact_sales": "order_line_id", "fact_returns": "return_id",
}
FOREIGN_KEYS = [
    ("fact_sales", "order_date_key", "dim_date", "date_key"),
    ("fact_sales", "ship_date_key", "dim_date", "date_key"),
    ("fact_sales", "customer_key", "dim_customer", "customer_key"),
    ("fact_sales", "product_key", "dim_product", "product_key"),
    ("fact_sales", "rep_key", "dim_sales_rep", "rep_key"),
    ("fact_returns", "return_date_key", "dim_date", "date_key"),
    ("fact_returns", "customer_key", "dim_customer", "customer_key"),
    ("fact_returns", "product_key", "dim_product", "product_key"),
    ("fact_returns", "rep_key", "dim_sales_rep", "rep_key"),
]


class ValidationError(Exception):
    pass


def validate(tables: dict[str, pd.DataFrame]) -> None:
    errors = []

    for table, key in PRIMARY_KEYS.items():
        col = tables[table][key]
        if col.isna().any():
            errors.append(f"{table}.{key} has missing values")
        if col.duplicated().any():
            errors.append(f"{table}.{key} has {int(col.duplicated().sum())} duplicate values")

    for fact, fk, dim, pk in FOREIGN_KEYS:
        values = tables[fact][fk].dropna()
        missing = ~values.isin(tables[dim][pk])
        if missing.any():
            errors.append(f"{fact}.{fk}: {int(missing.sum())} values not found in {dim}.{pk}")

    fs = tables["fact_sales"]
    if (fs["quantity"] <= 0).any():
        errors.append("fact_sales has non-positive quantities")
    if (fs["net_sales_eur"] < 0).any():
        errors.append("fact_sales has negative net sales")
    if not fs["discount_pct"].between(0, 0.9).all():
        errors.append("fact_sales has discounts outside 0-90%")
    ratio = fs["unit_price_local"] / fs["fx_rate"]
    if (ratio > 5000).any():
        errors.append("fact_sales has EUR unit prices above 5,000 (currency problem?)")

    if errors:
        for e in errors:
            log.error("Validation failed: %s", e)
        raise ValidationError(f"{len(errors)} validation check(s) failed - nothing was loaded")
    log.info("All %d validation checks passed", len(PRIMARY_KEYS) * 2 + len(FOREIGN_KEYS) + 4)
