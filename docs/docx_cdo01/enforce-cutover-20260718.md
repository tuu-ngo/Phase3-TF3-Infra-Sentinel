# Mandate 05 Enforce Cutover Evidence - 2026-07-18

## Scope

- Git source revision: `677e74b42b2b744646633c45e36ebbc614ca176b`
- Namespace: `techx-tf3`
- Kyverno controller: `v1.13.2` (`kyverno` chart `3.3.4`)
- Deployment path: reviewed PRs to `main`, followed by Argo CD auto-sync
- Imperative policy or workload apply: none

## Enforced policies

| Policy | Action | Ready | Negative admission result |
| --- | --- | --- | --- |
| `require-resource-requests` | Enforce | True | Deployment template without requests/limits denied by `autogen-require-cpu-memory-requests-limits`. |
| `disallow-latest-tag` | Enforce | True | Explicit `:latest` and implicit-latest Pod requests denied. |
| `require-first-party-image-digest` | Enforce | True | TechX ECR tag-only Pod request denied; exact `@sha256` request admitted. |
| `custom-baseline-security-context` | Enforce | True | Root Pod denied by three rules; privileged/Unconfined fixture denied by all eight baseline rules. |

All admission checks used `kubectl apply --dry-run=server` or
`kubectl run --dry-run=server`; no test Pod was persisted.

## Resource defaulting decision

The team accepted and retained `techx-limits`. A direct Pod which omits
requests/limits is defaulted by the Kubernetes LimitRanger before Kyverno
validation. The resource-policy rejection demo therefore uses a Deployment
template, which is evaluated by the Kyverno autogen rule before a Pod can be
created. ResourceQuota and LimitRange remain unchanged.

## Positive admission and exceptions

- Fully hardened first-party digest and third-party tagged fixtures were
  admitted by server-side dry-run.
- The `app=aiops-engine` synthetic fixture was admitted through the exact-label
  exception.
- The Kafka exception remains limited to
  `app.kubernetes.io/name=kafka` and the four documented init-ownership rules.
- The exception register still contains exactly two time-bounded records:
  Kafka PVC ownership init and the out-of-tree AIOps runtime.

## Runtime health after cutover

- All 11 Argo CD Applications: `Synced` and `Healthy`.
- Kyverno admission, background, cleanup and reports controllers: Running,
  Ready and zero restarts.
- `techx-tf3`: no Pod outside `Running`.
- Storefront: HTTP `200` through CloudFront.
- `flagd`: Deployment `1/1`, one Ready EndpointSlice endpoint.
- `/grafana`, `/jaeger`, `/feature` and `/loadgen`: HTTP `403` through the public
  CloudFront distribution.
- Reconciled PolicyReports: `activeFailures=[]`, `staleResults=[]`,
  `unresolvedResults=[]`; three active AIOps results map to the approved
  `m05-baseline-aiops-engine-runtime` exception.
- Admission-controller log scan after cutover: no new parse, substitution or
  unsupported-type engine errors.

## Remaining acceptance items

The Enforce cutover is complete. Mandate 05 remains open until:

1. the mentor performs the agreed rejection demonstration;
2. retained PM-101 Trivy/Cosign artifacts are packaged in the final evidence
   set; and
3. the two time-bounded runtime exceptions receive final mentor disposition or
   are remediated.
