from __future__ import annotations

import importlib
import os
from datetime import datetime
from typing import Any, Optional

asyncpg = importlib.import_module("asyncpg")


def _connection_kwargs(
    *,
    host: str | None = None,
    port: int | None = None,
    database: str | None = None,
    user: str | None = None,
    password: str | None = None,
    sslmode: str | None = None,
) -> dict[str, Any]:
    ssl = None if (sslmode or os.environ.get("POSTGRES_SSLMODE", "disable")).lower() == "disable" else "require"
    return {
        "host": host or os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "port": port or int(os.environ.get("POSTGRES_PORT", "5432") or "5432"),
        "database": database or os.environ.get("POSTGRES_DB", "lucas"),
        "user": user or os.environ.get("POSTGRES_USER", "lucas"),
        "password": password or os.environ.get("POSTGRES_PASSWORD", ""),
        "ssl": ssl,
    }


class _BasePostgresStore:
    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
        user: str | None = None,
        password: str | None = None,
        sslmode: str | None = None,
    ):
        self._connect_kwargs = _connection_kwargs(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            sslmode=sslmode,
        )
        self._db: Any | None = None

    def _db_conn(self) -> Any:
        if self._db is None:
            raise RuntimeError(f"{self.__class__.__name__} is not connected")
        return self._db

    async def _connect(self):
        self._db = await asyncpg.connect(**self._connect_kwargs)

    async def close(self):
        if self._db is not None:
            await self._db.close()


class PostgresRunStore(_BasePostgresStore):

    async def connect(self):
        await self._connect()
        db = self._db_conn()
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id BIGSERIAL PRIMARY KEY,
                started_at TIMESTAMP NOT NULL,
                ended_at TIMESTAMP,
                namespace TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'autonomous',
                status TEXT NOT NULL DEFAULT 'running',
                pod_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                fix_count INTEGER DEFAULT 0,
                report TEXT,
                log TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS fixes (
                id BIGSERIAL PRIMARY KEY,
                run_id BIGINT REFERENCES runs(id),
                timestamp TIMESTAMP NOT NULL,
                namespace TEXT NOT NULL,
                pod_name TEXT NOT NULL,
                error_type TEXT NOT NULL,
                error_message TEXT,
                fix_applied TEXT,
                status TEXT DEFAULT 'pending'
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS token_usage (
                id BIGSERIAL PRIMARY KEY,
                run_id BIGINT REFERENCES runs(id),
                namespace TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                cost DOUBLE PRECISION DEFAULT 0,
                created_at TIMESTAMP NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS recovery_actions (
                id BIGSERIAL PRIMARY KEY,
                namespace TEXT NOT NULL,
                workload_kind TEXT NOT NULL,
                workload_name TEXT NOT NULL,
                pod_name TEXT,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT,
                created_at TIMESTAMP NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS run_summaries (
                id BIGSERIAL PRIMARY KEY,
                parent_run_id BIGINT NOT NULL REFERENCES runs(id),
                started_at TIMESTAMP NOT NULL,
                ended_at TIMESTAMP,
                namespace TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'report',
                status TEXT NOT NULL,
                pod_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                fix_count INTEGER DEFAULT 0,
                summary TEXT
            )
            """
        )

    async def create_run(self, namespace: str, mode: str = "autonomous") -> int:
        db = self._db_conn()
        now = datetime.utcnow()
        return int(
            await db.fetchval(
                """
                INSERT INTO runs (started_at, namespace, mode, status)
                VALUES ($1, $2, $3, 'running')
                RETURNING id
                """,
                now,
                namespace,
                mode,
            )
        )

    async def update_run(
        self,
        run_id: int,
        status: str = "ok",
        pod_count: int = 0,
        error_count: int = 0,
        fix_count: int = 0,
        report: str | None = None,
        log: str | None = None,
    ):
        db = self._db_conn()
        await db.execute(
            """
            UPDATE runs SET
                ended_at = $1,
                status = $2,
                pod_count = $3,
                error_count = $4,
                fix_count = $5,
                report = $6,
                log = $7
            WHERE id = $8
            """,
            datetime.utcnow(),
            status,
            pod_count,
            error_count,
            fix_count,
            report,
            log,
            run_id,
        )

    async def record_fix(
        self,
        run_id: int,
        namespace: str,
        pod_name: str,
        error_type: str,
        error_message: str | None = None,
        fix_applied: str | None = None,
        status: str = "pending",
    ):
        db = self._db_conn()
        await db.execute(
            """
            INSERT INTO fixes (run_id, timestamp, namespace, pod_name, error_type, error_message, fix_applied, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            run_id,
            datetime.utcnow(),
            namespace,
            pod_name,
            error_type,
            error_message,
            fix_applied,
            status,
        )

    async def record_token_usage(
        self,
        run_id: int,
        namespace: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
    ):
        db = self._db_conn()
        await db.execute(
            """
            INSERT INTO token_usage (run_id, namespace, model, input_tokens, output_tokens, total_tokens, cost, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            run_id,
            namespace,
            model,
            input_tokens,
            output_tokens,
            input_tokens + output_tokens,
            cost,
            datetime.utcnow(),
        )

    async def record_recovery_action(
        self,
        namespace: str,
        workload_kind: str,
        workload_name: str,
        pod_name: str | None,
        action: str,
        status: str,
        reason: str | None = None,
    ):
        db = self._db_conn()
        await db.execute(
            """
            INSERT INTO recovery_actions (namespace, workload_kind, workload_name, pod_name, action, status, reason, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            namespace,
            workload_kind,
            workload_name,
            pod_name,
            action,
            status,
            reason,
            datetime.utcnow(),
        )

    async def get_latest_recovery_action(self, namespace: str, workload_kind: str, workload_name: str) -> Optional[dict[str, str]]:
        db = self._db_conn()
        row = await db.fetchrow(
            """
            SELECT created_at, action, status, reason, pod_name
            FROM recovery_actions
            WHERE namespace = $1 AND workload_kind = $2 AND workload_name = $3
            ORDER BY id DESC LIMIT 1
            """,
            namespace,
            workload_kind,
            workload_name,
        )
        if row is None:
            return None
        return {
            "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M:%S") if row["created_at"] else "",
            "action": row["action"],
            "status": row["status"],
            "reason": row["reason"] or "",
            "pod_name": row["pod_name"] or "",
        }

    async def replace_run_summaries(self, parent_run_id: int, rows: list[dict[str, Any]]):
        db = self._db_conn()
        parent_row = await db.fetchrow("SELECT started_at, ended_at FROM runs WHERE id = $1", parent_run_id)
        started_at = parent_row["started_at"] if parent_row and parent_row["started_at"] else datetime.utcnow()
        ended_at = parent_row["ended_at"] if parent_row else None
        async with db.transaction():
            await db.execute("DELETE FROM run_summaries WHERE parent_run_id = $1", parent_run_id)
            for row in rows:
                await db.execute(
                    """
                    INSERT INTO run_summaries (parent_run_id, started_at, ended_at, namespace, mode, status, pod_count, error_count, fix_count, summary)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    parent_run_id,
                    started_at,
                    ended_at,
                    row.get("namespace", ""),
                    row.get("mode", "report"),
                    row.get("status", "ok"),
                    row.get("pod_count", 0),
                    row.get("error_count", 0),
                    row.get("fix_count", 0),
                    row.get("summary", ""),
                )


class PostgresSessionStore(_BasePostgresStore):

    async def connect(self):
        await self._connect()
        db = self._db_conn()
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS slack_sessions (
                thread_ts TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                namespace TEXT,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )

    async def save_session(
        self,
        thread_ts: str,
        session_id: str,
        channel: str,
        namespace: str | None = None,
    ):
        db = self._db_conn()
        now = datetime.utcnow()
        await db.execute(
            """
            INSERT INTO slack_sessions (thread_ts, session_id, channel, namespace, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $5)
            ON CONFLICT (thread_ts) DO UPDATE SET
                session_id = EXCLUDED.session_id,
                channel = EXCLUDED.channel,
                namespace = EXCLUDED.namespace,
                updated_at = EXCLUDED.updated_at
            """,
            thread_ts,
            session_id,
            channel,
            namespace,
            now,
        )

    async def get_session(self, thread_ts: str) -> Optional[str]:
        db = self._db_conn()
        return await db.fetchval("SELECT session_id FROM slack_sessions WHERE thread_ts = $1", thread_ts)

    async def get_channel(self, thread_ts: str) -> Optional[str]:
        db = self._db_conn()
        return await db.fetchval("SELECT channel FROM slack_sessions WHERE thread_ts = $1", thread_ts)

    async def has_session(self, thread_ts: str) -> bool:
        return await self.get_session(thread_ts) is not None

    async def delete_session(self, thread_ts: str):
        db = self._db_conn()
        await db.execute("DELETE FROM slack_sessions WHERE thread_ts = $1", thread_ts)

    async def cleanup_old_sessions(self, days: int = 7) -> int:
        db = self._db_conn()
        result = await db.execute(
            "DELETE FROM slack_sessions WHERE updated_at < (NOW() - ($1::text || ' days')::interval)",
            days,
        )
        return int(result.split()[-1]) if result else 0

    async def get_session_count(self) -> int:
        db = self._db_conn()
        value = await db.fetchval("SELECT COUNT(*) FROM slack_sessions")
        return int(value or 0)
