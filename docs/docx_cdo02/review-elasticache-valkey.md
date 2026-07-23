# Review 2 - Mandate 08: Migrate Valkey to Amazon ElastiCache

## 1. Review objective
This file is intended for reading and reviewing the proposed solution for the Valkey scope of Mandate 08:
- migrate self-hosted Valkey/Redis in the cluster to Amazon ElastiCache;
- avoid breaking the cart flow;
- avoid degrading the storefront experience;
- use TLS, private endpoints, and encryption at rest;
- keep auth tokens and sensitive data in Secrets Manager.

## 2. Affected scope
Main components involved:
- `cart` service;
- cart persistence logic in `ValkeyCartStore`;
- Helm/GitOps values for Valkey address and auth configuration;
- AWS Secrets Manager / External Secrets for the auth token;
- Terraform for the ElastiCache replication group;
- security groups, subnet groups, and failover settings.

## 3. Current-state checks before approval
From the repository context, these are the points that matter:
- Valkey is currently self-hosted inside the cluster.
- `cart` is the main service using this store.
- Cart TTL behavior is important for user experience.
- Existing code suggests `ssl=false` is hardcoded today.

Reviewers should confirm that the solution answers:
- how cart reads and writes currently behave;
- what the current TTL is;
- how old keys are introduced into the new target before read cutover;
- whether a failure in ElastiCache during the migration window can break customer requests.

## 4. Summary of the proposed solution
A strong migration path for Valkey is:

1. Provision ElastiCache Valkey in private subnets.
2. Enable transit encryption, at-rest encryption, and auth token support.
3. Store the auth token in Secrets Manager.
4. Update `cart` so it supports:
   - TLS enablement through environment variables;
   - auth token through environment variables;
   - dual-write to a secondary store through a dedicated environment variable.
5. In the first phase:
   - `cart` still reads from the old Valkey instance;
   - it also writes to the new ElastiCache target.
6. Wait longer than the cart TTL so the new cache becomes warm.
7. Switch the read path to ElastiCache.
8. Optionally keep dual-write for a short period to support fast rollback.

This is the safe approach because cache is simpler than the database, but it still sits on the direct customer path and should not be switched abruptly.

## 5. Strengths of the solution
- Reduces the risk of a large cache miss wave immediately after cutover.
- Does not require storefront downtime.
- Rollback is fast because the read path can be pointed back to the old store quickly.
- It can be observed through key count, error rate, cart behavior, and checkout conversion.
- ElastiCache provides failover and managed operations that are stronger than a self-hosted cache pod.

## 6. Key risks to inspect during review
### 6.1. The biggest risk is dual-write causing customer requests to fail
If dual-write is implemented so that:
- write to the new store fails;
- customer request fails as a result;
then the team has created a new SPOF during migration.

Reviewers should expect the solution to state clearly:
- writes to the primary store remain mandatory;
- writes to the secondary store are best-effort;
- failures in the secondary write should be logged but must not fail the user request.

### 6.2. Cutover-too-early risk
If the read path switches before a full TTL window has elapsed:
- some carts may not yet exist in the new store;
- users may appear to lose their cart temporarily.

Reviewers should ask:
- what the actual cart TTL is;
- how long the team waits before switching reads;
- whether they include extra safety buffer beyond TTL.

### 6.3. TLS/auth not actually being active
Some solutions say "use secrets" but still leave endpoints or tokens exposed in values, or never enable TLS in the client.

Reviewers should expect:
- client TLS to be enabled through configuration;
- auth token to come from a secret;
- ElastiCache transit encryption to be enabled;
- endpoint exposure to remain private only.

### 6.4. Sizing and cost risk
Valkey is a cache, but cart is on the hot path. If the target is undersized:
- latency may rise;
- timeouts may increase;
- checkout conversion may drop.

Reviewers should look for:
- instance class;
- node count;
- replica/failover strategy;
- reasoning for Multi-AZ or replica count.

## 7. Suggested review checklist
- The solution describes ElastiCache configuration: engine, version, node type, replica count, and failover.
- TLS in transit and encryption at rest are enabled.
- Auth token is stored in Secrets Manager.
- `cart` is updated to support TLS and auth through environment variables.
- Dual-write design is described clearly.
- The solution states the cart TTL and the required wait time before read cutover.
- It explains how to validate key-count or behavioral parity between old and new stores.
- It includes a fast and concrete rollback path.
- It shows that storefront, cart, and checkout stay healthy during cutover.

## 8. Minimum evidence reviewers should require
- Screenshot or command output showing ElastiCache is `available` in private subnets.
- Screenshot or output showing `cart` is using TLS and secret-based auth.
- Key count comparison between source and target after the dual-write warmup window.
- Basic business-flow validation:
  - add item to cart;
  - update quantity;
  - clear cart;
  - complete checkout successfully.
- Dashboard or logs showing no spike in cart errors during cutover.
- Proof that the old `valkey-cart` pod remains in place until mentor sign-off is complete.

## 9. Review conclusion
A good Valkey solution is not just "change the endpoint." It must show:
- safe dual-write behavior;
- a wait period that covers the TTL window;
- a read switch that can be rolled back within minutes;
- correct TLS, auth token, and private endpoint handling.

If I were reviewing this Jira task, I would approve only if the solution demonstrates that customers do not lose their cart during the cache migration.
