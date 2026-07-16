# JIRA Ticket: COST-04.3 - Security Contexts Compliance

**Ticket ID:** SCRUM-169.3 / TF3-COST-043  
**Parent:** SCRUM-169 (COST-04 right-size resources)  
**Type:** Security & Compliance (MANDATE #5)  
**Priority:** High  
**Reporter:** CDO-02  
**Assignees:** CDO-02  
**Status:** In Progress  
**Created:** 16 July 2026 16:45  
**Target Completion:** 17 July 2026 18:00 (MANDATE #5 deadline)  

---

## Summary

Add security contexts to ALL application pods to comply with MANDATE #5 (Runtime Hardening) and pass Kyverno policy validation. Current pods violate 3 security policies: privilege escalation allowed, capabilities not dropped, seccomp profile not set.

---

## Problem Statement

### Background

**MANDATE #5: Runtime Hardening** requires all pods to run with restrictive security contexts by **17 July 2026**. Currently, Kyverno policies are in `audit` mode (warnings only) but will switch to `enforce` mode at deadline, causing pod creation failures.

### Current Violations

During **incident TF3-OPS-0003** investigation, discovered 3 Kyverno policy violations on aiops-engine pod:

```bash
$ kubectl describe pod aiops-engine-5b48bb4df5-b5jhp -n techx-tf3
Warning  PolicyViolation  policy require-allow-privilege-escalation-false fail
Warning  PolicyViolation  policy drop-all-capabilities fail
Warning  PolicyViolation  policy require-seccomp-profile-runtime-default fail
```

**Audit reveals:** ALL 20+ application pods have same violations.

### Business Impact

**Current Risk (audit mode):**
- ⚠️ Warnings logged but pods still run
- ⚠️ Non-compliant with security best practices

**After deadline (enforce mode):**
- ❌ Pods will **FAIL TO START**
- ❌ Service outages across entire platform
- ❌ Deployments blocked
- ❌ Rollbacks blocked

**Required Action:** Fix ALL pods before 17/07 deadline

---

## Kyverno Policy Requirements

### Policy 1: require-allow-privilege-escalation-false

**Requirement:** Containers must not allow privilege escalation

**Fix:**
```yaml
securityContext:
  allowPrivilegeEscalation: false
```

### Policy 2: drop-all-capabilities

**Requirement:** Containers must drop all Linux capabilities

**Fix:**
```yaml
securityContext:
  capabilities:
    drop:
      - ALL
```

### Policy 3: require-seccomp-profile-runtime-default

**Requirement:** Pods must use RuntimeDefault seccomp profile

**Fix:**
```yaml
podSecurityContext:
  seccompProfile:
    type: RuntimeDefault
```

---

## Proposed Solution

### Standard Security Context Template

Apply to ALL components in `values-prod.yaml`:

```yaml
components:
  <component-name>:
    # Pod-level security context
    podSecurityContext:
      runAsNonRoot: true
      runAsUser: 1000
      fsGroup: 1000
      seccompProfile:
        type: RuntimeDefault
    
    # Container-level security context
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true    # Set false if needs write access
      runAsNonRoot: true
      runAsUser: 1000
      capabilities:
        drop:
          - ALL
```

---

## Affected Components

### All Application Pods (20+ services)

Must add security contexts to:

**Frontend & Gateway:**
- frontend
- frontend-proxy (Envoy)

**Core Services:**
- product-catalog
- cart
- checkout
- payment
- currency
- shipping
- quote

**Backend Services:**
- product-reviews
- recommendation
- accounting
- email
- fraud-detection
- image-provider
- ad
- llm

**Infrastructure:**
- load-gen
- aiops-engine

**Data Stores (special handling):**
- kafka (has initContainer with root)
- postgresql
- valkey

---

## Special Cases

### Pods Needing Write Access

**readOnlyRootFilesystem: false** for:
- aiops-engine (model cache `/app/models`, temp `/tmp`)
- accounting (temp files)
- kafka (persistent storage `/var/lib/kafka`)

**Solution:** Mount emptyDir volumes

```yaml
aiops-engine:
  securityContext:
    readOnlyRootFilesystem: false
  volumeMounts:
    - name: model-cache
      mountPath: /app/models
    - name: tmp
      mountPath: /tmp
  volumes:
    - name: model-cache
      emptyDir: {}
    - name: tmp
      emptyDir: {}
```

### Kafka (Init Container as Root)

Kafka needs root for chown operations but main container runs as 1000:

```yaml
kafka:
  podSecurityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault
  
  initContainers:
    - name: init-kafka-data
      securityContext:
        runAsUser: 0           # ← Root only for init
  
  securityContext:
    allowPrivilegeEscalation: false
    runAsNonRoot: true
    runAsUser: 1000
    capabilities:
      drop:
        - ALL
```

---

## Implementation Plan

### Phase 1: Audit Current State (1 hour)

```bash
# Check all policy violations
kubectl get pods -n techx-tf3 -o json | \
  jq -r '.items[] | select(.metadata.annotations["policies.kyverno.io/last-applied-patches"] != null) | .metadata.name' | \
  wc -l

# Expected: 20+ pods
```

### Phase 2: Update All Components (4 hours)

```bash
git checkout -b feat/cost-04.3-security-contexts

# Edit phase3 - information/deploy/values-prod.yaml
# Add security contexts to ALL components (20+ sections)

git commit -m "feat(cost-04.3): Add security contexts for MANDATE #5 compliance"
git push
```

**CRITICAL:** Merge with COST-04.1 to avoid YAML conflicts!

### Phase 3: Deploy & Verify (1 hour)

```bash
# Apply via GitOps
# Watch rollout
kubectl get pods -n techx-tf3 -w

# Check no violations
kubectl get events -n techx-tf3 --field-selector reason=PolicyViolation

# Verify all pods running
kubectl get pods -n techx-tf3 | grep -v Running | grep -v Completed
```

### Success Criteria
- [ ] Zero Kyverno policy violations
- [ ] All pods in Running state
- [ ] No permission denied errors in logs
- [ ] Functional tests passing

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Pods fail to start | Critical | Test in dev first, rollback ready |
| Permission denied errors | High | Identify write paths, mount emptyDir |
| Init containers blocked | Medium | Allow root only for init, main as non-root |
| Kyverno enforce mode | Critical | Complete before 17/07 deadline |

---

## Testing Strategy

### Pre-Deployment

1. **YAML validation:**
```bash
yamllint values-prod.yaml
helm template techx-corp ./techx-corp-chart -f values-prod.yaml --debug
```

2. **Dry-run in dev namespace**

### Post-Deployment

1. **Check violations:**
```bash
kubectl get events -n techx-tf3 --field-selector reason=PolicyViolation
# Expected: 0 events
```

2. **Check pod status:**
```bash
kubectl get pods -n techx-tf3
# Expected: All Running
```

3. **Check logs for permission errors:**
```bash
kubectl logs -n techx-tf3 -l app=<app-name> --tail=50 | grep -i "permission denied"
# Expected: No results
```

---

## Cost-Benefit Analysis

**Cost:** $0 (security contexts have no resource cost)

**Benefit:**
- ✅ MANDATE #5 compliance (deadline 17/07)
- ✅ Enhanced security posture
- ✅ Prevention of service outages when enforce mode activates
- ✅ Industry best practices (CIS Kubernetes Benchmark)

---

## References

- **Parent:** SCRUM-169 (COST-04)
- **Related:** TF3-OPS-0003 (aiops-engine incident)
- **Mandate:** MANDATE #5 (Runtime Hardening) - deadline 17/07
- **Config:** `phase3 - information/deploy/values-prod.yaml`
- **Policies:** `gitops/policies/kyverno/*`

---

## Labels

- `security`
- `compliance`
- `mandate-5`
- `kyverno`
- `pod-security`
- `high-priority`
- `cdo-02`

---

**Created:** 16 Jul 2026 16:45  
**Deadline:** 17 Jul 2026 18:00 (MANDATE #5)  
**Owner:** CDO-02
