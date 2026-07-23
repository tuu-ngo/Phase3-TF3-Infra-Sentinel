# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM golang:1.26.5-bookworm@sha256:1ecb7edf62a0408027bd5729dfd6b1b8766e578e8df93995b225dfd0944eb651 AS builder

WORKDIR /usr/src/app/

COPY ./src/checkout/go.mod go.mod
COPY ./src/checkout/go.sum go.sum

COPY ./src/checkout/genproto/oteldemo/ genproto/oteldemo/
COPY ./src/checkout/kafka/ kafka/
COPY ./src/checkout/money/ money/
COPY ./src/checkout/main.go main.go

# Mandate #8: thêm github.com/xdg-go/scram (SCRAM client cho MSK). go.sum được resolve
# tại build bằng `go mod tidy` (cần source đã copy) thay cho `go mod download` — build
# runner có mạng, tự thêm entry go.sum đúng cho dependency mới + transitive.
RUN go mod tidy

RUN CGO_ENABLED=0 GOOS=linux go build -ldflags "-s -w" -o checkout main.go

FROM gcr.io/distroless/static-debian12:nonroot@sha256:f5b485ea962d9bd1186b2f6b3a061191539b905b82ec395de78cbfae51f20e35

WORKDIR /usr/src/app/

COPY --from=builder /usr/src/app/checkout/ ./

EXPOSE ${CHECKOUT_PORT}
ENTRYPOINT [ "./checkout" ]
