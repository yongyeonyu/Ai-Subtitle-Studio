from __future__ import annotations

from types import SimpleNamespace

from core.engine.subtitle_live_sync_manager import (
    SUBTITLE_LIVE_SYNC_PROGRESS_SCHEMA,
    SUBTITLE_LIVE_SYNC_TOPICLESS_SCHEMA,
    build_cut_boundary_topicless_live_sync_payload,
    build_subtitle_live_sync_progress,
    normalize_live_processing_stage_text,
    subtitle_live_sync_status_is_final,
)
from ui.editor.editor_pipeline_status import EditorPipelineStatusMixin


class _ProgressHarness(EditorPipelineStatusMixin):
    def __init__(self, *, total_time=0.0, segments=None):
        self.video_player = SimpleNamespace(total_time=total_time)
        self._segments = list(segments or [])

    def _get_current_segments(self):
        return list(self._segments)


def test_live_sync_progress_prefers_segment_time_over_chunk_count():
    progress = build_subtitle_live_sync_progress(
        1,
        10,
        current_segment_end=25.0,
        total_duration=100.0,
    )

    payload = progress.to_dict()
    assert payload["schema"] == SUBTITLE_LIVE_SYNC_PROGRESS_SCHEMA
    assert payload["percent"] == 25
    assert payload["source"] == "segment_time"


def test_live_sync_progress_falls_back_to_chunk_count():
    progress = build_subtitle_live_sync_progress(3, 6)

    assert progress.percent == 50
    assert progress.source == "chunk_count"


def test_editor_progress_percent_uses_live_sync_facade():
    harness = _ProgressHarness(total_time=120.0, segments=[{"start": 0.0, "end": 30.0}])

    assert harness._pipeline_progress_percent(1, 10) == 25


def test_live_sync_status_text_helpers_match_editor_contract():
    assert normalize_live_processing_stage_text("  처리 중  ") == "처리 중"
    assert subtitle_live_sync_status_is_final("에러 발생") is True
    assert subtitle_live_sync_status_is_final("계속 처리 중") is False
    assert _ProgressHarness()._is_final_status_message("실패", is_raw=True) is True


def test_topicless_live_sync_payload_preserves_rows_and_result_shape():
    rows = [{"start": 1.0, "end": 2.0, "text": "중분류"}]
    payload = build_cut_boundary_topicless_live_sync_payload(rows, source="unit")
    rows[0]["text"] = "mutated"

    data = payload.to_dict()
    assert data["schema"] == SUBTITLE_LIVE_SYNC_TOPICLESS_SCHEMA
    assert data["rows"][0]["text"] == "중분류"
    assert data["roughcut_result"]["segments"][0]["text"] == "중분류"
    assert data["roughcut_result"]["schema_version"] == "roughcut_result.v2"
    assert data["roughcut_result"]["source"] == "cut_boundary_unit"
    assert data["counts"] == {"rows": 1, "has_roughcut_result": True}


def test_empty_topicless_live_sync_payload_has_no_roughcut_result():
    payload = build_cut_boundary_topicless_live_sync_payload([], source="")

    data = payload.to_dict()
    assert data["rows"] == []
    assert data["source"] == "stream"
    assert data["roughcut_result"] is None
