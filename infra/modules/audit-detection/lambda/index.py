import json
import logging
import os
from datetime import datetime, timezone

import boto3


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

SNS = boto3.client("sns")
CLOUDWATCH = boto3.client("cloudwatch")

ALERT_TOPIC_ARN = os.environ["ALERT_TOPIC_ARN"]
METRIC_NAMESPACE = os.environ.get("METRIC_NAMESPACE", "TechX/AuditDetection")
DEPLOYMENT_LABEL = os.environ.get("DEPLOYMENT_LABEL", "unknown")
CONFIG = json.loads(os.environ.get("DETECTOR_CONFIG_JSON", "{}"))

GROUP_MAP = {
    "cloudtrail:StopLogging": 1,
    "cloudtrail:DeleteTrail": 1,
    "cloudtrail:UpdateTrail": 1,
    "cloudtrail:PutEventSelectors": 1,
    "cloudtrail:StartLogging": 1,
    "logs:DeleteLogGroup": 1,
    "logs:PutRetentionPolicy": 1,
    "iam:CreateAccessKey": 2,
    "iam:CreateUser": 2,
    "iam:CreateRole": 2,
    "iam:CreateLoginProfile": 2,
    "iam:UpdateAssumeRolePolicy": 3,
    "iam:AttachUserPolicy": 3,
    "iam:AttachRolePolicy": 3,
    "iam:PutUserPolicy": 3,
    "iam:PutRolePolicy": 3,
    "iam:CreatePolicyVersion": 3,
    "iam:SetDefaultPolicyVersion": 3,
    "iam:AddUserToGroup": 3,
    "iam:UpdateUser": 3,
    "eks:CreateAccessEntry": 4,
    "eks:UpdateAccessEntry": 4,
    "eks:DeleteAccessEntry": 4,
    "eks:AssociateAccessPolicy": 4,
    "eks:DisassociateAccessPolicy": 4,
    "secretsmanager:GetSecretValue": 5,
    "secretsmanager:BatchGetSecretValue": 5,
    "eks:DeleteCluster": 6,
    "eks:DeleteNodegroup": 6,
    "rds:DeleteDBInstance": 6,
    "rds:DeleteDBCluster": 6,
    "elasticache:DeleteReplicationGroup": 6,
    "elasticache:DeleteCacheCluster": 6,
    "kms:ScheduleKeyDeletion": 6,
    "secretsmanager:DeleteSecret": 6,
    "s3:DeleteBucket": 6,
}


def handler(event, _context):
    detail = event.get("detail", {})
    event_source = detail.get("eventSource", "")
    event_name = detail.get("eventName", "")
    event_key = f"{event_source.replace('.amazonaws.com', '')}:{event_name}"
    group = GROUP_MAP.get(event_key)

    if group is None:
        LOGGER.info(json.dumps({"ignored": True, "reason": "unmapped_event", "event_key": event_key}))
        return {"ignored": True, "reason": "unmapped_event", "event_key": event_key}

    actor = extract_actor(detail.get("userIdentity", {}))
    target = extract_target(detail)

    if is_allowed_automation(actor):
        LOGGER.info(json.dumps({"ignored": True, "reason": "allowlisted_automation", "actor": actor, "event_key": event_key}))
        return {"ignored": True, "reason": "allowlisted_automation", "actor": actor, "event_key": event_key}

    if is_suppressed(actor, target):
        LOGGER.info(json.dumps({"ignored": True, "reason": "suppressed", "actor": actor, "target": target, "event_key": event_key}))
        return {"ignored": True, "reason": "suppressed", "actor": actor, "target": target, "event_key": event_key}

    if group == 5 and not should_alert_secret_read(actor, target):
        LOGGER.info(json.dumps({"ignored": True, "reason": "non_human_or_unwatched_secret", "actor": actor, "target": target}))
        return {"ignored": True, "reason": "non_human_or_unwatched_secret", "actor": actor, "target": target}

    event_time = parse_time(detail.get("eventTime"))
    detected_at = datetime.now(timezone.utc)
    ttd_seconds = max(0, int((detected_at - event_time).total_seconds()))
    severity = map_severity(group, target)

    payload = {
        "severity": severity,
        "group": group,
        "rule_name": event.get("resources", ["eventbridge-rule-unknown"])[0],
        "event_name": event_name,
        "actor": {
            "principal": actor,
            "type": detail.get("userIdentity", {}).get("type"),
        },
        "when": {
            "eventTime": detail.get("eventTime"),
            "detectedAt": detected_at.isoformat(),
            "time_to_detect_seconds": ttd_seconds,
        },
        "from_where": {
            "sourceIPAddress": detail.get("sourceIPAddress"),
            "awsRegion": detail.get("awsRegion"),
            "userAgent": detail.get("userAgent"),
        },
        "target": target,
        "request_summary": summarize_request(detail.get("requestParameters", {})),
        "investigation_hint": f"Check CloudTrail for eventName={event_name} actor={actor}",
        "deployment_label": DEPLOYMENT_LABEL,
    }

    LOGGER.info(json.dumps(payload))
    publish_metric(group, severity, ttd_seconds)
    publish_alert(payload)
    return {"sent": True, "severity": severity, "group": group, "ttd_seconds": ttd_seconds}


def extract_actor(user_identity):
    actor_type = user_identity.get("type")
    session_issuer = (((user_identity.get("sessionContext") or {}).get("sessionIssuer")) or {})
    if session_issuer.get("arn"):
        return session_issuer["arn"]
    if user_identity.get("arn"):
        return user_identity["arn"]
    if user_identity.get("userName"):
        return user_identity["userName"]
    if user_identity.get("principalId"):
        return user_identity["principalId"]
    return actor_type or "unknown"


def extract_target(detail):
    request = detail.get("requestParameters") or {}
    for key in [
        "userName",
        "roleName",
        "groupName",
        "secretId",
        "name",
        "clusterName",
        "trailName",
        "bucketName",
        "keyId",
        "dbInstanceIdentifier",
        "dbClusterIdentifier",
        "replicationGroupId",
        "cacheClusterId",
        "principalArn",
    ]:
        value = request.get(key)
        if value:
            return str(value)

    resources = detail.get("resources") or []
    if resources:
        first = resources[0]
        if isinstance(first, dict):
            return first.get("ARN") or first.get("arn") or json.dumps(first)
        return str(first)

    return "unknown"


def should_alert_secret_read(actor, target):
    target_name = target or ""
    watched = CONFIG.get("sensitive_secret_names") or []
    if watched and not any(secret_name in target_name for secret_name in watched):
        return False

    if matches_any(actor, CONFIG.get("secret_reader_principals") or []):
        return False

    human_principals = CONFIG.get("human_principals") or []
    if not human_principals:
        return True

    return matches_any(actor, human_principals)


def is_allowed_automation(actor):
    return matches_any(actor, CONFIG.get("allowed_principals") or [])


def is_suppressed(actor, target):
    now = datetime.now(timezone.utc)
    for suppression in CONFIG.get("suppressions") or []:
        if suppression.get("actor") not in ("*", actor):
            continue
        resource = suppression.get("resource", "*")
        if resource not in ("*", target) and resource not in (target or ""):
            continue
        start = parse_time(suppression.get("start"))
        end = parse_time(suppression.get("end"))
        if start <= now <= end:
            return True
    return False


def matches_any(actor, candidates):
    for candidate in candidates:
        if actor == candidate:
            return True
    return False


def map_severity(group, target):
    if group in set(CONFIG.get("critical_group_numbers") or []):
        return "critical"
    if group == 6:
        lowered_target = (target or "").lower()
        for keyword in CONFIG.get("critical_group_6_target_keywords") or []:
            if keyword in lowered_target:
                return "critical"
        return "high"
    if group in (3, 5):
        return "high"
    return "info"


def summarize_request(request_parameters):
    if not request_parameters:
        return {}
    summary = {}
    for key in sorted(request_parameters.keys()):
        if key.lower() in {"secretstring", "secretbinary"}:
            continue
        value = request_parameters[key]
        if isinstance(value, (dict, list)):
            summary[key] = json.dumps(value)[:200]
        else:
            summary[key] = str(value)[:200]
    return summary


def publish_metric(group, severity, ttd_seconds):
    CLOUDWATCH.put_metric_data(
        Namespace=METRIC_NAMESPACE,
        MetricData=[
            {
                "MetricName": "AuditDetectionLatencySeconds",
                "Unit": "Seconds",
                "Value": ttd_seconds,
                "Dimensions": [
                    {"Name": "DeploymentLabel", "Value": DEPLOYMENT_LABEL},
                    {"Name": "Group", "Value": str(group)},
                    {"Name": "Severity", "Value": severity},
                ],
            }
        ],
    )


def publish_alert(payload):
    subject = (
        f"[{payload['severity'].upper()}][Audit][{DEPLOYMENT_LABEL}] "
        f"{payload['event_name']} by {payload['actor']['principal']} "
        f"(TTD {payload['when']['time_to_detect_seconds']}s)"
    )
    SNS.publish(
        TopicArn=ALERT_TOPIC_ARN,
        Subject=subject[:100],
        Message=json.dumps(payload, indent=2),
    )


def parse_time(value):
    if not value:
        return datetime.now(timezone.utc)
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)
