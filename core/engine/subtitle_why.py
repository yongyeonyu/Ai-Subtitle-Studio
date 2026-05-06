from __future__ import annotations

from typing import Any

from core.engine.subtitle_accuracy_pipeline import subtitle_decision_explanations


SUBTITLE_WHY_SCHEMA = "ai_subtitle_studio.subtitle_why_panel.v1"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _text_preview(value: Any, limit: int = 120) -> str:
    return " ".join(str(value or "").split())[: max(1, int(limit or 120))]


def _lora_examples(profile: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in list(profile.get("examples") or []):
        if isinstance(item, str):
            text = _text_preview(item)
            payload = {"text": text, "score": None, "kind": "example"}
        elif isinstance(item, dict):
            text = _text_preview(
                item.get("output")
                or item.get("corrected")
                or item.get("subtitle")
                or item.get("speech_training_text")
                or item.get("text")
                or item.get("input")
            )
            payload = {
                "text": text,
                "score": item.get("score", item.get("retrieval_score")),
                "kind": item.get("kind") or item.get("source") or "example",
                "line_break_pattern": item.get("line_break_pattern"),
            }
        else:
            continue
        if text:
            out.append(payload)
        if len(out) >= max(1, int(limit or 3)):
            break
    return out


def _stt_candidates(segment: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in (
        "stt_candidates",
        "stt_lattice_candidates",
        "vad_candidates",
        "stt_retry_candidates",
        "stt_recheck_candidates",
        "stt_rescue_candidates",
    ):
        for item in list(segment.get(key) or []):
            if not isinstance(item, dict):
                continue
            text = _text_preview(item.get("text") or item.get("output"))
            if not text:
                continue
            out.append(
                {
                    "family": key,
                    "source": item.get("source") or item.get("label") or key,
                    "text": text,
                    "score": item.get("score", item.get("stt_score", item.get("confidence"))),
                    "selected": str(item.get("source") or "").strip().upper()
                    == str(segment.get("stt_selected_source") or segment.get("stt_ensemble_source") or "").strip().upper(),
                }
            )
            if len(out) >= max(1, int(limit or 6)):
                return out
    return out


def _llm_summary(explanation: dict[str, Any], segment: dict[str, Any]) -> dict[str, Any]:
    gate = dict(explanation.get("llm_gate") or segment.get("_llm_gate_policy") or {})
    candidate = dict(explanation.get("llm_candidate_policy") or segment.get("_llm_candidate_policy") or {})
    verifier = dict(explanation.get("llm_verifier") or segment.get("_llm_verifier_policy") or {})
    rollback = dict(explanation.get("rollback") or segment.get("_llm_rollback_policy") or {})
    return {
        "called": gate.get("call_llm"),
        "gate_reason": gate.get("reason"),
        "gate_confidence": gate.get("confidence"),
        "candidate_reason": candidate.get("reason"),
        "candidate_accepted": candidate.get("accepted"),
        "verifier_accepted": verifier.get("accepted"),
        "verifier_reason": verifier.get("reason"),
        "rollback": rollback,
    }


def build_subtitle_why_payload(
    segment: dict[str, Any],
    *,
    index: int = 0,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seg = dict(segment or {})
    explanation = subtitle_decision_explanations([seg])[0] if seg else {}
    profile = dict(seg.get("_lora_generation_profile") or {})
    cut_guard = dict(seg.get("_cut_boundary_guard_policy") or explanation.get("cut_boundary_guard") or {})
    lora_score = _safe_float(explanation.get("lora_score", profile.get("top_score")), 0.0)
    return {
        "schema": SUBTITLE_WHY_SCHEMA,
        "index": int(index or 0),
        "segment_id": str(seg.get("segment_id") or seg.get("id") or index),
        "start": round(_safe_float(seg.get("start"), 0.0), 3),
        "end": round(_safe_float(seg.get("end"), 0.0), 3),
        "text": str(seg.get("text") or ""),
        "summary": {
            "actions": list(explanation.get("actions") or []),
            "lora_score": round(lora_score, 4),
            "decision_count": explanation.get("decision_count", 0),
            "quality": dict(seg.get("quality") or {}),
        },
        "lora": {
            "top_score": profile.get("top_score", lora_score),
            "used_kinds": dict(profile.get("used_kinds") or {}),
            "applied_settings": dict(profile.get("applied_settings") or {}),
            "examples": _lora_examples(profile),
        },
        "stt_candidates": _stt_candidates(seg),
        "llm": _llm_summary(explanation, seg),
        "cut_boundary": {
            "action": cut_guard.get("action"),
            "confidence": cut_guard.get("confidence"),
            "scene_start": cut_guard.get("scene_start"),
            "scene_end": cut_guard.get("scene_end"),
            "evidence": dict(cut_guard.get("evidence") or {}),
        },
        "deep": {
            "timing": dict(seg.get("_deep_timing_policy") or {}),
            "rerank": dict(seg.get("_deep_rerank_policy") or {}),
            "sequence": dict(seg.get("_deep_sequence_policy") or {}),
            "user_edit_metrics": dict(seg.get("_user_edit_metrics") or {}),
        },
    }


def format_subtitle_why_text(payload: dict[str, Any]) -> str:
    data = dict(payload or {})
    lines: list[str] = []
    lines.append(f"자막: {_text_preview(data.get('text'), 200)}")
    lines.append(f"시간: {data.get('start', 0):.3f}s → {data.get('end', 0):.3f}s")
    summary = dict(data.get("summary") or {})
    actions = [str(item) for item in list(summary.get("actions") or [])]
    lines.append("결정: " + (" / ".join(actions) if actions else "추가 정책 없음"))
    lines.append(f"LoRA 점수: {summary.get('lora_score', 0)}")

    lora = dict(data.get("lora") or {})
    examples = list(lora.get("examples") or [])
    lines.append("")
    lines.append("[LoRA 근거]")
    if examples:
        for idx, item in enumerate(examples, start=1):
            score = item.get("score")
            score_text = "" if score is None else f" · {score}"
            lines.append(f"{idx}. {item.get('kind', 'example')}{score_text}: {item.get('text', '')}")
    else:
        lines.append("LoRA 예시 없음")

    lines.append("")
    lines.append("[STT 후보]")
    candidates = list(data.get("stt_candidates") or [])
    if candidates:
        for idx, item in enumerate(candidates, start=1):
            selected = " 선택" if item.get("selected") else ""
            score = item.get("score")
            score_text = "" if score is None else f" · {score}"
            lines.append(f"{idx}. {item.get('source')}{selected}{score_text}: {item.get('text')}")
    else:
        lines.append("STT 후보 없음")

    llm = dict(data.get("llm") or {})
    lines.append("")
    lines.append("[LLM]")
    called = llm.get("called")
    called_text = "호출" if called is True else "스킵" if called is False else "기록 없음"
    lines.append(f"{called_text}: {llm.get('gate_reason') or '-'}")
    if llm.get("candidate_reason"):
        lines.append(f"후보 정책: {llm.get('candidate_reason')} / accepted={llm.get('candidate_accepted')}")
    if llm.get("verifier_reason"):
        lines.append(f"검증: {llm.get('verifier_reason')} / accepted={llm.get('verifier_accepted')}")
    if llm.get("rollback"):
        lines.append(f"롤백: {llm.get('rollback')}")

    cut = dict(data.get("cut_boundary") or {})
    lines.append("")
    lines.append("[컷 경계]")
    lines.append(f"동작: {cut.get('action') or '-'} / confidence={cut.get('confidence') or '-'}")
    evidence = dict(cut.get("evidence") or {})
    if evidence:
        lines.append("근거: " + ", ".join(f"{key}={value}" for key, value in evidence.items()))
    return "\n".join(lines)


__all__ = [
    "SUBTITLE_WHY_SCHEMA",
    "build_subtitle_why_payload",
    "format_subtitle_why_text",
]
