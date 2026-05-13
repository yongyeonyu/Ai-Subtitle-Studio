# Version: 03.02.01
# Phase: PHASE2
from __future__ import annotations

import gc
import json
from dataclasses import dataclass, field
from typing import Any

from .roughcut_prompts import build_roughcut_prompt, validate_roughcut_action_response
from .roughcut_llm_config import resolve_roughcut_llm_config
from .roughcut_settings import merge_roughcut_settings
from .roughcut_context_policy import trim_roughcut_payload_for_context


@dataclass(frozen=True, slots=True)
class RoughCutLLMActionResult:
    action: str
    ok: bool
    used_llm: bool = False
    data: dict[str, Any] = field(default_factory=dict)
    prompt: str = ""
    error: str = ""


def running_local_llm_models(*args, **kwargs):
    from core.llm.ollama_provider import running_local_llm_models as _running_local_llm_models

    return _running_local_llm_models(*args, **kwargs)


def stop_local_llm_models(*args, **kwargs):
    from core.llm.ollama_provider import stop_local_llm_models as _stop_local_llm_models

    return _stop_local_llm_models(*args, **kwargs)


def warmup_model(*args, **kwargs):
    from core.llm.ollama_provider import warmup_model as _warmup_model

    return _warmup_model(*args, **kwargs)


def _parse_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip().strip("`")
    if text.lower().startswith("json"):
        text = text[4:].strip()
    parsed = json.loads(text or "{}")
    return parsed if isinstance(parsed, dict) else {}


def _normalize_llm_model(value: Any) -> str:
    return str(value or "").strip()


def _llm_model_key(model: str) -> str:
    return _normalize_llm_model(model).casefold()


def _is_disabled_llm_model(model: str) -> bool:
    text = _normalize_llm_model(model)
    return not text or "사용 안함" in text


def _is_local_ollama_llm(provider: str, model: str) -> bool:
    if _is_disabled_llm_model(model):
        return False
    provider_key = str(provider or "").strip().lower()
    if provider_key in {"none", "openai", "google", "gemini", "anthropic", "claude"}:
        return False
    if provider_key and provider_key not in {"ollama", "local", "inherit"}:
        return False
    model_key = _llm_model_key(model)
    cloud_tokens = ("gemini", "openai", "gpt-", "api", "claude")
    return not any(token in model_key for token in cloud_tokens)


def _subtitle_llm_model_from_settings(settings: dict[str, Any]) -> str:
    for key in ("selected_model", "subtitle_llm_model", "selected_llm_model"):
        model = _normalize_llm_model(settings.get(key))
        if not _is_disabled_llm_model(model):
            return model
    return ""


def _subtitle_llm_provider_from_settings(settings: dict[str, Any]) -> str:
    for key in ("selected_llm_provider", "subtitle_llm_provider"):
        provider = str(settings.get(key) or "").strip()
        if provider:
            return provider
    return "ollama"


def _runtime_logger(logger=None):
    if logger is not None:
        return logger
    try:
        from core.runtime.logger import get_logger

        return get_logger()
    except Exception:
        return None


def _clear_runtime_memory_caches() -> None:
    try:
        gc.collect()
    except Exception:
        pass
    try:
        from core.audio.torch_acceleration import trim_torch_memory_caches

        trim_torch_memory_caches(include_sync=True)
    except Exception:
        pass
    try:
        import mlx.core as mx

        clear_cache = getattr(mx, "clear_cache", None)
        if callable(clear_cache):
            clear_cache()
    except Exception:
        pass


def _running_model_keys() -> set[str]:
    try:
        return {_llm_model_key(model) for model in running_local_llm_models() if model}
    except Exception:
        return set()


def prepare_roughcut_llm_model_for_run(
    settings: dict[str, Any] | None,
    llm_config,
    *,
    logger=None,
) -> bool:
    """Unload a different subtitle Ollama model before loading roughcut LLM."""
    if not bool(getattr(llm_config, "enabled", False)):
        return False
    settings = settings or {}
    roughcut_model = _normalize_llm_model(getattr(llm_config, "model", ""))
    roughcut_provider = str(getattr(llm_config, "provider", "") or "").strip().lower()
    if not _is_local_ollama_llm(roughcut_provider, roughcut_model):
        return False

    subtitle_model = _subtitle_llm_model_from_settings(settings)
    subtitle_provider = _subtitle_llm_provider_from_settings(settings)
    if not _is_local_ollama_llm(subtitle_provider, subtitle_model):
        return False
    if _llm_model_key(subtitle_model) == _llm_model_key(roughcut_model):
        return False

    running_keys = _running_model_keys()
    roughcut_key = _llm_model_key(roughcut_model)
    subtitle_key = _llm_model_key(subtitle_model)
    if roughcut_key in running_keys and subtitle_key not in running_keys:
        return False

    active_logger = _runtime_logger(logger)
    stopped = stop_local_llm_models(
        [subtitle_model],
        logger=active_logger,
        log_context="러프컷 LLM 전환",
    )
    _clear_runtime_memory_caches()
    if active_logger and not stopped:
        try:
            active_logger.log(f"🧹 러프컷 LLM 전환: 자막 모델 `{subtitle_model}` unload 요청 완료")
        except Exception:
            pass
    warmup_model(roughcut_model, logger=active_logger, timeout=8.0)
    return True


def run_roughcut_llm_action(
    action: str,
    payload: dict[str, Any],
    *,
    settings: dict[str, Any] | None = None,
    llm_client=None,
) -> RoughCutLLMActionResult:
    """Run a PAGE 3-B roughcut LLM action, falling back to local pipeline data."""
    roughcut_settings = merge_roughcut_settings(settings)
    llm_config = resolve_roughcut_llm_config(settings, payload=payload)
    scoped_payload = trim_roughcut_payload_for_context(payload, llm_config.context_policy)
    prompt = build_roughcut_prompt(
        action,
        scoped_payload,
        prompt_id=str(roughcut_settings.get("roughcut_llm_prompt_id") or ""),
        token_budget=int(roughcut_settings.get("roughcut_llm_token_budget", 4096) or 4096),
        user_prompt=llm_config.prompt,
    )
    if not llm_config.enabled:
        return RoughCutLLMActionResult(action=action, ok=False, used_llm=False, prompt=prompt, error="llm_disabled")
    if llm_client is None:
        prepare_roughcut_llm_model_for_run(settings, llm_config)
        llm_client = _default_roughcut_llm_client(llm_config)
    if llm_client is None:
        return RoughCutLLMActionResult(action=action, ok=False, used_llm=False, prompt=prompt, error="llm_client_missing")
    try:
        raw = llm_client(prompt)
        data = raw if isinstance(raw, dict) else _parse_json_object(str(raw or ""))
        ok, reason = validate_roughcut_action_response(action, data)
        if not ok:
            return RoughCutLLMActionResult(action=action, ok=False, used_llm=True, data=data, prompt=prompt, error=reason)
        return RoughCutLLMActionResult(action=action, ok=True, used_llm=True, data=data, prompt=prompt)
    except Exception as exc:
        return RoughCutLLMActionResult(action=action, ok=False, used_llm=True, prompt=prompt, error=str(exc))


def _default_roughcut_llm_client(llm_config):
    provider = str(getattr(llm_config, "provider", "") or "").strip().lower()
    model = str(getattr(llm_config, "model", "") or "").strip()
    if not model or "사용 안함" in model or provider == "none":
        return None

    def _client(prompt: str):
        from core.llm.provider_router import normalize_llm_provider
        from .editor_draft import _call_editor_roughcut_json, _call_gemini_json, _call_openai_json

        timeout = 180
        provider_key = normalize_llm_provider(provider, model)
        if provider_key in {"google", "gemini"} or "gemini" in model.lower():
            return _call_gemini_json(model, prompt)
        if provider_key == "openai":
            return _call_openai_json(model, prompt, timeout=timeout)
        return _call_editor_roughcut_json(provider_key, model, prompt, timeout=timeout)

    return _client


__all__ = ["RoughCutLLMActionResult", "prepare_roughcut_llm_model_for_run", "run_roughcut_llm_action"]
