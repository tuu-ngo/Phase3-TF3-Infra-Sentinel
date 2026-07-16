# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM --platform=${BUILDPLATFORM} gradle:8-jdk17 AS builder

WORKDIR /usr/src/app/

COPY ./src/fraud-detection/ ./
COPY ./pb/ ./src/main/proto/

RUN gradle shadowJar

# -----------------------------------------------------------------------------

FROM eclipse-temurin:17.0.19_10-jre-alpine-3.23

ARG OTEL_JAVA_AGENT_VERSION
WORKDIR /usr/src/app/

RUN apk upgrade --no-cache \
    && addgroup -S -g 10001 app \
    && adduser -S -D -H -u 10001 -G app app

ADD --chown=10001:10001 --chmod=644 https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v$OTEL_JAVA_AGENT_VERSION/opentelemetry-javaagent.jar /usr/src/app/opentelemetry-javaagent.jar
ENV JAVA_TOOL_OPTIONS=-javaagent:/usr/src/app/opentelemetry-javaagent.jar

COPY --from=builder --chown=10001:10001 /usr/src/app/build/libs/fraud-detection-1.0-all.jar fraud-detection-1.0-all.jar

USER 10001:10001

ENTRYPOINT [ "java", "-jar", "fraud-detection-1.0-all.jar" ]
