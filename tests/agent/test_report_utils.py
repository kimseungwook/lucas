import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/agent/main"))

from report_utils import extract_report_payload, format_slack_scan_message, parse_run_report


class ReportUtilsTests(unittest.TestCase):
    def test_extract_report_payload_reads_marked_json(self):
        report, full_log = extract_report_payload(
            'prefix\n===REPORT_START===\n{"pod_count": 2, "error_count": 1, "fix_count": 0, "status": "issues_found", "summary": "one issue", "details": []}\n===REPORT_END===\nsuffix'
        )
        self.assertIn('"pod_count": 2', report)
        self.assertIn('prefix', full_log)

    def test_parse_run_report_parses_json_details(self):
        parsed = parse_run_report('{"scope": "all", "run_id": 10, "total_pods": 2, "pod_count": 2, "issues": 1, "error_count": 1, "fix_count": 0, "status": "issues_found", "summary": "one issue", "pods_with_restarts": 1, "status_breakdown": {"Running": 1, "Pending": 1}, "reason_breakdown": {"CrashLoopBackOff": 1}, "top_problematic_pods": [{"namespace": "default", "pod": "api", "phase": "Running", "reason": "CrashLoopBackOff", "restarts": 1}], "details": [{"pod": "api", "issue": "CrashLoopBackOff"}], "drift_summary": {"runtime": 1}, "drifts": [{"type": "runtime.config_mismatch"}]}')
        self.assertEqual(parsed["pod_count"], 2)
        self.assertEqual(parsed["error_count"], 1)
        self.assertEqual(parsed["status"], "issues_found")
        self.assertEqual(parsed["details"][0]["pod"], "api")
        self.assertEqual(parsed["pods_with_restarts"], 1)
        self.assertEqual(parsed["status_breakdown"]["Pending"], 1)
        self.assertEqual(parsed["reason_breakdown"]["CrashLoopBackOff"], 1)
        self.assertEqual(parsed["drift_summary"]["runtime"], 1)
        self.assertEqual(parsed["drifts"][0]["type"], "runtime.config_mismatch")

    def test_format_slack_scan_message_avoids_transcript_summary(self):
        text = format_slack_scan_message(
            status="issues_found",
            namespace="default",
            run_id=20,
            summary="### Checking Pods\nbash kubectl get pods -n default\nOutput:",
            pod_count=3,
            error_count=1,
            details=[{"pod": "node-debugger", "issue": "Failed", "severity": "critical", "recommendation": "Delete the failed pod"}],
            pods_with_restarts=1,
            status_breakdown={"Running": 2, "Pending": 1},
            reason_breakdown={"Error": 1},
            top_problematic_pods=[{"namespace": "default", "pod": "node-debugger", "phase": "Failed", "reason": "Error", "restarts": 1}],
            drift_summary={"storage": 1, "code": 0, "runtime": 1},
            drifts=[{"type": "storage.node_placement_mismatch", "severity": "high", "resource": "deployment/a2w-lucas-agent", "likely_cause": "node placement drift"}],
        )
        self.assertIn("scope=default run=20", text)
        self.assertIn("total_pods=3 issues=1 pods_with_restarts=1", text)
        self.assertIn("status_breakdown", text)
        self.assertIn("- Pending: 1", text)
        self.assertIn("reason_breakdown", text)
        self.assertIn("- Error: 1", text)
        self.assertIn("default/node-debugger: Failed / Error / restarts=1", text)
        self.assertIn("drift_summary", text)
        self.assertIn("- runtime: 1", text)
        self.assertIn("top_drifts", text)
        self.assertIn("storage.node_placement_mismatch", text)
        self.assertNotIn("bash kubectl", text)
        self.assertIn("Lucas 정기 점검", text)
        self.assertIn("summary", text)

    def test_format_slack_scan_message_limits_drift_lines(self):
        text = format_slack_scan_message(
            status="issues_found",
            namespace="default",
            run_id=21,
            summary="drift summary",
            pod_count=1,
            error_count=0,
            details=[],
            drift_summary={"storage": 2},
            drifts=[
                {"type": "storage.attach_failure", "severity": "high", "resource": "pod/a", "likely_cause": "attach failed"},
                {"type": "code.runtime_surface_mismatch", "severity": "medium", "resource": "configmap/x", "likely_cause": "code mismatch"},
                {"type": "runtime.config_mismatch", "severity": "medium", "resource": "cronjob/a2w-lucas", "likely_cause": "provider mismatch"},
                {"type": "runtime.secret_ref_mismatch", "severity": "medium", "resource": "deployment/a2w-lucas-agent", "likely_cause": "secret mismatch"},
            ],
        )
        self.assertIn("storage.attach_failure", text)
        self.assertIn("code.runtime_surface_mismatch", text)
        self.assertIn("runtime.config_mismatch", text)
        self.assertNotIn("runtime.secret_ref_mismatch", text)


if __name__ == "__main__":
    unittest.main()
