from core.mode_policy import resolve_mode_policy


def test_auto_modes_can_use_only_stt_vad_segment_model_by_default():
    policy = resolve_mode_policy({"simple_operation_mode": "auto"})

    assert policy["stt_vad_segment_model"]["apply_to_current_mode"] is True
    assert policy["stt_vad_segment_model"]["allowed_scope"] == "vad_boundary_selection"
    assert policy["stt_dictation_lora"]["apply_to_auto_modes"] is False


def test_stt_mode_keeps_dictation_lora_active_without_llm():
    policy = resolve_mode_policy({"simple_operation_mode": "stt"})

    assert policy["stt_dictation_lora"]["active"] is True
    assert policy["llm"]["subtitle_enabled"] is False
    assert policy["stt"]["automatic_whisper_pipeline"] is False
