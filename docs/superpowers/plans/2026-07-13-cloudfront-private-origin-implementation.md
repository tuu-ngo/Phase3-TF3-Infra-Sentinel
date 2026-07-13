# CloudFront Private Origin Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CloudFront the only public storefront entry point by migrating to an internal ALB through CloudFront VPC Origin, while blocking operations UIs and preserving zero downtime.

**Architecture:** Terraform owns the internal-ALB security boundary, WAF, VPC Origin, staging distribution, deployment policy, and primary distribution phase. ArgoCD owns a standalone internal Ingress through a persistent `techx-edge` Application; the current public Helm Ingress remains until post-cutover cleanup.

**Tech Stack:** Terraform 1.15.4, AWS provider 5.100.0, AWS CloudFront VPC Origin, AWS WAFv2, AWS Load Balancer Controller 3.4.1, Kubernetes Ingress v1, ArgoCD, GitHub Actions.

## Global Constraints

- Never modify or remove flagd, `values-flagd-sync.yaml`, sync token wiring, or Envoy fault injection.
- Never commit real AWS credentials, flagd tokens, LLM keys, or the CloudFront staging selector value.
- Production EKS remains private-only and is accessed through the SSM bastion.
- Terraform plan/apply runs only on `deploy/account-migration-gitops` during this migration.
- Each phase uses a separately reviewed saved plan; bootstrap, staging, cutover, and cleanup are never combined into one apply.
- Public ALB cleanup is forbidden until the 60-minute observation gate passes and steady state is merged to `main`.
- Preserve user-owned changes in `infra/.terraform.lock.hcl` and `AGENTS.md`.

---

### Task 1: Add Edge Phase Contract and Terraform Tests

**Files:**
- Modify: `infra/modules/edge/variables.tf`
- Modify: `infra/modules/edge/versions.tf`
- Create: `infra/modules/edge/tests/phase_contract.tftest.hcl`

**Interfaces:**
- Consumes: `cluster_name`, public ALB DNS, VPC ID, private ALB stable name.
- Produces: `edge_phase` contract with values `public`, `waf`, `staging`, `private`; sensitive `cloudfront_staging_selector` used only in `staging`.

- [ ] **Step 1: Add failing phase-contract tests**

Create tests that call the module with mocked AWS data and assert:

```hcl
mock_provider "aws" {}

mock_provider "aws" {
  alias = "us_east_1"
}

run "rejects_unknown_phase" {
  command = plan
  variables {
    cluster_name                = "techx-corp-tf3"
    frontend_alb_dns_name       = "public.example.elb.amazonaws.com"
    vpc_id                      = "vpc-00000000000000000"
    private_alb_name            = "techx-tf3-frontend-internal"
    private_subnet_ids          = ["subnet-a", "subnet-b", "subnet-c"]
    edge_phase                  = "invalid"
    cloudfront_staging_selector = "test-only"
  }
  expect_failures = [var.edge_phase]
}
```

- [ ] **Step 2: Verify the test fails before the contract exists**

Run:

```bash
terraform -chdir=infra/modules/edge init -backend=false
terraform -chdir=infra/modules/edge test
```

Expected: FAIL because the new variables/provider alias are not defined.

- [ ] **Step 3: Add the phase variables and provider alias**

Add exact validations:

```hcl
variable "edge_phase" {
  description = "Controlled edge migration phase: public, waf, staging, or private."
  type        = string
  default     = "public"

  validation {
    condition     = contains(["public", "waf", "staging", "private"], var.edge_phase)
    error_message = "edge_phase must be one of: public, waf, staging, private."
  }
}

variable "cloudfront_staging_selector" {
  description = "Sensitive selector value for header-routed CloudFront staging requests."
  type        = string
  default     = ""
  sensitive   = true
}
```

Declare `configuration_aliases = [aws.us_east_1]` in the module AWS provider requirement.

- [ ] **Step 4: Run contract tests**

Run:

```bash
terraform -chdir=infra/modules/edge fmt -recursive
terraform -chdir=infra/modules/edge test
```

Expected: validation test passes; resource assertions added in Task 2 may still be absent.

- [ ] **Step 5: Commit the contract**

```bash
git add infra/modules/edge/variables.tf infra/modules/edge/versions.tf infra/modules/edge/tests/phase_contract.tftest.hcl
git commit -m "test: define edge migration phase contract"
```

### Task 2: Implement WAF, Internal-Origin Boundary, Staging, and Cutover

**Files:**
- Modify: `infra/modules/edge/main.tf`
- Modify: `infra/modules/edge/outputs.tf`
- Modify: `infra/modules/edge/tests/phase_contract.tftest.hcl`

**Interfaces:**
- Consumes: Task 1 phase variables plus `vpc_id`, `private_subnet_ids`, and stable ALB name.
- Produces: `internal_alb_security_group_id`, `cloudfront_vpc_origin_id`, `cloudfront_distribution_id`, and phase-aware primary/staging configuration.

- [ ] **Step 1: Add failing resource assertions**

Add mocked `plan` runs asserting:

```hcl
assert {
  condition     = aws_wafv2_web_acl.frontend[0].default_action[0].allow != null
  error_message = "WAF must default-allow storefront traffic."
}

assert {
  condition     = aws_security_group.internal_alb[0].vpc_id == "vpc-00000000000000000"
  error_message = "Internal ALB security group must be created in the production VPC."
}

assert {
  condition     = aws_cloudfront_distribution.frontend.web_acl_id != ""
  error_message = "WAF phase must associate the WebACL with CloudFront."
}
```

Add separate runs for `public`, `waf`, `staging`, and `private` resource counts and origin type.

- [ ] **Step 2: Verify resource tests fail**

Run:

```bash
terraform -chdir=infra/modules/edge test
```

Expected: FAIL because WAF, security group, VPC Origin, and staging resources do not exist.

- [ ] **Step 3: Implement phase locals and security boundary**

Use explicit booleans:

```hcl
locals {
  waf_enabled            = contains(["waf", "staging", "private"], var.edge_phase)
  private_origin_enabled = contains(["staging", "private"], var.edge_phase)
  staging_enabled        = var.edge_phase == "staging"
  primary_uses_private   = var.edge_phase == "private"
}
```

Create the internal ALB security group only when WAF/private migration is active. Permit TCP/80 only from `com.amazonaws.global.cloudfront.origin-facing`; keep unrestricted egress for ALB-to-target traffic. Lookup the private ALB by stable name only when `private_origin_enabled` is true.

- [ ] **Step 4: Implement WAF route blocking**

Create `aws_wafv2_web_acl.frontend` with `provider = aws.us_east_1`, scope `CLOUDFRONT`, default allow, and one block rule. The rule is an `or_statement` of four `byte_match_statement` blocks inspecting `uri_path`, applying `LOWERCASE`, and matching `STARTS_WITH` for:

```hcl
operations_path_prefixes = ["/grafana", "/jaeger", "/loadgen", "/feature"]
```

Enable CloudWatch metrics and sampled requests on both ACL and rule.

- [ ] **Step 5: Implement VPC Origin and phase-aware primary origin**

Create `aws_cloudfront_vpc_origin.frontend` only for `staging` and `private`, using the private ALB ARN and HTTP-only port 80. In the primary distribution:

```hcl
origin_id = local.primary_uses_private ? "frontend-private-alb" : "frontend-public-alb"
```

Render `vpc_origin_config` only in `private`; otherwise retain the current `custom_origin_config` and public ALB DNS. Associate WAF whenever `local.waf_enabled` is true.

- [ ] **Step 6: Implement deterministic staging traffic**

Create a staging distribution only in `staging`, with `staging = true`, the same cache/origin-request policies, the same WAF, and VPC Origin. Add a continuous deployment policy with:

```hcl
traffic_config {
  type = "SingleHeader"
  single_header_config {
    header = "aws-cf-cd-techx-private-origin"
    value  = var.cloudfront_staging_selector
  }
}
```

Attach the policy to primary only in `staging`. Add a resource precondition requiring a non-empty selector in that phase.

- [ ] **Step 7: Add outputs without exposing the selector**

Output:

```hcl
output "internal_alb_security_group_id" {
  value = try(aws_security_group.internal_alb[0].id, null)
}

output "cloudfront_vpc_origin_id" {
  value = try(aws_cloudfront_vpc_origin.frontend[0].id, null)
}
```

Never output `cloudfront_staging_selector`.

- [ ] **Step 8: Run module verification**

```bash
terraform -chdir=infra/modules/edge fmt -recursive
terraform -chdir=infra/modules/edge validate
terraform -chdir=infra/modules/edge test
```

Expected: all phase runs PASS.

- [ ] **Step 9: Commit the edge implementation**

```bash
git add infra/modules/edge
git commit -m "feat: add private CloudFront origin phases"
```

### Task 3: Wire Production and Guard CI Inputs

**Files:**
- Modify: `infra/live/production/providers.tf`
- Modify: `infra/live/production/variables.tf`
- Modify: `infra/live/production/main.tf`
- Modify: `infra/live/production/outputs.tf`
- Modify: `infra/live/production/production.auto.tfvars`
- Modify: `.github/workflows/terraform-plan.yml`
- Modify: `.github/workflows/terraform-apply.yml`

**Interfaces:**
- Consumes: Task 2 module interface.
- Produces: production phase fixed in tracked tfvars and staging selector supplied only from GitHub Environment secret `CLOUDFRONT_STAGING_SELECTOR`.

- [ ] **Step 1: Add the us-east-1 provider and root variables**

Add:

```hcl
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags {
    tags = {
      project    = "techx-corp-phase3"
      team       = "TF3"
      managed-by = "terraform"
    }
  }
}
```

Root variables mirror the module's `edge_phase`, `private_alb_name`, and sensitive selector contract.

- [ ] **Step 2: Wire the edge module**

Pass:

```hcl
providers = {
  aws           = aws
  aws.us_east_1 = aws.us_east_1
}

vpc_id                      = module.network.vpc_id
private_subnet_ids           = module.network.private_subnet_ids
edge_phase                   = var.edge_phase
private_alb_name             = var.private_alb_name
cloudfront_staging_selector  = var.cloudfront_staging_selector
```

Expose `internal_alb_security_group_id` and `cloudfront_vpc_origin_id` at root.

- [ ] **Step 3: Set the first safe deployment phase**

Add to `production.auto.tfvars`:

```hcl
edge_phase      = "waf"
private_alb_name = "techx-tf3-frontend-internal"
```

This first plan may add WAF and one security group and update CloudFront WebACL association. It must not reference or replace an ALB.

- [ ] **Step 4: Inject the staging selector without committing it**

At workflow job level add:

```yaml
environment: production
env:
  TF_VAR_cloudfront_staging_selector: ${{ secrets.CLOUDFRONT_STAGING_SELECTOR }}
```

The empty secret is valid in `public`, `waf`, and `private`; Terraform precondition rejects `staging` without it.

- [ ] **Step 5: Verify root and workflows**

```bash
terraform -chdir=infra/live/production fmt -recursive
terraform -chdir=infra/live/production init -backend=false
terraform -chdir=infra/live/production validate
/tmp/actionlint-1.7.12/actionlint .github/workflows/terraform-plan.yml .github/workflows/terraform-apply.yml
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit production wiring**

```bash
git add infra/live/production .github/workflows/terraform-plan.yml .github/workflows/terraform-apply.yml
git commit -m "ci: wire controlled edge migration phases"
```

### Task 4: Add the ArgoCD-Owned Internal Ingress

**Files:**
- Create: `gitops/edge/frontend-proxy-internal-ingress.yaml`
- Create: `gitops/apps/techx-edge.yaml`
- Test: rendered Kubernetes schema and server-side dry run through the SSM tunnel.

**Interfaces:**
- Consumes: Terraform-managed security group Name tag `techx-corp-tf3-internal-alb` and existing `frontend-proxy:8080` Service.
- Produces: stable internal ALB `techx-tf3-frontend-internal` without changing the existing Helm Ingress.

- [ ] **Step 1: Write the standalone Ingress**

Use:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: frontend-proxy-internal
  namespace: techx-tf3
  annotations:
    alb.ingress.kubernetes.io/load-balancer-name: techx-tf3-frontend-internal
    alb.ingress.kubernetes.io/scheme: internal
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}]'
    alb.ingress.kubernetes.io/healthcheck-path: /
    alb.ingress.kubernetes.io/security-groups: techx-corp-tf3-internal-alb
    alb.ingress.kubernetes.io/manage-backend-security-group-rules: "true"
spec:
  ingressClassName: alb
  rules:
    - http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend-proxy
                port:
                  number: 8080
```

The security-group value is the stable Terraform-managed `Name` tag; AWS Load Balancer
Controller supports lookup by either ID or Name tag. Add the three private subnet IDs
explicitly only if controller subnet discovery does not select all three tagged private
subnets in reconcile evidence.

- [ ] **Step 2: Write the persistent edge Application**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: techx-edge
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel.git
    targetRevision: deploy/account-migration-gitops
    path: gitops/edge
  destination:
    server: https://kubernetes.default.svc
    namespace: techx-tf3
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

- [ ] **Step 3: Validate without mutating the cluster**

```bash
kubectl apply --dry-run=client -f gitops/edge/frontend-proxy-internal-ingress.yaml
kubectl apply --dry-run=server -f gitops/edge/frontend-proxy-internal-ingress.yaml
kubectl apply --dry-run=server -f gitops/apps/techx-edge.yaml
```

Expected: all resources report created/configured in dry-run mode and the existing public Ingress remains unchanged.

- [ ] **Step 4: Commit GitOps resources**

```bash
git add gitops/edge/frontend-proxy-internal-ingress.yaml gitops/apps/techx-edge.yaml
git commit -m "feat: add internal frontend ingress"
```

### Task 5: Add an Executable Migration Runbook

**Files:**
- Create: `docs/runbooks/cloudfront-private-origin-migration.md`
- Modify: `infra/README.md`

**Interfaces:**
- Consumes: phase variables, Terraform outputs, ArgoCD resources, current SSM access path.
- Produces: exact operator commands, evidence capture, rollback, and cleanup procedure.

- [ ] **Step 1: Document Phase A apply and verification**

Include exact commands to trigger the saved plan workflow, inspect `0 destroy`, apply, and verify:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://d2tn71186d7ilz.cloudfront.net/
for path in grafana jaeger loadgen feature; do
  curl -sS -o /dev/null -w "$path %{http_code}\n" "https://d2tn71186d7ilz.cloudfront.net/$path/"
done
```

Expected: storefront 200; all operations paths 403.

- [ ] **Step 2: Document Phase B origin verification**

Include:

```bash
kubectl -n techx-tf3 get ingress frontend-proxy-internal -o wide
aws elbv2 describe-load-balancers --names techx-tf3-frontend-internal
aws elbv2 describe-target-health --target-group-arn "$TARGET_GROUP_ARN"
```

Expected: ALB scheme `internal`, state `active`, all targets `healthy`.

- [ ] **Step 3: Document staging, cutover, and rollback**

To enter staging, change tracked `edge_phase` from `waf` to `staging`, commit, plan, and apply. Test through the production domain with:

```bash
curl -H "aws-cf-cd-techx-private-origin: $CLOUDFRONT_STAGING_SELECTOR" \
  -sS -o /dev/null -w '%{http_code}\n' \
  https://d2tn71186d7ilz.cloudfront.net/
```

To cut over, change `edge_phase` to `private`. Rollback changes it to `waf`, which keeps WAF but returns primary to the public origin.

- [ ] **Step 4: Document cleanup guard**

State explicitly that cleanup requires 60 minutes of healthy metrics and a merged `main`. Cleanup disables `components.frontend-proxy.ingress.enabled` for the old Helm Ingress, changes `techx-edge` target revision to `main`, and never deletes the internal Ingress.

- [ ] **Step 5: Commit the runbook**

```bash
git add docs/runbooks/cloudfront-private-origin-migration.md infra/README.md
git commit -m "docs: add private origin migration runbook"
```

### Task 6: Review, Push, and Execute Phase A Only

**Files:**
- Review all files changed by Tasks 1-5.
- Do not modify user-owned `infra/.terraform.lock.hcl` or `AGENTS.md`.

**Interfaces:**
- Consumes: implementation commits and live production state.
- Produces: reviewed branch plus Phase A live state: WAF attached and internal ALB security group created, with the public ALB still serving origin traffic.

- [ ] **Step 1: Run complete local verification**

```bash
terraform fmt -check -recursive infra
terraform -chdir=infra/modules/edge test
terraform -chdir=infra/live/production validate
/tmp/actionlint-1.7.12/actionlint .github/workflows/*.yml
git diff --check origin/deploy/account-migration-gitops...HEAD
```

Expected: all exit 0.

- [ ] **Step 2: Review the actual production plan**

Run a refresh-only check first, then normal plan. Accept Phase A only when:

```text
Destroy: 0
CloudFront origin domain: unchanged public ALB DNS
Adds: WAF WebACL and internal ALB security group only
Changes: CloudFront WebACL association only
```

- [ ] **Step 3: Push the branch and run saved-plan apply**

```bash
git push origin deploy/account-migration-gitops
gh workflow run terraform-apply.yml --ref deploy/account-migration-gitops -f action=apply
```

Wait for the run to finish. Do not start Phase B while the run is active.

- [ ] **Step 4: Verify Phase A live**

```bash
aws cloudfront get-distribution-config --id E3DLSBEPU1N5UJ \
  --query 'DistributionConfig.WebACLId' --output text
curl -sS -o /dev/null -w '%{http_code}\n' https://d2tn71186d7ilz.cloudfront.net/
```

Expected: non-empty WebACL ARN and storefront 200. The four blocked paths must return 403. Direct public ALB remains available until the later cleanup gate.

- [ ] **Step 5: Record evidence and stop at the Phase B gate**

Record workflow URL, plan summary, CloudFront status, HTTP checks, and Terraform output for the internal ALB security group. Phase B begins only after the Ingress manifest contains that exact security group ID and receives a separate review.

---

## Plan Self-Review

- Spec coverage: ownership, WAF paths, runtime exceptions, private ALB, VPC Origin, staging, zero-downtime cutover, rollback, 60-minute observation, CI evidence, and cleanup are mapped to Tasks 1-6.
- Placeholder policy: no unfinished marker, generated-ID marker, or secret value is present in the plan.
- Interface consistency: `edge_phase`, `private_alb_name`, `cloudfront_staging_selector`, `internal_alb_security_group_id`, and `cloudfront_vpc_origin_id` use the same names across module, root, CI, GitOps, and runbook tasks.
