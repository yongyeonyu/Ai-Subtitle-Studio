#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_NAME="AI Subtitle Studio"
APP_DIR="$ROOT_DIR/dist/macos/$APP_NAME.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
APP_PAYLOAD_DIR="$RESOURCES_DIR/app"
PYTHON_PAYLOAD_DIR="$RESOURCES_DIR/python"
VERSION="$("$ROOT_DIR/venv/bin/python" - <<'PY'
from core.runtime import config
print(config.APP_VERSION)
PY
)"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This bundle target is macOS only." >&2
  exit 78
fi

command -v xcodebuild >/dev/null
command -v swift >/dev/null

rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR/native"

swift build -c release --package-path "$ROOT_DIR/experiments/whisperkit_persistent_worker"
swift build -c release --package-path "$ROOT_DIR/native/macos/AIStudioNative"

WORKER="$ROOT_DIR/experiments/whisperkit_persistent_worker/.build/release/WhisperKitPersistentWorker"
if [[ -x "$WORKER" ]]; then
  cp "$WORKER" "$RESOURCES_DIR/WhisperKitPersistentWorker"
fi

NATIVE_CLI="$ROOT_DIR/native/macos/AIStudioNative/.build/release/AIStudioNativeCLI"
if [[ -x "$NATIVE_CLI" ]]; then
  cp "$NATIVE_CLI" "$RESOURCES_DIR/native/AIStudioNativeCLI"
fi

find "$ROOT_DIR/core" -maxdepth 1 -type f \( -name "*.so" -o -name "*.dylib" \) -exec cp {} "$RESOURCES_DIR/native/" \;

"$ROOT_DIR/venv/bin/python" - <<PY
from __future__ import annotations

import shutil
from pathlib import Path

root = Path("$ROOT_DIR")
payload = Path("$APP_PAYLOAD_DIR")
ignore_names = {
    ".git",
    ".github",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".codex_work",
    ".build",
    ".swiftpm",
    "venv",
    "VENV",
    "__pycache__",
    "build",
    "dist",
    "models",
    "output",
    "projects",
    "test video",
    "dataset/video_preview_cache",
    "dataset/lora_personalization",
    "experiments/whisperkit_persistent_worker/.build",
    "native/macos/AIStudioNative/.build",
}

def ignored(dir_path: str, names: list[str]) -> set[str]:
    base = Path(dir_path)
    rel_base = base.relative_to(root) if base != root else Path("")
    out: set[str] = set()
    for name in names:
        rel = str((rel_base / name).as_posix())
        if name in ignore_names or rel in ignore_names:
            out.add(name)
        if name.endswith((".pyc", ".pyo")) or name == ".DS_Store":
            out.add(name)
    return out

payload.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(root, payload, ignore=ignored)
PY

if [[ "${INCLUDE_LOCAL_VENV:-0}" == "1" ]]; then
  if [[ ! -x "$ROOT_DIR/venv/bin/python" ]]; then
    echo "INCLUDE_LOCAL_VENV=1 was set, but $ROOT_DIR/venv/bin/python is missing." >&2
    exit 66
  fi
  command -v otool >/dev/null
  command -v install_name_tool >/dev/null
  mkdir -p "$PYTHON_PAYLOAD_DIR"
  if command -v rsync >/dev/null; then
    rsync -a --delete "$ROOT_DIR/venv/" "$PYTHON_PAYLOAD_DIR/"
  else
    "$ROOT_DIR/venv/bin/python" - <<PY
from pathlib import Path
import shutil
src = Path("$ROOT_DIR/venv")
dst = Path("$PYTHON_PAYLOAD_DIR")
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(src, dst)
PY
  fi
  "$ROOT_DIR/venv/bin/python" "$ROOT_DIR/packaging/macos/fix_bundled_python_runtime.py" \
    --source-venv "$ROOT_DIR/venv" \
    --bundle-python-dir "$PYTHON_PAYLOAD_DIR"
fi

sed "s/__APP_VERSION__/$VERSION/g" \
  "$ROOT_DIR/packaging/macos/Info.plist.template" \
  > "$CONTENTS_DIR/Info.plist"

cat > "$MACOS_DIR/$APP_NAME" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
CONTENTS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
APP_PAYLOAD="$RESOURCES_DIR/app"
export WHISPERKIT_PERSISTENT_WORKER="$RESOURCES_DIR/WhisperKitPersistentWorker"
export AI_SUBTITLE_STUDIO_BUNDLE_RESOURCES="$RESOURCES_DIR"
export PYTHONDONTWRITEBYTECODE=1
export PATH="/opt/homebrew/bin:/opt/homebrew/opt/python@3.11/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

if [[ -d "$RESOURCES_DIR/python/Frameworks/Python.framework/Versions/3.11" ]]; then
  export PYTHONHOME="$RESOURCES_DIR/python/Frameworks/Python.framework/Versions/3.11"
  export PYTHONPATH="$RESOURCES_DIR/python/lib/python3.11/site-packages:$APP_PAYLOAD${PYTHONPATH:+:$PYTHONPATH}"
fi

PYTHON="$RESOURCES_DIR/python/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$RESOURCES_DIR/python/bin/python3"
fi
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$APP_PAYLOAD/venv/bin/python"
fi
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3.11 || command -v python3)"
fi
if [[ -z "${PYTHON:-}" || ! -x "$PYTHON" ]]; then
  echo "Bundled Python runtime not found." >&2
  exit 69
fi

cd "$APP_PAYLOAD"
exec "$PYTHON" "$APP_PAYLOAD/main.py"
SH
chmod +x "$MACOS_DIR/$APP_NAME"

echo "Prepared $APP_DIR"
echo "Next: run packaging/macos/sign_app_bundle.sh and packaging/macos/validate_app_bundle.sh."
