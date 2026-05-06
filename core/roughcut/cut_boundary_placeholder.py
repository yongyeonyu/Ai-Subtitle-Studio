from __future__ import annotations

import os
import time
from typing import Iterable

from core.project.project_io import read_project_file, write_project_file


def _cut_sec(row) -> float | None:
    try:
        if isinstance(row, dict):
            return float(row.get("timeline_sec", row.get("time", row.get("start", 0.0))) or 0.0)
        return float(row)
    except Exception:
        return None


def _is_placeholder_row(row: dict) -> bool:
    if not isinstance(row, dict):
        return False

    title = str(row.get("title", row.get("name", "")) or "")
    tags = row.get("tags", []) or []
    if isinstance(tags, str):
        tags = [tags]

    return bool(
        row.get("is_topicless_placeholder")
        or row.get("is_cut_boundary_placeholder")
        or row.get("source") == "cut_boundary"
        or title == "주제없음"
        or "컷경계" in tags
    )


def _can_overwrite_segments(rows) -> bool:
    rows = list(rows or [])
    if not rows:
        return True
    return all(_is_placeholder_row(row) for row in rows if isinstance(row, dict))


def apply_topicless_placeholders_to_project(
    project_path: str,
    cut_boundaries: Iterable,
    *,
    media_duration: float | None = None,
    include_trailing: bool = False,
) -> list[dict]:
    """Save gray topicless middle segments into the current project.

    The project file is not moved or copied. Only analysis/roughcut fields are
    updated.
    """
    if not project_path or not os.path.exists(project_path):
        return []

    rows = build_topicless_middle_segments(
        cut_boundaries,
        media_duration=media_duration,
        include_trailing=include_trailing,
    )
    if not rows:
        return []

    project = read_project_file(project_path)

    project.setdefault("analysis", {})
    analysis = project["analysis"]

    analysis["cut_boundaries"] = list(cut_boundaries or [])

    # UI/roughcut loader가 어떤 이름을 보든 찾을 수 있게 호환 저장
    analysis["cut_boundary_topicless_middle_segments"] = list(rows)
    analysis["topicless_middle_segments"] = list(rows)
    analysis["roughcut_topicless_segments"] = list(rows)
    analysis["middle_segments"] = list(rows)

    # roughcut 계열 필드에도 placeholder-only 상태면 즉시 반영
    for key in ("roughcut", "roughcut_draft", "roughcut_result"):
        box = project.setdefault(key, {})
        if isinstance(box, dict) and _can_overwrite_segments(box.get("segments", [])):
            box["segments"] = list(rows)
            box["chapters"] = []
            box["edit_decisions"] = []
            box["edl_segments"] = []
            box["guide_markdown"] = ""
            box["schema_version"] = "roughcut_result.v2"
            box["draft_state"] = {"status": "review"}
            box["video_summary"] = f"컷 경계 기반 주제없음 중분류 {len(rows)}개"

    if _can_overwrite_segments(project.get("roughcut_segments", [])):
        project["roughcut_segments"] = list(rows)

    if _can_overwrite_segments(project.get("middle_segments", [])):
        project["middle_segments"] = list(rows)

    analysis["cut_boundary_topicless_updated_at"] = time.time()

    write_project_file(project_path, project)

    return rows


def extract_topicless_placeholders_from_project(project_path: str) -> list[dict]:
    if not project_path or not os.path.exists(project_path):
        return []

    try:
        project = read_project_file(project_path)
    except Exception:
        return []

    analysis = project.get("analysis", {}) if isinstance(project, dict) else {}

    for key in (
        "cut_boundary_topicless_middle_segments",
        "topicless_middle_segments",
        "roughcut_topicless_segments",
        "middle_segments",
    ):
        rows = analysis.get(key, [])
        if rows:
            return list(rows)

    for key in ("roughcut", "roughcut_draft", "roughcut_result"):
        box = project.get(key, {})
        if isinstance(box, dict):
            rows = box.get("segments", [])
            if rows and all(_is_placeholder_row(row) for row in rows if isinstance(row, dict)):
                return list(rows)

    rows = project.get("roughcut_segments", [])
    if rows and all(_is_placeholder_row(row) for row in rows if isinstance(row, dict)):
        return list(rows)

    rows = project.get("middle_segments", [])
    if rows and all(_is_placeholder_row(row) for row in rows if isinstance(row, dict)):
        return list(rows)

    return []


# === FULL TOPICLESS FRAME SPLIT PATCH START ===

def _topicless_middle_label(index: int) -> str:
    """1 -> A, 2 -> B, ... 26 -> Z, 27 -> AA."""
    try:
        index = max(1, int(index))
    except Exception:
        index = 1

    letters = ""
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _topicless_fps_from_boundaries(cut_boundaries, default: float = 30.0) -> float:
    from core.frame_time import normalize_fps

    for row in list(cut_boundaries or []):
        if not isinstance(row, dict):
            continue
        for key in ("fps", "frame_rate", "timeline_frame_rate"):
            try:
                value = float(row.get(key) or 0.0)
                if value > 1.0:
                    return normalize_fps(value)
            except Exception:
                pass
    return normalize_fps(default)


def _topicless_frame_from_boundary(row, fps: float) -> int | None:
    from core.frame_time import sec_to_frame

    if isinstance(row, dict):
        for key in ("timeline_frame", "frame", "start_frame", "timeline_start_frame"):
            try:
                value = row.get(key)
                if value is not None:
                    frame = int(value)
                    if frame > 0:
                        return frame
            except Exception:
                pass

        for key in ("timeline_sec", "time", "start", "timeline_start"):
            try:
                sec = float(row.get(key) or 0.0)
                if sec > 0.0:
                    return sec_to_frame(sec, fps)
            except Exception:
                pass
    else:
        try:
            sec = float(row)
            if sec > 0.0:
                return sec_to_frame(sec, fps)
        except Exception:
            pass

    return None


def _topicless_segment_row(index: int, start_frame: int, end_frame: int, fps: float) -> dict:
    from core.frame_time import frame_to_sec

    start_frame = max(0, int(start_frame))
    end_frame = max(start_frame, int(end_frame))

    start = frame_to_sec(start_frame, fps)
    end = frame_to_sec(end_frame, fps)

    major_label = _topicless_middle_label(index)
    internal_id = f"cut_topicless_middle_{major_label}"

    return {
        # UI 표시용 ID
        "id": major_label,
        "segment_id": major_label,
        "chapter_id": major_label,
        "major_id": major_label,

        # 내부 추적용 ID
        "internal_id": internal_id,
        "source_id": internal_id,

        # canonical frame fields
        "fps": fps,
        "frame_rate": fps,
        "timeline_frame_rate": fps,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "timeline_start_frame": start_frame,
        "timeline_end_frame": end_frame,
        "frame_range": {
            "unit": "frame",
            "start": start_frame,
            "end": end_frame,
            "timeline_frame_rate": fps,
        },

        # seconds are derived from frame/fps only
        "start": start,
        "end": end,
        "timeline_start": start,
        "timeline_end": end,

        # 주제 텍스트
        "title": "주제없음",
        "name": "주제없음",
        "display_title": f"{major_label} 주제없음",
        "display_name": f"{major_label} 주제없음",
        "label": f"{major_label} 주제없음",

        "summary": "컷 경계 기반으로 자동 생성된 임시 중분류 세그먼트입니다.",
        "llm_summary": "",

        "tags": ["컷경계", "주제없음"],
        "source": "cut_boundary",
        "story_role": "topicless_placeholder",
        "narrative_function": "cut_boundary_placeholder",

        "level": "middle",
        "segment_type": "middle",
        "roughcut_level": "middle",
        "category": "middle",
        "is_middle_segment": True,

        "is_topicless_placeholder": True,
        "is_cut_boundary_placeholder": True,
        "topicless": True,
        "color_role": "topicless",
        "display_color": "gray",
        "ui_color": "gray",
        "color": "#9CA3AF",

        "needs_review": True,
        "status": "needs_review",
        "safety": "acceptable",
        "importance": 0.0,
        "importance_score": 0.0,
        "boundary_confidence": 1.0,

        "can_move": True,
        "can_trim": True,
        "can_remove": True,
        "move_risk": "low",
        "dependencies": [],
    }


def build_topicless_middle_segments(
    cut_boundaries,
    *,
    media_duration: float | None = None,
    include_trailing: bool = False,
) -> list[dict]:
    """
    컷 경계 기준 회색 주제없음 중분류 생성.

    프레임 기준:
    - 컷이 없어도 duration이 있으면 A = 0프레임 ~ 영상끝프레임 생성
    - 컷이 생기면 frame 기준으로 A/B/C split
    - start/end 초는 frame_to_sec(frame, fps) 결과만 저장
    """
    from core.cut_boundary_middle import coalesce_topicless_middle_boundary_frames
    from core.frame_time import sec_to_frame

    cut_list = list(cut_boundaries or [])
    fps = _topicless_fps_from_boundaries(cut_list)

    duration_frame = 0
    try:
        duration = float(media_duration or 0.0)
        if duration > 0.0:
            duration_frame = sec_to_frame(duration, fps)
    except Exception:
        duration_frame = 0

    cut_rows: list[dict] = []
    for row in cut_list:
        frame = _topicless_frame_from_boundary(row, fps)
        if frame is not None and frame > 0:
            if isinstance(row, dict):
                cut_rows.append(dict(row))
            else:
                cut_rows.append({"timeline_frame": int(frame), "frame": int(frame), "fps": fps})

    try:
        from core.settings import load_settings

        settings = dict(load_settings() or {})
    except Exception:
        settings = {}

    cut_frames = coalesce_topicless_middle_boundary_frames(
        cut_rows,
        fps=fps,
        duration_frame=duration_frame,
        settings=settings,
    )

    # 핵심: 컷이 없어도 duration을 알면 전체 A 주제없음 생성
    if not cut_frames:
        if duration_frame > 0:
            return [_topicless_segment_row(1, 0, duration_frame, fps)]
        return []

    boundary_frames = [0] + cut_frames

    # duration을 알면 항상 마지막 컷~영상끝 구간도 생성
    if duration_frame > boundary_frames[-1]:
        boundary_frames.append(duration_frame)
    elif include_trailing and duration_frame > boundary_frames[-1]:
        boundary_frames.append(duration_frame)

    rows: list[dict] = []
    for idx in range(len(boundary_frames) - 1):
        start_frame = int(boundary_frames[idx])
        end_frame = int(boundary_frames[idx + 1])
        if end_frame <= start_frame:
            continue
        rows.append(_topicless_segment_row(idx + 1, start_frame, end_frame, fps))

    return rows

# === FULL TOPICLESS FRAME SPLIT PATCH END ===


# === TOPICLESS SPLIT LOG PATCH START ===

def _topicless_split_log_emit(message: str) -> None:
    try:
        from core.runtime.logger import get_logger
        get_logger().log(message)
    except Exception:
        try:
            print(message, flush=True)
        except Exception:
            pass


def _topicless_split_row_meta(row: dict) -> tuple[str, int, int, float, float, float]:
    try:
        label = str(row.get("major_id") or row.get("segment_id") or row.get("id") or "?")
    except Exception:
        label = "?"

    try:
        fps = float(row.get("fps", row.get("frame_rate", row.get("timeline_frame_rate", 30.0))) or 30.0)
    except Exception:
        fps = 30.0

    try:
        start_frame = int(row.get("timeline_start_frame", row.get("start_frame")))
    except Exception:
        try:
            start_frame = int(round(float(row.get("start", row.get("timeline_start", 0.0)) or 0.0) * fps))
        except Exception:
            start_frame = 0

    try:
        end_frame = int(row.get("timeline_end_frame", row.get("end_frame")))
    except Exception:
        try:
            end_frame = int(round(float(row.get("end", row.get("timeline_end", 0.0)) or 0.0) * fps))
        except Exception:
            end_frame = start_frame

    try:
        start_sec = float(row.get("start", row.get("timeline_start", start_frame / fps)) or 0.0)
    except Exception:
        start_sec = start_frame / fps

    try:
        end_sec = float(row.get("end", row.get("timeline_end", end_frame / fps)) or 0.0)
    except Exception:
        end_sec = end_frame / fps

    return label, start_frame, end_frame, start_sec, end_sec, fps


_TOPICLESS_SPLIT_LOGGED_KEYS: list[tuple[str, int, int]] = []


def _topicless_log_split_rows(rows, *, context: str = "build") -> None:
    rows = list(rows or [])
    if not rows:
        _topicless_split_log_emit(f"  ▒ [컷 경계] split 없음 context={context}")
        return

    current_keys: list[tuple[str, int, int]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label, start_frame, end_frame, _start_sec, _end_sec, _fps = _topicless_split_row_meta(row)
        current_keys.append((label, int(start_frame), int(end_frame)))

    global _TOPICLESS_SPLIT_LOGGED_KEYS
    previous_keys = list(_TOPICLESS_SPLIT_LOGGED_KEYS or [])

    should_reset = False
    if not previous_keys:
        should_reset = True
    elif len(current_keys) < len(previous_keys):
        should_reset = True
    elif current_keys:
        prev_first = previous_keys[0] if previous_keys else None
        prev_last = previous_keys[-1] if previous_keys else None
        if prev_first != current_keys[0] or prev_last != current_keys[-1]:
            should_reset = True

    previous_seen = set() if should_reset else set(previous_keys)
    new_rows = []
    for row, key in zip(rows, current_keys):
        if key not in previous_seen:
            new_rows.append(row)

    _TOPICLESS_SPLIT_LOGGED_KEYS = current_keys
    if not new_rows:
        return

    _topicless_split_log_emit(
        f"  ▒ [컷 경계] split frame/time 로그 시작 context={context} new={len(new_rows)} total={len(rows)}"
    )

    for row in new_rows:
        if not isinstance(row, dict):
            continue

        label, start_frame, end_frame, start_sec, end_sec, fps = _topicless_split_row_meta(row)
        title = str(row.get("title", row.get("name", "주제없음")) or "주제없음")
        dur_frame = max(0, int(end_frame) - int(start_frame))
        dur_sec = max(0.0, float(end_sec) - float(start_sec))

        _topicless_split_log_emit(
            f"  ▒ [컷 경계] split {label} {title} "
            f"frame={start_frame}->{end_frame} "
            f"time={start_sec:.3f}s->{end_sec:.3f}s "
            f"dur={dur_frame}f/{dur_sec:.3f}s "
            f"fps={fps:.3f}"
        )


_topicless_original_build_topicless_middle_segments = build_topicless_middle_segments
_topicless_original_apply_topicless_placeholders_to_project = apply_topicless_placeholders_to_project


def build_topicless_middle_segments(
    cut_boundaries,
    *,
    media_duration: float | None = None,
    include_trailing: bool = False,
) -> list[dict]:
    rows = _topicless_original_build_topicless_middle_segments(
        cut_boundaries,
        media_duration=media_duration,
        include_trailing=include_trailing,
    )
    _topicless_log_split_rows(rows, context=f"build include_trailing={bool(include_trailing)}")
    return rows


def apply_topicless_placeholders_to_project(
    project_path: str,
    cut_boundaries,
    *,
    media_duration: float | None = None,
    include_trailing: bool = False,
) -> list[dict]:
    rows = _topicless_original_apply_topicless_placeholders_to_project(
        project_path,
        cut_boundaries,
        media_duration=media_duration,
        include_trailing=include_trailing,
    )
    _topicless_log_split_rows(rows, context=f"project-save include_trailing={bool(include_trailing)}")
    return rows

# === TOPICLESS SPLIT LOG PATCH END ===
