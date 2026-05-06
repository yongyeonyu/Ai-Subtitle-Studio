# Version: 03.17.00
# Phase: PHASE3
"""Qt Quick SceneGraph renderer for timeline subtitle segments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor

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
    stt_candidate_selection_state,
    stt_preview_source,
    stt_preview_visual_style,
    subtitle_confidence_chips,
    subtitle_segment_visual_style,
)


QML_PATH = Path(__file__).with_name("timeline_scenegraph.qml")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
    quality_filter: str = "all",
    speaker_settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build FPS-anchored vector primitives consumed by the QML SceneGraph."""
    rows = [seg for seg in list(segments or []) if isinstance(seg, dict) and not seg.get("is_gap")]
    final_rows = [
        seg for seg in rows
        if not bool(seg.get("stt_pending") or seg.get("_live_stt_preview") or seg.get("_live_subtitle_preview"))
    ]
    fps = normalize_fps(fps or 30.0)
    px_per_frame = max(0.001, float(pps or 1.0) / fps)
    speaker_settings = current_speaker_settings(speaker_settings or {})
    visible_start_frame = sec_to_frame(max(0.0, visible_start_sec) - 0.35, fps)
    visible_end_frame = sec_to_frame(max(visible_start_sec, visible_end_sec) + 0.35, fps)
    objects: list[dict[str, Any]] = []

    for idx, seg in enumerate(rows):
        start = _safe_float(seg.get("start", seg.get("timeline_start", 0.0)))
        end = max(start, _safe_float(seg.get("end", seg.get("timeline_end", start)), start))
        start_frame = sec_to_frame(start, fps)
        end_frame = max(start_frame + 1, sec_to_frame(end, fps))
        if end_frame < visible_start_frame or start_frame > visible_end_frame:
            continue

        is_preview = bool(seg.get("stt_pending") or seg.get("_live_stt_preview") or seg.get("_live_subtitle_preview"))
        source = stt_preview_source(seg)
        if is_preview:
            if source == "STT2":
                y = STT2_TOP
                h = STT2_BOT - STT2_TOP
                visual = stt_preview_visual_style(
                    seg,
                    selection_state=stt_candidate_selection_state(seg, final_rows),
                    fill_hex="#1A3148",
                    border_hex="#64D2FF",
                    text_hex="#BDEBFF",
                )
            else:
                y = STT1_TOP
                h = STT1_BOT - STT1_TOP
                visual = stt_preview_visual_style(
                    seg,
                    selection_state=stt_candidate_selection_state(seg, final_rows),
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
        else:
            line = seg.get("line")
            is_active = (
                (active_line is not None and line == active_line)
                or (
                    active_start is not None
                    and abs(start - float(active_start)) < 0.001
                )
            )
            is_hover = hover_line is not None and line == hover_line
            visual = subtitle_segment_visual_style(
                seg,
                active=is_active,
                hover=is_hover,
                quality_filter=quality_filter,
            )
            fill = str(visual["fill"])
            border = str(visual["border"])
            text_color = str(visual.get("text") or "#DCE3EA")
            alpha = 255
            border_width = 2 if is_active or is_hover else 1
            speaker_color = _speaker_color(seg, speaker_settings)
            speaker_fill = _darker_hex(speaker_color, 135)
            speaker_names = " / ".join(speaker_labels_for_segment(speaker_settings, seg))
            y = SUBTITLE_TOP
            h = SUBTITLE_BOT - SUBTITLE_TOP

        width = max(2.0, float(end_frame - start_frame) * px_per_frame)
        objects.append(
            {
                "id": str(seg.get("id") or f"sg_seg_{idx}_{start_frame}_{end_frame}"),
                "line": int(seg.get("line", idx) or idx),
                "text": str(seg.get("text", "") or ""),
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
                "confidenceChips": subtitle_confidence_chips(seg),
                "speakerY": float(SPEAKER_TOP),
                "speakerH": float(SPEAKER_BOT - SPEAKER_TOP),
                "speakerFill": speaker_fill,
                "speakerText": speaker_names,
                "showSpeaker": bool(speaker_fill and width >= 42.0),
                "showHandles": bool(not is_preview and width >= SEGMENT_HANDLE_MIN_WIDTH),
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
        quality_filter: str,
        speaker_settings: dict[str, Any] | None,
    ) -> None:
        root = self.widget.rootObject()
        if root is None:
            self.widget.setVisible(False)
            return
        data = build_scenegraph_subtitle_segments(
            segments,
            pps=pps,
            fps=fps,
            visible_start_sec=visible_start_sec,
            visible_end_sec=visible_end_sec,
            active_start=active_start,
            active_line=active_line,
            hover_line=hover_line,
            quality_filter=quality_filter,
            speaker_settings=speaker_settings,
        )
        root.setProperty("segments", data)
        root.setProperty("pps", float(pps or 1.0))
        root.setProperty("fps", float(normalize_fps(fps)))
        root.setProperty("viewportX", float(scroll_x or 0))
        root.setProperty("fontFamily", str(config.FONT))
