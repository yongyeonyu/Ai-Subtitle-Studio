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
    NLE_PERSISTENCE_QUARANTINE_KEY,
    NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
    NLE_TOP_LEVEL_PERSISTENCE_APPROVAL_SCHEMA,
    UNAPPROVED_NLE_PERSISTENCE_KEYS,
    assert_no_unapproved_nle_persistence_fields,
    strip_unapproved_nle_persistence_fields,
)
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
        "canonical_load_owner_change_allowed": bool(projection.get("canonical_load_owner_change_allowed")),
        "nle_snapshot_canonical_load_source_allowed": False,
        "runtime_project_state_persistence_allowed": False,
        "legacy_disk_shape_replacement_allowed": False,
        "final_cutover_ready": bool(persistence_cutover_ready),
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
        "current_canonical_load_owner": str(projection.get("current_canonical_load_owner") or ""),
        "target_load_owner_candidate": "top_level_nle_shadow_metadata",
        "gate_order": list(CANONICAL_LOAD_OWNER_GATE_ORDER),
        "gates": gates,
        "ready_gate_count": len(gates) - len(blocked_gate_ids),
        "blocked_gate_count": len(blocked_gate_ids),
        "blocked_gate_ids": blocked_gate_ids,
        "not_runtime_change": True,
        "not_disk_format_cutover": True,
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
    blockers = list(CUTOVER_BLOCKERS)
    if not top_level_nle_compatibility_projection["gap_coverage_ready"]:
        blockers.insert(1, CUTOVER_GAP_COVERAGE_BLOCKER)
    persistence_cutover_ready = False
    canonical_load_owner_gate_matrix = _canonical_load_owner_gate_matrix(
        checks=checks,
        operation_roundtrip_all_passed=operation_roundtrip_all_passed,
        render_export_parity_passed=bool(render_export_parity["stable"]),
        persistence_cutover_ready=persistence_cutover_ready,
    )

    return {
        "schema": SCHEMA,
        "app_version": APP_VERSION,
        "status": "blocked",
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
        "top_level_nle_canonical_projection_complete": False,
        "remaining_full_cutover_gates": [
            "making top-level nle payloads canonical load owners",
            "persisting _nle_project_state payloads",
            "making nle_snapshot the canonical load source",
            "changing legacy editor_state compatibility guarantees",
        ],
        "next_safe_steps": [
            "keep legacy editor rows canonical while nle_snapshot is persisted as compatibility metadata",
            "treat top-level nle gap coverage as shadow compatibility evidence only",
            "define a separate owner-approval packet before any canonical load-owner change",
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
        "Compatibility audit evidence only. Top-level nle explicit projection includes legacy gap rows as non-caption gap metadata. Canonical project load still rebuilds from legacy editor_state rows; approved nle/nle_snapshot data remains shadow metadata.",
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
        "This matrix is a cutover preflight only. It does not switch the project load owner, persist runtime NLE state, replace legacy editor_state, or change UI/UX.",
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
