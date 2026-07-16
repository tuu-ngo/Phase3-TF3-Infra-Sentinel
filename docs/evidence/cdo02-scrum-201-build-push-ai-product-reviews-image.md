# SCRUM-201 - Build And Push AI Product-Reviews Image

Ngay cap nhat: 2026-07-16
Phu trach: CDO02

## Scope

Build lai image `product-reviews`, xu ly Trivy fail do OpenSSL packages cu, push artifact da va len ECR va cap nhat deployment dung image sach.

## Evidence

- PR enable rollout dung image da va: `#142`
  Link: <https://github.com/tuu-ngo/Phase3-TF3-Infra-Sentinel/pull/142>
- Dockerfile da duoc va:
  [phase3 - information/techx-corp-platform/src/product-reviews/Dockerfile](C:/Users/Admin/Desktop/xbrain-phase-3/Phase3-TF3-Infra-Sentinel/phase3%20-%20information/techx-corp-platform/src/product-reviews/Dockerfile)
- Values production tro dung image override:
  [phase3 - information/deploy/values-prod.yaml](C:/Users/Admin/Desktop/xbrain-phase-3/Phase3-TF3-Infra-Sentinel/phase3%20-%20information/deploy/values-prod.yaml)

## Outcome

- Trivy fail hom truoc la loi that cua image `product-reviews`, khong phai false positive.
- Da va OpenSSL package trong image, build lai, push lai, va tro deployment sang image moi.
- Khong mo rong pham vi sang cac service khac trong dot build do.
