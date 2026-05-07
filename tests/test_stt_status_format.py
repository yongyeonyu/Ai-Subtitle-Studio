from core.stt_mode.status import format_stt_status


def test_status_format_includes_progress_time_and_confidence():
    text = format_stt_status(
        state="ready_to_listen",
        completed_count=3,
        total_count=10,
        current_segment={"start": 12.0, "end": 15.5, "vad_confidence": 0.86, "vad_confidence_label": "high"},
    )

    assert "3/10" in text
    assert "12.00-15.50s" in text
    assert "VAD 0.86 high" in text
