import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/agent/main"))

from drift_auditor import build_drift_audit_result


class DriftAuditorTests(unittest.TestCase):
    def test_detects_storage_node_placement_mismatch(self):
        result = build_drift_audit_result(
            deployment_pod={"spec": {"nodeName": "10.130.115.253"}},
            deployment_events=[{"message": "AttachVolume.Attach failed for volume data: node has in transit encryption enabled, but attachment type is not paravirtualized"}],
            pvcs=[{"metadata": {"name": "lucas-data", "annotations": {"volume.kubernetes.io/selected-node": "10.130.107.220"}}}],
        )
        self.assertEqual(result["status"], "issues_found")
        self.assertEqual(result["drift_summary"]["storage"], 1)
        self.assertEqual(result["drifts"][0]["type"], "storage.node_placement_mismatch")

    def test_detects_attach_error_from_pod_events(self):
        result = build_drift_audit_result(
            cronjob_pod={"spec": {"nodeName": "10.130.115.253"}},
            cronjob_events=[{"message": "AttachVolume.Attach failed for volume data"}],
            pvcs=[{"metadata": {"name": "claude-sessions", "annotations": {"volume.kubernetes.io/selected-node": "10.130.107.220"}}}],
        )
        self.assertEqual(result["drift_summary"]["storage"], 1)
        self.assertIn("AttachVolume.Attach failed", result["drifts"][0]["evidence"][0])

    def test_detects_missing_provider_branch_in_mounted_llm_code_when_configmap_mounts_exist(self):
        result = build_drift_audit_result(
            deployment={"spec": {"template": {"spec": {"containers": [{"env": [{"name": "LLM_PROVIDER", "value": "openrouter"}]}]}}}},
            configmaps={
                "lucas-agent-code": {"llm.py": "def foo():\n    return 'gemini only'\n"},
                "lucas-cron-code": {"llm.py": "def foo():\n    return 'gemini only'\n"},
            },
        )
        self.assertEqual(result["drift_summary"]["code"], 1)
        self.assertEqual(result["drifts"][0]["type"], "code.provider_support_missing")

    def test_detects_agent_and_cron_runtime_surface_mismatch(self):
        result = build_drift_audit_result(
            deployment={"spec": {"template": {"spec": {"containers": [{"image": "python:3.12-slim@sha256:aaa"}]}}}},
            cronjob={"spec": {"jobTemplate": {"spec": {"template": {"spec": {"containers": [{"image": "python:3.12-slim@sha256:bbb"}]}}}}}},
            configmaps={},
        )
        self.assertEqual(result["drift_summary"]["code"], 1)
        self.assertEqual(result["drifts"][0]["type"], "code.runtime_surface_mismatch")

    def test_detects_provider_model_mismatch_between_deployment_and_cronjob(self):
        deployment = {"spec": {"template": {"spec": {"containers": [{"env": [
            {"name": "LLM_PROVIDER", "value": "openrouter"},
            {"name": "LLM_MODEL", "value": "stepfun/step-3.5-flash:free"},
            {"name": "OPENROUTER_API_KEY", "valueFrom": {"secretKeyRef": {"name": "llm-auth-openrouter", "key": "OPENROUTER_API_KEY"}}},
        ]}]}}}}
        cronjob = {"spec": {"jobTemplate": {"spec": {"template": {"spec": {"containers": [{"env": [
            {"name": "LLM_PROVIDER", "value": "gemini"},
            {"name": "LLM_MODEL", "value": "gemini-2.5-flash"},
            {"name": "GEMINI_API_KEY", "valueFrom": {"secretKeyRef": {"name": "llm-auth-gemini", "key": "GEMINI_API_KEY"}}},
        ]}]}}}}}}
        result = build_drift_audit_result(deployment=deployment, cronjob=cronjob)
        self.assertEqual(result["drift_summary"]["runtime"], 1)
        self.assertEqual(result["drifts"][0]["type"], "runtime.config_mismatch")

    def test_detects_secret_ref_mismatch_for_selected_provider(self):
        deployment = {"spec": {"template": {"spec": {"containers": [{"env": [
            {"name": "LLM_PROVIDER", "value": "openrouter"},
            {"name": "LLM_API_KEY", "valueFrom": {"secretKeyRef": {"name": "llm-auth", "key": "api-key"}}},
        ]}]}}}}
        result = build_drift_audit_result(deployment=deployment)
        self.assertEqual(result["drift_summary"]["runtime"], 1)
        self.assertEqual(result["drifts"][0]["type"], "runtime.secret_ref_mismatch")

    def test_build_drift_audit_result_returns_expected_top_level_shape(self):
        result = build_drift_audit_result()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["drift_summary"], {"storage": 0, "code": 0, "runtime": 0})
        self.assertEqual(result["drifts"], [])


if __name__ == "__main__":
    unittest.main()
