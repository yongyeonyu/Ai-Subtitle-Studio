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
    assert_nle_media_relink_parity,
    build_project_nle_state,
)
from core.project.project_context import build_editor_state  # noqa: E402
from core.project.project_io import read_project_storage_payload, write_project_file  # noqa: E402


SCHEMA = "ai_subtitle_studio.nle_relink_parity.v1"
AUDIT_ID = "nle_relink_parity_20260628"
FORBIDDEN_NLE_STORAGE_KEYS = ("nle", "nle_snapshot", NLE_PROJECT_STATE_RUNTIME_KEY)


def _fixture_project(media_path: Path, *, timeline_media_path: Path | None = None) -> dict[str, Any]:
    timeline_path = timeline_media_path or media_path
    return {
        "project_name": "nle_relink_parity",
        "mode": "single",
        "video": {"duration_sec": 6.0, "primary_fps": 30.0},
        "timeline": {
            "total_duration": 6.0,
            "timebase": {"primary_fps": 30.0},
            "tracks": [
                {
                    "clips": [
                        {
                            "id": "clip_main",
                            "source_path": str(timeline_path),
                            "type": "video",
                            "source_duration": 6.0,
                            "timeline_start": 0.0,
                            "timeline_end": 6.0,
                            "fps": 30.0,
                            "order": 0,
                        }
                    ]
                }
            ],
        },
        "editor_state": build_editor_state(
            mode="single",
            media_files=[str(media_path)],
            segments=[
                {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "first"},
                {"id": "caption_2", "start": 3.0, "end": 4.0, "text": "second"},
            ],
            primary_fps=30.0,
            preserve_segment_identity=True,
        ),
    }


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


def _runtime_check(tmp: Path) -> dict[str, Any]:
    original = tmp / "original.mov"
    relinked = tmp / "relinked.mov"
    original.write_bytes(b"old")
    relinked.write_bytes(b"new")
    project_path = tmp / "relinked.aissproj"
    project = _fixture_project(relinked)
    state = build_project_nle_state(project, project_path=str(project_path))
    signature = assert_nle_media_relink_parity(project, state, project_path=str(project_path))

    drift_error = ""
    drift_project = _fixture_project(relinked, timeline_media_path=original)
    drift_state = build_project_nle_state(drift_project, project_path=str(project_path))
    try:
        assert_nle_media_relink_parity(drift_project, drift_state, project_path=str(project_path))
    except Exception as exc:  # pragma: no cover - reported in audit output.
        drift_error = str(exc)

    return {
        "project_media_count": signature["project_media_count"],
        "nle_clip_count": signature["nle_clip_count"],
        "nle_asset_count": signature["nle_asset_count"],
        "project_primary_fps": signature["project_primary_fps"],
        "runtime_primary_fps": signature["runtime_primary_fps"],
        "sequence_fps": signature["sequence_fps"],
        "project_duration": signature["project_duration"],
        "sequence_duration": signature["sequence_duration"],
        "operation_journal_count": signature["operation_journal_count"],
        "relink_parity_consistent": True,
        "path_drift_rejected": "nle_media_path_order_drift" in drift_error,
        "path_drift_error": drift_error,
    }


def _storage_check(tmp: Path) -> dict[str, Any]:
    media = tmp / "source.mov"
    media.write_bytes(b"media")
    project_path = tmp / "storage.aissproj"
    project = _fixture_project(media)
    project[NLE_PROJECT_STATE_RUNTIME_KEY] = build_project_nle_state(project, project_path=str(project_path))
    project["nle"] = {"future": True}
    project["nle_snapshot"] = {"future": True}
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
    state_source = (ROOT / "core" / "project" / "nle_project_state.py").read_text(encoding="utf-8")
    snapshot_source = (ROOT / "core" / "project" / "nle_snapshot.py").read_text(encoding="utf-8")
    context_source = (ROOT / "core" / "project" / "project_context.py").read_text(encoding="utf-8")
    return {
        "relink_parity_helper_present": "def assert_nle_media_relink_parity(" in state_source,
        "relink_signature_helper_present": "def nle_media_relink_parity_signature(" in state_source,
        "project_media_projection_used": "project_media_files" in state_source,
        "snapshot_clip_paths_have_boundary_span": "\"boundary_span\"" in snapshot_source,
        "editor_state_media_files_present": "\"media_files\": normalized_media_files" in context_source,
    }


def build_nle_relink_parity_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="nle-relink-parity-") as tmp_name:
        tmp = Path(tmp_name)
        runtime = _runtime_check(tmp)
        storage = _storage_check(tmp)
    static = _static_contract_check()
    ready = (
        all(static.values())
        and runtime["relink_parity_consistent"]
        and runtime["path_drift_rejected"]
        and runtime["project_media_count"] == runtime["nle_clip_count"] == runtime["nle_asset_count"] == 1
        and runtime["project_primary_fps"] == runtime["runtime_primary_fps"] == runtime["sequence_fps"] == 30.0
        and runtime["project_duration"] == runtime["sequence_duration"] == 6.0
        and runtime["operation_journal_count"] == 0
        and storage["storage_forbidden_key_count"] == 0
    )
    return {
        "schema": SCHEMA,
        "audit_id": AUDIT_ID,
        "ready": bool(ready),
        "runtime_change_applied": False,
        "relink_parity_helper_present": static["relink_parity_helper_present"],
        "ui_layout_changed": False,
        "persisted_nle_fields_changed": False,
        "nas_required_for_contract": False,
        "static_contract": static,
        "runtime_check": runtime,
        "storage_check": storage,
        "blocked_scope": [
            "ui_layout_labels_colors_menus_popups",
            "persisted_nle_disk_format",
            "per_pixel_nle_writes",
            "subtitle_quality_or_stt_default_policy",
            "app_store_packaging_signing_upload",
            "automatic_relink_ui_or_dialog_behavior",
        ],
    }


def write_nle_relink_parity_report(output_dir: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "nle_relink_parity.json"
    markdown_path = output_dir / "nle_relink_parity.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    static = report["static_contract"]
    runtime = report["runtime_check"]
    storage = report["storage_check"]
    lines = [
        "# NLE Relink Parity Audit",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Audit ID: `{report['audit_id']}`",
        f"- Ready: `{report['ready']}`",
        f"- Runtime change applied: `{report['runtime_change_applied']}`",
        f"- Relink parity helper present: `{report['relink_parity_helper_present']}`",
        f"- UI layout changed: `{report['ui_layout_changed']}`",
        f"- Persisted NLE fields changed: `{report['persisted_nle_fields_changed']}`",
        f"- NAS required for contract: `{report['nas_required_for_contract']}`",
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
            f"- Project media count: `{runtime['project_media_count']}`",
            f"- NLE clip count: `{runtime['nle_clip_count']}`",
            f"- NLE asset count: `{runtime['nle_asset_count']}`",
            f"- Project primary FPS: `{runtime['project_primary_fps']}`",
            f"- Runtime primary FPS: `{runtime['runtime_primary_fps']}`",
            f"- Sequence FPS: `{runtime['sequence_fps']}`",
            f"- Project duration: `{runtime['project_duration']}`",
            f"- Sequence duration: `{runtime['sequence_duration']}`",
            f"- Operation journal count: `{runtime['operation_journal_count']}`",
            f"- Relink parity consistent: `{runtime['relink_parity_consistent']}`",
            f"- Path drift rejected: `{runtime['path_drift_rejected']}`",
            f"- Path drift error: `{runtime['path_drift_error']}`",
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
    report = build_nle_relink_parity_report()
    write_nle_relink_parity_report(args.output_dir, report)
    print(json.dumps({"ready": report["ready"], "output_dir": str(args.output_dir)}, ensure_ascii=False))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
