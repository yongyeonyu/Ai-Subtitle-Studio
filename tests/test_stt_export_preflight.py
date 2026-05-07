from core.stt_mode.export_preflight import exportable_stt_segments, run_stt_export_preflight


def test_preflight_blocks_invalid_frame_range():
    result = run_stt_export_preflight(
        final_segments=[{"id": "bad", "text": "x", "start_frame": 10, "end_frame": 10}],
        fps=30,
    )

    assert result["status"] == "blocked"
    assert result["errors"][0]["code"] == "invalid_frame_range"


def test_exportable_segments_exclude_pending_and_empty_rows():
    rows = exportable_stt_segments(
        [
            {"text": "", "start_frame": 0, "end_frame": 1},
            {"text": "대기", "stt_pending": True, "start_frame": 1, "end_frame": 2},
            {"text": "완료", "start_frame": 2, "end_frame": 3},
        ]
    )

    assert [row["text"] for row in rows] == ["완료"]
