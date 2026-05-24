from core.engine.subtitle_segments import (
    SUBTITLE_SEGMENTS_FACADE_SCHEMA,
    copy_segment_rows,
    infer_save_fps,
    prepare_save_reopen_segments,
)


def test_prepare_save_reopen_segments_applies_offset_before_frame_grid():
    rows = [{"start": 0.999, "end": 2.001, "text": "A", "timeline_frame_rate": 30.0}]

    def adjust(items):
        adjusted = [dict(item) for item in items]
        adjusted[0]["start"] += 1.0
        adjusted[0]["end"] += 1.0
        return adjusted

    prepared = prepare_save_reopen_segments(rows, apply_offset=True, adjust_timing_func=adjust)

    assert prepared.schema == SUBTITLE_SEGMENTS_FACADE_SCHEMA
    assert prepared.fps == 30.0
    assert prepared.source_segments[0]["start"] == 1.999
    assert prepared.prepared_segments[0]["start"] == 2.0
    assert prepared.prepared_segments[0]["end"] == 3.0


def test_prepare_save_reopen_segments_copies_rows_without_mutating_input():
    rows = [{"start": 0.0, "end": 1.0, "text": "A"}]

    prepared = prepare_save_reopen_segments(rows, apply_offset=False)
    prepared.source_segments[0]["text"] = "B"
    prepared.prepared_segments[0]["text"] = "C"

    assert rows[0]["text"] == "A"
    assert prepared.fps is None


def test_infer_save_fps_prefers_explicit_fps_then_segment_metadata():
    rows = [{"start": 0.0, "end": 1.0, "text": "A", "frame_range": {"timeline_frame_rate": 29.97}}]

    assert infer_save_fps(rows, 30.0) == 30.0
    assert infer_save_fps(rows, None) == 29.97


def test_copy_segment_rows_filters_non_dict_rows():
    row = {"text": "A"}
    copied = copy_segment_rows([row, None, ["bad"]])

    assert copied == [row]
    assert copied[0] is not row
