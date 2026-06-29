from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path

from core.runtime.config import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "packaging" / "macos" / "upload_app_store_build.sh"
UPLOAD_CONFIRM_ENV = "AI_SUBTITLE_STUDIO_APP_STORE_UPLOAD_CONFIRMED"


def _fake_macos_tools(tmp_path: Path) -> tuple[Path, Path]:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir(exist_ok=True)
    log_path = tmp_path / "xcrun_args.txt"
    uname = fakebin / "uname"
    uname.write_text("#!/usr/bin/env bash\nprintf 'Darwin\\n'\n", encoding="utf-8")
    uname.chmod(0o755)
    xcrun = fakebin / "xcrun"
    xcrun.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" > {str(log_path)!r}\n",
        encoding="utf-8",
    )
    xcrun.chmod(0o755)
    return fakebin, log_path


def _env(tmp_path: Path, package: Path) -> dict[str, str]:
    fakebin, _ = _fake_macos_tools(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fakebin}:{env.get('PATH', '')}",
            "PKG_PATH": str(package),
            "ASC_API_KEY": "KEY",
            "ASC_API_ISSUER": "ISSUER",
            "PYTHON": sys.executable,
        }
    )
    env.pop(UPLOAD_CONFIRM_ENV, None)
    return env


def _ready_readiness_json(tmp_path: Path, package: Path) -> Path:
    from tools.check_app_store_upload_preflight import REQUIRED_UPLOAD_GATES

    readiness = tmp_path / "readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "schema": "ai_subtitle_studio.app_store_readiness.v1",
                "root": str(tmp_path),
                "app_version": APP_VERSION,
                "app_store_submission_ready": True,
                "blockers": [],
                "submission_gate_summary": {gate: True for gate in REQUIRED_UPLOAD_GATES},
                "owner_metadata_values_preflight": {
                    "ready": True,
                    "owner_input_ready_count": 8,
                    "owner_input_total": 8,
                    "app_store_connect_metadata_ready_count": 8,
                    "app_store_connect_metadata_total": 8,
                    "forbidden_claim_scan": {"status": "pass"},
                },
                "artifacts": {"app_store_pkg": {"path": str(package), "is_file": True}},
            }
        ),
        encoding="utf-8",
    )
    return readiness


def test_upload_script_allows_validation_without_upload_confirmation(tmp_path):
    package = tmp_path / "AI Subtitle Studio.pkg"
    package.write_text("pkg", encoding="utf-8")
    fakebin, log_path = _fake_macos_tools(tmp_path)
    env = _env(tmp_path, package)
    env["PATH"] = f"{fakebin}:{os.environ.get('PATH', '')}"

    result = subprocess.run(
        ["bash", str(SCRIPT), "validate"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "App Store Connect validate completed" in result.stdout
    args = log_path.read_text(encoding="utf-8")
    assert "--validate-app" in args
    assert "--upload-app" not in args


def test_upload_script_blocks_upload_without_explicit_confirmation(tmp_path):
    package = tmp_path / "AI Subtitle Studio.pkg"
    package.write_text("pkg", encoding="utf-8")
    _, log_path = _fake_macos_tools(tmp_path)
    env = _env(tmp_path, package)

    result = subprocess.run(
        ["bash", str(SCRIPT), "upload"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 64
    assert UPLOAD_CONFIRM_ENV in result.stderr
    assert not log_path.exists()


def test_upload_script_blocks_upload_without_readiness_json_even_when_confirmed(tmp_path):
    package = tmp_path / "AI Subtitle Studio.pkg"
    package.write_text("pkg", encoding="utf-8")
    _, log_path = _fake_macos_tools(tmp_path)
    env = _env(tmp_path, package)
    env[UPLOAD_CONFIRM_ENV] = "1"

    result = subprocess.run(
        ["bash", str(SCRIPT), "upload"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 64
    assert "APP_STORE_READINESS_JSON" in result.stderr
    assert not log_path.exists()


def test_upload_script_runs_upload_when_explicitly_confirmed(tmp_path):
    package = tmp_path / "AI Subtitle Studio.pkg"
    package.write_text("pkg", encoding="utf-8")
    fakebin, log_path = _fake_macos_tools(tmp_path)
    env = _env(tmp_path, package)
    env["PATH"] = f"{fakebin}:{os.environ.get('PATH', '')}"
    env[UPLOAD_CONFIRM_ENV] = "1"
    env["APP_STORE_READINESS_JSON"] = str(_ready_readiness_json(tmp_path, package))

    result = subprocess.run(
        ["bash", str(SCRIPT), "upload"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "App Store Connect upload completed" in result.stdout
    args = log_path.read_text(encoding="utf-8")
    assert "--upload-app" in args
    assert "--validate-app" not in args
