from pathlib import Path

import pytest

from core.project.nle_project_state import (
    NLE_PROJECT_STATE_RUNTIME_KEY,
    assert_nle_media_relink_parity,
    build_project_nle_state,
)
from core.project.project_context import build_editor_state
from core.project.project_io import read_project_storage_payload, write_project_file
from tools.audit_nle_relink_parity import (
    build_nle_relink_parity_report,
    write_nle_relink_parity_report,
)


def _project(media_path: Path, *, timeline_media_path: Path | None = None) -> dict:
    timeline_path = timeline_media_path or media_path
    return {
        "project_name": "nle_relink_parity",
        "mode": "single",
        "video": {"duration_sec": 6.0, "primary_fps": 30.0},
        "timeline": {
            "total_duration": 6.0,
            "timebase": {"primary_fps": 30.0},
            "tracks": [
                {
                    "clips": [
                        {
                            "id": "clip_main",
                            "source_path": str(timeline_path),
                            "type": "video",
                            "source_duration": 6.0,
                            "timeline_start": 0.0,
                            "timeline_end": 6.0,
                            "fps": 30.0,
                            "order": 0,
                        }
                    ]
                }
            ],
        },
        "editor_state": build_editor_state(
            mode="single",
            media_files=[str(media_path)],
            segments=[
                {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "first"},
                {"id": "caption_2", "start": 3.0, "end": 4.0, "text": "second"},
            ],
            primary_fps=30.0,
            preserve_segment_identity=True,
        ),
    }


def test_nle_relink_parity_accepts_updated_project_and_runtime_state(tmp_path: Path):
    relinked = tmp_path / "relinked.mov"
    relinked.write_bytes(b"media")
    project = _project(relinked)
    state = build_project_nle_state(project, project_path=str(tmp_path / "case.aissproj"))

    signature = assert_nle_media_relink_parity(project, state, project_path=str(tmp_path / "case.aissproj"))

    assert signature["project_media_paths"] == [str(relinked)]
    assert signature["nle_clip_paths"] == [str(relinked)]
    assert signature["nle_unique_asset_paths"] == [str(relinked)]
    assert signature["project_primary_fps"] == 30.0
    assert signature["runtime_primary_fps"] == 30.0
    assert signature["sequence_duration"] == 6.0
    assert signature["operation_journal_count"] == 0


def test_nle_relink_parity_rejects_editor_timeline_path_drift(tmp_path: Path):
    original = tmp_path / "original.mov"
    relinked = tmp_path / "relinked.mov"
    original.write_bytes(b"old")
    relinked.write_bytes(b"new")
    project = _project(relinked, timeline_media_path=original)
    state = build_project_nle_state(project, project_path=str(tmp_path / "case.aissproj"))

    with pytest.raises(ValueError, match="nle_media_path_order_drift:0"):
        assert_nle_media_relink_parity(project, state, project_path=str(tmp_path / "case.aissproj"))


def test_nle_relink_parity_rejects_runtime_fps_drift(tmp_path: Path):
    media = tmp_path / "source.mov"
    media.write_bytes(b"media")
    project = _project(media)
    state = build_project_nle_state(project, project_path=str(tmp_path / "case.aissproj"))
    state.primary_fps = 24.0

    with pytest.raises(ValueError, match="nle_runtime_fps_drift"):
        assert_nle_media_relink_parity(project, state, project_path=str(tmp_path / "case.aissproj"))


def test_nle_relink_parity_keeps_runtime_state_out_of_storage(tmp_path: Path):
    media = tmp_path / "source.mov"
    project_path = tmp_path / "case.aissproj"
    media.write_bytes(b"media")
    project = _project(media)
    project[NLE_PROJECT_STATE_RUNTIME_KEY] = build_project_nle_state(project, project_path=str(project_path))

    write_project_file(str(project_path), project)
    storage = read_project_storage_payload(str(project_path))

    assert NLE_PROJECT_STATE_RUNTIME_KEY not in storage
    assert "nle" not in storage
    assert "nle_snapshot" not in storage


def test_nle_relink_parity_audit_ready(tmp_path: Path):
    report = build_nle_relink_parity_report()

    assert report["ready"] is True
    assert report["runtime_change_applied"] is False
    assert report["relink_parity_helper_present"] is True
    assert report["runtime_check"]["relink_parity_consistent"] is True
    assert report["runtime_check"]["path_drift_rejected"] is True
    assert report["storage_check"]["storage_forbidden_key_count"] == 0
    assert report["persisted_nle_fields_changed"] is False

    json_path, markdown_path = write_nle_relink_parity_report(tmp_path, report)
    assert json_path.exists()
    assert markdown_path.exists()
    assert "NLE Relink Parity Audit" in markdown_path.read_text(encoding="utf-8")
