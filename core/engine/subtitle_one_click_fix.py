from __future__ import annotations

from typing import Any

from core.personalization.editor_truth_memory import apply_recent_editor_truth_patterns
from core.personalization.lora_models import iso_now, stable_hash


ONE_CLICK_FIX_SCHEMA = "ai_subtitle_studio.subtitle_one_click_fix.v1"

ONE_CLICK_FIX_ACTIONS = {
    "re_recognize_region": "현재 구간 재인식",
    "recheck_cut_only": "이 컷만 다시 확인",
    "restore_source_no_llm": "LLM 없이 원문 복구",
    "reapply_similar_style": "비슷한 자막 스타일 재적용",
}


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").replace("\r", "\n").split()).strip()


def subtitle_source_text_without_llm(segment: dict[str, Any] | None) -> str:
    seg = dict(segment or {})
    quality = dict(seg.get("quality") or {})
    for value in (
        quality.get("auto_corrected_from"),
        seg.get("source_before_edit"),
        seg.get("original_text"),
        seg.get("dictated_text"),
    ):
        text = _clean_text(value)
        if text:
            return text
    selected = str(seg.get("stt_selected_source") or seg.get("stt_ensemble_source") or "").strip().upper()
    candidates = [item for item in list(seg.get("stt_candidates") or []) if isinstance(item, dict)]
    if selected:
        for item in candidates:
            if str(item.get("source") or "").strip().upper() == selected:
                text = _clean_text(item.get("text") or item.get("output"))
                if text:
                    return text
    for item in candidates:
        text = _clean_text(item.get("text") or item.get("output"))
        if text:
            return text
    return _clean_text(seg.get("text"))


def reapply_similar_subtitle_style(
    text: str,
    settings: dict[str, Any] | None = None,
    *,
    store_dir: str | None = None,
) -> tuple[str, dict[str, Any]]:
    updated, meta = apply_recent_editor_truth_patterns(text, settings or {}, store_dir=store_dir)
    if not meta:
        meta = {
            "schema": ONE_CLICK_FIX_SCHEMA,
            "task": "reapply_similar_style",
            "applied": False,
            "reason": "no_matching_editor_truth_pattern",
        }
    else:
        meta = dict(meta)
        meta["task"] = "reapply_similar_style"
    return updated, meta


def build_one_click_fix_request(
    action: str,
    segment: dict[str, Any] | None,
    *,
    reason: str = "",
) -> dict[str, Any]:
    seg = dict(segment or {})
    start = float(seg.get("start", 0.0) or 0.0)
    end = float(seg.get("end", start) or start)
    action_key = str(action or "").strip()
    return {
        "schema": ONE_CLICK_FIX_SCHEMA,
        "action": action_key,
        "label": ONE_CLICK_FIX_ACTIONS.get(action_key, action_key),
        "reason": str(reason or ""),
        "segment_id": str(seg.get("segment_id") or seg.get("id") or ""),
        "line": int(seg.get("line", -1) or -1),
        "start": round(start, 3),
        "end": round(end, 3),
        "text_preview": _clean_text(seg.get("text"))[:120],
        "requested_at": iso_now(),
        "request_id": stable_hash(
            {
                "action": action_key,
                "segment_id": str(seg.get("segment_id") or seg.get("id") or ""),
                "line": int(seg.get("line", -1) or -1),
                "start": round(start, 3),
                "end": round(end, 3),
                "text": _clean_text(seg.get("text")),
            }
        )[:24],
    }


__all__ = [
    "ONE_CLICK_FIX_ACTIONS",
    "ONE_CLICK_FIX_SCHEMA",
    "build_one_click_fix_request",
    "reapply_similar_subtitle_style",
    "subtitle_source_text_without_llm",
]
