# MANDATE 10 / PM-127
# SBOM cho image tự build + Kyverno `verifyImages` Admission Enforce

## Technical Specification, Execution Plan, Test Matrix và Evidence Contract

**Repository triển khai:** `tuu-ngo/Phase3-TF3-Infra-Sentinel`  
**Baseline audit ban đầu:** `main@a92084f266fa7f6d989c9ddf1c66461293ab4b13`
**Baseline triển khai cuối sau đồng bộ main:** `main@bbe25038b47bf743b5e35ec6f997d89380f639fd`
**Cluster:** `techx-corp-tf3`  
**AWS account:** `197826770971`  
**Region:** `ap-southeast-1`  
**ECR repository:** `197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp`  
**Namespace sản phẩm:** `techx-tf3`  
**Deadline mandate:** hết ngày 20/07/2026  
**Task owner:** Lê Hoàng Việt  
**Task liên quan:** PM-127, PM-104, PM-101, PM-122
**Mức ưu tiên:** cao nhất trong epic  
**Trạng thái tài liệu:** đặc tả triển khai; không phải bằng chứng production đã hoàn thành

---

## Jira reconciliation bắt buộc: PM-127, PM-128 và PM-114

Jira hiện ghi PM-127 `To Do` cho SBOM + `verifyImages`, trong khi PM-128 `Done` nói `verifyImages` đã đóng PM-114. Đây là trạng thái cần reconcile, không phải cơ sở để khẳng định PM-114 còn To Do hoặc admission đã được chứng minh production-ready.

Trước khi bất kỳ phần nào của tài liệu được đánh dấu triển khai xong, phải liên kết: PR/commit PM-128; policy source trong Git; `kubectl get clusterpolicy`; `Enforce` và `Ready=True`; signed image pass; và một first-party image thật nhưng unsigned/wrong-identity bị reject bởi đúng rule signature. Nếu thiếu mắt xích, reopen/correct ticket hoặc giữ `BLOCKED`.

Mọi ô `Pass` trong test matrix dưới đây là **expected acceptance result**, không phải evidence đã có. Chỉ run ID, artifact, output policy và evidence runtime được liên kết mới đổi trạng thái thành `PASS`.

### Final-main source re-audit tại `bbe25038`

Canonical audit verdict được giữ duy nhất tại `docs/docx_cdo01/plan/mandate-10/mandate-10-gap-analysis.md`. Spec này consume baseline/inventory từ PM-124 và không trở thành gap-analysis source of truth thứ hai.

- Có 7 workflow YAML ở snapshot hiện tại; final DoD vẫn phải discover động toàn bộ workflow/reusable workflow.
- Có 28 Dockerfile khi tính 20 production target, OpenSearch, 6 genproto và Cypress; Docker scope vẫn cần quyết định PM như PM-129 quy định.
- Authoritative production Helm render sử dụng đúng bốn values file: `values.yaml`, `values-flagd-sync.yaml`, `values-prod.yaml` và `values-aio-llm.yaml` theo Argo CD Application.
- Sau khi đồng bộ main, render đủ bốn values tạo `/tmp/techx-prod.yaml` gồm 22,445 dòng và 30 image reference duy nhất. Inventory/allow-list phải được sinh lại từ output này; không giữ số của render ba values cũ. Local `helm dependency build` cần cấu hình đủ năm Helm repository trước khi được dùng làm evidence, dù chart vendored hiện vẫn template được.
- `gitops/infrastructure/limit-range.yaml` đã bị xóa trên main. Resource/image-reference enforcement hiện có thêm native `ValidatingAdmissionPolicy` + binding `Deny`; các Kyverno policy digest/latest/resource/security-context vẫn phải được đối chiếu Git và live state trước cutover.
- Render vẫn có external image tag; inventory/allow-list và digest policy cho external images phải được kiểm theo contract, không suy ra từ việc Helm render pass.
- Final evidence phải đính kèm exact baseline SHA, machine-generated workflow/action/Dockerfile inventories và Unicode format-control scan; số 7/28 chỉ là snapshot `bbe25038`.

---

# 0. Kết luận điều tra hiện trạng

## 0.1. Những gì dự án đã có

Dự án đã có phần lớn nền móng của secure image delivery:

1. ECR `techx-corp` bật tag immutability.
2. Image production được render và deploy bằng digest.
3. Workflow chỉ build service thay đổi, có đường full build khi cần.
4. Candidate `linux/amd64` được Trivy scan trước khi push.
5. HIGH/CRITICAL làm workflow fail.
6. Sau push, workflow resolve đúng digest thật từ ECR.
7. Image đa kiến trúc được scan lại theo từng platform bằng digest.
8. Digest được ký keyless bằng Cosign qua GitHub Actions OIDC.
9. Chữ ký được verify ngay với:
   - issuer `https://token.actions.githubusercontent.com`;
   - identity của workflow `build-push-ecr.yml@refs/heads/main`.
10. Workflow tạo `approved-images.json`.
11. Workflow mở PR chỉ để cập nhật digest trong `values-prod.yaml`.
12. Kyverno hiện đã Enforce:
   - cấm `latest` và implicit latest;
   - bắt buộc first-party ECR dùng `@sha256:...`;
   - baseline security context;
   - CPU/memory requests và limits.
13. Argo CD tự đồng bộ policy từ `gitops/policies/kyverno`.
14. Production hiện có danh sách external image pinned bằng digest và workflow scan định kỳ.

## 0.2. Hai gap chính đúng theo task

### Gap A — chưa có SBOM

Không có bước nào trong `build-push-ecr.yml`:

- sinh CycloneDX SBOM từ digest đã push;
- attest SBOM vào digest;
- verify attestation;
- lưu mapping digest → SBOM;
- cung cấp lệnh tra SBOM theo digest.

### Gap B — chưa có admission verification chữ ký

Cluster đang bắt buộc digest nhưng chưa chứng minh digest đó được ký bởi workflow hợp lệ.

Một người có quyền push ECR vẫn có thể:

1. build image bên ngoài pipeline;
2. push image với tag mới;
3. lấy digest;
4. sửa GitOps manifest sang digest đó;
5. vượt qua policy “require digest” hiện tại.

PM-127 phải đóng đúng đường bypass này bằng Kyverno `verifyImages` ở `Enforce`.

## 0.3. Gap phụ bắt buộc phải xử lý để PM-127 hoạt động thật

### Private ECR authentication

Kyverno admission controller phải đọc signature/attestation từ private ECR.

Chỉ thêm `verifyImages` policy mà không cấp ECR read cho Kyverno sẽ khiến:

- image hợp lệ bị reject do registry authentication;
- Audit report đầy lỗi giả;
- Enforce có thể chặn toàn bộ rollout.

Cần IRSA least-privilege cho ít nhất:

- `kyverno-admission-controller`;
- `kyverno-background-controller`, nếu cần background PolicyReport.

### External inventory hiện chưa đủ

Workflow external scan hiện liệt kê tám image chính, nhưng production render còn có:

- BusyBox init containers;
- sidecars và init containers sinh bởi dependency chart;
- có thể có config reloader hoặc helper image.

Allow-list không được copy thủ công từ release notes. Nó phải được đối chiếu với Helm render production đầy đủ.

### ECR lifecycle và reference artifacts

ECR đang expire untagged artifacts sau bảy ngày. Signature và SBOM attestation là OCI reference artifacts. Trước cutover phải xác minh:

- lifecycle preview không nhắm sai reference artifact còn cần thiết;
- signature và SBOM vẫn truy xuất được khi subject image còn tồn tại;
- digest rollback cũ vẫn verify được.

### Action pinning vẫn là gap của toàn Mandate 10

Directive #10 còn yêu cầu GitHub Actions pin theo commit SHA. Workflow hiện vẫn dùng các ref dạng:

```yaml
actions/checkout@v6
aws-actions/configure-aws-credentials@v4
actions/upload-artifact@v4
sigstore/cosign-installer@v4.1.2
```

Task PM-127 đóng hai mảnh: SBOM attestation và admission signature verification bằng Kyverno `verifyImages`. Không được tuyên bố toàn bộ Mandate 10 hoàn tất nếu action/base-image pinning và required-check evidence chưa được đóng ở task khác.

---

# 1. Mục tiêu

Sau khi hoàn thành task này:

1. Mọi image first-party được build qua release workflow có CycloneDX SBOM.
2. SBOM được sinh từ đúng immutable image digest đã push.
3. SBOM được Cosign attest vào đúng digest.
4. Attestation được verify với cùng issuer và workflow identity.
5. Có một lệnh để lấy và verify SBOM từ digest.
6. Kyverno chỉ cho phép first-party ECR image có chữ ký hợp lệ từ workflow main.
7. External runtime image chỉ được dùng khi exact digest nằm trong allow-list được review.
8. Cả hai policy ở `Enforce` và `Ready=True`.
9. Image first-party chưa ký hoặc ký sai identity bị admission từ chối.
10. Running production images có zero unexplained false-positive.
11. Storefront, checkout, telemetry và GitOps không bị gián đoạn.
12. Có evidence đủ để mentor tự chạy và tự xác minh.

---

# 2. Phạm vi

## 2.1. In scope

- 20 build target trong `ALL_SERVICES`.
- Workflow `.github/workflows/build-push-ecr.yml`.
- SBOM CycloneDX cho `linux/amd64` và `linux/arm64`.
- Cosign SBOM attestation.
- Helper tra SBOM theo digest.
- Kyverno private-ECR authentication.
- ClusterPolicy first-party signature verification.
- ClusterPolicy explicit external-image digest allow-list.
- Helm-rendered image inventory.
- Kyverno unit tests.
- Admission server dry-run tests.
- Real unsigned-image rejection.
- PolicyReport reconciliation.
- Runtime/SLO smoke test.
- Evidence pack.
- Audit → Enforce controlled cutover.

## 2.2. Out of scope

- Viết lại Trivy vulnerability gate hiện có.
- Thay keyless Cosign bằng static key.
- TF3 tự ký external image như thể TF3 là producer.
- Chuyển registry.
- Thay đổi application behavior.
- Thay đổi flagd, OpenFeature hoặc fault injection.
- Thay đổi HPA, Karpenter, Argo Rollouts strategy.
- Migrate datastore.
- Mở rộng verifyImages ngay lập tức sang `kube-system` hoặc Kyverno.
- SLSA provenance đầy đủ nếu chưa có task riêng; task này phải giữ compatibility để bổ sung provenance sau.
- Tuyên bố action pinning đã hoàn tất khi chưa có bằng chứng riêng.

---

# 3. Các invariant bắt buộc

## 3.1. First-party image invariant

Mọi first-party runtime reference phải có dạng:

```text
197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@sha256:<64 lowercase hex>
```

Và digest đó phải có:

- Cosign signature;
- issuer chính xác;
- subject/identity chính xác;
- CycloneDX SBOM attestation;
- Trivy evidence;
- source SHA và workflow run mapping.

## 3.2. Signature identity invariant

Chỉ chấp nhận:

```text
issuer:
https://token.actions.githubusercontent.com
```

```text
subject:
https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/.github/workflows/build-push-ecr.yml@refs/heads/main
```

Không chấp nhận:

- wildcard repository;
- wildcard branch;
- pull-request identity;
- workflow khác;
- fork;
- developer keyless identity;
- static key không nằm trong decision record;
- `subjectRegExp: ".*"`;
- bỏ Rekor/Tlog validation mà không có ADR.

## 3.3. SBOM invariant

Mỗi published platform phải có một CycloneDX JSON:

```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "...",
  "metadata": {
    "properties": [
      {
        "name": "techx.platform",
        "value": "linux/amd64"
      },
      {
        "name": "techx.subjectDigest",
        "value": "sha256:..."
      }
    ]
  }
}
```

SBOM phải:

- sinh từ `repository@digest`, không từ mutable tag;
- có file hash SHA-256;
- được attest vào cùng subject digest;
- được verify ngay trong workflow;
- được upload làm evidence;
- truy được bằng helper một lệnh.

## 3.4. External image invariant

Mọi image không thuộc exact first-party repository phải:

- dùng digest;
- trùng khớp tuyệt đối một entry trong allow-list;
- xuất hiện trong authoritative production render;
- có owner và review cadence;
- không có entry dư/stale trong allow-list;
- không được chấp nhận chỉ vì cùng repository.

Ví dụ:

```text
docker.io/library/postgres@sha256:AAA   -> chỉ pass nếu AAA đúng allow-list
docker.io/library/postgres@sha256:BBB   -> fail
postgres:17.6                            -> fail
busybox@sha256:<approved>                -> pass
busybox@sha256:<different>               -> fail
```

## 3.5. Availability invariant

Trong toàn bộ cutover:

- Argo CD app Synced/Healthy;
- Kyverno admission available;
- không có admission timeout bất thường;
- storefront HTTP 200;
- browse/cart/checkout pass;
- checkout SLO không giảm dưới mức đã chấp nhận;
- telemetry vẫn chảy;
- flagd không thay đổi;
- Pod đang chạy không bị evict chỉ vì policy chuyển Enforce.

---

# 4. Target architecture

```text
Source commit on main
        |
        v
Detect changed services
        |
        v
Build linux/amd64 candidate
        |
        v
Trivy HIGH/CRITICAL pre-push gate
        |
        v
Push linux/amd64 + linux/arm64 to immutable ECR
        |
        v
Resolve exact manifest-list digest
        |
        +------------------------------+
        |                              |
        v                              v
Post-push Trivy per platform     Generate CycloneDX per platform
        |                              |
        v                              v
Zero HIGH/CRITICAL gate          Add platform + digest metadata
        |                              |
        +---------------+--------------+
                        |
                        v
             Cosign sign subject digest
                        |
                        v
       Cosign attest CycloneDX predicates
                        |
                        v
 Verify signature + each SBOM attestation
 issuer + exact workflow identity
                        |
                        v
 approved-images.json + signed-images.jsonl
 + sbom-index.json + raw evidence artifacts
                        |
                        v
 Image-bump PR updates values-prod digest
                        |
                        v
 Argo CD reconciliation
                        |
                        v
 Kyverno admission:
   1. external digest allow-list
   2. first-party keyless signature verification
                        |
                        v
               Pod admitted or denied
```

---

# 5. Critical design decisions

## 5.1. Dùng Trivy CycloneDX

Chọn:

```bash
trivy image --format cyclonedx
```

Lý do:

- Trivy đã có sẵn trong workflow;
- không thêm toolchain thứ hai nếu không cần;
- output CycloneDX đúng yêu cầu;
- cùng image reference và auth context;
- dễ giữ cùng version với vulnerability scanner.

Không dùng SBOM sinh từ local candidate làm source of truth. Local candidate chỉ phục vụ pre-push gate. SBOM promotion phải sinh từ exact pushed digest.

## 5.2. Một SBOM cho mỗi platform

Image production là manifest list gồm:

- `linux/amd64`;
- `linux/arm64`.

Hai platform có package khác nhau. Một SBOM không có `--platform` có thể không chứng minh đầy đủ cả hai.

Thiết kế bắt buộc:

```text
<service>-linux-amd64.cdx.json
<service>-linux-arm64.cdx.json
```

Cả hai attestation cùng tham chiếu top-level immutable digest, nhưng predicate chứa property platform.

EKS hiện chạy amd64, tuy nhiên artifact đã publish arm64 thì arm64 cũng phải có SBOM để không tạo blind spot.

## 5.3. SBOM là attestation, không chỉ GitHub artifact

GitHub Actions artifact có retention giới hạn và không nằm cạnh image.

SBOM phải có hai bản:

1. OCI/Cosign attestation gắn với digest — nguồn tra cứu theo digest.
2. GitHub artifact — evidence thuận tiện cho review và audit.

Nếu chỉ upload JSON lên Actions mà không attest, DoD “tra theo digest” chưa đủ mạnh.

## 5.4. `verifyImages` xác minh chữ ký; SBOM được kiểm chứng ở pipeline

PM-127 bắt buộc chữ ký admission Enforce.

Bản đầu của policy nên xác minh:

- image signature;
- issuer;
- workflow identity;
- digest.

Không nên đồng thời bắt admission parse CycloneDX predicate ngay trong PR Enforce đầu tiên nếu syntax/latency chưa được kiểm chứng trên Kyverno 1.13.

SBOM attestation vẫn là release gate bắt buộc:

- thiếu SBOM → workflow fail;
- attestation verify fail → không tạo image-bump PR.

Sau PM-127 có thể thêm một verify-attestation rule riêng khi đã benchmark.

## 5.5. Kyverno dùng Amazon registry helper + IRSA

Policy phải có:

```yaml
imageRegistryCredentials:
  helpers:
    - amazon
```

Kyverno controller phải có AWS identity qua IRSA.

Không đưa ECR password tĩnh vào Secret.

## 5.6. Policy scope ban đầu là `techx-tf3`

Task yêu cầu bảo vệ production image path.

Không mở rộng ngay ra toàn cluster vì:

- kube-system addon image không thuộc allow-list ứng dụng;
- Kyverno tự verify chính nó có nguy cơ deadlock;
- Argo CD và controller image có release cadence khác;
- blast radius quá lớn cho deadline ngắn.

Mở rộng cluster-wide là task riêng sau khi có dynamic inventory cho platform images.

## 5.7. Checkout Rollout hiện dùng `workloadRef`

`checkout-rollout` hiện không chứa Pod template/image; nó tham chiếu Deployment `checkout`.

Do đó:

- verify Deployment/Pod là đủ cho trạng thái hiện tại;
- phải có regression test bảo đảm Rollout không chuyển sang inline `spec.template` mà không cập nhật Kyverno `imageExtractors`;
- nếu sau này Rollout dùng inline template, phải thêm Kyverno custom-resource image extractor.

## 5.8. External allow-list lấy từ render, không lấy từ tài liệu thủ công

Authoritative render phải dùng đúng bốn values file:

```text
phase3 - information/techx-corp-chart/values.yaml
phase3 - information/deploy/values-flagd-sync.yaml
phase3 - information/deploy/values-prod.yaml
phase3 - information/deploy/values-aio-llm.yaml
```

CI phải so sánh tập hợp:

```text
rendered external images == policy allow-list images
```

Không chỉ kiểm `rendered ⊆ allow-list`, vì allow-list dư sẽ giữ quyền chạy image không còn dùng.

## 5.9. Enforce không được làm chung một lần

Cutover độc lập:

1. ECR auth/IRSA.
2. SBOM pipeline.
3. Signed/SBOM inventory backfill.
4. External allow-list Audit.
5. External allow-list Enforce.
6. First-party verifyImages Audit.
7. First-party verifyImages Enforce.

Mỗi bước có rollback commit riêng.

---

# 6. File impact map

## 6.1. Workflow và scripts

### Sửa

```text
.github/workflows/build-push-ecr.yml
.github/workflows/test-image-bump.yml
scripts/ci/requirements-image-bump.txt
scripts/ci/test_workflow_image_bump_contract.py
```

### Thêm

```text
scripts/security/get-sbom-by-digest.sh
scripts/ci/verify-sbom-evidence.py
scripts/ci/render-image-inventory.py
scripts/ci/verify-external-image-allowlist.py
scripts/ci/test_verify_sbom_evidence.py
scripts/ci/test_external_image_allowlist.py
```

Tùy cách backfill:

```text
.github/workflows/backfill-current-sboms.yml
```

Workflow backfill phải temporary hoặc được khóa bằng production environment approval.

## 6.2. Kyverno và GitOps

### Thêm

```text
gitops/policies/kyverno/verify-first-party-signatures.yaml
gitops/policies/kyverno/allow-approved-external-image-digests.yaml
```

### Sửa

```text
gitops/apps/kyverno-app.yaml
infra/modules/eks-platform/kyverno-ecr-verifier.tf
infra/modules/eks-platform/outputs.tf
infra/live/production/main.tf
```

Tên Terraform file có thể thay đổi theo convention hiện tại, nhưng quyền phải nằm trong IaC source of truth.

## 6.3. Tests

### Thêm

```text
tests/kyverno/mandate-10/kyverno-test.yaml
tests/kyverno/mandate-10/resources/...
tests/kyverno/mandate-10/values/...
tests/fixtures/mandate-10/...
```

## 6.4. Docs và evidence

### Thêm

```text
docs/adr/0012-mandate-10-sbom-verify-images.md
docs/evidence/mandate-10/README.md
docs/evidence/mandate-10/external-image-allowlist.yaml
docs/runbooks/sbom-by-digest.md
docs/runbooks/pm-127-enforce-cutover.md
docs/runbooks/pm-127-rollback.md
```

### Cập nhật

```text
docs/security/image-supply-chain-controls.md
docs/evidence/pm-101-image-supply-chain.md
docs/release-notes-v1.md
CLAUDE.md
```

## 6.5. Protected files

Task này không được thay đổi behavior của:

```text
flagd configuration
OpenFeature hooks
Envoy fault-injection routes
HPA
Karpenter NodePool
Argo Rollouts strategy
datastore connection/cutover
public/private ingress boundary
```

CI diff guard nên fail khi PR PM-127 thay đổi các khu vực này ngoài lý do tài liệu.

---

# 7. SBOM workflow specification

## 7.1. Vị trí

Đặt sau:

- push;
- resolve digest;
- post-push Trivy per-platform gate;
- Cosign installer.

Nó phải chạy trước:

- upload final release evidence;
- aggregate approved manifest;
- image-bump PR.

Workflow không được tạo image-bump PR khi bất kỳ SBOM hoặc attestation nào fail.

## 7.2. Directory contract

```text
release-evidence/
├── cosign/
│   └── <service>.json
├── sbom/
│   ├── <service>-linux-amd64.cdx.json
│   └── <service>-linux-arm64.cdx.json
├── attestations/
│   ├── <service>-linux-amd64.verify.jsonl
│   └── <service>-linux-arm64.verify.jsonl
├── signed-images.jsonl
└── sbom-index.json
```

## 7.3. Generation algorithm

Pseudo-shell:

```bash
service_count="$(jq '.services | length' approved-images.json)"

for ((index = 0; index < service_count; index++)); do
  service="$(jq -r ".services[$index].name" approved-images.json)"
  digest="$(jq -r ".services[$index].digest" approved-images.json)"
  image="${ECR_REGISTRY}/${ECR_REPOSITORY}@${digest}"

  for platform in ${BUILD_PLATFORMS//,/ }; do
    safe_platform="${platform//\//-}"
    sbom="release-evidence/sbom/${service}-${safe_platform}.cdx.json"
    tmp="${sbom}.tmp"

    trivy image \
      --platform "$platform" \
      --format cyclonedx \
      --output "$tmp" \
      --no-progress \
      "$image"

    jq \
      --arg platform "$platform" \
      --arg digest "$digest" \
      '
        .metadata.properties =
          ((.metadata.properties // []) + [
            {"name":"techx.platform","value":$platform},
            {"name":"techx.subjectDigest","value":$digest}
          ])
      ' "$tmp" > "$sbom"

    rm -f "$tmp"

    jq -e '
      .bomFormat == "CycloneDX" and
      (.specVersion | type == "string") and
      (.metadata | type == "object")
    ' "$sbom"

    sbom_sha256="$(sha256sum "$sbom" | awk "{print \$1}")"

    cosign attest --yes \
      --type cyclonedx \
      --predicate "$sbom" \
      "$image"

    cosign verify-attestation \
      --type cyclonedx \
      --certificate-oidc-issuer \
        https://token.actions.githubusercontent.com \
      --certificate-identity "$EXPECTED_IDENTITY" \
      "$image" \
      > "release-evidence/attestations/${service}-${safe_platform}.verify.jsonl"

    python3 scripts/ci/verify-sbom-evidence.py \
      --image "$image" \
      --platform "$platform" \
      --sbom "$sbom" \
      --attestation \
        "release-evidence/attestations/${service}-${safe_platform}.verify.jsonl" \
      --expected-issuer \
        https://token.actions.githubusercontent.com \
      --expected-identity "$EXPECTED_IDENTITY" \
      --expected-sbom-sha256 "$sbom_sha256"
  done
done
```

Lệnh chính xác phải được actionlint và chạy thử trên một digest test trước khi merge.

## 7.4. Evidence index schema

`sbom-index.json`:

```json
{
  "schemaVersion": 1,
  "registry": "197826770971.dkr.ecr.ap-southeast-1.amazonaws.com",
  "repository": "techx-corp",
  "sourceSha": "<40 hex>",
  "workflowRunId": "<id>",
  "workflowRunAttempt": "<attempt>",
  "issuer": "https://token.actions.githubusercontent.com",
  "identity": "https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/.github/workflows/build-push-ecr.yml@refs/heads/main",
  "services": [
    {
      "name": "checkout",
      "digest": "sha256:...",
      "image": ".../techx-corp@sha256:...",
      "platforms": [
        {
          "platform": "linux/amd64",
          "sbomPath": "sbom/checkout-linux-amd64.cdx.json",
          "sbomSha256": "<64 hex>",
          "attestationVerifyPath": "attestations/checkout-linux-amd64.verify.jsonl"
        },
        {
          "platform": "linux/arm64",
          "sbomPath": "sbom/checkout-linux-arm64.cdx.json",
          "sbomSha256": "<64 hex>",
          "attestationVerifyPath": "attestations/checkout-linux-arm64.verify.jsonl"
        }
      ]
    }
  ]
}
```

## 7.5. Workflow fail-closed rules

Workflow phải fail khi:

- Trivy không tạo file;
- CycloneDX JSON invalid;
- `bomFormat` không đúng;
- digest property không trùng subject;
- thiếu platform;
- cùng platform bị duplicate;
- file hash không khớp;
- `cosign attest` fail;
- `verify-attestation` fail;
- issuer khác;
- identity khác;
- service set không đúng matrix;
- thiếu evidence file;
- SBOM generated từ tag thay vì digest;
- artifact upload không có file;
- aggregate thiếu một service;
- aggregate thiếu một platform.

Không dùng:

```yaml
continue-on-error: true
```

cho generation, attestation hoặc verify.

## 7.6. One-command SBOM lookup

Script:

```text
scripts/security/get-sbom-by-digest.sh
```

Usage:

```bash
./scripts/security/get-sbom-by-digest.sh \
  sha256:<digest> \
  linux/amd64
```

Script phải:

1. validate digest regex;
2. xác định full ECR image;
3. dùng current AWS profile/ECR helper;
4. verify attestation với exact issuer/identity;
5. decode in-toto payload;
6. chọn predicate có `techx.platform` phù hợp;
7. validate subject digest;
8. in CycloneDX predicate ra stdout;
9. exit non-zero khi thiếu hoặc ambiguous.

Ví dụ lưu file:

```bash
./scripts/security/get-sbom-by-digest.sh \
  sha256:<digest> linux/amd64 \
  > /tmp/sbom.cdx.json
```

Không được chỉ chạy `cosign download attestation` mà bỏ verify.

---

# 8. Existing image SBOM backfill

## 8.1. Vì sao cần backfill

Khi bật `verifyImages`, running digest cũ cần có signature hợp lệ. Khi task yêu cầu mọi self-built image có SBOM, running digest cũ cũng phải có SBOM.

Không nhất thiết rebuild toàn bộ hệ.

## 8.2. Backfill flow

1. Render production đúng bốn values file.
2. Extract exact first-party digests.
3. Với từng digest:
   - verify existing Cosign signature exact identity;
   - verify Trivy evidence hoặc approved manifest hiện có;
   - generate CycloneDX per platform;
   - attest trong một workflow chạy từ `main`;
   - verify attestation;
   - record evidence.
4. Digest thiếu signature hoặc provenance:
   - không tự “hợp thức hóa” bằng attest;
   - rebuild đúng service qua scoped release pipeline;
   - promote digest mới bằng image-bump PR.

## 8.3. Backfill permissions

Backfill workflow:

- chỉ `workflow_dispatch`;
- chỉ chạy từ `main`;
- dùng GitHub environment `production`;
- cần reviewer approval;
- `id-token: write`;
- không update values;
- không deploy;
- không push image mới;
- chỉ push attestation cho approved existing digest.

## 8.4. Stop condition

Dừng backfill khi:

- signature hiện tại không đúng workflow identity;
- digest không nằm trong production render;
- thiếu scan evidence;
- ECR digest không tồn tại;
- subject media type bất thường;
- service mapping ambiguous.

---

# 9. Kyverno ECR verifier IRSA

## 9.1. Service accounts

Trước khi viết trust policy, agent phải render chart và xác minh tên chính xác:

```bash
helm template kyverno kyverno/kyverno \
  --version 3.3.4 \
  --namespace kyverno \
  -f <current-values> \
  > /tmp/kyverno-rendered.yaml

yq '
  select(.kind == "ServiceAccount")
  | [.metadata.name, .metadata.namespace]
' /tmp/kyverno-rendered.yaml
```

Expected thường là:

```text
kyverno-admission-controller
kyverno-background-controller
```

Không hardcode nếu render cho kết quả khác.

## 9.2. IAM policy

Least-privilege baseline:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GetECRAuthorizationToken",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ReadTechXECRSubjectAndReferrers",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer",
        "ecr:DescribeImages",
        "ecr:ListImages"
      ],
      "Resource": "arn:aws:ecr:ap-southeast-1:197826770971:repository/techx-corp"
    }
  ]
}
```

Không cấp:

```text
ecr:PutImage
ecr:InitiateLayerUpload
ecr:UploadLayerPart
ecr:CompleteLayerUpload
ecr:BatchDeleteImage
ecr:DeleteRepository
```

## 9.3. Trust policy

Trust chỉ exact service accounts trong namespace `kyverno`.

Có thể dùng:

- một role cho admission + background;
- hai role tách biệt.

Hai role là least-privilege rõ hơn nhưng thêm IaC. Một shared read-only role là chấp nhận được nếu ADR ghi rõ.

## 9.4. Helm values

Conceptual values:

```yaml
admissionController:
  serviceAccount:
    annotations:
      eks.amazonaws.com/role-arn: arn:aws:iam::197826770971:role/techx-corp-tf3-kyverno-ecr-verifier

backgroundController:
  serviceAccount:
    annotations:
      eks.amazonaws.com/role-arn: arn:aws:iam::197826770971:role/techx-corp-tf3-kyverno-ecr-verifier
```

Phải verify path bằng `helm template`; không đoán chart values.

## 9.5. IRSA acceptance test

```bash
kubectl -n kyverno get sa \
  kyverno-admission-controller \
  kyverno-background-controller \
  -o yaml

kubectl -n kyverno get deploy \
  kyverno-admission-controller \
  kyverno-background-controller \
  -o json \
  | jq '
      .items[]
      | {
          name: .metadata.name,
          serviceAccountName: .spec.template.spec.serviceAccountName,
          env: .spec.template.spec.containers[].env
        }
    '
```

Kiểm tra log:

```bash
kubectl -n kyverno logs deploy/kyverno-admission-controller \
  --since=15m \
  | grep -Ei 'ecr|registry|credential|signature|attestation|denied|error'
```

Good signed-image server dry-run phải pass. Nếu fail do auth, không được chuyển Enforce.

---

# 10. First-party `verifyImages` policy

## 10.1. File

```text
gitops/policies/kyverno/verify-first-party-signatures.yaml
```

## 10.2. Initial Audit policy skeleton

Policy phải được kiểm chứng với Kyverno CLI/version đang chạy trước khi commit:

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: verify-first-party-signatures
  annotations:
    policies.kyverno.io/title: Verify TechX first-party image signatures
    policies.kyverno.io/category: Mandate 10 Secure Delivery
    policies.kyverno.io/severity: high
spec:
  validationFailureAction: Audit
  background: true
  webhookTimeoutSeconds: 30
  rules:
    - name: verify-techx-main-workflow-signature
      match:
        any:
          - resources:
              kinds:
                - Pod
              namespaces:
                - techx-tf3
              operations:
                - CREATE
                - UPDATE
      verifyImages:
        - imageReferences:
            - "197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@sha256:*"
          required: true
          mutateDigest: false
          verifyDigest: true
          imageRegistryCredentials:
            helpers:
              - amazon
          attestors:
            - count: 1
              entries:
                - keyless:
                    subject: >-
                      https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/.github/workflows/build-push-ecr.yml@refs/heads/main
                    issuer: >-
                      https://token.actions.githubusercontent.com
                    rekor:
                      url: https://rekor.sigstore.dev
```

Notes:

- Exact syntax phải được xác nhận bằng Kyverno 1.13.2/CLI tương ứng.
- Không dùng regex identity rộng nếu exact subject hoạt động.
- `required: true` để missing signature fail.
- `mutateDigest: false` vì digest đã bắt buộc bởi policy Mandate 5.
- `verifyDigest: true` chống tag/digest mismatch.
- `background: true` chỉ sau khi background controller có ECR auth.
- Không exclude service first-party.

## 10.3. Controller coverage

Kyverno phải bảo vệ:

- Pod;
- Deployment;
- StatefulSet;
- DaemonSet;
- ReplicaSet;
- Job;
- CronJob;
- ReplicationController.

Kiểm tra generated/autogen rules:

```bash
kubectl get clusterpolicy verify-first-party-signatures -o yaml
```

Nếu version hiện tại không autogen `verifyImages` đúng:

- dùng explicit generated rules;
- hoặc nâng Kyverno có kiểm soát;
- không chấp nhận “Pod sẽ bị block sau” làm final UX nếu Deployment vẫn được tạo và Argo báo Synced nhưng không có Pod.

## 10.4. Rollout coverage

Current checkout Rollout dùng `workloadRef`, nên Deployment `checkout` vẫn là source image.

CI phải assert:

```text
Rollout checkout có workloadRef
Rollout checkout không có spec.template
```

Nếu assertion fail, task phải dừng và thêm `imageExtractors`.

---

# 11. External digest allow-list policy

## 11.1. File

```text
gitops/policies/kyverno/allow-approved-external-image-digests.yaml
```

## 11.2. Source of truth

Human-reviewed inventory:

```text
docs/evidence/mandate-10/external-image-allowlist.yaml
```

Example schema:

```yaml
schemaVersion: 1
namespace: techx-tf3
firstPartyRepository: 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp
images:
  - image: docker.io/library/postgres@sha256:...
    component: postgresql
    owner: TF3 Platform
    source: helm-render
    reviewCadence: quarterly
    lastReviewed: 2026-07-20
  - image: busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662
    component: wait-init-containers
    owner: TF3 Platform
    source: helm-render
    reviewCadence: monthly
    lastReviewed: 2026-07-20
```

Policy YAML được generate hoặc sync từ exact list nhưng phải review được trong Git.

## 11.3. Policy behavior

For each:

- `containers`;
- `initContainers`;
- `ephemeralContainers`;

Logic:

1. Nếu image là exact first-party ECR digest:
   - external policy không deny;
   - verifyImages policy chịu trách nhiệm.
2. Nếu không phải first-party:
   - image phải đúng một exact allow-list entry.
3. Tag hoặc digest khác:
   - deny.

## 11.4. Audit skeleton

Conceptual policy:

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: allow-approved-external-image-digests
spec:
  validationFailureAction: Audit
  background: true
  rules:
    - name: require-approved-external-image-digest
      match:
        any:
          - resources:
              kinds:
                - Pod
              namespaces:
                - techx-tf3
              operations:
                - CREATE
                - UPDATE
      validate:
        message: >-
          External images must match an explicitly approved digest from
          docs/evidence/mandate-10/external-image-allowlist.yaml.
        foreach:
          - list: "request.object.spec.containers"
            preconditions:
              all:
                - key: "{{ element.image }}"
                  operator: NotMatches
                  value: "^197826770971\\.dkr\\.ecr\\.ap-southeast-1\\.amazonaws\\.com/techx-corp@sha256:[0-9a-f]{64}$"
            deny:
              conditions:
                all:
                  - key: "{{ element.image }}"
                    operator: AnyNotIn
                    value:
                      - "<exact-rendered-external-image-1>"
                      - "<exact-rendered-external-image-2>"
          - list: "request.object.spec.initContainers || `[]`"
            ...
          - list: "request.object.spec.ephemeralContainers || `[]`"
            ...
```

Exact operators/JMESPath phải được xác nhận bằng Kyverno CLI. Có thể generate one deny condition per list nếu `AnyNotIn` semantics không ổn.

## 11.5. Exact-set CI gate

```bash
helm dependency build "phase3 - information/techx-corp-chart"

helm template techx-corp \
  "phase3 - information/techx-corp-chart" \
  --namespace techx-tf3 \
  -f "phase3 - information/techx-corp-chart/values.yaml" \
  -f "phase3 - information/deploy/values-flagd-sync.yaml" \
  -f "phase3 - information/deploy/values-prod.yaml" \
  -f "phase3 - information/deploy/values-aio-llm.yaml" \
  > /tmp/techx-prod.yaml

python3 scripts/ci/render-image-inventory.py \
  --rendered /tmp/techx-prod.yaml \
  --first-party-repository \
    197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp \
  --output /tmp/rendered-images.json

python3 scripts/ci/verify-external-image-allowlist.py \
  --rendered-inventory /tmp/rendered-images.json \
  --allowlist docs/evidence/mandate-10/external-image-allowlist.yaml \
  --policy gitops/policies/kyverno/allow-approved-external-image-digests.yaml
```

Script phải fail khi:

- rendered external image thiếu trong allow-list;
- allow-list có entry không còn render;
- policy và register lệch nhau;
- duplicate;
- image không có digest;
- mutable tag;
- first-party image bị đưa nhầm vào external list.

---

# 12. Pull-request execution plan

## PR 0 — Inventory, ADR, test harness

### Thay đổi

- ADR 0012 draft.
- authoritative render image inventory script.
- external allow-list register.
- SBOM evidence verifier unit tests.
- Kyverno Mandate 10 test fixtures.
- chưa thêm Enforce.
- không thay cluster auth.

### Exit gate

- render production đúng bốn values file;
- inventory chứa đủ normal/init/sidecar image;
- exact external set được review;
- current first-party digest set được ghi nhận;
- tests fail đúng với fixture xấu.

---

## PR 1 — SBOM generation và attestation

### Thay đổi

- workflow SBOM per platform;
- Cosign attest;
- verify-attestation;
- sbom-index;
- helper lookup;
- workflow contract tests;
- docs.

### Exit gate

Một scoped service run trên `main` phải chứng minh:

- image build/scan/push/sign pass;
- hai CycloneDX SBOM tồn tại;
- hai attestation verify pass;
- helper lấy được SBOM theo digest bằng một lệnh;
- image-bump PR chỉ mở sau khi SBOM gate pass.

### Rollback

Revert PR 1. Existing signature và deployed digest không bị ảnh hưởng.

---

## PR 2 — Kyverno ECR read IRSA

### Thay đổi

- Terraform role/policy/trust.
- Kyverno admission/background SA annotations.
- không thêm verifyImages policy hoặc vẫn để policy chưa sync.

### Exit gate

- Terraform plan chỉ thêm intended IAM;
- Argo/Kyverno rollout healthy;
- IRSA env/annotation đúng;
- Kyverno có thể read signature của một known-good digest;
- không có ECR write permission.

### Rollback

Revert SA annotation trước; giữ IAM role không gây runtime effect. Sau đó cleanup IaC bằng reviewed apply.

---

## PR 3 — Backfill current signed inventory

### Thay đổi

- controlled backfill workflow hoặc runbook/script;
- evidence only;
- không thay production digest.

### Exit gate

Mọi live first-party digest:

- tồn tại;
- signature đúng identity;
- có CycloneDX SBOM cho published platform;
- attestation verify được;
- mapping source/workflow/scan/sign/SBOM đầy đủ.

Digest không đạt phải rebuild scoped trước khi qua gate.

---

## PR 4 — Hai policy ở Audit

### Thay đổi

- add `verify-first-party-signatures.yaml` Audit;
- add `allow-approved-external-image-digests.yaml` Audit;
- Kyverno tests;
- PolicyReport reconciliation.

### Exit gate

- policy Ready=True;
- không có registry auth error;
- zero unexplained live failure;
- exact approved external set clean;
- all live first-party signatures verify;
- synthetic bad manifests tạo expected Audit result;
- no app rollout.

---

## PR 5 — External allow-list Enforce

### Thay đổi

Chỉ:

```yaml
validationFailureAction: Audit
```

→

```yaml
validationFailureAction: Enforce
```

cho external policy.

### Exit gate

- exact approved external Pod pass;
- same repository/different digest fail;
- BusyBox approved digest pass;
- new external image fail;
- production healthy;
- PolicyReport clean.

### Rollback

Git revert PR 5.

---

## PR 6 — First-party verifyImages Enforce

### Thay đổi

Chỉ chuyển first-party signature policy sang Enforce.

### Exit gate

- known-good signed digest pass;
- unsigned digest fail;
- wrong identity fail;
- standard image-bump rollout pass;
- Kyverno admission latency/error healthy;
- production smoke pass;
- PolicyReport clean.

### Rollback

Git revert PR 6. Không `kubectl edit` policy.

---

## PR 7 — Final evidence và closure

### Thay đổi

- final ADR;
- final evidence index;
- unsigned-image rejection output/video link;
- live provenance sample;
- DoD checklist;
- residual risk/action pin note.

### Exit gate

Mentor có thể tự:

1. lấy digest của một Pod;
2. verify signature;
3. lấy SBOM;
4. tìm source SHA/PR/scan;
5. thử unsigned image;
6. thấy admission deny;
7. kiểm tra policy Enforce/Ready.

---

# 13. Detailed execution list

## Phase A — Preflight

```bash
git switch main
git pull --ff-only
git status --short
git rev-parse HEAD

export AWS_PROFILE=techx-new
aws sts get-caller-identity

kubectl get clusterpolicy
kubectl -n kyverno get deploy,pod,sa
kubectl -n argocd get application
kubectl -n techx-tf3 get pods -o wide
```

Capture:

```bash
mkdir -p /tmp/mandate10-before

kubectl get clusterpolicy -o yaml \
  > /tmp/mandate10-before/clusterpolicies.yaml

kubectl -n techx-tf3 get pods -o json \
  > /tmp/mandate10-before/pods.json

kubectl get policyreport -A -o yaml \
  > /tmp/mandate10-before/policyreports.yaml
```

Stop khi:

- active incident;
- Argo Degraded;
- Kyverno unavailable;
- checkout SLO đang fail;
- cluster access profile sai account;
- main dirty hoặc stale.

---

## Phase B — Render production image inventory

Run authoritative render.

Extract:

- controller kind;
- namespace;
- workload;
- container type;
- container name;
- full image;
- first-party/external;
- digest;
- source Helm chart.

Review every entry.

Required output:

```json
{
  "firstParty": [],
  "external": [],
  "missingDigest": [],
  "duplicates": []
}
```

Gate:

```text
missingDigest == []
duplicates == []
```

---

## Phase C — Validate current signatures

For each first-party live digest:

```bash
cosign verify \
  --certificate-oidc-issuer \
    https://token.actions.githubusercontent.com \
  --certificate-identity \
    https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/.github/workflows/build-push-ecr.yml@refs/heads/main \
  "197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@sha256:<digest>"
```

Classify:

- signed-valid;
- unsigned;
- wrong identity;
- registry/auth failure;
- digest missing.

Do not proceed to Enforce until no live digest is unresolved.

---

## Phase D — Implement and run SBOM path

Use one changed low-risk service first, for example `image-provider` or another independently smoke-testable target.

Run scoped workflow on `main`.

Verify:

```bash
DIGEST=sha256:...

./scripts/security/get-sbom-by-digest.sh \
  "$DIGEST" linux/amd64 \
  | jq -e '.bomFormat == "CycloneDX"'

./scripts/security/get-sbom-by-digest.sh \
  "$DIGEST" linux/arm64 \
  | jq -e '.bomFormat == "CycloneDX"'
```

Check evidence artifact exact files.

---

## Phase E — Apply IRSA

Terraform:

```bash
terraform -chdir=infra/live/production fmt -check
terraform -chdir=infra/live/production init
terraform -chdir=infra/live/production validate
terraform -chdir=infra/live/production plan \
  -out=/tmp/mandate10-irsa.tfplan
terraform show -no-color /tmp/mandate10-irsa.tfplan
```

Review:

- no unrelated resource replacement;
- no EKS replacement;
- no existing role deletion;
- no ECR mutation;
- policy read-only.

Apply via normal protected workflow.

Wait:

```bash
kubectl -n argocd get application kyverno -w
kubectl -n kyverno rollout status \
  deploy/kyverno-admission-controller --timeout=10m
kubectl -n kyverno rollout status \
  deploy/kyverno-background-controller --timeout=10m
```

---

## Phase F — Audit policy rollout

After Argo sync:

```bash
kubectl get clusterpolicy \
  verify-first-party-signatures \
  allow-approved-external-image-digests \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.validationFailureAction}{" "}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}'
```

Expected:

```text
verify-first-party-signatures Audit True
allow-approved-external-image-digests Audit True
```

Observe at least one complete reconciliation window.

Export reports and reconcile only these policy names.

Do not use raw total `fail` count for all historic reports.

---

## Phase G — Enforce external policy

Run all good/bad server-side tests.

Merge isolated Enforce PR.

Immediately verify:

```bash
kubectl get clusterpolicy \
  allow-approved-external-image-digests \
  -o jsonpath='{.spec.validationFailureAction} {.status.conditions[?(@.type=="Ready")].status}{"\n"}'
```

Expected:

```text
Enforce True
```

Run runtime smoke.

---

## Phase H — Enforce signature policy

Run good signed image test before merge.

Merge isolated Enforce PR.

Expected:

```text
verify-first-party-signatures Enforce True
```

Run:

- signed digest pass;
- unsigned digest deny;
- wrong identity deny;
- normal image-bump deployment pass;
- storefront/cart/checkout pass.

---

# 14. Real unsigned-image rejection demo

## 14.1. Build outside release pipeline

Use a harmless minimal image.

Example Dockerfile:

```dockerfile
FROM public.ecr.aws/docker/library/busybox@sha256:<approved-base-digest>
CMD ["sh", "-c", "sleep 3600"]
```

Build and push manually under a unique immutable tag:

```bash
TAG="mandate10-unsigned-demo-$(date +%s)"

aws ecr get-login-password --region ap-southeast-1 \
  | docker login \
      --username AWS \
      --password-stdin \
      197826770971.dkr.ecr.ap-southeast-1.amazonaws.com

docker build -t \
  "197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp:${TAG}" \
  /tmp/mandate10-unsigned-demo

docker push \
  "197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp:${TAG}"

DIGEST="$(
  aws ecr describe-images \
    --repository-name techx-corp \
    --image-ids imageTag="$TAG" \
    --region ap-southeast-1 \
    --query 'imageDetails[0].imageDigest' \
    --output text
)"
```

Do not run `cosign sign`.

Confirm unsigned:

```bash
cosign verify \
  --certificate-oidc-issuer \
    https://token.actions.githubusercontent.com \
  --certificate-identity \
    https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/.github/workflows/build-push-ecr.yml@refs/heads/main \
  "197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@${DIGEST}"
```

Expected: verification fail.

## 14.2. Apply real violating manifest

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: mandate10-unsigned-demo
  namespace: techx-tf3
  labels:
    app.kubernetes.io/name: mandate10-unsigned-demo
spec:
  restartPolicy: Never
  securityContext:
    runAsNonRoot: true
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com/techx-corp@sha256:<UNSIGNED_DIGEST>
      command: ["sh", "-c", "sleep 3600"]
      securityContext:
        runAsUser: 65534
        runAsGroup: 65534
        runAsNonRoot: true
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
      resources:
        requests:
          cpu: 5m
          memory: 8Mi
        limits:
          cpu: 50m
          memory: 32Mi
```

Run actual apply, not client-side validation:

```bash
set +e
kubectl apply \
  -f docs/evidence/mandate-10/rejection-demo/unsigned-first-party.yaml \
  > docs/evidence/mandate-10/final/unsigned-rejection.txt 2>&1
status=$?
set -e

test "$status" -ne 0
kubectl -n techx-tf3 get pod mandate10-unsigned-demo \
  && exit 1 || true
```

Evidence must show:

- webhook denial;
- policy name;
- rule name;
- signature verification reason;
- Pod không tồn tại.

## 14.3. Cleanup

After evidence:

```bash
aws ecr batch-delete-image \
  --repository-name techx-corp \
  --image-ids imageDigest="$DIGEST" \
  --region ap-southeast-1
```

Only delete exact demo digest after confirming it is not referenced by production.

---

# 15. Test matrix

## 15.1. Workflow/SBOM tests

| ID | Test | Expected |
|---|---|---|
| SBOM-001 | Workflow YAML parses | Pass |
| SBOM-002 | Actionlint | Pass |
| SBOM-003 | SBOM runs only after digest resolution | Pass |
| SBOM-004 | SBOM image reference contains `@sha256` | Pass |
| SBOM-005 | SBOM never scans mutable tag | Pass |
| SBOM-006 | CycloneDX format selected | Pass |
| SBOM-007 | `bomFormat` equals `CycloneDX` | Pass |
| SBOM-008 | `specVersion` exists | Pass |
| SBOM-009 | metadata exists | Pass |
| SBOM-010 | subject digest metadata matches ECR digest | Pass |
| SBOM-011 | amd64 property exists | Pass |
| SBOM-012 | arm64 property exists | Pass |
| SBOM-013 | one SBOM per expected platform | Pass |
| SBOM-014 | duplicate platform evidence | Workflow fail |
| SBOM-015 | missing platform evidence | Workflow fail |
| SBOM-016 | empty SBOM file | Workflow fail |
| SBOM-017 | malformed JSON | Workflow fail |
| SBOM-018 | wrong `bomFormat` | Workflow fail |
| SBOM-019 | SBOM hash recorded | Pass |
| SBOM-020 | recorded hash differs from file | Workflow fail |
| SBOM-021 | `cosign attest --type cyclonedx` present | Pass |
| SBOM-022 | attest references exact digest | Pass |
| SBOM-023 | attestation verification uses exact issuer | Pass |
| SBOM-024 | attestation verification uses exact identity | Pass |
| SBOM-025 | wrong issuer fixture | Fail |
| SBOM-026 | wrong identity fixture | Fail |
| SBOM-027 | tampered local SBOM after attestation | Fail comparison |
| SBOM-028 | attestation subject digest differs | Fail |
| SBOM-029 | SBOM artifact upload missing files | Fail |
| SBOM-030 | `continue-on-error` on required SBOM step | Static test fail |
| SBOM-031 | scoped build one service | Evidence only that service |
| SBOM-032 | full build 20 services | Exactly 40 platform SBOMs |
| SBOM-033 | rerun-failed-jobs reuses stable digest/evidence safely | Pass |
| SBOM-034 | full workflow rerun hits ECR immutability | Fail closed, no overwrite |
| SBOM-035 | aggregate service set mismatch | Fail |
| SBOM-036 | aggregate platform set mismatch | Fail |
| SBOM-037 | image-bump job starts with missing SBOM | Must not start |
| SBOM-038 | image-bump job starts with failed attestation verify | Must not start |
| SBOM-039 | signed-images mapping includes SBOM paths | Pass |
| SBOM-040 | sbom-index schema validation | Pass |

## 15.2. SBOM lookup helper tests

| ID | Test | Expected |
|---|---|---|
| LOOK-001 | Valid digest + amd64 | CycloneDX JSON |
| LOOK-002 | Valid digest + arm64 | CycloneDX JSON |
| LOOK-003 | Digest missing `sha256:` | Exit non-zero |
| LOOK-004 | Digest wrong length | Exit non-zero |
| LOOK-005 | Uppercase digest | Exit non-zero |
| LOOK-006 | Unsupported platform | Exit non-zero |
| LOOK-007 | Missing attestation | Exit non-zero |
| LOOK-008 | Attestation wrong identity | Exit non-zero |
| LOOK-009 | Attestation wrong issuer | Exit non-zero |
| LOOK-010 | Multiple matching attestations | Exit ambiguous unless identical |
| LOOK-011 | Subject digest mismatch | Exit non-zero |
| LOOK-012 | Platform property mismatch | Exit non-zero |
| LOOK-013 | AWS/ECR auth unavailable | Clear non-zero error |
| LOOK-014 | Output piped to `jq` | Valid JSON only on stdout |
| LOOK-015 | Diagnostics | stderr, not stdout |

## 15.3. IRSA tests

| ID | Test | Expected |
|---|---|---|
| IAM-001 | Terraform fmt | Pass |
| IAM-002 | Terraform validate | Pass |
| IAM-003 | Plan contains only intended IAM/SA-related changes | Pass |
| IAM-004 | Trust subject exact admission SA | Pass |
| IAM-005 | Trust subject exact background SA | Pass |
| IAM-006 | Wrong namespace SA cannot assume role | Denied |
| IAM-007 | Role can GetAuthorizationToken | Pass |
| IAM-008 | Role can BatchGetImage for techx-corp | Pass |
| IAM-009 | Role cannot PutImage | Denied |
| IAM-010 | Role cannot delete image | Denied |
| IAM-011 | Role cannot read unrelated repository when scoped | Denied |
| IAM-012 | Kyverno Pod uses expected service account | Pass |
| IAM-013 | Kyverno Pod receives web identity env | Pass |
| IAM-014 | Signed image verify from admission | Pass |
| IAM-015 | Background verification creates report without auth error | Pass |
| IAM-016 | Controller restart obtains credentials again | Pass |

## 15.4. First-party signature policy unit tests

| ID | Image condition | Expected |
|---|---|---|
| SIG-001 | Signed exact workflow identity | Pass |
| SIG-002 | Unsigned first-party digest | Fail |
| SIG-003 | Signed by wrong workflow | Fail |
| SIG-004 | Signed by PR ref identity | Fail |
| SIG-005 | Signed by wrong branch | Fail |
| SIG-006 | Signed by wrong repository | Fail |
| SIG-007 | Wrong issuer | Fail |
| SIG-008 | Malformed digest | Fail digest policy |
| SIG-009 | First-party tag only | Fail existing digest policy |
| SIG-010 | Signature for different digest | Fail |
| SIG-011 | One valid signature plus unrelated signature | Pass only when valid attestor count met |
| SIG-012 | Expired/invalid certificate chain | Fail |
| SIG-013 | Rekor proof missing when required | Fail |
| SIG-014 | Registry auth error | Fail with auth diagnostic, not treated unsigned |
| SIG-015 | Ordinary container valid | Pass |
| SIG-016 | Ordinary container unsigned | Fail |
| SIG-017 | Second container unsigned | Entire Pod fail |
| SIG-018 | Init container first-party signed | Pass |
| SIG-019 | Init container first-party unsigned | Fail |
| SIG-020 | Ephemeral first-party unsigned | Fail subresource |
| SIG-021 | External image | Not evaluated by signature policy |
| SIG-022 | Pod outside `techx-tf3` | Not evaluated in initial scope |
| SIG-023 | Deployment signed | Pass/autogen |
| SIG-024 | Deployment unsigned | Fail/autogen |
| SIG-025 | StatefulSet unsigned | Fail |
| SIG-026 | DaemonSet unsigned | Fail |
| SIG-027 | Job unsigned | Fail |
| SIG-028 | CronJob unsigned | Fail |
| SIG-029 | ReplicaSet unsigned | Fail |
| SIG-030 | ReplicationController unsigned | Fail |
| SIG-031 | Checkout Rollout still uses workloadRef | Regression pass |
| SIG-032 | Rollout gains inline template without extractor | Static test fail |
| SIG-033 | Policy has wildcard subject | Static security test fail |
| SIG-034 | Policy has `ignoreTlog` | Static security review fail |
| SIG-035 | Policy `required` false | Static test fail |
| SIG-036 | Policy `verifyDigest` false | Static test fail |
| SIG-037 | Policy uses registry helper amazon | Pass |
| SIG-038 | Policy Ready condition | True |
| SIG-039 | Audit mode does not deny but reports bad digest | Pass expected Audit behavior |
| SIG-040 | Enforce mode rejects same bad digest | Pass expected Enforce behavior |

## 15.5. External allow-list tests

| ID | Condition | Expected |
|---|---|---|
| EXT-001 | Every exact rendered external image | Pass |
| EXT-002 | PostgreSQL same repo/different digest | Fail |
| EXT-003 | PostgreSQL tag | Fail |
| EXT-004 | BusyBox approved digest | Pass |
| EXT-005 | BusyBox different digest | Fail |
| EXT-006 | New Docker Hub image | Fail |
| EXT-007 | New GHCR image | Fail |
| EXT-008 | Quay image not listed | Fail |
| EXT-009 | First-party exact digest | Bypass external rule |
| EXT-010 | First-party tag | Existing digest policy fail |
| EXT-011 | External init container exact digest | Pass |
| EXT-012 | External init container new digest | Fail |
| EXT-013 | External sidecar exact digest | Pass |
| EXT-014 | External second container unapproved | Entire Pod fail |
| EXT-015 | Ephemeral external approved | Pass |
| EXT-016 | Ephemeral external unapproved | Fail |
| EXT-017 | Allow-list duplicate | CI fail |
| EXT-018 | Allow-list mutable tag | CI fail |
| EXT-019 | Allow-list malformed digest | CI fail |
| EXT-020 | Rendered image missing allow-list entry | CI fail |
| EXT-021 | Allow-list stale entry not rendered | CI fail |
| EXT-022 | Policy list differs from register | CI fail |
| EXT-023 | First-party image accidentally in external list | CI fail |
| EXT-024 | Missing owner | CI fail |
| EXT-025 | Missing review cadence | CI fail |
| EXT-026 | Review date expired | CI warning/fail by policy |
| EXT-027 | Pod outside namespace | Not evaluated |
| EXT-028 | Deployment unapproved external | Fail/autogen |
| EXT-029 | StatefulSet unapproved external | Fail |
| EXT-030 | CronJob unapproved external | Fail |

## 15.6. Audit-to-Enforce tests

| ID | Test | Expected |
|---|---|---|
| CUT-001 | Both policies initially Audit | Pass |
| CUT-002 | Both Ready=True | Pass |
| CUT-003 | Good live first-party report | Pass |
| CUT-004 | Good live external report | Pass |
| CUT-005 | No registry auth errors | Pass |
| CUT-006 | Zero unexplained verifyImages failures | Pass |
| CUT-007 | Zero unexplained external failures | Pass |
| CUT-008 | External policy switched alone | Enforce True |
| CUT-009 | Signature policy remains Audit during EXT cutover | Pass |
| CUT-010 | External rejection test | Denied |
| CUT-011 | Runtime healthy after EXT cutover | Pass |
| CUT-012 | Signature policy switched alone | Enforce True |
| CUT-013 | Unsigned rejection test | Denied |
| CUT-014 | Good signed admission test | Admitted |
| CUT-015 | Standard image-bump rollout | Healthy |
| CUT-016 | Rollback revert available | Pass |
| CUT-017 | No imperative policy mutation | Pass |
| CUT-018 | Argo reconciles exact Git state | Pass |

## 15.7. Live runtime tests

| ID | Test | Expected |
|---|---|---|
| LIVE-001 | Argo `kyverno` | Synced/Healthy |
| LIVE-002 | Argo `kyverno-policies` | Synced/Healthy |
| LIVE-003 | Argo `techx-corp` | Synced/Healthy |
| LIVE-004 | Kyverno admission replicas available | Desired |
| LIVE-005 | Kyverno background replicas available | Desired |
| LIVE-006 | ClusterPolicy status | Enforce/True |
| LIVE-007 | No admission-controller error burst | Pass |
| LIVE-008 | No webhook timeout | Pass |
| LIVE-009 | All production Pods Ready | Pass |
| LIVE-010 | No ImagePullBackOff | Pass |
| LIVE-011 | No new CrashLoopBackOff | Pass |
| LIVE-012 | Storefront | HTTP 200 |
| LIVE-013 | Product browse | Pass |
| LIVE-014 | Cart add/remove | Pass |
| LIVE-015 | Cart persistence | Pass |
| LIVE-016 | Checkout place order | Pass |
| LIVE-017 | Checkout Rollout | Healthy |
| LIVE-018 | Product reviews/Bedrock path | Pass |
| LIVE-019 | Kafka consumers | Healthy |
| LIVE-020 | Telemetry traces | Flowing |
| LIVE-021 | Prometheus scrape targets | Healthy |
| LIVE-022 | Grafana datasource | Healthy |
| LIVE-023 | Flagd service/config | Unchanged |
| LIVE-024 | HPA conditions | Healthy |
| LIVE-025 | PolicyReport target policies | Zero unexplained fail/warn/error |
| LIVE-026 | Running first-party digest signature | 100% valid |
| LIVE-027 | Running first-party digest SBOM amd64 | 100% retrievable |
| LIVE-028 | External running images exact allow-list | 100% |
| LIVE-029 | Old rollback digest signature/SBOM | Retrievable |
| LIVE-030 | Soak observation window | No delayed regression |

## 15.8. ECR lifecycle and retention tests

| ID | Test | Expected |
|---|---|---|
| RET-001 | Lifecycle preview before change | No required subject selected unexpectedly |
| RET-002 | Signature present immediately | Pass |
| RET-003 | SBOM attestation present immediately | Pass |
| RET-004 | Subject image retained by service rule | Pass |
| RET-005 | Old deployable rollback digest retained | Pass |
| RET-006 | Reference artifact still queryable after lifecycle execution | Pass |
| RET-007 | Deleting demo subject cleans only demo refs | Pass |
| RET-008 | Production digest deletion guard | Prevented by process |
| RET-009 | Ten-build retention still leaves current live digest | Pass |
| RET-010 | Runbook warns before rolling back beyond retention | Present |

## 15.9. Negative/failure-path tests

| ID | Failure | Expected behavior |
|---|---|---|
| NEG-001 | Trivy HIGH finding | No push/sign/SBOM promotion |
| NEG-002 | Push succeeds, digest resolve fails | No sign/attest/PR |
| NEG-003 | SBOM generation fails | No image-bump PR |
| NEG-004 | Cosign sign fails | No image-bump PR |
| NEG-005 | Attest fails | No image-bump PR |
| NEG-006 | Verify signature fails | No image-bump PR |
| NEG-007 | Verify attestation fails | No image-bump PR |
| NEG-008 | Artifact upload missing evidence | Job fail |
| NEG-009 | ECR auth unavailable in Kyverno Audit | Stop cutover |
| NEG-010 | Rekor unavailable | Fail closed; do not Enforce during unresolved outage |
| NEG-011 | Good signed Pod denied | Immediate rollback |
| NEG-012 | Unsigned Pod admitted | Stop, policy ineffective |
| NEG-013 | External unapproved Pod admitted | Stop |
| NEG-014 | Admission p95 latency exceeds agreed threshold | Stop/rollback |
| NEG-015 | Kyverno restart loses ability to verify | Stop/rollback |
| NEG-016 | Argo Degraded after policy sync | Stop/rollback |
| NEG-017 | Storefront non-200 | Immediate rollback |
| NEG-018 | Checkout error/SLO regression | Immediate rollback |
| NEG-019 | Flagd drift | Immediate rollback |
| NEG-020 | Policy scope unexpectedly cluster-wide | Stop before merge |

---

# 16. PolicyReport reconciliation

## 16.1. Không dùng raw total fail

PolicyReport có thể chứa historical controller revision.

Gate phải:

1. filter policy:
   - `verify-first-party-signatures`;
   - `allow-approved-external-image-digests`.
2. đối chiếu resource UID hiện tại;
3. phân loại:
   - active;
   - stale;
   - unresolved.
4. fail khi:
   - active fail/warn/error;
   - unresolved result;
   - registry auth error;
   - policy engine error.

## 16.2. Live export

```bash
kubectl get policyreport,clusterpolicyreport -A -o json \
  > /tmp/mandate10-policyreports.json

kubectl get \
  pod,deploy,rs,statefulset,daemonset,job,cronjob \
  -A -o json \
  > /tmp/mandate10-active-resources.json
```

Add Rollout separately:

```bash
kubectl get rollouts.argoproj.io -A -o json \
  > /tmp/mandate10-rollouts.json
```

Output contract:

```json
{
  "activeFailures": [],
  "authFailures": [],
  "approvedExceptions": [],
  "staleResults": [],
  "unresolvedResults": []
}
```

Final gate:

```text
activeFailures == []
authFailures == []
unresolvedResults == []
```

Task này không nên có permanent first-party signature exception.

---

# 17. Admission performance and availability

`verifyImages` gọi registry và Sigstore verification trên admission path.

## 17.1. Required observations

Capture before/after:

- admission request duration;
- webhook errors;
- registry errors;
- CPU/memory;
- restart count;
- timeout count.

## 17.2. Cache

Kyverno verification cache có thể giảm repeated lookup.

Test:

1. cold request known-good digest;
2. second request same digest;
3. controller restart;
4. cold request again.

Không giả định cache thay thế registry access.

## 17.3. Replica risk

Current Kyverno admission controller đang một replica.

Task không bắt buộc scale, nhưng trước Enforce phải đánh giá:

- một replica có thành single point on deployment path;
- rollout controller availability;
- resource headroom;
- PDB/anti-affinity.

Nếu Enforce làm admission critical, khuyến nghị tối thiểu hai admission replicas nếu budget/node capacity cho phép. Đây phải là reviewed reliability change riêng, không lén gộp.

---

# 18. Stop conditions

Dừng ngay khi:

- known-good signed image bị reject;
- unsigned image được admit;
- external unapproved image được admit;
- registry auth failure còn tồn tại;
- policy Ready không phải True;
- Kyverno admission timeout;
- Argo app Degraded;
- production Pod không Ready;
- storefront không HTTP 200;
- checkout fail;
- flagd drift;
- PolicyReport có active unexplained result;
- live first-party digest chưa có signature/SBOM;
- allow-list không exact-match render;
- ECR lifecycle có nguy cơ xóa evidence cần dùng;
- rollback commit chưa chuẩn bị;
- branch không còn dựa trên latest main;
- PR chứa unrelated application/infra change.

---

# 19. Rollback

## 19.1. Policy rollback

Dùng Git revert:

```bash
git revert <verify-images-enforce-commit>
git push
```

Hoặc external policy commit riêng.

Không dùng:

```bash
kubectl edit clusterpolicy
kubectl patch clusterpolicy
```

trừ emergency được phê duyệt, và phải reconcile Git ngay sau đó.

## 19.2. IRSA rollback

1. Revert Kyverno SA annotations.
2. Confirm controllers healthy.
3. Remove IAM role/policy bằng Terraform reviewed apply.

## 19.3. Workflow rollback

Revert SBOM workflow change.

Existing image/signature/attestation artifacts không gây runtime impact.

## 19.4. Rollback validation

```bash
kubectl get clusterpolicy \
  verify-first-party-signatures \
  allow-approved-external-image-digests \
  -o yaml

kubectl -n argocd get application kyverno-policies
kubectl -n techx-tf3 get pods
curl --fail https://d2tn71186d7ilz.cloudfront.net/
```

---

# 20. Evidence pack

```text
docs/evidence/mandate-10/
├── README.md
├── baseline/
│   ├── main-sha.txt
│   ├── current-pods.json
│   ├── current-images.json
│   ├── current-policies.yaml
│   └── current-policyreports.json
├── sbom/
│   ├── example-digest.txt
│   ├── lookup-amd64.txt
│   ├── lookup-arm64.txt
│   ├── sbom-index.json
│   └── workflow-run.txt
├── irsa/
│   ├── terraform-plan.txt
│   ├── service-accounts.yaml
│   ├── deployments.json
│   └── ecr-read-test.txt
├── audit/
│   ├── policies.yaml
│   ├── policyreports.json
│   └── reconciliation.json
├── enforce-external/
│   ├── policy.yaml
│   ├── good.txt
│   ├── bad-digest.txt
│   └── runtime-smoke.txt
├── enforce-signature/
│   ├── policy.yaml
│   ├── signed-pass.txt
│   ├── unsigned-rejection.txt
│   ├── wrong-identity-rejection.txt
│   └── runtime-smoke.txt
├── provenance/
│   ├── pod-to-digest.txt
│   ├── cosign-verify.json
│   ├── sbom.cdx.json
│   ├── trivy-report.json
│   ├── source-commit.txt
│   └── pr-review.txt
└── final/
    ├── clusterpolicy-status.txt
    ├── policyreport-reconciliation.json
    ├── pod-health.txt
    ├── storefront.txt
    ├── checkout.txt
    └── closure-checklist.md
```

Không commit:

- AWS credentials;
- kubeconfig;
- ECR password;
- OIDC token;
- Cloudflare token;
- private signing key;
- secret values.

---

# 21. One-Pod full provenance demo

Không tự đọc `containers[0]`/`containerStatuses[0]` hoặc coi runtime `imageID` là release index digest. Chọn rõ pod/container và gọi script chuẩn PM-129:

```bash
POD="$(kubectl -n techx-tf3 get pods \
  -l app.kubernetes.io/name=checkout \
  -o jsonpath='{.items[0].metadata.name}')"

./scripts/ci/trace-provenance.sh \
  --namespace techx-tf3 \
  --pod "$POD" \
  --container checkout \
  --sbom-type cyclonedx
```

Final evidence must show one unbroken chain:

```text
Pod/container
→ deployed release/index digest
→ runtime platform digest
→ verified runtime digest membership in release index
→ workflow run/attempt
→ approved-images entry
→ source SHA
→ merged PR + approver
→ Trivy per platform
→ Cosign identity + Rekor
→ CycloneDX SBOM
```

---

# 22. DoD mapping

## DoD 1

> Mọi image tự build có SBOM sinh ra, tra được theo digest bằng một lệnh.

Required evidence:

- scoped run and full run;
- `sbom-index.json`;
- helper command output;
- both platforms;
- attestation verification.

## DoD 2

> `kubectl get clusterpolicy` cho cả hai policy: Enforce/Ready=True.

Command:

```bash
kubectl get clusterpolicy \
  verify-first-party-signatures \
  allow-approved-external-image-digests \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.validationFailureAction}{" "}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}'
```

Expected:

```text
verify-first-party-signatures Enforce True
allow-approved-external-image-digests Enforce True
```

## DoD 3

> Apply image chưa ký hoặc sai identity bị từ chối.

Required:

- manually built unsigned digest;
- actual server admission;
- non-zero exit;
- explicit Kyverno policy/rule message;
- Pod absent.

## DoD 4

> Zero false-positive cho image hợp lệ đang chạy.

Required:

- all live first-party signatures valid;
- all live external images exact allow-list;
- PolicyReport reconciliation clean;
- no registry auth/engine error;
- normal rollout succeeds.

---

# 23. Full Mandate 10 distinction

Completing this task closes the missing pieces of requirement #3:

```text
SBOM + admission signature enforcement
```

Full Directive #10 still requires independent evidence for:

- branch protection and required checks;
- image/IaC/secret/SAST gates;
- provenance;
- actions pinned by commit SHA;
- base image digest pinning;
- Pod → reviewer traceability;
- scoped build/deploy.

Final report must say either:

```text
PM-127/task complete; full Mandate 10 has remaining controls
```

or provide evidence for every directive item.

Không dùng câu:

```text
Mandate 10 hoàn thành 100%
```

chỉ vì hai policy đã Enforce.

---

# 24. Agent execution contract

Agent phải:

1. cập nhật latest `main`;
2. record SHA;
3. không thay đổi production ngay trong PR đầu;
4. tạo small PRs theo plan;
5. không bật Enforce trước clean Audit;
6. không hardcode incomplete external list;
7. không bỏ qua BusyBox/init/sidecar;
8. không dùng static ECR credential;
9. không dùng broad identity regex;
10. không sign external images bằng TF3 identity;
11. không coi uploaded SBOM file là đủ nếu chưa attest;
12. không coi `runAs digest` là chữ ký;
13. không coi raw PolicyReport count là current state;
14. không bypass signature để unblock rollout;
15. không mutate policy bằng kubectl;
16. chuẩn bị rollback trước mỗi cutover;
17. dừng khi có stop condition;
18. không tuyên bố done nếu chưa có real unsigned-image rejection.

## Agent final report format

```text
Phase:
Branch:
Base main SHA:
PR:
Commits:
Files changed:

SBOM:
- Services covered:
- Platforms covered:
- Digest used:
- Generation command:
- Attestation command:
- Verification result:
- Lookup command:
- Evidence artifact:

Kyverno/ECR:
- Kyverno version:
- Admission SA:
- Background SA:
- IRSA role:
- ECR actions:
- Registry auth result:

Policies:
- External allow-list action/Ready:
- Signature verify action/Ready:
- Controller coverage:
- External exact-set delta:

Admission tests:
- Signed image:
- Unsigned image:
- Wrong identity:
- Unapproved external digest:

Live verification:
- Argo:
- Pods:
- Storefront:
- Browse:
- Cart:
- Checkout:
- Telemetry:
- Flagd invariant:
- PolicyReport active failures:
- Auth/engine failures:

Evidence paths:
Rollback commit:
Residual risks:
Full Mandate 10 remaining controls:
Recommendation:
```

---

# 25. Final acceptance checklist

- [ ] Latest `main` baseline recorded.
- [ ] Authoritative production render uses four values files.
- [ ] Normal, sidecar and init images are inventoried.
- [ ] First-party and external sets are distinct.
- [ ] External allow-list exact-matches render.
- [ ] BusyBox/init helper images are included.
- [ ] ECR lifecycle behavior reviewed.
- [ ] SBOM generated from exact digest.
- [ ] CycloneDX valid.
- [ ] amd64 SBOM exists.
- [ ] arm64 SBOM exists.
- [ ] SBOM file hash recorded.
- [ ] SBOM attested to exact digest.
- [ ] Attestation issuer verified.
- [ ] Attestation identity verified.
- [ ] Helper retrieves verified SBOM in one command.
- [ ] Scoped build passes.
- [ ] Full 20-target evidence passes.
- [ ] No image-bump PR on SBOM failure.
- [ ] Kyverno ECR IRSA applied.
- [ ] IAM has no ECR write.
- [ ] Admission controller reads private ECR.
- [ ] Background controller produces reports without auth error.
- [ ] First-party verify policy Audit/Ready.
- [ ] External allow-list policy Audit/Ready.
- [ ] Audit has zero unexplained live failure.
- [ ] Current live first-party digests have valid signatures.
- [ ] Current live first-party digests have SBOM.
- [ ] External policy Enforce/Ready.
- [ ] Signature policy Enforce/Ready.
- [ ] Approved external digest admitted.
- [ ] Unapproved external digest rejected.
- [ ] Signed first-party digest admitted.
- [ ] Unsigned first-party digest rejected.
- [ ] Wrong-identity signature rejected.
- [ ] Deployment/controller coverage proven.
- [ ] Checkout workloadRef regression test passes.
- [ ] Ephemeral container path tested.
- [ ] PolicyReport reconciliation clean.
- [ ] Argo apps Synced/Healthy.
- [ ] All production Pods Ready.
- [ ] Storefront returns 200.
- [ ] Browse/cart/checkout pass.
- [ ] Telemetry flows.
- [ ] Flagd unchanged.
- [ ] Admission latency/errors acceptable.
- [ ] Rollback commits prepared.
- [ ] One-Pod provenance demo complete.
- [ ] Evidence pack complete.
- [ ] PM-127 marked complete only after mentor-verifiable rejection.
- [ ] Full Mandate 10 residual controls stated honestly.

---

# 26. Recommended implementation order in one sentence

```text
Inventory → SBOM/attestation gate → ECR IRSA → backfill live digests →
external Audit → external Enforce → signature Audit → signature Enforce →
real unsigned rejection → provenance/evidence closure.
```
