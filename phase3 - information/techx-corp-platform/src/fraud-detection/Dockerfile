# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM --platform=${BUILDPLATFORM} gradle:8-jdk17 AS builder

WORKDIR /usr/src/app/

COPY ./src/fraud-detection/ ./
COPY ./pb/ ./src/main/proto/

RUN gradle shadowJar

# -----------------------------------------------------------------------------

FROM eclipse-temurin:17.0.19_10-jre-noble

ARG OTEL_JAVA_AGENT_VERSION
WORKDIR /usr/src/app/

# Apply security patches and create non-root user.
# noble = Ubuntu 24.04 LTS; supports linux/amd64 + linux/arm64.
RUN apt-get update -qq \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 app \
    && useradd -r -u 10001 -g app -M -d /usr/src/app app

ADD --chown=10001:10001 --chmod=644 https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v$OTEL_JAVA_AGENT_VERSION/opentelemetry-javaagent.jar /usr/src/app/opentelemetry-javaagent.jar
ENV JAVA_TOOL_OPTIONS=-javaagent:/usr/src/app/opentelemetry-javaagent.jar

COPY --from=builder --chown=10001:10001 /usr/src/app/build/libs/fraud-detection-1.0-all.jar fraud-detection-1.0-all.jar

USER 10001:10001

ENTRYPOINT [ "java", "-jar", "fraud-detection-1.0-all.jar" ]
