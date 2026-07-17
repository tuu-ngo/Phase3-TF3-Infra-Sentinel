# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

FROM docker.io/library/node:22-slim AS builder

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

FROM docker.io/library/node:22-slim AS deps

WORKDIR /app

COPY ./src/frontend/package.json package.json
COPY ./src/frontend/package-lock.json package-lock.json

RUN npm ci --omit=dev --no-audit --no-fund

# -----------------------------------------------------------------------------

FROM docker.io/library/node:22-alpine3.23

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
