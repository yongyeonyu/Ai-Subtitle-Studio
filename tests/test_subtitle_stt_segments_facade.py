from core.engine.subtitle_stt_segments import (
    SUBTITLE_STT_SEGMENTS_FACADE_SCHEMA,
    normalize_stt_source_label,
    prepare_stt_preview_timeline_rows,
)
from core.pipeline.stt_preview_optimizer import raw_stt_preview_segments


def test_prepare_stt_preview_timeline_rows_shapes_stt2_feed_without_mutating_input():
    row = {"start": 1.0, "end": 1.02, "text": " 후보 ", "score": 0.91}

    prepared = prepare_stt_preview_timeline_rows(
        [row],
        source_label=" stt2 ",
        clip_offset=10.0,
        clip_idx=3,
        clip_path="/tmp/clip.mp4",
        optimized=True,
    )

    assert prepared.schema == SUBTITLE_STT_SEGMENTS_FACADE_SCHEMA
    assert prepared.source_label == "STT2"
    assert row["text"] == " 후보 "
    assert prepared.rows == [
        {
            "start": 11.0,
            "end": 11.05,
            "text": "후보",
            "score": 0.91,
            "stt_preview_source": "STT2",
            "stt_pending": True,
            "_live_stt_preview": True,
            "stt_preview_optimized": True,
            "stt_preview_optimizer": "subtitle_split_gap_rules",
            "_clip_idx": 3,
            "_clip_file": "/tmp/clip.mp4",
        }
    ]


def test_prepare_stt_preview_timeline_rows_filters_invalid_and_blank_rows():
    prepared = prepare_stt_preview_timeline_rows(
        [
            None,
            {"start": "bad", "end": 2.0, "text": "x"},
            {"start": 1.0, "end": 2.0, "text": "   "},
            {"start": 1.0, "end": 2.0, "text": "ok"},
        ],
        source_label="STT1",
    )

    assert [row["text"] for row in prepared.rows] == ["ok"]


def test_normalize_stt_source_label_defaults_to_stt1():
    assert normalize_stt_source_label(None) == "STT1"
    assert normalize_stt_source_label(" stt2 ") == "STT2"
    assert normalize_stt_source_label("") == "STT1"


def test_raw_stt_preview_segments_uses_facade_shape():
    rows = raw_stt_preview_segments(
        [{"start": 0.0, "end": 1.0, "text": "raw"}],
        source_label="stt2",
        clip_offset=2.0,
    )

    assert rows[0]["start"] == 2.0
    assert rows[0]["end"] == 3.0
    assert rows[0]["stt_preview_source"] == "STT2"
    assert rows[0]["stt_preview_optimized"] is False
    assert rows[0]["stt_preview_optimizer"] == "raw_realtime"
