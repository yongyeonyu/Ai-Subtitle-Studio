# Version: 03.24.01
# Phase: STT_MODE_DESKTOP_WITH_IPAD_COMPAT
"""Portable STT Mode project state helpers."""
from __future__ import annotations

import hashlib
import os
from datetime import datetime
from typing import Any

from core.frame_time import normalize_fps
from core.media_fingerprint import media_file_fingerprint
from core.stt_mode.models import STT_MODE_LEARNING_SCHEMA, STT_MODE_STATE_SCHEMA


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _fingerprint(media_path: str | None) -> str:
    if media_path and os.path.exists(media_path):
        try:
            return media_file_fingerprint(media_path, sample_bytes=256 * 1024, include_samples=True)
        except Exception:
            pass
    return hashlib.sha1(str(media_path or "").encode("utf-8", errors="ignore")).hexdigest()


def default_adapter_refs(bundle_id: str = "stt_lora_bundle:v1") -> dict[str, str]:
    return {
        "stt_lora_bundle": bundle_id,
        "stt_vad_segment_model": "stt_vad_segment_model:v1",
        "stt_dictation_resegment": "stt_dictation_resegment:v1",
        "subtitle_style_policy": "personal_subtitle_style:v1",
    }


def build_stt_mode_state(
    *,
    media_path: str | None = None,
    primary_fps: float | int | str | None = None,
    work_segments: list[dict[str, Any]] | None = None,
    raw_dictation_segments: list[dict[str, Any]] | None = None,
    rolling_windows: list[dict[str, Any]] | None = None,
    final_segments: list[dict[str, Any]] | None = None,
    active_work_segment_id: str = "",
    adapter_refs: dict[str, Any] | None = None,
    previous_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous = dict(previous_state or {})
    work_source = previous.get("work_segments", []) if work_segments is None else work_segments
    raw_source = previous.get("raw_dictation_segments", []) if raw_dictation_segments is None else raw_dictation_segments
    window_source = previous.get("rolling_windows", []) if rolling_windows is None else rolling_windows
    final_source = previous.get("final_segments", []) if final_segments is None else final_segments
    work = [dict(row) for row in work_source or [] if isinstance(row, dict)]
    raw = [dict(row) for row in raw_source or [] if isinstance(row, dict)]
    windows = [dict(row) for row in window_source or [] if isinstance(row, dict)]
    final = [dict(row) for row in final_source or [] if isinstance(row, dict)]
    completed = sum(1 for row in work if str(row.get("stt_mode_status") or "") in {"input_done", "resegmented"} or not row.get("stt_pending"))
    state = dict(previous)
    state.update(
        {
            "schema": STT_MODE_STATE_SCHEMA,
            "mode": "stt",
            "cross_device": True,
            "media_fingerprint": _fingerprint(media_path or previous.get("media_path", "")),
            "media_path": media_path or previous.get("media_path", ""),
            "primary_fps": normalize_fps(primary_fps or previous.get("primary_fps") or 30.0),
            "work_segments": work,
            "raw_dictation_segments": raw,
            "rolling_windows": windows,
            "final_segments": final,
            "active_work_segment_id": str(active_work_segment_id or previous.get("active_work_segment_id", "") or ""),
            "completed_count": completed,
            "total_count": len(work),
            "adapter_refs": {**default_adapter_refs(), **dict(adapter_refs or previous.get("adapter_refs", {}) or {})},
            "updated_at": _now(),
        }
    )
    return state


def default_stt_mode_learning(previous: dict[str, Any] | None = None) -> dict[str, Any]:
    prev = dict(previous or {})
    return {
        **prev,
        "schema": STT_MODE_LEARNING_SCHEMA,
        "events": list(prev.get("events") or []),
        "vad_selection_pairs": list(prev.get("vad_selection_pairs") or []),
        "dictation_resegment_pairs": list(prev.get("dictation_resegment_pairs") or []),
        "edit_events": list(prev.get("edit_events") or []),
        "learning_opt_in": bool(prev.get("learning_opt_in", True)),
    }


def attach_stt_mode_state(
    project: dict[str, Any],
    state: dict[str, Any] | None = None,
    learning: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(project, dict):
        return project
    if state is not None:
        previous_state = project.get("stt_mode_state") if isinstance(project.get("stt_mode_state"), dict) else {}
        merged = dict(previous_state)
        merged.update(dict(state or {}))
        merged["schema"] = STT_MODE_STATE_SCHEMA
        merged["mode"] = "stt"
        merged["cross_device"] = True
        merged["updated_at"] = str(merged.get("updated_at") or _now())
        project["stt_mode_state"] = merged
    else:
        project.setdefault("stt_mode_state", build_stt_mode_state(previous_state=project.get("stt_mode_state", {})))
    if learning is not None:
        previous_learning = project.get("stt_mode_learning") if isinstance(project.get("stt_mode_learning"), dict) else {}
        merged_learning = default_stt_mode_learning(previous_learning)
        merged_learning.update(dict(learning or {}))
        merged_learning["schema"] = STT_MODE_LEARNING_SCHEMA
        project["stt_mode_learning"] = merged_learning
    else:
        project.setdefault("stt_mode_learning", default_stt_mode_learning(project.get("stt_mode_learning", {})))
    return project


def project_stt_mode_state(project: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(project, dict):
        return {}
    state = project.get("stt_mode_state")
    return dict(state) if isinstance(state, dict) else {}


def project_stt_mode_learning(project: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(project, dict):
        return default_stt_mode_learning()
    learning = project.get("stt_mode_learning")
    return default_stt_mode_learning(learning if isinstance(learning, dict) else {})


__all__ = [
    "attach_stt_mode_state",
    "build_stt_mode_state",
    "default_adapter_refs",
    "default_stt_mode_learning",
    "project_stt_mode_learning",
    "project_stt_mode_state",
]
