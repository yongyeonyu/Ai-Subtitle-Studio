# Version: 03.02.02
# Phase: PHASE2
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .roughcut_prompts import DEFAULT_ROUGHCUT_PROMPT_V1
from .roughcut_settings import merge_roughcut_settings


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


def resolve_roughcut_llm_config(settings: dict[str, Any] | None = None) -> RoughCutLLMConfig:
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
    return RoughCutLLMConfig(
        enabled=bool(merged.get("roughcut_llm_enabled", False)),
        use_override=use_override,
        provider=provider,
        model=model,
        api_key_mode=str(merged.get("roughcut_llm_api_key_mode") or "inherit"),
        temperature=max(0.0, min(1.0, float(merged.get("roughcut_llm_temperature", 0.2) or 0.2))),
        max_context_rows=max(1, int(merged.get("roughcut_llm_max_context_rows", 80) or 80)),
        chunk_rows=max(1, int(merged.get("roughcut_llm_chunk_rows", 12) or 12)),
        lookahead_rows=max(0, int(merged.get("roughcut_llm_lookahead_rows", 8) or 8)),
        threads=max(1, int(merged.get("roughcut_llm_threads", 4) or 4)),
        prompt=DEFAULT_ROUGHCUT_PROMPT_V1,
    )


__all__ = ["RoughCutLLMConfig", "resolve_roughcut_llm_config"]
