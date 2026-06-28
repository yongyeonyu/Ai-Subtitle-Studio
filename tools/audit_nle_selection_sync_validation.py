#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.project.nle_project_state import (  # noqa: E402
    NLE_PROJECT_STATE_RUNTIME_KEY,
    NLEProjectState,
    assert_nle_active_selection_consistent,
    nle_active_selection_signature,
)
from core.project.project_context import build_editor_state  # noqa: E402
from core.project.project_io import read_project_storage_payload, write_project_file  # noqa: E402
from ui.editor.editor_segments_reload import EditorSegmentsReloadMixin  # noqa: E402
from ui.project.project_session_runtime import sync_runtime_nle_state_from_editor_rows  # noqa: E402


SCHEMA = "ai_subtitle_studio.nle_selection_sync_validation.v1"
AUDIT_ID = "nle_selection_sync_validation_20260628"
FORBIDDEN_NLE_STORAGE_KEYS = ("nle", "nle_snapshot", NLE_PROJECT_STATE_RUNTIME_KEY)


class _TimelineProbe:
    def __init__(self) -> None:
        self.update_calls: list[dict[str, Any]] = []

    def setUpdatesEnabled(self, _enabled: bool) -> None:
        return None

    def update_segments(self, segs: list[dict[str, Any]], active_sec: float, total_dur: float) -> None:
        self.update_calls.append(
            {
                "row_count": len(list(segs or [])),
                "active_sec": float(active_sec),
                "total_dur": float(total_dur),
            }
        )


class _TextEditProbe:
    timestampArea = None

    def setUpdatesEnabled(self, _enabled: bool) -> None:
        return None

    def clear(self) -> None:
        return None


class _ReloadProbeEditor(EditorSegmentsReloadMixin):
    def __init__(self, *, active_sec: float) -> None:
        self.text_edit = _TextEditProbe()
        self.timeline = _TimelineProbe()
        self._active_seg_start = float(active_sec)
        self._cached_segs: list[dict[str, Any]] = []
        self._segment_queue: list[dict[str, Any]] = []
        self._live_editor_preview_segments: list[dict[str, Any]] = []
        self._live_editor_preview_queue: list[dict[str, Any]] = []
        self._live_editor_preview_keys: set[str] = set()
        self.dirty_count = 0
        self.schedule_count = 0

    def _bulk_load_segments_to_document(self, segs: list[dict[str, Any]], *, preserve_view: bool) -> list[dict[str, Any]]:
        return [dict(row) for row in list(segs or [])]

    def _refresh_editor_timestamp_metadata(self, *, full: bool = False) -> int:
        return 0

    def _mark_dirty(self) -> None:
        self.dirty_count += 1

    def _schedule_timeline(self) -> None:
        self.schedule_count += 1


def _fixture_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": "caption_0001",
            "line": 0,
            "index": 1,
            "start": 0.0,
            "end": 2.0,
            "start_frame": 0,
            "end_frame": 60,
            "text": "first",
            "speaker": "00",
        },
        {
            "id": "caption_0002",
            "line": 1,
            "index": 2,
            "start": 2.0,
            "end": 4.0,
            "start_frame": 60,
            "end_frame": 120,
            "text": "second",
            "speaker": "00",
        },
    ]


def _forbidden_key_paths(value: Any, *, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            current = f"{prefix}.{key_text}" if prefix else key_text
            if key_text in FORBIDDEN_NLE_STORAGE_KEYS:
                paths.append(current)
            paths.extend(_forbidden_key_paths(item, prefix=current))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(_forbidden_key_paths(item, prefix=f"{prefix}[{index}]"))
    return paths


def _runtime_reload_check() -> tuple[dict[str, Any], NLEProjectState | None]:
    active_sec = 2.0
    editor = _ReloadProbeEditor(active_sec=active_sec)
    rows = _fixture_rows()
    editor._reload_segments_from_list(rows, preserve_view=True, mark_dirty=False)
    timeline_rows = list(editor._cached_segs or [])
    state = sync_runtime_nle_state_from_editor_rows(
        editor,
        timeline_rows,
        project_path="/tmp/nle-selection-sync-validation.aissproj",
        primary_fps=30.0,
        sync_source="reload_selection_sync",
    )
    nle_rows = state.editor_rows() if isinstance(state, NLEProjectState) else []
    active_consistency_error = ""
    try:
        assert_nle_active_selection_consistent(
            timeline_rows,
            nle_rows,
            active_sec=active_sec,
            primary_fps=30.0,
        )
    except Exception as exc:  # pragma: no cover - reported in audit output.
        active_consistency_error = str(exc)
    editor_sig = nle_active_selection_signature(timeline_rows, active_sec=active_sec, primary_fps=30.0)
    nle_sig = nle_active_selection_signature(nle_rows, active_sec=active_sec, primary_fps=30.0)
    timeline_update = editor.timeline.update_calls[-1] if editor.timeline.update_calls else {}
    return (
        {
            "reload_row_count": len(timeline_rows),
            "runtime_nle_row_count": len(nle_rows),
            "active_sec": active_sec,
            "timeline_update_active_sec": timeline_update.get("active_sec"),
            "timeline_update_total_dur": timeline_update.get("total_dur"),
            "editor_active_signature": editor_sig,
            "nle_active_signature": nle_sig,
            "active_selection_consistent": not active_consistency_error,
            "active_consistency_error": active_consistency_error,
            "sync_source": getattr(state, "metadata", {}).get("last_editor_sync_source", "")
            if isinstance(state, NLEProjectState)
            else "",
            "runtime_storage_policy": getattr(state, "metadata", {}).get("runtime_storage_policy", "")
            if isinstance(state, NLEProjectState)
            else "",
            "operation_journal_count": len(getattr(state, "operation_journal", []) or [])
            if isinstance(state, NLEProjectState)
            else -1,
            "dirty_count": editor.dirty_count,
            "schedule_count": editor.schedule_count,
        },
        state if isinstance(state, NLEProjectState) else None,
    )


def _storage_check(state: NLEProjectState | None) -> dict[str, Any]:
    rows = _fixture_rows()
    with tempfile.TemporaryDirectory(prefix="nle-selection-sync-") as tmp:
        project_path = Path(tmp) / "selection_sync.aissproj"
        project: dict[str, Any] = {
            "project_name": "nle_selection_sync_validation",
            "video": {"duration_sec": 4.0, "primary_fps": 30.0},
            "timeline": {"total_duration": 4.0, "timebase": {"primary_fps": 30.0}, "tracks": [{"clips": []}]},
            "editor_state": build_editor_state(
                mode="single",
                media_files=[],
                segments=rows,
                primary_fps=30.0,
                preserve_segment_identity=True,
            ),
            "nle": {"future": True},
            "nle_snapshot": {"future": True},
        }
        if isinstance(state, NLEProjectState):
            project[NLE_PROJECT_STATE_RUNTIME_KEY] = state
        write_project_file(str(project_path), project)
        storage = read_project_storage_payload(str(project_path))
    forbidden_paths = _forbidden_key_paths(storage)
    return {
        "storage_forbidden_key_count": len(forbidden_paths),
        "storage_forbidden_key_paths": forbidden_paths,
        "storage_has_nle": "nle" in storage,
        "storage_has_nle_snapshot": "nle_snapshot" in storage,
        "storage_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in storage,
    }


def _static_contract_check() -> dict[str, Any]:
    runtime_source = (ROOT / "ui/project/project_session_runtime.py").read_text(encoding="utf-8")
    reload_source = (ROOT / "ui/editor/editor_segments_reload.py").read_text(encoding="utf-8")
    state_source = (ROOT / "core/project/nle_project_state.py").read_text(encoding="utf-8")
    return {
        "reload_updates_timeline_with_active_start": "self.timeline.update_segments(timeline_segments, self._active_seg_start, total_dur)" in reload_source,
        "runtime_sync_asserts_editor_rows": "assert_nle_editor_rows_consistent(editor_rows, state.editor_rows(), primary_fps=fps)" in runtime_source,
        "active_selection_helper_present": "def assert_nle_active_selection_consistent" in state_source,
        "active_signature_exact_start_priority": "exact_start = [row for row in candidates if row[\"start_frame\"] == active_frame]" in state_source,
    }


def build_nle_selection_sync_validation_report() -> dict[str, Any]:
    runtime, state = _runtime_reload_check()
    storage = _storage_check(state)
    static = _static_contract_check()
    ready = (
        all(static.values())
        and runtime["reload_row_count"] == 2
        and runtime["runtime_nle_row_count"] == 2
        and runtime["timeline_update_active_sec"] == runtime["active_sec"]
        and runtime["editor_active_signature"].get("id") == "caption_0002"
        and runtime["nle_active_signature"].get("id") == "caption_0002"
        and runtime["active_selection_consistent"]
        and runtime["sync_source"] == "reload_selection_sync"
        and runtime["runtime_storage_policy"] == "object_attribute_only"
        and runtime["operation_journal_count"] == 0
        and storage["storage_forbidden_key_count"] == 0
    )
    return {
        "schema": SCHEMA,
        "audit_id": AUDIT_ID,
        "ready": bool(ready),
        "runtime_change_applied": False,
        "validation_helper_added": True,
        "ui_layout_changed": False,
        "persisted_nle_fields_changed": False,
        "nas_required_for_contract": False,
        "active_boundary_policy": "exact_start_frame_wins_at_shared_boundary",
        "static_contract": static,
        "runtime_check": runtime,
        "storage_check": storage,
        "blocked_scope": [
            "ui_layout_labels_colors_menus_popups",
            "persisted_nle_disk_format",
            "per_pixel_nle_writes",
            "subtitle_quality_or_stt_default_policy",
            "app_store_packaging_signing_upload",
        ],
    }


def write_nle_selection_sync_validation_report(output_dir: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "nle_selection_sync_validation.json"
    markdown_path = output_dir / "nle_selection_sync_validation.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    runtime = report["runtime_check"]
    storage = report["storage_check"]
    static = report["static_contract"]
    lines = [
        "# NLE Selection Sync Validation Audit",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Audit ID: `{report['audit_id']}`",
        f"- Ready: `{report['ready']}`",
        f"- Runtime change applied: `{report['runtime_change_applied']}`",
        f"- Validation helper added: `{report['validation_helper_added']}`",
        f"- UI layout changed: `{report['ui_layout_changed']}`",
        f"- Persisted NLE fields changed: `{report['persisted_nle_fields_changed']}`",
        f"- NAS required for contract: `{report['nas_required_for_contract']}`",
        f"- Active boundary policy: `{report['active_boundary_policy']}`",
        "",
        "## Static Contract",
        "",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in static.items())
    lines.extend(
        [
            "",
            "## Runtime Check",
            "",
            f"- Reload row count: `{runtime['reload_row_count']}`",
            f"- Runtime NLE row count: `{runtime['runtime_nle_row_count']}`",
            f"- Active sec: `{runtime['active_sec']}`",
            f"- Timeline update active sec: `{runtime['timeline_update_active_sec']}`",
            f"- Editor active signature: `{runtime['editor_active_signature']}`",
            f"- NLE active signature: `{runtime['nle_active_signature']}`",
            f"- Active selection consistent: `{runtime['active_selection_consistent']}`",
            f"- Sync source: `{runtime['sync_source']}`",
            f"- Runtime storage policy: `{runtime['runtime_storage_policy']}`",
            f"- Operation journal count: `{runtime['operation_journal_count']}`",
            "",
            "## Storage Check",
            "",
            f"- Storage forbidden key count: `{storage['storage_forbidden_key_count']}`",
            f"- Storage forbidden key paths: `{storage['storage_forbidden_key_paths']}`",
            f"- Storage has NLE: `{storage['storage_has_nle']}`",
            f"- Storage has NLE snapshot: `{storage['storage_has_nle_snapshot']}`",
            f"- Storage has runtime NLE key: `{storage['storage_has_runtime_nle_key']}`",
            "",
            "## Blocked Scope",
            "",
        ]
    )
    lines.extend(f"- `{item}`" for item in report["blocked_scope"])
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "output" / "manual_verification" / "latest" / AUDIT_ID,
    )
    args = parser.parse_args(argv)
    report = build_nle_selection_sync_validation_report()
    write_nle_selection_sync_validation_report(args.output_dir, report)
    print(json.dumps({"ready": report["ready"], "output_dir": str(args.output_dir)}, ensure_ascii=False))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
