#!/bin/bash
# Builds the patched nginx .deb from source.

set -euo pipefail

NGINX_VERSION="${NGINX_VERSION:-1.25.5}"
DEB_REVISION="${DEB_REVISION:-1~bookworm}"
SRC_BASE="https://nginx.org/packages/mainline/debian/pool/nginx/n/nginx"

DSC="nginx_${NGINX_VERSION}-${DEB_REVISION}.dsc"
ORIG="nginx_${NGINX_VERSION}.orig.tar.gz"
DEBIAN_TAR="nginx_${NGINX_VERSION}-${DEB_REVISION}.debian.tar.xz"

echo "=== [1/4] Fetching nginx's own Debian source package (${NGINX_VERSION}-${DEB_REVISION}) ==="
# Downloads the source files needed in order to build the package.
for f in "$DSC" "$ORIG" "$DEBIAN_TAR"; do
    curl -fsSL -o "$f" "$SRC_BASE/$f"
done

# dpkg-source verifies the downloaded files against the checksums recorded in the .dsc.
dpkg-source --no-check -x "$DSC" nginx-src
cd nginx-src

echo "=== [2/4] Registering CVE backport patches with the Debian quilt patch system ==="
mkdir -p debian/patches
: > debian/patches/series
# Copies local patches into the Debian source tree and adds them to quilt's patch list.
for p in /build/patches/*.patch; do
    [ -e "$p" ] || continue
    cp "$p" debian/patches/
    basename "$p" >> debian/patches/series
done
echo "patch series:"
cat debian/patches/series

echo "=== [3/4] Compiling the .deb from source (dpkg-buildpackage) ==="
# debian/patches/series is applied automatically (dpkg source format 3.0 / quilt) as part
# of the build.
dpkg-buildpackage -b -uc -us

echo "=== [4/4] Collecting build artifacts ==="
cd ..
mkdir -p out
# Puts the generated packages and build metadata in the output directory.
cp ./*.deb ./*.buildinfo ./*.changes out/
ls -la out/
