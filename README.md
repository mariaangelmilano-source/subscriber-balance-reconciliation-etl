# Subscriber Balance Reconciliation ETL

Daily **theoretical vs. real balance** check for every prepaid subscriber of a fictional operator (*Andina Telecom*). The ETL pulls movements from several production schemas with inconsistent formats, normalizes and pivots them, loads them into **SQL Server** for analysis, and compares each subscriber's expected balance with the balance the platform actually holds.

It catches what totals hide: a recharge that was charged but never credited, a duplicated transfer record, or **systematic fraud by tiny amounts** spread over a small population.

> All data is synthetic, generated with a fixed seed. Operator, schemas, tables and amounts are invented. This repository reproduces the design of an ETL I built professionally, without any real data, system names or figures.

## The problem

A prepaid balance changes through many systems: recharges, usage rated by mediation, plan fees, customer-care adjustments and balance transfers between subscribers. Each lives in a different schema with its own conventions. Each daily query spans the **whole customer base**, so the data is hard to handle even on a local server. On top of that, the production database is read-only and doesn't allow CTEs.

The question is simple; answering it at scale is not:

```
theoretical balance(D) = real balance(D-1)
                       + recharges + credit adjustments + transfers received
                       − usage − plan fees − debit adjustments − transfers sent
deviation(D)           = real balance(D) − theoretical balance(D)
```

## Pipeline

```
 PRODUCTION (read-only, no CTEs)               ETL (Python)                       ANALYTICS (SQL Server)
┌───────────────────────────────┐   ┌──────────────────────────────────┐   ┌──────────────────────────────┐
│ billing.charges   cents,YYYYMMDD│──►│ 1 extract minimal columns, chunks│   │ ra.stg_daily_movements       │
│ recharge.topups   "12,50",DD/MM │──►│ 2 normalize formats → events     │──►│ ra.stg_balance_snapshot      │
│ mediation.usage   key/value rows│──►│ 3 pivot long → wide (per event)  │   │ ra.vw_balance_reconciliation │
│ care.adjustments  signed, ISO   │──►│ 4 group & pivot per subscriber-day│   │ micro-fraud & D+1 exceptions │
│ wallet.transfers / daily_balance│──►│ 5 bulk load (idempotent MERGE)   │   └──────────────────────────────┘
└───────────────────────────────┘   └──────────────────────────────────┘
```

Design decisions:

- **Extract the minimum.** Each source query selects only the columns the balance needs. From mediation's key/value table only 3 of the attributes come out (`msisdn`, `event_day`, `cost`), and the rest stays in production.
- **Stream, don't load.** Rows are read with `fetchmany()` in chunks. The pivot of key/value rows cuts chunks on event boundaries, so an event is never split. A test proves that tiny chunks give the same result as large ones.
- **No CTEs on the source.** Plain `SELECT`s and subqueries only (`sql/sqlserver/02_source_extract_no_cte.sql`). The heavy lifting happens after loading.
- **Pivot heterogeneous records.** Not every event carries the same fields, and not every subscriber has every movement type. Pivoting fills the gaps with explicit zeros, so every subscriber-day has the same shape.
- **Analyze on a shared SQL Server.** T-SQL schema, an idempotent `MERGE` load procedure, the reconciliation view with `LAG()`, and a micro-fraud query are in `sql/sqlserver/`. The demo runs the same logic on SQLite so it works anywhere.

## Run it

```bash
pip install -r requirements.txt
python -m balance_etl --subscribers 20000 --days 30
pytest -q
```

## Sample run (20,000 subscribers × 30 days, seed 11)

| Metric | Result |
|---|---|
| Movement events extracted and normalized | 557,276 |
| Subscriber-days reconciled | 600,000 |
| Subscriber-days with a deviation | 1,795 (0.3%) |
| Micro-fraud victims found (2–3 cents a day, every day) | **50 of 50, 0 false positives** |
| Recharges charged but not credited | 179 of 180 |
| Duplicated transfer records | 58 of 58 |
| Unexplained deviations | 0 |
| Runtime (generate + ETL + reconcile) | ~17 s on a laptop-class CPU |

The micro-fraud case is the point of the whole exercise. Each victim loses about USD 0.02 a day, which is invisible in any aggregate report. Only a per-subscriber daily balance, combined with frequency (`share_of_days`) and amount bands, separates a systematic pattern from rounding noise.

Full output: [`reports/summary.md`](reports/summary.md).

## Repository layout

```
balance_etl/
  sources.py     synthetic multi-schema production sources + injected issues (ground truth)
  extract.py     minimal, chunked, CTE-free extraction and format normalization; key/value pivot
  load.py        per subscriber-day aggregation, wide pivot, bulk load
  reconcile.py   theoretical vs real balance, micro-fraud detector, rule-based reasons
sql/sqlserver/   T-SQL: schema, extraction without CTEs, MERGE procedure, reconciliation view, micro-fraud query
tests/           format parsing, pivot with missing attributes, chunk invariance, end-to-end detection
```

## Production notes

- Load into SQL Server with `pyodbc` (`fast_executemany=True`) or `bcp` into `ra.load_daily_movements`, then run `ra.usp_merge_daily_movements`. Re-running a day replaces it.
- Clustered keys on `(day, msisdn)` match the access pattern: one day at a time, every subscriber.
- Schedule after the platform's end-of-day snapshot; the D+1 exception list comes from `ra.vw_balance_reconciliation`.
- The same flow can be built in Pentaho Data Integration (Table Input per schema → Select Values → Row Normaliser/Denormaliser → Group By → Table Output / Insert-Update).

## Author

**María Ángel Milano** — Data & BI engineer in telecom revenue assurance · [LinkedIn](https://linkedin.com/in/maria-angel-milano) · [GitHub](https://github.com/mariaangelmilano-source)
