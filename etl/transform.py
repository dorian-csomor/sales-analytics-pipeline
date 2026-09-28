"""
Transformation layer: raw source tables in, clean star schema out.

Every cleansing rule
  * is explicit (no silent fixes),
  * records what it found in the data quality log (check ids C.., P.., O.., L.., R..),
  * keeps rows whenever a sensible fix exists, and only excludes rows that
    must not be reported (test accounts, duplicates, invalid quantities).
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .cleaning import (build_date_dimension, clean_text, compile_pattern, fix_percentage_scale,
                       map_with_aliases, match_key, parse_mixed_dates, sku_key,
                       title_case_if_shouting, to_date_key)
from .config import Settings
from .quality import DataQualityLog
from .reference import COUNTRIES, COUNTRY_ALIASES, CURRENCY_ALIASES, ORDER_DATE_FORMATS, STATUS_ALIASES

log = logging.getLogger(__name__)
UNKNOWN = -1

# -----------------------------------------------------------------------------
# 0. Explicit data types (never trust what the driver guesses)
# -----------------------------------------------------------------------------
SOURCE_TYPES = {
    "sales_reps": {"rep_id": "int", "hire_date": "date", "termination_date": "date"},
    "customers": {"customer_id": "int", "assigned_rep_id": "int", "created_at": "date"},
    "products": {"product_id": "int", "list_price_eur": "float", "is_active": "bool",
                 "has_cost_history": "bool"},
    "product_cost_history": {"product_id": "int", "valid_from": "date", "valid_to": "date",
                             "unit_cost_eur": "float"},
    "fx_rates": {"rate_month": "date", "units_per_eur": "float"},
    "orders": {"order_id": "int", "customer_id": "int", "rep_id": "int", "created_at": "date"},
    "order_lines": {"order_line_id": "int", "order_id": "int", "product_id": "int",
                    "quantity": "float", "unit_price": "float", "discount_pct": "float"},
    "returns": {"return_id": "int", "order_id": "int", "product_id": "int", "return_date": "date",
                "quantity": "int"},
}


def standardize_types(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    out = {}
    for table, df in raw.items():
        df = df.copy()
        for col, kind in SOURCE_TYPES.get(table, {}).items():
            if kind == "int":
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
            elif kind == "float":
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
            elif kind == "date":
                df[col] = pd.to_datetime(df[col], errors="coerce").astype("datetime64[ns]")
            elif kind == "bool":
                df[col] = df[col].astype("string").str.lower().isin(["true", "t", "1"])
        out[table] = df
    return out


# -----------------------------------------------------------------------------
# 1. Customers
# -----------------------------------------------------------------------------
def clean_customers(c: pd.DataFrame, dq: DataQualityLog, cfg: Settings):
    c = c.copy()
    original = c["customer_name"].astype("string")
    c["customer_name"] = title_case_if_shouting(c["customer_name"])
    changed = (original != c["customer_name"]).fillna(True)
    dq.record("C01", "customers", "Customer name with extra spaces or typed in capitals",
              changed, "Trimmed, all-caps names converted to title case")

    pattern = compile_pattern(cfg.test_customer_pattern)
    is_test = c["customer_name"].str.contains(pattern, na=False)
    test_ids = set(c.loc[is_test, "customer_id"].astype(int))
    dq.record("C02", "customers", "Test / demo accounts", is_test, "Excluded, together with their orders")
    c = c[~is_test].copy()

    raw_country = clean_text(c["country"])
    canonical = map_with_aliases(c["country"], COUNTRY_ALIASES)
    nonstandard = raw_country.notna() & canonical.notna() & (raw_country != canonical)
    dq.record("C03", "customers", "Country spelled in a non-standard way (e.g. 'HU', 'Österreich')",
              nonstandard.fillna(False), "Mapped to standard country name")

    city_to_country = (pd.DataFrame({"city": c["city"], "country": canonical}).dropna()
                       .groupby("city")["country"].agg(lambda s: s.mode().iloc[0]))
    missing = canonical.isna()
    canonical = canonical.fillna(c["city"].map(city_to_country).astype("string"))
    still_missing = canonical.isna()
    dq.record("C04", "customers", "Country missing or unrecognised", missing,
              f"Inferred from city; {int(still_missing.sum())} left as 'Unknown'")
    c["country"] = canonical.fillna("Unknown")

    # duplicates: same normalised name + city -> keep the oldest record
    c["_key"] = match_key(c["customer_name"]) + "|" + match_key(c["city"]).fillna("")
    c = c.sort_values(["created_at", "customer_id"])
    c["canonical_id"] = c.groupby("_key")["customer_id"].transform("first")
    is_dup = c["customer_id"] != c["canonical_id"]
    dq.record("C05", "customers", "Duplicate customer records (same company, name spelled differently)",
              is_dup, "Merged into the oldest record; orders re-pointed")
    id_map = dict(zip(c["customer_id"].astype(int), c["canonical_id"].astype(int)))
    merged = (c[is_dup].groupby("canonical_id")["customer_id"]
              .agg(lambda s: ",".join(str(int(x)) for x in sorted(s))))
    customers = c[~is_dup].drop(columns=["_key", "canonical_id"]).copy()
    customers["merged_source_ids"] = customers["customer_id"].map(merged)
    return customers, id_map, test_ids


# -----------------------------------------------------------------------------
# 2. Products
# -----------------------------------------------------------------------------
def clean_products(p: pd.DataFrame, dq: DataQualityLog):
    p = p.copy()
    p["_sku_key"] = sku_key(p["sku"])
    # prefer the record that has a cost history, then the oldest id
    p = p.sort_values(["has_cost_history", "product_id"], ascending=[False, True])
    p["canonical_id"] = p.groupby("_sku_key")["product_id"].transform("first")
    is_dup = p["product_id"] != p["canonical_id"]
    dq.record("P01", "products", "Duplicate products from ERP migration (same SKU, different spelling)",
              is_dup, "Merged into the original product; order lines re-pointed")
    id_map = dict(zip(p["product_id"].astype(int), p["canonical_id"].astype(int)))
    merged = (p[is_dup].groupby("canonical_id")["product_id"]
              .agg(lambda s: ",".join(str(int(x)) for x in sorted(s))))

    products = p[~is_dup].copy()
    products["sku"] = products["sku"].astype("string").str.strip().str.upper()
    products["product_name"] = title_case_if_shouting(products["product_name"])
    products["merged_source_ids"] = products["product_id"].map(merged)
    dq.record("P02", "products", "Products without any cost history", ~products["has_cost_history"],
              "Kept; margin for these products will be overstated")
    return products.drop(columns=["_sku_key", "canonical_id"]), id_map


# -----------------------------------------------------------------------------
# 3. Orders (header level)
# -----------------------------------------------------------------------------
def clean_orders(o: pd.DataFrame, customers: pd.DataFrame, reps: pd.DataFrame, customer_map: dict,
                 test_ids: set, dq: DataQualityLog, cfg: Settings) -> pd.DataFrame:
    o = o.copy()

    is_test = o["customer_id"].isin(test_ids)
    dq.record("O01", "orders", "Orders from test / demo accounts", is_test, "Excluded")
    o = o[~is_test]

    o = o.sort_values(["created_at", "order_id"])
    is_dup = o.duplicated("order_number", keep="first")
    dq.record("O02", "orders", "Duplicate orders (same order number submitted twice)", is_dup,
              "Kept the first submission, dropped the copies and their lines")
    o = o[~is_dup].copy()

    # --- dates ----------------------------------------------------------------
    o["order_date"] = parse_mixed_dates(o["order_date_raw"], ORDER_DATE_FORMATS).dt.normalize()
    non_iso = ~o["order_date_raw"].astype("string").str.match(r"^\d{4}-\d{2}-\d{2}", na=False)
    dq.record("O03", "orders", "Order date stored as text in non-ISO formats (e.g. '14.03.2025')",
              non_iso & o["order_date"].notna(), f"Parsed with {len(ORDER_DATE_FORMATS)} explicit formats")
    unparsed = o["order_date"].isna()
    entry_date = o["created_at"].dt.normalize()
    implausible = o["order_date"].notna() & (
        (o["order_date"].dt.year < cfg.earliest_valid_year) | (o["order_date"] > entry_date))
    dq.record("O04", "orders", "Order date unreadable or impossible (e.g. year 2052, after entry date)",
              unparsed | implausible, "Replaced with the system entry date")
    o.loc[unparsed | implausible, "order_date"] = entry_date[unparsed | implausible]
    o["ship_date"] = pd.to_datetime(o["ship_date_raw"], format="%Y-%m-%d", errors="coerce")

    # --- status ---------------------------------------------------------------
    raw_status = o["status"].astype("string")
    o["order_status"] = map_with_aliases(o["status"], STATUS_ALIASES)
    dq.record("O05", "orders", "Status spelled inconsistently (e.g. 'DELIVERED', 'Canceled')",
              (raw_status != o["order_status"]).fillna(True), "Standardised")
    unknown_status = o["order_status"].isna()
    if unknown_status.any():
        dq.record("O05b", "orders", "Unknown status value", unknown_status, "Set to 'Unknown'")
        o["order_status"] = o["order_status"].fillna("Unknown")
    dq.record("O06", "orders", "Delivered orders without a ship date",
              (o["order_status"] == "Delivered") & o["ship_date"].isna(), "Kept; ship date left empty")

    # --- customer & rep references -------------------------------------------
    o["customer_id"] = o["customer_id"].map(lambda x: customer_map.get(int(x), int(x)) if pd.notna(x) else x)
    orphan = ~o["customer_id"].isin(customers["customer_id"])
    dq.record("O07", "orders", "Orders whose customer doesn't exist in the customer master", orphan,
              "Kept, assigned to 'Unknown customer'")
    o["customer_key"] = o["customer_id"].where(~orphan, UNKNOWN).astype(int)
    bad_rep = ~o["rep_id"].isin(reps["rep_id"])
    dq.record("O08", "orders", "Orders with a missing or unknown sales rep", bad_rep,
              "Assigned to 'Unknown rep'")
    o["rep_key"] = o["rep_id"].where(~bad_rep, UNKNOWN).astype(int)

    # --- currency -------------------------------------------------------------
    home_currency = (customers.set_index("customer_id")["country"]
                     .map(lambda c: COUNTRIES.get(c, {}).get("currency")))
    raw_cur = clean_text(o["currency"])
    cur = raw_cur.str.upper().map(CURRENCY_ALIASES).astype("string")
    dq.record("O09", "orders", "Currency code non-standard (e.g. 'huf', 'Ft')",
              (raw_cur.notna() & cur.notna() & (raw_cur != cur)).fillna(False), "Standardised to ISO code")
    missing = cur.isna()
    cur = cur.fillna(o["customer_key"].map(home_currency).astype("string"))
    dq.record("O10", "orders", "Currency missing", missing,
              "Derived from the customer's country; " f"{int(cur.isna().sum())} defaulted to EUR")
    o["order_currency"] = cur.fillna(cfg.reporting_currency)
    o["home_currency"] = o["customer_key"].map(home_currency)
    return o


# -----------------------------------------------------------------------------
# 4. Order lines -> fact_sales
# -----------------------------------------------------------------------------
def build_fact_sales(lines: pd.DataFrame, orders: pd.DataFrame, products: pd.DataFrame,
                     product_map: dict, cost: pd.DataFrame, fx: pd.DataFrame,
                     dq: DataQualityLog, cfg: Settings) -> pd.DataFrame:
    l = lines[lines["order_id"].isin(orders["order_id"])].copy()
    l["product_id"] = l["product_id"].map(lambda x: product_map.get(int(x), int(x)))

    bad_qty = ~(l["quantity"] > 0)
    dq.record("L01", "order_lines", "Zero, negative or missing quantity", bad_qty, "Excluded")
    l = l[~bad_qty].copy()
    l["quantity"] = l["quantity"].astype(int)

    l["discount_pct"], fixed = fix_percentage_scale(l["discount_pct"])
    dq.record("L02", "order_lines", "Discount stored as whole percentage (10 instead of 0.10)", fixed,
              "Divided by 100")
    bad_disc = l["discount_pct"].isna() | (l["discount_pct"] < 0) | (l["discount_pct"] > 0.9)
    dq.record("L03", "order_lines", "Discount missing or outside 0-90%", bad_disc, "Set to 0")
    l.loc[bad_disc, "discount_pct"] = 0.0

    l = l.merge(orders[["order_id", "order_number", "order_date", "ship_date", "customer_key", "rep_key",
                        "sales_channel", "order_status", "order_currency", "home_currency"]],
                on="order_id", how="inner")
    l = l.merge(products[["product_id", "list_price_eur"]], on="product_id", how="left")

    # --- currency mislabels: EUR orders priced like HUF orders -----------------
    ratio = l["unit_price"] / l["list_price_eur"]
    order_ratio = ratio.groupby(l["order_id"]).transform("median")
    mislabel = ((l["order_currency"] == "EUR") & (order_ratio > cfg.currency_mislabel_ratio)
                & l["home_currency"].notna() & (l["home_currency"] != "EUR"))
    dq.record("L04", "orders", "EUR orders with prices ~400x list price (amounts really in local currency)",
              l.loc[mislabel, "order_id"].nunique(), "Currency corrected to the customer's home currency")
    l.loc[mislabel, "order_currency"] = l.loc[mislabel, "home_currency"]

    # --- missing prices -------------------------------------------------------
    l["order_month"] = l["order_date"].dt.to_period("M").dt.to_timestamp()
    no_price = l["unit_price"].isna()
    by_month = l.groupby(["product_id", "order_currency", "order_month"])["unit_price"].transform("median")
    by_product = l.groupby(["product_id", "order_currency"])["unit_price"].transform("median")
    l["unit_price"] = l["unit_price"].fillna(by_month).fillna(by_product)
    still_missing = l["unit_price"].isna()
    dq.record("L05", "order_lines", "Missing unit price", no_price,
              f"Imputed from the median price of the same product, currency and month; "
              f"{int(still_missing.sum())} could not be imputed and were excluded")
    l["is_price_imputed"] = no_price
    l = l[~still_missing].copy()

    # --- exchange rates -------------------------------------------------------
    fx = fx.rename(columns={"rate_month": "order_month", "currency": "order_currency"})
    l = l.merge(fx[["order_month", "order_currency", "units_per_eur"]], on=["order_month", "order_currency"],
                how="left")
    no_fx = l["units_per_eur"].isna()
    dq.record("L06", "order_lines", "No exchange rate for order month and currency", no_fx, "Excluded")
    l = l[~no_fx].copy()

    # --- purchase cost valid on the order date (as-of join) --------------------
    cost = cost.assign(product_id=cost["product_id"].astype("int64"),
                       valid_from=cost["valid_from"].astype("datetime64[ns]")).sort_values("valid_from")
    l["product_id"] = l["product_id"].astype("int64")
    l["order_date"] = l["order_date"].astype("datetime64[ns]")
    l = pd.merge_asof(l.sort_values("order_date"), cost[["product_id", "valid_from", "unit_cost_eur"]],
                      left_on="order_date", right_on="valid_from", by="product_id", direction="backward")
    no_cost = l["unit_cost_eur"].isna()
    dq.record("L07", "order_lines", "No purchase cost valid on the order date", no_cost,
              "Cost set to 0 (margin overstated)")
    l["unit_cost_eur"] = l["unit_cost_eur"].fillna(0.0)

    # --- amounts in EUR -------------------------------------------------------
    l["gross_sales_eur"] = l["quantity"] * l["unit_price"] / l["units_per_eur"]
    l["discount_eur"] = l["gross_sales_eur"] * l["discount_pct"]
    l["net_sales_eur"] = l["gross_sales_eur"] - l["discount_eur"]
    l["cost_eur"] = l["quantity"] * l["unit_cost_eur"]
    l["gross_margin_eur"] = l["net_sales_eur"] - l["cost_eur"]

    cancelled = l["order_status"] == "Cancelled"
    dq.record("L08", "order_lines", "Lines on cancelled orders", cancelled,
              "Excluded from sales (not revenue)")
    l = l[~cancelled]

    fact = pd.DataFrame({
        "order_line_id": l["order_line_id"].astype(int),
        "order_id": l["order_id"].astype(int),
        "order_number": l["order_number"],
        "order_date_key": to_date_key(l["order_date"]),
        "ship_date_key": to_date_key(l["ship_date"]),
        "customer_key": l["customer_key"].astype(int),
        "product_key": l["product_id"].astype(int),
        "rep_key": l["rep_key"].astype(int),
        "sales_channel": l["sales_channel"],
        "order_status": l["order_status"],
        "order_currency": l["order_currency"],
        "quantity": l["quantity"],
        "unit_price_local": l["unit_price"].round(2),
        "discount_pct": l["discount_pct"].round(4),
        "fx_rate": l["units_per_eur"].round(4),
        "gross_sales_eur": l["gross_sales_eur"].round(2),
        "discount_eur": l["discount_eur"].round(2),
        "net_sales_eur": l["net_sales_eur"].round(2),
        "cost_eur": l["cost_eur"].round(2),
        "gross_margin_eur": l["gross_margin_eur"].round(2),
        "is_price_imputed": l["is_price_imputed"].astype(bool),
    })
    return fact.sort_values("order_line_id").reset_index(drop=True)


# -----------------------------------------------------------------------------
# 5. Returns -> fact_returns
# -----------------------------------------------------------------------------
def build_fact_returns(returns: pd.DataFrame, fact_sales: pd.DataFrame, product_map: dict,
                       dq: DataQualityLog) -> pd.DataFrame:
    r = returns.copy()
    r["product_key"] = r["product_id"].map(lambda x: product_map.get(int(x), int(x)))
    sold = (fact_sales.drop_duplicates(["order_id", "product_key"])
            [["order_id", "product_key", "order_line_id", "customer_key", "rep_key", "quantity",
              "net_sales_eur", "order_date_key"]])
    r = r.merge(sold, on=["order_id", "product_key"], how="left")

    unmatched = r["order_line_id"].isna()
    dq.record("R01", "returns", "Returns that don't match a valid sales line", unmatched, "Excluded")
    r = r[~unmatched].copy()

    too_many = r["quantity_x"] > r["quantity_y"]
    dq.record("R02", "returns", "Returned quantity larger than quantity sold", too_many,
              "Capped at quantity sold")
    r["quantity_returned"] = np.minimum(r["quantity_x"], r["quantity_y"]).astype(int)

    before_sale = to_date_key(r["return_date"]) < r["order_date_key"]
    dq.record("R03", "returns", "Return dated before the order", before_sale, "Kept, flagged in log only")

    fact = pd.DataFrame({
        "return_id": r["return_id"].astype(int),
        "return_date_key": to_date_key(r["return_date"]),
        "order_id": r["order_id"].astype(int),
        "order_line_id": r["order_line_id"].astype(int),
        "customer_key": r["customer_key"].astype(int),
        "product_key": r["product_key"].astype(int),
        "rep_key": r["rep_key"].astype(int),
        "quantity_returned": r["quantity_returned"],
        "return_value_eur": (r["quantity_returned"] * r["net_sales_eur"] / r["quantity_y"]).round(2),
        "return_reason": clean_text(r["reason"]),
    })
    return fact.sort_values("return_id").reset_index(drop=True)


# -----------------------------------------------------------------------------
# 6. Dimensions
# -----------------------------------------------------------------------------
def build_dim_sales_rep(reps: pd.DataFrame) -> pd.DataFrame:
    dim = pd.DataFrame({
        "rep_key": reps["rep_id"].astype(int),
        "rep_name": clean_text(reps["first_name"]) + " " + clean_text(reps["last_name"]),
        "territory": clean_text(reps["territory"]),
        "email": clean_text(reps["email"]).str.lower(),
        "hire_date": reps["hire_date"].dt.date,
        "termination_date": reps["termination_date"].dt.date,
        "is_active": reps["termination_date"].isna(),
    })
    unknown = pd.DataFrame([dict(rep_key=UNKNOWN, rep_name="Unknown rep", territory="Unknown", email=None,
                                 hire_date=None, termination_date=None, is_active=False)])
    return pd.concat([unknown, dim], ignore_index=True)


def build_dim_customer(customers: pd.DataFrame, fact_sales: pd.DataFrame, dim_rep: pd.DataFrame,
                       cfg: Settings) -> pd.DataFrame:
    dates = pd.to_datetime(fact_sales["order_date_key"].astype(str), format="%Y%m%d")
    stats = dates.groupby(fact_sales["customer_key"]).agg(["min", "max"])
    data_end = dates.max()
    rep_names = dim_rep.set_index("rep_key")["rep_name"]

    dim = pd.DataFrame({
        "customer_key": customers["customer_id"].astype(int),
        "customer_name": customers["customer_name"],
        "segment": clean_text(customers["segment"]).fillna("Unknown"),
        "city": clean_text(customers["city"]),
        "country": customers["country"],
        "country_code": customers["country"].map(lambda c: COUNTRIES.get(c, {}).get("code")),
        "account_owner": customers["assigned_rep_id"].map(rep_names),
        "customer_since": customers["created_at"].dt.date,
        "merged_source_ids": customers["merged_source_ids"],
    })
    dim["first_order_date"] = dim["customer_key"].map(stats["min"])
    dim["last_order_date"] = dim["customer_key"].map(stats["max"])
    dim["cohort_year"] = dim["first_order_date"].dt.year.astype("Int64")
    days_since = (data_end - dim["last_order_date"]).dt.days
    dim["customer_status"] = np.select(
        [dim["last_order_date"].isna(), days_since > cfg.lapsed_after_days], ["No orders", "Lapsed"], "Active")
    dim["first_order_date"] = dim["first_order_date"].dt.date
    dim["last_order_date"] = dim["last_order_date"].dt.date

    unknown = pd.DataFrame([dict(customer_key=UNKNOWN, customer_name="Unknown customer", segment="Unknown",
                                 city=None, country="Unknown", country_code=None, account_owner=None,
                                 customer_since=None, first_order_date=None, last_order_date=None,
                                 cohort_year=pd.NA, customer_status="Unknown", merged_source_ids=None)])
    cols = ["customer_key", "customer_name", "segment", "city", "country", "country_code", "account_owner",
            "customer_since", "first_order_date", "last_order_date", "cohort_year", "customer_status",
            "merged_source_ids"]
    return pd.concat([unknown, dim[cols]], ignore_index=True)[cols]


def build_dim_product(products: pd.DataFrame) -> pd.DataFrame:
    dim = pd.DataFrame({
        "product_key": products["product_id"].astype(int),
        "sku": products["sku"],
        "product_name": products["product_name"],
        "category": clean_text(products["category"]),
        "supplier": clean_text(products["supplier"]),
        "list_price_eur": products["list_price_eur"].round(2),
        "is_active": products["is_active"],
        "merged_source_ids": products["merged_source_ids"],
    })
    unknown = pd.DataFrame([dict(product_key=UNKNOWN, sku="UNKNOWN", product_name="Unknown product",
                                 category="Unknown", supplier="Unknown", list_price_eur=None,
                                 is_active=False, merged_source_ids=None)])
    return pd.concat([unknown, dim], ignore_index=True).sort_values("product_key").reset_index(drop=True)


# -----------------------------------------------------------------------------
# Orchestration
# -----------------------------------------------------------------------------
def transform(raw: dict[str, pd.DataFrame], dq: DataQualityLog, cfg: Settings) -> dict[str, pd.DataFrame]:
    src = standardize_types(raw)

    customers, customer_map, test_ids = clean_customers(src["customers"], dq, cfg)
    products, product_map = clean_products(src["products"], dq)
    orders = clean_orders(src["orders"], customers, src["sales_reps"], customer_map, test_ids, dq, cfg)
    fact_sales = build_fact_sales(src["order_lines"], orders, products, product_map,
                                  src["product_cost_history"], src["fx_rates"], dq, cfg)
    fact_returns = build_fact_returns(src["returns"], fact_sales, product_map, dq)

    dim_rep = build_dim_sales_rep(src["sales_reps"])
    dim_customer = build_dim_customer(customers, fact_sales, dim_rep, cfg)
    dim_product = build_dim_product(products)

    all_keys = pd.concat([fact_sales["order_date_key"], fact_sales["ship_date_key"],
                          fact_returns["return_date_key"]]).dropna()
    first_year, last_year = int(all_keys.min()) // 10000, int(all_keys.max()) // 10000
    dim_date = build_date_dimension(f"{first_year}-01-01", f"{last_year}-12-31")

    return {
        "dim_date": dim_date,
        "dim_customer": dim_customer,
        "dim_product": dim_product,
        "dim_sales_rep": dim_rep,
        "fact_sales": fact_sales,
        "fact_returns": fact_returns,
    }
