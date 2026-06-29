#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PKG_PATH="${PKG_PATH:-$ROOT_DIR/dist/macos/AI Subtitle Studio.pkg}"
MODE="${1:-validate}"
UPLOAD_CONFIRM_ENV="AI_SUBTITLE_STUDIO_APP_STORE_UPLOAD_CONFIRMED"
READINESS_JSON="${APP_STORE_READINESS_JSON:-}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "App Store upload target is macOS only." >&2
  exit 78
fi
if [[ ! -f "$PKG_PATH" ]]; then
  echo "Package not found: $PKG_PATH" >&2
  exit 66
fi
if [[ "$MODE" != "validate" && "$MODE" != "upload" ]]; then
  echo "Usage: $0 [validate|upload]" >&2
  exit 64
fi

ACTION="--validate-app"
if [[ "$MODE" == "upload" ]]; then
  if [[ "${AI_SUBTITLE_STUDIO_APP_STORE_UPLOAD_CONFIRMED:-}" != "1" ]]; then
    echo "Refusing App Store upload without ${UPLOAD_CONFIRM_ENV}=1 for this exact package." >&2
    exit 64
  fi
  if [[ -z "$READINESS_JSON" ]]; then
    echo "Refusing App Store upload without APP_STORE_READINESS_JSON pointing to the exact readiness report." >&2
    exit 64
  fi
  PYTHON_BIN="${PYTHON:-$ROOT_DIR/venv/bin/python}"
  if [[ ! -x "$PYTHON_BIN" ]]; then
    PYTHON_BIN="python3"
  fi
  "$PYTHON_BIN" "$ROOT_DIR/tools/check_app_store_upload_preflight.py" \
    --readiness-json "$READINESS_JSON" \
    --pkg-path "$PKG_PATH"
  ACTION="--upload-app"
fi

AUTH_ARGS=()
if [[ -n "${ASC_API_KEY:-}" && -n "${ASC_API_ISSUER:-}" ]]; then
  AUTH_ARGS=(--apiKey "$ASC_API_KEY" --apiIssuer "$ASC_API_ISSUER")
elif [[ -n "${ASC_USERNAME:-}" && -n "${ASC_PASSWORD:-}" ]]; then
  AUTH_ARGS=(-u "$ASC_USERNAME" -p "$ASC_PASSWORD")
else
  echo "Set ASC_API_KEY/ASC_API_ISSUER or ASC_USERNAME/ASC_PASSWORD." >&2
  exit 64
fi

xcrun altool "$ACTION" -f "$PKG_PATH" -t macos "${AUTH_ARGS[@]}" --output-format xml
echo "App Store Connect $MODE completed for: $PKG_PATH"
