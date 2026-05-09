#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_NAME="AI Subtitle Studio"
APP_PATH="${APP_PATH:-$ROOT_DIR/dist/macos/$APP_NAME.app}"
VERSION="$("$ROOT_DIR/venv/bin/python" - <<'PY'
from core.runtime import config
print(config.APP_VERSION)
PY
)"
DMG_NAME="${DMG_NAME:-AI Subtitle Studio-$VERSION-macOS.dmg}"
DMG_PATH="${DMG_PATH:-$ROOT_DIR/dist/macos/$DMG_NAME}"
STAGING_DIR=""
VOLUME_NAME="${VOLUME_NAME:-AI Subtitle Studio $VERSION}"
IDENTITY="${DMG_CODESIGN_IDENTITY:-${CODESIGN_IDENTITY:--}}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "DMG target is macOS only." >&2
  exit 78
fi
if [[ ! -d "$APP_PATH" ]]; then
  echo "App bundle not found: $APP_PATH" >&2
  exit 66
fi

cleanup() {
  if [[ -n "$STAGING_DIR" && -d "$STAGING_DIR" ]]; then
    rm -rf "$STAGING_DIR"
  fi
}
trap cleanup EXIT

codesign --verify --deep --strict --verbose=2 "$APP_PATH"

mkdir -p "$ROOT_DIR/dist/macos"
STAGING_DIR="$(mktemp -d "$ROOT_DIR/dist/macos/dmg-staging.XXXXXX")"
mkdir -p "$STAGING_DIR"
ditto "$APP_PATH" "$STAGING_DIR/$APP_NAME.app"
ln -s /Applications "$STAGING_DIR/Applications"
cat > "$STAGING_DIR/README_INSTALL.txt" <<TXT
AI Subtitle Studio $VERSION

Install:
1. Drag "AI Subtitle Studio.app" to Applications.
2. Or run packaging/macos/Install or Update AI Subtitle Studio.command from the repo.

Local test updater:
TARGET_APP="$HOME/Applications/AI Subtitle Studio.app" packaging/macos/install_or_update_app.sh "$DMG_PATH"
TXT

rm -f "$DMG_PATH"
hdiutil create \
  -volname "$VOLUME_NAME" \
  -srcfolder "$STAGING_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

if [[ "$IDENTITY" != "-" ]]; then
  codesign --force --timestamp --sign "$IDENTITY" "$DMG_PATH"
fi

hdiutil verify "$DMG_PATH"
echo "Prepared DMG: $DMG_PATH"
