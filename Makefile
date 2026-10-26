NGINX_VERSION ?= 1.25.5
DEB_REVISION  ?= 1~bookworm
IMAGE_NAME    ?= nginx-patched
IMAGE_TAG     ?= 1.25-bookworm
IMAGE         := $(IMAGE_NAME):$(IMAGE_TAG)


deb:
	docker build \
		--build-arg NGINX_VERSION=$(NGINX_VERSION) \
		--build-arg DEB_REVISION=$(DEB_REVISION) \
		--target export \
		--output type=local,dest=build/output \
		build/

image: deb
	docker build \
		--build-arg NGINX_VERSION=$(NGINX_VERSION) \
		--build-arg DEB_REVISION=$(DEB_REVISION) \
		-f Containerfile \
		-t $(IMAGE) \
		.

DOCKER_SOCK := /var/run/docker.sock
VEX_FILE     := vex/nginx-cve-2026-15176.openvex.json

scan:
	docker run --rm -v $(DOCKER_SOCK):$(DOCKER_SOCK) aquasec/trivy image --timeout 10m $(IMAGE) > reports/patched-trivy.txt
	docker run --rm -v $(DOCKER_SOCK):$(DOCKER_SOCK) anchore/grype docker:$(IMAGE) > reports/patched-grype.txt
	@echo ""
	@echo "CVE-2024-6119 was fixed with a version bump, so it should no longer show up:"
	@grep -i CVE-2024-6119 reports/patched-trivy.txt reports/patched-grype.txt || echo "  confirmed gone"
	@echo ""
	@echo "CVE-2026-15176 was fixed with a backport, so the scanners can still flag the old package version:"
	@grep -i CVE-2026-15176 reports/patched-trivy.txt reports/patched-grype.txt || echo "  scanner didn't catch it this run"

scan-vex:
	docker run --rm -v $(DOCKER_SOCK):$(DOCKER_SOCK) -v "$(CURDIR)/vex:/vex" aquasec/trivy image --timeout 10m --vex /vex/$(notdir $(VEX_FILE)) $(IMAGE) > reports/patched-trivy-vex.txt
	docker run --rm -v $(DOCKER_SOCK):$(DOCKER_SOCK) -v "$(CURDIR):/work" -w /work anchore/grype docker:$(IMAGE) --vex $(VEX_FILE) > reports/patched-grype-vex.txt
	@echo ""
	@echo "Same CVE-2026-15176 check, this time with the VEX statement applied:"
	@grep -i CVE-2026-15176 reports/patched-trivy-vex.txt reports/patched-grype-vex.txt || echo "  suppressed by the VEX document, as expected"
