import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/agent/main"))

from security_compensating_control import build_security_suspicion_result


class SecurityCompensatingControlTests(unittest.TestCase):
    def test_groups_multiple_signals_into_one_suspicious_behavior_finding(self):
        signal_bundle = {
            "enabled": True,
            "mode": "report-only",
            "monitored_namespaces": ["payments"],
            "policy_reports": [
                {"namespace": "payments", "policy": "detect-secret-use", "message": "service account used to access sensitive secret", "severity": "high", "source": "kyverno"}
            ],
            "events": [
                {"namespace": "payments", "resource": "Pod/api", "message": "kubectl exec used on workload"},
            ],
            "workloads": [],
        }
        result = build_security_suspicion_result(signal_bundle)
        self.assertEqual(result["status"], "issues_found")
        self.assertEqual(result["security_suspicion_summary"]["findings"], 1)
        self.assertEqual(result["security_suspicion_findings"][0]["namespace"], "payments")

    def test_assigns_severity_from_deterministic_signal_combination(self):
        signal_bundle = {
            "enabled": True,
            "mode": "report-only",
            "monitored_namespaces": ["payments"],
            "policy_reports": [
                {"namespace": "payments", "policy": "detect-secret-use", "message": "service account used to access sensitive secret", "severity": "high", "source": "kyverno"},
                {"namespace": "payments", "policy": "detect-egress", "message": "unexpected egress to new external destination", "severity": "medium", "source": "kyverno"},
            ],
            "events": [],
            "workloads": [],
        }
        result = build_security_suspicion_result(signal_bundle)
        self.assertEqual(result["security_suspicion_findings"][0]["severity"], "high")

    def test_output_uses_compensating_control_wording_not_runtime_detector_wording(self):
        signal_bundle = {
            "enabled": True,
            "mode": "report-only",
            "monitored_namespaces": ["payments"],
            "policy_reports": [
                {"namespace": "payments", "policy": "detect-exec", "message": "kubectl exec used on workload", "severity": "medium", "source": "kyverno"},
            ],
            "events": [],
            "workloads": [],
        }
        result = build_security_suspicion_result(signal_bundle)
        finding = result["security_suspicion_findings"][0]
        self.assertIn("possible", finding["likely_scenario"].lower())
        self.assertNotIn("malware detected", finding["likely_scenario"].lower())
        self.assertIn("compensating", result["control_mode"].lower())

    def test_output_preserves_raw_evidence_items(self):
        signal_bundle = {
            "enabled": True,
            "mode": "report-only",
            "monitored_namespaces": ["payments"],
            "policy_reports": [
                {"namespace": "payments", "policy": "detect-egress", "message": "unexpected egress to new external destination", "severity": "medium", "source": "kyverno"},
            ],
            "events": [
                {"namespace": "payments", "resource": "Pod/api", "message": "recent exec activity on workload"},
            ],
            "workloads": [],
        }
        result = build_security_suspicion_result(signal_bundle)
        finding = result["security_suspicion_findings"][0]
        self.assertIn("unexpected egress to new external destination", finding["evidence"])
        self.assertIn("recent exec activity on workload", finding["evidence"])

    def test_returns_empty_when_feature_disabled(self):
        result = build_security_suspicion_result({
            "enabled": False,
            "mode": "report-only",
            "monitored_namespaces": [],
            "policy_reports": [],
            "events": [],
            "workloads": [],
        })
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["security_suspicion_summary"]["findings"], 0)
        self.assertEqual(result["security_suspicion_findings"], [])


if __name__ == "__main__":
    unittest.main()
