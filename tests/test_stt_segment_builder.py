from core.stt_mode.segment_builder import build_stt_work_segments


def test_cut_boundary_splits_work_segment_without_changing_frames():
    rows = build_stt_work_segments(
        [{"start": 0.0, "end": 10.0, "vad_sources": ["silero"], "vad_confidence": 0.5}],
        cut_boundaries=[{"time": 5.0}],
        fps=30,
    )

    assert len(rows) == 2
    assert rows[0]["end_frame"] == 150
    assert rows[1]["start_frame"] == 150


def test_long_segment_splits_into_manageable_parts():
    rows = build_stt_work_segments(
        [{"start": 0.0, "end": 12.0, "vad_sources": ["silero"], "vad_confidence": 0.5}],
        fps=30,
        settings={"stt_mode_max_work_segment_sec": 5.0, "stt_mode_target_work_segment_sec": 4.0},
    )

    assert len(rows) >= 3
    assert all((row["end_frame"] - row["start_frame"]) / 30 <= 5.1 for row in rows)


def test_playback_preroll_postroll_do_not_change_saved_range():
    rows = build_stt_work_segments(
        [{"start": 1.0, "end": 2.0}],
        fps=30,
        media_duration=3.0,
        settings={"stt_mode_playback_preroll_sec": 0.5, "stt_mode_playback_postroll_sec": 0.25},
    )

    assert rows[0]["start"] == 1.0
    assert rows[0]["end"] == 2.0
    assert rows[0]["playback"]["start"] == 0.5
    assert rows[0]["playback"]["end"] == 2.25
