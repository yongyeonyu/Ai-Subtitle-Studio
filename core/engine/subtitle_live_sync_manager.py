from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SUBTITLE_LIVE_SYNC_PROGRESS_SCHEMA = "ai_subtitle_studio.subtitle_live_sync.progress.v1"
SUBTITLE_LIVE_SYNC_TOPICLESS_SCHEMA = "ai_subtitle_studio.subtitle_live_sync.topicless.v1"


def normalize_live_processing_stage_text(text: Any) -> str:
    return str(text or "").strip()


def subtitle_live_sync_status_is_final(text: Any, *, is_final: bool = False, is_raw: bool = False) -> bool:
    _ = is_raw
    message = str(text or "")
    return bool(is_final or "에러" in message or "실패" in message)


@dataclass(frozen=True)
class SubtitleLiveSyncProgress:
    schema: str
    current_index: int
    total_count: int
    percent: int
    current_segment_end: float
    total_duration: float
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "current_index": self.current_index,
            "total_count": self.total_count,
            "percent": self.percent,
            "current_segment_end": self.current_segment_end,
            "total_duration": self.total_duration,
            "source": self.source,
        }


def build_subtitle_live_sync_progress(
    current_index: Any,
    total_count: Any,
    *,
    current_segment_end: Any = 0.0,
    total_duration: Any = 0.0,
) -> SubtitleLiveSyncProgress:
    try:
        c_idx = int(current_index or 0)
    except Exception:
        c_idx = 0
    try:
        t_total = int(total_count or 0)
    except Exception:
        t_total = 0
    try:
        current_end = float(current_segment_end or 0.0)
    except Exception:
        current_end = 0.0
    try:
        duration = float(total_duration or 0.0)
    except Exception:
        duration = 0.0

    source = "empty"
    percent = 0
    if duration > 0 and current_end > 0:
        percent = min(100, int((current_end / duration) * 100))
        source = "segment_time"
    elif t_total > 0:
        percent = min(100, int((c_idx / t_total) * 100))
        source = "chunk_count"
    return SubtitleLiveSyncProgress(
        schema=SUBTITLE_LIVE_SYNC_PROGRESS_SCHEMA,
        current_index=c_idx,
        total_count=t_total,
        percent=percent,
        current_segment_end=current_end,
        total_duration=duration,
        source=source,
    )


@dataclass(frozen=True)
class SubtitleTopiclessLiveSyncPayload:
    schema: str
    rows: tuple[dict[str, Any], ...]
    source: str
    roughcut_result: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "rows": [dict(row) for row in self.rows],
            "source": self.source,
            "roughcut_result": dict(self.roughcut_result) if isinstance(self.roughcut_result, dict) else None,
            "counts": {
                "rows": len(self.rows),
                "has_roughcut_result": isinstance(self.roughcut_result, dict),
            },
        }


def build_cut_boundary_topicless_live_sync_payload(
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    source: str = "stream",
) -> SubtitleTopiclessLiveSyncPayload:
    copied_rows = [dict(row) for row in list(rows or []) if isinstance(row, dict)]
    source_text = str(source or "stream")
    result_dict: dict[str, Any] | None = None
    if copied_rows:
        result_dict = {
            "segments": [dict(row) for row in copied_rows],
            "chapters": [],
            "edit_decisions": [],
            "edl_segments": [],
            "guide_markdown": "",
            "schema_version": "roughcut_result.v2",
            "draft_state": {"status": "review"},
            "video_summary": f"컷 경계 기반 주제없음 중분류 {len(copied_rows)}개",
            "source": f"cut_boundary_{source_text}",
        }
    return SubtitleTopiclessLiveSyncPayload(
        schema=SUBTITLE_LIVE_SYNC_TOPICLESS_SCHEMA,
        rows=tuple(copied_rows),
        source=source_text,
        roughcut_result=result_dict,
    )


__all__ = [
    "SUBTITLE_LIVE_SYNC_PROGRESS_SCHEMA",
    "SUBTITLE_LIVE_SYNC_TOPICLESS_SCHEMA",
    "SubtitleLiveSyncProgress",
    "SubtitleTopiclessLiveSyncPayload",
    "build_cut_boundary_topicless_live_sync_payload",
    "build_subtitle_live_sync_progress",
    "normalize_live_processing_stage_text",
    "subtitle_live_sync_status_is_final",
]
