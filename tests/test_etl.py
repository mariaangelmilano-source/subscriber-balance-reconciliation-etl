from pathlib import Path

import pandas as pd
import pytest

from balance_etl.__main__ import run
from balance_etl.extract import QUERIES, _comma, _dmy, _pivot, _ymd
from balance_etl.load import BUCKETS, to_daily_wide


def test_format_normalizers():
    assert _ymd("20260901") == "2026-09-01"
    assert _dmy("01/09/2026") == "2026-09-01"
    assert _comma("12,50") == 12.5 and _comma("1.234,50") == 1234.5 and _comma("3.0") == 3.0


def test_source_queries_use_no_ctes():
    assert all("with " not in q.lower() for q in QUERIES.values())


def test_pivot_handles_missing_optional_attributes():
    rows = [(1, "msisdn", "A"), (1, "event_day", "2026-09-01"), (1, "cost", "0.5"), (1, "mb", "100"),
            (2, "msisdn", "B"), (2, "event_day", "2026-09-01"), (2, "cost", "0.2")]  # event 2 has no 'mb'
    df = _pivot(rows)
    assert list(df.amount) == [-0.5, -0.2]


def test_daily_wide_fills_missing_buckets():
    ev = pd.DataFrame([("A", "2026-09-01", "recharge", 5.0), ("A", "2026-09-01", "usage", -1.25),
                       ("A", "2026-09-01", "usage", -0.25)], columns=["msisdn", "day", "bucket", "amount"])
    w = to_daily_wide(ev)
    assert set(BUCKETS) <= set(w.columns)
    row = w.iloc[0]
    assert row.recharge == 5.0 and row.usage == -1.5 and row.transfer_out == 0 and row.n_events == 3


@pytest.fixture(scope="module")
def stats(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("run")
    return run(subscribers=1200, days=10, seed=3, workdir=tmp / "data", out=tmp / "reports", chunk=5_000)


def test_end_to_end_finds_injected_issues(stats):
    found, total = map(int, stats["micro_fraud_found"].split("/"))
    assert found == total and stats["micro_fraud_false_positives"] == 0
    f, t = map(int, stats["recharge_not_credited_found"].split("/"))
    assert f >= t - 1
    assert stats["unexplained"] == 0


def test_chunking_does_not_change_results(tmp_path):
    a = run(400, 5, 9, tmp_path / "a", tmp_path / "ra", chunk=50_000)
    b = run(400, 5, 9, tmp_path / "b", tmp_path / "rb", chunk=97)   # tiny chunks split events everywhere
    assert a["source_rows_events"] == b["source_rows_events"]
    assert a["flagged_subscriber_days"] == b["flagged_subscriber_days"]
