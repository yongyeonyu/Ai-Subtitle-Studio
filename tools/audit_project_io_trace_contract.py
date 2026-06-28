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

import core.runtime.trace_logger as trace_logger_module
from core.project.nle_project_state import NLE_PROJECT_STATE_RUNTIME_KEY
from core.project.project_context import build_editor_state
from core.project.project_io import (
    clear_project_file_cache,
    read_project_file,
    read_project_storage_payload,
    write_project_file,
)
from core.runtime.trace_logger import TraceLogger
from core.native_json import dumps_json_bytes

SCHEMA = "ai_subtitle_studio.project_io_trace_contract.v1"


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _fixture_project() -> dict[str, Any]:
    return {
        "project_name": "project_io_trace_contract",
        "mode": "single",
        "video": {"duration_sec": 2.0, "primary_fps": 30.0},
        "editor_state": build_editor_state(
            mode="single",
            media_files=[],
            segments=[
                {
                    "id": "subtitle_vector_0001",
                    "start": 0.0,
                    "end": 1.0,
                    "text": "first",
                    "speaker": "00",
                }
            ],
            primary_fps=30.0,
        ),
        NLE_PROJECT_STATE_RUNTIME_KEY: {"runtime_only": True},
    }


def build_project_io_trace_report(*, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    previous_logger = getattr(trace_logger_module, "_APP_TRACE_LOGGER", None)
    with tempfile.TemporaryDirectory(prefix="aiss-project-io-trace-") as tmp:
        tmp_path = Path(tmp)
        trace_root = tmp_path / "trace-root"
        project_path = tmp_path / "trace-contract.aissproj"
        logger = TraceLogger(root=trace_root, run_id="project-io-trace-contract")
        trace_logger_module._APP_TRACE_LOGGER = logger
        try:
            write_project_file(str(project_path), _fixture_project())
            storage = read_project_storage_payload(str(project_path))
            clear_project_file_cache(str(project_path))
            disk_loaded = read_project_file(str(project_path))
            cache_loaded = read_project_file(str(project_path))
            logger.flush(timeout_sec=2.0)
            events = _jsonl_rows(logger.events_path)
        finally:
            trace_logger_module._APP_TRACE_LOGGER = previous_logger
            logger.close(timeout_sec=1.0)

    project_events = [row for row in events if str(row.get("stage") or "") == "project-io"]
    save_events = [row for row in project_events if row.get("event") == "project_file_save"]
    open_events = [row for row in project_events if row.get("event") == "project_file_open"]
    disk_open_events = [row for row in open_events if row.get("cache_hit") is False]
    cache_hit_events = [row for row in open_events if row.get("cache_hit") is True]
    raw_text = json.dumps(project_events, ensure_ascii=False, sort_keys=True)
    raw_path_leak = str(project_path.parent) in raw_text
    storage_clean = (
        NLE_PROJECT_STATE_RUNTIME_KEY not in storage
        and not any(NLE_PROJECT_STATE_RUNTIME_KEY in str(value) for value in storage.values())
    )
    report = {
        "schema": SCHEMA,
        "passed": bool(
            save_events
            and disk_open_events
            and cache_hit_events
            and not raw_path_leak
            and storage_clean
            and bool(disk_loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY))
            and bool(cache_loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY))
            and all(row.get("project_path_hash") for row in project_events)
            and all("project_basename" in row for row in project_events)
            and all("project_path" not in row for row in project_events)
            and all(row.get("storage_clean_nle_runtime") is not False for row in save_events)
        ),
        "event_count": len(project_events),
        "save_event_count": len(save_events),
        "open_event_count": len(open_events),
        "disk_open_event_count": len(disk_open_events),
        "cache_hit_event_count": len(cache_hit_events),
        "raw_path_leak": raw_path_leak,
        "storage_clean": storage_clean,
        "disk_load_nle_runtime_state_attached": bool(disk_loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)),
        "cache_load_nle_runtime_state_attached": bool(cache_loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)),
        "events": project_events,
        "blocked_scope": [
            "no_raw_project_path_in_trace_event",
            "no_persisted_nle_runtime_state",
            "trace_events_are_best_effort_only",
            "no_ui_layout_or_behavior_change",
        ],
    }
    (output_dir / "project_io_trace_contract.json").write_bytes(
        dumps_json_bytes(report, sort_keys=True, append_newline=True)
    )
    (output_dir / "project_io_trace_contract.md").write_text(_markdown(report), encoding="utf-8")
    return report


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Project IO Trace Contract Audit",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Passed: `{report['passed']}`",
        f"- Project IO event count: `{report['event_count']}`",
        f"- Save/open/cache-hit counts: `{report['save_event_count']}/{report['disk_open_event_count']}/{report['cache_hit_event_count']}`",
        f"- Raw path leak: `{report['raw_path_leak']}`",
        f"- Storage clean of runtime NLE state: `{report['storage_clean']}`",
        f"- Disk/cache NLE state attached: `{report['disk_load_nle_runtime_state_attached']}/{report['cache_load_nle_runtime_state_attached']}`",
        "",
        "## Events",
        "",
        "| Event | Source | Cache hit | Basename | Has path hash | NLE attached | Storage clean |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.get("events") or []:
        lines.append(
            "| {event} | {source} | {cache_hit} | {basename} | {path_hash} | {attached} | {storage_clean} |".format(
                event=row.get("event", ""),
                source=row.get("source", ""),
                cache_hit=row.get("cache_hit", ""),
                basename=row.get("project_basename", ""),
                path_hash=bool(row.get("project_path_hash")),
                attached=row.get("nle_runtime_state_attached", ""),
                storage_clean=row.get("storage_clean_nle_runtime", ""),
            )
        )
    lines.extend(
        [
            "",
            "## Blocked Scope",
            "",
            *[f"- `{item}`" for item in report.get("blocked_scope") or []],
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit project open/save trace events for the NLE cutover lane.")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    report = build_project_io_trace_report(output_dir=Path(args.output_dir))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
