from __future__ import annotations

"""Deferred editor-save learning jobs.

Editor saves must feel finished immediately. This helper stores a compact copy
of the just-saved subtitle state in the normal personalization training queue;
the idle trainer later performs truth capture, text corpus accumulation, index
refresh, and maintenance while the Home screen is idle.
"""

from pathlib import Path
from typing import Any

from core.personalization.lora_models import TrainingQueueItem, stable_hash
from core.personalization.lora_store_records import upsert_training_queue_items


DEFERRED_EDITOR_LEARNING_SCHEMA = "ai_subtitle_studio.deferred_editor_learning.v1"
DEFERRED_EDITOR_LEARNING_JOB_TYPE = "capture_editor_learning"


def _safe_segment(segment: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "line",
        "index",
        "segment_id",
        "id",
        "start",
        "end",
        "start_frame",
        "end_frame",
        "timeline_frame_rate",
        "text",
        "speaker",
        "spk",
        "original_text",
        "original_start",
        "original_end",
        "source_segment_count",
        "score",
        "stt_score",
        "stt_candidates",
        "stt_selected_source",
        "stt_ensemble_llm_selected_source",
        "stt_ensemble_source",
        "quality",
        "quality_history",
        "_clip_idx",
        "_clip_file",
    }
    return {key: segment.get(key) for key in allowed if key in segment}


def _safe_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    keys = {
        "selected_audio_ai",
        "selected_vad",
        "selected_whisper_model",
        "selected_whisper_model_secondary",
        "selected_model",
        "selected_llm_provider",
        "stt_quality_preset",
        "subtitle_mode",
        "simple_operation_mode",
        "sub_max_cps",
        "sub_min_duration",
        "sub_max_duration",
        "editor_truth_capture_enabled",
        "editor_truth_capture_min_chars",
        "editor_truth_capture_max_chars",
        "user_edit_metrics_enabled",
        "user_edit_metrics_deep_event_enabled",
    }
    data = dict(settings or {})
    return {key: data.get(key) for key in keys if key in data}


def build_deferred_editor_learning_job(
    segments: list[dict[str, Any]] | None,
    *,
    media_path: str = "",
    subtitle_path: str = "",
    project_path: str = "",
    trigger: str = "manual_save",
    settings: dict[str, Any] | None = None,
    priority: int = 6,
) -> dict[str, Any]:
    rows = [
        _safe_segment(dict(seg))
        for seg in list(segments or [])
        if isinstance(seg, dict) and str(seg.get("text", "") or "").strip() and not seg.get("is_gap")
    ]
    payload = {
        "schema": DEFERRED_EDITOR_LEARNING_SCHEMA,
        "trigger": str(trigger or "manual_save"),
        "media_path": str(media_path or ""),
        "subtitle_path": str(subtitle_path or ""),
        "project_path": str(project_path or ""),
        "segments": rows,
        "settings": _safe_settings(settings),
        "foreground_deferred": True,
    }
    digest = stable_hash(
        {
            "trigger": payload["trigger"],
            "media_path": payload["media_path"],
            "subtitle_path": payload["subtitle_path"],
            "project_path": payload["project_path"],
            "segments": rows,
        }
    )[:18]
    media_id = stable_hash({"media_path": payload["media_path"], "project_path": payload["project_path"]})[:16]
    return TrainingQueueItem(
        media_id=media_id,
        media_path=payload["media_path"],
        subtitle_path=payload["subtitle_path"],
        job_type=DEFERRED_EDITOR_LEARNING_JOB_TYPE,
        job_id=f"editor-learning-{digest}",
        priority=int(priority),
        payload=payload,
    ).to_record()


def enqueue_deferred_editor_learning(
    segments: list[dict[str, Any]] | None,
    *,
    media_path: str = "",
    subtitle_path: str = "",
    project_path: str = "",
    trigger: str = "manual_save",
    settings: dict[str, Any] | None = None,
    store_dir: str | Path | None = None,
    priority: int = 6,
) -> dict[str, Any]:
    job = build_deferred_editor_learning_job(
        segments,
        media_path=media_path,
        subtitle_path=subtitle_path,
        project_path=project_path,
        trigger=trigger,
        settings=settings,
        priority=priority,
    )
    payload = dict(job.get("payload") or {})
    if not payload.get("segments"):
        return {
            "schema": DEFERRED_EDITOR_LEARNING_SCHEMA,
            "queued": False,
            "reason": "no_learning_segments",
            "job_id": str(job.get("job_id") or ""),
        }
    result = upsert_training_queue_items([job], store_dir)
    return {
        "schema": DEFERRED_EDITOR_LEARNING_SCHEMA,
        "queued": True,
        "job_id": str(job.get("job_id") or ""),
        "items": len(list(result.get("items") or [])),
        "trigger": trigger,
    }


def run_deferred_editor_learning_job(
    job: dict[str, Any],
    *,
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    payload = dict((job or {}).get("payload") or {})
    segments = [dict(seg) for seg in list(payload.get("segments") or []) if isinstance(seg, dict)]
    settings = dict(payload.get("settings") or {})
    trigger = str(payload.get("trigger") or "manual_save")
    media_path = str(payload.get("media_path") or job.get("media_path") or "")
    subtitle_path = str(payload.get("subtitle_path") or job.get("subtitle_path") or "")
    project_path = str(payload.get("project_path") or "")

    from core.personalization.editor_truth_capture import capture_editor_truth_records
    from core.personalization.text_lora_dataset import accumulate_personalization_dataset

    truth_result = capture_editor_truth_records(
        segments,
        media_path=media_path,
        subtitle_path=subtitle_path,
        project_path=project_path,
        trigger=trigger,
        settings=settings,
        store_dir=store_dir,
        enabled=bool(settings.get("editor_truth_capture_enabled", True)),
        min_chars=int(settings.get("editor_truth_capture_min_chars", 2) or 2),
        max_chars=int(settings.get("editor_truth_capture_max_chars", 240) or 240),
        refresh_bundle=False,
    )
    text_result = accumulate_personalization_dataset(
        current_segments=segments,
        current_project_path=project_path,
        trigger=trigger,
        refresh_bundle=False,
        store_dir=store_dir,
    )
    appended = (
        int(truth_result.get("appended_rows", 0) or 0)
        + int(truth_result.get("excluded_parenthetical_rows", 0) or 0)
        + int(text_result.get("appended_rows", 0) or 0)
        + int(text_result.get("voice_bridge_rows", 0) or 0)
        + int(text_result.get("multimodal_context_rows", 0) or 0)
    )
    return {
        "schema": DEFERRED_EDITOR_LEARNING_SCHEMA,
        "status": "complete",
        "score": float(appended),
        "result": {
            "truth": truth_result,
            "text_lora": text_result,
            "appended_total": appended,
            "reason": "deferred_home_idle_editor_learning",
        },
    }


__all__ = [
    "DEFERRED_EDITOR_LEARNING_JOB_TYPE",
    "DEFERRED_EDITOR_LEARNING_SCHEMA",
    "build_deferred_editor_learning_job",
    "enqueue_deferred_editor_learning",
    "run_deferred_editor_learning_job",
]
