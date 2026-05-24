# tests/test_performance_exception_filter.py
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import csv
import pytest

from exception_filter import ExceptionMatcher


@pytest.mark.performance
def test_exception_matcher_throughput(tmp_path: Path) -> None:
    csv_path = tmp_path / "exceptions.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["hostname", "username"])
        writer.writeheader()
        for i in range(1000):
            writer.writerow({"hostname": f"host{i}", "username": f"user{i}"})

    matcher = ExceptionMatcher.from_csv_files([csv_path])

    def worker(idx: int) -> bool:
        return matcher.is_exception(f"host{idx}", f"user{idx}")

    iterations = 10_000
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(worker, range(iterations)))
    duration = time.perf_counter() - start
    qps = iterations / duration
    # Sane lower bound; adjust as needed
    assert qps > 5_000
