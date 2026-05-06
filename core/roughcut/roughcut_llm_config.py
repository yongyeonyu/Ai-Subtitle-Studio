# Version: 03.02.02
# Phase: PHASE2
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.performance import adaptive_llm_worker_count

from .roughcut_prompts import DEFAULT_ROUGHCUT_PROMPT_V1
from .roughcut_settings import merge_roughcut_settings
from .roughcut_context_policy import resolve_roughcut_context_policy


@dataclass(frozen=True, slots=True)
class RoughCutLLMConfig:
    enabled: bool
    use_override: bool
    provider: str
    model: str
    api_key_mode: str
    temperature: float
    max_context_rows: int
    chunk_rows: int
    lookahead_rows: int
    threads: int
    prompt: str
    context_policy: dict[str, Any] = field(default_factory=dict)


def resolve_roughcut_llm_config(
    settings: dict[str, Any] | None = None,
    *,
    payload: dict[str, Any] | None = None,
    subtitle_rows: list[dict[str, Any]] | None = None,
) -> RoughCutLLMConfig:
    """Resolve roughcut-specific LLM settings without mutating subtitle LLM settings."""
    merged = merge_roughcut_settings(settings)
    source = settings or {}
    use_override = bool(merged.get("roughcut_llm_use_override", False))
    inherited_provider = str(source.get("selected_llm_provider") or "ollama")
    inherited_model = str(source.get("selected_model") or "")
    provider = str(merged.get("roughcut_llm_provider") or "inherit")
    model = str(merged.get("roughcut_llm_model") or "")
    if not use_override or provider == "inherit":
        provider = inherited_provider
    if not use_override or model in ("", "inherit"):
        model = inherited_model
    context_policy = resolve_roughcut_context_policy(
        merged,
        payload=payload,
        subtitle_rows=subtitle_rows,
    )
    max_context_rows = max(1, int(context_policy.get("max_context_rows", 80) or 80))
    chunk_rows = max(1, int(context_policy.get("chunk_rows", 12) or 12))
    lookahead_rows = max(0, int(context_policy.get("lookahead_rows", 8) or 8))
    threads, _thread_meta = adaptive_llm_worker_count(
        settings=merged,
        requested=merged.get("roughcut_llm_threads", 4),
        workload=max(1, max_context_rows // max(1, chunk_rows)),
        provider=provider,
        model=model,
        task="roughcut",
    )
    return RoughCutLLMConfig(
        enabled=bool(merged.get("roughcut_llm_enabled", False)),
        use_override=use_override,
        provider=provider,
        model=model,
        api_key_mode=str(merged.get("roughcut_llm_api_key_mode") or "inherit"),
        temperature=max(0.0, min(1.0, float(merged.get("roughcut_llm_temperature", 0.2) or 0.2))),
        max_context_rows=max_context_rows,
        chunk_rows=chunk_rows,
        lookahead_rows=lookahead_rows,
        threads=threads,
        prompt=DEFAULT_ROUGHCUT_PROMPT_V1,
        context_policy=dict(context_policy),
    )


__all__ = ["RoughCutLLMConfig", "resolve_roughcut_llm_config"]
