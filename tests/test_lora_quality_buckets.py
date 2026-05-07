from core.personalization.lora_quality_buckets import (
    LORA_BUCKET_HIGH,
    LORA_BUCKET_MEDIUM,
    annotate_lora_row_quality,
    lora_bucket_for_row,
)


def test_explicit_score_must_be_very_high_to_enter_high_bucket():
    medium_row = {
        "media_id": "trial-medium",
        "config": {"candidate": "medium"},
        "status": "complete",
        "score": 92.0,
        "reason": "usable but not top-tier",
    }
    high_row = {
        "media_id": "trial-high",
        "config": {"candidate": "high"},
        "status": "complete",
        "score": 97.0,
        "reason": "strong candidate",
        "usage_count": 2,
    }

    assert lora_bucket_for_row("setting_trials", medium_row) == LORA_BUCKET_MEDIUM
    assert lora_bucket_for_row("setting_trials", high_row) == LORA_BUCKET_HIGH


def test_default_scored_rows_need_pattern_signal_before_becoming_high():
    weak_truth = {
        "media_id": "truth-weak",
        "speech_training_text": "짧은 예시",
        "status": "complete",
    }
    strong_truth = {
        "media_id": "truth-strong",
        "speech_training_text": "강한 패턴 예시",
        "status": "reviewed",
        "line_break_pattern": "7|7",
        "punctuation_pattern": "statement",
        "detected_split_rule": "spoken_pause",
        "style_profile": {"tone": "netflix"},
        "usage_count": 3,
    }

    weak_bucket = annotate_lora_row_quality("truth_table", weak_truth)
    strong_bucket = annotate_lora_row_quality("truth_table", strong_truth)

    assert weak_bucket["lora_quality_bucket"] == LORA_BUCKET_MEDIUM
    assert strong_bucket["lora_quality_bucket"] == LORA_BUCKET_HIGH
