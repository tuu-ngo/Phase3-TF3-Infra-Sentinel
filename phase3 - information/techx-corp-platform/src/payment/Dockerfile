# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM docker.io/library/node:22.22.0-slim@sha256:dd9d21971ec4395903fa6143c2b9267d048ae01ca6d3ea96f16cb30df6187d94 AS builder

WORKDIR /usr/src/app/

COPY ./src/payment/package.json package.json
COPY ./src/payment/package-lock.json package-lock.json

RUN npm ci --omit=dev --no-audit --no-fund

# -----------------------------------------------------------------------------

FROM docker.io/library/node:22.22.0-alpine3.23@sha256:e4bf2a82ad0a4037d28035ae71529873c069b13eb0455466ae0bc13363826e34

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
