from core.stt_mode.finalizer import resegment_raw_dictation_window


def test_long_raw_text_splits_into_final_subtitles_without_llm():
    raw = [
        {
            "id": "dictation_raw_0001",
            "text": "오늘은 제가 이 차를 타고 강릉까지 가면서 승차감과 서스펜션을 자세히 확인해보겠습니다",
            "start_frame": 0,
            "end_frame": 210,
            "timeline_start_frame": 0,
            "timeline_end_frame": 210,
            "frame_rate": 30.0,
            "timeline_frame_rate": 30.0,
        }
    ]
    out = resegment_raw_dictation_window(
        rolling_window={
            "id": "stt_window_0001_0001",
            "text": raw[0]["text"],
            "start_frame": 0,
            "end_frame": 210,
            "timeline_start_frame": 0,
            "timeline_end_frame": 210,
        },
        raw_segments=raw,
        fps=30,
        settings={"stt_mode_target_chars_per_line": 8},
    )

    assert len(out) >= 2
    assert all(row["llm_used"] is False for row in out)
    assert out[0]["start_frame"] == 0
    assert out[-1]["end_frame"] == 210


def test_protected_term_is_not_split_across_lines():
    out = resegment_raw_dictation_window(
        rolling_window={
            "id": "stt_window_0001_0001",
            "text": "서스펜션 성능을 확인합니다",
            "start_frame": 0,
            "end_frame": 90,
            "timeline_start_frame": 0,
            "timeline_end_frame": 90,
        },
        raw_segments=[],
        fps=30,
        settings={"protected_terms": ["서스펜션"], "stt_mode_target_chars_per_line": 4},
    )

    assert "서스펜션" in "\n".join(row["text"] for row in out)
