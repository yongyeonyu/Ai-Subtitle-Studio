# Version: 03.07.05
# Phase: PHASE2
"""Canonical UI mode/stage labels for subtitle-generation status text."""
from __future__ import annotations

from functools import lru_cache

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
    "lora": "LoRA",
    "deep_learning": "딥러닝",
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
    "lora",
    "deep_learning",
]
_HTML_BREAK_TOKENS = ("<br>", "<br/>", "<br />")
_CUT_BOUNDARY_TOKENS = ("[컷 경계]", "컷 경계", "scan-cut", "scan cut", "cut boundary", "cut_boundary", "scene cut", "pyramid60")
_PREPROCESS_TOKENS = ("[전처리]", "오디오 추출", "ffmpeg 오디오", "전처리")
_AUDIO_TOKENS = ("[음성]", "음량", "필터", "deepfilter", "rnnoise", "resemble", "clearvoice", "노이즈", "보컬")
_SUBTITLE_LLM_TOKENS = ("[자막 llm]", "llm", "최적화", "교정", "분리")
_VAD_TOKENS = ("[vad]", "silero", "ten_vad", "ten vad", "검수", "위치 재계산", "음성 섹터")
_STT2_TOKENS = ("저점 구간", "stt2 확인", "stt2 결과로 보강")
_LORA_TOKENS = ("[lora]", "lora", "개인화", "텍스트 lora", "lo-ra")
_DEEP_LEARNING_TOKENS = ("[딥러닝]", "deep learning", "deep-learning", "deep subtitle", "deep policy")
_STT_TOKENS = ("[stt", "whisper", "stt", "자막 생성")
_DUAL_STT_STAGE_KEYS = frozenset({"stt1", "stt2"})
_STT_SUBTITLE_LLM_STAGE_KEYS = frozenset({"stt1", "subtitle_llm"})
_ENSEMBLE_STT_SUBTITLE_LLM_STAGE_KEYS = frozenset({"stt1", "stt2", "subtitle_llm"})


def stage_label_for_key(stage_key: str) -> str:
    return STAGE_LABELS.get(str(stage_key or ""), "대기")


def _contains_any(blob: str, tokens: tuple[str, ...]) -> bool:
    return any(token in blob for token in tokens)


def _status_blob(status_text: object) -> str:
    return str(status_text or "")


def _status_stage_keys_set(
    blob: str,
    *,
    stt_ensemble_enabled: bool,
    collect_all: bool,
) -> set[str]:
    return set(_status_stage_keys_cached(blob, stt_ensemble_enabled, collect_all))


def _status_stage_keys_frozen(
    status_text: object,
    *,
    stt_ensemble_enabled: bool,
    collect_all: bool,
) -> frozenset[str]:
    return _status_stage_keys_cached(
        _status_blob(status_text),
        stt_ensemble_enabled,
        collect_all,
    )


def _status_stage_keys(
    status_text: object,
    *,
    stt_ensemble_enabled: bool,
    collect_all: bool,
) -> set[str]:
    return _status_stage_keys_set(
        _status_blob(status_text),
        stt_ensemble_enabled=stt_ensemble_enabled,
        collect_all=collect_all,
    )


def _processing_stage_keys(status_text: object) -> frozenset[str]:
    return _stage_summary_cached(_status_blob(status_text), True)[0]


@lru_cache(maxsize=256)
def _normalized_status_lines_cached(blob: str) -> tuple[str, tuple[str, ...]]:
    normalized = blob
    for token in _HTML_BREAK_TOKENS:
        normalized = normalized.replace(token, "\n")
    lines = tuple(line.strip() for line in normalized.splitlines() if str(line or "").strip())
    return normalized, lines


@lru_cache(maxsize=256)
def _stage_keys_from_blob_cached(blob: str, stt_ensemble_enabled: bool) -> frozenset[str]:
    blob = str(blob or "").lower()
    if not blob:
        return frozenset()

    if _contains_any(blob, _CUT_BOUNDARY_TOKENS):
        return frozenset({"cut_boundary"})

    if _contains_any(blob, _PREPROCESS_TOKENS):
        return frozenset({"preprocess"})

    if _contains_any(blob, _AUDIO_TOKENS):
        return frozenset({"audio"})

    if "[stt+자막 llm]" in blob:
        keys = {"stt1", "subtitle_llm"}
        if stt_ensemble_enabled:
            keys.add("stt2")
        return frozenset(keys)

    if _contains_any(blob, _SUBTITLE_LLM_TOKENS):
        return frozenset({"subtitle_llm"})

    if _contains_any(blob, _VAD_TOKENS):
        return frozenset({"vad"})

    if "stt1 우선" in blob:
        return frozenset({"stt1"})
    if _contains_any(blob, _STT2_TOKENS):
        return frozenset({"stt2"})

    if _contains_any(blob, _LORA_TOKENS):
        return frozenset({"lora"})

    if _contains_any(blob, _DEEP_LEARNING_TOKENS):
        return frozenset({"deep_learning"})

    if _contains_any(blob, _STT_TOKENS):
        keys = {"stt1"}
        if stt_ensemble_enabled:
            keys.add("stt2")
        return frozenset(keys)

    return frozenset()


def _blob_stage_keys(
    normalized: str,
    lines: tuple[str, ...],
    *,
    stt_ensemble_enabled: bool,
    collect_all: bool,
) -> set[str]:
    if not normalized:
        return set()
    if collect_all:
        keys: set[str] = set()
        for line in lines:
            keys.update(_stage_keys_from_blob_cached(line, stt_ensemble_enabled))
        if not keys:
            keys.update(_stage_keys_from_blob_cached(normalized, stt_ensemble_enabled))
        return keys
    for line in reversed(lines):
        keys = _stage_keys_from_blob_cached(line, stt_ensemble_enabled)
        if keys:
            return set(keys)
    return set(_stage_keys_from_blob_cached(normalized, stt_ensemble_enabled))


@lru_cache(maxsize=256)
def _status_stage_keys_cached(
    blob: str,
    stt_ensemble_enabled: bool,
    collect_all: bool,
) -> frozenset[str]:
    latest_keys, all_keys, _label = _stage_summary_cached(blob, stt_ensemble_enabled)
    return all_keys if collect_all else latest_keys


@lru_cache(maxsize=256)
def _stage_summary_cached(
    blob: str,
    stt_ensemble_enabled: bool,
) -> tuple[frozenset[str], frozenset[str], str]:
    if not blob:
        return frozenset(), frozenset(), ""
    normalized, lines = _normalized_status_lines_cached(blob)
    latest_keys = frozenset(
        _blob_stage_keys(
            normalized,
            lines,
            stt_ensemble_enabled=stt_ensemble_enabled,
            collect_all=False,
        )
    )
    all_keys = frozenset(
        _blob_stage_keys(
            normalized,
            lines,
            stt_ensemble_enabled=stt_ensemble_enabled,
            collect_all=True,
        )
    )
    return latest_keys, all_keys, _stage_label_from_keys(latest_keys)


def generation_stage_keys(status_text: object, *, stt_ensemble_enabled: bool = False) -> set[str]:
    """Return canonical pipeline stage keys from raw log/status text."""
    latest_keys, _all_keys, _label = _stage_summary_cached(
        _status_blob(status_text),
        stt_ensemble_enabled,
    )
    return set(latest_keys)


def generation_stage_keys_all(status_text: object, *, stt_ensemble_enabled: bool = False) -> set[str]:
    """Return every canonical pipeline stage key mentioned in raw log/status text."""
    _latest_keys, all_keys, _label = _stage_summary_cached(
        _status_blob(status_text),
        stt_ensemble_enabled,
    )
    return set(all_keys)


def _stage_label_from_keys(keys: frozenset[str] | set[str]) -> str:
    if not keys:
        return ""
    if keys == _DUAL_STT_STAGE_KEYS:
        return "STT 1/2"
    if keys == _STT_SUBTITLE_LLM_STAGE_KEYS or keys == _ENSEMBLE_STT_SUBTITLE_LLM_STAGE_KEYS:
        return "STT+자막 LLM"
    for key in STAGE_ORDER:
        if key in keys:
            return stage_label_for_key(key)
    return "대기"


@lru_cache(maxsize=256)
def _generation_stage_label_cached(blob: str, stt_ensemble_enabled: bool) -> str:
    return _stage_summary_cached(blob, stt_ensemble_enabled)[2]


def generation_stage_summary(status_text: object, *, stt_ensemble_enabled: bool = False) -> dict[str, object]:
    latest_keys, all_keys, label = _stage_summary_cached(
        _status_blob(status_text),
        stt_ensemble_enabled,
    )
    return {
        "keys": set(latest_keys),
        "all_keys": set(all_keys),
        "label": label,
        "active": bool(latest_keys),
    }


def generation_stage_label(status_text: object, *, stt_ensemble_enabled: bool = False) -> str:
    return _generation_stage_label_cached(_status_blob(status_text), True)


def is_generation_stage_status(status_text: object) -> bool:
    return bool(_processing_stage_keys(status_text))


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
    stage_keys = _processing_stage_keys(status_text)
    active = bool(processing) or state_u == "ST_PROC" or bool(stage_keys)

    if not active:
        return "에디터"

    if "cut_boundary" in stage_keys:
        return "컷 경계"

    if process_mode_u == "MODE_AUTO":
        return "자동 처리"

    if process_mode_u == "MODE_PARTIAL":
        return "구간 생성"

    if process_mode_u == "MODE_FROM_HERE":
        return "이후 생성"

    return "자막 생성"
