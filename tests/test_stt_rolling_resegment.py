from core.stt_mode.rolling_resegment import apply_rolling_resegmentation, build_rolling_window


def _raw(idx, text, start, end):
    return {
        "id": f"dictation_raw_{idx:04d}",
        "text": text,
        "start_frame": start,
        "end_frame": end,
        "timeline_start_frame": start,
        "timeline_end_frame": end,
        "frame_rate": 30.0,
        "timeline_frame_rate": 30.0,
    }


def test_rolling_window_uses_previous_and_current_raw_dictation():
    rows = [_raw(1, "첫 문장", 0, 60), _raw(2, "둘째 문장", 60, 120)]
    window = build_rolling_window(rows, current_raw_id="dictation_raw_0002", window_size=2)

    assert window["raw_dictation_ids"] == ["dictation_raw_0001", "dictation_raw_0002"]
    assert window["start_frame"] == 0
    assert window["end_frame"] == 120


def test_manual_locked_final_segment_is_preserved():
    rows = [_raw(1, "첫 문장", 0, 60), _raw(2, "둘째 문장", 60, 120)]
    locked = {"id": "locked", "text": "사용자 수정", "start_frame": 0, "end_frame": 60, "timeline_start_frame": 0, "timeline_end_frame": 60, "locked": True}
    result = apply_rolling_resegmentation(raw_segments=rows, final_segments=[locked], current_raw_id="dictation_raw_0002", fps=30)

    assert any(row["id"] == "locked" for row in result["final_segments"])
    assert result["generated_segments"]
