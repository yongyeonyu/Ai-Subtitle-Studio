from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any

from core.project.nle_projection_parity import ProjectionParityReport

NLE_OPERATION_SCHEMA = "ai_subtitle_studio.nle_operation.v1"
NLE_UNDO_SNAPSHOT_SCHEMA = "ai_subtitle_studio.nle_undo_snapshot.v1"

NLE_OPERATION_KINDS = frozenset(
    {
        "caption_move",
        "caption_resize",
        "caption_text_edit",
        "caption_split",
        "caption_merge",
        "caption_delete",
        "caption_range_replace",
        "gap_generate",
        "gap_delete",
        "candidate_confirm",
        "marker_edit",
        "roughcut_range_edit",
    }
)

_FINAL_CAPTION_KINDS = frozenset(
    {
        "caption_move",
        "caption_resize",
        "caption_text_edit",
        "caption_split",
        "caption_merge",
        "caption_delete",
        "caption_range_replace",
        "candidate_confirm",
    }
)

_KIND_TIME_DOMAINS = {
    "caption_move": frozenset({"sequence"}),
    "caption_resize": frozenset({"sequence"}),
    "caption_text_edit": frozenset({"sequence"}),
    "caption_split": frozenset({"sequence"}),
    "caption_merge": frozenset({"sequence"}),
    "caption_delete": frozenset({"sequence"}),
    "caption_range_replace": frozenset({"sequence"}),
    "gap_generate": frozenset({"sequence"}),
    "gap_delete": frozenset({"sequence"}),
    "candidate_confirm": frozenset({"sequence"}),
    "marker_edit": frozenset({"sequence", "output"}),
    "roughcut_range_edit": frozenset({"output"}),
}


class NLEOperationValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NLEUndoSnapshot:
    snapshot_id: str
    operation_id: str
    editor_rows: tuple[dict[str, Any], ...] = ()
    candidate_lanes: tuple[dict[str, Any], ...] = ()
    silence_gaps: tuple[dict[str, Any], ...] = ()
    markers: tuple[dict[str, Any], ...] = ()
    ui_state_ref: dict[str, Any] = field(default_factory=dict)
    nle_projection_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    schema: str = NLE_UNDO_SNAPSHOT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("editor_rows", "candidate_lanes", "silence_gaps", "markers"):
            payload[key] = [dict(row) for row in payload[key]]
        return payload


@dataclass(frozen=True, slots=True)
class NLEEditorOperation:
    operation_id: str
    kind: str
    target_ids: tuple[str, ...]
    before_projection: dict[str, Any]
    after_projection: dict[str, Any]
    time_domain: str
    frame_policy: dict[str, Any]
    undo_snapshot: NLEUndoSnapshot
    metadata: dict[str, Any] = field(default_factory=dict)
    schema: str = NLE_OPERATION_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["target_ids"] = list(self.target_ids)
        payload["undo_snapshot"] = self.undo_snapshot.to_dict()
        return payload


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _deep_tuple(rows: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None) -> tuple[dict[str, Any], ...]:
    return tuple(deepcopy(row) for row in list(rows or []) if isinstance(row, dict))


def _projection_to_dict(projection: ProjectionParityReport | dict[str, Any]) -> dict[str, Any]:
    if isinstance(projection, ProjectionParityReport):
        return projection.to_dict()
    if isinstance(projection, dict):
        return deepcopy(projection)
    raise NLEOperationValidationError("operation_projection_required")


def _default_frame_policy(frame_policy: dict[str, Any] | None) -> dict[str, Any]:
    policy = dict(frame_policy or {})
    policy.setdefault("unit", "frame")
    policy.setdefault("rounding", "nearest")
    policy.setdefault("allow_final_overlap", False)
    return policy


def build_nle_undo_snapshot(
    *,
    operation_id: str,
    editor_rows: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    candidate_lanes: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    silence_gaps: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    markers: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    ui_state_ref: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    snapshot_id: str = "",
) -> NLEUndoSnapshot:
    operation_key = str(operation_id or "").strip()
    if not operation_key:
        raise NLEOperationValidationError("operation_id_required")
    editor_payload = _deep_tuple(editor_rows)
    candidate_payload = _deep_tuple(candidate_lanes)
    gap_payload = _deep_tuple(silence_gaps)
    marker_payload = _deep_tuple(markers)
    ui_ref = deepcopy(dict(ui_state_ref or {}))
    snapshot_payload = {
        "operation_id": operation_key,
        "editor_rows": editor_payload,
        "candidate_lanes": candidate_payload,
        "silence_gaps": gap_payload,
        "markers": marker_payload,
        "ui_state_ref": ui_ref,
    }
    projection_hash = _stable_hash(snapshot_payload)
    return NLEUndoSnapshot(
        snapshot_id=str(snapshot_id or f"undo_{projection_hash[:16]}"),
        operation_id=operation_key,
        editor_rows=editor_payload,
        candidate_lanes=candidate_payload,
        silence_gaps=gap_payload,
        markers=marker_payload,
        ui_state_ref=ui_ref,
        nle_projection_hash=projection_hash,
        metadata=deepcopy(dict(metadata or {})),
    )


def _validate_after_projection(kind: str, after_projection: dict[str, Any]) -> None:
    diff_summary = str(after_projection.get("diff_summary", "") or "")
    if diff_summary and diff_summary != "ok":
        raise NLEOperationValidationError(f"operation_projection_drift:{diff_summary}")
    if kind in _FINAL_CAPTION_KINDS:
        if int(after_projection.get("invalid_duration_count", 0) or 0) != 0:
            raise NLEOperationValidationError("operation_final_invalid_duration")
        if int(after_projection.get("non_monotonic_count", 0) or 0) != 0:
            raise NLEOperationValidationError("operation_final_non_monotonic")
        if int(after_projection.get("overlap_count", 0) or 0) != 0:
            raise NLEOperationValidationError("operation_final_overlap")
        if int(after_projection.get("max_active_segments", 0) or 0) > 1:
            raise NLEOperationValidationError("operation_final_max_active_segments")


def _validate_operation_metadata(kind: str, metadata: dict[str, Any]) -> None:
    if kind == "candidate_confirm":
        source = str(metadata.get("candidate_source") or metadata.get("source") or "").strip().upper()
        if source not in {"STT1", "STT2", "LLM_DRAFT", "DIAGNOSTIC"}:
            raise NLEOperationValidationError("candidate_confirm_source_required")


def build_nle_editor_operation(
    *,
    operation_id: str,
    kind: str,
    target_ids: list[str] | tuple[str, ...],
    before_projection: ProjectionParityReport | dict[str, Any],
    after_projection: ProjectionParityReport | dict[str, Any],
    time_domain: str = "",
    frame_policy: dict[str, Any] | None = None,
    undo_snapshot: NLEUndoSnapshot | None = None,
    metadata: dict[str, Any] | None = None,
) -> NLEEditorOperation:
    operation_key = str(operation_id or "").strip()
    if not operation_key:
        raise NLEOperationValidationError("operation_id_required")
    kind_key = str(kind or "").strip()
    if kind_key not in NLE_OPERATION_KINDS:
        raise NLEOperationValidationError(f"operation_kind_unsupported:{kind_key}")
    targets = tuple(str(item).strip() for item in target_ids if str(item).strip())
    if not targets:
        raise NLEOperationValidationError("operation_targets_required")
    domain = str(time_domain or ("output" if kind_key == "roughcut_range_edit" else "sequence")).strip()
    if domain not in _KIND_TIME_DOMAINS[kind_key]:
        raise NLEOperationValidationError(f"operation_time_domain_invalid:{kind_key}:{domain}")
    if undo_snapshot is None:
        raise NLEOperationValidationError("operation_undo_snapshot_required")
    if undo_snapshot.operation_id != operation_key:
        raise NLEOperationValidationError("operation_undo_snapshot_mismatch")

    before_payload = _projection_to_dict(before_projection)
    after_payload = _projection_to_dict(after_projection)
    metadata_payload = deepcopy(dict(metadata or {}))
    _validate_operation_metadata(kind_key, metadata_payload)
    _validate_after_projection(kind_key, after_payload)

    return NLEEditorOperation(
        operation_id=operation_key,
        kind=kind_key,
        target_ids=targets,
        before_projection=before_payload,
        after_projection=after_payload,
        time_domain=domain,
        frame_policy=_default_frame_policy(frame_policy),
        undo_snapshot=undo_snapshot,
        metadata=metadata_payload,
    )


__all__ = [
    "NLEEditorOperation",
    "NLEOperationValidationError",
    "NLEUndoSnapshot",
    "NLE_OPERATION_KINDS",
    "NLE_OPERATION_SCHEMA",
    "NLE_UNDO_SNAPSHOT_SCHEMA",
    "build_nle_editor_operation",
    "build_nle_undo_snapshot",
]
