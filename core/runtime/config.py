# Version: 04.00.16
# Phase: SOURCE_APP_CONTINUATION_V4_0_16_RELEASE


# === OS / Platform Detection ===
import os
import platform
from pathlib import Path

from dotenv import load_dotenv

OS_NAME = platform.system()          # "Darwin", "Windows", "Linux"
IS_MAC = OS_NAME == "Darwin"
IS_WINDOWS = OS_NAME == "Windows"
IS_LINUX = OS_NAME == "Linux"
APP_VERSION = "04.00.16"
MACBOOK_ONLY_APP = True
SUPPORTED_OS_NAMES = ("Darwin",)
APP_STORE_TARGET = True

# CPU / Apple Silicon
MACHINE = platform.machine()         # "arm64", "x86_64"
IS_APPLE_SILICON = IS_MAC and MACHINE == "arm64"

# .env 파일 로드
load_dotenv()

# ── 🏷️ 앱 기본 정보 ──
APP_NAME      = "AI Subtitle Studio"
INSTANCE_PORT = 47291

# ── 📂 주요 폴더 경로 설정 ──
BASE_DIR    = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BUNDLE_RESOURCES_DIR = os.environ.get("AI_SUBTITLE_STUDIO_BUNDLE_RESOURCES", "")
RUNNING_IN_APP_BUNDLE = bool(BUNDLE_RESOURCES_DIR)


def _default_user_data_dir() -> str:
    override = os.environ.get("AI_SUBTITLE_STUDIO_USER_DATA_DIR", "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if IS_MAC:
        return str(Path.home() / "Library" / "Application Support" / "AI Subtitle Studio")
    return os.path.join(BASE_DIR, ".local_app_data")


USER_DATA_DIR = _default_user_data_dir()
RUNTIME_BASE_DIR = USER_DATA_DIR if RUNNING_IN_APP_BUNDLE else BASE_DIR
DATASET_DIR = os.path.join(RUNTIME_BASE_DIR, "dataset")
OUTPUT_DIR  = os.path.join(RUNTIME_BASE_DIR, "output")
VOICE_DATA_DIR = os.path.join(RUNTIME_BASE_DIR, "voice_data")
PROJECTS_DIR = os.path.join(RUNTIME_BASE_DIR, "projects")
BUNDLED_DATASET_DIR = os.path.join(BASE_DIR, "dataset")

CORRECTIONS_DIR  = DATASET_DIR              # 호환용 alias
CORRECTIONS_FILE = os.path.join(DATASET_DIR, "dataset_correction.json")
RULES_FILE       = os.path.join(DATASET_DIR, "subtitle_rule.json")

# iCloud 드롭존
# ✅ 수정: 폴더명 분리 → 나중에 사용자 설정으로 이동 가능
ICLOUD_FOLDER_NAME = "AI_EDIT"
ICLOUD_DROPZONE    = os.path.expanduser(
    f"~/Library/Mobile Documents/com~apple~CloudDocs/{ICLOUD_FOLDER_NAME}"
)

# ── 🎙️ Whisper 및 오디오 설정 ──
WHISPERKIT_QUALITY_MODEL = "whisperkit-persistent:large-v3-v20240930_626MB"
WHISPERKIT_FAST_MODEL = "whisperkit-persistent:large-v3-v20240930_turbo_632MB"
MLX_FALLBACK_MODEL = "mlx-community/whisper-large-v3-turbo"
WHISPER_MODEL = WHISPERKIT_QUALITY_MODEL
LANGUAGE       = "ko"
TIME_OFFSET    = 0.2

# ✅ 수정: 하드코딩 경로 제거 → folder_settings.json에서 관리
DEFAULT_FOLDER = ""

# ── 🤖 AI 엔진 및 프롬프트 설정 ──
OLLAMA_MODEL = "exaone3.5:7.8b"

DEFAULT_LLM_PROMPT = (
    "너는 한국어 유튜브 자막 QA 편집자다.\n"
    "원문에 없는 말은 절대 추가하지 말고, 단어·순서·말투·의미를 보존한다.\n"
    "LoRA/ground truth 컨텍스트가 있으면 사용자 프롬프트보다 우선 적용한다.\n"
    "작업은 오탈자 최소 교정, 자연스러운 줄바꿈, 읽기 쉬운 호흡 정리뿐이다.\n"
    "출력은 요청된 JSON 형식만 반환한다.\n\n"
)

# ── ⚙️ 고급 상세 설정 ──
DEFAULT_ADV_SETTINGS = {
    "use_basic_filter": True,
    "none_hp":          200,
    "none_lp":          3000,
    "none_nf":          -25,
    "none_target":      -14,
    "none_comp_th":     -28,
    "none_vol":         4.0,
    "df_hp":            100,
    "df_eq_g":          8,
    "df_comp_th":       -28,
    "df_vol":           3.5,
    "w_df_no_speech":   0.4,
    "w_df_logprob":     -2.5,
    "w_df_comp":        2.4,
    "w_df_temp_max":    0.8,
    "w_none_no_speech": 0.85,
    "w_none_logprob":   -1.0,
    "w_none_comp":      1.6,
    "w_none_temp_max":  0.4,
    "split_length_threshold": 20,
    "subtitle_lora_split_floor_enabled": True,
    "subtitle_lora_split_floor_chars": 20,
    "subtitle_common_split_guard_enabled": True,
    "subtitle_common_split_target_chars": 20,
    "subtitle_common_split_hard_max_chars": 32,
    "subtitle_common_split_hard_max_duration_sec": 5.5,
    "subtitle_llm_prev_next_context_enabled": True,
    "subtitle_llm_context_candidate_limit": 5,
    "subtitle_llm_context_min_current_similarity": 0.86,
    "subtitle_llm_context_neighbor_reject_margin": 0.06,
    "subtitle_llm_context_boundary_refine_enabled": False,
    "subtitle_llm_context_word_correction_enabled": True,
    "subtitle_llm_context_max_pairs": 8,
    "subtitle_llm_context_require_risk_signal": True,
    "subtitle_llm_context_max_pair_gap_sec": 0.85,
    "subtitle_llm_context_min_pair_chars": 6,
    "subtitle_llm_context_max_pair_chars": 58,
    "subtitle_llm_context_allow_merge": True,
    "subtitle_llm_context_merge_max_chars": 32,
    "subtitle_llm_context_merge_micro_max_chars": 4,
    "subtitle_llm_context_merge_micro_max_duration_sec": 0.55,
    "subtitle_llm_context_max_word_corrections": 2,
    "subtitle_llm_context_timeout_sec": 45.0,
    "subtitle_llm_context_num_predict": 180,
    "llm_threads_auto_enabled": True,
    "llm_workers_auto_enabled": True,
    "runtime_hardware_acceleration_enabled": True,
    "apple_m_pipeline_parallel_enabled": True,
    "apple_m_chip_aware_scheduler_enabled": True,
    "apple_m_pipeline_respect_manual_worker_settings": False,
    "runtime_performance_profile": "max",
    "runtime_native_threads_auto_enabled": True,
    "runtime_native_threads": 8,
    "runtime_backend_autotune_enabled": True,
    "runtime_scheduler_auto_enabled": True,
    "stt_workers_auto_enabled": True,
    "cut_pioneer_workers_auto_enabled": True,
    "cut_follower_workers_auto_enabled": True,
    "lora_workers_auto_enabled": True,
    "stt_backend_policy": "native",
    "vad_backend_policy": "auto",
    "native_swift_vad_segments_enabled": True,
    "stt_apple_speech_challenger_enabled": False,
    "stt_apple_speech_vad_coupled_enabled": False,
    "stt_apple_speech_locale": "ko-KR",
    "stt_apple_speech_benchmark_only": True,
    "cut_boundary_backend_policy": "native",
    "audio_extract_backend_policy": "native",
    "llm_backend_policy": "auto",
    "editor_render_backend_policy": "native",
    "whisperkit_native_auto_enabled": True,
    "ffmpeg_videotoolbox_decode_enabled": True,
    "macos_native_fast_audio_flatten_enabled": True,
    "macos_native_fast_audio_flatten_hp": 150,
    "macos_native_fast_audio_flatten_lp": 4600,
    "macos_native_fast_audio_flatten_comp_th": -24,
    "macos_native_fast_audio_flatten_volume": 3.2,
    "macos_native_fast_audio_flatten_limiter": 0.93,
    "macos_native_app_store_target_enabled": True,
    "macos_native_require_xcode_tools": True,
    "runtime_scheduler_ramp_up_enabled": True,
    "runtime_scheduler_ramp_initial_sec": 45.0,
    "runtime_scheduler_ramp_step_sec": 60.0,
    "runtime_scheduler_reserve_cores": 0,
    "runtime_memory_monitor_interval_ms": 15000,
    "runtime_memory_disk_cache_budget_gb": 12.0,
    "runtime_memory_tracemalloc_enabled": False,
    "runtime_memory_tracemalloc_frames": 8,
    "macos_native_memory_snapshot_enabled": True,
    "macos_allocator_pressure_relief_enabled": True,
    "macos_allocator_pressure_relief_warning_mb": 64,
    "macos_allocator_pressure_relief_critical_mb": 256,
    "subtitle_generation_memory_guard_enabled": True,
    "subtitle_generation_memory_checkpoint_interval_ms": 3000,
    "subtitle_generation_gpu_trim_cooldown_sec": 8.0,
    "runtime_memory_warning_ratio": 0.20,
    "runtime_memory_critical_ratio": 0.12,
    "runtime_memory_warning_trim_cooldown_sec": 12.0,
    "runtime_memory_critical_trim_cooldown_sec": 6.0,
    "runtime_memory_warning_disk_trim_ratio": 0.72,
    "runtime_memory_critical_disk_trim_ratio": 0.45,
    "macos_memory_warning_reserve_gb": 3.0,
    "macos_memory_critical_reserve_gb": 1.5,
    "macos_memory_compressed_warning_ratio": 0.22,
    "macos_memory_compressed_critical_ratio": 0.30,
    "macos_memory_trim_runtime_caches_enabled": True,
    "macos_memory_cache_prune_enabled": True,
    "autopilot_enabled": True,
    "autopilot_single_user_mode": True,
    "operation_mode_choices_visible": False,
    "autopilot_internal_lanes_enabled": True,
    "autopilot_speaker_preflight_enabled": True,
    "autopilot_stage_prewarm_enabled": True,
    "autopilot_stage_prewarm_start_progress": 0.72,
    "autopilot_progress_events_enabled": True,
    "cut_boundary_policy_mode": "hybrid",
    "cut_boundary_user_level_visible": False,
    "cut_boundary_hybrid_enabled": True,
    "cut_boundary_hybrid_fast_level": "low",
    "cut_boundary_hybrid_escalate_level": "medium",
    "playhead_auto_cut_magnet_enabled": True,
    "playhead_auto_cut_magnet_strict_verify_enabled": True,
    "playhead_auto_cut_magnet_strict_multiplier": 1.22,
    "playhead_auto_cut_magnet_verify_window_sec": 0.42,
    "cut_boundary_audio_provisional_color": "#39FF14",
    "autopilot_cache_enabled": True,
    "autopilot_stage_cache_enabled": True,
    "autopilot_negative_cache_enabled": True,
    "autopilot_compressed_diagnostics_enabled": True,
    "cut_boundary_cache_enabled": True,
    "scan_cut_compare_max_width": 1920,
    "scan_cut_compare_max_height": 1080,
    # BENCH LOCK 2026-05-09 (Apple M5, X5_시승기_후반.MP4 4K HEVC):
    # Cut-boundary search is fastest and stable with pioneer=4 and follower
    # CPU 4-way outer split. Do not change without rerunning the full matrix.
    "scan_cut_pioneer_workers": 4,
    "scan_cut_verify_workers": 4,
    "scan_cut_pioneer_cpu_max_workers": 4,
    "scan_cut_follower_cpu_max_workers": 4,
    "scan_cut_follower_outer_splits": 4,
    "scan_cut_pioneer_worker_overlap_steps": 1,
    "scan_cut_cv2_threads_per_worker": 1,
    "scan_cut_cv2_video_backend": "avfoundation",
    "scan_cut_provisional_sample_step_sec": 2.0,
    "scan_cut_long4k_provisional_sample_step_sec": 4.0,
    "scan_cut_no_proxy_pioneer_max_samples": 180,
    "scan_cut_no_proxy_min_sample_step_sec": 8.0,
    "scan_cut_provisional_compare_max_width": 640,
    "scan_cut_provisional_compare_max_height": 360,
    "scan_cut_pioneer_packet_scout_enabled": True,
    "scan_cut_pioneer_packet_scout_timeout_sec": 60.0,
    "scan_cut_pioneer_packet_scout_raw_candidates": 180,
    "scan_cut_pioneer_packet_bucket_sec": 0.25,
    "scan_cut_pioneer_packet_min_gap_sec": 0.20,
    "scan_cut_pioneer_packet_delta_threshold": 1.4,
    "scan_cut_pioneer_packet_mad_multiplier": 3.0,
    "scan_cut_pioneer_pipe_enabled": False,
    "scan_cut_pioneer_pipe_hwaccel_enabled": True,
    "scan_cut_pioneer_pipe_fps": 1.0,
    "scan_cut_pioneer_pipe_width": 320,
    "scan_cut_pioneer_pipe_height": 180,
    "scan_cut_pioneer_pipe_dense_flow_enabled": True,
    "scan_cut_pioneer_pipe_flow_width": 160,
    "scan_cut_pioneer_pipe_pixel_threshold": 15.0,
    "scan_cut_pioneer_pipe_pixel_strong_threshold": 28.0,
    "scan_cut_pioneer_pipe_flow_residual_threshold": 10.0,
    "scan_cut_pioneer_pipe_timeout_sec": 120.0,
    "scan_cut_pioneer_pipe_max_candidates": 360,
    "scan_cut_pioneer_min_gap_sec": 0.45,
    "scan_cut_follower_visual_candidate_compact_gap_sec": 0.45,
    "scan_cut_follower_packet_candidate_compact_gap_sec": 0.20,
    "scan_cut_follower_scene_candidate_compact_gap_sec": 0.40,
    "scan_cut_pioneer_dense_flow_confirm_enabled": True,
    "scan_cut_pioneer_strict_multiplier": 0.72,
    "vad_detection_cache_enabled": True,
    # BENCH LOCK 2026-05-09: API LLM stays single-worker in runtime planning;
    # local 7B-class LLMs are resource-adaptive with a cap of 2 on this 16GB M5.
    "llm_workers":      4,
    "llm_threads_resource_max": 4,
    "local_ollama_llm_max_workers": 2,
    "subtitle_native_prepass_workers": 0,
    "subtitle_native_prepass_workers_resource_max": 0,
    "codex_subtitle_native_fast_path_enabled": True,
    "codex_subtitle_native_fast_path_min_segments": 80,
    "codex_subtitle_native_fast_path_long_text_llm_ratio": 2.8,
    "mac_native_acceleration_enabled": True,
    "native_cpp_llm_macro_groups_enabled": True,
    "native_swift_quality_scoring_enabled": True,
    "native_swift_quality_scoring_min_segments": 64,
    "native_swift_common_split_enabled": True,
    "native_swift_common_split_min_items": 1000,
    # BENCH LOCK 2026-05-09 (native policy benchmark, 80 rounds/2500 LoRA docs):
    # Python beat Swift worker for LLM candidates, Deep rerank, and LoRA scoring,
    # and Swift LoRA changed top-5 ranking. Keep these native policy paths off
    # until a rerun proves both speed and ranking parity.
    "native_swift_llm_candidate_policy_enabled": False,
    "native_swift_deep_policy_enabled": False,
    "native_swift_lora_scoring_enabled": False,
    "native_swift_lora_scoring_min_docs": 32,
    "sub_gap_break_sec":  1.5,
    "sub_min_duration":   0.2,
    "sub_max_cps":        12,
    "sub_dedup_window":   0.5,
    "accuracy_first_mode": True,
    "auto_start_mode": "balanced",
    "stt_quality_preset": "balanced",
    "stt_ensemble_enabled": False,
    "stt_ensemble_selective_enabled": False,
    "stt_ensemble_parallel_enabled": False,
    "stt_candidate_scoring_enabled": True,
    "stt_low_score_recheck_enabled": True,
    "stt_low_score_recheck_threshold": 72,
    "stt_low_score_recheck_padding_sec": 0.55,
    "stt_low_score_recheck_max_segments": 48,
    "stt_low_score_recheck_max_audio_sec": 160.0,
    "stt_low_score_recheck_min_improvement": 1.5,
    "stt_recheck_native_fast_audio_filter_enabled": True,
    "stt_persistent_runtime_reuse_enabled": True,
    # macOS native STT speed path: finish Swift/MLX STT1 first, then batch
    # low-score STT2 rescue and word-timestamp precision once instead of
    # pausing after every chunk.
    "stt_native_batch_refine_enabled": True,
    # BENCH LOCK 2026-05-09 (X5_시승기_후반.MP4 120.3s-180.3s, SRT reference):
    # STT1 keeps WhisperKit persistent quality: compact CER 1.083% beat
    # WhisperKit/MLX turbo at 1.805%. MLX turbo remains STT2/recheck for speed.
    "stt_primary_fast_native_enabled": False,
    "stt_primary_fast_native_model": WHISPERKIT_QUALITY_MODEL,
    "editor_live_stt_preview_follow_video_enabled": True,
    "editor_live_stt_preview_follow_interval_sec": 0.45,
    "stt_word_timestamps_mode": "selective",
    "stt_word_timestamps_default_enabled": False,
    "stt_word_timestamps_precision_enabled": True,
    "stt_word_timestamps_precision_threshold": 72.0,
    "stt_word_timestamps_precision_max_segments": 24,
    "stt_word_timestamps_precision_max_audio_sec": 90.0,
    "stt_word_timestamps_precision_keep_text": True,
    "stt_word_timestamps_precision_min_similarity": 0.18,
    "stt_word_timestamps_precision_max_timing_shift_sec": 0.55,
    "stt_word_timestamps_precision_min_duration_ratio": 0.45,
    "stt_word_timestamps_precision_max_duration_ratio": 1.8,
    "stt_worker_response_timeout_sec": 150.0,
    "stt_worker_word_timestamp_response_timeout_sec": 90.0,
    "stt_word_timestamp_worker_response_timeout_sec": 45.0,
    "stt_whisperkit_native_allocator_can_raise_workers": True,
    "stt_whisperkit_gpu_saturation_max_workers": 8,
    "stt_whisperkit_stream_results_enabled": True,
    "stt_whisperkit_native_compute_profile_enabled": True,
    "stt_whisperkit_compute_profile": "auto",
    "stt_missing_voice_min_duration_sec": 0.55,
    "selected_whisper_model_secondary": MLX_FALLBACK_MODEL,
    "stt_ensemble_llm_judge_enabled": False,
    "stt_ensemble_llm_judge_require_risk": True,
    "stt_ensemble_llm_judge_local_only": True,
    "stt_ensemble_llm_judge_low_score_threshold": 78.0,
    "stt_ensemble_llm_judge_min_score_delta": 10.0,
    "stt_ensemble_llm_judge_max_similarity": 0.94,
    "vad_post_stt_align_enabled": True,
    "vad_post_stt_max_shift_sec": 0.7,
    "vad_post_stt_edge_pad_sec": 0.04,
    "subtitle_quality_enabled": False,
    "subtitle_quality_auto_check_after_generate": True,
    "subtitle_quality_auto_correct_enabled": True,
    "editor_lora_runtime_enabled": True,
    "editor_truth_capture_enabled": True,
    "editor_truth_capture_min_chars": 2,
    "editor_truth_capture_max_chars": 240,
    "audio_chunk_routing_enabled": True,
    "audio_chunk_route_vad_enabled": True,
    "audio_chunk_route_max_workers": 4,
    "audio_chunk_profile_sec": 30.0,
    "direct_ffmpeg_chunk_min_sec": 1.0,
    "whisper_chunk_overlap_sec": 1.5,
    "chunk_time_limit": 240,
    "subtitle_bundle_autopilot_enabled": True,
    "subtitle_bundle_lora_enabled": True,
    "subtitle_bundle_lora_blend": 0.35,
    "subtitle_bundle_target_sec": 240,
    "subtitle_bundle_min_sec": 120,
    "subtitle_bundle_max_sec": 420,
    "subtitle_bundle_use_confirmed_cuts": True,
    "subtitle_bundle_use_provisional_cuts": True,
    "subtitle_bundle_confirmed_cut_min_sec": 45,
    "subtitle_bundle_provisional_cut_min_sec": 120,
    "subtitle_bundle_boundary_snap_window_sec": 1.0,
    "subtitle_cut_boundary_guard_enabled": True,
    "subtitle_cut_boundary_allow_high_confidence_crossing": False,
    "subtitle_cut_boundary_high_confidence_score": 96.0,
    "vad_pre_split_enabled": False,
    "review_vad_before_stt_enabled": True,
    "review_vad_strict_mode": True,
    "review_vad_speech_pad_sec": 0.35,
    "review_vad_min_silence_sec": 0.8,
    "review_min_segment_score_to_keep": 55,
    "review_auto_correct_apply_threshold": 94,
    "review_auto_correct_min_improvement": 8,
    "review_recheck_buffer_sec": 1.5,
    "review_auto_correct_require_user_confirm": False,
    "ten_vad_threshold": 0.5,
    "ten_vad_hop_size": 256,
    "correction_memory_enabled": True,
    "wrong_answer_memory_enabled": True,
    "score_weight_asr_metadata": 0.25,
    "score_weight_vad_alignment": 0.20,
    "score_weight_word_timestamp": 0.15,
    "score_weight_timing": 0.10,
    "score_weight_repetition": 0.10,
    "score_weight_context": 0.10,
    "score_weight_memory": 0.05,
    "score_weight_hallucination_penalty": 0.30
}

DEFAULT_ROUGHCUT_SETTINGS = {
    "editor_roughcut_draft_enabled": False,
    "editor_roughcut_draft_prompt": "",
    "editor_roughcut_draft_max_subtitle_count": 12,
    "editor_roughcut_draft_max_major_segments": 10,
    "roughcut_major_segment_ui_enabled": True,
    "roughcut_legacy_table_fallback": True,
    "roughcut_run_after_subtitle_generation": True,
    "roughcut_auto_load_subtitles_on_enter": True,
    "roughcut_start_button_mode_routing": True,
    "roughcut_llm_enabled": False,
    "roughcut_llm_use_override": False,
    "roughcut_llm_provider": "inherit",
    "roughcut_llm_model": "",
    "roughcut_llm_api_key_mode": "inherit",
    "roughcut_llm_temperature": 0.2,
    "roughcut_llm_max_context_rows": 80,
    "roughcut_llm_chunk_rows": 11,
    "roughcut_llm_lookahead_rows": 8,
    "roughcut_llm_rows_auto_enabled": True,
    "roughcut_llm_rows_lora_enabled": True,
    "roughcut_llm_rows_lora_blend": 0.30,
    "roughcut_llm_rows_exploration_rate": 0.05,
    "roughcut_llm_context_min_rows": 48,
    "roughcut_llm_context_max_rows": 160,
    "roughcut_llm_chunk_min_rows": 8,
    "roughcut_llm_chunk_max_rows": 18,
    "roughcut_llm_lookahead_min_rows": 4,
    "roughcut_llm_lookahead_max_rows": 12,
    "roughcut_codex_timeout_sec": 180,
    "roughcut_codex_max_context_rows": 160,
    "roughcut_codex_chunk_rows": 48,
    "roughcut_codex_lookahead_rows": 12,
    "roughcut_llm_threads_auto_enabled": True,
    "roughcut_llm_threads": 4,
    "roughcut_llm_threads_resource_max": 4,
    "roughcut_llm_prompt": "",
    "roughcut_llm_prompt_id": "roughcut_page3b_v1",
    "roughcut_llm_token_budget": 4096,
    "roughcut_boundary_verification_enabled": True,
    "roughcut_boundary_rollback_window_rows": 12,
    "roughcut_boundary_rollback_window_sec": 60.0,
    "roughcut_scene_cut_refine_enabled": True,
    "roughcut_scene_cut_strong_threshold": 28.0,
    "roughcut_scene_cut_default_threshold": 18.0,
    "roughcut_scene_cut_apply_subtitle_reassignment": True,
    "roughcut_silence_gap_prefer_sec": 1.0,
    "roughcut_title_suggestions_enabled": True,
    "roughcut_title_suggestions_count": 3,
    "roughcut_thumbnail_cache_enabled": True,
    "roughcut_thumbnail_fixed_width": 180,
    "roughcut_thumbnail_fixed_height": 120,
    "roughcut_hover_preview_step_sec": 1.0,
    "roughcut_hover_preview_max_sec": 3.0,
    "roughcut_hover_preview_enabled": True,
    "roughcut_draft_autosave_enabled": True,
    "roughcut_show_expanded_subtitles": True,
    "roughcut_show_minor_code_per_row": True,
    "roughcut_major_min_subtitle_count": 5,
    "roughcut_minor_min_subtitle_count": 1,
    "roughcut_major_min_duration_sec": 0.0,
    "roughcut_major_max_duration_sec": 0.0,
    "roughcut_major_max_subtitle_count": 0,
    "roughcut_major_max_segment_count": 10,
    "roughcut_boundary_refine_window_sec": 1.5,
    "roughcut_scene_cut_threshold": 18.0,
}

# ── 🔔 ntfy 푸시 알람 설정 ──
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")

# ── 🎨 다크 UI 테마 ──
BG           = "#1a1a1a"
BG2          = "#242424"
BG3          = "#2e2e2e"
FG           = "#ffffff"
FG2          = "#aaaaaa"
ACCENT       = "#2ecc71"
ACCENT_HOVER = "#1a8a50"
RED          = "#ff6b6b"
YELLOW       = "#ffcc44"
BLUE         = "#4fc3f7"
FONT         = "Apple SD Gothic Neo"

# ── 📏 자막 분리 기본 규칙 ──
DEFAULT_SPLIT_RULES = [
    "는데", "은데", "지만", "하지만", "어서", "아서",
    "가지고", "해서", "하고", "이고", "면서", "니까",
    "거든", "잖아", "있습니다", "습니다"
]
DEFAULT_SPLIT_PUNCTUATION = [".", "!", "?"]
DEFAULT_MAX_CHARS = 20

# ── 📂 폴더 자동 생성 ──
# ✅ 유지: 앱 실행 시 필요 폴더 보장
os.makedirs(DATASET_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR,  exist_ok=True)
os.makedirs(VOICE_DATA_DIR, exist_ok=True)
