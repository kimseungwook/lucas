import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/agent/main"))

from security_signal_collection import build_security_signal_inputs


class SecuritySignalCollectionTests(unittest.TestCase):
    def test_ignores_namespaces_outside_allowlist(self):
        bundle = build_security_signal_inputs(
            enabled=True,
            namespaces_csv="payments,redis",
            mode="report-only",
            policy_reports=[
                {"metadata": {"namespace": "payments", "name": "p1"}, "results": [{"policy": "secret-policy", "message": "secret exposure detected", "severity": "high", "source": "kyverno"}]},
                {"metadata": {"namespace": "logging", "name": "p2"}, "results": [{"policy": "egress-policy", "message": "unexpected egress destination", "severity": "medium", "source": "kyverno"}]},
            ],
            events=[
                {"metadata": {"namespace": "payments"}, "message": "kubectl exec used on pod/api", "involvedObject": {"kind": "Pod", "name": "api"}},
                {"metadata": {"namespace": "logging"}, "message": "unexpected egress destination", "involvedObject": {"kind": "Pod", "name": "log-agent"}},
            ],
            deployments=[],
            statefulsets=[],
        )
        self.assertEqual(bundle["monitored_namespaces"], ["payments", "redis"])
        self.assertEqual({item["namespace"] for item in bundle["policy_reports"]}, {"payments"})
        self.assertEqual({item["namespace"] for item in bundle["events"]}, {"payments"})

    def test_collects_only_allowed_namespaces_when_enabled(self):
        bundle = build_security_signal_inputs(
            enabled=True,
            namespaces_csv="redis",
            mode="report-only",
            policy_reports=[],
            events=[],
            deployments=[
                {"metadata": {"namespace": "redis", "name": "api-deploy"}, "spec": {"template": {"spec": {"containers": [{"image": "ghcr.io/example/api:latest"}]}}}},
                {"metadata": {"namespace": "payments", "name": "payments-deploy"}, "spec": {"template": {"spec": {"containers": [{"image": "ghcr.io/example/payments:latest"}]}}}},
            ],
            statefulsets=[],
        )
        self.assertEqual(len(bundle["workloads"]), 1)
        self.assertEqual(bundle["workloads"][0]["namespace"], "redis")

    def test_collects_policyreport_findings_from_allowed_namespaces(self):
        bundle = build_security_signal_inputs(
            enabled=True,
            namespaces_csv="payments",
            mode="report-only",
            policy_reports=[
                {
                    "metadata": {"namespace": "payments", "name": "policy-report"},
                    "summary": {"warn": 1},
                    "results": [
                        {
                            "policy": "detect-secret-use",
                            "category": "Suspicious Secret Access",
                            "message": "service account used to access sensitive secret",
                            "severity": "high",
                            "source": "kyverno",
                        }
                    ],
                }
            ],
            events=[],
            deployments=[],
            statefulsets=[],
        )
        self.assertEqual(bundle["policy_reports"][0]["policy"], "detect-secret-use")
        self.assertEqual(bundle["policy_reports"][0]["namespace"], "payments")

    def test_collects_kubernetes_events_and_rollout_context(self):
        bundle = build_security_signal_inputs(
            enabled=True,
            namespaces_csv="payments",
            mode="report-only",
            policy_reports=[],
            events=[
                {
                    "metadata": {"namespace": "payments"},
                    "message": "unexpected rollout image change detected",
                    "involvedObject": {"kind": "Deployment", "name": "api"},
                }
            ],
            deployments=[
                {
                    "metadata": {"namespace": "payments", "name": "api"},
                    "spec": {"template": {"spec": {"containers": [{"image": "ghcr.io/example/api:v2"}]}}},
                }
            ],
            statefulsets=[],
        )
        self.assertEqual(bundle["events"][0]["resource"], "Deployment/api")
        self.assertEqual(bundle["workloads"][0]["image"], "ghcr.io/example/api:v2")

    def test_returns_empty_when_disabled(self):
        bundle = build_security_signal_inputs(
            enabled=False,
            namespaces_csv="payments",
            mode="report-only",
            policy_reports=[{"metadata": {"namespace": "payments"}, "results": []}],
            events=[{"metadata": {"namespace": "payments"}, "message": "anything", "involvedObject": {"kind": "Pod", "name": "api"}}],
            deployments=[],
            statefulsets=[],
        )
        self.assertFalse(bundle["enabled"])
        self.assertEqual(bundle["monitored_namespaces"], [])
        self.assertEqual(bundle["policy_reports"], [])
        self.assertEqual(bundle["events"], [])


if __name__ == "__main__":
    unittest.main()
