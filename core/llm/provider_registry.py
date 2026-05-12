# Version: 02.03.00
# Phase: PHASE1-B
"""Available LLM model metadata for settings UI."""
from __future__ import annotations

from core.llm.codex_provider import CODEX_CLI_MODEL_CATALOG
from core.llm.openai_provider import OPENAI_MODEL_MAP


GEMINI_MODELS = [
    {"name": "Gemini 2.5 Flash [무료/제한 API]", "provider": "google", "paid": False, "raw_model": "Gemini 2.5 Flash (API)"},
    {"name": "Gemini 2.5 Pro [유료/API 고품질]", "provider": "google", "paid": True, "raw_model": "Gemini 2.5 Pro (API)"},
]

OPENAI_MODELS = [
    {
        "name": display,
        "provider": "openai",
        "paid": True,
        "raw_model": display,
        "codex_cli": False,
    }
    for display in OPENAI_MODEL_MAP
    if display not in {str(item.get("display_name") or "") for item in CODEX_CLI_MODEL_CATALOG}
]

CODEX_MODELS = [
    {
        "name": str(item.get("display_name") or ""),
        "provider": "openai",
        "paid": True,
        "raw_model": str(item.get("display_name") or ""),
        "codex_cli": True,
        "cli_model": str(item.get("cli_model", "") or ""),
        "family": str(item.get("family") or "OpenAI Codex CLI"),
        "label": str(item.get("label") or ""),
    }
    for item in CODEX_CLI_MODEL_CATALOG
]


def cloud_model_items() -> list[dict]:
    items = []
    for m in GEMINI_MODELS + OPENAI_MODELS + CODEX_MODELS:
        codex_cli = bool(m.get("codex_cli"))
        details = {
            "family": str(m.get("family") or ("OpenAI Codex CLI" if codex_cli else ("Google API" if m["provider"] == "google" else "OpenAI API"))),
            "parameter_size": "Cloud",
            "format": "cli" if codex_cli else "api",
            "billing": "구독/CLI" if codex_cli else ("유료" if m.get("paid") else "무료/제한"),
            "provider": m["provider"],
        }
        if codex_cli and m.get("cli_model"):
            details["cli_model"] = str(m.get("cli_model") or "")
        if codex_cli and m.get("label"):
            details["preset"] = str(m.get("label") or "")
        items.append({
            "name": m["raw_model"],
            "display_name": m["name"],
            "size": 0,
            "details": details,
        })
    return items
