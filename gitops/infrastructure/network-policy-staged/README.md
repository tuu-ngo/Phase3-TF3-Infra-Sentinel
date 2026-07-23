# Mandate 17 staged NetworkPolicies

This directory contains the reviewed policy set, but it is intentionally not
active. `techx-infrastructure-app` uses Argo CD directory mode without
`directory.recurse`, so only YAML files placed directly in
`gitops/infrastructure/` are synchronized.

Do not enable this directory by setting `directory.recurse: true`. Promote one
file at a time to `gitops/infrastructure/` in the order below. Each promotion
must use a separate PR and a low-traffic change window.

## Design constraints

- Production uses Amazon VPC CNI network policy in `standard` mode.
- A previous rollout proved that selector-only egress through a ClusterIP can
  be dropped by this cluster. The staged service rules therefore use exact pod
  selectors first, and the first canary must prove that behavior on the current
  VPC CNI before any wider promotion. If the canary still fails, stop and add
  read-only-audited Service ClusterIP `/32` peers in a follow-up PR; do not
  replace them with a broad VPC CIDR. Destination ingress policies still
  enforce the caller identity.
- Managed RDS, ElastiCache, and MSK endpoints live in the three production
  private subnets. Only their required ports are allowed.
- `product-reviews` is the only business workload allowed public HTTPS egress,
  because production selects the Bedrock provider in `us-east-1` through IRSA.
- `flagd` keeps its protected runtime read path and can synchronize only with
  the configured `122.248.223.194` HTTPS source. Nothing here changes or
  removes `/flagservice`.
- DNS is allowed only to CoreDNS on TCP/UDP 53, with a private-VPC fallback for
  the observed VPC CNI ClusterIP behavior. Public DNS egress remains blocked.
- Production has no direct `checkout -> quote` client configuration. The real
  path is `checkout -> shipping -> quote`, so no unnecessary direct rule is
  opened.

## Promotion order

1. Capture pre-change pods, events, Argo health, storefront HTTP 200, and
   positive/negative connectivity evidence.
2. Promote leaf services one at a time: `quote`, `currency`, `payment`,
   `email`, `ad`, `image-provider`, and `llm`.
3. Promote stateful clients one at a time: `product-catalog`, `cart`,
   `accounting`, and `fraud-detection`.
4. Promote callers from the bottom up: `shipping`, `recommendation`,
   `product-reviews`, `checkout`, `frontend`, and `frontend-proxy`.
5. Promote `flagd`, then the platform policies one at a time: `00-otel-gateway`,
   `01-grafana`, `02-jaeger`, `03-prometheus`, `04-opensearch`,
   `05-load-generator`, `06-cloudflared`, and `07-aiops-engine`.
6. Promote `90-default-deny-all.yaml` last.

After every file is synchronized:

```bash
kubectl -n argocd get application techx-infrastructure-app techx-corp
kubectl -n techx-tf3 get pods
kubectl -n techx-tf3 get events --sort-by=.lastTimestamp | tail -40
kubectl -n techx-tf3 get policyendpoints.networking.k8s.aws
curl -fsS -o /dev/null -w 'storefront=%{http_code} total=%{time_total}s\n' \
  https://d2tn71186d7ilz.cloudfront.net/
```

Run the browse, cart, and checkout smoke path. With temporary `pods/exec`
permission, also run one allowed dependency test and one unrelated-service
test from the newly isolated workload. The allowed call must succeed and the
unrelated call must time out.

If any positive test, readiness check, SLO, or Argo health check regresses,
revert that promotion commit immediately and let Argo CD prune the policy.
Never repair the live object with `kubectl apply`, `patch`, `edit`, or `delete`.

## Final acceptance tests

After `90-default-deny-all.yaml` is active:

```bash
# Unrelated east-west call: expected to time out.
kubectl -n techx-tf3 exec deploy/cart -- nc -vz -w 5 payment 8080

# Public internet from a business pod without an exception: expected to fail.
kubectl -n techx-tf3 exec deploy/cart -- \
  curl -I -L --connect-timeout 5 https://example.com

# Bedrock exception owner: DNS and HTTPS must still work from product-reviews.
kubectl -n techx-tf3 exec deploy/product-reviews -- \
  curl -I --connect-timeout 5 https://bedrock-runtime.us-east-1.amazonaws.com
```

An HTTP 403/404 from the Bedrock endpoint is sufficient network evidence; a
timeout is not. Capture command output, Argo `Synced/Healthy`, storefront 200,
and the browse/cart/checkout result as PR evidence.
