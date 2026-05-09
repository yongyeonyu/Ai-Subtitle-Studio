#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_PATH="${1:-$ROOT_DIR/dist/macos/AI Subtitle Studio.app}"
PROFILE="${NOTARY_KEYCHAIN_PROFILE:-}"
ZIP_PATH="${ZIP_PATH:-$ROOT_DIR/dist/macos/AI Subtitle Studio-notary.zip}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Notarization target is macOS only." >&2
  exit 78
fi
if [[ -z "$PROFILE" ]]; then
  echo "Set NOTARY_KEYCHAIN_PROFILE to a notarytool keychain profile." >&2
  exit 64
fi
if [[ ! -d "$APP_PATH" ]]; then
  echo "App bundle not found: $APP_PATH" >&2
  exit 66
fi

codesign --verify --deep --strict --verbose=2 "$APP_PATH"
rm -f "$ZIP_PATH"
ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"
xcrun notarytool submit "$ZIP_PATH" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$APP_PATH"
xcrun stapler validate "$APP_PATH"
echo "Notarized and stapled: $APP_PATH"
