from tools.verify_full_media_pipeline import summary_metrics


def test_summary_metrics_exposes_top_level_quality_and_performance_fields():
    payload = {
        "result": {
            "elapsed_sec": 12.3,
            "raw_segments": 10,
            "final_segments": 11,
            "avg_stt_score": 77.7,
            "readability": {"readability_score": 99.1},
        },
        "self_review_summary": {"overall_score": 66.6},
        "completion_report": {"avg_quality_score": 75.5, "llm_rollback_count": 0},
        "variant_score": {"score": 74.4},
    }

    assert summary_metrics(payload) == {
        "pipeline_elapsed_sec": 12.3,
        "raw_segment_count": 10,
        "final_segment_count": 11,
        "avg_stt_score": 77.7,
        "self_review_overall_score": 66.6,
        "completion_avg_quality": 75.5,
        "llm_rollback_count": 0,
        "output_variant_score": 74.4,
        "readability_score": 99.1,
    }
