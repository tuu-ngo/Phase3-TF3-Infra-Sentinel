# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM python:3.12.13-alpine3.23 AS base

FROM base AS builder
RUN apk add --no-cache build-base linux-headers

COPY ./src/load-generator/requirements.txt .
RUN pip install --no-cache-dir --prefix="/reqs" -r requirements.txt \
    # Playwright publishes a platform-independent Python/JavaScript bundle in
    # a manylinux wheel, but does not publish a musllinux wheel. Install that
    # bundle without its bundled glibc Node binary; the runtime stage replaces
    # the binary with Alpine's patched Node package.
    && pip install --no-cache-dir \
        --target="/reqs/lib/python3.12/site-packages" \
        --platform=manylinux2014_x86_64 \
        --only-binary=:all: \
        --no-deps \
        playwright==1.61.0

FROM base
RUN apk upgrade --no-cache \
    && apk add --no-cache chromium libstdc++ nodejs ttf-freefont \
    && addgroup -S -g 10001 locust \
    && adduser -S -D -u 10001 -G locust locust

WORKDIR /usr/src/app/
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
COPY --from=builder /reqs /usr/local

# Keep Playwright's Python/JavaScript API while using Alpine's patched Node and
# Chromium packages. This preserves browser traffic without introducing the
# vulnerable Debian/Xvfb packages from Playwright's default base image.
RUN rm /usr/local/lib/python3.12/site-packages/playwright/driver/node \
    && ln -s /usr/bin/node /usr/local/lib/python3.12/site-packages/playwright/driver/node \
    && browser_path="$(python -c 'from playwright.sync_api import sync_playwright; p=sync_playwright().start(); print(p.chromium.executable_path); p.stop()')" \
    && mkdir -p "$(dirname "$browser_path")" \
    && ln -s /usr/bin/chromium-browser "$browser_path" \
    && chown -R 10001:10001 /opt/pw-browsers /usr/src/app

COPY --chown=10001:10001 ./src/load-generator/locustfile.py .
COPY --chown=10001:10001 ./src/load-generator/people.json .

USER 10001:10001
ENTRYPOINT ["locust", "--skip-log-setup"]
