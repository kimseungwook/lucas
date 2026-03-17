import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/agent/main"))

from redis_recovery import build_redis_recovery_result


class RedisRecoveryTests(unittest.TestCase):
    def test_classifies_not_serving_when_k8s_and_ping_both_fail(self):
        observations = [
            {
                "workload": {"kind": "StatefulSet", "name": "redis", "namespace": "cache", "annotations": {"lucas.a2w/recovery-mode": "redis-safe-restart"}},
                "status": {"generation": 1, "observedGeneration": 1, "updatedReplicas": 1, "replicas": 1},
                "pods": [
                    {
                        "name": "redis-0",
                        "phase": "Running",
                        "ready": False,
                        "restarts": 4,
                        "events": ["Readiness probe failed"],
                        "ping": {"ok": False, "evidence": "PING timeout"},
                    }
                ],
            }
        ]
        result = build_redis_recovery_result(observations, auto_delete_enabled=False)
        self.assertEqual(result["status"], "issues_found")
        self.assertEqual(result["redis_recovery_summary"]["not_serving"], 1)
        self.assertEqual(result["redis_recovery_findings"][0]["health"], "not_serving")

    def test_does_not_trigger_on_single_signal_only(self):
        observations = [
            {
                "workload": {"kind": "StatefulSet", "name": "redis", "namespace": "cache", "annotations": {"lucas.a2w/recovery-mode": "redis-safe-restart"}},
                "status": {"generation": 1, "observedGeneration": 1, "updatedReplicas": 1, "replicas": 1},
                "pods": [
                    {
                        "name": "redis-0",
                        "phase": "Running",
                        "ready": True,
                        "restarts": 0,
                        "events": [],
                        "ping": {"ok": False, "evidence": "PING timeout"},
                    }
                ],
            }
        ]
        result = build_redis_recovery_result(observations, auto_delete_enabled=False)
        self.assertEqual(result["redis_recovery_summary"]["not_serving"], 0)
        self.assertEqual(result["redis_recovery_findings"][0]["health"], "unknown")
        self.assertEqual(result["redis_recovery_findings"][0]["action"], "none")

    def test_suppresses_when_generation_exceeds_observed_generation(self):
        observations = [
            {
                "workload": {"kind": "StatefulSet", "name": "redis", "namespace": "cache", "annotations": {"lucas.a2w/recovery-mode": "redis-safe-restart"}},
                "status": {"generation": 3, "observedGeneration": 2, "updatedReplicas": 1, "replicas": 1},
                "pods": [
                    {
                        "name": "redis-0",
                        "phase": "Running",
                        "ready": False,
                        "restarts": 3,
                        "events": [],
                        "ping": {"ok": False, "evidence": "PING timeout"},
                    }
                ],
            }
        ]
        result = build_redis_recovery_result(observations, auto_delete_enabled=True, mutations_allowed=True, current_environment="dev", allowed_environments=["dev"])
        finding = result["redis_recovery_findings"][0]
        self.assertTrue(finding["suppressed"])
        self.assertEqual(finding["suppression_reason"], "rollout_in_progress")
        self.assertEqual(finding["action"], "skipped")

    def test_suppresses_when_updated_replicas_are_behind(self):
        observations = [
            {
                "workload": {"kind": "StatefulSet", "name": "redis", "namespace": "cache", "annotations": {"lucas.a2w/recovery-mode": "redis-safe-restart"}},
                "status": {"generation": 2, "observedGeneration": 2, "updatedReplicas": 0, "replicas": 1},
                "pods": [
                    {
                        "name": "redis-0",
                        "phase": "Running",
                        "ready": False,
                        "restarts": 3,
                        "events": [],
                        "ping": {"ok": False, "evidence": "PING timeout"},
                    }
                ],
            }
        ]
        result = build_redis_recovery_result(observations, auto_delete_enabled=True, mutations_allowed=True, current_environment="dev", allowed_environments=["dev"])
        self.assertEqual(result["redis_recovery_findings"][0]["suppression_reason"], "rollout_in_progress")

    def test_suppresses_when_multiple_redis_pods_fail_together(self):
        observations = [
            {
                "workload": {"kind": "StatefulSet", "name": "redis", "namespace": "cache", "annotations": {"lucas.a2w/recovery-mode": "redis-safe-restart"}},
                "status": {"generation": 1, "observedGeneration": 1, "updatedReplicas": 2, "replicas": 2},
                "pods": [
                    {"name": "redis-0", "phase": "Running", "ready": False, "restarts": 2, "events": [], "ping": {"ok": False, "evidence": "PING timeout"}},
                    {"name": "redis-1", "phase": "Running", "ready": False, "restarts": 2, "events": [], "ping": {"ok": False, "evidence": "PING timeout"}},
                ],
            }
        ]
        result = build_redis_recovery_result(observations, auto_delete_enabled=True, mutations_allowed=True, current_environment="dev", allowed_environments=["dev"])
        self.assertEqual(result["redis_recovery_findings"][0]["suppression_reason"], "infra_correlated")

    def test_suppresses_when_storage_or_node_placement_failure_is_present(self):
        observations = [
            {
                "workload": {"kind": "StatefulSet", "name": "redis", "namespace": "cache", "annotations": {"lucas.a2w/recovery-mode": "redis-safe-restart"}},
                "status": {"generation": 1, "observedGeneration": 1, "updatedReplicas": 1, "replicas": 1},
                "pods": [
                    {
                        "name": "redis-0",
                        "phase": "Pending",
                        "ready": False,
                        "restarts": 0,
                        "events": ["AttachVolume.Attach failed for volume data", "FailedScheduling: node mismatch"],
                        "ping": {"ok": False, "evidence": "PING failed"},
                    }
                ],
            }
        ]
        result = build_redis_recovery_result(observations, auto_delete_enabled=True, mutations_allowed=True, current_environment="dev", allowed_environments=["dev"])
        self.assertEqual(result["redis_recovery_findings"][0]["suppression_reason"], "infra_correlated")

    def test_suppresses_when_recent_recovery_attempt_exists(self):
        observations = [
            {
                "workload": {"kind": "StatefulSet", "name": "redis", "namespace": "cache", "annotations": {"lucas.a2w/recovery-mode": "redis-safe-restart"}},
                "status": {"generation": 1, "observedGeneration": 1, "updatedReplicas": 1, "replicas": 1},
                "pods": [
                    {
                        "name": "redis-0",
                        "phase": "Running",
                        "ready": False,
                        "restarts": 3,
                        "events": [],
                        "ping": {"ok": False, "evidence": "PING timeout"},
                    }
                ],
            }
        ]
        recent_actions = {"cache/StatefulSet/redis": {"timestamp": 1000}}
        result = build_redis_recovery_result(
            observations,
            auto_delete_enabled=True,
            mutations_allowed=True,
            current_environment="dev",
            allowed_environments=["dev"],
            cooldown_seconds=600,
            now_ts=1100,
            recent_actions=recent_actions,
        )
        self.assertEqual(result["redis_recovery_findings"][0]["suppression_reason"], "cooldown_active")

    def test_auto_delete_requires_feature_flag_and_workload_opt_in(self):
        executed = []

        def fake_delete(namespace: str, pod_name: str) -> str:
            executed.append((namespace, pod_name))
            return "deleted"

        observations = [
            {
                "workload": {"kind": "StatefulSet", "name": "redis", "namespace": "cache", "annotations": {}},
                "status": {"generation": 1, "observedGeneration": 1, "updatedReplicas": 1, "replicas": 1},
                "pods": [
                    {
                        "name": "redis-0",
                        "phase": "Running",
                        "ready": False,
                        "restarts": 3,
                        "events": [],
                        "ping": {"ok": False, "evidence": "PING timeout"},
                    }
                ],
            }
        ]
        result = build_redis_recovery_result(
            observations,
            auto_delete_enabled=True,
            mutations_allowed=True,
            current_environment="dev",
            allowed_environments=["dev"],
            action_executor=fake_delete,
        )
        self.assertEqual(executed, [])
        self.assertEqual(result["redis_recovery_findings"][0]["action"], "skipped")

    def test_allows_single_action_when_lock_and_cooldown_are_clear(self):
        executed = []

        def fake_delete(namespace: str, pod_name: str) -> str:
            executed.append((namespace, pod_name))
            return "deleted redis-0"

        observations = [
            {
                "workload": {
                    "kind": "StatefulSet",
                    "name": "redis",
                    "namespace": "cache",
                    "annotations": {"lucas.a2w/recovery-mode": "redis-safe-restart"},
                },
                "status": {"generation": 1, "observedGeneration": 1, "updatedReplicas": 1, "replicas": 1},
                "pods": [
                    {
                        "name": "redis-0",
                        "phase": "Running",
                        "ready": False,
                        "restarts": 5,
                        "events": [],
                        "ping": {"ok": False, "evidence": "PING timeout"},
                    }
                ],
            }
        ]
        result = build_redis_recovery_result(
            observations,
            auto_delete_enabled=True,
            mutations_allowed=True,
            current_environment="dev",
            allowed_environments=["dev"],
            now_ts=2000,
            recent_actions={},
            action_executor=fake_delete,
        )
        self.assertEqual(executed, [("cache", "redis-0")])
        finding = result["redis_recovery_findings"][0]
        self.assertEqual(finding["action"], "delete_pod")
        self.assertEqual(finding["action_result"], "deleted redis-0")

    def test_build_redis_recovery_result_returns_expected_top_level_shape(self):
        result = build_redis_recovery_result([])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["redis_recovery_summary"], {"evaluated": 0, "not_serving": 0, "suppressed": 0, "actions_taken": 0})
        self.assertEqual(result["redis_recovery_findings"], [])


if __name__ == "__main__":
    unittest.main()
