#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.native_json import dumps_json_bytes
from core.project.nle_dual_write import (
    CUT_MARKER_POINT_EVIDENCE_POLICY,
    apply_marker_edit_dual_write_pilot,
)
from core.project.nle_project_state import NLE_PROJECT_STATE_RUNTIME_KEY
from core.project.project_context import build_editor_state, project_clip_boundaries


SCHEMA = "ai_subtitle_studio.nle_cut_marker_point_projection.v1"
AUDIT_ID = "nle_cut_marker_point_projection_20260628"
TARGET_FRAMES = (2766, 2676)
SPAN_KEYS = frozenset(
    {
        "start",
        "end",
        "timeline_start",
        "timeline_end",
        "start_frame",
        "end_frame",
        "timeline_start_frame",
        "timeline_end_frame",
        "duration",
        "duration_sec",
        "span",
        "clip_span",
        "clip_range",
        "clip_boundary",
        "clip_boundary_id",
        "clip_id",
        "frame_range",
        "range",
        "timeline_range",
        "source_range",
        "source_start",
        "source_end",
        "source_frame_range",
    }
)
BLOCKED_SCOPE = (
    "clip_span_mapping_for_cut_marker_not_allowed",
    "persisted_nle_project_fields_not_approved",
    "per_pixel_drag_nle_writes_not_allowed",
    "ui_layout_or_label_changes_not_allowed",
    "stt_or_cache_default_policy_not_changed",
    "visual_threshold_relaxation_not_allowed",
)


def _fixture_project() -> tuple[dict[str, Any], dict[str, Any]]:
    media_files = ["/tmp/a.mp4", "/tmp/b.mp4"]
    confirmed = {
        "timeline_frame": 2766,
        "timeline_sec": 2766.0 / 30.0,
        "fps": 30.0,
        "status": "confirmed",
        "source": "visual",
        "start": 91.5,
        "end": 92.8,
        "clip_span": {"clip_id": "clip_a", "start": 91.5, "end": 92.8},
        "clip_boundary_id": "clip_a_to_b",
    }
    marker = {
        "timeline_frame": 2676,
        "timeline_sec": 2676.0 / 30.0,
        "fps": 30.0,
        "status": "provisional",
        "start": 88.8,
        "end": 90.1,
        "timeline_start": 88.8,
        "timeline_end": 90.1,
        "source_start": 1.0,
        "source_end": 2.3,
        "clip_span": {"clip_id": "clip_b", "start": 88.8, "end": 90.1},
        "clip_boundary_id": "clip_b_internal",
    }
    project = {
        "project_name": "nle_cut_marker_point_projection",
        "mode": "multiclip",
        "video": {"duration_sec": 120.0, "primary_fps": 30.0},
        "editor_state": build_editor_state(
            mode="multiclip",
            media_files=media_files,
            segments=[
                {"id": "caption_1", "start": 88.0, "end": 89.0, "text": "before"},
                {"id": "caption_2", "start": 90.0, "end": 92.0, "text": "after"},
            ],
            clip_boundaries=[
                {"start": 0.0, "end": 60.0, "file": media_files[0], "name": "a.mp4"},
                {"start": 60.0, "end": 120.0, "file": media_files[1], "name": "b.mp4"},
            ],
            cut_boundaries=[confirmed],
            primary_fps=30.0,
            preserve_segment_identity=True,
        ),
    }
    return project, marker


def _marker_rows(project: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    analysis = ((project.get("editor_state") or {}).get("analysis") or {})
    confirmed = [dict(row) for row in list(analysis.get("cut_boundaries") or []) if isinstance(row, dict)]
    provisional = [
        dict(row)
        for row in list(analysis.get("cut_boundary_provisional_boundaries") or [])
        if isinstance(row, dict)
    ]
    return confirmed, provisional


def _span_leaks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    leaks: list[dict[str, Any]] = []
    for row in rows:
        leaked = sorted(SPAN_KEYS & set(row))
        if leaked:
            leaks.append({"timeline_frame": row.get("timeline_frame"), "leaked_keys": leaked})
    return leaks


def _projection_gate(result: Any) -> dict[str, Any]:
    report = result.after_projection
    passed = (
        report.diff_summary == "ok"
        and report.invalid_duration_count == 0
        and report.non_monotonic_count == 0
        and report.overlap_count == 0
        and report.max_active_segments <= 1
        and report.save_reload_stable
        and report.global_canvas_stable
    )
    return {
        "passed": passed,
        "diff_summary": report.diff_summary,
        "invalid_duration_count": report.invalid_duration_count,
        "non_monotonic_count": report.non_monotonic_count,
        "overlap_count": report.overlap_count,
        "max_active_segments": report.max_active_segments,
        "save_reload_stable": report.save_reload_stable,
        "global_canvas_stable": report.global_canvas_stable,
    }


def build_nle_cut_marker_point_projection_audit(*, output_dir: Path | None = None) -> dict[str, Any]:
    project, marker = _fixture_project()
    before_clip_boundaries = copy.deepcopy(project_clip_boundaries(project))
    result = apply_marker_edit_dual_write_pilot(
        project,
        action="create",
        marker=marker,
        before_markers=[],
        after_markers=[marker],
        commit_source="provisional_cut_boundary_create",
    )
    after_clip_boundaries = project_clip_boundaries(project)
    confirmed_rows, provisional_rows = _marker_rows(project)
    all_marker_rows = confirmed_rows + provisional_rows
    span_leaks = _span_leaks(all_marker_rows)
    frames = [int(row.get("timeline_frame", 0) or 0) for row in all_marker_rows]
    projection_gate = _projection_gate(result)
    runtime_metadata = dict((project.get(NLE_PROJECT_STATE_RUNTIME_KEY).metadata or {}))
    passed = (
        frames == list(TARGET_FRAMES)
        and not span_leaks
        and before_clip_boundaries == after_clip_boundaries
        and result.operation.metadata.get("marker_projection_policy") == CUT_MARKER_POINT_EVIDENCE_POLICY
        and result.operation.metadata.get("clip_span_mapping_allowed") is False
        and runtime_metadata.get("dual_write_marker_projection_policy") == CUT_MARKER_POINT_EVIDENCE_POLICY
        and runtime_metadata.get("dual_write_marker_clip_span_mapping_allowed") is False
        and projection_gate["passed"]
    )
    manifest = {
        "schema": SCHEMA,
        "audit_id": AUDIT_ID,
        "project_lane": "AI Subtitle Studio",
        "source_reference": "Taption cut marker semantics, adapted to AI Subtitle Studio PyQt/source-app runtime",
        "target_frames": list(TARGET_FRAMES),
        "observed_frames": frames,
        "marker_projection_policy": CUT_MARKER_POINT_EVIDENCE_POLICY,
        "confirmed_cut_markers_are_point_evidence": True,
        "clip_span_mapping_allowed": False,
        "span_leak_count": len(span_leaks),
        "span_leaks": span_leaks,
        "clip_boundaries_unchanged": before_clip_boundaries == after_clip_boundaries,
        "projection_gate": projection_gate,
        "operation_metadata": dict(result.operation.metadata),
        "runtime_metadata": runtime_metadata,
        "blocked_scope": list(BLOCKED_SCOPE),
        "nas_required_for_runtime_media_acceptance": True,
        "passed": passed,
    }
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "nle_cut_marker_point_projection.json"
        md_path = output_dir / "nle_cut_marker_point_projection.md"
        json_path.write_bytes(dumps_json_bytes(manifest, indent=2, sort_keys=True, append_newline=True))
        manifest["artifact_path"] = str(json_path)
        _write_markdown(md_path, manifest)
    return manifest


def _write_markdown(path: Path, manifest: dict[str, Any]) -> None:
    gate = dict(manifest.get("projection_gate") or {})
    lines = [
        "# NLE Cut Marker Point Projection Audit",
        "",
        f"- Project lane: `{manifest.get('project_lane')}`",
        f"- Passed: `{bool(manifest.get('passed'))}`",
        f"- Target frames: `{','.join(str(frame) for frame in manifest.get('target_frames', []))}`",
        f"- Observed frames: `{','.join(str(frame) for frame in manifest.get('observed_frames', []))}`",
        f"- Marker projection policy: `{manifest.get('marker_projection_policy')}`",
        f"- Clip span mapping allowed: `{bool(manifest.get('clip_span_mapping_allowed'))}`",
        f"- Span leak count: `{int(manifest.get('span_leak_count', 0) or 0)}`",
        f"- Clip boundaries unchanged: `{bool(manifest.get('clip_boundaries_unchanged'))}`",
        f"- Projection overlap count: `{gate.get('overlap_count')}`",
        f"- Projection max active segments: `{gate.get('max_active_segments')}`",
        "",
        "## Contract",
        "",
        "- Confirmed and provisional cut markers are point evidence.",
        "- Marker rows must not carry clip-span mapping into the legacy editor context.",
        "- The operation may update provisional cut marker state, but must not mutate clip boundaries.",
        "",
        "## Blocked Scope",
        "",
    ]
    for item in list(manifest.get("blocked_scope") or []):
        lines.append(f"- `{item}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit NLE cut marker point-evidence projection.")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    manifest = build_nle_cut_marker_point_projection_audit(output_dir=args.output_dir)
    print(dumps_json_bytes(manifest, indent=2, sort_keys=True).decode("utf-8"))
    return 0 if manifest.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
