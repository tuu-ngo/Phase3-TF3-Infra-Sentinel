import unittest
from pathlib import Path


WORKFLOW = Path(".github/workflows/terraform-apply.yml")
WORKFLOW_TEXT = WORKFLOW.read_text(encoding="utf-8")


class Pm127TerraformRolloutContractTests(unittest.TestCase):
    def test_scope_is_a_closed_choice_with_full_as_default(self):
        self.assertIn("      scope:\n", WORKFLOW_TEXT)
        self.assertIn("        default: full\n", WORKFLOW_TEXT)
        self.assertIn("          - full\n", WORKFLOW_TEXT)
        self.assertIn("          - pm127-kyverno-ecr\n", WORKFLOW_TEXT)
        self.assertNotIn("type: string", WORKFLOW_TEXT)

    def test_pm127_scope_targets_only_role_and_inline_policy(self):
        self.assertEqual(WORKFLOW_TEXT.count("-target="), 2)
        self.assertIn("-target=aws_iam_role.kyverno_ecr", WORKFLOW_TEXT)
        self.assertIn(
            "-target=aws_iam_role_policy.kyverno_ecr_read", WORKFLOW_TEXT
        )
        self.assertIn('case "$PLAN_SCOPE" in', WORKFLOW_TEXT)
        self.assertIn("Unsupported Terraform rollout scope", WORKFLOW_TEXT)

    def test_apply_consumes_only_the_hashed_saved_plan(self):
        self.assertIn("sha256sum tfplan > tfplan.sha256", WORKFLOW_TEXT)
        self.assertIn("sha256sum --check tfplan.sha256", WORKFLOW_TEXT)
        self.assertEqual(
            WORKFLOW_TEXT.count("terraform apply -input=false tfplan"), 1
        )
        apply_command = "terraform apply -input=false tfplan"
        self.assertNotIn("-target", apply_command)

    def test_pm127_apply_verifies_live_iam_objects(self):
        self.assertIn("name: Verify PM-127 Kyverno ECR role", WORKFLOW_TEXT)
        self.assertIn("if: inputs.scope == 'pm127-kyverno-ecr'", WORKFLOW_TEXT)
        self.assertIn("aws iam get-role \\", WORKFLOW_TEXT)
        self.assertIn("aws iam get-role-policy \\", WORKFLOW_TEXT)
        self.assertIn("techx-corp-tf3-kyverno-ecr-read", WORKFLOW_TEXT)


if __name__ == "__main__":
    unittest.main()
