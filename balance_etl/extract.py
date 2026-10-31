"""Extract only what the balance needs, source by source, in chunks.

Constraints reproduced from the real job:
- read-only access to production, and no CTEs allowed on the source database:
  every query is a plain SELECT (subqueries are fine, WITH is not);
- each query touches the whole customer base, so we select the minimum columns
  and stream rows with fetchmany() instead of loading full tables in memory;
- every source has its own formats, normalized here into one event layout:
  (msisdn, day 'YYYY-MM-DD', bucket, amount) with amount signed (+ credit, - debit).
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pandas as pd

from .sources import SCHEMAS

CHUNK = 50_000

# One SELECT per source. Minimal columns only. No CTEs.
QUERIES = {
    "billing": "SELECT msisdn, charge_date, amount_cents FROM billing.charges",
    "recharge": "SELECT subscriber, topup_dt, amount_txt FROM recharge.topups",
    # Only the three attributes the balance needs; optional attributes (mb, seconds) stay in production.
    "mediation": ("SELECT event_id, attr_name, attr_value FROM mediation.usage_attrs "
                  "WHERE attr_name IN ('msisdn', 'event_day', 'cost') ORDER BY event_id"),
    "care": "SELECT msisdn, substr(ts, 1, 10), amount FROM care.adjustments",
    "transfers": "SELECT donor, receiver, substr(ts, 1, 10), amount FROM wallet.transfers",
    "snapshots": "SELECT msisdn, snapshot_date, balance FROM wallet.daily_balance",
}


def connect_sources(folder: Path) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    for s in SCHEMAS:
        con.execute(f"ATTACH DATABASE ? AS {s}", (str(folder / f"{s}.db"),))
    return con


def stream(con: sqlite3.Connection, sql: str, chunk: int = CHUNK) -> Iterator[list[tuple]]:
    cur = con.execute(sql)
    while rows := cur.fetchmany(chunk):
        yield rows


def _ymd(s: str) -> str:          # 'YYYYMMDD' -> ISO
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


def _dmy(s: str) -> str:          # 'DD/MM/YYYY' -> ISO
    return datetime.strptime(s, "%d/%m/%Y").date().isoformat()


def _comma(s: str) -> float:      # '12,50' -> 12.5
    return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)


def extract_events(con: sqlite3.Connection, chunk: int = CHUNK) -> Iterator[pd.DataFrame]:
    """Yield normalized event chunks from every movement source."""
    for rows in stream(con, QUERIES["billing"], chunk):
        yield pd.DataFrame([(m, _ymd(d), "bundle_fee", -c / 100) for m, d, c in rows],
                           columns=["msisdn", "day", "bucket", "amount"])
    for rows in stream(con, QUERIES["recharge"], chunk):
        yield pd.DataFrame([(m, _dmy(d), "recharge", _comma(a)) for m, d, a in rows],
                           columns=["msisdn", "day", "bucket", "amount"])
    for rows in stream(con, QUERIES["care"], chunk):
        yield pd.DataFrame([(m, d, "adjustment_credit" if a > 0 else "adjustment_debit", a) for m, d, a in rows],
                           columns=["msisdn", "day", "bucket", "amount"])
    for rows in stream(con, QUERIES["transfers"], chunk):
        out = [(dn, d, "transfer_out", -a) for dn, _, d, a in rows] + [(rc, d, "transfer_in", a) for _, rc, d, a in rows]
        yield pd.DataFrame(out, columns=["msisdn", "day", "bucket", "amount"])
    yield from _mediation_events(con, chunk)


def _mediation_events(con: sqlite3.Connection, chunk: int) -> Iterator[pd.DataFrame]:
    """Pivot long key/value rows (one row per attribute) into one row per event.

    Chunks are cut on event boundaries so an event never splits across two pivots.
    """
    carry: list[tuple] = []
    for rows in stream(con, QUERIES["mediation"], chunk):
        rows = carry + rows
        last_id = rows[-1][0]
        carry = [r for r in rows if r[0] == last_id]
        body = [r for r in rows if r[0] != last_id]
        if body:
            yield _pivot(body)
    if carry:
        yield _pivot(carry)


def _pivot(rows: list[tuple]) -> pd.DataFrame:
    long = pd.DataFrame(rows, columns=["event_id", "attr", "value"])
    wide = long.pivot(index="event_id", columns="attr", values="value")
    return pd.DataFrame({
        "msisdn": wide["msisdn"].to_numpy(),
        "day": wide["event_day"].to_numpy(),
        "bucket": "usage",
        "amount": -wide["cost"].astype(float).to_numpy(),
    })


def extract_snapshots(con: sqlite3.Connection, chunk: int = CHUNK) -> Iterator[pd.DataFrame]:
    for rows in stream(con, QUERIES["snapshots"], chunk):
        yield pd.DataFrame(rows, columns=["msisdn", "day", "balance"])
