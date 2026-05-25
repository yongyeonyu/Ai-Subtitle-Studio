"""Post-edit subtitle LLM actions used from the global canvas menu."""

from __future__ import annotations

import json
import re
from typing import Any, Callable


JsonCaller = Callable[[str, str, str, int], dict[str, Any] | None]


def _parse_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    raw = raw.strip("`")
    if raw.lower().startswith("json"):
        raw = raw[4:].strip()
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {"segments": value}
    except Exception:
        pass
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _default_call_json(provider: str, model: str, prompt: str, timeout: int) -> dict[str, Any] | None:
    try:
        from core.roughcut.editor_draft import _call_editor_roughcut_json
    except Exception:
        from core.llm.provider_router import generate_text

        text = generate_text(
            provider,
            model,
            prompt,
            timeout=timeout,
            num_predict=4096,
            temperature=0.1,
            json_format=True,
            attempts=1,
        )
        return _parse_json_object(text)
    return _call_editor_roughcut_json(provider, model, prompt, timeout=timeout)


def _safe_text(value: Any) -> str:
    return str(value or "").replace("\u2028", "\n").strip()


def _build_prompt(action: str, batch: list[dict[str, Any]]) -> str:
    payload = [
        {
            "index": int(item.get("_post_llm_index", idx)),
            "text": _safe_text(item.get("text")),
        }
        for idx, item in enumerate(batch)
    ]
    if action == "spellcheck":
        task = (
            "Korean subtitle proofreading. Correct only spacing, spelling, and obvious typos. "
            "Do not translate, summarize, rewrite style, add explanations, change names, change numbers, "
            "or change meaning. Keep spoken subtitle tone."
        )
    elif action == "translate_en":
        task = (
            "Translate the Korean subtitle text into natural English subtitles. Preserve meaning, names, "
            "numbers, tone, and subtitle brevity. Do not add explanations."
        )
    else:
        raise ValueError(f"unknown_subtitle_post_llm_action:{action}")
    return (
        f"{task}\n"
        "Return JSON only with this exact schema:\n"
        "{\"segments\":[{\"index\":0,\"text\":\"...\"}]}\n"
        "Return one item for every input index. Keep the same index values.\n\n"
        f"INPUT:\n{json.dumps({'segments': payload}, ensure_ascii=False)}"
    )


def _apply_payload(rows: list[dict[str, Any]], payload: dict[str, Any] | None) -> int:
    if not isinstance(payload, dict):
        return 0
    updates = payload.get("segments")
    if isinstance(updates, dict):
        updates = [
            {"index": key, "text": value}
            for key, value in updates.items()
        ]
    if not isinstance(updates, list):
        return 0
    by_index: dict[int, str] = {}
    for item in updates:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index"))
        except Exception:
            continue
        if "text" in item:
            by_index[idx] = _safe_text(item.get("text"))
    changed = 0
    for row in rows:
        try:
            idx = int(row.get("_post_llm_index"))
        except Exception:
            continue
        if idx not in by_index:
            continue
        new_text = by_index[idx]
        if new_text and new_text != _safe_text(row.get("text")):
            row["text"] = new_text
            changed += 1
    return changed


def run_subtitle_post_llm_action(
    action: str,
    segments: list[dict[str, Any]],
    *,
    provider: str,
    model: str,
    batch_size: int = 60,
    timeout: int = 240,
    call_json: JsonCaller | None = None,
) -> tuple[list[dict[str, Any]], int]:
    rows = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
    editable = [
        row
        for row in rows
        if not bool(row.get("is_gap"))
        and not bool(row.get("stt_pending"))
        and _safe_text(row.get("text"))
    ]
    for idx, row in enumerate(editable):
        row["_post_llm_index"] = idx
    caller = call_json or _default_call_json
    changed = 0
    step = max(1, int(batch_size or 60))
    for start in range(0, len(editable), step):
        batch = editable[start : start + step]
        prompt = _build_prompt(action, batch)
        payload = caller(provider, model, prompt, timeout)
        if not isinstance(payload, dict):
            raise RuntimeError("LLM 응답이 비어 있거나 JSON 형식이 아닙니다.")
        changed += _apply_payload(batch, payload)
    for row in editable:
        row.pop("_post_llm_index", None)
    return rows, changed


__all__ = ["run_subtitle_post_llm_action"]
