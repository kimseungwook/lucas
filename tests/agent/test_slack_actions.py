import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, "/Users/bseed/git/lucas/src/agent/main")

from slack_actions import (
    confirmation_accepted,
    parse_slack_kube_action,
    slack_action_allowed,
)


class SlackActionsTests(unittest.TestCase):
    def test_parse_restart_deployment(self):
        parsed = parse_slack_kube_action("restart deployment api in namespace default", "default")
        self.assertTrue(parsed.matched)
        self.assertIsNone(parsed.error)
        self.assertEqual(parsed.action.verb, "restart")
        self.assertEqual(parsed.action.kind, "deployment")
        self.assertEqual(parsed.action.name, "api")
        self.assertEqual(parsed.action.namespace, "default")

    def test_parse_korean_statefulset_restart(self):
        parsed = parse_slack_kube_action("argocd namespace의 dex statefulset을 재시작해", "default")
        self.assertTrue(parsed.matched)
        self.assertEqual(parsed.action.verb, "restart")
        self.assertEqual(parsed.action.kind, "statefulset")
        self.assertEqual(parsed.action.name, "dex")
        self.assertEqual(parsed.action.namespace, "argocd")

    def test_restart_pod_is_refused(self):
        parsed = parse_slack_kube_action("argocd namespace의 dex pod를 재시작해", "default")
        self.assertTrue(parsed.matched)
        self.assertIsNotNone(parsed.error)
        self.assertIn("restart pod", parsed.error)

    def test_parse_scale_statefulset(self):
        parsed = parse_slack_kube_action("scale statefulset redis to 2 in namespace cache", "default")
        self.assertTrue(parsed.matched)
        self.assertEqual(parsed.action.verb, "scale")
        self.assertEqual(parsed.action.kind, "statefulset")
        self.assertEqual(parsed.action.replicas, 2)
        self.assertEqual(parsed.action.namespace, "cache")

    def test_parse_describe_pod(self):
        parsed = parse_slack_kube_action("describe pod api-123 in namespace default", "default")
        self.assertTrue(parsed.matched)
        self.assertEqual(parsed.action.verb, "describe")
        self.assertEqual(parsed.action.kind, "pod")
        self.assertEqual(parsed.action.name, "api-123")

    def test_parse_korean_pod_logs(self):
        parsed = parse_slack_kube_action("argocd namespace의 dex pod 로그를 보여줘", "default")
        self.assertTrue(parsed.matched)
        self.assertEqual(parsed.action.verb, "logs")
        self.assertEqual(parsed.action.kind, "pod")
        self.assertEqual(parsed.action.name, "dex")
        self.assertEqual(parsed.action.namespace, "argocd")

    def test_parse_english_pod_logs_phrase(self):
        parsed = parse_slack_kube_action("pod logs slack-action-test-123 in namespace a2w-lucas", "default")
        self.assertTrue(parsed.matched)
        self.assertEqual(parsed.action.verb, "logs")
        self.assertEqual(parsed.action.name, "slack-action-test-123")

    def test_scale_bounds_are_enforced(self):
        parsed = parse_slack_kube_action("scale deployment api to 99 in namespace default", "default")
        self.assertTrue(parsed.matched)
        self.assertIsNotNone(parsed.error)
        self.assertIn("0에서 20", parsed.error)

    def test_confirmation_accepts_korean_yes(self):
        self.assertTrue(confirmation_accepted("예"))
        self.assertTrue(confirmation_accepted("yes"))
        self.assertFalse(confirmation_accepted("아니오"))

    def test_slack_action_allowed_respects_channel_allowlist(self):
        with patch.dict(
            os.environ,
            {
                "SLACK_EMERGENCY_ACTIONS_ENABLED": "true",
                "SLACK_ACTION_ALLOWED_CHANNELS": "C123",
            },
            clear=False,
        ):
            allowed, reason = slack_action_allowed("C123", "U123", "default")
            self.assertTrue(allowed)
            self.assertIsNone(reason)

            allowed, reason = slack_action_allowed("C999", "U123", "default")
            self.assertFalse(allowed)
            self.assertIn("채널", reason)

    def test_slack_action_allowed_respects_namespace_allowlist(self):
        with patch.dict(
            os.environ,
            {
                "SLACK_EMERGENCY_ACTIONS_ENABLED": "true",
                "SLACK_ACTION_ALLOWED_NAMESPACES": "argocd,authentik",
            },
            clear=False,
        ):
            allowed, reason = slack_action_allowed("C123", "U123", "argocd")
            self.assertTrue(allowed)
            self.assertIsNone(reason)

            allowed, reason = slack_action_allowed("C123", "U123", "default")
            self.assertFalse(allowed)
            self.assertIn("namespace", reason)


if __name__ == "__main__":
    unittest.main()
