# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM --platform=${BUILDPLATFORM} gradle:8-jdk17@sha256:b7d2b978cad21a07a1192b9112029bc1a80ffe58db7ec828c3f399f833a468cb AS builder

WORKDIR /usr/src/app/

COPY ./src/fraud-detection/ ./
COPY ./pb/ ./src/main/proto/

RUN gradle shadowJar

# -----------------------------------------------------------------------------

FROM eclipse-temurin:17.0.19_10-jre-noble@sha256:543aebd60ff1deb9e906a8d4b117a7eda68a7f8e0d71041db2b5839d7fa057b8

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
