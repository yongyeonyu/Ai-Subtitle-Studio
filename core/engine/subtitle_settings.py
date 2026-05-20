# Version: 03.14.19
# Phase: PHASE2
"""Runtime settings helpers for subtitle optimization."""

from core.correction_dictionary_db import load_corrections as load_correction_dictionary
from core.llm.ollama_provider import ollama_probe_timeout, resolve_ollama_model_for_request
from core.llm.openai_provider import is_openai_model
from core.runtime import config
from core.runtime.multi_process import runtime_llm_worker_plan


def _get_user_settings():
    from core.settings import load_settings

    return load_settings()


def get_local_dataset_corrections() -> dict:
    return load_correction_dictionary(getattr(config, "CORRECTIONS_FILE", None))


def get_selected_llm() -> str:
    settings = _get_user_settings()
    runtime_enabled = settings.get("subtitle_llm_runtime_enabled")
    if runtime_enabled is False:
        return "사용 안함 (모드 정책)"
    if runtime_enabled is True:
        return settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"))
    try:
        from core.mode_policy import MODE_TOOL_STACKS, selected_mode_from_settings

        mode = selected_mode_from_settings(settings)
        if not bool(MODE_TOOL_STACKS.get(mode, {}).get("llm", False)):
            return "사용 안함 (모드 정책)"
    except Exception:
        pass
    return settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"))


def _setting_int(settings: dict, key: str, default: int, fallback_key: str | None = None) -> int:
    value = settings.get(key, None)
    if value in (None, "") and fallback_key:
        value = settings.get(fallback_key, None)
    if value in (None, ""):
        value = default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _setting_float(settings: dict, key: str, default: float) -> float:
    value = settings.get(key, default)
    if value in (None, ""):
        value = default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_local_ollama_model(model: str) -> bool:
    text = str(model or "").strip()
    if not text or "사용 안함" in text:
        return False
    if "Gemini" in text or is_openai_model(text):
        return False
    return True


def _resolve_runtime_llm_model(model: str, logger=None, *, context: str = "자막 LLM") -> str:
    text = str(model or "").strip()
    if not _is_local_ollama_model(text):
        return text
    return resolve_ollama_model_for_request(
        text,
        logger=logger,
        context=context,
        timeout=ollama_probe_timeout(text, 8.0),
        allow_fallback=True,
    )


def _effective_llm_workers(
    model: str,
    configured_workers: int,
    settings: dict,
    segment_count: int,
    *,
    local_worker_cap: int = 2,
) -> tuple[int, str]:
    configured = max(1, int(configured_workers or 1))
    count = max(1, int(segment_count or 1))
    if not _is_local_ollama_model(model):
        return 1, "api"
    if bool((settings or {}).get("llm_threads_auto_enabled", True)):
        workers, _meta = runtime_llm_worker_plan(
            settings=settings or {},
            requested=configured,
            workload=count,
            provider="ollama",
            model=model,
            task="subtitle",
        )
        return max(1, min(workers, count)), "local_auto"
    local_cap = max(1, _setting_int(settings or {}, "local_ollama_llm_max_workers", local_worker_cap))
    return max(1, min(configured, local_cap, count)), "local"


def _quality_conservative_enabled(settings: dict | None) -> bool:
    settings = settings or {}
    return bool(
        settings.get("subtitle_quality_enabled")
        or settings.get("subtitle_quality_auto_check_after_generate")
        or settings.get("subtitle_quality_auto_correct_enabled")
    )
