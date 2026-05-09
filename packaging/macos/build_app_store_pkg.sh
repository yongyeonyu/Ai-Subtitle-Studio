#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_PATH="${APP_PATH:-$ROOT_DIR/dist/macos/AI Subtitle Studio.app}"
PKG_PATH="${PKG_PATH:-$ROOT_DIR/dist/macos/AI Subtitle Studio.pkg}"
IDENTITY="${INSTALLER_IDENTITY:-}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "App Store package target is macOS only." >&2
  exit 78
fi
if [[ ! -d "$APP_PATH" ]]; then
  echo "App bundle not found: $APP_PATH" >&2
  exit 66
fi
if [[ -z "$IDENTITY" ]]; then
  echo "Set INSTALLER_IDENTITY to your Mac App Store installer signing identity." >&2
  exit 64
fi

codesign --verify --deep --strict --verbose=2 "$APP_PATH"
rm -f "$PKG_PATH"
productbuild --component "$APP_PATH" /Applications --sign "$IDENTITY" "$PKG_PATH"
pkgutil --check-signature "$PKG_PATH"
echo "Prepared App Store package: $PKG_PATH"
