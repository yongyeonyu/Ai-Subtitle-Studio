from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from core.frame_time import normalize_fps, sec_to_nearest_frame
from core.project.nle_project_state import (
    assert_nle_editor_rows_consistent,
    build_project_nle_state,
)
from core.project.nle_snapshot import NLESnapshot, build_project_nle_snapshot
from core.project.project_context import project_segments_to_editor
from core.project.project_format import project_primary_fps
from core.project.project_roughcut_store import selected_roughcut_candidate


@dataclass(frozen=True, slots=True)
class ProjectionSurfaceParity:
    target_surface: str
    stable: bool
    caption_count: int = 0
    gap_count: int = 0
    candidate_count: int = 0
    marker_count: int = 0
    diff_summary: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProjectionParityReport:
    projection_id: str
    source: str
    target_surface: str
    caption_count: int
    gap_count: int
    candidate_count: int
    marker_count: int
    invalid_duration_count: int
    non_monotonic_count: int
    overlap_count: int
    max_active_segments: int
    save_reload_stable: bool
    global_canvas_stable: bool
    render_export_stable: bool
    diff_summary: str
    surface_reports: tuple[ProjectionSurfaceParity, ...] = field(default_factory=tuple)

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


def _caption_frame_bounds(caption: Any, *, fps: float) -> tuple[int, int]:
    start = sec_to_nearest_frame(_as_float(getattr(caption, "sequence_start", 0.0)), fps)
    end = sec_to_nearest_frame(_as_float(getattr(caption, "sequence_end", 0.0)), fps)
    return start, max(start, end)


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


def _gap_rows(rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    return [row for row in list(rows or []) if isinstance(row, dict) and bool(row.get("is_gap"))]


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


def _candidate_track_count(project: dict[str, Any]) -> int:
    editor_state = project.get("editor_state") if isinstance(project.get("editor_state"), dict) else {}
    stt_state = editor_state.get("stt") if isinstance(editor_state.get("stt"), dict) else {}
    tracks = stt_state.get("candidate_tracks") if isinstance(stt_state.get("candidate_tracks"), dict) else {}
    return sum(len(rows) for rows in tracks.values() if isinstance(rows, list))


def _final_timing_metrics(rows: list[dict[str, Any]], *, fps: float) -> tuple[int, int, int, int]:
    invalid = 0
    non_monotonic = 0
    overlap = 0
    previous_start: int | None = None
    previous_end: int | None = None
    events: list[tuple[int, int]] = []
    for row in rows:
        start, end = _frame_bounds(row, fps=fps)
        if end <= start:
            invalid += 1
        if previous_start is not None and start < previous_start:
            non_monotonic += 1
        if previous_end is not None and start < previous_end:
            overlap += 1
        previous_start = start
        previous_end = end
        if end > start:
            events.append((start, 1))
            events.append((end, -1))
    active = 0
    max_active = 0
    for _frame, delta in sorted(events, key=lambda item: (item[0], item[1])):
        active += delta
        max_active = max(max_active, active)
    return invalid, non_monotonic, overlap, max_active


def _render_export_stable(project: dict[str, Any], snapshot: NLESnapshot) -> bool:
    selected = selected_roughcut_candidate(project.get("roughcut_state"))
    if not selected:
        return len(snapshot.render_plans) == 0
    outputs = selected.get("outputs") if isinstance(selected.get("outputs"), dict) else {}
    edl = outputs.get("edl") if isinstance(outputs.get("edl"), dict) else {}
    render_payload = outputs.get("render_plan") if isinstance(outputs.get("render_plan"), dict) else {}
    if not edl and not render_payload:
        return len(snapshot.render_plans) == 0
    if len(snapshot.render_plans) != 1:
        return False
    plan = snapshot.render_plans[0]
    edl_segments = [row for row in list(edl.get("segments") or []) if isinstance(row, dict)]
    manifest = [row for row in list(render_payload.get("segment_manifest") or []) if isinstance(row, dict)]
    stitched = list(edl.get("stitched_cut_boundaries") or render_payload.get("stitched_cut_boundaries") or [])
    if edl_segments and len(plan.segments) != len(edl_segments):
        return False
    if manifest and len(plan.segment_manifest) != len(manifest):
        return False
    if stitched and len(plan.stitched_cut_boundaries) != len(stitched):
        return False
    return True


def build_project_nle_projection_parity_report(
    project: dict[str, Any],
    *,
    project_path: str = "",
) -> ProjectionParityReport:
    source = project if isinstance(project, dict) else {}
    fps = normalize_fps(project_primary_fps(source))
    legacy_rows = project_segments_to_editor(source, include_analysis_candidates=False)
    nle_state = build_project_nle_state(source, project_path=project_path)
    nle_rows = nle_state.editor_rows()
    snapshot = build_project_nle_snapshot(source, project_path=project_path)
    sequence = snapshot.sequences[0] if snapshot.sequences else None

    diffs: list[str] = []
    try:
        assert_nle_editor_rows_consistent(legacy_rows, nle_rows, primary_fps=fps)
    except ValueError as exc:
        diffs.append(str(exc))

    legacy_final = _final_rows(legacy_rows)
    nle_final = _final_rows(nle_rows)
    legacy_gaps = _gap_rows(legacy_rows)
    nle_gaps = _gap_rows(nle_rows)
    captions = list(sequence.captions if sequence is not None else ())
    markers = list(sequence.markers if sequence is not None else ())
    candidate_count = max(_candidate_count_from_rows(legacy_rows), _candidate_count_from_rows(nle_rows), _candidate_track_count(source))

    if len(legacy_final) != len(captions):
        diffs.append(f"caption_count:{len(legacy_final)}!={len(captions)}")
    for index, (row, caption) in enumerate(zip(legacy_final, captions)):
        if _frame_bounds(row, fps=fps) != _caption_frame_bounds(caption, fps=fps):
            diffs.append(f"caption_frame_drift:{index}")
        if str(row.get("text", "") or "") != str(caption.text or ""):
            diffs.append(f"caption_text_drift:{index}")
        if str(row.get("speaker", row.get("spk", "")) or "") != str(caption.speaker or ""):
            diffs.append(f"caption_speaker_drift:{index}")
        if _candidate_count_from_rows([row]) != _candidate_count_from_rows([dict(caption.metadata or {})]):
            diffs.append(f"caption_candidate_metadata_drift:{index}")

    invalid, non_monotonic, overlap, max_active = _final_timing_metrics(legacy_final, fps=fps)
    if invalid or non_monotonic or overlap or max_active > 1:
        diffs.append(
            "final_timing:"
            f"invalid={invalid},non_monotonic={non_monotonic},overlap={overlap},max_active={max_active}"
        )

    timeline_stable = not diffs and len(legacy_rows) == len(nle_rows)
    overlay_stable = len(legacy_final) == len(captions) and invalid == 0 and non_monotonic == 0 and overlap == 0 and max_active <= 1
    global_canvas_stable = timeline_stable and len(legacy_gaps) == len(nle_gaps) and _candidate_track_count(source) == candidate_count
    save_reload_stable = timeline_stable and "nle" not in source and "nle_snapshot" not in source
    render_export_stable = _render_export_stable(source, snapshot)

    surfaces = (
        ProjectionSurfaceParity(
            "timeline",
            timeline_stable,
            caption_count=len(legacy_final),
            gap_count=len(legacy_gaps),
            candidate_count=candidate_count,
            marker_count=len(markers),
            diff_summary="ok" if timeline_stable else ";".join(diffs),
        ),
        ProjectionSurfaceParity(
            "video_overlay",
            overlay_stable,
            caption_count=len(captions),
            gap_count=0,
            candidate_count=0,
            marker_count=0,
            diff_summary="ok" if overlay_stable else "overlay_final_projection_drift",
        ),
        ProjectionSurfaceParity(
            "global_canvas",
            global_canvas_stable,
            caption_count=len(legacy_final),
            gap_count=len(legacy_gaps),
            candidate_count=candidate_count,
            marker_count=len(markers),
            diff_summary="ok" if global_canvas_stable else "global_canvas_projection_drift",
        ),
        ProjectionSurfaceParity(
            "save_export",
            save_reload_stable,
            caption_count=len(nle_final),
            gap_count=len(nle_gaps),
            candidate_count=candidate_count,
            marker_count=len(markers),
            diff_summary="ok" if save_reload_stable else "save_projection_drift",
        ),
        ProjectionSurfaceParity(
            "roughcut",
            render_export_stable,
            caption_count=len(captions),
            gap_count=len(legacy_gaps),
            candidate_count=candidate_count,
            marker_count=len([marker for marker in markers if marker.kind == "roughcut_exact_join"]),
            diff_summary="ok" if render_export_stable else "roughcut_render_projection_drift",
        ),
    )
    all_stable = all(surface.stable for surface in surfaces)
    diff_summary = "ok" if all_stable and not diffs else ";".join(diffs or [surface.diff_summary for surface in surfaces if not surface.stable])
    return ProjectionParityReport(
        projection_id="project_nle_read_only_parity_v1",
        source="legacy_project_payload",
        target_surface="timeline+video_overlay+global_canvas+save_export+roughcut",
        caption_count=len(legacy_final),
        gap_count=len(legacy_gaps),
        candidate_count=candidate_count,
        marker_count=len(markers),
        invalid_duration_count=invalid,
        non_monotonic_count=non_monotonic,
        overlap_count=overlap,
        max_active_segments=max_active,
        save_reload_stable=save_reload_stable,
        global_canvas_stable=global_canvas_stable,
        render_export_stable=render_export_stable,
        diff_summary=diff_summary,
        surface_reports=surfaces,
    )


def assert_project_nle_read_only_parity(
    project: dict[str, Any],
    *,
    project_path: str = "",
) -> ProjectionParityReport:
    report = build_project_nle_projection_parity_report(project, project_path=project_path)
    if (
        report.diff_summary != "ok"
        or report.invalid_duration_count != 0
        or report.non_monotonic_count != 0
        or report.overlap_count != 0
        or report.max_active_segments > 1
        or not report.save_reload_stable
        or not report.global_canvas_stable
        or not report.render_export_stable
    ):
        raise ValueError(f"nle_projection_parity_failed:{report.diff_summary}")
    return report


__all__ = [
    "ProjectionParityReport",
    "ProjectionSurfaceParity",
    "assert_project_nle_read_only_parity",
    "build_project_nle_projection_parity_report",
]
