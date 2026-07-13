# Mentor Mandate Review Access Design

## Goal

Give the TechX mentor temporary, independently usable access to verify Mandate #1 without granting infrastructure administration, workload mutation, secret access, or public access to operational UIs.

## Identity Flow

1. A bootstrap IAM user named `mentor-mandate-reviewer` receives only `sts:AssumeRole` permission for one role.
2. The role `techx-tf3-mandate-reviewer` trusts only that IAM user and limits sessions to one hour.
3. The role can describe the production EKS cluster and start an SSM port-forwarding session to the current production bastion using only `AWS-StartPortForwardingSessionToRemoteHost`.
4. An EKS `STANDARD` access entry maps the role to the Kubernetes group `techx:mandate-reviewers`.
5. Namespace RoleBindings grant that group read access plus `create` on `pods/portforward` in `techx-tf3` and `argocd` only.

The bootstrap access key is delivered out of band, never written to a tracked file, and deleted immediately after mentor verification.

## Allowed Verification

- Confirm the AWS caller identity after assuming the reviewer role.
- Open the private EKS API tunnel through the single SSM bastion.
- List pods and services in `techx-tf3` and `argocd`.
- Port-forward Grafana, Jaeger, and ArgoCD services.
- Read pod status and logs needed to verify availability.

## Explicit Denials By Absence

The reviewer receives no permission to mutate Deployments, Services, Ingresses, Secrets, Argo CD Applications, IAM, EC2, CloudFront, WAF, or Terraform state. The role cannot start a shell session because its IAM policy permits only the remote-host port-forwarding SSM document.

## Audit And Lifecycle

- CloudTrail Event History records IAM, STS, EKS, and SSM API activity.
- EKS control-plane audit logging records the generated EKS username and Kubernetes actions.
- SSM session history records session owner and timestamps.
- IAM resources and the EKS access entry are tagged with `Purpose=Mandate-01-Review` where supported.
- The runbook includes cleanup commands for the access key, access entry, policies, role, and user.

## Verification

Test with credentials belonging to the bootstrap user, not the administrator:

1. `sts:AssumeRole` succeeds and returns a one-hour session.
2. SSM port-forwarding to the configured bastion succeeds.
3. `kubectl auth can-i` confirms read and port-forward access.
4. Mutation and Secret reads return `no` or `AccessDenied`.
5. Grafana, Jaeger, and ArgoCD health endpoints respond through local port-forwards.
6. Public operational paths remain blocked and storefront availability remains unchanged.

## Rollback

Delete the bootstrap access key first, then the EKS access entry and Kubernetes RoleBindings, followed by IAM inline policies, role, and user. None of these operations changes storefront traffic, workloads, data, flagd, or the protected fault-injection mechanism.
