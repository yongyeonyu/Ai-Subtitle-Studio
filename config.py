# Version: 02.03.17
# Phase: PHASE1-C


# === OS / Platform Detection ===
import platform

OS_NAME = platform.system()          # "Darwin", "Windows", "Linux"
IS_MAC = OS_NAME == "Darwin"
IS_WINDOWS = OS_NAME == "Windows"
IS_LINUX = OS_NAME == "Linux"
APP_VERSION = "02.03.17"

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
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
OUTPUT_DIR  = os.path.join(BASE_DIR, "output")
VOICE_DATA_DIR = os.path.join(BASE_DIR, "voice_data")

CORRECTIONS_DIR  = DATASET_DIR              # 호환용 alias
CORRECTIONS_FILE = os.path.join(DATASET_DIR, "dataset_correction.json")
RULES_FILE       = os.path.join(DATASET_DIR, "subtitle_rule.json")

CORRECTIONS_DIR = DATASET_DIR  # ✅ 추가

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
    "당신은 유튜브 채널의 전문 자막 편집자입니다.\n"
    "아래 '원본 텍스트'의 단어, 문장 구조, 의미를 100% 그대로 유지하면서 오직 띄어쓰기/단순 오탈자만 교정하고 규칙에 따라 분리하세요.\n"
    "[기본 규칙]\n"
    "1. 맞춤법, 띄어쓰기를 교정한다.\n"
    "2. 음성인식 오류에 의한 단순 오탈자만 수정한다.\n"
    "3. 없는 사실을 지어내거나 화법을 멋대로 바꾸지 마라. 오직 들리는 내용만 교정한다.\n"
    "4. '~했고요', '~거든요', '~잖아' 등 특유의 구어체와 감성, 감탄사를 절대 표준어로 바꾸지 말고 원본 그대로 살린다.\n"
    "5. 절대 부가 설명이나 인사말을 넣지 말고, 오직 분리된 결과 문자열만 출력한다.\n"
    "6. 마침표(.)는 모두 제거하되 쉼표(,) / 느낌표(!) / 물결(~)은 문맥에 맞춰서 자연스럽게 넣는다.\n"
    "7. 한 줄당 글자 수가 약 {threshold}자(±5자 오차 허용)가 되도록 시청자가 읽기 편한 자연스러운 호흡(어절 단위)에서 문장을 나누세요.\n"
    "8. 문장을 나눌 때는 반드시 다음 단어들 뒤({end_words})나, 다음 단어들 앞({start_words})에서 나누세요.\n"
    "9. 원본 텍스트가 5자 이하이면서 문맥과 관계없는 파편화된 단어일 경우, 무리하게 문장으로 만들지 말고 해당 항목을 결과 리스트에서 제외(삭제)하라.\n\n"
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
    "sub_gap_break_sec":  1.5,
    "sub_min_duration":   0.2,
    "sub_max_cps":        12,
    "sub_dedup_window":   0.5
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
