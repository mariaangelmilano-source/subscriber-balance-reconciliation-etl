-- Analytics database on Microsoft SQL Server (target of the ETL).
-- Staging tables are loaded in bulk by the ETL; analysis runs here, not on production.
IF SCHEMA_ID('ra') IS NULL EXEC('CREATE SCHEMA ra');
GO

IF OBJECT_ID('ra.stg_daily_movements') IS NULL
CREATE TABLE ra.stg_daily_movements (
    msisdn            VARCHAR(15)   NOT NULL,
    day               DATE          NOT NULL,
    recharge          DECIMAL(12,2) NOT NULL DEFAULT 0,
    adjustment_credit DECIMAL(12,2) NOT NULL DEFAULT 0,
    transfer_in       DECIMAL(12,2) NOT NULL DEFAULT 0,
    usage             DECIMAL(12,2) NOT NULL DEFAULT 0,   -- negative
    bundle_fee        DECIMAL(12,2) NOT NULL DEFAULT 0,   -- negative
    adjustment_debit  DECIMAL(12,2) NOT NULL DEFAULT 0,   -- negative
    transfer_out      DECIMAL(12,2) NOT NULL DEFAULT 0,   -- negative
    n_events          INT           NOT NULL,
    loaded_at         DATETIME2(0)  NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT pk_stg_daily_movements PRIMARY KEY CLUSTERED (day, msisdn)
);
GO

IF OBJECT_ID('ra.stg_balance_snapshot') IS NULL
CREATE TABLE ra.stg_balance_snapshot (
    msisdn    VARCHAR(15)   NOT NULL,
    day       DATE          NOT NULL,
    balance   DECIMAL(12,2) NOT NULL,
    CONSTRAINT pk_stg_balance_snapshot PRIMARY KEY CLUSTERED (day, msisdn)
);
GO

-- Landing table for bulk inserts (BULK INSERT / bcp / pyodbc fast_executemany), merged by ra.usp_merge_daily_movements.
IF OBJECT_ID('ra.load_daily_movements') IS NULL
SELECT TOP 0 msisdn, day, recharge, adjustment_credit, transfer_in, usage, bundle_fee,
             adjustment_debit, transfer_out, n_events
INTO ra.load_daily_movements
FROM ra.stg_daily_movements;
GO
