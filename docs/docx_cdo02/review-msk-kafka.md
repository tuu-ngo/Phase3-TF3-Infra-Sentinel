# Review 3 - Mandate 08: Migrate Kafka to Amazon MSK

## 1. Review objective
This file is intended for reading and reviewing the proposed solution for the Kafka scope of Mandate 08:
- migrate self-hosted Kafka in the cluster to Amazon MSK;
- avoid message loss;
- avoid checkout failures;
- use TLS in transit, encryption at rest, and private endpoints;
- keep credentials in Secrets Manager.

## 2. Affected scope
Primary components involved:
- `checkout`: producer of order events;
- `accounting`: downstream consumer that persists orders;
- `fraud-detection`: downstream asynchronous consumer;
- topic `orders`;
- Helm/GitOps values for Kafka bootstrap servers;
- AWS Secrets Manager / External Secrets for SASL/SCRAM credentials;
- Terraform for the MSK cluster, broker settings, and security groups.

## 3. Current-state checks before approval
From the repository context, reviewers should anchor on these facts:
- Kafka is still self-hosted inside the cluster.
- `checkout` publishes synchronously and waits for ack before returning success.
- `accounting` and `fraud-detection` consume downstream.
- `checkout` is the most sensitive component because publish failure hits checkout SLO directly.

Reviewers should require the solution to explain:
- which ack mode the producer uses today;
- how consumer offsets are committed;
- how many partitions the `orders` topic has;
- whether existing retention is long enough to cover the migration window safely.

## 4. Summary of the proposed solution
For Kafka, a safe migration path should follow this order:

1. Provision Amazon MSK in private subnets with TLS and SASL/SCRAM.
2. Create the SCRAM secret in Secrets Manager.
3. Sync the secret into the cluster through External Secrets.
4. Update the three dependent services so they support:
   - `SASL_SSL`;
   - username and password from secrets;
   - TLS client configuration.
5. Pre-create the `orders` topic on MSK with the correct topology.
6. Cut over producer `checkout` to MSK first.
7. Wait until all `checkout` pods are fully rolled to the new revision.
8. Monitor the old Kafka cluster until consumers drain the remaining backlog there.
9. Move `accounting` and `fraud-detection` to MSK.
10. Let the new consumers read the backlog on MSK from `Earliest`, or from another strategy that is explicitly proven safe.

The key principle is:
- producers move first;
- consumers move second;
- the team must not mix partial producer and consumer cutover without controlling backlog and offsets carefully.

## 5. Strengths of the solution
- Reduces the risk of message loss during queue migration.
- Separates producer cutover and consumer cutover into two clear phases.
- Fits the current business flow where `accounting` is an asynchronous consumer.
- Supports a practical rollback path while the old Kafka broker remains in the cluster.
- MSK provides replication, managed broker operations, and stronger durability than a single self-hosted broker pod.

## 6. Key risks to inspect during review
### 6.1. Highest risk: checkout failure if the producer cannot publish
If `checkout` publishes synchronously and waits for ack:
- MSK connection failure;
- bad auth;
- broken TLS;
will fail checkout immediately.

Reviewers should expect the solution to include:
- producer validation with `SASL_SSL`;
- controlled rollout for `checkout`;
- a very fast producer rollback path if publish errors rise.

### 6.2. Orphaned-message risk caused by the wrong cutover order
If consumers are moved before all producers have switched:
- backlog can exist in both the old and new brokers at the same time;
- message-loss proof becomes weak;
- offset tracking becomes confusing.

Reviewers should prefer a strict rule:
- producer first;
- verify all producer pods are on the new revision;
- wait until lag on the old broker reaches `0`;
- only then move consumers.

### 6.3. Authentication feasibility across multiple languages
MSK is only truly compliant here if auth is enabled, but auth across different runtimes is the hard part.

Reviewers should see the solution specify:
- which SCRAM client is used for Go/Sarama;
- how `.NET` configures `SaslSsl` and `ScramSha512`;
- how Java/Kotlin sets `sasl.jaas.config`;
- where secrets are sourced from.

If the solution only says "enable TLS on Kafka" without auth, it does not meet the mandate.

### 6.4. Topic-configuration compatibility risk
If the current `orders` topic has only `1 partition`, and the solution increases partitions without analysis:
- ordering semantics may change;
- downstream behavior may be affected.

Reviewers should require an explanation of:
- target partition count;
- replication factor;
- `min.insync.replicas`;
- why the chosen configuration is safe and consistent with current semantics.

### 6.5. Cost and topology risk
MSK is likely the most expensive part of the three-store migration.

Reviewers should look for explanation of:
- why `3` brokers are selected instead of `2`;
- why that broker class is chosen;
- the estimated weekly or monthly cost;
- why the decision still fits the mandate budget.

## 7. Suggested review checklist
- The solution describes MSK configuration: version, broker type, broker count, and private subnets.
- TLS, encryption at rest, and SASL/SCRAM are enabled.
- SCRAM secrets are stored in Secrets Manager and synced into the cluster.
- `checkout`, `accounting`, and `fraud-detection` are all updated.
- The cutover order is explicit: producer first, consumer second.
- There is a step that verifies all `checkout` pods have completed rollout.
- There is a step to confirm lag on the old broker is `0` before switching consumers.
- The solution explains `orders` topic configuration on MSK and the reason for partition count, replication factor, and min ISR.
- It includes separate rollback logic for producer and consumer cutover.

## 8. Minimum evidence reviewers should require
- Screenshot or command output showing MSK is active and bootstrap endpoints are private.
- Proof that `checkout` publishes successfully through `SASL_SSL`.
- Proof that `accounting` and `fraud-detection` consume successfully from MSK.
- A before/after message-handling comparison covering:
  - offsets;
  - lag;
  - number of orders persisted to the database after replay.
- Checkout dashboard evidence showing success rate remains within acceptable range during cutover.
- Proof that the old Kafka broker is not deleted before mentor sign-off is completed.

## 9. Review conclusion
Of the three Mandate 08 data stores, Kafka/MSK is the highest-risk migration because it sits directly on the synchronous checkout path. A good solution must prove three things:
- producer migration to MSK does not break checkout;
- consumer migration to MSK does not lose messages;
- rollback is fast enough if auth, TLS, or routing fails.

If I were reviewing this Jira task, I would treat it as the most critical scope and approve only if the solution describes cutover order, offset/backlog handling, and multi-language authentication in a very explicit way.
