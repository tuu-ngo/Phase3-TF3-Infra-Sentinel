# Postmortem 0014 — PM-126 siết egress bastion về 443+DNS → chặn đường SSM tunnel tới RDS/ElastiCache (23/07/2026)

**Ngày:** 23/07/2026
**Người xử lý:** CDO02 (Huu Tai Ngo) — chẩn đoán & vá
**Nguồn gốc thay đổi:** commit `2cf73c2` (nvtank, PM-126 baseline hardening) — cùng commit gây postmortem [0013](0013-terraform-forcenew-bastion-replacement-ssm-lockout.md)
**Báo cáo bởi:** team AI (AIO02) — RDS connection timeout khi tunnel qua bastion
**Mức độ ảnh hưởng:** **KHÔNG ảnh hưởng khách hàng.** Chỉ chặn đường vận hành: không tunnel được từ
bastion tới RDS (5432) / ElastiCache (6379). Service trong cluster nối datastore bình thường (đi qua node
SG, không qua bastion).
**Trạng thái:** ✅ Đã vá code (thêm egress 5432/6379 cho bastion SG, scoped VPC CIDR) — chờ `terraform apply`.

---

## TL;DR

Commit `2cf73c2` (PM-126) thay egress của `aws_security_group.bastion` từ **mở (`0.0.0.0/0`, mọi cổng)**
sang **chỉ 443 (EKS API) + 53 (DNS)**. Đúng tinh thần least-privilege, nhưng **quá tay**: nó cắt luôn đường
ops hợp lệ từ bastion tới datastore. Trong khi đó module datastore vẫn **mở ingress RDS (5432) và
ElastiCache (6379) cho chính bastion SG** (`db_ops_sgs = node/cluster SG + bastion SG`) — tức thiết kế **có
chủ đích** cho bastion làm jump host tới RDS/ElastiCache. Hai bên mâu thuẫn: RDS SG cho bastion **vào**,
nhưng bastion SG không cho gói **ra** cổng 5432. SG là stateful → thiếu egress là gói chết ngay khi rời
bastion → `psql`/`redis-cli` qua SSM tunnel **timeout**. Team AI báo đúng triệu chứng "bastion → RDS network
path bị chặn".

---

## Why — Nguyên nhân gốc (xác minh bằng git)

- `git show origin/main:infra/modules/access/main.tf` → egress bastion chỉ có **443/tcp** (VPC CIDR) +
  **53 udp/tcp** (VPC resolver). **Không có 5432/6379/9096, không `0.0.0.0/0`.**
- `git show origin/main:infra/modules/datastores/security-groups.tf` + `main.tf` →
  `db_ops_sgs = concat(node/cluster SG, [bastion SG])`; `rds_ingress`/`elasticache_ingress` mở **5432/6379
  từ bastion SG**. ⇒ phía datastore **đã** cho bastion vào; block nằm **duy nhất** ở egress bastion.
- `git show 2cf73c2` → chính commit này thay egress mở bằng egress 443+DNS (cùng lúc thêm `encrypted=true`
  gây replace ở postmortem 0013).

**Mâu thuẫn thiết kế:** PM-126 hardening egress không đối chiếu với ý định của module datastore (bastion là
ops path tới RDS/ElastiCache). MSK thì nhất quán — `db_client_sgs` **không** gồm bastion, MSK SG không mở cho
bastion → 9096 cố ý đóng, không vá.

---

## Impact

- **Khách hàng:** không. Bastion không nằm trong luồng phục vụ; pod trong cluster nối RDS/ElastiCache/MSK qua
  node SG, không đụng bastion egress.
- **Vận hành:** không ai tunnel được tới RDS/ElastiCache qua bastion để debug/soi dữ liệu (team AI bị chặn).
- **Dữ liệu:** không đụng.

---

## Fix

Thêm 2 egress rule cho `aws_security_group.bastion` (`infra/modules/access/main.tf`):

```hcl
egress { description = "PostgreSQL to RDS via SSM tunnel"      from_port = 5432 to_port = 5432 protocol = "tcp" cidr_blocks = [var.vpc_cidr] }
egress { description = "Valkey/Redis to ElastiCache via SSM tunnel" from_port = 6379 to_port = 6379 protocol = "tcp" cidr_blocks = [var.vpc_cidr] }
```

Scope giữ trong **VPC CIDR** (không `0.0.0.0/0`) → giữ tinh thần PM-126 mà khôi phục đường ops. Đây là
**cập nhật SG tại chỗ** (revoke/authorize), **không** replace SG hay replace bastion → không đổi instance ID.

MSK (9096) **không** vá — đóng có chủ đích.

---

## Action items

1. **[CDO02 — ĐÃ XONG code, chờ apply]** Thêm egress 5432/6379 bastion SG. Apply qua workflow production
   (plan phải chỉ hiện +2 egress rule trên `...-bastion-sg`, **không** replace gì).
2. **[Verify sau apply]** `aws ec2 describe-security-groups --filters Name=tag:Name,Values=techx-corp-tf3-bastion-sg
   --query "SecurityGroups[0].IpPermissionsEgress[].FromPort"` phải có 5432 và 6379; team AI tunnel lại RDS OK.
3. **[CDO01/Security] Rà lại PM-126** — hardening egress cần đối chiếu đường ops đã thiết kế (datastore module
   mở ingress cho bastion) trước khi siết, tránh mâu thuẫn hai đầu SG.
4. **[Nếu vẫn timeout sau apply]** Kiểm NACL subnet bastion/datastore (mặc định allow-all; nếu có NACL siết thì
   xử thêm). SG egress là nguyên nhân đã xác nhận; NACL là khả năng còn lại duy nhất.

---

## Liên quan

- Postmortem [0013](0013-terraform-forcenew-bastion-replacement-ssm-lockout.md) — cùng commit `2cf73c2`, hệ quả replace bastion.
- Runbook [`ssm-access-all-iam.md`](../runbooks/ssm-access-all-iam.md) — đường tunnel RDS/ElastiCache cho mọi IAM.
- Commit `2cf73c2` (nvtank, PM-126) — `infra/modules/access/main.tf`.
