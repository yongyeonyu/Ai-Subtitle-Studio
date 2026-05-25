from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from core.llm.openai_provider import is_codex_model, resolve_openai_model
from core.llm.secure_keys import get_api_key


def _call_ollama_json(model: str, prompt: str, *, timeout: int) -> dict[str, Any] | None:
    from core.llm.ollama_provider import generate_text

    text = generate_text(
        model,
        prompt,
        timeout=timeout,
        keep_alive=-1,
        num_predict=1024,
        temperature=0.2,
        json_format=True,
        attempts=2,
    )
    return _parse_json_object(text)


def _call_local_llm_json(provider: str, model: str, prompt: str, *, timeout: int) -> dict[str, Any] | None:
    from core.llm.provider_router import generate_text

    text = generate_text(
        provider,
        model,
        prompt,
        timeout=timeout,
        num_predict=1024,
        temperature=0.2,
        json_format=True,
        attempts=1,
    )
    return _parse_json_object(text)


def _call_openai_json(model: str, prompt: str, *, timeout: int) -> dict[str, Any] | None:
    if is_codex_model(model):
        from core.llm.codex_provider import run_json as codex_run_json

        return codex_run_json(model, prompt, timeout=timeout)
    api_key = get_api_key("openai")
    if not api_key:
        return None
    body = json.dumps(
        {
            "model": resolve_openai_model(model),
            "input": prompt,
            "text": {"format": {"type": "json_object"}},
            "reasoning": {"effort": "none"},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"OpenAI API 오류 {exc.code}: {detail}") from exc
    return _parse_json_object(_extract_openai_text(payload))


def _call_gemini_json(model: str, prompt: str) -> dict[str, Any] | None:
    api_key = get_api_key("google")
    if not api_key:
        return None
    from google import genai
    from google.genai import types

    gemini_model = "gemini-2.5-pro" if "Pro" in model else "gemini-2.5-flash"
    response = genai.Client(api_key=api_key).models.generate_content(
        model=gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
    )
    return _parse_json_object(response.text or "")


def _parse_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip().strip("`")
    if text.lower().startswith("json"):
        text = text[4:].strip()
    parsed = json.loads(text or "{}")
    return parsed if isinstance(parsed, dict) else None


def _extract_openai_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    parts: list[str] = []
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()
