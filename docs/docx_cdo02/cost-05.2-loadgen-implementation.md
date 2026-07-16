# JIRA Ticket: COST-05.2 - Load-Gen Fix Implementation

**Ticket ID:** SCRUM-170.2 / TF3-COST-052  
**Parent:** SCRUM-170 (COST-05 load-gen OOM root cause)  
**Type:** Implementation & Deployment  
**Priority:** Medium  
**Reporter:** CDO-02  
**Assignees:** CDO-02  
**Status:** Pending (Blocked by COST-05.1)  
**Created:** 16 July 2026 17:00  
**Target Completion:** 17 July 2026 18:00  

---

## Summary

Implement fix for load-gen memory issues based on findings from COST-05.1 investigation. Update resource limits, deploy via GitOps, verify stability, and close parent ticket.

---

## Prerequisites

**Blocked by:** COST-05.1 (Investigation must complete first)

**Required Input from COST-05.1:**
- [ ] OOMKilled status (Yes/No)
- [ ] Current memory limit
- [ ] Peak memory usage
- [ ] Recommended new limit
- [ ] Root cause analysis

---

## Implementation Plan

### Phase 1: Update Configuration (30 minutes)

**Based on COST-05.1 findings:**

#### Scenario A: Fix Required

**File to modify:** `phase3 - information/deploy/values-prod.yaml`

**Current configuration (TBD from investigation):**
```yaml
components:
  load-gen:
    resources:
      requests:
        cpu: ???m
        memory: ???Mi
      limits:
        cpu: ???m
        memory: ???Mi        # ← Current limit (insufficient)
```

**New configuration (values from COST-05.1):**
```yaml
components:
  load-gen:
    resources:
      requests:
        cpu: ???m
        memory: ???Mi        # ← Increased to peak × 1.2
      limits:
        cpu: ???m
        memory: ???Mi        # ← Increased to peak × 1.5
    
    # Optional: Add if load-gen needs longer startup
    readinessProbe:
      httpGet:
        path: /health
        port: 8080
      initialDelaySeconds: 30
      timeoutSeconds: 5
      periodSeconds: 10
      failureThreshold: 3
    
    livenessProbe:
      httpGet:
        path: /health
        port: 8080
      initialDelaySeconds: 60
      timeoutSeconds: 5
      periodSeconds: 30
      failureThreshold: 3
```

**Rationale:**
- New limit based on: [Peak usage from COST-05.1] + [X% headroom]
- Prevents OOMKilled during normal operation
- Allows for traffic spikes

**Cost Impact:** $X/month (calculate based on limit increase)

---

#### Scenario B: No Fix Required

**If COST-05.1 determines no action needed:**
- Document current stable configuration
- Add monitoring/alerts as preventive measure
- Close parent ticket

---

### Phase 2: Git Workflow (15 minutes)

**Create feature branch:**
```bash
cd D:\Capstone\Phase3-TF3-Infra-Sentinel

# Pull latest
git checkout main
git pull origin main

# Create branch
git checkout -b feat/cost-05-fix-loadgen-memory

# Edit values-prod.yaml
# Update load-gen resources section

# Commit with detailed message
git add phase3\ -\ information/deploy/values-prod.yaml
git commit -m "feat(cost-05): Fix load-gen memory limit

- Increase memory limit from XXXMi to YYYMi
- Based on investigation COST-05.1 findings
- Peak usage: ZZZMi, new limit provides AA% headroom
- Prevents OOMKilled during load testing

Root Cause: [Summary from COST-05.1]

Refs: SCRUM-170.2, COST-05.1"

# Push to remote
git push -u origin feat/cost-05-fix-loadgen-memory
```

**Create Pull Request:**
- Title: `feat(cost-05): Fix load-gen memory OOM issue`
- Link to COST-05.1 investigation
- Include cost impact analysis
- Request review from team lead

---

### Phase 3: Deployment (30 minutes)

**Apply via GitOps:**
```bash
# After PR approval + merge

# Check ArgoCD sync status
# UI: https://argocd.arthur-ngo.org/applications/techx-corp

# Manual sync (if needed)
argocd app sync techx-corp

# Watch rollout
kubectl rollout status deployment/load-gen -n techx-tf3

# Verify new pod created
kubectl get pods -n techx-tf3 -l app=load-gen

# Check new resource limits applied
kubectl describe pod <new-load-gen-pod> -n techx-tf3 | grep -A 5 "Limits:"
```

**Expected output:**
```
Limits:
  cpu:     ???m
  memory:  ???Mi        # ← Should match new value
Requests:
  cpu:     ???m
  memory:  ???Mi        # ← Should match new value
```

---

### Phase 4: Verification (24 hours)

#### T+1 hour: Initial Check

```bash
# Pod status
kubectl get pod -n techx-tf3 -l app=load-gen

# Expected: Running, 0 restarts
# NAME                     READY   STATUS    RESTARTS   AGE
# load-gen-xxxx-yyyy       1/1     Running   0          1h

# Check logs (no errors)
kubectl logs -n techx-tf3 -l app=load-gen --tail=50

# Check memory usage
kubectl top pod -n techx-tf3 -l app=load-gen

# Expected: < 80% of new limit
```

#### T+6 hours: Mid-Point Check

```bash
# Restart count (should still be 0)
kubectl get pod -n techx-tf3 -l app=load-gen -o json | \
  jq '.items[0].status.containerStatuses[0].restartCount'

# Check for OOMKilled events (should be none)
kubectl get events -n techx-tf3 --field-selector reason=OOMKilling,involvedObject.name=load-gen-*

# Memory trend (should be stable)
kubectl top pod -n techx-tf3 -l app=load-gen
```

#### T+24 hours: Final Verification

**Success Criteria:**
- [ ] Pod running for 24h without restart
- [ ] No OOMKilled events
- [ ] Memory usage < 80% of new limit
- [ ] Load test functionality confirmed
- [ ] No errors in application logs

**Verification Commands:**
```bash
# Final checks
kubectl get pods -n techx-tf3 -l app=load-gen
kubectl get events -n techx-tf3 --field-selector reason=OOMKilling
kubectl top pod -n techx-tf3 -l app=load-gen

# Check load test output (if applicable)
kubectl logs -n techx-tf3 -l app=load-gen --tail=100 | grep -E "Users|Requests|Success"
```

---

## Testing Strategy

### Functional Tests

**1. Load Test Execution:**
```bash
# Verify load-gen is running tests
kubectl logs -n techx-tf3 -l app=load-gen --tail=50

# Expected log patterns:
# ✅ "Starting load test with X users"
# ✅ "Request success rate: XX%"
# ✅ "Average response time: XXXms"
# ✅ No memory errors
```

**2. End-to-End Validation:**
- Load-gen should generate traffic to frontend
- Check frontend logs for requests from load-gen
- Verify metrics in Prometheus/Grafana

```bash
# Check if frontend receives load-gen traffic
kubectl logs -n techx-tf3 -l app=frontend --tail=100 | grep load-gen
```

---

## Monitoring & Alerts

### Add Prometheus Alert

**Create alert rule for load-gen:**

```yaml
# prometheus-rules-loadgen.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: loadgen-memory-alerts
  namespace: techx-tf3
spec:
  groups:
    - name: loadgen-memory
      interval: 30s
      rules:
        - alert: LoadGenHighMemory
          expr: |
            container_memory_usage_bytes{pod=~"load-gen.*"} 
            / container_spec_memory_limit_bytes{pod=~"load-gen.*"} 
            > 0.85
          for: 10m
          labels:
            severity: warning
            component: load-gen
          annotations:
            summary: "Load-gen high memory usage"
            description: "Pod {{ $labels.pod }} memory > 85% for 10+ min"
        
        - alert: LoadGenOOMKilled
          expr: kube_pod_container_status_last_terminated_reason{pod=~"load-gen.*", reason="OOMKilled"} == 1
          labels:
            severity: critical
            component: load-gen
          annotations:
            summary: "Load-gen pod was OOMKilled"
            description: "Investigate and increase limit further"
```

**Apply:**
```bash
kubectl apply -f prometheus-rules-loadgen.yaml
```

---

## Rollback Plan

**If pod crashes after deployment:**

```bash
# Option 1: Git revert
git revert HEAD
git push

# Option 2: Manual kubectl patch (immediate)
kubectl patch deployment load-gen -n techx-tf3 -p '{"spec":{"template":{"spec":{"containers":[{"name":"load-gen","resources":{"limits":{"memory":"<OLD_VALUE>"}}}]}}}}'

# Option 3: ArgoCD rollback via UI
```

**Rollback Triggers:**
- Pod crashes 3+ times
- OOMKilled still occurring
- Load test failures
- Critical alerts

---

## Cost Analysis

### Cost Impact (TBD from COST-05.1)

**Before:**
- Memory limit: ???Mi
- Monthly cost: $X

**After:**
- Memory limit: ???Mi
- Monthly cost: $Y
- **Delta:** $Z/month ($ZZ/year)

**Justification:**
- Prevents load test disruptions
- Enables continuous performance validation
- Cost << value of continuous testing

---

## Documentation Updates

### Files to Update

1. ✅ **This ticket** (SCRUM-170.2)
2. ⏳ **Parent ticket** SCRUM-170 (mark complete)
3. ⏳ **Investigation report** (add resolution section)
4. ⏳ **Runbook** `docs/runbooks/load-gen-operations.md` (create if needed)
5. ⏳ **CDO-02 Mandate Summary** (update MANDATE #8 progress)

---

## Success Criteria

- [ ] Configuration updated in values-prod.yaml
- [ ] Changes committed and pushed
- [ ] PR approved and merged
- [ ] ArgoCD synced successfully
- [ ] New pod running with updated limits
- [ ] No restarts for 24 hours
- [ ] No OOMKilled events
- [ ] Memory usage < 80% of new limit
- [ ] Load test functionality verified
- [ ] Monitoring alerts configured
- [ ] Documentation updated
- [ ] Parent ticket closed

---

## Lessons Learned

### Post-Implementation Review

**What Went Well:**
- [TBD after completion]

**What Could Be Improved:**
- [TBD after completion]

**Preventive Measures:**
- Add memory alerts for load-gen
- Include load-gen in quarterly resource audits
- Document load test memory requirements

---

## References

- **Parent:** SCRUM-170 (COST-05)
- **Dependency:** COST-05.1 (Investigation)
- **Related:** COST-04.1 (Similar OOMKilled fix methodology)
- **Config:** `phase3 - information/deploy/values-prod.yaml`

---

## Labels

- `implementation`
- `oomkilled-fix`
- `load-gen`
- `memory-optimization`
- `mandate-8`
- `cdo-02`

---

**Created:** 16 Jul 2026 17:00  
**Blocked By:** COST-05.1  
**Target:** 17 Jul 2026 18:00  
**Owner:** CDO-02  
**Status:** Pending
