from core.stt_mode.dictation_state import create_raw_dictation_segment


def test_manual_input_produces_raw_dictation_without_whisper():
    raw = create_raw_dictation_segment(
        {
            "id": "stt_segment_0001",
            "start_frame": 0,
            "end_frame": 30,
            "timeline_start_frame": 0,
            "timeline_end_frame": 30,
            "frame_rate": 30.0,
            "timeline_frame_rate": 30.0,
        },
        " 안녕하세요 ",
        input_provider="manual",
    )

    assert raw["source"] == "human_dictation"
    assert raw["text"] == "안녕하세요"
    assert raw["whisper_used"] is False
    assert raw["llm_used"] is False
    assert raw["status"] == "input_done"
    assert raw["start_frame"] == 0


def test_empty_input_marks_needs_review_by_default():
    raw = create_raw_dictation_segment({"id": "stt_segment_0002"}, "", input_provider="os_dictation")

    assert raw["status"] == "needs_review"
    assert raw["input_provider"] == "os_dictation"
