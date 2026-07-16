# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM docker.io/library/node:22.22.0-slim AS builder

WORKDIR /usr/src/app/

COPY ./src/payment/package.json package.json
COPY ./src/payment/package-lock.json package-lock.json

RUN npm ci --omit=dev --no-audit --no-fund

# -----------------------------------------------------------------------------

FROM docker.io/library/node:22.22.0-alpine3.23

RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/node_modules/npm \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx \
    && corepack disable \
    && rm -f /usr/local/bin/corepack

WORKDIR /usr/src/app/

COPY --from=builder --chown=node:node /usr/src/app/node_modules/ node_modules/

COPY --chown=node:node ./pb/demo.proto demo.proto

COPY --chown=node:node ./src/payment/charge.js charge.js
COPY --chown=node:node ./src/payment/index.js index.js
COPY --chown=node:node ./src/payment/logger.js logger.js
COPY --chown=node:node ./src/payment/opentelemetry.js opentelemetry.js

USER node

EXPOSE ${PAYMENT_PORT}

CMD ["node", "--require=./opentelemetry.js", "index.js"]
