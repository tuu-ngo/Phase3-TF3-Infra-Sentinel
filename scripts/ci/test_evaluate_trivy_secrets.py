import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("evaluate-trivy-secrets.py")
SPEC = importlib.util.spec_from_file_location("trivy_secret_evaluator", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class SecretEvaluatorTests(unittest.TestCase):
    def run_evaluator(self, payload):
        directory = tempfile.TemporaryDirectory()
        root = Path(directory.name)
        raw = root / "raw.json"
        report = root / "sanitized.json"
        summary = root / "summary.json"
        raw.write_text(json.dumps(payload), encoding="utf-8")
        result = MODULE.evaluate(raw, report, summary)
        return directory, result, report.read_text(), json.loads(summary.read_text())

    def test_passes_empty_report(self):
        directory, result, report, summary = self.run_evaluator({"Results": []})
        self.addCleanup(directory.cleanup)
        self.assertEqual(result, 0)
        self.assertEqual(summary["verdict"], "PASS")
        self.assertEqual(json.loads(report)["findings"], [])

    def test_fails_high_and_redacts_match_and_code(self):
        marker = "MANDATE10_TEST_" + "VALUE_MUST_NOT_LEAK"
        payload = {
            "Results": [
                {
                    "Target": "/src/example.py",
                    "Secrets": [
                        {
                            "RuleID": "test-rule",
                            "Category": "test",
                            "Severity": "HIGH",
                            "Title": "Synthetic test key",
                            "StartLine": 2,
                            "EndLine": 2,
                            "Match": marker,
                            "Code": {"Lines": [{"Content": marker}]},
                        }
                    ],
                }
            ]
        }
        directory, result, report, summary = self.run_evaluator(payload)
        self.addCleanup(directory.cleanup)
        self.assertEqual(result, 1)
        self.assertEqual(summary["verdict"], "FAIL")
        self.assertNotIn(marker, report)
        self.assertNotIn("Match", report)
        self.assertNotIn("Code", report)
        self.assertIn('"Target": "example.py"', report)

    def test_ignores_non_blocking_severity(self):
        payload = {
            "Results": [
                {
                    "Target": "sample.txt",
                    "Secrets": [
                        {"RuleID": "low-rule", "Severity": "LOW", "Match": "redacted"}
                    ],
                }
            ]
        }
        directory, result, report, summary = self.run_evaluator(payload)
        self.addCleanup(directory.cleanup)
        self.assertEqual(result, 0)
        self.assertEqual(summary["findingCount"], 0)
        self.assertNotIn("redacted", report)

    def test_rejects_malformed_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.json"
            raw.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Results"):
                MODULE.evaluate(raw, root / "report.json", root / "summary.json")


if __name__ == "__main__":
    unittest.main()
