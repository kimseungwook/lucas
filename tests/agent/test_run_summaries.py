import asyncio
import sqlite3
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


class _CursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def fetchone(self):
        return self._cursor.fetchone()

    async def fetchall(self):
        return self._cursor.fetchall()

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    def __await__(self):
        async def _identity():
            return self

        return _identity().__await__()


class _ConnectionWrapper:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path)

    def execute(self, query, params=()):
        cursor = self._conn.execute(query, params)
        return _CursorWrapper(cursor)

    async def commit(self):
        self._conn.commit()

    async def close(self):
        self._conn.close()


async def _connect(path: str):
    return _ConnectionWrapper(path)


sys.modules.setdefault("aiosqlite", SimpleNamespace(connect=_connect))

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/agent/main"))

from run_summaries import build_namespace_summary_rows
from sessions import RunStore


class NamespaceSummaryTests(unittest.TestCase):
    def test_build_namespace_summary_rows_for_all_scan(self):
        rows = build_namespace_summary_rows(
            101,
            {
                "summary": {
                    "default": {"pods": 10, "issues": 2, "restarts": 1},
                    "redis": {"pods": 2, "issues": 0, "restarts": 0},
                }
            },
            mode="report",
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["parent_run_id"], 101)
        self.assertEqual(rows[0]["namespace"], "default")
        self.assertEqual(rows[0]["status"], "issues_found")
        self.assertEqual(rows[1]["status"], "ok")

    def test_replace_run_summaries_persists_rows(self):
        async def scenario():
            store = RunStore(db_path=":memory:")
            await store.connect()
            run_id = await store.create_run("all", mode="report")
            await store.replace_run_summaries(
                run_id,
                [
                    {
                        "namespace": "default",
                        "status": "issues_found",
                        "pod_count": 10,
                        "error_count": 2,
                        "fix_count": 0,
                        "summary": "주의가 필요한 파드가 2건 있습니다.",
                        "mode": "report",
                    },
                    {
                        "namespace": "redis",
                        "status": "ok",
                        "pod_count": 2,
                        "error_count": 0,
                        "fix_count": 0,
                        "summary": "조치가 필요한 이슈가 발견되지 않았습니다.",
                        "mode": "report",
                    },
                ],
            )
            db = store._db_conn()
            async with db.execute("SELECT parent_run_id, namespace, status, pod_count, error_count, fix_count, summary FROM run_summaries ORDER BY namespace") as cursor:
                rows = await cursor.fetchall()
            await store.close()
            return rows

        rows = asyncio.run(scenario())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(rows[0][1], "default")
        self.assertEqual(rows[1][1], "redis")


if __name__ == "__main__":
    unittest.main()
