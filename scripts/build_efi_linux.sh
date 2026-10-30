#!/usr/bin/env bash
# language: bash, file: build_efi_linux.sh
set -euo pipefail

EDK2_DIR="${EDK2_DIR:-$HOME/edk2}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG_SRC="$REPO_ROOT/QackLockerPkg"
PKG_LINK="$EDK2_DIR/QackLockerPkg"

if [ ! -d "$EDK2_DIR" ]; then
  echo "EDK2 not found at $EDK2_DIR. Clone it first:"
  echo "  git clone --recurse-submodules https://github.com/tianocore/edk2.git ~/edk2"
  exit 1
fi

cd "$EDK2_DIR"
source edksetup.sh BaseTools
make -C BaseTools

ln -sfn "$PKG_SRC" "$PKG_LINK"

build -p QackLockerPkg/QackLockerPkg.dsc -a X64 -t GCC5 -b RELEASE

OUT="$EDK2_DIR/Build/QackLockerPkg/RELEASE_GCC5/X64/QackLockerEfi.efi"
if [ ! -f "$OUT" ]; then
  echo "Build failed: $OUT not found"
  exit 1
fi

cp "$OUT" "$REPO_ROOT/bootx64.efi"
echo "Built: $REPO_ROOT/bootx64.efi"
