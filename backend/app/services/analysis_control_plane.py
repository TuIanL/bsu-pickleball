"""跨进程分析任务控制面。

任务摘要和大型分析产物继续分离：本模块只保存用于调度、心跳、取消和恢复的
JSON payload 以及少量可索引字段。每次操作使用独立 SQLite connection，避免
Web API 与 analysis-worker 共享进程内缓存。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any


PayloadMutator = Callable[[dict[str, Any]], dict[str, Any] | None]
PayloadSelector = Callable[[dict[str, Any]], bool]


class AnalysisControlPlane:
    """为 JobStore 提供带条件更新的 SQLite 控制面。"""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    job_id TEXT PRIMARY KEY,
                    canonical_status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT,
                    queued_at TEXT,
                    updated_at TEXT,
                    worker_id TEXT,
                    worker_pid INTEGER,
                    worker_run_id TEXT,
                    claimed_at TEXT,
                    worker_heartbeat_at TEXT,
                    last_progress_at TEXT,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    cancel_requested_at TEXT,
                    interrupted_at TEXT,
                    interruption_code TEXT,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_analysis_jobs_queue "
                "ON analysis_jobs (canonical_status, priority DESC, queued_at, created_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_analysis_jobs_heartbeat "
                "ON analysis_jobs (canonical_status, worker_heartbeat_at)"
            )

    @staticmethod
    def _columns(payload: dict[str, Any]) -> tuple[Any, ...]:
        return (
            payload.get("id"),
            payload.get("canonicalStatus", "queued"),
            int(payload.get("priority") or 0),
            payload.get("createdAt"),
            payload.get("queuedAt"),
            payload.get("updatedAt"),
            payload.get("workerId"),
            payload.get("workerPid"),
            payload.get("workerRunId"),
            payload.get("claimedAt"),
            payload.get("workerHeartbeatAt"),
            payload.get("lastProgressAt"),
            int(payload.get("attempt") or 0),
            payload.get("cancelRequestedAt"),
            payload.get("interruptedAt"),
            payload.get("interruptionCode"),
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
        )

    @staticmethod
    def _payload_from_row(row: sqlite3.Row) -> dict[str, Any]:
        payload = json.loads(row["payload_json"])
        if not isinstance(payload, dict):
            raise ValueError("analysis control payload must be an object")
        # 索引字段是跨进程条件更新的权威投影，读取时覆盖 payload 中可能过时的值。
        mapping = {
            "canonicalStatus": "canonical_status",
            "priority": "priority",
            "createdAt": "created_at",
            "queuedAt": "queued_at",
            "updatedAt": "updated_at",
            "workerId": "worker_id",
            "workerPid": "worker_pid",
            "workerRunId": "worker_run_id",
            "claimedAt": "claimed_at",
            "workerHeartbeatAt": "worker_heartbeat_at",
            "lastProgressAt": "last_progress_at",
            "attempt": "attempt",
            "cancelRequestedAt": "cancel_requested_at",
            "interruptedAt": "interrupted_at",
            "interruptionCode": "interruption_code",
        }
        for payload_key, column in mapping.items():
            payload[payload_key] = row[column]
        return payload

    def _upsert_in_connection(self, connection: sqlite3.Connection, payload: dict[str, Any]) -> None:
        connection.execute(
            """
            INSERT INTO analysis_jobs (
                job_id, canonical_status, priority, created_at, queued_at, updated_at,
                worker_id, worker_pid, worker_run_id, claimed_at, worker_heartbeat_at,
                last_progress_at, attempt, cancel_requested_at, interrupted_at,
                interruption_code, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                canonical_status=excluded.canonical_status,
                priority=excluded.priority,
                created_at=excluded.created_at,
                queued_at=excluded.queued_at,
                updated_at=excluded.updated_at,
                worker_id=excluded.worker_id,
                worker_pid=excluded.worker_pid,
                worker_run_id=excluded.worker_run_id,
                claimed_at=excluded.claimed_at,
                worker_heartbeat_at=excluded.worker_heartbeat_at,
                last_progress_at=excluded.last_progress_at,
                attempt=excluded.attempt,
                cancel_requested_at=excluded.cancel_requested_at,
                interrupted_at=excluded.interrupted_at,
                interruption_code=excluded.interruption_code,
                payload_json=excluded.payload_json
            """,
            self._columns(payload),
        )

    def upsert(self, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._upsert_in_connection(connection, payload)
            connection.execute("COMMIT")

    def insert_if_missing(self, payload: dict[str, Any]) -> bool:
        values = self._columns(payload)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO analysis_jobs (
                    job_id, canonical_status, priority, created_at, queued_at, updated_at,
                    worker_id, worker_pid, worker_run_id, claimed_at, worker_heartbeat_at,
                    last_progress_at, attempt, cancel_requested_at, interrupted_at,
                    interruption_code, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            connection.execute("COMMIT")
            return cursor.rowcount == 1

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM analysis_jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._payload_from_row(row) if row is not None else None

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM analysis_jobs "
                "ORDER BY COALESCE(updated_at, created_at) DESC, created_at DESC, job_id DESC"
            ).fetchall()
        return [self._payload_from_row(row) for row in rows]

    def mutate(
        self,
        job_id: str,
        mutator: PayloadMutator,
        *,
        expected_status: str | None = None,
        expected_worker_run_id: str | None = None,
        require_worker_run_id: bool = False,
    ) -> dict[str, Any] | None:
        """在同一 SQLite transaction 内读取、校验、修改并写回一条任务。"""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM analysis_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                connection.execute("ROLLBACK")
                return None
            current = self._payload_from_row(row)
            if expected_status is not None and current.get("canonicalStatus") != expected_status:
                connection.execute("ROLLBACK")
                return None
            if require_worker_run_id and expected_worker_run_id is None:
                connection.execute("ROLLBACK")
                return None
            if expected_worker_run_id is not None and current.get("workerRunId") != expected_worker_run_id:
                connection.execute("ROLLBACK")
                return None
            updated = mutator(dict(current))
            if updated is None:
                connection.execute("ROLLBACK")
                return None
            self._upsert_in_connection(connection, updated)
            connection.execute("COMMIT")
            return updated

    def mutate_next(self, selector: PayloadSelector, mutator: PayloadMutator) -> dict[str, Any] | None:
        """原子选择并修改一个 queued 任务，适合多个 Worker 竞争 claim。"""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT * FROM analysis_jobs WHERE canonical_status = 'queued' "
                "ORDER BY priority DESC, COALESCE(queued_at, created_at), created_at, job_id"
            ).fetchall()
            for row in rows:
                current = self._payload_from_row(row)
                if not selector(current):
                    continue
                updated = mutator(dict(current))
                if updated is None:
                    continue
                self._upsert_in_connection(connection, updated)
                connection.execute("COMMIT")
                return updated
            connection.execute("ROLLBACK")
            return None

    def delete(self, job_id: str) -> bool:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute("DELETE FROM analysis_jobs WHERE job_id = ?", (job_id,))
            connection.execute("COMMIT")
            return cursor.rowcount == 1

    def import_legacy(self, payloads: Iterable[dict[str, Any]]) -> int:
        imported = 0
        for payload in payloads:
            if self.insert_if_missing(payload):
                imported += 1
        return imported
