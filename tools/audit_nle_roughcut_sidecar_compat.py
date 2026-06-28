#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.project.nle_render_export_parity import assert_project_nle_render_export_parity  # noqa: E402
from core.project.project_context import build_editor_state  # noqa: E402
from core.project.project_io import (  # noqa: E402
    clear_project_file_cache,
    read_project_file,
    read_project_storage_payload,
    write_project_file,
)
from core.roughcut import (  # noqa: E402
    ChapterMetadata,
    EDLSegment,
    RoughCutMinorGroup,
    RoughCutSegment,
    build_concat_render_plan,
    edl_to_dict,
)
from ui.editor.editor_project_open_native import load_stitched_cut_boundaries_for_srt_open  # noqa: E402


SCHEMA = "ai_subtitle_studio.nle_roughcut_sidecar_compat.v1"
AUDIT_ID = "nle_roughcut_sidecar_compat_20260628"
FORBIDDEN_NLE_STORAGE_KEYS = ("nle", "nle_snapshot", "_nle_project_state")
BLOCKED_SCOPE = (
    "persisted_nle_project_fields_not_approved",
    "per_pixel_nle_writes_not_allowed",
    "ui_layout_or_label_changes_not_allowed",
    "stt_default_policy_changes_not_allowed",
    "app_store_packaging_not_allowed",
)


def _forbidden_key_paths(value: Any, *, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        paths: list[str] = []
        for key, item in value.items():
            current = f"{prefix}.{key}" if prefix else str(key)
            if str(key) in FORBIDDEN_NLE_STORAGE_KEYS:
                paths.append(current)
            paths.extend(_forbidden_key_paths(item, prefix=current))
        return paths
    if isinstance(value, list):
        paths = []
        for index, item in enumerate(value):
            paths.extend(_forbidden_key_paths(item, prefix=f"{prefix}[{index}]"))
        return paths
    return []


def _fixture(root: Path) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    media_path = root / "source.mov"
    media_path.write_bytes(b"roughcut-source-media")
    chapters = (
        ChapterMetadata("chapter_0001", "first", 0.0, 2.0, major_id="A", minor_code="A1"),
        ChapterMetadata("chapter_0002", "second", 3.0, 6.0, major_id="A", minor_code="A2"),
    )
    majors = (
        RoughCutSegment(
            "major_A",
            0.0,
            6.0,
            major_id="A",
            title="A",
            minor_groups=(
                RoughCutMinorGroup("A1", "A", "A1", "first", 0.0, 2.0, chapter_ids=("chapter_0001",)),
                RoughCutMinorGroup("A2", "A", "A2", "second", 3.0, 6.0, chapter_ids=("chapter_0002",)),
            ),
        ),
    )
    edl_segments = (
        EDLSegment(str(media_path), "chapter_0001", 0.0, 2.0, 0.0, 2.0, chapter_id="chapter_0001"),
        EDLSegment(str(media_path), "chapter_0002", 3.0, 6.0, 2.0, 5.0, chapter_id="chapter_0002"),
    )
    edl_payload = edl_to_dict(
        edl_segments,
        metadata={"source": str(media_path)},
        chapters=chapters,
        major_segments=majors,
    )
    plan = build_concat_render_plan(edl_segments, root / "roughcut.mov", root / "parts", render_mode="sync_safe")
    srt_path = root / "clip_roughcut.srt"
    srt_path.write_text("", encoding="utf-8")
    render_payload = {
        "stitched_cut_boundaries": list(getattr(plan, "stitched_cut_boundaries", ()) or ()),
        "edl": edl_payload,
        "render_plan": asdict(plan),
        "render_mode": getattr(plan, "render_mode", "sync_safe"),
    }
    render_plan_path = srt_path.with_name(f"{srt_path.stem}_render_plan.json")
    edl_path = srt_path.with_name(f"{srt_path.stem}_edl.json")
    render_plan_path.write_text(json.dumps(render_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    edl_path.write_text(json.dumps(edl_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    loaded_render = json.loads(render_plan_path.read_text(encoding="utf-8"))
    loaded_edl = json.loads(edl_path.read_text(encoding="utf-8"))
    return srt_path, media_path, loaded_render, loaded_edl


def _project_from_sidecars(root: Path, media_path: Path, render_payload: dict[str, Any], edl_payload: dict[str, Any]) -> dict:
    return {
        "project_name": "nle_roughcut_sidecar_compat",
        "mode": "single",
        "video": {"duration_sec": 6.0, "primary_fps": 30.0},
        "editor_state": build_editor_state(
            mode="single",
            media_files=[str(media_path)],
            segments=[
                {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "first", "speaker": "00"},
                {"id": "gap_1", "start": 1.0, "end": 2.0, "text": "", "is_gap": True},
                {"id": "caption_2", "start": 2.0, "end": 3.0, "text": "second", "speaker": "01"},
            ],
            cut_boundaries=[{"time": 2.0, "source": "visual", "status": "confirmed"}],
            primary_fps=30.0,
        ),
        "analysis": {"cut_boundaries": [{"time": 2.0, "source": "visual", "status": "confirmed"}]},
        "roughcut_state": {
            "selected_candidate_id": "roughcut_a",
            "candidates": [
                {
                    "candidate_id": "roughcut_a",
                    "name": "roughcut A",
                    "outputs": {
                        "edl": edl_payload,
                        "render_plan": dict(render_payload.get("render_plan") or {}),
                    },
                }
            ],
        },
    }


def build_nle_roughcut_sidecar_compat_report(*, output_dir: Path) -> dict[str, Any]:
    work_dir = output_dir / "_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    srt_path, media_path, render_payload, edl_payload = _fixture(work_dir)
    restored_rows, restored_sidecar_path = load_stitched_cut_boundaries_for_srt_open(str(srt_path), str(media_path))
    project = _project_from_sidecars(work_dir, media_path, render_payload, edl_payload)
    parity = assert_project_nle_render_export_parity(project, project_path=str(work_dir / "sidecar.aissproj"))

    dirty_project = copy.deepcopy(project)
    dirty_project["nle"] = {"future": True}
    dirty_project["nle_snapshot"] = {"future": True}
    dirty_project["_nle_project_state"] = {"runtime": True}
    project_path = work_dir / "sidecar.aissproj"
    write_project_file(str(project_path), dirty_project)
    clear_project_file_cache(str(project_path))
    loaded_project = read_project_file(str(project_path))
    storage_payload = read_project_storage_payload(str(project_path))

    sidecar_forbidden_paths = _forbidden_key_paths(render_payload) + _forbidden_key_paths(edl_payload)
    storage_forbidden_paths = _forbidden_key_paths(storage_payload)
    surfaces = {surface.target_surface: surface.to_dict() for surface in parity.surface_reports}
    sidecar_rows = list(render_payload.get("stitched_cut_boundaries") or [])
    sidecar_restore_matches = bool(restored_rows) and [row.get("timeline_sec") for row in restored_rows] == [
        row.get("timeline_sec") for row in sidecar_rows
    ]
    ready = (
        sidecar_restore_matches
        and parity.diff_summary == "ok"
        and parity.invalid_duration_count == 0
        and parity.non_monotonic_count == 0
        and parity.overlap_count == 0
        and parity.max_active_segments <= 1
        and surfaces.get("roughcut_sidecar", {}).get("stable") is True
        and surfaces.get("exported_assets", {}).get("stable") is True
        and not sidecar_forbidden_paths
        and not storage_forbidden_paths
    )
    return {
        "schema": SCHEMA,
        "audit_id": AUDIT_ID,
        "ready": ready,
        "runtime_behavior_changed": False,
        "ui_layout_change_applied": False,
        "persisted_nle_fields_changed": False,
        "sidecar_files_written": True,
        "srt_path": str(srt_path),
        "restored_sidecar_path": str(restored_sidecar_path),
        "sidecar_restore_matches": sidecar_restore_matches,
        "sidecar_forbidden_key_count": len(sidecar_forbidden_paths),
        "sidecar_forbidden_key_paths": sidecar_forbidden_paths,
        "storage_forbidden_key_count": len(storage_forbidden_paths),
        "storage_forbidden_key_paths": storage_forbidden_paths,
        "runtime_nle_state_hydrated_after_read": "_nle_project_state" in loaded_project,
        "parity_diff_summary": parity.diff_summary,
        "final_invalid_duration_count": parity.invalid_duration_count,
        "final_non_monotonic_count": parity.non_monotonic_count,
        "final_overlap_count": parity.overlap_count,
        "global_max_active_segments": parity.max_active_segments,
        "roughcut_sidecar_stable": surfaces.get("roughcut_sidecar", {}).get("stable") is True,
        "exported_assets_stable": surfaces.get("exported_assets", {}).get("stable") is True,
        "render_segment_count": parity.render_segment_count,
        "manifest_count": parity.manifest_count,
        "stitched_boundary_count": parity.stitched_boundary_count,
        "surface_reports": list(surfaces.values()),
        "blocked_scope": list(BLOCKED_SCOPE),
    }


def write_nle_roughcut_sidecar_compat_report(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "nle_roughcut_sidecar_compat.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# NLE Roughcut Sidecar Compatibility Audit",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Ready: `{report['ready']}`",
        f"- Runtime behavior changed: `{report['runtime_behavior_changed']}`",
        f"- UI layout change applied: `{report['ui_layout_change_applied']}`",
        f"- Persisted NLE fields changed: `{report['persisted_nle_fields_changed']}`",
        f"- Sidecar files written: `{report['sidecar_files_written']}`",
        f"- Sidecar restore matches: `{report['sidecar_restore_matches']}`",
        f"- Parity diff summary: `{report['parity_diff_summary']}`",
        f"- Final invalid/non-monotonic/overlap: `{report['final_invalid_duration_count']}/{report['final_non_monotonic_count']}/{report['final_overlap_count']}`",
        f"- Global max active segments: `{report['global_max_active_segments']}`",
        f"- Roughcut sidecar stable: `{report['roughcut_sidecar_stable']}`",
        f"- Exported assets stable: `{report['exported_assets_stable']}`",
        f"- Render/manifest/stitched counts: `{report['render_segment_count']}/{report['manifest_count']}/{report['stitched_boundary_count']}`",
        f"- Sidecar forbidden key count: `{report['sidecar_forbidden_key_count']}`",
        f"- Storage forbidden key count: `{report['storage_forbidden_key_count']}`",
        "",
        "## Blocked Scope",
        "",
    ]
    lines.extend(f"- `{item}`" for item in report["blocked_scope"])
    (output_dir / "nle_roughcut_sidecar_compat.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit roughcut sidecar compatibility with NLE render/export parity.")
    parser.add_argument(
        "--output-dir",
        default="output/manual_verification/latest/nle_roughcut_sidecar_compat_20260628",
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    report = build_nle_roughcut_sidecar_compat_report(output_dir=output_dir)
    write_nle_roughcut_sidecar_compat_report(output_dir, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report.get("ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
