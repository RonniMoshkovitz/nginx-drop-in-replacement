#!/bin/bash
# Builds the patched nginx .deb from source.

set -euo pipefail

NGINX_VERSION="${NGINX_VERSION:-1.25.5}"
DEB_REVISION="${DEB_REVISION:-1~bookworm}"
SRC_BASE="https://nginx.org/packages/mainline/debian/pool/nginx/n/nginx"

DSC="nginx_${NGINX_VERSION}-${DEB_REVISION}.dsc"
ORIG="nginx_${NGINX_VERSION}.orig.tar.gz"
DEBIAN_TAR="nginx_${NGINX_VERSION}-${DEB_REVISION}.debian.tar.xz"

echo "Pulling nginx's own Debian source package for ${NGINX_VERSION}-${DEB_REVISION}"
for f in "$DSC" "$ORIG" "$DEBIAN_TAR"; do
    curl -fsSL -o "$f" "$SRC_BASE/$f"
done

dpkg-source --no-check -x "$DSC" nginx-src
cd nginx-src

echo "Wiring local patches into quilt's patch series"
mkdir -p debian/patches
: > debian/patches/series

for p in /build/patches/*.patch; do
    [ -e "$p" ] || continue
    cp "$p" debian/patches/
    basename "$p" >> debian/patches/series
done
echo "patch series:"
cat debian/patches/series

echo "Compiling the .deb from source (dpkg-buildpackage)"

dpkg-buildpackage -b -uc -us

echo "Build finished, copying output"
cd ..
mkdir -p out
cp ./*.deb ./*.buildinfo ./*.changes out/
ls -la out/