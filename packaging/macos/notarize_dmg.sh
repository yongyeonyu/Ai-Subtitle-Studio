#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="$("$ROOT_DIR/venv/bin/python" - <<'PY'
from core.runtime import config
print(config.APP_VERSION)
PY
)"
DMG_PATH="${1:-$ROOT_DIR/dist/macos/AI Subtitle Studio-$VERSION-macOS.dmg}"
PROFILE="${NOTARY_KEYCHAIN_PROFILE:-}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "DMG notarization target is macOS only." >&2
  exit 78
fi
if [[ -z "$PROFILE" ]]; then
  echo "Set NOTARY_KEYCHAIN_PROFILE to a notarytool keychain profile." >&2
  exit 64
fi
if [[ ! -f "$DMG_PATH" ]]; then
  echo "DMG not found: $DMG_PATH" >&2
  exit 66
fi

xcrun notarytool submit "$DMG_PATH" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$DMG_PATH"
xcrun stapler validate "$DMG_PATH"
echo "Notarized and stapled DMG: $DMG_PATH"
