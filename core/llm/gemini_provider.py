# Version: 02.03.02
# Phase: PHASE1-B
"""Google Gemini adapter for subtitle text splitting."""
from __future__ import annotations

import json
import re
import time


def resolve_gemini_model(model_name: str) -> str:
    return "gemini-2.5-pro" if "Pro" in (model_name or "") else "gemini-2.5-flash"


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


def split_text(api_key: str, model_name: str, prompt: str, max_retries: int = 2) -> list[str] | None:
    if not api_key:
        return None

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    gemini_model = resolve_gemini_model(model_name)

    last_error: Exception | None = None
    for _ in range(max(1, max_retries)):
        try:
            response = client.models.generate_content(
                model=gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            chunks = _parse_chunks(response.text or "")
            return chunks or None
        except Exception as e:
            last_error = e
            if "429" in str(e):
                time.sleep(1)
                continue
            raise

    if last_error:
        raise last_error
    return None
