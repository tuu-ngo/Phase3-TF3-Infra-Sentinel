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

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /nonexistent --shell /usr/sbin/nologin --no-create-home app

ADD --chown=10001:10001 --chmod=644 https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v$OTEL_JAVA_AGENT_VERSION/opentelemetry-javaagent.jar /usr/src/app/opentelemetry-javaagent.jar
ENV JAVA_TOOL_OPTIONS=-javaagent:/usr/src/app/opentelemetry-javaagent.jar

COPY --from=builder --chown=10001:10001 /usr/src/app/build/libs/fraud-detection-1.0-all.jar fraud-detection-1.0-all.jar

USER 10001:10001

ENTRYPOINT [ "java", "-jar", "fraud-detection-1.0-all.jar" ]
