-- Idempotent load: re-running a day replaces it instead of duplicating it.
CREATE OR ALTER PROCEDURE ra.usp_merge_daily_movements
AS
BEGIN
    SET NOCOUNT ON;
    MERGE ra.stg_daily_movements AS t
    USING ra.load_daily_movements AS s      -- bulk-inserted by the ETL (same columns)
       ON t.day = s.day AND t.msisdn = s.msisdn
    WHEN MATCHED THEN UPDATE SET
        recharge = s.recharge, adjustment_credit = s.adjustment_credit, transfer_in = s.transfer_in,
        usage = s.usage, bundle_fee = s.bundle_fee, adjustment_debit = s.adjustment_debit,
        transfer_out = s.transfer_out, n_events = s.n_events, loaded_at = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN INSERT
        (msisdn, day, recharge, adjustment_credit, transfer_in, usage, bundle_fee, adjustment_debit, transfer_out, n_events)
        VALUES (s.msisdn, s.day, s.recharge, s.adjustment_credit, s.transfer_in, s.usage, s.bundle_fee,
                s.adjustment_debit, s.transfer_out, s.n_events);
    TRUNCATE TABLE ra.load_daily_movements;
END;
GO
