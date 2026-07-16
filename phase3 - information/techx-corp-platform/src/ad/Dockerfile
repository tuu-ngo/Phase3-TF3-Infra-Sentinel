# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM --platform=${BUILDPLATFORM} eclipse-temurin:21-jdk AS builder
ARG _JAVA_OPTIONS
WORKDIR /usr/src/app/

COPY ./src/ad/gradlew* ./src/ad/settings.gradle* ./src/ad/build.gradle ./
COPY ./src/ad/gradle ./gradle

RUN chmod +x ./gradlew
RUN ./gradlew
RUN ./gradlew downloadRepos

COPY ./src/ad/ ./
COPY ./pb/ ./proto
RUN chmod +x ./gradlew
RUN ./gradlew installDist -PprotoSourceDir=./proto

# -----------------------------------------------------------------------------

FROM eclipse-temurin:21-jre-alpine-3.23

# The upstream Alpine image can lag patched repository packages for a few days.
# Upgrade inside the immutable release image so the pre-push gate evaluates the
# fixed libexpat/p11-kit packages instead of accepting a stale base layer.
RUN apk upgrade --no-cache

ARG OTEL_JAVA_AGENT_VERSION
ARG _JAVA_OPTIONS

WORKDIR /usr/src/app/

COPY --from=builder --chown=65532:65532 \
  /usr/src/app/build/install/techx-corp-ad/ ./build/install/techx-corp-ad/
ADD --chmod=644 https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v$OTEL_JAVA_AGENT_VERSION/opentelemetry-javaagent.jar /usr/src/app/opentelemetry-javaagent.jar
RUN groupadd --system --gid 65532 nonroot \
    && useradd --system --uid 65532 --gid 65532 --home-dir /nonexistent --shell /usr/sbin/nologin nonroot \
    && chown -R 65532:65532 /usr/src/app
USER 65532:65532
ENV JAVA_TOOL_OPTIONS=-javaagent:/usr/src/app/opentelemetry-javaagent.jar

EXPOSE ${AD_PORT}
ENTRYPOINT [ "java", "-cp", "build/install/techx-corp-ad/lib/*", "oteldemo.AdService" ]
