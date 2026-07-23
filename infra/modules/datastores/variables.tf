# Datastores module — Mandate #8: migrate 3 store lên managed (RDS / ElastiCache / MSK).
# Cơ sở quyết định + đánh đổi: docs/adr/0009-mandate-08-managed-migration-cdo02.md.
# Nguyên tắc bảo mật: private subnet, SG mở tối thiểu, TLS in-transit, encryption at rest,
# credential trong Secrets Manager. RDS dùng managed master password (không vào TF state);
# ElastiCache AUTH token + MSK SCRAM password sinh trong module (vào state — xoay sau cutover, ADR §3).

variable "enabled" {
  description = "Bật/tắt toàn bộ tầng datastore managed. false = không tạo gì (giữ nguyên in-cluster)."
  type        = bool
  default     = false
}

variable "cluster_name" {
  description = "Tên EKS cluster, dùng làm prefix đặt tên tài nguyên (vd techx-corp-tf3)."
  type        = string
}

variable "name_prefix" {
  description = "Prefix ngắn cho tên tài nguyên/secret (vd techx-tf3)."
  type        = string
}

variable "vpc_id" {
  description = "VPC chứa cluster + datastore."
  type        = string
}

variable "private_subnet_ids" {
  description = "Danh sách private subnet (3 AZ) cho subnet group của cả 3 store."
  type        = list(string)
}

variable "allowed_client_security_group_ids" {
  description = "SG của client được phép kết nối (SG node/cluster EKS — pod đi qua đây)."
  type        = list(string)
}

variable "bastion_security_group_id" {
  description = "SG bastion — mở thêm cho RDS/ElastiCache để thao tác migration/vận hành qua SSM tunnel. MSK không cần (thao tác qua pod trong cluster)."
  type        = string
}

variable "external_secrets_role_name" {
  description = "Tên IAM role của External Secrets Operator — module gắn policy đọc 3 secret mới vào role này."
  type        = string
}

variable "tags" {
  description = "Tag chung gắn lên mọi tài nguyên."
  type        = map(string)
  default     = {}
}

# ---------- RDS PostgreSQL ----------
variable "rds_engine_version" {
  # Khởi tạo 17.6 (khớp store in-cluster lúc migrate Mandate #8); store cũ đã tắt (§8)
  # nên ràng buộc "khớp 1:1" không còn. AWS auto minor upgrade đã nâng lên 17.9 —
  # đặt default = 17.9 để khớp thực tế; engine_version được ignore_changes ở rds.tf
  # nên chỉ có tác dụng khi tạo mới instance.
  description = "Phiên bản PostgreSQL khởi tạo. Drift minor do AWS được ignore ở rds.tf."
  type        = string
  default     = "17.9"
}

variable "rds_instance_class" {
  description = "Instance class RDS (right-size: db.t4g.micro, Graviton rẻ hơn t3)."
  type        = string
  default     = "db.t4g.micro"
}

variable "rds_allocated_storage" {
  description = "Dung lượng gp3 (GB). DB hiện ~38 MB → 20 GB dư thoải mái, là mức tối thiểu gp3."
  type        = number
  default     = 20
}

variable "rds_multi_az" {
  description = "Multi-AZ cho RDS — dữ liệu tài chính, durability đáng giá nhất (ADR: +$19/mo)."
  type        = bool
  default     = true
}

variable "rds_master_username" {
  description = "Master user RDS. Đặt = user app (otelu) để pg_dump/restore giữ nguyên owner, app chỉ đổi host+sslmode."
  type        = string
  default     = "otelu"
}

variable "rds_database_name" {
  description = "DB khởi tạo trên RDS (khớp in-cluster: otel)."
  type        = string
  default     = "otel"
}

# ---------- ElastiCache Valkey ----------
variable "elasticache_engine_version" {
  description = "Phiên bản Valkey — khớp in-cluster (9.0)."
  type        = string
  default     = "9.0"
}

variable "elasticache_node_type" {
  description = "Node type ElastiCache (cache.t4g.micro)."
  type        = string
  default     = "cache.t4g.micro"
}

variable "elasticache_replica_count" {
  description = "Số node (1 primary + N replica). 2 = 1 primary + 1 replica cho auto-failover (cart trên luồng đồng bộ)."
  type        = number
  default     = 2
}

# ---------- MSK Kafka ----------
variable "msk_kafka_version" {
  description = "Phiên bản Kafka MSK — khớp in-cluster 3.9.x KRaft."
  type        = string
  default     = "3.9.x.kraft"
}

variable "msk_broker_instance_type" {
  # MSK 3.9.x KHONG con ho tro kafka.t3.small (CreateCluster tra BadRequest). Instance nho nhat
  # hop le hien tai la kafka.m7g.large (Graviton, re nhat trong danh sach valid). Da verify qua
  # loi API tra ve danh sach valid types.
  description = "Instance type broker MSK. 3.9.x yeu cau m5.large / m7g.large tro len (t3.small bi loai)."
  type        = string
  default     = "kafka.m7g.large"
}

variable "msk_number_of_brokers" {
  description = "Số broker (bội số của số AZ). 3 broker/3 AZ → RF=3, min.insync=2, chịu mất 1 broker mà checkout acks=all vẫn produce."
  type        = number
  default     = 3
}

variable "msk_broker_ebs_volume_size" {
  description = "Dung lượng EBS mỗi broker (GB)."
  type        = number
  default     = 10
}
