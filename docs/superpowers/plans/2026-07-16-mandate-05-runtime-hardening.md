# Mandate 05 Runtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Loại bỏ cấu hình runtime nguy hiểm khỏi toàn bộ workload TF3, sau đó dùng Kyverno admission policy để từ chối workload chạy root, dùng image trôi, thiếu resources hoặc thiếu security context mà không gây gián đoạn storefront.

**Architecture:** Remediate workload trước và enforce admission sau. Bốn nhóm policy độc lập (`resources`, `images`, `non-root`, `runtime-security-context`) bắt đầu ở Audit; mỗi policy chỉ chuyển sang Enforce khi Helm-rendered manifests và live PolicyReport đều sạch. Workload được harden theo các wave độc lập, từ stateless ngoài critical path đến browse/checkout rồi stateful singleton.

**Tech Stack:** Kubernetes 1.34, EKS, Helm, ArgoCD, Argo Rollouts, Kyverno 1.13.2, Terraform-managed AWS infrastructure, ECR digest pinning, Prometheus/Grafana.

## Global Constraints

- Deadline directive: thứ Sáu 17/07/2026.
- Không gỡ, vô hiệu hóa hoặc đổi hướng flagd/OpenFeature; không đổi URI/token trong `values-flagd-sync.yaml`.
- Không commit secret thật, AWS credential, flagd token hoặc LLM API key.
- Không patch trực tiếp production; mọi thay đổi đi qua branch, PR và ArgoCD.
- Không push thẳng `main`; status check `gitleaks` phải xanh.
- Không đổi image application version và runtime security context trong cùng rollout trừ khi image mới là điều kiện bắt buộc để chạy non-root.
- Mỗi wave chỉ rollout một service tại một thời điểm.
- Stateful singleton phải rehearsal quyền volume trước production.
- Kyverno Enforce và PSA `restricted` không được bật trong cùng cutover.
- Checkout SLO phải giữ `>=99.0%`; browse/cart `>=99.5%`; browse p95 `<1s`.
- Mọi exception phải hẹp theo workload/rule, có owner, lý do, ngày hết hạn và kế hoạch loại bỏ; exception vĩnh viễn không được tính là pass mandate.

---

## Current Baseline (16/07/2026)

- Kyverno admission/background/reports/cleanup controller đều Running; hai ClusterPolicy hiện tại Ready nhưng ở `Audit`.
- Namespace `techx-tf3` mới có PSA `audit=baseline,warn=baseline`; chưa enforce.
- Live inventory: 56 container/init-container trên 44 pod.
- Resources: 56/56 có đủ CPU/memory requests và limits.
- `runAsNonRoot: true` còn thiếu trên 40/56 container, liên quan 32/44 pod.
- Quan sát runtime xác nhận ít nhất 9 application container chạy UID 0: `ad`, `aiops-engine`, hai `cart`, hai `currency`, `email`, `llm`, `load-generator`.
- 7 init-container còn dùng `busybox:latest` hoặc `busybox` không tag.
- 38/56 container chưa drop `ALL`; 50/56 chưa có `RuntimeDefault` ở pod/container level.
- Live PolicyReport có 56 fail results trên các pod hiện hành.
- Vì các vi phạm trên, bật Enforce toàn bộ ngay lập tức là **NO-GO**.

## File Map

- Modify: `gitops/policies/kyverno/require-resource-requests.yaml` — kiểm đủ CPU/RAM request/limit trên container, init-container và ephemeral-container.
- Modify: `gitops/policies/kyverno/baseline-security-context.yaml` — giữ các rule runtime security context, bỏ exception rộng và bổ sung coverage.
- Create: `gitops/policies/kyverno/disallow-floating-images.yaml` — cấm `latest` và image không tag/digest.
- Create: `gitops/policies/kyverno/require-non-root.yaml` — bắt buộc `runAsNonRoot: true` và cấm UID 0.
- Create: `gitops/policies/kyverno/tests/` — positive/negative test resources cho policy CLI và mentor demo.
- Modify: `phase3 - information/techx-corp-chart/values.yaml` — pin init image và khai báo security context mặc định/per-component.
- Modify: `phase3 - information/deploy/values-prod.yaml` — production digest/security overrides, Kafka volume permissions.
- Modify as required: `phase3 - information/techx-corp-platform/src/*/Dockerfile` — tạo user/group cố định và đặt `USER` cho image đang chạy root.
- Create: `scripts/audit-runtime-hardening.sh` — inventory resources, image, UID/security fields và PolicyReport.
- Create: `scripts/test-mandate-05-policies.sh` — render manifests và chạy policy tests.
- Create: `docs/adr/0008-mandate-05-runtime-admission-hardening.md` — quyết định, cutover, exception và chữ ký.
- Create: `docs/runbooks/mandate-05-admission-demo.md` — mentor demo, positive control, rollback.
- Create: `docs/evidence/mandate-05/README.md` — index evidence, không lưu secret/log nhạy cảm.

---

### Task 1: Freeze Scope and Capture a Reproducible Baseline

**Files:**
- Create: `scripts/audit-runtime-hardening.sh`
- Create: `docs/evidence/mandate-05/README.md`

**Interfaces:**
- Consumes: live namespace `techx-tf3`, Kyverno PolicyReports, SSM tunnel on `localhost:8443`.
- Produces: a non-mutating audit command and dated evidence index used by every later gate.

- [ ] **Step 1: Create an isolated branch/worktree**

Run from the clean primary checkout:

```bash
git fetch origin
git worktree add ../Phase3-TF3-M05 -b feat/mandate-05-runtime-hardening origin/main
```

Expected: new worktree on `feat/mandate-05-runtime-hardening`; do not copy `ssm_tunnel.log`, credentials or untracked local files.

- [ ] **Step 2: Implement the read-only audit script**

The script must use `set -euo pipefail`, accept namespace as `${1:-techx-tf3}`, and print these counters from live Pod JSON:

```text
total_containers
missing_run_as_non_root
explicit_uid_zero
missing_allow_privilege_escalation_false
missing_drop_all
missing_runtime_default_seccomp
floating_images
missing_cpu_request
missing_memory_request
missing_cpu_limit
missing_memory_limit
policy_report_failures
```

It must inspect `spec.containers`, `spec.initContainers` and `spec.ephemeralContainers`. It must not exec arbitrary shell from a pod or mutate any object.

- [ ] **Step 3: Verify the script against the current known baseline**

Run:

```bash
bash scripts/audit-runtime-hardening.sh techx-tf3
```

Expected before remediation: resources counters are zero; security/image/policy failure counters are non-zero.

- [ ] **Step 4: Capture operational baseline**

Run and copy sanitized output references into the evidence index:

```bash
kubectl -n techx-tf3 get pods -o wide
kubectl get clusterpolicy -o wide
kubectl -n techx-tf3 get policyreport
kubectl -n argocd get application techx-corp techx-infrastructure-app kyverno kyverno-policies
kubectl -n techx-tf3 get hpa,pdb
```

Capture Grafana screenshots or query results for browse success, browse p95, cart success and checkout success. Never commit tokens, request headers or credential-bearing URLs.

- [ ] **Step 5: Commit baseline tooling**

```bash
git add scripts/audit-runtime-hardening.sh docs/evidence/mandate-05/README.md
git commit -m "docs: add mandate 05 runtime hardening baseline audit"
```

**Acceptance criteria:**
- Audit is read-only and covers normal/init/ephemeral containers.
- Evidence index records time, AWS account, namespace and commands without secrets.
- Baseline makes the current NO-GO for global Enforce reproducible.

---

### Task 2: Add Policy Tests Before Changing Admission Behavior

**Files:**
- Create: `gitops/policies/kyverno/tests/pass/compliant-pod.yaml`
- Create: `gitops/policies/kyverno/tests/fail/root-pod.yaml`
- Create: `gitops/policies/kyverno/tests/fail/latest-image-pod.yaml`
- Create: `gitops/policies/kyverno/tests/fail/untagged-image-pod.yaml`
- Create: `gitops/policies/kyverno/tests/fail/missing-resources-pod.yaml`
- Create: `gitops/policies/kyverno/tests/fail/unsafe-security-context-pod.yaml`
- Create: `gitops/policies/kyverno/tests/fail/unsafe-init-container.yaml`
- Create: `gitops/policies/kyverno/tests/fail/unsafe-rollout.yaml`
- Create: `scripts/test-mandate-05-policies.sh`

**Interfaces:**
- Consumes: policy YAML from `gitops/policies/kyverno/`.
- Produces: deterministic pass/fail contract for Task 3 policy implementation.

- [ ] **Step 1: Write the compliant fixture**

Use a pinned BusyBox digest and this complete container security/resource contract:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 65532
  runAsGroup: 65532
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
  seccompProfile:
    type: RuntimeDefault
resources:
  requests: {cpu: 10m, memory: 16Mi}
  limits: {cpu: 50m, memory: 32Mi}
```

- [ ] **Step 2: Write one isolated negative fixture per rule**

Each fixture must violate only the rule named by its filename. `unsafe-init-container.yaml` must keep the application container compliant while its init-container violates all runtime controls. `unsafe-rollout.yaml` must use `argoproj.io/v1alpha1/Rollout` so the test proves custom controller coverage.

- [ ] **Step 3: Implement the test script**

The script must:

1. Fail if Kyverno CLI is absent and print the supported install command/version.
2. Run policy tests for every fixture.
3. Run `kubectl apply --dry-run=server` only when a cluster connection is available.
4. Exit non-zero when a negative fixture passes or the positive fixture fails.

- [ ] **Step 4: Run tests and confirm they fail against missing policies**

```bash
bash scripts/test-mandate-05-policies.sh
```

Expected: image and non-root negative tests fail the test harness because no matching policy exists yet. This is the required red phase.

- [ ] **Step 5: Commit test contract**

```bash
git add gitops/policies/kyverno/tests scripts/test-mandate-05-policies.sh
git commit -m "test: define mandate 05 admission policy contract"
```

**Acceptance criteria:**
- Every mandate rule has an independent negative test.
- Init-container and Argo Rollout bypasses are explicitly tested.
- Positive fixture proves policies do not reject compliant workloads.

---

### Task 3: Implement Complete Kyverno Policies in Audit Mode

**Files:**
- Modify: `gitops/policies/kyverno/require-resource-requests.yaml`
- Modify: `gitops/policies/kyverno/baseline-security-context.yaml`
- Create: `gitops/policies/kyverno/disallow-floating-images.yaml`
- Create: `gitops/policies/kyverno/require-non-root.yaml`

**Interfaces:**
- Consumes: test contract from Task 2.
- Produces: four independent `ClusterPolicy` resources, all initially `validationFailureAction: Audit`.

- [ ] **Step 1: Complete resource validation**

Require all four fields for every normal/init/ephemeral container:

```yaml
requests:
  cpu: "?*"
  memory: "?*"
limits:
  cpu: "?*"
  memory: "?*"
```

- [ ] **Step 2: Add floating-image validation**

Reject both forms:

```text
*:latest
image-name-without-tag-or-@sha256
```

Allow a fixed tag or digest to match the directive; document digest as the production preference.

- [ ] **Step 3: Add non-root validation**

Require `runAsNonRoot: true` and reject explicit `runAsUser: 0` at pod and container levels. A container-level UID must not override a safe pod-level setting with zero.

- [ ] **Step 4: Complete runtime context validation**

Require:

```yaml
allowPrivilegeEscalation: false
capabilities.drop: ["ALL"]
seccompProfile.type: RuntimeDefault
```

Do not require `readOnlyRootFilesystem` for Mandate #5; keep it as a separately tracked audit recommendation because stateful and observability write paths require individual validation.

- [ ] **Step 5: Cover Argo Rollouts explicitly**

Do not rely only on Kyverno Pod-controller autogeneration. Add explicit matching/validation for `Rollout` pod templates so Argo receives an immediate admission error instead of accepting a Rollout whose child pods can never start.

- [ ] **Step 6: Remove broad permanent exceptions**

Delete workload-name exclusions for `currency`, `llm` and `product-reviews` from the final Enforce path. Temporary Audit findings are acceptable; permanent exclusions are not. Retain system namespace exclusions only where TF3 does not own the third-party lifecycle, and document scope in the ADR.

- [ ] **Step 7: Run policy tests**

```bash
bash scripts/test-mandate-05-policies.sh
```

Expected: all negative fixtures are reported as violations; compliant fixture passes; every policy remains Audit.

- [ ] **Step 8: Commit Audit policies**

```bash
git add gitops/policies/kyverno
git commit -m "feat: audit mandate 05 runtime admission controls"
```

**Acceptance criteria:**
- Policies cover all container types and Argo Rollout templates.
- All policy tests pass.
- No policy is Enforce yet.
- No broad workload exception can remain in the final state.

### Checkpoint A: Merge Audit-Only Foundation

- [ ] Open PR containing Tasks 1–3 only.
- [ ] Confirm `gitleaks`, YAML validation and policy tests pass.
- [ ] Merge and let ArgoCD sync; do not sync manually.
- [ ] Confirm all Kyverno policies Ready and all storefront pods unchanged.
- [ ] Confirm PolicyReport enumerates violations without admission rejection.

---

### Task 4: Pin Every Floating Init Image

**Files:**
- Modify: `phase3 - information/techx-corp-chart/values.yaml`
- Modify: `phase3 - information/deploy/values-prod.yaml`
- Modify: `docs/release-notes-v1.md`

**Interfaces:**
- Consumes: trusted BusyBox version/digest verified in the registry.
- Produces: zero `latest` or untagged images in rendered/live TF3 workloads.

- [ ] **Step 1: Resolve and record the approved digest**

Resolve the exact digest for the chosen BusyBox version and record tag plus digest in the release inventory. Do not copy a digest from memory; verify it against the registry used by the cluster.

- [ ] **Step 2: Replace all floating references**

Replace every `busybox:latest` and bare `busybox` used by `wait-for-kafka`, `wait-for-valkey-cart` and flagd `init-config` with the approved digest. Do not change commands, environment variables, flagd source, URI or token wiring.

- [ ] **Step 3: Render and scan manifests**

```bash
helm lint "phase3 - information/techx-corp-chart" \
  -f "phase3 - information/deploy/values-prod.yaml"
helm template techx-corp "phase3 - information/techx-corp-chart" \
  -n techx-tf3 \
  -f "phase3 - information/deploy/values-prod.yaml" > /tmp/mandate-05-rendered.yaml
rg -n 'image:.*(:latest|busybox[" ]*$)' /tmp/mandate-05-rendered.yaml
```

Expected: `helm lint` succeeds and `rg` returns no matches.

- [ ] **Step 4: Commit and deploy through ArgoCD**

```bash
git add "phase3 - information/techx-corp-chart/values.yaml" \
  "phase3 - information/deploy/values-prod.yaml" docs/release-notes-v1.md
git commit -m "fix: pin mandate 05 init container images"
```

- [ ] **Step 5: Verify each affected workload sequentially**

For each affected service, wait for Ready before proceeding:

```bash
kubectl -n techx-tf3 get pods
kubectl -n techx-tf3 get events --sort-by=.lastTimestamp | tail -n 50
bash scripts/audit-runtime-hardening.sh techx-tf3
```

Expected: init containers Complete, no `ImagePullBackOff`, floating image count zero, flagd remains operational.

**Acceptance criteria:**
- Rendered and live floating-image count is zero.
- Flagd behavior is unchanged.
- Browse/cart/checkout smoke tests pass after rollout.

---

### Task 5: Enforce Resources and Image Immutability

**Files:**
- Modify: `gitops/policies/kyverno/require-resource-requests.yaml`
- Modify: `gitops/policies/kyverno/disallow-floating-images.yaml`

**Interfaces:**
- Consumes: zero resource/image violations from Tasks 1 and 4.
- Produces: the first two active admission guardrails.

- [ ] **Step 1: Confirm zero pre-existing violations**

```bash
bash scripts/audit-runtime-hardening.sh techx-tf3
```

Expected: all resource-missing counters and `floating_images` equal zero. Stop if not zero.

- [ ] **Step 2: Change only resource policy to Enforce**

Set `validationFailureAction: Enforce` only in `require-resource-requests.yaml`, commit, merge and wait for ArgoCD.

- [ ] **Step 3: Run admission and SLO checks**

```bash
kubectl apply --dry-run=server -f gitops/policies/kyverno/tests/pass/compliant-pod.yaml
kubectl apply --dry-run=server -f gitops/policies/kyverno/tests/fail/missing-resources-pod.yaml
```

Expected: positive accepted; missing-resources denied. Observe SLO and Argo health for at least 15 minutes.

- [ ] **Step 4: Change only floating-image policy to Enforce**

Repeat the isolated commit/merge/observe cycle for `disallow-floating-images.yaml`.

- [ ] **Step 5: Verify negative image admission**

```bash
kubectl apply --dry-run=server -f gitops/policies/kyverno/tests/fail/latest-image-pod.yaml
kubectl apply --dry-run=server -f gitops/policies/kyverno/tests/fail/untagged-image-pod.yaml
```

Expected: both denied by the image policy.

**Rollback:** Revert only the commit changing the affected policy back to Audit; do not delete Kyverno or bypass ArgoCD.

**Acceptance criteria:**
- Resource and image policies Enforce independently.
- Positive control passes; both negative controls fail.
- No workload rollout or SLO regression occurs.

---

### Task 6: Convert Non-Critical Stateless Images to Non-Root

**Files:**
- Modify as applicable: service Dockerfiles for `ad`, `email`, `llm`, `load-generator`, `aiops-engine`.
- Modify: `phase3 - information/techx-corp-chart/values.yaml`
- Modify: `phase3 - information/deploy/values-prod.yaml`
- Modify: `docs/release-notes-v1.md`

**Interfaces:**
- Consumes: Audit-mode runtime/non-root policies.
- Produces: non-root images and pinned digests for Wave A services.

- [ ] **Step 1: Inventory each image write path**

For each service list executable, working directory, config/secret paths, writable cache/temp/log paths, listening ports and current runtime UID. Do not assume `/tmp` is the only write path.

- [ ] **Step 2: Add a fixed runtime user to one image**

Use the package-manager-appropriate equivalent of this contract:

```dockerfile
RUN addgroup --system --gid 10001 app \
 && adduser --system --uid 10001 --gid 10001 app \
 && chown -R 10001:10001 /app
USER 10001:10001
```

Do not copy this syntax verbatim into non-Debian images; preserve the service's existing base-image conventions.

- [ ] **Step 3: Test the image locally**

```bash
docker run --rm --user 10001:10001 <new-image-ref> id -u
```

Expected: non-zero UID and the service starts with its normal entrypoint. Add a writable `emptyDir` only for a proven runtime write path.

- [ ] **Step 4: Add the Kubernetes security contract**

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
podSecurityContext:
  seccompProfile:
    type: RuntimeDefault
```

- [ ] **Step 5: Build, scan, push and pin digest**

Use the existing scoped ECR workflow. Record the new digest in `values-prod.yaml` and the release inventory; never bump the shared default tag for a single-service build.

- [ ] **Step 6: Roll out exactly one service**

Wait for ArgoCD, readiness and SLO gates. Run the audit script and service-specific smoke test. Only then repeat Steps 1–6 for the next Wave A service.

- [ ] **Step 7: Commit one service per reviewable change**

Use messages such as:

```text
fix(ad): run runtime image as non-root
fix(email): run runtime image as non-root
```

**Acceptance criteria:**
- Every Wave A container runs a declared non-zero UID.
- No broad policy exception is added.
- Each service can be reverted independently.

---

### Task 7: Harden Browse and Checkout Stateless Workloads in Waves

**Files:**
- Modify as applicable: Dockerfiles for affected services.
- Modify: `phase3 - information/techx-corp-chart/values.yaml`
- Modify: `phase3 - information/deploy/values-prod.yaml`
- Modify: `docs/release-notes-v1.md`

**Interfaces:**
- Consumes: proven Task 6 image/security pattern.
- Produces: non-root browse and transaction paths while preserving SLO.

- [ ] **Step 1: Wave B browse services sequentially**

Order: `currency` → `recommendation` → `product-reviews` → `product-catalog` → `frontend` → `frontend-proxy`.

Apply the same per-service cycle from Task 6. After every rollout verify browse success and p95. Do not rollout `frontend` and `frontend-proxy` together.

- [ ] **Step 2: Wave C transaction services sequentially**

Order: `quote` → `shipping` → `payment` → `fraud-detection` → `accounting` → `cart` → `checkout`.

After each rollout execute:

```text
browse -> add cart -> read cart -> checkout -> Kafka publish -> accounting consume
```

- [ ] **Step 3: Enforce per-rollout availability gates**

Before each critical rollout confirm replicas, PDB, readiness and current error budget. Abort when a singleton or missing readiness would make zero-downtime impossible; fix that prerequisite in a separate change.

- [ ] **Step 4: Apply rollback triggers**

Immediately revert the current service change on `CreateContainerConfigError`, `CrashLoopBackOff`, permission errors, failed readiness, elevated 5xx, checkout `<99.0%`, browse/cart `<99.5%`, browse p95 `>=1s`, or abnormal Kafka consumer lag.

**Acceptance criteria:**
- Browse/cart/checkout critical paths pass end-to-end after every wave.
- All stateless service containers have explicit non-root and runtime security contexts.
- No simultaneous dependency rollout occurs.

---

### Task 8: Rehearse and Harden Stateful Workloads

**Files:**
- Modify: `phase3 - information/deploy/values-prod.yaml`
- Modify as required: chart values/templates governing Kafka, PostgreSQL and Valkey volumes.
- Create: `docs/evidence/mandate-05/stateful-permission-rehearsal.md`

**Interfaces:**
- Consumes: non-production rehearsal PVC and known image UIDs.
- Produces: evidence that non-root stateful processes can write, restart and retain data.

- [ ] **Step 1: Rehearse Kafka volume permissions**

Use a disposable PVC with the same storage class. Validate this target contract:

```yaml
podSecurityContext:
  runAsUser: 1000
  runAsGroup: 1000
  fsGroup: 1000
  fsGroupChangePolicy: OnRootMismatch
  seccompProfile:
    type: RuntimeDefault
```

The init-container must run UID/GID 1000, create `/var/lib/kafka/data`, write a file, restart and read it back. Do not alter the production PVC during rehearsal.

- [ ] **Step 2: Replace root Kafka initialization**

Remove `runAsUser: 0` and recursive root `chown` only after rehearsal passes. Preserve `CLUSTER_ID`, `KAFKA_LOG_DIRS`, `publishNotReadyAddresses`, Recreate strategy and all existing reliability fixes.

- [ ] **Step 3: Harden PostgreSQL and Valkey separately**

For each datastore verify its documented image UID, PVC data-directory ownership, write/read, restart persistence and readiness. Do not change image version and UID/security context in the same rollout.

- [ ] **Step 4: Roll out stateful changes one at a time**

Use a dedicated maintenance observation window even though the target is no user-visible downtime. Validate application dependency behavior, not just Pod `Running`.

**Acceptance criteria:**
- No stateful init/application container runs UID 0.
- Kafka registration, Postgres queries and Valkey cart persistence pass after restart.
- Existing BTC/flagd and Kafka reliability configuration remains intact.

---

### Task 9: Harden Observability Workloads Without Losing Evidence

**Files:**
- Modify: relevant observability sections in `phase3 - information/techx-corp-chart/values.yaml` and `phase3 - information/deploy/values-prod.yaml`.

**Interfaces:**
- Consumes: vendor-documented image UIDs and write paths.
- Produces: non-root observability stack that continues collecting evidence for the mandate.

- [ ] **Step 1: Apply changes in dependency-safe order**

Order: OTel Collector → Prometheus → Jaeger → Grafana → OpenSearch. Change one workload at a time.

- [ ] **Step 2: Validate writable paths**

Check cache, plugins, dashboards, TSDB, trace/log data and temp directories. Mount `emptyDir` or set `fsGroup` only for observed requirements.

- [ ] **Step 3: Verify telemetry continuity**

After each rollout confirm new metrics, traces and logs arrive with current timestamps. A Ready pod without new telemetry is a failed rollout.

**Acceptance criteria:**
- Observability containers are non-root and meet runtime policy.
- No evidence gap occurs during the final mandate verification window.

---

### Task 10: Enforce Runtime Security Policies One at a Time

**Files:**
- Modify: `gitops/policies/kyverno/baseline-security-context.yaml`
- Modify: `gitops/policies/kyverno/require-non-root.yaml`

**Interfaces:**
- Consumes: zero current runtime/non-root violations.
- Produces: active rejection of future unsafe runtime manifests.

- [ ] **Step 1: Prove the precondition**

```bash
bash scripts/audit-runtime-hardening.sh techx-tf3
```

Expected before proceeding:

```text
missing_run_as_non_root=0
explicit_uid_zero=0
missing_allow_privilege_escalation_false=0
missing_drop_all=0
missing_runtime_default_seccomp=0
floating_images=0
all resource missing counters=0
policy_report_failures=0
```

- [ ] **Step 2: Enforce privilege escalation rule**

Commit/merge only this action change, verify the matching negative test is denied, then observe Argo/SLO for at least 15 minutes.

- [ ] **Step 3: Enforce capability rule**

Repeat the isolated cutover and observation cycle.

- [ ] **Step 4: Enforce seccomp rule**

Repeat the isolated cutover and observation cycle.

- [ ] **Step 5: Enforce non-root rule last**

Repeat the isolated cutover and observation cycle. Verify both `runAsNonRoot: false` and explicit UID 0 are denied.

- [ ] **Step 6: Keep PSA restricted out of this cutover**

Leave PSA at audit/warn during Mandate #5 enforcement. Treat PSA `restricted` Enforce as a separate defense-in-depth decision after Kyverno stability is proven.

**Rollback:** Revert only the last action change to Audit through GitOps. Do not delete policy, uninstall Kyverno or add a namespace-wide bypass.

**Acceptance criteria:**
- All four mandate policy groups are Enforce.
- Positive control remains accepted.
- Existing Argo Rollout/Deployment updates are not blocked.

---

### Task 11: Write and Sign the ADR

**Files:**
- Create: `docs/adr/0008-mandate-05-runtime-admission-hardening.md`

**Interfaces:**
- Consumes: final policy scope, rollout evidence and any temporary exception history.
- Produces: signed decision record required by the directive.

- [ ] **Step 1: Record the decision**

ADR must include:

- Context and threat model: privilege escalation, supply-chain drift and resource exhaustion.
- Why Kyverno was retained instead of adding another admission service.
- Exact policy/rule names and namespace/controller scope.
- Rules in Enforce and any rule intentionally left Audit.
- Audit → Enforce gates and timeline.
- Stateful volume-permission design.
- Why `readOnlyRootFilesystem` is not part of the mandatory Enforce set unless individually verified.
- Exception lifecycle with owner and expiry; final pass requires no exception to the four directive requirements.
- SLO gates and rollback mechanism.
- Cost statement: no new infrastructure service; only existing in-cluster policy/config.
- Flagd non-interference statement.
- Named author/reviewer/approver signatures and dates.

- [ ] **Step 2: Cross-check ADR against live state**

Every policy named Enforce in the ADR must be live Ready and actually reject its negative fixture. Do not describe intended state as completed state.

- [ ] **Step 3: Commit signed ADR**

```bash
git add docs/adr/0008-mandate-05-runtime-admission-hardening.md
git commit -m "docs: record mandate 05 runtime admission decision"
```

**Acceptance criteria:**
- ADR is implementation-accurate, signed and contains no unresolved placeholder.

---

### Task 12: Mentor Admission Demo and Final Evidence Pack

**Files:**
- Create: `docs/runbooks/mandate-05-admission-demo.md`
- Modify: `docs/evidence/mandate-05/README.md`

**Interfaces:**
- Consumes: Enforce policies and test fixtures.
- Produces: reproducible mentor demonstration and final pass evidence.

- [ ] **Step 1: Document the demo prerequisites**

Require correct AWS identity, SSM tunnel, mentor RBAC for creating a Pod in the designated demo scope, and all ClusterPolicies Ready. The runbook must not contain credentials.

- [ ] **Step 2: Have the mentor apply isolated negative tests without dry-run**

```bash
kubectl apply -f gitops/policies/kyverno/tests/fail/root-pod.yaml
kubectl apply -f gitops/policies/kyverno/tests/fail/latest-image-pod.yaml
kubectl apply -f gitops/policies/kyverno/tests/fail/missing-resources-pod.yaml
```

Expected for each: `admission webhook ... denied the request` naming the correct policy/rule.

- [ ] **Step 3: Prove rejected objects do not exist**

```bash
kubectl -n techx-tf3 get pod mandate-05-root-test
kubectl -n techx-tf3 get pod mandate-05-latest-test
kubectl -n techx-tf3 get pod mandate-05-resources-test
```

Expected: `NotFound` for all three.

- [ ] **Step 4: Run positive control**

```bash
kubectl apply -f gitops/policies/kyverno/tests/pass/compliant-pod.yaml
kubectl -n techx-tf3 wait --for=condition=Ready pod/mandate-05-compliant --timeout=60s
kubectl -n techx-tf3 delete pod mandate-05-compliant
```

Expected: apply and Ready succeed; cleanup succeeds.

- [ ] **Step 5: Capture final live health**

```bash
bash scripts/audit-runtime-hardening.sh techx-tf3
kubectl get clusterpolicy -o wide
kubectl -n techx-tf3 get pods
kubectl -n argocd get application
```

Attach sanitized SLO evidence for browse/cart/checkout and proof that flagd remains connected and functional.

- [ ] **Step 6: Complete final pass matrix**

```text
Policies Ready                         PASS
PolicyReport failures = 0              PASS
Runtime UID 0 = 0                      PASS
Floating images = 0                    PASS
Missing resources = 0                  PASS
Negative tests rejected                PASS
Positive test accepted                 PASS
All production pods Ready              PASS
ArgoCD Healthy/Synced                  PASS
Browse/cart/checkout SLO               PASS
Flagd operational                      PASS
ADR signed                             PASS
```

- [ ] **Step 7: Commit evidence index and runbook**

```bash
git add docs/runbooks/mandate-05-admission-demo.md docs/evidence/mandate-05/README.md
git commit -m "docs: add mandate 05 mentor admission evidence"
```

**Acceptance criteria:**
- Mentor personally observes three independent admission denials.
- Positive control proves the policies are not blocking compliant work.
- Final evidence demonstrates both zero current violations and prevention of recurrence.

---

## Mandatory Checkpoints

### Checkpoint A — Audit Policies Live

- Policies Ready in Audit.
- Test suite catches all negative fixtures.
- No production workload restarted or blocked.

### Checkpoint B — Low-Risk Enforce

- Resource and image live violations are zero.
- Resource/image policies Enforce.
- SLO and Argo remain healthy.

### Checkpoint C — Stateless Runtime Clean

- All stateless workloads use non-zero UID and complete runtime security context.
- Browse/cart/checkout end-to-end passes.

### Checkpoint D — Stateful and Observability Clean

- Volume rehearsal evidence exists.
- Kafka/Postgres/Valkey restart and persistence checks pass.
- Metrics/logs/traces continue arriving.

### Checkpoint E — Full Enforce and Mentor Pass

- Audit counters and PolicyReport failures are zero.
- All mandatory policies Enforce.
- Negative and positive mentor tests produce expected results.
- ADR is signed and evidence pack complete.

## Risk Register

| Risk | Impact | Mitigation | Rollback |
|---|---|---|---|
| Image defaults to UID 0 | Pod cannot start with `runAsNonRoot` | Fix Dockerfile and test image before manifest change | Revert service image/security commit |
| Non-root cannot write runtime path | CrashLoop or partial failure | Inventory write paths; chown at build; narrow `emptyDir`/`fsGroup` | Revert current service only |
| Kafka root init removal breaks EBS permissions | Kafka unavailable, checkout event path affected | Disposable-PVC rehearsal; preserve KRaft settings; do stateful last | Revert Kafka GitOps commit |
| Kyverno rule misses init-container/Rollout | Unsafe manifest bypasses policy | Dedicated negative fixtures for both | Fix policy while still Audit |
| Enforce blocks existing Argo reconciliation | Rollout Degraded | Require zero PolicyReport failures and server dry-run before action change | Revert action to Audit |
| Simultaneous policy changes obscure root cause | Slow recovery | One policy action per commit/cutover | Revert last action only |
| Observability hardening stops telemetry | Loss of SLO/evidence | Sequential rollout and current-timestamp telemetry checks | Revert current observability workload |
| Broad exception remains after deadline | Mandate fails despite apparent Enforce | No namespace-wide/permanent exceptions; exception expiry in ADR | Remove exception after remediation |
| Flagd init image/security change alters incident channel | Disqualification | Pin artifact only; preserve command/source/URI/token; verify sync | Immediate Git revert |

## Execution Order and Parallelism

- Tasks 1–3 are sequential because policy tests define the contract implemented by policies.
- Task 4 must finish before image policy Enforce in Task 5.
- Tasks 6 and documentation preparation may be split across team owners, but production rollouts remain sequential.
- Tasks 7–9 may have independent image/Dockerfile work in parallel; shared Helm values edits require one integrator and serialized merges.
- Task 10 requires Tasks 6–9 and a zero-violation audit.
- Tasks 11–12 consume final live state and must not claim future/intended results as completed evidence.

## Final Go/No-Go Rule

The team may mark Mandate #5 complete only when every Checkpoint E item is PASS. A ClusterPolicy showing `Enforce` is insufficient if existing workloads still violate it, an exception bypasses the rule, or mentor has not observed independent rejection for root, floating image and missing resources.
