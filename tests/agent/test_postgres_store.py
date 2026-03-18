import asyncio
import os
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/agent/main"))

from postgres_store import PostgresRunStore, PostgresSessionStore
from sessions import ShadowRunStore, ShadowSessionStore


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class PostgresHarness:
    def __init__(self):
        self.port = _free_port()
        self.tempdir = tempfile.TemporaryDirectory(prefix="lucas-postgres-")
        self.datadir = Path(self.tempdir.name) / "data"
        self.logfile = Path(self.tempdir.name) / "postgres.log"
        self.env = {
            "POSTGRES_HOST": "127.0.0.1",
            "POSTGRES_PORT": str(self.port),
            "POSTGRES_DB": "lucas",
            "POSTGRES_USER": "lucas",
            "POSTGRES_PASSWORD": "lucas",
            "POSTGRES_SSLMODE": "disable",
        }

    def start(self):
        self.datadir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "initdb",
                "-D",
                str(self.datadir),
                "-U",
                "lucas",
                "-A",
                "trust",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        conf = self.datadir / "postgresql.conf"
        conf.write_text(conf.read_text() + f"\nport = {self.port}\nlisten_addresses = '127.0.0.1'\n")
        subprocess.run(
            [
                "pg_ctl",
                "-D",
                str(self.datadir),
                "-l",
                str(self.logfile),
                "start",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        deadline = time.time() + 30
        while time.time() < deadline:
            result = subprocess.run(
                ["pg_isready", "-h", "127.0.0.1", "-p", str(self.port), "-U", "lucas", "-d", "postgres"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                subprocess.run(
                    [
                        "createdb",
                        "-h",
                        "127.0.0.1",
                        "-p",
                        str(self.port),
                        "-U",
                        "lucas",
                        "lucas",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return
            time.sleep(1)
        raise RuntimeError("Postgres test harness did not become ready")

    def stop(self):
        subprocess.run(["pg_ctl", "-D", str(self.datadir), "stop", "-m", "immediate"], check=False, capture_output=True, text=True)
        self.tempdir.cleanup()


class PostgresStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.harness = PostgresHarness()
        cls.harness.start()
        cls.old_env = {key: os.environ.get(key) for key in cls.harness.env}
        os.environ.update(cls.harness.env)

    @classmethod
    def tearDownClass(cls):
        for key, value in cls.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cls.harness.stop()

    def test_create_and_update_run_in_postgres(self):
        async def scenario():
            store = PostgresRunStore()
            await store.connect()
            run_id = await store.create_run("default", mode="report")
            await store.update_run(run_id, status="issues_found", pod_count=2, error_count=1, fix_count=0, report="report", log="log")
            row = await store._db_conn().fetchrow("SELECT namespace, status, pod_count, error_count, report, log FROM runs WHERE id = $1", run_id)
            await store.close()
            return row

        row = asyncio.run(scenario())
        self.assertEqual(row["namespace"], "default")
        self.assertEqual(row["status"], "issues_found")
        self.assertEqual(row["pod_count"], 2)
        self.assertEqual(row["error_count"], 1)
        self.assertEqual(row["report"], "report")
        self.assertEqual(row["log"], "log")

    def test_store_and_read_session_mapping_in_postgres(self):
        async def scenario():
            store = PostgresSessionStore()
            await store.connect()
            await store.save_session("123.45", "sess-1", "C123", namespace="default")
            session_id = await store.get_session("123.45")
            channel = await store.get_channel("123.45")
            count = await store.get_session_count()
            await store.close()
            return session_id, channel, count

        session_id, channel, count = asyncio.run(scenario())
        self.assertEqual(session_id, "sess-1")
        self.assertEqual(channel, "C123")
        self.assertEqual(count, 1)

    def test_store_run_summaries_in_postgres(self):
        async def scenario():
            store = PostgresRunStore()
            await store.connect()
            run_id = await store.create_run("all", mode="report")
            await store.update_run(run_id, status="issues_found", pod_count=12, error_count=2, fix_count=0, report="all report", log="all log")
            await store.replace_run_summaries(
                run_id,
                [
                    {"namespace": "default", "mode": "report", "status": "issues_found", "pod_count": 10, "error_count": 2, "fix_count": 0, "summary": "2 issues"},
                    {"namespace": "redis", "mode": "report", "status": "ok", "pod_count": 2, "error_count": 0, "fix_count": 0, "summary": "no issues"},
                ],
            )
            rows = await store._db_conn().fetch("SELECT namespace, status, pod_count, summary FROM run_summaries WHERE parent_run_id = $1 ORDER BY namespace", run_id)
            await store.close()
            return rows

        rows = asyncio.run(scenario())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["namespace"], "default")
        self.assertEqual(rows[1]["namespace"], "redis")

    def test_shadow_run_store_writes_primary_and_mirror(self):
        class FakeRunStore:
            def __init__(self):
                self.calls = []

            async def connect(self):
                self.calls.append(("connect",))

            async def close(self):
                self.calls.append(("close",))

            async def create_run(self, namespace, mode="autonomous"):
                self.calls.append(("create_run", namespace, mode))
                return 11 if namespace == "default" else 22

            async def update_run(self, **kwargs):
                self.calls.append(("update_run", kwargs))

            async def record_fix(self, **kwargs):
                self.calls.append(("record_fix", kwargs))

            async def record_token_usage(self, **kwargs):
                self.calls.append(("record_token_usage", kwargs))

            async def record_recovery_action(self, **kwargs):
                self.calls.append(("record_recovery_action", kwargs))

            async def get_latest_recovery_action(self, *args, **kwargs):
                self.calls.append(("get_latest_recovery_action", args, kwargs))
                return {"status": "primary"}

            async def replace_run_summaries(self, parent_run_id, rows):
                self.calls.append(("replace_run_summaries", parent_run_id, rows))

        async def scenario():
            primary = FakeRunStore()
            mirror = FakeRunStore()
            store = ShadowRunStore(primary=primary, mirror=mirror)
            await store.connect()
            run_id = await store.create_run("default", mode="report")
            await store.update_run(run_id=run_id, status="ok")
            await store.record_fix(run_id=run_id, namespace="default", pod_name="p", error_type="x")
            await store.record_token_usage(run_id=run_id, namespace="default", model="m", input_tokens=1, output_tokens=2, cost=0.1)
            await store.record_recovery_action(namespace="default", workload_kind="Deployment", workload_name="x", pod_name="p", action="noop", status="ok")
            await store.replace_run_summaries(run_id, [{"namespace": "default"}])
            action = await store.get_latest_recovery_action("default", "Deployment", "x")
            return primary.calls, mirror.calls, action

        primary_calls, mirror_calls, action = asyncio.run(scenario())
        self.assertEqual(action["status"], "primary")
        self.assertIn(("create_run", "default", "report"), primary_calls)
        self.assertIn(("create_run", "default", "report"), mirror_calls)
        self.assertTrue(any(call[0] == "replace_run_summaries" for call in mirror_calls))

    def test_shadow_session_store_reads_from_primary_and_mirrors_writes(self):
        class FakeSessionStore:
            def __init__(self):
                self.calls = []

            async def connect(self):
                self.calls.append(("connect",))

            async def close(self):
                self.calls.append(("close",))

            async def save_session(self, *args, **kwargs):
                self.calls.append(("save_session", args, kwargs))

            async def get_session(self, thread_ts):
                self.calls.append(("get_session", thread_ts))
                return "sess-primary"

            async def get_channel(self, thread_ts):
                self.calls.append(("get_channel", thread_ts))
                return "C123"

            async def has_session(self, thread_ts):
                self.calls.append(("has_session", thread_ts))
                return True

            async def delete_session(self, thread_ts):
                self.calls.append(("delete_session", thread_ts))

            async def cleanup_old_sessions(self, days=7):
                self.calls.append(("cleanup_old_sessions", days))
                return 1

            async def get_session_count(self):
                self.calls.append(("get_session_count",))
                return 2

        async def scenario():
            primary = FakeSessionStore()
            mirror = FakeSessionStore()
            store = ShadowSessionStore(primary=primary, mirror=mirror)
            await store.connect()
            await store.save_session("1", "sess", "C123")
            session_id = await store.get_session("1")
            await store.delete_session("1")
            count = await store.get_session_count()
            return primary.calls, mirror.calls, session_id, count

        primary_calls, mirror_calls, session_id, count = asyncio.run(scenario())
        self.assertEqual(session_id, "sess-primary")
        self.assertEqual(count, 2)
        self.assertTrue(any(call[0] == "save_session" for call in mirror_calls))
        self.assertTrue(any(call[0] == "delete_session" for call in mirror_calls))


if __name__ == "__main__":
    unittest.main()
