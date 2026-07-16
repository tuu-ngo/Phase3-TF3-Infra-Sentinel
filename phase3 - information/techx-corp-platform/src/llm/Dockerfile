# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM docker.io/library/python:3.12.13-alpine3.23 AS build-venv

COPY ./src/llm/requirements.txt requirements.txt

RUN python -m venv venv && \
    venv/bin/pip install --no-cache-dir -r requirements.txt

FROM docker.io/library/python:3.12.13-alpine3.23

# Apply Alpine security fixes in the runtime layer; Trivy is the release gate.
RUN apk upgrade --no-cache

COPY --from=build-venv /venv/ /venv/

WORKDIR /app

COPY ./src/llm/app.py app.py
COPY ./src/llm/product-review-summaries/product-review-summaries.json product-review-summaries.json
COPY ./src/llm/product-review-summaries/inaccurate-product-review-summaries.json inaccurate-product-review-summaries.json

EXPOSE ${LLM_PORT}
ENTRYPOINT [ "/venv/bin/python", "app.py" ]
