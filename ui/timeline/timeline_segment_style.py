"""Pure style and selection helpers for timeline subtitle/STT rendering."""

from __future__ import annotations

from bisect import bisect_left, bisect_right

from core.audio.stt_candidate_scorer import stt_score_to_color
from ui.timeline.timeline_analysis import SUBTITLE_STATUS_COLORS, subtitle_review_state


SEGMENT_TEXT_KIND_STYLES = {
    "speech": {
        "fill": "#123A24",
        "border": "#34C759",
        "text": "#E8FFF0",
    },
    "silence": {
        "fill": "#3B2A13",
        "border": "#FF9500",
        "text": "#FFF1D6",
    },
}

QUALITY_SEGMENT_COLORS = {
    "green": ("#203A2A", "#34C759"),
    "yellow": ("#3B341D", "#FFCC00"),
    "red": ("#4A1F24", "#FF453A"),
    "gray": ("#2F343A", "#8E8E93"),
}

SUBTITLE_STATE_SEGMENT_COLORS = {
    "confirmed": ("#203A2A", SUBTITLE_STATUS_COLORS["confirmed"]),
    "pending": ("#3B341D", SUBTITLE_STATUS_COLORS["pending"]),
    "recheck": ("#4A1F24", SUBTITLE_STATUS_COLORS["recheck"]),
    "conflict": ("#2F343A", SUBTITLE_STATUS_COLORS["conflict"]),
}

STAGE_CONFIDENCE_COLORS = {
    "green": "#34C759",
    "yellow": "#FFCC00",
    "red": "#FF453A",
    "gray": "#8E8E93",
}

_HIDDEN_BOUNDARY_MARKER_STYLE = {"visible": False}
_FOLLOWER_FINAL_BOUNDARY_STATUSES = {"checked", "verified", "confirmed", "accepted", "done", "reviewed"}
_AUDIO_BOUNDARY_LINE_HINTS = {"#39ff14", "audio_gain", "green", "neon_green"}
_PROVISIONAL_BOUNDARY_SOURCES = {
    "audio_gain_provisional",
    "visual_provisional",
    "cut_boundary_provisional",
    "cut_boundary_follower",
}
_AUTO_CONFIRMED_BOUNDARY_SOURCES = {"visual", "visual_cut", "fused_cut_boundary", "fused"}
_AUTO_CONFIRMED_BOUNDARY_REASONS = {
    "visual_cut_boundary",
    "fused_cut_boundary",
    "audio_gain_boundary",
}


def _cut_boundary_marker_hidden_after_follower(marker) -> bool:
    if not isinstance(marker, dict):
        return False
    source = str(marker.get("source", "") or "").strip().lower()
    reason = str(marker.get("reason", "") or "").strip().lower()
    if source == "manual_verified" or reason.startswith("relative_") or reason.startswith("manual_"):
        return False
    status = str(marker.get("status", "") or "").strip().lower()
    detector = str(marker.get("detector", "") or marker.get("detector_name", "") or "").strip().lower()
    stage = str(marker.get("detector_stage", "") or "").strip().lower()
    provisional_type = str(marker.get("provisional_type", "") or "").strip().lower()
    boundary_kind = str(marker.get("boundary_kind", "") or "").strip().lower()
    line_color = str(marker.get("line_color", "") or "").strip().lower()
    audio_gain_hint = any(
        key in marker and marker.get(key) not in (None, "")
        for key in ("audio_gain_db_delta", "audio_gain_delta_db", "audio_gain_score", "audio_peak_delta_db")
    )
    terminal_reason = any(
        token in reason
        for token in ("timeline_end", "duration_end", "end_frame", "terminal")
    )
    if (
        bool(marker.get("is_terminal_boundary"))
        or bool(marker.get("terminal_boundary"))
        or bool(marker.get("timeline_end_boundary"))
        or terminal_reason
    ):
        return True
    follower_done = (
        status in _FOLLOWER_FINAL_BOUNDARY_STATUSES
        or bool(marker.get("scan_checked"))
        or bool(marker.get("verified"))
        or bool(marker.get("confirmed"))
        or bool(marker.get("follower_checked"))
        or bool(marker.get("follower_relocated"))
        or bool(marker.get("rollback_relocated"))
        or bool(marker.get("middle_merge_preferred"))
        or bool(marker.get("same_scene_color_similarity"))
        or stage in {"follower_checked", "follower_done", "follower_reviewed"}
    )
    if not follower_done:
        return False
    audio_hint = (
        source == "audio_gain_provisional"
        or audio_gain_hint
        or detector.startswith("audio-gain")
        or provisional_type == "audio_gain"
        or boundary_kind == "audio"
        or line_color in _AUDIO_BOUNDARY_LINE_HINTS
    )
    provisional_hint = (
        source in _PROVISIONAL_BOUNDARY_SOURCES
        or "provisional" in source
        or bool(marker.get("_live_cut_boundary_preview"))
        or bool(provisional_type)
    )
    auto_cut_metadata_hint = (
        reason in _AUTO_CONFIRMED_BOUNDARY_REASONS
        or reason.startswith("cut_boundary_")
        or bool(marker.get("cut_boundary_algorithm_id"))
        or bool(marker.get("cut_boundary_algorithm_version"))
        or bool(marker.get("candidate_key"))
    )
    automatic_confirmed_hint = source in _AUTO_CONFIRMED_BOUNDARY_SOURCES and auto_cut_metadata_hint
    return bool(audio_hint or provisional_hint or automatic_confirmed_hint)


def subtitle_confidence_chips(seg: dict) -> list[dict]:
    confidence = dict(seg.get("subtitle_stage_confidence") or {})
    stages = dict(confidence.get("stages") or {})
    order = list(confidence.get("stage_order") or ["cut", "stt", "llm", "lora", "final"])
    labels = {
        "cut": "컷",
        "stt": "STT",
        "llm": "LLM",
        "lora": "LoRA",
        "final": "최종",
    }
    chips = []
    for stage in order:
        item = dict(stages.get(stage) or {})
        if not item:
            continue
        label = str(item.get("label") or "gray").strip().lower()
        chips.append(
            {
                "stage": stage,
                "text": labels.get(stage, str(stage).upper()),
                "label": label,
                "score": item.get("score"),
                "reason": item.get("reason", ""),
                "color": STAGE_CONFIDENCE_COLORS.get(label, STAGE_CONFIDENCE_COLORS["gray"]),
            }
        )
    return chips


def subtitle_render_detail_mode(
    *,
    visible_segment_count: int,
    pps: float,
    editing: bool = False,
    scenegraph: bool = False,
    playback_active: bool = False,
) -> str:
    """Return a lightweight subtitle paint mode for dense timelines."""
    if scenegraph:
        return "gpu"
    if editing:
        return "full"
    count = max(0, int(visible_segment_count or 0))
    zoom = max(0.0, float(pps or 0.0))
    # Playback must not remove labels that are readable while paused. Keep text
    # detail based on density/zoom only so subtitle segments remain legible.
    if playback_active:
        return "full"
    if count >= 180 or (count >= 72 and zoom < 24.0) or (count >= 32 and zoom < 10.0):
        return "ultra"
    if count >= 56 or (count >= 28 and zoom < 40.0):
        return "dense"
    return "full"


def cut_boundary_scan_marker_verified(marker) -> bool:
    if not isinstance(marker, dict):
        return False
    status = str(marker.get("status", "") or "").strip().lower()
    return (
        status in {"verified", "confirmed", "accepted", "done", "checked", "reviewed"}
        or bool(marker.get("verified"))
        or bool(marker.get("confirmed"))
        or bool(marker.get("scan_checked"))
    )


def scan_boundary_marker_visual(marker, *, hover: bool = False) -> dict:
    if _cut_boundary_marker_hidden_after_follower(marker):
        return dict(_HIDDEN_BOUNDARY_MARKER_STYLE)
    if hover:
        return {"color": "#00B7FF", "width": 3, "style": "solid"}
    if isinstance(marker, dict):
        status = str(marker.get("status", "") or "").strip().lower()
        stage = str(marker.get("detector_stage", "") or "").strip().lower()
        if (
            status in {"verifying", "checking", "follower", "follower_verifying"}
            or stage == "follower"
            or bool(marker.get("follower_active"))
        ):
            return {"color": "#FFCC00", "width": 2, "style": "dash"}
    if cut_boundary_scan_marker_verified(marker):
        return {"color": "#8E8E93", "width": 1, "style": "dot"}
    if isinstance(marker, dict):
        raw_color = str(marker.get("line_color", "") or "").strip()
        color_aliases = {
            "audio_gain": "#39FF14",
            "green": "#39FF14",
            "gray": "#8E8E93",
            "grey": "#8E8E93",
            "cyan": "#00B7FF",
            "neon_green": "#39FF14",
            "neon_blue": "#00B7FF",
        }
        color = color_aliases.get(raw_color.lower(), raw_color)
        if color:
            raw_style = str(marker.get("line_style", "") or "solid").strip().lower()
            style_aliases = {
                "dashed": "dash",
                "dash": "dash",
                "dotted": "dot",
                "dot": "dot",
            }
            style = style_aliases.get(raw_style, "solid")
            width = 1
            return {"color": color, "width": width, "style": style}
    return {"color": "#00B7FF", "width": 1, "style": "solid"}


def official_boundary_marker_visual(marker) -> dict:
    if isinstance(marker, dict):
        source = str(marker.get("source", "") or "").strip().lower()
        reason = str(marker.get("reason", "") or "").strip().lower()
        if source == "manual_verified" or reason.startswith("relative_") or reason.startswith("manual_"):
            raw_color = str(marker.get("line_color", "") or "").strip() or "#7FDBFF"
            return {"color": raw_color, "width": 2, "style": "solid"}
        if _cut_boundary_marker_hidden_after_follower(marker):
            return dict(_HIDDEN_BOUNDARY_MARKER_STYLE)
        status = str(marker.get("status", "") or "").strip().lower()
        provisional_type = str(marker.get("provisional_type", "") or "").strip().lower()
        boundary_kind = str(marker.get("boundary_kind", "") or "").strip().lower()
        line_color = str(marker.get("line_color", "") or "").strip().lower()
        stale_audio_visual = (
            source in {"visual", "visual_cut", "fused_cut_boundary", "fused"}
            and (status in {"verified", "confirmed", "accepted", "done"} or bool(marker.get("verified") or marker.get("confirmed")))
            and (
                provisional_type == "audio_gain"
                or boundary_kind == "audio"
                or line_color in {"#39ff14", "audio_gain", "green", "neon_green"}
            )
        )
        if stale_audio_visual:
            return dict(_HIDDEN_BOUNDARY_MARKER_STYLE)
        raw_color = str(marker.get("line_color", "") or "").strip()
        if raw_color:
            color_aliases = {
                "white": "#F5F7FA",
                "light": "#F5F7FA",
                "gray": "#D0D7DE",
                "grey": "#D0D7DE",
            }
            color = color_aliases.get(raw_color.lower(), raw_color)
            return {"color": color or "#F5F7FA", "width": 1, "style": "solid"}
    return {"color": "#F5F7FA", "width": 1, "style": "solid"}


def scan_boundary_marker_label(marker) -> str:
    # 컷 경계는 전부 1px 선으로만 보여야 하므로 작업 라벨 박스를 붙이지 않는다.
    _ = marker
    return ""


def segment_text_kind(text: str) -> str:
    raw = str(text or "")
    if raw == "음성":
        return "speech"
    if raw == "무음":
        return "silence"
    if len(raw) <= 8:
        normalized = "".join(raw.split())
        if normalized == "음성":
            return "speech"
        if normalized == "무음":
            return "silence"
    return ""


def _normalize_quality_filter(value: str) -> str:
    raw = str(value or "all").strip().lower()
    aliases = {
        "": "all",
        "all": "all",
        "전체": "all",
        "green": "green",
        "초록": "green",
        "confirmed": "green",
        "yellow": "yellow",
        "노랑": "yellow",
        "pending": "yellow",
        "red": "red",
        "빨강": "red",
        "gray": "gray",
        "grey": "gray",
        "회색": "gray",
        "needs_review": "needs_review",
        "확인 필요": "needs_review",
        "auto_corrected": "auto_corrected",
        "자동 교정됨": "auto_corrected",
    }
    return aliases.get(raw, "all")


_REVIEW_QUALITY_FLAGS = frozenset(
    {"non_speech_hallucination_risk", "high_no_speech_prob", "outside_vad_speech"}
)


def _quality_flags_tuple(flags) -> tuple[str, ...]:
    if not flags:
        return ()
    if isinstance(flags, str):
        return (flags,)
    if isinstance(flags, tuple) and all(isinstance(flag, str) for flag in flags):
        return flags
    return tuple(str(flag) for flag in flags)


def _quality_filter_matches(
    quality: dict,
    q_label: str,
    q_filter: str,
    q_flags: tuple[str, ...] | None = None,
) -> bool:
    q_filter = _normalize_quality_filter(q_filter)
    if q_filter == "all" or q_filter == q_label:
        return True
    flags = _quality_flags_tuple(quality.get("flags") or ()) if q_flags is None else q_flags
    if q_filter == "needs_review":
        return q_label in {"red", "gray"} or any(flag in _REVIEW_QUALITY_FLAGS for flag in flags)
    if q_filter == "auto_corrected":
        return "auto_corrected" in flags
    return False


def subtitle_segment_visual_style(
    seg: dict,
    *,
    active: bool = False,
    hover: bool = False,
    quality_filter: str = "all",
) -> dict:
    """Return zoom-stable subtitle segment colors."""
    is_stt_pending = bool(seg.get("stt_pending"))
    quality = seg.get("quality") or {}
    q_label = str(quality.get("confidence_label") or "")
    kind_style = SEGMENT_TEXT_KIND_STYLES.get(segment_text_kind(seg.get("text", "")), {})
    review_state = subtitle_review_state(seg)
    q_filter = _normalize_quality_filter(quality_filter)
    q_flags = _quality_flags_tuple(quality.get("flags") or ()) if quality and q_filter != "all" else ()
    manually_confirmed = bool(quality.get("manual_confirmed")) or bool(q_flags and "manual_confirmed" in q_flags)
    muted_by_filter = (
        bool(quality)
        and not manually_confirmed
        and q_filter != "all"
        and not _quality_filter_matches(quality, q_label, q_filter, q_flags)
    )

    if review_state in SUBTITLE_STATE_SEGMENT_COLORS and not kind_style and not is_stt_pending:
        fill, border = SUBTITLE_STATE_SEGMENT_COLORS[review_state]
        text = ""
    elif kind_style:
        fill = kind_style["fill"]
        border = kind_style["border"]
        text = kind_style.get("text", "")
    elif quality and q_label in QUALITY_SEGMENT_COLORS:
        fill, border = QUALITY_SEGMENT_COLORS[q_label]
        text = ""
    else:
        fill = "#4A1F24" if is_stt_pending else ("#1D3D76" if active else ("#222A31" if hover else "#242A30"))
        border = "#FF453A" if is_stt_pending else ("#8AB8FF" if active else "#3A4650")
        text = ""

    if muted_by_filter:
        fill = "#1A2025"
        border = "#2D3942"

    return {"fill": fill, "border": border, "text": text, "muted": muted_by_filter}


def subtitle_segment_style_cache_key(seg: dict, *, render_epoch: int, quality_filter: str) -> tuple:
    quality = seg.get("quality") or {}
    flags = quality.get("flags") or ()
    return (
        id(seg),
        int(render_epoch),
        str(quality_filter or "all"),
        bool(seg.get("stt_pending")),
        segment_text_kind(seg.get("text", "")),
        str(quality.get("confidence_label", "") or ""),
        quality.get("confidence_score"),
        bool(quality.get("manual_confirmed")),
        _quality_flags_tuple(flags),
        str(seg.get("subtitle_auto_review_severity", "") or ""),
        str(seg.get("subtitle_confidence_label", "") or ""),
        str(seg.get("stt_selected_source", "") or ""),
        str(seg.get("stt_ensemble_llm_selected_source", "") or ""),
        bool(seg.get("stt_ensemble_needs_llm_review")),
        len(seg.get("stt_candidates") or ()),
    )


def stt_preview_source(seg: dict) -> str:
    source = (
        seg.get("stt_preview_source")
        or seg.get("stt_source")
        or seg.get("stt_ensemble_source")
        or ""
    )
    return str(source or "").strip().upper()


def stt_preview_visual_style(
    seg: dict,
    *,
    selection_state: str = "",
    fill_hex: str = "#173524",
    border_hex: str = "#34C759",
    text_hex: str = "#D7FFE4",
) -> dict:
    """Return STT candidate lane colors; unselected candidates still keep score color."""
    quality = dict(seg.get("quality") or {})
    score = seg.get("stt_score", seg.get("score", quality.get("confidence_score")))
    score_hex = str(seg.get("score_color") or seg.get("stt_score_color") or "")
    if not score_hex:
        try:
            score_hex = stt_score_to_color(float(score))
        except Exception:
            score_hex = ""
    state = str(selection_state or "")
    is_selected = state in {"manual", "llm"}
    is_unselected = state == "unselected"
    fill = score_hex or fill_hex
    border = "#FFCC00" if state == "llm" else ("#FFFFFF" if is_selected else (score_hex or border_hex))
    return {
        "fill": fill,
        "border": border,
        "text": "#C9D0D6" if is_unselected else text_hex,
        "alpha": 96 if is_unselected else 142,
        "border_width": 2 if is_selected else 1,
        "score_color": score_hex,
    }


def _segment_overlap_ratio(left: dict, right: dict) -> float:
    try:
        l_start = float(left.get("start", 0.0) or 0.0)
        l_end = float(left.get("end", l_start) or l_start)
        r_start = float(right.get("start", 0.0) or 0.0)
        r_end = float(right.get("end", r_start) or r_start)
    except Exception:
        return 0.0
    overlap = max(0.0, min(l_end, r_end) - max(l_start, r_start))
    base = max(0.001, min(max(0.001, l_end - l_start), max(0.001, r_end - r_start)))
    return overlap / base


def build_stt_selection_index(final_segments: list[dict]) -> dict:
    """Build a time index for STT preview-vs-final selection lookups."""
    rows: list[tuple[float, float, dict, str, str, str]] = []
    max_span = 0.0
    for final in final_segments or []:
        if not isinstance(final, dict):
            continue
        manual_source = str(final.get("stt_selected_source", "") or "").strip().upper()
        llm_source = str(final.get("stt_ensemble_llm_selected_source", "") or "").strip().upper()
        selected_source = manual_source or llm_source
        if selected_source not in {"STT1", "STT2"}:
            continue
        try:
            start = float(final.get("start", 0.0) or 0.0)
            end = float(final.get("end", start) or start)
        except Exception:
            continue
        if end < start:
            start, end = end, start
        max_span = max(max_span, max(0.0, end - start))
        rows.append((start, end, final, manual_source, llm_source, selected_source))
    rows.sort(key=lambda item: (item[0], item[1], id(item[2])))
    return {
        "rows": rows,
        "starts": [row[0] for row in rows],
        "max_span": float(max_span),
    }


def stt_candidate_selection_state(
    candidate: dict,
    final_segments: list[dict],
    selection_index: dict | None = None,
) -> str:
    candidate_source = stt_preview_source(candidate)
    if candidate_source not in {"STT1", "STT2"}:
        return ""
    candidate_text = "".join(str(candidate.get("text", "") or "").split())
    try:
        cand_start = float(candidate.get("start", 0.0) or 0.0)
        cand_end = float(candidate.get("end", cand_start) or cand_start)
    except Exception:
        cand_start = cand_end = 0.0
    if cand_end < cand_start:
        cand_start, cand_end = cand_end, cand_start

    if isinstance(selection_index, dict):
        rows = selection_index.get("rows") or ()
        starts = selection_index.get("starts") or ()
        max_span = max(0.0, float(selection_index.get("max_span", 0.0) or 0.0))
        if not rows or not starts:
            return ""
        left = bisect_left(starts, max(0.0, cand_start - max_span))
        right = bisect_right(starts, cand_end)
        iterable = rows[left:right]
        if not iterable:
            return ""
    else:
        iterable = []
        for final in final_segments or []:
            manual_source = str(final.get("stt_selected_source", "") or "").strip().upper()
            llm_source = str(final.get("stt_ensemble_llm_selected_source", "") or "").strip().upper()
            selected_source = manual_source or llm_source
            if selected_source not in {"STT1", "STT2"}:
                continue
            try:
                start = float(final.get("start", 0.0) or 0.0)
                end = float(final.get("end", start) or start)
            except Exception:
                continue
            if end < start:
                start, end = end, start
            iterable.append((start, end, final, manual_source, llm_source, selected_source))

    for final_start, final_end, final, manual_source, llm_source, selected_source in iterable:
        overlap = max(0.0, min(cand_end, final_end) - max(cand_start, final_start))
        base = max(0.001, min(max(0.001, cand_end - cand_start), max(0.001, final_end - final_start)))
        if overlap / base < 0.20:
            continue
        selected_by_this_source = selected_source == candidate_source
        final_candidates = list(final.get("stt_candidates") or [])
        if selected_by_this_source and final_candidates:
            for item in final_candidates:
                if str(item.get("source", "") or "").strip().upper() != candidate_source:
                    continue
                selected_text = "".join(str(item.get("text", "") or "").split())
                if not candidate_text or not selected_text or candidate_text == selected_text:
                    return "manual" if manual_source else "llm"
            return "unselected"
        if selected_by_this_source:
            return "manual" if manual_source else "llm"
        return "unselected"
    return ""


def stt_candidate_selected_by_llm(candidate: dict, final_segments: list[dict]) -> bool:
    return stt_candidate_selection_state(candidate, final_segments) == "llm"


def stt_candidate_selected(candidate: dict, final_segments: list[dict]) -> bool:
    return stt_candidate_selection_state(candidate, final_segments) in {"manual", "llm"}


def stt_candidate_unselected(candidate: dict, final_segments: list[dict]) -> bool:
    return stt_candidate_selection_state(candidate, final_segments) == "unselected"


def final_stt_selection_source(seg: dict) -> str:
    manual_source = str(seg.get("stt_selected_source", "") or "").strip().upper()
    llm_source = str(seg.get("stt_ensemble_llm_selected_source", "") or "").strip().upper()
    selected_source = manual_source or llm_source
    return selected_source if selected_source in {"STT1", "STT2"} else ""


__all__ = [
    "SEGMENT_TEXT_KIND_STYLES",
    "QUALITY_SEGMENT_COLORS",
    "SUBTITLE_STATE_SEGMENT_COLORS",
    "STAGE_CONFIDENCE_COLORS",
    "build_stt_selection_index",
    "cut_boundary_scan_marker_verified",
    "official_boundary_marker_visual",
    "final_stt_selection_source",
    "scan_boundary_marker_label",
    "scan_boundary_marker_visual",
    "segment_text_kind",
    "stt_candidate_selected",
    "stt_candidate_selected_by_llm",
    "stt_candidate_selection_state",
    "stt_candidate_unselected",
    "stt_preview_source",
    "stt_preview_visual_style",
    "subtitle_confidence_chips",
    "subtitle_render_detail_mode",
    "subtitle_segment_style_cache_key",
    "subtitle_segment_visual_style",
]
