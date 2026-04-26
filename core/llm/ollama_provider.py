# Version: 02.03.02
# Phase: PHASE1-B
"""Ollama adapter for local subtitle text splitting."""
from __future__ import annotations

import json
import re
import threading
import urllib.request


_WARMED: set[str] = set()
_WARM_LOCK = threading.Lock()


def _parse_chunks(out_text: str) -> list[str]:
    try:
        parsed = json.loads(out_text or "")
        if isinstance(parsed, dict) and isinstance(parsed.get("result"), list):
            return [str(x) for x in parsed["result"] if isinstance(x, str)]
        if isinstance(parsed, list):
            return [str(x) for x in parsed if isinstance(x, str)]
    except Exception:
        pass
    return [m for m in re.findall(r'"([^"]*)"', out_text or "") if m != "result" and len(m) > 1]


def split_text(model: str, prompt: str, timeout: int = 120) -> list[str] | None:
    if not model or "사용 안함" in model:
        return None

    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "keep_alive": -1,
        "options": {
            "temperature": 0.0,
            "num_predict": 256,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Connection": "keep-alive",
        },
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out_text = json.loads(resp.read().decode("utf-8")).get("response", "")
    chunks = _parse_chunks(out_text)
    return chunks or None


def warmup_model(model: str, logger=None) -> None:
    if not model or "사용 안함" in model:
        return

    with _WARM_LOCK:
        if model in _WARMED:
            return

        try:
            body = json.dumps({
                "model": model,
                "prompt": " ",
                "stream": False,
                "keep_alive": -1,
                "options": {
                    "temperature": 0.0,
                    "num_predict": 1,
                },
            }).encode("utf-8")

            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Connection": "keep-alive",
                },
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()

            _WARMED.add(model)
            if logger:
                logger.log(f"🔥 Ollama 워밍업 완료: {model}")
        except Exception as e:
            if logger:
                logger.log(f"⚠️ Ollama 워밍업 실패: {e}")
