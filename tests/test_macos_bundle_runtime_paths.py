from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


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
        cwd=Path(__file__).resolve().parents[1],
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
