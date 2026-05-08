# Version: 03.14.31
# Phase: PHASE2
"""
ui/timeline_paint.py
Timeline paint mixin
"""
from bisect import bisect_left, bisect_right

import numpy as np
from PyQt6.QtCore import QPoint, QRect, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygon
from PyQt6.QtWidgets import QScrollArea

from core.audio.stt_candidate_scorer import stt_score_to_color
from core.runtime import config

from ui.timeline.timeline_constants import (
    ANALYSIS_BOT,
    ANALYSIS_TOP,
    CANVAS_H,
    DIAMOND_Y,
    HANDLE_R,
    ICON_SZ,
    LANE_LABEL_GUTTER_W,
    RULER_H,
    SEG_BOT,
    SEG_TOP,
    SEGMENT_HANDLE_MIN_WIDTH,
    SPEAKER_BOT,
    SPEAKER_TOP,
    STT1_BOT,
    STT1_TOP,
    STT2_BOT,
    STT2_TOP,
    SUBTITLE_BOT,
    SUBTITLE_TOP,
    VOICE_ACTIVITY_BOT,
    VOICE_ACTIVITY_TOP,
    WAVE_H,
    WAVE_HALF,
    WAVE_MID,
)
from ui.timeline.timeline_analysis import (
    SUBTITLE_STATUS_COLORS,
    analysis_markers_for_widget,
    roughcut_major_markers_for_widget,
    subtitle_review_state,
)
from ui.timeline.speaker_labels import (
    current_speaker_settings,
    normalize_speaker_id,
    speaker_labels_for_segment,
)

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
) -> str:
    """Return a lightweight subtitle paint mode for dense timelines."""
    if scenegraph:
        return "gpu"
    if editing:
        return "full"
    count = max(0, int(visible_segment_count or 0))
    zoom = max(0.0, float(pps or 0.0))
    if count >= 220 or (count >= 120 and zoom < 18.0):
        return "ultra"
    if count >= 80 or (count >= 48 and zoom < 36.0):
        return "dense"
    return "full"


def cut_boundary_scan_marker_verified(marker) -> bool:
    if not isinstance(marker, dict):
        return False
    status = str(marker.get("status", "") or "").strip().lower()
    return (
        status in {"verified", "confirmed", "accepted", "done"}
        or bool(marker.get("verified"))
        or bool(marker.get("confirmed"))
    )


def scan_boundary_marker_visual(marker, *, hover: bool = False) -> dict:
    if hover:
        return {"color": "#00FFFF", "width": 3, "style": "solid"}
    if cut_boundary_scan_marker_verified(marker):
        return {"color": "#8E8E93", "width": 1, "style": "dot"}
    if isinstance(marker, dict):
        raw_color = str(marker.get("line_color", "") or "").strip()
        color_aliases = {
            "audio_gain": "#39FF14",
            "green": "#39FF14",
            "gray": "#8E8E93",
            "grey": "#8E8E93",
            "cyan": "#00FFFF",
            "neon_green": "#39FF14",
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
            width = 3 if color.upper() == "#39FF14" else 2
            return {"color": color, "width": width, "style": style}
    return {"color": "#00FFFF", "width": 2, "style": "solid"}


def segment_text_kind(text: str) -> str:
    normalized = "".join(str(text or "").split())
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


def _quality_filter_matches(quality: dict, q_label: str, q_filter: str) -> bool:
    q_filter = _normalize_quality_filter(q_filter)
    q_flags = set(quality.get("flags") or ())
    return (
        q_filter == "all"
        or q_filter == q_label
        or (
            q_filter == "needs_review"
            and (
                q_label in {"red", "gray"}
                or bool(
                    q_flags.intersection(
                        {"non_speech_hallucination_risk", "high_no_speech_prob", "outside_vad_speech"}
                    )
                )
            )
        )
        or (q_filter == "auto_corrected" and "auto_corrected" in q_flags)
    )


def subtitle_segment_visual_style(
    seg: dict,
    *,
    active: bool = False,
    hover: bool = False,
    quality_filter: str = "all",
) -> dict:
    """Return zoom-stable subtitle segment colors."""
    is_stt_pending = bool(seg.get("stt_pending"))
    quality = dict(seg.get("quality") or {})
    q_label = str(quality.get("confidence_label") or "")
    q_flags = set(str(flag) for flag in (quality.get("flags") or ()))
    manually_confirmed = bool(quality.get("manual_confirmed")) or "manual_confirmed" in q_flags
    kind_style = SEGMENT_TEXT_KIND_STYLES.get(segment_text_kind(seg.get("text", "")), {})
    review_state = subtitle_review_state(seg)
    q_filter = _normalize_quality_filter(quality_filter)
    muted_by_filter = (
        bool(quality)
        and not manually_confirmed
        and not _quality_filter_matches(quality, q_label, q_filter)
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


def stt_candidate_selection_state(candidate: dict, final_segments: list[dict]) -> str:
    candidate_source = stt_preview_source(candidate)
    if candidate_source not in {"STT1", "STT2"}:
        return ""
    candidate_text = "".join(str(candidate.get("text", "") or "").split())
    for final in final_segments or []:
        manual_source = str(final.get("stt_selected_source", "") or "").strip().upper()
        llm_source = str(final.get("stt_ensemble_llm_selected_source", "") or "").strip().upper()
        selected_source = manual_source or llm_source
        if selected_source not in {"STT1", "STT2"}:
            continue
        if _segment_overlap_ratio(candidate, final) < 0.20:
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


class TimelinePaintMixin:

    def paintEvent(self, event):
        if bool(getattr(self, "_shutdown_in_progress", False)):
            return
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        total_w = self.total_width()
        total_secs = self.total_duration + 2
        paint_clip = event.rect()
        if hasattr(self, "_viewport_paint_clip"):
            paint_clip = self._viewport_paint_clip(paint_clip)
            if paint_clip.isEmpty():
                p.end()
                return
            p.setClipRect(paint_clip)
        clip_left = max(0, paint_clip.left())
        clip_right = min(total_w, paint_clip.right() + 1)
        if hasattr(self, "_paint_time_window") and hasattr(self, "_visible_items_for_paint"):
            visible_start_sec, visible_end_sec = self._paint_time_window(paint_clip)
            visible_segments = self._visible_items_for_paint(
                getattr(self, "segments", []),
                "segments",
                visible_start_sec,
                visible_end_sec,
                pad_sec=0.35,
            )
            visible_gap_segments = self._visible_items_for_paint(
                getattr(self, "gap_segments", []),
                "gaps",
                visible_start_sec,
                visible_end_sec,
                pad_sec=0.10,
            )
            visible_vad_segments = self._visible_items_for_paint(
                getattr(self, "vad_segments", []),
                "vad",
                visible_start_sec,
                visible_end_sec,
                pad_sec=0.10,
            )
            visible_voice_activity_segments = self._visible_items_for_paint(
                getattr(self, "voice_activity_segments", []),
                "voice_activity",
                visible_start_sec,
                visible_end_sec,
                pad_sec=0.10,
            )
            visible_multiclip_boxes = self._visible_items_for_paint(
                getattr(self, "_multiclip_boxes", []),
                "multiclip_boxes",
                visible_start_sec,
                visible_end_sec,
                pad_sec=0.25,
            )
        else:
            visible_start_sec = max(0.0, clip_left / max(0.001, float(self.pps)))
            visible_end_sec = max(visible_start_sec, clip_right / max(0.001, float(self.pps)))
            visible_segments = list(getattr(self, "segments", []) or [])
            visible_gap_segments = list(getattr(self, "gap_segments", []) or [])
            visible_vad_segments = list(getattr(self, "vad_segments", []) or [])
            visible_voice_activity_segments = list(getattr(self, "voice_activity_segments", []) or [])
            visible_multiclip_boxes = list(getattr(self, "_multiclip_boxes", []) or [])
        overview_mode = float(getattr(self, "pps", 0.0) or 0.0) < 8.0
        subtitle_top = SUBTITLE_TOP
        subtitle_bot = SUBTITLE_BOT
        speaker_top = SPEAKER_TOP
        speaker_bot = SPEAKER_BOT
        voice_mid = (VOICE_ACTIVITY_TOP + VOICE_ACTIVITY_BOT) // 2
        audio_mid = (ANALYSIS_TOP + ANALYSIS_BOT) // 2
        track_bottom = SEG_BOT
        stt_preview_segments = [
            seg for seg in visible_segments
            if bool(seg.get("stt_pending") or seg.get("_live_stt_preview"))
        ]
        final_stt_segments = [
            seg for seg in visible_segments
            if not bool(seg.get("stt_pending") or seg.get("_live_stt_preview"))
        ]
        stt1_preview_segments = [seg for seg in stt_preview_segments if stt_preview_source(seg) != "STT2"]
        stt2_preview_segments = [seg for seg in stt_preview_segments if stt_preview_source(seg) == "STT2"]
        scenegraph_subtitles = bool(getattr(self, "_scenegraph_subtitle_rendering", False)) and not bool(getattr(self, "_edit_active", False))
        subtitle_detail_mode = subtitle_render_detail_mode(
            visible_segment_count=len(final_stt_segments) + len(stt_preview_segments),
            pps=float(getattr(self, "pps", 0.0) or 0.0),
            editing=bool(getattr(self, "_edit_active", False)),
            scenegraph=scenegraph_subtitles,
        )
        dense_segment_mode = subtitle_detail_mode in {"dense", "ultra"}
        ultra_dense_segment_mode = subtitle_detail_mode == "ultra"
        self._paint_density_mode = subtitle_detail_mode

        def _owner_speaker_settings():
            owner = self.parent()
            while owner and not hasattr(owner, "settings"):
                owner = owner.parent()
            return getattr(owner, "settings", {}) if owner is not None else {}

        speaker_settings = current_speaker_settings(_owner_speaker_settings())

        def _speaker_color(seg):
            spk = normalize_speaker_id(seg.get("speaker", seg.get("spk_id", "")))
            palette = {
                str(speaker_settings.get("spk1_id", "00")): str(speaker_settings.get("spk1_color", "#579DFF")),
                str(speaker_settings.get("spk2_id", "01")): str(speaker_settings.get("spk2_color", "#75C76B")),
                str(speaker_settings.get("spk3_id", "02")): str(speaker_settings.get("spk3_color", "#FF9F2F")),
            }
            return QColor(palette.get(spk, "#8E8E93"))

        def _speaker_names(seg):
            return speaker_labels_for_segment(speaker_settings, seg)

        def _draw_lane_wave(mid_y, color_top, color_bot, gain=1.0, alpha=210):
            if self._waveform is None:
                return
            wf = self._waveform
            wf_len = len(wf)
            if wf_len <= 0:
                return
            clip = paint_clip
            x_start = max(0, clip.left())
            x_end = min(total_w, clip.right() + 1)
            top = QColor(color_top); top.setAlpha(alpha)
            bot = QColor(color_bot); bot.setAlpha(alpha)
            p.setPen(QPen(QColor(255, 255, 255, 24), 1))
            p.drawLine(x_start, mid_y, x_end, mid_y)
            for x in range(x_start, x_end):
                idx = int((x / max(0.001, self.pps)) * 100)
                if idx >= wf_len:
                    break
                val = float(wf[idx])
                if val < 0.006:
                    continue
                h = max(1, min(11, int(val * 18 * gain)))
                p.setPen(QPen(top, 1)); p.drawLine(x, mid_y, x, mid_y - h)
                p.setPen(QPen(bot, 1)); p.drawLine(x, mid_y + 1, x, mid_y + h)

        def _draw_subtitle_detection_lane(mid_y):
            clip = paint_clip
            lane_top = mid_y - 12
            lane_h = 24
            p.setPen(Qt.PenStyle.NoPen)
            voice_segments = list(visible_voice_activity_segments or [])
            if not voice_segments:
                try:
                    if hasattr(self, "visible_voice_activity_segments_cached"):
                        voice_segments = self.visible_voice_activity_segments_cached(
                            visible_start_sec,
                            visible_end_sec,
                            visible_segments,
                            visible_vad_segments,
                            visible_gap_segments,
                        )
                    else:
                        from ui.timeline.timeline_analysis import subtitle_detection_segments_for_editor

                        voice_segments = subtitle_detection_segments_for_editor(
                            list(visible_segments or []),
                            list(visible_vad_segments or []),
                            list(visible_gap_segments or []),
                            float(getattr(self, "total_duration", 0.0) or 0.0),
                        )
                except Exception:
                    voice_segments = []
                if voice_segments and hasattr(self, "_visible_items_for_paint"):
                    voice_segments = self._visible_items_for_paint(
                        voice_segments,
                        "voice_activity_fallback",
                        visible_start_sec,
                        visible_end_sec,
                        pad_sec=0.10,
                    )

            fill_batches: dict[tuple[str, int], list[QRect]] = {}
            border_batches: dict[tuple[str, int], list[QRect]] = {}
            label_items = []
            for vs in voice_segments:
                x1 = self._x(float(vs.get("start", 0.0) or 0.0))
                x2 = self._x(float(vs.get("end", 0.0) or 0.0))
                if x2 < clip.left() or x1 > clip.right():
                    continue
                w = max(2, x2 - x1)
                rect = QRect(int(x1), lane_top, int(w), lane_h)
                base_color = QColor(str(vs.get("color", "#34C759") or "#34C759"))
                _append_batch(fill_batches, (base_color.name(), int(vs.get("alpha", 120) or 120)), rect)
                _append_batch(border_batches, (base_color.name(), 230), rect)
                if w >= 38 and not dense_segment_mode:
                    label_items.append((vs, x1, w))
            _draw_color_batches(fill_batches)
            _draw_color_batches(border_batches, as_pen=True)
            if label_items:
                p.setFont(QFont(config.FONT, 8, QFont.Weight.Bold))
                p.setPen(QColor("#F5F7FA"))
                for vs, x1, w in label_items:
                    p.drawText(
                        QRect(int(x1) + 5, lane_top, max(8, int(w) - 10), lane_h),
                        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                        str(vs.get("label", "") or ""),
                    )
            p.setPen(QPen(QColor(87, 157, 255, 80), 1))
            p.drawLine(max(0, clip.left()), mid_y, min(total_w, clip.right() + 1), mid_y)

        def _draw_analysis_lane(mid_y):
            lane_top = mid_y - 12
            lane_h = 24
            clip = paint_clip
            x_start = max(0, clip.left())
            x_end = min(total_w, clip.right() + 1)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#0B1418"))
            p.drawRect(QRect(x_start, lane_top, max(1, x_end - x_start), lane_h))
            p.setPen(QPen(QColor("#2D3942"), 1))
            p.drawLine(x_start, mid_y, x_end, mid_y)

            if hasattr(self, "analysis_markers_visible_cached"):
                markers = self.analysis_markers_visible_cached(
                    visible_start_sec,
                    visible_end_sec,
                    visible_segments,
                    visible_vad_segments,
                    visible_gap_segments,
                )
            elif hasattr(self, "analysis_markers_cached"):
                markers = self.analysis_markers_cached()
            else:
                markers = analysis_markers_for_widget(
                    self,
                    list(getattr(self, "segments", []) or []),
                    list(getattr(self, "vad_segments", []) or []),
                    list(getattr(self, "gap_segments", []) or []),
                    float(getattr(self, "total_duration", 0.0) or 0.0),
                )
            if markers and hasattr(self, "_visible_items_for_paint"):
                markers = self._visible_items_for_paint(
                    markers,
                    "analysis_markers",
                    visible_start_sec,
                    visible_end_sec,
                    pad_sec=0.10,
                )
            markers.sort(key=lambda item: int(item.get("priority", 0) or 0))
            fill_batches: dict[tuple[str, int], list[QRect]] = {}
            border_batches: dict[tuple[str, int], list[QRect]] = {}
            label_items = []
            for marker in markers:
                start = max(0.0, float(marker.get("start", 0.0) or 0.0))
                end = max(start, float(marker.get("end", start) or start))
                x1 = self._x(start)
                x2 = self._x(end)
                if x2 < clip.left() or x1 > clip.right():
                    continue
                w = max(2, x2 - x1)
                color = QColor(str(marker.get("color", "#8B949E")))
                rect = QRect(int(x1), lane_top + 3, int(w), lane_h - 6)
                _append_batch(fill_batches, (color.name(), int(marker.get("alpha", 120) or 120)), rect)
                _append_batch(border_batches, (color.name(), 220), rect)
                if w >= 42 and not dense_segment_mode:
                    label_items.append((marker, x1, w))
            _draw_color_batches(fill_batches)
            _draw_color_batches(border_batches, as_pen=True)
            if label_items:
                p.setPen(QColor("#F5F7FA"))
                p.setFont(QFont(config.FONT, 8, QFont.Weight.Bold))
                for marker, x1, w in label_items:
                    p.drawText(QRect(int(x1) + 4, lane_top + 2, int(w) - 8, lane_h - 4), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, str(marker.get("label", "")))

        def _draw_roughcut_major_lane():
            markers = self.roughcut_major_markers_cached() if hasattr(self, "roughcut_major_markers_cached") else roughcut_major_markers_for_widget(self)
            if not markers:
                return
            if hasattr(self, "_visible_items_for_paint"):
                markers = self._visible_items_for_paint(
                    markers,
                    "roughcut_major_markers",
                    visible_start_sec,
                    visible_end_sec,
                    pad_sec=0.10,
                )
                if not markers:
                    return
            clip = paint_clip
            lane_top = RULER_H + WAVE_H + 5
            lane_h = max(18, SEG_TOP - lane_top - 7)
            x_start = max(0, clip.left())
            x_end = min(total_w, clip.right() + 1)
            p.setPen(QPen(QColor("#2D3942"), 1))
            p.setBrush(QColor("#0B1418"))
            p.drawRect(QRect(x_start, lane_top, max(1, x_end - x_start), lane_h))
            p.setFont(QFont(config.FONT, 9, QFont.Weight.Bold))
            fill_batches: dict[tuple[str, int], list[QRect]] = {}
            border_batches: dict[str, list[QRect]] = {}
            label_items = []
            for marker in markers:
                start = max(0.0, float(marker.get("start", 0.0) or 0.0))
                end = max(start, float(marker.get("end", start) or start))
                x1 = self._x(start)
                x2 = self._x(end)
                if x2 < clip.left() or x1 > clip.right():
                    continue
                w = max(2, x2 - x1)
                color = QColor(str(marker.get("color", "#34C759")))
                rect = QRect(int(x1) + 1, lane_top + 2, max(2, int(w) - 2), lane_h - 4)
                _append_batch(fill_batches, (color.name(), int(marker.get("alpha", 48) or 48)), rect)
                _append_batch(border_batches, color.name(), rect)
                label = str(marker.get("label", "") or "")
                title = str(marker.get("title", "") or "").strip()
                text = label if w < 118 or not title else f"{label}  {title[:18]}"
                if w >= 28 and text and not dense_segment_mode:
                    label_items.append((text, color, x1, w))
            _draw_color_batches(fill_batches)
            _draw_color_batches(border_batches, as_pen=True)
            for text, color, x1, w in label_items:
                p.setPen(color.lighter(145))
                p.drawText(QRect(int(x1) + 6, lane_top, int(w) - 12, lane_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter, text)

        def _draw_lane_labels():
            scroll_area = self.parent()
            while scroll_area and not isinstance(scroll_area, QScrollArea):
                scroll_area = scroll_area.parent()
            gutter_x = int(scroll_area.horizontalScrollBar().value()) if scroll_area else 0
            gutter_w = int(LANE_LABEL_GUTTER_W)
            gutter_right = gutter_x + gutter_w
            if gutter_w <= 0 or clip_right < gutter_x or clip_left > gutter_right:
                return
            p.setPen(QPen(QColor("#2D3942"), 1))
            draw_left = max(gutter_x, int(clip_left))
            draw_right = min(gutter_right, int(clip_right))
            for y in (
                subtitle_top - 5,
                STT1_TOP - 3,
                STT2_TOP - 3,
                speaker_top - 3,
                voice_mid - 14,
                audio_mid - 14,
                track_bottom,
            ):
                p.drawLine(draw_left, y, draw_right, y)
            p.setFont(QFont(config.FONT, 9, QFont.Weight.Bold))
            for text, y in (
                ("자막", subtitle_top + 20),
                ("STT1", STT1_TOP + 20),
                ("STT2", STT2_TOP + 20),
                ("화자", speaker_top + 15),
                ("자막감지", voice_mid + 4),
                ("음성/무음", audio_mid + 4),
            ):
                if overview_mode and text in {"자막감지", "음성/무음"}:
                    continue
                p.setPen(QColor("#A9B0B7"))
                p.drawText(QRect(gutter_x + 8, y - 16, max(12, gutter_w - 14), 22), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

        def _draw_rect_batch(rects, *, fill: QColor | None = None, pen: QPen | None = None):
            if not rects:
                return
            p.setBrush(QBrush(fill) if fill is not None else Qt.BrushStyle.NoBrush)
            p.setPen(pen if pen is not None else Qt.PenStyle.NoPen)
            try:
                p.drawRects(rects)
            except TypeError:
                for rect in rects:
                    p.drawRect(rect)

        def _append_batch(batches: dict, key, rect: QRect):
            batches.setdefault(key, []).append(rect)

        def _draw_color_batches(batches: dict, *, as_pen: bool = False, width: int = 1, style=Qt.PenStyle.SolidLine):
            for key, rects in batches.items():
                if isinstance(key, tuple):
                    color = QColor(str(key[0]))
                    if len(key) > 1:
                        color.setAlpha(int(key[1]))
                else:
                    color = QColor(str(key))
                if as_pen:
                    _draw_rect_batch(rects, pen=QPen(color, width, style))
                else:
                    _draw_rect_batch(rects, fill=color)

        p.fillRect(paint_clip, QColor("#0F1518"))

        def _fmt_ruler(sec):
            s = int(sec)
            h, rem = divmod(s, 3600)
            m, sc = divmod(rem, 60)
            if h > 0:
                return f"{h}:{m:02d}:{sc:02d}"
            return f"{m:02d}:{sc:02d}"

        ruler_font = QFont(config.FONT, 10)
        ruler_font.setBold(True)
        p.setFont(ruler_font)
        fm_ruler = p.fontMetrics()

        MIN_LABEL_PX = 80
        nice_steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600]

        major_step = 1.0
        for ns in nice_steps:
            if ns * self.pps >= MIN_LABEL_PX:
                major_step = ns
                break
        else:
            major_step = nice_steps[-1]

        if major_step >= 0.5:
            sub_step = major_step / 5
        else:
            sub_step = major_step / 2
        
        visible_start_sec = max(0.0, clip_left / max(0.001, float(self.pps)))

        # 메이저 틱 + 라벨
        sec_i = max(0.0, (int(visible_start_sec / major_step) * major_step) - major_step)
        while sec_i <= total_secs:
            tx = self._x(sec_i)
            if tx > clip_right:
                break
            if sec_i > 0:
                p.setPen(QColor("#6F7A83"))
                p.drawLine(tx, 10, tx, RULER_H - 9)
                label = _fmt_ruler(sec_i)
                lw = fm_ruler.horizontalAdvance(label)
                p.setPen(QColor("#A9B0B7"))
                p.drawText(tx - lw // 2, RULER_H - 7, label)
            sec_i = round(sec_i + major_step, 3)

        # 서브 틱 (라벨 없음)
        sec_f = max(0.0, (int(visible_start_sec / sub_step) * sub_step) - sub_step)
        while sec_f <= total_secs:
            tx = self._x(sec_f)
            if tx > clip_right:
                break
            # 메이저 틱 위치면 스킵
            if major_step > 0 and abs(round(sec_f / major_step) * major_step - sec_f) < 0.001:
                sec_f = round(sec_f + sub_step, 3)
                continue
            p.setPen(QColor("#46525B"))
            p.drawLine(tx, 13, tx, RULER_H - 14)
            sec_f = round(sec_f + sub_step, 3)

        p.fillRect(QRect(clip_left, RULER_H, max(1, clip_right - clip_left), WAVE_H), QColor("#070A0C"))

        if self._waveform is not None:
            wf = self._waveform
            wf_len = len(wf)

            p.setPen(QPen(QColor("#2D3942"), 1))
            p.drawLine(clip_left, WAVE_MID, clip_right, WAVE_MID)

            if self._speech_mask is None or self._speech_mask_wf_len != wf_len:
                mask = np.zeros(wf_len, dtype=bool)
                for vs in self.vad_segments:
                    s_idx = max(0, int(vs["start"] * 100))
                    e_idx = min(wf_len, int(vs["end"] * 100) + 1)
                    mask[s_idx:e_idx] = True
                self._speech_mask = mask
                self._speech_mask_wf_len = wf_len
            speech_mask = self._speech_mask

            clip = paint_clip
            x_start = max(0, clip.left())
            x_end = min(total_w, clip.right() + 1)

            pen_top_norm = QPen(QColor(170, 176, 184), 1)
            pen_bot_norm = QPen(QColor(104, 110, 118), 1)
            pen_top_loud = QPen(QColor(220, 224, 228), 1)
            pen_bot_loud = QPen(QColor(150, 156, 164), 1)
            pen_top_sil = QPen(QColor(82, 87, 94), 1)
            pen_bot_sil = QPen(QColor(56, 61, 68), 1)

            for x in range(x_start, x_end):
                idx = int((x / self.pps) * 100)
                if idx >= wf_len: break
                val = wf[idx]
                if val < 0.008: continue
                h = min(int(val * WAVE_HALF * 2.0), WAVE_HALF - 1)
                in_sp = speech_mask[idx]
                if in_sp:
                    if val > 0.6:
                        p.setPen(pen_top_loud); p.drawLine(x, WAVE_MID, x, WAVE_MID - h)
                        p.setPen(pen_bot_loud); p.drawLine(x, WAVE_MID + 1, x, WAVE_MID + h)
                    else:
                        p.setPen(pen_top_norm); p.drawLine(x, WAVE_MID, x, WAVE_MID - h)
                        p.setPen(pen_bot_norm); p.drawLine(x, WAVE_MID + 1, x, WAVE_MID + h)
                else:
                    p.setPen(pen_top_sil); p.drawLine(x, WAVE_MID, x, WAVE_MID - h)
                    p.setPen(pen_bot_sil); p.drawLine(x, WAVE_MID + 1, x, WAVE_MID + h)

            p.setPen(Qt.PenStyle.NoPen)
            vad_rects = []
            for vs in visible_vad_segments:
                vx1 = self._x(vs["start"])
                vx2 = self._x(vs["end"])
                if vx2 < clip_left or vx1 > clip_right:
                    continue
                vad_rects.append(QRect(vx1, RULER_H, max(1, vx2 - vx1), WAVE_H))
            _draw_rect_batch(vad_rects, fill=QColor(87, 157, 255, 34))

        if self.re_recog_zone:
            rs, re_sec = self.re_recog_zone
            rp = self.re_recog_progress if self.re_recog_progress is not None else rs
            yx1 = self._x(rs); yx2 = self._x(rp)
            if yx2 > yx1:
                p.fillRect(QRect(yx1, RULER_H, yx2 - yx1, WAVE_H), QColor(255, 255, 0, 100))
            gx1 = self._x(max(rs, rp)); gx2 = self._x(re_sec)
            if gx2 > gx1:
                p.fillRect(QRect(gx1, RULER_H, gx2 - gx1, WAVE_H), QColor(0, 255, 0, 70))

        _draw_roughcut_major_lane()

        p.fillRect(QRect(clip_left, SEG_TOP, max(1, clip_right - clip_left), SEG_BOT - SEG_TOP), QColor("#11181C"))
        p.setPen(QPen(QColor("#2D3942"), 1))
        for y in (subtitle_top - 5, STT1_TOP - 3, STT2_TOP - 3, speaker_top - 3, voice_mid - 14, audio_mid - 14, track_bottom):
            p.drawLine(clip_left, y, clip_right, y)

        def _draw_gap_lane(gaps):
            if not gaps:
                return
            compact_gap_mode = bool(overview_mode or ultra_dense_segment_mode or len(gaps) >= 512)
            base_rects: list[QRect] = []
            border_rects: list[QRect] = []
            plus_items: list[tuple[QRect, QRect]] = []
            active_items: list[tuple[QRect, QRect]] = []
            for g in gaps:
                x1, x2 = self._x(g["start"]), self._x(g["end"])
                sw = max(4, x2 - x1)
                if x2 < clip_left or x1 > clip_right:
                    continue
                rect = QRect(x1, SEG_TOP, sw, SEG_BOT - SEG_TOP)
                if g.get("active", False):
                    active_items.append((rect, self._icon_rect(x1, x2)))
                    continue
                if compact_gap_mode:
                    continue
                base_rects.append(rect)
                border_rects.append(rect)
                if sw >= ICON_SZ + 8 and not dense_segment_mode:
                    plus_items.append((rect, self._plus_rect(x1, x2)))
            _draw_rect_batch(base_rects, fill=QColor(20, 16, 0, 118))
            _draw_rect_batch(border_rects, pen=QPen(QColor("#4F5962"), 1, Qt.PenStyle.DotLine))
            if plus_items:
                p.setFont(QFont(config.FONT, 18, QFont.Weight.Bold))
                for _rect, ir in plus_items:
                    p.fillRect(ir, QColor("#17232A"))
                    p.setPen(QColor("#8EA4B8"))
                    p.drawText(ir, Qt.AlignmentFlag.AlignCenter, "+")
            if active_items:
                p.setFont(QFont(config.FONT, 9, QFont.Weight.Bold))
                for rect, ir in active_items:
                    p.fillRect(rect, QColor(20, 16, 0, 118))
                    p.setPen(QPen(QColor("#FFFFFF"), 2))
                    p.drawRect(rect)
                    p.fillRect(ir, QColor("#3B1D20"))
                    p.setPen(QColor("#FF8A80"))
                    p.drawText(ir, Qt.AlignmentFlag.AlignCenter, "✕")

        dragging_timing = getattr(self, "_drag_seg", None) is not None or getattr(self, "_drag_edge", None) == "diamond"
        if not dragging_timing:
            _draw_gap_lane(visible_gap_segments)

        def _draw_stt_preview_lane(preview_segments, lane_top, lane_bot, fill_hex, border_hex, text_hex):
            if not preview_segments:
                return
            p.setFont(QFont(config.FONT, 8))
            fills: dict[tuple[str, int], list[QRect]] = {}
            borders: dict[tuple[str, int, int], list[QRect]] = {}
            detail_items = []
            for seg in preview_segments:
                x1 = self._x(float(seg.get("start", 0.0) or 0.0))
                x2 = self._x(float(seg.get("end", seg.get("start", 0.0)) or seg.get("start", 0.0) or 0.0))
                sw = max(2, x2 - x1)
                if x2 < clip_left or x1 > clip_right:
                    continue
                rect = QRect(x1 + 1, lane_top, max(2, sw - 2), lane_bot - lane_top)
                selection_state = stt_candidate_selection_state(seg, final_stt_segments)
                is_selected = selection_state in {"manual", "llm"}
                visual = stt_preview_visual_style(
                    seg,
                    selection_state=selection_state,
                    fill_hex=fill_hex,
                    border_hex=border_hex,
                    text_hex=text_hex,
                )
                _append_batch(fills, (str(visual["fill"]), int(visual["alpha"])), rect)
                _append_batch(borders, (str(visual["border"]), 255, int(visual["border_width"])), rect)
                if rect.width() >= 44 and not dense_segment_mode:
                    detail_items.append((seg, rect, selection_state, is_selected, visual))
            _draw_color_batches(fills)
            for (color_name, alpha, border_width), rects in borders.items():
                color = QColor(color_name)
                color.setAlpha(int(alpha))
                _draw_rect_batch(rects, pen=QPen(color, int(border_width)))
            for seg, rect, selection_state, is_selected, visual in detail_items:
                    text_color = QColor(visual["text"])
                    badge_w = 36 if is_selected and rect.width() >= 90 else 0
                    text_rect = QRect(rect.x() + 8, rect.y() + 5, max(8, rect.width() - 16 - badge_w), rect.height() - 10)
                    p.setPen(text_color)
                    preview_text = str(seg.get("text", "") or "")
                    if rect.width() < 132:
                        preview_text = p.fontMetrics().elidedText(preview_text.replace("\n", " "), Qt.TextElideMode.ElideRight, text_rect.width())
                        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, preview_text)
                    else:
                        p.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, preview_text)
                    if badge_w:
                        badge_rect = QRect(rect.right() - badge_w - 4, rect.y() + 6, badge_w, 18)
                        badge_fill = QColor("#5A4600" if selection_state == "llm" else "#174A2A")
                        badge_border = QColor("#FFCC00" if selection_state == "llm" else "#34C759")
                        badge_text = "LLM" if selection_state == "llm" else "선택"
                        p.fillRect(badge_rect, badge_fill)
                        p.setPen(QPen(badge_border, 1))
                        p.drawRect(badge_rect)
                        p.setPen(QColor("#FFF2A8"))
                        p.setFont(QFont(config.FONT, 7, QFont.Weight.Bold))
                        p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)
                        p.setFont(QFont(config.FONT, 8))

        def _draw_vector_subtitle_strips(segments) -> set[int]:
            """Batch dense subtitle geometry so large projects repaint like vector strips."""
            if not segments:
                return set()
            fill_batches: dict[str, list[QRect]] = {}
            border_batches: dict[str, list[QRect]] = {}
            speaker_batches: dict[str, list[QRect]] = {}
            drawn_ids: set[int] = set()
            style_cache = getattr(self, "_segment_visual_style_cache", None)
            if not isinstance(style_cache, dict):
                style_cache = {}
                self._segment_visual_style_cache = style_cache
            render_epoch = int(getattr(self, "_render_epoch", 0) or 0)
            quality_filter = str(getattr(self, "quality_filter", "all") or "all")
            speaker_color_cache: dict[str, str] = {}
            for seg in segments:
                try:
                    x1 = self._x(float(seg.get("start", 0.0) or 0.0))
                    x2 = self._x(float(seg.get("end", seg.get("start", 0.0)) or 0.0))
                except Exception:
                    continue
                if x2 < clip_left or x1 > clip_right:
                    continue
                sw = max(2, x2 - x1)
                rect = QRect(x1 + 1, subtitle_top, max(2, sw - 2), subtitle_bot - subtitle_top)
                is_active = self._is_active_segment(seg) if hasattr(self, "_is_active_segment") else (
                    self.active_seg_start is not None and abs(float(seg.get("start", 0.0) or 0.0) - self.active_seg_start) < 0.001
                )
                is_hover = self._hover_line == seg.get("line")
                if is_active or is_hover:
                    continue
                quality = dict(seg.get("quality") or {})
                style_key = (
                    id(seg),
                    render_epoch,
                    quality_filter,
                    bool(seg.get("stt_pending")),
                    segment_text_kind(seg.get("text", "")),
                    str(quality.get("confidence_label", "")),
                    quality.get("confidence_score"),
                    bool(quality.get("manual_confirmed")),
                    tuple(str(flag) for flag in (quality.get("flags") or ())),
                    str(seg.get("subtitle_auto_review_severity", "") or ""),
                    str(seg.get("subtitle_confidence_label", "") or ""),
                    str(seg.get("stt_selected_source", "") or ""),
                    str(seg.get("stt_ensemble_llm_selected_source", "") or ""),
                    bool(seg.get("stt_ensemble_needs_llm_review")),
                    len(list(seg.get("stt_candidates") or [])),
                )
                cached_style = style_cache.get(style_key)
                if cached_style is None:
                    visual_style = subtitle_segment_visual_style(
                        seg,
                        active=False,
                        hover=False,
                        quality_filter=quality_filter,
                    )
                    cached_style = (str(visual_style["fill"]), str(visual_style["border"]))
                    style_cache[style_key] = cached_style
                fill_color, border_color = cached_style
                fill_batches.setdefault(fill_color, []).append(rect)
                border_batches.setdefault(border_color, []).append(rect)
                speaker_key = str(seg.get("speaker", seg.get("spk_id", "")) or "")
                speaker_color_name = speaker_color_cache.get(speaker_key)
                if speaker_color_name is None:
                    speaker_color_name = _speaker_color(seg).darker(135).name()
                    speaker_color_cache[speaker_key] = speaker_color_name
                speaker_batches.setdefault(speaker_color_name, []).append(
                    QRect(rect.x(), speaker_top, rect.width(), speaker_bot - speaker_top)
                )
                drawn_ids.add(id(seg))

            if not fill_batches:
                return set()
            for color_name, rects in fill_batches.items():
                _draw_rect_batch(rects, fill=QColor(color_name))
            for color_name, rects in speaker_batches.items():
                _draw_rect_batch(rects, fill=QColor(color_name))
            for color_name, rects in border_batches.items():
                _draw_rect_batch(rects, pen=QPen(QColor(color_name), 1))
            return drawn_ids

        if not scenegraph_subtitles:
            _draw_stt_preview_lane(stt1_preview_segments, STT1_TOP, STT1_BOT, "#173524", "#34C759", "#D7FFE4")
            _draw_stt_preview_lane(stt2_preview_segments, STT2_TOP, STT2_BOT, "#1A3148", "#64D2FF", "#BDEBFF")

            seg_font = QFont(config.FONT, 9); p.setFont(seg_font)
            vector_drawn_ids = (
                _draw_vector_subtitle_strips(final_stt_segments)
                if dense_segment_mode and not bool(getattr(self, "_edit_active", False))
                else set()
            )
            for seg in final_stt_segments:
                if id(seg) in vector_drawn_ids:
                    continue
                if bool(seg.get("stt_pending") or seg.get("_live_stt_preview")):
                    continue
                x1, x2 = self._x(seg["start"]), self._x(seg["end"]); sw = max(2, x2 - x1)
                if x2 < clip_left or x1 > clip_right:
                    continue
                rect = QRect(x1 + 1, subtitle_top, max(2, sw - 2), subtitle_bot - subtitle_top)
                is_active = self._is_active_segment(seg) if hasattr(self, "_is_active_segment") else (
                    self.active_seg_start is not None and abs(seg["start"] - self.active_seg_start) < 0.001
                )
                is_hover = self._hover_line == seg.get("line")
                is_editing = (self._edit_active and self._edit_line == seg.get("line"))
                focus_detail = bool(is_active or is_hover or is_editing)
                compact_seg = sw < 24 or (dense_segment_mode and not focus_detail)
                is_stt_pending = bool(seg.get("stt_pending"))
                spk_color = _speaker_color(seg)
                visual_style = subtitle_segment_visual_style(
                    seg,
                    active=is_active,
                    hover=is_hover,
                    quality_filter=getattr(self, "quality_filter", "all"),
                )
                if overview_mode and compact_seg:
                    fill = QColor(visual_style["fill"])
                    border = QColor(visual_style["border"])
                    p.fillRect(rect, fill)
                    p.setPen(QPen(border, 1))
                    p.drawRect(rect)
                    speaker_rect = QRect(rect.x(), speaker_top, rect.width(), speaker_bot - speaker_top)
                    p.fillRect(speaker_rect, spk_color.darker(135))
                    continue
                fill = QColor(visual_style["fill"])
                border = QColor(visual_style["border"])
                bw = 2 if (is_active or is_hover) and not compact_seg else 1

                p.fillRect(rect, fill)
                p.setPen(QPen(border, bw))
                p.drawRect(rect)
                chips = subtitle_confidence_chips(seg)
                chips_drawn = False
                if chips and rect.width() >= 72 and rect.height() >= 30 and not compact_seg and (not dense_segment_mode or focus_detail):
                    chip_w = max(6, min(18, (rect.width() - 10) // max(1, len(chips))))
                    chip_h = 4
                    chip_y = rect.y() + 3
                    chip_x = rect.x() + 5
                    for chip in chips[:5]:
                        chip_rect = QRect(int(chip_x), int(chip_y), int(chip_w), int(chip_h))
                        p.fillRect(chip_rect, QColor(str(chip.get("color") or "#8E8E93")))
                        chip_x += chip_w + 2
                    chips_drawn = True
                p.setFont(seg_font)
                top_pad = 12 if chips_drawn else 6
                text_rect = QRect(rect.x() + 10, rect.y() + top_pad, max(8, rect.width() - 20), rect.height() - top_pad - 6)
                if is_editing:
                    disp_text = self._edit_text
                    preedit = getattr(self, '_ime_preedit', '')
                    cur = self._edit_cursor
                    if preedit:
                        disp_text = disp_text[:cur] + preedit + disp_text[cur:]
                    lines = disp_text.split('\n')
                    fm = p.fontMetrics()
                    line_h = fm.height()
                    tx0 = text_rect.x(); ty0 = text_rect.y() + fm.ascent()
                    p.fillRect(text_rect, QColor("#123A24"))
                    vis_cur = cur + len(preedit)
                    r = 0; c = vis_cur
                    for i, line in enumerate(lines):
                        if c <= len(line): r = i; break
                        c -= (len(line) + 1)
                    curr_y = ty0
                    for i, line in enumerate(lines):
                        p.setPen(QColor("#FFFF88"))
                        if preedit and i == r:
                            pre_start = c - len(preedit)
                            p.drawText(tx0, curr_y, line)
                            pre_w_start = fm.horizontalAdvance(line[:pre_start])
                            pre_w_end = fm.horizontalAdvance(line[:c])
                            p.setPen(QColor("#FFFF00"))
                            p.drawText(tx0 + pre_w_start, curr_y, preedit)
                            p.setPen(QPen(QColor("#FFFF00"), 1))
                            p.drawLine(tx0 + pre_w_start, curr_y + 1, tx0 + pre_w_end, curr_y + 1)
                        else:
                            p.drawText(tx0, curr_y, line)
                        if self._cursor_vis and i == r:
                            cx = tx0 + fm.horizontalAdvance(line[:c])
                            cursor_top = curr_y - fm.ascent()
                            cursor_bot = cursor_top + line_h
                            p.setPen(QPen(QColor("#FFFFFF"), 1))
                            p.drawLine(cx, cursor_top, cx, cursor_bot)
                        curr_y += line_h + 4
                else:
                    if rect.width() >= 44 and (not dense_segment_mode or focus_detail):
                        text_color = visual_style.get("text", "")
                        p.setPen(QColor(text_color) if text_color else (QColor("#8A8F98") if is_stt_pending else QColor("#DCE3EA")))
                        seg_text = str(seg.get("text", "") or "")
                        if rect.width() < 164:
                            seg_text = p.fontMetrics().elidedText(seg_text.replace("\n", " "), Qt.TextElideMode.ElideRight, text_rect.width())
                            p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, seg_text)
                        else:
                            p.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, seg_text)
                        selected_source = final_stt_selection_source(seg)
                        if selected_source and rect.width() >= 104 and (not dense_segment_mode or focus_detail):
                            is_llm_choice = bool(str(seg.get("stt_ensemble_llm_selected_source", "") or "").strip())
                            badge_rect = QRect(rect.right() - 42, rect.y() + 6, 38, 18)
                            badge_fill = QColor("#5A4600" if is_llm_choice else "#174A2A")
                            badge_border = QColor("#FFCC00" if is_llm_choice else "#34C759")
                            badge_text_color = QColor("#FFF2A8" if is_llm_choice else "#D7FFE4")
                            p.fillRect(badge_rect, badge_fill)
                            p.setPen(QPen(badge_border, 1))
                            p.drawRect(badge_rect)
                            p.setPen(badge_text_color)
                            p.setFont(QFont(config.FONT, 7, QFont.Weight.Bold))
                            p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "선택")
                            p.setFont(seg_font)
                speaker_rect = QRect(rect.x(), speaker_top, rect.width(), speaker_bot - speaker_top)
                if compact_seg:
                    p.fillRect(speaker_rect, spk_color.darker(135))
                else:
                    p.setPen(QPen(QColor("#2D3942"), 1))
                    p.setBrush(QColor("#1B2429"))
                    p.drawRect(speaker_rect)
                if not compact_seg and speaker_rect.width() >= 42 and (not dense_segment_mode or focus_detail):
                    self._draw_speaker_names(p, speaker_rect, spk_color, _speaker_names(seg))

                if sw >= SEGMENT_HANDLE_MIN_WIDTH and (not dense_segment_mode or focus_detail) and not ultra_dense_segment_mode:
                    lh = self._hover_handle_matches(seg, "left")
                    rh = self._hover_handle_matches(seg, "right")
                    self._draw_handle(p, x1, True, QColor("#44FF88") if lh else QColor("#888888"))
                    self._draw_handle(p, x2, False, QColor("#44FF88") if rh else QColor("#888888"))

        llm_review = dict(getattr(self, "llm_review_segment", {}) or {})
        if llm_review.get("active"):
            try:
                review_start = float(llm_review.get("start", 0.0) or 0.0)
                review_end = float(llm_review.get("end", review_start) or review_start)
            except Exception:
                review_start = review_end = 0.0
            if review_end > review_start:
                x1 = self._x(review_start)
                x2 = self._x(review_end)
                if x2 >= clip_left and x1 <= clip_right:
                    rect = QRect(max(clip_left, x1) + 1, subtitle_top + 1, max(2, min(clip_right, x2) - max(clip_left, x1) - 2), subtitle_bot - subtitle_top - 2)
                    p.setPen(QPen(QColor("#0A84FF"), 3))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(rect)

        if not overview_mode:
            _draw_subtitle_detection_lane(voice_mid)
            _draw_analysis_lane(audio_mid)

        _draw_lane_labels()

        if self.pps >= 8:
            diamond_pairs = self._diamond_pairs() if hasattr(self, "_diamond_pairs") else []
            was_antialias = p.renderHints() & QPainter.RenderHint.Antialiasing
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            for i, (_, _, s1, _) in enumerate(diamond_pairs):
                bx = self._x(s1["end"]); r = 7; cy = DIAMOND_Y
                if bx < clip_left - r or bx > clip_right + r:
                    continue
                is_hover = (getattr(self, '_hover_diamond', None) == i)
                fill = QColor("#FFE45C") if is_hover else QColor("#DDE7F0")
                pts = QPolygon([
                    QPoint(bx, cy - r),
                    QPoint(bx + r, cy),
                    QPoint(bx, cy + r),
                    QPoint(bx - r, cy),
                ])
                p.setPen(QPen(QColor("#FFD400"), 2))
                p.setBrush(QBrush(fill))
                p.drawPolygon(pts)
                p.setPen(QPen(QColor("#061018"), 1))
                p.drawLine(bx - 3, cy, bx + 3, cy)
                p.setBrush(Qt.BrushStyle.NoBrush)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, bool(was_antialias))

        self._clip_delete_rects = []
        self._clip_add_rect = QRect()
        self._clip_add_placeholder = None
        if self._multiclip_boxes:
            for box in visible_multiclip_boxes:
                bx1 = self._x(box["start"])
                bx2 = self._x(box["end"])
                bw = bx2 - bx1
                if bx2 < clip_left or bx1 > clip_right:
                    continue

                clip_idx = box.get("index", 1) - 1
                is_active = clip_idx == getattr(self, "_active_clip_idx", -1)

                color = "#4AFF80" if is_active else "#666666"
                width = 3 if is_active else 1

                p.setPen(QPen(QColor(color), width))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(int(bx1), 0, int(bw), CANVAS_H)

                # CLIP label: top-right outside box + delete
                clip_label = f"CLIP {box.get('index', '?')}"
                delete_label = '[X]'
                p.setFont(QFont("", 9, QFont.Weight.Bold))
                fm = p.fontMetrics()
                label_w = fm.horizontalAdvance(clip_label) + 10
                delete_w = fm.horizontalAdvance(delete_label) + 10
                label_total_w = label_w + 6 + delete_w
                lbl_x = int(bx2) - label_total_w - 4
                lbl_y = 20
                clip_rect = QRect(lbl_x, lbl_y, label_w, 16)
                delete_rect = QRect(lbl_x + label_w + 6, lbl_y, delete_w, 16)
                self._clip_delete_rects.append((clip_idx, delete_rect))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, 180))
                p.drawRoundedRect(clip_rect, 3, 3)
                p.drawRoundedRect(delete_rect, 3, 3)
                p.setPen(QColor(color))
                p.drawText(clip_rect, Qt.AlignmentFlag.AlignCenter, clip_label)
                p.setPen(QColor('#FF8080'))
                p.drawText(delete_rect, Qt.AlignmentFlag.AlignCenter, delete_label)

        add_anchor_sec = None
        if self._multiclip_boxes:
            add_anchor_sec = float(self._multiclip_boxes[-1].get("end", 0.0) or 0.0)
        elif self.total_duration > 0:
            add_anchor_sec = float(self.total_duration)
        elif self.segments:
            add_anchor_sec = max(float(seg.get("end", 0.0) or 0.0) for seg in self.segments)

        if add_anchor_sec is not None:
            add_x = self._x(add_anchor_sec) + 8
            add_w = 50
            add_h = max(24, subtitle_bot - subtitle_top)
            max_add_x = max(0, self.width() - add_w - 6)
            add_x = min(add_x, max_add_x)
            self._clip_add_rect = QRect(int(add_x), int(subtitle_top), add_w, add_h)
            self._clip_add_placeholder = {
                "start": add_anchor_sec,
                "end": add_anchor_sec + (add_w / max(1.0, float(self.pps))),
            }
            p.setPen(QPen(QColor("#4AFF80"), 1, Qt.PenStyle.DashLine))
            p.setBrush(QColor(17, 34, 51, 180))
            p.drawRoundedRect(QRectF(self._clip_add_rect), 5, 5)
            p.setPen(QColor("#4AFF80"))
            p.setFont(QFont(config.FONT, 20, QFont.Weight.Bold))
            p.drawText(self._clip_add_rect, Qt.AlignmentFlag.AlignCenter, "+")

        boundary_lane_top = RULER_H + WAVE_H + 5
        boundary_lane_h = max(18, SEG_TOP - boundary_lane_top - 7)
        boundary_top = int(boundary_lane_top + 3)
        boundary_bot = int(boundary_lane_top + boundary_lane_h - 3)

        def _visible_time_items(items, sec_getter, *, keep_index: bool = False):
            rows = list(items or [])
            if len(rows) < 64:
                visible_rows = []
                for idx, item in enumerate(rows):
                    try:
                        sec = float(sec_getter(item))
                    except Exception:
                        continue
                    visible_rows.append((idx, item, sec))
                if keep_index:
                    return visible_rows
                return [(item, sec) for _idx, item, sec in visible_rows]

            timed = []
            for idx, item in enumerate(rows):
                try:
                    sec = float(sec_getter(item))
                except Exception:
                    continue
                if sec < 0.0:
                    continue
                timed.append((sec, idx, item))
            timed.sort(key=lambda row: (row[0], row[1]))
            secs = [row[0] for row in timed]
            pad = max(0.02, 12.0 / max(0.001, float(getattr(self, "pps", 1.0) or 1.0)))
            start_idx = bisect_left(secs, visible_start_sec - pad)
            end_idx = bisect_right(secs, visible_end_sec + pad)
            if keep_index:
                return [(idx, item, sec) for sec, idx, item in timed[start_idx:end_idx]]
            return [(item, sec) for sec, _idx, item in timed[start_idx:end_idx]]

        if getattr(self, "boundary_times", None):
            pen_confirmed_boundary = QPen(QColor("#8E8E93"), 1, Qt.PenStyle.DashLine)
            for bt, sec in _visible_time_items(getattr(self, "boundary_times", []) or [], lambda item: float(item or 0.0)):
                bx = self._x(sec)
                if bx < clip_left or bx > clip_right:
                    continue
                p.setPen(pen_confirmed_boundary)
                p.drawLine(bx, boundary_top, bx, boundary_bot)
        if getattr(self, "scan_boundary_times", None):
            hover_scan_boundary_idx = getattr(self, "_hover_scan_boundary_idx", None)
            for idx, bt, sec in _visible_time_items(
                getattr(self, "scan_boundary_times", []) or [],
                lambda item: self._scan_boundary_sec(item) if hasattr(self, "_scan_boundary_sec") else (
                    item.get("timeline_sec", item.get("time", item.get("start", 0.0))) if isinstance(item, dict) else item
                ),
                keep_index=True,
            ):
                visual = scan_boundary_marker_visual(bt, hover=(hover_scan_boundary_idx == idx))
                pen_style = (
                    Qt.PenStyle.DotLine
                    if visual["style"] == "dot"
                    else (Qt.PenStyle.DashLine if visual["style"] == "dash" else Qt.PenStyle.SolidLine)
                )
                pen_boundary = QPen(QColor(visual["color"]), int(visual["width"]), pen_style)
                bx = self._x(sec)
                if bx < clip_left or bx > clip_right:
                    continue
                p.setPen(pen_boundary)
                p.drawLine(bx, boundary_top, bx, boundary_bot)

        guide_x = getattr(self, "_drag_guide_x", None)
        if guide_x is not None:
            p.setPen(QPen(QColor("#B15CFF"), 2, Qt.PenStyle.SolidLine))
            p.drawLine(int(guide_x), 0, int(guide_x), CANVAS_H)

        if hasattr(self, '_snap_lines') and self._snap_lines:
            p.setPen(QPen(QColor("#FF1F1F"), 4, Qt.PenStyle.SolidLine))
            for sx in self._snap_lines:
                p.drawLine(int(sx), 0, int(sx), CANVAS_H)

        if getattr(self, '_is_listening', False):
            listening_line = getattr(self, "_listening_line", None)
            if listening_line is None and getattr(self, "_edit_active", False):
                listening_line = getattr(self, "_edit_line", None)
            if hasattr(self, "_segment_for_line") and listening_line is not None:
                seg = self._segment_for_line(listening_line)
            else:
                seg = next((s for s in self.segments if s.get("line") == listening_line), None)
            if seg:
                sx1 = self._x(float(seg.get("start", 0.0) or 0.0))
                sx2 = self._x(float(seg.get("end", seg.get("start", 0.0)) or seg.get("start", 0.0) or 0.0))
                sw = max(2, sx2 - sx1)
                if sx2 >= clip_left and sx1 <= clip_right:
                    wave_rect = QRect(sx1 + 14, subtitle_top + 12, max(18, sw - 28), max(10, subtitle_bot - subtitle_top - 24))
                    samples = list(getattr(self, "_mic_waveform_samples", []) or [])
                    if samples and wave_rect.width() >= 8:
                        p.save()
                        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                        p.setClipRect(wave_rect.adjusted(-1, -1, 1, 1))
                        mid_y = wave_rect.center().y()
                        amp_h = max(4, int(wave_rect.height() * 0.40))
                        p.setPen(QPen(QColor("#FF3B30"), 2))
                        prev_x = wave_rect.x()
                        prev_y = mid_y
                        sample_count = max(1, len(samples) - 1)
                        denom = max(1, wave_rect.width() - 1)
                        for px in range(wave_rect.width()):
                            idx = int((px / denom) * sample_count)
                            amp = max(-1.0, min(1.0, float(samples[idx])))
                            x = wave_rect.x() + px
                            y = mid_y - int(amp * amp_h)
                            if px > 0:
                                p.drawLine(prev_x, prev_y, x, y)
                            prev_x, prev_y = x, y
                        p.restore()
                    else:
                        mic_x = self._x(seg["end"]) + 8
                        mic_y = SEG_TOP + 5
                        p.setFont(QFont(config.FONT, 18))
                        p.setPen(QColor("#FF4444"))
                        p.drawText(mic_x, mic_y + 20, "🎤")
                        p.setFont(QFont(config.FONT, 10))
                        p.setPen(QColor("#FF8888"))
                        p.drawText(mic_x + 24, mic_y + 18, "Listening...")

        if self.playhead_sec >= 0 and not getattr(self, "_external_playhead_overlay", False):
            ph_color = QColor("#4AFF80") if getattr(self, 'focus_mode', 'segment') == "waveform" else QColor("#FF4444")
            p.setPen(QPen(ph_color, 2)); px = self._x(self.playhead_sec); p.drawLine(px, 0, px, CANVAS_H)
            handle_r = 7
            self._playhead_handle_rect = QRect(int(px - handle_r), 2, handle_r * 2, handle_r * 2)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(QBrush(QColor("#FF453A" if getattr(self, "playhead_busy", False) else "#FFCC00")))
            p.setPen(QPen(QColor("#FFFFFF"), 1))
            p.drawEllipse(self._playhead_handle_rect)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    def _draw_handle(self, p, bx, is_left, color):
        cy = SEG_TOP + 32
        w = HANDLE_R; hw = HANDLE_R // 2; hh = 12; th = 4
        if is_left:
            bx += 2
            pts = QPolygon([QPoint(bx, cy), QPoint(bx + hw, cy - hh), QPoint(bx + hw, cy - th), QPoint(bx + w, cy - th), QPoint(bx + w, cy + th), QPoint(bx + hw, cy + th), QPoint(bx + hw, cy + hh)])
        else:
            bx -= 2
            pts = QPolygon([QPoint(bx, cy), QPoint(bx - hw, cy - hh), QPoint(bx - hw, cy - th), QPoint(bx - w, cy - th), QPoint(bx - w, cy + th), QPoint(bx - hw, cy + th), QPoint(bx - hw, cy + hh)])
        p.setPen(QPen(QColor("#000000"), 1)); p.setBrush(QBrush(color)); p.drawPolygon(pts); p.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_speaker_names(self, p, rect: QRect, color: QColor, names: list[str]):
        names = [str(name).strip() for name in names if str(name).strip()]
        if not names:
            return

        max_lines = 2
        visible_names = names[:max_lines]
        multi_line = len(visible_names) > 1
        font_size = 7 if multi_line else 8
        p.setFont(QFont(config.FONT, font_size, QFont.Weight.Bold))
        fm = p.fontMetrics()
        line_h = fm.height()
        gap = 0 if multi_line else 1
        dot = 6 if multi_line else 8
        text_gap = 5 if multi_line else 6
        row_h = max(dot, line_h)
        total_h = len(visible_names) * row_h + max(0, len(visible_names) - 1) * gap
        y = rect.y() + max(0, (rect.height() - total_h) // 2)
        max_row_w = max(
            dot + text_gap + fm.horizontalAdvance(name)
            for name in visible_names
        )
        x = rect.x() + max(6, (rect.width() - max_row_w) // 2)
        max_text_w = max(8, rect.right() - x - dot - text_gap - 4)

        p.setPen(color)
        p.setBrush(color)
        for idx, name in enumerate(visible_names):
            row_y = y + idx * (row_h + gap)
            dot_y = row_y + max(0, (row_h - dot) // 2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawEllipse(QRect(x, dot_y, dot, dot))
            p.setPen(color)
            text_rect = QRect(x + dot + text_gap, row_y, max_text_w, row_h)
            p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)

    def _hover_handle_matches(self, seg, edge: str) -> bool:
        hovered = getattr(self, "_hover_handle", None)
        if not hovered or len(hovered) < 2 or hovered[1] != edge:
            return False
        hover_seg = hovered[0]
        if hover_seg is seg:
            return True
        try:
            return (
                hover_seg.get("line") == seg.get("line")
                and abs(float(hover_seg.get("start", -1.0)) - float(seg.get("start", -2.0))) < 0.001
                and abs(float(hover_seg.get("end", -1.0)) - float(seg.get("end", -2.0))) < 0.001
            )
        except Exception:
            return False
