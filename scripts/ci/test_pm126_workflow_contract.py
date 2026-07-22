import re
import unittest
from pathlib import Path


WORKFLOW = Path(".github/workflows/secure-delivery-gate.yml")
WORKFLOW_TEXT = WORKFLOW.read_text(encoding="utf-8")
WORKFLOW_DIR = Path(".github/workflows")


def job_block(job_id: str, next_job_id: str | None = None) -> str:
    start = WORKFLOW_TEXT.index(f"  {job_id}:\n")
    if next_job_id:
        end = WORKFLOW_TEXT.index(f"  {next_job_id}:\n", start)
    else:
        end = len(WORKFLOW_TEXT)
    return WORKFLOW_TEXT[start:end]


class SecureDeliveryWorkflowContractTests(unittest.TestCase):
    def test_runs_for_every_pr_and_merge_queue_without_path_filters(self):
        event_block = WORKFLOW_TEXT.split("permissions:", 1)[0]
        self.assertIn('"on":\n', event_block)
        self.assertIn("  pull_request:\n", event_block)
        self.assertIn("  merge_group:\n", event_block)
        self.assertNotIn("paths:", event_block)
        self.assertNotIn("paths-ignore:", event_block)

    def test_untrusted_pr_permissions_are_read_only(self):
        self.assertIn("permissions:\n  contents: read\n", WORKFLOW_TEXT)
        for forbidden in (
            "id-token: write",
            "contents: write",
            "packages: write",
            "pull-requests: write",
            "pull_request_target",
            "${{ secrets.",
            "configure-aws-credentials",
            "terraform apply",
            "aws ecr",
            "ecr login",
            "docker push",
        ):
            self.assertNotIn(forbidden, WORKFLOW_TEXT.lower())
        self.assertEqual(WORKFLOW_TEXT.count("persist-credentials: false"), 3)

    def test_all_external_actions_and_scanner_images_are_immutable(self):
        action_refs = re.findall(r"^\s*uses:\s*([^\s#]+)", WORKFLOW_TEXT, re.MULTILINE)
        self.assertEqual(len(action_refs), 6)
        for action_ref in action_refs:
            self.assertRegex(action_ref, r"^[^@]+@[0-9a-f]{40}$")
        scanner_refs = re.findall(
            r"^\s+(?:aquasec/(?:tfsec|trivy)|semgrep/semgrep):[^\s]+@sha256:[0-9a-f]{64}",
            WORKFLOW_TEXT,
            re.MULTILINE,
        )
        self.assertEqual(len(scanner_refs), 3)

    def test_three_scans_always_run_and_publish_artifacts(self):
        iac = job_block("iac_misconfiguration", "secret_scan")
        secret = job_block("secret_scan", "sast")
        sast = job_block("sast", "secure_delivery_gate")
        for block in (iac, secret, sast):
            self.assertNotRegex(block, r"^\s{4}if:", "scan job must not be conditional")
            self.assertIn("actions/upload-artifact@", block)
            self.assertIn("retention-days: 90", block)
        self.assertIn("/src/infra/live/production", iac)
        self.assertIn('--user "$(id -u):$(id -g)"', iac)
        self.assertIn("--minimum-severity HIGH", iac)
        self.assertIn("--scanners secret", secret)
        self.assertIn("--severity HIGH,CRITICAL", secret)
        self.assertIn("/src\n", secret)
        self.assertNotIn("raw.json\n", secret.split("path: |", 1)[-1].split("if-no-files-found", 1)[0])
        self.assertIn("--config p/owasp-top-ten", sast)
        self.assertIn("--severity ERROR", sast)
        self.assertIn("--error", sast)
        self.assertIn("techx-corp-platform/src", sast)

    def test_aggregate_is_always_created_and_fails_closed(self):
        aggregate = job_block("secure_delivery_gate")
        self.assertIn("name: Secure delivery gate", aggregate)
        self.assertIn("if: ${{ always() }}", aggregate)
        for job_id in ("iac_misconfiguration", "secret_scan", "sast"):
            self.assertIn(f"      - {job_id}", aggregate)
            self.assertIn(f"needs.{job_id}.result", aggregate)
        self.assertIn('!= "success"', aggregate)
        self.assertIn("exit 1", aggregate)
        self.assertIn("pre-merge/pre-ECR-push gate", aggregate)

    def test_required_context_name_is_unique_repo_wide(self):
        occurrences = []
        for path in WORKFLOW_DIR.glob("*.yml"):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.fullmatch(r"\s*name:\s*Secure delivery gate\s*", line):
                    occurrences.append((path, line_number))
        self.assertEqual(len(occurrences), 1)
        self.assertEqual(occurrences[0][0], WORKFLOW)


if __name__ == "__main__":
    unittest.main()
