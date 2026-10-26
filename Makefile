NGINX_VERSION ?= 1.25.5
DEB_REVISION  ?= 1~bookworm


deb:
	docker build \
		--build-arg NGINX_VERSION=$(NGINX_VERSION) \
		--build-arg DEB_REVISION=$(DEB_REVISION) \
		--target export \
		--output type=local,dest=build/output \
		build/

