from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any

from core.frame_time import normalize_fps, sec_to_nearest_frame
from core.project.nle_projection_parity import build_project_nle_projection_parity_report
from core.project.nle_snapshot import NLESnapshot, build_project_nle_snapshot
from core.project.project_context import project_segments_to_editor
from core.project.project_format import project_primary_fps
from core.project.project_roughcut_store import selected_roughcut_candidate

NLE_RENDER_EXPORT_PARITY_SCHEMA = "ai_subtitle_studio.nle_render_export_parity.v1"


@dataclass(frozen=True, slots=True)
class RenderExportSurfaceReport:
    target_surface: str
    stable: bool
    projection_hash: str = ""
    caption_count: int = 0
    gap_count: int = 0
    candidate_count: int = 0
    marker_count: int = 0
    render_segment_count: int = 0
    manifest_count: int = 0
    stitched_boundary_count: int = 0
    diff_summary: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RenderExportParityReport:
    schema: str
    projection_id: str
    final_projection_hash: str
    caption_count: int
    gap_count: int
    candidate_count: int
    marker_count: int
    invalid_duration_count: int
    non_monotonic_count: int
    overlap_count: int
    max_active_segments: int
    render_segment_count: int
    manifest_count: int
    stitched_boundary_count: int
    diff_summary: str
    surface_reports: tuple[RenderExportSurfaceReport, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["surface_reports"] = [surface.to_dict() for surface in self.surface_reports]
        return payload


_CANDIDATE_KEYS = (
    "stt_candidates",
    "stt_lattice_candidates",
    "manual_stt_candidates",
    "stt_retry_candidates",
    "stt_recheck_candidates",
    "stt_rescue_candidates",
)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _frame_bounds(row: dict[str, Any], *, fps: float) -> tuple[int, int]:
    frame_range = row.get("frame_range") if isinstance(row.get("frame_range"), dict) else {}
    start_frame = row.get("start_frame", row.get("timeline_start_frame", frame_range.get("start")))
    end_frame = row.get("end_frame", row.get("timeline_end_frame", frame_range.get("end")))
    if start_frame is None:
        start_frame = sec_to_nearest_frame(_as_float(row.get("start", row.get("timeline_start", 0.0))), fps)
    if end_frame is None:
        end_frame = sec_to_nearest_frame(_as_float(row.get("end", row.get("timeline_end", 0.0))), fps)
    start = _as_int(start_frame, 0)
    return start, max(start, _as_int(end_frame, start))


def _final_rows(rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    return [
        row
        for row in list(rows or [])
        if isinstance(row, dict)
        and not bool(row.get("is_gap"))
        and not bool(row.get("stt_pending"))
        and not bool(row.get("_live_stt_preview"))
        and not bool(row.get("_live_subtitle_preview"))
    ]


def _gap_count(rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> int:
    return len([row for row in list(rows or []) if isinstance(row, dict) and bool(row.get("is_gap"))])


def _candidate_count_from_rows(rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> int:
    total = 0
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        for key in _CANDIDATE_KEYS:
            value = row.get(key)
            if isinstance(value, list):
                total += len([item for item in value if isinstance(item, dict)])
    return total


def _projection_hash(rows: tuple[dict[str, Any], ...]) -> str:
    raw = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _row_projection(rows: list[dict[str, Any]], *, fps: float) -> tuple[dict[str, Any], ...]:
    projected: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        start, end = _frame_bounds(row, fps=fps)
        projected.append(
            {
                "index": index,
                "id": str(row.get("id") or row.get("index") or f"caption_{index + 1:04d}"),
                "start_frame": start,
                "end_frame": end,
                "text": str(row.get("text") or ""),
                "speaker": str(row.get("speaker") or row.get("spk") or ""),
            }
        )
    return tuple(projected)


def _caption_projection(snapshot: NLESnapshot, *, fps: float) -> tuple[dict[str, Any], ...]:
    sequence = snapshot.sequences[0] if snapshot.sequences else None
    captions = list(sequence.captions if sequence is not None else ())
    projected: list[dict[str, Any]] = []
    for index, caption in enumerate(captions):
        start = sec_to_nearest_frame(_as_float(getattr(caption, "sequence_start", 0.0)), fps)
        end = sec_to_nearest_frame(_as_float(getattr(caption, "sequence_end", 0.0)), fps)
        projected.append(
            {
                "index": index,
                "id": str(getattr(caption, "caption_id", "") or f"caption_{index + 1:04d}"),
                "start_frame": start,
                "end_frame": max(start, end),
                "text": str(getattr(caption, "text", "") or ""),
                "speaker": str(getattr(caption, "speaker", "") or ""),
            }
        )
    return tuple(projected)


def _selected_outputs(project: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    selected = selected_roughcut_candidate(project.get("roughcut_state"))
    outputs = selected.get("outputs") if isinstance(selected, dict) and isinstance(selected.get("outputs"), dict) else {}
    edl = outputs.get("edl") if isinstance(outputs.get("edl"), dict) else {}
    render_plan = outputs.get("render_plan") if isinstance(outputs.get("render_plan"), dict) else {}
    return selected if isinstance(selected, dict) else {}, edl, render_plan


def _rows(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(dict(row) for row in value if isinstance(row, dict))


def _stitched_rows(edl: dict[str, Any], render_plan: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    render_rows = _rows(render_plan.get("stitched_cut_boundaries"))
    if render_rows:
        return render_rows
    return _rows(edl.get("stitched_cut_boundaries"))


def _roughcut_marker_count(snapshot: NLESnapshot) -> int:
    sequence = snapshot.sequences[0] if snapshot.sequences else None
    markers = list(sequence.markers if sequence is not None else ())
    return len([marker for marker in markers if marker.kind == "roughcut_exact_join"])


def _surface(
    target: str,
    *,
    stable: bool,
    projection_hash: str = "",
    caption_count: int = 0,
    gap_count: int = 0,
    candidate_count: int = 0,
    marker_count: int = 0,
    render_segment_count: int = 0,
    manifest_count: int = 0,
    stitched_boundary_count: int = 0,
    diff_summary: str = "ok",
) -> RenderExportSurfaceReport:
    return RenderExportSurfaceReport(
        target_surface=target,
        stable=stable,
        projection_hash=projection_hash,
        caption_count=caption_count,
        gap_count=gap_count,
        candidate_count=candidate_count,
        marker_count=marker_count,
        render_segment_count=render_segment_count,
        manifest_count=manifest_count,
        stitched_boundary_count=stitched_boundary_count,
        diff_summary=diff_summary if not stable else "ok",
    )


def build_project_nle_render_export_parity_report(
    project: dict[str, Any],
    *,
    project_path: str = "",
) -> RenderExportParityReport:
    source = project if isinstance(project, dict) else {}
    fps = normalize_fps(project_primary_fps(source))
    base_report = build_project_nle_projection_parity_report(source, project_path=project_path)
    snapshot = build_project_nle_snapshot(source, project_path=project_path)
    all_rows = project_segments_to_editor(source, include_analysis_candidates=False)
    final_rows = _final_rows(all_rows)
    source_projection = _row_projection(final_rows, fps=fps)
    nle_projection = _caption_projection(snapshot, fps=fps)
    source_hash = _projection_hash(source_projection)
    nle_hash = _projection_hash(nle_projection)
    selected, edl, render_payload = _selected_outputs(source)
    edl_segments = _rows(edl.get("segments"))
    manifest = _rows(render_payload.get("segment_manifest"))
    sidecar_stitched = _stitched_rows(edl, render_payload)
    render_plan = snapshot.render_plans[0] if snapshot.render_plans else None
    snapshot_segments = tuple(render_plan.segments if render_plan is not None else ())
    snapshot_manifest = tuple(render_plan.segment_manifest if render_plan is not None else ())
    snapshot_stitched = tuple(render_plan.stitched_cut_boundaries if render_plan is not None else ())
    roughcut_marker_count = _roughcut_marker_count(snapshot)

    source_stable = source_projection == nle_projection
    overlay_stable = source_stable and base_report.overlap_count == 0 and base_report.max_active_segments <= 1
    global_stable = source_stable and base_report.global_canvas_stable
    has_render_outputs = bool(selected and (edl or render_payload))
    sidecar_stable = (
        not has_render_outputs
        or (
            len(snapshot_stitched) == len(sidecar_stitched)
            and roughcut_marker_count == len(sidecar_stitched)
            and tuple(snapshot_stitched) == tuple(sidecar_stitched)
        )
    )
    export_stable = (
        not has_render_outputs
        or (
            render_plan is not None
            and tuple(snapshot_segments) == tuple(edl_segments)
            and tuple(snapshot_manifest) == tuple(manifest)
            and (not manifest or len(snapshot_manifest) == len(snapshot_segments))
            and tuple(snapshot_stitched) == tuple(sidecar_stitched)
        )
    )

    surfaces = (
        _surface(
            "source_subtitles",
            stable=source_stable,
            projection_hash=source_hash,
            caption_count=len(source_projection),
            gap_count=_gap_count(all_rows),
            candidate_count=_candidate_count_from_rows(all_rows),
            diff_summary="source_subtitle_projection_drift",
        ),
        _surface(
            "final_overlay",
            stable=overlay_stable,
            projection_hash=nle_hash,
            caption_count=len(nle_projection),
            gap_count=0,
            candidate_count=0,
            diff_summary="final_overlay_projection_drift",
        ),
        _surface(
            "global_canvas",
            stable=global_stable,
            projection_hash=source_hash,
            caption_count=len(source_projection),
            gap_count=_gap_count(all_rows),
            candidate_count=_candidate_count_from_rows(all_rows),
            marker_count=base_report.marker_count,
            diff_summary="global_canvas_projection_drift",
        ),
        _surface(
            "roughcut_sidecar",
            stable=sidecar_stable,
            projection_hash=nle_hash,
            caption_count=len(nle_projection),
            marker_count=roughcut_marker_count,
            stitched_boundary_count=len(snapshot_stitched),
            diff_summary="roughcut_sidecar_projection_drift",
        ),
        _surface(
            "exported_assets",
            stable=export_stable,
            projection_hash=nle_hash,
            caption_count=len(nle_projection),
            render_segment_count=len(snapshot_segments),
            manifest_count=len(snapshot_manifest),
            stitched_boundary_count=len(snapshot_stitched),
            diff_summary="export_asset_projection_drift",
        ),
    )
    diff_summary = "ok" if all(surface.stable for surface in surfaces) else ";".join(
        surface.diff_summary for surface in surfaces if not surface.stable
    )
    return RenderExportParityReport(
        schema=NLE_RENDER_EXPORT_PARITY_SCHEMA,
        projection_id="project_nle_render_export_parity_v1",
        final_projection_hash=nle_hash,
        caption_count=len(nle_projection),
        gap_count=_gap_count(all_rows),
        candidate_count=_candidate_count_from_rows(all_rows),
        marker_count=base_report.marker_count,
        invalid_duration_count=base_report.invalid_duration_count,
        non_monotonic_count=base_report.non_monotonic_count,
        overlap_count=base_report.overlap_count,
        max_active_segments=base_report.max_active_segments,
        render_segment_count=len(snapshot_segments),
        manifest_count=len(snapshot_manifest),
        stitched_boundary_count=len(snapshot_stitched),
        diff_summary=diff_summary,
        surface_reports=surfaces,
    )


def assert_project_nle_render_export_parity(
    project: dict[str, Any],
    *,
    project_path: str = "",
) -> RenderExportParityReport:
    report = build_project_nle_render_export_parity_report(project, project_path=project_path)
    if (
        report.diff_summary != "ok"
        or report.invalid_duration_count != 0
        or report.non_monotonic_count != 0
        or report.overlap_count != 0
        or report.max_active_segments > 1
    ):
        raise ValueError(f"nle_render_export_parity_failed:{report.diff_summary}")
    return report


__all__ = [
    "NLE_RENDER_EXPORT_PARITY_SCHEMA",
    "RenderExportParityReport",
    "RenderExportSurfaceReport",
    "assert_project_nle_render_export_parity",
    "build_project_nle_render_export_parity_report",
]
