# Terraform Production Layout Design

## Goal

Reconstruct the Terraform configuration so it describes the production
infrastructure in AWS account `197826770971`, then reorganize it into explicit
bootstrap, production root, and reusable module boundaries without changing
AWS resources during the refactor.

## Safety Contract

- Do not run `terraform apply`, `terraform import`, `terraform state mv`, or any
  command that writes production state.
- Use `techx-tf3-197826770971-tfstate` with key
  `eks-baseline/terraform.tfstate` as the production state source.
- Run diagnostic plans with `-lock=false`; use `-refresh=false` when comparing
  code structure so live drift does not contaminate the comparison.
- Preserve all state-tracked resources. Address changes caused by local module
  nesting must be declared with Terraform `moved` blocks.
- Preserve the protected flagd integration and never commit real flagd tokens,
  AWS credentials, or application secrets.
- Keep the existing user changes in `infra/.terraform.lock.hcl` and `AGENTS.md`
  outside refactor commits.

## Source Reconstruction

Before moving files, the flat root configuration must describe the account-new
state:

- EKS control plane and managed node group version `1.35`.
- EKS access entry for the account-new administrative principal currently
  tracked in state.
- S3, ECR API, ECR DKR, SSM, SSM Messages, and EC2 Messages VPC endpoints.
- The account-new frontend ALB DNS name tracked by the CloudFront distribution.
- The account-new backend bucket and lock configuration.
- No account-old IAM principal or account-old backend reference in the active
  production root or its GitHub Actions workflows.

The desired configuration remains private-only for the EKS API. The live
`endpoint_public_access=true` setting is pre-existing drift and is not changed
or recorded into state as part of this refactor.

## Target Layout

```text
infra/
|-- bootstrap/
|   |-- backend/
|   `-- github-oidc/
|-- live/
|   `-- production/
|       |-- backend.tf
|       |-- backend.hcl.example
|       |-- main.tf
|       |-- moved.tf
|       |-- outputs.tf
|       |-- production.auto.tfvars
|       |-- providers.tf
|       |-- variables.tf
|       `-- versions.tf
|-- modules/
|   |-- access/
|   |-- edge/
|   |-- eks-platform/
|   `-- network/
`-- README.md
```

## Ownership Boundaries

### Bootstrap Backend

Documents and eventually manages the S3 backend security controls separately
from the production platform state. Backend adoption or import is not part of
this refactor because it would write a new state.

### Bootstrap GitHub OIDC

Owns GitHub OIDC plan/apply roles independently from the production platform.
The production root must not depend on roles that it is itself expected to use
for apply. Creating or importing these roles is a later, separately approved
bootstrap operation.

### Network Module

Owns the VPC module, subnets, NAT gateway, endpoint security group, and all S3,
ECR, and SSM-related VPC endpoints.

### EKS Platform Module

Owns the EKS encryption key, EKS module, managed node group, managed add-ons,
and IRSA roles for cluster autoscaler and AWS Load Balancer Controller.

### Access Module

Owns the private SSM bastion, its IAM role and instance profile, and the rule
that permits the bastion to reach the EKS private endpoint.

### Edge Module

Owns the CloudFront distribution and its managed policy lookups. The ALB remains
owned by the Kubernetes AWS Load Balancer Controller and enters Terraform as an
explicit production input.

### Production Root

Contains backend/provider/version configuration, production values, module
composition, cross-module wiring, outputs, and all state address migration
declarations. It contains no application workload or Helm release ownership.

## State Address Migration

Moving existing resources under local modules changes Terraform addresses. The
production root therefore includes explicit `moved` blocks for every affected
root resource and existing registry module call, for example:

```hcl
moved {
  from = module.vpc
  to   = module.network.module.vpc
}

moved {
  from = aws_instance.bastion
  to   = module.access.aws_instance.bastion
}
```

No imperative `terraform state mv` command is used. A future approved apply may
record the new addresses in state, but Terraform must propose no AWS resource
create, update, replace, or destroy solely because of the refactor.

## GitHub Actions

Terraform workflows change their working directory to
`infra/live/production`, watch both production and shared module paths, and use
the account-new backend configuration. This design does not apply production or
provision missing CI roles. Saved-plan approval improvements are a subsequent
CI hardening change so the structural refactor remains independently reviewable.

## Verification

1. Capture the reconstructed flat-root plan with
   `terraform plan -refresh=false -lock=false`.
2. Validate every module and root with `terraform fmt -check` and
   `terraform validate`.
3. Run the reorganized production plan against the same remote state with
   `-refresh=false -lock=false`.
4. Confirm the final plan contains no AWS create, update, replace, or destroy
   action caused by the refactor.
5. Run `terraform plan -refresh-only -lock=false` only as a diagnostic and
   confirm the known EKS public-endpoint drift remains clearly separated.
6. Confirm the S3 state serial and live AWS resources were not modified.

## Out Of Scope

- Running Terraform apply or modifying production state.
- Changing the live EKS public endpoint setting.
- Creating GitHub OIDC plan/apply roles.
- Narrowing IAM permissions or redesigning the saved-plan workflow.
- Changing Helm, ArgoCD applications, Kubernetes workloads, or flagd sync.
- Updating provider, Terraform, EKS add-on, or AMI versions beyond matching the
  account-new state.
