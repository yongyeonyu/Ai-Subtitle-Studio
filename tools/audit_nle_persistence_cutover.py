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

from core.project.nle_persistence_guard import (
    NLE_FINAL_CUTOVER_APPROVAL_SCHEMA,
    NLE_LEGACY_DISK_SHAPE_REPLACEMENT_APPROVAL_SCHEMA,
    NLE_LEGACY_CANONICAL_LOAD_OWNER,
    NLE_PERSISTENCE_QUARANTINE_KEY,
    NLE_RUNTIME_STATE_PERSISTENCE_APPROVAL_SCHEMA,
    NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
    NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
    NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER,
    NLE_TOP_LEVEL_PERSISTENCE_APPROVAL_SCHEMA,
    UNAPPROVED_NLE_PERSISTENCE_KEYS,
    assert_no_unapproved_nle_persistence_fields,
    strip_unapproved_nle_persistence_fields,
)
from tools.audit_direct_srt_precedence_contract import build_direct_srt_precedence_report
from core.project.nle_dual_write import (
    apply_candidate_confirm_dual_write_pilot,
    apply_caption_delete_dual_write_pilot,
    apply_caption_merge_dual_write_pilot,
    apply_caption_move_dual_write_pilot,
    apply_caption_range_replace_dual_write_pilot,
    apply_caption_resize_dual_write_pilot,
    apply_caption_split_dual_write_pilot,
    apply_caption_text_edit_dual_write_pilot,
    apply_gap_delete_dual_write_pilot,
    apply_gap_generate_dual_write_pilot,
    apply_marker_edit_dual_write_pilot,
)
from core.project.nle_project_state import NLEProjectState, NLE_PROJECT_STATE_RUNTIME_KEY
from core.project.nle_render_export_parity import assert_project_nle_render_export_parity
from core.project.nle_snapshot import NLE_SNAPSHOT_READBACK_PARITY_KEY, NLE_TOP_LEVEL_SHADOW_SCHEMA
from core.project import project_io
from core.project.project_context import (
    build_editor_state,
    project_cut_boundary_provisional_segments,
    project_segments_to_editor,
)
from core.project.project_io import (
    clear_project_file_cache,
    read_project_file,
    read_project_storage_payload,
    write_project_file,
)
from core.runtime.config import APP_VERSION


SCHEMA = "ai_subtitle_studio.nle_persistence_cutover_readiness.v1"
CUTOVER_GAP_COVERAGE_BLOCKER = "top_level_nle_projection_gap_coverage_missing"
CUTOVER_BLOCKERS = (
    "top_level_nle_shadow_not_canonical_load_owner",
    "runtime_nle_project_state_must_remain_runtime_only",
    "legacy_disk_shape_required_for_full_cutover",
)
CANONICAL_LOAD_OWNER_GATE_ORDER = (
    "top_level_shadow_ready",
    "compatibility_projection_ready",
    "legacy_default_load_still_canonical",
    "operation_roundtrip_ready",
    "render_export_parity_ready",
    "roughcut_sidecar_ready",
    "rollback_boundary_defined",
    "canonical_load_owner_change_allowed",
    "nle_snapshot_canonical_load_source_allowed",
    "runtime_project_state_persistence_allowed",
    "legacy_disk_shape_replacement_allowed",
    "final_cutover_ready",
)


def _legacy_project() -> dict[str, Any]:
    return {
        "project_name": "nle_persistence_cutover_audit",
        "mode": "single",
        "video": {"duration_sec": 4.0, "primary_fps": 30.0},
        "timeline": {
            "total_duration": 4.0,
            "timebase": {"primary_fps": 30.0},
            "tracks": [{"clips": []}],
        },
        "editor_state": build_editor_state(
            mode="single",
            media_files=[],
            segments=[
                {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "first", "speaker": "00"},
                {"id": "gap_1", "start": 1.0, "end": 2.0, "text": "", "is_gap": True},
                {"id": "caption_2", "start": 2.0, "end": 3.0, "text": "second", "speaker": "01"},
            ],
            primary_fps=30.0,
        ),
    }


def _three_caption_project() -> dict[str, Any]:
    return {
        "project_name": "nle_persistence_operation_roundtrip",
        "mode": "single",
        "video": {"duration_sec": 6.0, "primary_fps": 30.0},
        "editor_state": build_editor_state(
            mode="single",
            media_files=[],
            segments=[
                {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "first", "speaker": "00"},
                {"id": "caption_2", "start": 1.0, "end": 2.0, "text": "second", "speaker": "01"},
                {"id": "caption_3", "start": 2.0, "end": 3.0, "text": "third", "speaker": "02"},
            ],
            primary_fps=30.0,
        ),
    }


def _render_export_project(root: Path) -> dict[str, Any]:
    media_path = root / "source.mov"
    media_path.write_bytes(b"media")
    segment_rows = [
        {
            "segment_id": "chapter_0001",
            "source_path": str(media_path),
            "source_start": 0.0,
            "source_end": 2.0,
            "output_start": 0.0,
            "output_end": 2.0,
            "chapter_id": "chapter_0001",
        },
        {
            "segment_id": "chapter_0002",
            "source_path": str(media_path),
            "source_start": 3.0,
            "source_end": 6.0,
            "output_start": 2.0,
            "output_end": 5.0,
            "chapter_id": "chapter_0002",
        },
    ]
    manifest_rows = [
        {
            "segment_id": row["segment_id"],
            "source_path": row["source_path"],
            "source_start": row["source_start"],
            "source_end": row["source_end"],
            "output_start": row["output_start"],
            "output_end": row["output_end"],
        }
        for row in segment_rows
    ]
    stitched = [
        {
            "time": 2.0,
            "timeline_sec": 2.0,
            "source": "roughcut_concat_join",
            "segment_before_id": "chapter_0001",
            "segment_after_id": "chapter_0002",
        }
    ]
    return {
        "project_name": "nle_persistence_render_export_parity",
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
                            "source_path": str(media_path),
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
                {
                    "id": "caption_1",
                    "start": 0.0,
                    "end": 1.0,
                    "text": "first",
                    "speaker": "00",
                    "stt_candidates": [
                        {"source": "STT1", "start": 0.0, "end": 1.0, "text": "first raw", "score": 0.8}
                    ],
                },
                {"id": "gap_1", "start": 1.0, "end": 2.0, "text": "", "is_gap": True},
                {
                    "id": "caption_2",
                    "start": 2.0,
                    "end": 3.0,
                    "text": "second",
                    "speaker": "01",
                    "stt_candidates": [
                        {"source": "STT2", "start": 2.0, "end": 3.0, "text": "second raw", "score": 0.7}
                    ],
                },
            ],
            stt_preview_segments=[
                {"start": 4.0, "end": 5.0, "text": "diagnostic only", "stt_preview_source": "STT1"}
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
                        "edl": {
                            "duration": 5.0,
                            "segments": segment_rows,
                            "stitched_cut_boundaries": stitched,
                        },
                        "render_plan": {
                            "output_path": str(root / "roughcut.mov"),
                            "render_mode": "sync_safe",
                            "segment_manifest": manifest_rows,
                            "stitched_cut_boundaries": stitched,
                        },
                    },
                }
            ],
        },
    }


def _storage_has_unapproved_nle_fields(storage: dict[str, Any]) -> bool:
    if not isinstance(storage, dict):
        return True
    return any(key in storage for key in UNAPPROVED_NLE_PERSISTENCE_KEYS) or NLE_PERSISTENCE_QUARANTINE_KEY in storage


def _runtime_roundtrip_check(work_dir: Path) -> dict[str, Any]:
    project_path = work_dir / "nle-persistence-cutover-audit.aissproj"
    project = _legacy_project()
    write_project_file(str(project_path), project)
    clear_project_file_cache(str(project_path))

    loaded = read_project_file(str(project_path))
    state = loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    storage = read_project_storage_payload(str(project_path))
    assert_no_unapproved_nle_persistence_fields(storage, surface="audit_storage")
    storage_clean = not _storage_has_unapproved_nle_fields(storage)

    return {
        "project_path": str(project_path),
        "loaded_runtime_state": isinstance(state, NLEProjectState),
        "runtime_state_schema": str(getattr(state, "schema", "") or ""),
        "runtime_caption_count": len(getattr(state, "captions", []) or []),
        "storage_clean": storage_clean,
        "storage_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in storage,
        "storage_has_nle": "nle" in storage,
        "storage_has_nle_snapshot": "nle_snapshot" in storage,
        "storage_has_quarantine": NLE_PERSISTENCE_QUARANTINE_KEY in storage,
        "storage_schema": str(storage.get("storage_schema", "") or ""),
    }


def _render_export_parity_check(work_dir: Path) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    project_path = work_dir / "nle-render-export-parity.aissproj"
    project = _render_export_project(work_dir)
    write_project_file(str(project_path), project)
    storage = read_project_storage_payload(str(project_path))
    assert_no_unapproved_nle_persistence_fields(storage, surface="render_export_parity_storage")
    clear_project_file_cache(str(project_path))
    loaded = read_project_file(str(project_path))
    report = assert_project_nle_render_export_parity(loaded, project_path=str(project_path))
    surfaces = [surface.to_dict() for surface in report.surface_reports]
    return {
        "project_path": str(project_path),
        "stable": report.diff_summary == "ok" and all(bool(surface.get("stable")) for surface in surfaces),
        "storage_clean": not _storage_has_unapproved_nle_fields(storage),
        "projection_hash": report.final_projection_hash,
        "caption_count": report.caption_count,
        "gap_count": report.gap_count,
        "candidate_count": report.candidate_count,
        "render_segment_count": report.render_segment_count,
        "manifest_count": report.manifest_count,
        "stitched_boundary_count": report.stitched_boundary_count,
        "invalid_duration_count": report.invalid_duration_count,
        "non_monotonic_count": report.non_monotonic_count,
        "overlap_count": report.overlap_count,
        "max_active_segments": report.max_active_segments,
        "surface_reports": surfaces,
    }


def _future_payload_quarantine_check() -> dict[str, Any]:
    project = _legacy_project()
    project["nle"] = {"future_doc": {"tracks": []}}
    project["nle_snapshot"] = {"schema": "future_snapshot"}
    project[NLE_PROJECT_STATE_RUNTIME_KEY] = {"schema": "persisted_future_state"}
    report = strip_unapproved_nle_persistence_fields(project, source="audit_future_payload")
    assert_no_unapproved_nle_persistence_fields(project, surface="audit_future_payload")
    return {
        "quarantine_recorded": isinstance(report, dict),
        "stripped_keys": list(report.get("stripped_keys") or []) if isinstance(report, dict) else [],
        "remaining_unapproved_fields": [
            key for key in UNAPPROVED_NLE_PERSISTENCE_KEYS if key in project
        ],
        "quarantine_key_present": NLE_PERSISTENCE_QUARANTINE_KEY in project,
    }


def _row_signature(
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    include_id: bool,
) -> list[dict[str, Any]]:
    signature: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = {
            "text": str(row.get("text") or ""),
            "is_gap": bool(row.get("is_gap")),
            "start_frame": int(row.get("start_frame", row.get("timeline_start_frame", 0)) or 0),
            "end_frame": int(row.get("end_frame", row.get("timeline_end_frame", 0)) or 0),
        }
        if include_id:
            item["id"] = str(row.get("id") or "")
        signature.append(item)
    return signature


def _editor_rows_from_top_level_nle_payload(nle_payload: dict[str, Any]) -> list[dict[str, Any]]:
    sequences = nle_payload.get("sequences") if isinstance(nle_payload.get("sequences"), list) else []
    sequence = sequences[0] if sequences and isinstance(sequences[0], dict) else {}
    try:
        fps = float(sequence.get("fps") or 30.0)
    except (TypeError, ValueError):
        fps = 30.0
    captions = sequence.get("captions") if isinstance(sequence.get("captions"), list) else []
    rows: list[dict[str, Any]] = []
    for index, caption in enumerate(captions):
        if not isinstance(caption, dict):
            continue
        try:
            start = float(caption.get("sequence_start") or 0.0)
            end = max(start, float(caption.get("sequence_end") or start))
        except (TypeError, ValueError):
            start = 0.0
            end = 0.0
        rows.append(
            {
                "id": str(caption.get("caption_id") or f"caption_{index + 1:04d}"),
                "start": round(start, 6),
                "end": round(end, 6),
                "start_frame": int(round(start * fps)),
                "end_frame": int(round(end * fps)),
                "text": str(caption.get("text") or ""),
                "speaker": str(caption.get("speaker") or ""),
                "is_gap": False,
            }
        )
    gaps = sequence.get("gaps") if isinstance(sequence.get("gaps"), list) else []
    for index, gap in enumerate(gaps):
        if not isinstance(gap, dict):
            continue
        try:
            start = float(gap.get("sequence_start") or 0.0)
            end = max(start, float(gap.get("sequence_end") or start))
        except (TypeError, ValueError):
            start = 0.0
            end = 0.0
        rows.append(
            {
                "id": str(gap.get("gap_id") or f"gap_{index + 1:04d}"),
                "start": round(start, 6),
                "end": round(end, 6),
                "start_frame": int(round(start * fps)),
                "end_frame": int(round(end * fps)),
                "text": "",
                "speaker": "",
                "is_gap": True,
            }
        )
    rows.sort(key=lambda row: (int(row.get("start_frame") or 0), int(row.get("end_frame") or 0), bool(row.get("is_gap"))))
    return rows


def _first_caption_text(rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> str:
    for row in rows:
        if isinstance(row, dict) and not row.get("is_gap"):
            return str(row.get("text") or "")
    return ""


def _top_level_nle_compatibility_projection_check(work_dir: Path) -> dict[str, Any]:
    project_path = work_dir / "top-level-nle-compatibility-projection.aissproj"
    project = _legacy_project()
    project["nle_persistence"] = {
        "persist_snapshot": True,
        "persist_top_level_nle": True,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
    }
    expected_default_rows = _row_signature(
        project_segments_to_editor(project, include_analysis_candidates=False),
        include_id=False,
    )
    write_project_file(str(project_path), project)
    storage = read_project_storage_payload(str(project_path))
    nle_payload = storage.get("nle") if isinstance(storage.get("nle"), dict) else {}
    sequences = nle_payload.get("sequences") if isinstance(nle_payload.get("sequences"), list) else []
    sequence = sequences[0] if sequences and isinstance(sequences[0], dict) else {}
    captions = sequence.get("captions") if isinstance(sequence.get("captions"), list) else []
    shadow_override_caption_text = "nle shadow first"
    if captions and isinstance(captions[0], dict):
        captions[0]["text"] = shadow_override_caption_text
    project_path.write_text(json.dumps(storage, ensure_ascii=False), encoding="utf-8")
    clear_project_file_cache(str(project_path))

    storage_with_shadow_override = read_project_storage_payload(str(project_path))
    shadow_payload = (
        storage_with_shadow_override.get("nle")
        if isinstance(storage_with_shadow_override.get("nle"), dict)
        else {}
    )
    assert_no_unapproved_nle_persistence_fields(
        storage_with_shadow_override,
        surface="top_level_nle_compatibility_projection_storage",
    )
    explicit_rows = _editor_rows_from_top_level_nle_payload(shadow_payload)
    explicit_signature = _row_signature(explicit_rows, include_id=False)
    loaded = read_project_file(str(project_path))
    default_rows = project_segments_to_editor(loaded, include_analysis_candidates=False)
    default_signature = _row_signature(default_rows, include_id=False)
    explicit_caption_signature = _row_signature(
        [row for row in explicit_rows if isinstance(row, dict) and not row.get("is_gap")],
        include_id=False,
    )
    default_caption_signature = _row_signature(
        [row for row in default_rows if isinstance(row, dict) and not row.get("is_gap")],
        include_id=False,
    )
    explicit_gap_count = sum(1 for row in explicit_rows if isinstance(row, dict) and row.get("is_gap"))
    default_gap_count = sum(1 for row in default_rows if isinstance(row, dict) and row.get("is_gap"))
    loaded_state = loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    write_project_file(str(project_path), loaded)
    storage_after = read_project_storage_payload(str(project_path))
    rebuilt_nle = storage_after.get("nle") if isinstance(storage_after.get("nle"), dict) else {}
    rebuilt_rows = _editor_rows_from_top_level_nle_payload(rebuilt_nle)
    rebuilt_signature = _row_signature(rebuilt_rows, include_id=False)
    gap_coverage_ready = explicit_gap_count == default_gap_count and explicit_gap_count > 0
    explicit_first_caption_text = _first_caption_text(explicit_rows)
    default_first_caption_text = _first_caption_text(default_rows)
    resave_first_caption_text = _first_caption_text(rebuilt_rows)

    return {
        "status": "gap_projection_coverage_ready_blocked",
        "not_runtime_change": True,
        "canonical_load_owner_unchanged": True,
        "current_canonical_load_owner": "legacy_editor_state",
        "canonical_load_owner_change_allowed": False,
        "disk_format_cutover_allowed": False,
        "explicit_projection_source": "top_level_nle_shadow_metadata",
        "default_load_source": "legacy_editor_state",
        "explicit_projection_uses_top_level_nle": bool(explicit_rows),
        "default_load_uses_legacy_rows": default_signature == expected_default_rows,
        "explicit_projection_differs_from_default": explicit_signature != default_signature,
        "explicit_projection_row_count": len(explicit_signature),
        "explicit_projection_caption_count": len(explicit_caption_signature),
        "explicit_projection_gap_count": explicit_gap_count,
        "default_row_count": len(default_signature),
        "default_caption_count": len(default_caption_signature),
        "default_gap_count": default_gap_count,
        "shadow_override_caption_text": shadow_override_caption_text,
        "explicit_first_caption_text": explicit_first_caption_text,
        "default_first_caption_text": default_first_caption_text,
        "resave_first_caption_text": resave_first_caption_text,
        "shadow_override_visible_in_explicit_projection": explicit_first_caption_text == shadow_override_caption_text,
        "shadow_override_absent_from_default_load": default_first_caption_text != shadow_override_caption_text,
        "default_load_preserved_legacy_text": default_first_caption_text == "first",
        "resave_discarded_shadow_override": resave_first_caption_text != shadow_override_caption_text,
        "resave_preserved_legacy_text": resave_first_caption_text == "first",
        "gap_coverage_ready": gap_coverage_ready,
        "default_legacy_rows_stable": default_signature == expected_default_rows,
        "runtime_state_hydrated_from_legacy": isinstance(loaded_state, NLEProjectState),
        "shadow_role": str(shadow_payload.get("role") or ""),
        "shadow_schema": str(shadow_payload.get("schema") or ""),
        "shadow_canonical_load_owner": str(shadow_payload.get("canonical_load_owner") or ""),
        "shadow_runtime_project_state_persisted": bool(shadow_payload.get("runtime_project_state_persisted")),
        "storage_has_nle": "nle" in storage_with_shadow_override,
        "storage_has_nle_snapshot": "nle_snapshot" in storage_with_shadow_override,
        "runtime_report_persisted_after_resave": NLE_SNAPSHOT_READBACK_PARITY_KEY in storage_after,
        "runtime_state_persisted_after_resave": NLE_PROJECT_STATE_RUNTIME_KEY in storage_after,
        "quarantine_persisted_after_resave": NLE_PERSISTENCE_QUARANTINE_KEY in storage_after,
        "resave_rebuilt_shadow_from_legacy": rebuilt_signature == default_signature,
        "resave_rebuilt_shadow_captions_from_legacy": _row_signature(
            [row for row in rebuilt_rows if not row.get("is_gap")],
            include_id=False,
        )
        == default_caption_signature,
        "resave_rebuilt_shadow_rows_from_legacy": rebuilt_signature == default_signature,
        "full_cutover_blockers": [
            "default_project_load_still_uses_legacy_editor_state",
            "owner_approval_and_rollback_boundary_required_for_any_load_owner_change",
        ],
    }


def _top_level_nle_canonical_load_opt_in_check(work_dir: Path) -> dict[str, Any]:
    project_path = work_dir / "top-level-nle-canonical-load-opt-in.aissproj"
    project = _legacy_project()
    project["nle_persistence"] = {
        "persist_snapshot": True,
        "persist_top_level_nle": True,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
        "canonical_load_owner": NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER,
        "canonical_load_owner_change_allowed": True,
    }
    expected_legacy_rows = _row_signature(
        project_segments_to_editor(project, include_analysis_candidates=False),
        include_id=False,
    )
    expected_canonical_text = "nle canonical first"
    write_project_file(str(project_path), project)
    storage = read_project_storage_payload(str(project_path))
    storage["nle"]["sequences"][0]["captions"][0]["text"] = expected_canonical_text
    storage["nle_snapshot"]["sequences"][0]["captions"][0]["text"] = expected_canonical_text
    project_path.write_bytes(project_io._pack_project_payload(storage))

    clear_project_file_cache(str(project_path))
    loaded = read_project_file(str(project_path))
    loaded_rows = project_segments_to_editor(loaded, include_analysis_candidates=False)
    loaded_signature = _row_signature(loaded_rows, include_id=False)
    loaded_state = loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    runtime_rows = loaded_state.editor_rows() if isinstance(loaded_state, NLEProjectState) else []
    runtime_signature = _row_signature(runtime_rows, include_id=False)
    write_project_file(str(project_path), loaded)
    storage_after = read_project_storage_payload(str(project_path))
    clear_project_file_cache(str(project_path))
    reloaded = read_project_file(str(project_path))
    reloaded_rows = project_segments_to_editor(reloaded, include_analysis_candidates=False)
    reloaded_signature = _row_signature(reloaded_rows, include_id=False)
    storage_after_nle = storage_after.get("nle") if isinstance(storage_after.get("nle"), dict) else {}
    storage_after_snapshot = (
        storage_after.get("nle_snapshot") if isinstance(storage_after.get("nle_snapshot"), dict) else {}
    )
    storage_after_nle_rows = _editor_rows_from_top_level_nle_payload(storage_after_nle)
    storage_after_snapshot_rows = _editor_rows_from_top_level_nle_payload(storage_after_snapshot)
    storage_after_nle_signature = _row_signature(storage_after_nle_rows, include_id=False)
    storage_after_snapshot_signature = _row_signature(storage_after_snapshot_rows, include_id=False)
    editor_state_after_rows = project_segments_to_editor(
        {"editor_state": storage_after.get("editor_state") or {}, "video": storage_after.get("video") or {}},
        include_analysis_candidates=False,
    )
    editor_state_after_signature = _row_signature(editor_state_after_rows, include_id=False)

    canonical_text_loaded = _first_caption_text(loaded_rows)
    legacy_text_after = _first_caption_text(editor_state_after_rows)
    storage_nle_first = _first_caption_text(storage_after_nle_rows)
    storage_snapshot_first = _first_caption_text(storage_after_snapshot_rows)
    ready = (
        str(storage.get("nle", {}).get("role") or "") == "canonical_load_owner"
        and str(storage.get("nle", {}).get("canonical_load_owner") or "") == NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER
        and canonical_text_loaded == expected_canonical_text
        and _first_caption_text(runtime_rows) == expected_canonical_text
        and _first_caption_text(reloaded_rows) == expected_canonical_text
        and storage_nle_first == expected_canonical_text
        and storage_snapshot_first == expected_canonical_text
        and loaded_signature == runtime_signature == reloaded_signature == storage_after_nle_signature
        and storage_after_nle_signature == storage_after_snapshot_signature
        and editor_state_after_signature == expected_legacy_rows
        and legacy_text_after == "first"
        and NLE_PROJECT_STATE_RUNTIME_KEY not in storage_after
        and NLE_SNAPSHOT_READBACK_PARITY_KEY not in storage_after
        and NLE_PERSISTENCE_QUARANTINE_KEY not in storage_after
    )
    return {
        "ready": ready,
        "status": "ready" if ready else "blocked",
        "not_runtime_state_persistence": True,
        "not_legacy_disk_shape_replacement": True,
        "not_final_cutover": True,
        "canonical_load_owner_change_allowed": True,
        "canonical_load_owner": str(storage_after_nle.get("canonical_load_owner") or ""),
        "role": str(storage_after_nle.get("role") or ""),
        "expected_canonical_text": expected_canonical_text,
        "loaded_first_caption_text": canonical_text_loaded,
        "runtime_first_caption_text": _first_caption_text(runtime_rows),
        "reloaded_first_caption_text": _first_caption_text(reloaded_rows),
        "storage_nle_first_caption_text": storage_nle_first,
        "storage_snapshot_first_caption_text": storage_snapshot_first,
        "legacy_editor_state_first_caption_text_after_resave": legacy_text_after,
        "loaded_signature_matches_runtime": loaded_signature == runtime_signature,
        "loaded_signature_matches_reloaded": loaded_signature == reloaded_signature,
        "storage_nle_matches_snapshot": storage_after_nle_signature == storage_after_snapshot_signature,
        "legacy_editor_state_preserved_for_rollback": editor_state_after_signature == expected_legacy_rows,
        "storage_after_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in storage_after,
        "storage_after_has_readback_report": NLE_SNAPSHOT_READBACK_PARITY_KEY in storage_after,
        "storage_after_has_quarantine": NLE_PERSISTENCE_QUARANTINE_KEY in storage_after,
        "blocked_gates_remaining": [
            "legacy_disk_shape_replacement_allowed",
            "final_cutover_ready",
        ],
    }


def _nle_snapshot_canonical_load_source_check(work_dir: Path) -> dict[str, Any]:
    project_path = work_dir / "nle-snapshot-canonical-load-source.aissproj"
    project = _legacy_project()
    project["nle_persistence"] = {
        "persist_snapshot": True,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
        "canonical_load_owner": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
        "canonical_load_owner_change_allowed": True,
        "nle_snapshot_canonical_load_source_allowed": True,
        "legacy_editor_state_remains_canonical": False,
        "legacy_editor_state_preserved_for_rollback": True,
    }
    expected_legacy_rows = _row_signature(
        project_segments_to_editor(project, include_analysis_candidates=False),
        include_id=False,
    )
    expected_canonical_text = "snapshot canonical first"
    write_project_file(str(project_path), project)
    storage = read_project_storage_payload(str(project_path))
    storage["nle_snapshot"]["sequences"][0]["captions"][0]["text"] = expected_canonical_text
    project_path.write_bytes(project_io._pack_project_payload(storage))
    clear_project_file_cache(str(project_path))

    loaded = read_project_file(str(project_path))
    loaded_rows = project_segments_to_editor(loaded, include_analysis_candidates=False)
    runtime_state = loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    runtime_rows = (
        runtime_state.editor_rows()
        if isinstance(runtime_state, NLEProjectState) and callable(getattr(runtime_state, "editor_rows", None))
        else []
    )
    write_project_file(str(project_path), loaded)
    storage_after = read_project_storage_payload(str(project_path))
    clear_project_file_cache(str(project_path))
    reloaded = read_project_file(str(project_path))
    reloaded_rows = project_segments_to_editor(reloaded, include_analysis_candidates=False)

    snapshot_after = storage_after.get("nle_snapshot") if isinstance(storage_after.get("nle_snapshot"), dict) else {}
    snapshot_after_rows = _editor_rows_from_top_level_nle_payload(snapshot_after)
    editor_state_after_rows = project_segments_to_editor(
        {"editor_state": storage_after.get("editor_state") or {}, "video": storage_after.get("video") or {}},
        include_analysis_candidates=False,
    )
    loaded_signature = _row_signature(loaded_rows, include_id=False)
    runtime_signature = _row_signature(runtime_rows, include_id=False)
    reloaded_signature = _row_signature(reloaded_rows, include_id=False)
    snapshot_signature = _row_signature(snapshot_after_rows, include_id=False)
    editor_state_after_signature = _row_signature(editor_state_after_rows, include_id=False)
    snapshot_persistence = snapshot_after.get("persistence") if isinstance(snapshot_after.get("persistence"), dict) else {}
    ready = (
        str(snapshot_persistence.get("canonical_load_owner") or "") == NLE_SNAPSHOT_CANONICAL_LOAD_OWNER
        and bool(snapshot_persistence.get("canonical_load_owner_change_allowed"))
        and bool(snapshot_persistence.get("nle_snapshot_canonical_load_source_allowed"))
        and not bool(snapshot_persistence.get("legacy_editor_state_remains_canonical"))
        and bool(snapshot_persistence.get("legacy_editor_state_preserved_for_rollback"))
        and _first_caption_text(loaded_rows) == expected_canonical_text
        and _first_caption_text(runtime_rows) == expected_canonical_text
        and _first_caption_text(reloaded_rows) == expected_canonical_text
        and _first_caption_text(snapshot_after_rows) == expected_canonical_text
        and loaded_signature == runtime_signature == reloaded_signature == snapshot_signature
        and editor_state_after_signature == expected_legacy_rows
        and _first_caption_text(editor_state_after_rows) == "first"
        and "nle" not in storage_after
        and NLE_PROJECT_STATE_RUNTIME_KEY not in storage_after
        and NLE_SNAPSHOT_READBACK_PARITY_KEY not in storage_after
        and NLE_PERSISTENCE_QUARANTINE_KEY not in storage_after
    )
    return {
        "ready": ready,
        "status": "ready" if ready else "blocked",
        "explicit_opt_in": True,
        "canonical_load_owner": str(snapshot_persistence.get("canonical_load_owner") or ""),
        "canonical_load_owner_change_allowed": bool(snapshot_persistence.get("canonical_load_owner_change_allowed")),
        "nle_snapshot_canonical_load_source_allowed": bool(
            snapshot_persistence.get("nle_snapshot_canonical_load_source_allowed")
        ),
        "legacy_editor_state_preserved_for_rollback": editor_state_after_signature == expected_legacy_rows,
        "loaded_first_caption_text": _first_caption_text(loaded_rows),
        "runtime_first_caption_text": _first_caption_text(runtime_rows),
        "reloaded_first_caption_text": _first_caption_text(reloaded_rows),
        "storage_snapshot_first_caption_text": _first_caption_text(snapshot_after_rows),
        "legacy_editor_state_first_caption_text_after_resave": _first_caption_text(editor_state_after_rows),
        "loaded_signature_matches_runtime": loaded_signature == runtime_signature,
        "loaded_signature_matches_reloaded": loaded_signature == reloaded_signature,
        "storage_snapshot_matches_loaded": snapshot_signature == loaded_signature,
        "storage_after_has_top_level_nle": "nle" in storage_after,
        "storage_after_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in storage_after,
        "storage_after_has_readback_report": NLE_SNAPSHOT_READBACK_PARITY_KEY in storage_after,
        "storage_after_has_quarantine": NLE_PERSISTENCE_QUARANTINE_KEY in storage_after,
        "not_runtime_state_persistence": True,
        "not_legacy_disk_shape_replacement": True,
        "not_final_cutover": True,
        "blocked_gates_remaining": [
            "legacy_disk_shape_replacement_allowed",
            "final_cutover_ready",
        ],
    }


def _runtime_project_state_persistence_opt_in_check(work_dir: Path) -> dict[str, Any]:
    project_path = work_dir / "runtime-project-state-persistence-opt-in.aissproj"
    project = _legacy_project()
    project["nle_persistence"] = {
        "persist_snapshot": True,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
        "canonical_load_owner": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
        "canonical_load_owner_change_allowed": True,
        "nle_snapshot_canonical_load_source_allowed": True,
        "legacy_editor_state_remains_canonical": False,
        "legacy_editor_state_preserved_for_rollback": True,
        "persist_runtime_project_state": True,
        "runtime_project_state_persistence_allowed": True,
        "default_project_authority_unchanged": True,
        "legacy_disk_shape_replacement_allowed": False,
        "final_cutover_ready": False,
    }
    expected_legacy_rows = _row_signature(
        project_segments_to_editor(project, include_analysis_candidates=False),
        include_id=False,
    )
    expected_canonical_text = "runtime persisted snapshot first"
    write_project_file(str(project_path), project)
    storage = read_project_storage_payload(str(project_path))
    storage["nle_snapshot"]["sequences"][0]["captions"][0]["text"] = expected_canonical_text
    storage[NLE_PROJECT_STATE_RUNTIME_KEY]["editor_rows"][0]["text"] = expected_canonical_text
    storage[NLE_PROJECT_STATE_RUNTIME_KEY]["snapshot"]["sequences"][0]["captions"][0]["text"] = expected_canonical_text
    project_path.write_bytes(project_io._pack_project_payload(storage))
    clear_project_file_cache(str(project_path))

    loaded = read_project_file(str(project_path))
    loaded_rows = project_segments_to_editor(loaded, include_analysis_candidates=False)
    runtime_state = loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    runtime_rows = runtime_state.editor_rows() if isinstance(runtime_state, NLEProjectState) else []
    write_project_file(str(project_path), loaded)
    storage_after = read_project_storage_payload(str(project_path))
    cached = read_project_file(str(project_path))
    cached_runtime_state = cached.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    write_project_file(str(project_path), cached)
    storage_after_cache_hit = read_project_storage_payload(str(project_path))
    clear_project_file_cache(str(project_path))
    reloaded = read_project_file(str(project_path))
    reloaded_rows = project_segments_to_editor(reloaded, include_analysis_candidates=False)

    snapshot_after = storage_after.get("nle_snapshot") if isinstance(storage_after.get("nle_snapshot"), dict) else {}
    runtime_after = (
        storage_after.get(NLE_PROJECT_STATE_RUNTIME_KEY)
        if isinstance(storage_after.get(NLE_PROJECT_STATE_RUNTIME_KEY), dict)
        else {}
    )
    runtime_persistence = (
        runtime_after.get("persistence") if isinstance(runtime_after.get("persistence"), dict) else {}
    )
    snapshot_after_rows = _editor_rows_from_top_level_nle_payload(snapshot_after)
    runtime_after_rows = runtime_after.get("editor_rows") if isinstance(runtime_after.get("editor_rows"), list) else []
    editor_state_after_rows = project_segments_to_editor(
        {"editor_state": storage_after.get("editor_state") or {}, "video": storage_after.get("video") or {}},
        include_analysis_candidates=False,
    )

    loaded_signature = _row_signature(loaded_rows, include_id=False)
    runtime_signature = _row_signature(runtime_rows, include_id=False)
    reloaded_signature = _row_signature(reloaded_rows, include_id=False)
    snapshot_signature = _row_signature(snapshot_after_rows, include_id=False)
    runtime_after_signature = _row_signature(runtime_after_rows, include_id=False)
    editor_state_after_signature = _row_signature(editor_state_after_rows, include_id=False)
    ready = (
        bool(runtime_after)
        and str(runtime_after.get("schema") or "") == "ai_subtitle_studio.nle_project_state.v1"
        and str(runtime_persistence.get("schema") or "") == NLE_RUNTIME_STATE_PERSISTENCE_APPROVAL_SCHEMA
        and bool(runtime_persistence.get("runtime_project_state_persistence_allowed"))
        and bool(runtime_persistence.get("default_project_authority_unchanged"))
        and not bool(runtime_persistence.get("legacy_disk_shape_replacement_allowed"))
        and not bool(runtime_persistence.get("final_cutover_ready"))
        and isinstance(runtime_state, NLEProjectState)
        and isinstance(cached_runtime_state, NLEProjectState)
        and _first_caption_text(loaded_rows) == expected_canonical_text
        and _first_caption_text(runtime_rows) == expected_canonical_text
        and _first_caption_text(reloaded_rows) == expected_canonical_text
        and _first_caption_text(snapshot_after_rows) == expected_canonical_text
        and _first_caption_text(runtime_after_rows) == expected_canonical_text
        and loaded_signature == runtime_signature == reloaded_signature == snapshot_signature == runtime_after_signature
        and editor_state_after_signature == expected_legacy_rows
        and _first_caption_text(editor_state_after_rows) == "first"
        and "nle" not in storage_after
        and NLE_SNAPSHOT_READBACK_PARITY_KEY not in storage_after
        and NLE_PERSISTENCE_QUARANTINE_KEY not in storage_after
        and NLE_PROJECT_STATE_RUNTIME_KEY in storage_after_cache_hit
        and NLE_PERSISTENCE_QUARANTINE_KEY not in storage_after_cache_hit
    )
    return {
        "ready": ready,
        "status": "ready" if ready else "blocked",
        "explicit_opt_in": True,
        "runtime_project_state_persistence_allowed": bool(
            runtime_persistence.get("runtime_project_state_persistence_allowed")
        ),
        "default_project_authority_unchanged": bool(runtime_persistence.get("default_project_authority_unchanged")),
        "legacy_disk_shape_replacement_allowed": bool(runtime_persistence.get("legacy_disk_shape_replacement_allowed")),
        "final_cutover_ready": bool(runtime_persistence.get("final_cutover_ready")),
        "runtime_payload_schema": str(runtime_after.get("schema") or ""),
        "runtime_persistence_schema": str(runtime_persistence.get("schema") or ""),
        "loaded_first_caption_text": _first_caption_text(loaded_rows),
        "runtime_first_caption_text": _first_caption_text(runtime_rows),
        "reloaded_first_caption_text": _first_caption_text(reloaded_rows),
        "storage_snapshot_first_caption_text": _first_caption_text(snapshot_after_rows),
        "storage_runtime_first_caption_text": _first_caption_text(runtime_after_rows),
        "legacy_editor_state_first_caption_text_after_resave": _first_caption_text(editor_state_after_rows),
        "loaded_signature_matches_runtime": loaded_signature == runtime_signature,
        "loaded_signature_matches_reloaded": loaded_signature == reloaded_signature,
        "storage_runtime_matches_snapshot": runtime_after_signature == snapshot_signature,
        "legacy_editor_state_preserved_for_rollback": editor_state_after_signature == expected_legacy_rows,
        "cache_hit_runtime_state_hydrated": isinstance(cached_runtime_state, NLEProjectState),
        "cache_hit_storage_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in storage_after_cache_hit,
        "storage_after_has_top_level_nle": "nle" in storage_after,
        "storage_after_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in storage_after,
        "storage_after_has_readback_report": NLE_SNAPSHOT_READBACK_PARITY_KEY in storage_after,
        "storage_after_has_quarantine": NLE_PERSISTENCE_QUARANTINE_KEY in storage_after,
        "not_default_authority_change": True,
        "not_legacy_disk_shape_replacement": True,
        "not_final_cutover": True,
        "blocked_gates_remaining": [
            "legacy_disk_shape_replacement_allowed",
            "final_cutover_ready",
        ],
    }


def _legacy_disk_shape_replacement_opt_in_check(work_dir: Path) -> dict[str, Any]:
    project_path = work_dir / "legacy-disk-shape-replacement-opt-in.aissproj"
    project = _legacy_project()
    project["nle_persistence"] = {
        "persist_snapshot": True,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
        "canonical_load_owner": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
        "canonical_load_owner_change_allowed": True,
        "nle_snapshot_canonical_load_source_allowed": True,
        "legacy_editor_state_remains_canonical": False,
        "legacy_editor_state_preserved_for_rollback": True,
        "persist_runtime_project_state": True,
        "runtime_project_state_persistence_allowed": True,
        "default_project_authority_unchanged": True,
        "legacy_disk_shape_replacement_allowed": True,
        "legacy_editor_state_rows_replaced": True,
        "legacy_editor_state_projection_source": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
        "legacy_disk_shape_replacement_schema": NLE_LEGACY_DISK_SHAPE_REPLACEMENT_APPROVAL_SCHEMA,
        "final_cutover_ready": False,
    }
    replacement_text = "legacy replacement canonical first"
    write_project_file(str(project_path), project)
    storage = read_project_storage_payload(str(project_path))
    storage["nle_snapshot"]["sequences"][0]["captions"][0]["text"] = replacement_text
    project_path.write_bytes(project_io._pack_project_payload(storage))
    clear_project_file_cache(str(project_path))

    loaded = read_project_file(str(project_path))
    loaded_rows = project_segments_to_editor(loaded, include_analysis_candidates=False)
    runtime_state = loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    runtime_rows = runtime_state.editor_rows() if isinstance(runtime_state, NLEProjectState) else []
    write_project_file(str(project_path), loaded)
    storage_after = read_project_storage_payload(str(project_path))
    cached = read_project_file(str(project_path))
    cached_runtime_state = cached.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    write_project_file(str(project_path), cached)
    storage_after_cache_hit = read_project_storage_payload(str(project_path))
    clear_project_file_cache(str(project_path))
    reloaded = read_project_file(str(project_path))
    reloaded_rows = project_segments_to_editor(reloaded, include_analysis_candidates=False)

    policy_after = storage_after.get("nle_persistence") if isinstance(storage_after.get("nle_persistence"), dict) else {}
    snapshot_after = storage_after.get("nle_snapshot") if isinstance(storage_after.get("nle_snapshot"), dict) else {}
    runtime_after = (
        storage_after.get(NLE_PROJECT_STATE_RUNTIME_KEY)
        if isinstance(storage_after.get(NLE_PROJECT_STATE_RUNTIME_KEY), dict)
        else {}
    )
    editor_state_after = storage_after.get("editor_state") if isinstance(storage_after.get("editor_state"), dict) else {}
    editor_state_after_rows = project_segments_to_editor(
        {"editor_state": editor_state_after, "video": storage_after.get("video") or {}},
        include_analysis_candidates=False,
    )
    snapshot_after_rows = _editor_rows_from_top_level_nle_payload(snapshot_after)
    runtime_after_rows = runtime_after.get("editor_rows") if isinstance(runtime_after.get("editor_rows"), list) else []

    loaded_signature = _row_signature(loaded_rows, include_id=False)
    runtime_signature = _row_signature(runtime_rows, include_id=False)
    reloaded_signature = _row_signature(reloaded_rows, include_id=False)
    snapshot_signature = _row_signature(snapshot_after_rows, include_id=False)
    runtime_after_signature = _row_signature(runtime_after_rows, include_id=False)
    editor_state_after_signature = _row_signature(editor_state_after_rows, include_id=False)

    forged = _legacy_project()
    forged["nle_persistence"] = {
        "persist_snapshot": True,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
        "canonical_load_owner": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
        "canonical_load_owner_change_allowed": True,
        "nle_snapshot_canonical_load_source_allowed": True,
        "legacy_editor_state_remains_canonical": False,
        "legacy_editor_state_preserved_for_rollback": True,
        "persist_runtime_project_state": True,
        "runtime_project_state_persistence_allowed": True,
        "default_project_authority_unchanged": True,
        "legacy_disk_shape_replacement_allowed": True,
        "legacy_editor_state_rows_replaced": True,
        "final_cutover_ready": False,
    }
    forged_path = work_dir / "forged-legacy-disk-shape-replacement.aissproj"
    write_project_file(str(forged_path), forged)
    forged_storage = read_project_storage_payload(str(forged_path))
    forged_policy = (
        forged_storage.get("nle_persistence") if isinstance(forged_storage.get("nle_persistence"), dict) else {}
    )
    direct_srt = build_direct_srt_precedence_report(output_dir=work_dir / "direct_srt_precedence")

    ready = (
        str(policy_after.get("legacy_disk_shape_replacement_schema") or "")
        == NLE_LEGACY_DISK_SHAPE_REPLACEMENT_APPROVAL_SCHEMA
        and bool(policy_after.get("legacy_disk_shape_replacement_allowed"))
        and bool(policy_after.get("legacy_editor_state_rows_replaced"))
        and bool(policy_after.get("legacy_editor_state_preserved_for_rollback"))
        and bool(policy_after.get("default_project_authority_unchanged"))
        and not bool(policy_after.get("final_cutover_ready"))
        and isinstance(runtime_state, NLEProjectState)
        and isinstance(cached_runtime_state, NLEProjectState)
        and _first_caption_text(loaded_rows) == replacement_text
        and _first_caption_text(runtime_rows) == replacement_text
        and _first_caption_text(reloaded_rows) == replacement_text
        and _first_caption_text(snapshot_after_rows) == replacement_text
        and _first_caption_text(runtime_after_rows) == replacement_text
        and _first_caption_text(editor_state_after_rows) == replacement_text
        and loaded_signature
        == runtime_signature
        == reloaded_signature
        == snapshot_signature
        == runtime_after_signature
        == editor_state_after_signature
        and bool(editor_state_after.get("legacy_disk_shape_replacement"))
        and bool((editor_state_after.get("subtitles") or {}).get("legacy_disk_shape_replaced"))
        and "nle" not in storage_after
        and NLE_SNAPSHOT_READBACK_PARITY_KEY not in storage_after
        and NLE_PERSISTENCE_QUARANTINE_KEY not in storage_after
        and NLE_PROJECT_STATE_RUNTIME_KEY in storage_after
        and NLE_PROJECT_STATE_RUNTIME_KEY in storage_after_cache_hit
        and not bool(forged_policy.get("legacy_disk_shape_replacement_allowed"))
        and not bool(forged_policy.get("legacy_editor_state_rows_replaced"))
        and bool(direct_srt.get("passed"))
    )
    return {
        "ready": ready,
        "status": "ready" if ready else "blocked",
        "explicit_opt_in": True,
        "legacy_disk_shape_replacement_allowed": bool(policy_after.get("legacy_disk_shape_replacement_allowed")),
        "legacy_disk_shape_replacement_schema": str(policy_after.get("legacy_disk_shape_replacement_schema") or ""),
        "legacy_editor_state_rows_replaced": bool(policy_after.get("legacy_editor_state_rows_replaced")),
        "legacy_editor_state_preserved_for_rollback": bool(
            policy_after.get("legacy_editor_state_preserved_for_rollback")
        ),
        "default_project_authority_unchanged": bool(policy_after.get("default_project_authority_unchanged")),
        "final_cutover_ready": bool(policy_after.get("final_cutover_ready")),
        "loaded_first_caption_text": _first_caption_text(loaded_rows),
        "runtime_first_caption_text": _first_caption_text(runtime_rows),
        "reloaded_first_caption_text": _first_caption_text(reloaded_rows),
        "storage_snapshot_first_caption_text": _first_caption_text(snapshot_after_rows),
        "storage_runtime_first_caption_text": _first_caption_text(runtime_after_rows),
        "legacy_editor_state_first_caption_text_after_resave": _first_caption_text(editor_state_after_rows),
        "loaded_signature_matches_runtime": loaded_signature == runtime_signature,
        "loaded_signature_matches_reloaded": loaded_signature == reloaded_signature,
        "legacy_editor_state_matches_snapshot": editor_state_after_signature == snapshot_signature,
        "storage_runtime_matches_snapshot": runtime_after_signature == snapshot_signature,
        "cache_hit_runtime_state_hydrated": isinstance(cached_runtime_state, NLEProjectState),
        "cache_hit_storage_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in storage_after_cache_hit,
        "storage_after_has_top_level_nle": "nle" in storage_after,
        "storage_after_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in storage_after,
        "storage_after_has_readback_report": NLE_SNAPSHOT_READBACK_PARITY_KEY in storage_after,
        "storage_after_has_quarantine": NLE_PERSISTENCE_QUARANTINE_KEY in storage_after,
        "forged_policy_blocked": not bool(forged_policy.get("legacy_disk_shape_replacement_allowed")),
        "direct_srt_precedence_preserved": bool(direct_srt.get("passed")),
        "not_final_cutover": True,
        "blocked_gates_remaining": ["final_cutover_ready"],
    }


def _final_cutover_ready_check(work_dir: Path) -> dict[str, Any]:
    project_path = work_dir / "final-cutover-ready-opt-in.aissproj"
    project = _legacy_project()
    project["nle_persistence"] = {
        "persist_snapshot": True,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
        "canonical_load_owner": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
        "canonical_load_owner_change_allowed": True,
        "nle_snapshot_canonical_load_source_allowed": True,
        "legacy_editor_state_remains_canonical": False,
        "legacy_editor_state_preserved_for_rollback": True,
        "persist_runtime_project_state": True,
        "runtime_project_state_persistence_allowed": True,
        "default_project_authority_unchanged": False,
        "default_project_authority_changed": True,
        "default_project_authority": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
        "legacy_disk_shape_replacement_allowed": True,
        "legacy_editor_state_rows_replaced": True,
        "legacy_editor_state_projection_source": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
        "legacy_disk_shape_replacement_schema": NLE_LEGACY_DISK_SHAPE_REPLACEMENT_APPROVAL_SCHEMA,
        "legacy_editor_state_compatibility_key_preserved": True,
        "final_cutover_ready": True,
        "final_cutover_schema": NLE_FINAL_CUTOVER_APPROVAL_SCHEMA,
    }
    final_text = "final cutover canonical first"
    write_project_file(str(project_path), project)
    storage = read_project_storage_payload(str(project_path))
    storage["nle_snapshot"]["sequences"][0]["captions"][0]["text"] = final_text
    project_path.write_bytes(project_io._pack_project_payload(storage))
    clear_project_file_cache(str(project_path))

    loaded = read_project_file(str(project_path))
    loaded_rows = project_segments_to_editor(loaded, include_analysis_candidates=False)
    runtime_state = loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    runtime_rows = runtime_state.editor_rows() if isinstance(runtime_state, NLEProjectState) else []
    write_project_file(str(project_path), loaded)
    storage_after = read_project_storage_payload(str(project_path))
    cached = read_project_file(str(project_path))
    cached_runtime_state = cached.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    write_project_file(str(project_path), cached)
    storage_after_cache_hit = read_project_storage_payload(str(project_path))
    clear_project_file_cache(str(project_path))
    reloaded = read_project_file(str(project_path))
    reloaded_rows = project_segments_to_editor(reloaded, include_analysis_candidates=False)

    policy_after = storage_after.get("nle_persistence") if isinstance(storage_after.get("nle_persistence"), dict) else {}
    snapshot_after = storage_after.get("nle_snapshot") if isinstance(storage_after.get("nle_snapshot"), dict) else {}
    runtime_after = (
        storage_after.get(NLE_PROJECT_STATE_RUNTIME_KEY)
        if isinstance(storage_after.get(NLE_PROJECT_STATE_RUNTIME_KEY), dict)
        else {}
    )
    editor_state_after = storage_after.get("editor_state") if isinstance(storage_after.get("editor_state"), dict) else {}
    editor_state_after_rows = project_segments_to_editor(
        {"editor_state": editor_state_after, "video": storage_after.get("video") or {}},
        include_analysis_candidates=False,
    )
    snapshot_after_rows = _editor_rows_from_top_level_nle_payload(snapshot_after)
    runtime_after_rows = runtime_after.get("editor_rows") if isinstance(runtime_after.get("editor_rows"), list) else []

    loaded_signature = _row_signature(loaded_rows, include_id=False)
    runtime_signature = _row_signature(runtime_rows, include_id=False)
    reloaded_signature = _row_signature(reloaded_rows, include_id=False)
    snapshot_signature = _row_signature(snapshot_after_rows, include_id=False)
    runtime_after_signature = _row_signature(runtime_after_rows, include_id=False)
    editor_state_after_signature = _row_signature(editor_state_after_rows, include_id=False)
    subtitle_meta = editor_state_after.get("subtitles") if isinstance(editor_state_after.get("subtitles"), dict) else {}
    canvas = (
        editor_state_after.get("rendering", {}).get("subtitle_canvas", {})
        if isinstance(editor_state_after.get("rendering"), dict)
        else {}
    )

    forged = _legacy_project()
    forged["nle_persistence"] = {
        "persist_snapshot": True,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
        "canonical_load_owner": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
        "canonical_load_owner_change_allowed": True,
        "nle_snapshot_canonical_load_source_allowed": True,
        "legacy_editor_state_remains_canonical": False,
        "legacy_editor_state_preserved_for_rollback": True,
        "persist_runtime_project_state": True,
        "runtime_project_state_persistence_allowed": True,
        "default_project_authority_unchanged": False,
        "default_project_authority_changed": True,
        "default_project_authority": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
        "legacy_disk_shape_replacement_allowed": True,
        "legacy_editor_state_rows_replaced": True,
        "legacy_editor_state_projection_source": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
        "legacy_disk_shape_replacement_schema": NLE_LEGACY_DISK_SHAPE_REPLACEMENT_APPROVAL_SCHEMA,
        "legacy_editor_state_compatibility_key_preserved": True,
        "final_cutover_ready": True,
    }
    forged_path = work_dir / "forged-final-cutover-ready.aissproj"
    write_project_file(str(forged_path), forged)
    forged_storage = read_project_storage_payload(str(forged_path))
    forged_policy = (
        forged_storage.get("nle_persistence") if isinstance(forged_storage.get("nle_persistence"), dict) else {}
    )
    direct_srt = build_direct_srt_precedence_report(output_dir=work_dir / "direct_srt_precedence")

    ready = (
        str(policy_after.get("final_cutover_schema") or "") == NLE_FINAL_CUTOVER_APPROVAL_SCHEMA
        and bool(policy_after.get("final_cutover_ready"))
        and str(policy_after.get("canonical_load_owner") or "") == NLE_SNAPSHOT_CANONICAL_LOAD_OWNER
        and str(policy_after.get("default_project_authority") or "") == NLE_SNAPSHOT_CANONICAL_LOAD_OWNER
        and bool(policy_after.get("default_project_authority_changed"))
        and not bool(policy_after.get("default_project_authority_unchanged"))
        and bool(policy_after.get("legacy_editor_state_compatibility_key_preserved"))
        and bool(policy_after.get("legacy_editor_state_preserved_for_rollback"))
        and bool(policy_after.get("legacy_disk_shape_replacement_allowed"))
        and bool(policy_after.get("legacy_editor_state_rows_replaced"))
        and isinstance(runtime_state, NLEProjectState)
        and isinstance(cached_runtime_state, NLEProjectState)
        and _first_caption_text(loaded_rows) == final_text
        and _first_caption_text(runtime_rows) == final_text
        and _first_caption_text(reloaded_rows) == final_text
        and _first_caption_text(snapshot_after_rows) == final_text
        and _first_caption_text(runtime_after_rows) == final_text
        and _first_caption_text(editor_state_after_rows) == final_text
        and loaded_signature
        == runtime_signature
        == reloaded_signature
        == snapshot_signature
        == runtime_after_signature
        == editor_state_after_signature
        and bool(editor_state_after.get("legacy_disk_shape_replacement"))
        and bool(subtitle_meta.get("legacy_editor_state_compatibility_key_preserved"))
        and bool(canvas.get("legacy_editor_state_compatibility_key_preserved"))
        and "nle" not in storage_after
        and NLE_SNAPSHOT_READBACK_PARITY_KEY not in storage_after
        and NLE_PERSISTENCE_QUARANTINE_KEY not in storage_after
        and NLE_PROJECT_STATE_RUNTIME_KEY in storage_after
        and NLE_PROJECT_STATE_RUNTIME_KEY in storage_after_cache_hit
        and not bool(forged_policy.get("final_cutover_ready"))
        and str(forged_policy.get("final_cutover_schema") or "") != NLE_FINAL_CUTOVER_APPROVAL_SCHEMA
        and bool(direct_srt.get("passed"))
    )
    return {
        "ready": ready,
        "status": "ready" if ready else "blocked",
        "explicit_opt_in": True,
        "final_cutover_ready": bool(policy_after.get("final_cutover_ready")),
        "final_cutover_schema": str(policy_after.get("final_cutover_schema") or ""),
        "canonical_load_owner": str(policy_after.get("canonical_load_owner") or ""),
        "default_project_authority": str(policy_after.get("default_project_authority") or ""),
        "default_project_authority_changed": bool(policy_after.get("default_project_authority_changed")),
        "default_project_authority_unchanged": bool(policy_after.get("default_project_authority_unchanged")),
        "legacy_disk_shape_replacement_allowed": bool(policy_after.get("legacy_disk_shape_replacement_allowed")),
        "legacy_editor_state_rows_replaced": bool(policy_after.get("legacy_editor_state_rows_replaced")),
        "legacy_editor_state_preserved_for_rollback": bool(
            policy_after.get("legacy_editor_state_preserved_for_rollback")
        ),
        "legacy_editor_state_compatibility_key_preserved": bool(
            policy_after.get("legacy_editor_state_compatibility_key_preserved")
        ),
        "editor_state_key_present": "editor_state" in storage_after,
        "editor_state_is_compatibility_projection": bool(
            subtitle_meta.get("legacy_editor_state_compatibility_key_preserved")
        ),
        "loaded_first_caption_text": _first_caption_text(loaded_rows),
        "runtime_first_caption_text": _first_caption_text(runtime_rows),
        "reloaded_first_caption_text": _first_caption_text(reloaded_rows),
        "storage_snapshot_first_caption_text": _first_caption_text(snapshot_after_rows),
        "storage_runtime_first_caption_text": _first_caption_text(runtime_after_rows),
        "legacy_editor_state_first_caption_text_after_resave": _first_caption_text(editor_state_after_rows),
        "loaded_signature_matches_runtime": loaded_signature == runtime_signature,
        "loaded_signature_matches_reloaded": loaded_signature == reloaded_signature,
        "legacy_editor_state_matches_snapshot": editor_state_after_signature == snapshot_signature,
        "storage_runtime_matches_snapshot": runtime_after_signature == snapshot_signature,
        "cache_hit_runtime_state_hydrated": isinstance(cached_runtime_state, NLEProjectState),
        "cache_hit_storage_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in storage_after_cache_hit,
        "storage_after_has_top_level_nle": "nle" in storage_after,
        "storage_after_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in storage_after,
        "storage_after_has_readback_report": NLE_SNAPSHOT_READBACK_PARITY_KEY in storage_after,
        "storage_after_has_quarantine": NLE_PERSISTENCE_QUARANTINE_KEY in storage_after,
        "forged_policy_blocked": not bool(forged_policy.get("final_cutover_ready"))
        and str(forged_policy.get("final_cutover_schema") or "") != NLE_FINAL_CUTOVER_APPROVAL_SCHEMA,
        "direct_srt_precedence_preserved": bool(direct_srt.get("passed")),
        "blocked_gates_remaining": [],
    }


def _canonical_load_owner_rollback_boundary_check(work_dir: Path) -> dict[str, Any]:
    project_path = work_dir / "canonical-load-owner-rollback-boundary.aissproj"
    project = _legacy_project()
    project["nle_persistence"] = {
        "persist_snapshot": True,
        "persist_top_level_nle": True,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
    }
    expected_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    expected_signature = _row_signature(expected_rows, include_id=False)
    write_project_file(str(project_path), project)
    storage = read_project_storage_payload(str(project_path))

    candidate_load_owner = "top_level_nle_shadow_metadata"
    rollback_probe_text = "rollback candidate shadow text"
    candidate_storage = deepcopy(storage)
    nle_payload = candidate_storage.get("nle") if isinstance(candidate_storage.get("nle"), dict) else {}
    nle_payload["canonical_load_owner"] = candidate_load_owner
    nle_payload["runtime_project_state_persisted"] = True
    nle_persistence = nle_payload.get("persistence") if isinstance(nle_payload.get("persistence"), dict) else {}
    nle_persistence["canonical_load_owner"] = candidate_load_owner
    nle_persistence["legacy_editor_state_remains_canonical"] = False
    nle_persistence["runtime_project_state_persisted"] = True
    sequences = nle_payload.get("sequences") if isinstance(nle_payload.get("sequences"), list) else []
    sequence = sequences[0] if sequences and isinstance(sequences[0], dict) else {}
    captions = sequence.get("captions") if isinstance(sequence.get("captions"), list) else []
    if captions and isinstance(captions[0], dict):
        captions[0]["text"] = rollback_probe_text
    snapshot = (
        candidate_storage.get("nle_snapshot")
        if isinstance(candidate_storage.get("nle_snapshot"), dict)
        else {}
    )
    snapshot_persistence = (
        snapshot.get("persistence") if isinstance(snapshot.get("persistence"), dict) else {}
    )
    snapshot_persistence["legacy_editor_state_remains_canonical"] = False
    snapshot_persistence["runtime_project_state_persisted"] = True
    candidate_storage[NLE_PROJECT_STATE_RUNTIME_KEY] = {"schema": "future-runtime-persistence-candidate"}
    project_path.write_text(json.dumps(candidate_storage, ensure_ascii=False), encoding="utf-8")
    clear_project_file_cache(str(project_path))

    loaded = read_project_file(str(project_path))
    rollback_report = (
        loaded.get(NLE_PERSISTENCE_QUARANTINE_KEY)
        if isinstance(loaded.get(NLE_PERSISTENCE_QUARANTINE_KEY), dict)
        else {}
    )
    loaded_rows = project_segments_to_editor(loaded, include_analysis_candidates=False)
    loaded_signature = _row_signature(loaded_rows, include_id=False)
    loaded_state = loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    write_project_file(str(project_path), loaded)
    storage_after = read_project_storage_payload(str(project_path))
    try:
        assert_no_unapproved_nle_persistence_fields(storage_after, surface="rollback_boundary_storage_after")
        storage_after_clean = True
    except ValueError:
        storage_after_clean = False
    storage_after_nle = storage_after.get("nle") if isinstance(storage_after.get("nle"), dict) else {}
    storage_after_rows = _editor_rows_from_top_level_nle_payload(storage_after_nle)
    storage_after_first_caption_text = _first_caption_text(storage_after_rows)
    stripped_keys = list(rollback_report.get("stripped_keys") or [])
    ready = (
        bool(rollback_report)
        and {"nle", "nle_snapshot", NLE_PROJECT_STATE_RUNTIME_KEY}.issubset(set(stripped_keys))
        and loaded_signature == expected_signature
        and _first_caption_text(loaded_rows) == "first"
        and _first_caption_text(loaded_rows) != rollback_probe_text
        and isinstance(loaded_state, NLEProjectState)
        and storage_after_clean
        and "nle" in storage_after
        and "nle_snapshot" in storage_after
        and str(storage_after_nle.get("canonical_load_owner") or "") == "legacy_editor_state"
        and storage_after_first_caption_text == "first"
        and storage_after_first_caption_text != rollback_probe_text
        and NLE_PROJECT_STATE_RUNTIME_KEY not in storage_after
        and NLE_PERSISTENCE_QUARANTINE_KEY not in storage_after
    )
    return {
        "project_path": str(project_path),
        "ready": ready,
        "status": "defined" if ready else "blocked",
        "not_runtime_change": True,
        "not_disk_format_cutover": True,
        "not_ui_change": True,
        "rollback_target": "legacy_editor_state",
        "candidate_load_owner": candidate_load_owner,
        "candidate_runtime_state_persistence_attempted": True,
        "candidate_snapshot_canonical_source_attempted": True,
        "candidate_shadow_text": rollback_probe_text,
        "loaded_first_caption_text": _first_caption_text(loaded_rows),
        "resave_first_caption_text": storage_after_first_caption_text,
        "candidate_shadow_text_leaked_to_default_load": _first_caption_text(loaded_rows) == rollback_probe_text,
        "candidate_shadow_text_leaked_after_resave": storage_after_first_caption_text == rollback_probe_text,
        "quarantine_recorded": bool(rollback_report),
        "stripped_keys": stripped_keys,
        "stripped_count": int(rollback_report.get("stripped_count") or 0),
        "default_load_preserved_legacy_rows": loaded_signature == expected_signature,
        "runtime_state_hydrated_from_legacy": isinstance(loaded_state, NLEProjectState),
        "storage_after_clean": storage_after_clean,
        "storage_after_nle_canonical_load_owner": str(storage_after_nle.get("canonical_load_owner") or ""),
        "storage_after_has_nle": "nle" in storage_after,
        "storage_after_has_nle_snapshot": "nle_snapshot" in storage_after,
        "storage_after_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in storage_after,
        "storage_after_has_quarantine": NLE_PERSISTENCE_QUARANTINE_KEY in storage_after,
    }


def _approved_snapshot_persistence_check(work_dir: Path) -> dict[str, Any]:
    project_path = work_dir / "approved-nle-snapshot.aissproj"
    project = _legacy_project()
    project["nle_persistence"] = {
        "persist_snapshot": True,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
    }
    expected_rows = _row_signature(
        project_segments_to_editor(project, include_analysis_candidates=False),
        include_id=False,
    )
    write_project_file(str(project_path), project)
    storage = read_project_storage_payload(str(project_path))
    assert_no_unapproved_nle_persistence_fields(storage, surface="approved_snapshot_storage")
    clear_project_file_cache(str(project_path))
    loaded = read_project_file(str(project_path))
    loaded_rows = _row_signature(
        project_segments_to_editor(loaded, include_analysis_candidates=False),
        include_id=False,
    )
    loaded_state = loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    parity = loaded.get(NLE_SNAPSHOT_READBACK_PARITY_KEY) if isinstance(loaded.get(NLE_SNAPSHOT_READBACK_PARITY_KEY), dict) else {}
    snapshot = storage.get("nle_snapshot") if isinstance(storage.get("nle_snapshot"), dict) else {}
    persistence = snapshot.get("persistence") if isinstance(snapshot.get("persistence"), dict) else {}
    ready = (
        bool(snapshot)
        and str(snapshot.get("schema") or "") == "ai_subtitle_studio.nle_snapshot.v1"
        and str(persistence.get("approval") or "") == NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID
        and expected_rows == loaded_rows
        and isinstance(loaded_state, NLEProjectState)
        and bool(parity.get("stable"))
        and int(parity.get("mismatch_count") or 0) == 0
        and "nle" not in storage
        and NLE_PROJECT_STATE_RUNTIME_KEY not in storage
        and NLE_PERSISTENCE_QUARANTINE_KEY not in storage
    )
    return {
        "project_path": str(project_path),
        "ready": ready,
        "snapshot_persisted": bool(snapshot),
        "snapshot_schema": str(snapshot.get("schema") or ""),
        "snapshot_caption_count": int((snapshot.get("metadata") or {}).get("caption_count") or 0)
        if isinstance(snapshot.get("metadata"), dict)
        else 0,
        "snapshot_gap_count": int((snapshot.get("metadata") or {}).get("gap_count") or 0)
        if isinstance(snapshot.get("metadata"), dict)
        else 0,
        "approval": str(persistence.get("approval") or ""),
        "legacy_rows_stable": expected_rows == loaded_rows,
        "readback_parity_checked": bool(parity.get("checked")),
        "readback_parity_stable": bool(parity.get("stable")),
        "readback_mismatch_count": int(parity.get("mismatch_count") or 0),
        "loaded_runtime_state": isinstance(loaded_state, NLEProjectState),
        "storage_has_nle": "nle" in storage,
        "storage_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in storage,
        "storage_has_nle_snapshot": "nle_snapshot" in storage,
        "storage_has_quarantine": NLE_PERSISTENCE_QUARANTINE_KEY in storage,
    }


def _approved_top_level_nle_shadow_check(work_dir: Path) -> dict[str, Any]:
    project_path = work_dir / "approved-top-level-nle-shadow.aissproj"
    project = _legacy_project()
    project["nle_persistence"] = {
        "persist_snapshot": True,
        "persist_top_level_nle": True,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
    }
    expected_rows = _row_signature(
        project_segments_to_editor(project, include_analysis_candidates=False),
        include_id=False,
    )
    write_project_file(str(project_path), project)
    storage = read_project_storage_payload(str(project_path))
    assert_no_unapproved_nle_persistence_fields(storage, surface="approved_top_level_nle_storage")
    nle_payload = storage.get("nle") if isinstance(storage.get("nle"), dict) else {}
    nle_metadata = nle_payload.get("metadata") if isinstance(nle_payload.get("metadata"), dict) else {}
    nle_persistence = nle_payload.get("persistence") if isinstance(nle_payload.get("persistence"), dict) else {}
    clear_project_file_cache(str(project_path))
    loaded = read_project_file(str(project_path))
    loaded_rows = _row_signature(
        project_segments_to_editor(loaded, include_analysis_candidates=False),
        include_id=False,
    )
    loaded_state = loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    parity = loaded.get(NLE_SNAPSHOT_READBACK_PARITY_KEY) if isinstance(loaded.get(NLE_SNAPSHOT_READBACK_PARITY_KEY), dict) else {}
    write_project_file(str(project_path), loaded)
    storage_after = read_project_storage_payload(str(project_path))
    ready = (
        str(nle_payload.get("schema") or "") == NLE_TOP_LEVEL_SHADOW_SCHEMA
        and str(nle_payload.get("role") or "") == "shadow_metadata"
        and str(nle_payload.get("canonical_load_owner") or "") == "legacy_editor_state"
        and not bool(nle_payload.get("runtime_project_state_persisted"))
        and str(nle_persistence.get("schema") or "") == NLE_TOP_LEVEL_PERSISTENCE_APPROVAL_SCHEMA
        and str(nle_persistence.get("approval") or "") == NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID
        and bool(nle_persistence.get("legacy_editor_state_remains_canonical"))
        and loaded_rows == expected_rows
        and isinstance(loaded_state, NLEProjectState)
        and bool(parity.get("stable"))
        and "nle_snapshot" in storage
        and NLE_PROJECT_STATE_RUNTIME_KEY not in storage
        and NLE_PERSISTENCE_QUARANTINE_KEY not in storage
        and NLE_SNAPSHOT_READBACK_PARITY_KEY not in storage_after
        and NLE_PROJECT_STATE_RUNTIME_KEY not in storage_after
        and NLE_PERSISTENCE_QUARANTINE_KEY not in storage_after
    )
    return {
        "project_path": str(project_path),
        "ready": ready,
        "shadow_schema": str(nle_payload.get("schema") or ""),
        "shadow_role": str(nle_payload.get("role") or ""),
        "canonical_load_owner": str(nle_payload.get("canonical_load_owner") or ""),
        "runtime_project_state_persisted": bool(nle_payload.get("runtime_project_state_persisted")),
        "persistence_schema": str(nle_persistence.get("schema") or ""),
        "approval": str(nle_persistence.get("approval") or ""),
        "legacy_rows_stable": loaded_rows == expected_rows,
        "readback_parity_stable": bool(parity.get("stable")),
        "caption_count": int(nle_metadata.get("caption_count") or 0),
        "gap_count": int(nle_metadata.get("gap_count") or 0),
        "marker_count": int(nle_metadata.get("marker_count") or 0),
        "render_plan_count": int(nle_metadata.get("render_plan_count") or 0),
        "storage_has_nle": "nle" in storage,
        "storage_has_nle_snapshot": "nle_snapshot" in storage,
        "storage_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in storage,
        "runtime_report_persisted": NLE_SNAPSHOT_READBACK_PARITY_KEY in storage_after,
        "runtime_state_persisted": NLE_PROJECT_STATE_RUNTIME_KEY in storage_after,
        "quarantine_persisted": NLE_PERSISTENCE_QUARANTINE_KEY in storage_after,
    }


def _corrupted_snapshot_readback_check(work_dir: Path) -> dict[str, Any]:
    project_path = work_dir / "corrupted-approved-nle-snapshot.aissproj"
    project = _legacy_project()
    project["nle_persistence"] = {
        "persist_snapshot": True,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
    }
    expected_rows = _row_signature(
        project_segments_to_editor(project, include_analysis_candidates=False),
        include_id=False,
    )
    write_project_file(str(project_path), project)
    storage = read_project_storage_payload(str(project_path))
    storage["nle_snapshot"]["sequences"][0]["captions"][0]["sequence_start"] = 3.5
    project_path.write_text(json.dumps(storage), encoding="utf-8")
    clear_project_file_cache(str(project_path))
    loaded = read_project_file(str(project_path))
    parity = loaded.get(NLE_SNAPSHOT_READBACK_PARITY_KEY) if isinstance(loaded.get(NLE_SNAPSHOT_READBACK_PARITY_KEY), dict) else {}
    loaded_rows = _row_signature(
        project_segments_to_editor(loaded, include_analysis_candidates=False),
        include_id=False,
    )
    write_project_file(str(project_path), loaded)
    storage_after = read_project_storage_payload(str(project_path))
    return {
        "project_path": str(project_path),
        "drift_detected": bool(parity.get("checked")) and not bool(parity.get("stable")),
        "mismatch_count": int(parity.get("mismatch_count") or 0),
        "legacy_rows_stable": loaded_rows == expected_rows,
        "runtime_report_persisted": NLE_SNAPSHOT_READBACK_PARITY_KEY in storage_after,
        "runtime_state_persisted": NLE_PROJECT_STATE_RUNTIME_KEY in storage_after,
        "quarantine_persisted": NLE_PERSISTENCE_QUARANTINE_KEY in storage_after,
    }


def _surface_by_name(report: Any, target_surface: str) -> dict[str, Any]:
    surfaces = getattr(report, "surface_reports", ()) or ()
    for surface in surfaces:
        payload = surface.to_dict()
        if payload.get("target_surface") == target_surface:
            return payload
    return {}


def _roughcut_sidecar_readback_check(work_dir: Path) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    project_path = work_dir / "roughcut-sidecar-approved.aissproj"
    project = _render_export_project(work_dir)
    project["nle_persistence"] = {
        "persist_snapshot": True,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
    }
    write_project_file(str(project_path), project)
    storage = read_project_storage_payload(str(project_path))
    clear_project_file_cache(str(project_path))

    approved_loaded = read_project_file(str(project_path))
    approved_parity = (
        approved_loaded.get(NLE_SNAPSHOT_READBACK_PARITY_KEY)
        if isinstance(approved_loaded.get(NLE_SNAPSHOT_READBACK_PARITY_KEY), dict)
        else {}
    )
    approved_render_report = assert_project_nle_render_export_parity(
        approved_loaded,
        project_path=str(project_path),
    )
    approved_roughcut = _surface_by_name(approved_render_report, "roughcut_sidecar")

    corrupted_storage = deepcopy(storage)
    persisted_snapshot = (
        corrupted_storage.get("nle_snapshot")
        if isinstance(corrupted_storage.get("nle_snapshot"), dict)
        else {}
    )
    persisted_sequences = (
        persisted_snapshot.get("sequences")
        if isinstance(persisted_snapshot.get("sequences"), list)
        else []
    )
    persisted_sequence = persisted_sequences[0] if persisted_sequences and isinstance(persisted_sequences[0], dict) else {}
    persisted_markers = persisted_sequence.get("markers") if isinstance(persisted_sequence, dict) else []
    persisted_marker_count_before_corruption = len(persisted_markers or [])
    if isinstance(persisted_sequence, dict):
        persisted_sequence["markers"] = []
    project_path.write_text(json.dumps(corrupted_storage, ensure_ascii=False), encoding="utf-8")
    clear_project_file_cache(str(project_path))

    corrupted_loaded = read_project_file(str(project_path))
    corrupted_parity = (
        corrupted_loaded.get(NLE_SNAPSHOT_READBACK_PARITY_KEY)
        if isinstance(corrupted_loaded.get(NLE_SNAPSHOT_READBACK_PARITY_KEY), dict)
        else {}
    )
    corrupted_render_report = assert_project_nle_render_export_parity(
        corrupted_loaded,
        project_path=str(project_path),
    )
    corrupted_roughcut = _surface_by_name(corrupted_render_report, "roughcut_sidecar")
    write_project_file(str(project_path), corrupted_loaded)
    storage_after = read_project_storage_payload(str(project_path))

    return {
        "project_path": str(project_path),
        "approved_snapshot_persisted": isinstance(storage.get("nle_snapshot"), dict),
        "approved_readback_checked": bool(approved_parity.get("checked")),
        "approved_readback_stable": bool(approved_parity.get("stable")),
        "approved_roughcut_sidecar_stable": bool(approved_roughcut.get("stable")),
        "persisted_marker_count_before_corruption": persisted_marker_count_before_corruption,
        "corrupted_marker_drift_detected": bool(corrupted_parity.get("checked"))
        and not bool(corrupted_parity.get("stable")),
        "mismatch_count": int(corrupted_parity.get("mismatch_count") or 0),
        "render_export_stable": corrupted_render_report.diff_summary == "ok",
        "roughcut_sidecar_stable": bool(corrupted_roughcut.get("stable")),
        "sidecar_stitched_boundary_count": int(corrupted_roughcut.get("stitched_boundary_count") or 0),
        "roughcut_marker_count": int(corrupted_roughcut.get("marker_count") or 0),
        "runtime_report_persisted": NLE_SNAPSHOT_READBACK_PARITY_KEY in storage_after,
        "runtime_state_persisted": NLE_PROJECT_STATE_RUNTIME_KEY in storage_after,
        "top_level_nle_persisted": "nle" in storage_after,
        "quarantine_persisted": NLE_PERSISTENCE_QUARANTINE_KEY in storage_after,
    }


def _marker_signature(rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    signature: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = {
            "status": str(row.get("status") or ""),
            "timeline_frame": int(row.get("timeline_frame", row.get("frame", 0)) or 0),
        }
        try:
            item["timeline_sec"] = round(float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0), 6)
        except (TypeError, ValueError):
            item["timeline_sec"] = 0.0
        signature.append(item)
    return signature


def _operation_roundtrip_check(work_dir: Path, operation_name: str, project: dict[str, Any], result: Any) -> dict[str, Any]:
    operation_dir = work_dir / operation_name
    operation_dir.mkdir(parents=True, exist_ok=True)
    project_path = operation_dir / f"{operation_name}.aissproj"
    expected_rows = _row_signature(list(result.projected_rows or []), include_id=False)
    expected_identity_rows = _row_signature(list(result.projected_rows or []), include_id=True)
    expected_markers = _marker_signature(project_cut_boundary_provisional_segments(project))

    write_project_file(str(project_path), deepcopy(project))
    storage = read_project_storage_payload(str(project_path))
    assert_no_unapproved_nle_persistence_fields(storage, surface=f"{operation_name}_storage")
    clear_project_file_cache(str(project_path))
    reopened = read_project_file(str(project_path))
    reopened_state = reopened.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    reopened_rows = project_segments_to_editor(reopened, include_analysis_candidates=False)
    reopened_signature = _row_signature(reopened_rows, include_id=False)
    reopened_identity_signature = _row_signature(reopened_rows, include_id=True)
    reopened_markers = _marker_signature(project_cut_boundary_provisional_segments(reopened))

    return {
        "operation_family": operation_name,
        "project_path": str(project_path),
        "operation_kind": str(getattr(result.operation, "kind", "") or ""),
        "runtime_state_hydrated": isinstance(reopened_state, NLEProjectState),
        "storage_clean": not _storage_has_unapproved_nle_fields(storage),
        "storage_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in storage,
        "storage_has_nle": "nle" in storage,
        "storage_has_nle_snapshot": "nle_snapshot" in storage,
        "reopened_matches_projected": reopened_signature == expected_rows,
        "reopened_identity_preserved": reopened_identity_signature == expected_identity_rows,
        "reopened_markers_preserved": reopened_markers == expected_markers,
        "projected_count": len(expected_rows),
        "reopened_count": len(reopened_signature),
        "projected_marker_count": len(expected_markers),
        "reopened_marker_count": len(reopened_markers),
        "invalid_duration_count": int(getattr(result.after_projection, "invalid_duration_count", 0) or 0),
        "non_monotonic_count": int(getattr(result.after_projection, "non_monotonic_count", 0) or 0),
        "overlap_count": int(getattr(result.after_projection, "overlap_count", 0) or 0),
        "max_active_segments": int(getattr(result.after_projection, "max_active_segments", 0) or 0),
    }


def _operation_roundtrip_matrix(work_dir: Path) -> list[dict[str, Any]]:
    cases: list[tuple[str, dict[str, Any], Any]] = []

    project = _legacy_project()
    cases.append(("gap_delete", project, apply_gap_delete_dual_write_pilot(project, gap_id="gap_1")))

    project = _legacy_project()
    cases.append((
        "gap_generate",
        project,
        apply_gap_generate_dual_write_pilot(project, gap_id="gap_1", sub_start=1.5, sub_end=2.0, mode="from", text="새자막"),
    ))

    project = _legacy_project()
    cases.append((
        "caption_move",
        project,
        apply_caption_move_dual_write_pilot(project, caption_id="subtitle_vector_0002", new_start=3.0, new_end=4.0),
    ))

    project = _three_caption_project()
    cases.append((
        "caption_resize",
        project,
        apply_caption_resize_dual_write_pilot(project, caption_id="subtitle_vector_0002", new_start=0.5, new_end=2.0, edge="square_left"),
    ))

    project = _three_caption_project()
    cases.append((
        "caption_text_edit",
        project,
        apply_caption_text_edit_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            new_text="second\nedited",
            commit_boundary="release",
            commit_source="timeline_inline_text",
        ),
    ))

    project = _three_caption_project()
    cases.append((
        "caption_split",
        project,
        apply_caption_split_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            split_sec=1.4,
            left_text="left",
            right_text="right",
            new_caption_id="subtitle_vector_0002_split_right",
        ),
    ))

    project = _three_caption_project()
    cases.append((
        "caption_range_replace",
        project,
        apply_caption_range_replace_dual_write_pilot(
            project,
            target_start=1.0,
            target_end=2.0,
            committed_rows=[
                {"line": 0, "start": 0.0, "end": 1.0, "text": "first", "speaker": "00"},
                {"line": 1, "start": 1.0, "end": 1.5, "text": "second-a", "speaker": "01"},
                {"line": 2, "start": 1.5, "end": 2.0, "text": "second-b", "speaker": "01"},
                {"line": 3, "start": 2.0, "end": 3.0, "text": "third", "speaker": "02"},
            ],
            commit_boundary="release",
            commit_source="partial_insert_range_replace",
        ),
    ))

    project = _three_caption_project()
    cases.append((
        "caption_merge",
        project,
        apply_caption_merge_dual_write_pilot(
            project,
            left_caption_id="subtitle_vector_0001",
            right_caption_id="subtitle_vector_0002",
            merged_text="first second",
        ),
    ))

    project = _legacy_project()
    cases.append((
        "caption_delete",
        project,
        apply_caption_delete_dual_write_pilot(project, caption_id="subtitle_vector_0002", replacement_gap_id="gap_deleted_caption_2"),
    ))

    project = _three_caption_project()
    candidate = {"source": "STT2", "start": 1.0, "end": 2.0, "text": "STT2 후보"}
    confirmed_rows = [
        {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "first", "speaker": "00"},
        {
            "id": "caption_2",
            "start": 1.0,
            "end": 2.0,
            "text": "STT2 후보",
            "speaker": "01",
            "stt_selected_source": "STT2",
            "stt_candidates": [dict(candidate)],
        },
        {"id": "caption_3", "start": 2.0, "end": 3.0, "text": "third", "speaker": "02"},
    ]
    cases.append((
        "candidate_confirm",
        project,
        apply_candidate_confirm_dual_write_pilot(
            project,
            confirmed_rows=confirmed_rows,
            candidate=candidate,
            candidate_source="STT2",
            candidate_lanes=[candidate],
        ),
    ))

    project = _legacy_project()
    marker = {"timeline_sec": 1.5, "timeline_frame": 45, "fps": 30.0, "status": "provisional"}
    cases.append((
        "marker_edit",
        project,
        apply_marker_edit_dual_write_pilot(
            project,
            action="create",
            marker=marker,
            before_markers=[],
            after_markers=[marker],
            commit_source="provisional_cut_boundary_create",
        ),
    ))

    return [
        _operation_roundtrip_check(work_dir, operation_name, project, result)
        for operation_name, project, result in cases
    ]


def _canonical_load_owner_gate_matrix(
    *,
    checks: dict[str, Any],
    operation_roundtrip_all_passed: bool,
    render_export_parity_passed: bool,
    persistence_cutover_ready: bool,
) -> dict[str, Any]:
    top_level = checks.get("approved_top_level_nle_shadow") if isinstance(checks.get("approved_top_level_nle_shadow"), dict) else {}
    projection = (
        checks.get("top_level_nle_compatibility_projection")
        if isinstance(checks.get("top_level_nle_compatibility_projection"), dict)
        else {}
    )
    canonical_opt_in = (
        checks.get("top_level_nle_canonical_load_opt_in")
        if isinstance(checks.get("top_level_nle_canonical_load_opt_in"), dict)
        else {}
    )
    snapshot_canonical = (
        checks.get("nle_snapshot_canonical_load_source")
        if isinstance(checks.get("nle_snapshot_canonical_load_source"), dict)
        else {}
    )
    runtime_persistence = (
        checks.get("runtime_project_state_persistence_opt_in")
        if isinstance(checks.get("runtime_project_state_persistence_opt_in"), dict)
        else {}
    )
    legacy_shape_replacement = (
        checks.get("legacy_disk_shape_replacement_opt_in")
        if isinstance(checks.get("legacy_disk_shape_replacement_opt_in"), dict)
        else {}
    )
    final_cutover = (
        checks.get("final_cutover_ready")
        if isinstance(checks.get("final_cutover_ready"), dict)
        else {}
    )
    roughcut = checks.get("roughcut_sidecar_readback") if isinstance(checks.get("roughcut_sidecar_readback"), dict) else {}
    rollback = checks.get("canonical_load_owner_rollback_boundary") if isinstance(checks.get("canonical_load_owner_rollback_boundary"), dict) else {}
    gate_values = {
        "top_level_shadow_ready": bool(top_level.get("ready")),
        "compatibility_projection_ready": bool(projection.get("explicit_projection_uses_top_level_nle"))
        and bool(projection.get("default_load_uses_legacy_rows"))
        and bool(projection.get("gap_coverage_ready"))
        and bool(projection.get("shadow_override_visible_in_explicit_projection")),
        "legacy_default_load_still_canonical": str(projection.get("current_canonical_load_owner") or "")
        == "legacy_editor_state"
        and bool(projection.get("default_load_uses_legacy_rows"))
        and bool(projection.get("shadow_override_absent_from_default_load"))
        and bool(projection.get("resave_discarded_shadow_override"))
        and str(top_level.get("canonical_load_owner") or "") == "legacy_editor_state",
        "operation_roundtrip_ready": bool(operation_roundtrip_all_passed),
        "render_export_parity_ready": bool(render_export_parity_passed),
        "roughcut_sidecar_ready": bool(roughcut.get("render_export_stable"))
        and bool(roughcut.get("roughcut_sidecar_stable"))
        and bool(roughcut.get("corrupted_marker_drift_detected")),
        "rollback_boundary_defined": bool(rollback.get("ready")),
        "canonical_load_owner_change_allowed": bool(canonical_opt_in.get("ready"))
        and bool(canonical_opt_in.get("canonical_load_owner_change_allowed"))
        and bool(canonical_opt_in.get("legacy_editor_state_preserved_for_rollback")),
        "nle_snapshot_canonical_load_source_allowed": bool(snapshot_canonical.get("ready"))
        and bool(snapshot_canonical.get("explicit_opt_in"))
        and bool(snapshot_canonical.get("nle_snapshot_canonical_load_source_allowed"))
        and bool(snapshot_canonical.get("legacy_editor_state_preserved_for_rollback")),
        "runtime_project_state_persistence_allowed": bool(runtime_persistence.get("ready"))
        and bool(runtime_persistence.get("explicit_opt_in"))
        and bool(runtime_persistence.get("runtime_project_state_persistence_allowed"))
        and bool(runtime_persistence.get("default_project_authority_unchanged"))
        and bool(runtime_persistence.get("legacy_editor_state_preserved_for_rollback")),
        "legacy_disk_shape_replacement_allowed": bool(legacy_shape_replacement.get("ready"))
        and bool(legacy_shape_replacement.get("explicit_opt_in"))
        and bool(legacy_shape_replacement.get("legacy_disk_shape_replacement_allowed"))
        and bool(legacy_shape_replacement.get("legacy_editor_state_rows_replaced"))
        and bool(legacy_shape_replacement.get("legacy_editor_state_preserved_for_rollback"))
        and bool(legacy_shape_replacement.get("default_project_authority_unchanged"))
        and bool(legacy_shape_replacement.get("direct_srt_precedence_preserved"))
        and bool(legacy_shape_replacement.get("forged_policy_blocked")),
        "final_cutover_ready": bool(persistence_cutover_ready)
        and bool(final_cutover.get("ready"))
        and bool(final_cutover.get("explicit_opt_in"))
        and bool(final_cutover.get("final_cutover_ready"))
        and bool(final_cutover.get("default_project_authority_changed"))
        and not bool(final_cutover.get("default_project_authority_unchanged"))
        and bool(final_cutover.get("legacy_editor_state_compatibility_key_preserved"))
        and bool(final_cutover.get("editor_state_key_present"))
        and bool(final_cutover.get("editor_state_is_compatibility_projection"))
        and bool(final_cutover.get("cache_hit_runtime_state_hydrated"))
        and bool(final_cutover.get("cache_hit_storage_has_runtime_nle_key"))
        and bool(final_cutover.get("forged_policy_blocked"))
        and bool(final_cutover.get("direct_srt_precedence_preserved"))
        and not bool(final_cutover.get("storage_after_has_top_level_nle"))
        and not bool(final_cutover.get("storage_after_has_readback_report"))
        and not bool(final_cutover.get("storage_after_has_quarantine")),
    }
    gates = [
        {
            "id": gate_id,
            "status": "ready" if bool(gate_values[gate_id]) else "blocked",
            "ready": bool(gate_values[gate_id]),
        }
        for gate_id in CANONICAL_LOAD_OWNER_GATE_ORDER
    ]
    blocked_gate_ids = [row["id"] for row in gates if not row["ready"]]
    return {
        "status": "ready" if not blocked_gate_ids else "blocked",
        "overall_stoplight": "green" if not blocked_gate_ids else "red",
        "current_canonical_load_owner": str(
            snapshot_canonical.get("canonical_load_owner")
            or canonical_opt_in.get("canonical_load_owner")
            or projection.get("current_canonical_load_owner")
            or ""
        ),
        "target_load_owner_candidate": "nle_snapshot",
        "gate_order": list(CANONICAL_LOAD_OWNER_GATE_ORDER),
        "gates": gates,
        "ready_gate_count": len(gates) - len(blocked_gate_ids),
        "blocked_gate_count": len(blocked_gate_ids),
        "blocked_gate_ids": blocked_gate_ids,
        "not_runtime_change": not bool(gate_values["runtime_project_state_persistence_allowed"]),
        "not_disk_format_cutover": not bool(persistence_cutover_ready),
        "not_ui_change": True,
    }


def build_nle_persistence_cutover_report(*, output_dir: Path | None = None) -> dict[str, Any]:
    out_dir = Path(output_dir or ROOT / "output" / "manual_verification" / "latest" / "nle_persistence_cutover_audit")
    out_dir.mkdir(parents=True, exist_ok=True)
    runtime_roundtrip = _runtime_roundtrip_check(out_dir / "roundtrip_fixture")
    future_payload = _future_payload_quarantine_check()
    approved_snapshot = _approved_snapshot_persistence_check(out_dir / "approved_snapshot_fixture")
    top_level_nle_shadow = _approved_top_level_nle_shadow_check(out_dir / "approved_top_level_nle_fixture")
    top_level_nle_compatibility_projection = _top_level_nle_compatibility_projection_check(
        out_dir / "top_level_nle_compatibility_projection_fixture"
    )
    top_level_nle_canonical_load_opt_in = _top_level_nle_canonical_load_opt_in_check(
        out_dir / "top_level_nle_canonical_load_opt_in_fixture"
    )
    nle_snapshot_canonical_load_source = _nle_snapshot_canonical_load_source_check(
        out_dir / "nle_snapshot_canonical_load_source_fixture"
    )
    runtime_project_state_persistence_opt_in = _runtime_project_state_persistence_opt_in_check(
        out_dir / "runtime_project_state_persistence_opt_in_fixture"
    )
    legacy_disk_shape_replacement_opt_in = _legacy_disk_shape_replacement_opt_in_check(
        out_dir / "legacy_disk_shape_replacement_opt_in_fixture"
    )
    final_cutover_ready_check = _final_cutover_ready_check(
        out_dir / "final_cutover_ready_fixture"
    )
    canonical_load_owner_rollback_boundary = _canonical_load_owner_rollback_boundary_check(
        out_dir / "canonical_load_owner_rollback_boundary_fixture"
    )
    corrupted_snapshot = _corrupted_snapshot_readback_check(out_dir / "corrupted_snapshot_fixture")
    roughcut_sidecar = _roughcut_sidecar_readback_check(out_dir / "roughcut_sidecar_readback_fixture")
    operation_roundtrip_matrix = _operation_roundtrip_matrix(out_dir / "operation_roundtrip_matrix")
    render_export_parity = _render_export_parity_check(out_dir / "render_export_parity")
    operation_roundtrip_all_passed = all(
        bool(row.get("runtime_state_hydrated"))
        and bool(row.get("storage_clean"))
        and bool(row.get("reopened_matches_projected"))
        and bool(row.get("reopened_markers_preserved"))
        and int(row.get("invalid_duration_count") or 0) == 0
        and int(row.get("non_monotonic_count") or 0) == 0
        and int(row.get("overlap_count") or 0) == 0
        and int(row.get("max_active_segments") or 0) <= 1
        for row in operation_roundtrip_matrix
    )

    checks = {
        "runtime_roundtrip": runtime_roundtrip,
        "future_payload_quarantine": future_payload,
        "approved_snapshot_persistence": approved_snapshot,
        "approved_top_level_nle_shadow": top_level_nle_shadow,
        "top_level_nle_compatibility_projection": top_level_nle_compatibility_projection,
        "top_level_nle_canonical_load_opt_in": top_level_nle_canonical_load_opt_in,
        "nle_snapshot_canonical_load_source": nle_snapshot_canonical_load_source,
        "runtime_project_state_persistence_opt_in": runtime_project_state_persistence_opt_in,
        "legacy_disk_shape_replacement_opt_in": legacy_disk_shape_replacement_opt_in,
        "final_cutover_ready": final_cutover_ready_check,
        "canonical_load_owner_rollback_boundary": canonical_load_owner_rollback_boundary,
        "corrupted_snapshot_readback": corrupted_snapshot,
        "roughcut_sidecar_readback": roughcut_sidecar,
        "operation_roundtrip_matrix": operation_roundtrip_matrix,
        "render_export_parity": render_export_parity,
    }
    prep_ready = (
        runtime_roundtrip["loaded_runtime_state"]
        and runtime_roundtrip["storage_clean"]
        and future_payload["quarantine_recorded"]
        and not future_payload["remaining_unapproved_fields"]
        and approved_snapshot["ready"]
        and top_level_nle_shadow["ready"]
        and top_level_nle_compatibility_projection["explicit_projection_uses_top_level_nle"]
        and top_level_nle_compatibility_projection["default_load_uses_legacy_rows"]
        and top_level_nle_compatibility_projection["explicit_projection_differs_from_default"]
        and top_level_nle_compatibility_projection["gap_coverage_ready"]
        and top_level_nle_compatibility_projection["shadow_override_visible_in_explicit_projection"]
        and top_level_nle_compatibility_projection["shadow_override_absent_from_default_load"]
        and top_level_nle_compatibility_projection["resave_discarded_shadow_override"]
        and top_level_nle_compatibility_projection["runtime_state_hydrated_from_legacy"]
        and top_level_nle_canonical_load_opt_in["ready"]
        and top_level_nle_canonical_load_opt_in["legacy_editor_state_preserved_for_rollback"]
        and not top_level_nle_canonical_load_opt_in["storage_after_has_runtime_nle_key"]
        and not top_level_nle_canonical_load_opt_in["storage_after_has_readback_report"]
        and not top_level_nle_canonical_load_opt_in["storage_after_has_quarantine"]
        and nle_snapshot_canonical_load_source["ready"]
        and nle_snapshot_canonical_load_source["legacy_editor_state_preserved_for_rollback"]
        and not nle_snapshot_canonical_load_source["storage_after_has_top_level_nle"]
        and not nle_snapshot_canonical_load_source["storage_after_has_runtime_nle_key"]
        and not nle_snapshot_canonical_load_source["storage_after_has_readback_report"]
        and not nle_snapshot_canonical_load_source["storage_after_has_quarantine"]
        and runtime_project_state_persistence_opt_in["ready"]
        and runtime_project_state_persistence_opt_in["legacy_editor_state_preserved_for_rollback"]
        and runtime_project_state_persistence_opt_in["default_project_authority_unchanged"]
        and runtime_project_state_persistence_opt_in["storage_after_has_runtime_nle_key"]
        and runtime_project_state_persistence_opt_in["cache_hit_runtime_state_hydrated"]
        and runtime_project_state_persistence_opt_in["cache_hit_storage_has_runtime_nle_key"]
        and not runtime_project_state_persistence_opt_in["storage_after_has_top_level_nle"]
        and not runtime_project_state_persistence_opt_in["storage_after_has_readback_report"]
        and not runtime_project_state_persistence_opt_in["storage_after_has_quarantine"]
        and not runtime_project_state_persistence_opt_in["legacy_disk_shape_replacement_allowed"]
        and not runtime_project_state_persistence_opt_in["final_cutover_ready"]
        and legacy_disk_shape_replacement_opt_in["ready"]
        and legacy_disk_shape_replacement_opt_in["legacy_editor_state_rows_replaced"]
        and legacy_disk_shape_replacement_opt_in["legacy_editor_state_preserved_for_rollback"]
        and legacy_disk_shape_replacement_opt_in["default_project_authority_unchanged"]
        and legacy_disk_shape_replacement_opt_in["legacy_editor_state_matches_snapshot"]
        and legacy_disk_shape_replacement_opt_in["cache_hit_runtime_state_hydrated"]
        and legacy_disk_shape_replacement_opt_in["cache_hit_storage_has_runtime_nle_key"]
        and legacy_disk_shape_replacement_opt_in["forged_policy_blocked"]
        and legacy_disk_shape_replacement_opt_in["direct_srt_precedence_preserved"]
        and not legacy_disk_shape_replacement_opt_in["storage_after_has_top_level_nle"]
        and not legacy_disk_shape_replacement_opt_in["storage_after_has_readback_report"]
        and not legacy_disk_shape_replacement_opt_in["storage_after_has_quarantine"]
        and not legacy_disk_shape_replacement_opt_in["final_cutover_ready"]
        and final_cutover_ready_check["ready"]
        and final_cutover_ready_check["default_project_authority_changed"]
        and not final_cutover_ready_check["default_project_authority_unchanged"]
        and final_cutover_ready_check["legacy_editor_state_compatibility_key_preserved"]
        and final_cutover_ready_check["legacy_editor_state_rows_replaced"]
        and final_cutover_ready_check["legacy_editor_state_matches_snapshot"]
        and final_cutover_ready_check["editor_state_key_present"]
        and final_cutover_ready_check["editor_state_is_compatibility_projection"]
        and final_cutover_ready_check["storage_after_has_runtime_nle_key"]
        and final_cutover_ready_check["cache_hit_runtime_state_hydrated"]
        and final_cutover_ready_check["cache_hit_storage_has_runtime_nle_key"]
        and final_cutover_ready_check["forged_policy_blocked"]
        and final_cutover_ready_check["direct_srt_precedence_preserved"]
        and not final_cutover_ready_check["storage_after_has_top_level_nle"]
        and not final_cutover_ready_check["storage_after_has_readback_report"]
        and not final_cutover_ready_check["storage_after_has_quarantine"]
        and canonical_load_owner_rollback_boundary["ready"]
        and not top_level_nle_compatibility_projection["runtime_report_persisted_after_resave"]
        and not top_level_nle_compatibility_projection["runtime_state_persisted_after_resave"]
        and not top_level_nle_compatibility_projection["quarantine_persisted_after_resave"]
        and not top_level_nle_shadow["runtime_report_persisted"]
        and not top_level_nle_shadow["runtime_state_persisted"]
        and not top_level_nle_shadow["quarantine_persisted"]
        and corrupted_snapshot["drift_detected"]
        and corrupted_snapshot["legacy_rows_stable"]
        and not corrupted_snapshot["runtime_report_persisted"]
        and roughcut_sidecar["approved_readback_stable"]
        and roughcut_sidecar["corrupted_marker_drift_detected"]
        and roughcut_sidecar["render_export_stable"]
        and roughcut_sidecar["roughcut_sidecar_stable"]
        and not roughcut_sidecar["runtime_report_persisted"]
        and not roughcut_sidecar["runtime_state_persisted"]
        and not roughcut_sidecar["top_level_nle_persisted"]
        and not roughcut_sidecar["quarantine_persisted"]
        and operation_roundtrip_all_passed
        and render_export_parity["stable"]
        and render_export_parity["storage_clean"]
    )
    blockers = []
    if not final_cutover_ready_check["ready"]:
        blockers.append("final_cutover_ready")
    if not top_level_nle_compatibility_projection["gap_coverage_ready"]:
        blockers.append(CUTOVER_GAP_COVERAGE_BLOCKER)
    if not prep_ready:
        blockers.append("cutover_prep_incomplete")
    persistence_cutover_ready = bool(prep_ready and not blockers)
    canonical_load_owner_gate_matrix = _canonical_load_owner_gate_matrix(
        checks=checks,
        operation_roundtrip_all_passed=operation_roundtrip_all_passed,
        render_export_parity_passed=bool(render_export_parity["stable"]),
        persistence_cutover_ready=persistence_cutover_ready,
    )

    return {
        "schema": SCHEMA,
        "app_version": APP_VERSION,
        "status": "ready" if persistence_cutover_ready else "blocked",
        "prep_ready": prep_ready,
        "persistence_cutover_ready": persistence_cutover_ready,
        "blockers": blockers,
        "canonical_load_owner_gate_matrix": canonical_load_owner_gate_matrix,
        "checks": checks,
        "operation_roundtrip_all_passed": operation_roundtrip_all_passed,
        "operation_roundtrip_family_count": len(operation_roundtrip_matrix),
        "render_export_parity_passed": bool(render_export_parity["stable"]),
        "top_level_nle_shadow_ready": bool(top_level_nle_shadow["ready"]),
        "top_level_nle_compatibility_projection_passed": bool(
            top_level_nle_compatibility_projection["explicit_projection_uses_top_level_nle"]
            and top_level_nle_compatibility_projection["default_load_uses_legacy_rows"]
            and top_level_nle_compatibility_projection["explicit_projection_differs_from_default"]
            and top_level_nle_compatibility_projection["gap_coverage_ready"]
            and top_level_nle_compatibility_projection["shadow_override_visible_in_explicit_projection"]
            and top_level_nle_compatibility_projection["shadow_override_absent_from_default_load"]
            and top_level_nle_compatibility_projection["resave_discarded_shadow_override"]
        ),
        "top_level_nle_canonical_projection_complete": bool(top_level_nle_canonical_load_opt_in["ready"]),
        "top_level_nle_canonical_load_opt_in_ready": bool(top_level_nle_canonical_load_opt_in["ready"]),
        "nle_snapshot_canonical_load_source_ready": bool(nle_snapshot_canonical_load_source["ready"]),
        "runtime_project_state_persistence_opt_in_ready": bool(runtime_project_state_persistence_opt_in["ready"]),
        "legacy_disk_shape_replacement_opt_in_ready": bool(legacy_disk_shape_replacement_opt_in["ready"]),
        "final_cutover_ready": bool(final_cutover_ready_check["ready"]),
        "remaining_full_cutover_gates": [] if persistence_cutover_ready else list(blockers),
        "next_safe_steps": [
            "run the full source-app QA suite before any release claim",
            "keep editor_state as a compatibility projection key until explicit removal approval exists",
            "keep App Store packaging, signing, upload, and metadata proof separate from this source-app persistence audit",
        ],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _markdown_report(payload: dict[str, Any]) -> str:
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    runtime = checks.get("runtime_roundtrip") if isinstance(checks.get("runtime_roundtrip"), dict) else {}
    future = checks.get("future_payload_quarantine") if isinstance(checks.get("future_payload_quarantine"), dict) else {}
    approved = checks.get("approved_snapshot_persistence") if isinstance(checks.get("approved_snapshot_persistence"), dict) else {}
    top_level = checks.get("approved_top_level_nle_shadow") if isinstance(checks.get("approved_top_level_nle_shadow"), dict) else {}
    top_level_projection = (
        checks.get("top_level_nle_compatibility_projection")
        if isinstance(checks.get("top_level_nle_compatibility_projection"), dict)
        else {}
    )
    canonical_opt_in = (
        checks.get("top_level_nle_canonical_load_opt_in")
        if isinstance(checks.get("top_level_nle_canonical_load_opt_in"), dict)
        else {}
    )
    snapshot_canonical = (
        checks.get("nle_snapshot_canonical_load_source")
        if isinstance(checks.get("nle_snapshot_canonical_load_source"), dict)
        else {}
    )
    runtime_persistence = (
        checks.get("runtime_project_state_persistence_opt_in")
        if isinstance(checks.get("runtime_project_state_persistence_opt_in"), dict)
        else {}
    )
    legacy_shape_replacement = (
        checks.get("legacy_disk_shape_replacement_opt_in")
        if isinstance(checks.get("legacy_disk_shape_replacement_opt_in"), dict)
        else {}
    )
    final_cutover = (
        checks.get("final_cutover_ready")
        if isinstance(checks.get("final_cutover_ready"), dict)
        else {}
    )
    rollback = (
        checks.get("canonical_load_owner_rollback_boundary")
        if isinstance(checks.get("canonical_load_owner_rollback_boundary"), dict)
        else {}
    )
    corrupted = checks.get("corrupted_snapshot_readback") if isinstance(checks.get("corrupted_snapshot_readback"), dict) else {}
    roughcut = checks.get("roughcut_sidecar_readback") if isinstance(checks.get("roughcut_sidecar_readback"), dict) else {}
    operations = checks.get("operation_roundtrip_matrix") if isinstance(checks.get("operation_roundtrip_matrix"), list) else []
    render_export = checks.get("render_export_parity") if isinstance(checks.get("render_export_parity"), dict) else {}
    render_surfaces = (
        render_export.get("surface_reports") if isinstance(render_export.get("surface_reports"), list) else []
    )
    lines = [
        "# NLE Persistence Cutover Audit",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- App version: `{payload.get('app_version')}`",
        f"- Prep ready: `{bool(payload.get('prep_ready'))}`",
        f"- Persistence cutover allowed: `{bool(payload.get('persistence_cutover_ready'))}`",
        f"- Operation roundtrip families: `{payload.get('operation_roundtrip_family_count')}`",
        f"- Operation roundtrip all passed: `{bool(payload.get('operation_roundtrip_all_passed'))}`",
        "",
        "## Runtime Roundtrip",
        "",
        f"- Runtime NLE state hydrated: `{bool(runtime.get('loaded_runtime_state'))}`",
        f"- Runtime caption count: `{runtime.get('runtime_caption_count')}`",
        f"- Disk storage clean of NLE runtime fields: `{bool(runtime.get('storage_clean'))}`",
        f"- Storage schema: `{runtime.get('storage_schema')}`",
        "",
        "## Approved Snapshot Persistence",
        "",
        f"- Ready: `{bool(approved.get('ready'))}`",
        f"- Snapshot persisted: `{bool(approved.get('snapshot_persisted'))}`",
        f"- Approval: `{approved.get('approval')}`",
        f"- Legacy rows stable: `{bool(approved.get('legacy_rows_stable'))}`",
        f"- Read-back parity stable: `{bool(approved.get('readback_parity_stable'))}`",
        f"- Read-back mismatch count: `{approved.get('readback_mismatch_count')}`",
        f"- Runtime NLE state hydrated: `{bool(approved.get('loaded_runtime_state'))}`",
        f"- Storage has NLE snapshot: `{bool(approved.get('storage_has_nle_snapshot'))}`",
        f"- Storage has top-level NLE/runtime/quarantine: `{bool(approved.get('storage_has_nle'))}/{bool(approved.get('storage_has_runtime_nle_key'))}/{bool(approved.get('storage_has_quarantine'))}`",
        "",
        "## Top-Level NLE Shadow",
        "",
        f"- Ready: `{bool(top_level.get('ready'))}`",
        f"- Storage has top-level NLE: `{bool(top_level.get('storage_has_nle'))}`",
        f"- Storage has NLE snapshot: `{bool(top_level.get('storage_has_nle_snapshot'))}`",
        f"- Schema: `{top_level.get('shadow_schema')}`",
        f"- Role: `{top_level.get('shadow_role')}`",
        f"- Canonical load owner: `{top_level.get('canonical_load_owner')}`",
        f"- Caption/gap count: `{top_level.get('caption_count')}` / `{top_level.get('gap_count')}`",
        f"- Runtime project state persisted: `{bool(top_level.get('runtime_project_state_persisted'))}`",
        f"- Legacy rows stable: `{bool(top_level.get('legacy_rows_stable'))}`",
        f"- Read-back parity stable: `{bool(top_level.get('readback_parity_stable'))}`",
        f"- Runtime report/state/quarantine persisted: `{bool(top_level.get('runtime_report_persisted'))}/{bool(top_level.get('runtime_state_persisted'))}/{bool(top_level.get('quarantine_persisted'))}`",
        "",
        "## Top-Level NLE Compatibility Projection",
        "",
        "Compatibility audit evidence only. Non-opt-in default project load still rebuilds from legacy editor_state rows; approved shadow nle/nle_snapshot data remains compatibility metadata unless the explicit canonical opt-in policy is present.",
        "",
        f"- Status: `{top_level_projection.get('status')}`",
        f"- Not runtime change: `{bool(top_level_projection.get('not_runtime_change'))}`",
        f"- Current canonical load owner: `{top_level_projection.get('current_canonical_load_owner')}`",
        f"- Default load source: `{top_level_projection.get('default_load_source')}`",
        f"- Explicit projection source: `{top_level_projection.get('explicit_projection_source')}`",
        f"- Explicit projection uses top-level NLE: `{bool(top_level_projection.get('explicit_projection_uses_top_level_nle'))}`",
        f"- Default load uses legacy rows: `{bool(top_level_projection.get('default_load_uses_legacy_rows'))}`",
        f"- Explicit projection differs from default legacy captions: `{bool(top_level_projection.get('explicit_projection_differs_from_default'))}`",
        f"- Explicit projection row count: `{top_level_projection.get('explicit_projection_row_count')}`",
        f"- Explicit projection caption/gap count: `{top_level_projection.get('explicit_projection_caption_count')}` / `{top_level_projection.get('explicit_projection_gap_count')}`",
        f"- Default row/caption/gap count: `{top_level_projection.get('default_row_count')}` / `{top_level_projection.get('default_caption_count')}` / `{top_level_projection.get('default_gap_count')}`",
        f"- Shadow override caption text: `{top_level_projection.get('shadow_override_caption_text')}`",
        f"- Explicit/default/resave first caption text: `{top_level_projection.get('explicit_first_caption_text')}` / `{top_level_projection.get('default_first_caption_text')}` / `{top_level_projection.get('resave_first_caption_text')}`",
        f"- Shadow override visible in explicit projection: `{bool(top_level_projection.get('shadow_override_visible_in_explicit_projection'))}`",
        f"- Shadow override absent from default load: `{bool(top_level_projection.get('shadow_override_absent_from_default_load'))}`",
        f"- Resave discarded shadow override: `{bool(top_level_projection.get('resave_discarded_shadow_override'))}`",
        f"- Gap coverage ready: `{bool(top_level_projection.get('gap_coverage_ready'))}`",
        f"- Canonical load owner change allowed: `{bool(top_level_projection.get('canonical_load_owner_change_allowed'))}`",
        f"- Disk format cutover allowed: `{bool(top_level_projection.get('disk_format_cutover_allowed'))}`",
        f"- Resave rebuilt shadow from legacy rows: `{bool(top_level_projection.get('resave_rebuilt_shadow_from_legacy'))}`",
        "",
        "## Top-Level NLE Canonical Load Opt-In",
        "",
        "Explicit owner-approved opt-in evidence only. This proves top-level nle can be the project load source when nle and nle_snapshot agree, while legacy editor_state remains on disk as rollback compatibility. This top-level fixture does not by itself approve standalone nle_snapshot sourcing, runtime-state persistence, legacy disk-shape replacement, final cutover, or UI/UX change.",
        "",
        f"- Ready: `{bool(canonical_opt_in.get('ready'))}`",
        f"- Status: `{canonical_opt_in.get('status')}`",
        f"- Role: `{canonical_opt_in.get('role')}`",
        f"- Canonical load owner: `{canonical_opt_in.get('canonical_load_owner')}`",
        f"- Canonical load owner change allowed: `{bool(canonical_opt_in.get('canonical_load_owner_change_allowed'))}`",
        f"- Loaded/runtime/reloaded first caption text: `{canonical_opt_in.get('loaded_first_caption_text')}` / `{canonical_opt_in.get('runtime_first_caption_text')}` / `{canonical_opt_in.get('reloaded_first_caption_text')}`",
        f"- Storage nle/snapshot first caption text: `{canonical_opt_in.get('storage_nle_first_caption_text')}` / `{canonical_opt_in.get('storage_snapshot_first_caption_text')}`",
        f"- Legacy editor_state first caption text after resave: `{canonical_opt_in.get('legacy_editor_state_first_caption_text_after_resave')}`",
        f"- Loaded signature matches runtime/reloaded: `{bool(canonical_opt_in.get('loaded_signature_matches_runtime'))}` / `{bool(canonical_opt_in.get('loaded_signature_matches_reloaded'))}`",
        f"- Storage nle matches snapshot: `{bool(canonical_opt_in.get('storage_nle_matches_snapshot'))}`",
        f"- Legacy editor_state preserved for rollback: `{bool(canonical_opt_in.get('legacy_editor_state_preserved_for_rollback'))}`",
        f"- Storage after has runtime/readback/quarantine: `{bool(canonical_opt_in.get('storage_after_has_runtime_nle_key'))}/{bool(canonical_opt_in.get('storage_after_has_readback_report'))}/{bool(canonical_opt_in.get('storage_after_has_quarantine'))}`",
        f"- Remaining blocked gates: `{', '.join(canonical_opt_in.get('blocked_gates_remaining') or [])}`",
        "",
        "## NLE Snapshot Standalone Canonical Load Opt-In",
        "",
        "Explicit owner-approved opt-in evidence only. This proves standalone nle_snapshot load-source routing for this approved payload while default and failed paths remain legacy editor_state. This snapshot-only fixture does not persist runtime state, replace legacy editor_state, declare final cutover, or change UI/UX.",
        "",
        f"- Ready: `{bool(snapshot_canonical.get('ready'))}`",
        f"- Status: `{snapshot_canonical.get('status')}`",
        f"- Explicit opt-in: `{bool(snapshot_canonical.get('explicit_opt_in'))}`",
        f"- Canonical load owner: `{snapshot_canonical.get('canonical_load_owner')}`",
        f"- Canonical load owner change allowed: `{bool(snapshot_canonical.get('canonical_load_owner_change_allowed'))}`",
        f"- Snapshot load source allowed: `{bool(snapshot_canonical.get('nle_snapshot_canonical_load_source_allowed'))}`",
        f"- Loaded/runtime/reloaded first caption text: `{snapshot_canonical.get('loaded_first_caption_text')}` / `{snapshot_canonical.get('runtime_first_caption_text')}` / `{snapshot_canonical.get('reloaded_first_caption_text')}`",
        f"- Storage snapshot first caption text: `{snapshot_canonical.get('storage_snapshot_first_caption_text')}`",
        f"- Legacy editor_state first caption text after resave: `{snapshot_canonical.get('legacy_editor_state_first_caption_text_after_resave')}`",
        f"- Loaded signature matches runtime/reloaded: `{bool(snapshot_canonical.get('loaded_signature_matches_runtime'))}` / `{bool(snapshot_canonical.get('loaded_signature_matches_reloaded'))}`",
        f"- Storage snapshot matches loaded: `{bool(snapshot_canonical.get('storage_snapshot_matches_loaded'))}`",
        f"- Legacy editor_state preserved for rollback: `{bool(snapshot_canonical.get('legacy_editor_state_preserved_for_rollback'))}`",
        f"- Storage after has top-level/runtime/readback/quarantine: `{bool(snapshot_canonical.get('storage_after_has_top_level_nle'))}/{bool(snapshot_canonical.get('storage_after_has_runtime_nle_key'))}/{bool(snapshot_canonical.get('storage_after_has_readback_report'))}/{bool(snapshot_canonical.get('storage_after_has_quarantine'))}`",
        f"- Remaining blocked gates: `{', '.join(snapshot_canonical.get('blocked_gates_remaining') or [])}`",
        "",
        "## Runtime NLE Project State Persistence Opt-In",
        "",
        "Explicit owner-approved opt-in evidence only. This proves `_nle_project_state` can persist as a supplemental runtime-state payload when tied to the standalone `nle_snapshot` canonical load-source policy. Default project load/save/export authority remains unchanged; this does not replace legacy `editor_state`, alter Direct SRT precedence, change roughcut sidecars, declare final disk-format cutover, or change UI/UX.",
        "",
        f"- Ready: `{bool(runtime_persistence.get('ready'))}`",
        f"- Status: `{runtime_persistence.get('status')}`",
        f"- Explicit opt-in: `{bool(runtime_persistence.get('explicit_opt_in'))}`",
        f"- Runtime persistence allowed: `{bool(runtime_persistence.get('runtime_project_state_persistence_allowed'))}`",
        f"- Default project authority unchanged: `{bool(runtime_persistence.get('default_project_authority_unchanged'))}`",
        f"- Legacy disk-shape replacement allowed: `{bool(runtime_persistence.get('legacy_disk_shape_replacement_allowed'))}`",
        f"- Final disk-format cutover allowed: `{bool(runtime_persistence.get('final_cutover_ready'))}`",
        f"- Runtime payload schema: `{runtime_persistence.get('runtime_payload_schema')}`",
        f"- Loaded/runtime/reloaded first caption text: `{runtime_persistence.get('loaded_first_caption_text')}` / `{runtime_persistence.get('runtime_first_caption_text')}` / `{runtime_persistence.get('reloaded_first_caption_text')}`",
        f"- Storage snapshot/runtime first caption text: `{runtime_persistence.get('storage_snapshot_first_caption_text')}` / `{runtime_persistence.get('storage_runtime_first_caption_text')}`",
        f"- Legacy editor_state first caption text after resave: `{runtime_persistence.get('legacy_editor_state_first_caption_text_after_resave')}`",
        f"- Loaded signature matches runtime/reloaded: `{bool(runtime_persistence.get('loaded_signature_matches_runtime'))}` / `{bool(runtime_persistence.get('loaded_signature_matches_reloaded'))}`",
        f"- Storage runtime matches snapshot: `{bool(runtime_persistence.get('storage_runtime_matches_snapshot'))}`",
        f"- Cache-hit runtime/storage ready: `{bool(runtime_persistence.get('cache_hit_runtime_state_hydrated'))}` / `{bool(runtime_persistence.get('cache_hit_storage_has_runtime_nle_key'))}`",
        f"- Legacy editor_state preserved for rollback: `{bool(runtime_persistence.get('legacy_editor_state_preserved_for_rollback'))}`",
        f"- Storage after has top-level/runtime/readback/quarantine: `{bool(runtime_persistence.get('storage_after_has_top_level_nle'))}/{bool(runtime_persistence.get('storage_after_has_runtime_nle_key'))}/{bool(runtime_persistence.get('storage_after_has_readback_report'))}/{bool(runtime_persistence.get('storage_after_has_quarantine'))}`",
        f"- Remaining blocked gates: `{', '.join(runtime_persistence.get('blocked_gates_remaining') or [])}`",
        "",
        "## Legacy Disk Shape Replacement Opt-In",
        "",
        "Explicit owner-approved opt-in evidence only. This proves legacy-compatible `editor_state` rows can be regenerated from the approved standalone `nle_snapshot` canonical source while the `editor_state` key remains present for compatibility. Direct SRT precedence and roughcut sidecars stay separate proof surfaces, and this legacy-only fixture keeps final policy disabled.",
        "",
        f"- Ready: `{bool(legacy_shape_replacement.get('ready'))}`",
        f"- Status: `{legacy_shape_replacement.get('status')}`",
        f"- Explicit opt-in: `{bool(legacy_shape_replacement.get('explicit_opt_in'))}`",
        f"- Replacement allowed: `{bool(legacy_shape_replacement.get('legacy_disk_shape_replacement_allowed'))}`",
        f"- Replacement schema: `{legacy_shape_replacement.get('legacy_disk_shape_replacement_schema')}`",
        f"- Editor rows replaced: `{bool(legacy_shape_replacement.get('legacy_editor_state_rows_replaced'))}`",
        f"- Legacy editor_state preserved for rollback: `{bool(legacy_shape_replacement.get('legacy_editor_state_preserved_for_rollback'))}`",
        f"- Default project authority unchanged: `{bool(legacy_shape_replacement.get('default_project_authority_unchanged'))}`",
        f"- Final disk-format cutover allowed: `{bool(legacy_shape_replacement.get('final_cutover_ready'))}`",
        f"- Loaded/runtime/reloaded first caption text: `{legacy_shape_replacement.get('loaded_first_caption_text')}` / `{legacy_shape_replacement.get('runtime_first_caption_text')}` / `{legacy_shape_replacement.get('reloaded_first_caption_text')}`",
        f"- Storage snapshot/runtime/editor_state first caption text: `{legacy_shape_replacement.get('storage_snapshot_first_caption_text')}` / `{legacy_shape_replacement.get('storage_runtime_first_caption_text')}` / `{legacy_shape_replacement.get('legacy_editor_state_first_caption_text_after_resave')}`",
        f"- Editor state matches snapshot: `{bool(legacy_shape_replacement.get('legacy_editor_state_matches_snapshot'))}`",
        f"- Storage runtime matches snapshot: `{bool(legacy_shape_replacement.get('storage_runtime_matches_snapshot'))}`",
        f"- Cache-hit runtime/storage ready: `{bool(legacy_shape_replacement.get('cache_hit_runtime_state_hydrated'))}` / `{bool(legacy_shape_replacement.get('cache_hit_storage_has_runtime_nle_key'))}`",
        f"- Forged policy blocked: `{bool(legacy_shape_replacement.get('forged_policy_blocked'))}`",
        f"- Direct SRT precedence preserved: `{bool(legacy_shape_replacement.get('direct_srt_precedence_preserved'))}`",
        f"- Storage after has top-level/runtime/readback/quarantine: `{bool(legacy_shape_replacement.get('storage_after_has_top_level_nle'))}/{bool(legacy_shape_replacement.get('storage_after_has_runtime_nle_key'))}/{bool(legacy_shape_replacement.get('storage_after_has_readback_report'))}/{bool(legacy_shape_replacement.get('storage_after_has_quarantine'))}`",
        f"- Remaining blocked gates: `{', '.join(legacy_shape_replacement.get('blocked_gates_remaining') or [])}`",
        "",
        "## Final Cutover Ready Opt-In",
        "",
        "Explicit owner-approved source-app project persistence load-owner proof only. This declares `nle_snapshot` authority for the approved payload while retaining the `editor_state` compatibility key; compatibility key retained does not mean dual canonical ownership. It is not UI/UX, STT, package signing, upload, or App Store submission proof.",
        "",
        f"- Ready: `{bool(final_cutover.get('ready'))}`",
        f"- Status: `{final_cutover.get('status')}`",
        f"- Explicit opt-in: `{bool(final_cutover.get('explicit_opt_in'))}`",
        f"- Final schema: `{final_cutover.get('final_cutover_schema')}`",
        f"- Final policy allowed: `{bool(final_cutover.get('final_cutover_ready'))}`",
        f"- Canonical load owner: `{final_cutover.get('canonical_load_owner')}`",
        f"- Default project authority: `{final_cutover.get('default_project_authority')}`",
        f"- Default authority changed/unchanged: `{bool(final_cutover.get('default_project_authority_changed'))}` / `{bool(final_cutover.get('default_project_authority_unchanged'))}`",
        f"- Compatibility editor_state key preserved: `{bool(final_cutover.get('legacy_editor_state_compatibility_key_preserved'))}`",
        f"- Editor state key present/compatibility projection: `{bool(final_cutover.get('editor_state_key_present'))}` / `{bool(final_cutover.get('editor_state_is_compatibility_projection'))}`",
        f"- Loaded/runtime/reloaded first caption text: `{final_cutover.get('loaded_first_caption_text')}` / `{final_cutover.get('runtime_first_caption_text')}` / `{final_cutover.get('reloaded_first_caption_text')}`",
        f"- Storage snapshot/runtime/editor_state first caption text: `{final_cutover.get('storage_snapshot_first_caption_text')}` / `{final_cutover.get('storage_runtime_first_caption_text')}` / `{final_cutover.get('legacy_editor_state_first_caption_text_after_resave')}`",
        f"- Editor state matches snapshot: `{bool(final_cutover.get('legacy_editor_state_matches_snapshot'))}`",
        f"- Storage runtime matches snapshot: `{bool(final_cutover.get('storage_runtime_matches_snapshot'))}`",
        f"- Cache-hit runtime/storage ready: `{bool(final_cutover.get('cache_hit_runtime_state_hydrated'))}` / `{bool(final_cutover.get('cache_hit_storage_has_runtime_nle_key'))}`",
        f"- Forged policy blocked: `{bool(final_cutover.get('forged_policy_blocked'))}`",
        f"- Direct SRT precedence preserved: `{bool(final_cutover.get('direct_srt_precedence_preserved'))}`",
        f"- Storage after has top-level/runtime/readback/quarantine: `{bool(final_cutover.get('storage_after_has_top_level_nle'))}/{bool(final_cutover.get('storage_after_has_runtime_nle_key'))}/{bool(final_cutover.get('storage_after_has_readback_report'))}/{bool(final_cutover.get('storage_after_has_quarantine'))}`",
        f"- Remaining blocked gates: `{', '.join(final_cutover.get('blocked_gates_remaining') or [])}`",
        "",
        "## Canonical Load-Owner Rollback Boundary",
        "",
        "Rollback-boundary audit evidence only. A future candidate payload that claims canonical NLE ownership is quarantined back to legacy editor_state rows before any default load or resave can adopt it.",
        "",
        f"- Ready: `{bool(rollback.get('ready'))}`",
        f"- Status: `{rollback.get('status')}`",
        f"- Rollback target: `{rollback.get('rollback_target')}`",
        f"- Candidate load owner: `{rollback.get('candidate_load_owner')}`",
        f"- Candidate shadow text: `{rollback.get('candidate_shadow_text')}`",
        f"- Loaded first caption text: `{rollback.get('loaded_first_caption_text')}`",
        f"- Resave first caption text: `{rollback.get('resave_first_caption_text')}`",
        f"- Candidate shadow text leaked to default load: `{bool(rollback.get('candidate_shadow_text_leaked_to_default_load'))}`",
        f"- Candidate shadow text leaked after resave: `{bool(rollback.get('candidate_shadow_text_leaked_after_resave'))}`",
        f"- Quarantine recorded: `{bool(rollback.get('quarantine_recorded'))}`",
        f"- Stripped keys: `{', '.join(rollback.get('stripped_keys') or [])}`",
        f"- Default load preserved legacy rows: `{bool(rollback.get('default_load_preserved_legacy_rows'))}`",
        f"- Storage after clean: `{bool(rollback.get('storage_after_clean'))}`",
        f"- Storage after NLE canonical load owner: `{rollback.get('storage_after_nle_canonical_load_owner')}`",
        f"- Storage after has NLE/snapshot/runtime/quarantine: `{bool(rollback.get('storage_after_has_nle'))}/{bool(rollback.get('storage_after_has_nle_snapshot'))}/{bool(rollback.get('storage_after_has_runtime_nle_key'))}/{bool(rollback.get('storage_after_has_quarantine'))}`",
        "",
        "## Canonical Load-Owner Gate Matrix",
        "",
        "This matrix is a source-app persistence preflight only. It proves explicit top-level nle, standalone nle_snapshot load-source, supplemental runtime-state persistence, legacy-compatible editor_state projection, and final policy opt-ins, but does not change UI/UX or prove App Store readiness.",
        "",
    ]
    gate_matrix = payload.get("canonical_load_owner_gate_matrix") if isinstance(payload.get("canonical_load_owner_gate_matrix"), dict) else {}
    lines.extend([
        f"- Status: `{gate_matrix.get('status')}`",
        f"- Overall stoplight: `{gate_matrix.get('overall_stoplight')}`",
        f"- Current canonical load owner: `{gate_matrix.get('current_canonical_load_owner')}`",
        f"- Target load-owner candidate: `{gate_matrix.get('target_load_owner_candidate')}`",
        f"- Ready/blocked gates: `{gate_matrix.get('ready_gate_count')}` / `{gate_matrix.get('blocked_gate_count')}`",
        f"- Not runtime change: `{bool(gate_matrix.get('not_runtime_change'))}`",
        f"- Not disk-format cutover: `{bool(gate_matrix.get('not_disk_format_cutover'))}`",
        f"- Not UI change: `{bool(gate_matrix.get('not_ui_change'))}`",
        "",
        "| Gate | Status |",
        "| --- | --- |",
    ])
    for gate in gate_matrix.get("gates") or []:
        if not isinstance(gate, dict):
            continue
        lines.append(f"| {gate.get('id')} | {gate.get('status')} |")
    lines.extend([
        "",
        "## Corrupted Snapshot Readback",
        "",
        f"- Drift detected: `{bool(corrupted.get('drift_detected'))}`",
        f"- Mismatch count: `{corrupted.get('mismatch_count')}`",
        f"- Legacy rows stable: `{bool(corrupted.get('legacy_rows_stable'))}`",
        f"- Runtime report persisted: `{bool(corrupted.get('runtime_report_persisted'))}`",
        "",
        "## Roughcut Sidecar Readback",
        "",
        f"- Approved read-back stable: `{bool(roughcut.get('approved_readback_stable'))}`",
        f"- Corrupted marker drift detected: `{bool(roughcut.get('corrupted_marker_drift_detected'))}`",
        f"- Mismatch count: `{roughcut.get('mismatch_count')}`",
        f"- Render/export stable after corrupted snapshot read: `{bool(roughcut.get('render_export_stable'))}`",
        f"- Roughcut sidecar stable after corrupted snapshot read: `{bool(roughcut.get('roughcut_sidecar_stable'))}`",
        f"- Sidecar stitched/markers: `{roughcut.get('sidecar_stitched_boundary_count')}/{roughcut.get('roughcut_marker_count')}`",
        f"- Runtime report persisted: `{bool(roughcut.get('runtime_report_persisted'))}`",
        "",
        "## Render / Export Parity",
        "",
        f"- Stable: `{bool(render_export.get('stable'))}`",
        f"- Storage clean of NLE runtime fields: `{bool(render_export.get('storage_clean'))}`",
        f"- Captions/gaps/candidates: `{render_export.get('caption_count')}/{render_export.get('gap_count')}/{render_export.get('candidate_count')}`",
        f"- Render segments/manifest/stitched: `{render_export.get('render_segment_count')}/{render_export.get('manifest_count')}/{render_export.get('stitched_boundary_count')}`",
        f"- Final invalid/non-monotonic/overlap: `{render_export.get('invalid_duration_count')}/{render_export.get('non_monotonic_count')}/{render_export.get('overlap_count')}`",
        f"- Global max active: `{render_export.get('max_active_segments')}`",
        "",
        "| Surface | Stable | Captions | Gaps | Candidates | Render Segments | Manifest | Stitched |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for surface in render_surfaces:
        if not isinstance(surface, dict):
            continue
        lines.append(
            "| "
            + " | ".join([
                str(surface.get("target_surface") or ""),
                str(bool(surface.get("stable"))),
                str(surface.get("caption_count")),
                str(surface.get("gap_count")),
                str(surface.get("candidate_count")),
                str(surface.get("render_segment_count")),
                str(surface.get("manifest_count")),
                str(surface.get("stitched_boundary_count")),
            ])
            + " |"
        )
    lines.extend([
        "",
        "## Future Payload Quarantine",
        "",
        f"- Quarantine recorded: `{bool(future.get('quarantine_recorded'))}`",
        f"- Stripped keys: `{', '.join(future.get('stripped_keys') or [])}`",
        f"- Remaining unapproved fields: `{', '.join(future.get('remaining_unapproved_fields') or []) or 'none'}`",
        "",
        "## Operation Roundtrip Matrix",
        "",
        "| Operation | Runtime NLE | Storage Clean | Reopened Matches | ID Preserved | Markers Preserved | Final Overlap | Max Active |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for row in operations:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            + " | ".join([
                str(row.get("operation_family") or ""),
                str(bool(row.get("runtime_state_hydrated"))),
                str(bool(row.get("storage_clean"))),
                str(bool(row.get("reopened_matches_projected"))),
                str(bool(row.get("reopened_identity_preserved"))),
                str(bool(row.get("reopened_markers_preserved"))),
                str(row.get("overlap_count")),
                str(row.get("max_active_segments")),
            ])
            + " |"
        )
    lines.extend([
        "",
        "## Blockers",
        "",
    ])
    lines.extend(f"- `{item}`" for item in payload.get("blockers") or [])
    lines.extend(["", "## Next Safe Steps", ""])
    lines.extend(f"- {item}" for item in payload.get("next_safe_steps") or [])
    lines.append("")
    return "\n".join(lines)


def write_nle_persistence_cutover_report(output_dir: Path, payload: dict[str, Any]) -> None:
    _write_json(output_dir / "nle_persistence_cutover_audit.json", payload)
    (output_dir / "nle_persistence_cutover_audit.md").write_text(_markdown_report(payload), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit NLE persistence cutover readiness without changing disk format.")
    parser.add_argument("--output-dir", default="output/manual_verification/latest/nle_persistence_cutover_audit_20260628")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser()
    payload = build_nle_persistence_cutover_report(output_dir=output_dir)
    write_nle_persistence_cutover_report(output_dir, payload)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
