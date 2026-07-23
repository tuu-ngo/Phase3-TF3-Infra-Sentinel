# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Run the builder natively on the CI host arch regardless of TARGETARCH - its
# output (.next/standalone + .next/static, copied below) is portable JS/static
# assets, so cross-compiling here is free. This avoids running `npm ci`/
# `npm run build` under QEMU emulation, which has hung for multi-hour periods
# on this image's linux/arm64 leg (native npm/swc under binfmt emulation is a
# known class of issue, see nodejs/docker-node#1335, #1973).
FROM --platform=$BUILDPLATFORM docker.io/library/node:22-slim@sha256:6c74791e557ce11fc957704f6d4fe134a7bc8d6f5ca4403205b2966bd488f6b3 AS builder

WORKDIR /app

COPY ./src/frontend/package.json package.json
COPY ./src/frontend/package-lock.json package-lock.json

# Trivy evaluates the assembled runtime image below. Disable npm's separate
# network audit here so reproducible builds do not stall on the advisory API.
RUN npm ci --no-audit --no-fund

COPY ./src/frontend/components/ components/
COPY ./src/frontend/gateways/ gateways/
COPY ./src/frontend/pages/ pages/
COPY ./src/frontend/protos/ protos/
COPY ./src/frontend/providers/ providers/
COPY ./src/frontend/services/ services/
COPY ./src/frontend/styles/ styles/
COPY ./src/frontend/types/ types/

COPY ./src/frontend/utils/enums/ utils/enums/
COPY ./src/frontend/utils/telemetry/ utils/telemetry/
COPY ./src/frontend/utils/imageLoader.js utils/imageLoader.js
COPY ./src/frontend/utils/Request.ts utils/Request.ts

COPY ./src/frontend/next.config.js next.config.js
COPY ./src/frontend/tsconfig.json tsconfig.json

RUN npm run build

# -----------------------------------------------------------------------------

# Same QEMU-hang avoidance as the builder stage above, but this stage's
# node_modules ARE shipped into the final runtime image (COPY --from=deps
# below), so a naive --platform=$BUILDPLATFORM would install native
# optionalDependencies (@next/swc-*, sharp) matching the CI host's arch
# instead of TARGETARCH. npm 10 (bundled with node:22) resolves
# platform-specific optionalDependencies from the `cpu`/`os`/`libc` config
# keys (NOT `arch`/`platform` - verified directly against `npm config list -l`
# in this exact base image; those older key names are silently ignored and
# fall back to auto-detecting the host). Setting them forces npm to resolve
# and download the same packages an emulated `npm ci` on TARGETARCH would
# have picked - only *where* the process runs changes, not *what* gets
# installed. libc stays glibc to match this stage's own node:22-slim
# (Debian) base, same as the existing (pre-fix) behavior.
FROM --platform=$BUILDPLATFORM docker.io/library/node:22-slim@sha256:6c74791e557ce11fc957704f6d4fe134a7bc8d6f5ca4403205b2966bd488f6b3 AS deps

ARG TARGETARCH

WORKDIR /app

COPY ./src/frontend/package.json package.json
COPY ./src/frontend/package-lock.json package-lock.json

# Docker's TARGETARCH ("amd64"/"arm64") and Node's own `cpu` naming
# ("x64"/"arm64") only agree on arm64 - verified directly that
# npm_config_cpu=amd64 silently drops @next/swc-*/sharp entirely (no error,
# just an empty install) instead of matching x64, which would ship a runtime
# image missing them. Map explicitly rather than assume the two conventions
# line up.
RUN set -eu; \
    case "${TARGETARCH}" in \
      amd64) npm_arch=x64 ;; \
      arm64) npm_arch=arm64 ;; \
      *) echo "unsupported TARGETARCH=${TARGETARCH} for npm cpu mapping" >&2; exit 1 ;; \
    esac; \
    npm_config_os=linux \
    npm_config_cpu="$npm_arch" \
    npm_config_libc=glibc \
    npm ci --omit=dev --no-audit --no-fund

# -----------------------------------------------------------------------------

FROM docker.io/library/node:22-alpine3.23@sha256:8516dce0483394d5708d4b2ee6cacb79fb1d617ea4e2787c2120bcca92ce372e

# Pull patched Alpine packages into the immutable application image before the
# strict Trivy gate evaluates it (notably OpenSSL/libexpat fixes).
RUN apk upgrade --no-cache

# Package managers are build-time tools. Removing them from the runtime image
# shrinks the attack surface and avoids shipping npm's unused Sigstore client.
RUN rm -rf /usr/local/lib/node_modules/npm \
  && rm -f /usr/local/bin/npm /usr/local/bin/npx \
  && corepack disable \
  && rm -f /usr/local/bin/corepack

WORKDIR /app

COPY --from=builder --chown=node:node /app/.next/standalone/ ./
COPY --from=builder --chown=node:node /app/.next/static/ .next/static/

COPY --from=deps --chown=node:node /app/node_modules/ node_modules/

COPY --chown=node:node ./src/frontend/public/ public/

COPY --chown=node:node ./src/frontend/utils/telemetry/Instrumentation.js Instrumentation.js

USER node
EXPOSE ${FRONTEND_PORT}

CMD ["node", "--require=./Instrumentation.js", "server.js"]
