# Ghi chú task: Image supply chain

## Mục tiêu

Task này siết chuỗi cung ứng image theo 3 lớp:

1. ECR không cho ghi đè tag sau release.
2. Helm/manifest giữ được tag + digest để rollback không phụ thuộc tag mutable.
3. Có gate scan để chặn image có HIGH/CRITICAL vượt ngưỡng đã thống nhất.

## Đã làm

- Thêm resource Terraform cho ECR `techx-corp` và đặt:
  - `image_tag_mutability = "IMMUTABLE"`
  - `scan_on_push = true`
- Mở rộng Helm chart để hỗ trợ `digest` trong image ref.
- Pin digest cho các app image đang chạy trong `phase3 - information/deploy/values-prod.yaml`.
- Thêm workflow gate scan ECR sau khi build/push.
- Ghi lại bảng digest và các exception cần review định kỳ trong file này.

## Vì sao làm như vậy

- Tag mutable làm rollback và audit khó tin cậy.
- Digest là định danh thật của artifact, nên giữ được đúng image đã kiểm thử.
- Scan gate giúp chặn release xấu trước khi image được dùng rộng.
- Zero downtime vẫn giữ được vì chỉ đổi cách trỏ image, không đổi service surface hay rollout strategy.

## Trạng thái live đã kiểm tra

- Namespace `techx-tf3` đang chạy ổn.
- ECR repo `techx-corp` trước khi chuẩn hóa đang báo `MUTABLE`.
- Live cluster có các pod app đang chạy bình thường, không có thay đổi scale/replica ngoài phạm vi task này.

## Bảng digest image app đang chạy

| Component | Tag | Digest |
|---|---|---|
| accounting | `6a3fe95-accounting` | `sha256:8fc8a91f98ae40d6be284ff9009b32dd0e1e1c3152532362ed363f8bc71c4ed6` |
| ad | `58b13f2-ad` | `sha256:a45fdb96972c11c4b75261ef1205f96c92f5c23fb5edbc47f3b6bb95eb3f27bb` |
| cart | `6a3fe95-cart` | `sha256:1cc20ba4d7f195245429e084e5aa495a305ed0b14539261953f8595ab50c05b6` |
| checkout | `7527509-checkout` | `sha256:a774cb69f27795406f768881a7c575ba882f024f8e99ca928413047f3b3eb532` |
| currency | `58b13f2-currency` | `sha256:e4e4c76b27fea4d82bbc25aa2f2d6c2163450a223f89c71e7ae4985fb6c0203a` |
| email | `58b13f2-email` | `sha256:ca14e55cc0855e3a8a2de19098d75f69772408d2bef6f9b52663e864ae1a545f` |
| fraud-detection | `58b13f2-fraud-detection` | `sha256:b4797d6b16bf6a3b88ec8ddb9dbcd6c29c208e6be221f4f018af4b5f624fbc13` |
| frontend | `58b13f2-frontend` | `sha256:047faed92fe4ecf8b2bb7d3d99c191a2d495f41024abc44c204fe94a9ae019a3` |
| frontend-proxy | `6a3fe95-frontend-proxy` | `sha256:7cf4dd2e0c5cdf097ee8c56600ca94b31d4bd1fc04965dac13f6c26262287630` |
| image-provider | `58b13f2-image-provider` | `sha256:00b73a3efd2caab3e69fce24b40b4e176da5c5f89b7b2c8ae2f37c25400cf44a` |
| kafka | `58b13f2-kafka` | `sha256:afc05edcd00b7f56c8331d5e4a83c7ff6bf46182fd0667033529c964bccc2e68` |
| llm | `58b13f2-llm` | `sha256:85a7578ef9b826196632fdd219eaa131f0caed024753499d036fc5baabf374b8` |
| load-generator | `58b13f2-load-generator` | `sha256:db7016dbed1d6b24c5aa6beb1102fd11148aa791a6b61b745ef8fdebc6146641` |
| payment | `58b13f2-payment` | `sha256:839b9cb5e5c50ba9a03acea8a4b15e29be724089e30cf18904530a1bc07bede5` |
| product-catalog | `6a3fe95-product-catalog` | `sha256:412f75faac8b02fc48676c1fe2d3bc695e39b9cf6c0fbd6bb941c1fbea80f83f` |
| product-reviews | `6a3fe95-product-reviews` | `sha256:4d5403f3b7beda840dad76b406e1a25f4d1dd90248638930ed4327bdb1517439` |
| quote | `58b13f2-quote` | `sha256:97fbf36ede49bb20218b75bfe0f2c9e90ed976114813091abb11ca789f567df3` |
| recommendation | `6a3fe95-recommendation` | `sha256:7b1246d011356a0e6d2b0b94b854b2bc3eb0ee06a502d02d9a79a3163b447b78` |
| shipping | `58b13f2-shipping` | `sha256:4952c73703cca38ec8afe934a3571f5f0a5f5e8e2adeb4af3eafc5cfa5ddb3ec` |

## Exception / chưa pin ở mức này

- `flagd`: image external từ GHCR, không thuộc repo `techx-corp`.
- `postgres:17.6`, `valkey/valkey:9.0.1-alpine3.23`, `docker.io/grafana/grafana:13.0.1`, `jaegertracing/jaeger:2.17.0`, `quay.io/prometheus/prometheus:v3.11.3`, `opensearchproject/opensearch:3.6.0`, `otel/opentelemetry-collector-contrib:0.151.0`.
- Lý do: các image này đến từ chart/subchart vendor hoặc component nền tảng, nên review version/digest theo chu kỳ riêng thay vì pin gộp như app image.

## Lịch review đề xuất

- App image nội bộ: review lại mỗi lần release.
- External image nền tảng: review định kỳ hàng tháng hoặc khi upstream có CVE đáng chú ý.
- Nếu digest thay đổi mà tag không đổi: phải coi là drift và cập nhật release note ngay.

## Cách kiểm tra lại

```bash
aws ecr describe-repositories --repository-names techx-corp --region ap-southeast-1
kubectl -n techx-tf3 get pods -o wide
kubectl -n techx-tf3 describe pod <pod>
aws ecr describe-image-scan-findings --repository-name techx-corp --region ap-southeast-1 --image-id imageDigest=<digest>
```

## Ghi chú vận hành

- Tag chỉ là nhãn release.
- Digest mới là artifact thật đang chạy.
- Khi rollback, ưu tiên quay về digest cũ đã ghi trong note/release history, không dựa vào tag có thể bị ghi đè.
