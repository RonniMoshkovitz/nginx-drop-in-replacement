FROM debian:bookworm-slim

ARG NGINX_VERSION=1.25.5
ARG DEB_REVISION=1~bookworm
ARG NJS_VERSION=0.8.4
ARG NJS_RELEASE=3~bookworm
ARG OPENSSL_VERSION=3.0.22-1~deb12u2

ENV NGINX_VERSION=${NGINX_VERSION} \
    NJS_VERSION=${NJS_VERSION} \
    NJS_RELEASE=${NJS_RELEASE} \
    PKG_RELEASE=${DEB_REVISION}

RUN set -eux; \
    groupadd --system --gid 101 nginx; \
    useradd --system --gid nginx --no-create-home --home /nonexistent \
        --comment "nginx user" --shell /bin/false --uid 101 nginx

COPY build/output/nginx_${NGINX_VERSION}-${DEB_REVISION}_*.deb /tmp/

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gettext-base \
        libssl3=${OPENSSL_VERSION} \
        openssl=${OPENSSL_VERSION} \
    ; \
    dpkgArch="$(dpkg --print-architecture)"; \
    modBase="https://nginx.org/packages/mainline/debian/pool/nginx/n"; \
    curl -fsSL -o /tmp/nginx-module-xslt.deb \
        "$modBase/nginx-module-xslt/nginx-module-xslt_${NGINX_VERSION}-${PKG_RELEASE}_${dpkgArch}.deb"; \
    curl -fsSL -o /tmp/nginx-module-geoip.deb \
        "$modBase/nginx-module-geoip/nginx-module-geoip_${NGINX_VERSION}-${PKG_RELEASE}_${dpkgArch}.deb"; \
    curl -fsSL -o /tmp/nginx-module-image-filter.deb \
        "$modBase/nginx-module-image-filter/nginx-module-image-filter_${NGINX_VERSION}-${PKG_RELEASE}_${dpkgArch}.deb"; \
    curl -fsSL -o /tmp/nginx-module-njs.deb \
        "$modBase/nginx-module-njs/nginx-module-njs_${NGINX_VERSION}+${NJS_VERSION}-${NJS_RELEASE}_${dpkgArch}.deb"; \
    apt-get install -y --no-install-recommends /tmp/nginx_*.deb /tmp/nginx-module-*.deb; \
    rm -rf /var/lib/apt/lists/* /tmp/*.deb; \
    ln -sf /dev/stdout /var/log/nginx/access.log; \
    ln -sf /dev/stderr /var/log/nginx/error.log; \
    mkdir -p /docker-entrypoint.d

COPY docker/docker-entrypoint.sh /
COPY docker/docker-entrypoint.d/ /docker-entrypoint.d/
RUN chmod +x /docker-entrypoint.sh /docker-entrypoint.d/*.sh /docker-entrypoint.d/*.envsh

ENTRYPOINT ["/docker-entrypoint.sh"]
EXPOSE 80
STOPSIGNAL SIGQUIT
CMD ["nginx", "-g", "daemon off;"]