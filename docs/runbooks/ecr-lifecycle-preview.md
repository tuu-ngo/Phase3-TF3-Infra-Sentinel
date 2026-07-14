# ECR Lifecycle Preview Runbook

Use this before applying `infra/live/production/ecr.tf` to production.

## 1. Preview the policy without applying it

```powershell
$policy = Get-Content .\infra\ecr-lifecycle-preview.json -Raw
aws ecr start-lifecycle-policy-preview `
  --repository-name techx-corp `
  --region ap-southeast-1 `
  --lifecycle-policy-text $policy
```

## 2. Inspect preview results

```powershell
aws ecr get-lifecycle-policy-preview `
  --repository-name techx-corp `
  --region ap-southeast-1 `
  --query "previewResults[].[imageTags,imagePushedAt,action.type,appliedRulePriority]"
```

Expected outcome:

- Current release tags still in use by Helm are **not** selected for expiry.
- Old per-service tags beyond the retention window are selected.
- Old untagged multi-arch artifacts are selected only after the 7-day threshold.

## 3. Emergency rollback

```powershell
aws ecr delete-lifecycle-policy --repository-name techx-corp --region ap-southeast-1
```
