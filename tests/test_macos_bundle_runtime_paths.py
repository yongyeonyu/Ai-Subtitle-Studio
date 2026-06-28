from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX_RUNTIME_PATH = ROOT / "packaging/macos/fix_bundled_python_runtime.py"
FIX_RUNTIME_SPEC = importlib.util.spec_from_file_location("fix_bundled_python_runtime", FIX_RUNTIME_PATH)
assert FIX_RUNTIME_SPEC is not None
fix_bundled_python_runtime = importlib.util.module_from_spec(FIX_RUNTIME_SPEC)
assert FIX_RUNTIME_SPEC.loader is not None
FIX_RUNTIME_SPEC.loader.exec_module(fix_bundled_python_runtime)
parse_python_framework_dependency = fix_bundled_python_runtime.parse_python_framework_dependency


def test_bundle_runtime_paths_use_writable_app_support(tmp_path):
    support_dir = tmp_path / "App Support" / "AI Subtitle Studio"
    bundle_resources = tmp_path / "AI Subtitle Studio.app" / "Contents" / "Resources"
    env = dict(os.environ)
    env["AI_SUBTITLE_STUDIO_BUNDLE_RESOURCES"] = str(bundle_resources)
    env["AI_SUBTITLE_STUDIO_USER_DATA_DIR"] = str(support_dir)

    code = """
import json
from core.runtime import config
print(json.dumps({
    "running": config.RUNNING_IN_APP_BUNDLE,
    "base": config.BASE_DIR,
    "runtime": config.RUNTIME_BASE_DIR,
    "dataset": config.DATASET_DIR,
    "output": config.OUTPUT_DIR,
    "voice": config.VOICE_DATA_DIR,
    "projects": config.PROJECTS_DIR,
}))
"""
    output = subprocess.check_output(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        text=True,
    )
    data = json.loads(output)

    assert data["running"] is True
    assert Path(data["runtime"]) == support_dir
    assert Path(data["dataset"]) == support_dir / "dataset"
    assert Path(data["output"]) == support_dir / "output"
    assert Path(data["voice"]) == support_dir / "voice_data"
    assert Path(data["projects"]) == support_dir / "projects"
    assert (support_dir / "dataset").is_dir()
    assert (support_dir / "output").is_dir()
    assert (support_dir / "voice_data").is_dir()


def test_parse_python_framework_dependency_uses_framework_binary():
    output = """
/tmp/python:
\t/opt/homebrew/Cellar/python@3.11/3.11.15/Frameworks/Python.framework/Versions/3.11/Python (compatibility version 3.11.0, current version 3.11.0)
\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1356.0.0)
"""
    assert (
        parse_python_framework_dependency(output)
        == "/opt/homebrew/Cellar/python@3.11/3.11.15/Frameworks/Python.framework/Versions/3.11/Python"
    )


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS bundle validation uses Apple tooling")
def test_validate_app_bundle_rejects_external_symlinks(tmp_path):
    root = ROOT
    app = tmp_path / "AI Subtitle Studio.app"
    contents = app / "Contents"
    resources = contents / "Resources"
    macos = contents / "MacOS"
    native = resources / "native"
    payload = resources / "app"
    macos.mkdir(parents=True)
    native.mkdir(parents=True)
    payload.mkdir(parents=True)

    (contents / "Info.plist").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>com.soseolgayumossi.aisubtitlestudio</string>
  <key>CFBundleShortVersionString</key><string>04.01.06</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.video</string>
</dict>
</plist>
""",
        encoding="utf-8",
    )
    for executable in [
        macos / "AI Subtitle Studio",
        resources / "WhisperKitPersistentWorker",
        native / "AIStudioNativeCLI",
    ]:
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
    (payload / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (resources / "python").mkdir()
    (resources / "python" / "external-python").symlink_to("/opt/homebrew/bin/python3.11")

    result = subprocess.run(
        ["bash", str(root / "packaging/macos/validate_app_bundle.sh"), str(app)],
        cwd=root,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 65
    assert "External symlink leaked into bundle" in result.stderr


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS bundle validation uses Apple tooling")
def test_validate_app_bundle_rejects_broken_symlinks(tmp_path):
    root = ROOT
    app = tmp_path / "AI Subtitle Studio.app"
    contents = app / "Contents"
    resources = contents / "Resources"
    macos = contents / "MacOS"
    native = resources / "native"
    payload = resources / "app"
    macos.mkdir(parents=True)
    native.mkdir(parents=True)
    payload.mkdir(parents=True)

    (contents / "Info.plist").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>com.soseolgayumossi.aisubtitlestudio</string>
  <key>CFBundleShortVersionString</key><string>04.01.06</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.video</string>
</dict>
</plist>
""",
        encoding="utf-8",
    )
    for executable in [
        macos / "AI Subtitle Studio",
        resources / "WhisperKitPersistentWorker",
        native / "AIStudioNativeCLI",
    ]:
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
    (payload / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (resources / "python").mkdir()
    (resources / "python" / "broken-python").symlink_to("../missing/python3.11")

    result = subprocess.run(
        ["bash", str(root / "packaging/macos/validate_app_bundle.sh"), str(app)],
        cwd=root,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 65
    assert "Broken symlink leaked into bundle" in result.stderr
