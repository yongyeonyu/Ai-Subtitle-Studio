from __future__ import annotations

import difflib
import json
import re
from typing import Any

from core.native_swift_subtitle_core import run_subtitle_core_operation_via_swift


CONTEXT_SCHEMA = "ai_subtitle_studio.subtitle_llm_context_pack.v1"
GATE_SCHEMA = "ai_subtitle_studio.subtitle_llm_context_gate.v1"


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).lower()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _round3(value: Any) -> float:
    return round(_safe_float(value), 3)


def _candidate_rows(row: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(text: Any, source: Any, rank: int) -> None:
        cleaned = _clean_text(text)
        key = _compact(cleaned)
        if not key or key in seen or len(out) >= limit:
            return
        seen.add(key)
        out.append(
            {
                "rank": int(rank),
                "source": str(source or "").strip(),
                "text": cleaned[:96],
                "compact_len": len(key),
            }
        )

    selected_source = (
        row.get("stt_selected_source")
        or row.get("stt_ensemble_source")
        or row.get("stt_ensemble_llm_selected_source")
        or row.get("source")
        or "CURRENT"
    )
    add(row.get("text"), selected_source, 0)
    for index, candidate in enumerate(list(row.get("stt_candidates") or []), start=1):
        if not isinstance(candidate, dict):
            continue
        add(candidate.get("text"), candidate.get("source") or candidate.get("stt_source") or "STT", index)
    return out


def _row_summary(index: int, role: str, row: dict[str, Any] | None, *, limit: int = 5) -> dict[str, Any]:
    if not isinstance(row, dict) or not row:
        return {"index": index, "role": role, "exists": False, "text": "", "candidates": []}
    return {
        "index": int(index),
        "role": role,
        "exists": True,
        "start": _round3(row.get("start")),
        "end": _round3(row.get("end")),
        "text": _clean_text(row.get("text")),
        "selected_source": str(
            row.get("stt_selected_source")
            or row.get("stt_ensemble_source")
            or row.get("stt_ensemble_llm_selected_source")
            or row.get("source")
            or ""
        ).strip(),
        "candidates": _candidate_rows(row, limit=limit),
    }


def _vad_summary(vad_segments: list[dict[str, Any]], start: float, end: float) -> dict[str, Any]:
    duration = max(0.001, float(end) - float(start))
    hints: list[dict[str, float]] = []
    overlap = 0.0
    for row in list(vad_segments or []):
        if not isinstance(row, dict):
            continue
        vad_start = _safe_float(row.get("start"))
        vad_end = _safe_float(row.get("end"), vad_start)
        if vad_end < start - 0.4 or vad_start > end + 0.4:
            continue
        clipped_start = max(start, vad_start)
        clipped_end = min(end, vad_end)
        if clipped_end > clipped_start:
            overlap += clipped_end - clipped_start
        if len(hints) < 8:
            hints.append({"start": round(vad_start, 3), "end": round(vad_end, 3)})
    return {"speech_overlap_ratio": round(min(1.0, max(0.0, overlap / duration)), 3), "hints": hints}


def _fallback_context_packs(
    segments: list[dict[str, Any]],
    vad_segments: list[dict[str, Any]] | None = None,
    *,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows = [dict(row) for row in list(segments or []) if isinstance(row, dict)]
    vad_rows = [dict(row) for row in list(vad_segments or []) if isinstance(row, dict)]
    limit = max(1, min(8, int(_safe_float((settings or {}).get("subtitle_llm_context_candidate_limit"), 5))))
    packs: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        start = _safe_float(row.get("start"))
        end = _safe_float(row.get("end"), start)
        packs.append(
            {
                "schema": CONTEXT_SCHEMA,
                "index": index,
                "window": {
                    "previous": _row_summary(index - 1, "previous", rows[index - 1] if index > 0 else None, limit=limit),
                    "current": _row_summary(index, "current", row, limit=limit),
                    "next": _row_summary(index + 1, "next", rows[index + 1] if index + 1 < len(rows) else None, limit=limit),
                },
                "vad": _vad_summary(vad_rows, start, end),
                "constraints": {
                    "llm_role": "advisory_only",
                    "current_subtitle_required": True,
                    "previous_next_are_context_only": True,
                    "forbidden": ["invent_words", "replace_current_with_neighbor", "move_time_outside_vad_stt_span"],
                },
            }
        )
    return packs


def build_subtitle_llm_context_packs_via_swift(
    segments: list[dict[str, Any]],
    vad_segments: list[dict[str, Any]] | None = None,
    *,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    payload = {
        "segments": list(segments or []),
        "vad_segments": list(vad_segments or []),
        "settings": dict(settings or {}),
    }
    native = run_subtitle_core_operation_via_swift(
        "subtitle_llm_context_plan",
        payload,
        settings=settings,
        context={"bridge": "native_swift_subtitle_llm_context"},
    )
    if isinstance(native, dict) and native.get("schema") == CONTEXT_SCHEMA:
        packs = native.get("packs")
        if isinstance(packs, list):
            return [dict(item) for item in packs if isinstance(item, dict)]
    return _fallback_context_packs(segments, vad_segments, settings=settings)


def _context_candidate_texts(context_pack: dict[str, Any] | None, roles: tuple[str, ...]) -> list[str]:
    window = dict((context_pack or {}).get("window") or {})
    out: list[str] = []
    seen: set[str] = set()
    for role in roles:
        row = dict(window.get(role) or {})
        for text in [row.get("text")] + [item.get("text") for item in list(row.get("candidates") or []) if isinstance(item, dict)]:
            cleaned = _clean_text(text)
            key = _compact(cleaned)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(cleaned)
    return out


def _similarity(left: Any, right: Any) -> float:
    a = _compact(left)
    b = _compact(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return float(difflib.SequenceMatcher(None, a, b).ratio())


def _fallback_context_gate(
    source_text: str,
    chunks: list[str],
    context_pack: dict[str, Any] | None = None,
    *,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output = _clean_text(" ".join(str(chunk or "") for chunk in chunks))
    if not output:
        return {"schema": GATE_SCHEMA, "backend": "python_fallback", "accepted": False, "reason": "empty_output"}
    settings = dict(settings or {})
    min_current = max(0.5, min(1.0, _safe_float(settings.get("subtitle_llm_context_min_current_similarity"), 0.86)))
    neighbor_margin = max(0.0, min(0.30, _safe_float(settings.get("subtitle_llm_context_neighbor_reject_margin"), 0.06)))
    current = _context_candidate_texts(context_pack, ("current",)) or [_clean_text(source_text)]
    neighbors = _context_candidate_texts(context_pack, ("previous", "next"))
    current_best = max((_similarity(output, text), text) for text in current) if current else (0.0, "")
    neighbor_best = max((_similarity(output, text), text) for text in neighbors) if neighbors else (0.0, "")
    source_sim = _similarity(output, source_text)
    if neighbor_best[0] >= min_current and neighbor_best[0] > current_best[0] + neighbor_margin:
        accepted = False
        reason = "neighbor_context_takeover"
    elif current_best[0] < min_current and source_sim < min_current:
        accepted = False
        reason = "not_supported_by_current_stt_context"
    else:
        accepted = True
        reason = "stt_vad_context_supported"
    return {
        "schema": GATE_SCHEMA,
        "backend": "python_fallback",
        "accepted": accepted,
        "reason": reason,
        "source_similarity": round(source_sim, 3),
        "current_context_similarity": round(float(current_best[0]), 3),
        "neighbor_context_similarity": round(float(neighbor_best[0]), 3),
        "matched_current_text": str(current_best[1])[:96],
    }


def evaluate_subtitle_llm_context_gate_via_swift(
    source_text: str,
    chunks: list[str] | None,
    context_pack: dict[str, Any] | None = None,
    *,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "source_text": str(source_text or ""),
        "chunks": [str(chunk or "") for chunk in list(chunks or [])],
        "context_pack": dict(context_pack or {}),
        "settings": dict(settings or {}),
    }
    native = run_subtitle_core_operation_via_swift(
        "subtitle_llm_context_gate",
        payload,
        settings=settings,
        context={"bridge": "native_swift_subtitle_llm_context_gate"},
    )
    if isinstance(native, dict) and native.get("schema") == GATE_SCHEMA:
        return native
    return _fallback_context_gate(source_text, [str(chunk or "") for chunk in list(chunks or [])], context_pack, settings=settings)


def format_subtitle_llm_context_for_prompt(context_pack: dict[str, Any] | None) -> str:
    if not isinstance(context_pack, dict) or not context_pack:
        return ""
    payload = {
        "schema": context_pack.get("schema") or CONTEXT_SCHEMA,
        "index": context_pack.get("index"),
        "window": context_pack.get("window") or {},
        "vad": context_pack.get("vad") or {},
        "constraints": context_pack.get("constraints") or {},
    }
    return (
        "[이전/현재/다음 STT/VAD 문맥 - Swift]\n"
        "아래 window에서 previous/next는 문맥 참고용이고, current가 현재 자막의 원본입니다.\n"
        "STT1/STT2 후보와 VAD span이 현재 자막의 기준이며, 이전/다음 후보를 현재 자막으로 가져오면 실패입니다.\n"
        "LLM은 오타수정/합치기/나누기 제안만 하고, 새 단어 생성이나 시간 이동 확정은 금지입니다.\n"
        f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
    )


__all__ = [
    "CONTEXT_SCHEMA",
    "GATE_SCHEMA",
    "build_subtitle_llm_context_packs_via_swift",
    "evaluate_subtitle_llm_context_gate_via_swift",
    "format_subtitle_llm_context_for_prompt",
]
