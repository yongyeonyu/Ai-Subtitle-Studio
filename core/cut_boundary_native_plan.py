from __future__ import annotations

"""Central cut-boundary row planning and native scan presets.

This module is the single place that defines:
- initial topicless middle segment shape
- provisional audio / visual boundary display rows
- follower-reviewed middle segment drafts
- pioneer/follower native scan presets
"""

from typing import Any, Iterable

from core.cut_boundary_audio import AUDIO_GAIN_LINE_COLOR, is_audio_gain_boundary
from core.frame_time import frame_to_sec, normalize_fps, sec_to_frame
from core.media_info import probe_media
from core.roughcut.cut_boundary_placeholder import build_topicless_middle_segments


VISUAL_PROVISIONAL_LINE_COLOR = "#00B7FF"
FOLLOWER_CHECKED_LINE_COLOR = "#8E8E93"
INITIAL_MIDDLE_BORDER_COLOR = "#8E8E93"
PROVISIONAL_VISUAL_COMPARE_WIDTH = 1280
PROVISIONAL_VISUAL_COMPARE_HEIGHT = 720
PROVISIONAL_PACKET_BUCKET_SEC = 0.25
PROVISIONAL_PACKET_MIN_GAP_SEC = 0.20
PROVISIONAL_PIONEER_MIN_GAP_SEC = 0.45
PROVISIONAL_PACKET_RAW_CANDIDATES = 180
FOLLOWER_VERIFY_COMPARE_WIDTH = 1920
FOLLOWER_VERIFY_COMPARE_HEIGHT = 1080
PROVISIONAL_VISUAL_SCAN_PROFILE = {
    "level": "low",
    "label": "낮음 - 3×3 십자가 4칸",
    "grid": "3x3",
    "grid_size": 3,
    "mask": "cross4",
    "positions": (1, 3, 5, 7),
    "cell_count": 4,
}
FOLLOWER_REVIEW_SCAN_PROFILE = {
    "level": "follower",
    "label": "후발대 - 5×5 중앙 3×3 9칸",
    "grid": "5x5",
    "grid_size": 5,
    "mask": "inner9",
    "positions": (6, 7, 8, 11, 12, 13, 16, 17, 18),
    "cell_count": 9,
}
FOLLOWER_MIDDLE_COLORS = (
    "#00E676",
    "#FF453A",
    "#FFD60A",
    "#76FF03",
    "#00B8D4",
    "#FF9F0A",
    "#BF5AF2",
    "#64D2FF",
    "#FF2D55",
    "#30D158",
    "#0A84FF",
    "#FF6B00",
    "#D0FF00",
    "#5E5CE6",
    "#00F5D4",
    "#FFB3C7",
    "#9DFF00",
    "#FF375F",
    "#40C8E0",
    "#FFCC66",
    "#32D74B",
    "#DA8FFF",
    "#66D4CF",
    "#FF7A90",
    "#A1A1FF",
    "#C6FF3D",
)
FOLLOWER_FINAL_BOUNDARY_STATUSES = {"verified", "confirmed", "accepted", "done"}


def _major_color(major_id: str, index: int = 0) -> str:
    code = str(major_id or "").strip().upper()
    if code and "A" <= code[0] <= "Z":
        return FOLLOWER_MIDDLE_COLORS[ord(code[0]) - ord("A")]
    return FOLLOWER_MIDDLE_COLORS[int(index or 0) % len(FOLLOWER_MIDDLE_COLORS)]


def _segment_title(row: dict[str, Any], default_title: str = "주제없음") -> str:
    title = str(row.get("title") or row.get("name") or default_title).strip()
    return title or default_title


def _segment_display_label(major_id: str, title: str) -> str:
    return f"{str(major_id or '').strip() or 'A'} - {str(title or '주제없음').strip() or '주제없음'}"


def _boundary_row_fps(rows: Iterable[dict[str, Any]] | None, default: float = 30.0) -> float:
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        for key in ("fps", "frame_rate", "timeline_frame_rate"):
            try:
                value = float(row.get(key) or 0.0)
            except Exception:
                value = 0.0
            if value > 1.0:
                return normalize_fps(value)
    return normalize_fps(default)


def resolve_cut_boundary_fps(
    rows: Iterable[dict[str, Any]] | None = None,
    *,
    files: list[str] | None = None,
    default: float = 30.0,
) -> float:
    fps = _boundary_row_fps(rows, default=default)
    if fps > 1.0 and fps != normalize_fps(default):
        return fps
    for path in list(files or []):
        try:
            info = probe_media(path)
            value = float(info.get("fps", 0.0) or 0.0)
        except Exception:
            value = 0.0
        if value > 1.0:
            return normalize_fps(value)
    return fps


def build_initial_middle_segment(
    *,
    media_duration: float,
    fps: float,
    major_id: str = "A",
) -> list[dict[str, Any]]:
    fps_value = resolve_cut_boundary_fps([], default=fps)
    duration_frame = max(0, sec_to_frame(max(0.0, float(media_duration or 0.0)), fps_value))
    if duration_frame <= 0:
        return []
    major_id = str(major_id or "A").strip().upper() or "A"
    title = "주제없음"
    display_label = _segment_display_label(major_id, title)
    end_sec = frame_to_sec(duration_frame, fps_value)
    return [
        {
            "id": major_id,
            "segment_id": major_id,
            "chapter_id": major_id,
            "major_id": major_id,
            "internal_id": f"cut_topicless_middle_{major_id}",
            "source_id": f"cut_topicless_middle_{major_id}",
            "fps": fps_value,
            "frame_rate": fps_value,
            "timeline_frame_rate": fps_value,
            "start_frame": 0,
            "end_frame": duration_frame,
            "timeline_start_frame": 0,
            "timeline_end_frame": duration_frame,
            "frame_range": {
                "unit": "frame",
                "start": 0,
                "end": duration_frame,
                "timeline_frame_rate": fps_value,
            },
            "start": 0.0,
            "end": end_sec,
            "timeline_start": 0.0,
            "timeline_end": end_sec,
            "title": title,
            "name": title,
            "display_title": display_label,
            "display_name": display_label,
            "label": display_label,
            "summary": "컷 경계 검토 전 전체 영상을 감싸는 초기 중분류입니다.",
            "llm_summary": "",
            "tags": ["컷경계", "초기중분류", "주제없음"],
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
            "cut_boundary_middle_stage": "initial_placeholder",
            "color_role": "topicless",
            "display_color": "gray",
            "ui_color": "gray",
            "color": INITIAL_MIDDLE_BORDER_COLOR,
            "border_color": INITIAL_MIDDLE_BORDER_COLOR,
            "border_width": 1,
            "border_style": "rounded_outline",
            "fill_alpha": 0,
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
    ]


def build_provisional_visual_scan_profile(*, sample_step_sec: float | None = None) -> dict[str, Any]:
    profile = dict(PROVISIONAL_VISUAL_SCAN_PROFILE)
    if sample_step_sec is not None:
        try:
            profile["sample_step_sec"] = max(0.25, float(sample_step_sec))
        except Exception:
            pass
    return profile


def build_provisional_native_settings(
    settings: dict[str, Any] | None,
    *,
    sample_step_sec: float | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    tuned = dict(settings or {})
    profile = build_provisional_visual_scan_profile(sample_step_sec=sample_step_sec)

    def _safe_float(key: str, default: float) -> float:
        try:
            return float(tuned.get(key, default) or default)
        except Exception:
            return float(default)

    def _safe_int(key: str, default: int) -> int:
        try:
            return int(tuned.get(key, default) or default)
        except Exception:
            return int(default)

    tuned["scan_cut_boundary_level"] = "low"
    tuned["cut_boundary_level"] = "low"
    tuned["scan_cut_level"] = "low"
    tuned["scan_cut_compare_max_width"] = PROVISIONAL_VISUAL_COMPARE_WIDTH
    tuned["scan_cut_compare_max_height"] = PROVISIONAL_VISUAL_COMPARE_HEIGHT
    tuned["scan_cut_pioneer_min_gap_sec"] = max(
        0.20,
        min(_safe_float("scan_cut_pioneer_min_gap_sec", PROVISIONAL_PIONEER_MIN_GAP_SEC), PROVISIONAL_PIONEER_MIN_GAP_SEC),
    )
    tuned["scan_cut_pioneer_packet_min_gap_sec"] = max(
        0.10,
        min(_safe_float("scan_cut_pioneer_packet_min_gap_sec", PROVISIONAL_PACKET_MIN_GAP_SEC), PROVISIONAL_PACKET_MIN_GAP_SEC),
    )
    tuned["scan_cut_pioneer_packet_bucket_sec"] = max(
        0.10,
        min(_safe_float("scan_cut_pioneer_packet_bucket_sec", PROVISIONAL_PACKET_BUCKET_SEC), PROVISIONAL_PACKET_BUCKET_SEC),
    )
    tuned["scan_cut_pioneer_packet_scout_raw_candidates"] = max(
        PROVISIONAL_PACKET_RAW_CANDIDATES,
        _safe_int("scan_cut_pioneer_packet_scout_raw_candidates", PROVISIONAL_PACKET_RAW_CANDIDATES),
    )
    tuned["scan_cut_boundary_resolved_level"] = str(profile.get("level") or "low")
    tuned["scan_cut_boundary_resolved_mask"] = str(profile.get("mask") or "")
    return tuned, profile


def build_follower_review_scan_profile() -> dict[str, Any]:
    return dict(FOLLOWER_REVIEW_SCAN_PROFILE)


def build_follower_native_verify_settings(
    settings: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    tuned = dict(settings or {})
    profile = build_follower_review_scan_profile()
    def _safe_int(key: str, default: int) -> int:
        try:
            return int(tuned.get(key, default) or default)
        except Exception:
            return int(default)

    def _safe_float(key: str, default: float) -> float:
        try:
            return float(tuned.get(key, default) or default)
        except Exception:
            return float(default)

    tuned["scan_cut_compare_max_width"] = FOLLOWER_VERIFY_COMPARE_WIDTH
    tuned["scan_cut_compare_max_height"] = FOLLOWER_VERIFY_COMPARE_HEIGHT
    tuned["scan_cut_auto_verify_rollback_window_sec"] = max(
        1.0,
        _safe_float("scan_cut_auto_verify_rollback_window_sec", 1.0),
    )
    tuned["scan_cut_auto_verify_forward_window_sec"] = max(
        1.0,
        _safe_float("scan_cut_auto_verify_forward_window_sec", 1.0),
    )
    tuned["scan_cut_auto_verify_window_stages"] = [21, 11, 5, 2, 1]
    tuned["scan_cut_color_avg_window_frames"] = max(
        17,
        _safe_int("scan_cut_color_avg_window_frames", 17),
    )
    tuned["scan_cut_dense_flow_width"] = max(
        448,
        _safe_int("scan_cut_dense_flow_width", 448),
    )
    tuned["scan_cut_dense_flow_window_radius"] = max(
        3,
        _safe_int("scan_cut_dense_flow_window_radius", 3),
    )
    tuned["scan_cut_dense_flow_backend"] = str(tuned.get("scan_cut_dense_flow_backend") or "dis")
    tuned["scan_cut_sample_width"] = max(15, _safe_int("scan_cut_sample_width", 18))
    tuned["scan_cut_sample_height"] = max(9, _safe_int("scan_cut_sample_height", 10))
    tuned["scan_cut_target_samples"] = max(64, _safe_int("scan_cut_target_samples", 81))
    tuned["scan_cut_dense_flow_motion_votes_required"] = max(
        4,
        _safe_int("scan_cut_dense_flow_motion_votes_required", 4),
    )
    tuned["scan_cut_follower_strict_multiplier"] = max(
        1.20,
        _safe_float("scan_cut_follower_strict_multiplier", 1.20),
    )
    tuned["scan_cut_follower_gray_agreement_frames"] = max(
        3,
        _safe_int("scan_cut_follower_gray_agreement_frames", 4),
    )
    tuned["scan_cut_follower_gray_color_agreement_frames"] = max(
        3,
        _safe_int("scan_cut_follower_gray_color_agreement_frames", 5),
    )
    tuned["scan_cut_follower_local_color_confirm_frames"] = max(
        2,
        _safe_int("scan_cut_follower_local_color_confirm_frames", 6),
    )
    tuned["scan_cut_follower_same_scene_color_enabled"] = bool(
        tuned.get("scan_cut_follower_same_scene_color_enabled", True)
    )
    tuned["scan_cut_follower_same_scene_color_max_score"] = min(
        _safe_float("scan_cut_follower_same_scene_color_max_score", 11.0),
        11.0,
    )
    tuned["scan_cut_follower_same_scene_color_max_luma_delta"] = min(
        _safe_float("scan_cut_follower_same_scene_color_max_luma_delta", 9.0),
        9.0,
    )
    tuned["scan_cut_follower_same_scene_color_max_chroma_delta"] = min(
        _safe_float("scan_cut_follower_same_scene_color_max_chroma_delta", 8.5),
        8.5,
    )
    tuned["scan_cut_follower_gray_dominance_margin"] = max(
        0.10,
        _safe_float("scan_cut_follower_gray_dominance_margin", 0.20),
    )
    tuned["scan_cut_native_peak_bonus_scale"] = max(
        0.05,
        _safe_float("scan_cut_native_peak_bonus_scale", 0.22),
    )
    tuned["scan_cut_native_peak_contrast_scale"] = max(
        0.05,
        _safe_float("scan_cut_native_peak_contrast_scale", 0.16),
    )
    tuned["scan_cut_native_peak_sharpness_scale"] = max(
        0.02,
        _safe_float("scan_cut_native_peak_sharpness_scale", 0.08),
    )
    tuned["scan_cut_boundary_resolved_level"] = str(profile.get("level") or "follower")
    tuned["scan_cut_boundary_resolved_mask"] = str(profile.get("mask") or "")
    tuned["scan_cut_follower_fast_verify_active"] = True
    return tuned, profile


def provisional_boundary_row(row: dict[str, Any]) -> dict[str, Any]:
    styled = dict(row or {})
    styled["status"] = "provisional"
    styled.setdefault("detector_stage", "pioneer")
    styled["line_width"] = 1
    styled["line_render"] = "line"
    styled["follower_active"] = False
    if is_audio_gain_boundary(styled):
        styled.setdefault("source", "audio_gain_provisional")
        styled["boundary_kind"] = "audio"
        styled["line_color"] = str(styled.get("line_color") or AUDIO_GAIN_LINE_COLOR)
        styled["line_style"] = "solid"
    else:
        styled.setdefault("source", "visual_provisional")
        styled["boundary_kind"] = "visual"
        styled["line_color"] = str(styled.get("line_color") or VISUAL_PROVISIONAL_LINE_COLOR)
        styled["line_style"] = "solid"
    return styled


def checked_provisional_boundary_row(row: dict[str, Any], *, verified: bool = False) -> dict[str, Any]:
    checked = provisional_boundary_row(row)
    checked["status"] = "checked"
    checked["detector_stage"] = "follower_checked"
    checked["scan_checked"] = True
    checked["verified"] = bool(verified or checked.get("verified"))
    checked["confirmed"] = bool(verified or checked.get("confirmed"))
    checked["line_color"] = FOLLOWER_CHECKED_LINE_COLOR
    checked["line_style"] = "dotted"
    checked["line_width"] = 1
    checked["line_render"] = "line"
    checked["follower_active"] = False
    return checked


def reviewed_middle_source_rows(
    provisional_rows: Iterable[dict[str, Any]] | None,
    *,
    detected_rows: Iterable[dict[str, Any]] | None = None,
    candidate_key_resolver=None,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _row_key(row: dict[str, Any]) -> str:
        if callable(candidate_key_resolver):
            try:
                key = str(candidate_key_resolver(row) or "")
            except Exception:
                key = ""
            if key:
                return key
        try:
            frame = int(row.get("timeline_frame", row.get("frame", row.get("start_frame", row.get("timeline_start_frame", -1)))) or -1)
        except Exception:
            frame = -1
        try:
            sec = float(row.get("timeline_sec", row.get("time", row.get("start", 0.0))) or 0.0)
        except Exception:
            sec = 0.0
        return f"{frame}:{sec:.3f}:{str(row.get('source') or '')}"

    for row in list(detected_rows or []) + list(provisional_rows or []):
        if not isinstance(row, dict):
            continue
        status = str(row.get("status", "") or "").strip().lower()
        audio_checked = bool(is_audio_gain_boundary(row) and row.get("scan_checked"))
        relocated_support = bool(row.get("follower_relocated") or row.get("rollback_relocated"))
        middle_merge_preferred = bool(
            row.get("middle_merge_preferred")
            or row.get("same_scene_color_similarity")
        )
        strict_reviewed = bool(
            row.get("verified")
            or row.get("confirmed")
            or row.get("visual_verify_skipped")
            or status in FOLLOWER_FINAL_BOUNDARY_STATUSES
        )
        if audio_checked and middle_merge_preferred and not strict_reviewed:
            continue
        is_reviewed = bool(
            strict_reviewed
            or audio_checked
            or relocated_support
        )
        if not is_reviewed:
            continue
        item = dict(row)
        key = str(item.get("candidate_key") or _row_key(item))
        if key in seen:
            continue
        seen.add(key)
        item.setdefault("candidate_key", key)
        if relocated_support and not strict_reviewed and not audio_checked:
            item["middle_snap_only"] = True
        merged.append(item)
    return merged


def follower_middle_segment_rows(
    boundary_rows: Iterable[dict[str, Any]] | None,
    *,
    media_duration: float | None = None,
    include_trailing: bool = True,
    prefer_all_boundary_frames: bool = False,
) -> list[dict[str, Any]]:
    rows = build_topicless_middle_segments(
        list(boundary_rows or []),
        media_duration=media_duration,
        include_trailing=bool(include_trailing),
        prefer_all_boundary_frames=bool(prefer_all_boundary_frames),
    )
    out: list[dict[str, Any]] = []
    for index, row in enumerate(list(rows or []), start=1):
        item = dict(row)
        major_id = str(item.get("major_id") or item.get("segment_id") or item.get("id") or chr(64 + index)).strip().upper()
        title = _segment_title(item)
        display_label = _segment_display_label(major_id, title)
        color = _major_color(major_id, index - 1)
        item.update(
            {
                "id": major_id,
                "segment_id": major_id,
                "chapter_id": major_id,
                "major_id": major_id,
                "title": title,
                "name": title,
                "display_title": display_label,
                "display_name": display_label,
                "label": display_label,
                "summary": "후발대가 음성/영상 컷 경계를 재검토해 만든 임시 중분류 세그먼트입니다.",
                "tags": ["컷경계", "임시중분류", "주제없음"],
                "source": "cut_boundary_follower",
                "story_role": "cut_boundary_follower_provisional",
                "narrative_function": "cut_boundary_follower_middle_segment",
                "is_topicless_placeholder": False,
                "is_cut_boundary_placeholder": False,
                "topicless": True,
                "cut_boundary_middle_stage": "follower_provisional",
                "color_role": "cut_boundary_follower",
                "display_color": color,
                "ui_color": color,
                "color": color,
                "border_color": color,
                "border_width": 1,
                "border_style": "rounded_outline",
                "fill_alpha": 0,
                "needs_review": True,
                "status": "provisional",
                "boundary_confidence": max(0.6, float(item.get("boundary_confidence", 0.82) or 0.82)),
            }
        )
        out.append(item)
    return out


def build_middle_segments_for_stage(
    boundary_rows: Iterable[dict[str, Any]] | None,
    *,
    media_duration: float | None = None,
    files: list[str] | None = None,
    done: bool = False,
    prefer_all_boundary_frames: bool = False,
) -> list[dict[str, Any]]:
    rows = [dict(row) for row in list(boundary_rows or []) if isinstance(row, dict)]
    if rows:
        return follower_middle_segment_rows(
            rows,
            media_duration=media_duration,
            include_trailing=bool(done),
            prefer_all_boundary_frames=bool(prefer_all_boundary_frames),
        )
    fps = resolve_cut_boundary_fps(rows, files=files, default=30.0)
    return build_initial_middle_segment(
        media_duration=max(0.0, float(media_duration or 0.0)),
        fps=fps,
    )


__all__ = [
    "AUDIO_GAIN_LINE_COLOR",
    "FOLLOWER_CHECKED_LINE_COLOR",
    "FOLLOWER_VERIFY_COMPARE_HEIGHT",
    "FOLLOWER_VERIFY_COMPARE_WIDTH",
    "INITIAL_MIDDLE_BORDER_COLOR",
    "PROVISIONAL_VISUAL_COMPARE_HEIGHT",
    "PROVISIONAL_VISUAL_COMPARE_WIDTH",
    "VISUAL_PROVISIONAL_LINE_COLOR",
    "build_follower_native_verify_settings",
    "build_follower_review_scan_profile",
    "build_initial_middle_segment",
    "build_middle_segments_for_stage",
    "build_provisional_native_settings",
    "build_provisional_visual_scan_profile",
    "checked_provisional_boundary_row",
    "follower_middle_segment_rows",
    "provisional_boundary_row",
    "resolve_cut_boundary_fps",
    "reviewed_middle_source_rows",
]
