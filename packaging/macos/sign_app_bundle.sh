#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_PATH="${1:-$ROOT_DIR/dist/macos/AI Subtitle Studio.app}"
ENTITLEMENTS="${ENTITLEMENTS_PATH:-$ROOT_DIR/packaging/macos/AI Subtitle Studio.entitlements}"
IDENTITY="${CODESIGN_IDENTITY:--}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Code signing target is macOS only." >&2
  exit 78
fi
if [[ ! -d "$APP_PATH" ]]; then
  echo "App bundle not found: $APP_PATH" >&2
  exit 66
fi
if [[ ! -f "$ENTITLEMENTS" ]]; then
  echo "Entitlements file not found: $ENTITLEMENTS" >&2
  exit 66
fi

SIGN_ARGS=(--force --timestamp --options runtime --entitlements "$ENTITLEMENTS" --sign "$IDENTITY")
if [[ "$IDENTITY" == "-" ]]; then
  SIGN_ARGS=(--force --sign -)
fi

while IFS= read -r -d '' item; do
  codesign "${SIGN_ARGS[@]}" "$item"
done < <(
  find "$APP_PATH/Contents" -type f \( -perm -111 -o -name "*.so" -o -name "*.dylib" \) -print0
)

codesign "${SIGN_ARGS[@]}" "$APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"
echo "Signed and verified: $APP_PATH"
