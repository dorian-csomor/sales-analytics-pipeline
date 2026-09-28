-- =============================================================================
-- Vireo Wholesale - operational (source) database
-- -----------------------------------------------------------------------------
-- Simulates the ERP / order-entry system of a fictional office and facility
-- supplies distributor operating in Hungary, Austria, Czechia, Slovakia and
-- Romania.
--
-- Like many real legacy systems, this schema is NOT analytics-friendly:
--   * order dates are stored as free text (different branches, different formats)
--   * foreign keys are not enforced (orphan records are possible)
--   * amounts are stored in local currency
--   * product cost lives in a separate history table
-- The ETL pipeline in this repository turns it into a clean star schema.
-- =============================================================================

DROP SCHEMA IF EXISTS ops CASCADE;
CREATE SCHEMA ops;

COMMENT ON SCHEMA ops IS 'Operational (source) system of Vireo Wholesale - read-only for analytics';

-- Sales representatives ------------------------------------------------------
CREATE TABLE ops.sales_reps (
    rep_id            INTEGER PRIMARY KEY,
    first_name        VARCHAR(50)  NOT NULL,
    last_name         VARCHAR(50)  NOT NULL,
    email             VARCHAR(120),
    territory         VARCHAR(50),              -- country the rep covers
    hire_date         DATE,
    termination_date  DATE                      -- NULL = still employed
);

-- Customers ------------------------------------------------------------------
CREATE TABLE ops.customers (
    customer_id       INTEGER PRIMARY KEY,
    customer_name     VARCHAR(150) NOT NULL,
    segment           VARCHAR(30),              -- Enterprise / Mid-Market / SMB
    city              VARCHAR(80),
    country           VARCHAR(50),              -- free text, entered by hand
    assigned_rep_id   INTEGER,                  -- current account owner
    created_at        TIMESTAMP
);

-- Products -------------------------------------------------------------------
CREATE TABLE ops.products (
    product_id        INTEGER PRIMARY KEY,
    sku               VARCHAR(30)  NOT NULL,
    product_name      VARCHAR(150) NOT NULL,
    category          VARCHAR(50),
    supplier          VARCHAR(80),
    list_price_eur    NUMERIC(12,2),            -- current list price
    is_active         BOOLEAN DEFAULT TRUE
);

-- Purchase cost history (one row per product per validity period) ------------
CREATE TABLE ops.product_cost_history (
    product_id        INTEGER      NOT NULL,
    valid_from        DATE         NOT NULL,
    valid_to          DATE,                     -- NULL = current cost
    unit_cost_eur     NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (product_id, valid_from)
);

-- Monthly average exchange rates (units of currency per 1 EUR) ----------------
CREATE TABLE ops.fx_rates (
    rate_month        DATE        NOT NULL,     -- first day of month
    currency          CHAR(3)     NOT NULL,
    units_per_eur     NUMERIC(12,4) NOT NULL,
    PRIMARY KEY (rate_month, currency)
);

-- Order headers --------------------------------------------------------------
CREATE TABLE ops.orders (
    order_id          INTEGER PRIMARY KEY,
    order_number      VARCHAR(20)  NOT NULL,    -- business key shown on invoices
    customer_id       INTEGER,
    rep_id            INTEGER,
    order_date        VARCHAR(30),              -- free text! format depends on entry channel
    ship_date         VARCHAR(30),
    status            VARCHAR(20),
    currency          VARCHAR(5),
    sales_channel     VARCHAR(20),
    created_at        TIMESTAMP
);

-- Order lines ----------------------------------------------------------------
CREATE TABLE ops.order_lines (
    order_line_id     INTEGER PRIMARY KEY,
    order_id          INTEGER NOT NULL,
    product_id        INTEGER NOT NULL,
    quantity          INTEGER,
    unit_price        NUMERIC(14,2),            -- in order currency
    discount_pct      NUMERIC(6,3)              -- expected as a fraction (0.05 = 5%)
);

-- Returns --------------------------------------------------------------------
CREATE TABLE ops.returns (
    return_id         INTEGER PRIMARY KEY,
    order_id          INTEGER NOT NULL,
    product_id        INTEGER NOT NULL,
    return_date       DATE,
    quantity          INTEGER,
    reason            VARCHAR(60)
);

CREATE INDEX ix_order_lines_order   ON ops.order_lines (order_id);
CREATE INDEX ix_orders_customer     ON ops.orders (customer_id);
CREATE INDEX ix_returns_order       ON ops.returns (order_id);
