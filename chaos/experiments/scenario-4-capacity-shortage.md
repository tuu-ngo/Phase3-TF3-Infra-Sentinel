# Mandate #15 — Scenario 4: "TỰ KHẮC PHỤC THÀNH CÔNG"

> Kịch bản **duy nhất** trong bộ này chấm được *"sau khi engine hành động thì sự cố hết"*.
> Ba kịch bản kia chỉ chấm được *phát hiện* và *ra quyết định*.

## Vì sao cần nó

Ở Scenario 1/2/3, lỗi do Chaos Mesh giữ tới hết `duration`. Engine scale hay restart thì
netem/stress vẫn nguyên — sự cố hết là do **hết giờ**, không phải do engine. Chấm "khắc
phục thành công" ở đó thì engine trượt dù không làm gì sai.

Kịch bản này dùng loại lỗi khác: **thiếu năng lực phục vụ**. Và điểm mấu chốt khiến nó
chữa được thật:

> Chaos Mesh **chốt danh sách pod đích tại thời điểm inject** — nó không đuổi theo pod
> mới. Nên khi engine scale lên, các pod mới sinh ra **hoàn toàn khoẻ**, gánh phần lớn
> traffic, và checkout p95 tụt xuống **thật**.

## Điều kiện tiên quyết

- **PR thêm `payment` vào `ignoreDifferences` phải đã merge.** Không có nó, cả lệnh hạ
  replica của mình lẫn lệnh scale của engine đều bị ArgoCD selfHeal kéo về trong vài giây.
  Kiểm tra: hạ replica xong đợi 1 phút, nếu nó tự về 2 thì PR chưa có hiệu lực.
- Tunnel SSM đang mở.
- Engine đang chạy (`deployment/aiops-engine`, `AIOPS_SIMULATION_MODE=false`).

## Các bước

**Bước 1 — hạ năng lực phục vụ về mức tối thiểu** (T−2 phút, làm trước khi bấm giờ):

```bash
kubectl -n techx-tf3 scale deploy/payment --replicas=1
```

Đợi tới khi chỉ còn 1 pod `1/1 Running`:

```bash
kubectl -n techx-tf3 get pod -l app.kubernetes.io/name=payment
```

**Bước 2 — tăng tải** (cần port-forward Locust ở terminal khác):

```bash
curl -s -X POST http://localhost:8089/swarm -d 'user_count=100&spawn_rate=5'
```

**Bước 3 — bơm nghẽn CPU** (đây là T+0, bấm giờ từ đây):

```bash
kubectl apply -f chaos/experiments/scenario-4-capacity-shortage.yaml
```

**Bước 4 — quan sát, KHÔNG can thiệp.** Engine cần ~5 phút warm-up rồi mới phát hiện và
hành động. Nếu nó làm đúng, nó sẽ chạy:

```
kubectl -n techx-tf3 scale deploy/payment --replicas=3
```

## Đo gì — đây là phần khác hẳn 3 kịch bản kia

| Mốc | Cần ghi lại |
|---|---|
| T+0 | checkout p95 **trước** khi nghẽn (baseline) |
| T+3 | checkout p95 **lúc nghẽn** — phải tăng rõ rệt |
| t_action | thời điểm engine thực sự gọi scale (xem `kubectl -n techx-tf3 get deploy payment -w`) |
| t_action+2ph | checkout p95 **sau khi engine hành động** — **phải tụt xuống** |

**Tiêu chí đạt:** p95 sau hành động thấp hơn hẳn p95 lúc nghẽn, và `payment` đạt số
replica mới với các pod mới `1/1 Ready`. Đây là bằng chứng **hành động của engine tạo ra
sự hồi phục**, không phải chờ hết giờ.

Để loại trừ nghi ngờ "tự hết do hết giờ": stress đặt `10m`, nên nếu p95 tụt ở khoảng
t_action+2 phút mà lúc đó chưa tới T+10 thì chắc chắn là do scale, không phải do hết hạn.

## Dọn sau khi chạy

```bash
kubectl -n techx-tf3 delete stresschaos m15-s4-payment-cpu-saturation
```

Trả replica và tải về nền:

```bash
kubectl -n techx-tf3 scale deploy/payment --replicas=2
```

```bash
curl -s -X POST http://localhost:8089/swarm -d 'user_count=10&spawn_rate=5'
```

## ⚠️ Bắt buộc chạy nháp trước

Chưa chạy thử lần nào. `payment` có CPU limit **300m** (chặt hơn `recommendation`) và
readinessProbe tcpSocket timeout **2s**. Ép quá tay thì pod mất `Ready`, bị loại khỏi
endpoint, và sự cố trượt từ *quá tải* thành *chết hẳn* — đúng cái bẫy đã dính ở Scenario 1
(xem PR #400).

Chạy nháp đạt khi: `payment` vẫn `1/1 Ready`, checkout **vẫn phục vụ được nhưng chậm rõ**.
Nếu pod mất Ready thì hạ `load` trong file YAML (60 → 40 → 30) rồi thử lại.
