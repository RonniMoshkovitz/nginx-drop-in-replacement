FROM debian:bookworm-slim AS build

ARG NGINX_VERSION=1.25.5
ARG DEB_REVISION=1~bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        build-essential \
        debhelper \
        dpkg-dev \
        quilt \
        lsb-release \
        libssl-dev \
        libpcre2-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY patches/ patches/
COPY build.sh build.sh

RUN NGINX_VERSION=${NGINX_VERSION} DEB_REVISION=${DEB_REVISION} \
    bash /build/build.sh

FROM scratch AS export
COPY --from=build /build/out/ /
