-- =============================================================================
-- Vireo Wholesale - analytics schema (star schema)
-- -----------------------------------------------------------------------------
-- Target of the ETL pipeline (run_pipeline.py). Clean, conformed and
-- BI-tool independent: Power BI, Tableau, Excel or plain SQL can read it.
--
--   dim_date ─┐
--   dim_customer ─┤
--   dim_product ──┼── fact_sales    (grain: one order line)
--   dim_sales_rep ┘── fact_returns  (grain: one return record)
--
-- All amounts are converted to EUR (reporting currency).
-- Every dimension has an "Unknown" member with key -1 so that facts never
-- lose rows because of a missing reference.
-- The pipeline does a full refresh: this script drops and recreates the schema.
-- =============================================================================

DROP SCHEMA IF EXISTS analytics CASCADE;
CREATE SCHEMA analytics;

-- Dimensions -----------------------------------------------------------------
CREATE TABLE analytics.dim_date (
    date_key          INTEGER PRIMARY KEY,        -- YYYYMMDD
    date              DATE        NOT NULL,
    year              SMALLINT    NOT NULL,
    quarter           VARCHAR(2)  NOT NULL,        -- Q1..Q4
    month_number      SMALLINT    NOT NULL,
    month_name        VARCHAR(10) NOT NULL,
    month_short       VARCHAR(3)  NOT NULL,
    year_month        VARCHAR(7)  NOT NULL,        -- 2025-03
    iso_week          SMALLINT    NOT NULL,
    day_of_week       SMALLINT    NOT NULL,        -- 1 = Monday
    day_name          VARCHAR(10) NOT NULL,
    is_weekend        BOOLEAN     NOT NULL
);

CREATE TABLE analytics.dim_customer (
    customer_key      INTEGER PRIMARY KEY,
    customer_name     VARCHAR(150) NOT NULL,
    segment           VARCHAR(30)  NOT NULL,
    city              VARCHAR(80),
    country           VARCHAR(50)  NOT NULL,
    country_code      CHAR(2),
    account_owner     VARCHAR(110),                -- current sales rep
    customer_since    DATE,
    first_order_date  DATE,
    last_order_date   DATE,
    cohort_year       SMALLINT,                    -- year of first order
    customer_status   VARCHAR(20)  NOT NULL,       -- Active / Lapsed / No orders
    merged_source_ids VARCHAR(100)                 -- duplicate source ids merged into this customer
);

CREATE TABLE analytics.dim_product (
    product_key       INTEGER PRIMARY KEY,
    sku               VARCHAR(30)  NOT NULL,
    product_name      VARCHAR(150) NOT NULL,
    category          VARCHAR(50)  NOT NULL,
    supplier          VARCHAR(80)  NOT NULL,
    list_price_eur    NUMERIC(12,2),
    is_active         BOOLEAN,
    merged_source_ids VARCHAR(100)
);

CREATE TABLE analytics.dim_sales_rep (
    rep_key           INTEGER PRIMARY KEY,
    rep_name          VARCHAR(110) NOT NULL,
    territory         VARCHAR(50)  NOT NULL,
    email             VARCHAR(120),
    hire_date         DATE,
    termination_date  DATE,
    is_active         BOOLEAN      NOT NULL
);

-- Facts ----------------------------------------------------------------------
CREATE TABLE analytics.fact_sales (
    order_line_id     INTEGER PRIMARY KEY,
    order_id          INTEGER      NOT NULL,
    order_number      VARCHAR(20)  NOT NULL,
    order_date_key    INTEGER      NOT NULL REFERENCES analytics.dim_date (date_key),
    ship_date_key     INTEGER               REFERENCES analytics.dim_date (date_key),
    customer_key      INTEGER      NOT NULL REFERENCES analytics.dim_customer (customer_key),
    product_key       INTEGER      NOT NULL REFERENCES analytics.dim_product (product_key),
    rep_key           INTEGER      NOT NULL REFERENCES analytics.dim_sales_rep (rep_key),
    sales_channel     VARCHAR(20),
    order_status      VARCHAR(20)  NOT NULL,
    order_currency    CHAR(3)      NOT NULL,
    quantity          INTEGER      NOT NULL,
    unit_price_local  NUMERIC(14,2) NOT NULL,
    discount_pct      NUMERIC(6,4) NOT NULL,
    fx_rate           NUMERIC(12,4) NOT NULL,      -- units of order currency per 1 EUR
    gross_sales_eur   NUMERIC(14,2) NOT NULL,      -- before discount
    discount_eur      NUMERIC(14,2) NOT NULL,
    net_sales_eur     NUMERIC(14,2) NOT NULL,      -- revenue
    cost_eur          NUMERIC(14,2) NOT NULL,
    gross_margin_eur  NUMERIC(14,2) NOT NULL,
    is_price_imputed  BOOLEAN      NOT NULL
);

CREATE TABLE analytics.fact_returns (
    return_id         INTEGER PRIMARY KEY,
    return_date_key   INTEGER      NOT NULL REFERENCES analytics.dim_date (date_key),
    order_id          INTEGER      NOT NULL,
    order_line_id     INTEGER,
    customer_key      INTEGER      NOT NULL REFERENCES analytics.dim_customer (customer_key),
    product_key       INTEGER      NOT NULL REFERENCES analytics.dim_product (product_key),
    rep_key           INTEGER      NOT NULL REFERENCES analytics.dim_sales_rep (rep_key),
    quantity_returned INTEGER      NOT NULL,
    return_value_eur  NUMERIC(14,2) NOT NULL,
    return_reason     VARCHAR(60)
);

CREATE INDEX ix_fact_sales_date     ON analytics.fact_sales (order_date_key);
CREATE INDEX ix_fact_sales_customer ON analytics.fact_sales (customer_key);
CREATE INDEX ix_fact_sales_product  ON analytics.fact_sales (product_key);
