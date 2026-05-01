# Version: 03.02.01
# Phase: PHASE2
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .roughcut_prompts import build_roughcut_prompt, validate_roughcut_action_response
from .roughcut_llm_config import resolve_roughcut_llm_config
from .roughcut_settings import merge_roughcut_settings


@dataclass(frozen=True, slots=True)
class RoughCutLLMActionResult:
    action: str
    ok: bool
    used_llm: bool = False
    data: dict[str, Any] = field(default_factory=dict)
    prompt: str = ""
    error: str = ""


def _parse_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip().strip("`")
    if text.lower().startswith("json"):
        text = text[4:].strip()
    parsed = json.loads(text or "{}")
    return parsed if isinstance(parsed, dict) else {}


def run_roughcut_llm_action(
    action: str,
    payload: dict[str, Any],
    *,
    settings: dict[str, Any] | None = None,
    llm_client=None,
) -> RoughCutLLMActionResult:
    """Run a PAGE 3-B roughcut LLM action, falling back to local pipeline data."""
    roughcut_settings = merge_roughcut_settings(settings)
    llm_config = resolve_roughcut_llm_config(settings)
    prompt = build_roughcut_prompt(
        action,
        payload,
        prompt_id=str(roughcut_settings.get("roughcut_llm_prompt_id") or ""),
        token_budget=int(roughcut_settings.get("roughcut_llm_token_budget", 4096) or 4096),
        user_prompt=llm_config.prompt,
    )
    if not llm_config.enabled:
        return RoughCutLLMActionResult(action=action, ok=False, used_llm=False, prompt=prompt, error="llm_disabled")
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


__all__ = ["RoughCutLLMActionResult", "run_roughcut_llm_action"]
