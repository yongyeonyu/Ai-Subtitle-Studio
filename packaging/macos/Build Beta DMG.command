#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT_DIR"
echo "Building AI Subtitle Studio beta DMG..."
"$SCRIPT_DIR/build_beta_dmg.sh"
echo
echo "Done. Output folder: $ROOT_DIR/dist/macos"
echo "Press Return to close this window."
read -r _
