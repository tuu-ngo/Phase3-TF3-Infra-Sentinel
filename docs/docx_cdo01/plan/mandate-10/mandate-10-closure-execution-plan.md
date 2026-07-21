# Mandate 10 — Closure Execution Master Plan

## 1. Vai trò tài liệu và trạng thái thật

Tài liệu này điều phối đường triển khai và evidence để đóng Mandate 10. Nó không thay thế canonical audit tại `mandate-10-gap-analysis.md` và không tự tạo bằng chứng production.

| Dimension | Current verdict |
|---|---|
| Plan quality | `PASS FOR IMPLEMENTATION` sau khi các clause trong bộ plan được review |
| Implementation | `BLOCKED` |
| Production evidence | `BLOCKED` |
| Mandate 10 closure | `BLOCKED` |

Không ticket nào được chuyển `Done` chỉ vì plan được merge. PM-132 chỉ chuyển một criterion sang `PASS` khi exact run/PR/policy/artifact tương ứng tồn tại.

## 2. Authority hierarchy và baseline freshness

1. Current-state verdict: `mandate-10-gap-analysis.md`.
2. Closure order và cross-task gates: file này.
3. Control detail: PM-125, PM-127, PM-129 và PM-132 specs cùng thư mục.
4. Runtime truth: final-main Git tree, GitHub ruleset export, workflow runs, ECR, Argo CD và live cluster.

Planning baseline sau sync là:

```text
main@63db1d8d171a9d64284cea0f496a37b859791484
workflow files: 7
external action references: 37
Dockerfiles: 28
four-values Helm render: 23,065 lines / 30 unique image references
```

Đây chỉ là planning snapshot. Trước mỗi implementation PR phải record `BASE_SHA`; trước closure phải tạo lại audit bundle từ exact `FINAL_MAIN_SHA`. Nếu `origin/main` đổi sau inventory/render, evidence cũ thành `STALE` và gate dừng.

Planning PR #288 không cần giả vờ có production audit bundle. Bundle machine-generated là exit artifact bắt buộc của final implementation/closure PR, không phải điều kiện merge tài liệu planning. PR #288 chỉ cần baseline commands/output trong review và mọi claim ghi rõ `planned`/`blocked`.

## 3. Các quyết định kiến trúc đã chốt

### D1 — Trust boundary của required gate

Repo hiện là public repository thuộc user `tuu-ngo`, không phải organization repository. Vì vậy plan không phụ thuộc organization-level required workflow.

Trust boundary hiện hành gồm cả bốn lớp sau; thiếu một lớp thì PM-125 vẫn `BLOCKED`:

1. `.github/CODEOWNERS` bảo vệ chính file ownership, workflow, security scripts, Kyverno policy, Terraform IRSA và evidence contract.
2. Ruleset `main` yêu cầu code-owner approval, dismiss stale approvals, approval cho most recent reviewable push, strict up-to-date branch và không cho direct/force push.
3. Required context có tên duy nhất `Secure delivery gate`, expected source là GitHub Actions App; repo-wide checker fail nếu workflow/job khác tạo cùng check name.
4. Security-control PR phải được một owner hợp lệ khác author approve; bypass list rỗng hoặc mọi ngoại lệ phải có owner, expiry, incident/ticket và audit export.

CODEOWNERS contract:

```text
/.github/CODEOWNERS                         @<approved-security-owner>
/.github/workflows/**                       @<approved-security-owner>
/scripts/ci/**                              @<approved-security-owner>
/scripts/security/**                        @<approved-security-owner>
/gitops/policies/kyverno/**                 @<approved-security-owner>
/infra/modules/eks-platform/**              @<approved-security-owner>
/docs/evidence/mandate-10/**                @<approved-security-owner>
```

`@<approved-security-owner>` không được merge như placeholder. Repo admin phải chọn một GitHub user/team có write access, khác author của control PR, và chứng minh CODEOWNERS resolve trên GitHub trước khi bật required gate.

Negative governance test bắt buộc: mở disposable PR sửa aggregate thành unconditional PASS hoặc tạo job trùng tên. PR phải vẫn không merge được vì code-owner/stale-review/source/context controls. Không merge fixture.

Nếu repo chuyển vào organization có plan hỗ trợ, ADR có thể nâng lên organization ruleset “Require workflows to pass before merging” từ security-controls repository riêng. Đây là hardening tiếp theo, không được ghi như capability đang có.

### D2 — PR Trivy scan cả AMD64 và ARM64

Chọn phương án mạnh: mọi changed production target trong PR được build và Trivy scan cho cả `linux/amd64` và `linux/arm64` trước merge.

- Matrix key là `(service, platform)`; expected set sinh từ change detector và authoritative platform list.
- QEMU/Buildx chỉ tạo local/OCI candidate; không ECR login/push, không AWS OIDC, không sign, không promotion.
- Mỗi platform phải có report parse được và HIGH/CRITICAL bằng zero.
- Thiếu report, matrix cell fail/cancel/skip trái contract hoặc platform set không đủ đều làm aggregate fail.
- Post-merge release vẫn scan lại exact published platform digests; PR scan không thay release gate.

Chi phí build/scan tăng được chấp nhận để đáp ứng “HIGH/CRITICAL chặn merge” trên mọi platform publish. Nếu sau này hạ về AMD64-only, ADR phải hạ claim thành “ARM64 blocked at promotion, not merge”.

### D3 — SBOM identity và attestation selection

Mỗi CycloneDX predicate phải có các property:

```text
techx.service
techx.platform
techx.subjectDigest
techx.sourceSha
techx.workflowRunId
techx.workflowRunAttempt
techx.generator
techx.generatorVersion
```

`techx.sbomSha256` không nhúng vào chính SBOM vì tạo self-referential hash. Hash được tính sau khi SBOM hoàn tất và lưu trong:

- `sbom-index.json`;
- signed custom attestation type `https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/attestations/release-provenance/v1` liên kết exact subject/service/platform/run/attempt;
- Actions evidence artifact cùng run/attempt.

Lookup phải match đồng thời subject digest, service, platform, source SHA, run ID và attempt. Zero hoặc nhiều candidate hợp lệ là fail ambiguity; không chọn newest hoặc phần tử đầu tiên.

### D4 — Admission final demo dùng actual apply

`--dry-run=server` là rehearsal/preflight. Final evidence phải chạy actual `kubectl apply`, nhận non-zero từ exact signature rule, rồi chứng minh Pod `NotFound`. Registry/auth/network/resource/security-context rejection làm demo `INVALID`.

### D5 — SBOM enforcement boundary

Hai câu sau phải xuất hiện nguyên nghĩa trong ADR/final report:

> Đây là end-to-end traceability provenance, chưa tuyên bố đạt SLSA level.

> SBOM được enforce ở release pipeline; admission giai đoạn đầu enforce signature identity và digest, chưa enforce SBOM predicate trực tiếp.

### D6 — Dependency freshness

Pin SHA/digest không được trở thành “pin rồi quên”. Chọn Renovate làm primary automation cho `github-actions` và `dockerfile` managers:

- lịch weekly;
- giữ version comment cạnh full SHA/digest;
- không automerge;
- mọi bump chạy PR gate, multi-platform Trivy và code-owner review;
- dashboard/report liệt kê dependency quá hạn và PR bị block.

Nếu Renovate App chưa được phê duyệt, fallback là scheduled read-only dependency audit tạo artifact/issue; closure ADR phải ghi owner và SLA tạo bump PR. Không được bỏ cả automation lẫn scheduled audit.

## 4. Execution sequence và hard gates

### Gate 0 — Planning/governance ready

Deliverables:

- branch sync latest main;
- current baseline commands rerun;
- master plan/ADR decisions reviewed;
- actual security CODEOWNER principal được chốt;
- PR title/body phản ánh PM-124/125/127/129/132;
- planning review approved.

Exit: plan có thể merge. Implementation/evidence vẫn `BLOCKED`.

### Gate 1 — Governance + PM-125 PR security gate

Implementation PR:

- CODEOWNERS + ruleset export plan;
- read-only `pull_request`/`merge_group` workflow;
- immutable action/tool pins;
- Gitleaks, dual-platform Trivy, IaC, SAST;
- always-created aggregate + unique-name checker;
- positive/negative/fork/governance fixtures.

Order: merge code first, observe check context, admin then enables exact required context. Do not require a context before it exists on default branch.

Exit evidence:

- ruleset JSON/screenshot with exact context and GitHub Actions source;
- normal PR PASS;
- each negative fixture FAIL + merge blocked;
- malicious gate-edit PR blocked without security-owner approval;
- zero AWS/ECR/production writes.

Rollback: disable only newly added required context if it deadlocks all PRs, retain review protection, revert workflow through reviewed PR, record admin action.

### Gate 2 — PM-127 SBOM release contract

Implementation PR:

- per-platform CycloneDX with D3 metadata;
- exact-digest generation, hash/index and signed release-provenance link;
- Cosign attest + verify exact issuer/identity;
- 90-day minimum evidence retention;
- lookup helper ambiguity tests;
- current live digest backfill plan.

Exit evidence: scoped and full release runs prove both platforms, hashes, attestations and helper lookup. Any missing platform/metadata/attestation blocks promotion.

### Gate 3 — Kyverno ECR auth and policy rollout

Separate GitOps PRs:

1. IRSA/ECR read-only and controller reliability;
2. SBOM backfill for live first-party digests;
3. external exact allow-list in Audit then Enforce;
4. first-party signature policy in Audit then Enforce.

Before Enforce:

- minimum two admission replicas when capacity allows;
- PDB `minAvailable: 1` and anti-affinity/topology spread reviewed;
- cold/warm registry lookup tests;
- no known-good rejection;
- rollback commit prepared.

Operational acceptance window:

- zero webhook/registry errors in controlled signed-image test set;
- no admission timeout;
- p95/p99 measured before/after and within ADR-approved budget;
- controller Ready/restarts/resources healthy;
- Argo/storefront/browse/cart/checkout/telemetry healthy.

If capacity prevents two replicas/PDB, risk owner must explicitly accept single-point-of-failure before Enforce; otherwise Gate 3 remains `BLOCKED`.

### Gate 4 — PM-129 immutable dependencies + complete provenance

Implementation PRs:

- full-SHA Actions and checksummed tools;
- authoritative Dockerfile inventory and all external stages pinned to correct index/manifest digest;
- Renovate/scheduled freshness control;
- retention/durable archive;
- `trace-provenance.sh` linking source PR and promotion PR separately;
- fail-closed candidate selection.

Exit evidence: dynamic final-main audits are clean and one real Pod produces `trace-result.json` with all links through SBOM.

### Gate 5 — PM-131 scoped build/deploy evidence

Required tests:

- one-service positive;
- shared-input/full-set positive;
- docs-only/no-op negative;
- unknown mapping, empty unexpected matrix, extra service, missing digest and out-of-scope promotion negative.

Exit evidence: exact run/attempt, selected/skipped sets, aggregate and promotion PR agree.

### Gate 6 — PM-132 final evidence and sign-off

Run only after Gates 1–5 pass on exact final-main SHA:

- required merge-gate negative PR;
- all PR security controls;
- per-platform SBOM/attestation;
- policies `Enforce` and `Ready=True`;
- real unsigned ECR digest actual-apply rejection + Pod absent;
- action/Docker pin audits;
- scoped evidence;
- one-Pod provenance trace;
- production smoke/telemetry;
- ADR + owner/reviewer/mentor sign-off.

No row may be marked `PASS` from YAML, a plan, expected output or rehearsal.

## 5. Final audit bundle contract

Generate after implementation has landed and immediately before closure review:

```text
docs/evidence/mandate-10/audit/
├── baseline-sha.txt
├── workflow-inventory.txt
├── action-ref-inventory.txt
├── dockerfile-inventory.json
├── helm-render-image-inventory.json
├── unicode-format-control-scan.txt
├── ruleset-export.json
└── README.md
```

Every file records generator version/command, UTC timestamp and exact SHA. `README.md` maps checksums and DoD criterion. If closure PR changes workflow/Dockerfile/chart/values after bundle generation, CI fails stale-baseline validation and bundle must be regenerated.

## 6. Closure matrix

| Gate | Owner task | Required evidence | Initial status |
|---|---|---|---|
| Governance trust boundary | PM-125/admin | CODEOWNERS + ruleset export + malicious gate-edit PR blocked | BLOCKED |
| Required PR gate | PM-125 | Exact required context + negative merge lock | BLOCKED |
| PR scan gates | PM-125/126 | Gitleaks, AMD64+ARM64 Trivy, IaC, SAST runs | BLOCKED |
| SBOM release gate | PM-127 | Per-platform predicate/index/provenance attestations | BLOCKED |
| Signature admission | PM-127/128 | Enforce/Ready + signed pass + actual unsigned reject | BLOCKED |
| Immutable dependencies | PM-129 | Dynamic Actions/Docker audit clean + freshness automation | BLOCKED |
| Full provenance | PM-129/130 | One-Pod `trace-result.json` PASS | BLOCKED |
| Scoped build/deploy | PM-131 | Positive/negative contract evidence | BLOCKED |
| Production health | PM-132 | Smoke, telemetry, admission latency/error evidence | BLOCKED |
| Decision/sign-off | PM-132 | ADR owner/reviewer/mentor approval | BLOCKED |

Mandate 10 chỉ `Done` khi tất cả hàng là `PASS`, exact `FINAL_MAIN_SHA` vẫn current và không có exception hết hạn hoặc evidence ambiguity.

## 7. ADR trade-offs bắt buộc

| Decision | Benefit | Cost/residual risk |
|---|---|---|
| Aggregate required check | Stable context; no path-skip deadlock | Single point of trust; protected by governance controls |
| Separate read-only PR workflow | No production credentials in untrusted PR | Build/scan duplicated at release |
| Dual-platform PR scan | HIGH/CRITICAL blocked before merge on all publish platforms | More CI time/QEMU/storage |
| CycloneDX per platform | No ARM64 package blind spot | More attestations and lookup complexity |
| Signature-only admission first | Lower latency/syntax risk | Admission does not directly require SBOM predicate |
| Scope `techx-tf3` | Lower blast radius | Other namespaces not covered |
| Exact external allow-list | Rejects unreviewed digest | Every image update needs review flow |
| SHA/digest pins | Prevents dependency substitution | Requires active update automation |
| 90-day Actions retention | Meets near-term audit window | Not durable production archive |
| Fail-closed ambiguity | Prevents selecting wrong run/PR/artifact | Legitimate reruns may require explicit disambiguation |
| Custom trace chain | Connects artifact to both approvals and live revision | Not a claim of SLSA build provenance level |

ADR must include owner, approvers, review date, rollback, accepted exceptions with expiry, and the two D5 scope statements.

## 8. Primary references

- [GitHub ruleset rules and expected status-check source](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- [GitHub CODEOWNERS and required code-owner review](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
- [GitHub protected branches and unique job-name warning](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [Sigstore Cosign custom image attestations](https://docs.sigstore.dev/cosign/signing/signing_with_containers/)
