# Version: 02.03.00
# Phase: PHASE1-B
"""OpenAI Responses API adapter."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from core.llm.codex_provider import DEFAULT_CODEX_LABEL, is_codex_model


OPENAI_MODEL_MAP = {
    "OpenAI GPT-5 Nano [유료/API 저비용]": "gpt-5-nano",
    "OpenAI GPT-5 Mini [유료/API 균형]": "gpt-5-mini",
    "OpenAI GPT-5.2 [유료/API 고품질]": "gpt-5.2",
    "OpenAI GPT-5.2 Chat [유료/API ChatGPT]": "gpt-5.2-chat-latest",
    DEFAULT_CODEX_LABEL: "codex-chatgpt-cli",
}


def is_openai_model(model_name: str) -> bool:
    text = model_name or ""
    return is_codex_model(text) or "OpenAI" in text or text.startswith("gpt-")


def resolve_openai_model(model_name: str) -> str:
    model_name = (model_name or "").strip()
    return OPENAI_MODEL_MAP.get(model_name, model_name or "gpt-5-mini")


def _extract_text(payload: dict) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    parts: list[str] = []
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def _parse_chunks(out_text: str) -> list[str]:
    out_text = (out_text or "").strip().strip("`")
    if out_text.lower().startswith("json"):
        out_text = out_text[4:].strip()
    try:
        parsed = json.loads(out_text)
        if isinstance(parsed, dict) and isinstance(parsed.get("result"), list):
            return [str(x) for x in parsed["result"] if isinstance(x, str)]
        if isinstance(parsed, list):
            return [str(x) for x in parsed if isinstance(x, str)]
    except Exception:
        pass
    return [m for m in re.findall(r'"([^"]*)"', out_text) if m != "result" and len(m) > 1]


def split_text(api_key: str, model_name: str, prompt: str, timeout: int = 120) -> list[str] | None:
    if is_codex_model(model_name):
        from core.llm.codex_provider import split_text as codex_split_text

        return codex_split_text(model_name, prompt, timeout=timeout)
    if not api_key:
        return None
    body = json.dumps({
        "model": resolve_openai_model(model_name),
        "input": prompt,
        "text": {"format": {"type": "json_object"}},
        "reasoning": {"effort": "none"},
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        chunks = _parse_chunks(_extract_text(payload))
        return chunks or None
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            detail = str(e)
        raise RuntimeError(f"OpenAI API 오류 {e.code}: {detail}") from e
