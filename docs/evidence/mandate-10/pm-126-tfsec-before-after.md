# PM-126 tfsec before/after and residual report

## Scope and safety boundary

- Baseline: `main@855e1753d6e504445bb7ca8ee43883499f89b982`.
- Scanner: `aquasec/tfsec:v1.28.14@sha256:ac46d48a384ae2c0bbd0413cd2a18229e45e21a44d22c8be28b56de5b38d74c3`.
- Scope: the production root `infra/live/production` and every repo-owned local module reached from it; downloaded third-party modules are excluded from repository finding ownership.
- Gate threshold: `--minimum-severity HIGH`; a non-zero scanner exit blocks the PR.
- This change only updates Terraform desired state and CI controls. No `terraform plan` against production, `terraform apply`, AWS write, Kubernetes write, Argo CD sync, ECR push or deployment was run while producing this report.

Baseline command:

```bash
docker run --rm -v "$PWD:/src" \
  aquasec/tfsec:v1.28.14@sha256:ac46d48a384ae2c0bbd0413cd2a18229e45e21a44d22c8be28b56de5b38d74c3 \
  /src/infra/live/production --exclude-downloaded-modules \
  --minimum-severity HIGH --format json
```

## Before

The repo-owned baseline contained **10 unresolved findings: 8 HIGH and 2 CRITICAL**.

| Severity | Rule | Instances | Source | Baseline problem |
|---|---|---:|---|---|
| CRITICAL | AVD-AWS-0104 | 1 | `infra/modules/network/main.tf` | Interface-endpoint security group allowed unrestricted public egress. |
| CRITICAL | AVD-AWS-0104 | 1 | `infra/modules/access/main.tf` | Bastion security group allowed unrestricted public egress. |
| HIGH | AVD-AWS-0013 | 1 | `infra/modules/edge/main.tf` | CloudFront default-certificate TLS policy reported as legacy. |
| HIGH | AVD-AWS-0015 | 1 | `infra/modules/audit-detection/main.tf` | CloudTrail had no customer-managed KMS key. |
| HIGH | AVD-AWS-0131 | 1 | `infra/modules/access/main.tf` | Bastion root block device did not declare encryption. |
| HIGH | AVD-AWS-0057 | 2 | `infra/modules/audit-detection/main.tf` | The shared policy source uses the required CloudWatch Logs child-stream ARN suffix; two production module instances caused two scanner results. |
| HIGH | AVD-AWS-0132 | 1 | `infra/modules/audit-detection/main.tf` | CloudTrail S3 encryption used AES256 rather than a customer-managed KMS key. |
| HIGH | AVD-AWS-0095 | 2 | `infra/modules/audit-detection/main.tf` | Both regional SNS topics lacked encryption. |

The full dependency graph also reported one finding in a downloaded third-party EKS module. It is not counted as a repo-owned finding or silently baselined; dependency pin/remediation belongs to the immutable-dependency workstream. The PM-126 gate deliberately excludes generated/downloaded module source and scans all checked-in production Terraform.

## Remediation

| Rule | Resolution |
|---|---|
| AVD-AWS-0104 | Removed endpoint security-group egress. Restricted bastion egress to VPC HTTPS and the Amazon-provided VPC DNS resolver over TCP/UDP 53. |
| AVD-AWS-0015 / AVD-AWS-0132 / AVD-AWS-0095 | Added one rotating customer-managed audit KMS key and scoped key policy; use it for CloudTrail, the trail S3 bucket and regional SNS topics. |
| AVD-AWS-0131 | Declared encrypted bastion root storage. |
| AVD-AWS-0013 | Accepted only on the two exact CloudFront resources that intentionally use the `cloudfront.net` hostname/default certificate. |
| AVD-AWS-0057 | Classified as an exact-source false positive: CloudWatch Logs requires the log-group ARN suffix `:*` to address child streams; actions remain limited to stream creation and writes. |

The KMS and networking changes must go through the normal Terraform review and maintenance workflow before any future apply. In particular, the bastion root-volume change may require instance replacement; PM-126 does not authorize or execute that replacement.

## After

The same blocking scan exits `0` with **0 unresolved HIGH/CRITICAL findings**. Approved ignores are not presented as remediated findings: they remain visible in the governed residual table below and are validated on every PR.

| Result | Before | After |
|---|---:|---:|
| CRITICAL unresolved | 2 | 0 |
| HIGH unresolved | 8 | 0 |
| Exact approved exception records | 0 | 3 |

The gate stays live after PM-126, so later work can add records to the same ledger. Mandate 12 added one (last row below), bringing the ledger to 4; the PM-126 baseline columns above are left at their measured values.

## Residual finding / exception table

| Rule | Exact resource | Classification | Owner | Ticket | Review date | Reason |
|---|---|---|---|---|---|---|
| AVD-AWS-0013 | `aws_cloudfront_distribution.staging` | Operational necessity | `tuu-ngo` | PM-126 | 2026-08-22 | Default CloudFront certificate mode only supports the legacy minimum protocol value; HTTPS redirect is still enforced. |
| AVD-AWS-0013 | `aws_cloudfront_distribution.frontend` | Operational necessity | `tuu-ngo` | PM-126 | 2026-08-22 | Default CloudFront certificate mode only supports the legacy minimum protocol value; HTTPS redirect is still enforced. |
| AVD-AWS-0057 | `data.aws_iam_policy_document.audit_alert_router` | False positive | `tuu-ngo` | PM-126 | 2026-08-22 | The wildcard is the required child log-stream suffix and is paired only with `CreateLogStream`/`PutLogEvents`. |
| AVD-AWS-0057 | `data.aws_iam_policy_document.m12_audit_heartbeat` | Operational necessity | `tuu-ngo` | PM-126 | 2026-08-22 | Read-only audit-health role with no mutating action. `cloudwatch:DescribeAlarms` and `cloudtrail:DescribeTrails` have no resource-level permission support, and the log statement uses the required child log-stream suffix. Added by Mandate 12. |

Machine-readable authority: `docs/evidence/mandate-10/pm-126-tfsec-exceptions.json`.

The validator rejects missing fields, unsupported classifications, expired dates, duplicate rule/resource pairs, non-adjacent ignores and any tfsec ignore anywhere under `infra/` that is absent from this ledger. There is no baseline file, global skip or severity downgrade.
