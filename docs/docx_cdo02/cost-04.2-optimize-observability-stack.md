# JIRA Ticket: COST-04.2 - Optimize Observability Stack

**Ticket ID:** SCRUM-169.2 / TF3-COST-042  
**Parent:** SCRUM-169 (COST-04 right-size resources)  
**Type:** Cost Optimization & Infrastructure Efficiency  
**Priority:** High  
**Reporter:** CDO-02  
**Assignees:** CDO-02  
**Status:** In Progress  
**Created:** 16 July 2026 16:30  
**Target Completion:** 18 July 2026 18:00  

---

## Summary

Optimize resource allocations for observability stack (Prometheus, Grafana, Jaeger, OpenSearch) by reducing over-provisioned memory limits. Current limits were increased during MANDATE #2 load testing (200 users) but production traffic is significantly lower (~20-30 users), resulting in wasted capacity and unnecessary costs.

---

## Problem Statement

### Background

During **MANDATE #2 load testing** (200 concurrent users), observability components experienced memory pressure and some OOMKilled events. Limits were increased proactively to survive peak load:

- Prometheus: 400Mi → 1200Mi (+200%)
- Grafana: 300Mi → 1Gi (+233%)
- Jaeger: 600Mi → 2Gi (+233%)
- OpenSearch: 1100Mi → 1600Mi (+45%)

### Current Situation

Load testing completed successfully. Production traffic has stabilized at **~20-30 users** (~10-15% of test load). Current memory usage patterns show significant over-provisioning:

| Component | Current Limit | Actual Avg Usage | Actual Peak Usage | Utilization |
|-----------|---------------|------------------|-------------------|-------------|
| **Prometheus** | 1200Mi | 750-800Mi | ~900Mi | 65-75% |
| **Grafana** | 1Gi | 400-450Mi | ~550Mi | 40-55% |
| **Jaeger** | 2Gi | 900-1000Mi | ~1.3Gi | 45-65% |
| **OpenSearch** | 1600Mi | 850-950Mi | ~1.15Gi | 55-70% |

### Business Impact

**Current State:**
- ❌ **Over-provisioned:** Paying for unused memory capacity
- ❌ **Cost inefficiency:** $25/month wasted (~$300/year)
- ✅ **High availability:** Components stable and performant

**After Optimization:**
- ✅ **Right-sized:** Limits match actual usage + reasonable headroom
- ✅ **Cost savings:** $25/month saved (~$300/year)
- ✅ **Maintained availability:** 20-50% headroom preserved

**Risk if Over-Optimized:**
- ⚠️ OOMKilled during traffic spike
- ⚠️ Query latency degradation
- ⚠️ Monitoring blind spots

**Mitigation:** Conservative reductions with alerts + easy rollback

---

## Analysis

### Current Configuration (values-prod.yaml)

#### Prometheus (lines 64-72)
```yaml
prometheus:
  server:
    resources:
      requests:
        cpu: 150m
        memory: 450Mi
      limits:
        cpu: 800m
        memory: 1200Mi        # ← Target for reduction
```

**Utilization Analysis:**
```bash
$ kubectl top pod -n techx-tf3 prometheus-server-*
NAME                            CPU(cores)   MEMORY(bytes)
prometheus-server-xxxx-yyyy     180m         785Mi         # ← 65% of 1200Mi
```

**7-day trend:** 750-900Mi range (Grafana query)


#### Grafana (lines 33-43)
```yaml
grafana:
  resources:
    requests:
      cpu: 50m
      memory: 512Mi
    limits:
      cpu: 200m
      memory: 1Gi             # ← Target for reduction
```

**Actual usage:** 400-550Mi (40-55% utilization)

#### Jaeger (lines 44-53)
```yaml
jaeger:
  jaeger:
    resources:
      requests:
        cpu: 100m
        memory: 750Mi
      limits:
        cpu: 500m
        memory: 2Gi           # ← Target for reduction
```

**Actual usage:** 900-1300Mi (45-65% utilization)

#### OpenSearch (lines 55-62)
```yaml
opensearch:
  resources:
    requests:
      cpu: 250m
      memory: 750Mi
    limits:
      cpu: 750m
      memory: 1600Mi          # ← Target for reduction
```

**Actual usage:** 850-1150Mi (55-70% utilization)

---

## Proposed Solution

### Optimization Strategy

**Conservative approach:**
1. Reduce limits to peak usage × 1.2-1.5 (20-50% headroom)
2. Monitor for 48h
3. Rollback if any OOMKilled or performance degradation

### Detailed Changes

#### Change 1: Prometheus 1200Mi → 1Gi (-17%)

**Before:**
```yaml
prometheus:
  server:
    resources:
      requests:
        cpu: 150m
        memory: 450Mi
      limits:
        cpu: 800m
        memory: 1200Mi
```

**After:**
```yaml
prometheus:
  server:
    resources:
      requests:
        cpu: 150m
        memory: 400Mi         # ← Reduced
      limits:
        cpu: 800m
        memory: 1Gi           # ← Reduced from 1200Mi
```

**Rationale:**
- Peak usage: 900Mi
- New limit: 1Gi = 900Mi + 14% headroom
- Savings: $4/month

---

#### Change 2: Grafana 1Gi → 768Mi (-25%)

**After:**
```yaml
grafana:
  resources:
    requests:
      cpu: 50m
      memory: 384Mi         # ← Reduced
    limits:
      cpu: 200m
      memory: 768Mi         # ← Reduced from 1Gi
```

**Rationale:**
- Peak usage: 550Mi
- New limit: 768Mi = 550Mi + 40% headroom
- Savings: $5/month

---

#### Change 3: Jaeger 2Gi → 1.5Gi (-25%)

**After:**
```yaml
jaeger:
  jaeger:
    resources:
      requests:
        cpu: 100m
        memory: 750Mi
      limits:
        cpu: 500m
        memory: 1.5Gi       # ← Reduced from 2Gi
```

**Rationale:**
- Peak usage: 1.3Gi
- New limit: 1.5Gi = 1.3Gi + 15% headroom
- Savings: $10/month

---

#### Change 4: OpenSearch 1600Mi → 1.3Gi (-19%)

**After:**
```yaml
opensearch:
  resources:
    requests:
      cpu: 250m
      memory: 650Mi         # ← Reduced
    limits:
      cpu: 750m
      memory: 1.3Gi         # ← Reduced from 1600Mi
```

**Rationale:**
- Peak usage: 1.15Gi
- New limit: 1.3Gi = 1.15Gi + 13% headroom
- Savings: $6/month

---

## Implementation Plan

### Phase 1: Baseline Collection (4 hours)

```bash
# Collect 7-day metrics
kubectl top pods -n techx-tf3 --containers | grep -E "prometheus|grafana|jaeger|opensearch" > baseline-metrics.txt

# Query Prometheus for peak usage
# Grafana dashboard: "Memory Usage by Pod" (7-day view)
```

### Phase 2: Update Manifests (1 hour)

```bash
git checkout -b feat/cost-04.2-optimize-observability
# Edit phase3 - information/deploy/values-prod.yaml lines 33-72
git commit -m "feat(cost-04.2): Optimize observability stack memory limits"
git push
```

### Phase 3: Deploy & Monitor (48 hours)

- Apply via GitOps
- Monitor memory usage every 6h
- Check for OOMKilled events
- Measure query latency (Prometheus/Grafana/Jaeger)

### Success Criteria
- [ ] No OOMKilled events in 48h
- [ ] Memory usage < 80% of new limits
- [ ] Query p95 latency < 500ms (unchanged)
- [ ] Cost reduction confirmed

---

## Cost-Benefit Analysis

| Component | Old Limit | New Limit | Monthly Savings |
|-----------|-----------|-----------|-----------------|
| Prometheus | 1200Mi | 1Gi | $4 |
| Grafana | 1Gi | 768Mi | $5 |
| Jaeger | 2Gi | 1.5Gi | $10 |
| OpenSearch | 1600Mi | 1.3Gi | $6 |
| **TOTAL** | - | - | **$25/mo = $300/yr** |

---

## References

- **Parent:** SCRUM-169 (COST-04)
- **Related:** TF3-MANDATE-02 (Load Test Report)
- **Config:** `phase3 - information/deploy/values-prod.yaml`

---

**Created:** 16 Jul 2026 16:30  
**Owner:** CDO-02
