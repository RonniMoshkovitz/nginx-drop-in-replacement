FROM debian:bookworm-slim

ARG NGINX_VERSION=1.25.5
ARG DEB_REVISION=1~bookworm


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
        libssl3 \
        openssl \
    ; \
    apt-get install -y --no-install-recommends /tmp/nginx_*.deb; \
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
