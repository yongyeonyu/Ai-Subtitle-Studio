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

import core.runtime.preview_frame_cache as preview_cache
from core.frame_time import frame_to_sec, sec_to_nearest_frame


SCHEMA = "ai_subtitle_studio.nle_preview_skimming_cache_contract.v1"
AUDIT_ID = "nle_preview_skimming_cache_contract_20260628"
BLOCKED_SCOPE = (
    "preview_cache_not_cut_boundary_evidence",
    "ui_thread_sync_decode_on_preview_miss_not_allowed",
    "qml_or_gpu_timeline_default_surface_not_allowed",
    "layout_label_menu_popup_changes_not_allowed",
)


def _video_surface_contract() -> dict[str, Any]:
    source_path = ROOT / "ui" / "editor" / "video_player_surface.py"
    text = source_path.read_text(encoding="utf-8")
    nearest = "_show_nearest_preview_frame_at(source_path, sec, width=width)"
    schedule = "_schedule_preview_frame_cache_prepare(source_path, sec, width=width)"
    nearest_index = text.find(nearest)
    schedule_index = text.find(schedule)
    return {
        "owner": "ui.editor.video_player_surface.VideoPlayerSurfaceMixin",
        "nearest_lookup_before_worker_schedule": nearest_index >= 0 and schedule_index > nearest_index,
        "cache_miss_worker_schedule_present": schedule_index >= 0,
        "preview_worker_uses_ensure_preview_frame": "result = ensure_preview_frame(" in text
        and "name=\"video-preview-frame-cache\"" in text,
        "legacy_sync_thumbnail_helper_not_called_by_unprimed_preview": "show_cached_thumbnail_at(source_path, sec" not in text,
    }


def _trace_event_contract() -> dict[str, Any]:
    source_path = ROOT / "ui" / "editor" / "video_player_surface.py"
    text = source_path.read_text(encoding="utf-8")
    return {
        "owner": "ui.editor.video_player_surface.VideoPlayerSurfaceMixin",
        "uses_trace_logger_queue": "current_app_trace_logger()" in text and "logger.log_event(event" in text,
        "best_effort_trace_failure": "except Exception:\n            return False" in text,
        "events_present": all(
            event in text
            for event in (
                "nle_preview_frame_cache_hit",
                "nle_preview_frame_cache_miss",
                "nle_preview_frame_cache_schedule",
                "nle_preview_frame_cache_ready",
            )
        ),
        "preview_only_fields_present": all(
            field in text
            for field in (
                "\"source\": \"editor_preview_skimming\"",
                "\"evidence_role\": \"user_preview_only\"",
                "\"cut_boundary_evidence\": False",
                "\"ui_thread_decode_allowed\": False",
                "cache_hit=",
                "status=",
                "\"requested_sec\"",
                "\"snapped_sec\"",
            )
        ),
        "exact_fps_fields_present": "fps_parts(fps)" in text and "\"fps_num\"" in text and "\"fps_den\"" in text,
        "preview_seek_throttle_present": "elapsed < 0.18" in text,
    }


def _cache_miss_thread_contract() -> dict[str, Any]:
    source_path = ROOT / "ui" / "editor" / "video_player_surface.py"
    text = source_path.read_text(encoding="utf-8")
    schedule_idx = text.find("def _schedule_preview_frame_cache_prepare(")
    worker_idx = text.find("def _worker() -> None:", schedule_idx)
    ensure_idx = text.find("result = ensure_preview_frame(", worker_idx)
    thread_idx = text.find("threading.Thread(", worker_idx)
    return {
        "owner": "ui.editor.video_player_surface.VideoPlayerSurfaceMixin",
        "cache_miss_uses_worker_thread": schedule_idx >= 0 and worker_idx > schedule_idx and thread_idx > worker_idx,
        "decode_runs_inside_worker": worker_idx >= 0 and ensure_idx > worker_idx,
        "worker_thread_named": 'name="video-preview-frame-cache"' in text,
        "worker_started_after_decode_closure": thread_idx > ensure_idx > worker_idx,
        "worker_active_flag_guards_reentry": "self._preview_frame_worker_active = True" in text
        and "self._preview_frame_worker_active = False" in text,
        "ready_paint_uses_signal": "self.preview_thumbnail_ready.emit(request_key, str(result.path))" in text,
    }


def build_nle_preview_skimming_cache_report(*, output_dir: Path) -> dict[str, Any]:
    work_dir = output_dir / "_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    source = work_dir / "source.mp4"
    source.write_bytes(b"media")
    fps = 60000 / 1001
    width = 320
    snapped_sec = frame_to_sec(sec_to_nearest_frame(1.0, fps), fps)
    frame_cache_dir = preview_cache.preview_frame_cache_dir(work_dir)
    cached_path = preview_cache.preview_frame_cache_path(str(source), snapped_sec, width=width, root=work_dir)
    cached_path.parent.mkdir(parents=True, exist_ok=True)
    cached_path.write_bytes(b"jpg")
    nearest = preview_cache.nearest_cached_preview_frame(
        str(source),
        1.03,
        fps=fps,
        width=width,
        tolerance_frames=3,
        root=work_dir,
    )

    original_ensure_thumbnail = preview_cache.ensure_thumbnail
    try:
        preview_cache.ensure_thumbnail = lambda *args, **kwargs: SimpleNamespace(  # type: ignore[assignment]
            status="cached",
            path=str(cached_path),
            timestamp=1.0,
            reason="",
        )
        ensure_result = preview_cache.ensure_preview_frame(str(source), 1.0, fps=fps, width=width, root=work_dir)
    finally:
        preview_cache.ensure_thumbnail = original_ensure_thumbnail  # type: ignore[assignment]

    manifest = preview_cache.read_preview_frame_manifest(cached_path)
    manifest_path = preview_cache.preview_frame_manifest_path(cached_path)
    video_surface = _video_surface_contract()
    trace_events = _trace_event_contract()
    cache_miss_thread = _cache_miss_thread_contract()
    preview_workspace_isolated = (
        "Preview" in str(frame_cache_dir)
        and "FrameThumbnails" in str(frame_cache_dir)
        and "Diagnostics/Trace" not in str(frame_cache_dir)
    )
    manifest_ok = (
        manifest.get("schema") == preview_cache.PREVIEW_FRAME_CACHE_SCHEMA
        and manifest.get("purpose") == preview_cache.PREVIEW_FRAME_CACHE_PURPOSE
        and manifest.get("source") == preview_cache.PREVIEW_FRAME_CACHE_SOURCE
        and manifest.get("cache_kind") == "nle_preview_skimming_frame"
        and manifest.get("evidence_role") == "user_preview_only"
        and manifest.get("cut_boundary_evidence") is False
        and manifest.get("ui_thread_decode_allowed") is False
    )
    source_fps_grid_ok = manifest.get("frame") == 60 and abs(float(manifest.get("fps", 0.0) or 0.0) - fps) < 1e-9
    all_passed = (
        preview_workspace_isolated
        and str(nearest) == str(cached_path)
        and getattr(ensure_result, "status", "") in ("cached", "created")
        and manifest_ok
        and source_fps_grid_ok
        and all(bool(value) for key, value in video_surface.items() if key != "owner")
        and all(bool(value) for key, value in trace_events.items() if key != "owner")
        and all(bool(value) for key, value in cache_miss_thread.items() if key != "owner")
    )
    return {
        "schema": SCHEMA,
        "audit_id": AUDIT_ID,
        "ready": all_passed,
        "ui_runtime_change_applied": False,
        "preview_cache_contract_applied": True,
        "preview_workspace_isolated": preview_workspace_isolated,
        "preview_cache_dir": str(frame_cache_dir),
        "nearest_cached_preview_frame_hit": str(nearest) == str(cached_path),
        "manifest_path": str(manifest_path),
        "manifest_schema": manifest.get("schema"),
        "manifest_purpose": manifest.get("purpose"),
        "manifest_evidence_role": manifest.get("evidence_role"),
        "manifest_cut_boundary_evidence": manifest.get("cut_boundary_evidence"),
        "manifest_ui_thread_decode_allowed": manifest.get("ui_thread_decode_allowed"),
        "source_fps_grid_ok": source_fps_grid_ok,
        "manifest_frame": manifest.get("frame"),
        "manifest_fps": manifest.get("fps"),
        "video_surface_contract": video_surface,
        "trace_event_contract": trace_events,
        "cache_miss_thread_contract": cache_miss_thread,
        "blocked_scope": list(BLOCKED_SCOPE),
    }


def write_nle_preview_skimming_cache_report(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "nle_preview_skimming_cache_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# NLE Preview Skimming Cache Contract Audit",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Ready: `{report['ready']}`",
        f"- UI runtime change applied: `{report['ui_runtime_change_applied']}`",
        f"- Preview cache contract applied: `{report['preview_cache_contract_applied']}`",
        f"- Preview workspace isolated: `{report['preview_workspace_isolated']}`",
        f"- Nearest cached preview frame hit: `{report['nearest_cached_preview_frame_hit']}`",
        f"- Manifest purpose: `{report['manifest_purpose']}`",
        f"- Manifest evidence role: `{report['manifest_evidence_role']}`",
        f"- Manifest cut-boundary evidence: `{report['manifest_cut_boundary_evidence']}`",
        f"- Source-fps grid ok: `{report['source_fps_grid_ok']}`",
        "",
        "## Video Surface Contract",
        "",
        "| owner | nearest_before_worker | worker_schedule | worker_ensure_preview | no_legacy_sync_cached_thumb |",
        "| --- | --- | --- | --- | --- |",
        "| {owner} | {nearest} | {schedule} | {worker} | {legacy} |".format(
            owner=report["video_surface_contract"]["owner"],
            nearest=report["video_surface_contract"]["nearest_lookup_before_worker_schedule"],
            schedule=report["video_surface_contract"]["cache_miss_worker_schedule_present"],
            worker=report["video_surface_contract"]["preview_worker_uses_ensure_preview_frame"],
            legacy=report["video_surface_contract"]["legacy_sync_thumbnail_helper_not_called_by_unprimed_preview"],
        ),
        "",
        "## Trace Event Contract",
        "",
        "| owner | trace_queue | best_effort | events | preview_only_fields | exact_fps | throttle |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        "| {owner} | {trace_queue} | {best_effort} | {events} | {preview_fields} | {exact_fps} | {throttle} |".format(
            owner=report["trace_event_contract"]["owner"],
            trace_queue=report["trace_event_contract"]["uses_trace_logger_queue"],
            best_effort=report["trace_event_contract"]["best_effort_trace_failure"],
            events=report["trace_event_contract"]["events_present"],
            preview_fields=report["trace_event_contract"]["preview_only_fields_present"],
            exact_fps=report["trace_event_contract"]["exact_fps_fields_present"],
            throttle=report["trace_event_contract"]["preview_seek_throttle_present"],
        ),
        "",
        "## Cache Miss Thread Contract",
        "",
        "| owner | worker_thread | decode_in_worker | named_thread | start_after_closure | reentry_guard | ready_signal |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        "| {owner} | {worker} | {decode} | {named} | {start_after} | {guard} | {signal} |".format(
            owner=report["cache_miss_thread_contract"]["owner"],
            worker=report["cache_miss_thread_contract"]["cache_miss_uses_worker_thread"],
            decode=report["cache_miss_thread_contract"]["decode_runs_inside_worker"],
            named=report["cache_miss_thread_contract"]["worker_thread_named"],
            start_after=report["cache_miss_thread_contract"]["worker_started_after_decode_closure"],
            guard=report["cache_miss_thread_contract"]["worker_active_flag_guards_reentry"],
            signal=report["cache_miss_thread_contract"]["ready_paint_uses_signal"],
        ),
        "",
        "## Blocked Scope",
        "",
    ]
    lines.extend(f"- `{item}`" for item in report["blocked_scope"])
    (output_dir / "nle_preview_skimming_cache_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit NLE preview/skimming frame-cache contract.")
    parser.add_argument(
        "--output-dir",
        default="output/manual_verification/latest/nle_preview_skimming_cache_audit_20260628",
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    report = build_nle_preview_skimming_cache_report(output_dir=output_dir)
    write_nle_preview_skimming_cache_report(output_dir, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report.get("ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
