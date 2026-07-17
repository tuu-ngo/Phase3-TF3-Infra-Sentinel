# Review 1 - Mandate 08: Migrate PostgreSQL to Amazon RDS

## 1. Review objective
This file is intended for reading and reviewing the proposed solution for the PostgreSQL scope of Mandate 08:
- migrate self-hosted PostgreSQL in the cluster to Amazon RDS;
- preserve current application behavior;
- avoid data loss;
- avoid dropping checkout SLO during cutover;
- satisfy TLS, private endpoint, encryption at rest, and secret management requirements.

## 2. Affected scope
Components directly involved:
- `accounting`: the service that writes order data into PostgreSQL;
- `product-catalog`: read-only consumer of catalog data;
- `product-reviews`: read-only consumer of review data;
- Helm values / GitOps configuration for database connection strings;
- AWS Secrets Manager / External Secrets;
- Terraform for RDS, subnet groups, security groups, backup, and encryption.

## 3. Current-state checks before approval
Based on the material already present in the repository, the current PostgreSQL state is:
- PostgreSQL is still self-hosted inside the cluster.
- `accounting` is the only writer to PostgreSQL.
- `product-catalog` and `product-reviews` are read-only.
- The database contains both seed schema and business data.
- Existing credentials appear in plaintext in values, and that must be removed.

Reviewers should verify that the solution clearly confirms:
- source and target engine versions are compatible 1:1 or close enough without migration risk;
- there are no unsupported extensions outside normal RDS support;
- the migration plan does not depend on restarting the source database;
- there is evidence that `accounting` is in fact the only writer.

## 4. Summary of the proposed solution
A sound approach for PostgreSQL in this context is:

1. Provision Amazon RDS PostgreSQL in private subnets.
2. Enable encryption at rest, backup retention, and Multi-AZ.
3. Store credentials in AWS Secrets Manager instead of plaintext manifests.
4. Render per-service connection strings through External Secrets.
5. Before cutover, scale `accounting` to `0` in order to freeze the only writer.
6. Run `pg_dump` from the source and restore into RDS.
7. Perform data parity validation between source and target.
8. Switch `accounting`, `product-catalog`, and `product-reviews` to RDS with `sslmode=require`.
9. Scale `accounting` back up so it can replay the Kafka backlog into RDS.

This is a strong approach because it:
- avoids enabling logical replication on the source cluster database;
- avoids a restart of the source database;
- keeps storefront reads available because read-only services continue to operate;
- is lower risk than introducing a more complex replication mechanism under time pressure.

## 5. Strengths of the solution
- Isolating the single writer makes the cutover controlled and auditable.
- Data parity can be demonstrated clearly through row counts and checksums.
- Rollback is simple: point services back to the old PostgreSQL endpoint and scale `accounting` back.
- The audit trail is straightforward: freeze, dump, restore, verify, switch.
- RDS provides automated backups, managed operations, and stronger durability than an in-cluster self-hosted pod.

## 6. Key risks to inspect during review
### 6.1. Logical data-loss risk
The main risk is not the dump/restore step itself. It is the window:
- when `accounting` is scaled down;
- when endpoints are switched;
- when `accounting` is scaled back up.

The solution should explain clearly:
- where newly created orders go during that window;
- why orders are not lost;
- why replay after cutover is safe.

### 6.2. Connection-string format risk
The repository contains different client styles:
- .NET uses an Npgsql-style connection string;
- Go often uses URL format;
- Python/libpq uses key-value format.

If the solution only says "use one shared DB secret," that is not precise enough. Reviewers should require:
- explicit secret keys per service;
- example formats for each connection string;
- `sslmode=require`.

### 6.3. Read-path downtime risk
If the plan touches the source database in a way that requires restart or long blocking:
- `product-catalog`;
- `product-reviews`;
could be affected directly.

The preferred solution should:
- avoid restarting the source PostgreSQL instance;
- avoid changes that break the read path;
- use rolling restarts with `maxUnavailable: 0`.

### 6.4. Security gaps against mandate requirements
Reviewers should see all four controls:
- RDS in private subnets;
- security groups allowing only node group and bastion access;
- encrypted storage;
- secrets in Secrets Manager, with no plaintext left in chart values or manifests.

## 7. Suggested review checklist
- The solution describes RDS configuration clearly: engine version, instance class, storage, backup retention, and Multi-AZ.
- It explains why Multi-AZ is chosen instead of Single-AZ.
- It describes private subnets and least-privilege inbound security groups.
- It includes a clear plan for secret creation and cluster secret sync.
- It identifies exactly which three services switch database endpoints.
- It includes the writer-freeze step by scaling `accounting` to `0`.
- It defines the dump/restore process clearly.
- It includes parity criteria using row counts and checksums.
- It explains how application behavior is verified after cutover.
- It contains a concrete rollback plan rather than a generic statement.

## 8. Minimum evidence reviewers should require
- Screenshot or command output proving RDS is `available` and not public.
- Screenshot or output proving application pods are pointing to the new RDS endpoint.
- A before/after parity table covering:
  - row count for `order`;
  - row count for `orderitem`;
  - row count for `shipping`;
  - seed data in `products`;
  - seed data in `productreviews`.
- Proof that secrets are no longer stored in plaintext values or manifests.
- Proof that the old PostgreSQL pod is not deleted before mentor sign-off.

## 9. Review conclusion
Given the current system shape, migrating PostgreSQL to RDS using the sequence "freeze the single writer -> dump/restore -> verify parity -> switch endpoints -> replay backlog" is the most practical and controllable approach.

If I were reviewing this Jira task, I would approve only if the solution proves:
- no data loss;
- no storefront downtime;
- correct handling of secrets and TLS;
- a rollback plan clear enough to answer mentor questions immediately.
