# JIRA Ticket: COST-05.1 - Load-Gen Investigation & Root Cause Analysis

**Ticket ID:** SCRUM-170.1 / TF3-COST-051  
**Parent:** SCRUM-170 (COST-05 load-gen OOM root cause)  
**Type:** Investigation  
**Priority:** Medium  
**Reporter:** CDO-02  
**Assignees:** CDO-02  
**Status:** In Progress  
**Created:** 16 July 2026 17:00  
**Target Completion:** 16 July 2026 19:00 (2 hours)  

---

## Summary

Investigate load-gen pod to determine if it is experiencing OOMKilled issues, analyze memory usage patterns, identify root cause, and calculate required resource limits for remediation.

---

## Investigation Checklist

### Step 1: Check Pod Status (15 minutes)

**Commands:**
```bash
# Check if load-gen pods exist
kubectl get pods -n techx-tf3 -l app=load-gen

# Expected outputs:
# Scenario A: Pod running
# Scenario B: Pod in CrashLoopBackOff
# Scenario C: No pods found
```

**Document:**
- [ ] Number of load-gen pods
- [ ] Current status (Running/CrashLoopBackOff/Pending)
- [ ] Restart count
- [ ] Age

---

### Step 2: Inspect Pod Details (15 minutes)

**If pod exists:**
```bash
# Get pod name
POD_NAME=$(kubectl get pods -n techx-tf3 -l app=load-gen -o jsonpath='{.items[0].metadata.name}')

# Describe pod
kubectl describe pod $POD_NAME -n techx-tf3 > D:\Capstone\Phase3-TF3-Infra-Sentinel\logs\load-gen-describe.txt

# Key information to extract:
# 1. Last State (look for Exit Code 137 = OOMKilled)
# 2. Current resource limits
# 3. Events (OOMKilling, Unhealthy, BackOff)
```

**Check for OOMKilled:**
```bash
# Search for Exit Code 137
grep "Exit Code: 137" D:\Capstone\Phase3-TF3-Infra-Sentinel\logs\load-gen-describe.txt

# If found: OOMKilled confirmed ❌
# If not found: Check other exit codes
```

**Document:**
- [ ] Exit code from Last State
- [ ] Current memory limit
- [ ] Current memory request
- [ ] Events indicating crashes

---

### Step 3: Analyze Logs (20 minutes)

**Get logs from previous run (if crashed):**
```bash
# Previous container logs
kubectl logs $POD_NAME -n techx-tf3 --previous --tail=200 > D:\Capstone\Phase3-TF3-Infra-Sentinel\logs\load-gen-previous.log

# Current logs (if running)
kubectl logs $POD_NAME -n techx-tf3 --tail=200 > D:\Capstone\Phase3-TF3-Infra-Sentinel\logs\load-gen-current.log
```

**Analyze patterns:**
- Memory allocation errors
- Gradual memory increase
- Sudden spikes
- User count correlation

**Document:**
- [ ] Error messages related to memory
- [ ] Memory allocation patterns
- [ ] Load test configuration (user count, duration)

---

### Step 4: Check Current Memory Usage (10 minutes)

**If pod is running:**
```bash
# Real-time memory usage
kubectl top pod $POD_NAME -n techx-tf3

# Expected output format:
# NAME                     CPU(cores)   MEMORY(bytes)
# load-gen-xxxx-yyyy       100m         ???Mi

# Calculate utilization percentage
# Usage% = (MEMORY / Limit) × 100
```

**Document:**
- [ ] Current memory usage (Mi)
- [ ] Current CPU usage
- [ ] Utilization percentage

---

### Step 5: Check Historical Metrics (30 minutes)

**Query Prometheus (if available):**
```promql
# Memory usage over 7 days
container_memory_usage_bytes{pod=~"load-gen.*", namespace="techx-tf3"}

# Memory limit
container_spec_memory_limit_bytes{pod=~"load-gen.*", namespace="techx-tf3"}

# Peak usage
max_over_time(container_memory_usage_bytes{pod=~"load-gen.*"}[7d])
```

**Check Grafana Dashboard:**
- Navigate to "Pod Memory Usage" dashboard
- Filter: pod=load-gen, namespace=techx-tf3
- Time range: Last 7 days

**Document:**
- [ ] Average memory usage
- [ ] Peak memory usage
- [ ] Memory usage trend (increasing/stable)
- [ ] Correlation with events (load test runs)

---

### Step 6: Review Load-Gen Configuration (20 minutes)

**Check deployment manifest:**
```bash
# Find load-gen configuration
kubectl get deployment load-gen -n techx-tf3 -o yaml > D:\Capstone\Phase3-TF3-Infra-Sentinel\logs\load-gen-deployment.yaml

# Or check Helm values
grep -A 20 "load-gen:" phase3\ -\ information/deploy/values-prod.yaml
```

**Extract:**
- [ ] User count configuration
- [ ] Test duration
- [ ] Request patterns
- [ ] Resource limits/requests

---

### Step 7: Root Cause Analysis (20 minutes)

**5 Whys Analysis:**

**If OOMKilled (Exit Code 137):**

1. **Why did pod crash?**
   - Pod was OOMKilled (Exit Code 137)

2. **Why was pod OOMKilled?**
   - Memory usage exceeded limit

3. **Why did memory usage exceed limit?**
   - [INVESTIGATE: Load test workload? Memory leak? Configuration?]

4. **Why does load test use so much memory?**
   - [INVESTIGATE: User count? Request buffering? Data structures?]

5. **Why wasn't limit set appropriately?**
   - Initial sizing didn't account for actual workload

**Document:**
- [ ] Primary root cause
- [ ] Contributing factors
- [ ] Evidence supporting conclusion

---

## Findings Template

### Summary of Investigation

**Pod Status:**
- State: [Running / CrashLoopBackOff / Not Found]
- Restarts: [count]
- Age: [duration]

**OOMKilled Status:**
- Confirmed: [Yes / No]
- Exit Code: [137 or other]
- Last OOMKilled: [timestamp]

**Current Configuration:**
```yaml
resources:
  requests:
    cpu: ???
    memory: ???Mi
  limits:
    cpu: ???
    memory: ???Mi
```

**Actual Usage:**
- Average: ???Mi
- Peak: ???Mi
- Current: ???Mi
- Utilization: ???%

**Root Cause:**
[Description of why OOMKilled occurred or why at risk]

**Evidence:**
- Exit Code 137 in pod describe
- Logs showing memory errors
- Prometheus metrics showing usage trend
- [Other evidence]

---

## Recommendations

### Scenario A: OOMKilled Confirmed

**Recommended Action:**
- Increase memory limit from ???Mi to ???Mi
- Rationale: Peak usage (???Mi) + 20-50% headroom
- Cost impact: $X/month

**Next Steps:**
1. Update COST-05.2 ticket with findings
2. Implement fix in COST-05.2
3. Monitor for 24h post-fix

---

### Scenario B: High Risk (80%+ utilization)

**Recommended Action:**
- Proactively increase memory limit
- Rationale: Prevent future OOMKilled
- Cost impact: $X/month

**Next Steps:**
1. Update COST-05.2 ticket
2. Implement preventive fix

---

### Scenario C: Stable (No Action Required)

**Finding:**
- Memory usage healthy (< 70% utilization)
- Adequate headroom
- No OOMKilled history

**Recommended Action:**
- No changes needed
- Continue monitoring

**Next Steps:**
1. Document configuration as baseline
2. Close parent ticket SCRUM-170

---

## Deliverables

### Investigation Report

Create detailed report:

**File:** `docs/postmortem/load-gen-memory-investigation-report.md`

**Contents:**
1. Executive Summary
2. Investigation Methodology
3. Findings
4. Root Cause Analysis
5. Recommendations
6. Next Steps

### Update Parent Ticket

Update SCRUM-170 with:
- Investigation results
- Root cause (if OOMKilled)
- Recommended fix (if needed)
- Link to COST-05.2 (if proceeding with fix)

---

## Success Criteria

- [ ] Pod status determined (Running/CrashLoopBackOff/Not Found)
- [ ] OOMKilled status confirmed (Yes/No)
- [ ] Current resource limits documented
- [ ] Actual memory usage measured (average/peak)
- [ ] Root cause identified (if OOMKilled)
- [ ] Recommendations documented
- [ ] Investigation report created
- [ ] Parent ticket updated

---

## References

- **Parent:** SCRUM-170 (COST-05)
- **Related:** COST-04.1 (Fix OOMKilled pods methodology)
- **Related:** TF3-OPS-0003 (aiops-engine incident - similar pattern)

---

## Labels

- `investigation`
- `oomkilled`
- `load-gen`
- `memory-analysis`
- `cdo-02`

---

**Created:** 16 Jul 2026 17:00  
**Target:** 16 Jul 2026 19:00  
**Owner:** CDO-02  
**Status:** In Progress
