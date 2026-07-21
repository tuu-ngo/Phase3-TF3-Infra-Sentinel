# Artifact — NetworkPolicy backup sự cố 0012 (Mandate #5)

Bản sao **nguyên trạng** các NetworkPolicy do CDO01 (IAM `cdo-admin-team`) apply tay lúc
`2026-07-20T14:55Z` (Mandate #5), **trước khi CDO02 rollback** để khôi phục sự cố P1.
Xem [postmortem 0012](../../0012-mandate5-networkpolicy-batch-outage.md).

| File | Nội dung |
|---|---|
| `mandate5-all-networkpolicies-backup.yaml` | Toàn bộ NetworkPolicy trong `techx-tf3` tại thời điểm rollback (17 policy batch còn lại **+ các policy pre-existing** grafana/kafka/postgres/valkey/… KHÔNG thuộc Mandate #5). |
| `checkout-network-policy-backup-cdo01.yaml` | Policy checkout (xoá đầu tiên, không có trong all-backup). |
| `product-catalog-network-policy-backup-cdo01.yaml` | Policy product-catalog (xoá trước all-backup). |
| `product-reviews-network-policy-backup-cdo01.yaml` | Policy product-reviews (xoá trước all-backup). |
| `recommendation-network-policy-backup-cdo01.yaml` | Policy recommendation (xoá trước all-backup). |

## ⚠️ Cho CDO01 khi dựng lại
**KHÔNG apply lại nguyên trạng** — các policy này gây outage vì:
1. Egress ra datastore chỉ cho `podSelector` store CŨ in-cluster (`postgresql`/`valkey-cart`/`kafka` pod),
   **thiếu `ipBlock`** cho managed endpoint (RDS `…:5432`, ElastiCache `…:6379`, MSK `…:9096`) sau Mandate #8.
2. Egress kiểu `podSelector` tới **ClusterIP Service** không được VPC CNI network-policy permit
   → mọi lời gọi service-to-service bị drop dù rule "allow".

Sửa: dùng `ipBlock` (pod CIDR / service CIDR / managed-store CIDR) cho egress, và test kỹ trên
AWS VPC CNI network policy TRƯỚC khi apply hàng loạt.
