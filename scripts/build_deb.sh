#!/usr/bin/env bash
set -euo pipefail

# Determine repository root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Extract version from linux_rufus/__init__.py
VERSION=$(python3 -c "import re; print(re.search(r'__version__\s*=\s*[\"\']([^\"\']+)[\"\']', open('${REPO_ROOT}/linux_rufus/__init__.py').read()).group(1))")
PACKAGE_NAME="linux-rufus"
ARCH="all"
DEB_NAME="${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
STAGE_DIR="$(mktemp -d /tmp/deb_stage.XXXXXX)"
DIST_DIR="${REPO_ROOT}/dist"

mkdir -p "${DIST_DIR}"

echo "Building Debian package for ${PACKAGE_NAME} v${VERSION}..."

# Create directory tree
mkdir -p "${STAGE_DIR}/DEBIAN"
mkdir -p "${STAGE_DIR}/usr/bin"
mkdir -p "${STAGE_DIR}/usr/lib/python3/dist-packages/linux_rufus"
mkdir -p "${STAGE_DIR}/usr/share/applications"
mkdir -p "${STAGE_DIR}/usr/share/doc/${PACKAGE_NAME}"

# Write DEBIAN/control
cat << EOF > "${STAGE_DIR}/DEBIAN/control"
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Maintainer: Amit Padhan <amitpadhan979@gmail.com>
Depends: python3 (>= 3.9), dosfstools, parted, util-linux
Recommends: python3-tk, wimtools, 7zip
Description: A reliable, safety-first Linux utility inspired by Rufus
 Linux Rufus is a fast and safety-centric tool to create bootable USB drives
 directly from ISO and IMG files. Supports Rufus DD raw mode, UEFI/GPT
 FAT32 extraction, Windows 11 TPM/Secure Boot hardware bypasses, and
 an interactive terminal UI alongside classic desktop GUI.
EOF

# Copy Python package files
cp -r "${REPO_ROOT}/linux_rufus/"* "${STAGE_DIR}/usr/lib/python3/dist-packages/linux_rufus/"

# Clean any pycache in staging
find "${STAGE_DIR}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "${STAGE_DIR}" -type f -name "*.pyc" -delete 2>/dev/null || true

# Install wrapper script into /usr/bin/linux-rufus and /usr/bin/lrufus
cat << 'EOF' > "${STAGE_DIR}/usr/bin/linux-rufus"
#!/usr/bin/env python3
import sys
from linux_rufus.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
EOF
chmod 0755 "${STAGE_DIR}/usr/bin/linux-rufus"
ln -sf linux-rufus "${STAGE_DIR}/usr/bin/lrufus"

# Install .desktop file
cp "${REPO_ROOT}/packaging/linux-rufus.desktop" "${STAGE_DIR}/usr/share/applications/"
chmod 0644 "${STAGE_DIR}/usr/share/applications/linux-rufus.desktop"

# Install documentation & license
cp "${REPO_ROOT}/README.md" "${STAGE_DIR}/usr/share/doc/${PACKAGE_NAME}/README"
cp "${REPO_ROOT}/LICENSE" "${STAGE_DIR}/usr/share/doc/${PACKAGE_NAME}/copyright"
chmod 0644 "${STAGE_DIR}/usr/share/doc/${PACKAGE_NAME}/"*

# Build the .deb archive
dpkg-deb --root-owner-group --build "${STAGE_DIR}" "${DIST_DIR}/${DEB_NAME}"

# Cleanup
rm -rf "${STAGE_DIR}"

echo "✔ Successfully generated: ${DIST_DIR}/${DEB_NAME}"
