"""Theoretical vs. real balance, deviation classification and micro-fraud detection."""
from __future__ import annotations

import sqlite3

import pandas as pd

TOLERANCE = 0.005  # currency units; anything above is a real deviation (rounding stays below)

# Same logic as sql/sqlserver/04_vw_balance_reconciliation.sql, in SQLite dialect.
RECON_SQL = """
SELECT
    s.msisdn,
    s.day,
    p.balance                                              AS opening_balance,
    COALESCE(m.recharge,0) + COALESCE(m.adjustment_credit,0) + COALESCE(m.transfer_in,0) AS credits,
    COALESCE(m.usage,0) + COALESCE(m.bundle_fee,0) + COALESCE(m.adjustment_debit,0) + COALESCE(m.transfer_out,0) AS debits,
    COALESCE(m.recharge,0)     AS recharge,
    COALESCE(m.transfer_in,0)  AS transfer_in,
    COALESCE(m.transfer_out,0) AS transfer_out,
    ROUND(p.balance
          + COALESCE(m.recharge,0) + COALESCE(m.adjustment_credit,0) + COALESCE(m.transfer_in,0)
          + COALESCE(m.usage,0) + COALESCE(m.bundle_fee,0) + COALESCE(m.adjustment_debit,0) + COALESCE(m.transfer_out,0), 2)
                                                           AS theoretical_balance,
    s.balance                                              AS real_balance
FROM stg_balance_snapshot s
JOIN stg_balance_snapshot p
  ON p.msisdn = s.msisdn AND p.day = date(s.day, '-1 day')
LEFT JOIN stg_daily_movements m
  ON m.msisdn = s.msisdn AND m.day = s.day
"""


def reconcile(con: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(RECON_SQL, con)
    df["deviation"] = (df.real_balance - df.theoretical_balance).round(2)
    df["flag"] = df.deviation.abs() > TOLERANCE
    return df


def flag_micro_fraud(recon: pd.DataFrame, max_amount: float = 0.05, min_share: float = 0.6) -> pd.DataFrame:
    """Subscribers losing tiny unexplained amounts on most days.

    One-off cents are noise; the same few cents almost every day are a pattern.
    Returns one row per suspect with frequency, typical amount and total exposure.
    """
    neg = recon[(recon.deviation < -TOLERANCE) & (recon.deviation >= -max_amount)]
    days = recon.groupby("msisdn").day.nunique()
    agg = neg.groupby("msisdn").agg(days_hit=("day", "nunique"), median_cents=("deviation", lambda s: -s.median() * 100),
                                    total_loss=("deviation", lambda s: -s.sum()))
    agg["share_of_days"] = agg.days_hit / days.reindex(agg.index)
    return agg[agg.share_of_days >= min_share].sort_values("total_loss", ascending=False).round(3)


def classify_day_level(recon: pd.DataFrame, micro: pd.DataFrame) -> pd.DataFrame:
    """Explain the remaining (non-micro) deviations with simple, auditable rules."""
    d = recon[recon.flag & ~recon.msisdn.isin(micro.index)].copy()

    def why(r):
        dev = r.deviation
        if dev < 0 and r.recharge > 0 and abs(abs(dev) - r.recharge) <= 0.01:
            return "recharge_not_credited"
        if dev > 0 and r.transfer_out < 0 and dev <= -r.transfer_out / 2 + 0.01:
            return "transfer_log_duplicated_donor"
        if dev < 0 and r.transfer_in > 0 and abs(dev) <= r.transfer_in / 2 + 0.01:
            return "transfer_log_duplicated_receiver"
        return "unexplained"

    d["reason"] = d.apply(why, axis=1) if len(d) else []
    return d.sort_values("deviation")
