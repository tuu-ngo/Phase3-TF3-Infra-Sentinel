"""Mandate 12 audit heartbeat.

Chạy 5 phút/lần, so trạng thái live của audit foundation với cấu hình đã được
phê duyệt. Mục tiêu là phát hiện "sự im lặng": nếu ai đó tắt trail, làm yếu
selector/bucket policy, sửa rule/target, đổi alarm hoặc giết router thì
heartbeat FAIL và tự publish cảnh báo qua nhiều đường độc lập.

Đặt ở thư mục riêng, KHÔNG chung với lambda/index.py: module M11 đóng gói
router bằng archive_file với source_dir = "${path.module}/lambda", nên mọi file
nằm trong đó sẽ lọt vào audit-alert-router.zip và làm router redeploy thừa.
"""

import json
import os
from datetime import datetime, timezone

import boto3


def _age_minutes(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - value).total_seconds() / 60


def _field_values(fields, name, operator="Equals"):
    return set(fields.get(name, {}).get(operator, []))


def _as_set(value):
    if value is None:
        return set()
    if isinstance(value, list):
        return set(value)
    return {value}


def _condition_values(condition, operator, key):
    operator_value = condition.get(operator, {})
    for current_key, value in operator_value.items():
        if current_key.lower() == key.lower():
            return _as_set(value)
    return set()


def _principal_is_all(principal):
    if principal == "*":
        return True
    return (
        isinstance(principal, dict)
        and set(principal) == {"AWS"}
        and _as_set(principal.get("AWS")) == {"*"}
    )


def _has_exact_archive_mutation_deny(policy, bucket_name):
    expected_actions = {
        "s3:abortmultipartupload",
        "s3:bypassgovernanceretention",
        "s3:deleteobject",
        "s3:deleteobjecttagging",
        "s3:deleteobjectversion",
        "s3:putobject",
        "s3:putobjectacl",
        "s3:putobjectlegalhold",
        "s3:putobjectretention",
        "s3:putobjecttagging",
        "s3:restoreobject",
    }
    expected_resource = f"arn:aws:s3:::{bucket_name}/*"

    for statement in policy.get("Statement", []):
        actions = {item.lower() for item in _as_set(statement.get("Action"))}
        resources = _as_set(statement.get("Resource"))
        condition = statement.get("Condition", {})
        condition_shape_is_exact = (
            set(condition) == {"StringNotEqualsIfExists"}
            and {
                item.lower()
                for item in condition.get("StringNotEqualsIfExists", {})
            } == {"aws:principalservicename"}
        )
        if (
            statement.get("Sid") == "DenyNonCloudTrailObjectMutation"
            and statement.get("Effect") == "Deny"
            and actions == expected_actions
            and resources == {expected_resource}
            and _principal_is_all(statement.get("Principal"))
            and condition_shape_is_exact
            and _condition_values(
                condition,
                "StringNotEqualsIfExists",
                "aws:PrincipalServiceName",
            ) == {"cloudtrail.amazonaws.com"}
            and "NotAction" not in statement
            and "NotResource" not in statement
            and "NotPrincipal" not in statement
        ):
            return True
    return False


def _check_alarm_configuration(alarm, expected, expected_actions, alarm_name):
    failures = []
    if not alarm.get("ActionsEnabled"):
        failures.append(f"heartbeat alarm actions are disabled: {alarm_name}")
    if set(alarm.get("AlarmActions", [])) != expected_actions:
        failures.append(f"heartbeat alarm actions differ from approved state: {alarm_name}")

    scalar_fields = (
        "Namespace",
        "MetricName",
        "Statistic",
        "Period",
        "EvaluationPeriods",
        "DatapointsToAlarm",
        "Threshold",
        "ComparisonOperator",
        "TreatMissingData",
    )
    for field in scalar_fields:
        if alarm.get(field) != expected.get(field):
            failures.append(f"heartbeat alarm {field} differs from approved state: {alarm_name}")

    actual_dimensions = {
        item.get("Name"): item.get("Value")
        for item in alarm.get("Dimensions", [])
    }
    if actual_dimensions != expected.get("Dimensions", {}):
        failures.append(f"heartbeat alarm Dimensions differ from approved state: {alarm_name}")

    for field in ("OKActions", "InsufficientDataActions"):
        if set(alarm.get(field, [])) != set(expected.get(field, [])):
            failures.append(f"heartbeat alarm {field} differs from approved state: {alarm_name}")

    for unsupported in ("Metrics", "ExtendedStatistic", "ThresholdMetricId", "Unit"):
        if alarm.get(unsupported) not in (None, []):
            failures.append(f"heartbeat alarm has unexpected {unsupported}: {alarm_name}")
    return failures


def _check_cloudwatch_publish_policy(attributes, topic_arn, source_arn_pattern, label):
    failures = []
    try:
        policy = json.loads(attributes.get("Policy", "{}"))
    except (TypeError, json.JSONDecodeError) as exc:
        return [f"SNS topic policy is not valid JSON: {label}: {exc}"]

    account_id = topic_arn.split(":")[4]
    found = False
    for statement in policy.get("Statement", []):
        principal = statement.get("Principal", {})
        services = _as_set(principal.get("Service")) if isinstance(principal, dict) else set()
        condition = statement.get("Condition", {})
        if (
            statement.get("Effect") == "Allow"
            and {item.lower() for item in _as_set(statement.get("Action"))} == {"sns:publish"}
            and _as_set(statement.get("Resource")) == {topic_arn}
            and services == {"cloudwatch.amazonaws.com"}
            and set(condition) == {"StringEquals", "ArnLike"}
            and _condition_values(condition, "StringEquals", "aws:SourceAccount") == {account_id}
            and _condition_values(condition, "ArnLike", "aws:SourceArn") == {source_arn_pattern}
        ):
            found = True
            break
    if not found:
        failures.append(f"SNS CloudWatch publish policy is missing or weakened: {label}")
    return failures


def _check_selectors(client, trail_name, required_s3_arns):
    response = client.get_event_selectors(TrailName=trail_name)
    selectors = response.get("AdvancedEventSelectors", [])
    management_selector_count = 0
    s3_selector_count = 0
    discovered_s3 = set()
    unexpected_selectors = []

    for selector in selectors:
        fields = {item["Field"]: item for item in selector.get("FieldSelectors", [])}
        categories = _field_values(fields, "eventCategory")
        exact_management = (
            selector.get("Name") == "ManagementReadWrite"
            and set(fields) == {"eventCategory"}
            and set(fields["eventCategory"]) == {"Field", "Equals"}
            and categories == {"Management"}
        )
        exact_s3 = (
            selector.get("Name") == "ApprovedSensitiveS3Objects"
            and categories == {"Data"}
            and "AWS::S3::Object" in _field_values(fields, "resources.type")
            and set(fields) == {"eventCategory", "resources.type", "resources.ARN"}
            and set(fields["eventCategory"]) == {"Field", "Equals"}
            and set(fields["resources.type"]) == {"Field", "Equals"}
            and set(fields["resources.ARN"]) == {"Field", "StartsWith"}
        )
        if exact_management:
            management_selector_count += 1
        elif exact_s3:
            s3_selector_count += 1
            discovered_s3.update(_field_values(fields, "resources.ARN", "StartsWith"))
        else:
            unexpected_selectors.append(selector.get("Name", "<unnamed>"))

    failures = []
    if management_selector_count != 1:
        failures.append("exactly one approved ManagementReadWrite selector is required")
    required = set(required_s3_arns)
    expected_s3_selector_count = 1 if required else 0
    if s3_selector_count != expected_s3_selector_count:
        failures.append("approved S3 selector count differs from expected state")
    if discovered_s3 != required:
        failures.append(
            "S3 data selector differs from approved scope: "
            f"missing={sorted(required - discovered_s3)}, unexpected={sorted(discovered_s3 - required)}"
        )
    if unexpected_selectors:
        failures.append(f"unexpected or weakened advanced selectors: {sorted(unexpected_selectors)}")
    return failures


def _check_rule(client, rule_name, expected, target_arn, label):
    failures = []
    rule = client.describe_rule(Name=rule_name)
    if rule.get("State") not in ("ENABLED", "ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS"):
        failures.append(f"EventBridge rule is not enabled: {label}/{rule_name}")

    actual_pattern = json.loads(rule.get("EventPattern", "{}"))
    actual_detail = actual_pattern.get("detail", {})
    checks = (
        ("source", set(actual_pattern.get("source", [])), set(expected["sources"])),
        ("detail-type", set(actual_pattern.get("detail-type", [])), {"AWS API Call via CloudTrail"}),
        ("detail.eventSource", set(actual_detail.get("eventSource", [])), set(expected["event_sources"])),
        ("detail.eventName", set(actual_detail.get("eventName", [])), set(expected["event_names"])),
    )
    if set(actual_pattern) != {"source", "detail-type", "detail"}:
        failures.append(f"EventBridge pattern has unexpected top-level filters: {label}/{rule_name}")
    if set(actual_detail) != {"eventSource", "eventName"}:
        failures.append(f"EventBridge detail pattern has unexpected filters: {label}/{rule_name}")
    for field, actual, wanted in checks:
        if actual != wanted:
            failures.append(f"EventBridge pattern mismatch {label}/{rule_name}/{field}")

    # Không chỉ so AWS state với giá trị Terraform sinh ra: cách đó luôn PASS kể
    # cả khi Terraform khai báo sai. Invariant này suy source từ chính
    # eventSource nên bắt được cặp sai như aws.cloudwatch + monitoring.amazonaws.com.
    semantic_sources = {
        f"aws.{event_source.split('.', 1)[0]}"
        for event_source in actual_detail.get("eventSource", [])
    }
    if set(actual_pattern.get("source", [])) != semantic_sources:
        failures.append(f"EventBridge source/eventSource semantic mismatch: {label}/{rule_name}")

    targets = client.list_targets_by_rule(Rule=rule_name).get("Targets", [])
    if target_arn not in {item.get("Arn") for item in targets}:
        failures.append(f"EventBridge router target missing: {label}/{rule_name}")
    return failures


def _count_confirmed_subscriptions(client, topic_arn):
    """Đếm subscription đã confirm — GHI NHẬN, không phải invariant.

    Bản trước coi cả PendingConfirmation lẫn Deleted là FAIL. Một người chưa bấm
    link xác nhận là trạng thái onboarding, không phải hệ thống hỏng, mà heartbeat
    chạy 5 phút/lần nên nó biến thành hàng trăm mail mỗi ngày — và mail đó chỉ tới
    được đúng những người ĐÃ confirm. Số liệu vẫn được ghi vào output để dùng làm
    bằng chứng nghiệm thu.
    """
    confirmed = 0
    pending = 0
    token = None
    while True:
        kwargs = {"TopicArn": topic_arn}
        if token:
            kwargs["NextToken"] = token
        response = client.list_subscriptions_by_topic(**kwargs)
        for subscription in response.get("Subscriptions", []):
            if subscription.get("SubscriptionArn", "").startswith("arn:"):
                confirmed += 1
            else:
                pending += 1
        token = response.get("NextToken")
        if not token:
            break
    return {"confirmed": confirmed, "unconfirmed": pending}


def _check_router_integrity(client, function_arn, expected, label):
    """So cấu hình router thật với trạng thái đã được Terraform duyệt.

    State=Active là chưa đủ: router có thể bị thay code thành no-op mà vẫn
    Active, khi đó alert bị nuốt hoàn toàn trong im lặng. detectorConfig nằm
    trong danh sách vì đó là nơi chứa critical_group_numbers — sửa nó là cách
    gỡ bypass allowlist mà không cần đụng tới code.
    """
    failures = []
    config = client.get_function_configuration(FunctionName=function_arn)

    if config.get("State") != "Active" or config.get("LastUpdateStatus") not in (None, "Successful"):
        failures.append(f"{label} Lambda is not healthy")

    if not expected:
        failures.append(f"{label} has no approved baseline in ROUTER_EXPECTED_JSON")
        return failures

    checks = (
        ("code", config.get("CodeSha256"), expected.get("codeSha256")),
        ("handler", config.get("Handler"), expected.get("handler")),
        ("role", config.get("Role"), expected.get("roleArn")),
        (
            "detector config",
            (config.get("Environment") or {}).get("Variables", {}).get("DETECTOR_CONFIG_JSON"),
            expected.get("detectorConfig"),
        ),
    )
    for field, actual, wanted in checks:
        if wanted and actual != wanted:
            failures.append(f"{label} {field} differs from the approved deployment")

    concurrency = client.get_function_concurrency(FunctionName=function_arn)
    if "ReservedConcurrentExecutions" in concurrency:
        failures.append(f"{label} Lambda has unexpected reserved concurrency")

    return failures


def _check_bounded_principals(client, expected_boundaries):
    """Xác nhận permissions boundary vẫn còn attach trên từng principal đã duyệt.

    Với `gitlab-ci-deployer` việc attach là thủ công (user nằm ngoài Terraform
    state), nên không có gì cưỡng chế nó tồn tại. Nếu ai đó gỡ, chỉ CloudTrail
    bắt được — trừ khi heartbeat cũng kiểm tra. Map rỗng nghĩa là chưa tới
    Phase 4b; khi đó bỏ qua để không FAIL giả.
    """
    failures = []
    for principal_arn, expected_boundary_arn in expected_boundaries.items():
        name = principal_arn.rsplit("/", 1)[-1]
        try:
            if ":user/" in principal_arn:
                entity = client.get_user(UserName=name)["User"]
            elif ":role/" in principal_arn:
                entity = client.get_role(RoleName=name)["Role"]
            else:
                failures.append(f"unsupported bounded principal ARN: {principal_arn}")
                continue
        except Exception as exc:
            failures.append(f"bounded principal check failed: {principal_arn}: {type(exc).__name__}: {exc}")
            continue

        actual = (entity.get("PermissionsBoundary") or {}).get("PermissionsBoundaryArn")
        if actual != expected_boundary_arn:
            failures.append(
                f"permissions boundary missing or changed on {principal_arn}: "
                f"expected {expected_boundary_arn}, found {actual}"
            )
    return failures


def _publish_independently(destinations, subject, message):
    delivered = []
    failures = []
    for client, topic_arn, label in destinations:
        try:
            client.publish(TopicArn=topic_arn, Subject=subject, Message=message)
            delivered.append(label)
        except Exception as exc:
            failures.append(f"{label}: {type(exc).__name__}: {exc}")
    return delivered, failures


def handler(event, _context):
    region = os.environ["PRIMARY_REGION"]
    global_region = os.environ["GLOBAL_REGION"]
    trail_name = os.environ["TRAIL_NAME"]
    bucket_name = os.environ["AUDIT_BUCKET_NAME"]
    topic_arn = os.environ["ALERT_TOPIC_ARN"]
    global_topic_arn = os.environ["GLOBAL_ALERT_TOPIC_ARN"]
    required_bucket_kms_key_arn = os.environ["REQUIRED_BUCKET_KMS_KEY_ARN"]
    max_log_age = int(os.environ["MAX_LOG_DELIVERY_AGE_MINUTES"])
    max_digest_age = int(os.environ["MAX_DIGEST_DELIVERY_AGE_MINUTES"])
    required_retention = int(os.environ["REQUIRED_RETENTION_DAYS"])
    required_lifecycle = int(os.environ["REQUIRED_LIFECYCLE_DAYS"])
    eks_cluster_name = os.environ["EKS_CLUSTER_NAME"]
    primary_rules = json.loads(os.environ["PRIMARY_RULES_JSON"])
    global_rules = json.loads(os.environ["GLOBAL_RULES_JSON"])
    primary_router_arn = os.environ["PRIMARY_ROUTER_ARN"]
    global_router_arn = os.environ["GLOBAL_ROUTER_ARN"]
    router_expected = json.loads(os.environ["ROUTER_EXPECTED_JSON"])
    bounded_principals = json.loads(os.environ.get("BOUNDED_PRINCIPALS_JSON", "{}"))
    schedule_rule_name = os.environ["HEARTBEAT_SCHEDULE_RULE_NAME"]
    heartbeat_function_arn = os.environ["HEARTBEAT_FUNCTION_ARN"]
    alarm_names = json.loads(os.environ["HEARTBEAT_ALARM_NAMES_JSON"])
    expected_alarm_config = json.loads(os.environ["HEARTBEAT_ALARM_CONFIG_JSON"])
    expected_alarm_actions = set(json.loads(os.environ["HEARTBEAT_ALARM_ACTION_ARNS_JSON"]))
    alarm_source_arn_pattern = os.environ["HEARTBEAT_ALARM_SOURCE_ARN_PATTERN"]
    required_s3_arns = json.loads(os.environ["S3_DATA_EVENT_ARNS_JSON"])

    cloudtrail = boto3.client("cloudtrail", region_name=region)
    s3 = boto3.client("s3", region_name=region)
    sns = boto3.client("sns", region_name=region)
    sns_global = boto3.client("sns", region_name=global_region)
    events_primary = boto3.client("events", region_name=region)
    events_global = boto3.client("events", region_name=global_region)
    lambda_primary = boto3.client("lambda", region_name=region)
    lambda_global = boto3.client("lambda", region_name=global_region)
    cloudwatch = boto3.client("cloudwatch", region_name=region)
    eks = boto3.client("eks", region_name=region)
    iam = boto3.client("iam")
    failures = []

    direct_alert_destinations = (
        (sns, topic_arn, region),
        (sns_global, global_topic_arn, global_region),
    )

    # Chế độ test đường alert: KHÔNG chạy health check nào. Status dùng tiền tố
    # TEST- để output này không bị nhầm thành bằng chứng heartbeat healthy.
    if isinstance(event, dict) and event.get("forceAlertTest") is True:
        test_result = {
            "checkedAt": datetime.now(timezone.utc).isoformat(),
            "mode": "forceAlertTest",
            "status": "TEST",
            "message": "Mandate 12 heartbeat direct alert-path test; no audit configuration was checked or changed.",
        }
        delivered, delivery_failures = _publish_independently(
            direct_alert_destinations,
            "TEST: TF3 Mandate 12 heartbeat alert paths",
            json.dumps(test_result, indent=2),
        )
        test_result["alertDeliveredTo"] = delivered
        test_result["alertDeliveryFailures"] = delivery_failures
        test_result["status"] = (
            "TEST-PASS" if len(delivered) == len(direct_alert_destinations) else "TEST-FAIL"
        )
        print(json.dumps(test_result, default=str))
        if test_result["status"] != "TEST-PASS":
            raise RuntimeError("one or more heartbeat direct alert paths failed")
        return test_result

    try:
        trails = cloudtrail.describe_trails(trailNameList=[trail_name], includeShadowTrails=False)
        if len(trails.get("trailList", [])) != 1:
            failures.append("exactly one protected CloudTrail configuration was not found")
        else:
            trail = trails["trailList"][0]
            if trail.get("S3BucketName") != bucket_name:
                failures.append("CloudTrail destination bucket differs from approved bucket")
            if not trail.get("IsMultiRegionTrail"):
                failures.append("CloudTrail is no longer multi-region")
            if not trail.get("IncludeGlobalServiceEvents"):
                failures.append("CloudTrail no longer includes global service events")
            if not trail.get("LogFileValidationEnabled"):
                failures.append("CloudTrail log-file validation is disabled")

        status = cloudtrail.get_trail_status(Name=trail_name)
        if not status.get("IsLogging"):
            failures.append("CloudTrail IsLogging is false")
        delivery_age = _age_minutes(status.get("LatestDeliveryTime"))
        if delivery_age is None or delivery_age > max_log_age:
            failures.append(f"LatestDeliveryTime is missing or older than {max_log_age} minutes")
        digest_age = _age_minutes(status.get("LatestDigestDeliveryTime"))
        if digest_age is None or digest_age > max_digest_age:
            failures.append(f"LatestDigestDeliveryTime is missing or older than {max_digest_age} minutes")
        for key in ("LatestDeliveryError", "LatestDigestDeliveryError"):
            if status.get(key):
                failures.append(f"{key}: {status[key]}")
        failures.extend(_check_selectors(cloudtrail, trail_name, required_s3_arns))
    except Exception as exc:
        failures.append(f"CloudTrail check failed: {type(exc).__name__}: {exc}")

    try:
        versioning = s3.get_bucket_versioning(Bucket=bucket_name)
        if versioning.get("Status") != "Enabled":
            failures.append("audit bucket versioning is not Enabled")
        lock = s3.get_object_lock_configuration(Bucket=bucket_name).get("ObjectLockConfiguration", {})
        retention = lock.get("Rule", {}).get("DefaultRetention", {})
        if lock.get("ObjectLockEnabled") != "Enabled":
            failures.append("audit bucket Object Lock is not Enabled")
        if retention.get("Mode") != "COMPLIANCE" or retention.get("Days", 0) < required_retention:
            failures.append("audit bucket retention is not COMPLIANCE at the required duration")

        lifecycle = s3.get_bucket_lifecycle_configuration(Bucket=bucket_name)
        # Chỉ xét rule có Expiration. Rule chỉ có Transition (ví dụ tiering
        # Glacier IR nếu sau này được duyệt) không được coi là retention 0 ngày.
        expiration_days = [
            rule["Expiration"]["Days"]
            for rule in lifecycle.get("Rules", [])
            if rule.get("Status") == "Enabled"
            and rule.get("Expiration", {}).get("Days") is not None
        ]
        if not expiration_days or min(expiration_days) < required_lifecycle:
            failures.append("audit bucket lifecycle is shorter than the approved retention")
        noncurrent_expiration_days = [
            rule["NoncurrentVersionExpiration"]["NoncurrentDays"]
            for rule in lifecycle.get("Rules", [])
            if rule.get("Status") == "Enabled"
            and rule.get("NoncurrentVersionExpiration", {}).get("NoncurrentDays") is not None
        ]
        if not noncurrent_expiration_days or min(noncurrent_expiration_days) < required_lifecycle:
            failures.append("audit bucket noncurrent-version lifecycle is shorter than approved")

        # PM-126 đã đưa bucket từ AES256 sang CMK. Kiểm cả thuật toán LẪN key:
        # đúng "aws:kms" nhưng trỏ sang key khác vẫn là mất quyền kiểm soát khoá,
        # mà kẻ tấn công đổi key thì bucket vẫn "được mã hoá" trên giấy tờ.
        encryption = s3.get_bucket_encryption(Bucket=bucket_name)
        rules = encryption.get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
        defaults = [rule.get("ApplyServerSideEncryptionByDefault", {}) for rule in rules]
        algorithms = {item.get("SSEAlgorithm") for item in defaults}
        key_ids = {item.get("KMSMasterKeyID") for item in defaults}
        if algorithms != {"aws:kms"}:
            failures.append("audit bucket default encryption is not aws:kms")
        elif key_ids != {required_bucket_kms_key_arn}:
            failures.append("audit bucket is encrypted with a key other than the approved audit key")

        public_access = s3.get_public_access_block(Bucket=bucket_name)["PublicAccessBlockConfiguration"]
        if not all(public_access.get(key) for key in (
            "BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets"
        )):
            failures.append("audit bucket public-access block is incomplete")
        if s3.get_bucket_policy_status(Bucket=bucket_name).get("PolicyStatus", {}).get("IsPublic"):
            failures.append("audit bucket policy is public")
        policy = json.loads(s3.get_bucket_policy(Bucket=bucket_name)["Policy"])
        if not _has_exact_archive_mutation_deny(policy, bucket_name):
            failures.append("audit bucket non-CloudTrail object-mutation deny is missing or weakened")
    except Exception as exc:
        failures.append(f"S3 audit bucket check failed: {type(exc).__name__}: {exc}")

    for client, expected_rules, router_arn, label in (
        (events_primary, primary_rules, primary_router_arn, region),
        (events_global, global_rules, global_router_arn, global_region),
    ):
        for rule_name, expected in expected_rules.items():
            try:
                failures.extend(_check_rule(client, rule_name, expected, router_arn, label))
            except Exception as exc:
                failures.append(f"EventBridge rule check failed: {label}/{rule_name}: {type(exc).__name__}: {exc}")

    try:
        schedule = events_primary.describe_rule(Name=schedule_rule_name)
        if schedule.get("State") != "ENABLED" or schedule.get("ScheduleExpression") != "rate(5 minutes)":
            failures.append("heartbeat schedule rule configuration differs from approved state")
        schedule_targets = events_primary.list_targets_by_rule(Rule=schedule_rule_name).get("Targets", [])
        if heartbeat_function_arn not in {item.get("Arn") for item in schedule_targets}:
            failures.append("heartbeat schedule target is missing")
    except Exception as exc:
        failures.append(f"heartbeat schedule check failed: {type(exc).__name__}: {exc}")

    for client, function_arn, label in (
        (lambda_primary, primary_router_arn, "primary router"),
        (lambda_global, global_router_arn, "global router"),
    ):
        try:
            failures.extend(_check_router_integrity(
                client,
                function_arn,
                router_expected.get(function_arn),
                label,
            ))
        except Exception as exc:
            failures.append(f"{label} Lambda check failed: {type(exc).__name__}: {exc}")

    try:
        alarms = cloudwatch.describe_alarms(AlarmNames=alarm_names).get("MetricAlarms", [])
        alarms_by_name = {alarm["AlarmName"]: alarm for alarm in alarms}
        for alarm_name in alarm_names:
            alarm = alarms_by_name.get(alarm_name)
            if not alarm:
                failures.append(f"heartbeat alarm is missing: {alarm_name}")
            else:
                failures.extend(_check_alarm_configuration(
                    alarm,
                    expected_alarm_config[alarm_name],
                    expected_alarm_actions,
                    alarm_name,
                ))
    except Exception as exc:
        failures.append(f"CloudWatch alarm check failed: {type(exc).__name__}: {exc}")

    subscription_counts = {}
    for client, current_topic, label in (
        (sns, topic_arn, region),
        (sns_global, global_topic_arn, global_region),
    ):
        try:
            attributes = client.get_topic_attributes(TopicArn=current_topic).get("Attributes", {})
            subscription_counts[label] = _count_confirmed_subscriptions(client, current_topic)
            if current_topic in expected_alarm_actions:
                failures.extend(_check_cloudwatch_publish_policy(
                    attributes,
                    current_topic,
                    alarm_source_arn_pattern,
                    label,
                ))
        except Exception as exc:
            failures.append(f"SNS alert path check failed: {label}: {type(exc).__name__}: {exc}")

    if bounded_principals:
        failures.extend(_check_bounded_principals(iam, bounded_principals))

    try:
        logging_config = eks.describe_cluster(name=eks_cluster_name)["cluster"].get("logging", {})
        enabled_types = set()
        for entry in logging_config.get("clusterLogging", []):
            if entry.get("enabled"):
                enabled_types.update(entry.get("types", []))
        if "audit" not in enabled_types:
            failures.append("EKS control-plane audit logging is not enabled")
    except Exception as exc:
        failures.append(f"EKS audit logging check failed: {type(exc).__name__}: {exc}")

    result = {
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "trail": trail_name,
        "status": "FAIL" if failures else "PASS",
        "failures": failures,
        # Ghi nhận, không phải invariant — xem _count_confirmed_subscriptions.
        "subscriptions": subscription_counts,
    }
    if failures:
        delivered, delivery_failures = _publish_independently(
            direct_alert_destinations,
            "CRITICAL: TF3 Mandate 12 audit heartbeat failed",
            json.dumps(result, indent=2, default=str),
        )
        result["alertDeliveredTo"] = delivered
        result["alertDeliveryFailures"] = delivery_failures
        print(json.dumps(result, default=str))
        if not delivered:
            raise RuntimeError("heartbeat failed and both direct alert paths failed")
    else:
        print(json.dumps(result, default=str))
    return result
