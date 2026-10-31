"""Synthetic production sources for a fictional prepaid operator ("Andina Telecom").

The real-world problem this mimics: the movements that change a prepaid balance
live in different systems and schemas, each with its own formats. Here every
source is a separate SQLite file attached as its own schema, with deliberately
inconsistent conventions:

    billing.charges        amounts in cents (INTEGER), dates 'YYYYMMDD'
    recharge.topups        amounts as text with decimal comma ('12,50'), dates 'DD/MM/YYYY'
    mediation.usage_attrs  long key/value rows (attr_name, attr_value): needs a pivot,
                           and not every event carries every attribute
    care.adjustments       signed amounts in currency units, ISO timestamps
    wallet.transfers       balance transfers between subscribers (donor and receiver)
    wallet.daily_balance   end-of-day balance snapshot per subscriber ("real" balance)

Anomalies are injected with ground truth so the reconciliation can be scored.
"""
from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

SCHEMAS = ("billing", "recharge", "mediation", "care", "wallet")


@dataclass
class Truth:
    micro_fraud: set[str] = field(default_factory=set)       # tiny systematic unexplained debits
    lost_topups: set[tuple[str, str]] = field(default_factory=set)      # (msisdn, day) credit not applied
    duplicated_transfers: set[tuple[str, str]] = field(default_factory=set)


def _cents(x: float) -> int:
    return int(round(x * 100))


def build_sources(folder: Path, n_subscribers: int = 2_000, days: int = 14, seed: int = 11,
                  start: date = date(2026, 9, 1)) -> Truth:
    folder.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    cons = {}
    for s in SCHEMAS:
        path = folder / f"{s}.db"
        path.unlink(missing_ok=True)
        cons[s] = sqlite3.connect(path)

    cons["billing"].execute("CREATE TABLE charges (msisdn TEXT, charge_date TEXT, kind TEXT, amount_cents INTEGER)")
    cons["recharge"].execute("CREATE TABLE topups (subscriber TEXT, topup_dt TEXT, channel TEXT, amount_txt TEXT)")
    cons["mediation"].execute("CREATE TABLE usage_attrs (event_id INTEGER, attr_name TEXT, attr_value TEXT)")
    cons["care"].execute("CREATE TABLE adjustments (msisdn TEXT, ts TEXT, code TEXT, amount REAL)")
    cons["wallet"].execute("CREATE TABLE transfers (donor TEXT, receiver TEXT, ts TEXT, amount REAL)")
    cons["wallet"].execute("CREATE TABLE daily_balance (msisdn TEXT, snapshot_date TEXT, balance REAL)")

    subs = [f"S{i:07d}" for i in range(n_subscribers)]
    balance = {m: round(rng.uniform(0, 30), 2) for m in subs}
    truth = Truth(micro_fraud=set(rng.sample(subs, max(3, n_subscribers // 400))))

    # opening snapshot (day before start)
    cons["wallet"].executemany("INSERT INTO daily_balance VALUES (?,?,?)",
                               [(m, (start - timedelta(days=1)).isoformat(), b) for m, b in balance.items()])
    event_id = 0
    for d in range(days):
        day = start + timedelta(days=d)
        charges, topups, attrs, adjs, transfers = [], [], [], [], []
        for m in subs:
            b = balance[m]
            # recharges (credit) — sometimes the credit never reaches the wallet
            if rng.random() < 0.15:
                amt = rng.choice([2, 5, 10, 20])
                topups.append((m, day.strftime("%d/%m/%Y"), rng.choice(["APP", "POS", "BANK"]), f"{amt:.2f}".replace(".", ",")))
                if rng.random() < 0.002:
                    truth.lost_topups.add((m, day.isoformat()))   # recorded but not applied
                else:
                    b += amt
            # usage rated by mediation (debit), long format
            if rng.random() < 0.7:
                event_id += 1
                cost = round(rng.lognormvariate(-1.2, 0.8), 2)
                svc = rng.choice(["DATA", "VOICE", "SMS"])
                rows = [("msisdn", m), ("event_day", day.isoformat()), ("service", svc), ("cost", f"{cost}")]
                if svc == "DATA":
                    rows.append(("mb", f"{rng.randint(10, 900)}"))
                if svc == "VOICE":
                    rows.append(("seconds", f"{rng.randint(10, 1200)}"))
                attrs += [(event_id, k, v) for k, v in rows]
                b -= cost
            # bundles / plan fees (debit, cents)
            if rng.random() < 0.05:
                fee = rng.choice([1.5, 3.0, 4.5])
                charges.append((m, day.strftime("%Y%m%d"), "BUNDLE", _cents(fee)))
                b -= fee
            # customer-care adjustments (signed)
            if rng.random() < 0.01:
                amt = round(rng.choice([-1, 1]) * rng.uniform(0.5, 5), 2)
                adjs.append((m, f"{day.isoformat()}T{rng.randint(8, 20):02d}:00:00", rng.choice(["ADJ-CR", "ADJ-DB"]), amt))
                b += amt
            # balance transfers between subscribers
            if rng.random() < 0.01:
                r = rng.choice(subs)
                if r != m:
                    amt = round(rng.uniform(1, 5), 2)
                    ts = f"{day.isoformat()}T{rng.randint(8, 22):02d}:30:00"
                    transfers.append((m, r, ts, amt))
                    b -= amt
                    balance[r] += amt
                    if rng.random() < 0.01:   # duplicated record in the transfer log, money moved once
                        transfers.append((m, r, ts, amt))
                        truth.duplicated_transfers.add((m, day.isoformat()))
            # systematic micro-debits nobody billed (the fraud we want to catch)
            if m in truth.micro_fraud:
                b -= rng.choice([0.01, 0.02, 0.03])
            balance[m] = round(b, 2)

        cons["billing"].executemany("INSERT INTO charges VALUES (?,?,?,?)", charges)
        cons["recharge"].executemany("INSERT INTO topups VALUES (?,?,?,?)", topups)
        cons["mediation"].executemany("INSERT INTO usage_attrs VALUES (?,?,?)", attrs)
        cons["care"].executemany("INSERT INTO adjustments VALUES (?,?,?,?)", adjs)
        cons["wallet"].executemany("INSERT INTO transfers VALUES (?,?,?,?)", transfers)
        cons["wallet"].executemany("INSERT INTO daily_balance VALUES (?,?,?)",
                                   [(m, day.isoformat(), balance[m]) for m in subs])
    for c in cons.values():
        c.commit()
        c.close()
    return truth
