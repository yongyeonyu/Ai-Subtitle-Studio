from unittest.mock import patch

from core.engine.subtitle_global_canvas import (
    SUBTITLE_GLOBAL_CANVAS_FACADE_SCHEMA,
    global_canvas_merge_gap_sec,
    global_canvas_minimap_rows,
    global_canvas_silence_rows,
    merged_global_canvas_minimap_segments,
    merged_global_canvas_silence_segments,
    subtitle_global_canvas_lane_for_segment,
)


def test_global_canvas_lane_for_segment_preserves_stt1_stt2_and_final_lanes():
    assert subtitle_global_canvas_lane_for_segment({"text": "final"}) == "SUBTITLE"
    assert subtitle_global_canvas_lane_for_segment(
        {"stt_pending": True, "stt_preview_source": "STT1"}
    ) == "STT1"
    assert subtitle_global_canvas_lane_for_segment(
        {"_live_stt_preview": True, "stt_preview_source": "STT2"}
    ) == "STT2"


def test_global_canvas_minimap_rows_filters_lanes_and_normalizes_text():
    rows = global_canvas_minimap_rows(
        [
            {"start": -1.0, "end": 1.0, "text": " final "},
            {"start": 2.0, "end": 3.0, "text": "stt", "stt_pending": True, "stt_preview_source": "STT2"},
            {"start": "bad", "end": 4.0, "text": "drop"},
        ],
        lanes=("SUBTITLE",),
    )

    assert rows == [{"start": 0.0, "end": 1.0, "lane": "SUBTITLE", "text": "final"}]


def test_merged_global_canvas_minimap_segments_uses_pixel_gap_without_ui_widget():
    with patch("core.native_subtitle_global_canvas.native_subtitle_global_canvas_enabled", return_value=False):
        merged = merged_global_canvas_minimap_segments(
            [
                {"start": 1.0, "end": 1.2, "text": "앞"},
                {"start": 1.24, "end": 1.4, "text": "뒤"},
                {"start": 3.0, "end": 3.5, "text": "후보", "stt_pending": True, "stt_preview_source": "STT2"},
            ],
            width=420,
            total=10.0,
            lanes=("SUBTITLE",),
            output_lane="SUBTITLE",
            merge_gap_px=4,
        )

    assert global_canvas_merge_gap_sec(420, 10.0, merge_gap_px=4) == 4 * 10.0 / 420
    assert len(merged) == 1
    assert merged[0]["start"] == 1.0
    assert merged[0]["end"] == 1.4
    assert merged[0]["lane"] == "SUBTITLE"
    assert merged[0]["text"] == "앞 뒤"


def test_merged_global_canvas_silence_segments_keeps_textless_rows():
    with patch("core.native_subtitle_global_canvas.native_subtitle_global_canvas_enabled", return_value=False):
        merged = merged_global_canvas_silence_segments(
            [
                {"start": 0.0, "end": 1.0, "text": "ignored"},
                {"start": 1.02, "end": 2.0, "text": "ignored"},
                {"start": 3.0, "end": 3.0, "text": "drop"},
            ],
            width=100,
            total=10.0,
            merge_gap_px=1,
        )

    assert SUBTITLE_GLOBAL_CANVAS_FACADE_SCHEMA.endswith(".v1")
    assert global_canvas_silence_rows([{"start": 3.0, "end": 3.0}]) == []
    assert merged == [{"start": 0.0, "end": 2.0, "lane": "SILENCE", "count": 2}]
