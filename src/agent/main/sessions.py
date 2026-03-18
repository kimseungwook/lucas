"""Session and run store for the Lucas agent."""

import importlib
import os
from datetime import datetime
from typing import Any, Optional

aiosqlite = importlib.import_module("aiosqlite")


class RunStore:
    """Store for recording Lucas runs to the dashboard database."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.environ.get("SQLITE_PATH", "/data/lucas.db")
        self._db: Any | None = None

    def _db_conn(self) -> Any:
        if self._db is None:
            raise RuntimeError("RunStore is not connected")
        return self._db

    async def connect(self):
        """Initialize database connection and ensure tables exist."""
        self._db = await aiosqlite.connect(self.db_path)
        db = self._db_conn()
        # Ensure runs table exists (same schema as CronJob uses)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                namespace TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'autonomous',
                status TEXT NOT NULL DEFAULT 'running',
                pod_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                fix_count INTEGER DEFAULT 0,
                report TEXT,
                log TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fixes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                timestamp TEXT NOT NULL,
                namespace TEXT NOT NULL,
                pod_name TEXT NOT NULL,
                error_type TEXT NOT NULL,
                error_message TEXT,
                fix_applied TEXT,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (run_id) REFERENCES runs(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                namespace TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                cost REAL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS recovery_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace TEXT NOT NULL,
                workload_kind TEXT NOT NULL,
                workload_name TEXT NOT NULL,
                pod_name TEXT,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS run_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_run_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                namespace TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'report',
                status TEXT NOT NULL,
                pod_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                fix_count INTEGER DEFAULT 0,
                summary TEXT,
                FOREIGN KEY (parent_run_id) REFERENCES runs(id)
            )
        """)
        await db.commit()

    async def close(self):
        """Close database connection."""
        if self._db:
            await self._db.close()

    async def create_run(self, namespace: str, mode: str = "autonomous") -> int:
        """Create a new run record and return its ID."""
        db = self._db_conn()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        cursor = await db.execute(
            """INSERT INTO runs (started_at, namespace, mode, status)
               VALUES (?, ?, ?, 'running')""",
            (now, namespace, mode)
        )
        await db.commit()
        return cursor.lastrowid

    async def update_run(
        self,
        run_id: int,
        status: str = "ok",
        pod_count: int = 0,
        error_count: int = 0,
        fix_count: int = 0,
        report: str | None = None,
        log: str | None = None
    ):
        """Update a run record with results."""
        db = self._db_conn()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            """UPDATE runs SET
               ended_at = ?,
               status = ?,
               pod_count = ?,
               error_count = ?,
               fix_count = ?,
               report = ?,
               log = ?
               WHERE id = ?""",
            (now, status, pod_count, error_count, fix_count, report, log, run_id)
        )
        await db.commit()

    async def record_fix(
        self,
        run_id: int,
        namespace: str,
        pod_name: str,
        error_type: str,
        error_message: str | None = None,
        fix_applied: str | None = None,
        status: str = "pending"
    ):
        """Record a fix attempt."""
        db = self._db_conn()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            """INSERT INTO fixes (run_id, timestamp, namespace, pod_name, error_type, error_message, fix_applied, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, now, namespace, pod_name, error_type, error_message, fix_applied, status)
        )
        await db.commit()

    async def record_token_usage(
        self,
        run_id: int,
        namespace: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float
    ):
        """Record token usage for a run."""
        db = self._db_conn()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        total_tokens = input_tokens + output_tokens
        await db.execute(
            """INSERT INTO token_usage (run_id, namespace, model, input_tokens, output_tokens, total_tokens, cost, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, namespace, model, input_tokens, output_tokens, total_tokens, cost, now)
        )
        await db.commit()

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
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            """INSERT INTO recovery_actions (namespace, workload_kind, workload_name, pod_name, action, status, reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (namespace, workload_kind, workload_name, pod_name, action, status, reason, now),
        )
        await db.commit()

    async def get_latest_recovery_action(self, namespace: str, workload_kind: str, workload_name: str) -> Optional[dict[str, str]]:
        db = self._db_conn()
        async with db.execute(
            """SELECT created_at, action, status, reason, pod_name
               FROM recovery_actions
               WHERE namespace = ? AND workload_kind = ? AND workload_name = ?
               ORDER BY id DESC LIMIT 1""",
            (namespace, workload_kind, workload_name),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "created_at": row[0],
                "action": row[1],
                "status": row[2],
                "reason": row[3],
                "pod_name": row[4],
            }

    async def replace_run_summaries(self, parent_run_id: int, rows: list[dict[str, Any]]):
        db = self._db_conn()
        await db.execute("DELETE FROM run_summaries WHERE parent_run_id = ?", (parent_run_id,))
        async with db.execute(
            "SELECT started_at, ended_at FROM runs WHERE id = ?",
            (parent_run_id,),
        ) as cursor:
            parent_row = await cursor.fetchone()
        started_at = parent_row[0] if parent_row and parent_row[0] else datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        ended_at = parent_row[1] if parent_row else None
        for row in rows:
            await db.execute(
                """INSERT INTO run_summaries (parent_run_id, started_at, ended_at, namespace, mode, status, pod_count, error_count, fix_count, summary)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
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
                ),
            )
        await db.commit()


class SessionStore:
    """SQLite-based session store."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.environ.get("SQLITE_PATH", "/data/lucas.db")
        self._db: Any | None = None

    def _db_conn(self) -> Any:
        if self._db is None:
            raise RuntimeError("SessionStore is not connected")
        return self._db

    async def connect(self):
        """Initialize database connection and create tables."""
        self._db = await aiosqlite.connect(self.db_path)
        db = self._db_conn()
        await db.execute("""
            CREATE TABLE IF NOT EXISTS slack_sessions (
                thread_ts TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                namespace TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await db.commit()

    async def close(self):
        """Close database connection."""
        if self._db:
            await self._db.close()

    async def save_session(
        self,
        thread_ts: str,
        session_id: str,
        channel: str,
        namespace: str | None = None
    ):
        """Save or update a session mapping."""
        db = self._db_conn()
        now = datetime.utcnow().isoformat()
        await db.execute("""
            INSERT INTO slack_sessions (thread_ts, session_id, channel, namespace, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(thread_ts) DO UPDATE SET
                session_id = excluded.session_id,
                updated_at = excluded.updated_at
        """, (thread_ts, session_id, channel, namespace, now, now))
        await db.commit()

    async def get_session(self, thread_ts: str) -> Optional[str]:
        """Get session ID for a thread."""
        db = self._db_conn()
        async with db.execute(
            "SELECT session_id FROM slack_sessions WHERE thread_ts = ?",
            (thread_ts,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def get_channel(self, thread_ts: str) -> Optional[str]:
        """Get channel for a thread."""
        db = self._db_conn()
        async with db.execute(
            "SELECT channel FROM slack_sessions WHERE thread_ts = ?",
            (thread_ts,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def has_session(self, thread_ts: str) -> bool:
        """Check if a thread has an associated session."""
        return await self.get_session(thread_ts) is not None

    async def delete_session(self, thread_ts: str):
        """Delete a session mapping."""
        db = self._db_conn()
        await db.execute(
            "DELETE FROM slack_sessions WHERE thread_ts = ?",
            (thread_ts,)
        )
        await db.commit()

    async def cleanup_old_sessions(self, days: int = 7) -> int:
        """Remove sessions older than specified days. Returns count deleted."""
        db = self._db_conn()
        cursor = await db.execute("""
            DELETE FROM slack_sessions
            WHERE datetime(updated_at) < datetime('now', ?)
        """, (f"-{days} days",))
        await db.commit()
        return cursor.rowcount

    async def get_session_count(self) -> int:
        """Get total number of sessions."""
        db = self._db_conn()
        async with db.execute("SELECT COUNT(*) FROM slack_sessions") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
