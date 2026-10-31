"""Transform (aggregate + pivot to wide) and load into the analytics server.

Production target is Microsoft SQL Server (DDL and procedures in sql/sqlserver/).
For a self-contained demo the same tables are created in SQLite; the loader only
uses ANSI-style INSERTs so the code path is the same with a pyodbc connection.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

BUCKETS = ["recharge", "adjustment_credit", "transfer_in", "usage", "bundle_fee", "adjustment_debit", "transfer_out"]

DDL = """
CREATE TABLE IF NOT EXISTS stg_daily_movements (
    msisdn TEXT NOT NULL, day TEXT NOT NULL,
    recharge REAL, adjustment_credit REAL, transfer_in REAL,
    usage REAL, bundle_fee REAL, adjustment_debit REAL, transfer_out REAL,
    n_events INTEGER,
    PRIMARY KEY (msisdn, day)
);
CREATE TABLE IF NOT EXISTS stg_balance_snapshot (
    msisdn TEXT NOT NULL, day TEXT NOT NULL, balance REAL,
    PRIMARY KEY (msisdn, day)
);
"""


def to_daily_wide(events: pd.DataFrame) -> pd.DataFrame:
    """Group events per subscriber-day and pivot buckets into columns.

    Not every subscriber has every movement type, so missing buckets become 0.
    """
    g = events.groupby(["msisdn", "day", "bucket"], sort=True).amount.agg(["sum", "count"]).reset_index()
    wide = g.pivot_table(index=["msisdn", "day"], columns="bucket", values="sum", aggfunc="sum", fill_value=0.0)
    wide = wide.reindex(columns=BUCKETS, fill_value=0.0)
    wide["n_events"] = g.groupby(["msisdn", "day"])["count"].sum()
    return wide.round(2).reset_index().sort_values(["msisdn", "day"])


def load(con: sqlite3.Connection, daily: pd.DataFrame, snapshots: pd.DataFrame) -> None:
    con.executescript(DDL)
    cols = ["msisdn", "day", *BUCKETS, "n_events"]
    con.executemany(f"INSERT INTO stg_daily_movements ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    daily[cols].itertuples(index=False, name=None))
    con.executemany("INSERT INTO stg_balance_snapshot (msisdn, day, balance) VALUES (?,?,?)",
                    snapshots[["msisdn", "day", "balance"]].itertuples(index=False, name=None))
    con.commit()
