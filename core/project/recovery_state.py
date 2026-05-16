from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from typing import Any

from core.media_fingerprint import media_fingerprint_digest, media_fingerprint_snapshot

RECOVERY_STATE_SCHEMA = "ai_subtitle_studio.recovery_state.v1"
RECOVERY_CONTROLS_SCHEMA = "ai_subtitle_studio.recovery_controls.v1"

PIPELINE_STAGE_ORDER = (
    "queued",
    "diagnostics",
    "preprocess",
    "audio",
    "cut_boundary",
    "vad",
    "stt",
    "subtitle_llm",
    "quality",
    "save",
    "export",
    "complete",
)

_STAGE_ALIASES = {
    "diagnostic": "diagnostics",
    "diagnose": "diagnostics",
    "extract_audio": "audio",
    "audio_extract": "audio",
    "cut": "cut_boundary",
    "cuts": "cut_boundary",
    "rough_cut": "cut_boundary",
    "roughcut": "cut_boundary",
    "llm": "subtitle_llm",
    "subtitle": "subtitle_llm",
    "subtitles": "subtitle_llm",
    "validate": "quality",
    "validation": "quality",
    "saved": "save",
    "saving": "save",
    "done": "complete",
    "finished": "complete",
}

_SAFE_STATUSES = {"complete", "completed", "success", "saved", "done", "ok"}


def normalize_recovery_stage(stage: Any) -> str:
    value = str(stage or "").strip().lower().replace("-", "_").replace(" ", "_")
    value = _STAGE_ALIASES.get(value, value)
    if value in PIPELINE_STAGE_ORDER:
        return value
    return "queued"


def recovery_stage_rank(stage: Any) -> int:
    normalized = normalize_recovery_stage(stage)
    try:
        return PIPELINE_STAGE_ORDER.index(normalized)
    except ValueError:
        return 0


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _settings_digest(settings: dict[str, Any] | None) -> str:
    if not isinstance(settings, dict) or not settings:
        return ""
    try:
        raw = json.dumps(settings, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        raw = str(sorted(settings.keys()))
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def media_recovery_snapshot(media_path: str) -> dict[str, Any]:
    path = os.path.abspath(os.path.expanduser(str(media_path or "")))
    snapshot = media_fingerprint_snapshot(path) if path else {
        "path": "",
        "exists": False,
        "size": 0,
        "mtime_ns": 0,
        "fingerprint": "",
        "fingerprint_digest": "",
    }
    snapshot["name"] = os.path.basename(path)
    return snapshot


def _compact_previous_state(state: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(state, dict) or not state:
        return {}
    return {
        "stage": normalize_recovery_stage(state.get("stage")),
        "status": str(state.get("status", "") or ""),
        "last_safe_stage": normalize_recovery_stage(state.get("last_safe_stage") or state.get("stage")),
        "updated_at": str(state.get("updated_at", "") or ""),
        "segment_count": int(state.get("segment_count", 0) or 0),
        "resume_stage": str(state.get("resume_stage", "") or ""),
    }


def build_recovery_checkpoint(
    *,
    media_path: str = "",
    project_path: str = "",
    stage: str = "queued",
    status: str = "running",
    detail: str = "",
    segments: list[dict[str, Any]] | None = None,
    artifacts: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    previous_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_stage = normalize_recovery_stage(stage)
    normalized_status = str(status or "running").strip().lower()
    previous = previous_state if isinstance(previous_state, dict) else {}
    previous_safe = normalize_recovery_stage(previous.get("last_safe_stage") or previous.get("stage"))
    if normalized_status in _SAFE_STATUSES:
        last_safe_stage = normalized_stage
    elif recovery_stage_rank(previous_safe) > recovery_stage_rank(normalized_stage):
        last_safe_stage = previous_safe
    else:
        last_safe_stage = normalize_recovery_stage(previous.get("last_safe_stage") or "queued")

    segment_count = 0
    if isinstance(segments, list):
        segment_count = len(segments)
    elif previous:
        segment_count = int(previous.get("segment_count", 0) or 0)

    state: dict[str, Any] = {
        "schema": RECOVERY_STATE_SCHEMA,
        "updated_at": _utc_now_iso(),
        "project_path": os.path.abspath(project_path) if project_path else "",
        "stage": normalized_stage,
        "status": normalized_status,
        "detail": str(detail or ""),
        "last_safe_stage": last_safe_stage,
        "resume_stage": next_recovery_stage({"last_safe_stage": last_safe_stage, "status": normalized_status}),
        "can_resume": normalized_stage != "complete",
        "stale": False,
        "cache_valid": True,
        "segment_count": segment_count,
    }
    if media_path:
        state["media"] = media_recovery_snapshot(media_path)
    if isinstance(artifacts, dict):
        state["artifacts"] = dict(artifacts)
    digest = _settings_digest(settings)
    if digest:
        state["settings_digest"] = digest
    compact_previous = _compact_previous_state(previous)
    history = []
    if compact_previous:
        history = list(previous.get("history", []) or [])[-8:]
        history.append(compact_previous)
    state["history"] = history[-8:]
    artifact_data = dict(artifacts or {}) if isinstance(artifacts, dict) else {}
    ui_profile = str(artifact_data.get("ui_profile", "") or "")
    state["recovery_controls"] = build_recovery_controls(
        state,
        tablet_profile=ui_profile.startswith("tablet") or bool(artifact_data.get("tablet_mode")),
        low_power=bool(artifact_data.get("low_power") or artifact_data.get("on_battery")),
        foreground_activity=bool(artifact_data.get("foreground_activity")),
    )
    return state


def merge_recovery_checkpoint(existing: dict[str, Any] | None, checkpoint: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(checkpoint, dict):
        return dict(existing or {}) if isinstance(existing, dict) else {}
    if not isinstance(existing, dict) or not existing:
        return dict(checkpoint)
    merged = dict(existing)
    merged.update(checkpoint)
    history = list(existing.get("history", []) or [])
    compact_existing = _compact_previous_state(existing)
    if compact_existing:
        history.append(compact_existing)
    history.extend(list(checkpoint.get("history", []) or []))
    merged["history"] = history[-8:]
    return merged


def recovery_state_is_stale(state: dict[str, Any] | None, media_path: str) -> bool:
    if not isinstance(state, dict) or not media_path:
        return False
    media = state.get("media") if isinstance(state.get("media"), dict) else {}
    previous_digest = str(media.get("fingerprint_digest") or state.get("media_fingerprint_digest") or "")
    if not previous_digest:
        return False
    try:
        return previous_digest != media_fingerprint_digest(media_path)
    except Exception:
        return True


def next_recovery_stage(state: dict[str, Any] | None) -> str:
    if not isinstance(state, dict):
        return "queued"
    if bool(state.get("stale")):
        return "queued"
    stage = normalize_recovery_stage(state.get("last_safe_stage") or state.get("stage"))
    status = str(state.get("status", "") or "").strip().lower()
    if stage == "complete" or status in {"complete", "completed"}:
        return "complete"
    idx = recovery_stage_rank(stage)
    return PIPELINE_STAGE_ORDER[min(idx + 1, len(PIPELINE_STAGE_ORDER) - 1)]


def build_recovery_controls(
    state: dict[str, Any] | None,
    *,
    tablet_profile: bool = False,
    low_power: bool = False,
    foreground_activity: bool = False,
) -> dict[str, Any]:
    """Return touch-safe pause/resume/cancel action metadata for recovery UI."""
    data = dict(state or {}) if isinstance(state, dict) else {}
    stage = normalize_recovery_stage(data.get("stage"))
    status = str(data.get("status", "") or "").strip().lower()
    can_resume = bool(data.get("can_resume", stage != "complete")) and not bool(data.get("stale"))
    complete = stage == "complete" or status in {"complete", "completed"}
    touch_target = 48 if tablet_profile else 44
    paused_like = status in {"paused", "interrupted", "failed", "error", "cancelled", "stopped"}
    running = status in {"running", "processing", "saving", "queued", ""}

    actions = [
        {
            "id": "pause",
            "label": "일시정지",
            "enabled": bool(running and not complete),
            "intent": "checkpoint_then_stop",
            "min_touch_target": touch_target,
        },
        {
            "id": "resume",
            "label": "이어하기",
            "enabled": bool(can_resume and paused_like and not complete),
            "intent": "resume_from_checkpoint",
            "resume_stage": next_recovery_stage(data),
            "min_touch_target": touch_target,
        },
        {
            "id": "cancel",
            "label": "중지",
            "enabled": not complete,
            "intent": "stop_and_keep_checkpoint",
            "min_touch_target": touch_target,
        },
    ]
    if low_power or foreground_activity:
        actions.append(
            {
                "id": "foreground_safe",
                "label": "저전력 보호",
                "enabled": True,
                "intent": "reduce_background_work",
                "min_touch_target": touch_target,
                "reason": "foreground_activity" if foreground_activity else "low_power",
            }
        )
    return {
        "schema": RECOVERY_CONTROLS_SCHEMA,
        "profile": "tablet" if tablet_profile else "desktop",
        "touch_target": touch_target,
        "actions": actions,
    }


def _recovery_control_context(state: dict[str, Any]) -> dict[str, bool]:
    artifacts = dict(state.get("artifacts") or {}) if isinstance(state.get("artifacts"), dict) else {}
    controls = dict(state.get("recovery_controls") or {}) if isinstance(state.get("recovery_controls"), dict) else {}
    actions = list(controls.get("actions") or [])
    reasons = {
        str(action.get("reason") or "")
        for action in actions
        if isinstance(action, dict) and str(action.get("id") or "") == "foreground_safe"
    }
    ui_profile = str(artifacts.get("ui_profile", "") or "")
    return {
        "tablet_profile": (
            ui_profile.startswith("tablet")
            or bool(artifacts.get("tablet_mode"))
            or str(controls.get("profile") or "") == "tablet"
        ),
        "low_power": bool(artifacts.get("low_power") or artifacts.get("on_battery") or "low_power" in reasons),
        "foreground_activity": bool(artifacts.get("foreground_activity") or "foreground_activity" in reasons),
    }


def cache_artifact_is_stale(record: dict[str, Any] | None, media_path: str) -> bool:
    if not isinstance(record, dict) or not media_path:
        return False
    previous_digest = str(
        record.get("media_fingerprint_digest")
        or record.get("fingerprint_digest")
        or ((record.get("media") or {}) if isinstance(record.get("media"), dict) else {}).get("fingerprint_digest")
        or ""
    )
    if not previous_digest:
        return False
    try:
        return previous_digest != media_fingerprint_digest(media_path)
    except Exception:
        return True


def attach_recovery_state_to_project(project: dict[str, Any], recovery_state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(project, dict) or not isinstance(recovery_state, dict) or not recovery_state:
        return project
    project.setdefault("analysis", {})
    project["analysis"]["recovery_state_schema"] = RECOVERY_STATE_SCHEMA
    project["analysis"]["recovery_state"] = dict(recovery_state)
    editor_state = project.get("editor_state")
    if isinstance(editor_state, dict):
        editor_state.setdefault("analysis", {})
        editor_state["analysis"]["recovery_state_schema"] = RECOVERY_STATE_SCHEMA
        editor_state["analysis"]["recovery_state"] = dict(recovery_state)
    return project


def refresh_project_recovery_state(project: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(project, dict):
        return project
    analysis = project.get("analysis", {}) if isinstance(project.get("analysis"), dict) else {}
    editor_analysis = (
        (project.get("editor_state", {}) or {}).get("analysis", {})
        if isinstance(project.get("editor_state"), dict)
        else {}
    )
    state = analysis.get("recovery_state") or editor_analysis.get("recovery_state")
    if not isinstance(state, dict):
        return project
    media_path = ""
    media = state.get("media") if isinstance(state.get("media"), dict) else {}
    media_path = str(media.get("path") or "")
    if not media_path:
        media_items = list(project.get("media") or [])
        if media_items and isinstance(media_items[0], dict):
            media_path = str(media_items[0].get("path") or "")
    refreshed = dict(state)
    stale = recovery_state_is_stale(refreshed, media_path) if media_path else False
    refreshed["stale"] = bool(stale)
    refreshed["cache_valid"] = not bool(stale)
    refreshed["can_resume"] = not bool(stale) and normalize_recovery_stage(refreshed.get("stage")) != "complete"
    refreshed["resume_stage"] = "queued" if stale else next_recovery_stage(refreshed)
    if stale:
        invalidated = list(refreshed.get("invalidated_artifacts", []) or [])
        for key in ("cut_boundary_cache_path", "subtitle_accuracy_graph_path", "stt_lattice_artifact_path"):
            value = analysis.get(key) or editor_analysis.get(key)
            if value and value not in invalidated:
                invalidated.append(value)
        refreshed["invalidated_artifacts"] = invalidated
        refreshed["detail"] = "media fingerprint changed; cached pipeline state invalidated"
    refreshed["recovery_controls"] = build_recovery_controls(
        refreshed,
        **_recovery_control_context(refreshed),
    )
    attach_recovery_state_to_project(project, refreshed)
    return project


__all__ = [
    "RECOVERY_STATE_SCHEMA",
    "PIPELINE_STAGE_ORDER",
    "attach_recovery_state_to_project",
    "build_recovery_checkpoint",
    "cache_artifact_is_stale",
    "media_recovery_snapshot",
    "merge_recovery_checkpoint",
    "next_recovery_stage",
    "normalize_recovery_stage",
    "recovery_stage_rank",
    "recovery_state_is_stale",
    "refresh_project_recovery_state",
]
