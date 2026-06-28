#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_PATH="${1:-$ROOT_DIR/dist/macos/AI Subtitle Studio.app}"
INFO_PLIST="$APP_PATH/Contents/Info.plist"
WORKER="$APP_PATH/Contents/Resources/WhisperKitPersistentWorker"
NATIVE_CLI="$APP_PATH/Contents/Resources/native/AIStudioNativeCLI"
PAYLOAD="$APP_PATH/Contents/Resources/app/main.py"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Validation target is macOS only." >&2
  exit 78
fi
if [[ ! -d "$APP_PATH" ]]; then
  echo "App bundle not found: $APP_PATH" >&2
  exit 66
fi

plutil -lint "$INFO_PLIST" >/dev/null

BUNDLE_ID="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$INFO_PLIST")"
VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$INFO_PLIST")"
MIN_SYSTEM="$(/usr/libexec/PlistBuddy -c 'Print :LSMinimumSystemVersion' "$INFO_PLIST")"
CATEGORY="$(/usr/libexec/PlistBuddy -c 'Print :LSApplicationCategoryType' "$INFO_PLIST")"

[[ "$BUNDLE_ID" == "com.soseolgayumossi.aisubtitlestudio" ]]
[[ "$VERSION" != "__APP_VERSION__" && -n "$VERSION" ]]
[[ -n "$MIN_SYSTEM" ]]
[[ "$CATEGORY" == "public.app-category.video" ]]
[[ -x "$APP_PATH/Contents/MacOS/AI Subtitle Studio" ]]
[[ -x "$WORKER" ]]
[[ -x "$NATIVE_CLI" ]]
[[ -f "$PAYLOAD" ]]

if find "$APP_PATH" -path "*/.git/*" -print -quit | grep -q .; then
  echo "Git metadata leaked into bundle." >&2
  exit 65
fi
while IFS= read -r -d '' link_path; do
  target="$(readlink "$link_path")"
  if [[ "$target" == /* ]]; then
    if ! resolved="$(realpath "$target" 2>/dev/null)"; then
      echo "Broken symlink leaked into bundle: $link_path -> $target" >&2
      exit 65
    fi
    case "$resolved" in
      "$APP_PATH"/*) ;;
      *)
        echo "External symlink leaked into bundle: $link_path -> $target" >&2
        exit 65
        ;;
    esac
  elif [[ ! -e "$(dirname "$link_path")/$target" ]]; then
    echo "Broken symlink leaked into bundle: $link_path -> $target" >&2
    exit 65
  fi
done < <(find "$APP_PATH" -type l -print0)
for forbidden in "__pycache__" ".codex_work" ".build" ".swiftpm" "output" "projects" "dataset/video_preview_cache" "dataset/lora_personalization"; do
  if find "$APP_PATH/Contents/Resources/app" -path "*/$forbidden" -print -quit | grep -q .; then
    echo "Runtime-only path leaked into bundle: $forbidden" >&2
    exit 65
  fi
done

if codesign --verify --deep --strict --verbose=2 "$APP_PATH" >/dev/null 2>&1; then
  echo "codesign verification: ok"
else
  echo "codesign verification: not signed yet or not strict-valid" >&2
fi

echo "Bundle validation passed: $APP_PATH"
