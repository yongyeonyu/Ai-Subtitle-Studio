"""Persistent Subtitle Accuracy Graph artifacts."""
from __future__ import annotations

import json
import uuid
from itertools import islice
from pathlib import Path
from typing import Any, Iterable

from core.media_fingerprint import media_fingerprint_digest
from core.engine.subtitle_accuracy_pipeline import (
    SUBTITLE_ACCURACY_SCHEMA,
    subtitle_accuracy_metrics,
    subtitle_decision_explanations,
)
from core.personalization.lora_models import iso_now, stable_hash
from core.personalization.lora_storage import LORA_INTERNAL_CACHE_DIR


SUBTITLE_ACCURACY_GRAPH_SCHEMA = "ai_subtitle_studio.subtitle_accuracy_graph.v1"


def _json_safe(value: Any, *, max_depth: int = 8) -> Any:
    if max_depth <= 0:
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item, max_depth=max_depth - 1) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item, max_depth=max_depth - 1) for item in list(value)]
    return str(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _iter_dict_rows(rows: Any) -> Iterable[dict[str, Any]]:
    for row in (() if rows is None else rows):
        if isinstance(row, dict):
            yield row


def _sequence_head(rows: Any, limit: int) -> list[Any]:
    max_items = max(0, int(limit or 0))
    if max_items <= 0:
        return []
    if isinstance(rows, list):
        return rows[:max_items]
    if isinstance(rows, tuple):
        return list(rows[:max_items])
    return list(islice(() if rows is None else rows, max_items))


def _segment_id(segment: dict[str, Any], index: int) -> str:
    explicit = str(segment.get("id") or segment.get("segment_id") or "").strip()
    if explicit:
        return explicit
    return stable_hash(
        {
            "index": index,
            "start": round(_safe_float(segment.get("start", segment.get("timeline_start"))), 3),
            "end": round(_safe_float(segment.get("end", segment.get("timeline_end"))), 3),
            "text": str(segment.get("text") or "")[:160],
        }
    )[:20]


def _compact_stt_outputs(segment: dict[str, Any]) -> dict[str, Any]:
    outputs: dict[str, Any] = {}
    for key in (
        "stt_candidates",
        "stt_lattice_candidates",
        "vad_candidates",
        "stt_retry_candidates",
        "stt_recheck_candidates",
        "stt_rescue_candidates",
        "manual_stt_candidates",
        "manual_recheck_candidates",
        "manual_rerecognition_candidates",
        "manual_re_recognition_candidates",
        "stt_manual_candidates",
    ):
        compact_rows: list[dict[str, Any]] = []
        for item in _iter_dict_rows(segment.get(key)):
            compact_rows.append(
                {
                    "source": str(item.get("source") or item.get("label") or ""),
                    "text": str(item.get("text") or "")[:240],
                    "score": _json_safe(item.get("score", item.get("stt_score"))),
                    "confidence": _json_safe(item.get("confidence", item.get("confidence_score"))),
                }
            )
            if len(compact_rows) >= 10:
                break
        if compact_rows:
            outputs[key] = compact_rows
    for key in (
        "stt_ensemble_llm_selected_source",
        "stt_ensemble_llm_selected_label",
        "stt_ensemble_deep_selected_source",
        "stt_ensemble_deep_selected_label",
        "stt_ensemble_deep_selected_score",
        "stt_ensemble_deep_selected_margin",
        "stt_ensemble_needs_llm_review",
        "stt_selected_source",
    ):
        if key in segment:
            outputs[key] = _json_safe(segment.get(key))
    if "_stt_lattice_policy" in segment:
        outputs["stt_lattice_policy"] = _json_safe(segment.get("_stt_lattice_policy"))
    return outputs


def _compact_lora(segment: dict[str, Any]) -> dict[str, Any]:
    profile = dict(segment.get("_lora_generation_profile") or {})
    return {
        "segment_score": _json_safe(segment.get("_lora_segment_score")),
        "doc_count": _json_safe(segment.get("_lora_segment_doc_count")),
        "query": str(segment.get("_lora_segment_query") or "")[:500],
        "settings": _json_safe(segment.get("_lora_segment_settings") or {}),
        "gap_settings": _json_safe(segment.get("_lora_gap_settings") or {}),
        "profile": {
            "top_score": _json_safe(profile.get("top_score")),
            "used_kinds": _json_safe(profile.get("used_kinds") or {}),
            "examples": _json_safe(_sequence_head(profile.get("examples"), 6)),
            "setting_sources": _json_safe(_sequence_head(profile.get("setting_sources"), 6)),
            "style_hints": _json_safe(_sequence_head(profile.get("style_hints"), 6)),
            "exclusions": _json_safe(_sequence_head(profile.get("exclusions"), 6)),
        },
    }


def _compact_deep(segment: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "_deep_rerank_policy",
        "_deep_candidate_selector_policy",
        "_deep_timing_policy",
        "_timing_fusion_policy",
        "_deep_sequence_policy",
        "_output_selector_policy",
        "_context_consistency_policy",
        "_context_repair_policy",
        "_lora_style_policy",
        "_subtitle_bundle_policy",
        "_cut_boundary_guard_policy",
        "_uncertainty_policy",
        "_uncertainty_bucket",
        "_uncertainty_risk_score",
        "_uncertainty_schedule_summary",
        "_editor_truth_runtime_policy",
        "_user_edit_metrics",
        "_one_click_fix_request",
    )
    return {key.lstrip("_"): _json_safe(segment.get(key)) for key in keys if key in segment}


def _compact_llm(segment: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "_llm_gate_policy",
        "_llm_minimize_policy",
        "_llm_candidate_policy",
        "_llm_verifier_policy",
        "_llm_rollback_policy",
    )
    return {key.lstrip("_"): _json_safe(segment.get(key)) for key in keys if key in segment}


def _compact_timing(segment: dict[str, Any]) -> dict[str, Any]:
    start = _safe_float(segment.get("start", segment.get("timeline_start")), 0.0)
    end = _safe_float(segment.get("end", segment.get("timeline_end")), start)
    word_count = 0
    first_word = None
    last_word = None
    for item in _iter_dict_rows(segment.get("words")):
        word_count += 1
        if first_word is None:
            first_word = item
        last_word = item
    return {
        "start": round(start, 3),
        "end": round(end, 3),
        "duration_sec": round(max(0.0, end - start), 3),
        "word_count": word_count,
        "first_word": _json_safe(first_word) if first_word is not None else None,
        "last_word": _json_safe(last_word) if last_word is not None else None,
        "timing_policy": _json_safe(segment.get("_deep_timing_policy") or {}),
        "timing_fusion_policy": _json_safe(segment.get("_timing_fusion_policy") or {}),
        "gap_settings": _json_safe(segment.get("_lora_gap_settings") or {}),
    }


def build_subtitle_accuracy_graph(
    segments: Iterable[dict[str, Any]] | None,
    settings: dict[str, Any] | None = None,
    *,
    media_path: str = "",
    project_path: str = "",
) -> dict[str, Any]:
    rows = [row for row in _iter_dict_rows(segments) if not row.get("is_gap")]
    explanations = subtitle_decision_explanations(rows)
    explanations_by_index = {int(item.get("index", idx)): item for idx, item in enumerate(explanations)}
    segment_graphs: list[dict[str, Any]] = []
    rollback_count = 0
    llm_called_count = 0
    llm_skipped_count = 0
    for index, segment in enumerate(rows):
        graph = dict(segment.get("_accuracy_decision_graph") or {})
        if graph.get("schema") != SUBTITLE_ACCURACY_SCHEMA:
            graph = {"schema": SUBTITLE_ACCURACY_SCHEMA, "decisions": []}
        llm_payload = _compact_llm(segment)
        llm_gate_policy = llm_payload.get("llm_gate_policy") if isinstance(llm_payload, dict) else {}
        if isinstance(llm_gate_policy, dict):
            call_llm = llm_gate_policy.get("call_llm")
            if call_llm:
                llm_called_count += 1
            elif call_llm is False:
                llm_skipped_count += 1
        if llm_payload.get("llm_rollback_policy"):
            rollback_count += 1
        verifier_decisions = [
            item
            for item in _iter_dict_rows(graph.get("decisions"))
            if str(item.get("task") or "") in {"llm_verifier", "llm_rollback", "llm_candidate_policy", "llm_minimize"}
        ]
        segment_graphs.append(
            {
                "segment_id": _segment_id(segment, index),
                "index": index,
                "start": round(_safe_float(segment.get("start", segment.get("timeline_start"))), 3),
                "end": round(_safe_float(segment.get("end", segment.get("timeline_end"))), 3),
                "text": str(segment.get("text") or ""),
                "speaker": str(segment.get("speaker") or ""),
                "raw_stt_outputs": _compact_stt_outputs(segment),
                "lora": _compact_lora(segment),
                "deep_learning": _compact_deep(segment),
                "llm": llm_payload,
                "verifier_decisions": _json_safe(verifier_decisions),
                "timing": _compact_timing(segment),
                "decision_graph": _json_safe(graph),
                "final_explanation": _json_safe(explanations_by_index.get(index, {})),
            }
        )
    metrics = subtitle_accuracy_metrics(rows, settings or {})
    try:
        media_digest = media_fingerprint_digest(media_path, sample_bytes=0, include_samples=False) if media_path else ""
    except Exception:
        media_digest = ""
    return {
        "schema": SUBTITLE_ACCURACY_GRAPH_SCHEMA,
        "created_at": iso_now(),
        "media_path": str(media_path or ""),
        "media_fingerprint_digest": media_digest,
        "project_path": str(project_path or ""),
        "segment_count": len(segment_graphs),
        "summary": {
            "metrics": _json_safe(metrics),
            "rollback_count": rollback_count,
            "llm_called_count": llm_called_count,
            "llm_skipped_count": llm_skipped_count,
        },
        "segments": segment_graphs,
    }


def accuracy_graph_artifact_path(
    *,
    project_path: str = "",
    media_path: str = "",
    cache_dir: str | Path | None = None,
) -> Path:
    if project_path:
        path = Path(project_path)
        return path.with_name(f"{path.stem}.subtitle_accuracy_graph.json")
    root = Path(cache_dir) if cache_dir else Path(LORA_INTERNAL_CACHE_DIR) / "accuracy_graphs"
    try:
        media_digest = media_fingerprint_digest(media_path, sample_bytes=0, include_samples=False) if media_path else ""
    except Exception:
        media_digest = ""
    key = stable_hash({"media_path": str(media_path or ""), "media_fingerprint_digest": media_digest, "project_path": str(project_path or "")})[:20]
    return root / f"{key}.subtitle_accuracy_graph.json"


def persist_subtitle_accuracy_graph(
    segments: Iterable[dict[str, Any]] | None,
    settings: dict[str, Any] | None = None,
    *,
    media_path: str = "",
    project_path: str = "",
    cache_dir: str | Path | None = None,
) -> dict[str, Any]:
    settings = dict(settings or {})
    enabled = settings.get("accuracy_graph_persist_enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in {"0", "false", "off", "no", "끔"}
    if not enabled:
        return {"schema": SUBTITLE_ACCURACY_GRAPH_SCHEMA, "enabled": False, "path": ""}
    graph = build_subtitle_accuracy_graph(segments, settings, media_path=media_path, project_path=project_path)
    path = accuracy_graph_artifact_path(project_path=project_path, media_path=media_path, cache_dir=cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
    return {
        "schema": SUBTITLE_ACCURACY_GRAPH_SCHEMA,
        "enabled": True,
        "path": str(path),
        "segment_count": graph["segment_count"],
        "summary": graph["summary"],
    }


__all__ = [
    "SUBTITLE_ACCURACY_GRAPH_SCHEMA",
    "accuracy_graph_artifact_path",
    "build_subtitle_accuracy_graph",
    "persist_subtitle_accuracy_graph",
]
