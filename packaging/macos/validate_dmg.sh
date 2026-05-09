#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="$("$ROOT_DIR/venv/bin/python" - <<'PY'
from core.runtime import config
print(config.APP_VERSION)
PY
)"
DMG_PATH="${1:-$ROOT_DIR/dist/macos/AI Subtitle Studio-$VERSION-macOS.dmg}"
MOUNT_DIR=""

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "DMG validation target is macOS only." >&2
  exit 78
fi
if [[ ! -f "$DMG_PATH" ]]; then
  echo "DMG not found: $DMG_PATH" >&2
  exit 66
fi

cleanup() {
  if [[ -n "$MOUNT_DIR" && -d "$MOUNT_DIR" ]]; then
    hdiutil detach "$MOUNT_DIR" -quiet || true
  fi
}
trap cleanup EXIT

hdiutil verify "$DMG_PATH"
MOUNT_DIR="$(mktemp -d /tmp/ai-subtitle-studio-dmg.XXXXXX)"
hdiutil attach "$DMG_PATH" -mountpoint "$MOUNT_DIR" -nobrowse -readonly -quiet

APP_PATH="$MOUNT_DIR/AI Subtitle Studio.app"
[[ -d "$APP_PATH" ]]
[[ -L "$MOUNT_DIR/Applications" || -d "$MOUNT_DIR/Applications" ]]
"$ROOT_DIR/packaging/macos/validate_app_bundle.sh" "$APP_PATH"
spctl --assess --type execute --verbose "$APP_PATH" || {
  echo "Gatekeeper assessment failed. This is expected for ad-hoc signed local test builds." >&2
}

echo "DMG validation passed: $DMG_PATH"
