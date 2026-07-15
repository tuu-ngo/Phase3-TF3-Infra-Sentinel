# Mandate #2 — Báo cáo kết quả load test flash sale (200 user / 15 phút)

**Ngày chạy test:** _(điền sau khi chạy)_
**Người chạy:** _(điền)_
**Người xác nhận/chứng kiến (mentor, nếu có):** _(điền)_

> File này là template nộp cho mandate — điền vào sau khi chạy xong Bước 1-3 của
> `docs/runbooks/flash-sale-load-test.md`. Đối chiếu lại đúng 2 yêu cầu "Phải nộp" trong
> `MANDATE-02-scale-under-budget.md`: (1) SLO giữ + cost trong trần, kèm cost trước/sau hoặc
> cost/đơn; (2) cách cho mentor chạy lại hoặc chứng kiến để tự xác nhận.

---

## 1. Chuẩn bị trước test (đã làm)

- [ ] Backup thủ công 3 datastore xong (`$BACKUP_DIR`: _điền đường dẫn_)
- [ ] flagd healthy, tất cả flag `off`/`0`/`false` xác nhận qua OFREP (đính kèm output)
- [ ] Ramp thử nhỏ (50 user) đã chạy ổn, đã reset stats trước khi vào 200 chính thức
- [ ] Abort threshold đã chốt (xem runbook) — người trực đã đọc và hiểu tiêu chí dừng
- [ ] Baseline trước test đã chụp (HPA replicas, số node, cost) — xem mục 4

## 2. Kết quả SLO — 3 ngưỡng bắt buộc

| SLO | Ngưỡng | Kết quả đo được | Đạt? |
|---|---|---|---|
| Checkout success rate | ≥ 99% | _điền_ | ☐ |
| Browse/Cart success rate | ≥ 99.5% | _điền_ | ☐ |
| Storefront p95 latency | < 1000ms | _điền_ | ☐ |

**Ảnh chụp cần đính kèm** (lưu vào `docs/postmortem/images/` hoặc thư mục ảnh riêng cho mandate 02, đặt tên rõ ràng, tham chiếu lại ở đây):
1. Grafana `apm-dashboard`/`slo-dashboard` — toàn bộ cửa sổ 15 phút @200 user, thấy rõ cả 3 đường success-rate + p95, có timestamp.
2. Grafana panel HPA replicas theo thời gian — thấy rõ đường **co lên** trong lúc tải và **co xuống** sau đỉnh (nối liền với mục 4 bên dưới).
3. `kubectl get nodepool,nodeclaim` (hoặc Karpenter dashboard nếu có) — lúc đỉnh tải, thấy Spot node được thêm.
4. (Nếu có sự cố abort) Ảnh chụp đúng lúc chạm abort threshold + log/event liên quan.

Nếu có bất kỳ ngưỡng nào KHÔNG đạt: ghi rõ nguyên nhân, đã fix hay chưa, có test lại không — không che giấu, đúng tinh thần honesty của toàn bộ tài liệu program này.

## 3. Cost — trong trần, cost/đơn không phình

| Mốc | Cost | Nguồn |
|---|---|---|
| Baseline (trước test, /ngày hoặc /giờ tương ứng) | _điền_ | AWS Cost Explorer |
| Trong cửa sổ test (15 phút @200 user, quy đổi) | _điền_ | AWS Cost Explorer |
| Số đơn checkout thành công trong cửa sổ test | _điền_ | Grafana / Postgres `accounting` |
| **Cost / đơn trong test** | _điền_ (= cost cửa sổ test / số đơn) | tính toán |
| **Cost / đơn baseline** (đối chiếu, tải thường) | _điền_ | tính toán từ traffic ngày thường |

**Kết luận cost:** _điền — cost/đơn có phình so với baseline không, có vượt trần ~$300/tuần/TF không (quy đổi cửa sổ test ra tỷ lệ tuần nếu cần)._

Ảnh chụp cần đính kèm: AWS Cost Explorer trước/sau (hoặc trong ngày chạy test), có timestamp rõ ràng.

## 4. Co lên → co xuống (bằng chứng scale thật, không neo tài nguyên)

| Mốc | Số pod (tổng HPA-managed) | Số node | Ghi chú |
|---|---|---|---|
| Trước test (baseline) | _điền_ | _điền_ | |
| Đỉnh tải (~200 user) | _điền_ | _điền_ | |
| Sau đỉnh (~10 phút sau khi dừng loadgen) | _điền_ | _điền_ | phải gần bằng baseline |

Nếu sau 10 phút vẫn chưa co xuống về gần baseline: ghi rõ lý do (Karpenter `consolidateAfter` đang set 1h cho cửa sổ test — nhắc đã đổi lại `2m` chưa, xem runbook Bước 3) và thời điểm co xuống thực tế.

- [ ] **Đã đổi `consolidateAfter` về lại `2m`** sau khi xác nhận co xuống (bắt buộc — để lâu tốn thêm chi phí, đi ngược mục tiêu cost của chính mandate này).
- [ ] **Đã gỡ `podAnnotations.karpenter.sh/do-not-disrupt`** khỏi cả 5 component (`cart`, `checkout`, `payment`, `shipping`, `quote`) trong `values-prod.yaml` — xem `docs/mandate-02-load-test-remediation-plan.md` mục 0 để đối chiếu danh sách đầy đủ.

## 5. Điểm nghẽn tự phát hiện và đã xử (yêu cầu #3 của mandate — "tự tìm và xử điểm nghẽn")

Liệt kê các điểm nghẽn phát hiện được **trong quá trình chuẩn bị/chạy test này**, đã xử lý ra sao — tham chiếu `docs/mandate-02-load-test-remediation-plan.md` để không lặp lại nội dung, chỉ tóm tắt:

1. Checkout canary rollout Degraded do Karpenter consolidation quá nhạy (`consolidateAfter: 2m`) evict pod đúng lúc phân tích SLO → tăng lên `1h` cho cửa sổ test.
2. Pod quota namespace gần chạm trần (42/90 → cộng dồn HPA max có thể chạm) → tăng lên 100.
3. Observability (Prometheus/OpenSearch/Kafka) gần chạm memory limit ở tải thấp, rủi ro OOM đúng lúc cần bằng chứng nhất → tăng limit cả 3.
4. `payment`/`shipping`/`quote` memory limit quá mỏng, không HPA → tăng limit (payment đã dùng ~50% limit chỉ với 10 user nền).
5. Checkout thiếu `topologySpreadConstraints` — 2 pod từng nằm chung 1 node, rủi ro mất cả 2 nếu node chết → đã thêm spread theo hostname + zone.
6. _(điền thêm nếu phát hiện gì mới trong lúc chạy test thật, kể cả nếu phải xử lý real-time)_

## 6. Cách cho mentor chạy lại / chứng kiến (yêu cầu bắt buộc của mandate)

Mentor có thể tự xác nhận bằng 1 trong 2 cách:

**Cách A — Chứng kiến trực tiếp lúc chạy lại:**
```bash
# 1. Baseline trước khi bắt đầu (mentor tự chạy để so sánh)
kubectl -n techx-tf3 get hpa
kubectl get nodes

# 2. Chạy load test (xem chi tiết docs/runbooks/flash-sale-load-test.md Bước 1)
kubectl -n techx-tf3 set env deploy/load-generator LOCUST_USERS=200 LOCUST_SPAWN_RATE=20
kubectl -n techx-tf3 rollout restart deploy/load-generator

# 3. Theo dõi trực tiếp qua Grafana (port-forward riêng tư, xem private-access-to-ops-uis.md)
kubectl -n techx-tf3 port-forward svc/grafana 3000:80
#   -> http://localhost:3000, dashboard apm-dashboard / slo-dashboard

# 4. Sau 15 phút, dừng tải và xác nhận co xuống
kubectl -n techx-tf3 set env deploy/load-generator LOCUST_USERS=0
kubectl -n techx-tf3 get hpa    # đợi ~5-10 phút, xem replicas co về min
```

**Cách B — Xem lại bằng chứng đã lưu (nếu mentor không chạy được real-time):**
- Ảnh chụp Grafana/Cost Explorer đính kèm ở mục 2-3.
- File này (`docs/mandate-02-load-test-report.md`) + `docs/mandate-02-load-test-remediation-plan.md` làm bằng chứng quá trình chuẩn bị.
- Log rollout/events tại thời điểm test (nếu còn giữ, `kubectl` history có giới hạn thời gian retention).

## 7. Kết luận

_(điền sau khi có đủ số liệu mục 2-4)_ — GO/NO-GO thực tế đạt được, có cần chạy lại lần nữa không, và nếu không đạt thì bước tiếp theo là gì.
