from __future__ import annotations

LORA_RETRIEVAL_INDEX_SCHEMA = "ai_subtitle_studio.lora_retrieval_index.v1"
LORA_RETRIEVAL_SCORE_MODEL = "hybrid_hash_vector_bm25_context_facet_v2"
LORA_RETRIEVAL_HASH_DIM = 768
LORA_RETRIEVAL_MAX_TEXT_CHARS = 2400
LORA_QUERY_CACHE_MAX = 96

SCORE_POINT_WEIGHTS = {
    "vector": 44.0,
    "bm25": 9.0,
    "bm25_cap": 24.0,
    "overlap": 8.0,
    "quality": 8.0,
    "recency_cap": 2.5,
}
FACET_POINT_WEIGHTS = {
    "scene": 4.0,
    "topic": 5.0,
    "mic_type": 2.0,
    "noise_level": 2.0,
}
LIST_FACET_POINT_WEIGHTS = {
    "noise_sources": (1.1, 3.3),
    "training_focus": (0.65, 2.6),
    "topic_terms": (0.35, 2.1),
}

INDEX_JSONL_SOURCE_KEYS = (
    "truth_table",
    "excluded_parentheticals",
    "setting_trials",
    "prompt_trials",
    "voice_lora_bridge",
    "stt1_whisper_adapter_dataset",
    "text_lora_dataset",
    "text_lora_corpus",
    "audio_preset_lora",
    "multimodal_lora_context",
)
INDEX_JSON_SOURCE_KEYS = (
    "learned_split_rules",
    "learned_line_break_rules",
    "best_settings",
    "text_lora_manifest",
    "text_lora_corpus_manifest",
    "text_lora_training_plan",
    "voice_lora_profile_manifest",
    "voice_lora_training_plan",
    "voice_lora_dataset_manifest",
    "stt1_whisper_adapter_dataset_manifest",
    "stt1_whisper_adapter_training_plan",
    "stt1_whisper_adapter_runtime_manifest",
)
RUNTIME_SETTING_KEYS = {
    "selected_audio_ai",
    "selected_whisper_model",
    "stt_ensemble_enabled",
    "stt_quality_preset",
    "subtitle_quality_enabled",
    "subtitle_quality_auto_check_after_generate",
    "subtitle_quality_auto_correct_enabled",
    "continuous_threshold",
    "gap_push_rate",
    "single_subtitle_end",
    "split_length_threshold",
    "sub_min_duration",
    "sub_max_duration",
    "sub_max_cps",
    "sub_dedup_window",
    "sub_gap_break_sec",
    "selected_model",
    "selected_llm_provider",
    "roughcut_llm_model",
    "roughcut_llm_provider",
}
