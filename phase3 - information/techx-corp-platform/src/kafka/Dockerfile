# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM apache/kafka:4.3.1

USER root
ARG OTEL_JAVA_AGENT_VERSION

# Keep the supported Alpine base current at build time. Kafka 4.3.1 is the
# latest supported bug-fix release and contains the patched dependency set.
RUN apk upgrade --no-cache

# Kafka 4.3.1 predates the patched Jackson 2.21.4 artifact. Replace only the
# vulnerable jar and verify the Maven Central payload at build time.
ADD --checksum=sha256:3888e9e69ab66fbacaacc9aea0e9ffbf15368288e4aca468b024dba11c09fbf9 \
    https://repo.maven.apache.org/maven2/com/fasterxml/jackson/core/jackson-databind/2.21.4/jackson-databind-2.21.4.jar \
    /tmp/jackson-databind-2.21.4.jar

# The broker does not expose JLine's optional Telnet server. Remove that module
# (classes and Maven metadata) from the otherwise retained JLine CLI bundle.
RUN apk add --no-cache zip \
  && rm /opt/kafka/libs/jackson-databind-*.jar \
  && mv /tmp/jackson-databind-2.21.4.jar /opt/kafka/libs/ \
  && zip -q -d /opt/kafka/libs/jline-3.30.4.jar \
       'org/jline/builtins/telnet/*' \
       'META-INF/maven/org.jline/jline-remote-telnet/*' \
  && apk del zip \
  && chown appuser:appuser /opt/kafka/libs/jackson-databind-2.21.4.jar \
                           /opt/kafka/libs/jline-3.30.4.jar

USER appuser

ADD --chown=appuser:appuser https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v$OTEL_JAVA_AGENT_VERSION/opentelemetry-javaagent.jar /tmp/opentelemetry-javaagent.jar

ENV KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER
ENV KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
ENV KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS=0
ENV KAFKA_PROCESS_ROLES=controller,broker
ENV KAFKA_NODE_ID=1
ENV KAFKA_METADATA_LOG_SEGMENT_MS=15000
ENV KAFKA_METADATA_MAX_RETENTION_MS=60000
ENV KAFKA_METADATA_LOG_MAX_RECORD_BYTES_BETWEEN_SNAPSHOTS=2800
ENV KAFKA_AUTO_CREATE_TOPICS_ENABLE=true
ENV KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1
ENV KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1
ENV KAFKA_OPTS="-javaagent:/tmp/opentelemetry-javaagent.jar -Dotel.jmx.target.system=kafka-broker"
ENV CLUSTER_ID=ckjPoprWQzOf0-FuNkGfFQ
