"""PostgreSQL storage adapter.

Schema:
    checkpoints (run_id TEXT, step INT, data BYTEA, created_at TIMESTAMPTZ, metadata JSONB)
    runs (run_id TEXT PK, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ, status TEXT, ...)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

from agentcheckpoint.state import RunInfo, StepInfo
from agentcheckpoint.storage import StorageBackend

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS checkpoints (
    run_id TEXT NOT NULL,
    step INTEGER NOT NULL,
    data BYTEA NOT NULL,
    checksum TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (run_id, step)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    total_steps INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    framework TEXT DEFAULT 'generic',
    model TEXT DEFAULT '',
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_run_id ON checkpoints (run_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs (status);
"""


class PostgresStorageBackend(StorageBackend):
    """PostgreSQL storage backend with connection pooling.

    Requires: pip install agentcheckpoint[postgres]
    """

    def __init__(
        self,
        conninfo: str = "",
        host: str | None = None,
        port: int = 5432,
        dbname: str = "agentcheckpoint",
        user: str | None = None,
        password: str | None = None,
        min_pool_size: int = 2,
        max_pool_size: int = 10,
        auto_create_schema: bool = True,
    ):
        try:
            import psycopg
            from psycopg_pool import ConnectionPool
        except ImportError:
            raise ImportError(
                "psycopg is required for Postgres storage. "
                "Install with: pip install agentcheckpoint[postgres]"
            )

        if conninfo:
            self._conninfo = conninfo
        else:
            parts = []
            if host:
                parts.append(f"host={host}")
            parts.append(f"port={port}")
            parts.append(f"dbname={dbname}")
            if user:
                parts.append(f"user={user}")
            if password:
                parts.append(f"password={password}")
            self._conninfo = " ".join(parts)

        self._pool = ConnectionPool(
            self._conninfo,
            min_size=min_pool_size,
            max_size=max_pool_size,
        )

        if auto_create_schema:
            self._init_schema()

    def _init_schema(self) -> None:
        with self._pool.connection() as conn:
            conn.execute(SCHEMA_SQL)
            conn.commit()

    def save(self, run_id: str, step: int, data: bytes, metadata: dict | None = None) -> None:
        checksum = hashlib.sha256(data).hexdigest()[:16]
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (run_id, step, data, checksum, size_bytes, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, step) DO UPDATE SET
                    data = EXCLUDED.data,
                    checksum = EXCLUDED.checksum,
                    size_bytes = EXCLUDED.size_bytes,
                    metadata = EXCLUDED.metadata,
                    created_at = NOW()
                """,
                (run_id, step, data, checksum, len(data), json.dumps(metadata or {})),
            )
            conn.commit()

    def load(self, run_id: str, step: int) -> bytes:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT data FROM checkpoints WHERE run_id = %s AND step = %s",
                (run_id, step),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Checkpoint not found: run={run_id}, step={step}")
        return bytes(row[0])

    def list_runs(self) -> list[RunInfo]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT run_id, created_at, updated_at, total_steps, status, "
                "framework, model, metadata FROM runs ORDER BY updated_at DESC"
            ).fetchall()
        return [
            RunInfo(
                run_id=r[0],
                created_at=r[1].isoformat() if r[1] else "",
                updated_at=r[2].isoformat() if r[2] else "",
                total_steps=r[3],
                status=r[4],
                framework=r[5] or "generic",
                model=r[6] or "",
                metadata=r[7] or {},
            )
            for r in rows
        ]

    def list_steps(self, run_id: str) -> list[StepInfo]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT step, created_at, checksum, size_bytes FROM checkpoints "
                "WHERE run_id = %s ORDER BY step",
                (run_id,),
            ).fetchall()
        return [
            StepInfo(
                step_number=r[0],
                timestamp=r[1].isoformat() if r[1] else "",
                checksum=r[2],
                size_bytes=r[3],
            )
            for r in rows
        ]

    def delete_run(self, run_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM checkpoints WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))
            conn.commit()

    def delete_step(self, run_id: str, step: int) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "DELETE FROM checkpoints WHERE run_id = %s AND step = %s",
                (run_id, step),
            )
            conn.commit()

    def save_run_meta(self, run_info: RunInfo) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO runs (run_id, created_at, updated_at, total_steps, status,
                                  framework, model, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    updated_at = EXCLUDED.updated_at,
                    total_steps = EXCLUDED.total_steps,
                    status = EXCLUDED.status,
                    framework = EXCLUDED.framework,
                    model = EXCLUDED.model,
                    metadata = EXCLUDED.metadata
                """,
                (
                    run_info.run_id,
                    run_info.created_at,
                    run_info.updated_at,
                    run_info.total_steps,
                    run_info.status,
                    run_info.framework,
                    run_info.model,
                    json.dumps(run_info.metadata),
                ),
            )
            conn.commit()

    def load_run_meta(self, run_id: str) -> Optional[RunInfo]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT run_id, created_at, updated_at, total_steps, status, "
                "framework, model, metadata FROM runs WHERE run_id = %s",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return RunInfo(
            run_id=row[0],
            created_at=row[1].isoformat() if row[1] else "",
            updated_at=row[2].isoformat() if row[2] else "",
            total_steps=row[3],
            status=row[4],
            framework=row[5] or "generic",
            model=row[6] or "",
            metadata=row[7] or {},
        )

    def close(self) -> None:
        """Close the connection pool."""
        self._pool.close()
