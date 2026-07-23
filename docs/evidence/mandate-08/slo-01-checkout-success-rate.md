# Evidence SLO — checkout success rate (Mandate #8)

**Đo:** 22/07/2026 · **Nguồn:** Prometheus in-cluster · **Cửa sổ dữ liệu còn giữ:** 17/07 10:59 UTC → nay

> ⚠️ Prometheus dùng `emptyDir` (ephemeral) + `retention=7d`. Số liệu dưới đây **chụp lại tại thời điểm đo**;
> pod restart là mất. Đây là bản lưu bền.

## Công thức SLO chính thức của hệ thống

Lấy đúng từ `AnalysisTemplate/checkout-slo` mà Argo Rollouts dùng làm cổng gác canary:

```promql
1 - (
  (sum(rate(traces_span_metrics_calls_total{service_name="checkout", status_code="STATUS_CODE_ERROR"}[w])) or vector(0))
  /
  clamp_min(sum(rate(traces_span_metrics_calls_total{service_name="checkout"}[w])), 0.001)
)
```

---

## 1. Tổng thể (5 ngày gần nhất)

| Chỉ số | Giá trị |
|---|---|
| Tổng request checkout | **3.180.572** |
| Request lỗi (`STATUS_CODE_ERROR`) | **2.754** |
| **Success rate** | **99,913 %** |
| Error budget (ngưỡng 99%) | cho phép 31.806 lỗi — **dùng 2.754 (≈8,7 %)** |

→ Theo **error budget**, SLO tổng thể **ĐẠT** (99,91 % > 99 %), còn dư ~91 % ngân sách lỗi.

## 2. Theo từng giờ — chỉ 2/116 giờ dưới 99 %

| Thời điểm (UTC) | Success rate | Tương ứng |
|---|---|---|
| 19/07 18:00 | 98,93 % | blip nhỏ |
| **20/07 16:00** | **68,65 %** | **sự cố 0012** (NetworkPolicy Mandate #5) |

## 3. ⚠️ ĐIỂM MÙ của công thức — sự cố 0010 KHÔNG hiện ra

Công thức đo **tỉ lệ lỗi trong số request TỚI ĐƯỢC checkout**. Khi checkout chết hẳn
(0010: pod CrashLoop · 0012: mất hết endpoint), request **không sinh span nào** → không có lỗi để đếm
→ công thức báo ~100 % **dù khách thất bại hoàn toàn**.

**Kiểm chứng bằng lưu lượng** (bình thường **16,9 req/s**):

| Cửa sổ (UTC) | Lưu lượng | Sự cố |
|---|---|---|
| 19/07 15:30 | 2,374 req/s | **0010** — khớp postmortem (22:26–22:40 +07) |
| 19/07 15:45 | 1,703 req/s | 0010 |
| 20/07 15:00 | 2,106 req/s | **0012** |
| 20/07 15:15 | **0,307 req/s** | 0012 (đáy) |
| 20/07 15:30 | 0,636 req/s | 0012 |
| 20/07 15:45 | 0,929 req/s | 0012 |

→ **Cả hai sự cố đều làm lưu lượng sụp còn ~2–6 % bình thường**, nhưng chỉ 0012 hiện lên ở SLO.

## 4. Sự thật phía khách hàng (đo ở biên, không có điểm mù)

Với sự cố 0012, đo từ log `frontend-proxy` (Envoy) — đây là thứ khách thực sự gặp:

| Chỉ số | Giá trị |
|---|---|
| Lượt `POST /api/checkout` trong cửa sổ | 207 |
| Thành công (200) | 31 |
| **Thất bại (503)** | **176** |
| **Đơn bị mất** | **0** (xem postmortem 0012) |

Toàn bộ 176 lỗi là `503 upstream_reset_before_response_started` — hỏng ở **tầng kết nối**,
tức request chưa hề chạy logic đơn hàng → không charge, không mất đơn.

---

## 5. Kết luận trung thực cho nghiệm thu

| Cách đo | Kết quả | Nhận xét |
|---|---|---|
| **Error budget 5 ngày** (span-based) | **99,913 % — ĐẠT** | Dùng hết ~8,7 % ngân sách lỗi |
| **Trong cửa sổ cutover Kafka** | **68,65 %** (giờ 20/07 16:00) — KHÔNG đạt | Do sự cố 0012 |
| **Cutover Valkey + Postgres** | Không có giờ nào < 99 % | 2/3 store **cutover sạch** |

**Đội không dùng con số 99,913 % để nói "SLO đạt".** Yêu cầu ghi rõ *"giữ SLO ≥99 % **trong suốt quá trình
chuyển**"* → đo theo **cửa sổ cutover**, và ở cửa sổ Kafka thì **KHÔNG đạt** (2 sự cố: 0010 của CDO02,
0012 của CDO01). Con số error-budget chỉ để cho thấy **mức độ ảnh hưởng tổng thể là nhỏ và đã hồi phục**.

## 6. 🔧 Phát hiện cần cải thiện (ngoài phạm vi Mandate #8)

**SLO gate của Argo Rollouts có điểm mù nguy hiểm:** nếu canary chết hoàn toàn (không nhận request),
công thức trả ~100 % → **analysis PASS dù service đã sập**. Đề xuất bổ sung điều kiện **lưu lượng tối thiểu**
(AnalysisTemplate đã có metric `checkout-request-rate ≥ 0.05` — cần kiểm tra ngưỡng này đủ nhạy chưa) hoặc
đo SLO **ở biên (frontend-proxy)** thay vì theo span của chính service.

---

### Cách tái tạo

```bash
P=$(kubectl -n techx-tf3 get pods --no-headers | grep prometheus | awk '{print $1}')
kubectl -n techx-tf3 exec $P -c prometheus-server -- sh -c \
  "wget -qO- --post-data='query=sum(increase(traces_span_metrics_calls_total{service_name=\"checkout\"}[5d]))' \
   'http://localhost:9090/api/v1/query'"
```
