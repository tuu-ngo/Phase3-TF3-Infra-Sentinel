# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

FROM envoyproxy/envoy:v1.34.10@sha256:3343a698c1bdfdbb174f1bd907dea789d728692f4f99a943e3e6f0bc5ef6513f

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y gettext-base && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

USER envoy

WORKDIR /home/envoy

COPY ./src/frontend-proxy/envoy.tmpl.yaml envoy.tmpl.yaml

# validate config
RUN ENVOY_PORT=8080 ENVOY_ADMIN_PORT=10000 PORT=8080 envsubst < envoy.tmpl.yaml > /tmp/envoy-rendered.yaml && envoy --mode validate -c /tmp/envoy-rendered.yaml

EXPOSE ${ENVOY_PORT}
EXPOSE ${ENVOY_ADMIN_PORT}
ENTRYPOINT ["/bin/sh", "-c", "envsubst < envoy.tmpl.yaml > envoy.yaml && envoy -c envoy.yaml;"]
