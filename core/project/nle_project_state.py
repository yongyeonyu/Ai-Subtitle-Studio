from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any

from core.frame_time import frame_to_sec, normalize_fps, sec_to_nearest_frame
from core.project.nle_snapshot import NLESnapshot, build_project_nle_snapshot
from core.project.project_context import project_segments_to_editor
from core.project.project_format import project_primary_fps

NLE_PROJECT_STATE_SCHEMA = "ai_subtitle_studio.nle_project_state.v1"
NLE_PROJECT_STATE_RUNTIME_KEY = "_nle_project_state"
NLE_OPERATION_JOURNAL_ENTRY_SCHEMA = "ai_subtitle_studio.nle_operation_journal_entry.v1"
NLE_OPERATION_JOURNAL_MAX_ENTRIES = 128


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


def _row_frame_bounds(row: dict[str, Any], *, fps: float) -> tuple[int, int]:
    frame_range = row.get("frame_range", {}) if isinstance(row.get("frame_range"), dict) else {}
    start_frame = row.get("start_frame", row.get("timeline_start_frame", frame_range.get("start")))
    end_frame = row.get("end_frame", row.get("timeline_end_frame", frame_range.get("end")))
    start = _as_float(row.get("start", row.get("timeline_start", 0.0)), 0.0)
    end = _as_float(row.get("end", row.get("timeline_end", start)), start)
    if start_frame is None:
        start_frame = sec_to_nearest_frame(start, fps)
    if end_frame is None:
        end_frame = sec_to_nearest_frame(max(start, end), fps)
    start_frame = _as_int(start_frame, 0)
    end_frame = max(start_frame, _as_int(end_frame, start_frame))
    return start_frame, end_frame


def _caption_metadata(row: dict[str, Any]) -> dict[str, Any]:
    drop = {
        "id",
        "index",
        "line",
        "start",
        "end",
        "timeline_start",
        "timeline_end",
        "text",
        "speaker",
        "spk",
        "is_gap",
        "clip_id",
    }
    return deepcopy({str(key): value for key, value in row.items() if str(key) not in drop})


@dataclass(slots=True)
class NLECaptionState:
    caption_id: str
    sequence_start: float
    sequence_end: float
    text: str
    speaker: str = "00"
    line: int = 0
    clip_id: str = ""
    is_gap: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_editor_row(cls, row: dict[str, Any], *, index: int, fps: float) -> "NLECaptionState":
        start_frame, end_frame = _row_frame_bounds(row, fps=fps)
        is_gap = bool(row.get("is_gap"))
        return cls(
            caption_id=str(row.get("id") or ("gap" if is_gap else "caption") + f"_{index + 1:04d}"),
            sequence_start=frame_to_sec(start_frame, fps),
            sequence_end=frame_to_sec(end_frame, fps),
            text="" if is_gap else str(row.get("text", "") or ""),
            speaker=str(row.get("speaker", row.get("spk", "00")) or "00"),
            line=_as_int(row.get("line"), index),
            clip_id=str(row.get("clip_id") or ""),
            is_gap=is_gap,
            metadata=_caption_metadata(row),
        )

    def to_editor_row(self, *, index: int, fps: float) -> dict[str, Any]:
        start_frame = sec_to_nearest_frame(self.sequence_start, fps)
        end_frame = max(start_frame, sec_to_nearest_frame(self.sequence_end, fps))
        row = deepcopy(self.metadata)
        frame_range = dict(row.get("frame_range") or {}) if isinstance(row.get("frame_range"), dict) else {}
        frame_range.update(
            {
                "unit": "frame",
                "start": start_frame,
                "end": end_frame,
                "timeline_frame_rate": fps,
            }
        )
        row.update(
            {
                "id": self.caption_id,
                "line": index,
                "index": index + 1,
                "start": frame_to_sec(start_frame, fps),
                "end": frame_to_sec(end_frame, fps),
                "timeline_start": frame_to_sec(start_frame, fps),
                "timeline_end": frame_to_sec(end_frame, fps),
                "text": "" if self.is_gap else self.text,
                "speaker": self.speaker,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "timeline_start_frame": start_frame,
                "timeline_end_frame": end_frame,
                "frame_rate": fps,
                "timeline_frame_rate": fps,
                "frame_range": frame_range,
            }
        )
        if self.clip_id:
            row["clip_id"] = self.clip_id
        if self.is_gap:
            row["is_gap"] = True
            row["text"] = ""
        else:
            row.pop("is_gap", None)
        return row


@dataclass(slots=True)
class NLEOperationJournalEntry:
    sequence: int
    operation_id: str
    operation_kind: str
    operation_family: str
    target_ids: tuple[str, ...]
    commit_boundary: str = ""
    commit_source: str = ""
    undo_snapshot_id: str = ""
    projected_count: int = 0
    after_invalid_duration_count: int = 0
    after_non_monotonic_count: int = 0
    after_overlap_count: int = 0
    after_max_active_segments: int = 0
    schema: str = NLE_OPERATION_JOURNAL_ENTRY_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["target_ids"] = list(self.target_ids)
        return payload


@dataclass(slots=True)
class NLEProjectState:
    schema: str
    source_project_path: str
    primary_fps: float
    snapshot: NLESnapshot
    captions: list[NLECaptionState] = field(default_factory=list)
    operation_journal: list[NLEOperationJournalEntry] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def editor_rows(self) -> list[dict[str, Any]]:
        return [
            caption.to_editor_row(index=index, fps=self.primary_fps)
            for index, caption in enumerate(self.captions)
        ]

    def operation_journal_rows(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.operation_journal]


def build_project_nle_state(project: dict[str, Any], *, project_path: str = "") -> NLEProjectState:
    source = project if isinstance(project, dict) else {}
    fps = normalize_fps(project_primary_fps(source))
    snapshot = build_project_nle_snapshot(source, project_path=project_path)
    rows = project_segments_to_editor(source, include_analysis_candidates=False)
    captions = [
        NLECaptionState.from_editor_row(row, index=index, fps=fps)
        for index, row in enumerate(rows)
        if isinstance(row, dict)
    ]
    return NLEProjectState(
        schema=NLE_PROJECT_STATE_SCHEMA,
        source_project_path=str(project_path or source.get("_project_file_path") or source.get("project_path") or ""),
        primary_fps=fps,
        snapshot=snapshot,
        captions=captions,
        metadata={
            "runtime_only": True,
            "hydrated_from": "legacy_project_payload",
            "caption_row_count": len(captions),
            "snapshot_caption_count": snapshot.metadata.get("caption_count", 0),
        },
    )


def attach_project_nle_state(project: dict[str, Any], *, project_path: str = "") -> dict[str, Any]:
    if not isinstance(project, dict):
        return project
    state = project.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    if not isinstance(state, NLEProjectState):
        project[NLE_PROJECT_STATE_RUNTIME_KEY] = build_project_nle_state(project, project_path=project_path)
    return project


def project_nle_state(project: dict[str, Any], *, project_path: str = "") -> NLEProjectState:
    attach_project_nle_state(project, project_path=project_path)
    state = project.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    if not isinstance(state, NLEProjectState):
        raise TypeError("nle_project_state_missing")
    return state


def sync_project_nle_state_from_editor_rows(
    project: dict[str, Any],
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    project_path: str = "",
) -> NLEProjectState:
    state = project_nle_state(project, project_path=project_path)
    fps = normalize_fps(project_primary_fps(project) or state.primary_fps)
    state.primary_fps = fps
    state.captions = [
        NLECaptionState.from_editor_row(row, index=index, fps=fps)
        for index, row in enumerate(list(rows or []))
        if isinstance(row, dict)
    ]
    state.metadata = {
        **dict(state.metadata or {}),
        "last_editor_sync_source": "save_project",
        "last_editor_sync_count": len(state.captions),
    }
    return state


def record_nle_operation_journal_entry(
    state: NLEProjectState,
    operation: Any,
    *,
    projected_count: int = 0,
    max_entries: int = NLE_OPERATION_JOURNAL_MAX_ENTRIES,
) -> NLEOperationJournalEntry:
    if not isinstance(state, NLEProjectState):
        raise TypeError("nle_project_state_required")
    if not getattr(operation, "operation_id", "") or not getattr(operation, "kind", ""):
        raise TypeError("nle_operation_required")
    limit = max(1, int(max_entries or NLE_OPERATION_JOURNAL_MAX_ENTRIES))
    metadata = dict(operation.metadata or {})
    after_projection = dict(operation.after_projection or {})
    next_sequence = (state.operation_journal[-1].sequence + 1) if state.operation_journal else 1
    entry = NLEOperationJournalEntry(
        sequence=next_sequence,
        operation_id=str(operation.operation_id or ""),
        operation_kind=str(operation.kind or ""),
        operation_family=str(metadata.get("operation_family") or operation.kind or ""),
        target_ids=tuple(str(item) for item in tuple(operation.target_ids or ())),
        commit_boundary=str(metadata.get("commit_boundary") or ""),
        commit_source=str(metadata.get("commit_source") or ""),
        undo_snapshot_id=str(getattr(operation.undo_snapshot, "snapshot_id", "") or ""),
        projected_count=max(0, _as_int(projected_count, 0)),
        after_invalid_duration_count=max(0, _as_int(after_projection.get("invalid_duration_count"), 0)),
        after_non_monotonic_count=max(0, _as_int(after_projection.get("non_monotonic_count"), 0)),
        after_overlap_count=max(0, _as_int(after_projection.get("overlap_count"), 0)),
        after_max_active_segments=max(0, _as_int(after_projection.get("max_active_segments"), 0)),
    )
    state.operation_journal.append(entry)
    if len(state.operation_journal) > limit:
        state.operation_journal = state.operation_journal[-limit:]
    state.metadata = {
        **dict(state.metadata or {}),
        "operation_journal_runtime_only": True,
        "operation_journal_count": len(state.operation_journal),
        "operation_journal_last_operation_id": entry.operation_id,
        "operation_journal_max_entries": limit,
    }
    _trace_nle_operation_journal_entry(state, entry, operation, max_entries=limit)
    return entry


def _trace_nle_operation_journal_entry(
    state: NLEProjectState,
    entry: NLEOperationJournalEntry,
    operation: Any,
    *,
    max_entries: int,
) -> bool:
    try:
        from core.runtime.trace_logger import current_app_trace_logger

        logger = current_app_trace_logger()
        if logger is None:
            return False
        return bool(
            logger.log_event(
                "nle_operation_journal_append",
                stage="nle-operation",
                level="INFO",
                event_type="nle_operation_commit",
                operation_id=entry.operation_id,
                operation_kind=entry.operation_kind,
                operation_family=entry.operation_family,
                time_domain=str(getattr(operation, "time_domain", "") or ""),
                sequence=entry.sequence,
                target_count=len(entry.target_ids),
                commit_boundary=entry.commit_boundary,
                commit_source=entry.commit_source,
                undo_snapshot_id=entry.undo_snapshot_id,
                projected_count=entry.projected_count,
                after_invalid_duration_count=entry.after_invalid_duration_count,
                after_non_monotonic_count=entry.after_non_monotonic_count,
                after_overlap_count=entry.after_overlap_count,
                after_max_active_segments=entry.after_max_active_segments,
                runtime_journal_count=len(state.operation_journal),
                runtime_journal_max_entries=max(1, int(max_entries or NLE_OPERATION_JOURNAL_MAX_ENTRIES)),
                runtime_only=True,
                state_schema=state.schema,
            )
        )
    except Exception:
        return False


def project_segments_from_nle_state(project: dict[str, Any], *, project_path: str = "") -> list[dict[str, Any]]:
    return project_nle_state(project, project_path=project_path).editor_rows()


def assert_nle_editor_rows_consistent(
    editor_rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    nle_rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    primary_fps: float,
) -> None:
    fps = normalize_fps(primary_fps)
    left = [row for row in list(editor_rows or []) if isinstance(row, dict)]
    right = [row for row in list(nle_rows or []) if isinstance(row, dict)]
    if len(left) != len(right):
        raise ValueError(f"nle_editor_row_count_drift:{len(left)}!={len(right)}")
    for index, (editor_row, nle_row) in enumerate(zip(left, right)):
        editor_start, editor_end = _row_frame_bounds(editor_row, fps=fps)
        nle_start, nle_end = _row_frame_bounds(nle_row, fps=fps)
        if (editor_start, editor_end) != (nle_start, nle_end):
            raise ValueError(f"nle_editor_timing_drift:{index}:{editor_start}-{editor_end}!={nle_start}-{nle_end}")
        if bool(editor_row.get("is_gap")) != bool(nle_row.get("is_gap")):
            raise ValueError(f"nle_editor_gap_drift:{index}")
        if not bool(editor_row.get("is_gap")) and str(editor_row.get("text", "") or "") != str(nle_row.get("text", "") or ""):
            raise ValueError(f"nle_editor_text_drift:{index}")


__all__ = [
    "NLECaptionState",
    "NLEOperationJournalEntry",
    "NLEProjectState",
    "NLE_OPERATION_JOURNAL_ENTRY_SCHEMA",
    "NLE_OPERATION_JOURNAL_MAX_ENTRIES",
    "NLE_PROJECT_STATE_RUNTIME_KEY",
    "NLE_PROJECT_STATE_SCHEMA",
    "attach_project_nle_state",
    "assert_nle_editor_rows_consistent",
    "build_project_nle_state",
    "project_nle_state",
    "project_segments_from_nle_state",
    "record_nle_operation_journal_entry",
    "sync_project_nle_state_from_editor_rows",
]
