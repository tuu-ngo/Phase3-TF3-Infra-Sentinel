"""Mandate 12: group 7 chỉ được alert khi đòn nhắm vào chính audit plane.

Rule `g7` khớp theo `eventName` và không lọc resource ở tầng event pattern, nên
nếu router không lọc theo target thì mọi `PutMetricAlarm` / `UpdateFunctionCode`
/ `PutBucketPolicy` trong account đều thành CRITICAL không tắt được. Alert bị mute
là cửa sổ mù mà mandate muốn chặn, nên hành vi này được khoá bằng test.
"""

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

ROUTER = Path(__file__).resolve().parents[2] / "infra/modules/audit-detection/lambda/index.py"

CLUSTER = "techx-corp-tf3"
ACCOUNT = "111122223333"
AUTOMATION = f"arn:aws:iam::{ACCOUNT}:role/{CLUSTER}-gha-terraform-apply"
HUMAN = f"arn:aws:iam::{ACCOUNT}:user/CDO02"
ALERT_TOPIC = f"arn:aws:sns:ap-southeast-1:{ACCOUNT}:{CLUSTER}-audit-detection-ap-southeast-1-alerts"

AUDIT_PLANE_KEYWORDS = [
    f"{CLUSTER}-audit-detection",
    f"{CLUSTER}-audit-trail",
    f"{CLUSTER}-m12-audit-heartbeat",
]


def base_config(**overrides):
    config = {
        "deployment_label": "ap-southeast-1",
        "allowed_principals": [AUTOMATION],
        "human_principals": [HUMAN],
        "secret_reader_principals": [],
        "sensitive_secret_names": [],
        "suppressions": [],
        "critical_group_numbers": [1, 2, 3, 4, 7, 8],
        "critical_group_6_target_keywords": ["cloudtrail", "kms", "secret"],
        "critical_group_7_target_keywords": list(AUDIT_PLANE_KEYWORDS),
    }
    config.update(overrides)
    return config


class _StubClient:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: {}


def load_router(config, monkeypatch_env):
    """Nạp một bản router độc lập với CONFIG cho trước.

    CONFIG đọc env ở thời điểm import nên mỗi biến thể config cần một lần nạp
    riêng. boto3 bị thay bằng stub để test không cần dependency hay region.
    """
    monkeypatch_env("ALERT_TOPIC_ARN", ALERT_TOPIC)
    monkeypatch_env("DEPLOYMENT_LABEL", "ap-southeast-1")
    monkeypatch_env("DETECTOR_CONFIG_JSON", json.dumps(config))

    stub = types.ModuleType("boto3")
    stub.client = lambda *args, **kwargs: _StubClient()
    original = sys.modules.get("boto3")
    sys.modules["boto3"] = stub
    try:
        spec = importlib.util.spec_from_file_location("audit_router_under_test", ROUTER)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(module)
    finally:
        if original is None:
            sys.modules.pop("boto3", None)
        else:
            sys.modules["boto3"] = original

    module.published = []
    module.publish_alert = module.published.append
    module.publish_metric = lambda *args, **kwargs: None
    return module


def event(source, name, request, actor=HUMAN):
    return {
        "detail": {
            "eventSource": f"{source}.amazonaws.com",
            "eventName": name,
            "eventTime": "2026-07-23T10:00:00Z",
            "requestParameters": request,
            "userIdentity": {"type": "AssumedRole", "arn": actor},
        },
        "resources": [f"arn:aws:events:ap-southeast-1:{ACCOUNT}:rule/g7-audit-controls"],
    }


class Group7TargetingTest(unittest.TestCase):
    def setUp(self):
        self._saved_env = {}
        self.router = load_router(base_config(), self._set_env)

    def _set_env(self, key, value):
        import os

        self._saved_env.setdefault(key, os.environ.get(key))
        os.environ[key] = value

    def tearDown(self):
        import os

        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def assertIgnored(self, result, reason):
        self.assertTrue(result.get("ignored"), result)
        self.assertEqual(result.get("reason"), reason, result)
        self.assertEqual(self.router.published, [])

    def assertAlerted(self, result, severity):
        self.assertTrue(result.get("sent"), result)
        self.assertEqual(result.get("severity"), severity, result)
        self.assertEqual(len(self.router.published), 1)

    def test_routine_lambda_deploy_outside_audit_plane_is_not_alerted(self):
        result = self.router.handler(
            event("lambda", "UpdateFunctionCode", {"functionName": "techx-corp-frontend"}), None
        )
        self.assertIgnored(result, "non_audit_target")

    def test_routine_alarm_and_bucket_changes_are_not_alerted(self):
        for evt in (
            event("monitoring", "PutMetricAlarm", {"alarmName": "techx-corp-checkout-latency"}),
            event("s3", "PutBucketPolicy", {"bucketName": "techx-tf3-terraform-state"}),
            event("events", "PutRule", {"name": "karpenter-interruption"}),
        ):
            with self.subTest(event_name=evt["detail"]["eventName"]):
                self.assertIgnored(self.router.handler(evt, None), "non_audit_target")

    def test_router_tamper_stays_critical(self):
        result = self.router.handler(
            event(
                "lambda",
                "UpdateFunctionCode",
                {"functionName": f"{CLUSTER}-audit-detection-ap-southeast-1-router"},
            ),
            None,
        )
        self.assertAlerted(result, "critical")

    def test_heartbeat_alarm_tamper_stays_critical(self):
        result = self.router.handler(
            event(
                "monitoring", "PutMetricAlarm", {"alarmName": f"{CLUSTER}-m12-audit-heartbeat-errors"}
            ),
            None,
        )
        self.assertAlerted(result, "critical")

    def test_list_valued_alarm_names_are_matched(self):
        # monitoring:DeleteAlarms truyền alarmNames dạng mảng; dò key đơn lẻ sẽ trượt.
        result = self.router.handler(
            event(
                "monitoring",
                "DeleteAlarms",
                {"alarmNames": [f"{CLUSTER}-m12-audit-heartbeat-missing", "unrelated-alarm"]},
            ),
            None,
        )
        self.assertAlerted(result, "critical")

    def test_audit_archive_bucket_control_stays_critical(self):
        result = self.router.handler(
            event(
                "s3",
                "PutBucketPolicy",
                {"bucketName": f"{CLUSTER}-audit-trail-ap-southeast-1-{ACCOUNT}"},
            ),
            None,
        )
        self.assertAlerted(result, "critical")

    def test_alert_topic_subscription_change_stays_critical(self):
        result = self.router.handler(
            event("sns", "Subscribe", {"topicArn": ALERT_TOPIC}), None
        )
        self.assertAlerted(result, "critical")

    def test_rule_target_removal_is_matched_by_rule_parameter(self):
        result = self.router.handler(
            event(
                "events",
                "RemoveTargets",
                {"rule": f"{CLUSTER}-audit-detection-ap-southeast-1-g7-audit-controls"},
            ),
            None,
        )
        self.assertAlerted(result, "critical")

    def test_unparsable_target_fails_safe_and_alerts(self):
        result = self.router.handler(event("lambda", "UpdateFunctionCode", {}), None)
        self.assertAlerted(result, "critical")

    def test_missing_keyword_config_fails_safe_and_alerts(self):
        router = load_router(
            base_config(critical_group_7_target_keywords=[]), self._set_env
        )
        result = router.handler(
            event("lambda", "UpdateFunctionCode", {"functionName": "techx-corp-frontend"}), None
        )
        self.assertTrue(result.get("sent"), result)
        self.assertEqual(result.get("severity"), "critical")

    def test_trusted_automation_cannot_mute_an_audit_plane_change(self):
        result = self.router.handler(
            event(
                "lambda",
                "UpdateFunctionCode",
                {"functionName": f"{CLUSTER}-audit-detection-ap-southeast-1-router"},
                actor=AUTOMATION,
            ),
            None,
        )
        self.assertAlerted(result, "critical")

    def test_other_groups_are_unchanged(self):
        result = self.router.handler(
            event(
                "cloudtrail",
                "StopLogging",
                {"name": f"{CLUSTER}-audit-detection-ap-southeast-1-trail"},
                actor=AUTOMATION,
            ),
            None,
        )
        self.assertAlerted(result, "critical")


if __name__ == "__main__":
    unittest.main()
