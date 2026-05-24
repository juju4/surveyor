# tests/test_exception_filter_online.py
from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
from typing import List

from exception_filter import ExceptionMatcher
from surveyor import _write_results  # type: ignore[attr-defined]


@dataclass
class DummyResult:
    hostname: str
    username: str
    path: str
    command_line: str
    other_data: List[str]


class DummyTag:
    def __init__(self, tag: str) -> None:
        self.tag = tag


class DummyLogger:
    def info(self, msg: str) -> None:
        pass

    def debug(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        pass

    def error(self, msg: str) -> None:
        pass


def test_write_results_marks_exceptions(tmp_path) -> None:
    exception_csv = tmp_path / "exceptions.csv"
    with exception_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["hostname", "username"])
        writer.writeheader()
        writer.writerow({"hostname": "host1", "username": ""})

    matcher = ExceptionMatcher.from_csv_files([exception_csv])

    results = [
        DummyResult(
            hostname="host1",
            username="user1",
            path="/bin/ls",
            command_line="ls -la",
            other_data=[],
        ),
        DummyResult(
            hostname="host2",
            username="user2",
            path="/bin/cat",
            command_line="cat /etc/passwd",
            other_data=[],
        ),
    ]

    buffer = StringIO()
    writer = csv.writer(buffer)

    # header
    writer.writerow(
        [
            "hostname",
            "username",
            "path",
            "command_line",
            "program",
            "source",
            "exception",
        ]
    )

    _write_results(
        output=writer,
        results=results,  # type: ignore[arg-type]
        program="test-program",
        source="test-source",
        tag=DummyTag("test-tag"),
        log=DummyLogger(),
        use_tqdm=False,
        exception_matcher=matcher,
        exception_marker="EXC",
    )

    buffer.seek(0)
    rows = list(csv.DictReader(buffer))
    assert rows[0]["exception"] == "EXC"
    assert rows[1]["exception"] == ""
