# Version: 03.15.00
# Phase: PHASE2


# === OS / Platform Detection ===
import platform

OS_NAME = platform.system()          # "Darwin", "Windows", "Linux"
IS_MAC = OS_NAME == "Darwin"
IS_WINDOWS = OS_NAME == "Windows"
IS_LINUX = OS_NAME == "Linux"
APP_VERSION = "03.15.00"

# CPU / Apple Silicon
MACHINE = platform.machine()         # "arm64", "x86_64"
IS_APPLE_SILICON = IS_MAC and MACHINE == "arm64"

import os

# .env 파일 로드
from dotenv import load_dotenv
load_dotenv()

# ── 🏷️ 앱 기본 정보 ──
APP_NAME      = "AI Subtitle Studio"
INSTANCE_PORT = 47291

# ── 📂 주요 폴더 경로 설정 ──
BASE_DIR    = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
OUTPUT_DIR  = os.path.join(BASE_DIR, "output")
VOICE_DATA_DIR = os.path.join(BASE_DIR, "voice_data")

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
WHISPER_MODEL = "mlx-community/whisper-large-v3-mlx" if IS_MAC else "large-v3"
LANGUAGE       = "ko"
TIME_OFFSET    = 0.2

# ✅ 수정: 하드코딩 경로 제거 → folder_settings.json에서 관리
DEFAULT_FOLDER = ""

# ── 🤖 AI 엔진 및 프롬프트 설정 ──
OLLAMA_MODEL = "exaone3.5:7.8b"

DEFAULT_LLM_PROMPT = (
    "당신은 한국어 유튜브/브이로그 자막을 검수하는 전문 자막 QA 편집자입니다.\n"
    "아래 '원본 텍스트'는 이미 STT가 들은 발화입니다. 들리지 않은 말을 보태지 말고, 원문의 단어·순서·말투·의미를 최대한 보존하세요.\n"
    "역할은 번역/요약/각색이 아니라 자막 검수입니다. 시청자가 읽기 편하도록 띄어쓰기, 명백한 오탈자, 최소 문장부호, 자연스러운 줄 분리만 수행하세요.\n"
    "[기본 규칙]\n"
    "1. 맞춤법보다 원문 보존이 우선입니다. 확실한 띄어쓰기와 명백한 STT 오탈자만 교정하세요.\n"
    "2. 고유명사, 행사명, 브랜드명, 숫자, 영어 표기는 추측해서 바꾸지 말고 원문을 우선 유지하세요.\n"
    "3. 없는 사실, 설명, 주어, 목적어, 감정 표현을 추가하지 마세요. 문맥상 그럴듯해도 들린 내용이 아니면 금지입니다.\n"
    "4. '~했고요', '~거든요', '~잖아', '아', '어', '뭐' 같은 구어체·머뭇거림·감탄은 의미가 있으면 살리고 문어체로 고치지 마세요.\n"
    "5. 반복 발화는 실제 말버릇이면 유지하되, STT 환각처럼 같은 문구가 비정상적으로 반복되면 새 문장을 만들지 말고 원문 범위 안에서 최소 정리하세요.\n"
    "6. 마침표(.)는 모두 제거하고, 쉼표(,) / 느낌표(!) / 물결(~)은 의미가 바뀌지 않을 때만 최소로 사용하세요.\n"
    "7. 한 줄당 글자 수가 약 {threshold}자(±5자 오차 허용)가 되도록 시청자가 읽기 편한 호흡과 어절 단위에서 나누세요.\n"
    "8. 문장을 나눌 때는 가능한 한 다음 단어들 뒤({end_words})나, 다음 단어들 앞({start_words})에서 나누세요.\n"
    "9. 원본 텍스트가 5자 이하이고 문맥과 무관한 파편/환각으로 보일 때만 결과 리스트에서 제외하세요. 확실하지 않으면 유지하세요.\n"
    "10. 절대 부가 설명이나 인사말을 넣지 말고, 오직 분리된 결과 문자열만 출력하세요.\n\n"
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
    "split_length_threshold": 10,
    "llm_workers":      6,
    "local_ollama_llm_max_workers": 2,
    "sub_gap_break_sec":  1.5,
    "sub_min_duration":   0.2,
    "sub_max_cps":        12,
    "sub_dedup_window":   0.5,
    "accuracy_first_mode": True,
    "auto_start_mode": "quality",
    "stt_quality_preset": "precise",
    "stt_ensemble_enabled": True,
    "stt_candidate_scoring_enabled": True,
    "stt_low_score_recheck_enabled": True,
    "stt_low_score_recheck_threshold": 60,
    "stt_low_score_recheck_padding_sec": 0.8,
    "stt_low_score_recheck_max_segments": 240,
    "selected_whisper_model_secondary": (
        "youngouk/ghost613-turbo-korean-4bit-mlx"
        if IS_MAC else
        "ghost613/faster-whisper-large-v3-turbo-korean"
    ),
    "stt_ensemble_llm_judge_enabled": True,
    "vad_post_stt_align_enabled": True,
    "vad_post_stt_max_shift_sec": 0.7,
    "vad_post_stt_edge_pad_sec": 0.04,
    "subtitle_quality_enabled": False,
    "subtitle_quality_auto_check_after_generate": True,
    "subtitle_quality_auto_correct_enabled": True,
    "editor_lora_runtime_enabled": True,
    "audio_chunk_routing_enabled": True,
    "audio_chunk_route_vad_enabled": True,
    "audio_chunk_profile_sec": 30.0,
    "whisper_chunk_overlap_sec": 3.0,
    "chunk_time_limit": 180,
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
    "roughcut_run_after_subtitle_generation": False,
    "roughcut_auto_load_subtitles_on_enter": True,
    "roughcut_start_button_mode_routing": True,
    "roughcut_llm_enabled": False,
    "roughcut_llm_use_override": False,
    "roughcut_llm_provider": "inherit",
    "roughcut_llm_model": "",
    "roughcut_llm_api_key_mode": "inherit",
    "roughcut_llm_temperature": 0.2,
    "roughcut_llm_max_context_rows": 80,
    "roughcut_llm_chunk_rows": 12,
    "roughcut_llm_lookahead_rows": 8,
    "roughcut_llm_threads": 4,
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
