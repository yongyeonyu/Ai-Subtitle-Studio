#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_NAME="AI Subtitle Studio"
DEFAULT_TARGET="/Applications/$APP_NAME.app"
TARGET_APP="${TARGET_APP:-${TARGET_APP_PATH:-$DEFAULT_TARGET}}"
SOURCE_PATH="${1:-}"
MOUNT_DIR=""
TMP_DIR=""

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Updater target is macOS only." >&2
  exit 78
fi

cleanup() {
  if [[ -n "$MOUNT_DIR" && -d "$MOUNT_DIR" ]]; then
    hdiutil detach "$MOUNT_DIR" -quiet || true
  fi
  if [[ -n "$TMP_DIR" && -d "$TMP_DIR" ]]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT

latest_dmg() {
  find "$ROOT_DIR/dist/macos" -maxdepth 1 -type f -name "AI Subtitle Studio-*-macOS.dmg" -print 2>/dev/null | sort | tail -n 1
}

if [[ -z "$SOURCE_PATH" ]]; then
  SOURCE_PATH="$(latest_dmg || true)"
fi
if [[ -z "$SOURCE_PATH" && -d "$ROOT_DIR/dist/macos/$APP_NAME.app" ]]; then
  SOURCE_PATH="$ROOT_DIR/dist/macos/$APP_NAME.app"
fi
if [[ -z "$SOURCE_PATH" ]]; then
  echo "No source app/DMG found. Build one with packaging/macos/build_beta_dmg.sh." >&2
  exit 66
fi
SOURCE_PATH="$(cd "$(dirname "$SOURCE_PATH")" && pwd)/$(basename "$SOURCE_PATH")"

APP_SOURCE=""
case "$SOURCE_PATH" in
  *.app)
    APP_SOURCE="$SOURCE_PATH"
    ;;
  *.dmg)
    MOUNT_DIR="$(mktemp -d /tmp/ai-subtitle-studio-update.XXXXXX)"
    hdiutil attach "$SOURCE_PATH" -mountpoint "$MOUNT_DIR" -nobrowse -readonly -quiet
    APP_SOURCE="$MOUNT_DIR/$APP_NAME.app"
    ;;
  *.zip)
    TMP_DIR="$(mktemp -d /tmp/ai-subtitle-studio-update-zip.XXXXXX)"
    ditto -x -k "$SOURCE_PATH" "$TMP_DIR"
    APP_SOURCE="$(find "$TMP_DIR" -maxdepth 2 -type d -name "$APP_NAME.app" -print -quit)"
    ;;
  *)
    echo "Unsupported update source: $SOURCE_PATH" >&2
    exit 64
    ;;
esac

if [[ ! -d "$APP_SOURCE" ]]; then
  echo "Source app not found in: $SOURCE_PATH" >&2
  exit 66
fi
codesign --verify --deep --strict --verbose=2 "$APP_SOURCE"

if pgrep -x "$APP_NAME" >/dev/null 2>&1; then
  osascript -e 'tell application "AI Subtitle Studio" to quit' >/dev/null 2>&1 || true
  sleep 2
fi
if pgrep -x "$APP_NAME" >/dev/null 2>&1; then
  echo "AI Subtitle Studio is still running. Please quit it and run this updater again." >&2
  exit 75
fi

TARGET_DIR="$(dirname "$TARGET_APP")"
if [[ ! -d "$TARGET_DIR" ]]; then
  mkdir -p "$TARGET_DIR"
fi
if [[ ! -w "$TARGET_DIR" ]]; then
  echo "Target directory is not writable: $TARGET_DIR" >&2
  echo "Try running this command from Terminal with sudo, or set TARGET_APP to a writable path." >&2
  exit 77
fi

BACKUP=""
if [[ -d "$TARGET_APP" ]]; then
  BACKUP="$TARGET_APP.backup.$(date +%Y%m%d%H%M%S)"
  mv "$TARGET_APP" "$BACKUP"
fi

if ditto "$APP_SOURCE" "$TARGET_APP"; then
  codesign --verify --deep --strict --verbose=2 "$TARGET_APP"
  if [[ -x "$ROOT_DIR/packaging/macos/validate_app_bundle.sh" ]]; then
    "$ROOT_DIR/packaging/macos/validate_app_bundle.sh" "$TARGET_APP"
  fi
  echo "Updated: $TARGET_APP"
  if [[ -n "$BACKUP" ]]; then
    echo "Backup kept at: $BACKUP"
  fi
else
  echo "Update failed." >&2
  rm -rf "$TARGET_APP"
  if [[ -n "$BACKUP" && -d "$BACKUP" ]]; then
    mv "$BACKUP" "$TARGET_APP"
    echo "Restored previous app from backup." >&2
  fi
  exit 1
fi
