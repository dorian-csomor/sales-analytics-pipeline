"""
End-to-end test of the transform step on a tiny, hand-made source dataset.
Each row is built to trigger one specific cleansing rule.
"""

import pandas as pd
import pytest

from etl.config import Settings
from etl.quality import DataQualityLog
from etl.transform import transform
from etl.validate import validate


@pytest.fixture
def raw():
    reps = pd.DataFrame([dict(rep_id=101, first_name="Anna", last_name="Kovács", email="anna@x.example",
                              territory="Hungary", hire_date="2016-03-01", termination_date=None)])
    customers = pd.DataFrame([
        dict(customer_id=1, customer_name="  Apex Media Kft. ", segment="SMB", city="Budapest", country="HU",
             assigned_rep_id=101, created_at="2020-01-01"),
        dict(customer_id=2, customer_name="APEX MEDIA KFT", segment="SMB", city="Budapest", country="Hungary",
             assigned_rep_id=101, created_at="2024-01-01"),                                  # duplicate of 1
        dict(customer_id=3, customer_name="TEST CUSTOMER - DO NOT USE", segment="SMB", city="Budapest",
             country="Hungary", assigned_rep_id=101, created_at="2024-01-01"),               # test account
    ])
    products = pd.DataFrame([
        dict(product_id=1001, sku="PP-001", product_name="A4 Paper", category="Paper & Printing",
             supplier="PaperMill Europa", list_price_eur=5.0, is_active=True, has_cost_history=True),
        dict(product_id=1002, sku="pp-001 ", product_name="A4 PAPER", category="Paper & Printing",
             supplier="PaperMill Europa", list_price_eur=5.0, is_active=True, has_cost_history=False),
    ])
    cost = pd.DataFrame([dict(product_id=1001, valid_from="2023-01-01", valid_to=None, unit_cost_eur=4.0)])
    fx = pd.DataFrame([dict(rate_month="2025-03-01", currency="HUF", units_per_eur=400.0),
                       dict(rate_month="2025-03-01", currency="EUR", units_per_eur=1.0)])
    orders = pd.DataFrame([
        dict(order_id=1, order_number="SO-1", customer_id=1, rep_id=101, order_date_raw="2025.03.14.",
             ship_date_raw="2025-03-17", status="DELIVERED", currency="Ft", sales_channel="Phone/Email",
             created_at="2025-03-14 10:00:00"),
        dict(order_id=2, order_number="SO-1", customer_id=1, rep_id=101, order_date_raw="2025.03.14.",
             ship_date_raw="2025-03-17", status="Delivered", currency="HUF", sales_channel="Web Shop",
             created_at="2025-03-14 10:00:20"),                                              # double submit
        dict(order_id=3, order_number="SO-3", customer_id=2, rep_id=101, order_date_raw="2052-03-20",
             ship_date_raw=None, status="Delivered", currency="EUR", sales_channel="Sales Rep",
             created_at="2025-03-20 09:00:00"),                            # typo year + mislabelled currency
        dict(order_id=4, order_number="SO-4", customer_id=3, rep_id=101, order_date_raw="2025-03-21",
             ship_date_raw=None, status="Open", currency="HUF", sales_channel="Web Shop",
             created_at="2025-03-21 09:00:00"),                                              # test customer
    ])
    lines = pd.DataFrame([
        dict(order_line_id=1, order_id=1, product_id=1001, quantity=10, unit_price=2000, discount_pct=10),
        dict(order_line_id=2, order_id=2, product_id=1001, quantity=10, unit_price=2000, discount_pct=0.1),
        dict(order_line_id=3, order_id=3, product_id=1002, quantity=5, unit_price=2000, discount_pct=0),
        dict(order_line_id=4, order_id=3, product_id=1001, quantity=-1, unit_price=2000, discount_pct=0),
        dict(order_line_id=5, order_id=4, product_id=1001, quantity=1, unit_price=2000, discount_pct=0),
    ])
    returns = pd.DataFrame([dict(return_id=1, order_id=1, product_id=1001, return_date="2025-03-25",
                                 quantity=50, reason="Defective")])
    return dict(sales_reps=reps, customers=customers, products=products, product_cost_history=cost,
                fx_rates=fx, orders=orders, order_lines=lines, returns=returns)


@pytest.fixture
def result(raw):
    dq = DataQualityLog("test")
    tables = transform(raw, dq, Settings())
    findings = {e["check_id"]: e["rows_affected"] for e in dq.entries}
    return tables, findings


def test_output_passes_validation(result):
    tables, _ = result
    validate(tables)


def test_duplicates_and_test_data_are_removed(result):
    tables, findings = result
    fs = tables["fact_sales"]
    assert sorted(fs["order_line_id"]) == [1, 3]          # 2 = duplicate order, 4 = bad qty, 5 = test
    assert findings["O02"] == 1 and findings["O01"] == 1 and findings["L01"] == 1
    assert set(fs["customer_key"]) == {1}                  # customer 2 merged into 1
    assert set(fs["product_key"]) == {1001}                # product 1002 merged into 1001


def test_dates_currency_and_discounts_are_fixed(result):
    tables, findings = result
    fs = tables["fact_sales"].set_index("order_line_id")
    assert fs.loc[3, "order_date_key"] == 20250320        # 2052 replaced by entry date
    assert fs.loc[1, "order_currency"] == "HUF"           # 'Ft'
    assert fs.loc[3, "order_currency"] == "HUF"           # EUR label with HUF prices
    assert fs.loc[1, "discount_pct"] == 0.1               # 10 -> 0.10
    assert fs.loc[1, "net_sales_eur"] == 45.0             # 10 x 2000 HUF / 400 x 0.9
    assert fs.loc[1, "cost_eur"] == 40.0
    assert findings["L04"] == 1


def test_return_quantity_capped(result):
    tables, findings = result
    fr = tables["fact_returns"]
    assert fr.loc[0, "quantity_returned"] == 10
    assert fr.loc[0, "return_value_eur"] == 45.0
    assert findings["R02"] == 1


def test_dimensions_have_unknown_member(result):
    tables, _ = result
    for dim, key in [("dim_customer", "customer_key"), ("dim_product", "product_key"),
                     ("dim_sales_rep", "rep_key")]:
        assert -1 in set(tables[dim][key])
    cust = tables["dim_customer"].set_index("customer_key")
    assert cust.loc[1, "customer_name"] == "Apex Media Kft."
    assert cust.loc[1, "country"] == "Hungary"
    assert cust.loc[1, "merged_source_ids"] == "2"
