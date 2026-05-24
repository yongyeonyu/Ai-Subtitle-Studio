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

from core.frame_time import frame_count, frame_to_sec, normalize_fps, sec_to_nearest_frame
from core.runtime import config
from ui.editor.ux.timeline_playhead_mode import playhead_line_color_hex
from ui.style import COLORS

from ui.timeline.timeline_constants import (
    CANVAS_H,
    DIAMOND_Y,
    HANDLE_R,
    LANE_LABEL_GUTTER_W,
    RULER_H,
    SCORE_H,
    SCORE_TOP,
    SEG_BOT,
    SEG_TOP,
    SEGMENT_HANDLE_MIN_WIDTH,
    SPEAKER_BOT,
    SPEAKER_TOP,
    STT1_BOT,
    STT1_TOP,
    STT2_BOT,
    STT2_TOP,
    STT_PREVIEW_VERTICAL_INSET,
    SUBTITLE_BOT,
    SUBTITLE_TOP,
    VOICE_ACTIVITY_BOT,
    VOICE_ACTIVITY_TOP,
    WAVE_H,
    WAVE_HALF,
    WAVE_MID,
)
from ui.timeline.timeline_analysis import (
    SUBTITLE_SCORE_DETECTION_KINDS,
    analysis_markers_for_widget,
    roughcut_major_markers_for_widget,
    subtitle_score_overlay_marker,
)
from ui.timeline.timeline_roughcut_paint import (
    clamp_expanded_roughcut_marker_spans,
    coalesce_roughcut_paint_markers,
    expanded_roughcut_marker_span,
    visible_roughcut_label_span,
)
from ui.timeline.paint_passes import (
    build_aggregate_vector_subtitle_paint_plan,
    build_cut_boundary_work_lane_paint_plan,
    build_gap_lane_paint_plan,
    build_stt_preview_lane_paint_plan,
    coalesce_rects_by_row,
    visible_pixel_span,
)
from ui.timeline.stt_preview_layout import dedupe_stt_preview_segments_for_display
from ui.timeline.speaker_labels import (
    current_speaker_settings,
    normalize_speaker_id,
    speaker_labels_for_segment,
    speaker_rows_for_segment,
)
from ui.timeline.timeline_segment_style import (
    SEGMENT_TEXT_KIND_STYLES,  # noqa: F401 - compatibility re-export for tests/legacy callers
    SPEAKER_SEGMENT_BORDER,
    SPEAKER_SEGMENT_FILL,
    build_stt_selection_index,
    cut_boundary_scan_marker_verified,  # noqa: F401 - compatibility re-export for tests/legacy callers
    final_stt_selection_source,
    segment_text_kind,  # noqa: F401 - compatibility re-export for tests/legacy callers
    speaker_segment_fill_hex,
    speaker_segment_text_hex,
    stt_candidate_selected,  # noqa: F401 - compatibility re-export for tests/legacy callers
    stt_candidate_selected_by_llm,  # noqa: F401 - compatibility re-export for tests/legacy callers
    stt_candidate_selection_state,  # noqa: F401 - compatibility re-export for tests/legacy callers
    stt_candidate_unselected,  # noqa: F401 - compatibility re-export for tests/legacy callers
    stt_preview_source,
    stt_preview_visual_style,
    subtitle_confidence_chips,
    subtitle_render_detail_mode,
    subtitle_segment_style_cache_key,
    subtitle_segment_visual_style,
)
from ui.ux.apple_black_palette import APPLE_BLACK_WAVEFORM

WAVEFORM_RULER_BG = APPLE_BLACK_WAVEFORM["ruler_bg"]
WAVEFORM_RULER_LINE = APPLE_BLACK_WAVEFORM["ruler_line"]
WAVEFORM_BG = APPLE_BLACK_WAVEFORM["bg"]
WAVEFORM_BG_GRID = APPLE_BLACK_WAVEFORM["bg_grid"]
WAVEFORM_MIDLINE = APPLE_BLACK_WAVEFORM["midline"]
WAVEFORM_TOP = QColor(*APPLE_BLACK_WAVEFORM["top_rgba"])
WAVEFORM_BOTTOM = QColor(*APPLE_BLACK_WAVEFORM["bottom_rgba"])
WAVEFORM_TOP_LOUD = QColor(*APPLE_BLACK_WAVEFORM["top_loud_rgba"])
WAVEFORM_BOTTOM_LOUD = QColor(*APPLE_BLACK_WAVEFORM["bottom_loud_rgba"])
WAVEFORM_TOP_QUIET = QColor(*APPLE_BLACK_WAVEFORM["top_quiet_rgba"])
WAVEFORM_BOTTOM_QUIET = QColor(*APPLE_BLACK_WAVEFORM["bottom_quiet_rgba"])
WAVEFORM_VAD_OVERLAY = QColor(*APPLE_BLACK_WAVEFORM["vad_overlay_rgba"])


def should_paint_subtitle_segment_text(
    *,
    native_inline_active: bool,
    rect_width: int,
    dense_segment_mode: bool,
    focus_detail: bool,
) -> bool:
    if native_inline_active:
        return False
    return int(rect_width) >= 44 and (not bool(dense_segment_mode) or bool(focus_detail))


class TimelinePaintMixin:
    def _timeline_playback_active(self) -> bool:
        owner = self.parent()
        while owner is not None:
            probe = getattr(owner, "_is_video_playing", None)
            if callable(probe):
                try:
                    return bool(probe())
                except (RuntimeError, AttributeError, TypeError):
                    pass
            player = getattr(getattr(owner, "video_player", None), "media_player", None)
            if player is not None:
                try:
                    state = player.playbackState()
                    playing_state = getattr(player.PlaybackState, "PlayingState", None)
                    if playing_state is not None:
                        return bool(state == playing_state)
                except (RuntimeError, AttributeError, TypeError):
                    pass
            next_owner = None
            try:
                next_owner = owner.parentWidget()
            except Exception:
                next_owner = None
            if next_owner is None:
                try:
                    next_owner = owner.parent()
                except Exception:
                    next_owner = None
            owner = next_owner
        return False

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

    def _fps_ruler_minor_step_frames(self, fps: float, min_tick_px: float = 6.0) -> int:
        fps_frames = max(1, int(round(normalize_fps(fps))))
        pps = max(1.0, float(getattr(self, "pps", 1.0) or 1.0))
        if pps < 96.0:
            return fps_frames
        ticks_per_second = max(1, int(math.floor(pps / max(1.0, float(min_tick_px or 0.0)))))
        return max(1, int(math.ceil(float(fps_frames) / float(ticks_per_second))))

    def _ruler_nice_seconds_step(self, required_seconds: float) -> int:
        required = max(1.0, float(required_seconds or 1.0))
        steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600]
        while steps[-1] < required:
            steps.append(steps[-1] * 2)
        return next((step for step in steps if step >= required), steps[-1])

    def _fps_ruler_major_step_seconds(self, min_major_px: float = 42.0) -> int:
        pps = max(0.001, float(getattr(self, "pps", 1.0) or 1.0))
        return self._ruler_nice_seconds_step(float(min_major_px or 0.0) / pps)

    def _fps_ruler_reference_label_step_seconds(self, min_label_px: float = 72.0) -> int:
        pps = max(0.001, float(getattr(self, "pps", 1.0) or 1.0))
        major_step = self._fps_ruler_major_step_seconds()
        label_step = self._ruler_nice_seconds_step(float(min_label_px or 0.0) / pps)
        if label_step <= major_step:
            return int(major_step)
        multiplier = int(math.ceil(float(label_step) / float(max(1, major_step))))
        return int(max(major_step, major_step * multiplier))

    def _fps_ruler_should_draw_minor_ticks(self, major_step_seconds: int, minor_step_frames: int, fps: float) -> bool:
        fps_frames = max(1, int(round(normalize_fps(fps))))
        return int(major_step_seconds or 1) <= 1 and int(minor_step_frames or fps_frames) < fps_frames

    def _ruler_time_label_background_rect(
        self,
        center_x: int,
        label_width: int,
        *,
        baseline_y: int,
        font_ascent: int,
        font_descent: int,
        clip_left: int | None = None,
        clip_right: int | None = None,
    ) -> QRect:
        pad_x = 5
        pad_y = 2
        left = int(round(center_x - (max(1, int(label_width or 0)) / 2.0))) - pad_x
        top = max(1, int(baseline_y) - max(1, int(font_ascent or 0)) - pad_y)
        bottom = min(RULER_H - 2, int(baseline_y) + max(0, int(font_descent or 0)) + pad_y)
        rect = QRect(left, top, max(1, int(label_width or 0) + pad_x * 2), max(1, bottom - top + 1))
        if clip_left is None or clip_right is None:
            return rect
        clip_rect = QRect(int(clip_left), 0, max(1, int(clip_right) - int(clip_left)), RULER_H)
        return rect.intersected(clip_rect)


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
            if hasattr(self, "visible_segments_for_time_window"):
                visible_segments = self.visible_segments_for_time_window(
                    visible_start_sec,
                    visible_end_sec,
                    pad_sec=0.35,
                )
            else:
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
        voice_top = VOICE_ACTIVITY_TOP
        voice_bot = VOICE_ACTIVITY_BOT
        voice_mid = voice_top + ((voice_bot - voice_top) // 2)
        track_bottom = SEG_BOT
        selected_final_stt_segments = []
        selected_final_stt_index = {}
        if hasattr(self, "visible_segment_lanes_cached"):
            lane_data = self.visible_segment_lanes_cached(visible_segments)
            stt_preview_segments = lane_data.get("stt_preview_segments") or []
            final_stt_segments = lane_data.get("final_segments") or []
            selected_final_stt_segments = lane_data.get("selected_final_segments") or []
            stt1_preview_segments = lane_data.get("stt1_preview_segments") or []
            stt2_preview_segments = lane_data.get("stt2_preview_segments") or []
            selected_final_stt_index = lane_data.get("selected_final_index") or {}
            stt1_lane_map = lane_data.get("stt1_lane_map") or {}
            stt1_lane_count = int(lane_data.get("stt1_lane_count") or 1)
            stt2_lane_map = lane_data.get("stt2_lane_map") or {}
            stt2_lane_count = int(lane_data.get("stt2_lane_count") or 1)
            stt_selection_states = lane_data.get("stt_selection_states") or {}
        else:
            stt_preview_segments = []
            final_stt_segments = []
            stt1_preview_segments = []
            stt2_preview_segments = []
            stt1_lane_map = {}
            stt1_lane_count = 1
            stt2_lane_map = {}
            stt2_lane_count = 1
            stt_selection_states = {}
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
            stt1_preview_segments = dedupe_stt_preview_segments_for_display(stt1_preview_segments)
            stt2_preview_segments = dedupe_stt_preview_segments_for_display(stt2_preview_segments)
            stt_preview_segments = stt1_preview_segments + stt2_preview_segments
            selected_final_stt_index = build_stt_selection_index(selected_final_stt_segments)
        scenegraph_subtitles = bool(getattr(self, "_scenegraph_subtitle_rendering", False)) and not bool(getattr(self, "_edit_active", False))
        # Keep the timeline body visually stable while playback advances so
        # narrow playhead dirty-rect updates do not leave a progressive
        # fill/trail behind.
        actual_playback_active = bool(self._timeline_playback_active()) if hasattr(self, "_timeline_playback_active") else False
        body_playback_active = False
        subtitle_detail_mode = subtitle_render_detail_mode(
            visible_segment_count=len(final_stt_segments) + len(stt_preview_segments),
            pps=float(getattr(self, "pps", 0.0) or 0.0),
            editing=bool(getattr(self, "_edit_active", False)),
            scenegraph=scenegraph_subtitles,
            playback_active=body_playback_active,
        )
        playback_light_mode = False
        dense_segment_mode = subtitle_detail_mode in {"dense", "ultra"}
        ultra_dense_segment_mode = subtitle_detail_mode == "ultra"
        self._paint_density_mode = subtitle_detail_mode

        def _draw_canvas_playhead(
            *,
            include_subtitle_band: bool,
            include_non_subtitle_band: bool,
            include_handle: bool,
        ) -> None:
            external_overlay = bool(getattr(self, "_external_playhead_overlay", False)) and not bool(
                getattr(self, "_single_owner_2d_renderer", True)
            )
            if self.playhead_sec < 0 or external_overlay:
                return
            px = int(self._x(self.playhead_sec))
            ph_color = QColor(playhead_line_color_hex(getattr(self, "focus_mode", None)))
            p.setPen(QPen(ph_color, 2))
            if include_non_subtitle_band:
                top_end = max(0, int(subtitle_top))
                if top_end > 0:
                    p.drawLine(px, 0, px, top_end)
                bottom_start = min(CANVAS_H, max(0, int(subtitle_bot)))
                if bottom_start < CANVAS_H:
                    p.drawLine(px, bottom_start, px, CANVAS_H)
            if include_subtitle_band:
                band_top = max(0, int(subtitle_top))
                band_bottom = min(CANVAS_H, max(0, int(subtitle_bot)))
                if band_top < band_bottom:
                    p.drawLine(px, band_top, px, band_bottom)
            if include_handle:
                handle_r = 7
                self._playhead_handle_rect = QRect(int(px - handle_r), 2, handle_r * 2, handle_r * 2)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setBrush(QBrush(QColor("#FF453A" if getattr(self, "playhead_busy", False) else COLORS["warning"])))
                p.setPen(QPen(QColor("#FFFFFF"), 1))
                p.drawEllipse(self._playhead_handle_rect)
                p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        def _owner_speaker_settings():
            provider = getattr(self, "_speaker_settings_provider", None)
            if callable(provider):
                try:
                    return provider()
                except (RuntimeError, AttributeError, TypeError):
                    pass
            owner = self.parent()
            while owner and not hasattr(owner, "settings"):
                owner = owner.parent()
            return getattr(owner, "settings", {}) if owner is not None else {}

        if callable(getattr(self, "_speaker_settings_provider", None)):
            speaker_settings = _owner_speaker_settings()
        else:
            speaker_settings = current_speaker_settings(_owner_speaker_settings())

        def _speaker_rows(seg):
            return speaker_rows_for_segment(speaker_settings, seg)

        def _speaker_color(seg):
            rows = _speaker_rows(seg)
            if rows:
                return QColor(str(rows[0].get("color") or "#8E8E93"))
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
            if voice_bot <= voice_top:
                return
            clip = paint_clip
            lane_top = voice_top
            lane_h = max(8, voice_bot - voice_top)
            center_y = lane_top + (lane_h // 2)
            p.setPen(Qt.PenStyle.NoPen)
            voice_segments = (
                visible_voice_activity_segments
                if isinstance(visible_voice_activity_segments, list)
                else list(visible_voice_activity_segments or [])
            )
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
            voice_segments = [
                vs for vs in list(voice_segments or [])
                if str(vs.get("kind", "") or "").strip().lower() not in SUBTITLE_SCORE_DETECTION_KINDS
            ]
            voice_segments = [
                vs for vs in voice_segments
                if str(vs.get("kind", "") or "").strip().lower() not in {
                    "generation_silence",
                    "linked_silence",
                    "llm_selected",
                    "manual_selected",
                    "pending",
                    "silence",
                    "subtitle_score",
                }
                and str(vs.get("label", "") or "").strip() not in {"무음", "무음구간"}
            ]
            if not voice_segments:
                return

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
                if w >= 56 and not dense_segment_mode:
                    label_items.append((vs, x1, w))
            _draw_color_batches(fill_batches)
            _draw_color_batches(border_batches, as_pen=True)
            if label_items:
                p.setFont(QFont(config.FONT, 8, QFont.Weight.Bold))
                p.setPen(QColor("#F5F7FA"))
                for vs, x1, w in label_items:
                    label_rect = QRect(int(x1) + 5, lane_top, max(8, int(w) - 10), lane_h)
                    p.save()
                    p.setClipRect(label_rect.adjusted(0, 0, 1, 0))
                    p.drawText(
                        label_rect,
                        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                        str(vs.get("label", "") or ""),
                    )
                    p.restore()
            p.setPen(QPen(QColor(87, 157, 255, 80), 1))
            p.drawLine(max(0, clip.left()), center_y, min(total_w, clip.right() + 1), center_y)

        def _draw_subtitle_score_labels(segments):
            if actual_playback_active:
                return
            if not segments:
                return
            if SCORE_H <= 8:
                return
            p.setFont(QFont(config.FONT, 9, QFont.Weight.Bold))
            fm = p.fontMetrics()
            segment_rects = []
            label_items = []
            for seg in segments:
                try:
                    x1 = self._x(float(seg.get("start", 0.0) or 0.0))
                    x2 = self._x(float(seg.get("end", seg.get("start", 0.0)) or 0.0))
                except Exception:
                    continue
                visible_span = visible_pixel_span(
                    x1,
                    x2,
                    clip_left=clip_left,
                    clip_right=clip_right,
                    min_edge_fragment_px=2,
                )
                if visible_span is None:
                    continue
                draw_x1, draw_x2 = visible_span
                width = max(2, int(draw_x2 - draw_x1))
                segment_rects.append(QRect(int(draw_x1), int(SCORE_TOP), width, int(SCORE_H)))
                marker = subtitle_score_overlay_marker(seg)
                if marker and width >= 44:
                    label_items.append((int(draw_x1), width, marker))
            _draw_rect_batch(
                segment_rects,
                fill=QColor(31, 40, 46, 205),
                pen=QPen(QColor(82, 96, 108, 220), 1),
                coalesce=False,
            )
            for x1, width, marker in label_items:
                if width < 44:
                    continue
                text_rect = QRect(x1, int(SCORE_TOP), width, int(SCORE_H))
                label = fm.elidedText(str(marker.get("label", "") or ""), Qt.TextElideMode.ElideRight, max(8, width - 6))
                p.setPen(QColor(0, 0, 0, 190))
                p.drawText(text_rect.translated(1, 1), Qt.AlignmentFlag.AlignCenter, label)
                p.setPen(QColor(str(marker.get("color", COLORS["warning"]) or COLORS["warning"])))
                p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)

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
            markers = coalesce_roughcut_paint_markers(
                markers,
                pps=max(0.001, float(getattr(self, "pps", 1.0) or 1.0)),
                max_gap_px=2.0,
            )
            if not markers:
                return
            clip = paint_clip
            label_clip_left = int(clip.left())
            label_clip_right = int(clip.right())
            try:
                scroll_area = self.parent()
                while scroll_area is not None and not isinstance(scroll_area, QScrollArea):
                    scroll_area = scroll_area.parent()
                if scroll_area is not None:
                    label_clip_left = int(scroll_area.horizontalScrollBar().value())
                    label_clip_right = label_clip_left + max(1, int(scroll_area.viewport().width())) - 1
            except Exception:
                label_clip_left = int(clip.left())
                label_clip_right = int(clip.right())
            lane_top = RULER_H + WAVE_H + 5
            lane_h = max(18, SEG_TOP - lane_top - 7)
            x_start = max(0, clip.left())
            x_end = min(total_w, clip.right() + 1)
            p.setPen(QPen(QColor("#2D3942"), 1))
            p.setBrush(QColor("#0B1418"))
            p.drawRect(QRect(x_start, lane_top, max(1, x_end - x_start), lane_h))
            box_top = lane_top + 3
            box_h = max(12, lane_h - 6)
            text_color = QColor("#E7F5EE")
            text_shadow = QColor(0, 0, 0, 120)
            text_font = QFont(config.FONT, 11, QFont.Weight.Bold)

            def _draw_major_label(marker, x1: int, x2: int) -> None:
                width = max(2, int(x2 - x1) + 1)
                if width < 44:
                    return
                label = str(marker.get("display_label", "") or marker.get("label", "") or "").strip()
                if not label:
                    return
                p.save()
                try:
                    p.setFont(text_font)
                    p.setPen(text_color)
                    text_rect = QRect(int(x1) + 8, int(box_top), max(8, width - 16), max(10, int(box_h)))
                    if text_rect.width() < 8 or text_rect.height() < 8:
                        return
                    fm = p.fontMetrics()
                    elided = fm.elidedText(label, Qt.TextElideMode.ElideRight, text_rect.width())
                    if not elided:
                        return
                    p.setClipRect(text_rect.adjusted(0, 0, 1, 0))
                    p.setPen(text_shadow)
                    p.drawText(text_rect.translated(1, 1), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)
                    p.setPen(text_color)
                    p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)
                finally:
                    p.restore()
            if playback_light_mode:
                fill_batches: dict[tuple[str, int], list[QRect]] = {}
                border_batches: dict[tuple[str, int, int], list[QRect]] = {}
                label_items: list[tuple[dict, int, int]] = []
                paint_spans = []
                for marker in markers:
                    start = max(0.0, float(marker.get("start", 0.0) or 0.0))
                    end = max(start, float(marker.get("end", start) or start))
                    raw_x1, raw_x2 = self._x(start), self._x(end)
                    x1, x2 = expanded_roughcut_marker_span(raw_x1, raw_x2)
                    paint_spans.append((marker, raw_x1, raw_x2, x1, x2))
                for marker, x1, x2 in clamp_expanded_roughcut_marker_spans(paint_spans):
                    if x2 < clip.left() or x1 > clip.right():
                        continue
                    color = QColor(str(marker.get("color", "#34C759")))
                    rect = QRect(int(x1), int(box_top), max(2, int(x2 - x1) + 1), max(10, int(box_h)))
                    _append_batch(fill_batches, (color.name(), 18 if dense_segment_mode else 28), rect)
                    _append_batch(border_batches, (color.name(), 150, 1), rect)
                    label_items.append((marker, int(x1), int(x2)))
                _draw_color_batches(fill_batches, coalesce=True, max_gap_px=1)
                for (color_name, alpha, border_width), rects in border_batches.items():
                    color = QColor(color_name)
                    color.setAlpha(int(alpha))
                    _draw_rect_batch(rects, pen=QPen(color, int(border_width)), coalesce=True, max_gap_px=1)
                for marker, x1, x2 in label_items:
                    label_span = visible_roughcut_label_span(
                        x1,
                        x2,
                        clip_left=label_clip_left,
                        clip_right=label_clip_right,
                    )
                    if label_span is not None:
                        _draw_major_label(marker, label_span[0], label_span[1])
                return
            p.setFont(QFont(config.FONT, 11, QFont.Weight.Bold))
            radius = max(4.0, min(7.0, float(box_h) / 2.1))
            was_antialias = p.renderHints() & QPainter.RenderHint.Antialiasing
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            paint_spans = []
            for marker in markers:
                start = max(0.0, float(marker.get("start", 0.0) or 0.0))
                end = max(start, float(marker.get("end", start) or start))
                raw_x1, raw_x2 = self._x(start), self._x(end)
                x1, x2 = expanded_roughcut_marker_span(raw_x1, raw_x2)
                paint_spans.append((marker, raw_x1, raw_x2, x1, x2))
            for marker, x1, x2 in clamp_expanded_roughcut_marker_spans(paint_spans):
                if x2 < clip.left() or x1 > clip.right():
                    continue
                color = QColor(str(marker.get("color", "#34C759")))
                fill = QColor(color)
                fill.setAlpha(30 if not dense_segment_mode else 18)
                width = max(3, int(x2 - x1))
                rect = QRectF(float(x1) + 0.5, float(box_top) + 0.5, float(width), float(box_h - 1))
                p.setPen(QPen(color, 1))
                p.setBrush(fill)
                p.drawRoundedRect(rect, radius, radius)
                label_span = visible_roughcut_label_span(
                    x1,
                    x2,
                    clip_left=label_clip_left,
                    clip_right=label_clip_right,
                )
                if label_span is not None:
                    _draw_major_label(marker, label_span[0], label_span[1])
            p.setRenderHint(QPainter.RenderHint.Antialiasing, bool(was_antialias))

        def _draw_cut_boundary_work_lane():
            official_rows = getattr(self, "boundary_times", []) or []
            scan_rows = getattr(self, "scan_boundary_times", []) or []
            try:
                fps = normalize_fps(self._get_fps() if hasattr(self, "_get_fps") else getattr(self, "frame_rate", 30.0))
            except Exception:
                fps = 30.0
            plan = build_cut_boundary_work_lane_paint_plan(
                official_rows=official_rows,
                scan_rows=scan_rows,
                visible_start_sec=visible_start_sec,
                visible_end_sec=visible_end_sec,
                clip_left=paint_clip.left(),
                clip_right=paint_clip.right(),
                total_duration=float(getattr(self, "total_duration", 0.0) or 0.0),
                fps=fps,
                dense_segment_mode=dense_segment_mode,
                sec_to_x=self._x,
                visible_filter=getattr(self, "_visible_items_for_paint", None),
            )
            if not plan.has_items:
                return
            clip = paint_clip
            lane_top = int(plan.lane_top)
            lane_h = int(plan.lane_h)
            p.setFont(QFont(config.FONT, 8, QFont.Weight.Bold))
            for item in plan.lines:
                color = QColor(item.color)
                width = max(1, int(item.width))
                style_name = str(item.style or "solid")
                pen_style = Qt.PenStyle.DashLine if style_name == "dash" else (Qt.PenStyle.DotLine if style_name == "dot" else Qt.PenStyle.SolidLine)
                p.setPen(QPen(color, width, pen_style))
                top_offset = 2 if item.kind == "official" else 3
                bottom_offset = 3 if item.kind == "official" else 4
                p.drawLine(int(item.x), lane_top + top_offset, int(item.x), lane_top + lane_h - bottom_offset)
            for item in plan.labels:
                label = item.label
                color = QColor(item.color)
                x = int(item.x)
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
                voice_top - 2,
                track_bottom,
            ):
                p.drawLine(draw_left, y, draw_right, y)

        def _coalesce_rects(rects, *, max_gap_px: int = 0) -> list[QRect]:
            return coalesce_rects_by_row(rects, max_gap_px=max_gap_px)

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

        p.fillRect(paint_clip, QColor(COLORS["bg"]))

        def _fmt_ruler(sec):
            s = int(sec)
            h, rem = divmod(s, 3600)
            m, sc = divmod(rem, 60)
            if h > 0:
                return f"{h}:{m:02d}:{sc:02d}"
            return f"{m:02d}:{sc:02d}"

        ruler_font = QFont(config.FONT, 9)
        ruler_font.setBold(False)
        p.setFont(ruler_font)
        fm_ruler = p.fontMetrics()
        p.fillRect(QRect(clip_left, 0, max(1, clip_right - clip_left), RULER_H), QColor(WAVEFORM_RULER_BG))
        p.setPen(QPen(QColor(WAVEFORM_RULER_LINE), 1))
        p.drawLine(clip_left, RULER_H - 1, clip_right, RULER_H - 1)

        fps = normalize_fps(self._get_fps() if hasattr(self, "_get_fps") else getattr(self, "frame_rate", 30.0))
        total_frames = max(0, frame_count(total_secs, fps))
        visible_start_frame = max(0, self._frame_from_x(clip_left)) if hasattr(self, "_frame_from_x") else 0
        visible_end_frame = min(total_frames, max(visible_start_frame, self._frame_from_x(clip_right))) if hasattr(self, "_frame_from_x") else total_frames
        major_step_seconds = self._fps_ruler_major_step_seconds(42.0)
        minor_step_frames = self._fps_ruler_minor_step_frames(fps, 22.0)
        label_step_seconds = self._fps_ruler_reference_label_step_seconds(96.0)

        visible_start_sec = max(0, int(math.floor(frame_to_sec(visible_start_frame, fps))))
        visible_end_sec = max(visible_start_sec, int(math.ceil(frame_to_sec(visible_end_frame, fps))))
        major_frames: dict[int, int] = {}
        first_major_sec = max(0, (max(0, visible_start_sec - major_step_seconds) // major_step_seconds) * major_step_seconds)
        for second_mark in range(first_major_sec, visible_end_sec + major_step_seconds + 1, major_step_seconds):
            frame_mark = sec_to_nearest_frame(second_mark, fps)
            if frame_mark > total_frames:
                break
            major_frames[frame_mark] = second_mark

        if self._fps_ruler_should_draw_minor_ticks(major_step_seconds, minor_step_frames, fps):
            frame_f = max(0, ((visible_start_frame // minor_step_frames) * minor_step_frames) - minor_step_frames)
            while frame_f <= total_frames:
                tx = self._frame_x(frame_f) if hasattr(self, "_frame_x") else self._x(frame_to_sec(frame_f, fps))
                if tx > clip_right:
                    break
                if frame_f >= 0 and frame_f not in major_frames:
                    p.setPen(QColor("#56606A" if minor_step_frames == 1 else "#48515B"))
                    tick_top = 12 if minor_step_frames == 1 else 14
                    p.drawLine(tx, tick_top, tx, RULER_H - 10)
                frame_f += minor_step_frames

        for frame_i in sorted(major_frames):
            tx = self._frame_x(frame_i) if hasattr(self, "_frame_x") else self._x(frame_to_sec(frame_i, fps))
            if tx < clip_left:
                continue
            if tx > clip_right:
                break
            second_mark = major_frames[frame_i]
            p.setPen(QPen(QColor("#9BB7E4"), 1))
            p.drawLine(tx, 6, tx, RULER_H - 6)
            if second_mark % label_step_seconds == 0:
                label = _fmt_ruler(float(second_mark))
                lw = fm_ruler.horizontalAdvance(label)
                label_baseline_y = RULER_H - 9
                label_bg = self._ruler_time_label_background_rect(
                    tx,
                    lw,
                    baseline_y=label_baseline_y,
                    font_ascent=fm_ruler.ascent(),
                    font_descent=fm_ruler.descent(),
                    clip_left=clip_left,
                    clip_right=clip_right,
                )
                if not label_bg.isEmpty():
                    p.fillRect(label_bg, QColor(WAVEFORM_RULER_BG))
                p.setPen(QColor("#B3BBC4"))
                p.drawText(tx - lw // 2, label_baseline_y, label)

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

        p.fillRect(QRect(clip_left, SEG_TOP, max(1, clip_right - clip_left), SEG_BOT - SEG_TOP), QColor(COLORS["sidebar"]))
        p.setPen(QPen(QColor(COLORS["separator"]), 1))
        for y in (subtitle_top - 5, STT1_TOP - 3, STT2_TOP - 3, speaker_top - 3, voice_top - 2, track_bottom):
            p.drawLine(clip_left, y, clip_right, y)

        if bool(getattr(self, "_edit_active", False)):
            _draw_canvas_playhead(
                include_subtitle_band=True,
                include_non_subtitle_band=False,
                include_handle=False,
            )

        def _draw_gap_lane(gaps):
            plan = build_gap_lane_paint_plan(
                gaps=gaps,
                clip_left=clip_left,
                clip_right=clip_right,
                seg_top=SEG_TOP,
                seg_bot=SEG_BOT,
                overview_mode=overview_mode,
                ultra_dense_segment_mode=ultra_dense_segment_mode,
                dense_segment_mode=dense_segment_mode,
                show_gap_insert_controls=bool(getattr(self, "show_gap_insert_controls", True)),
                sec_to_x=self._x,
                icon_rect_builder=self._icon_rect,
                plus_rect_builder=self._plus_rect,
            )
            if not plan.has_items:
                return
            if plan.compact_gap_mode:
                if not plan.active_items:
                    return
                p.setFont(QFont(config.FONT, 9, QFont.Weight.Bold))
                for item in plan.active_items:
                    p.fillRect(item.rect, QColor(20, 16, 0, 118))
                    p.setPen(QPen(QColor("#FFFFFF"), 2))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(item.rect)
                    p.fillRect(item.icon_rect, QColor("#3B1D20"))
                    p.setPen(QColor("#FF8A80"))
                    p.drawText(item.icon_rect, Qt.AlignmentFlag.AlignCenter, "✕")
                return
            _draw_rect_batch(plan.inactive_rects, fill=QColor(20, 16, 0, 118))
            _draw_rect_batch(plan.inactive_rects, pen=QPen(QColor("#4F5962"), 1, Qt.PenStyle.DotLine))
            if plan.inactive_plus_rects:
                p.setFont(QFont(config.FONT, 18, QFont.Weight.Bold))
                for ir in plan.inactive_plus_rects:
                    p.fillRect(ir, QColor("#17232A"))
                    p.setPen(QColor("#8EA4B8"))
                    p.drawText(ir, Qt.AlignmentFlag.AlignCenter, "+")
            if plan.active_items:
                p.setFont(QFont(config.FONT, 9, QFont.Weight.Bold))
                for item in plan.active_items:
                    p.fillRect(item.rect, QColor(20, 16, 0, 118))
                    p.setPen(QPen(QColor("#FFFFFF"), 2))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(item.rect)
                    p.fillRect(item.icon_rect, QColor("#3B1D20"))
                    p.setPen(QColor("#FF8A80"))
                    p.drawText(item.icon_rect, Qt.AlignmentFlag.AlignCenter, "✕")

        dragging_timing = getattr(self, "_drag_seg", None) is not None or getattr(self, "_drag_edge", None) == "diamond"
        if not dragging_timing:
            _draw_gap_lane(visible_gap_segments)

        def _draw_stt_preview_lane(
            preview_segments,
            lane_top,
            lane_bot,
            fill_hex,
            border_hex,
            text_hex,
            *,
            sublane_map=None,
            sublane_count: int = 1,
            selection_state_map=None,
            selected_final_segments=None,
            selected_final_index=None,
        ):
            selected_final_segments = list(selected_final_segments or [])
            selected_final_index = selected_final_index or {}
            plan = build_stt_preview_lane_paint_plan(
                preview_segments=preview_segments,
                clip_left=clip_left,
                clip_right=clip_right,
                lane_top=lane_top,
                lane_bot=lane_bot,
                pps=float(getattr(self, "pps", 1.0) or 1.0),
                ultra_dense_segment_mode=ultra_dense_segment_mode,
                selected_final_stt_segments=selected_final_segments,
                selected_final_stt_index=selected_final_index,
                sec_to_x=self._x,
                sublane_map=sublane_map,
                sublane_count=sublane_count,
                selection_state_map=selection_state_map,
            )
            if not plan.has_items:
                return
            if plan.aggregate_rects:
                _draw_rect_batch(plan.aggregate_rects, fill=QColor(fill_hex))
                _draw_rect_batch(plan.aggregate_rects, pen=QPen(QColor(border_hex), 1))
                return
            preview_font = self._stt_preview_font() if hasattr(self, "_stt_preview_font") else QFont(config.FONT, 10)
            p.setFont(preview_font)
            fills: dict[tuple[str, int], list[QRect]] = {}
            borders: dict[tuple[str, int, int], list[QRect]] = {}
            detail_items = []
            for item in plan.items:
                seg = item.segment
                rect = item.rect
                selection_state = item.selection_state
                is_selected = item.is_selected
                visual = stt_preview_visual_style(
                    seg,
                    selection_state=selection_state,
                    fill_hex=fill_hex,
                    border_hex=border_hex,
                    text_hex=text_hex,
                )
                _append_batch(fills, (str(visual["fill"]), int(visual["alpha"])), rect)
                _append_batch(borders, (str(visual["border"]), 255, int(visual["border_width"])), rect)
                if rect.width() >= 40 and rect.height() >= 14 and not ultra_dense_segment_mode:
                    detail_items.append((seg, rect, selection_state, is_selected, visual))
            _draw_color_batches(fills)
            for (color_name, alpha, border_width), rects in borders.items():
                color = QColor(color_name)
                color.setAlpha(int(alpha))
                _draw_rect_batch(rects, pen=QPen(color, int(border_width)))
            for seg, rect, selection_state, is_selected, visual in detail_items:
                    text_color = QColor(visual["text"])
                    badge_w = 36 if is_selected and rect.width() >= 90 else 0
                    center_stt1_badge = bool(
                        badge_w
                        and selection_state != "llm"
                        and stt_preview_source(seg) == "STT1"
                    )
                    text_rect = QRect(
                        rect.x() + 8,
                        rect.y() + 5,
                        max(8, rect.width() - 16 - (0 if center_stt1_badge else badge_w)),
                        rect.height() - 10,
                    )
                    p.setPen(text_color)
                    preview_text = str(seg.get("text", "") or "")
                    if not preview_text.strip().strip(".·…"):
                        preview_text = ""
                    p.save()
                    p.setClipRect(text_rect.adjusted(0, 0, 1, 1))
                    if not preview_text or text_rect.width() < 36:
                        pass
                    elif rect.width() < 132:
                        preview_text = p.fontMetrics().elidedText(preview_text.replace("\n", " "), Qt.TextElideMode.ElideRight, text_rect.width())
                        if preview_text.strip().strip(".·…"):
                            p.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, preview_text)
                    else:
                        p.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, preview_text)
                    p.restore()
                    if badge_w:
                        if center_stt1_badge:
                            # KEEP: only the STT1 preview "선택" badge lives in the
                            # visual center. Subtitle-segment badges and STT2 badges
                            # intentionally keep their prior edge-aligned placement.
                            badge_rect = QRect(
                                rect.x() + max(4, (rect.width() - badge_w) // 2),
                                rect.y() + 6,
                                badge_w,
                                18,
                            )
                        else:
                            badge_rect = QRect(rect.right() - badge_w - 4, rect.y() + 6, badge_w, 18)
                        badge_fill = QColor(COLORS["warning_badge"] if selection_state == "llm" else "#174A2A")
                        badge_border = QColor(COLORS["warning"] if selection_state == "llm" else "#34C759")
                        badge_text = "LLM" if selection_state == "llm" else "선택"
                        p.fillRect(badge_rect, badge_fill)
                        p.setPen(QPen(badge_border, 1))
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.drawRect(badge_rect)
                        p.setPen(QColor(COLORS["warning_text_soft"]))
                        p.setFont(QFont(config.FONT, 7, QFont.Weight.Bold))
                        p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)
                        p.setFont(preview_font)

        def _draw_vector_subtitle_strips(segments):
            """Batch dense subtitle geometry so large projects repaint like vector strips."""
            if not segments:
                return set()
            pps = float(getattr(self, "pps", 1.0) or 1.0)
            aggregate_plan = build_aggregate_vector_subtitle_paint_plan(
                segments=segments,
                clip_left=clip_left,
                clip_right=clip_right,
                pps=pps,
                subtitle_top=subtitle_top,
                subtitle_bot=subtitle_bot,
                speaker_top=speaker_top,
                speaker_bot=speaker_bot,
                ultra_dense_segment_mode=ultra_dense_segment_mode,
                active_seg_start=getattr(self, "active_seg_start", None),
                hover_line=getattr(self, "_hover_line", None),
            )
            if aggregate_plan.enabled:
                if aggregate_plan.subtitle_rects:
                    _draw_rect_batch(aggregate_plan.subtitle_rects, fill=QColor(24, 64, 42, 168))
                    _draw_rect_batch(aggregate_plan.speaker_rects, fill=QColor(38, 98, 72, 156))
                    _draw_rect_batch(aggregate_plan.subtitle_rects, pen=QPen(QColor(64, 148, 98, 170), 1))
                return set(), list(aggregate_plan.detail_segments)

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
                visible_span = visible_pixel_span(
                    x1,
                    x2,
                    clip_left=clip_left,
                    clip_right=clip_right,
                    min_edge_fragment_px=2,
                )
                if visible_span is None:
                    continue
                draw_x1, draw_x2 = visible_span
                sw = max(2, draw_x2 - draw_x1)
                rect = (
                    self._subtitle_segment_visual_rect(seg, draw_x1, draw_x2, subtitle_top, subtitle_bot)
                    if hasattr(self, "_subtitle_segment_visual_rect")
                    else QRect(draw_x1 + 1, subtitle_top, max(2, sw - 2), subtitle_bot - subtitle_top)
                )
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
                        playback_active=body_playback_active,
                        quality_filter=quality_filter,
                    )
                    cached_style = (str(visual_style["fill"]), str(visual_style["border"]))
                    style_cache[style_key] = cached_style
                fill_color, border_color = cached_style
                fill_batches.setdefault(fill_color, []).append(rect)
                border_batches.setdefault(border_color, []).append(rect)
                speaker_rows = _speaker_rows(seg)
                for row, row_rect in self._speaker_row_rects(QRect(rect.x(), speaker_top, rect.width(), speaker_bot - speaker_top), speaker_rows):
                    speaker_color_key = str(row.get("color") or "#8E8E93")
                    speaker_color_name = speaker_color_cache.get(speaker_color_key)
                    if speaker_color_name is None:
                        speaker_color_name = speaker_segment_fill_hex(speaker_color_key)
                        speaker_color_cache[speaker_color_key] = speaker_color_name
                    speaker_batches.setdefault(speaker_color_name, []).append(row_rect)
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
            _draw_stt_preview_lane(
                stt1_preview_segments,
                STT1_TOP,
                STT1_BOT,
                "#173524",
                "#34C759",
                "#D7FFE4",
                sublane_map=stt1_lane_map,
                sublane_count=stt1_lane_count,
                selection_state_map=stt_selection_states,
                selected_final_segments=selected_final_stt_segments,
                selected_final_index=selected_final_stt_index,
            )
            _draw_stt_preview_lane(
                stt2_preview_segments,
                STT2_TOP,
                STT2_BOT,
                "#1A3148",
                "#64D2FF",
                "#BDEBFF",
                sublane_map=stt2_lane_map,
                sublane_count=stt2_lane_count,
                selection_state_map=stt_selection_states,
                selected_final_segments=selected_final_stt_segments,
                selected_final_index=selected_final_stt_index,
            )

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
                visible_span = visible_pixel_span(
                    x1,
                    x2,
                    clip_left=clip_left,
                    clip_right=clip_right,
                    min_edge_fragment_px=2,
                )
                if visible_span is None:
                    continue
                draw_x1, draw_x2 = visible_span
                sw = max(2, draw_x2 - draw_x1)
                rect = (
                    self._subtitle_segment_visual_rect(seg, draw_x1, draw_x2, subtitle_top, subtitle_bot)
                    if hasattr(self, "_subtitle_segment_visual_rect")
                    else QRect(draw_x1 + 1, subtitle_top, max(2, sw - 2), subtitle_bot - subtitle_top)
                )
                is_active = self._is_active_segment(seg) if hasattr(self, "_is_active_segment") else (
                    self.active_seg_start is not None and abs(seg["start"] - self.active_seg_start) < 0.001
                )
                is_hover = self._hover_line == seg.get("line")
                is_editing = (self._edit_active and self._edit_line == seg.get("line"))
                is_split_editing = bool(
                    is_editing
                    and hasattr(self, "_smart_split_edit_active")
                    and self._smart_split_edit_active()
                )
                is_merge_preview = bool(
                    hasattr(self, "_is_merge_preview_segment")
                    and self._is_merge_preview_segment(seg)
                )
                native_inline_active = bool(
                    is_editing
                    and hasattr(self, "_native_inline_editor_active")
                    and self._native_inline_editor_active()
                )
                render_active = bool(is_active)
                render_hover = bool(is_hover)
                focus_detail = bool(render_active or render_hover or is_editing or is_merge_preview)
                compact_seg = sw < 24 or (dense_segment_mode and not focus_detail)
                is_stt_pending = bool(seg.get("stt_pending"))
                spk_color = _speaker_color(seg)
                visual_style = subtitle_segment_visual_style(
                    seg,
                    active=render_active,
                    hover=render_hover,
                    playback_active=body_playback_active,
                    quality_filter=getattr(self, "quality_filter", "all"),
                )
                if is_split_editing:
                    visual_style = dict(visual_style)
                    visual_style["fill"] = "#4A3416"
                    visual_style["border"] = COLORS["warning"]
                elif is_editing:
                    visual_style = dict(visual_style)
                    visual_style["border"] = "#44FF88"
                if overview_mode and compact_seg:
                    fill = QColor(visual_style["fill"])
                    border = QColor(visual_style["border"])
                    p.fillRect(rect, fill)
                    p.setPen(QPen(border, 1))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(rect)
                    speaker_rect = QRect(rect.x(), speaker_top, rect.width(), speaker_bot - speaker_top)
                    self._fill_speaker_rows(p, speaker_rect, _speaker_rows(seg))
                    continue
                fill = QColor(visual_style["fill"])
                border = QColor(visual_style["border"])
                bw = 2 if (render_active or render_hover) and not compact_seg else 1

                p.fillRect(rect, fill)
                p.setPen(QPen(border, bw))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(rect)
                if is_merge_preview:
                    preview_rect = rect.adjusted(1, 1, -1, -1)
                    if preview_rect.isValid():
                        p.fillRect(preview_rect, QColor(10, 132, 255, 36))
                    p.setPen(QPen(QColor("#0A84FF"), 2))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(rect.adjusted(0, 0, -1, -1))
                chips = subtitle_confidence_chips(seg)
                chips_drawn = False
                if (
                    not playback_light_mode
                    and chips
                    and rect.width() >= 72
                    and rect.height() >= 30
                    and not compact_seg
                    and (not dense_segment_mode or focus_detail)
                ):
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
                    not playback_light_mode
                    and not is_editing
                    and selected_source
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
                    p.fillRect(text_rect, QColor(COLORS["accent_surface"]))
                    vis_cur = cur + len(preedit)
                    r = 0; c = vis_cur
                    for i, line in enumerate(lines):
                        if c <= len(line): r = i; break
                        c -= (len(line) + 1)
                    curr_y = ty0
                    for i, line in enumerate(lines):
                        p.setPen(QColor(COLORS["warning_text_soft"]))
                        if preedit and i == r:
                            pre_start = c - len(preedit)
                            p.drawText(tx0, curr_y, line)
                            pre_w_start = fm.horizontalAdvance(line[:pre_start])
                            pre_w_end = fm.horizontalAdvance(line[:c])
                            p.setPen(QColor(COLORS["warning"]))
                            p.drawText(tx0 + pre_w_start, curr_y, preedit)
                            p.setPen(QPen(QColor(COLORS["warning"]), 1))
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
                    # native inline editor가 활성화된 세그먼트는 위젯이 텍스트를 그리므로 배경 QPainter 텍스트를 중복 렌더하지 않는다.
                    if should_paint_subtitle_segment_text(
                        native_inline_active=native_inline_active,
                        rect_width=rect.width(),
                        dense_segment_mode=dense_segment_mode,
                        focus_detail=focus_detail,
                    ):
                        text_color = visual_style.get("text", "")
                        p.setPen(QColor(text_color) if text_color else (QColor("#8A8F98") if is_stt_pending else QColor("#DCE3EA")))
                        seg_text = str(seg.get("text", "") or "")
                        p.save()
                        p.setClipRect(text_rect.adjusted(0, 0, 1, 1))
                        if rect.width() < 164:
                            seg_text = p.fontMetrics().elidedText(seg_text.replace("\n", " "), Qt.TextElideMode.ElideRight, text_rect.width())
                            p.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, seg_text)
                        else:
                            p.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, seg_text)
                        p.restore()
                        if show_badge:
                            is_llm_choice = bool(str(seg.get("stt_ensemble_llm_selected_source", "") or "").strip())
                            badge_rect = QRect(max(text_left + 6, text_right - 38), rect.y() + 6, 38, 18)
                            badge_fill = QColor("#5A4600" if is_llm_choice else "#174A2A")
                            badge_border = QColor(COLORS["warning"] if is_llm_choice else "#34C759")
                            badge_text_color = QColor("#FFF2A8" if is_llm_choice else "#D7FFE4")
                            p.fillRect(badge_rect, badge_fill)
                            p.setPen(QPen(badge_border, 1))
                            p.setBrush(Qt.BrushStyle.NoBrush)
                            p.drawRect(badge_rect)
                            p.setPen(badge_text_color)
                            p.setFont(QFont(config.FONT, 7, QFont.Weight.Bold))
                            p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "선택")
                            p.setFont(seg_font)
                speaker_rect = QRect(rect.x(), speaker_top, rect.width(), speaker_bot - speaker_top)
                if compact_seg:
                    self._fill_speaker_rows(p, speaker_rect, _speaker_rows(seg))
                else:
                    p.setPen(QPen(QColor(SPEAKER_SEGMENT_BORDER), 1))
                    p.setBrush(QColor(SPEAKER_SEGMENT_FILL))
                    p.drawRect(speaker_rect)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    self._fill_speaker_rows(p, speaker_rect, _speaker_rows(seg))
                if (
                    not playback_light_mode
                    and not compact_seg
                    and speaker_rect.width() >= 42
                    and (not dense_segment_mode or focus_detail)
                ):
                    self._draw_speaker_names(p, speaker_rect, spk_color, _speaker_names(seg), _speaker_rows(seg))

                if (
                    not body_playback_active
                    and sw >= SEGMENT_HANDLE_MIN_WIDTH
                    and (not dense_segment_mode or focus_detail)
                    and not ultra_dense_segment_mode
                ):
                    lh = self._hover_handle_matches(seg, "left")
                    rh = self._hover_handle_matches(seg, "right")
                    self._draw_handle(p, x1, True, QColor("#44FF88") if lh else QColor("#888888"))
                    self._draw_handle(p, x2, False, QColor("#44FF88") if rh else QColor("#888888"))

        _draw_subtitle_score_labels(final_stt_segments)

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
                p.setPen(QPen(QColor(COLORS["warning"]), 2))
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

        shadow_playhead_sec = getattr(self, "shadow_playhead_sec", None)
        if shadow_playhead_sec is not None:
            shadow_x = self._x(float(shadow_playhead_sec or 0.0))
            if clip_left - 8 <= shadow_x <= clip_right + 8:
                p.setPen(QPen(QColor(255, 214, 10, 170), 2, Qt.PenStyle.DashLine))
                p.drawLine(int(shadow_x), 0, int(shadow_x), CANVAS_H)

        drag_shadow_playhead_sec = getattr(self, "_drag_shadow_playhead_sec", None)
        if drag_shadow_playhead_sec is not None:
            drag_shadow_x = self._x(float(drag_shadow_playhead_sec or 0.0))
            if clip_left - 8 <= drag_shadow_x <= clip_right + 8:
                p.setPen(QPen(QColor(177, 92, 255, 180), 2, Qt.PenStyle.DashLine))
                p.drawLine(int(drag_shadow_x), 0, int(drag_shadow_x), CANVAS_H)

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

        _draw_canvas_playhead(
            include_subtitle_band=not bool(getattr(self, "_edit_active", False)),
            include_non_subtitle_band=True,
            include_handle=True,
        )

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

    def _speaker_row_rects(self, rect: QRect, rows: list[dict] | None):
        visible_rows = [dict(row or {}) for row in list(rows or [])[:2]]
        if not visible_rows:
            visible_rows = [{"name": "", "color": "#8E8E93"}]
        count = max(1, len(visible_rows))
        top = int(rect.y())
        height = max(1, int(rect.height()))
        out: list[tuple[dict, QRect]] = []
        for idx, row in enumerate(visible_rows):
            row_top = top + int(round(height * idx / count))
            row_bot = top + int(round(height * (idx + 1) / count))
            out.append((row, QRect(rect.x(), row_top, max(1, rect.width()), max(1, row_bot - row_top))))
        return out

    def _fill_speaker_rows(self, p, rect: QRect, rows: list[dict] | None):
        row_rects = self._speaker_row_rects(rect, rows)
        p.save()
        for row, row_rect in row_rects:
            p.fillRect(row_rect, QColor(speaker_segment_fill_hex(str(row.get("color") or "#8E8E93"))))
        if len(row_rects) > 1:
            p.setPen(QPen(QColor(0, 0, 0, 120), 1))
            for _row, row_rect in row_rects[:-1]:
                p.drawLine(row_rect.left(), row_rect.bottom(), row_rect.right(), row_rect.bottom())
        p.restore()

    def _draw_speaker_names(self, p, rect: QRect, color: QColor, names: list[str], rows: list[dict] | None = None):
        row_entries = [dict(row or {}) for row in list(rows or [])[:2]]
        if not row_entries:
            row_entries = [
                {"name": str(name).strip(), "color": color.name()}
                for name in list(names or [])[:2]
                if str(name).strip()
            ]
        names = [str(row.get("name", "") or "").strip() for row in row_entries if str(row.get("name", "") or "").strip()]
        if not names:
            return

        max_lines = 2
        visible_rows = [
            row
            for row in row_entries[:max_lines]
            if str(row.get("name", "") or "").strip()
        ]
        visible_names = [str(row.get("name", "") or "").strip() for row in visible_rows]
        multi_line = len(visible_names) > 1
        font_size = 7 if multi_line else 8
        p.save()
        p.setFont(QFont(config.FONT, font_size, QFont.Weight.Bold))
        fm = p.fontMetrics()
        text_pad = 7
        for row, row_rect in self._speaker_row_rects(rect, visible_rows):
            name = str(row.get("name", "") or "").strip()
            if not name:
                continue
            p.setPen(QColor(speaker_segment_text_hex(str(row.get("color") or color.name()))))
            text_rect = row_rect.adjusted(text_pad, 0, -text_pad, 0)
            max_text_w = max(8, text_rect.width())
            text = fm.elidedText(name, Qt.TextElideMode.ElideRight, max_text_w)
            p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        p.restore()

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
