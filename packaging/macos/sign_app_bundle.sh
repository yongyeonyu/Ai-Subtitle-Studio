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

SIGN_ARGS=(--force --timestamp --options runtime --sign "$IDENTITY")
APP_SIGN_ARGS=(--force --timestamp --options runtime --entitlements "$ENTITLEMENTS" --sign "$IDENTITY")
if [[ "$IDENTITY" == "-" ]]; then
  SIGN_ARGS=(--force --sign -)
  APP_SIGN_ARGS=(--force --sign -)
fi

while IFS= read -r -d '' item; do
  codesign "${SIGN_ARGS[@]}" "$item"
done < <(
  find "$APP_PATH/Contents" -type f \( -perm -111 -o -name "*.so" -o -name "*.dylib" \) -print0
)

NESTED_CODE_LIST="$(mktemp)"
trap 'rm -f "$NESTED_CODE_LIST"' EXIT
"$ROOT_DIR/venv/bin/python" - <<PY > "$NESTED_CODE_LIST"
from pathlib import Path

root = Path("$APP_PATH") / "Contents"
def has_bundle_plist(path: Path) -> bool:
    if path.suffix == ".app":
        return (path / "Contents" / "Info.plist").is_file()
    if path.suffix == ".framework":
        return any(path.glob("**/Info.plist"))
    return False

items = [
    path
    for path in root.rglob("*")
    if path.is_dir() and path.suffix in {".app", ".framework"} and has_bundle_plist(path)
]
for path in sorted(items, key=lambda item: len(item.parts), reverse=True):
    print(path)
PY

while IFS= read -r item; do
  [[ -n "$item" ]] || continue
  codesign "${SIGN_ARGS[@]}" "$item"
done < "$NESTED_CODE_LIST"

codesign "${APP_SIGN_ARGS[@]}" "$APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"
echo "Signed and verified: $APP_PATH"
