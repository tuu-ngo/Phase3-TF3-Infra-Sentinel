# Stateful On-Demand Capacity in ap-southeast-1a

## Goal

Move PostgreSQL and Valkey off the `flash-sale-spot` NodePool before Mandate #2 load testing, without replacing or migrating their existing EBS volumes.

## Design

Terraform creates one dedicated EKS managed node group using on-demand capacity and only the private subnet in `ap-southeast-1a`. The node group has label `techx.io/workload=stateful` and taint `techx.io/workload=stateful:NoSchedule`, so burst workloads cannot consume its reserved capacity.

The Helm production values consumed by the ArgoCD `techx-corp` Application add matching `nodeSelector` and `tolerations` to PostgreSQL and Valkey. Their existing gp2 PVCs, `Recreate` strategy, probes, and protected flagd configuration remain unchanged.

## Deployment order

1. Merge a Terraform-only PR into the deployment branch.
2. Run the production Terraform saved-plan workflow and apply that exact plan.
3. Verify the on-demand node is Ready in `ap-southeast-1a` with the expected label and taint.
4. Only then merge a second PR containing the ArgoCD-owned workload placement.
5. Verify PostgreSQL and Valkey are Ready on the dedicated on-demand node, then run datastore and checkout smoke tests.

## Rollback

Revert only the workload scheduling rules if either datastore cannot schedule. Do not delete or recreate PVCs/PVs. Keep the dedicated node group until both workloads are healthy elsewhere; Terraform removal is a separate, later change.

## Acceptance criteria

- Terraform plan creates one on-demand managed node group restricted to the 1a subnet and does not replace the default node group.
- Helm renders both datastore Deployments with the dedicated selector and toleration.
- Live node labels show `ap-southeast-1a`, `ON_DEMAND`, and `techx.io/workload=stateful`.
- PostgreSQL and Valkey run on that node and no longer run on `karpenter.sh/capacity-type=spot`.
- Product catalog, product reviews, accounting, cart, and checkout remain healthy.
- No flagd routing, sync token, URI, credential, PVC, or PV definition is changed.
