from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.personalization.ground_truth_import import (
    _detect_split_rule,
    _punctuation_pattern,
    extract_parenthetical_segments,
)
from core.personalization.lora_models import (
    ExcludedParentheticalRow,
    TrainingQueueItem,
    TruthTableRow,
    line_break_pattern_for_text,
    stable_hash,
)
from core.personalization.subtitle_style_profile import build_subtitle_style_profile
from core.personalization.editor_truth_memory import append_editor_truth_patterns
from core.personalization.lora_storage import (
    append_excluded_parentheticals,
    append_truth_table_rows,
    refresh_unified_lora_data_bundle,
)
from core.personalization.lora_store_records import upsert_training_queue_items
from core.personalization.user_edit_metrics import (
    measure_user_edit_metrics,
    user_edit_metric_reasons,
)


EDITOR_TRUTH_CAPTURE_SCHEMA = "ai_subtitle_studio.editor_truth_capture.v1"

_SETTING_SNAPSHOT_KEYS = (
    "selected_audio_ai",
    "selected_vad",
    "selected_whisper_model",
    "selected_whisper_model_secondary",
    "selected_model",
    "selected_llm_provider",
    "stt_quality_preset",
    "split_length_threshold",
    "continuous_threshold",
    "gap_push_rate",
    "gap_pull_rate",
    "single_subtitle_end",
    "sub_min_duration",
    "sub_max_duration",
    "sub_max_cps",
    "sub_gap_break_sec",
    "subtitle_bundle_target_sec",
    "subtitle_bundle_min_sec",
    "subtitle_bundle_max_sec",
    "subtitle_bundle_lora_blend",
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except Exception:
            pass
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except Exception:
        return str(value)


def _normalize_path(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return str(Path(raw).expanduser())
    except Exception:
        return raw


def _media_id_for_segment(media_path: str, project_path: str) -> str:
    return stable_hash(
        {
            "media_path": _normalize_path(media_path),
            "project_path": _normalize_path(project_path),
        }
    )[:20]


def _segment_id(seg: dict[str, Any], index: int, media_path: str) -> str:
    explicit = str(seg.get("segment_id") or seg.get("id") or "").strip()
    if explicit:
        return explicit
    return stable_hash(
        {
            "media_path": _normalize_path(media_path),
            "line": _safe_int(seg.get("line"), index),
            "start": round(_safe_float(seg.get("start")), 3),
            "end": round(_safe_float(seg.get("end"), _safe_float(seg.get("start"))), 3),
            "text": str(seg.get("text") or "").strip(),
        }
    )[:24]


def _settings_snapshot(settings: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(settings or {})
    return {key: _json_safe(raw[key]) for key in _SETTING_SNAPSHOT_KEYS if key in raw}


def _quality_snapshot(seg: dict[str, Any]) -> dict[str, Any]:
    quality = dict(seg.get("quality") or {})
    snapshot: dict[str, Any] = {}
    for key in ("score", "label", "flags", "components"):
        value = quality.get(key)
        if value not in (None, "", [], {}):
            snapshot[key] = _json_safe(value)
    for key in (
        "score",
        "stt_score",
        "score_color",
        "stt_score_color",
        "stt_score_label",
        "stt_score_flags",
        "stt_score_components",
        "quality_stale",
    ):
        value = seg.get(key)
        if value not in (None, "", [], {}):
            snapshot[key] = _json_safe(value)
    return snapshot


def _candidate_snapshot(seg: dict[str, Any]) -> dict[str, Any]:
    candidates = []
    for item in list(seg.get("stt_candidates") or [])[:8]:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("output") or "").strip()
        if not text:
            continue
        candidates.append(
            {
                "source": str(item.get("source") or item.get("label") or "").strip(),
                "text": text[:240],
                "score": _json_safe(item.get("score", item.get("stt_score"))),
                "confidence": _json_safe(item.get("confidence")),
            }
        )
    snapshot = {
        "selected_source": str(seg.get("stt_selected_source") or "").strip(),
        "llm_selected_source": str(seg.get("stt_ensemble_llm_selected_source") or "").strip(),
        "ensemble_source": str(seg.get("stt_ensemble_source") or "").strip(),
        "ensemble_label": str(seg.get("stt_ensemble_llm_selected_label") or "").strip(),
        "needs_llm_review": bool(seg.get("stt_ensemble_needs_llm_review", False)),
        "inserted_from_stt2": bool(seg.get("stt_ensemble_inserted_from_stt2", False)),
        "candidates": candidates,
    }
    return {key: value for key, value in snapshot.items() if value not in (None, "", [], {})}


def _hard_case_reasons(seg: dict[str, Any], text: str, edit_metrics: dict[str, Any] | None = None) -> list[str]:
    reasons: list[str] = []
    if bool(seg.get("stt_ensemble_needs_llm_review", False)):
        reasons.append("stt_ensemble_llm_review")
    if bool(seg.get("quality_stale", False)):
        reasons.append("quality_stale_after_edit")
    for score_key in ("score", "stt_score"):
        value = seg.get(score_key)
        if value is None:
            continue
        try:
            if float(value) < 80.0:
                reasons.append(f"low_{score_key}")
        except Exception:
            pass
    original = str(seg.get("original_text") or seg.get("dictated_text") or "").strip()
    if original and original != text:
        reasons.append("user_text_changed")
    reasons.extend(user_edit_metric_reasons(edit_metrics or {}))
    if len(text.replace("\n", "")) > 42:
        reasons.append("long_subtitle")
    return sorted(dict.fromkeys(reasons))


def build_editor_truth_records(
    segments: list[dict[str, Any]] | None,
    *,
    media_path: str = "",
    subtitle_path: str = "",
    project_path: str = "",
    trigger: str = "manual_save",
    settings: dict[str, Any] | None = None,
    min_chars: int = 2,
    max_chars: int = 240,
) -> dict[str, Any]:
    truth_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []
    skipped = {
        "gap": 0,
        "pending": 0,
        "empty": 0,
        "too_short": 0,
        "too_long": 0,
        "invalid_time": 0,
    }
    settings_payload = _settings_snapshot(settings)

    source_segments = list(segments or [])
    for index, raw_seg in enumerate(source_segments):
        seg = dict(raw_seg or {})
        if bool(seg.get("is_gap", False)):
            skipped["gap"] += 1
            continue
        if bool(seg.get("stt_pending", False)) or bool(seg.get("live_preview", False)):
            skipped["pending"] += 1
            continue
        text = str(seg.get("text") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            skipped["empty"] += 1
            continue

        extracted = extract_parenthetical_segments(text)
        speech_text = str(extracted.get("speech_training_text") or "").strip()
        speech_chars = len(speech_text.replace("\n", "").replace(" ", ""))
        if speech_chars <= 0:
            skipped["empty"] += 1
            continue
        if speech_chars < max(1, int(min_chars)):
            skipped["too_short"] += 1
            continue
        if speech_chars > max(1, int(max_chars)):
            skipped["too_long"] += 1
            continue

        start_sec = _safe_float(seg.get("start"), 0.0)
        end_sec = _safe_float(seg.get("end"), start_sec)
        if end_sec <= start_sec:
            skipped["invalid_time"] += 1
            continue
        previous_seg = source_segments[index - 1] if index > 0 and isinstance(source_segments[index - 1], dict) else None
        next_seg = source_segments[index + 1] if index + 1 < len(source_segments) and isinstance(source_segments[index + 1], dict) else None
        previous_end_sec = _safe_float(previous_seg.get("end"), start_sec) if previous_seg else None
        next_start_sec = _safe_float(next_seg.get("start"), end_sec) if next_seg else None

        seg_media_path = _normalize_path(seg.get("_clip_file") or seg.get("media_path") or media_path)
        media_id = str(seg.get("media_id") or "").strip() or _media_id_for_segment(seg_media_path, project_path)
        segment_id = _segment_id(seg, index, seg_media_path)
        speaker = str(seg.get("speaker") or seg.get("spk") or "").strip()
        source_before_edit = str(seg.get("original_text") or seg.get("dictated_text") or "").strip()
        edit_metrics = measure_user_edit_metrics(
            {**seg, "source_before_edit": source_before_edit},
            final_text=text,
            final_speech_text=speech_text,
            start_sec=start_sec,
            end_sec=end_sec,
        )
        hard_case_reasons = _hard_case_reasons(seg, text, edit_metrics)
        extra = {
            "schema_source": EDITOR_TRUTH_CAPTURE_SCHEMA,
            "source": "editor_saved_subtitle",
            "trigger": str(trigger or "manual_save"),
            "project_path": _normalize_path(project_path),
            "line": _safe_int(seg.get("line"), index),
            "editor_segment_index": index,
            "edited_in_editor": True,
            "settings_snapshot": settings_payload,
            "quality_snapshot": _quality_snapshot(seg),
            "stt_candidate_snapshot": _candidate_snapshot(seg),
            "source_before_edit": source_before_edit,
            "user_edit_metrics": edit_metrics,
            "style_profile": build_subtitle_style_profile(
                raw_text=text,
                speech_text=speech_text,
                start_sec=start_sec,
                end_sec=end_sec,
                previous_end_sec=previous_end_sec,
                next_start_sec=next_start_sec,
            ),
            "hard_case": bool(hard_case_reasons),
            "hard_case_reasons": hard_case_reasons,
        }
        if seg.get("_clip_idx") is not None:
            extra["clip_index"] = _safe_int(seg.get("_clip_idx"), 0)

        truth_rows.append(
            TruthTableRow(
                media_id=media_id,
                media_path=seg_media_path,
                subtitle_path=_normalize_path(subtitle_path),
                segment_id=segment_id,
                start_sec=start_sec,
                end_sec=end_sec,
                raw_ground_truth_text=text,
                speech_training_text=speech_text,
                excluded_parenthetical_text=str(extracted.get("excluded_parenthetical_text") or ""),
                line_break_pattern=line_break_pattern_for_text(speech_text),
                punctuation_pattern=_punctuation_pattern(text),
                detected_split_rule=_detect_split_rule(speech_text),
                speaker_or_voice_hint=speaker,
                extra=_json_safe(extra),
            ).to_record()
        )

        excluded_text = str(extracted.get("excluded_parenthetical_text") or "").strip()
        if excluded_text:
            excluded_rows.append(
                ExcludedParentheticalRow(
                    media_id=media_id,
                    media_path=seg_media_path,
                    subtitle_path=_normalize_path(subtitle_path),
                    segment_id=segment_id,
                    original_text=text,
                    excluded_text=excluded_text,
                    kept_text=speech_text,
                ).to_record()
            )

    return {
        "schema": EDITOR_TRUTH_CAPTURE_SCHEMA,
        "truth_rows": truth_rows,
        "excluded_parenthetical_rows": excluded_rows,
        "stats": {
            "input_segments": len(list(segments or [])),
            "truth_rows": len(truth_rows),
            "excluded_parenthetical_rows": len(excluded_rows),
            **skipped,
        },
    }


def _enqueue_truth_capture_jobs(
    *,
    trigger: str,
    appended_rows: int,
    excluded_rows: int,
    store_dir: str | Path | None,
) -> dict[str, Any]:
    changed_rows = int(appended_rows or 0) + int(excluded_rows or 0)
    if changed_rows <= 0:
        return {"queued": False, "reason": "no_new_rows", "items": 0}
    batch_id = stable_hash(
        {
            "trigger": str(trigger or ""),
            "appended_rows": int(appended_rows or 0),
            "excluded_rows": int(excluded_rows or 0),
        }
    )[:12]
    payload = {
        "auto_maintenance": True,
        "trigger": str(trigger or ""),
        "batch_id": batch_id,
        "new_rows": {
            "truth": int(appended_rows or 0),
            "excluded_parentheticals": int(excluded_rows or 0),
        },
    }
    items = [
        TrainingQueueItem(
            media_id="global",
            media_path="",
            subtitle_path="",
            job_type="analyze_truth_table",
            job_id=f"editor-truth-rules-{batch_id}",
            priority=12,
            payload=payload,
        ).to_record(),
        TrainingQueueItem(
            media_id="global",
            media_path="",
            subtitle_path="",
            job_type="build_text_training_plan",
            job_id=f"editor-truth-text-{batch_id}",
            priority=24,
            payload=payload,
        ).to_record(),
    ]
    result = upsert_training_queue_items(items, store_dir)
    return {"queued": True, "batch_id": batch_id, "items": len(list(result.get("items") or []))}


def capture_editor_truth_records(
    segments: list[dict[str, Any]] | None,
    *,
    media_path: str = "",
    subtitle_path: str = "",
    project_path: str = "",
    trigger: str = "manual_save",
    settings: dict[str, Any] | None = None,
    store_dir: str | Path | None = None,
    enabled: bool = True,
    min_chars: int = 2,
    max_chars: int = 240,
    refresh_bundle: bool = True,
) -> dict[str, Any]:
    if not enabled:
        return {
            "schema": EDITOR_TRUTH_CAPTURE_SCHEMA,
            "enabled": False,
            "appended_rows": 0,
            "excluded_parenthetical_rows": 0,
        }

    built = build_editor_truth_records(
        segments,
        media_path=media_path,
        subtitle_path=subtitle_path,
        project_path=project_path,
        trigger=trigger,
        settings=settings,
        min_chars=min_chars,
        max_chars=max_chars,
    )
    truth_rows = list(built.get("truth_rows") or [])
    excluded_rows = list(built.get("excluded_parenthetical_rows") or [])
    truth_result = append_truth_table_rows(truth_rows, store_dir) if truth_rows else {"appended_rows": 0}
    excluded_result = (
        append_excluded_parentheticals(excluded_rows, store_dir)
        if excluded_rows
        else {"appended_rows": 0}
    )
    appended = int(truth_result.get("appended_rows", 0) or 0)
    excluded_appended = int(excluded_result.get("appended_rows", 0) or 0)
    queue_result = _enqueue_truth_capture_jobs(
        trigger=trigger,
        appended_rows=appended,
        excluded_rows=excluded_appended,
        store_dir=store_dir,
    )
    pattern_result = append_editor_truth_patterns(truth_rows, store_dir) if appended else {
        "appended_patterns": 0,
        "total_patterns": 0,
    }
    metric_event_result: dict[str, Any] = {"status": "skipped", "appended_rows": 0, "queued_hard_cases": 0}
    if appended and bool(dict(settings or {}).get("user_edit_metrics_enabled", True)):
        try:
            from core.personalization.deep_policy_learning import record_user_edit_metric_events_for_truth_rows

            metric_event_result = record_user_edit_metric_events_for_truth_rows(
                truth_rows,
                settings=settings,
                store_dir=str(store_dir) if store_dir is not None else None,
            )
        except Exception as exc:
            metric_event_result = {"status": "error", "error": str(exc), "appended_rows": 0, "queued_hard_cases": 0}
    bundle_result: dict[str, Any] = {"refreshed": False}
    if refresh_bundle and (appended or excluded_appended):
        try:
            bundle_result = refresh_unified_lora_data_bundle(store_dir, force=False)
        except Exception as exc:
            bundle_result = {"refreshed": False, "error": str(exc)}
    return {
        "schema": EDITOR_TRUTH_CAPTURE_SCHEMA,
        "enabled": True,
        "truth_path": str(truth_result.get("path", "") or ""),
        "appended_rows": appended,
        "total_rows": int(truth_result.get("total_rows", 0) or 0),
        "excluded_parenthetical_rows": excluded_appended,
        "stats": dict(built.get("stats") or {}),
        "runtime_patterns": pattern_result,
        "user_edit_metrics": {
            "enabled": bool(dict(settings or {}).get("user_edit_metrics_enabled", True)),
            "event_status": metric_event_result.get("status"),
            "event_rows": int(metric_event_result.get("appended_rows", 0) or 0),
            "queued_hard_cases": int(metric_event_result.get("queued_hard_cases", 0) or 0),
        },
        "auto_maintenance": queue_result,
        "bundle": bundle_result,
    }


__all__ = [
    "EDITOR_TRUTH_CAPTURE_SCHEMA",
    "build_editor_truth_records",
    "capture_editor_truth_records",
]
