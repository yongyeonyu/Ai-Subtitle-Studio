# Version: 03.14.31
# Phase: PHASE2
"""
ui/timeline_paint.py
Timeline paint mixin
"""
import math
import numpy as np
from PyQt6.QtCore import QLine, QPoint, QRect, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygon
from PyQt6.QtWidgets import QScrollArea

from core.frame_time import frame_count, frame_to_sec, normalize_fps
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
    analysis_markers_for_widget,
    roughcut_major_markers_for_widget,
)
from ui.timeline.speaker_labels import (
    current_speaker_settings,
    normalize_speaker_id,
    speaker_labels_for_segment,
)
from ui.timeline.timeline_segment_style import (
    QUALITY_SEGMENT_COLORS,
    SEGMENT_TEXT_KIND_STYLES,
    STAGE_CONFIDENCE_COLORS,
    SUBTITLE_STATE_SEGMENT_COLORS,
    build_stt_selection_index,
    cut_boundary_scan_marker_verified,
    final_stt_selection_source,
    scan_boundary_marker_label,
    scan_boundary_marker_visual,
    segment_text_kind,
    stt_candidate_selected,
    stt_candidate_selected_by_llm,
    stt_candidate_selection_state,
    stt_candidate_unselected,
    stt_preview_source,
    stt_preview_visual_style,
    subtitle_confidence_chips,
    subtitle_render_detail_mode,
    subtitle_segment_style_cache_key,
    subtitle_segment_visual_style,
)

WAVEFORM_RULER_BG = "#24231F"
WAVEFORM_RULER_LINE = "#6A6651"
WAVEFORM_BG = "#2B2500"
WAVEFORM_BG_GRID = "#463D08"
WAVEFORM_MIDLINE = "#827C43"
WAVEFORM_TOP = QColor(80, 245, 238, 232)
WAVEFORM_BOTTOM = QColor(23, 159, 166, 238)
WAVEFORM_TOP_LOUD = QColor(144, 255, 247, 248)
WAVEFORM_BOTTOM_LOUD = QColor(35, 214, 220, 248)
WAVEFORM_TOP_QUIET = QColor(58, 168, 164, 160)
WAVEFORM_BOTTOM_QUIET = QColor(35, 104, 111, 155)
WAVEFORM_VAD_OVERLAY = QColor(0, 255, 210, 22)


class TimelinePaintMixin:
    def _ruler_step_candidates_frames(self, fps: float) -> list[int]:
        base_steps = {
            1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 24, 25, 30, 36, 40, 45, 48, 50,
            60, 72, 75, 90, 96, 100, 120, 144, 150, 180, 192, 200, 240, 300, 360,
            480, 600, 720, 900, 1200, 1800, 2400, 3600,
        }
        for multiplier in (0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 30.0, 60.0):
            base_steps.add(max(1, int(round(float(fps) * multiplier))))
        return sorted(base_steps)

    def _ruler_step_frames(self, fps: float, min_label_px: float) -> tuple[int, int]:
        pixels_per_frame = max(0.001, float(getattr(self, "pps", 1.0) or 1.0) / max(1.0, float(fps or 30.0)))
        min_major_frames = max(1, int(math.ceil(float(min_label_px or 0.0) / pixels_per_frame)))
        steps = self._ruler_step_candidates_frames(fps)
        while steps[-1] < min_major_frames:
            steps.append(steps[-1] * 2)
        major_frames = next((step for step in steps if step >= min_major_frames), steps[-1])
        min_minor_frames = max(1, int(math.ceil(12.0 / pixels_per_frame)))
        minor_frames = max(min_minor_frames, int(round(major_frames / 5.0)))
        if minor_frames >= major_frames:
            minor_frames = major_frames
        return max(1, major_frames), max(1, minor_frames)

    def _speech_mask_for_waveform(self, wf_len: int):
        wf_len = max(0, int(wf_len or 0))
        if wf_len <= 0:
            return None
        if self._speech_mask is None or self._speech_mask_wf_len != wf_len:
            mask = np.zeros(wf_len, dtype=bool)
            for vs in list(getattr(self, "vad_segments", []) or []):
                try:
                    s_idx = max(0, int(float(vs.get("start", 0.0) or 0.0) * 100))
                    e_idx = min(wf_len, int(float(vs.get("end", 0.0) or 0.0) * 100) + 1)
                except Exception:
                    continue
                if e_idx > s_idx:
                    mask[s_idx:e_idx] = True
            self._speech_mask = mask
            self._speech_mask_wf_len = wf_len
            self._waveform_line_cache_key = None
            self._waveform_line_cache = None
        return self._speech_mask

    def _waveform_line_groups_cached(self, x_start: int, x_end: int):
        wf = getattr(self, "_waveform", None)
        if wf is None:
            return None
        try:
            wf_len = len(wf)
        except Exception:
            return None
        if wf_len <= 0:
            return None
        speech_mask = self._speech_mask_for_waveform(wf_len)
        if speech_mask is None:
            return None
        pps = max(0.001, float(getattr(self, "pps", 1.0) or 1.0))
        x_start = max(0, int(x_start or 0))
        x_end = max(x_start, int(x_end or x_start))
        key = (
            id(wf),
            wf_len,
            id(speech_mask),
            round(pps, 4),
            int(x_start),
            int(x_end),
            int(WAVE_HALF),
        )
        if key == getattr(self, "_waveform_line_cache_key", None):
            cached = getattr(self, "_waveform_line_cache", None)
            if cached is not None:
                return cached

        top_norm_lines: list[QLine] = []
        bot_norm_lines: list[QLine] = []
        top_loud_lines: list[QLine] = []
        bot_loud_lines: list[QLine] = []
        top_sil_lines: list[QLine] = []
        bot_sil_lines: list[QLine] = []
        for x in range(x_start, x_end):
            idx = int((x / pps) * 100)
            if idx >= wf_len:
                break
            try:
                val = float(wf[idx])
            except Exception:
                continue
            if val < 0.008:
                continue
            h = max(1, min(int(val * (WAVE_HALF * 2.0)), WAVE_HALF))
            if bool(speech_mask[idx]):
                if val > 0.6:
                    top_loud_lines.append(QLine(x, WAVE_MID, x, WAVE_MID - h))
                    bot_loud_lines.append(QLine(x, WAVE_MID + 1, x, WAVE_MID + h))
                else:
                    top_norm_lines.append(QLine(x, WAVE_MID, x, WAVE_MID - h))
                    bot_norm_lines.append(QLine(x, WAVE_MID + 1, x, WAVE_MID + h))
            else:
                top_sil_lines.append(QLine(x, WAVE_MID, x, WAVE_MID - h))
                bot_sil_lines.append(QLine(x, WAVE_MID + 1, x, WAVE_MID + h))
        result = (
            top_norm_lines,
            bot_norm_lines,
            top_loud_lines,
            bot_loud_lines,
            top_sil_lines,
            bot_sil_lines,
        )
        self._waveform_line_cache_key = key
        self._waveform_line_cache = result
        return result

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
        track_bottom = SEG_BOT
        stt_preview_segments = []
        final_stt_segments = []
        selected_final_stt_segments = []
        stt1_preview_segments = []
        stt2_preview_segments = []
        for seg in visible_segments:
            if bool(seg.get("stt_pending") or seg.get("_live_stt_preview")):
                stt_preview_segments.append(seg)
                if stt_preview_source(seg) == "STT2":
                    stt2_preview_segments.append(seg)
                else:
                    stt1_preview_segments.append(seg)
                continue
            final_stt_segments.append(seg)
            if final_stt_selection_source(seg):
                selected_final_stt_segments.append(seg)
        selected_final_stt_index = build_stt_selection_index(selected_final_stt_segments)
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
            provider = getattr(self, "_speaker_settings_provider", None)
            if callable(provider):
                try:
                    return provider()
                except Exception:
                    pass
            owner = self.parent()
            while owner and not hasattr(owner, "settings"):
                owner = owner.parent()
            return getattr(owner, "settings", {}) if owner is not None else {}

        if callable(getattr(self, "_speaker_settings_provider", None)):
            speaker_settings = _owner_speaker_settings()
        else:
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

        def _analysis_silence_markers():
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
            return [
                marker for marker in markers
                if str(marker.get("kind", "") or "").strip().lower() == "silence"
            ]

        def _draw_speaker_silence_overlay():
            markers = _analysis_silence_markers()
            if not markers:
                return
            clip = paint_clip
            lane_h = 7
            lane_top = max(speaker_top + 1, speaker_bot - lane_h - 2)
            fill_batches: dict[tuple[str, int], list[QRect]] = {}
            border_batches: dict[tuple[str, int], list[QRect]] = {}
            for marker in markers:
                start = max(0.0, float(marker.get("start", 0.0) or 0.0))
                end = max(start, float(marker.get("end", start) or start))
                x1 = self._x(start)
                x2 = self._x(end)
                if x2 < clip.left() or x1 > clip.right():
                    continue
                w = max(2, x2 - x1)
                color = QColor(str(marker.get("color", "#8B949E")))
                rect = QRect(int(x1), lane_top, int(w), lane_h)
                _append_batch(fill_batches, (color.name(), int(marker.get("alpha", 120) or 120)), rect)
                _append_batch(border_batches, (color.name(), 220), rect)
            _draw_color_batches(fill_batches)
            _draw_color_batches(border_batches, as_pen=True)

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

        def _draw_cut_boundary_work_lane():
            scan_rows = getattr(self, "scan_boundary_times", []) or []
            if hasattr(self, "_visible_items_for_paint"):
                candidates = self._visible_items_for_paint(
                    scan_rows,
                    "scan_boundaries",
                    visible_start_sec,
                    visible_end_sec,
                    pad_sec=0.05,
                )
            else:
                candidates = list(scan_rows or [])
            items = [
                item for item in list(candidates or [])
                if isinstance(item, dict) and not cut_boundary_scan_marker_verified(item)
            ]
            if not items:
                return
            clip = paint_clip
            lane_top = RULER_H + WAVE_H + 5
            lane_h = max(18, SEG_TOP - lane_top - 7)
            x_start = max(0, clip.left())
            x_end = min(total_w, clip.right() + 1)
            p.setPen(QPen(QColor("#2D3942"), 1))
            p.setBrush(QColor(11, 20, 24, 172))
            p.drawRect(QRect(x_start, lane_top, max(1, x_end - x_start), lane_h))
            p.setFont(QFont(config.FONT, 8, QFont.Weight.Bold))
            detail_items = []
            for item in items:
                try:
                    sec = float(item.get("timeline_sec", item.get("time", item.get("start", 0.0))) or 0.0)
                except Exception:
                    continue
                x = self._x(sec)
                if x < clip.left() - 8 or x > clip.right() + 8:
                    continue
                visual = scan_boundary_marker_visual(item)
                color = QColor(str(visual.get("color") or "#8E8E93"))
                width = max(2, int(visual.get("width", 2) or 2))
                style_name = str(visual.get("style") or "solid")
                pen_style = Qt.PenStyle.DashLine if style_name == "dash" else (Qt.PenStyle.DotLine if style_name == "dot" else Qt.PenStyle.SolidLine)
                p.setPen(QPen(color, width, pen_style))
                p.drawLine(int(x), lane_top + 3, int(x), lane_top + lane_h - 4)
                label = scan_boundary_marker_label(item)
                if label and not dense_segment_mode:
                    detail_items.append((label, color, x, width))
            for label, color, x, _width in detail_items:
                label_w = max(34, min(76, p.fontMetrics().horizontalAdvance(label) + 12))
                rect = QRect(int(x) + 7, lane_top + 2, label_w, min(18, lane_h - 4))
                if rect.right() > clip.right():
                    rect.moveRight(int(x) - 7)
                p.setPen(Qt.PenStyle.NoPen)
                fill = QColor("#11181C")
                fill.setAlpha(218)
                p.setBrush(fill)
                p.drawRoundedRect(QRectF(rect), 4, 4)
                p.setPen(QPen(color, 1))
                p.drawRoundedRect(QRectF(rect), 4, 4)
                p.setPen(QColor("#F5F7FA"))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

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
                track_bottom,
            ):
                p.drawLine(draw_left, y, draw_right, y)

        def _coalesce_rects(rects, *, max_gap_px: int = 0) -> list[QRect]:
            """Merge adjacent same-lane rects in dense modes to reduce painter calls."""
            rows: dict[tuple[int, int], list[QRect]] = {}
            for rect in rects or []:
                if rect is None or not rect.isValid() or rect.isEmpty():
                    continue
                rows.setdefault((int(rect.y()), int(rect.height())), []).append(rect)
            merged: list[QRect] = []
            for (y, h), row_rects in rows.items():
                row_rects.sort(key=lambda r: (int(r.left()), int(r.right())))
                cur_left: int | None = None
                cur_right: int | None = None
                for rect in row_rects:
                    left = int(rect.left())
                    right = int(rect.right())
                    if cur_left is not None and left <= cur_right + max(0, int(max_gap_px)) + 1:
                        cur_right = max(cur_right, right)
                        continue
                    if cur_left is not None:
                        merged.append(QRect(cur_left, y, max(1, cur_right - cur_left + 1), h))
                    cur_left, cur_right = left, right
                if cur_left is not None:
                    merged.append(QRect(cur_left, y, max(1, cur_right - cur_left + 1), h))
            return merged

        def _draw_rect_batch(
            rects,
            *,
            fill: QColor | None = None,
            pen: QPen | None = None,
            coalesce: bool = False,
            max_gap_px: int = 0,
        ):
            if not rects:
                return
            if coalesce and len(rects) >= 24:
                rects = _coalesce_rects(rects, max_gap_px=max_gap_px)
            p.setBrush(QBrush(fill) if fill is not None else Qt.BrushStyle.NoBrush)
            p.setPen(pen if pen is not None else Qt.PenStyle.NoPen)
            try:
                p.drawRects(rects)
            except TypeError:
                for rect in rects:
                    p.drawRect(rect)

        def _append_batch(batches: dict, key, rect: QRect):
            batches.setdefault(key, []).append(rect)

        def _draw_color_batches(
            batches: dict,
            *,
            as_pen: bool = False,
            width: int = 1,
            style=Qt.PenStyle.SolidLine,
            coalesce: bool = False,
            max_gap_px: int = 0,
        ):
            for key, rects in batches.items():
                if isinstance(key, tuple):
                    color = QColor(str(key[0]))
                    if len(key) > 1:
                        color.setAlpha(int(key[1]))
                else:
                    color = QColor(str(key))
                if as_pen:
                    _draw_rect_batch(rects, pen=QPen(color, width, style), coalesce=coalesce, max_gap_px=max_gap_px)
                else:
                    _draw_rect_batch(rects, fill=color, coalesce=coalesce, max_gap_px=max_gap_px)

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
        p.fillRect(QRect(clip_left, 0, max(1, clip_right - clip_left), RULER_H), QColor(WAVEFORM_RULER_BG))
        p.setPen(QPen(QColor(WAVEFORM_RULER_LINE), 1))
        p.drawLine(clip_left, RULER_H - 1, clip_right, RULER_H - 1)

        fps = normalize_fps(self._get_fps() if hasattr(self, "_get_fps") else getattr(self, "frame_rate", 30.0))
        total_frames = max(0, frame_count(total_secs, fps))
        visible_start_frame = max(0, self._frame_from_x(clip_left)) if hasattr(self, "_frame_from_x") else 0
        visible_end_frame = max(visible_start_frame + 1, self._frame_from_x(clip_right) + 1) if hasattr(self, "_frame_from_x") else total_frames
        major_step_frames, sub_step_frames = self._ruler_step_frames(fps, 80.0)

        # 메이저 틱 + 라벨
        frame_i = max(0, ((visible_start_frame // major_step_frames) * major_step_frames) - major_step_frames)
        while frame_i <= total_frames:
            tx = self._frame_x(frame_i) if hasattr(self, "_frame_x") else self._x(frame_to_sec(frame_i, fps))
            if tx > clip_right:
                break
            if frame_i > 0:
                p.setPen(QColor("#7B7A69"))
                p.drawLine(tx, 10, tx, RULER_H - 9)
                label = _fmt_ruler(frame_to_sec(frame_i, fps))
                lw = fm_ruler.horizontalAdvance(label)
                p.setPen(QColor("#B9B5A2"))
                p.drawText(tx - lw // 2, RULER_H - 7, label)
            frame_i += major_step_frames

        # 서브 틱 (라벨 없음)
        frame_f = max(0, ((visible_start_frame // sub_step_frames) * sub_step_frames) - sub_step_frames)
        while frame_f <= total_frames:
            tx = self._frame_x(frame_f) if hasattr(self, "_frame_x") else self._x(frame_to_sec(frame_f, fps))
            if tx > clip_right:
                break
            # 메이저 틱 위치면 스킵
            if major_step_frames > 0 and frame_f % major_step_frames == 0:
                frame_f += sub_step_frames
                continue
            p.setPen(QColor("#555244"))
            p.drawLine(tx, 13, tx, RULER_H - 14)
            frame_f += sub_step_frames

        p.fillRect(QRect(clip_left, RULER_H, max(1, clip_right - clip_left), WAVE_H), QColor(WAVEFORM_BG))
        p.setPen(QPen(QColor(WAVEFORM_BG_GRID), 1))
        p.drawLine(clip_left, RULER_H, clip_right, RULER_H)
        p.drawLine(clip_left, RULER_H + WAVE_H - 1, clip_right, RULER_H + WAVE_H - 1)
        p.setPen(QPen(QColor(WAVEFORM_MIDLINE), 1))
        p.drawLine(clip_left, WAVE_MID, clip_right, WAVE_MID)

        if self._waveform is not None:
            clip = paint_clip
            x_start = max(0, clip.left())
            x_end = min(total_w, clip.right() + 1)

            pen_top_norm = QPen(WAVEFORM_TOP, 1)
            pen_bot_norm = QPen(WAVEFORM_BOTTOM, 1)
            pen_top_loud = QPen(WAVEFORM_TOP_LOUD, 1)
            pen_bot_loud = QPen(WAVEFORM_BOTTOM_LOUD, 1)
            pen_top_sil = QPen(WAVEFORM_TOP_QUIET, 1)
            pen_bot_sil = QPen(WAVEFORM_BOTTOM_QUIET, 1)
            line_groups = self._waveform_line_groups_cached(x_start, x_end)
            if line_groups is None:
                line_groups = ([], [], [], [], [], [])
            (
                top_norm_lines,
                bot_norm_lines,
                top_loud_lines,
                bot_loud_lines,
                top_sil_lines,
                bot_sil_lines,
            ) = line_groups

            for pen, lines in (
                (pen_top_norm, top_norm_lines),
                (pen_bot_norm, bot_norm_lines),
                (pen_top_loud, top_loud_lines),
                (pen_bot_loud, bot_loud_lines),
                (pen_top_sil, top_sil_lines),
                (pen_bot_sil, bot_sil_lines),
            ):
                if lines:
                    p.setPen(pen)
                    p.drawLines(lines)

            p.setPen(Qt.PenStyle.NoPen)
            vad_rects = []
            for vs in visible_vad_segments:
                vx1 = self._x(vs["start"])
                vx2 = self._x(vs["end"])
                if vx2 < clip_left or vx1 > clip_right:
                    continue
                vad_rects.append(QRect(vx1, RULER_H, max(1, vx2 - vx1), WAVE_H))
            _draw_rect_batch(vad_rects, fill=WAVEFORM_VAD_OVERLAY)

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
        _draw_cut_boundary_work_lane()

        p.fillRect(QRect(clip_left, SEG_TOP, max(1, clip_right - clip_left), SEG_BOT - SEG_TOP), QColor("#11181C"))
        p.setPen(QPen(QColor("#2D3942"), 1))
        for y in (subtitle_top - 5, STT1_TOP - 3, STT2_TOP - 3, speaker_top - 3, voice_mid - 14, track_bottom):
            p.drawLine(clip_left, y, clip_right, y)

        def _draw_gap_lane(gaps):
            if not bool(getattr(self, "show_gap_insert_controls", True)):
                return
            if not gaps:
                return
            compact_gap_mode = bool(overview_mode or ultra_dense_segment_mode or len(gaps) >= 512)
            if compact_gap_mode:
                active_gaps = [g for g in gaps if g.get("active", False)]
                if not active_gaps:
                    return
                p.setFont(QFont(config.FONT, 9, QFont.Weight.Bold))
                for g in active_gaps:
                    x1, x2 = self._x(g["start"]), self._x(g["end"])
                    sw = max(4, x2 - x1)
                    if x2 < clip_left or x1 > clip_right:
                        continue
                    rect = QRect(x1, SEG_TOP, sw, SEG_BOT - SEG_TOP)
                    ir = self._icon_rect(x1, x2)
                    p.fillRect(rect, QColor(20, 16, 0, 118))
                    p.setPen(QPen(QColor("#FFFFFF"), 2))
                    p.drawRect(rect)
                    p.fillRect(ir, QColor("#3B1D20"))
                    p.setPen(QColor("#FF8A80"))
                    p.drawText(ir, Qt.AlignmentFlag.AlignCenter, "✕")
                return
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
            if ultra_dense_segment_mode and len(preview_segments) >= 96 and not selected_final_stt_segments:
                spans: list[tuple[int, int]] = []
                cur_l: int | None = None
                cur_r: int | None = None
                pps = float(getattr(self, "pps", 1.0) or 1.0)
                merge_gap_px = 4 if pps < 10.0 else 3
                for seg in preview_segments:
                    try:
                        x1 = self._x(float(seg.get("start", 0.0) or 0.0))
                        x2 = self._x(float(seg.get("end", seg.get("start", 0.0)) or seg.get("start", 0.0) or 0.0))
                    except Exception:
                        continue
                    if x2 < clip_left or x1 > clip_right:
                        continue
                    x2 = max(x1 + 1, x2)
                    if cur_l is not None and x1 <= cur_r + merge_gap_px:
                        cur_r = max(cur_r, x2)
                    else:
                        if cur_l is not None:
                            spans.append((cur_l, cur_r))
                        cur_l, cur_r = x1, x2
                if cur_l is not None:
                    spans.append((cur_l, cur_r))
                if spans:
                    rects = [QRect(left, lane_top, max(1, right - left), lane_bot - lane_top) for left, right in spans]
                    _draw_rect_batch(rects, fill=QColor(fill_hex))
                    _draw_rect_batch(rects, pen=QPen(QColor(border_hex), 1))
                return
            p.setFont(self._stt_preview_font() if hasattr(self, "_stt_preview_font") else QFont(config.FONT, 10))
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
                selection_state = (
                    stt_candidate_selection_state(seg, selected_final_stt_segments, selected_final_stt_index)
                    if selected_final_stt_segments
                    else ""
                )
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
                        p.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, preview_text)
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
                        p.setFont(self._stt_preview_font() if hasattr(self, "_stt_preview_font") else QFont(config.FONT, 10))

        def _draw_vector_subtitle_strips(segments):
            """Batch dense subtitle geometry so large projects repaint like vector strips."""
            if not segments:
                return set()
            pps = float(getattr(self, "pps", 1.0) or 1.0)
            aggregate_overview = bool(
                ultra_dense_segment_mode
                and (len(segments) >= 96 or (len(segments) >= 32 and pps < 10.0))
            )
            if aggregate_overview:
                spans: list[tuple[int, int]] = []
                detail_segments: list[dict] = []
                active_start = getattr(self, "active_seg_start", None)
                try:
                    active_start_f = float(active_start) if active_start is not None else None
                except Exception:
                    active_start_f = None
                hover_line = getattr(self, "_hover_line", None)
                merge_gap_px = 4 if pps < 10.0 else 3
                cur_l: int | None = None
                cur_r: int | None = None
                for seg in segments:
                    try:
                        start = float(seg.get("start", 0.0) or 0.0)
                        end = float(seg.get("end", start) or start)
                    except Exception:
                        continue
                    if end < start:
                        start, end = end, start
                    x1 = int(start * pps)
                    x2 = int(end * pps)
                    if x2 < clip_left or x1 > clip_right:
                        continue
                    is_active = active_start_f is not None and abs(start - active_start_f) < 0.001
                    is_hover = hover_line == seg.get("line")
                    if is_active or is_hover:
                        detail_segments.append(seg)
                        continue
                    x2 = max(x1 + 1, x2)
                    if cur_l is not None and x1 <= cur_r + merge_gap_px:
                        if x2 > cur_r:
                            cur_r = x2
                    else:
                        if cur_l is not None:
                            spans.append((cur_l, cur_r))
                        cur_l, cur_r = x1, x2
                if cur_l is not None:
                    spans.append((cur_l, cur_r))
                if spans:
                    sub_h = subtitle_bot - subtitle_top
                    speaker_h = speaker_bot - speaker_top
                    rects = [QRect(left, subtitle_top, max(1, right - left), sub_h) for left, right in spans]
                    speaker_rects = [QRect(left, speaker_top, max(1, right - left), speaker_h) for left, right in spans]
                    _draw_rect_batch(rects, fill=QColor(24, 64, 42, 168))
                    _draw_rect_batch(speaker_rects, fill=QColor(38, 98, 72, 156))
                    _draw_rect_batch(rects, pen=QPen(QColor(64, 148, 98, 170), 1))
                return set(), detail_segments

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
                style_key = subtitle_segment_style_cache_key(
                    seg,
                    render_epoch=render_epoch,
                    quality_filter=quality_filter,
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
            merge_gap_px = 1 if dense_segment_mode else 0
            for color_name, rects in fill_batches.items():
                _draw_rect_batch(rects, fill=QColor(color_name), coalesce=True, max_gap_px=merge_gap_px)
            for color_name, rects in speaker_batches.items():
                _draw_rect_batch(rects, fill=QColor(color_name), coalesce=True, max_gap_px=merge_gap_px)
            for color_name, rects in border_batches.items():
                _draw_rect_batch(rects, pen=QPen(QColor(color_name), 1), coalesce=True, max_gap_px=merge_gap_px)
            return drawn_ids

        if not scenegraph_subtitles:
            _draw_stt_preview_lane(stt1_preview_segments, STT1_TOP, STT1_BOT, "#173524", "#34C759", "#D7FFE4")
            _draw_stt_preview_lane(stt2_preview_segments, STT2_TOP, STT2_BOT, "#1A3148", "#64D2FF", "#BDEBFF")

            seg_font = self._subtitle_segment_font() if hasattr(self, "_subtitle_segment_font") else QFont(config.FONT, 11); p.setFont(seg_font)
            detail_segments = final_stt_segments
            vector_result = (
                _draw_vector_subtitle_strips(final_stt_segments)
                if dense_segment_mode and not bool(getattr(self, "_edit_active", False))
                else set()
            )
            if isinstance(vector_result, tuple):
                vector_drawn_ids, detail_segments = vector_result
            else:
                vector_drawn_ids = vector_result
            for seg in detail_segments:
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
                is_merge_preview = bool(
                    hasattr(self, "_is_merge_preview_segment")
                    and self._is_merge_preview_segment(seg)
                )
                native_inline_active = bool(
                    is_editing
                    and hasattr(self, "_native_inline_editor_active")
                    and self._native_inline_editor_active()
                )
                focus_detail = bool(is_active or is_hover or is_editing or is_merge_preview)
                compact_seg = sw < 24 or (dense_segment_mode and not focus_detail)
                is_stt_pending = bool(seg.get("stt_pending"))
                spk_color = _speaker_color(seg)
                visual_style = subtitle_segment_visual_style(
                    seg,
                    active=is_active,
                    hover=is_hover,
                    quality_filter=getattr(self, "quality_filter", "all"),
                )
                if is_editing:
                    visual_style = dict(visual_style)
                    visual_style["border"] = "#44FF88"
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
                if is_merge_preview:
                    preview_rect = rect.adjusted(1, 1, -1, -1)
                    if preview_rect.isValid():
                        p.fillRect(preview_rect, QColor(10, 132, 255, 36))
                    p.setPen(QPen(QColor("#0A84FF"), 2))
                    p.drawRect(rect.adjusted(0, 0, -1, -1))
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
                text_left = rect.x() + 10
                text_right = rect.right() - 9
                if hasattr(self, "_subtitle_segment_text_body_bounds"):
                    try:
                        body_left, body_right = self._subtitle_segment_text_body_bounds(seg)
                    except Exception:
                        body_left, body_right = text_left, text_right
                    text_left = max(text_left, int(body_left))
                    text_right = min(text_right, int(body_right))
                text_left = max(rect.x() + 6, text_left)
                text_right = min(rect.right() - 6, text_right)
                selected_source = final_stt_selection_source(seg)
                show_badge = bool(
                    selected_source
                    and rect.width() >= 104
                    and (not dense_segment_mode or focus_detail)
                    and (text_right - text_left) >= 70
                )
                badge_reserved_w = 44 if show_badge else 0
                text_rect = QRect(
                    text_left,
                    rect.y() + top_pad,
                    max(8, text_right - text_left - badge_reserved_w),
                    rect.height() - top_pad - 6,
                )
                if is_editing and not native_inline_active:
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
                            p.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, seg_text)
                        else:
                            p.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, seg_text)
                        if show_badge:
                            is_llm_choice = bool(str(seg.get("stt_ensemble_llm_selected_source", "") or "").strip())
                            badge_rect = QRect(max(text_left + 6, text_right - 38), rect.y() + 6, 38, 18)
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
            _draw_speaker_silence_overlay()

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
                p.setFont(QFont(config.FONT, 9, QFont.Weight.Bold))
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

        # Cut boundary data remains active for snapping and subtitle timing, but
        # the dedicated blue UI lines are hidden so the middle-category lane stays
        # visually clean. Do not clear boundary_times or scan_boundary_times here.

        user_alignment_guides = [
            self._x(float(sec or 0.0))
            for sec in list(getattr(self, "user_alignment_guides", []) or [])
        ]
        if user_alignment_guides:
            p.setPen(QPen(QColor(142, 142, 147, 170), 2, Qt.PenStyle.SolidLine))
            for guide_x in user_alignment_guides:
                if guide_x < clip_left - 4 or guide_x > clip_right + 4:
                    continue
                p.drawLine(int(guide_x), 0, int(guide_x), CANVAS_H)

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
