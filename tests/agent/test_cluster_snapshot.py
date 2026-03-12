import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, "/Users/bseed/git/lucas/src/agent/main")

from cluster_snapshot import build_cluster_overview_snapshot, build_interactive_snapshot, resolve_target_namespaces, summarize_cluster_overview


class ClusterSnapshotTests(unittest.TestCase):
    def test_namespace_query_includes_namespaces(self):
        def fake_run(args):
            if args[:2] == ["get", "namespaces"]:
                return "NAME STATUS AGE\ndefault Active 1d"
            if args[:2] == ["get", "pods"]:
                return "NAME READY STATUS RESTARTS AGE\napi 1/1 Running 0 1d"
            raise AssertionError(args)

        with patch("cluster_snapshot._run_kubectl", side_effect=fake_run):
            snapshot = build_interactive_snapshot("namespace의 list를 출력해줘", "default")
            self.assertIn("Namespaces:", snapshot)
            self.assertIn("default Active", snapshot)

    def test_pod_query_targets_requested_namespace(self):
        seen = []

        def fake_run(args):
            seen.append(args)
            return "ok"

        with patch("cluster_snapshot._run_kubectl", side_effect=fake_run):
            build_interactive_snapshot("check pods in namespace kube-system", "default")

        self.assertIn(["get", "pods", "-n", "kube-system", "-o", "wide"], seen)

    def test_korean_namespace_expression_is_parsed(self):
        seen = []

        def fake_run(args):
            seen.append(args)
            return "ok"

        with patch("cluster_snapshot._run_kubectl", side_effect=fake_run):
            build_interactive_snapshot("authentik의 pod 목록을 보여줘", "default")

        self.assertIn(["get", "pods", "-n", "authentik", "-o", "wide"], seen)

    def test_resolve_target_namespaces_all_uses_list(self):
        with patch("cluster_snapshot.list_namespaces", return_value=["default", "argocd", "authentik"]):
            namespaces = resolve_target_namespaces("default", "all")

        self.assertEqual(namespaces, ["default", "argocd", "authentik"])

    def test_build_cluster_overview_snapshot_summarizes_problematic_pods(self):
        payloads = {
            "default": {
                "items": [
                    {
                        "metadata": {"namespace": "default", "name": "api"},
                        "status": {
                            "phase": "Running",
                            "containerStatuses": [{"restartCount": 0, "state": {"running": {}}}],
                        },
                    }
                ]
            },
            "argocd": {
                "items": [
                    {
                        "metadata": {"namespace": "argocd", "name": "dex"},
                        "status": {
                            "phase": "Running",
                            "containerStatuses": [{"restartCount": 2, "state": {"waiting": {"reason": "CrashLoopBackOff"}}}],
                        },
                    }
                ]
            },
        }

        def fake_run(args):
            namespace = args[args.index("-n") + 1]
            return __import__("json").dumps(payloads[namespace])

        with patch("cluster_snapshot._run_kubectl", side_effect=fake_run):
            snapshot = build_cluster_overview_snapshot(["default", "argocd"])

        self.assertIn("default: pods=1, issues=0", snapshot)
        self.assertIn("argocd: pods=1, issues=1", snapshot)
        self.assertIn("argocd/dex", snapshot)

    def test_summarize_cluster_overview_tracks_status_breakdown_and_restarts(self):
        payloads = {
            "default": {
                "items": [
                    {
                        "metadata": {"namespace": "default", "name": "api"},
                        "status": {
                            "phase": "Running",
                            "containerStatuses": [{"restartCount": 3, "state": {"running": {}}}],
                        },
                    }
                ]
            },
            "argocd": {
                "items": [
                    {
                        "metadata": {"namespace": "argocd", "name": "dex"},
                        "status": {
                            "phase": "Pending",
                            "containerStatuses": [],
                        },
                    }
                ]
            },
        }

        def fake_run(args):
            namespace = args[args.index("-n") + 1]
            return __import__("json").dumps(payloads[namespace])

        with patch("cluster_snapshot._run_kubectl", side_effect=fake_run):
            overview = summarize_cluster_overview(["default", "argocd"])

        self.assertEqual(overview["pod_count"], 2)
        self.assertEqual(overview["issue_count"], 2)
        self.assertEqual(overview["pods_with_restarts"], 1)
        self.assertEqual(overview["status_breakdown"]["Running"], 1)
        self.assertEqual(overview["status_breakdown"]["Pending"], 1)


if __name__ == "__main__":
    unittest.main()
