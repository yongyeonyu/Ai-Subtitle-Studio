#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT_DIR"
echo "Installing or updating AI Subtitle Studio..."
echo "Default target: /Applications/AI Subtitle Studio.app"
echo "For a local test target, run from Terminal with:"
echo "TARGET_APP=\"$HOME/Applications/AI Subtitle Studio.app\" \"$SCRIPT_DIR/install_or_update_app.sh\""
echo
"$SCRIPT_DIR/install_or_update_app.sh" "$@"
echo
echo "Done."
echo "Press Return to close this window."
read -r _
