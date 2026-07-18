# Mandate 11 Audit Detection Review

## 1. Short Conclusion

The recommended direction for Mandate 11 is to treat auditability as an active detection problem, not only a post-incident investigation capability.

The implementation should focus on:

- high-risk control-plane behaviors;
- alert routing to a real human recipient;
- time-to-detect measurement;
- low operational noise.

## 2. Recommended Detection Architecture

### 2.1. Minimum alerting flow

`CloudTrail management events -> EventBridge rules -> Lambda audit-alert-router -> SNS topic -> operator email`

Why this is the right baseline:

- **Outside the EKS cluster**: if the cluster is under attack, the detection path still works.
- **Low cost**: no need for SIEM, CloudTrail Lake, or Security Hub for this mandate.
- **Fast enough**: EventBridge on CloudTrail management events is generally fast enough for a minutes-level alerting commitment.
- **Easy to demo**: the mentor can run `aws iam create-access-key ...` or `aws eks create-access-entry ...` and wait for the alert.

### 2.2. Alert delivery channel

Based on the current repo and environment, the recommended first channel is:

- **Primary**: `SNS email` to the right recipients
- **Optional**: `AWS Chatbot` only if the team already has a working Slack path

Email should come first because it is:

- simpler to deploy;
- independent from Slack workspace setup and permissions;
- sufficient to satisfy the requirement that the alert must actually reach a person.

### 2.3. Terraform components that should exist

- `infra/modules/audit-detection/`
  - `main.tf`
  - `variables.tf`
  - `outputs.tf`
  - a small Lambda folder such as `lambda/index.py`
- `infra/live/production/audit-detection.tf`
- `docs/adr/0010-mandate-11-audit-detection.md`
- `docs/runbooks/mandate-11-audit-detection-demo.md`

This should stay separate from the existing EKS module. This is control-plane security and audit detection, not application runtime logic.

---

## 3. What Must Be Detected For CDO01, CDO02, and the Mentor

This is the core of the review. The point is not “which AWS service should be enabled,” but:

**Given that `CDO01`, `CDO02`, and `mentor` are all IAM users with `AdministratorAccess`, which behaviors must trigger detection if their accounts or keys are misused?**

The grouping below is behavior-based, not service-based.

### 3.1. Group 1 - Actions that blind the system

This group must always alert at the highest level, regardless of whether the actor is `CDO01`, `CDO02`, or `mentor`.

What must be detected:

- disabling audit or log collection;
- changing logging so it no longer captures the same evidence as before;
- deleting logs;
- shortening retention for audit logs;
- deleting or weakening the storage location that holds audit evidence.

API/actions to match directly:

- `cloudtrail:StopLogging`
- `cloudtrail:DeleteTrail`
- `cloudtrail:UpdateTrail`
- `cloudtrail:PutEventSelectors`
- `cloudtrail:StartLogging` when it follows an unexpected stop or occurs on a sensitive trail
- `logs:DeleteLogGroup`
- `logs:PutRetentionPolicy`
- plus any direct bucket or KMS policy change that affects the audit log storage path, if configured

Why this group matters:

- Attackers often disable visibility before doing anything else.
- Even a short logging gap can break the evidence chain.
- In the current model, every admin user can do this, so this must always be treated as `critical`.

Operational interpretation:

- If `CDO01` does this, alert.
- If `CDO02` does this, alert.
- If `mentor` does this, alert.
- “They are an admin, so maybe they meant it” is not a valid reason to suppress detection.

### 3.2. Group 2 - Actions that create a new way into the environment

This is the next most important group. The core idea is **creating a new credential, a new principal, a new login path, or a new persistence point**.

What must be detected:

- creating a new access key;
- creating a new IAM user;
- creating a new role for human use;
- creating a new login profile;
- changing trust policy so another principal can assume a role;
- attaching policy that increases a principal’s effective power;
- creating a new policy version and making it the default.

API/actions to match directly:

- `iam:CreateAccessKey`
- `iam:CreateUser`
- `iam:CreateRole`
- `iam:CreateLoginProfile`
- `iam:UpdateAssumeRolePolicy`
- `iam:AttachUserPolicy`
- `iam:AttachRolePolicy`
- `iam:PutUserPolicy`
- `iam:PutRolePolicy`
- `iam:CreatePolicyVersion`
- `iam:SetDefaultPolicyVersion`

Why this group matters:

- In the current IAM-user-admin model, a new access key is effectively a new side door.
- If an attacker gets one admin key, creating another credential is a common persistence step.
- From an audit perspective, this is an immediate expansion of attack surface.

Per-actor interpretation:

- `CDO01`: a new access key or role outside planned and reviewed change must alert.
- `CDO02`: same.
- `mentor`: this should alert even more strongly, because the mentor should not need to create new credentials to verify the mandate.

Important principle:

- Detection should fire first.
- Legitimacy is investigated after the alert, not before it.

### 3.3. Group 3 - Actions that broaden administrative power beyond expected scope

This group is not always about creating a new identity. It is about **making an existing identity more powerful than before**.

What must be detected:

- attaching a high-privilege policy to an existing user or role;
- switching a policy to a broader default version;
- changing trust relationships so additional principals can use a role;
- adding a user to a privileged group;
- renaming an IAM user in a way that obscures attribution or disguises a privileged identity;
- turning a previously narrow access path into a broad one.

API/actions to match directly:

- `iam:AttachUserPolicy`
- `iam:AttachRolePolicy`
- `iam:PutUserPolicy`
- `iam:PutRolePolicy`
- `iam:CreatePolicyVersion`
- `iam:SetDefaultPolicyVersion`
- `iam:UpdateAssumeRolePolicy`
- `iam:AddUserToGroup`
- `iam:UpdateUser`
- plus any permission-boundary or access-path mutation API if the team later uses them

Why this group matters:

- In an environment that already has admins, many privilege-expanding changes appear small while still being clear abuse indicators.
- These are the exact changes that can be disguised as “just making operations easier.”

Per-actor interpretation:

- `CDO01`: even if working on hardening, silent privilege expansion for people or automation must still alert.
- `CDO02`: if extra privilege is added for emergency operations, it still needs an alert unless it was explicitly pre-approved and time-bounded.
- `mentor`: there is no valid review-time reason for the mentor to broaden their own access or someone else’s.

### 3.4. Group 4 - Actions that open the cluster or runtime to more access

For this repository, changes to EKS access are especially important because they bridge AWS control-plane authority into actual runtime control.

What must be detected:

- adding cluster access for a principal;
- modifying an access entry so an existing principal gets more access;
- associating cluster admin level access;
- creating a new access path into private operational runtime resources.

API/actions to match directly:

- `eks:CreateAccessEntry`
- `eks:UpdateAccessEntry`
- `eks:DeleteAccessEntry`
- `eks:AssociateAccessPolicy`
- `eks:DisassociateAccessPolicy`
- plus any direct API used later to widen private bastion or operational UI access paths

Why this group matters:

- This is the step from “can touch AWS” to “can control workloads.”
- If someone adds or changes EKS access outside Git/Terraform change management, that is a direct bypass.

Per-actor interpretation:

- `CDO01` and `CDO02` are already admins, so any further expansion of cluster access still matters and still should alert.
- `mentor` should only have the review scope already granted; creating a new access path should be treated as abnormal immediately.

### 3.5. Group 5 - Access to sensitive secrets by a human account

Since the team still uses admin IAM users, any secret access by a human identity deserves review.

What must be detected:

- reading operationally sensitive secrets;
- reading application secrets that are normally only needed by automation;
- reading secrets outside a planned maintenance window or outside a known purpose.

API/actions to match directly:

- `secretsmanager:GetSecretValue`
- `secretsmanager:BatchGetSecretValue` if the account uses it

Secrets that should be watched at minimum:

- `techx-corp-tf3/flagd-sync-token` or the exact secret name in use
- RDS / MSK / ElastiCache secrets if Mandate #8 moves them into Secrets Manager

Why this group matters:

- Secret reads are often a preparation step for larger actions.
- If an admin key is compromised, attackers often pivot into secrets next.
- For a human operator, reading secrets should be an exception, not the default path.

Per-actor interpretation:

- `CDO01`: there may be rare legitimate cases, but it still requires signal.
- `CDO02`: same.
- `mentor`: there is almost never a valid reason to read secrets while only verifying the mandate.

Important note:

- This detection must filter out known legitimate automation, otherwise it will be too noisy.
- The audit target here is **human secret access**, not every secret access event.

### 3.6. Group 6 - Destructive actions that remove recovery paths

This group is not only “delete resource.” It is specifically about deleting what the team needs in order to recover, roll back, or continue investigating.

What must be detected:

- deleting the cluster, node groups, datastores, secrets, keys, or log buckets;
- scheduling key deletion;
- deleting test or canary resources used for verification;
- deleting components that support rollback or post-incident analysis.

API/actions to match directly:

- `eks:DeleteCluster`
- `eks:DeleteNodegroup`
- `rds:DeleteDBInstance`
- `rds:DeleteDBCluster`
- `elasticache:DeleteReplicationGroup`
- `elasticache:DeleteCacheCluster`
- `kms:ScheduleKeyDeletion`
- `secretsmanager:DeleteSecret`
- `s3:DeleteBucket`
- `cloudtrail:DeleteTrail`

Why this group matters:

- Some deletions do not cause immediate outage, but they remove the recovery path.
- For an auditability mandate, losing rollback or evidence paths is itself a dangerous event.

Per-actor interpretation:

- `CDO01`: deleting defensive controls or evidence stores must alert.
- `CDO02`: deleting important data or runtime infrastructure must alert.
- `mentor`: the mentor should not be deleting foundational resources during verification.

### 3.7. Summary for these three admin actors

If this needs to be explained simply to the mentor or to the team:

- `CDO01`, `CDO02`, and `mentor` are **all admins**, so “did the user have permission?” is not a useful detection criterion.
- Detection therefore has to focus on **behavior**:
  - blinding audit trails;
  - creating new access paths;
  - broadening privilege;
  - broadening cluster or runtime access;
  - reading secrets from a human account;
  - destroying resources or recovery paths.
- Every alert must include:
  - who;
  - what;
  - when;
  - from where;
  - and how long detection took.

---

## 4. What Should Not Be Done In The First Iteration

- Do not deploy `Security Hub`, `GuardDuty`, `CloudTrail Lake`, or an `OpenSearch SIEM` just to pass this mandate.
- Do not alert on all `Describe*`, `List*`, or `Get*` actions; that will create noise immediately.
- Do not depend on Grafana or Prometheus inside the cluster for this control-plane audit detection path; if the cluster is affected, the detector may fail with it.
- Do not claim “we can perfectly distinguish legitimate admin actions from malicious ones” while the team still uses admin IAM users with static keys.

---

## 5. What Every Alert Must Include

Each alert should contain at least:

- `severity`
- `rule_name`
- `event_name`
- `actor`
  - `userIdentity.type`
  - `userName` or `arn`
- `when`
  - `eventTime`
  - `detectedAt`
  - `time_to_detect_seconds`
- `from_where`
  - `sourceIPAddress`
  - `awsRegion`
  - `userAgent`
- `target`
  - resource ARN or resource name if present
- `request_summary`
  - a short, filtered summary of the important request parameters
- `investigation_hint`
  - for example: “check CloudTrail Event History for eventName=CreateAccessKey and actor=<user>”

Example email subject:

`[CRITICAL][Audit] CreateAccessKey by arn:aws:iam::197826770971:user/CDO02 from 203.x.x.x (TTD 47s)`

The message body should stay short enough to be readable on a phone.

---

## 6. How Time-To-Detect Should Be Measured

### 6.1. Suggested commitment

Recommended public commitment:

- **Commitment to mentor**: the alert reaches a human in **<= 5 minutes**
- **Internal goal**: median **< 90 seconds**, p95 **< 180 seconds**

Why this is the right level:

- It is realistic enough for AWS event latency variation.
- It is strong enough to demonstrate active detection.
- It avoids overcommitting to an unrealistic “under 30 seconds” target.

### 6.2. How to calculate it

Inside the alerting Lambda:

- extract `event_time = detail.eventTime` from the CloudTrail event;
- compute `detected_at = now()`;
- calculate `ttd_seconds = detected_at - event_time`.

Then:

- include `ttd_seconds` in the alert payload;
- write structured JSON to CloudWatch Logs;
- publish a custom metric such as `AuditDetectionLatencySeconds`.

### 6.3. How to prove it

Before submission:

1. Run at least three real drills.
2. Keep:
   - the event timestamp from CloudTrail;
   - the received email alert;
   - the Lambda log containing `ttd_seconds`.
3. Record a simple evidence table in the runbook:
   - event;
   - event time;
   - detected time;
   - `ttd_seconds`;
   - committed threshold;
   - pass or fail.

Important point:

- The mentor should not have to trust a spoken claim.
- The alert itself should show TTD.
- The logs and metric should be available for verification.

---

## 7. Noise Control and Mentor Verification

### 7.1. Noise control requirements

To stay credible and avoid alert fatigue, the detector should apply a small set of explicit noise-control rules:

- keep an allowlist of known automation principals, such as CI/CD roles and approved IRSA roles;
- treat human secret access differently from automation secret access;
- use time-bounded maintenance suppressions with at least:
  - `actor`
  - `resource`
  - `start`
  - `end`
  - `reason`
- make suppressions expire automatically instead of leaving them open-ended;
- page only on the highest-risk groups by default:
  - Group 1 - blinding audit
  - Group 2 - creating new access paths
  - Group 4 - broadening cluster or runtime access
- keep Group 3 and Group 5 at review or high severity unless the target or actor makes them critical;
- set Group 6 severity based on the target, with destructive actions against evidence, keys, or critical datastores treated as `critical`.

This is the minimum needed to satisfy the directive requirement that alerts remain trustworthy and are not muted as noise.

### 7.1.1. Minimum implementation

The recommended minimum implementation is intentionally small:

- keep one detector configuration file directly inside the Lambda package;
- store:
  - `allowed_principals`
  - `human_principals`
  - `secret_reader_principals`
  - `suppressions`
- make each suppression contain:
  - `actor`
  - `resource`
  - `start`
  - `end`
  - `reason`
- make the detector evaluate each event in this order:
  1. check whether the principal is an approved automation principal;
  2. check whether a valid, unexpired suppression exists;
  3. check whether the event is secret access by a human principal;
  4. map the event into a severity based on the event group and target.

The recommended default severity mapping is:

- Group 1, Group 2, Group 4 -> `critical`
- Group 3, Group 5 -> `high`
- Group 6 -> `high` by default, `critical` when the target is an evidence store, a KMS key, or a critical datastore

This is enough to answer the mentor's likely questions about CI/CD activity, approved automation, and planned maintenance without building a full alert-management product or adding extra configuration infrastructure.

### 7.2. Mentor self-verification expectations

The mentor must be able to perform one harmless but clearly dangerous action and verify the result without relying on verbal explanation.

The verification flow should therefore show:

- the action performed by the mentor;
- the resulting alert arriving within the committed threshold;
- the alert contents:
  - who
  - what
  - when
  - from where
  - time-to-detect
- the end-to-end alert path:
  - event source
  - processing step
  - recipient channel

Suitable self-verification actions include:

- `iam:CreateAccessKey`
- `eks:CreateAccessEntry`
- `cloudtrail:StopLogging` followed by `cloudtrail:StartLogging` on an approved test target

The important point is not the specific test action by itself, but that the mentor can independently see the alert, the routing path, and the measured detection time.

---

## 8. Cost Position

For the scoped design of management events + EventBridge + Lambda + SNS email:

- the cost should be very small compared with the `$300/week` ceiling;
- it is far more cost-effective than bringing in Security Hub, GuardDuty, or SIEM tooling just for this mandate.

Important guardrails:

- do not enable unnecessary data events;
- only watch secret-access events for genuinely sensitive secrets;
- do not keep CloudWatch retention infinite for Lambda and detector logs.

A short retention period such as 14 to 30 days is likely enough unless there is a separate audit retention requirement.
