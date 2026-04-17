"""Cryptographic audit log — tamper-evident, hash-chained log entries.

Every checkpoint operation (write, read, resume, delete) is logged with
a hash of the previous entry, creating a chain that breaks if tampered with.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agentcheckpoint.enterprise import require_enterprise

logger = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    """A single audit log entry."""

    sequence: int
    timestamp: str
    action: str  # "checkpoint_write", "checkpoint_read", "resume", "delete"
    run_id: str
    step: Optional[int] = None
    user: str = ""
    details: dict | None = None
    prev_hash: str = ""
    entry_hash: str = ""

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of this entry (excluding entry_hash field)."""
        d = asdict(self)
        d.pop("entry_hash", None)
        raw = json.dumps(d, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


class AuditLog:
    """Tamper-evident audit log with cryptographic hash chaining.

    Each entry includes the hash of the previous entry, creating a chain.
    Any modification to a past entry breaks the chain and is detectable.
    """

    def __init__(self, log_path: str | Path = "./audit_log.jsonl"):
        require_enterprise("Audit Log")

        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._sequence = 0
        self._last_hash = "genesis"

        # Load existing log to get sequence and last hash
        if self._path.exists():
            self._load_tail()

    def _load_tail(self) -> None:
        """Load the last entry to get sequence number and hash."""
        last_line = ""
        with open(self._path, "r") as f:
            for line in f:
                if line.strip():
                    last_line = line.strip()

        if last_line:
            entry_data = json.loads(last_line)
            self._sequence = entry_data.get("sequence", 0)
            self._last_hash = entry_data.get("entry_hash", "genesis")

    def log(
        self,
        action: str,
        run_id: str,
        step: int | None = None,
        user: str = "",
        details: dict | None = None,
    ) -> AuditEntry:
        """Add a new entry to the audit log."""
        self._sequence += 1

        entry = AuditEntry(
            sequence=self._sequence,
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=action,
            run_id=run_id,
            step=step,
            user=user,
            details=details,
            prev_hash=self._last_hash,
        )
        entry.entry_hash = entry.compute_hash()
        self._last_hash = entry.entry_hash

        # Append to log file
        with open(self._path, "a") as f:
            f.write(json.dumps(asdict(entry), default=str) + "\n")

        return entry

    def verify_chain(self) -> tuple[bool, int]:
        """Verify the entire audit log chain integrity.

        Returns (is_valid, entries_checked).
        """
        if not self._path.exists():
            return True, 0

        prev_hash = "genesis"
        count = 0

        with open(self._path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                data = json.loads(line)
                count += 1

                # Check chain link
                if data.get("prev_hash") != prev_hash:
                    logger.error(f"Chain broken at entry {count}: expected prev_hash={prev_hash}")
                    return False, count

                # Verify entry hash
                entry = AuditEntry(**data)
                computed = entry.compute_hash()
                if computed != data.get("entry_hash"):
                    logger.error(f"Hash mismatch at entry {count}")
                    return False, count

                prev_hash = data["entry_hash"]

        return True, count

    def export_json(self, output_path: str | Path) -> int:
        """Export the audit log as a formatted JSON file. Returns entry count."""
        entries = []
        if self._path.exists():
            with open(self._path, "r") as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line.strip()))

        with open(output_path, "w") as f:
            json.dump(entries, f, indent=2, default=str)

        return len(entries)

    def export_csv(self, output_path: str | Path) -> int:
        """Export the audit log as CSV. Returns entry count."""
        import csv

        entries = []
        if self._path.exists():
            with open(self._path, "r") as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line.strip()))

        if not entries:
            return 0

        fieldnames = list(entries[0].keys())
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for entry in entries:
                writer.writerow(entry)

        return len(entries)
