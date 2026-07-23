# Mandate 08 - Phương án tốt nhất và flow thực hiện

**Cập nhật:** 17/07/2026  
**Mục tiêu:** Hoàn thành Mandate 08 trên hệ thống hiện tại theo cách ít rủi ro nhất, giữ SLO checkout và không để khách hàng nhận ra thời điểm chuyển đổi.

## 1. Kết luận ngắn

Với hệ thống hiện tại, phương án tốt nhất là:

1. Chuyển `PostgreSQL -> RDS` trước
2. Chuyển `Valkey -> ElastiCache` sau
3. Để `Kafka` cuối cùng

Không làm cả 3 datastore cùng lúc.  
Không đụng Kafka đầu tiên.  
Không đổi kiến trúc ứng dụng quá mức chỉ để phục vụ migration.

## 2. Hiểu đúng flow dữ liệu hiện tại

### Luồng sản phẩm / review

```text
frontend
  -> frontend-proxy
  -> product-catalog / product-reviews
  -> postgresql
```

Luồng này đi thẳng vào PostgreSQL, không qua Kafka.

### Luồng giỏ hàng

```text
frontend
  -> frontend-proxy
  -> cart
  -> valkey-cart
```

Luồng này đi thẳng vào Valkey, không qua Kafka.

### Luồng đặt hàng

```text
frontend
  -> frontend-proxy
  -> checkout
  -> cart / currency / product-catalog / shipping / payment
  -> checkout publish event
  -> kafka
  -> accounting consume event
  -> postgresql
```

`fraud-detection` cũng consume event từ Kafka.

Điểm quan trọng: **không phải mọi dữ liệu runtime đều đi `Kafka -> RDS`**.  
Chỉ luồng `accounting` là vốn đã có Kafka ở giữa.

## 3. Điều kiện để bắt đầu

Chỉ nên cutover khi đủ các điều kiện sau:

- `checkout-rollout` đang đủ `2/2`
- không có incident mở trên checkout path
- core pod không có `CrashLoopBackOff`
- team Mandate 05 đã xử lý đủ phần liên quan:
  - harden `postgresql`, `valkey-cart`, `kafka`
  - harden `otel-collector-agent`
  - dọn `PolicyViolation` quan trọng
  - bổ sung `CPU/memory requests-limits` cho nhóm stateful + observability
  - ghi rõ exception nào là tạm thời, exception nào là chấp nhận có ý thức
- platform/security đã cung cấp:
  - managed resource thật
  - private endpoint
  - secret
  - network path
  - TLS nếu yêu cầu

## 4. Flow tốt nhất từ đầu tới cuối

## Bước 1 - Chuẩn bị và chụp baseline

Trước khi đổi bất cứ gì:

- xác nhận dependency map:
  - `product-catalog`, `product-reviews`, `accounting` dùng Postgres
  - `cart` dùng Valkey
  - `checkout`, `accounting`, `fraud-detection` dùng Kafka
- chụp baseline:
  - pod state
  - rollout/hpa/pdb
  - checkout success rate
  - browse/cart success rate
  - latency
  - restart/error hiện tại

Mục tiêu của bước này là để có số đối chiếu trước và sau cutover.

## Bước 2 - Chuyển PostgreSQL sang RDS

Đây là bước đầu tiên vì dễ kiểm data parity nhất.

### Flow dữ liệu

```text
PostgreSQL cũ
  -> dump dữ liệu nền
  -> restore vào RDS
  -> kiểm parity
  -> final sync phần chênh lệch cuối
  -> đổi app sang RDS
```

### Giải thích đúng trọng tâm

Trong lúc dump nền:

- user vẫn đang dùng hệ thống bình thường
- dữ liệu mới vẫn đang ghi vào `PostgreSQL cũ`
- `RDS` lúc đó chỉ là bản sao nền, chưa phải DB live

Vì vậy bắt buộc phải có:

1. dump nền từ `PostgreSQL cũ -> RDS`
2. kiểm schema / row count / sample data
3. làm `final sync` lấy nốt phần chênh lệch cuối
4. rồi mới đổi app sang RDS

### Cách tránh vòng lặp sync vô tận

Không làm kiểu dump lặp mãi cho tới khi giống.

Phải có điểm cắt:

- chọn giờ tải thấp
- final sync ở cuối trong cửa sổ rất ngắn
- đổi app sang RDS ngay sau final sync

### Thứ tự đổi service

1. `product-catalog`
2. `product-reviews`
3. `accounting`

### Flow sau khi đổi

```text
product-catalog / product-reviews
  -> RDS

checkout
  -> kafka
  -> accounting
  -> RDS
```

### Smoke test cần làm

- mở trang sản phẩm
- vào product detail
- xem review
- tạo một order test
- xác nhận `accounting` vẫn ghi được vào RDS

### Rollback

Nếu có lỗi:

- đổi connection string về `PostgreSQL cũ`
- rollout restart service vừa đổi

## Bước 3 - Chuyển Valkey sang ElastiCache

Đây là bước thứ hai vì cart là soft-state, ít rủi ro hơn Kafka.

### Flow dữ liệu

```text
cart
  -> valkey-cart
```

sẽ đổi thành:

```text
cart
  -> ElastiCache
```

### Cách làm

1. dựng ElastiCache
2. test kết nối từ `cart`
3. đổi config của `cart`
4. rollout restart `cart`
5. smoke test add/update cart
6. test checkout còn lấy được cart

### Rollback

Nếu lỗi:

- đổi `cart` về `valkey-cart` cũ
- rollout restart `cart`

## Bước 4 - Chuyển Kafka sang managed Kafka

Đây là bước cuối cùng và khó nhất.

### Vì sao để cuối

Kafka là luồng sống:

```text
checkout
  -> kafka
  -> accounting / fraud-detection
```

Nếu chuyển sai dễ gây:

- checkout chậm hoặc fail
- consumer không đọc được
- mất continuity của event
- mất dấu order downstream

### Phương án tốt nhất

Nếu làm được, ưu tiên:

- producer dual-write tạm sang Kafka cũ và Kafka mới
- consumer test trên Kafka mới trước
- khi chắc đường mới ổn mới bỏ Kafka cũ

Nếu chưa có dual-write, chỉ nên:

- chọn giờ traffic thấp
- giảm backlog cũ
- đổi producer/consumer trong cửa sổ rất ngắn
- theo dõi sát rồi rollback ngay nếu có lỗi

### Flow sau khi đổi

```text
checkout
  -> managed Kafka
  -> accounting
  -> RDS

checkout
  -> managed Kafka
  -> fraud-detection
```

### Smoke test cần làm

- đặt order test
- checkout trả OK
- accounting nhận event
- fraud-detection nhận event
- không có lag/error bất thường

## Bước 5 - Nghiệm thu Mandate 08

Mandate 08 chỉ nên coi là hoàn thành khi đủ cả 4 điều sau:

### 1. App đã dùng managed service thật

- `product-catalog`, `product-reviews`, `accounting` dùng `RDS`
- `cart` dùng `ElastiCache`
- `checkout/accounting/fraud-detection` dùng managed Kafka nếu scope đã gồm Kafka

### 2. SLO không tụt

- checkout success rate giữ `>= 99%`
- browse/cart không có spike lỗi rõ rệt

### 3. Có bằng chứng không mất dữ liệu

- parity check cho RDS
- test read/write sau cutover
- test event flow sau cutover Kafka

### 4. Có rollback và evidence

- secret cũ
- endpoint cũ
- cấu hình cũ
- ảnh dashboard / log / kết quả test

## 5. Tóm tắt flow tối ưu

```text
Chuẩn bị baseline
  -> PostgreSQL sang RDS
  -> ổn định và kiểm chứng
  -> Valkey sang ElastiCache
  -> ổn định và kiểm chứng
  -> Kafka sang managed Kafka
  -> nghiệm thu Mandate 08
```

## 6. Kết luận cuối

Với hệ thống hiện tại, phương án tốt nhất là:

- không làm big-bang
- không cố nhét mọi write-path qua Kafka
- dùng `RDS` trước, `ElastiCache` sau, `Kafka` cuối
- sau mỗi bước đều phải:
  - smoke test
  - theo dõi SLO
  - giữ rollback ngay được

Đây là cách thực tế nhất để vừa đáp ứng Mandate 08, vừa giảm nguy cơ làm khách hàng nhận ra thời điểm chuyển đổi.
