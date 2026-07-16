# SCRUM-199 - Prepare AI Bedrock Integration

Ngay cap nhat: 2026-07-16
Phu trach: CDO02

## Scope

Chuan bi rollout AI runtime that cho `product-reviews` bang AWS Bedrock theo cach an toan, tach pha chuan bi ha tang/khoi tao quyen voi pha bat runtime.

## Evidence

- PR rollout preparation: `#140`
  Link: <https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/pull/140>
- PR enable Bedrock runtime: `#142`
  Link: <https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/pull/142>
- PR chuan hoa runbook AI: `#144`
  Link: <https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/pull/144>
- Terraform role cho Bedrock:
  [infra/modules/eks-platform/product-reviews-bedrock.tf](C:/Users/Admin/Desktop/xbrain-phase-3/Phase3-TF3-Infra-Sentinel/infra/modules/eks-platform/product-reviews-bedrock.tf)
- Runbook rollout AI:
  [docs/runbooks/aio-bedrock-rollout.md](C:/Users/Admin/Desktop/xbrain-phase-3/Phase3-TF3-Infra-Sentinel/docs/runbooks/aio-bedrock-rollout.md)

## Outcome

- Tach rollout thanh 2 pha de giam rui ro production.
- Tao IRSA role rieng cho `product-reviews` de goi Bedrock.
- Xac minh runtime Bedrock da duoc bat dung service account, dung image, dung env.
