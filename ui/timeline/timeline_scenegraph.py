# Version: 03.17.00
# Phase: PHASE3
"""Qt Quick SceneGraph renderer for timeline subtitle segments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor

from core.coerce import safe_float as _safe_float
from core.frame_time import frame_to_sec, normalize_fps, sec_to_frame
from core.runtime import config
from ui.gpu_rendering import scenegraph_enabled
from ui.timeline.speaker_labels import current_speaker_settings, normalize_speaker_id, speaker_labels_for_segment
from ui.timeline.timeline_constants import (
    SEGMENT_HANDLE_MIN_WIDTH,
    SPEAKER_BOT,
    SPEAKER_TOP,
    STT1_BOT,
    STT1_TOP,
    STT2_BOT,
    STT2_TOP,
    SUBTITLE_BOT,
    SUBTITLE_TOP,
)
from ui.timeline.timeline_paint import (
    build_stt_selection_index,
    stt_candidate_selection_state,
    stt_preview_source,
    stt_preview_visual_style,
    subtitle_confidence_chips,
    subtitle_segment_visual_style,
)


QML_PATH = Path(__file__).with_name("timeline_scenegraph.qml")

def _speaker_color(seg: dict[str, Any], speaker_settings: dict[str, Any]) -> str:
    spk = normalize_speaker_id(seg.get("speaker", seg.get("spk_id", "")))
    palette = {
        str(speaker_settings.get("spk1_id", "00")): str(speaker_settings.get("spk1_color", "#579DFF")),
        str(speaker_settings.get("spk2_id", "01")): str(speaker_settings.get("spk2_color", "#75C76B")),
        str(speaker_settings.get("spk3_id", "02")): str(speaker_settings.get("spk3_color", "#FF9F2F")),
    }
    return palette.get(spk, "#8E8E93")


def _darker_hex(hex_color: str, factor: int = 135) -> str:
    color = QColor(str(hex_color or "#8E8E93"))
    return color.darker(int(factor)).name()


def _scenegraph_vector_profile(visible_segment_count: int, pps: float) -> str:
    """Return how aggressively the GPU subtitle layer should collapse segment detail."""
    count = max(0, int(visible_segment_count or 0))
    zoom = max(0.0, float(pps or 0.0))
    if count >= 220 or (count >= 120 and zoom < 18.0):
        return "minimal"
    if count >= 96 or (count >= 48 and zoom < 32.0):
        return "compact"
    return "full"


def _scenegraph_playback_focus_signature(
    segments: list[dict[str, Any]] | None,
    *,
    playhead_sec: float | None,
    fps: float,
) -> tuple[Any, ...] | None:
    if playhead_sec is None:
        return None
    rows = segments if isinstance(segments, list) else list(segments or [])
    if not rows:
        return ("frame", int(sec_to_frame(float(playhead_sec or 0.0), fps)))
    playhead = float(playhead_sec or 0.0)
    edge_tol = max(0.001, min(0.05, 2.0 / max(1.0, float(fps or 30.0))))
    for seg in rows:
        if not isinstance(seg, dict) or seg.get("is_gap"):
            continue
        if bool(seg.get("stt_pending") or seg.get("_live_stt_preview")):
            continue
        start = _safe_float(seg.get("start", seg.get("timeline_start", 0.0)))
        end = max(start, _safe_float(seg.get("end", seg.get("timeline_end", start)), start))
        if start - edge_tol <= playhead < end + edge_tol:
            return (
                "segment",
                int(seg.get("line", -1) or -1),
                int(sec_to_frame(start, fps)),
                int(max(sec_to_frame(end, fps), sec_to_frame(start, fps) + 1)),
            )
    return ("frame", int(sec_to_frame(playhead, fps)))


def _speaker_settings_signature(speaker_settings: dict[str, Any] | None) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(key), str(value)) for key, value in dict(speaker_settings or {}).items()))


def build_scenegraph_subtitle_segments(
    segments: list[dict[str, Any]] | None,
    *,
    pps: float,
    fps: float,
    visible_start_sec: float,
    visible_end_sec: float,
    active_start: float | None = None,
    active_line: int | None = None,
    hover_line: int | None = None,
    playback_active: bool = False,
    playhead_sec: float | None = None,
    quality_filter: str = "all",
    speaker_settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build FPS-anchored vector primitives consumed by the QML SceneGraph."""
    rows: list[dict[str, Any]] = []
    final_rows: list[dict[str, Any]] = []
    preview_present = False
    for seg in segments or ():
        if not isinstance(seg, dict) or seg.get("is_gap"):
            continue
        rows.append(seg)
        is_preview = bool(seg.get("stt_pending") or seg.get("_live_stt_preview"))
        preview_present = preview_present or is_preview
        if not is_preview:
            final_rows.append(seg)
    final_selection_index = build_stt_selection_index(final_rows) if preview_present else {}
    fps = normalize_fps(fps or 30.0)
    px_per_frame = max(0.001, float(pps or 1.0) / fps)
    speaker_settings = current_speaker_settings(speaker_settings or {})
    render_profile = _scenegraph_vector_profile(len(rows), pps)
    visible_start_frame = sec_to_frame(max(0.0, visible_start_sec) - 0.35, fps)
    visible_end_frame = sec_to_frame(max(visible_start_sec, visible_end_sec) + 0.35, fps)
    objects: list[dict[str, Any]] = []
    playhead_value = float(playhead_sec or 0.0) if playhead_sec is not None else 0.0
    playback_edge_tol = max(0.001, min(0.05, 2.0 / fps)) if playback_active and playhead_sec is not None else 0.0

    for idx, seg in enumerate(rows):
        start = _safe_float(seg.get("start", seg.get("timeline_start", 0.0)))
        end = max(start, _safe_float(seg.get("end", seg.get("timeline_end", start)), start))
        start_frame = sec_to_frame(start, fps)
        end_frame = max(start_frame + 1, sec_to_frame(end, fps))
        if end_frame < visible_start_frame or start_frame > visible_end_frame:
            continue

        is_preview = bool(seg.get("stt_pending") or seg.get("_live_stt_preview"))
        source = stt_preview_source(seg)
        if is_preview:
            if source == "STT2":
                y = STT2_TOP
                h = STT2_BOT - STT2_TOP
                visual = stt_preview_visual_style(
                    seg,
                    selection_state=stt_candidate_selection_state(seg, final_rows, final_selection_index),
                    fill_hex="#1A3148",
                    border_hex="#64D2FF",
                    text_hex="#BDEBFF",
                )
            else:
                y = STT1_TOP
                h = STT1_BOT - STT1_TOP
                visual = stt_preview_visual_style(
                    seg,
                    selection_state=stt_candidate_selection_state(seg, final_rows, final_selection_index),
                    fill_hex="#173524",
                    border_hex="#34C759",
                    text_hex="#D7FFE4",
                )
            fill = str(visual["fill"])
            border = str(visual["border"])
            text_color = str(visual["text"])
            alpha = int(visual["alpha"])
            border_width = int(visual["border_width"])
            speaker_fill = ""
            speaker_names = ""
            is_active = False
            is_hover = False
        else:
            line = seg.get("line")
            if playback_active and playhead_sec is not None:
                is_active = start - playback_edge_tol <= playhead_value < end + playback_edge_tol
            else:
                is_active = (
                    (active_line is not None and line == active_line)
                    or (
                        active_start is not None
                        and abs(start - float(active_start)) < 0.001
                    )
                )
            is_hover = hover_line is not None and line == hover_line
            render_active = bool(is_active and not playback_active)
            render_hover = bool(is_hover and not playback_active)
            visual = subtitle_segment_visual_style(
                seg,
                active=render_active,
                hover=render_hover,
                playback_active=playback_active,
                quality_filter=quality_filter,
            )
            fill = str(visual["fill"])
            border = str(visual["border"])
            text_color = str(visual.get("text") or "#DCE3EA")
            alpha = 255
            border_width = 2 if render_active or render_hover else 1
            speaker_fill = ""
            speaker_names = ""
            y = SUBTITLE_TOP
            h = SUBTITLE_BOT - SUBTITLE_TOP

        width = max(2.0, float(end_frame - start_frame) * px_per_frame)
        allow_text = render_profile == "full"
        if render_profile == "compact" and width >= 184.0 and (is_active or is_hover):
            allow_text = True
        show_text = bool(width >= 44.0 and allow_text)
        show_confidence_chips = bool(
            not is_preview
            and not playback_active
            and render_profile == "full"
            and width >= 72.0
            and float(h) >= 30.0
        )
        show_speaker_bar = bool(not is_preview and render_profile != "minimal" and width >= 24.0)
        show_speaker_text = bool(
            not playback_active
            and show_speaker_bar
            and render_profile == "full"
            and width >= 64.0
        )
        show_handles = bool(
            not is_preview
            and not playback_active
            and render_profile == "full"
            and width >= SEGMENT_HANDLE_MIN_WIDTH
        )
        if not is_preview and show_speaker_bar:
            speaker_color = _speaker_color(seg, speaker_settings)
            speaker_fill = _darker_hex(speaker_color, 135)
            speaker_names = " / ".join(speaker_labels_for_segment(speaker_settings, seg)) if show_speaker_text else ""
            show_speaker_text = bool(show_speaker_text and speaker_names)
        display_text = str(seg.get("text", "") or "") if show_text else ""
        chip_rows = subtitle_confidence_chips(seg) if show_confidence_chips else []
        objects.append(
            {
                "id": str(seg.get("id") or f"sg_seg_{idx}_{start_frame}_{end_frame}"),
                "line": int(seg.get("line", idx) or idx),
                "text": display_text,
                "x": float(start_frame) * px_per_frame,
                "y": float(y),
                "w": width,
                "h": float(h),
                "startFrame": int(start_frame),
                "endFrame": int(end_frame),
                "startSec": frame_to_sec(start_frame, fps),
                "endSec": frame_to_sec(end_frame, fps),
                "fps": fps,
                "fill": fill,
                "border": border,
                "textColor": text_color,
                "alpha": alpha,
                "borderWidth": border_width,
                "confidenceChips": chip_rows,
                "speakerY": float(SPEAKER_TOP),
                "speakerH": float(SPEAKER_BOT - SPEAKER_TOP),
                "speakerFill": speaker_fill if show_speaker_bar else "",
                "speakerText": speaker_names if show_speaker_text else "",
                "showText": show_text,
                "showConfidenceChips": show_confidence_chips,
                "showSpeakerBar": show_speaker_bar,
                "showSpeakerText": show_speaker_text,
                "showHandles": show_handles,
                "renderProfile": render_profile,
                "preview": bool(is_preview),
            }
        )
    return objects


class TimelineSceneGraphLayer:
    """Thin QQuickWidget wrapper kept separate so QWidget fallback stays intact."""

    def __init__(self, parent=None):
        from PyQt6.QtQuickWidgets import QQuickWidget

        self.widget = QQuickWidget(parent)
        self.widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.widget.setClearColor(QColor(0, 0, 0, 0))
        self.widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.widget.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, True)
        self.widget.setSource(QUrl.fromLocalFile(str(QML_PATH)))
        self.widget.setVisible(False)
        self._last_segment_count = 0
        self._last_state_key = None

    @staticmethod
    def enabled() -> bool:
        return scenegraph_enabled("timeline") and QML_PATH.exists()

    def set_geometry(self, rect) -> None:
        self.widget.setGeometry(rect)

    def set_visible(self, visible: bool) -> None:
        self.widget.setVisible(bool(visible))

    def raise_(self) -> None:
        self.widget.raise_()

    def delete_later(self) -> None:
        self.widget.deleteLater()

    def set_state(
        self,
        *,
        segments: list[dict[str, Any]],
        pps: float,
        fps: float,
        scroll_x: int,
        visible_start_sec: float,
        visible_end_sec: float,
        active_start: float | None,
        active_line: int | None,
        hover_line: int | None,
        playback_active: bool,
        playhead_sec: float | None,
        quality_filter: str,
        speaker_settings: dict[str, Any] | None,
        render_epoch: int = 0,
    ) -> int:
        root = self.widget.rootObject()
        if root is None:
            self._last_segment_count = 0
            self._last_state_key = None
            self.widget.setVisible(False)
            return 0
        fps = normalize_fps(fps or 30.0)
        state_key = (
            int(render_epoch or 0),
            id(segments),
            len(segments or []),
            round(float(pps or 1.0), 4),
            round(float(fps or 30.0), 4),
            int(scroll_x or 0),
            round(float(visible_start_sec or 0.0), 3),
            round(float(visible_end_sec or 0.0), 3),
            None if playback_active else (None if active_start is None else int(sec_to_frame(float(active_start), fps))),
            None if playback_active else (None if active_line is None else int(active_line)),
            None if hover_line is None else int(hover_line),
            bool(playback_active),
            str(quality_filter or "all"),
            _speaker_settings_signature(speaker_settings),
        )
        if state_key == getattr(self, "_last_state_key", None):
            return int(getattr(self, "_last_segment_count", 0) or 0)
        data = build_scenegraph_subtitle_segments(
            segments,
            pps=pps,
            fps=fps,
            visible_start_sec=visible_start_sec,
            visible_end_sec=visible_end_sec,
            active_start=active_start,
            active_line=active_line,
            hover_line=hover_line,
            playback_active=playback_active,
            playhead_sec=playhead_sec,
            quality_filter=quality_filter,
            speaker_settings=speaker_settings,
        )
        self._last_segment_count = len(data)
        self._last_state_key = state_key
        root.setProperty("segments", data)
        root.setProperty("pps", float(pps or 1.0))
        root.setProperty("fps", float(fps))
        root.setProperty("viewportX", float(scroll_x or 0))
        root.setProperty("fontFamily", str(config.FONT))
        return self._last_segment_count
