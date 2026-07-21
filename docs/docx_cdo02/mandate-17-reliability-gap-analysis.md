# Đánh giá Reliability — Chịu lỗi & Chịu mất AZ

# Mandate 17: Yêu cầu #1 (dependency chết) & #2 (mất một AZ)

## Người phụ trách

CDO02 (Platform — trụ Reliability + Cost Optimization)

## Thông tin đánh giá

| Trường           | Giá trị                                                                                      |
| ---------------- | -------------------------------------------------------------------------------------------- |
| Ngày đánh giá    | 2026-07-21                                                                                   |
| Cluster          | techx-corp-tf3                                                                               |
| Region           | ap-southeast-1                                                                               |
| Namespace        | techx-tf3                                                                                    |
| Người thực hiện  | CDO02                                                                                        |
| Phương pháp      | Live cluster verify qua SSM tunnel (`kubectl`, `psql`, `valkey-cli`, `kafka-consumer-groups`) + đọc source code |

> Mandate 17 áp dụng cho **toàn bộ Task Force (phần CDO)** và được nghiệm thu trong **một buổi demo chung**.
> Tài liệu này phủ **yêu cầu #1 và #2**. Yêu cầu #3 và #4 do CDO01 phụ trách — xem tài liệu bổ trợ.

---

## Tóm tắt điều hành

| ID        | Mức độ  | Mô tả                                                                                   | Yêu cầu |
| --------- | ------- | ----------------------------------------------------------------------------------------- | ------- |
| REL-17-01 | **CAO** | Dual-write của `cart` chặn đồng bộ 2s trong `lock` → mất AZ 1a làm cart nghẽn ~40–60s **đúng lúc mentor bấm giờ RTO** | #2      |
| REL-17-02 | **CAO** | Frontend gọi `ad`/`recommendation` **không deadline, không fallback** → dependency treo kéo theo frontend | #1      |
| REL-17-03 | TRUNG BÌNH | `flagd` 1 replica, cố định AZ 1c — mất 1c là mất cơ chế đọc flag toàn hệ                  | #1, #2  |
| REL-17-04 | THẤP    | Toàn bộ observability 1 replica — mất AZ có thể mất luôn khả năng **chứng minh** SLO giữa demo | #2      |
| REL-17-05 | ✅ ĐẠT   | 9/9 service luồng ra tiền có 2 replica trải ≥2 AZ, `DoNotSchedule` cưỡng bức             | #2      |

**Kết luận:** Yêu cầu #2 phần *pod placement* đã đạt thật. Nhưng có **hai SPOF ẩn** không nằm ở tầng
scheduler mà nằm trong **code đường request** (REL-17-01, REL-17-02) — đây là chỗ mandate 17 nhắm tới và
là chỗ chúng ta đang hở.

---

## Phạm vi

- **Yêu cầu #1 — Sống qua một dependency chết.** Một service downstream lỗi/chậm → browse → cart → checkout
  vẫn giữ SLO nhờ timeout + fallback + degrade graceful; lỗi không lan ngược.
- **Yêu cầu #2 — Chịu mất cả một AZ.** Workload trải đủ AZ để luồng ra tiền giữ SLO khi mất trọn một AZ.

---

## Hiện trạng hạ tầng — bản đồ AZ

```bash
$ kubectl get nodes -L topology.kubernetes.io/zone,node.kubernetes.io/instance-type

NAME                                             STATUS   AGE     ZONE              INSTANCE-TYPE
ip-10-0-14-228.ap-southeast-1.compute.internal   Ready    10h     ap-southeast-1a   t3.small     (spot/Karpenter)
ip-10-0-4-166.ap-southeast-1.compute.internal    Ready    6d10h   ap-southeast-1a   t3.medium    (node group stateful_1a)
ip-10-0-8-134.ap-southeast-1.compute.internal    Ready    7d13h   ap-southeast-1a   t3.large
ip-10-0-26-153.ap-southeast-1.compute.internal   Ready    7d13h   ap-southeast-1b   t3.large
ip-10-0-43-83.ap-southeast-1.compute.internal    Ready    7d13h   ap-southeast-1c   t3.large
```

**Phân bố không cân:** AZ 1a có 3 node, 1b và 1c mỗi AZ **chỉ 1 node**. Mất 1b hoặc 1c = mất trọn một node
mang ~15 pod. Mất 1a = mất 3 node nhưng phần lớn là node phụ.

---

## REL-17-05 — Luồng ra tiền trải AZ: ĐẠT ✅

Đếm từng pod theo node, quy chiếu về AZ:

| Service         | Replica 1 (AZ)      | Replica 2 (AZ)      | Kết luận |
| --------------- | ------------------- | ------------------- | -------- |
| frontend        | `10-0-43-83` (1c)   | `10-0-8-134` (1a)   | ✅ 2 AZ  |
| frontend-proxy  | `10-0-43-83` (1c)   | `10-0-8-134` (1a)   | ✅ 2 AZ  |
| product-catalog | `10-0-26-153` (1b)  | `10-0-43-83` (1c)   | ✅ 2 AZ  |
| cart            | `10-0-43-83` (1c)   | `10-0-8-134` (1a)   | ✅ 2 AZ  |
| checkout        | `10-0-14-228` (1a)  | `10-0-43-83` (1c)   | ✅ 2 AZ  |
| payment         | `10-0-43-83` (1c)   | `10-0-8-134` (1a)   | ✅ 2 AZ  |
| currency        | `10-0-43-83` (1c)   | `10-0-8-134` (1a)   | ✅ 2 AZ  |
| shipping        | `10-0-26-153` (1b)  | `10-0-43-83` (1c)   | ✅ 2 AZ  |
| quote           | `10-0-26-153` (1b)  | `10-0-43-83` (1c)   | ✅ 2 AZ  |

Cơ chế: `topologySpreadConstraints` với `topologyKey: topology.kubernetes.io/zone` +
`whenUnsatisfiable: DoNotSchedule` (cưỡng bức, không phải best-effort) — khai báo trong
`phase3 - information/deploy/values-prod.yaml`, kèm PDB `minAvailable: 1` cho 9/9 service.

Tầng dữ liệu sau Mandate 08 cũng đã đa AZ: RDS Multi-AZ · ElastiCache 2 node auto-failover ·
MSK 3 broker/3 AZ, RF=3, `min.insync.replicas=2`.

**→ Nếu mentor chỉ chặn AZ và nhìn pod, chúng ta qua bài. Vấn đề nằm ở hai mục dưới.**

---

## REL-17-01 (CAO) — Dual-write của cart: SPOF ẩn theo AZ

### Hiện trạng

```bash
$ kubectl get deploy cart -n techx-tf3 -o jsonpath='...'
VALKEY_ADDR=master.techx-tf3-valkey.pkeslh.apse1.cache.amazonaws.com:6379   # ElastiCache
VALKEY_DUAL_WRITE_ADDR=valkey-cart:6379                                     # pod cũ, CÒN SỐNG
```

```bash
$ kubectl exec valkey-cart-f64d8cc69-lw48c -- valkey-cli dbsize
766
$ kubectl exec valkey-cart-f64d8cc69-lw48c -- valkey-cli info clients
connected_clients:5
```

`valkey-cart` = **1 replica, node `ip-10-0-4-166`, AZ 1a** — đường lui của Mandate 08, đang nhận ghi thật.

### Vì sao là SPOF

`phase3 - information/techx-corp-platform/src/cart/src/cartstore/ValkeyCartStore.cs`:

```csharp
// dòng 259 — nằm INLINE trên đường request khách
await DualWriteAsync(userId, cartEntries);

// dòng 189-196 — bên trong DualWriteAsync
lock (_dualWriteLocker) {
    _dualWriteRedis = ConnectionMultiplexer.Connect(_dualWriteConnectionOptions);  // ConnectTimeout = 2000ms
}
// dòng 207 — khi lỗi
_isDualWriteConnectionOpened = false;   // → request kế tiếp lại thử Connect từ đầu
```

Một lời gọi **blocking 2 giây nằm trong `lock`**, trên đường request, và **thử lại mỗi request** vì cờ
kết nối bị reset khi lỗi.

**Khi mất AZ 1a:** mọi `AddItemAsync` / `EmptyCartAsync` xếp hàng qua một lock, mỗi lượt tốn tới 2s.
Throughput cart tụt còn **~0,5 req/s mỗi pod**. Không exception, không pod cart nào `NotReady` — nhưng
cart p95 vọt lên ~2s (SLO storefront là p95 < 1s) và khách không thêm được hàng vào giỏ.

**Cửa sổ ảnh hưởng — nói cho chính xác (mentor sẽ vặn chỗ này):** tác động này **có giới hạn thời gian**,
không kéo dài vô hạn. Khi AZ 1a mất:

- Node `ip-10-0-4-166` không heartbeat → node controller đánh `NotReady` sau ~40s → pod `valkey-cart`
  bị đặt `Ready=False` → endpoint bị gỡ khỏi Service.
- **Trước** mốc đó, Service `valkey-cart` vẫn còn endpoint trỏ vào một node đã chết → gói tin đi vào
  **hố đen**, không bị RST → `Connect` chờ đủ `ConnectTimeout = 2000ms`. **Đây là cửa sổ convoy: ~40–60 giây.**
- **Sau** khi endpoint bị gỡ, ClusterIP không còn backend → kube-proxy REJECT ngay → `Connect` fail
  trong vài ms → convoy tự hết, chỉ còn overhead không đáng kể.

Nghĩa là REL-17-01 là **một hố ~40–60 giây p95 ≈ 2s ngay tại thời điểm mất AZ**, đúng vào lúc mentor
đang bấm giờ RTO — chứ không phải một sự cố kéo dài. Vẫn phải sửa: đó chính là khoảng thời gian bài thi
chấm. Nhưng đừng trình bày quá tay thành "cart chết", vì kiểm chứng lại sẽ thấy nó tự hồi.

Comment trong code ghi *"Never throws — a failure here must not break the customer path"*. **Đúng về tính
đúng đắn, sai về throughput.** Đây chính xác là loại lỗi mandate 17 muốn phát hiện: một mảnh chết mà
khách *có* biết.

### Ràng buộc quan trọng — KHÔNG được gỡ config

`docs/runbooks/mandate-08-managed-cutover.md` §8 (**"ĐIỂM KHÔNG QUAY LUI"**):

> Chỉ làm sau khi mentor đã nghiệm thu xong cả 3 store.
> Bước 2. PR gỡ dual-write của cart: bỏ `VALKEY_DUAL_WRITE_ADDR`
> ← *từ giây phút này valkey cũ bắt đầu lạc hậu; rollback Valkey không còn zero-loss*

**Mandate 08 chưa được nghiệm thu (§7 chưa diễn ra).** Gỡ `VALKEY_DUAL_WRITE_ADDR` lúc này là tự đốt
đường lui của một mandate chưa chốt.

### Hướng xử — sửa code, không gỡ config

Thêm **circuit breaker** cho `DualWriteAsync`: sau N lần lỗi liên tiếp thì bỏ qua dual-write trong X giây
rồi mới thử lại; và đưa `Connect` ra ngoài `lock` trên đường request (dùng `ConnectAsync` + cờ atomic).

Giữ nguyên đường lui của Mandate 08 (valkey cũ vẫn nhận ghi khi nó sống), xoá SPOF của Mandate 17.

**Đánh đổi cần ghi vào ADR:** trong cửa sổ circuit mở, valkey cũ lạc hậu. Nhưng nếu circuit mở thì valkey
cũ vốn đã không truy cập được — không mất thêm gì so với hiện trạng.

---

## REL-17-02 (CAO) — Không có timeout/fallback với dependency

### Bằng chứng code

`phase3 - information/techx-corp-platform/src/frontend/gateways/rpc/Ad.gateway.ts:14`:

```ts
client.getAds({ contextKeys }, (error, response) => (error ? reject(error) : resolve(response)))
```

Không deadline, không try/catch, không giá trị mặc định. **gRPC-js không có deadline mặc định** — nếu `ad`
treo (chứ không chết hẳn) thì promise chờ vô hạn, giữ luôn request Next.js. `Recommendations.gateway.ts`
giống hệt.

`phase3 - information/techx-corp-platform/src/frontend/pages/api/recommendations.ts` còn thêm một tầng:
sau khi gọi `recommendation`, nó fan-out `Promise.all` sang `product-catalog` — **một sản phẩm lỗi là
reject cả panel**.

### Bằng chứng vận hành

`docs/postmortem/0011-btc-injected-productcatalogfailure-checkout-degradation.md` (20/07): BTC bơm
`productCatalogFailure` → `PlaceOrder` lỗi **617/4.038 = 15,3%** trong 24 phút → **thủng SLO checkout ≥99%**.

Đây đúng là kịch bản yêu cầu #1. **Hiện tại chúng ta trượt bài này, có tài liệu chứng minh.**

### Phân loại dependency — điều phải trình bày với mentor

Không phải dependency nào cũng fallback được. Trình bày theo phân loại này thay vì hứa "cái gì chết cũng sống":

| Dependency        | Chết thì khách mất gì      | Xử lý                                          |
| ----------------- | -------------------------- | ---------------------------------------------- |
| `ad`              | Không thấy quảng cáo       | ✅ Timeout ngắn + trả rỗng — degrade thật       |
| `recommendation`  | Không thấy gợi ý           | ✅ Timeout ngắn + trả rỗng, bỏ `Promise.all` cứng |
| `currency`        | Sai đơn vị tiền            | ⚠️ Cache tỷ giá gần nhất, hết hạn thì fail rõ ràng |
| `product-catalog` | Không biết đang bán gì     | ❌ **Cố ý không fallback** — fallback = bịa dữ liệu |
| `payment`         | Không thu được tiền        | ❌ **Cố ý không fallback** — không được fake success |

Với hai cái cuối, thứ phải chứng minh **không phải** là "vẫn bán được", mà là **lỗi không lan ngược**:
checkout fail nhanh, không treo, không làm cạn connection pool của frontend, không kéo sập browse cho các
SKU khác.

---

## REL-17-03 (TRUNG BÌNH) — flagd 1 replica, cố định AZ 1c

```bash
$ kubectl get deploy flagd -n techx-tf3
flagd   READY 1   DESIRED 1      # pod trên ip-10-0-43-83 → AZ 1c
```

Mất AZ 1c = mất flagd. Mọi service đọc flag qua `FLAGD_HOST=flagd` sẽ không đánh giá được flag trong lúc
pod được lập lịch lại.

> ⚠️ **Cảnh báo tuân thủ:** flagd là cơ chế BTC bơm sự cố. RULES cấm gỡ/đổi hướng/vô hiệu hoá.
> Nâng số replica **không phải** là vô hiệu hoá — nhưng vì đây là vùng nhạy cảm, **phải hỏi leader và
> mentor trước khi đụng vào**, không tự ý sửa. Nếu không được phép thì ghi nhận là **rủi ro chấp nhận**
> trong ADR, kèm lý do.

---

## REL-17-04 (THẤP) — Observability đơn lẻ

`grafana`, `jaeger`, `prometheus`, `opensearch-0` đều 1 replica. `prometheus` + `grafana` + `opensearch-0`
nằm chung node `ip-10-0-8-134` (AZ 1a).

Không phải sản phẩm, không tính vào SLO. Nhưng **mất AZ 1a giữa buổi demo = mất luôn dashboard để chứng
minh SLO vẫn giữ**. Rủi ro về mặt trình bày, không phải về mặt khách hàng. Mandate 03 đã ghi nhận blip
502 ~1 phút của Grafana khi drain node — cùng gốc rễ.

---

## Bàn giao CDO01 — phát hiện thuộc yêu cầu #4

Tài liệu của CDO01 (SEC-02) xếp việc mount SA token ở mức **TRUNG BÌNH**, với nhận định:

> *"Token hợp lệ này có thể dùng để gọi Kubernetes API **nếu SA được cấp thêm quyền sau này**"*

Kiểm tra live cho thấy quyền đó **đã tồn tại rồi**, không phải giả định tương lai:

```bash
$ kubectl auth can-i update deployments/scale --as=system:serviceaccount:techx-tf3:default -n techx-tf3
yes
$ kubectl auth can-i patch deployments --as=system:serviceaccount:techx-tf3:default -n techx-tf3
yes
```

Chuỗi đầy đủ:

```
RoleBinding aiops-engine-rolebinding  →  SA "default"  (KHÔNG phải SA riêng của aiops-engine)
  └─ Role aiops-engine-role: apps/deployments + deployments/scale [get,list,watch,update,patch]

Pod đang dùng SA "default":
  - aiops-engine-5d5c7964c6-pz569   (chủ ý)
  - cloudflared-747fd76fc9-7l62d    ← pod hứng tunnel từ Internet
  - cloudflared-747fd76fc9-w598s    ← pod hứng tunnel từ Internet
  - opensearch-0

$ kubectl get pod cloudflared-747fd76fc9-w598s -o jsonpath='{.spec.volumes[*].name}'
kube-api-access-st4jj             ← token ĐÃ được mount
```

**Tác động:** `cloudflared` là pod phơi ra Internet nhiều nhất cluster. Nếu bị chiếm, kẻ tấn công
`scale` mọi Deployment trong `techx-tf3` về 0 → tắt storefront. Đây đúng là kịch bản yêu cầu #4.

**Đề nghị:** nâng SEC-02 lên **CAO**, và fix bằng 2 việc nhỏ:
1. Tạo SA riêng cho `aiops-engine`, chuyển `RoleBinding` sang SA đó (gỡ quyền khỏi `default`).
2. `automountServiceAccountToken: false` cho các service không gọi K8s API.

Ghi chú tích cực: SA `techx-corp` (31 pod dùng chung) **không có RoleBinding nào** —
`kubectl auth can-i list pods --as=...:techx-corp` → `no`. Blast radius của nó gần bằng 0.

---

## Kế hoạch

Sắp theo **tỷ lệ (giảm rủi ro thật) / (công sức)**, không theo thứ tự yêu cầu.

| # | Việc                                                                     | Gap        | Công sức | Chặn bởi                    |
| - | ------------------------------------------------------------------------ | ---------- | -------- | --------------------------- |
| 1 | Circuit breaker + bỏ blocking `Connect` trong `lock` cho dual-write cart  | REL-17-01  | ~0,5 ngày | — (làm được ngay)           |
| 2 | Timeout + fallback rỗng cho `ad` / `recommendation`; bỏ `Promise.all` cứng | REL-17-02  | ~1 ngày   | — (làm được ngay)           |
| 3 | Đóng gói bằng chứng AZ spread thành artifact demo                         | REL-17-05  | ~1 giờ    | — (đã đạt, chỉ thiếu giấy)  |
| 4 | Bàn giao chuỗi leo thang `default` SA cho CDO01                           | yêu cầu #4 | 5 phút    | — (làm ngay)                |
| 5 | flagd HA                                                                 | REL-17-03  | ~1 giờ    | **Phải xin phép leader/mentor** |
| 6 | Anti-affinity cho observability                                          | REL-17-04  | ~1 giờ    | Ưu tiên thấp                |
| — | Gỡ hẳn `VALKEY_DUAL_WRITE_ADDR` + dọn pod/PVC cũ                          | REL-17-01  | 1 dòng    | ⛔ **Mandate 08 §7 chưa nghiệm thu** |

Việc cuối cùng là cách sửa *đúng* và *rẻ nhất* cho REL-17-01, nhưng **bị khoá cho tới khi mentor nghiệm
thu Mandate 08**. Cho tới lúc đó, việc #1 là giải pháp thay thế giữ được cả hai mục tiêu.

---

## Chuẩn bị demo chung

Mandate 17 nghiệm thu **cùng một buổi với CDO01, trên cùng cluster**. Nguyên văn mục *Phải nộp*:

> Mentor tự **giết một dependency** (service downstream) **hoặc chặn một AZ** …

Chữ **"hoặc"** là quyền của mentor. Không chuẩn bị một phía rồi hy vọng né phía kia.

**Rủi ro đồng đội — đã xảy ra thật:** ngày 20/07, batch 20 NetworkPolicy của CDO01 (để đạt yêu cầu #3)
làm `checkout` chết ~30 phút — tức là phá thẳng yêu cầu #1 và #2 (postmortem 0012). Trước buổi demo phải
chốt với CDO01:

1. **Không apply NetworkPolicy trong ngày demo.**
2. Khi apply lại, policy phải có **`ipBlock`** cho RDS/ElastiCache/MSK (store không còn là pod sau Mandate 08).
3. Lưu ý AWS VPC CNI **không permit egress kiểu `podSelector` tới ClusterIP Service** — rule ghi "allow"
   mà traffic vẫn drop. Đây là thứ làm patch chữa cháy hôm 20/07 không cứu được.

**Cần mở sẵn khi demo:** Grafana panel checkout success-rate + p95 · Grafana panel số node/AZ ·
`kubectl get pods -o wide` với cột node/AZ · postmortem 0011 (để nói về yêu cầu #1 một cách trung thực).

---

## Điều chúng tôi cố ý KHÔNG làm

- **Không fallback cho `product-catalog` / `payment`.** Fallback ở đó là bịa dữ liệu sản phẩm hoặc giả vờ
  thu được tiền. Thứ chúng tôi cam kết là *lỗi không lan ngược*, không phải *luôn bán được*.
- **Không tự ý đụng flagd.** Kể cả việc nâng replica — xin phép trước.
- **Không gỡ dual-write trước khi Mandate 08 được nghiệm thu**, dù đó là fix rẻ nhất cho REL-17-01.
- **Không nhận đủ 4 yêu cầu.** Tới hạn 21/07, yêu cầu #1 đang hở và yêu cầu #3 vừa bị rollback. Trình bày
  đúng cái đã đạt và đúng cái chưa, kèm kế hoạch có ngày.

---

## Tham chiếu

- `phase3/mandates/MANDATE-17-resilience-and-containment.md`
- `docs/postmortem/0011-btc-injected-productcatalogfailure-checkout-degradation.md`
- `docs/postmortem/0012-mandate5-networkpolicy-batch-outage.md`
- `docs/runbooks/mandate-08-managed-cutover.md` §7, §8
- `docs/adr/0009-mandate-08-managed-migration-cdo02.md`
- `docs/mandate-03-drain-node-report.md`
