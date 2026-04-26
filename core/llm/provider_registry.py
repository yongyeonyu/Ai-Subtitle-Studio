# Version: 02.03.00
# Phase: PHASE1-B
"""Available LLM model metadata for settings UI."""
from __future__ import annotations

from core.llm.openai_provider import OPENAI_MODEL_MAP


GEMINI_MODELS = [
    {"name": "Gemini 2.5 Flash [무료/제한 API]", "provider": "google", "paid": False, "raw_model": "Gemini 2.5 Flash (API)"},
    {"name": "Gemini 2.5 Pro [유료/API 고품질]", "provider": "google", "paid": True, "raw_model": "Gemini 2.5 Pro (API)"},
]

OPENAI_MODELS = [
    {"name": display, "provider": "openai", "paid": True, "raw_model": display}
    for display in OPENAI_MODEL_MAP
]


def cloud_model_items() -> list[dict]:
    items = []
    for m in GEMINI_MODELS + OPENAI_MODELS:
        details = {
            "family": "Google API" if m["provider"] == "google" else "OpenAI API",
            "parameter_size": "Cloud",
            "format": "api",
            "billing": "유료" if m.get("paid") else "무료/제한",
            "provider": m["provider"],
        }
        items.append({
            "name": m["raw_model"],
            "display_name": m["name"],
            "size": 0,
            "details": details,
        })
    return items
