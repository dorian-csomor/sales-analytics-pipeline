-- Alternative to scripts/setup_source_db.py for people who prefer psql.
-- Run from the repository root, after generating the CSV files:
--
--   psql -U postgres -d vireo -f database/source/01_create_source_schema.sql
--   psql -U postgres -d vireo -f database/source/02_load_source_data.sql

\copy ops.sales_reps           FROM 'data/source_csv/sales_reps.csv'           WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy ops.customers            FROM 'data/source_csv/customers.csv'            WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy ops.products             FROM 'data/source_csv/products.csv'             WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy ops.product_cost_history FROM 'data/source_csv/product_cost_history.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy ops.fx_rates             FROM 'data/source_csv/fx_rates.csv'             WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy ops.orders               FROM 'data/source_csv/orders.csv'               WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy ops.order_lines          FROM 'data/source_csv/order_lines.csv'          WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy ops.returns              FROM 'data/source_csv/returns.csv'              WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
