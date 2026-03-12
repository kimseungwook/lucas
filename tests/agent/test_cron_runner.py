import sys
import unittest

sys.path.insert(0, "/Users/bseed/git/lucas/src/agent/main")

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


if __name__ == "__main__":
    unittest.main()
