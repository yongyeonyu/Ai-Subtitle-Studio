# Version: 03.24.01
# Phase: STT_MODE_DESKTOP_WITH_IPAD_COMPAT
"""Append-only learning events for STT Mode."""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any

from core.native_json import dumps_json_bytes
from core.runtime import config


STT_LEARNING_EVENT_SCHEMA = "ai_subtitle_studio.stt_learning_event.v1"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def create_learning_event(
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    project_id: str = "",
    platform: str = "desktop",
    event_id: str | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(payload or {})
    settings = settings or {}
    if not bool(settings.get("stt_learning_save_audio_snippets", False)):
        for key in ("audio", "audio_path", "audio_snippet", "mic_audio_path", "source_audio_path"):
            payload.pop(key, None)
    return {
        "event_id": str(event_id or uuid.uuid4()),
        "schema": STT_LEARNING_EVENT_SCHEMA,
        "event_type": str(event_type or "unknown"),
        "project_id": str(project_id or ""),
        "platform": str(platform or "desktop"),
        "created_at": _now(),
        "payload": payload,
    }


def dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in events or []:
        if not isinstance(event, dict):
            continue
        if event.get("schema") != STT_LEARNING_EVENT_SCHEMA:
            continue
        event_id = str(event.get("event_id") or "")
        if not event_id or event_id in seen:
            continue
        seen.add(event_id)
        out.append(dict(event))
    return out


def dataset_file_for_event(event_type: str, *, dataset_dir: str | None = None) -> str:
    root = dataset_dir or os.path.join(config.BASE_DIR, "dataset", "personalization")
    os.makedirs(root, exist_ok=True)
    event_type = str(event_type or "")
    if event_type == "vad_ensemble_decision":
        name = "stt_vad_selection_pairs.jsonl"
    elif event_type in {"dictation_input_done", "rolling_resegment_done"}:
        name = "stt_dictation_resegment_pairs.jsonl"
    elif event_type in {"subtitle_manual_edit", "segment_split", "segment_merge", "segment_trim"}:
        name = "stt_edit_events.jsonl"
    else:
        name = "stt_mode_events.jsonl"
    return os.path.join(root, name)


def append_learning_events(
    events: list[dict[str, Any]],
    *,
    dataset_dir: str | None = None,
    existing_ids: set[str] | None = None,
) -> dict[str, Any]:
    ids = set(existing_ids or set())
    written = 0
    skipped = 0
    for event in dedupe_events(events):
        event_id = str(event.get("event_id") or "")
        if event_id in ids:
            skipped += 1
            continue
        ids.add(event_id)
        path = dataset_file_for_event(str(event.get("event_type") or ""), dataset_dir=dataset_dir)
        with open(path, "ab") as handle:
            handle.write(dumps_json_bytes(event, sort_keys=True, append_newline=True))
        written += 1
    return {"written": written, "skipped": skipped, "known_event_ids": ids}


def import_learning_events_from_project(
    project: dict[str, Any],
    *,
    dataset_dir: str | None = None,
    existing_ids: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(project, dict):
        return {"written": 0, "skipped": 0, "known_event_ids": set(existing_ids or set())}
    learning = project.get("stt_mode_learning") if isinstance(project.get("stt_mode_learning"), dict) else {}
    events = learning.get("events") if isinstance(learning, dict) else []
    return append_learning_events(events or [], dataset_dir=dataset_dir, existing_ids=existing_ids)


__all__ = [
    "STT_LEARNING_EVENT_SCHEMA",
    "append_learning_events",
    "create_learning_event",
    "dedupe_events",
    "import_learning_events_from_project",
]
