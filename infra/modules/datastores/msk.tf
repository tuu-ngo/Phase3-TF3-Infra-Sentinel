# MSK Kafka 3.9.x KRaft, 3 broker/3 AZ, RF=3 + min.insync.replicas=2 (checkout acks=all
# chịu mất 1 broker mà vẫn produce), TLS in-transit + at-rest (CMK), SASL/SCRAM auth, private.
# SCRAM secret ở secrets.tf (bắt buộc prefix AmazonMSK_ + mã hoá CMK).

resource "aws_msk_configuration" "kafka" {
  count = local.count_flag

  name              = "${var.name_prefix}-kafka"
  kafka_versions    = [var.msk_kafka_version]
  server_properties = <<-PROPERTIES
    auto.create.topics.enable=false
    default.replication.factor=3
    min.insync.replicas=2
    num.partitions=1
    log.retention.hours=168
  PROPERTIES

  lifecycle { create_before_destroy = true }
}

resource "aws_msk_cluster" "kafka" {
  count = local.count_flag

  cluster_name           = "${var.name_prefix}-kafka"
  kafka_version          = var.msk_kafka_version
  number_of_broker_nodes = var.msk_number_of_brokers

  broker_node_group_info {
    instance_type   = var.msk_broker_instance_type
    client_subnets  = var.private_subnet_ids
    security_groups = [aws_security_group.msk[0].id]

    storage_info {
      ebs_storage_info {
        volume_size = var.msk_broker_ebs_volume_size
      }
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.kafka[0].arn
    revision = aws_msk_configuration.kafka[0].latest_revision
  }

  # Encryption at rest bằng CMK (đã có cho SCRAM secret) + in-transit TLS, interbroker TLS.
  encryption_info {
    encryption_at_rest_kms_key_arn = aws_kms_key.datastores[0].arn

    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  # Chỉ bật SASL/SCRAM (không unauthenticated, không IAM) — yêu cầu #3: credential trong Secrets Manager.
  client_authentication {
    sasl {
      scram = true
    }
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-kafka" })
}
