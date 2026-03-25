import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/agent/main"))

from src.agent.main.report_utils import extract_report_payload, format_slack_scan_message, merge_pod_incident_report, parse_run_report


class ReportUtilsTests(unittest.TestCase):
    def test_extract_report_payload_reads_marked_json(self):
        report, full_log = extract_report_payload(
            'prefix\n===REPORT_START===\n{"pod_count": 2, "error_count": 1, "fix_count": 0, "status": "issues_found", "summary": "one issue", "details": []}\n===REPORT_END===\nsuffix'
        )
        self.assertIn('"pod_count": 2', report)
        self.assertIn('prefix', full_log)

    def test_parse_run_report_parses_json_details(self):
        parsed = parse_run_report('{"scope": "all", "run_id": 10, "total_pods": 2, "pod_count": 2, "issues": 1, "error_count": 1, "fix_count": 0, "status": "issues_found", "summary": "one issue", "pods_with_restarts": 1, "status_breakdown": {"Running": 1, "Pending": 1}, "reason_breakdown": {"CrashLoopBackOff": 1}, "top_problematic_pods": [{"namespace": "default", "pod": "api", "phase": "Running", "reason": "CrashLoopBackOff", "restarts": 1}], "details": [{"pod": "api", "issue": "CrashLoopBackOff"}], "drift_summary": {"runtime": 1}, "drifts": [{"type": "runtime.config_mismatch"}], "redis_recovery_summary": {"evaluated": 1, "not_serving": 1, "suppressed": 0, "actions_taken": 1}, "redis_recovery_findings": [{"action": "delete_pod"}], "security_suspicion_summary": {"findings": 1, "high": 1, "medium": 0, "evaluated_namespaces": 1}, "security_suspicion_findings": [{"type": "security.suspicious_behavior", "namespace": "payments"}], "pod_incident_summary": {"findings": 1, "high": 1, "medium": 0, "evaluated_namespaces": 1}, "pod_incident_findings": [{"type": "runtime.pod_incident", "namespace": "payments", "category": "config_or_secret_failure"}]}')
        self.assertEqual(parsed["pod_count"], 2)
        self.assertEqual(parsed["error_count"], 1)
        self.assertEqual(parsed["status"], "issues_found")
        self.assertEqual(parsed["details"][0]["pod"], "api")
        self.assertEqual(parsed["pods_with_restarts"], 1)
        self.assertEqual(parsed["status_breakdown"]["Pending"], 1)
        self.assertEqual(parsed["reason_breakdown"]["CrashLoopBackOff"], 1)
        self.assertEqual(parsed["drift_summary"]["runtime"], 1)
        self.assertEqual(parsed["drifts"][0]["type"], "runtime.config_mismatch")
        self.assertEqual(parsed["redis_recovery_summary"]["actions_taken"], 1)
        self.assertEqual(parsed["redis_recovery_findings"][0]["action"], "delete_pod")
        self.assertEqual(parsed["security_suspicion_summary"]["findings"], 1)
        self.assertEqual(parsed["security_suspicion_findings"][0]["namespace"], "payments")
        self.assertEqual(parsed["pod_incident_summary"]["findings"], 1)
        self.assertEqual(parsed["pod_incident_findings"][0]["category"], "config_or_secret_failure")

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
            redis_recovery_summary={"evaluated": 1, "not_serving": 1, "suppressed": 0, "actions_taken": 1},
            redis_recovery_findings=[{"type": "redis.safe_self_recovery", "health": "not_serving", "action": "delete_pod", "target_pod": "redis-0"}],
            security_suspicion_summary={"findings": 1, "high": 1, "medium": 0, "evaluated_namespaces": 1},
            security_suspicion_findings=[{"type": "security.suspicious_behavior", "namespace": "payments", "severity": "high", "resource": "Pod/api", "likely_scenario": "Possible outbound abuse."}],
            pod_incident_summary={"findings": 1, "high": 1, "medium": 0, "evaluated_namespaces": 1},
            pod_incident_findings=[{"type": "runtime.pod_incident", "namespace": "payments", "severity": "high", "resource": "pod/api-123", "category": "config_or_secret_failure", "likely_cause": "Missing secret blocks startup."}],
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
        self.assertIn("redis_recovery_summary", text)
        self.assertIn("actions_taken=1", text)
        self.assertIn("redis.safe_self_recovery", text)
        self.assertIn("security_suspicion_summary", text)
        self.assertIn("evaluated_namespaces=1", text)
        self.assertIn("security.suspicious_behavior", text)
        self.assertIn("pod_incident_summary", text)
        self.assertIn("runtime.pod_incident", text)
        self.assertIn("config_or_secret_failure", text)
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

    def test_merge_pod_incident_report_promotes_ok_report_to_issue(self):
        merged = merge_pod_incident_report(
            {
                "pod_count": 2,
                "error_count": 0,
                "fix_count": 0,
                "status": "ok",
                "summary": "조치가 필요한 이슈가 발견되지 않았습니다.",
                "details": [],
            },
            {
                "pod_incident_summary": {"findings": 1, "high": 1, "medium": 0, "evaluated_namespaces": 1},
                "pod_incident_findings": [
                    {
                        "type": "runtime.pod_incident",
                        "namespace": "payments",
                        "pod": "api-123",
                        "severity": "high",
                        "category": "config_or_secret_failure",
                        "likely_cause": "Missing secret blocks startup.",
                    }
                ],
            },
        )

        self.assertEqual(merged["status"], "issues_found")
        self.assertEqual(merged["error_count"], 1)
        self.assertEqual(merged["pod_incident_summary"]["findings"], 1)
        self.assertEqual(merged["details"][0]["pod"], "payments/api-123")
        self.assertIn("config_or_secret_failure", merged["details"][0]["issue"])

    def test_merge_pod_incident_report_preserves_existing_issue_summary(self):
        merged = merge_pod_incident_report(
            {
                "pod_count": 2,
                "error_count": 2,
                "fix_count": 0,
                "status": "issues_found",
                "summary": "이미 다른 장애가 감지되었습니다.",
                "details": [{"pod": "payments/api", "issue": "CrashLoopBackOff"}],
            },
            {
                "pod_incident_summary": {"findings": 1, "high": 1, "medium": 0, "evaluated_namespaces": 1},
                "pod_incident_findings": [{"type": "runtime.pod_incident", "namespace": "payments", "pod": "api-123", "severity": "high", "category": "config_or_secret_failure", "likely_cause": "Missing secret blocks startup."}],
            },
        )

        self.assertEqual(merged["summary"], "이미 다른 장애가 감지되었습니다.")
        self.assertEqual(len(merged["details"]), 1)
        self.assertEqual(merged["pod_incident_findings"][0]["type"], "runtime.pod_incident")


if __name__ == "__main__":
    unittest.main()
