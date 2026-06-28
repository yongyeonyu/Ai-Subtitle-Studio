from pathlib import Path

import pytest

from core.project.nle_project_state import (
    assert_nle_active_selection_consistent,
    nle_active_selection_signature,
)
from tools.audit_nle_selection_sync_validation import (
    build_nle_selection_sync_validation_report,
    write_nle_selection_sync_validation_report,
)


def _rows() -> list[dict]:
    return [
        {
            "id": "caption_0001",
            "start": 0.0,
            "end": 2.0,
            "start_frame": 0,
            "end_frame": 60,
            "text": "first",
        },
        {
            "id": "caption_0002",
            "start": 2.0,
            "end": 4.0,
            "start_frame": 60,
            "end_frame": 120,
            "text": "second",
        },
    ]


def test_active_selection_signature_prefers_exact_segment_start_at_shared_boundary():
    signature = nle_active_selection_signature(_rows(), active_sec=2.0, primary_fps=30.0)

    assert signature["id"] == "caption_0002"
    assert signature["row_index"] == 1
    assert signature["active_frame"] == 60
    assert signature["start_frame"] == 60


def test_active_selection_consistency_rejects_runtime_nle_id_drift():
    nle_rows = _rows()
    nle_rows[1] = {**nle_rows[1], "id": "caption_wrong"}

    with pytest.raises(ValueError, match="nle_active_selection_id_drift"):
        assert_nle_active_selection_consistent(
            _rows(),
            nle_rows,
            active_sec=2.0,
            primary_fps=30.0,
        )


def test_nle_selection_sync_validation_audit_ready(tmp_path: Path):
    report = build_nle_selection_sync_validation_report()

    assert report["ready"] is True
    assert report["active_boundary_policy"] == "exact_start_frame_wins_at_shared_boundary"
    assert report["runtime_check"]["editor_active_signature"]["id"] == "caption_0002"
    assert report["runtime_check"]["nle_active_signature"]["id"] == "caption_0002"
    assert report["runtime_check"]["active_selection_consistent"] is True
    assert report["runtime_check"]["operation_journal_count"] == 0
    assert report["storage_check"]["storage_forbidden_key_count"] == 0
    assert report["persisted_nle_fields_changed"] is False

    json_path, markdown_path = write_nle_selection_sync_validation_report(tmp_path, report)
    assert json_path.exists()
    assert markdown_path.exists()
    assert "NLE Selection Sync Validation Audit" in markdown_path.read_text(encoding="utf-8")
