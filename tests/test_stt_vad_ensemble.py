from core.stt_mode.vad_ensemble import ensemble_vad_candidates


def test_overlapping_silero_ten_candidates_produce_high_confidence_segment():
    rows = ensemble_vad_candidates(
        [{"provider": "silero", "start": 1.0, "end": 3.0}],
        [{"provider": "ten_vad", "start": 1.1, "end": 2.9}],
        fps=30,
    )

    assert len(rows) == 1
    assert rows[0]["vad_confidence_label"] == "high"
    assert rows[0]["vad_decision"] == "weighted_consensus"
    assert rows[0]["vad_sources"] == ["silero", "ten_vad"]
    assert rows[0]["end_frame"] > rows[0]["start_frame"]


def test_one_provider_candidate_uses_fallback_metadata():
    rows = ensemble_vad_candidates(
        [{"provider": "silero", "start": 0.0, "end": 1.0}],
        [],
        fps=24,
    )

    assert len(rows) == 1
    assert rows[0]["vad_decision"] == "silero_only_fallback"
    assert rows[0]["timeline_frame_rate"] == 24.0
    assert rows[0]["stt_pending"] is True


def test_sorted_output_has_valid_ranges():
    rows = ensemble_vad_candidates(
        [
            {"provider": "silero", "start": 3.0, "end": 3.8},
            {"provider": "silero", "start": 1.0, "end": 1.8},
        ],
        [],
        fps=30,
    )

    assert [row["start_frame"] for row in rows] == sorted(row["start_frame"] for row in rows)
    assert all(row["end_frame"] > row["start_frame"] for row in rows)
