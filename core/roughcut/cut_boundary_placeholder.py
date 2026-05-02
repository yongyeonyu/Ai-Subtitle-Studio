from __future__ import annotations

import json
import os
import time
from typing import Iterable


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


def build_topicless_middle_segments(
    cut_boundaries: Iterable,
    *,
    media_duration: float | None = None,
    include_trailing: bool = False,
) -> list[dict]:
    """Build gray middle segments from absolute cut boundaries.

    During scan:
    - first cut creates 00:00~first_cut immediately.

    After full scan:
    - include_trailing=True also creates last_cut~video_end.
    """
    cuts: list[float] = []
    for row in list(cut_boundaries or []):
        sec = _cut_sec(row)
        if sec is not None and sec > 0.0:
            cuts.append(round(float(sec), 3))

    cuts = sorted(set(cuts))
    if not cuts:
        return []

    duration = float(media_duration or 0.0)
    boundaries = [0.0] + cuts

    if include_trailing and duration > boundaries[-1]:
        boundaries.append(round(duration, 3))

    rows: list[dict] = []
    for idx in range(len(boundaries) - 1):
        start = round(float(boundaries[idx]), 3)
        end = round(float(boundaries[idx + 1]), 3)
        if end <= start:
            continue

        seg_id = f"cut_topicless_middle_{idx + 1:03d}"
        rows.append({
            "id": seg_id,
            "segment_id": seg_id,
            "chapter_id": seg_id,
            "major_id": seg_id,

            "start": start,
            "end": end,

            "title": "주제없음",
            "name": "주제없음",
            "summary": "컷 경계 기반으로 자동 생성된 임시 중분류 세그먼트입니다.",
            "llm_summary": "",

            "tags": ["컷경계", "주제없음"],
            "source": "cut_boundary",
            "story_role": "topicless_placeholder",
            "narrative_function": "cut_boundary_placeholder",

            # 중분류로 인식시키기 위한 호환 필드
            "level": "middle",
            "segment_type": "middle",
            "roughcut_level": "middle",
            "category": "middle",
            "is_middle_segment": True,

            # 회색 placeholder로 인식시키기 위한 호환 필드
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
        })

    return rows


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

    with open(project_path, "r", encoding="utf-8") as f:
        project = json.load(f)

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

    with open(project_path, "w", encoding="utf-8") as f:
        json.dump(project, f, ensure_ascii=False, indent=2)

    return rows


def extract_topicless_placeholders_from_project(project_path: str) -> list[dict]:
    if not project_path or not os.path.exists(project_path):
        return []

    try:
        with open(project_path, "r", encoding="utf-8") as f:
            project = json.load(f)
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
