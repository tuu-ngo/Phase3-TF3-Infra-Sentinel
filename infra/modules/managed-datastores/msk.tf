# ── MSK (Amazon Managed Streaming for Apache Kafka) ──────────────────────────
#
# Authentication strategy: SASL/SCRAM + TLS.
#   - SASL/SCRAM credentials stored in Secrets Manager (prefix "AmazonMSK/").
#   - TLS in-transit enforced (plaintext disabled).
#   - IAM auth also enabled so EKS pods can authenticate via IRSA without
#     managing SCRAM passwords (both modes coexist on port 9098 / 9094).
#
# NOTE: MSK with SASL/SCRAM requires Secrets Manager secrets to follow the
# naming convention "AmazonMSK/<name>" and be associated with the cluster
# after creation. The secret shell is created here; actual user credentials
# must be set and associated as a separate step (see docs/runbooks/).

resource "aws_msk_configuration" "main" {
  name           = "${var.cluster_name}-kafka"
  description    = "MSK broker configuration for ${var.cluster_name}"
  kafka_versions = [var.msk_kafka_version]

  server_properties = <<-EOT
    auto.create.topics.enable=false
    default.replication.factor=3
    min.insync.replicas=2
    num.partitions=6
    log.retention.hours=168
    log.segment.bytes=1073741824
    offsets.topic.replication.factor=3
    transaction.state.log.replication.factor=3
    transaction.state.log.min.isr=2
  EOT
}

resource "aws_msk_cluster" "main" {
  cluster_name           = "${var.cluster_name}-kafka"
  kafka_version          = var.msk_kafka_version
  number_of_broker_nodes = var.msk_number_of_broker_nodes

  broker_node_group_info {
    instance_type   = var.msk_instance_type
    client_subnets  = var.private_subnet_ids
    security_groups = [aws_security_group.msk.id]

    storage_info {
      ebs_storage_info {
        volume_size = var.msk_broker_storage_gib

        # EBS-level at-rest encryption via KMS
        provisioned_throughput {
          enabled = false
        }
      }
    }
  }

  # ── Encryption ──────────────────────────────────────────────────────────────
  encryption_info {
    # At-rest: KMS CMK
    encryption_at_rest_kms_key_arn = aws_kms_key.msk.arn

    # In-transit: TLS required for client-broker and broker-broker communication.
    # PLAINTEXT disabled entirely.
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  # ── Authentication ──────────────────────────────────────────────────────────
  client_authentication {
    # SASL/SCRAM — credentials managed via Secrets Manager
    sasl {
      scram = true
      # IAM auth: EKS pods can use IRSA instead of SCRAM passwords
      iam = true
    }

    # TLS mutual auth (optional — disabled here; use SASL instead)
    tls {
      certificate_authority_arns = []
    }

    unauthenticated = false
  }

  configuration_info {
    arn      = aws_msk_configuration.main.arn
    revision = aws_msk_configuration.main.latest_revision
  }

  # ── Monitoring ──────────────────────────────────────────────────────────────
  open_monitoring {
    prometheus {
      jmx_exporter {
        enabled_in_broker = true
      }
      node_exporter {
        enabled_in_broker = true
      }
    }
  }

  logging_info {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = aws_cloudwatch_log_group.msk_broker.name
      }
    }
  }

  tags = {
    Name = "${var.cluster_name}-kafka"
  }

  depends_on = [aws_msk_configuration.main]
}

resource "aws_cloudwatch_log_group" "msk_broker" {
  name              = "/aws/msk/${var.cluster_name}/broker"
  retention_in_days = 14

  tags = {
    Name = "${var.cluster_name}-msk-broker-logs"
  }
}

# ── SASL/SCRAM bootstrap credential secret ────────────────────────────────────
# Naming convention "AmazonMSK/<cluster>/<username>" is required by MSK.
# The secret value must be set manually (or via a separate rotation lambda)
# then associated with the MSK cluster via aws_msk_scram_secret_association.
# The Terraform resource creates the shell; real password must be set
# before association — see docs/runbooks/ for the cutover procedure.

resource "aws_secretsmanager_secret" "msk_scram" {
  name                    = "AmazonMSK/${var.cluster_name}-kafka/kafka-admin"
  description             = "SASL/SCRAM credentials for MSK cluster ${var.cluster_name}-kafka. Set the secret value before associating."
  kms_key_id              = aws_kms_key.secrets.arn
  recovery_window_in_days = 7

  tags = {
    Name = "AmazonMSK/${var.cluster_name}-kafka/kafka-admin"
  }
}

# Associate the SCRAM secret with the MSK cluster.
# MSK will use this secret to validate SCRAM-authenticated clients.
# NOTE: The secret value MUST be populated (via AWS Console / CLI) before
# running terraform apply on this resource, otherwise the association will fail.
# Uncomment the resource below only after the secret value has been set.

# resource "aws_msk_scram_secret_association" "main" {
#   cluster_arn     = aws_msk_cluster.main.arn
#   secret_arn_list = [aws_secretsmanager_secret.msk_scram.arn]
#   depends_on      = [aws_secretsmanager_secret.msk_scram]
# }
