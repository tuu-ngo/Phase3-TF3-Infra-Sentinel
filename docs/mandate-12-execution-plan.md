# Mandate #12 — Audit Anti-Defeat · Kế hoạch thực thi

> **Trình duyệt:** Tech Lead / IaC owner (CD01) · **Trạng thái:** `READY FOR REVIEW — NOT APPROVED FOR APPLY`
> **Account:** `197826770971` · **Region:** `ap-southeast-1` (+ `us-east-1` cho IAM global events)
> **PR này:** audit foundation. **IAM hardening là PR riêng**, không gộp.

> [!CAUTION]
> Merge PR này **không** đồng nghĩa được apply. Apply chỉ diễn ra qua
> `terraform-apply.yml` (`workflow_dispatch`), trong change window, sau khi đủ
> 5 gate ở §8. Không tạo canary, không chạy attack test trước approval.

---

## 1. Tóm tắt cho người duyệt

**Vấn đề.** Mandate 11 đã dựng CloudTrail + EventBridge + Lambda router + SNS và đang chạy. Nhưng nền đó còn bốn lỗ hổng khiến audit trail vẫn bị vô hiệu hoá được:

1. Router **bỏ qua** mọi event từ principal trong automation allowlist — kể cả `StopLogging`. `gitlab-ci-deployer` (admin, chưa MFA, 2 access key đang hoạt động) nằm trong allowlist đó.
2. Trail **không ghi S3 data events** → đọc/kéo object không để lại vết.
3. **Không có rule nào bảo vệ chính alert plane** — xoá rule, huỷ subscription, sửa code router đều im lặng.
4. Object Lock **GOVERNANCE 14 ngày** — bypass được, và quá ngắn so với yêu cầu điều tra.

**Cách xử lý.** Nâng cấp **in-place** nền M11. Không tạo trail thứ hai, không tạo bucket mới, không tạo router mới.

| Nhóm | Thay đổi trong PR này |
|---|---|
| Router | Nhóm critical `[1,2,3,4,7,8]` không còn bị allowlist/suppression làm im lặng; thêm ~45 action vào `GROUP_MAP` |
| Coverage | Basic selector → advanced selector: giữ Management Read/Write, thêm S3 Object data events theo scope owner duyệt |
| Retention | Object Lock `GOVERNANCE 14` → `COMPLIANCE 365` (object mới); lifecycle `30` → `400` ngày |
| Archive | Bucket policy thêm Deny mọi object mutation không phải từ CloudTrail |
| Alert plane | Thêm rule `g7` (regional: EventBridge/SNS/Lambda/CloudWatch/S3 controls) và `g8` (global: IAM boundary/policy/OIDC) |
| Heartbeat | Lambda 5 phút/lần kiểm ~30 invariant; 2 alarm; 1 SNS fallback cùng region |
| **CI boundary** | Permissions boundary chuyên biệt cho `gha-terraform-apply`/`plan`: cho phép IAM CRUD chung, deny các kill switch audit. Tạo sẵn nhưng **chưa attach** (`enable_ci_audit_boundary = false`) |
| CI workflow | `terraform-plan.yml` thêm `pull_request` trigger để reviewer xem được plan **trước** khi merge |

**Không đụng:** EKS workload, VPC/network, ALB, CloudFront, Cloudflare, ArgoCD/GitOps, datastore, **flagd**. Không có đường ảnh hưởng tới SLO checkout/browse/cart.

**Hai câu cần Tech Lead quyết** — chi tiết ở §15:
1. Ngưỡng chấp nhận số lượng alert CRITICAL sinh ra bởi `g7` mỗi lần `terraform apply`
2. Ai chịu trách nhiệm điều phối 10 lần xác nhận subscription SNS còn thiếu

> Câu hỏi thứ ba của bản trước — boundary cho `gha-terraform-apply` — **đã được chốt: phương án (b)**, boundary riêng cho CI. Thiết kế, giới hạn và quy trình attach ở §9.

---

## 2. Bối cảnh

### 2.1 Đề bài yêu cầu gì

Mandate #12 yêu cầu chứng minh audit trail không bị vô hiệu hoá bằng **ba cách**, và **mentor tự thử, không nghe khai**:

| Đòn | Kẻ tấn công làm gì | Mentor thử | PASS khi |
|---|---|---|---|
| **Làm mù** | Tắt/dừng đường ghi log trước khi ra tay | `StopLogging` / `DeleteTrail` / xoá cấu hình trail | Bị chặn **hoặc** kêu ngay, chỉ ra được vết "ai tắt, lúc mấy giờ" |
| **Làm hụt** | Hoạt động ở chỗ không được ghi (đọc secret, kéo bucket) | Một hành động **đọc dữ liệu** | Team chỉ ra được vết trong log. Không có vết = coverage gap chưa bịt |
| **Làm mỏng/sửa** | Log sơ sài không dựng lại được, hoặc bị thêm/xoá/sửa lén | Team chạy xác minh toàn vẹn trước mặt | `validate-logs` không thiếu digest, không `INVALID` |

Cộng thêm **retention đủ lâu** cho tấn công kéo dài nhiều ngày, và nêu rõ vì sao đủ.

**Ràng buộc:** ngân sách ~$300/tuần/TF · storefront vẫn public, cổng vận hành vẫn riêng tư (Directive #1) · **không đụng/vô hiệu hoá flagd**.

### 2.2 Hiện trạng Mandate 11 (đã apply)

Module `infra/modules/audit-detection/` được gọi **hai lần** trong `infra/live/production/audit-detection.tf`:

**`audit_detection_ap_southeast_1`** (`create_trail = true`):

| Resource | Trước PR này |
|---|---|
| `aws_cloudtrail.audit` | multi-region, global events, `enable_log_file_validation = true`, **basic `event_selector`** (Management All) — không có data events |
| `aws_s3_bucket.trail_logs` | `techx-corp-tf3-audit-trail-ap-southeast-1-197826770971`, versioning, SSE-S3, PAB |
| `aws_s3_bucket_object_lock_configuration` | **GOVERNANCE, 14 ngày** |
| `aws_s3_bucket_lifecycle_configuration` | expiration **30 ngày** |
| `aws_s3_bucket_policy` | Allow CloudTrail ACL/Write + Deny insecure transport. **Không có** Deny object mutation |
| `aws_lambda_function.audit_alert_router` | python3.12 + DLQ SQS |
| Rules | `g1-audit`, `g4-eks`, `g5-secrets`, `g6-destroy` |

**`audit_detection_us_east_1`** (`create_trail = false`): SNS riêng, rules `g2-new-access`, `g3-privilege`.

**Đường alert:** `CloudTrail → EventBridge rule → Lambda router → SNS → email`.

Module **không có** `aws_sns_topic_policy`. Đây là lý do rule mới phải đi qua router chứ không target thẳng SNS, và là lý do PR này phải thêm policy cho CloudWatch alarm publish.

### 2.3 Bốn lỗ hổng và bằng chứng

#### Lỗ hổng 1 — Router bỏ qua critical event từ principal allowlisted

`infra/modules/audit-detection/lambda/index.py` trước PR:

```python
group = GROUP_MAP.get(event_key)
if group is None:
    return {"ignored": True, "reason": "unmapped_event"}      # action không có trong map bị bỏ

actor = extract_actor(...)
if is_allowed_automation(actor):                               # áp cho MỌI group, kể cả group 1
    return {"ignored": True, "reason": "allowlisted_automation"}
```

`allowed_principals` gồm `external_secrets`, `gha-terraform-plan`, `gha-terraform-apply` và (từ tfvars) `gitlab-ci-deployer`.

**Hệ quả:** các principal này gọi `cloudtrail:StopLogging` → router trả `ignored` → **không có cảnh báo nào**. Group 1 chính là nhóm "làm mù" của đề bài.

Đây là lỗi triển khai chứ không phải chủ ý: comment ngay trong file (dòng 32-34) viết cho group 3 rằng *"Kể cả khi actor là CI/CD hoặc Terraform automation role, event vẫn phải alert"* — nhưng code chặn trước khi tới bất kỳ xử lý riêng nào.

**Tầng thứ hai:** `GROUP_MAP` không chứa bất kỳ action nào về `events:*`, `sns:*`, `lambda:*`, `s3:PutBucketPolicy`, `iam:*PermissionsBoundary`. Nên dù có tạo rule EventBridge cho chúng, router vẫn bỏ ở nhánh `unmapped_event`.

#### Lỗ hổng 2 — Không có S3 data events

`get-event-selectors` trả `DataResources: []`. Đọc object không sinh event → trượt thẳng đòn "làm hụt".

#### Lỗ hổng 3 — Không bảo vệ chính alert plane

Không rule nào bắt `events:DisableRule`, `sns:Unsubscribe`, `lambda:UpdateFunctionCode`, `s3:PutBucketPolicy`. Kẻ tấn công tắt alert trước, rồi mới tắt trail.

#### Lỗ hổng 4 — Object Lock quá yếu

`GOVERNANCE 14` bypass được bằng `s3:BypassGovernanceRetention`; 14 ngày không đủ điều tra tấn công kéo dài.

### 2.4 Kịch bản tấn công hiện tại

1. Lấy access key `gitlab-ci-deployer` → `StopLogging` → router bỏ qua vì allowlisted → **không alert**, trail dừng ghi
2. `delete-object --bypass-governance-retention` → xoá log
3. `events:DisableRule g1-audit` → không có trong `GROUP_MAP` → bỏ qua
4. `sns:Unsubscribe` từng email → không có trong `GROUP_MAP` → bỏ qua
5. `aws s3 cp s3://.../terraform.tfstate ./` → không có data events → **exfil vô hình**

Bốn trong năm bước không sinh một dòng cảnh báo nào.

---

## 3. Quyết định kiến trúc

### 3.1 Nâng cấp in-place M11, không tạo trail thứ hai

**Chọn:** sửa module M11 đang chạy. **Bỏ:** dựng `infra/live/audit/` với trail riêng.

- AWS miễn phí **một** multi-region management trail đầu tiên mỗi account. M11 đã dùng slot đó — trail thứ hai tính phí per-event
- Trùng lặp bucket + SNS + router cho cùng bộ event: tăng chi phí, không tăng giá trị
- Detection `g1-g6` đang chạy tốt; M12 chỉ cần bổ sung phần thiếu
- Blast radius review nhỏ: một module thay vì ba Terraform root mới

### 3.2 Nâng Object Lock in-place, không tạo bucket mới

`PutObjectLockConfiguration` sửa được default retention của bucket đã bật Object Lock. Không cần bucket mới, và quan trọng hơn — trail giữ nguyên destination nên **digest chain không bị đứt**.

**Giới hạn phải nói rõ trong evidence:** cấu hình mới chỉ áp cho **object ghi sau cutover**. Object cũ giữ GOVERNANCE 14 ngày. Claim đúng là *"retention 365 ngày tính từ UTC cutover"*, không hồi tố.

**Ràng buộc kỹ thuật:** lifecycle phải **dài hơn** Object Lock. Object bị Compliance-lock 365 ngày mà lifecycle đặt 30 ngày thì S3 để rule fail âm thầm. Module có `precondition` chặn cấu hình sai; giá trị chọn là 400 (365 + 35 ngày đệm xử lý/export).

### 3.3 Rule mới đi qua Lambda router, không target thẳng SNS

Module không có `aws_sns_topic_policy` cho `events.amazonaws.com`. Rule target thẳng SNS sẽ `FailedInvocations` 100%. Đi qua router còn giữ được format alert thống nhất, DLQ và metric latency đã có.

### 3.4 Nhóm critical bypass allowlist + suppression

Tái dùng `critical_group_numbers` đã có trong `detector_config`, mở rộng `[1,2,4]` → `[1,2,3,4,7,8]`, và bọc hai nhánh lọc:

```python
critical_groups = set(CONFIG.get("critical_group_numbers") or [])
if group not in critical_groups and is_allowed_automation(actor): ...
if group not in critical_groups and is_suppressed(actor, target): ...
```

Group 3 (leo thang quyền IAM) được đưa vào critical vì `AttachRolePolicy` / `UpdateAssumeRolePolicy` từ một CI role là đúng kịch bản phải bắt.

**Đánh đổi có chủ ý:** change đã duyệt cũng sẽ sinh alert. Xử lý bằng quy trình change-ID (§8 gate 5), **không** bằng cách thêm suppression.

### 3.5 Heartbeat — phát hiện "sự im lặng"

Alert dựa-trên-sự-kiện chỉ kêu khi có event. Nếu kẻ tấn công phá đồng thời trail và alert plane thì không còn event nào để kêu.

Heartbeat chạy 5 phút/lần, so trạng thái live với cấu hình đã duyệt: trail logging/multi-region/validation, tuổi log ≤ 20 phút, tuổi digest ≤ 90 phút, exact advanced selectors, Object Lock/lifecycle/encryption/PAB/bucket-policy-Deny, exact event pattern + target của từng rule, sức khoẻ + reserved concurrency của cả hai router, cấu hình đầy đủ của 2 alarm, subscription đã confirmed trên 3 topic, và EKS audit logging.

**Điểm quan trọng:** heartbeat publish qua **hai đường độc lập** (SNS primary + SNS global), và 2 alarm publish tới **primary + fallback cùng region**. Một đường hỏng không làm mất tín hiệu.

---

## 4. Thay đổi trong PR này

### 4.1 `infra/modules/audit-detection/m12-variables.tf` — MỚI

Ba biến, **default giữ đúng hành vi M11 hiện tại** để module không đổi khi caller chưa truyền giá trị:

| Biến | Default | Ý nghĩa |
|---|---|---|
| `trail_object_lock_mode` | `GOVERNANCE` | Chỉ instance production truyền `COMPLIANCE` |
| `trail_object_lock_days` | `14` | Production truyền `365` |
| `s3_data_event_arns` | `[]` | Rỗng = không tạo selector data events |
| `require_s3_data_event_coverage` | `false` | Production truyền `true` → plan FAIL nếu list rỗng |

`s3_data_event_arns` có validation: mỗi ARN phải khớp `^arn:aws:s3:::[^/]+/.*$` **và** kết thúc bằng `/`.

### 4.2 `infra/modules/audit-detection/main.tf` — 6 thay đổi

| # | Vị trí | Thay đổi | Vì sao |
|---|---|---|---|
| 1 | `locals.detector_config` | `critical_group_numbers` `[1,2,4]` → `[1,2,3,4,7,8]` | Nhóm critical không bị allowlist/suppression làm im lặng |
| 2 | `aws_s3_bucket.trail_logs` | Thêm `lifecycle { prevent_destroy = true }` | Bucket là nguồn bằng chứng; chặn plan vô tình replace/delete |
| 3 | `aws_s3_bucket_object_lock_configuration` | `mode`/`days` hard-code → biến | Cho phép production đặt COMPLIANCE 365 |
| 4 | `aws_s3_bucket_lifecycle_configuration` | Thêm `precondition`: `trail_s3_retention_days > trail_object_lock_days` | Chặn cấu hình khiến lifecycle fail âm thầm |
| 5 | `data.aws_iam_policy_document.trail_logs` | Thêm statement `DenyNonCloudTrailObjectMutation` | Chặn put/delete/đổi retention/bypass-governance ở tầng resource policy, độc lập IAM |
| 6 | `aws_cloudtrail.audit` | Bỏ `event_selector`; thêm 2 `advanced_event_selector`; `prevent_destroy` + **2 precondition**: chống đưa audit bucket vào selector, và chặn plan khi `s3_data_event_arns` rỗng lúc `require_s3_data_event_coverage = true` | Bật data events; tránh vòng lặp logging; biến gate coverage từ tài liệu thành lỗi plan |
| 7 | `outputs.tf` | Thêm `lambda_source_code_hash`, `lambda_handler`, `lambda_role_arn`, `lambda_detector_config` | Heartbeat cần baseline để phát hiện router bị thay code/config |
| 8 | `data.archive_file.audit_alert_router` | `source_dir` → **`source_file`** (đúng `lambda/index.py`) | `source_dir` nuốt cả `__pycache__` trên máy chạy Terraform → hash lệch → `CodeSha256` check vô dụng. `.gitignore` không giúp vì `archive_file` đọc filesystem chứ không đọc git. Router chỉ import stdlib + boto3 nên một file là đủ |

**Điểm cần chú ý khi review #6:** advanced selectors **thay thế hoàn toàn** basic selector. Selector `ManagementReadWrite` phải được khai báo lại — nếu thiếu là mất toàn bộ coverage của M11.

### 4.3 `infra/modules/audit-detection/lambda/index.py` — 2 thay đổi

**a. `GROUP_MAP` thêm ~45 action:**

| Group | Nhóm action |
|---|---|
| 7 (regional) | `events:` DisableRule/DeleteRule/PutRule/RemoveTargets/PutTargets · `sns:` AddPermission/RemovePermission/DeleteTopic/SetTopicAttributes/Subscribe/ConfirmSubscription/SetSubscriptionAttributes/Unsubscribe · `lambda:` DeleteFunction/UpdateFunctionCode/UpdateFunctionConfiguration/**PutFunctionConcurrency**/DeleteFunctionConcurrency · `monitoring:` DeleteAlarms/DisableAlarmActions/PutMetricAlarm · `s3:` PutBucketPolicy/DeleteBucketPolicy/PutBucketVersioning/PutObjectLockConfiguration/PutBucketLifecycleConfiguration/DeleteBucketLifecycle/PutBucketEncryption/DeleteBucketEncryption/PutPublicAccessBlock/DeletePublicAccessBlock |
| 8 (global) | `iam:` Put/Delete User+Role PermissionsBoundary · DeletePolicy/DeletePolicyVersion/DeleteUserPolicy/DeleteRolePolicy · DetachUserPolicy/DetachRolePolicy · 5 action OIDC provider |

`lambda:PutFunctionConcurrency` đáng chú ý: đặt reserved concurrency = 0 làm router ngừng xử lý **mà không xoá gì**. Heartbeat cũng kiểm tra điều này.

**b. Bọc hai nhánh lọc bằng `critical_groups`** — xem §3.4.

### 4.4 `infra/modules/audit-detection/lambda-heartbeat/heartbeat.py` — MỚI

~500 dòng, không phụ thuộc gì ngoài `boto3`. Hai điểm thiết kế đáng chú ý:

**Xác minh tính toàn vẹn của router.** `State = Active` là chưa đủ: CI boundary **buộc phải** cho phép `lambda:UpdateFunctionCode` (Terraform cần nó để deploy router), nên router có thể bị thay bằng no-op mà vẫn Active — alert bị nuốt hoàn toàn trong im lặng. Heartbeat so bốn field với giá trị Terraform đã duyệt (`ROUTER_EXPECTED_JSON`):

| Field | Bắt được gì |
|---|---|
| `CodeSha256` | Thay code router |
| `Handler` | Trỏ sang entrypoint khác |
| `Role` | Đổi sang role không có quyền publish SNS |
| `DETECTOR_CONFIG_JSON` | **Sửa `critical_group_numbers`** — cách gỡ bypass allowlist mà không cần đụng code |

Đây là lớp bù cho việc không thể chặn `UpdateFunctionCode` ở tầng IAM.

Để `CodeSha256` có ý nghĩa, artifact phải tất định: `data.archive_file.audit_alert_router` dùng **`source_file`** (đúng một `index.py`) chứ không phải `source_dir`. `source_dir` sẽ nuốt cả `__pycache__` có sẵn trên máy chạy Terraform và làm hash lệch — `.gitignore` không giúp được vì `archive_file` đọc filesystem chứ không đọc git.

**Xác nhận permissions boundary còn attach.** `BOUNDED_PRINCIPALS_JSON` map principal ARN → boundary ARN; heartbeat gọi `iam:GetRole`/`GetUser` và so `PermissionsBoundaryArn`. Với `gitlab-ci-deployer` việc attach là thủ công nên **không có gì cưỡng chế nó tồn tại** — đây là thứ duy nhất phát hiện được nếu ai đó gỡ. Map rỗng thì bỏ qua, để không FAIL giả trước Phase 4b.

**Semantic invariant cho event pattern.** Nếu chỉ so trạng thái AWS với giá trị Terraform sinh ra thì check luôn PASS kể cả khi Terraform khai báo sai. Heartbeat suy `source` từ chính `eventSource`:

```python
semantic_sources = {f"aws.{es.split('.', 1)[0]}" for es in actual_detail.get("eventSource", [])}
if set(actual_pattern.get("source", [])) != semantic_sources:
    failures.append("EventBridge source/eventSource semantic mismatch")
```

Điều này bắt được cặp sai như `aws.cloudwatch` + `monitoring.amazonaws.com` — cặp đúng phải là `aws.monitoring`.

**Exact-match bucket policy Deny.** So khớp cả shape của `Principal`, `Condition`, và từ chối `NotAction`/`NotResource`/`NotPrincipal`. Statement bị làm yếu nhưng vẫn tồn tại sẽ không lọt.

Chế độ `forceAlertTest`: gọi Lambda với `{"forceAlertTest": true}` để kiểm tra đường alert mà không phải phá topic thật. Output có `status` tiền tố `TEST-` để không nhầm với health check.

### 4.5 `infra/live/production/m12-variables.tf` — MỚI

| Biến | Default | Ghi chú |
|---|---|---|
| `audit_detection_s3_data_event_arns` | `[]` | Validation format. Giá trị vòng 1 đã điền trong tfvars — xem §8.1 |
| `audit_detection_trail_object_lock_mode` | `COMPLIANCE` | |
| `audit_detection_trail_object_lock_days` | `365` | Validation `>= 365` |
| `audit_detection_bounded_principals` | `{}` | Map principal ARN → boundary ARN cho heartbeat canh. Để rỗng tới Phase 4b, nếu không FAIL giả |

### 4.6 `infra/live/production/audit-heartbeat.tf` — MỚI

| Resource | Ghi chú |
|---|---|
| `aws_sns_topic.m12_heartbeat_fallback` + policy + 6 subscription | Alarm không phụ thuộc duy nhất topic M11. `prevent_destroy` |
| `aws_sns_topic_policy.m12_primary_alarm_topic` | **Topic M11 primary chưa có policy cho `cloudwatch.amazonaws.com`** — thiếu nó alarm action fail âm thầm |
| `aws_lambda_function.m12_audit_heartbeat` + role + policy + log group | Quyền chỉ đọc; publish giới hạn 2 topic M11 |
| `aws_cloudwatch_event_rule` + target + permission | `rate(5 minutes)` |
| `aws_cloudwatch_metric_alarm...heartbeat_missing` | Invocations < 1 trong 900s, `treat_missing_data = breaching` |
| `aws_cloudwatch_metric_alarm...heartbeat_errors` | Errors ≥ 1 trong 300s |

Cả hai alarm publish tới **primary + fallback**. Topic global không dùng làm alarm action vì CloudWatch alarm chỉ publish được tới SNS cùng region — heartbeat Lambda dùng nó trực tiếp.

### 4.7 `infra/live/production/audit-detection.tf` — 3 thay đổi

1. Thêm `g7-audit-controls` vào `local.audit_detection_regional_event_rules`
2. Thêm `g8-iam-controls` vào `local.audit_detection_global_event_rules`
3. Truyền 3 input mới cho module `ap-southeast-1` (module `us-east-1` không nhận vì `create_trail = false`)

**Chú ý khi review g7:** `sources` dùng `aws.monitoring`, **không** phải `aws.cloudwatch`. EventBridge dùng namespace suy từ `eventSource` (`monitoring.amazonaws.com` → `aws.monitoring`). Dùng sai thì rule không khớp và im lặng — và heartbeat có invariant bắt đúng lỗi này.

### 4.8 `infra/live/production/production.auto.tfvars` — 3 thay đổi

- `audit_detection_trail_s3_retention_days = 400` (từ default 30)
- `audit_detection_s3_data_event_arns` = nguyên bucket Terraform state (§8.1), kèm giải thích vì sao không dùng prefix hẹp và vì sao ba bucket kia hoãn
- Thêm comment cảnh báo về `gitlab-ci-deployer` trong allowlist (xử lý ở PR IAM)

### 4.9 `.github/workflows/terraform-plan.yml` — 2 thay đổi

Thêm trigger `pull_request` và nới điều kiện job, kèm guard chặn PR từ fork:
```yaml
if: >-
  (github.event_name == 'pull_request'
   && github.event.pull_request.head.repo.full_name == github.repository)
  || github.ref == 'refs/heads/main'
```

GitHub vốn không cấp `id-token: write` cho workflow chạy từ fork PR, nên fork không lấy được OIDC token để assume plan role. Guard này chặn tường minh để không phụ thuộc vào hành vi ngầm của nền tảng.

Trước đó plan **chỉ chạy sau khi merge vào `main`** — reviewer không xem được plan trước khi duyệt. Với change đụng CloudTrail, bucket policy và IAM, review sau merge là quá muộn.

Dùng `pull_request` (không phải `pull_request_target`) để PR từ fork không lấy được credential OIDC. Role plan chỉ có `ReadOnlyAccess` + quyền đọc state.

### 4.10 `.gitignore`

Bỏ qua zip do `archive_file` sinh (`m12-audit-heartbeat.zip`, `audit-alert-router.zip`) và bytecode Python (`__pycache__/`, `*.py[cod]`).

Lưu ý: `.gitignore` **không** bảo vệ được artifact — `archive_file` đọc filesystem chứ không đọc git. Việc đó do `source_file` xử lý (§4.2 #8). Ở đây chỉ là giữ `git status` sạch.

### 4.11 `infra/bootstrap/github-oidc/ci-audit-boundary.tf` — MỚI

Permissions boundary cho hai GitHub Actions Terraform role, và (attach thủ công) cho `gitlab-ci-deployer`. Chi tiết thiết kế ở **§9**.

Đặt ở root này vì đó là nơi **sở hữu** hai role (state riêng `bootstrap/github-oidc/terraform.tfstate`). Attach từ `infra/live/production` hoặc bằng tay sẽ tạo drift mà lần apply bootstrap sau sẽ revert.

### 4.12 `infra/bootstrap/github-oidc/{main,variables,README}.tf|md` — SỬA

- Hai role nhận `permissions_boundary = var.enable_ci_audit_boundary ? ... : null`
- Thêm biến `ci_audit_boundary_name`, `enable_ci_audit_boundary` (**default `false`**) và `additional_bounded_principal_arns` (default chứa `gitlab-ci-deployer`)
- README ghi quy trình attach + rollback

> `permissions_boundary` trên `aws_iam_role` là **update in-place** (`PutRolePermissionsBoundary`), không recreate role. Không có gián đoạn OIDC trust.

### 4.13 KHÔNG có trong PR này

| Hạng mục | Thuộc về |
|---|---|
| **Attach** CI boundary (`enable_ci_audit_boundary = true`) | Bước riêng sau simulation — §9.4 |
| **Attach** boundary cho `gitlab-ci-deployer` + điền `audit_detection_bounded_principals` | Phase 4b — §9.5 |
| Điều kiện `iam:PermissionsBoundary` trên `CreateRole`/`CreateUser` | Vòng hardening sau — cần truyền boundary xuống mọi module tạo service role (§9.3) |
| Role `audit-admin`, `break-glass`, `iam-change` | PR IAM hardening |
| Operator permissions boundary cho human user | PR IAM hardening |
| Gỡ `gitlab-ci-deployer` khỏi allowlist + rotate key + bật MFA | PR IAM hardening (cần owner GitLab và team AI) |
| S3 data events cho AIOps playbook / model / ALB log | Vòng 2, sau khi AIO02 và SOSFlow ký (§8.1) |
| Canary object/secret | Phase test, tạo trong change window |
| Storage tiering Glacier IR | Change riêng sau khi có số liệu dung lượng |

---

## 5. Ba khác biệt so với staging `Task_mandate_12/code_audit`

Ghi rõ để reviewer đối chiếu được với tài liệu gốc:

| # | Staging v2.2 | Trong PR này | Lý do |
|---|---|---|---|
| 1 | `heartbeat.py` đặt ở `modules/audit-detection/lambda/` | Đặt ở `modules/audit-detection/lambda-heartbeat/` | Ban đầu vì `archive_file` dùng `source_dir` nên mọi file trong `lambda/` lọt vào zip router. Lý do đó **nay không còn** — PR này đã đổi sang `source_file`. Giữ thư mục riêng vì vẫn đúng về mặt tách bạch: hai Lambda khác vòng đời, khác quyền, khác nhịp thay đổi |
| 2 | `forceAlertTest` trả `status: "PASS"` | Trả `"TEST-PASS"` / `"TEST-FAIL"` | Nhánh test **return sớm, không chạy health check nào**. `status: PASS` dễ bị chụp màn hình và trình bày nhầm thành bằng chứng heartbeat healthy |
| 3 | Không đề cập CI trigger | Thêm `pull_request` vào `terraform-plan.yml` | Xem §4.9 |

Điểm 1 và 2 là sửa lỗi. Điểm 3 là bổ sung để chính PR này review được.

---

## 6. Ảnh hưởng workload và SLO

### 6.1 Không có đường ảnh hưởng tới SLO sản phẩm

Toàn bộ thay đổi nằm ở tầng audit-plane. Không sửa: EKS workload/Helm, VPC/network/ALB, CloudFront, Cloudflare Access, ArgoCD/GitOps, RDS/ElastiCache/MSK, `values-flagd-sync.yaml`, cấu hình Envoy `frontend-proxy` (kể cả filter `envoy.filters.http.fault`).

SLO checkout / browse / cart không có đường tác động kỹ thuật.

### 6.2 Năm rủi ro thật

| # | Rủi ro | Cơ chế | Phát hiện | Giảm thiểu |
|---|---|---|---|---|
| 1 | **Router hỏng sau khi sửa `index.py`** | Lỗi logic làm **toàn bộ g1-g8 ngừng cảnh báo**, không riêng M12 | DLQ SQS; heartbeat kiểm tra router `State` + concurrency | **Unit test bắt buộc §7** trước khi tạo PR; rollback bằng revert PR |
| 2 | **Bucket policy Deny chặn nhầm CloudTrail** | Nếu điều kiện `aws:PrincipalServiceName` không như kỳ vọng → mất log | `LatestDeliveryError`; heartbeat bắt trong ≤ 20 phút | Deny chỉ ở object-level (`/*`), không chạm bucket-level config. Verify ngay sau apply |
| 3 | **Advanced selector thay basic** | Khoảnh khắc `UpdateTrail`; ARN sai định dạng → data events không ghi | T03 canary `GetObject`; heartbeat so exact ARN set | Validation bắt buộc kết thúc `/`; verify bằng `get-event-selectors` |
| 4 | **Alert volume tăng** | `g7` khớp theo `eventName`, **không lọc resource** → mọi `PutRule`/`PutBucketPolicy`/`UpdateFunctionCode`/`PutMetricAlarm` trong **toàn account** đều CRITICAL | Người trực | Xem §6.3 — cần Tech Lead chốt ngưỡng |
| 5 | **Lifecycle 30 → 400 ngày** | Áp cho **cả object hiện có chưa bị xoá** → dung lượng tăng | Cost Explorer | Inventory dung lượng trước apply; cost approval |
| 6 | **CI boundary attach sai** (Phase 4b) | Deny quá tay → `terraform plan/apply` fail → **không deploy được gì nữa**, kể cả rollback qua CI | CI job đỏ ngay lần chạy đầu | `enable_ci_audit_boundary` default `false` · simulation 2 chiều bắt buộc (§9.4) · rollback bằng flag ở root bootstrap, do người MFA thực hiện |

Rủi ro #6 không chạm SLO sản phẩm — workload đang chạy không bị ảnh hưởng, chỉ mất khả năng deploy thay đổi mới cho tới khi gỡ boundary.

### 6.3 Định lượng rủi ro #4 trước khi apply

`g7` không có bộ lọc resource. Cần đếm trước để biết mức nhiễu thật:

```powershell
$env:AWS_PROFILE = "techx-new"
aws lambda list-functions      --region ap-southeast-1 --query 'length(Functions)'
aws events list-rules          --region ap-southeast-1 --query 'length(Rules)'
aws cloudwatch describe-alarms --region ap-southeast-1 --query 'length(MetricAlarms)'
aws sns list-topics            --region ap-southeast-1 --query 'length(Topics)'
aws s3api list-buckets --query 'length(Buckets)'
```

Ghi kết quả vào change record. Nếu một `terraform apply` bình thường sinh > 20 email CRITICAL cho 6 người nhận, cần chốt **trước** một trong ba hướng:

- chấp nhận + cam kết quy trình đối chiếu change ID,
- thêm điều kiện `requestParameters` vào pattern `g7` để giới hạn về đúng resource audit,
- tách `g7` thành `g7-audit-resources` (critical) và `g7-other` (severity thấp hơn).

Đây là quyết định phải chốt trước apply. Alert bị mute chính là cửa sổ mù mà mandate muốn chặn.

### 6.4 Chi phí

| Khoản | Ước tính |
|---|---|
| Management events | $0.00 — dùng lại slot trail miễn phí của M11 |
| S3 data events (1 prefix) | ~$0.01/tuần |
| Heartbeat Lambda (8.640 invoke/tháng) | $0.00 — trong free tier |
| 2 CloudWatch alarm | ~$0.20/tháng |
| SNS (3 topic × 6 email) | $0.00 — 1.000 email đầu miễn phí/tháng |
| Storage tăng do lifecycle 400 ngày | **Cần inventory §6.2 #5** |
| **Tổng thường xuyên** | **< $0.50/tuần** trước phần storage |

Ngân sách $300/tuần/TF → dưới 0,2%.

---

## 7. Kiểm thử bắt buộc trước khi tạo PR

Router là điểm hỏng chung của **cả `g1-g6` (M11) lẫn `g7-g8` (M12)**. Syntax check không đủ: nếu sửa `critical_groups` sai (nhầm tên biến, sai thứ tự toán tử) thì Python vẫn compile nhưng bypass không chạy — và `StopLogging` từ principal allowlisted lại bị bỏ qua, đúng thứ mandate muốn chứng minh đã bịt.

> [!IMPORTANT]
> `PYTHONDONTWRITEBYTECODE=1` là vệ sinh, không còn là bắt buộc: `archive_file` nay dùng `source_file` nên `__pycache__` **không** lọt được vào artifact router. Vẫn nên đặt để thư mục nguồn sạch và `git status` không nhiễu.

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:ALERT_TOPIC_ARN = "arn:aws:sns:ap-southeast-1:197826770971:unit-test"
$env:DETECTOR_CONFIG_JSON = @'
{"allowed_principals":["arn:aws:iam::197826770971:user/gitlab-ci-deployer"],
 "critical_group_numbers":[1,2,3,4,7,8],
 "suppressions":[{"actor":"*","resource":"*","start":"2000-01-01T00:00:00Z","end":"2099-01-01T00:00:00Z","reason":"unit-test"}]}
'@

python - <<'PY'
import os, sys
sys.path.insert(0, os.path.join("infra", "modules", "audit-detection", "lambda"))
import index

index.SNS = type("N", (), {"publish": staticmethod(lambda **k: None)})()
index.CLOUDWATCH = type("C", (), {"put_metric_data": staticmethod(lambda **k: None)})()

def ev(source, name, actor):
    return {"detail": {"eventSource": source, "eventName": name,
            "userIdentity": {"type": "IAMUser", "arn": actor},
            "eventTime": "2026-07-21T10:00:00Z", "requestParameters": {"name": "x"}}}

allow = "arn:aws:iam::197826770971:user/gitlab-ci-deployer"
cases = [
    ("cloudtrail.amazonaws.com", "StopLogging",                   allow, 1),
    ("iam.amazonaws.com",        "AttachRolePolicy",              allow, 3),
    ("events.amazonaws.com",     "DisableRule",                   allow, 7),
    ("lambda.amazonaws.com",     "PutFunctionConcurrency",        allow, 7),
    ("monitoring.amazonaws.com", "DeleteAlarms",                  allow, 7),
    ("iam.amazonaws.com",        "DeleteRolePermissionsBoundary", allow, 8),
]
bad = 0
for src, name, actor, want in cases:
    r = index.handler(ev(src, name, actor), None)
    ok = r.get("sent") is True and r.get("group") == want
    print(("PASS " if ok else "FAIL "), name, "->", r)
    bad += 0 if ok else 1
sys.exit(bad)
PY
```

Cả 6 case phải PASS: mọi nhóm critical vượt qua **cả** `allowed_principals` **lẫn** `suppressions` (config test cố tình đặt một suppression bao trùm mọi thứ).

Ngoài ra:
```powershell
terraform fmt -check -recursive infra/
python -c "from pathlib import Path; [compile(p.read_text(encoding='utf-8'), str(p), 'exec') for p in [Path('infra/modules/audit-detection/lambda/index.py'), Path('infra/modules/audit-detection/lambda-heartbeat/heartbeat.py')]]; print('syntax OK')"
```

---

## 8. Năm gate trước apply

| # | Gate | Cách đóng | Trạng thái |
|---|---|---|---|
| 1 | **Exact S3 coverage được ký** | Đã chốt vòng 1: nguyên bucket Terraform state (§8.1). Ba bucket của đội khác hoãn sang vòng 2.<br>**Gate này được Terraform cưỡng chế:** production truyền `require_s3_data_event_coverage = true`, nên `terraform plan` **FAIL** khi danh sách rỗng | ✅ vòng 1 |
| 2 | **SNS không còn pending** | Live: primary 3/6, global 5/6 confirmed. PR này thêm topic fallback → **6 subscription mới**, tổng 18 cần Confirmed. Heartbeat FAIL cho tới khi đủ | ❌ |
| 3 | **Deployment identity** | Caller đúng account, không root, có MFA hoặc là approved short-lived role | ❌ |
| 4 | **CD01 xác nhận state ownership + change window** | AWS không cho biết resource thuộc Terraform state nào. CD01 xác nhận M11 thuộc `infra/live/production` và cấp change window | ❌ |
| 5 | **Change ID** | Ticket ghi Git SHA, saved-plan hash, principal, UTC window, **danh sách g7/g8 action dự kiến**, và người trực cam kết đối chiếu thay vì mute | ❌ |

Bổ sung từ §6.3 và §7: ngưỡng alert volume được chấp nhận, và unit test router PASS.

Còn một dòng ❌ = **NO-GO**.

### 8.1 S3 data-event scope — quyết định vòng 1

```hcl
audit_detection_s3_data_event_arns = [
  "arn:aws:s3:::techx-tf3-197826770971-tfstate/",
]
```

**Vì sao nguyên bucket, không phải `eks-baseline/`.** Bucket chứa hai state key:

| Key | Nội dung |
|---|---|
| `eks-baseline/terraform.tfstate` | EKS, network, edge, audit-detection |
| `bootstrap/github-oidc/terraform.tfstate` | CI OIDC roles + **chính policy `ci-audit-boundary`** |

Với Mandate 12, file thứ hai mới là thứ nhạy cảm nhất: đọc được nó là biết boundary audit deny những gì và sót chỗ nào. Prefix hẹp `eks-baseline/` bỏ lọt đúng thứ cần bảo vệ nhất.

Volume thấp — state chỉ được đọc khi Terraform chạy — nên không cần lọc `readOnly` và chi phí data events không đáng kể.

**Vì sao chỉ một bucket.** `m12-coverage-v2.1.md` yêu cầu mỗi hàng phải có **data owner ký**. Grep toàn repo cho ba bucket còn lại không ra một tham chiếu nào — chúng không do repo này quản, và tên bucket không phải bằng chứng sở hữu:

| Bucket hoãn | Owner cần ký | Lý do hoãn |
|---|---|---|
| `techx-aiops-playbooks-f6230446` | AIO02 | Playbook vận hành — cần AIO02 xác nhận prefix nhạy cảm thực tế |
| `tf3-aiops-models-197826770971` | AIO02 | Model artifact — cần kiểm tra volume đọc của inference workload trước |
| `sosflow-alb-logs-197826770971` | Dự án SOSFlow | Khác dự án. Bật data events nghĩa là TF3 trả tiền cho traffic của họ và quyết định thay họ về dữ liệu của họ |

Ba bucket này giữ trạng thái `PENDING OWNER` trong coverage matrix. Vòng 2 xử lý sau khi có chữ ký; riêng ALB logs cần thêm khả năng lọc `readOnly` (xem §6.3) vì ALB ghi liên tục sẽ lấp luồng data event.

**Giới hạn phải ghi vào verdict:** claim coverage của Mandate 12 vòng 1 chỉ áp cho Terraform state. Đọc trộm playbook, model hay ALB log **vẫn chưa có vết**. Đây là exception có owner và có kế hoạch, không phải "ngoại lệ im lặng" mà coverage matrix cấm.

### 8.2 Canary cho đòn 2 — đặt ở đâu

Canary phải nằm **trong** selector đã duyệt, nên lần này nằm trong bucket state. Quy tắc:

- Key dùng prefix riêng: `m12-canary/m12-canary-<timestamp>.txt`
- **Tuyệt đối không** đụng bất kỳ đường dẫn `*/terraform.tfstate` nào
- Xoá sau khi evidence đã hash

Việc này **không** mâu thuẫn với quy tắc "không dùng Terraform state làm fixture" trong `m12-tests-v2.2.md`: quy tắc đó cấm **đọc file state thật** để chứng minh coverage. Ghi một object vô hại vào prefix riêng của cùng bucket là chuyện khác — Terraform không quan tâm object lạ, và bucket đã bật versioning.

> Năm gate trên áp cho **apply foundation** (Phase 2). CI boundary có gate riêng ở **§9.4** và chỉ chạy ở Phase 4b, sau khi foundation đã healthy — nếu boundary sai thì foundation vẫn còn nguyên và alert vẫn hoạt động.

---

## 9. CI audit boundary cho `gha-terraform-apply`

### 9.1 Bài toán

`gha-terraform-apply` có `AdministratorAccess` và là identity dùng để apply `infra/live/production` — tức là **chính nó deploy audit foundation**. Hai hướng cực đoan đều sai:

- **Giữ nguyên admin:** một `terraform apply` duy nhất có thể tắt trail, xoá rule, giết router và huỷ subscription cùng lúc. Khi alert plane cũng bị phá thì không còn tín hiệu nào để kêu.
- **Boundary strict** (deny toàn bộ `iam:Create*`/`Attach*`/`Put*`): CI chết cho mọi thay đổi IAM, kể cả chính module audit-detection.

### 9.2 Phương án đã chốt — boundary riêng cho CI

Cho phép IAM CRUD chung và mọi thao tác Terraform cần để quản audit foundation; deny đúng những action mà **Terraform không bao giờ cần** trên resource audit — các kill switch tức thời.

> [!IMPORTANT]
> Mọi statement Deny đều là **cặp (action + resource)**, scope vào đúng ARN pattern của resource audit. **Không statement nào dùng `Resource: "*"`.** Xoá một Lambda khác, một alarm khác, một EventBridge rule khác đều **không bị ảnh hưởng** — chúng rơi xuống Allow ceiling.

| Service | DENY — nhưng **chỉ trên** resource pattern này | Vẫn ALLOW trên chính resource audit (Terraform cần) |
|---|---|---|
| `cloudtrail` | **StopLogging**, DeleteTrail<br>`trail/techx-corp-tf3-audit-detection-*` | CreateTrail, UpdateTrail, PutEventSelectors, StartLogging |
| `s3` | DeleteBucket, DeleteBucketPolicy, DeleteBucketLifecycle<br>`techx-corp-tf3-audit-trail-*`<br>**BypassGovernanceRetention** + toàn bộ object mutation<br>`techx-corp-tf3-audit-trail-*/*` | CreateBucket, PutBucketPolicy, PutObjectLockConfiguration, PutBucketLifecycleConfiguration, PutBucketVersioning |
| `events` | **DisableRule**, DeleteRule, RemoveTargets<br>`rule/techx-corp-tf3-audit-detection-*`<br>`rule/techx-corp-tf3-m12-audit-heartbeat-*` | PutRule, PutTargets, DescribeRule |
| `sns` | DeleteTopic, RemovePermission<br>`techx-corp-tf3-audit-detection-*`<br>`techx-corp-tf3-m12-audit-heartbeat-fallback` | CreateTopic, Subscribe, SetTopicAttributes |
| `sns` (ngoại lệ) | **Unsubscribe**, SetSubscriptionAttributes<br>**`Resource = "*"`** — xem ghi chú dưới | Subscribe (thêm recipient) vẫn chạy |
| `lambda` | DeleteFunction, **PutFunctionConcurrency**, DeleteFunctionConcurrency, RemovePermission<br>`function:techx-corp-tf3-audit-detection-*-router`<br>`function:techx-corp-tf3-m12-audit-heartbeat` | CreateFunction, UpdateFunctionCode, UpdateFunctionConfiguration, AddPermission |
| `cloudwatch` | DeleteAlarms, DisableAlarmActions<br>`alarm:techx-corp-tf3-m12-audit-heartbeat-*` | PutMetricAlarm, DescribeAlarms |
| `iam` (boundary) | Delete Role/User PermissionsBoundary — **`Resource = "*"`**<br>Put Role/User PermissionsBoundary khi `iam:PermissionsBoundary` **≠** boundary này<br>Create/Delete/SetDefault PolicyVersion, DeletePolicy **trên chính boundary này** | CreateRole, AttachRolePolicy, PutRolePolicy, CreatePolicy… (CRUD chung); gắn **đúng** boundary này lên principal bất kỳ |
| `sts` + `iam` (credential) | AssumeRole, GetFederationToken, CreateAccessKey, UpdateAccessKey, Create/UpdateLoginProfile, Create/ResetServiceSpecificCredential — **`Resource = "*"`** | AssumeRoleWithWebIdentity/WithSAML giữ nguyên để không phá đường OIDC của chính CI |

**Vì sao ba nhóm cuối phải là `Resource = "*"`.** Đường vượt rào kinh điển của permissions boundary là: tạo principal mới → không gắn boundary (hoặc gắn cái yếu, hoặc gắn rồi gỡ) → lấy credential cho nó → hành động không bị giới hạn. Deny theo scope hẹp không chặn được vì principal mới chưa tồn tại lúc viết policy. Ba nhóm này cắt cả ba mắt xích:

- **Gỡ boundary:** deny toàn cục. CI không có nhu cầu hợp lệ nào phải gỡ boundary; rollback đi qua root bootstrap do người có MFA apply.
- **Gắn boundary yếu:** cho phép `Put*PermissionsBoundary` nhưng điều kiện `iam:PermissionsBoundary` phải đúng ARN boundary này.
- **Lấy credential:** deny `sts:AssumeRole` (đã verify workflow dùng OIDC trực tiếp, không chain; provider Terraform không có block `assume_role`) và `iam:CreateAccessKey` (đã verify Terraform không quản `aws_iam_access_key` nào).

### Không bị ảnh hưởng — đã đối chiếu với repo

| Resource | Tên | Vì sao không khớp pattern |
|---|---|---|
| Karpenter interruption rules | `techx-corp-tf3-karpenter-*` | Prefix `-karpenter-`, không phải `-audit-detection-` hay `-m12-audit-heartbeat-` |
| Mọi alarm SLO/vận hành | tuỳ tên | Chỉ `alarm:techx-corp-tf3-m12-audit-heartbeat-*` bị deny |
| Terraform state bucket | `techx-tf3-197826770971-tfstate` | Prefix khác `techx-corp-tf3-audit-trail-` |
| Bucket sản phẩm | `techx-products-catalog-2026`, … | idem |
| Mọi Lambda khác | tuỳ tên | Chỉ 2 router + 1 heartbeat bị deny |

ARN dùng prefix pattern thay vì lấy từ output production root vì hai root dùng state khác nhau. Pattern cũng tự bảo vệ resource mới cùng tiền tố khi audit foundation mở rộng.

### Ngoại lệ `sns:Unsubscribe` — vì sao phải `Resource = "*"`

SNS **không có resource type cho subscription**. `sns:Unsubscribe` và `sns:SetSubscriptionAttributes` chỉ authorize được với `Resource = "*"`; Deny scope theo topic ARN sẽ **không bao giờ match**, tức là vô hiệu.

Vì thế hai action này nằm trong statement riêng `DenySubscriptionTeardownAccountWide` với `Resource = "*"`.

**Thiệt hại phụ: không có.** Toàn repo chỉ có hai `aws_sns_topic_subscription` (`audit-heartbeat.tf:185`, `modules/audit-detection/main.tf:321`) và cả hai đều thuộc audit plane. Hệ quả thực tế: CI không gỡ được recipient alert của bất kỳ topic nào — gỡ recipient trở thành thao tác human-approved, đúng ý đồ. Thêm recipient (`sns:Subscribe`) vẫn chạy bình thường.

Nếu sau này có subscription không thuộc audit cần Terraform quản việc gỡ, phải mở lại quyết định này bằng change riêng.

### 9.3 Giới hạn phải nói rõ

Boundary này **không** làm CI hoàn toàn không thể làm yếu audit. `PutEventSelectors`, `UpdateTrail` và `PutBucketPolicy` vẫn được phép vì Terraform cần chúng — một PR độc hại vẫn có thể thu hẹp selector hoặc gỡ Deny khỏi bucket policy.

Ba lớp còn lại xử lý phần đó:

| Lớp | Cơ chế |
|---|---|
| Review | PR bắt buộc + branch protection trên `main`; CI plan hiển thị diff trước merge |
| Alert | Group 1 (`UpdateTrail`, `PutEventSelectors`) và `g7` (`PutBucketPolicy`) đã **bypass automation allowlist** → kêu cả khi actor là CI role |
| Detect | Heartbeat so exact selector set và exact bucket-policy Deny mỗi 5 phút |

Boundary loại bỏ các đường tắt tức thời; ba lớp kia phủ các đường "hình dạng Terraform". Đây là mức phòng thủ đạt được trong single-account mà không phá CI.

**Một đường vượt rào chưa đóng hết.** CI vẫn được `iam:CreateRole` + `iam:UpdateAssumeRolePolicy` + `iam:AttachRolePolicy` vì Terraform cần chúng để quản service role của mọi module. Về lý thuyết một PR độc hại có thể tạo role mới, trỏ trust sang account ngoài, gắn `AdministratorAccess`, rồi assume **từ bên ngoài** — boundary của CI không áp lên phiên đó.

Ba lớp hiện chặn phần lớn kịch bản đó:

| Mắt xích | Trạng thái |
|---|---|
| Tạo role không boundary | **Chưa chặn** — chặn được thì phải bắt mọi `CreateRole` mang boundary, kéo theo sửa toàn bộ module tạo service role |
| Gỡ / thay boundary yếu | ✅ Đã chặn (`Resource = "*"` + điều kiện) |
| Lấy credential từ trong CI | ✅ Đã chặn (`AssumeRole`, `CreateAccessKey`) |
| Phát hiện | ✅ `CreateRole` = group 2, `UpdateAssumeRolePolicy` + `AttachRolePolicy` = group 3 — **cả hai đều critical nên bypass allowlist**, alert ngay cả khi actor là CI role |

**Việc còn lại (vòng sau, ngoài PR này):** bắt buộc boundary trên `iam:CreateRole`/`CreateUser` bằng điều kiện `iam:PermissionsBoundary`, đồng thời truyền `permissions_boundary` xuống mọi module tạo service role (`eks-platform`, `access`, `edge`, `audit-detection`). Đây là thay đổi diện rộng chạm nhiều module ngoài phạm vi Mandate 12 nên tách riêng — nhưng phải ghi vào backlog, không để trôi.

### 9.4 Quy trình attach — hai bước tách biệt

Root `infra/bootstrap/github-oidc` apply **thủ công** bởi người có MFA, không qua CI.

**Bước 1 — merge PR (không đổi hành vi CI).** `enable_ci_audit_boundary = false` là default, nên apply chỉ **tạo** managed policy. Hai role chưa có boundary, CI chạy y như cũ. Kết quả: policy có thể review trên AWS Console trước khi ràng buộc bất kỳ thứ gì.

**Bước 2 — simulate rồi mới attach.**

```powershell
$env:AWS_PROFILE = "techx-new"
$acct     = "197826770971"
$applyArn = "arn:aws:iam::${acct}:role/techx-corp-tf3-gha-terraform-apply"
$boundary = "arn:aws:iam::${acct}:policy/techx-corp-tf3-ci-audit-boundary"

aws iam get-policy-version --policy-arn $boundary `
  --version-id (aws iam get-policy --policy-arn $boundary --query Policy.DefaultVersionId --output text) `
  --query Policy.Document --output json | Set-Content .\ci-boundary.json

# A. BASELINE — tất cả phải "allowed", nếu không CI sẽ hỏng
aws iam simulate-principal-policy --policy-source-arn $applyArn `
  --permissions-boundary-policy-input-list file://ci-boundary.json `
  --action-names `
      cloudtrail:UpdateTrail cloudtrail:PutEventSelectors cloudtrail:StartLogging `
      s3:PutBucketPolicy s3:PutObjectLockConfiguration s3:PutBucketLifecycleConfiguration `
      events:PutRule events:PutTargets `
      sns:Subscribe sns:SetTopicAttributes `
      lambda:UpdateFunctionCode lambda:UpdateFunctionConfiguration lambda:AddPermission `
      cloudwatch:PutMetricAlarm `
      iam:CreateRole iam:AttachRolePolicy iam:PutRolePolicy iam:CreatePolicy `
      eks:DescribeCluster ec2:DescribeInstances `
  --resource-arns "*" `
  --query "EvaluationResults[?EvalDecision!='allowed'].[EvalActionName,EvalDecision]" --output table

# B. KILL SWITCH — tất cả phải "explicitDeny"
aws iam simulate-principal-policy --policy-source-arn $applyArn `
  --permissions-boundary-policy-input-list file://ci-boundary.json `
  --action-names `
      cloudtrail:StopLogging cloudtrail:DeleteTrail `
      s3:DeleteObject s3:BypassGovernanceRetention s3:DeleteBucket `
      events:DisableRule events:DeleteRule events:RemoveTargets `
      sns:DeleteTopic sns:Unsubscribe `
      lambda:DeleteFunction lambda:PutFunctionConcurrency `
      cloudwatch:DeleteAlarms cloudwatch:DisableAlarmActions `
      iam:DeleteRolePermissionsBoundary iam:CreatePolicyVersion `
      sts:AssumeRole sts:GetFederationToken iam:CreateAccessKey iam:CreateLoginProfile `
  --resource-arns `
      "arn:aws:cloudtrail:ap-southeast-1:${acct}:trail/techx-corp-tf3-audit-detection-ap-southeast-1-trail" `
      "arn:aws:s3:::techx-corp-tf3-audit-trail-ap-southeast-1-${acct}" `
      "arn:aws:s3:::techx-corp-tf3-audit-trail-ap-southeast-1-${acct}/AWSLogs/sim" `
      "arn:aws:events:ap-southeast-1:${acct}:rule/techx-corp-tf3-audit-detection-ap-southeast-1-g7-audit-controls" `
      "arn:aws:sns:ap-southeast-1:${acct}:techx-corp-tf3-audit-detection-ap-southeast-1-alerts" `
      "arn:aws:lambda:ap-southeast-1:${acct}:function:techx-corp-tf3-audit-detection-ap-southeast-1-router" `
      "arn:aws:cloudwatch:ap-southeast-1:${acct}:alarm:techx-corp-tf3-m12-audit-heartbeat-missing" `
      $applyArn $boundary `
  --query "EvaluationResults[?EvalDecision=='allowed'].[EvalActionName,EvalDecision]" --output table
```

```powershell
# C. RESOURCE NGOÀI AUDIT — cùng action như bảng B nhưng nhắm resource khác.
#    Tất cả phải "allowed": boundary không được cản việc xoá Lambda/alarm/rule
#    không liên quan audit.
aws iam simulate-principal-policy --policy-source-arn $applyArn `
  --permissions-boundary-policy-input-list file://ci-boundary.json `
  --action-names `
      lambda:DeleteFunction lambda:PutFunctionConcurrency `
      cloudwatch:DeleteAlarms cloudwatch:DisableAlarmActions `
      events:DeleteRule events:DisableRule events:RemoveTargets `
      sns:DeleteTopic `
      s3:DeleteObject s3:DeleteBucket `
      iam:PutUserPermissionsBoundary iam:PutRolePermissionsBoundary `
  --resource-arns `
      "arn:aws:lambda:ap-southeast-1:${acct}:function:some-unrelated-function" `
      "arn:aws:cloudwatch:ap-southeast-1:${acct}:alarm:some-slo-alarm" `
      "arn:aws:events:ap-southeast-1:${acct}:rule/techx-corp-tf3-karpenter-spot_interruption" `
      "arn:aws:sns:ap-southeast-1:${acct}:some-other-topic" `
      "arn:aws:s3:::techx-products-catalog-2026/obj" `
      "arn:aws:s3:::techx-products-catalog-2026" `
      "arn:aws:iam::${acct}:user/cdo02-tl" `
      "arn:aws:iam::${acct}:role/tf3-production-operator" `
  --query "EvaluationResults[?EvalDecision!='allowed'].[EvalActionName,EvalDecision]" --output table
```

**Gate:** cả ba bảng đều **rỗng**.

| Bảng | Ý nghĩa khi rỗng |
|---|---|
| A | Không action Terraform baseline nào bị deny → CI không hỏng |
| B | Không kill switch audit nào được allow → boundary có tác dụng |
| C | Không action nào trên resource ngoài audit bị deny → **boundary không lan sang việc khác** |

Bảng C là bằng chứng trực tiếp cho câu hỏi "xoá Lambda/alarm/rule khác có bị chặn không". Nếu bảng C có dòng nào, nghĩa là ARN pattern trong `local.m12_*` quá rộng — sửa pattern rồi simulate lại, **không** attach.

Lưu output cả ba bảng + SHA-256 vào evidence.

Chỉ khi cả hai bảng rỗng mới đặt `enable_ci_audit_boundary = true` và apply lại root bootstrap.

**Bước 3 — smoke test CI.** Chạy `terraform-plan.yml` (`workflow_dispatch`) trên `main`. Plan phải chạy hết, không `AccessDenied`. Sau đó mới dùng `terraform-apply.yml` cho change tiếp theo.

### 9.5 `gitlab-ci-deployer` — attach thủ công

IAM user admin, chưa MFA, còn access key dài hạn, **không do Terraform quản lý** và không xoá được vì pipeline GitLab đang dùng. Quyết định: **áp cùng boundary CI**.

Vì sao dùng đúng boundary này chứ không tạo cái chặt hơn: boundary này cho phép mọi thứ trừ kill switch audit, nên **không thay đổi hành vi deploy hiện tại** của pipeline — rủi ro làm hỏng GitLab CI gần bằng không, trong khi vẫn đóng đúng lỗ hổng Mandate 12 quan tâm. Một boundary chặt hơn đòi hỏi inventory workflow GitLab mà hiện chưa có.

`permissions_boundary` là thuộc tính của `aws_iam_user`, nên Terraform chỉ set được nếu quản lý user đó. User này nằm ngoài state → attach bằng CLI, sau khi simulation §9.4 pass:

```powershell
$boundary = "arn:aws:iam::197826770971:policy/techx-corp-tf3-ci-audit-boundary"

# Simulate TRƯỚC — cùng ba bảng A/B/C như §9.4, đổi policy-source-arn
aws iam simulate-principal-policy `
  --policy-source-arn "arn:aws:iam::197826770971:user/gitlab-ci-deployer" `
  --permissions-boundary-policy-input-list file://ci-boundary.json `
  --action-names <bộ action tương ứng> --resource-arns <resource tương ứng>

# Attach (người có MFA thực hiện, không phải chính user đó)
aws iam put-user-permissions-boundary `
  --user-name gitlab-ci-deployer `
  --permissions-boundary $boundary

# Verify
aws iam get-user --user-name gitlab-ci-deployer --query User.PermissionsBoundary
```

Sau attach, user **không tự gỡ được** boundary: statement `DenyRemovingAnyBoundary` deny `iam:DeleteUserPermissionsBoundary` ở `Resource = "*"`, và `DenyAttachingAnyOtherBoundary` không cho thay bằng boundary yếu hơn.

**Inventory bắt buộc TRƯỚC khi attach.** Boundary deny `sns:Unsubscribe`/`SetSubscriptionAttributes` ở `Resource = "*"`, và deny `sts:AssumeRole` + `iam:CreateAccessKey`. Nếu pipeline GitLab dùng bất kỳ thứ nào trong đó, nó sẽ gãy. Repo này không thấy được pipeline đó, nên owner phải trả lời trước:

| Câu hỏi | Nếu "có" thì sao |
|---|---|
| Pipeline có gỡ/sửa SNS subscription nào không? | Tách deployment identity riêng, hoặc chuyển thao tác đó sang quy trình human-approved |
| Pipeline có `sts:AssumeRole` sang role khác không? | Cần allowlist ARN cụ thể — thêm điều kiện vào statement, không bỏ deny |
| Pipeline có tự phát hành access key không? | Chuyển sang OIDC hoặc tách identity |

**Smoke test bắt buộc:** chạy một pipeline GitLab thật sau khi attach. Nếu hỏng, gỡ bằng `aws iam delete-user-permissions-boundary --user-name gitlab-ci-deployer` (từ identity MFA khác — user đó không tự gỡ được), root-cause rồi thử lại.

**Sau khi attach xong**, điền `audit_detection_bounded_principals` trong `production.auto.tfvars` để heartbeat canh boundary còn attach hay không:

```hcl
audit_detection_bounded_principals = {
  "arn:aws:iam::197826770971:role/techx-corp-tf3-gha-terraform-plan"  = "arn:aws:iam::197826770971:policy/techx-corp-tf3-ci-audit-boundary"
  "arn:aws:iam::197826770971:role/techx-corp-tf3-gha-terraform-apply" = "arn:aws:iam::197826770971:policy/techx-corp-tf3-ci-audit-boundary"
  "arn:aws:iam::197826770971:user/gitlab-ci-deployer"                 = "arn:aws:iam::197826770971:policy/techx-corp-tf3-ci-audit-boundary"
}
```

Không gõ tay — root bootstrap sinh sẵn đúng map này:

```powershell
terraform -chdir=infra/bootstrap/github-oidc output -json ci_audit_boundary_expected_map
```

Để rỗng trước Phase 4b, nếu không heartbeat FAIL giả. Đây là thứ duy nhất phát hiện được việc boundary của `gitlab-ci-deployer` bị gỡ, vì attach thủ công không có gì cưỡng chế.

**Hai việc còn lại, ngoài phạm vi boundary:**

| Việc | Ai | Ghi chú |
|---|---|---|
| Bật MFA cho identity | Team AI (chủ sở hữu) | Boundary không thay được MFA — key dài hạn không MFA vẫn là đường vào |
| Rotate/vô hiệu 2 access key | Owner pipeline GitLab | Cần downtime window |

**Về automation allowlist:** hiện `gitlab-ci-deployer` vẫn nằm trong `audit_detection_additional_allowed_automation_principal_arns`. Sau khi bounded, việc đó ít nguy hiểm hơn nhiều — group 1/2/3/4/7/8 đã là critical nên vẫn alert, và các action audit đã bị boundary chặn. Phần còn bị suppress là **group 5** (đọc secret nhạy cảm) và **group 6** (xoá cluster/RDS/bucket). Group 6 với một admin CI là điểm mù vận hành đáng cân nhắc gỡ, nhưng nằm ngoài phạm vi Mandate 12 — đề xuất xử lý ở PR IAM cùng lúc với rotate key, và chấp nhận đánh đổi alert volume.

### 9.6 Rollback

Đặt `enable_ci_audit_boundary = false` và apply lại root bootstrap. Boundary được gỡ ngay, không đụng role hay workload nào khác. Thời gian: vài phút.

**Lưu ý quan trọng:** khi boundary đã attach, **CI không tự gỡ được** (`DenyRemovingAnyBoundary`). Rollback bắt buộc do người có MFA thực hiện tại root bootstrap. Đây là chủ ý — nhưng nghĩa là phải luôn có ít nhất một người giữ được đường đó.

### 9.7 Access Analyzer warning

Statement `AllowEverythingWithinBoundary` dùng `Action: "*"` / `Resource: "*"`. Đây là **trần bắt buộc** của permissions boundary — không có nó thì mọi thứ bị chặn. Nó không cấp thêm quyền nào: quyền thật vẫn do policy gắn trực tiếp quyết định, và explicit Deny luôn thắng.

IAM Access Analyzer sẽ cảnh báo. Đây là cảnh báo đã biết, cần ghi acceptance bằng văn bản trong change record.

---

## 10. Trình tự triển khai

| Phase | Việc | Exit gate | Ước lượng |
|---:|---|---|---|
| 0 | Revalidate live (trail/bucket/SNS/router), lưu baseline + hash. Đếm resource cho §6.3 | Baseline có hash; approval đủ | 30-60 phút |
| 1 | Điền `audit_detection_s3_data_event_arns` → unit test §7 → tạo PR → CI plan chạy trên PR → review | Plan chỉ update/add audit control; **zero destroy/replace** | 2-4 giờ |
| 2 | Merge → `workflow_dispatch action=plan` → review artifact + hash → `action=apply` | `IsLogging=true`; trail ARN/bucket không đổi | 30-60 phút |
| 3 | Verify delivery/digest/retention/heartbeat. Confirm 6 subscription fallback | Digest bao phủ cutover; heartbeat PASS | 90-120 phút |
| 4 | Canary `GetObject` + `GetSecretValue`, thu evidence | Coverage + integrity pass | 60-120 phút |
| 4b | **Attach CI boundary** (§9.4): apply bootstrap tạo policy → simulate → `enable_ci_audit_boundary = true` → apply lại → smoke test CI plan. Sau đó attach thủ công cho `gitlab-ci-deployer` (§9.5) + smoke test pipeline GitLab | Ba bảng simulation rỗng; CI plan và pipeline GitLab chạy hết không `AccessDenied` | 90-120 phút |
| 5 | **PR IAM hardening riêng**: audit-admin, break-glass, operator boundary cho human user, gỡ `gitlab-ci-deployer`, rotate key | Simulation → rollout từng identity → denied test | Nửa ngày trở lên |
| 6 | Mentor test, verdict, residual acceptance | T01-T11 pass; evidence có hash | 2-4 giờ |

Phase 4b tách khỏi Phase 5 vì hai lý do: nó chạm root Terraform khác (`bootstrap/github-oidc` chứ không phải `live/production`), và nếu sai thì hỏng CI chứ không hỏng người dùng — cần rollback độc lập.

### Gate plan ở Phase 1

**Được phép:**
- `~ update in-place`: `aws_s3_bucket_object_lock_configuration`, `aws_s3_bucket_lifecycle_configuration`, `aws_s3_bucket_policy`, `aws_cloudtrail.audit` (selector), `aws_lambda_function.audit_alert_router` (×2, đổi code hash + `DETECTOR_CONFIG_JSON`)
- `+ create`: rule/target/permission cho `g7` và `g8`, toàn bộ resource heartbeat, SNS fallback + policy + 6 subscription, policy CloudWatch cho topic primary

> [!IMPORTANT]
> `require_s3_data_event_coverage = true` làm `terraform plan` **FAIL** nếu `audit_detection_s3_data_event_arns` rỗng. Giá trị vòng 1 đã điền (§8.1) nên gate này hiện **đã thoả**. Nếu ai đó xoá giá trị, plan sẽ dừng ngay thay vì apply âm thầm một trail không ghi `GetObject`.

**NO-GO nếu plan có:**
- bất kỳ `- destroy` hoặc `-/+ replace` — đặc biệt trên `aws_cloudtrail.audit` hoặc `aws_s3_bucket.trail_logs` (`prevent_destroy` sẽ chặn, nhưng plan hiện `replace` là dấu hiệu sai)
- thay đổi EKS / network / datastore / workload / flagd
- ARN chưa được owner duyệt trong selector
- audit bucket nằm trong `s3_data_event_arns`

---

## 11. Verify sau apply

```powershell
$env:AWS_PROFILE = "techx-new"
$t = "techx-corp-tf3-audit-detection-ap-southeast-1-trail"
$b = "techx-corp-tf3-audit-trail-ap-southeast-1-197826770971"

# Trail: ARN/bucket không đổi, vẫn logging
aws cloudtrail describe-trails --trail-name-list $t --region ap-southeast-1
aws cloudtrail get-trail-status --name $t --region ap-southeast-1

# Selector: Management + approved S3 Data
aws cloudtrail get-event-selectors --trail-name $t --region ap-southeast-1

# Archive
aws s3api get-object-lock-configuration      --bucket $b   # COMPLIANCE / 365
aws s3api get-bucket-lifecycle-configuration --bucket $b   # 400
aws s3api get-bucket-policy --bucket $b                    # có DenyNonCloudTrailObjectMutation

# Heartbeat
aws logs filter-log-events --log-group-name /aws/lambda/techx-corp-tf3-m12-audit-heartbeat `
  --region ap-southeast-1 --filter-pattern '"status"' --limit 5
aws cloudwatch describe-alarms --alarm-name-prefix techx-corp-tf3-m12-audit-heartbeat --region ap-southeast-1

# Subscription: cả 3 topic không còn PendingConfirmation
```

> [!CAUTION]
> **`CodeSha256` lệch = DỪNG, không bao giờ nới kiểm tra.**
>
> Heartbeat báo lệch nghĩa là artifact đang chạy khác artifact Terraform đã duyệt. Chỉ có hai khả năng, và cả hai đều phải dừng deploy để điều tra:
>
> 1. **Router thật sự bị thay code** → Critical incident. Preserve evidence, không apply gì thêm, truy CloudTrail `UpdateFunctionCode` xem actor/thời điểm.
> 2. **Artifact đóng gói không tất định** → lỗi build, phải sửa build chứ không sửa control.
>
> Khả năng (2) đã được loại phần lớn: `archive_file` dùng `source_file` đóng gói đúng `index.py`, nên file lạ trong thư mục — kể cả `__pycache__` do unit test sinh ra — không vào được artifact. Nếu vẫn lệch, kiểm tra theo thứ tự:
>
> ```powershell
> # 1. So hash thật với baseline Terraform
> aws lambda get-function-configuration --function-name <router> --region ap-southeast-1 --query CodeSha256
> terraform -chdir=infra/live/production state show 'module.audit_detection_ap_southeast_1.aws_lambda_function.audit_alert_router' | Select-String source_code_hash
>
> # 2. Ai đổi code gần nhất?
> aws cloudtrail lookup-events --region ap-southeast-1 `
>   --lookup-attributes AttributeKey=EventName,AttributeValue=UpdateFunctionCode --max-results 10
> ```
>
> **Không** gỡ field `codeSha256` khỏi `m12_router_expected`. Làm vậy là tự tay tạo lại đúng lỗ hổng mà kiểm tra này sinh ra để bịt: router bị thay bằng no-op vẫn `Active` và heartbeat vẫn PASS.

**Retention chỉ chứng minh được bằng object MỚI.** Chờ một object CloudTrail được giao sau cutover, rồi:
```powershell
aws s3api get-object-retention --bucket $b --key "<key-object-sau-cutover>"
# Mode=COMPLIANCE, RetainUntilDate >= cutover + 365 ngày
```

**Digest phát theo giờ**, không phải 5-15 phút (đó là log file). Kiểm tra `LatestDigestDeliveryTime` đã vượt thời điểm bắt đầu window rồi mới chạy:
```powershell
aws cloudtrail validate-logs --trail-arn <arn> --start-time <utc> --end-time <utc> --verbose
```
Thực tế cần chờ ~90 phút sau apply.

---

## 12. Nghiệm thu — ba đòn mentor

Chi tiết đầy đủ ở `Task_mandate_12/m12-tests-v2.2.md` (T01-T11). Tóm tắt:

### Đòn 1 — Làm mù

Từ bounded identity, thử `stop-logging` (**cả dạng tên và dạng ARN**), `delete-trail`, `put-event-selectors`, mutation lên audit bucket, `disable-rule`, `unsubscribe`, `update-function-code`, và mutation boundary trên principal test chuyên dụng.

**PASS:** mỗi lệnh `AccessDenied` + CloudTrail có event (actor/session/time/region) + **Lambda router có log `"sent": true`** (không phải `"ignored"`) + SNS receipt + control sau test không đổi.

**Bài test mạnh nhất:** chạy `StopLogging` từ một principal **đang nằm trong** `allowed_principals`. Alert vẫn phải kêu — đây là bằng chứng trực tiếp lỗ hổng 1 đã bịt.

### Đòn 2 — Làm hụt

Tạo canary secret + canary object, đọc cả hai. Canary object đặt tại `s3://techx-tf3-197826770971-tfstate/m12-canary/` theo quy tắc §8.2 — prefix riêng, không đụng `*/terraform.tfstate`. Audit-admin tải bản sao log `.json.gz`, chạy `Export-M12CloudTrailEvidence.ps1`.

**PASS:** evidence có `GetObject` (bucket/key/actor/session/requestID) và `GetSecretValue` (secret ARN/actor/session), **không** chứa `SecretString`/`SecretBinary`.

**Giới hạn phải nói với mentor:** coverage vòng 1 chỉ gồm Terraform state. Đọc trộm AIOps playbook, model artifact hay ALB log **hiện chưa có vết** — ba bucket đó đang chờ owner tương ứng ký (§8.1). Nêu chủ động, không để mentor tự phát hiện.

### Đòn 3 — Làm mỏng/sửa

`validate-logs` trên window sau cutover, cộng bằng chứng WORM.

**PASS:** không `INVALID`, không thiếu digest; Object Lock COMPLIANCE 365 trên object mới; lifecycle 400.

### Đòn bổ sung — Heartbeat

Gọi Lambda với `{"forceAlertTest": true}` để chứng minh cả hai đường publish hoạt động độc lập. Dùng `set-alarm-state` có kiểm soát trên alarm Errors để chứng minh cả primary và fallback nhận cùng alert. **Không** xoá hay sửa topic production.

---

## 13. Rollback

| Tình huống | Xử lý |
|---|---|
| Plan có drift/replace/delete ngoài dự kiến | NO-GO. Không apply; owner xử lý drift rồi tạo plan mới |
| **CI boundary làm hỏng plan/apply** | Đặt `enable_ci_audit_boundary = false`, apply lại root bootstrap bằng identity MFA. Vài phút. **CI không tự gỡ được** — phải có người giữ đường này |
| Router lỗi sau apply | DLQ SQS giữ event. Revert PR và apply lại. **Không** tắt rule, không tắt trail |
| Selector/heartbeat sai sau apply | Fix-forward trong production root. Không stop trail, không xoá bucket |
| Delivery/digest lỗi | Preserve evidence, kiểm tra bucket policy/status, fix-forward. Không claim cutover |
| Lệnh đáng lẽ deny lại thành công | Dừng test ngay, mở Critical incident, preserve event + post-state |
| Compliance retention đã áp dụng | **Không rút ngắn được** — kể cả root. Chấp nhận retention/cost theo approval |
| Có version hiện hữu đã ≥ 400 ngày | NO-GO trước apply: chọn lifecycle dài hơn hoặc export/preservation có owner approval |

`prevent_destroy` trên bucket và trail sẽ làm `terraform apply` **fail** nếu plan muốn xoá chúng. Muốn xoá thật phải PR riêng gỡ guard, có chữ ký security owner.

---

## 14. Rủi ro tồn dư — cần ký nhận

1. **Root** không thể bị permissions boundary và vẫn tác động được audit/alert plane. Bắt buộc: root MFA, không có root access key, custodian có tên, quy trình incident-only, chữ ký chấp nhận.
2. **`gha-terraform-apply`** giữ `AdministratorAccess`, nhưng sau Phase 4b có boundary chặn các kill switch. **Phần còn lại:** `PutEventSelectors`, `UpdateTrail`, `PutBucketPolicy`, `UpdateFunctionCode` vẫn được phép vì Terraform cần — một PR độc hại vẫn thu hẹp được selector, gỡ Deny khỏi bucket policy, hoặc thay code router. Bù bằng PR review + alert group 1/`g7` (đã bypass allowlist) + heartbeat so exact selector, bucket policy và `CodeSha256`/`Handler`/`Role`/`DETECTOR_CONFIG_JSON` của router mỗi 5 phút. Xem §9.3.
3. **Object giao trước cutover** giữ GOVERNANCE 14 ngày. Claim 365 ngày chỉ tính từ UTC cutover.
4. **Lifecycle 400 ngày áp cả object hiện có** → chi phí lưu trữ tăng ngay sau apply.
5. **`gitlab-ci-deployer`** — IAM user admin, **chưa MFA**, còn 2 access key dài hạn, không xoá được. Sau Phase 4b nó mang boundary nên mất đường tắt tắt audit, nhưng:
   - **Access key không MFA vẫn là đường vào.** Boundary giới hạn *làm được gì*, không giới hạn *ai đăng nhập được*. Team AI (chủ sở hữu identity) phải bật MFA; rotate key cần owner pipeline xác nhận downtime. Cả hai thuộc PR IAM.
   - Vẫn nằm trong automation allowlist → group 5 (đọc secret) và group 6 (xoá cluster/RDS/bucket) bị suppress. Group 6 với một admin CI là điểm mù vận hành; đề xuất gỡ khỏi allowlist ở PR IAM, đánh đổi bằng alert volume.
   - Attach thủ công nên **không có gì cưỡng chế nó tồn tại**. Nếu ai đó gỡ, chỉ CloudTrail `DeleteUserPermissionsBoundary` (group 8, critical) phát hiện — heartbeat hiện không kiểm tra boundary attachment. Cân nhắc bổ sung ở vòng sau.
6. **Alert volume `g7`** — nếu quy trình đối chiếu change ID không được duy trì, người nhận sẽ mute và tạo lại cửa sổ mù.
7. **Single-account** — không có SCP, không organization trail, không cross-account archive.
8. **CI vẫn tạo được principal mới không mang boundary.** `iam:CreateRole` + `UpdateAssumeRolePolicy` + `AttachRolePolicy` phải để mở vì Terraform cần quản service role của mọi module. Một PR độc hại có thể tạo role trust sang account ngoài rồi assume từ đó — boundary CI không áp lên phiên ngoài. Đã chặn được ba mắt xích còn lại (gỡ boundary, thay boundary yếu, lấy credential từ trong CI) và cả ba action trên đều là group 2/3 critical nên alert ngay. **Đóng hẳn cần vòng sau:** điều kiện `iam:PermissionsBoundary` trên `CreateRole`/`CreateUser` + truyền `permissions_boundary` xuống mọi module tạo service role.
9. **Coverage S3 vòng 1 chỉ gồm Terraform state.** Ba bucket còn lại (`techx-aiops-playbooks-*`, `tf3-aiops-models-*`, `sosflow-alb-logs-*`) chưa có vết đọc vì TF3 không phải data owner. Đây là exception **có owner và có kế hoạch vòng 2** (§8.1), không phải ngoại lệ im lặng — nhưng tới khi đóng, claim "đóng coverage gap" chỉ đúng trong phạm vi đã liệt kê.

Câu claim đúng khi nghiệm thu:

> Với các daily operator/CI identity đã inventory và đã harden, mọi attempt thay đổi audit control đều bị deny và có evidence alert trong test window. Claim này **không** chứng minh root, break-glass hay `gha-terraform-apply` bị chặn tuyệt đối, và **không** chứng minh alert delivery liên tục nếu toàn bộ alert plane cùng account bị thay đổi. Retention 365 ngày chỉ áp cho object ghi từ `<UTC cutover>` trở đi.

---

## 15. Definition of Done

**Foundation (PR này):**

- [ ] Unit test router PASS 6/6 case (§7)
- [ ] `terraform fmt -check -recursive infra/` sạch
- [ ] CI plan trên PR: chỉ update/add audit control, **zero destroy/replace**
- [ ] Exact S3 scope được ký và điền vào tfvars
- [ ] Change ID có Git SHA, saved-plan hash, UTC window, danh sách g7/g8 dự kiến, người trực
- [ ] Apply xong: trail ARN/bucket không đổi, `IsLogging=true`, `LatestDeliveryError` rỗng
- [ ] Selector đúng Management + approved S3 Data
- [ ] Object **mới** có `COMPLIANCE` retain-until ≥ 365 ngày; lifecycle 400
- [ ] `validate-logs` sạch trên window sau cutover
- [ ] Heartbeat PASS; 2 alarm có đúng `AlarmActions` primary + fallback
- [ ] Heartbeat xác nhận `CodeSha256`/`Handler`/`Role`/`DETECTOR_CONFIG_JSON` của cả hai router khớp baseline Terraform
- [ ] 18 subscription (3 topic × 6 email) đều `Confirmed`
- [ ] Canary `GetObject` + `GetSecretValue` có evidence sạch, không lộ secret value
- [ ] Mọi CRITICAL alert trong window apply được đối chiếu với change ID

**CI boundary (Phase 4b):**

- [ ] Managed policy `techx-corp-tf3-ci-audit-boundary` đã tạo và được review
- [ ] Simulation bảng A (baseline) rỗng — không action Terraform nào bị deny
- [ ] Simulation bảng B (kill switch) rỗng — không action tấn công nào được allow
- [ ] Simulation bảng C (resource ngoài audit) rỗng — boundary không lan sang Lambda/alarm/rule khác
- [ ] Xác nhận `sns:Unsubscribe` bị deny (statement `Resource = "*"`) và `sns:Subscribe` vẫn allowed
- [ ] Access Analyzer warning về `Action: "*"` có acceptance bằng văn bản
- [ ] `enable_ci_audit_boundary = true`, apply bootstrap thành công
- [ ] `terraform-plan.yml` chạy hết trên `main`, không `AccessDenied`
- [ ] Owner GitLab đã trả lời 3 câu inventory (SNS subscription / AssumeRole / access key) trước khi attach
- [ ] `gitlab-ci-deployer` đã attach boundary; `get-user` xác nhận `PermissionsBoundary`
- [ ] Một pipeline GitLab thật chạy hết sau khi attach
- [ ] `audit_detection_bounded_principals` đã điền cả 3 principal; heartbeat xác nhận boundary còn attach
- [ ] Simulation xác nhận `sts:AssumeRole` và `iam:CreateAccessKey` là `explicitDeny`; `iam:PutRolePermissionsBoundary` với boundary khác cũng `explicitDeny`
- [ ] Có ít nhất một người MFA giữ được đường rollback ở root bootstrap

**Toàn mandate (sau PR IAM):**

- [ ] IAM inventory đầy đủ, không còn identity `Unknown`
- [ ] `gitlab-ci-deployer` gỡ khỏi allowlist + key rotate/vô hiệu
- [ ] Operator boundary rollout từng human identity, baseline pass
- [ ] T01-T11 pass, evidence có SHA-256 và observer/approver
- [ ] Residual risk §14 được ký

> Foundation pass nhưng IAM chưa xong = **`AUDIT READY / PARTIAL`**, không phải `VERIFIED`.
> Không dùng deadline để bỏ qua gate.

---

## 16. Hai câu hỏi còn lại cần Tech Lead quyết

### Câu 1 — Ngưỡng alert volume cho `g7`

`g7` khớp theo `eventName` không lọc resource, nên mọi `PutRule` / `PutBucketPolicy` / `UpdateFunctionCode` / `PutMetricAlarm` trong toàn account đều thành CRITICAL và bypass allowlist.

Chạy lệnh đếm ở §6.3, rồi chọn: **(a)** chấp nhận + cam kết quy trình change-ID · **(b)** thêm điều kiện `requestParameters` giới hạn về resource audit · **(c)** tách `g7` thành hai mức severity.

### Câu 2 — Người điều phối xác nhận subscription

PR này tạo topic `techx-corp-tf3-m12-audit-heartbeat-fallback` với 6 email subscription mới. Heartbeat báo **FAIL liên tục** cho tới khi cả 6 confirm. Cộng với 4 subscription M11 đang pending → **10 lần xác nhận** cần điều phối trước khi nghiệm thu.

Cần một người chịu trách nhiệm nhắc và theo dõi tới khi đủ 18/18.

### Đã chốt — boundary cho `gha-terraform-apply`

Nhóm chọn **phương án (b)**: boundary riêng cho CI, deny đúng resource audit, cho phép IAM CRUD chung. Thiết kế, giới hạn, quy trình simulate/attach và rollback ở **§9**.

Phương án **(c)** — tách `AuditFoundationApplyRole` khỏi `WorkloadTerraformApplyRole` — giữ trong backlog cho giai đoạn sau.

---

## 17. Tài liệu liên quan

| Tài liệu | Nội dung |
|---|---|
| `Task_mandate_12/m12-plan-v2.2.md` | Kế hoạch gốc, nguồn chuẩn kỹ thuật |
| `Task_mandate_12/m12-solution-v2.2.md` | Kiến trúc và trade-off |
| `Task_mandate_12/m12-coverage-v2.1.md` | Coverage matrix S3/secret |
| `Task_mandate_12/m12-iam-scope-v2.0.md` | IAM ownership và migration |
| `Task_mandate_12/m12-tests-v2.2.md` | Test matrix T01-T11 và evidence pack |
| `Task_mandate_12/m12-runbook-v2.2.md` | Phase, gate, rollback |
| `Task_mandate_12/m12-phoi-hop-cd01-v2.0.md` | Phân chia trách nhiệm với CD01 |
| `Task_mandate_12/code_audit/HD_audit_foundation-v2.2.md` | Hướng dẫn từng bước cho foundation |
| `Task_mandate_12/code_audit/HD_iam_hardening-v2.1.md` | Hướng dẫn từng bước cho IAM |

Nguồn AWS: [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html) · [CloudTrail data-event selectors](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/filtering-data-events.html) · [CloudTrail digest chain](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-digest-file-structure.html) · [validate-logs](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-cli.html) · [IAM permissions boundaries](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html)

---

**Cập nhật:** 2026-07-21 · **Trạng thái:** READY FOR REVIEW — chưa được phép apply
