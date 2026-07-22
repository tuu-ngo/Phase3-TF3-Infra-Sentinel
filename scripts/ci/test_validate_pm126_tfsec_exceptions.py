import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPT = Path(__file__).with_name("validate-pm126-tfsec-exceptions.py")
SPEC = importlib.util.spec_from_file_location("pm126_exception_validator", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def write_fixture(tmp_path: Path, *, expiry: str = "2099-01-01", declared: bool = True):
    terraform = tmp_path / "infra/modules/example/main.tf"
    terraform.parent.mkdir(parents=True)
    terraform.write_text(
        "# rule=AVD-AWS-0001\n"
        "# resource=aws_example.demo\n"
        "# reason=Exact resource exception for a deterministic test fixture.\n"
        "# owner=security-owner\n"
        "# ticket=PM-126\n"
        f"# review_date={expiry}\n"
        f"#tfsec:ignore:aws-example-rule:exp:{expiry}\n"
        'resource "aws_example" "demo" {\n}\n',
        encoding="utf-8",
    )
    ledger = tmp_path / "exceptions.json"
    ledger.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "exceptions": (
                    [
                        {
                            "rule": "AVD-AWS-0001",
                            "tfsecIgnore": "aws-example-rule",
                            "resource": "aws_example.demo",
                            "reason": "Exact resource exception for a deterministic test fixture.",
                            "owner": "security-owner",
                            "ticket": "PM-126",
                            "reviewDate": expiry,
                            "source": "infra/modules/example/main.tf",
                            "status": "approved-false-positive",
                        }
                    ]
                    if declared
                    else []
                ),
            }
        ),
        encoding="utf-8",
    )
    return ledger


class ExceptionValidatorTests(unittest.TestCase):
    def test_accepts_exact_resource_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = write_fixture(root)
            self.assertEqual(MODULE.validate(ledger, root, date(2026, 7, 22)), 1)

    def test_rejects_expired_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = write_fixture(root, expiry="2026-07-21")
            with self.assertRaisesRegex(ValueError, "expired"):
                MODULE.validate(ledger, root, date(2026, 7, 22))

    def test_rejects_unregistered_ignore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = write_fixture(root, declared=False)
            with self.assertRaisesRegex(ValueError, "must not be empty"):
                MODULE.validate(ledger, root, date(2026, 7, 22))

    def test_rejects_blanket_or_extra_ignore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = write_fixture(root)
            extra = root / "infra/global.tf"
            extra.write_text(
                "#tfsec:ignore:aws-untracked-rule:exp:2099-01-01\n"
                'resource "aws_other" "bad" {}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "undeclared"):
                MODULE.validate(ledger, root, date(2026, 7, 22))


if __name__ == "__main__":
    unittest.main()
