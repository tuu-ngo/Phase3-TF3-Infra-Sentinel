# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Use a Debian-based Hex builder and a pinned distroless Debian runtime. This
# avoids Alpine DNS differences while keeping build-only packages out of prod.
#
# https://hub.docker.com/r/hexpm/elixir/tags?name=ubuntu
# https://hub.docker.com/_/ubuntu/tags
#
# This file is based on these images:
#
#   - https://hub.docker.com/r/hexpm/elixir/tags - for the build image
#   - https://github.com/GoogleContainerTools/distroless - for the release image
#   - https://pkgs.org/ - resource for finding needed packages
#   - Ex: docker.io/hexpm/elixir:1.18.4-erlang-27.3.4-debian-bookworm-20250610-slim
#
ARG ELIXIR_VERSION=1.19.3
ARG OTP_VERSION=27.3.4
ARG DEBIAN_VERSION=bookworm-20260610-slim

ARG BUILDER_IMAGE="docker.io/hexpm/elixir:${ELIXIR_VERSION}-erlang-${OTP_VERSION}-debian-${DEBIAN_VERSION}"
ARG RUNNER_IMAGE="gcr.io/distroless/cc-debian13:nonroot@sha256:d97bc0a941b8d4be647dc0ee75b264ddbb772f1ac5ba690a4309c00723b23775"

FROM ${BUILDER_IMAGE} AS builder

# Pin the official Tailwind v4 binary so `mix assets.setup` never depends on a
# best-effort runtime download. The checksum protects the remote ADD against
# replacement and keeps the builder reproducible.
ADD --checksum=sha256:08951af1ce3cd66e715ba647d1f624e63f374885738c5cb525f31518495bcda6 \
    https://github.com/tailwindlabs/tailwindcss/releases/download/v4.0.9/tailwindcss-linux-x64 \
    /opt/tailwindcss
RUN chmod 0755 /opt/tailwindcss

# Materialize the same locked heroicons v2.2.0 source without installing Git.
# Normalize its archive layout to the path expected by Tailwind's plugin.
ADD --checksum=sha256:42bd31001127631a20270e7bd87ac13647bfcd628dd533e2ff31497068b4f7af \
    https://github.com/tailwindlabs/heroicons/archive/refs/tags/v2.2.0.tar.gz \
    /tmp/heroicons-v2.2.0.tar.gz
RUN mkdir -p /opt/heroicons \
  && tar -xzf /tmp/heroicons-v2.2.0.tar.gz \
       -C /opt/heroicons --strip-components=1 \
       heroicons-2.2.0/optimized \
  && if [ -d /opt/heroicons/24 ]; then \
       mv /opt/heroicons/24 /opt/heroicons/optimized; \
     fi \
  && test -d /opt/heroicons/optimized/24/outline \
  && rm /tmp/heroicons-v2.2.0.tar.gz

# prepare build dir
WORKDIR /app

# install hex + rebar
RUN mix local.hex --force \
  && mix local.rebar --force

# set build ENV
ENV MIX_ENV="prod"
ENV HEX_HTTP_CONCURRENCY="4"
ENV HEX_HTTP_TIMEOUT="180"

# install mix dependencies
COPY ./src/flagd-ui/mix.exs ./src/flagd-ui/mix.lock ./
RUN --mount=type=cache,target=/root/.hex mix deps.get --only $MIX_ENV
RUN ln -s /opt/heroicons /app/deps/heroicons
RUN mix hex.audit
RUN mkdir config

# copy compile-time config files before we compile dependencies
# to ensure any relevant config change will trigger the dependencies
# to be re-compiled.
COPY ./src/flagd-ui/config/config.exs ./src/flagd-ui/config/${MIX_ENV}.exs ./src/flagd-ui/config/runtime.exs config/
RUN mix deps.compile

RUN mix assets.setup

COPY ./src/flagd-ui/priv priv

COPY ./src/flagd-ui/lib lib

COPY ./src/flagd-ui/assets assets

# compile assets
RUN mix assets.deploy

# Compile the release
RUN mix compile

COPY ./src/flagd-ui/rel rel
RUN mix release

# Phoenix releases use a POSIX shell launcher. Keep the final image
# distroless and provide only a pinned static BusyBox command surface.
FROM docker.io/library/busybox:1.37.0-musl@sha256:222ad6d973c0d198014546a65cd02c5fdedcc172123c5b4c2bf0af636550bd94 AS shell
RUN mkdir -p /runtime-bin \
  && cp /bin/busybox /runtime-bin/busybox \
  && /bin/busybox --install -s /runtime-bin

# start a new build stage so that the final image will only contain
# the compiled release and other runtime necessities
FROM ${RUNNER_IMAGE} AS final

COPY --from=shell /runtime-bin/ /bin/
COPY --from=builder /lib/x86_64-linux-gnu/libtinfo.so.6* /lib/x86_64-linux-gnu/
COPY --from=builder /usr/lib/x86_64-linux-gnu/libcrypto.so.3 /usr/lib/x86_64-linux-gnu/

WORKDIR "/app"

# set runner ENV
ENV MIX_ENV="prod"
ENV LANG="C.UTF-8"
ENV LANGUAGE="C.UTF-8"
ENV LC_ALL="C.UTF-8"
ENV ELIXIR_ERL_OPTIONS="+fnu"

# Only copy the final release from the build stage
COPY --from=builder --chown=65532:65532 /app/_build/${MIX_ENV}/rel/flagd_ui ./

USER 65532:65532

EXPOSE ${FLAGD_UI_PORT}

# If using an environment that doesn't automatically reap zombie processes, it is
# advised to add an init process such as tini via `apt-get install`
# above and adding an entrypoint. See https://github.com/krallin/tini for details
# ENTRYPOINT ["/tini", "--"]

CMD ["/app/bin/server"]
