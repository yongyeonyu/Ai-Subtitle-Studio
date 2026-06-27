from tools.evaluate_reference_benchmark_acceptance import evaluate_reference_benchmark_acceptance


def _payload(
    *,
    quality=80.0,
    text=90.0,
    timing=1.0,
    overlap=0,
    final_stable=True,
    global_active=1,
    last_end=10.0,
    min_duration=1.0,
    max_duration=3.0,
    short_count=0,
    long_count=0,
):
    return {
        "start_sec": 0.0,
        "duration_sec": 10.0,
        "ranked_results": [
            {
                "name": "mode_high",
                "elapsed_sec": 10.0,
                "raw_segments": 12,
                "final_segments": 10,
                "quality": {
                    "reference_segments": 11,
                    "quality_score": quality,
                    "text_score": text,
                    "timing_mae_sec": timing,
                },
                "native_segments_summary": {
                    "invalid_duration_count": 0,
                    "non_monotonic_count": 0,
                    "overlap_count": overlap,
                    "stable_for_save_reopen": final_stable,
                    "segment_count": 10,
                    "last_end": last_end,
                    "min_segment_duration_sec": min_duration,
                    "max_segment_duration_sec": max_duration,
                    "short_segment_count": short_count,
                    "long_segment_count": long_count,
                },
                "native_global_canvas_summary": {
                    "max_active_segments": global_active,
                    "stable_for_global_canvas": True,
                },
            }
        ]
    }


def test_reference_benchmark_acceptance_accepts_stable_reference_result():
    report = evaluate_reference_benchmark_acceptance(_payload(), duration_bound_sec=10.0)

    assert report["accepted"] is True
    assert report["reasons"] == []


def test_reference_benchmark_acceptance_rejects_semantic_mismatch():
    report = evaluate_reference_benchmark_acceptance(_payload(quality=23.0, text=5.0, timing=3.3))

    assert report["accepted"] is False
    assert "quality_score_below_floor" in report["reasons"]
    assert "text_score_below_floor" in report["reasons"]
    assert "timing_mae_above_ceiling" in report["reasons"]


def test_reference_benchmark_acceptance_rejects_final_overlap():
    report = evaluate_reference_benchmark_acceptance(_payload(overlap=1))

    assert report["accepted"] is False
    assert "final_overlap_nonzero" in report["reasons"]


def test_reference_benchmark_acceptance_rejects_last_end_beyond_duration_bound():
    report = evaluate_reference_benchmark_acceptance(
        _payload(last_end=182.032),
        duration_bound_sec=180.584,
    )

    assert report["accepted"] is False
    assert "final_last_end_beyond_duration_bound" in report["reasons"]


def test_reference_benchmark_acceptance_rejects_short_and_long_tail_segments():
    report = evaluate_reference_benchmark_acceptance(
        _payload(min_duration=0.05, max_duration=59.792, short_count=16, long_count=1),
        duration_bound_sec=180.584,
    )

    assert report["accepted"] is False
    assert "final_min_segment_duration_below_floor" in report["reasons"]
    assert "final_short_segment_count_nonzero" in report["reasons"]
    assert "final_max_segment_duration_above_ceiling" in report["reasons"]
    assert "final_long_segment_count_nonzero" in report["reasons"]
