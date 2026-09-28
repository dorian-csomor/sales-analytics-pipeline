-- =============================================================================
-- ETL metadata (schema `etl`)
-- -----------------------------------------------------------------------------
-- Kept separate from the analytics schema so the run history and data quality
-- history survive full refreshes. Safe to run repeatedly.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS etl;

CREATE TABLE IF NOT EXISTS etl.data_quality_log (
    run_id            VARCHAR(20)  NOT NULL,
    check_id          VARCHAR(10)  NOT NULL,
    source_table      VARCHAR(50)  NOT NULL,
    issue             VARCHAR(200) NOT NULL,
    rows_affected     INTEGER      NOT NULL,
    action_taken      VARCHAR(200) NOT NULL
);

CREATE TABLE IF NOT EXISTS etl.pipeline_runs (
    run_id            VARCHAR(20)  PRIMARY KEY,
    started_at        TIMESTAMP    NOT NULL,
    finished_at       TIMESTAMP    NOT NULL,
    status            VARCHAR(20)  NOT NULL,
    fact_sales_rows   INTEGER,
    fact_returns_rows INTEGER,
    net_sales_eur     NUMERIC(16,2)
);
