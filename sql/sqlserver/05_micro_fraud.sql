-- Subscribers losing a few unexplained cents on most days of the month (systematic micro-debits).
SELECT r.msisdn,
       COUNT(*)                                                  AS days_hit,
       CAST(COUNT(*) AS FLOAT) / MAX(t.days_observed)            AS share_of_days,
       SUM(r.theoretical_balance - r.real_balance)               AS total_loss
FROM ra.vw_balance_reconciliation r
JOIN (SELECT msisdn, COUNT(*) AS days_observed
      FROM ra.stg_balance_snapshot GROUP BY msisdn) t ON t.msisdn = r.msisdn
WHERE r.real_balance - r.theoretical_balance BETWEEN -0.05 AND -0.006
GROUP BY r.msisdn
HAVING CAST(COUNT(*) AS FLOAT) / MAX(t.days_observed) >= 0.6
ORDER BY total_loss DESC;
