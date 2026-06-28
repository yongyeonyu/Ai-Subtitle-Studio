#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.project.nle_project_state import NLE_PROJECT_STATE_RUNTIME_KEY, NLEProjectState
from core.project.project_context import build_editor_state
from core.project.project_format import build_storage_project_payload
from ui.project.project_session_runtime import sync_runtime_nle_state_from_editor_rows


SCHEMA = "ai_subtitle_studio.nle_undo_redo_runtime_state.v1"
AUDIT_ID = "nle_undo_redo_runtime_state_20260628"


def _rows_before() -> list[dict[str, Any]]:
    return [
        {
            "id": "caption_1",
            "start": 1.0,
            "end": 3.0,
            "text": "before",
            "speaker": "00",
        }
    ]


def _rows_after() -> list[dict[str, Any]]:
    return [
        {
            "id": "caption_1",
            "start": 1.0,
            "end": 2.0,
            "text": "after left",
            "speaker": "00",
        },
        {
            "id": "caption_2",
            "start": 2.0,
            "end": 3.0,
            "text": "after right",
            "speaker": "00",
        },
    ]


def _row_signature(rows: list[dict[str, Any]]) -> list[tuple[str, int, int]]:
    return [
        (str(row.get("text", "")), int(row.get("start_frame", -1)), int(row.get("end_frame", -1)))
        for row in rows
    ]


def _static_contract_check() -> dict[str, Any]:
    undo_source = (ROOT / "ui/editor/undo_manager.py").read_text(encoding="utf-8")
    runtime_source = (ROOT / "ui/project/project_session_runtime.py").read_text(encoding="utf-8")
    return {
        "undo_restore_calls_runtime_sync": "sync_runtime_nle_state_from_editor_rows" in undo_source,
        "undo_restore_sync_source": 'sync_source="undo_redo_restore"' in undo_source,
        "runtime_helper_sets_object_attribute": "setattr(owner, NLE_PROJECT_STATE_RUNTIME_KEY, state)" in runtime_source,
        "runtime_helper_storage_policy": "object_attribute_only" in runtime_source,
        "undo_restore_appends_operation_journal": "record_nle_operation_journal_entry" in undo_source,
    }


def _runtime_sync_check() -> dict[str, Any]:
    owner = SimpleNamespace(_current_project_path="/tmp/nle-undo-redo-runtime-state.aissproj")
    before_state = sync_runtime_nle_state_from_editor_rows(
        owner,
        _rows_before(),
        project_path=owner._current_project_path,
        primary_fps=30.0,
        sync_source="undo_redo_restore",
    )
    before_rows = before_state.editor_rows() if isinstance(before_state, NLEProjectState) else []
    after_state = sync_runtime_nle_state_from_editor_rows(
        owner,
        _rows_after(),
        project_path=owner._current_project_path,
        primary_fps=30.0,
        sync_source="undo_redo_restore",
    )
    storage_payload = build_storage_project_payload(
        {
            "project_name": "nle_undo_redo_runtime_state",
            "video": {"duration_sec": 3.0, "primary_fps": 30.0},
            "timeline": {"total_duration": 3.0, "timebase": {"primary_fps": 30.0}, "tracks": [{"clips": []}]},
            "editor_state": build_editor_state(
                mode="single",
                media_files=[],
                segments=_rows_after(),
                primary_fps=30.0,
                preserve_segment_identity=True,
            ),
            NLE_PROJECT_STATE_RUNTIME_KEY: after_state,
        }
    )
    after_rows = after_state.editor_rows() if isinstance(after_state, NLEProjectState) else []
    return {
        "before_state_hydrated": isinstance(before_state, NLEProjectState),
        "after_state_hydrated": isinstance(after_state, NLEProjectState),
        "before_signature": _row_signature(before_rows),
        "after_signature": _row_signature(after_rows),
        "sync_source": getattr(after_state, "metadata", {}).get("last_editor_sync_source", "")
        if isinstance(after_state, NLEProjectState)
        else "",
        "runtime_storage_policy": getattr(after_state, "metadata", {}).get("runtime_storage_policy", "")
        if isinstance(after_state, NLEProjectState)
        else "",
        "operation_journal_count": len(getattr(after_state, "operation_journal", []) or [])
        if isinstance(after_state, NLEProjectState)
        else -1,
        "storage_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in storage_payload,
        "storage_has_nle": "nle" in storage_payload,
        "storage_has_nle_snapshot": "nle_snapshot" in storage_payload,
    }


def build_nle_undo_redo_runtime_state_report() -> dict[str, Any]:
    static = _static_contract_check()
    runtime = _runtime_sync_check()
    ready = (
        static["undo_restore_calls_runtime_sync"]
        and static["undo_restore_sync_source"]
        and static["runtime_helper_sets_object_attribute"]
        and static["runtime_helper_storage_policy"]
        and not static["undo_restore_appends_operation_journal"]
        and runtime["before_state_hydrated"]
        and runtime["after_state_hydrated"]
        and runtime["before_signature"] == [("before", 30, 90)]
        and runtime["after_signature"] == [("after left", 30, 60), ("after right", 60, 90)]
        and runtime["sync_source"] == "undo_redo_restore"
        and runtime["runtime_storage_policy"] == "object_attribute_only"
        and runtime["operation_journal_count"] == 0
        and not runtime["storage_has_runtime_nle_key"]
        and not runtime["storage_has_nle"]
        and not runtime["storage_has_nle_snapshot"]
    )
    return {
        "schema": SCHEMA,
        "audit_id": AUDIT_ID,
        "ready": bool(ready),
        "runtime_change_applied": True,
        "ui_layout_changed": False,
        "persisted_nle_fields_changed": False,
        "operation_journal_write_allowed": False,
        "nas_required_for_contract": False,
        "static_contract": static,
        "runtime_check": runtime,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _markdown_report(report: dict[str, Any]) -> str:
    static = report["static_contract"]
    runtime = report["runtime_check"]
    lines = [
        "# NLE Undo/Redo Runtime State Audit",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Audit ID: `{report['audit_id']}`",
        f"- Ready: `{report['ready']}`",
        f"- Runtime change applied: `{report['runtime_change_applied']}`",
        f"- UI layout changed: `{report['ui_layout_changed']}`",
        f"- Persisted NLE fields changed: `{report['persisted_nle_fields_changed']}`",
        f"- Operation journal write allowed: `{report['operation_journal_write_allowed']}`",
        f"- NAS required for contract: `{report['nas_required_for_contract']}`",
        "",
        "## Static Contract",
        "",
        f"- Undo restore calls runtime sync: `{static['undo_restore_calls_runtime_sync']}`",
        f"- Undo restore sync source: `{static['undo_restore_sync_source']}`",
        f"- Runtime helper sets object attribute: `{static['runtime_helper_sets_object_attribute']}`",
        f"- Runtime helper storage policy: `{static['runtime_helper_storage_policy']}`",
        f"- Undo restore appends operation journal: `{static['undo_restore_appends_operation_journal']}`",
        "",
        "## Runtime Check",
        "",
        f"- Before state hydrated: `{runtime['before_state_hydrated']}`",
        f"- After state hydrated: `{runtime['after_state_hydrated']}`",
        f"- Before signature: `{runtime['before_signature']}`",
        f"- After signature: `{runtime['after_signature']}`",
        f"- Sync source: `{runtime['sync_source']}`",
        f"- Runtime storage policy: `{runtime['runtime_storage_policy']}`",
        f"- Operation journal count: `{runtime['operation_journal_count']}`",
        f"- Storage has runtime NLE key: `{runtime['storage_has_runtime_nle_key']}`",
        f"- Storage has NLE: `{runtime['storage_has_nle']}`",
        f"- Storage has NLE snapshot: `{runtime['storage_has_nle_snapshot']}`",
    ]
    return "\n".join(lines) + "\n"


def write_nle_undo_redo_runtime_state_report(output_dir: Path, report: dict[str, Any]) -> None:
    _write_json(output_dir / "nle_undo_redo_runtime_state.json", report)
    (output_dir / "nle_undo_redo_runtime_state.md").write_text(_markdown_report(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="output/manual_verification/latest/nle_undo_redo_runtime_state_20260628",
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    report = build_nle_undo_redo_runtime_state_report()
    write_nle_undo_redo_runtime_state_report(output_dir, report)
    print(json.dumps({"ready": report["ready"], "output_dir": str(output_dir)}, ensure_ascii=False))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
