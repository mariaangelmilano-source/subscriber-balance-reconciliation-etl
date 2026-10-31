"""python -m balance_etl --subscribers 20000 --days 30"""
from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

import pandas as pd

from .extract import connect_sources, extract_events, extract_snapshots
from .load import load, to_daily_wide
from .reconcile import classify_day_level, flag_micro_fraud, reconcile
from .sources import build_sources


def run(subscribers: int, days: int, seed: int, workdir: Path, out: Path, chunk: int = 50_000) -> dict:
    t0 = time.perf_counter()
    truth = build_sources(workdir / "sources", subscribers, days, seed)
    t1 = time.perf_counter()

    src = connect_sources(workdir / "sources")
    events = pd.concat(extract_events(src, chunk), ignore_index=True)
    snaps = pd.concat(extract_snapshots(src, chunk), ignore_index=True)
    daily = to_daily_wide(events)
    t2 = time.perf_counter()

    target_path = workdir / "analytics.db"
    target_path.unlink(missing_ok=True)
    tgt = sqlite3.connect(target_path)
    load(tgt, daily, snaps)
    recon = reconcile(tgt)
    micro = flag_micro_fraud(recon)
    explained = classify_day_level(recon, micro)
    t3 = time.perf_counter()

    out.mkdir(exist_ok=True)
    micro.to_csv(out / "micro_fraud_suspects.csv")
    explained.to_csv(out / "deviations.csv", index=False)

    found_micro = set(micro.index)
    lost = {(r.msisdn, r.day) for r in explained.itertuples() if r.reason == "recharge_not_credited"}
    dup = {(r.msisdn, r.day) for r in explained.itertuples() if r.reason == "transfer_log_duplicated_donor"}
    stats = {
        "subscribers": subscribers, "days": days,
        "source_rows_events": len(events), "subscriber_days_reconciled": len(recon),
        "flagged_subscriber_days": int(recon.flag.sum()),
        "micro_fraud_found": f"{len(found_micro & truth.micro_fraud)}/{len(truth.micro_fraud)}",
        "micro_fraud_false_positives": len(found_micro - truth.micro_fraud),
        "micro_fraud_total_loss": round(micro.total_loss.sum(), 2),
        "recharge_not_credited_found": f"{len(lost & truth.lost_topups)}/{len(truth.lost_topups)}",
        "duplicated_transfer_logs_found": f"{len(dup & truth.duplicated_transfers)}/{len(truth.duplicated_transfers)}",
        "unexplained": int((explained.reason == "unexplained").sum()) if len(explained) else 0,
        "seconds_generate": round(t1 - t0, 1), "seconds_extract_transform": round(t2 - t1, 1),
        "seconds_load_reconcile": round(t3 - t2, 1),
    }
    lines = ["# Balance reconciliation run — Andina Telecom (synthetic)", ""] + [f"- **{k}**: {v}" for k, v in stats.items()]
    lines += ["", "## Top micro-fraud suspects", micro.head(10).to_markdown(), "",
              "## Deviation reasons", explained.reason.value_counts().to_frame("subscriber_days").to_markdown() if len(explained) else "none", ""]
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="Theoretical vs. real prepaid balance reconciliation (synthetic data)")
    ap.add_argument("--subscribers", type=int, default=20_000)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--workdir", default="data")
    ap.add_argument("--out", default="reports")
    a = ap.parse_args()
    stats = run(a.subscribers, a.days, a.seed, Path(a.workdir), Path(a.out))
    for k, v in stats.items():
        print(f"{k:32s} {v}")


if __name__ == "__main__":
    main()
