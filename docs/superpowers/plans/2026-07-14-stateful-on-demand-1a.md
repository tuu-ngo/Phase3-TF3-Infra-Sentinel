# Stateful On-Demand Capacity in ap-southeast-1a Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provision dedicated on-demand capacity in `ap-southeast-1a` and constrain PostgreSQL and Valkey to it before the Mandate #2 load test.

**Architecture:** Terraform owns a single-AZ EKS managed node group with a dedicated label and taint. ArgoCD continues to own the Helm release and applies matching scheduling rules only after Terraform capacity is Ready.

**Tech Stack:** Terraform 1.15, terraform-aws-modules/eks v20, Helm, ArgoCD, Kubernetes, GitHub Actions.

## Global Constraints

- Do not change flagd, `values-flagd-sync.yaml`, its TOKEN/URI, or any incident-injection path.
- Do not commit AWS credentials, sync tokens, LLM keys, Terraform plans, or generated state.
- Do not modify or recreate the existing PostgreSQL or Valkey PVC/PV resources.
- Terraform capacity must be applied before ArgoCD moves the datastore pods.
- Preserve unrelated changes from commit `3e86530`.

---

### Task 1: Add the dedicated managed node group

**Files:**
- Modify: `infra/live/production/main.tf`
- Modify: `infra/live/production/variables.tf`
- Modify: `infra/modules/eks-platform/main.tf`
- Modify: `infra/modules/eks-platform/variables.tf`

**Interfaces:**
- Consumes: ordered `var.azs` and `module.network.private_subnet_ids`.
- Produces: an EKS managed node labeled `techx.io/workload=stateful` in the subnet corresponding to `var.stateful_node_availability_zone`.

- [ ] Add validated production variables for AZ and instance type.
- [ ] Resolve the selected AZ to exactly one subnet and pass it into `eks-platform`.
- [ ] Add `stateful_1a` managed node group with `ON_DEMAND`, sizes `1/1/1`, label, taint, and EBS CSI policy.
- [ ] Run `terraform fmt -check -recursive infra`.
- [ ] Run `terraform -chdir=infra/live/production init -backend=false -input=false` and `terraform validate`.
- [ ] Run a remote-state-backed read-only `terraform plan`; confirm one node group is added and the default node group is not replaced.

### Task 2: Constrain datastore scheduling through ArgoCD-owned values

**Files:**
- Modify: `phase3 - information/deploy/values-prod.yaml`

**Interfaces:**
- Consumes: node label and taint created by Task 1.
- Produces: PostgreSQL and Valkey pod specs with `nodeSelector.techx.io/workload=stateful` and the matching `NoSchedule` toleration.

- [ ] Add identical `schedulingRules` to PostgreSQL and Valkey only.
- [ ] Build chart dependencies with `helm dependency build`.
- [ ] Render the exact ArgoCD value stack with `helm template`.
- [ ] Assert both rendered Deployments contain the selector and toleration and no other Deployment receives them.

### Task 3: Review, publish, and apply Terraform capacity

**Files:**
- Modify: `docs/superpowers/specs/2026-07-14-stateful-on-demand-1a-design.md`
- Modify: `docs/superpowers/plans/2026-07-14-stateful-on-demand-1a.md`

**Interfaces:**
- Consumes: verified Terraform and Helm changes.
- Produces: reviewed Terraform-only PR into `deploy/account-migration-gitops` and a Ready dedicated node.

- [ ] Inspect `git diff --check`, `git diff --stat`, and the full diff for unrelated changes or secrets.
- [ ] Commit only Terraform and design/plan files and push `fix/stateful-on-demand-1a`.
- [ ] Open a Terraform-only PR targeting `deploy/account-migration-gitops` and wait for checks.
- [ ] Merge only after checks pass; confirm the deployment branch contains the exact commit.
- [ ] Confirm the push-triggered Terraform Plan workflow passes.
- [ ] Manually dispatch Terraform Apply with `action=apply`; verify the saved plan checksum and apply job pass.
- [ ] Verify the dedicated node is Ready before creating the ArgoCD placement PR.

### Task 4: Publish ArgoCD placement and verify workloads

**Files:**
- Modify: `phase3 - information/deploy/values-prod.yaml`

**Interfaces:**
- Consumes: the live Ready node produced by Task 3.
- Produces: datastore pods placed on the dedicated on-demand node.

- [ ] Create a second branch from the updated deployment branch after Terraform apply succeeds.
- [ ] Add the already-verified PostgreSQL and Valkey scheduling rules only.
- [ ] Render and assert the exact Helm value stack again.
- [ ] Open and merge a second PR targeting `deploy/account-migration-gitops`.
- [ ] Confirm ArgoCD sync succeeds.
- [ ] Verify PostgreSQL and Valkey placement, PVC attachment, readiness, dependent services, cart, and checkout.
- [ ] Stop and rollback the scheduling change if the node is absent or either datastore fails to become Ready.
