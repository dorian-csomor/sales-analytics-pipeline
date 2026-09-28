# Data quality report

Run `20260928_151247`

## Summary

| Metric | Value |
|---|---|
| Source order lines | 61,882 |
| Sales lines loaded (fact_sales) | 59,503 |
| Returns loaded (fact_returns) | 1,150 |
| Customers (dim_customer, excl. Unknown) | 527 |
| Products (dim_product, excl. Unknown) | 88 |
| Net sales (EUR) | 50,315,278.15 |
| Gross margin | 25.0% |
| Issues logged | 21 checks with findings |
| Run time | 45.3 s |

## Checks

| # | Table | Issue | Rows | Action |
|---|---|---|---:|---|
| C01 | `customers` | Customer name with extra spaces or typed in capitals | 20 | Trimmed, all-caps names converted to title case |
| C02 | `customers` | Test / demo accounts | 2 | Excluded, together with their orders |
| C03 | `customers` | Country spelled in a non-standard way (e.g. 'HU', 'Österreich') | 75 | Mapped to standard country name |
| C04 | `customers` | Country missing or unrecognised | 10 | Inferred from city; 0 left as 'Unknown' |
| C05 | `customers` | Duplicate customer records (same company, name spelled differently) | 6 | Merged into the oldest record; orders re-pointed |
| P01 | `products` | Duplicate products from ERP migration (same SKU, different spelling) | 8 | Merged into the original product; order lines re-pointed |
| P02 | `products` | Products without any cost history | 0 | Kept; margin for these products will be overstated |
| O01 | `orders` | Orders from test / demo accounts | 40 | Excluded |
| O02 | `orders` | Duplicate orders (same order number submitted twice) | 67 | Kept the first submission, dropped the copies and their lines |
| O03 | `orders` | Order date stored as text in non-ISO formats (e.g. '14.03.2025') | 4,112 | Parsed with 5 explicit formats |
| O04 | `orders` | Order date unreadable or impossible (e.g. year 2052, after entry date) | 6 | Replaced with the system entry date |
| O05 | `orders` | Status spelled inconsistently (e.g. 'DELIVERED', 'Canceled') | 1,470 | Standardised |
| O06 | `orders` | Delivered orders without a ship date | 177 | Kept; ship date left empty |
| O07 | `orders` | Orders whose customer doesn't exist in the customer master | 10 | Kept, assigned to 'Unknown customer' |
| O08 | `orders` | Orders with a missing or unknown sales rep | 0 | Assigned to 'Unknown rep' |
| O09 | `orders` | Currency code non-standard (e.g. 'huf', 'Ft') | 422 | Standardised to ISO code |
| O10 | `orders` | Currency missing | 73 | Derived from the customer's country; 0 defaulted to EUR |
| L01 | `order_lines` | Zero, negative or missing quantity | 184 | Excluded |
| L02 | `order_lines` | Discount stored as whole percentage (10 instead of 0.10) | 556 | Divided by 100 |
| L03 | `order_lines` | Discount missing or outside 0-90% | 0 | Set to 0 |
| L04 | `orders` | EUR orders with prices ~400x list price (amounts really in local currency) | 15 | Currency corrected to the customer's home currency |
| L05 | `order_lines` | Missing unit price | 490 | Imputed from the median price of the same product, currency and month; 0 could not be imputed and were excluded |
| L06 | `order_lines` | No exchange rate for order month and currency | 0 | Excluded |
| L07 | `order_lines` | No purchase cost valid on the order date | 0 | Cost set to 0 (margin overstated) |
| L08 | `order_lines` | Lines on cancelled orders | 1,849 | Excluded from sales (not revenue) |
| R01 | `returns` | Returns that don't match a valid sales line | 5 | Excluded |
| R02 | `returns` | Returned quantity larger than quantity sold | 0 | Capped at quantity sold |
| R03 | `returns` | Return dated before the order | 0 | Kept, flagged in log only |
