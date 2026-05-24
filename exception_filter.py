# exception_filter.py
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Set


@dataclass(frozen=True)
class ExceptionEntry:
    hostname: Optional[str]
    username: Optional[str]

    @staticmethod
    def _normalize(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        v = value.strip()
        return v.lower() if v else None

    @classmethod
    def from_row(cls, row: dict) -> "ExceptionEntry":
        # --- Custom CSV format ---
        hostname = row.get("hostname")
        username = row.get("username")

        # --- AD Group format ---
        if not hostname and "DNSHostName" in row:
            hostname = row.get("DNSHostName")

        if not username:
            if "SamAccountName" in row:
                username = row.get("SamAccountName")
            elif "UserPrincipalName" in row:
                upn = row.get("UserPrincipalName")
                if upn and "@" in upn:
                    username = upn.split("@")[0]

        hostname = cls._normalize(hostname)
        username = cls._normalize(username)

        if not hostname and not username:
            raise ValueError("Row contains no usable hostname or username")

        return cls(hostname=hostname, username=username)


class ExceptionMatcher:
    def __init__(self, entries: Iterable[ExceptionEntry]) -> None:
        self._entries: Set[ExceptionEntry] = set(entries)

    @classmethod
    def from_csv_files(cls, paths: Iterable[str | Path]) -> "ExceptionMatcher":
        entries: List[ExceptionEntry] = []
        for path in paths:
            p = Path(path)
            if not p.is_file():
                raise FileNotFoundError(f"Exception CSV not found: {p}")

            with p.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        entry = ExceptionEntry.from_row(row)
                        entries.append(entry)
                    except ValueError:
                        continue  # skip invalid rows

        return cls(entries)

    def is_exception(self, hostname: str, username: str) -> bool:
        h = (hostname or "").strip().lower()
        u = (username or "").strip().lower()

        for entry in self._entries:
            if entry.hostname and entry.hostname != h:
                continue
            if entry.username and entry.username != u:
                continue
            return True

        return False
