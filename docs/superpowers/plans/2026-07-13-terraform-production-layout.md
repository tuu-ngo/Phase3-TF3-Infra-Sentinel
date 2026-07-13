# Terraform Production Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Terraform describe AWS account `197826770971`, then move the production root into `infra/live/production` and split logical capabilities into local modules without changing AWS resources or production state.

**Architecture:** Reconstruct the current flat root against the account-new remote state first, then compare a no-refresh plan before and after module extraction. Declarative `moved` blocks migrate every changed state address; bootstrap ownership is separated from the production platform without running bootstrap operations.

**Tech Stack:** Terraform 1.15.x, HashiCorp AWS provider 5.100.0, AWS S3 backend, GitHub Actions OIDC.

## Global Constraints

- Never run `terraform apply`, `terraform import`, `terraform state mv/rm/push`, or `terraform force-unlock`.
- Every plan must use `-lock=false`; structural comparisons must use `-refresh=false`.
- Production state is `s3://techx-tf3-197826770971-tfstate/eks-baseline/terraform.tfstate`.
- Desired EKS version is `1.35`; desired API access is private-only.
- Preserve S3, ECR API, ECR DKR, SSM, SSM Messages, and EC2 Messages endpoints.
- Do not modify Helm, ArgoCD, Kubernetes workload, flagd sync, `infra/.terraform.lock.hcl`, or `AGENTS.md`.
- Do not commit secrets, credentials, binary plans, state snapshots, or command output containing state values.
- Use `apply_patch` for manual file changes and commit only task-owned paths.

---

### Task 1: Capture Read-Only Baseline

**Files:**
- Create: `/tmp/tf3-state-addresses.before.txt` (untracked diagnostic)
- Create: `/tmp/tf3-flat-plan.before.txt` (untracked diagnostic)
- Create: `/tmp/tf3-state-metadata.before.json` (untracked diagnostic)

**Interfaces:**
- Consumes: account-new backend and current flat root.
- Produces: state address list, state serial/lineage, and baseline action summary used by Tasks 2 and 5.

- [x] Verify AWS identity is account `197826770971` with `aws sts get-caller-identity`.
- [x] Initialize `infra/` using `-reconfigure` and the account-new bucket, key, region, lock table, and encryption settings.
- [x] Save `terraform state list | sort` to `/tmp/tf3-state-addresses.before.txt`.
- [x] Read only `version`, `terraform_version`, `serial`, and `lineage` from the S3 state object into `/tmp/tf3-state-metadata.before.json`.
- [x] Run `terraform plan -refresh=false -lock=false -input=false -no-color` and save text output to `/tmp/tf3-flat-plan.before.txt`.
- [x] Record the baseline action summary; do not save a binary plan.

### Task 2: Reconstruct the Account-New Flat Root

**Files:**
- Modify: `infra/backend.hcl.example`
- Modify: `infra/networking.tf`
- Modify: `infra/variables.tf`
- Modify: `infra/ci.auto.tfvars`
- Modify: `infra/README.md`
- Remove from production ownership: `infra/ci.tf`

**Interfaces:**
- Consumes: Task 1 state addresses and live/state values.
- Produces: a flat root whose no-refresh plan has no account-old identity, missing endpoint, EKS downgrade, or stale CloudFront origin action.

- [x] Add interface endpoints named `ssm`, `ssmmessages`, and `ec2messages` using the existing endpoint subnets, security group, private DNS, region, and tags pattern.
- [x] Set `cluster_version = "1.35"` and the CloudFront ALB default to the account-new state value.
- [x] Replace account-old EKS principals with `arn:aws:iam::197826770971:user/cdo-2-admin-team`.
- [x] Change backend examples and commands to bucket `techx-tf3-197826770971-tfstate` and table `techx-tf3-terraform-lock`.
- [x] Remove `infra/ci.tf` from the active production root; preserve its intent for Task 4 bootstrap ownership.
- [x] Run `terraform fmt -check -recursive`, `terraform validate`, and a no-refresh/no-lock plan.
- [x] Confirm the plan no longer proposes destroying SSM endpoints, removing the account-new EKS access entry, adding account-old principals, or downgrading EKS.
- [x] Commit only the reconstructed flat-root files with `refactor: align Terraform with new account state`.

### Task 3: Extract Production Modules With Declarative Moves

**Files:**
- Create: `infra/modules/network/{main.tf,variables.tf,outputs.tf,versions.tf}`
- Create: `infra/modules/eks-platform/{main.tf,variables.tf,outputs.tf,versions.tf}`
- Create: `infra/modules/access/{main.tf,variables.tf,outputs.tf,versions.tf}`
- Create: `infra/modules/edge/{main.tf,variables.tf,outputs.tf,versions.tf}`
- Create: `infra/live/production/{backend.tf,backend.hcl.example,main.tf,moved.tf,outputs.tf,production.auto.tfvars,providers.tf,variables.tf,versions.tf}`
- Remove relocated flat-root Terraform files from `infra/`.

**Interfaces:**
- `network` produces `vpc_id`, private/public subnet IDs, and endpoint security group ID.
- `eks-platform` consumes VPC/subnets and produces cluster name, endpoint, security group ID, OIDC provider ARN, and controller role ARNs.
- `access` consumes VPC/private subnets/cluster security group/cluster endpoint and produces bastion ID and tunnel command inputs.
- `edge` consumes the frontend ALB DNS and produces the CloudFront HTTPS domain.
- Production root wires modules and preserves existing public outputs.

- [x] Extract VPC and all endpoint resources into `module.network` without changing arguments.
- [x] Extract KMS, EKS, managed node group/add-ons, and controller IRSA modules into `module.eks_platform`.
- [x] Extract bastion resources into `module.access`.
- [x] Extract CloudFront resources into `module.edge`.
- [x] Add whole-module moves for `module.vpc`, `module.eks`, `module.cluster_autoscaler_irsa`, and `module.lb_controller_irsa`.
- [x] Add resource moves for every root resource/data source moved into the four modules, including all six VPC endpoints.
- [x] Move backend/provider/version/variables/values/outputs into `infra/live/production` and compose the four modules in `main.tf`.
- [x] Initialize the new production root against the same backend without migration and run fmt/validate.
- [x] Run a no-refresh/no-lock plan and confirm address moves produce no AWS create, update, replace, or destroy actions.
- [x] Commit only the module and production-root relocation with `refactor: split Terraform production capabilities`.

### Task 4: Separate Bootstrap Ownership and Update Automation

**Files:**
- Create: `infra/bootstrap/backend/{README.md,main.tf,outputs.tf,providers.tf,variables.tf,versions.tf}`
- Create: `infra/bootstrap/github-oidc/{README.md,main.tf,outputs.tf,providers.tf,variables.tf,versions.tf}`
- Modify: `.github/workflows/terraform-plan.yml`
- Modify: `.github/workflows/terraform-apply.yml`
- Modify: `infra/README.md`

**Interfaces:**
- Bootstrap roots are independent and are not initialized/applied in this task.
- Workflows consume only `infra/live/production` and `infra/modules` for production planning.

- [x] Define backend resources and GitHub OIDC role configuration in independent bootstrap roots while documenting that adoption/provisioning requires separate approval.
- [x] Set workflow working directory to `infra/live/production`.
- [x] Watch `infra/live/production/**` and `infra/modules/**` paths.
- [x] Use the account-new bucket, state key, region, and lock table in workflow init.
- [x] Keep current plan/apply behavior otherwise unchanged so saved-plan hardening remains a separate change.
- [x] Search active production/workflow paths and confirm account `012619468490` does not appear.
- [x] Commit bootstrap/workflow/docs changes with `refactor: separate Terraform bootstrap ownership`.

### Task 5: Production-Safety Audit

**Files:**
- Inspect all changed Terraform, workflow, and documentation files.
- Update: `docs/superpowers/plans/2026-07-13-terraform-production-layout.md` checkboxes as work completes.

**Interfaces:**
- Consumes all prior task outputs.
- Produces evidence that code movement did not mutate or propose mutation of AWS resources.

- [x] Run `terraform fmt -check -recursive` from `infra/`.
- [x] Initialize and validate `infra/live/production` against the account-new backend.
- [x] Validate each local module using the production root dependency graph.
- [x] Run final `terraform plan -refresh=false -lock=false -input=false -no-color` and save output only under `/tmp`.
- [x] Verify the final plan has no resource create, update, replace, or destroy action caused by refactoring.
- [x] Run `terraform plan -refresh-only -lock=false -input=false -no-color` and report the known EKS public endpoint drift separately.
- [x] Re-read state metadata from S3 and compare serial/lineage with Task 1.
- [x] Compare state addresses with `moved.tf` and ensure every changed address is covered.
- [x] Search the diff for account-old IDs, credentials, tokens, state files, binary plans, Helm, ArgoCD, Kubernetes, and flagd changes.
- [x] Run `git diff --check`, inspect every staged diff, and run a production-focused code/security review.
- [x] Commit only final verification documentation if it changed; do not push or create a PR.
