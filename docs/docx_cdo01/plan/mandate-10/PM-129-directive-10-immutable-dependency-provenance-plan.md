# PM-129 — Directive #10: Immutable dependency pinning + truy ngược full provenance

**Repo:** `tuu-ngo/Phase3-TF3-Infra-Sentinel`
**Liên quan:** PM-124 (audit pin), PM-127 (SBOM + `verifyImages` — dependency cứng của Phase 4)
**Trạng thái:** Kế hoạch thực thi chuẩn
**Ngày tạo:** 2026-07-21

> **Nguyên tắc:** thiếu một mắt xích provenance thì kết quả cuối không được ghi `PASS`. `--allow-pending-sbom` chỉ dành cho rehearsal trước khi PM-127 hoàn thành.

## 0. Chốt scope Dockerfile

Phase 0 không chặn Phase 1, nhưng phải hoàn tất trước Phase 2. Audit PM-124 và thực tế repo lệch nhau; cần PM xác nhận trước khi tính DoD.

| Hạng mục | Audit cũ nói | Thực tế repo | Cần chốt / áp dụng |
|---|---:|---|---|
| Workflow dùng tag | 6 | **7**: `build-push-ecr`, `scan-external-images`, `secret-scan`, `terraform-plan`, `terraform-apply`, `validate-production-access`, `test-image-bump` | Dùng số 7 |
| Service build | 18 | **20** theo `ALL_SERVICES` trong `build-push-ecr.yml`: `accounting`, `ad`, `cart`, `checkout`, `currency`, `email`, `fraud-detection`, `frontend`, `frontend-proxy`, `image-provider`, `kafka`, `llm`, `load-generator`, `payment`, `product-catalog`, `product-reviews`, `quote`, `recommendation`, `shipping`, `flagd-ui` | Dùng số 20 |
| `opensearch` | — | Có Dockerfile + bake target trong `docker-compose.yml`, nhưng không thuộc `ALL_SERVICES`; không build/push/scan bởi `build-push-ecr.yml` | PM quyết định có thuộc Directive #4 hay là vendor image ngoài pipeline |
| Genproto Dockerfile | — | 6 file (`checkout`, `currency`, `frontend`, `product-catalog`, `product-reviews`, `recommendation`), được `docker-gen-proto.sh` dùng thực sự để regenerate protobuf; không tạo production image | PM quyết định có thuộc DoD Dockerfile hay loại trừ vì không lên cluster |
| `frontend/Dockerfile.cypress` | — | Dùng trong `docker-compose-tests.yml` làm E2E gate, không phải runtime image | Nên pin; ghi rõ là test image |

**Output bắt buộc:** một dòng xác nhận của PM trên chat/comment ticket chốt ba phạm vi `opensearch`, genproto và Cypress. Không tự quyết rồi báo DoD.

DoD không dùng số cứng `0/20`; `20` chỉ là số build target trong `ALL_SERVICES`. Viết:

```text
0 external FROM trong toàn bộ Dockerfile thuộc scope đã được PM xác nhận
còn sử dụng image tag mà không kèm @sha256.
```

### 0.1 Quyết định PM bổ sung

1. **PR approval policy:** tối thiểu một latest review `APPROVED` hay bắt buộc `reviewDecision == APPROVED`; approver có phải khác author không.
2. **SBOM contract PM-127:** SPDX JSON/CycloneDX, predicate type, attach release-index hay platform digest, certificate identity/issuer, lệnh verify chuẩn.
3. **Evidence retention:** fix ngắn hạn manifest approved lên 90 ngày; durable design bằng OCI/SLSA attestation hoặc S3 Object Lock.

Approval/SBOM policy phải chốt trước final Phase 4; Docker scope phải chốt trước Phase 2.

### 0.2 Definition of Done chuẩn hóa

- [ ] 0 external `uses:` trong **mọi** workflow ở final-main SHA còn tag/branch/short SHA. `7` chỉ là inventory snapshot trước PM-125/127, không phải mẫu số DoD.
- [ ] Mọi action pin full SHA 40 ký tự, có comment version gốc.
- [ ] Không còn `/main/`, `/master/`, `/releases/latest/`, `@latest` là remote CI dependency trong scope.
- [ ] Actionlint pin release + checksum.
- [ ] 0 external `FROM` thiếu digest trong Dockerfile scope PM xác nhận.
- [ ] Regression checker + unit tests chạy trong CI.
- [ ] Local build thật `linux/amd64` đủ 20 target pass trước merge.
- [ ] Một run `main` có aggregate manifest đúng 20 target và toàn bộ Trivy/Cosign gate pass.
- [ ] Trace pod thật: digest → commit → PR approver → scan → signature/Rekor → SBOM.
- [ ] Final evidence không dùng `--allow-pending-sbom`.
- [ ] Có runbook, terminal log và `trace-result.json` tự đứng làm bằng chứng.

## Phase 1 — Pin GitHub Actions theo commit SHA

### 1.1 Script pin thật

Tạo `scripts/ci/pin-actions.sh`. Script phải **tự discover** mọi external `uses:` và reusable-workflow reference trong `.github/workflows/*.{yml,yaml}` ở commit đang audit, resolve SHA thật qua GitHub API, thay exact ref, giữ comment tag/version, sinh `scripts/ci/action-pins.lock.json`, và fail nếu còn tag/branch/short SHA. Không dùng array viết tay làm source of truth, vì PM-125/127 có thể thêm workflow/action sau inventory 7 workflow.

```bash
ACTIONS=( # seed inventory only; script must merge with dynamic discovery
  "actions/checkout@v6" "actions/checkout@v4"
  "actions/upload-artifact@v4" "actions/download-artifact@v4"
  "actions/setup-python@v5"
  "aws-actions/configure-aws-credentials@v4" "aws-actions/amazon-ecr-login@v2"
  "docker/setup-qemu-action@v3" "docker/setup-buildx-action@v3"
  "aquasecurity/setup-trivy@v0.3.1" "sigstore/cosign-installer@v4.1.2"
  "gitleaks/gitleaks-action@v3" "hashicorp/setup-terraform@v3"
)

for entry in "${ACTIONS[@]}"; do
  repo="${entry%@*}"; tag="${entry#*@}"
  sha="$(gh api "repos/${repo}/commits/${tag}" --jq .sha)"
  [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo "FAIL: ${entry} không resolve thành full SHA" >&2; exit 1; }
  echo "${repo}@${tag} -> ${sha}"
done
```

Workflow phải có dạng:

```yaml
uses: actions/checkout@<full-40-char-sha>  # v6
```

`actions/checkout@v4` của `test-image-bump.yml` là version lệch cần note trong PR. Lock phải lưu `workflow path`, original ref, resolved SHA và thời điểm resolve, để review phát hiện action mới ngoài seed inventory.

### 1.2 Actionlint không dùng floating remote script

Thay `curl ...raw.githubusercontent.com/rhysd/actionlint/main/...` trong `test-image-bump.yml` bằng CLI chính chủ `rhysd/actionlint` **v1.7.12**: URL release asset `linux_x86_64` chứa tag cố định, SHA256 chính thức hard-code trong workflow/lock file, chạy `sha256sum -c` trước giải nén. Không dùng wrapper third-party hoặc `uses:` cho repo không phải GitHub Action.

Cấm `/main/`, `/master/`, `/releases/latest/`, `@latest` trong CI path thuộc scope.

### 1.3 Mở rộng lint gate

Thay path filter hẹp bằng:

```yaml
paths:
  - ".github/workflows/**"
  - "scripts/ci/**"
```

Chạy toàn bộ:

```bash
./actionlint
```

### 1.4 Regression checker

Thêm `scripts/ci/verify-immutable-pins.py`, chạy trong `test-image-bump.yml`. `actionlint` chỉ kiểm cú pháp; checker phải discover toàn workflow tree và fail khi gặp external `uses:`/reusable workflow không phải 40-char SHA, external `FROM` thiếu `@sha256`, hoặc dependency CI floating. Cho phép `uses: ./local-action`, `FROM scratch`, và stage nội bộ như `FROM base AS builder`.

### 1.5 Exit criteria Phase 1

- [ ] Bảy workflow không còn `uses: <action>@<tag-không-phải-sha>`.
- [ ] Không còn actionlint `curl .../main/...`; v1.7.12 và checksum đã pin.
- [ ] Pin có comment version gốc; lint toàn workflow và trigger path đã mở rộng.
- [ ] Checker tồn tại, chạy trong CI, và fail đúng case test.

## Phase 2 — Pin Dockerfile base image theo digest

### 2.1 Lấy digest từ registry

Không dùng digest cache local. Lấy từ registry:

```bash
docker buildx imagetools inspect "$IMAGE:$TAG" --format '{{json .Manifest}}' |
  jq -er '.digest | select(test("^sha256:[0-9a-f]{64}$"))'
```

### 2.2 Scope xử lý

**Nhóm A, pin trực tiếp mọi build/runtime stage:** `accounting`, `ad`, `cart`, `checkout`, `currency`, `email`, `fraud-detection`, `frontend`, `image-provider`, `kafka`, `llm`, `load-generator`, `payment`, `product-catalog`, `product-reviews`, `quote`, `recommendation`, `shipping`.

**Nhóm B:** `flagd-ui/Dockerfile` chỉ vá `BUILDER_IMAGE` (`hexpm/elixir`); giữ `RUNNER_IMAGE` distroless đã pin. `frontend-proxy/Dockerfile` (`envoyproxy/envoy:v1.34.10`) pin theo cách chuẩn.

**Nhóm C:** `opensearch/Dockerfile`, sáu genproto Dockerfile, `frontend/Dockerfile.cypress`; chỉ pin/loại trừ sau khi PM chốt, và ghi lý do.

### 2.3 Verify fail-closed, resolve ARG

`verify-immutable-pins.py --dockerfiles` phải resolve `ARG` và `FROM ${VAR}`, phân biệt external image/stage nội bộ, và kiểm toàn scope PM chốt (không chỉ git diff). Bước syntax và registry resolution tách riêng:

```bash
python3 scripts/ci/verify-immutable-pins.py --dockerfiles
while IFS= read -r ref; do
  docker buildx imagetools inspect "$ref" >/dev/null || {
    echo "FAIL: digest không resolve được: $ref" >&2
    exit 1
  }
done < <(python3 scripts/ci/verify-immutable-pins.py --list-refs)
```

Unit test bắt buộc: ARG resolve (bao gồm `flagd-ui`), nested/cyclic ARG, `FROM --platform=$BUILDPLATFORM`, `scratch`, internal stage, multistage/logical line `\\`, digest sai, external tag thiếu digest, action SHA ngắn, reusable external workflow SHA ngắn, ARG không resolve phải fail-closed.

### 2.4 Exit criteria Phase 2

- [ ] Không còn external `FROM` thiếu digest trong scope PM xác nhận.
- [ ] Nhóm C có quyết định PM và lý do rõ.
- [ ] Toàn bộ digest pin resolve qua `imagetools inspect`.

## Phase 3 — Verify build không gãy

`build-push-ecr.yml` chỉ chạy `workflow_dispatch` và push `main` theo path filter, không có `pull_request`; PR check không là evidence full build. Trước merge chạy build thật single-arch:

```bash
TARGETS=(accounting ad cart checkout currency email fraud-detection frontend frontend-proxy image-provider kafka llm load-generator payment product-catalog product-reviews quote recommendation shipping flagd-ui)
docker buildx bake -f docker-compose.yml --check "${TARGETS[@]}"
docker buildx bake -f docker-compose.yml --set '*.platform=linux/amd64' "${TARGETS[@]}"
```

Merge Dockerfile vào `main` dự kiến tự trigger push build do path filter. Theo dõi run đó trước; chỉ `workflow_dispatch` nếu push run không chạy, bị cancel, aggregate thiếu đúng 20 target, hoặc cần rehearsal riêng. Không chạy đồng thời hai run gây build/push trùng chi phí.

```bash
gh run list -R tuu-ngo/Phase3-TF3-Infra-Sentinel --workflow build-push-ecr.yml --limit 1
```

Lưu `run_id`, link run, aggregate manifest; xác nhận Trivy/Cosign pass và đủ chính xác 20 service, không suy diễn từ mode `full`/`scoped`.

## Phase 4 — `scripts/ci/trace-provenance.sh`

### 4.1 Retention là prerequisite

`trivy-*` và `signed-release-evidence-*` retention 90 ngày; `approved-image-<run_id>-<service>` và `approved-images-<run_id>-<attempt>` hiện 7 ngày và chứa `sourceSha`. Trước Phase 4 phải nâng hai loại approved artifact lên 90 ngày (fix ngắn hạn, phụ thuộc repo/org max retention), hoặc archive durable qua OCI/SLSA attestation/S3 Object Lock. Ưu tiên OCI lâu dài; 90 ngày đủ deadline nhưng phải ghi rõ là tạm thời.

### 4.2 CLI và cấu hình

```text
Usage: trace-provenance.sh --pod POD --namespace NAMESPACE
       [--container NAME] [--pr NUMBER] [--sbom-type TYPE] [--allow-pending-sbom]
```

`--pod`, `--namespace` bắt buộc; container tự chọn chỉ khi pod có một container; `--pr` giải ambiguity; `--sbom-type` bắt buộc final; `--allow-pending-sbom` chỉ rehearsal. Parser validate missing value/unknown option, không placeholder.

```bash
REPO="tuu-ngo/Phase3-TF3-Infra-Sentinel"
ECR_REPO="techx-corp"; AWS_REGION="ap-southeast-1"
ECR_REGISTRY="197826770971.dkr.ecr.ap-southeast-1.amazonaws.com"
WORKFLOW_PATH=".github/workflows/build-push-ecr.yml"
EXPECTED_IDENTITY="https://github.com/${REPO}/${WORKFLOW_PATH}@refs/heads/main"
EXPECTED_ISSUER="https://token.actions.githubusercontent.com"
SERVICES=(accounting ad cart checkout currency email fraud-detection frontend frontend-proxy image-provider kafka llm load-generator payment product-catalog product-reviews quote recommendation shipping flagd-ui)
```

Preflight fail-closed: kiểm `aws gh kubectl jq cosign docker`, `gh auth status`, `aws sts get-caller-identity`, quyền `kubectl get pods`; dùng `mktemp -d`, cleanup trap, và ghi `trace-result.json` bằng temp + atomic move để không dùng nhầm PASS cũ.

### 4.3 Năm mắt xích bắt buộc

1. **Pod → release/runtime digest.** Lấy `spec.containers[].image` và `status.containerStatuses[].imageID`; release phải immutable `sha256:...`; parse runtime bằng regex. Inspect manifest của release index. Nếu release/runtime khác nhau, runtime phải là child digest trong manifest; nếu không fail.
2. **Digest → ECR tag → run → aggregate.** Lấy toàn `imageTags`, không dùng `imageTags[0]` hay `cut -d- -f2`. Match suffix theo 20 service, lấy segment số ngay trước suffix làm run candidate. Với mỗi candidate, REST API phải xác nhận `success`, branch `main`, event `push|workflow_dispatch`, đúng workflow path, attempt dương; tải aggregate `approved-images-${RUN_ID}-${RUN_ATTEMPT}`. Manifest phải khớp run ID/attempt/source SHA, service đúng một lần, digest đúng release, platforms không rỗng. Nhiều candidate hợp lệ là fail ambiguity.
3. **Source SHA → PR + approver.** Query associated PR; chỉ PR merged vào `main`. `--pr` phải thuộc tập hợp. Một PR thì dùng; nhiều PR ưu tiên `merge_commit_sha == SOURCE_SHA`, còn mơ hồ thì fail. Mặc định cần ít nhất một latest `APPROVED`; `reviewDecision` và separation-of-duties chỉ enforce khi PM đã chốt.
4. **Trivy theo run/platform.** Download `trivy-post-push-${RUN_ID}-${SERVICE}`. Mọi platform aggregate (`linux/amd64`, `linux/arm64`) phải có file JSON parse được, `ArtifactName` chứa đúng release digest. Đếm riêng HIGH/CRITICAL; bất kỳ số nào > 0 là fail, vì artifact upload `if: always()`.
5. **Cosign keyless + Rekor + SBOM.** `cosign verify` với exact identity/issuer và private ECR image; lưu raw JSON/evidence: identity, issuer, signed digest, Rekor index/ID/integrated time. Final cần `--sbom-type`, `cosign verify-attestation` success cùng identity/issuer và raw attestation. Rehearsal cần explicit `--allow-pending-sbom`, đặt `sbomVerified=false`, `overallResult=REHEARSAL_BLOCKED_BY_PM_127`; không được `PASS`.

Khi fail, exit non-zero và atomic `trace-result.json` tối thiểu:

```json
{"overallResult":"FAIL","failedStep":"TRIVY","error":"missing linux/arm64 report"}
```

Final result phải có ít nhất các trường: pod/namespace/container/service, deployed image, release/runtime digest và quan hệ, workflow ID/attempt/URL/event/path, source SHA, PR+author+reviews+approvers, Trivy platforms/HIGH/CRITICAL, Cosign identity/issuer/signed digest/Rekor fields, SBOM predicate/verified, và `overallResult: "PASS"`.

### 4.4 Exit criteria Phase 4

- [ ] Retention approved artifact 90 ngày hoặc durable archive.
- [ ] Một pod thật trace đủ năm mắt xích bằng một lệnh.
- [ ] Fail rõ khi thiếu SBOM/platform report, Trivy HIGH/CRITICAL, Cosign hoặc approval fail.
- [ ] Pod nhiều container không tự chọn container đầu.
- [ ] JSON đủ tự đứng làm evidence; PM chốt separation-of-duties.

## Phase 5 — Runbook, rehearsal, final evidence

Tạo `scripts/ci/RUNBOOK.md` với preflight (`aws gh kubectl jq cosign docker`, `gh auth status`, `aws sso login`, AWS identity, kube context/RBAC) và ECR login riêng cho Cosign:

```bash
aws ecr get-login-password --region ap-southeast-1 | docker login \
  --username AWS --password-stdin 197826770971.dkr.ecr.ap-southeast-1.amazonaws.com
```

Rehearsal trước PM-127:

```bash
./scripts/ci/trace-provenance.sh --pod <pod> --namespace techx-tf3 \
  --container <container> --allow-pending-sbom 2>&1 |
  tee docs/evidence/mandate-10/trace-rehearsal.log
```

Kết quả hợp lệ duy nhất khi SBOM thiếu là `REHEARSAL_BLOCKED_BY_PM_127`.

Final sau PM-127:

```bash
./scripts/ci/trace-provenance.sh --pod <pod> --namespace techx-tf3 \
  --container <container> --sbom-type <predicate-type-PM-127> 2>&1 |
  tee docs/evidence/mandate-10/trace-terminal.log
cp trace-result.json docs/evidence/mandate-10/trace-result.json
jq -e '.overallResult == "PASS" and .sbomVerified == true' docs/evidence/mandate-10/trace-result.json
```

Evidence package:

```text
docs/evidence/mandate-10/
├── pm-scope-confirmation.md
├── action-pin-audit-before.txt
├── action-pin-audit-after.txt
├── action-pins.lock.json
├── docker-pin-audit.txt
├── local-amd64-build.log
├── build-run.json
├── approved-images.json
├── trace-rehearsal.log
├── trace-terminal.log
├── trace-result.json
├── cosign-verify.json
├── sbom-attestation.json
└── README.md
```

`README.md` map trực tiếp từng DoD sang evidence. Runbook phải có troubleshooting cho image không digest, runtime mismatch, thiếu ECR tag/expired aggregate/wrong attempt, không hoặc nhiều PR, thiếu platform report, vulnerability, Cosign/SBOM fail.

## Rủi ro, thứ tự và trạng thái báo cáo

Rủi ro xuyên suốt: PM-127 chưa xong chặn final SBOM; Phase 0 chưa chốt chặn DoD Dockerfile; retention 7 ngày có thể làm demo provenance fail.

```text
Phase 1: pin Actions + actionlint/checksum + checker
  ↓ (song song)
Phase 0: PM chốt Dockerfile scope
  ↓
Phase 2: pin digest + checker ARG-based
  ↓
Phase 3: local amd64 build 20 target → merge → theo dõi push run
  ↓
Nâng retention approved-image lên 90 ngày hoặc durable archive
  ↓
Phase 4: trace-provenance fail-closed
  ↓
Phase 5: runbook + rehearsal/final evidence
```

| Tình trạng | Cách báo cáo |
|---|---|
| Phase 1–3 xong, PM-127 chưa xong | `In Progress — provenance core ready; blocked by PM-127 for final SBOM link` |
| Rehearsal đủ trừ SBOM | `REHEARSAL_BLOCKED_BY_PM_127` — không gọi PASS |
| Đủ năm mắt xích final | `Done — end-to-end provenance PASS` |
| Artifact hết retention | `Blocked — evidence retention gap` |
| Không có PR approver | `Failed change-control provenance` |

## Điều kiện đóng Directive #10

Chỉ đóng khi đồng thời có dependency bất biến (Actions SHA, actionlint checksum, Docker digest), build hoạt động (local AMD64 20 target và main aggregate/scan/sign pass), provenance đầy đủ (digest → commit → approver → Trivy → Cosign/Rekor → SBOM), evidence tái chạy được (runbook/log/result/retention), và final `overallResult == "PASS"`, `sbomVerified == true`, không có `--allow-pending-sbom`.
