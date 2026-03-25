import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/agent/main"))

from src.agent.main.pod_incident_triage import build_pod_incident_inputs, collect_pod_incident_inputs
from src.agent.main.pod_incident_triage import resolve_pod_incident_target_namespaces, resolve_pod_incident_target_workloads


class PodIncidentTriageTests(unittest.TestCase):
    def test_top_level_import_works_for_cron_style_execution(self):
        module = importlib.import_module("pod_incident_triage")

        self.assertTrue(hasattr(module, "build_pod_incident_inputs"))
        self.assertTrue(callable(module.build_pod_incident_inputs))

    def test_collects_phase_reason_restart_and_owner_for_failing_pod(self):
        result = build_pod_incident_inputs(
            namespace="payments",
            pods_payload={
                "items": [
                    {
                        "metadata": {
                            "namespace": "payments",
                            "name": "api-123",
                            "ownerReferences": [{"kind": "ReplicaSet", "name": "api-rs"}],
                        },
                        "spec": {"nodeName": "node-a"},
                        "status": {
                            "phase": "Running",
                            "containerStatuses": [
                                {
                                    "restartCount": 3,
                                    "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                                    "lastState": {"terminated": {"reason": "Error"}},
                                }
                            ],
                        },
                    },
                    {
                        "metadata": {
                            "namespace": "payments",
                            "name": "api-124",
                            "ownerReferences": [{"kind": "ReplicaSet", "name": "api-rs"}],
                        },
                        "spec": {"nodeName": "node-a"},
                        "status": {
                            "phase": "Running",
                            "containerStatuses": [{"restartCount": 0, "state": {"running": {}}}],
                        },
                    },
                ]
            },
            events_payload={"items": [{"involvedObject": {"name": "api-123"}, "message": "Back-off restarting failed container"}]},
        )

        self.assertEqual(result["status"], "issues_found")
        self.assertEqual(result["incident_summary"]["issue_count"], 1)
        incident = result["incidents"][0]
        self.assertEqual(incident["pod"], "api-123")
        self.assertEqual(incident["owner_kind"], "ReplicaSet")
        self.assertEqual(incident["owner_name"], "api-rs")
        self.assertEqual(incident["phase"], "Running")
        self.assertEqual(incident["reason"], "CrashLoopBackOff")
        self.assertEqual(incident["restarts"], 3)
        self.assertEqual(incident["healthy_peer_count"], 1)
        self.assertIn("Back-off restarting failed container", incident["events"][0])

    def test_collects_previous_log_hint_when_restart_count_is_nonzero(self):
        result = build_pod_incident_inputs(
            namespace="payments",
            pods_payload={
                "items": [
                    {
                        "metadata": {"namespace": "payments", "name": "worker-1"},
                        "status": {
                            "phase": "Running",
                            "containerStatuses": [{"restartCount": 2, "state": {"running": {}}}],
                        },
                    }
                ]
            },
            events_payload={"items": []},
        )

        self.assertTrue(result["incidents"][0]["needs_previous_logs"])

    def test_marks_single_pod_failure_as_isolated_when_peers_are_healthy(self):
        result = build_pod_incident_inputs(
            namespace="payments",
            pods_payload={
                "items": [
                    {
                        "metadata": {
                            "namespace": "payments",
                            "name": "api-1",
                            "ownerReferences": [{"kind": "ReplicaSet", "name": "api-rs"}],
                        },
                        "status": {
                            "phase": "Running",
                            "containerStatuses": [{"restartCount": 1, "state": {"waiting": {"reason": "CrashLoopBackOff"}}}],
                        },
                    },
                    {
                        "metadata": {
                            "namespace": "payments",
                            "name": "api-2",
                            "ownerReferences": [{"kind": "ReplicaSet", "name": "api-rs"}],
                        },
                        "status": {
                            "phase": "Running",
                            "containerStatuses": [{"restartCount": 0, "state": {"running": {}}}],
                        },
                    },
                ]
            },
            events_payload={"items": []},
        )

        self.assertEqual(result["incidents"][0]["blast_radius"], "isolated_pod")

    def test_marks_multi_workload_failure_as_non_isolated(self):
        result = build_pod_incident_inputs(
            namespace="payments",
            pods_payload={
                "items": [
                    {
                        "metadata": {
                            "namespace": "payments",
                            "name": "api-1",
                            "ownerReferences": [{"kind": "ReplicaSet", "name": "api-rs"}],
                        },
                        "status": {
                            "phase": "Running",
                            "containerStatuses": [{"restartCount": 1, "state": {"waiting": {"reason": "CrashLoopBackOff"}}}],
                        },
                    },
                    {
                        "metadata": {
                            "namespace": "payments",
                            "name": "worker-1",
                            "ownerReferences": [{"kind": "Job", "name": "worker-job"}],
                        },
                        "status": {
                            "phase": "Failed",
                            "containerStatuses": [{"restartCount": 0, "state": {"terminated": {"reason": "Error"}}}],
                        },
                    },
                ]
            },
            events_payload={"items": []},
        )

        self.assertEqual(result["incident_summary"]["affected_owners"], 2)
        self.assertEqual(result["incidents"][0]["blast_radius"], "multi_workload")
        self.assertEqual(result["incidents"][1]["blast_radius"], "multi_workload")

    def test_collect_pod_incident_inputs_reads_pods_and_events(self):
        seen = []

        def fake_run(args):
            seen.append(args)
            if args[:4] == ["-n", "payments", "get", "pods"]:
                return {"items": []}
            if args[:4] == ["-n", "payments", "get", "events"]:
                return {"items": []}
            raise AssertionError(args)

        with patch("src.agent.main.pod_incident_triage._run_kubectl_json", side_effect=fake_run):
            result = collect_pod_incident_inputs("payments")

        self.assertEqual(result["status"], "ok")
        self.assertIn(["-n", "payments", "get", "pods", "-o", "json"], seen)
        self.assertIn(["-n", "payments", "get", "events", "-o", "json"], seen)

    def test_classifies_createcontainerconfigerror_as_config_failure(self):
        result = build_pod_incident_inputs(
            namespace="payments",
            pods_payload={
                "items": [
                    {
                        "metadata": {"namespace": "payments", "name": "api-1"},
                        "status": {
                            "phase": "Pending",
                            "containerStatuses": [{"restartCount": 0, "state": {"waiting": {"reason": "CreateContainerConfigError"}}}],
                        },
                    }
                ]
            },
            events_payload={"items": [{"involvedObject": {"name": "api-1"}, "message": "secret \"db-auth\" not found"}]},
        )

        incident = result["incidents"][0]
        self.assertEqual(incident["category"], "config_or_secret_failure")
        self.assertIn("secret \"db-auth\" not found", incident["evidence"][0])

    def test_classifies_imagepullbackoff_as_image_failure(self):
        result = build_pod_incident_inputs(
            namespace="payments",
            pods_payload={
                "items": [
                    {
                        "metadata": {"namespace": "payments", "name": "api-1"},
                        "status": {
                            "phase": "Pending",
                            "containerStatuses": [{"restartCount": 0, "state": {"waiting": {"reason": "ImagePullBackOff"}}}],
                        },
                    }
                ]
            },
            events_payload={"items": [{"involvedObject": {"name": "api-1"}, "message": "Failed to pull image \"goyo/app:bad\""}]},
        )

        incident = result["incidents"][0]
        self.assertEqual(incident["category"], "image_or_startup_failure")
        self.assertIn("Failed to pull image", incident["likely_cause"])

    def test_classifies_oomkilled_as_resource_or_probe_failure(self):
        result = build_pod_incident_inputs(
            namespace="payments",
            pods_payload={
                "items": [
                    {
                        "metadata": {"namespace": "payments", "name": "api-1"},
                        "status": {
                            "phase": "Running",
                            "containerStatuses": [
                                {
                                    "restartCount": 4,
                                    "state": {"running": {}},
                                    "lastState": {"terminated": {"reason": "OOMKilled"}},
                                }
                            ],
                        },
                    }
                ]
            },
            events_payload={"items": [{"involvedObject": {"name": "api-1"}, "message": "Container api was OOMKilled"}]},
        )

        incident = result["incidents"][0]
        self.assertEqual(incident["category"], "resource_or_probe_failure")
        self.assertIn("OOMKilled", " ".join(incident["evidence"]))

    def test_classifies_attach_failure_as_infra_or_placement_failure(self):
        result = build_pod_incident_inputs(
            namespace="payments",
            pods_payload={
                "items": [
                    {
                        "metadata": {"namespace": "payments", "name": "api-1"},
                        "spec": {"nodeName": "node-a"},
                        "status": {
                            "phase": "Pending",
                            "containerStatuses": [],
                        },
                    }
                ]
            },
            events_payload={"items": [{"involvedObject": {"name": "api-1"}, "message": "AttachVolume.Attach failed for volume data"}]},
        )

        incident = result["incidents"][0]
        self.assertEqual(incident["category"], "infra_or_placement_failure")
        self.assertIn("AttachVolume.Attach failed", incident["evidence"][0])

    def test_keeps_evidence_cause_and_actions_separate(self):
        result = build_pod_incident_inputs(
            namespace="payments",
            pods_payload={
                "items": [
                    {
                        "metadata": {"namespace": "payments", "name": "api-1"},
                        "status": {
                            "phase": "Pending",
                            "containerStatuses": [{"restartCount": 0, "state": {"waiting": {"reason": "CreateContainerConfigError"}}}],
                        },
                    }
                ]
            },
            events_payload={"items": [{"involvedObject": {"name": "api-1"}, "message": "configmap \"api-config\" not found"}]},
        )

        incident = result["incidents"][0]
        self.assertIn("configmap \"api-config\" not found", incident["evidence"][0])
        self.assertNotEqual(incident["likely_cause"], incident["evidence"][0])
        self.assertTrue(incident["recommended_actions"])
        self.assertFalse(any("executed" in action.lower() or "applied" in action.lower() for action in incident["recommended_actions"]))

    def test_resolve_pod_incident_target_namespaces_prefers_feature_scope_then_falls_back(self):
        with patch.dict(
            "os.environ",
            {
                "TARGET_NAMESPACE": "default",
                "TARGET_NAMESPACES": "payments,orders",
                "POD_INCIDENT_TARGET_NAMESPACES": "auth, batch ",
            },
            clear=False,
        ):
            self.assertEqual(resolve_pod_incident_target_namespaces(), ["auth", "batch"])

        with patch.dict(
            "os.environ",
            {
                "TARGET_NAMESPACE": "default",
                "TARGET_NAMESPACES": "payments,orders",
                "POD_INCIDENT_TARGET_NAMESPACES": "",
            },
            clear=False,
        ):
            self.assertEqual(resolve_pod_incident_target_namespaces(), ["payments", "orders"])

    def test_resolve_pod_incident_target_workloads_parses_csv(self):
        with patch.dict("os.environ", {"POD_INCIDENT_TARGET_WORKLOADS": "deployment/api, statefulset/redis ,cronjob/report"}, clear=False):
            self.assertEqual(
                resolve_pod_incident_target_workloads(),
                ["deployment/api", "statefulset/redis", "cronjob/report"],
            )

    def test_filters_to_targeted_deployment_workload_using_replicaset_owner_chain(self):
        result = build_pod_incident_inputs(
            namespace="payments",
            pods_payload={
                "items": [
                    {
                        "metadata": {
                            "namespace": "payments",
                            "name": "api-123",
                            "ownerReferences": [{"kind": "ReplicaSet", "name": "api-7d9c"}],
                        },
                        "status": {
                            "phase": "Running",
                            "containerStatuses": [{"restartCount": 2, "state": {"waiting": {"reason": "CrashLoopBackOff"}}}],
                        },
                    },
                    {
                        "metadata": {
                            "namespace": "payments",
                            "name": "worker-123",
                            "ownerReferences": [{"kind": "ReplicaSet", "name": "worker-6ffb"}],
                        },
                        "status": {
                            "phase": "Running",
                            "containerStatuses": [{"restartCount": 2, "state": {"waiting": {"reason": "CrashLoopBackOff"}}}],
                        },
                    },
                ]
            },
            events_payload={"items": []},
            replicasets_payload={
                "items": [
                    {"metadata": {"name": "api-7d9c"}, "ownerReferences": [{"kind": "Deployment", "name": "api"}]},
                    {"metadata": {"name": "worker-6ffb"}, "ownerReferences": [{"kind": "Deployment", "name": "worker"}]},
                ]
            },
            target_workloads=["deployment/api"],
        )

        self.assertEqual(result["incident_summary"]["pod_count"], 1)
        self.assertEqual(result["incidents"][0]["workload_ref"], "deployment/api")

    def test_collect_pod_incident_inputs_filters_to_targeted_workloads_from_env(self):
        def fake_run(args):
            if args[:4] == ["-n", "payments", "get", "pods"]:
                return {
                    "items": [
                        {
                            "metadata": {"namespace": "payments", "name": "api-123", "ownerReferences": [{"kind": "ReplicaSet", "name": "api-7d9c"}]},
                            "status": {"phase": "Running", "containerStatuses": [{"restartCount": 1, "state": {"waiting": {"reason": "CrashLoopBackOff"}}}]},
                        },
                        {
                            "metadata": {"namespace": "payments", "name": "worker-123", "ownerReferences": [{"kind": "ReplicaSet", "name": "worker-6ffb"}]},
                            "status": {"phase": "Running", "containerStatuses": [{"restartCount": 1, "state": {"waiting": {"reason": "CrashLoopBackOff"}}}]},
                        },
                    ]
                }
            if args[:4] == ["-n", "payments", "get", "events"]:
                return {"items": []}
            if args[:4] == ["-n", "payments", "get", "replicasets"]:
                return {
                    "items": [
                        {"metadata": {"name": "api-7d9c"}, "ownerReferences": [{"kind": "Deployment", "name": "api"}]},
                        {"metadata": {"name": "worker-6ffb"}, "ownerReferences": [{"kind": "Deployment", "name": "worker"}]},
                    ]
                }
            if args[:4] == ["-n", "payments", "get", "jobs"]:
                return {"items": []}
            raise AssertionError(args)

        with patch.dict("os.environ", {"POD_INCIDENT_TARGET_WORKLOADS": "deployment/api"}, clear=False):
            with patch("src.agent.main.pod_incident_triage._run_kubectl_json_or_empty", side_effect=fake_run):
                result = collect_pod_incident_inputs("payments")

        self.assertEqual(result["incident_summary"]["pod_count"], 1)
        self.assertEqual(result["incidents"][0]["workload_ref"], "deployment/api")


if __name__ == "__main__":
    unittest.main()
