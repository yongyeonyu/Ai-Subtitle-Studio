from __future__ import annotations

import re
from typing import Any


ROUGHCUT_LLM_MIN_PARAMETERS_B = 7.0
ROUGHCUT_LLM_MIN_SIZE_BYTES = 3_500_000_000
ROUGHCUT_CAPABLE_CLOUD_TOKENS = (
    "gemini 2.5 pro",
    "gpt-5.2",
    "gpt-5.5",
)
ROUGHCUT_BLOCKED_CLOUD_TOKENS = (
    "flash",
    "nano",
    "mini",
)
ROUGHCUT_CAPABLE_LOCAL_LATEST = (
    "exaone3.5:latest",
    "gemma2:latest",
    "llama3:latest",
    "llama3.1:latest",
    "mistral:latest",
    "qwen2.5:latest",
)


def roughcut_llm_parameter_b(item: dict[str, Any] | None) -> float | None:
    details = dict((item or {}).get("details") or {})
    parts = [
        str((item or {}).get("name") or ""),
        str((item or {}).get("display_name") or ""),
        str(details.get("parameter_size") or ""),
        str(details.get("family") or ""),
    ]
    for text in parts:
        for match in re.finditer(r"(?<!\d)(\d+(?:\.\d+)?)\s*b\b", text.lower()):
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


def roughcut_llm_is_capable(item: dict[str, Any] | None) -> bool:
    row = dict(item or {})
    details = dict(row.get("details") or {})
    provider = str(details.get("provider") or "ollama").lower()
    name = str(row.get("name") or "")
    display_name = str(row.get("display_name") or name)
    label_l = f"{name} {display_name}".lower()
    if provider == "none" or "사용 안함" in label_l:
        return False

    if provider in {"google", "openai"}:
        if any(re.search(rf"\b{re.escape(token)}\b", label_l) for token in ROUGHCUT_BLOCKED_CLOUD_TOKENS):
            return False
        if "codex" in label_l and ("chatgpt" in label_l or "구독" in label_l or "cli" in label_l):
            return True
        return any(token in label_l for token in ROUGHCUT_CAPABLE_CLOUD_TOKENS) or "gpt-5" in label_l

    params_b = roughcut_llm_parameter_b(row)
    if params_b is not None:
        return params_b >= ROUGHCUT_LLM_MIN_PARAMETERS_B

    if any(token in label_l for token in ROUGHCUT_CAPABLE_LOCAL_LATEST):
        return True

    try:
        return int(row.get("size") or 0) >= ROUGHCUT_LLM_MIN_SIZE_BYTES
    except (TypeError, ValueError):
        return False
