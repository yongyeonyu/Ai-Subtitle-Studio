#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Beta DMG target is macOS only." >&2
  exit 78
fi

"$ROOT_DIR/packaging/macos/build_app_bundle.sh"
"$ROOT_DIR/packaging/macos/sign_app_bundle.sh"
"$ROOT_DIR/packaging/macos/validate_app_bundle.sh"
"$ROOT_DIR/packaging/macos/create_dmg.sh"
"$ROOT_DIR/packaging/macos/validate_dmg.sh"

if [[ -n "${NOTARY_KEYCHAIN_PROFILE:-}" ]]; then
  "$ROOT_DIR/packaging/macos/notarize_dmg.sh"
  "$ROOT_DIR/packaging/macos/validate_dmg.sh"
else
  echo "Skipping notarization because NOTARY_KEYCHAIN_PROFILE is not set."
fi

echo "Beta DMG is ready in $ROOT_DIR/dist/macos."
