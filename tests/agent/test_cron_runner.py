import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/agent/main"))
sys.modules.setdefault("aiosqlite", MagicMock())

from cron_runner import build_stored_report_payload
from report_utils import extract_report_payload, parse_run_report


class CronRunnerTests(unittest.TestCase):
    def test_extract_report_payload_uses_marked_section(self):
        report, full_log = extract_report_payload(
            'prefix\n===REPORT_START==={"status":"ok","pod_count":3}\n===REPORT_END===\nsuffix'
        )
        self.assertIn('"status":"ok"', report)
        self.assertIn("prefix", full_log)

    def test_parse_run_report_handles_json_report(self):
        parsed = parse_run_report(
            '{"pod_count": 4, "error_count": 1, "fix_count": 0, "status": "issues_found", "summary": "One pod failing"}'
        )
        self.assertEqual((parsed["pod_count"], parsed["error_count"], parsed["fix_count"]), (4, 1, 0))
        self.assertEqual(parsed["status"], "issues_found")
        self.assertEqual(parsed["summary"], "One pod failing")

    def test_parse_run_report_uses_text_fallback(self):
        parsed = parse_run_report(
            "Found 7 pods and one CrashLoopBackOff issue requiring attention"
        )
        self.assertEqual(parsed["pod_count"], 7)
        self.assertEqual(parsed["error_count"], 1)
        self.assertEqual(parsed["status"], "issues_found")

    def test_build_stored_report_payload_includes_drift_fields(self):
        report = build_stored_report_payload(
            run_scope="default",
            run_id=42,
            status="issues_found",
            pod_count=3,
            error_count=1,
            fix_count=0,
            summary="storage drift detected",
            details=[{"pod": "default/api", "issue": "Pending"}],
            pods_with_restarts=1,
            status_breakdown={"Running": 2, "Pending": 1},
            reason_breakdown={"AttachVolume.Attach failed": 1},
            top_problematic_pods=[{"namespace": "default", "pod": "api", "phase": "Pending", "reason": "AttachVolume.Attach failed", "restarts": 0}],
            drift_audit={
                "status": "issues_found",
                "drift_summary": {"storage": 1, "code": 0, "runtime": 0},
                "drifts": [
                    {
                        "type": "storage.node_placement_mismatch",
                        "severity": "high",
                        "resource": "deployment/a2w-lucas-agent",
                        "evidence": ["selected-node=10.0.0.1"],
                        "likely_cause": "node placement drift",
                        "recommended_actions": ["pin workload to node pool"],
                    }
                ],
            },
        )
        parsed = parse_run_report(report)
        self.assertEqual(parsed["drift_summary"]["storage"], 1)
        self.assertEqual(parsed["drifts"][0]["type"], "storage.node_placement_mismatch")

    def test_build_stored_report_payload_includes_redis_recovery_fields(self):
        report = build_stored_report_payload(
            run_scope="cache",
            run_id=43,
            status="issues_found",
            pod_count=1,
            error_count=1,
            fix_count=0,
            summary="redis unhealthy",
            details=[{"pod": "cache/redis-0", "issue": "PING timeout"}],
            pods_with_restarts=1,
            status_breakdown={"Running": 1},
            reason_breakdown={"Readiness probe failed": 1},
            top_problematic_pods=[{"namespace": "cache", "pod": "redis-0", "phase": "Running", "reason": "Readiness probe failed", "restarts": 4}],
            redis_recovery={
                "redis_recovery_summary": {"evaluated": 1, "not_serving": 1, "suppressed": 0, "actions_taken": 1},
                "redis_recovery_findings": [
                    {
                        "type": "redis.safe_self_recovery",
                        "workload": "StatefulSet/redis",
                        "namespace": "cache",
                        "health": "not_serving",
                        "action": "delete_pod",
                        "target_pod": "redis-0",
                    }
                ],
            },
        )
        parsed = parse_run_report(report)
        self.assertEqual(parsed["redis_recovery_summary"]["actions_taken"], 1)
        self.assertEqual(parsed["redis_recovery_findings"][0]["action"], "delete_pod")


if __name__ == "__main__":
    unittest.main()
