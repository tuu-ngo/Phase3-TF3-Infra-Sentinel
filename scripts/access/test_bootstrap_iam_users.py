from pathlib import Path
import stat

import pytest

from bootstrap_iam_users import OPERATOR_USERS, READONLY_USER, bootstrap_users


class FakeIAM:
    def __init__(self):
        self.users = set()
        self.login_profiles = {}
        self.access_keys = {}

    def get_user(self, UserName):
        if UserName not in self.users:
            raise self.exceptions.NoSuchEntityException({}, "GetUser")
        return {"User": {"UserName": UserName}}

    def create_user(self, UserName, Tags):
        self.users.add(UserName)
        return {"User": {"UserName": UserName}}

    def get_login_profile(self, UserName):
        if UserName not in self.login_profiles:
            raise self.exceptions.NoSuchEntityException({}, "GetLoginProfile")
        return {"LoginProfile": {"UserName": UserName}}

    def create_login_profile(self, UserName, Password, PasswordResetRequired):
        self.login_profiles[UserName] = {
            "Password": Password,
            "PasswordResetRequired": PasswordResetRequired,
        }

    def list_access_keys(self, UserName):
        return {"AccessKeyMetadata": self.access_keys.get(UserName, [])}

    def create_access_key(self, UserName):
        key = {
            "UserName": UserName,
            "AccessKeyId": f"TESTKEY-{UserName}",
            "SecretAccessKey": f"test-secret-{UserName}",
            "Status": "Active",
        }
        self.access_keys.setdefault(UserName, []).append(key)
        return {"AccessKey": key}

    class exceptions:
        class NoSuchEntityException(Exception):
            pass


def test_bootstrap_creates_exact_users_and_protected_handoff(tmp_path: Path):
    iam = FakeIAM()
    output = tmp_path / "handoff.json"

    records = bootstrap_users(iam, "197826770971", output, lambda: "Strong-temp-Password-42!")

    assert OPERATOR_USERS == ("cdo01-pm", "cdo01-tl", "cdo02-pm", "cdo02-tl")
    assert READONLY_USER == "tf3-members-readonly"
    assert iam.users == {*OPERATOR_USERS, READONLY_USER}
    assert len(records) == 5
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert all(iam.login_profiles[name]["PasswordResetRequired"] for name in OPERATOR_USERS)
    assert iam.login_profiles[READONLY_USER]["PasswordResetRequired"] is False
    assert all(len(iam.access_keys[name]) == 1 for name in (*OPERATOR_USERS, READONLY_USER))
    assert all("AccessKeyId" in record and "SecretAccessKey" in record for record in records)


def test_bootstrap_refuses_to_overwrite_existing_handoff(tmp_path: Path):
    iam = FakeIAM()
    output = tmp_path / "handoff.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError):
        bootstrap_users(iam, "197826770971", output, lambda: "Strong-temp-Password-42!")


def test_bootstrap_rejects_wrong_account_before_mutation(tmp_path: Path):
    iam = FakeIAM()

    with pytest.raises(ValueError, match="AWS account"):
        bootstrap_users(iam, "000000000000", tmp_path / "handoff.json")

    assert iam.users == set()


def test_bootstrap_does_not_create_second_access_key(tmp_path: Path):
    iam = FakeIAM()
    iam.users.add("cdo01-pm")
    iam.login_profiles["cdo01-pm"] = {"PasswordResetRequired": True}
    iam.access_keys["cdo01-pm"] = [{"AccessKeyId": "EXISTING", "Status": "Active"}]

    records = bootstrap_users(iam, "197826770971", tmp_path / "handoff.json")

    assert len(iam.access_keys["cdo01-pm"]) == 1
    record = next(item for item in records if item["UserName"] == "cdo01-pm")
    assert record["AccessKeyStatus"] == "existing-access-key-not-retrievable"
    assert "SecretAccessKey" not in record
