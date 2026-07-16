# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM ghcr.io/mlocati/php-extension-installer:2.9.11 AS installer

FROM docker.io/library/composer:2.8.12 AS vendor

WORKDIR /tmp/

COPY ./src/quote/composer.json composer.json

RUN composer install \
    --ignore-platform-reqs \
    --no-interaction \
    --no-plugins \
    --no-scripts \
    --no-dev \
    --prefer-dist

FROM docker.io/library/php:8.4-cli-alpine3.22

# Trivy gate (PM-101): patch known-fixed HIGH CVEs in the Alpine base layer
# (c-ares CVE-2026-33630, openssl/libcrypto3/libssl3 CVE-2026-45447) instead
# of waiting for the upstream php:8.4-cli-alpine3.22 tag to be refreshed.
RUN apk update && apk upgrade --no-cache c-ares libcrypto3 libssl3 openssl

COPY --from=installer /usr/bin/install-php-extensions /usr/local/bin/

RUN apk upgrade --no-cache && \
    install-php-extensions opcache pcntl protobuf opentelemetry

WORKDIR /var/www

USER www-data

COPY --from=vendor /tmp/vendor/ vendor/

COPY ./src/quote/app/ app/
COPY ./src/quote/public/ public/
COPY ./src/quote/src/ src/

EXPOSE ${QUOTE_PORT}

CMD ["php", "public/index.php"]
