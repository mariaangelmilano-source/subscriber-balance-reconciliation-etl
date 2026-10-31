-- Theoretical vs. real balance per subscriber and day.
-- theoretical = yesterday's real balance + today's credits + today's (negative) debits
CREATE OR ALTER VIEW ra.vw_balance_reconciliation AS
SELECT
    s.msisdn,
    s.day,
    LAG(s.balance) OVER (PARTITION BY s.msisdn ORDER BY s.day)               AS opening_balance,
    ISNULL(m.recharge,0) + ISNULL(m.adjustment_credit,0) + ISNULL(m.transfer_in,0)   AS credits,
    ISNULL(m.usage,0) + ISNULL(m.bundle_fee,0) + ISNULL(m.adjustment_debit,0) + ISNULL(m.transfer_out,0) AS debits,
    LAG(s.balance) OVER (PARTITION BY s.msisdn ORDER BY s.day)
      + ISNULL(m.recharge,0) + ISNULL(m.adjustment_credit,0) + ISNULL(m.transfer_in,0)
      + ISNULL(m.usage,0) + ISNULL(m.bundle_fee,0) + ISNULL(m.adjustment_debit,0) + ISNULL(m.transfer_out,0)
                                                                              AS theoretical_balance,
    s.balance                                                                 AS real_balance
FROM ra.stg_balance_snapshot s
LEFT JOIN ra.stg_daily_movements m
       ON m.msisdn = s.msisdn AND m.day = s.day;
GO

-- Daily exception list: run the morning after (D+1).
-- SELECT * FROM ra.vw_balance_reconciliation
-- WHERE day = DATEADD(day, -1, CAST(GETDATE() AS DATE))
--   AND ABS(real_balance - theoretical_balance) > 0.005;
