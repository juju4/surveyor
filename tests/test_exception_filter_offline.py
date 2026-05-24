# tests/test_exception_filter_offline.py
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from exception_filter import ExceptionEntry, ExceptionMatcher


@pytest.fixture
def tmp_exception_csv(tmp_path: Path) -> Path:
    path = tmp_path / "exceptions.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["hostname", "username"])
        writer.writeheader()
        writer.writerow({"hostname": "host1", "username": ""})
        writer.writerow({"hostname": "", "username": "user1"})
        writer.writerow({"hostname": "host-utf-8-😀", "username": "weird\ufffduser"})
        writer.writerow(
            {"hostname": "sql-host", "username": "user'; DROP TABLE users;--"}
        )
    return path


def test_exception_entry_requires_hostname_or_username() -> None:
    with pytest.raises(ValueError):
        ExceptionEntry.from_row({"hostname": "", "username": ""})


def test_exception_matcher_from_csv(tmp_exception_csv: Path) -> None:
    matcher = ExceptionMatcher.from_csv_files([tmp_exception_csv])
    assert matcher.is_exception("host1", "anyuser")
    assert matcher.is_exception("anyhost", "user1")
    assert matcher.is_exception("HOST1", "ANYUSER")  # case-insensitive
    assert matcher.is_exception("host-utf-8-😀", "x")
    assert matcher.is_exception("sql-host", "user'; DROP TABLE users;--")
    assert not matcher.is_exception("other-host", "other-user")


@pytest.mark.parametrize(
    "hostname,username",
    [
        ("long-" + "x" * 4096, "user"),
        ("host", "long-" + "y" * 4096),
        ("emoji-😀-😈", "user-👾"),
        ("\ue000private-use", "user"),
        ("garbled-â€“™", "user"),
    ],
)
def test_exception_matcher_handles_anomalous_strings(
    tmp_exception_csv: Path, hostname: str, username: str
) -> None:
    matcher = ExceptionMatcher.from_csv_files([tmp_exception_csv])
    # Should not raise, regardless of content
    matcher.is_exception(hostname, username)
