#!/usr/bin/env python3
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core.project.project_io as project_io_module
from core.project.nle_persistence_guard import (
    NLE_PERSISTENCE_QUARANTINE_KEY,
    UNAPPROVED_NLE_PERSISTENCE_KEYS,
    assert_no_unapproved_nle_persistence_fields,
)
from core.project.nle_project_state import NLEProjectState, NLE_PROJECT_STATE_RUNTIME_KEY
from core.project.nle_projection_parity import build_project_nle_projection_parity_report
from core.project.project_context import build_editor_state, project_segments_to_editor
from core.project.project_io import (
    clear_project_file_cache,
    read_project_file,
    read_project_storage_payload,
    write_project_file,
)


SCHEMA = "ai_subtitle_studio.nle_adapter_cache_consistency.v1"
AUDIT_ID = "nle_adapter_cache_consistency_20260628"
BLOCKED_SCOPE = (
    "persisted_nle_project_fields_not_approved",
    "per_pixel_nle_drag_writes_not_allowed",
    "qml_or_gpu_timeline_default_surface_not_allowed",
)


def _fixture_project() -> dict[str, Any]:
    return {
        "project_name": "nle_adapter_cache_consistency",
        "mode": "single",
        "video": {"duration_sec": 6.0, "primary_fps": 30.0},
        "timeline": {
            "total_duration": 6.0,
            "timebase": {"primary_fps": 30.0},
            "tracks": [{"clips": []}],
        },
        "editor_state": build_editor_state(
            mode="single",
            media_files=[],
            segments=[
                {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "first", "speaker": "00"},
                {"id": "gap_1", "start": 1.0, "end": 2.0, "text": "", "is_gap": True},
                {"id": "caption_2", "start": 2.0, "end": 3.5, "text": "second", "speaker": "01"},
                {"id": "caption_3", "start": 3.5, "end": 5.0, "text": "third", "speaker": "02"},
            ],
            stt_preview_segments=[
                {"start": 5.0, "end": 5.5, "text": "diagnostic only", "stt_preview_source": "STT1"}
            ],
            primary_fps=30.0,
        ),
    }


def _cache_entry_count() -> int:
    cache = getattr(project_io_module, "_PROJECT_FILE_CACHE", {})
    try:
        return len(cache)
    except TypeError:
        return 0


def _cache_entry_max() -> int:
    return int(getattr(project_io_module, "_PROJECT_FILE_CACHE_MAX", 0) or 0)


def _storage_flags(storage: dict[str, Any]) -> dict[str, Any]:
    keys = set(storage.keys()) if isinstance(storage, dict) else set()
    return {
        "storage_clean": not any(key in keys for key in UNAPPROVED_NLE_PERSISTENCE_KEYS)
        and NLE_PERSISTENCE_QUARANTINE_KEY not in keys,
        "storage_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in keys,
        "storage_has_nle": "nle" in keys,
        "storage_has_nle_snapshot": "nle_snapshot" in keys,
        "storage_has_quarantine": NLE_PERSISTENCE_QUARANTINE_KEY in keys,
    }


def _row_signature(project: dict[str, Any]) -> list[tuple[str, int, int, str, str, bool]]:
    rows = project_segments_to_editor(project, include_analysis_candidates=False)
    signature: list[tuple[str, int, int, str, str, bool]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        signature.append(
            (
                str(row.get("id") or ""),
                int(round(float(row.get("start", row.get("timeline_start", 0.0)) or 0.0) * 1000.0)),
                int(round(float(row.get("end", row.get("timeline_end", 0.0)) or 0.0) * 1000.0)),
                str(row.get("text", "") or ""),
                str(row.get("speaker", row.get("spk", "")) or ""),
                bool(row.get("is_gap")),
            )
        )
    return signature


def _state_marker_persisted(project: dict[str, Any], marker: str) -> bool:
    state = project.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    if not isinstance(state, NLEProjectState):
        return False
    return str((state.metadata or {}).get("adapter_cache_cycle_marker") or "") == marker


def _cycle_check(project_path: Path, *, cycle: int, baseline_signature: list[tuple[str, int, int, str, str, bool]]) -> dict[str, Any]:
    marker = f"cycle-{cycle}"
    clear_project_file_cache(str(project_path))
    loaded = read_project_file(str(project_path))
    state = loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    if isinstance(state, NLEProjectState):
        state.metadata["adapter_cache_cycle_marker"] = marker
    cached = read_project_file(str(project_path))
    cached_state = cached.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    write_project_file(str(project_path), loaded)
    storage_after_write = read_project_storage_payload(str(project_path))
    assert_no_unapproved_nle_persistence_fields(storage_after_write, surface="nle_adapter_consistency_storage")
    clear_project_file_cache(str(project_path))
    reopened = read_project_file(str(project_path))
    reopened_state = reopened.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    cached_reopened = read_project_file(str(project_path))
    cached_reopened_state = cached_reopened.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    parity = build_project_nle_projection_parity_report(reopened, project_path=str(project_path))
    flags = _storage_flags(storage_after_write)
    return {
        "cycle": cycle,
        "runtime_state_hydrated": isinstance(state, NLEProjectState),
        "runtime_state_schema": str(getattr(state, "schema", "") or ""),
        "runtime_caption_count": len(getattr(state, "captions", []) or []),
        "same_cache_state_id_stable": isinstance(state, NLEProjectState)
        and isinstance(cached_state, NLEProjectState)
        and id(state) == id(cached_state),
        "post_clear_runtime_state_rehydrated": isinstance(reopened_state, NLEProjectState),
        "post_clear_same_cache_state_id_stable": isinstance(reopened_state, NLEProjectState)
        and isinstance(cached_reopened_state, NLEProjectState)
        and id(reopened_state) == id(cached_reopened_state),
        "runtime_marker_visible_before_clear": _state_marker_persisted(cached, marker),
        "runtime_marker_persisted_after_clear": _state_marker_persisted(reopened, marker),
        "row_signature_stable": _row_signature(reopened) == baseline_signature,
        "projection_diff_summary": parity.diff_summary,
        "invalid_duration_count": parity.invalid_duration_count,
        "non_monotonic_count": parity.non_monotonic_count,
        "overlap_count": parity.overlap_count,
        "max_active_segments": parity.max_active_segments,
        "global_canvas_stable": parity.global_canvas_stable,
        "save_reload_stable": parity.save_reload_stable,
        "cache_entry_count_after_cycle": _cache_entry_count(),
        **flags,
    }


def _lru_cache_limit_check(work_dir: Path) -> dict[str, Any]:
    clear_project_file_cache()
    cache_max = _cache_entry_max()
    paths: list[str] = []
    for index in range(cache_max + 2):
        project_path = work_dir / f"lru-{index}.aissproj"
        project = _fixture_project()
        project["project_name"] = f"nle_adapter_cache_lru_{index}"
        write_project_file(str(project_path), deepcopy(project))
        read_project_file(str(project_path))
        paths.append(str(project_path))
    return {
        "cache_owner": "core.project.project_io._PROJECT_FILE_CACHE",
        "cache_max_entries": cache_max,
        "paths_written": len(paths),
        "cache_entry_count": _cache_entry_count(),
        "cache_limit_respected": _cache_entry_count() <= cache_max,
    }


def build_nle_adapter_consistency_report(*, output_dir: Path, cycles: int = 6) -> dict[str, Any]:
    work_dir = output_dir / "_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    project_path = work_dir / "nle-adapter-consistency.aissproj"
    clear_project_file_cache()
    write_project_file(str(project_path), deepcopy(_fixture_project()))
    clear_project_file_cache(str(project_path))
    initial = read_project_file(str(project_path))
    baseline_signature = _row_signature(initial)
    initial_state = initial.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    initial_storage = read_project_storage_payload(str(project_path))
    initial_flags = _storage_flags(initial_storage)
    cycle_reports = [
        _cycle_check(project_path, cycle=index + 1, baseline_signature=baseline_signature)
        for index in range(max(1, int(cycles or 1)))
    ]
    lru = _lru_cache_limit_check(work_dir)
    all_cycles_passed = all(
        row["runtime_state_hydrated"]
        and row["same_cache_state_id_stable"]
        and row["post_clear_runtime_state_rehydrated"]
        and row["post_clear_same_cache_state_id_stable"]
        and row["runtime_marker_visible_before_clear"]
        and not row["runtime_marker_persisted_after_clear"]
        and row["row_signature_stable"]
        and row["storage_clean"]
        and row["invalid_duration_count"] == 0
        and row["non_monotonic_count"] == 0
        and row["overlap_count"] == 0
        and row["max_active_segments"] <= 1
        and row["global_canvas_stable"]
        and row["save_reload_stable"]
        for row in cycle_reports
    )
    return {
        "schema": SCHEMA,
        "audit_id": AUDIT_ID,
        "runtime_change_applied": False,
        "ready": bool(
            isinstance(initial_state, NLEProjectState)
            and initial_flags["storage_clean"]
            and all_cycles_passed
            and lru["cache_limit_respected"]
        ),
        "cycles_requested": max(1, int(cycles or 1)),
        "cycles_passed": sum(1 for row in cycle_reports if row["storage_clean"] and row["row_signature_stable"]),
        "project_path": str(project_path),
        "owners": {
            "cache": "core/project/project_io.py:_PROJECT_FILE_CACHE",
            "read_hydration": "core/project/project_io.py:read_project_file",
            "write_strip": "core/project/project_io.py:write_project_file",
            "runtime_state": "core/project/nle_project_state.py:NLEProjectState",
            "projection_parity": "core/project/nle_projection_parity.py",
        },
        "initial": {
            "runtime_state_hydrated": isinstance(initial_state, NLEProjectState),
            "runtime_state_schema": str(getattr(initial_state, "schema", "") or ""),
            "runtime_caption_count": len(getattr(initial_state, "captions", []) or []),
            "row_signature_count": len(baseline_signature),
            **initial_flags,
        },
        "checks": {
            "repeated_save_reopen": cycle_reports,
            "lru_cache_limit": lru,
        },
        "blocked_scope": list(BLOCKED_SCOPE),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _markdown_report(report: dict[str, Any]) -> str:
    lru = report["checks"]["lru_cache_limit"]
    lines = [
        "# NLE Adapter Cache Consistency Audit",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Ready: `{report['ready']}`",
        f"- Runtime change applied: `{report['runtime_change_applied']}`",
        f"- Cycles: `{report['cycles_passed']}/{report['cycles_requested']}`",
        f"- Project path: `{report['project_path']}`",
        "",
        "## Owners",
        "",
    ]
    for key, value in report["owners"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## Initial Runtime State",
            "",
            f"- Runtime state hydrated: `{report['initial']['runtime_state_hydrated']}`",
            f"- Runtime state schema: `{report['initial']['runtime_state_schema']}`",
            f"- Runtime caption count: `{report['initial']['runtime_caption_count']}`",
            f"- Storage clean: `{report['initial']['storage_clean']}`",
            "",
            "## Repeated Save / Reopen",
            "",
            "| cycle | storage_clean | cache_id_stable | marker_before_clear | marker_after_clear | rows_stable | invalid | non_monotonic | overlap | max_active |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in report["checks"]["repeated_save_reopen"]:
        lines.append(
            "| {cycle} | {storage_clean} | {cache_id} | {marker_before} | {marker_after} | {rows} | {invalid} | {non_monotonic} | {overlap} | {max_active} |".format(
                cycle=row["cycle"],
                storage_clean=row["storage_clean"],
                cache_id=row["same_cache_state_id_stable"],
                marker_before=row["runtime_marker_visible_before_clear"],
                marker_after=row["runtime_marker_persisted_after_clear"],
                rows=row["row_signature_stable"],
                invalid=row["invalid_duration_count"],
                non_monotonic=row["non_monotonic_count"],
                overlap=row["overlap_count"],
                max_active=row["max_active_segments"],
            )
        )
    lines.extend(
        [
            "",
            "## LRU Cache Limit",
            "",
            f"- Cache owner: `{lru['cache_owner']}`",
            f"- Cache max entries: `{lru['cache_max_entries']}`",
            f"- Paths written: `{lru['paths_written']}`",
            f"- Cache entry count: `{lru['cache_entry_count']}`",
            f"- Cache limit respected: `{lru['cache_limit_respected']}`",
            "",
            "## Blocked Scope",
            "",
        ]
    )
    for item in report["blocked_scope"]:
        lines.append(f"- `{item}`")
    return "\n".join(lines) + "\n"


def write_nle_adapter_consistency_report(output_dir: Path, report: dict[str, Any]) -> None:
    _write_json(output_dir / "nle_adapter_consistency_audit.json", report)
    (output_dir / "nle_adapter_consistency_audit.md").write_text(_markdown_report(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit source-app NLE adapter/cache consistency.")
    parser.add_argument("--output-dir", default="output/manual_verification/latest/nle_adapter_consistency_audit_20260628")
    parser.add_argument("--cycles", type=int, default=6)
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser()
    report = build_nle_adapter_consistency_report(output_dir=output_dir, cycles=args.cycles)
    write_nle_adapter_consistency_report(output_dir, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if bool(report.get("ready")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
