# Version: 03.07.05
# Phase: PHASE2
"""Canonical UI mode/stage labels for subtitle-generation status text."""
from __future__ import annotations

from core.work_mode import EDITOR_MODE, ROUGHCUT_MODE, SHORTFORM_MODE, normalize_work_mode


STAGE_LABELS = {
    "cut_boundary": "컷 경계",
    "preprocess": "전처리",
    "audio": "음성",
    "stt1": "STT 1",
    "stt2": "STT 2",
    "vad": "VAD",
    "subtitle_llm": "자막 LLM",
    "roughcut_llm": "러프컷 LLM",
}

STAGE_ORDER = [
    "cut_boundary",
    "preprocess",
    "audio",
    "stt1",
    "stt2",
    "vad",
    "subtitle_llm",
    "roughcut_llm",
]


def stage_label_for_key(stage_key: str) -> str:
    return STAGE_LABELS.get(str(stage_key or ""), "대기")


def _stage_keys_from_blob(blob: str, *, stt_ensemble_enabled: bool = False) -> set[str]:
    blob = str(blob or "").lower()
    if not blob:
        return set()

    if any(token in blob for token in (
        "[컷 경계]",
        "컷 경계",
        "scan-cut",
        "scan cut",
        "cut boundary",
        "cut_boundary",
        "scene cut",
        "pyramid60",
    )):
        return {"cut_boundary"}

    if any(token in blob for token in ("[전처리]", "오디오 추출", "ffmpeg 오디오", "전처리")):
        return {"preprocess"}

    if any(token in blob for token in (
        "[음성]",
        "음량",
        "필터",
        "deepfilter",
        "rnnoise",
        "resemble",
        "clearvoice",
        "노이즈",
        "보컬",
    )):
        return {"audio"}

    if "[stt+자막 llm]" in blob:
        keys = {"stt1", "subtitle_llm"}
        if stt_ensemble_enabled:
            keys.add("stt2")
        return keys

    if any(token in blob for token in ("[자막 llm]", "llm", "최적화", "교정", "분리")):
        return {"subtitle_llm"}

    if any(token in blob for token in ("[vad]", "silero", "ten_vad", "ten vad", "검수", "위치 재계산", "음성 섹터")):
        return {"vad"}

    if any(token in blob for token in ("[stt", "whisper", "stt", "자막 생성")):
        keys = {"stt1"}
        if stt_ensemble_enabled:
            keys.add("stt2")
        return keys

    return set()


def generation_stage_keys(status_text: object, *, stt_ensemble_enabled: bool = False) -> set[str]:
    """Return canonical pipeline stage keys from raw log/status text."""
    blob = str(status_text or "")
    if not blob:
        return set()

    normalized = blob.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    lines = [line.strip() for line in normalized.splitlines() if str(line or "").strip()]

    for line in reversed(lines):
        keys = _stage_keys_from_blob(line, stt_ensemble_enabled=stt_ensemble_enabled)
        if keys:
            return keys

    return _stage_keys_from_blob(normalized, stt_ensemble_enabled=stt_ensemble_enabled)


def generation_stage_label(status_text: object, *, stt_ensemble_enabled: bool = False) -> str:
    keys = generation_stage_keys(status_text, stt_ensemble_enabled=True)
    if not keys:
        return ""

    if keys == {"stt1", "stt2"}:
        return "STT 1/2"

    if keys == {"stt1", "subtitle_llm"} or keys == {"stt1", "stt2", "subtitle_llm"}:
        return "STT+자막 LLM"

    for key in STAGE_ORDER:
        if key in keys:
            return stage_label_for_key(key)

    return "대기"


def is_generation_stage_status(status_text: object) -> bool:
    return bool(generation_stage_keys(status_text, stt_ensemble_enabled=True))


def process_mode_label(
    *,
    screen_mode: object = EDITOR_MODE,
    process_mode: object = "",
    state: object = "",
    status_text: object = "",
    processing: bool = False,
    stt_mode_enabled: bool = False,
) -> str:
    screen_mode = normalize_work_mode(screen_mode)

    if screen_mode == ROUGHCUT_MODE:
        return "러프컷"

    if screen_mode == SHORTFORM_MODE:
        return "숏폼"

    if stt_mode_enabled:
        return "STT"

    process_mode_u = str(process_mode or "").upper()
    state_u = str(state or "").upper()
    active = bool(processing) or state_u == "ST_PROC" or is_generation_stage_status(status_text)

    if not active:
        return "에디터"

    if "cut_boundary" in generation_stage_keys(status_text, stt_ensemble_enabled=True):
        return "컷 경계"

    if process_mode_u == "MODE_AUTO":
        return "자동 처리"

    if process_mode_u == "MODE_PARTIAL":
        return "구간 생성"

    if process_mode_u == "MODE_FROM_HERE":
        return "이후 생성"

    return "자막 생성"
