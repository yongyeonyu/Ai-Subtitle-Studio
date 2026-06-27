#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime.temp_workspace import REQUIRED_SUBDIRECTORIES, ensure_temp_workspace, workspace_usage
from core.runtime.trace_logger import TRACE_MANIFEST_SCHEMA, TRACE_RUN_RETENTION_LIMIT, TRACE_SCHEMA, TraceLogger
from tools.collect_trace_package import collect_trace_package


SCHEMA = "ai_subtitle_studio.trace_log_bundle_audit.v1"
REQUIRED_MANIFEST_FIELDS = (
    "schema",
    "app_name",
    "app_version",
    "git_commit",
    "git_dirty",
    "python_version",
    "macos_version",
    "machine",
    "pid",
    "started",
    "run_id",
    "session_id",
    "media_fingerprint",
    "mode_settings_snapshot_hash",
)
REQUIRED_EVENT_FIELDS = (
    "schema",
    "ts",
    "seq",
    "run_id",
    "session_id",
    "event",
    "stage",
    "level",
    "thread",
    "media_id",
    "project_id",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _missing_keys(payload: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    return [key for key in keys if key not in payload]


def _package_files(package_dir: Path) -> dict[str, bool]:
    return {
        "package_manifest": (package_dir / "package_manifest.json").exists(),
        "latest_jsonl": (package_dir / "latest.jsonl").exists(),
        "run_manifest": any(package_dir.glob("runs/*/manifest.json")),
        "run_events": any(package_dir.glob("runs/*/events.jsonl")),
    }


def build_trace_log_bundle_audit(*, output_dir: Path | None = None) -> dict[str, Any]:
    out_dir = Path(output_dir or ROOT / "output" / "manual_verification" / "latest" / "trace_log_bundle_audit")
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aiss-trace-audit-") as tmp:
        workspace_root = Path(tmp)
        media_path = workspace_root / "source.mp4"
        media_path.write_bytes(b"bounded media identity fixture")
        paths = ensure_temp_workspace(workspace_root)
        runs_dir = paths["Diagnostics/Trace/runs"]
        for index in range(TRACE_RUN_RETENTION_LIMIT + 4):
            run_dir = runs_dir / f"old-run-{index:02d}"
            run_dir.mkdir(parents=True)
            (run_dir / "events.jsonl").write_text("{}\n", encoding="utf-8")
            run_dir.touch()
        logger = TraceLogger(
            root=workspace_root,
            run_id="trace-audit",
            media_path=media_path,
            media_duration_sec=465.849,
            media_frame_count=27923,
            fps=60000 / 1001,
            fps_num=60000,
            fps_den=1001,
            mode_settings={"mode": "High", "trace_audit": True},
            project_id="trace-audit-project",
        )
        logger.log_event(
            "cut_boundary_candidate",
            stage="cut-boundary",
            level="DEBUG",
            frame=2677,
            time_sec=2677 / (60000 / 1001),
            fps=60000 / 1001,
            widget="timeline_canvas",
            action="audit_frame_candidate",
        )
        logger.log_event(
            "timeline_repaint_summary",
            stage="ui",
            level="INFO",
            widget="timeline_canvas",
            action="audit_repaint",
            playhead_frame=2677,
            playhead_sec=2677 / (60000 / 1001),
        )
        logger.flush(timeout_sec=2.0)
        package_manifest = collect_trace_package(
            root=workspace_root,
            run_id=logger.run_id,
            package_name="AISSTrace-audit",
        )
        logger.close(timeout_sec=2.0)

        manifest = _read_json(logger.manifest_path)
        events = _read_jsonl(logger.events_path)
        latest = _read_jsonl(logger.latest_path)
        package_dir = Path(str(package_manifest.get("package_dir") or ""))
        package_file_state = _package_files(package_dir)
        package_run_events = _read_jsonl(package_dir / "runs" / logger.run_id / "events.jsonl")
        retained_run_dirs = [path for path in runs_dir.iterdir() if path.is_dir()]

        required_dirs_created = all(paths[relative].exists() for relative in REQUIRED_SUBDIRECTORIES)
        event_missing_fields = sorted({
            missing
            for event in events
            for missing in _missing_keys(event, REQUIRED_EVENT_FIELDS)
        })
        frame_events = [event for event in events if event.get("event") == "cut_boundary_candidate"]
        frame_precision_ok = bool(frame_events) and all(
            int(event.get("fps_num") or 0) == 60000 and int(event.get("fps_den") or 0) == 1001
            for event in frame_events
        )
        media_fingerprint = manifest.get("media_fingerprint") if isinstance(manifest.get("media_fingerprint"), dict) else {}
        bounded_media_fingerprint = (
            bool(media_fingerprint.get("basename"))
            and bool(media_fingerprint.get("path_hash"))
            and "sha256" not in media_fingerprint
            and "file_hash" not in media_fingerprint
            and int(media_fingerprint.get("size") or 0) == media_path.stat().st_size
        )
        package_complete = all(package_file_state.values()) and len(package_run_events) >= 2
        manifest_missing_fields = _missing_keys(manifest, REQUIRED_MANIFEST_FIELDS)
        trace_status = logger.status()
        retention_ok = (
            len(retained_run_dirs) <= TRACE_RUN_RETENTION_LIMIT
            and (runs_dir / logger.run_id).exists()
            and not (runs_dir / "old-run-00").exists()
        )
        usage = workspace_usage(workspace_root)
        passed = (
            manifest.get("schema") == TRACE_MANIFEST_SCHEMA
            and not manifest_missing_fields
            and required_dirs_created
            and bool(events)
            and bool(latest)
            and all(event.get("schema") == TRACE_SCHEMA for event in events)
            and not event_missing_fields
            and frame_precision_ok
            and bounded_media_fingerprint
            and package_complete
            and retention_ok
            and not bool(trace_status.get("disabled"))
        )
        return {
            "schema": SCHEMA,
            "passed": passed,
            "workspace_root": str(workspace_root),
            "required_dirs_created": required_dirs_created,
            "required_subdirectories": list(REQUIRED_SUBDIRECTORIES),
            "manifest_schema": manifest.get("schema"),
            "manifest_missing_fields": manifest_missing_fields,
            "event_count": len(events),
            "latest_event_count": len(latest),
            "event_missing_fields": event_missing_fields,
            "frame_precision_ok": frame_precision_ok,
            "bounded_media_fingerprint": bounded_media_fingerprint,
            "media_fingerprint_keys": sorted(media_fingerprint.keys()),
            "package_complete": package_complete,
            "package_files": package_file_state,
            "package_event_count": len(package_run_events),
            "retention_ok": retention_ok,
            "retention_limit": TRACE_RUN_RETENTION_LIMIT,
            "retained_run_count": len(retained_run_dirs),
            "retention_removed_count": int(logger.retention_report.get("removed_count") or 0),
            "trace_disabled": bool(trace_status.get("disabled")),
            "trace_drop_counts": dict(trace_status.get("drop_counts") or {}),
            "workspace_file_count": int(usage.get("file_count") or 0),
            "workspace_total_bytes": int(usage.get("total_bytes") or 0),
        }


def write_trace_log_bundle_audit(output_dir: Path, payload: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "trace_log_bundle_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Trace Log Bundle Audit",
        "",
        f"- Passed: `{bool(payload.get('passed'))}`",
        f"- Required dirs created: `{bool(payload.get('required_dirs_created'))}`",
        f"- Manifest schema: `{payload.get('manifest_schema')}`",
        f"- Manifest missing fields: `{', '.join(payload.get('manifest_missing_fields') or []) or 'none'}`",
        f"- Event count: `{payload.get('event_count')}`",
        f"- Event missing fields: `{', '.join(payload.get('event_missing_fields') or []) or 'none'}`",
        f"- Frame precision ok: `{bool(payload.get('frame_precision_ok'))}`",
        f"- Bounded media fingerprint: `{bool(payload.get('bounded_media_fingerprint'))}`",
        f"- Package complete: `{bool(payload.get('package_complete'))}`",
        f"- Package event count: `{payload.get('package_event_count')}`",
        f"- Retention ok: `{bool(payload.get('retention_ok'))}`",
        f"- Retained run count: `{payload.get('retained_run_count')}/{payload.get('retention_limit')}`",
        f"- Retention removed count: `{payload.get('retention_removed_count')}`",
        f"- Trace disabled: `{bool(payload.get('trace_disabled'))}`",
        f"- Trace drop counts: `{payload.get('trace_drop_counts')}`",
        "",
        "## Package Files",
        "",
        "| File | Present |",
        "| --- | --- |",
    ]
    package_files = payload.get("package_files") if isinstance(payload.get("package_files"), dict) else {}
    for name, present in package_files.items():
        lines.append(f"| {name} | {bool(present)} |")
    lines.append("")
    (output_dir / "trace_log_bundle_audit.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Trace Log Bundle contract without changing app behavior.")
    parser.add_argument("--output-dir", default="output/manual_verification/latest/trace_log_bundle_audit_20260628")
    args = parser.parse_args()
    output_dir = Path(args.output_dir).expanduser()
    payload = build_trace_log_bundle_audit(output_dir=output_dir)
    write_trace_log_bundle_audit(output_dir, payload)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
