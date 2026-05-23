# Version: 03.14.03
# Phase: PHASE2
"""
ui/timeline_widget.py
Timeline widget container
"""
import time

import numpy as np

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QInputDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.editor.ux.timeline_playhead_mode import playhead_line_color_hex
from ui.timeline.timeline_constants import CANVAS_H, FOCUS_BORDER_COLOR, FOCUS_BORDER_WIDTH, RULER_H, SEG_TOP, WAVE_H
from ui.timeline.timeline_canvas import TimelineCanvas
from ui.timeline.timeline_global import GlobalCanvas, MINIMAP_HEIGHT
from ui.timeline.timeline_waveform import WaveformWorker, MultiClipWaveformWorker, patch_waveform_buffer
from ui.responsive_profile import responsive_profile_for_size
from ui.style import COLORS, button_style, settings_dialog_stylesheet
from core.settings import load_settings, save_settings
from core.frame_time import frame_count, frame_to_sec, normalize_fps, sec_to_nearest_frame, snap_sec_to_frame


def _scan_boundary_sec_value(item) -> float:
    try:
        if isinstance(item, dict):
            return float(item.get("timeline_sec", item.get("time", item.get("start", 0.0))) or 0.0)
        return float(item or 0.0)
    except Exception:
        return 0.0


def _scan_boundary_signature(times) -> tuple:
    rows = []
    for item in list(times or []):
        sec = round(_scan_boundary_sec_value(item), 3)
        if isinstance(item, dict):
            rows.append(
                (
                    sec,
                    str(item.get("status", "") or ""),
                    str(item.get("detector_stage", "") or ""),
                    str(item.get("source", "") or ""),
                    str(item.get("kind", "") or ""),
                    str(item.get("line_color", "") or ""),
                    str(item.get("line_style", "") or ""),
                    str(item.get("ui_label", "") or ""),
                    bool(item.get("verified", False)),
                    bool(item.get("follower_active", False)),
                    bool(item.get("follower_relocated", False)),
                    str(item.get("candidate_key", "") or ""),
                )
            )
        else:
            rows.append((sec,))
    return tuple(rows)


def _boundary_signature(times) -> tuple:
    values = []
    for item in list(times or []):
        sec = round(_scan_boundary_sec_value(item), 3)
        if isinstance(item, dict):
            values.append(
                (
                    sec,
                    str(item.get("status", "") or ""),
                    str(item.get("source", "") or ""),
                    str(item.get("reason", "") or ""),
                    str(item.get("line_color", "") or ""),
                    bool(item.get("verified", False)),
                    int(item.get("verified_count", 0) or 0),
                )
            )
        else:
            values.append((sec,))
    return tuple(values)


def _compact_toolbar_button_style(*, font_size: str = "11px", padding: str = "2px 8px") -> str:
    return (
        "QPushButton { "
        f"background: {COLORS['control']}; color: {COLORS['text']}; border: 1px solid {COLORS['separator']}; "
        f"padding: {padding}; font-size: {font_size}; border-radius: 7px; min-width: 64px; "
        "} "
        f"QPushButton:hover {{ background: {COLORS['control_hover']}; }} "
        f"QPushButton:pressed {{ background: #182026; border-color: {COLORS['primary']}; }}"
    )


def _compact_toolbar_checkbox_style(*, font_size: str = "11px", padding: str = "2px 8px") -> str:
    return (
        "QCheckBox { "
        f"background: {COLORS['control']}; color: {COLORS['text']}; border: 1px solid {COLORS['separator']}; "
        f"padding: {padding}; font-size: {font_size}; font-weight: 700; border-radius: 7px; min-width: 64px; "
        "spacing: 5px; "
        "} "
        f"QCheckBox:hover {{ background: {COLORS['control_hover']}; }} "
        f"QCheckBox:pressed {{ background: #182026; border-color: {COLORS['primary']}; }} "
        f"QCheckBox:checked {{ border-color: {COLORS['primary']}; }} "
        "QCheckBox::indicator { "
        "width: 13px; height: 13px; border-radius: 3px; "
        f"border: 1px solid {COLORS['separator']}; background: transparent; "
        "} "
        f"QCheckBox::indicator:hover {{ border-color: {COLORS['primary']}; }} "
        f"QCheckBox::indicator:checked {{ background: {COLORS['primary']}; border-color: {COLORS['primary']}; }}"
    )


class TimelinePlayheadOverlay(QWidget):
    """Paint the moving playhead without invalidating the heavy timeline body."""

    def __init__(self, timeline, parent=None):
        super().__init__(parent)
        self._timeline = timeline
        self._sec = 0.0
        self._shadow_sec: float | None = None
        self._scroll_x = 0
        self._center_locked = False
        self._busy = False
        self._last_visual_px: int | None = None
        self._last_shadow_visual_px: int | None = None
        self._last_state_signature = None
        self._render_visuals = False
        self._quick = self._create_quick_layer()
        self._shutdown_in_progress = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

    def _visual_strip_rect(self, *positions: int | None) -> QRect | None:
        xs = [int(pos) for pos in positions if pos is not None]
        if not xs:
            return None
        left = max(0, min(xs) - 12)
        right = min(max(1, self.width()), max(xs) + 13)
        return QRect(left, 0, max(1, right - left), max(1, self.height()))

    def set_state(
        self,
        sec: float,
        scroll_x: int,
        *,
        center_locked: bool = False,
        busy: bool = False,
        shadow_sec: float | None = None,
    ):
        old_px = self._last_visual_px
        old_shadow_px = self._last_shadow_visual_px
        self._sec = max(0.0, float(sec or 0.0))
        self._shadow_sec = None if shadow_sec is None else max(0.0, float(shadow_sec or 0.0))
        self._scroll_x = max(0, int(scroll_x or 0))
        self._center_locked = bool(center_locked)
        self._busy = bool(busy)
        visual_px = int(round(self._playhead_visual_x()))
        shadow_px = None if self._shadow_sec is None else int(round(self._playhead_visual_x_for_sec(self._shadow_sec, center_locked=False)))
        signature = (
            visual_px,
            shadow_px,
            bool(self._center_locked),
            bool(self._busy),
            int(self.width()),
            int(self.height()),
        )
        if signature == getattr(self, "_last_state_signature", None):
            return False
        self._last_visual_px = visual_px
        self._last_shadow_visual_px = shadow_px
        self._last_state_signature = signature
        if not bool(getattr(self, "_render_visuals", False)): return True
        if getattr(self, "_quick", None) is not None:
            self._sync_quick_layer()
            return True
        dirty = self._visual_strip_rect(old_px, visual_px, old_shadow_px, shadow_px)
        if dirty is not None:
            self.update(dirty)
        return True

    def _create_quick_layer(self):
        # A full-viewport QQuickWidget overlay can composite as an opaque black
        # surface on macOS/Metal and hide the classic painter timeline canvas.
        # Keep the playhead on the lightweight QWidget overlay instead.
        return None

    def _playhead_visual_x_for_sec(self, sec: float, *, center_locked: bool) -> float:
        timeline = self._timeline
        canvas = getattr(timeline, "canvas", None)
        if canvas is None:
            return 0.0
        if center_locked:
            return max(0.0, self.width() / 2.0)
        return float(canvas._x(sec) if hasattr(canvas, "_x") else (float(sec or 0.0) * float(getattr(canvas, "pps", 1.0) or 1.0))) - float(self._scroll_x)

    def _playhead_visual_x(self) -> float:
        return self._playhead_visual_x_for_sec(self._sec, center_locked=bool(self._center_locked))

    def _sync_quick_layer(self, quick=None):
        quick = quick or getattr(self, "_quick", None)
        if quick is None:
            return
        timeline = self._timeline
        canvas = getattr(timeline, "canvas", None)
        visible = bool(canvas is not None and float(getattr(canvas, "total_duration", 0.0) or 0.0) > 0)
        line_color = playhead_line_color_hex(getattr(canvas, "focus_mode", None))
        try:
            root = quick.rootObject()
            if root is None:
                return
            root.setProperty("playheadX", float(self._playhead_visual_x()))
            root.setProperty("lineColor", str(line_color))
            root.setProperty("playheadBusy", bool(self._busy))
            root.setProperty("visiblePlayhead", bool(visible))
            root.setProperty("centerLocked", bool(self._center_locked))
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._last_state_signature = None
        quick = getattr(self, "_quick", None)
        if quick is not None:
            quick.setGeometry(self.rect())
            self._sync_quick_layer(quick)
        else:
            self.update()

    def paintEvent(self, event):
        if bool(getattr(self, "_shutdown_in_progress", False)):
            return
        if getattr(self, "_quick", None) is not None:
            return
        timeline = self._timeline
        canvas = getattr(timeline, "canvas", None)
        if canvas is None or float(getattr(canvas, "total_duration", 0.0) or 0.0) <= 0:
            return
        px = int(round(self._playhead_visual_x()))
        shadow_sec = getattr(self, "_shadow_sec", None)
        shadow_px = None if shadow_sec is None else int(round(self._playhead_visual_x_for_sec(shadow_sec, center_locked=False)))
        current_visible = -16 <= px <= self.width() + 16
        shadow_visible = shadow_px is not None and -16 <= shadow_px <= self.width() + 16
        if not current_visible and not shadow_visible:
            return
        painter = QPainter(self)
        if not painter.isActive():
            return
        try:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(event.rect(), Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        except Exception:
            pass
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if shadow_visible:
            shadow_color = QColor(255, 214, 10, 170)
            painter.setPen(QPen(shadow_color, 2, Qt.PenStyle.DashLine))
            painter.drawLine(shadow_px, 0, shadow_px, self.height())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(255, 214, 10, 210), 1))
            painter.drawEllipse(shadow_px - 6, 3, 12, 12)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if current_visible:
            color = QColor(playhead_line_color_hex(getattr(canvas, "focus_mode", None)))
            painter.setPen(QPen(color, 2))
            painter.drawLine(px, 0, px, self.height())
            handle_r = 7
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setBrush(QBrush(QColor("#FF453A" if self._busy else COLORS["warning"])))
            painter.setPen(QPen(QColor("#FFFFFF"), 1))
            painter.drawEllipse(px - handle_r, 2, handle_r * 2, handle_r * 2)
        painter.end()


class TimelineWidget(QWidget):
    EDIT_WINDOW_SETTINGS_KEY = "timeline_edit_window_seconds"
    seg_clicked = pyqtSignal(int, float)
    seg_right_clicked = pyqtSignal(float, QPoint)
    stt_candidate_selected = pyqtSignal(dict)
    seg_double_clicked = pyqtSignal(int, float)
    seg_time_changed = pyqtSignal(int, float, float, str)
    seg_timing_confirm_requested = pyqtSignal(list)
    diamond_merge = pyqtSignal(int, int)
    sig_smart_split = pyqtSignal(int, float, bool)
    seg_to_gap = pyqtSignal(int)
    gap_activated = pyqtSignal(float, float)
    gap_to_segs = pyqtSignal(float, float)
    gap_generate_requested = pyqtSignal(float, float, float, str)
    scrub_sec = pyqtSignal(float)
    drag_preview_sec = pyqtSignal(float)
    drag_started = pyqtSignal()
    drag_finished = pyqtSignal()
    step_frame = pyqtSignal(int)
    sig_inline_text_changed = pyqtSignal(int, str)
    sig_editing_mode = pyqtSignal(bool)
    playhead_menu_requested = pyqtSignal(QPoint, float)
    provisional_cut_boundary_requested = pyqtSignal(float)
    provisional_cut_boundary_delete_requested = pyqtSignal(int, float)
    sig_clip_selected = pyqtSignal(int)
    waveform_ready = pyqtSignal(str, float)
    subtitle_magnet_requested = pyqtSignal()
    tab_timing_requested = pyqtSignal()
    roughcut_llm_run_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._preferred_edit_window_seconds = self._load_preferred_edit_window_seconds()

        self._base_canvas_height = CANVAS_H
        self._canvas_height_bonus = 0
        self._base_widget_height = CANVAS_H + MINIMAP_HEIGHT + 28
        self.setMinimumHeight(self._base_widget_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 0)
        lay.setSpacing(0)

        toolbar_checkbox_style = _compact_toolbar_checkbox_style()
        self.lock_chk = QCheckBox("Lock Edit")
        self.lock_chk.setStyleSheet(toolbar_checkbox_style)
        self.lock_chk.setFixedHeight(24)
        self.lock_chk.setCursor(Qt.CursorShape.PointingHandCursor)

        lock_row = QHBoxLayout()
        lock_row.setContentsMargins(0, 0, 0, 0)
        lock_row.addWidget(self.lock_chk)
        self.repeat_chk = QCheckBox("반복재생")
        self.repeat_chk.setStyleSheet(toolbar_checkbox_style)
        self.repeat_chk.setFixedHeight(24)
        self.repeat_chk.setCursor(Qt.CursorShape.PointingHandCursor)
        lock_row.addWidget(self.repeat_chk)
        lock_row.addStretch()
        self.magnet_btn = QPushButton("자막자석")
        self.magnet_btn.setStyleSheet(_compact_toolbar_button_style())
        self.magnet_btn.setFixedHeight(24)
        self.magnet_btn.clicked.connect(self.subtitle_magnet_requested.emit)
        lock_row.addWidget(self.magnet_btn)
        self._zoom_buttons = []
        for text, tip, slot in (
            ("+", "캔버스 확대", self.zoom_in),
            ("-", "캔버스 축소", self.zoom_out),
            ("O", "", self.show_ten_second_edit_window),
            ("ㅁ", "캔버스 화면 너비에 맞춤", self.fit_to_view),
        ):
            btn = QPushButton(text)
            btn.setFixedSize(28, 24)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setToolTip(tip)
            btn.setStyleSheet(button_style("toolbar", font_size="11px", padding="2px 6px"))
            btn.clicked.connect(slot)
            if text == "O":
                btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                btn.customContextMenuRequested.connect(self._queue_time_window_seconds_dialog)
                self.time_window_btn = btn
                self._refresh_time_window_button_tooltip()
            self._zoom_buttons.append(btn)
            lock_row.addWidget(btn)
        lay.addLayout(lock_row)

        self.canvas = TimelineCanvas()

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(False)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(self._base_canvas_height)
        self.scroll.setStyleSheet("QScrollArea{border:none;}")

        lay.addWidget(self.scroll)
        self._playhead_overlay = self._create_playhead_overlay()
        if self._playhead_overlay is not None:
            self._playhead_overlay.setGeometry(self.scroll.viewport().rect())
            self._playhead_overlay.hide()
        self.canvas._external_playhead_overlay = False
        self._scenegraph_layer = self._create_scenegraph_layer()
        self._apply_responsive_touch_targets()

        self.global_canvas = GlobalCanvas()
        lay.addWidget(self.global_canvas)

        self.canvas.installEventFilter(self)
        self.global_canvas.installEventFilter(self)
        self.scroll.installEventFilter(self)
        self.lock_chk.installEventFilter(self)
        self.magnet_btn.installEventFilter(self)
        self.repeat_chk.installEventFilter(self)

        self.canvas.seg_clicked.connect(self.seg_clicked)
        self.canvas.seg_right_clicked.connect(self._on_canvas_right_clicked)
        self.canvas.stt_candidate_selected.connect(self.stt_candidate_selected.emit)
        self.canvas.seg_double_clicked.connect(self.seg_double_clicked)
        self.canvas.seg_time_changed.connect(self.seg_time_changed)
        self.canvas.seg_timing_confirm_requested.connect(self.seg_timing_confirm_requested.emit)
        self.canvas.seg_to_gap.connect(self.seg_to_gap)
        self.canvas.gap_activated.connect(self.gap_activated)
        self.canvas.gap_to_segs.connect(self.gap_to_segs)
        self.canvas.gap_generate_requested.connect(self.gap_generate_requested.emit)
        self.canvas.scrub_sec.connect(self.scrub_sec)
        self.canvas.drag_preview_sec.connect(self.drag_preview_sec.emit)
        self.canvas.drag_started.connect(self.drag_started)
        self.canvas.drag_finished.connect(self.drag_finished)
        # 자막 세그먼트 좌우 화살표 리사이즈 중에는 타임라인 뷰포트가 따라 이동하지 않게 고정한다.
        self.canvas.drag_started.connect(self._begin_subtitle_resize_keep_view)
        self.canvas.drag_finished.connect(self._finish_subtitle_resize_keep_view)
        # Keep the timeline viewport fixed while subtitle segment edges are resized.
        self.canvas.drag_started.connect(self._begin_segment_drag_view_freeze)
        self.canvas.drag_finished.connect(self._finish_segment_drag_view_freeze)
        self.canvas.sig_clip_selected.connect(self._on_clip_selected)
        self.canvas.sig_inline_text_changed.connect(self.sig_inline_text_changed.emit)
        self.canvas.sig_editing_mode.connect(self.sig_editing_mode.emit)
        self.canvas.playhead_menu_requested.connect(self.playhead_menu_requested.emit)
        self.canvas.provisional_cut_boundary_requested.connect(self.provisional_cut_boundary_requested.emit)
        self.canvas.provisional_cut_boundary_delete_requested.connect(self.provisional_cut_boundary_delete_requested.emit)
        self.canvas.diamond_merge.connect(self.diamond_merge)
        self.canvas.tab_timing_requested.connect(self.tab_timing_requested.emit)
        self.canvas.sig_smart_split.connect(self.sig_smart_split)
        self.canvas.step_frame.connect(self.step_frame)

        self.global_canvas.seek_frac.connect(self._on_global_seek)
        self.global_canvas.roughcut_llm_run_requested.connect(self.roughcut_llm_run_requested.emit)

        self._wf_worker = None
        self._mc_worker = None
        self._waveform_mode = "single"
        self._waveform_path = ""
        self._selected_clip_idx = -1
        self._selected_clip_offset = 0.0
        self._selected_clip_duration = 0.0
        self._selected_clip_label = ""
        self._multiclip_fit_done = False
        self._multiclip_waveform_buffer: np.ndarray | None = None
        self._home_compact_mode = False
        self._home_compact_state: dict[str, object] = {}

        self._vp = QTimer(self)
        self._vp.setSingleShot(True)
        self._vp.setInterval(16)
        self._vp.timeout.connect(self._sync_vp)
        self.scroll.horizontalScrollBar().valueChanged.connect(self._schedule_vp_sync)
        self.scroll.horizontalScrollBar().valueChanged.connect(lambda *_: self._sync_playhead_overlay())
        self.scroll.horizontalScrollBar().valueChanged.connect(lambda *_: self._sync_scenegraph_layer())

        self._target_scroll_x = 0.0
        self._current_scroll_x = 0.0
        self._playback_center_lock = False
        self._pending_playback_center_lock = False
        self._manual_scroll_until = 0.0
        self._fit_to_view_locked = False
        self._fit_after_resize_pending = False
        self._manual_zoom_since_fit = False
        self._time_window_dialog_pending = False
        self._initial_open_view_request: dict[str, object] | None = None
        self._initial_open_view_token = None
        self.set_toolbar_tooltips(
            lock_tip="실수 편집 방지 잠금",
            magnet_tip="짧은 무음구간을 자막자석으로 붙입니다.",
            repeat_tip="선택된 세그먼트를 반복 재생합니다.",
        )
        self._speaker_settings_cache = {}
        self._speaker_settings_cache_at = 0.0
        self._boundary_times_signature = _boundary_signature(getattr(self.canvas, "boundary_times", []))
        self._scan_boundary_times_signature = _scan_boundary_signature(getattr(self.canvas, "scan_boundary_times", []))

        self._smooth_scroll_timer = QTimer(self)
        self._smooth_scroll_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._smooth_scroll_timer.setInterval(16)
        self._smooth_scroll_timer.timeout.connect(self._update_smooth_scroll)

        self._focus_border = QWidget(self)
        self._focus_border.setObjectName("TimelineFocusBorder")
        self._focus_border.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._focus_border.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._focus_border.setStyleSheet(
            "QWidget#TimelineFocusBorder {"
            " background: transparent;"
            f" border: {FOCUS_BORDER_WIDTH}px solid {FOCUS_BORDER_COLOR};"
            " border-radius: 0px;"
            "}"
        )
        self._focus_border.hide()
        self._shutdown_in_progress = False
        self._sync_scenegraph_layer()
        self._sync_focus_border()
        try:
            self.canvas._speaker_settings_provider = self._timeline_speaker_settings
        except Exception:
            pass

    def canvas_height_bonus(self) -> int:
        return int(getattr(self, "_canvas_height_bonus", 0) or 0)

    def set_canvas_height_bonus(self, bonus_px: int) -> None:
        bonus = max(0, int(bonus_px or 0))
        if bonus == self.canvas_height_bonus():
            return
        self._canvas_height_bonus = bonus
        canvas_height = self._base_canvas_height + bonus
        widget_height = self._base_widget_height + bonus
        self.canvas.setMinimumHeight(canvas_height)
        self.scroll.setFixedHeight(canvas_height)
        self.setMinimumHeight(widget_height)
        try:
            self.resize(self.width(), widget_height)
        except Exception:
            pass
        self.updateGeometry()
        self._sync_focus_border()
        self._sync_playhead_overlay()
        self._sync_scenegraph_layer()

    def _reset_single_media_context(self, *, clear_duration: bool) -> None:
        self._waveform_mode = "single"
        self._selected_clip_idx = -1
        self._selected_clip_offset = 0.0
        self._selected_clip_duration = 0.0
        self._selected_clip_label = ""
        self._multiclip_fit_done = False
        if hasattr(self.canvas, "_multiclip_boxes"):
            self.canvas._multiclip_boxes = []
        if hasattr(self.canvas, "_active_clip_idx"):
            self.canvas._active_clip_idx = 0
        if hasattr(self.global_canvas, "_multiclip_boxes"):
            self.global_canvas._multiclip_boxes = []
        if hasattr(self.global_canvas, "_active_clip_idx"):
            self.global_canvas._active_clip_idx = 0
        self.global_canvas.set_clip_label("")
        self.clear_shadow_playhead()
        if clear_duration:
            self.canvas.total_duration = 0.0
            self.global_canvas.total_duration = 0.0
        target_w = self._canvas_width_for_duration(float(getattr(self.canvas, "total_duration", 0.0) or 0.0))
        if self.canvas.width() != target_w:
            self.canvas.setFixedWidth(target_w)
        self._schedule_vp_sync()
        self._sync_scenegraph_layer()
        self._sync_playhead_overlay()

    def set_auto_gap_segments_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        canvas = getattr(self, "canvas", None)
        if canvas is not None:
            canvas.auto_generate_gap_segments = enabled
            canvas.show_gap_insert_controls = enabled
            canvas._gap_segments_signature = None
            if not enabled:
                canvas.gap_segments = [
                    dict(gap)
                    for gap in list(getattr(canvas, "gap_segments", []) or [])
                    if bool(gap.get("_explicit_gap"))
                ]
            if hasattr(canvas, "_invalidate_marker_caches"):
                canvas._invalidate_marker_caches()
            if hasattr(canvas, "_invalidate_render_cache"):
                canvas._invalidate_render_cache()
            canvas.update()

    def _apply_single_media_duration(self, dur: float) -> None:
        self._reset_single_media_context(clear_duration=False)
        duration = max(0.0, float(dur or 0.0))
        self.canvas.total_duration = duration
        self.global_canvas.total_duration = duration
        target_w = self._canvas_width_for_duration(duration)
        if self.canvas.width() != target_w:
            self.canvas.setFixedWidth(target_w)
        self._schedule_vp_sync()
        if bool(getattr(self, "_fit_to_view_locked", False)):
            self.schedule_fit_to_view((0,))
        else:
            self._sync_scenegraph_layer()
            self._sync_playhead_overlay()

    def stop_waveform_workers(self, timeout_ms: int = 1200):
        for attr in ("_wf_worker", "_mc_worker"):
            worker = getattr(self, attr, None)
            if worker is None:
                continue
            try:
                if hasattr(worker, "stop"):
                    worker.stop()
                else:
                    worker.requestInterruption()
                    worker.quit()
                if worker.isRunning() and not worker.wait(max(50, int(timeout_ms))):
                    if hasattr(worker, "stop"):
                        worker.stop()
                    worker.wait(200)
            except Exception:
                pass
            finally:
                setattr(self, attr, None)

    def compact_for_home_navigation(self) -> None:
        if bool(getattr(self, "_home_compact_mode", False)):
            return
        self._home_compact_mode = True
        self._home_compact_state = {
            "waveform_mode": str(getattr(self, "_waveform_mode", "single") or "single"),
            "waveform_path": str(getattr(self, "_waveform_path", "") or ""),
        }
        self.stop_waveform_workers()
        self._multiclip_waveform_buffer = None
        self._speaker_settings_cache = {}
        self._speaker_settings_cache_at = 0.0
        try:
            self.canvas.set_waveform(None)
            self.global_canvas.set_waveform(None)
        except Exception:
            pass
        try:
            self.clear_shadow_playhead()
        except Exception:
            pass
        try:
            self._refresh_canvas_playhead_cache()
            self.update()
        except Exception:
            pass

    def restore_after_home_navigation(
        self,
        *,
        waveform_path: str = "",
        multiclip_boundaries=None,
    ) -> None:
        state = dict(getattr(self, "_home_compact_state", {}) or {})
        if not bool(getattr(self, "_home_compact_mode", False)) and not state:
            return
        self._home_compact_mode = False
        self._home_compact_state = {}
        mode = str(state.get("waveform_mode", getattr(self, "_waveform_mode", "single")) or "single")
        path = str(waveform_path or state.get("waveform_path", "") or "")
        if mode == "multi" and list(multiclip_boundaries or []):
            self.load_multiclip_waveform(list(multiclip_boundaries or []))
            return
        if path:
            self.load_waveform(path, force=True)
            return
        try:
            self._sync_scenegraph_layer()
            self._sync_playhead_overlay()
            self.update()
        except Exception:
            pass

    def closeEvent(self, event):
        self._shutdown_in_progress = True
        setattr(self.canvas, "_shutdown_in_progress", True)
        setattr(self.global_canvas, "_shutdown_in_progress", True)
        self.stop_waveform_workers()
        try:
            self._smooth_scroll_timer.stop()
        except Exception:
            pass
        layer = getattr(self, "_scenegraph_layer", None)
        if layer is not None:
            try:
                layer.delete_later()
            except Exception:
                pass
        overlay = getattr(self, "_playhead_overlay", None)
        if overlay is not None:
            try:
                overlay._shutdown_in_progress = True
                overlay.hide()
                overlay.deleteLater()
            except Exception:
                pass
        super().closeEvent(event)

    def set_frame_rate(self, fps: float):
        fps = normalize_fps(fps)
        self.video_fps = fps
        if hasattr(self, "canvas"):
            self.canvas.set_frame_rate(fps)
        if hasattr(self, "global_canvas"):
            setattr(self.global_canvas, "frame_rate", fps)
        self._sync_scenegraph_layer()

    def _create_scenegraph_layer(self):
        self.canvas._scenegraph_subtitle_rendering = False
        return None

    def _timeline_speaker_settings(self) -> dict:
        now = time.monotonic()
        cache = getattr(self, "_speaker_settings_cache", None)
        cached_at = float(getattr(self, "_speaker_settings_cache_at", 0.0) or 0.0)
        if isinstance(cache, dict) and cache and (now - cached_at) < 1.0:
            return dict(cache)
        owner = self.parent()
        while owner is not None and not hasattr(owner, "settings"):
            owner = owner.parent()
        settings = getattr(owner, "settings", {}) if owner is not None else {}
        try:
            from ui.timeline.speaker_labels import current_speaker_settings

            settings = current_speaker_settings(dict(settings or {}))
        except Exception:
            settings = dict(settings or {})
        self._speaker_settings_cache = dict(settings or {})
        self._speaker_settings_cache_at = now
        return dict(self._speaker_settings_cache)

    def _sync_scenegraph_layer(self):
        canvas = getattr(self, "canvas", None)
        if canvas is not None and bool(getattr(canvas, "_single_owner_2d_renderer", True)):
            canvas._scenegraph_subtitle_rendering = False
            layer = getattr(self, "_scenegraph_layer", None)
            if layer is not None:
                try: layer.set_visible(False)
                except RuntimeError: pass
            return
        layer = getattr(self, "_scenegraph_layer", None)
        if layer is None:
            return
        viewport = self.scroll.viewport() if hasattr(self, "scroll") else None
        if canvas is None or viewport is None:
            return
        try:
            layer.set_geometry(viewport.rect())
            pps = max(0.001, float(getattr(canvas, "pps", 1.0) or 1.0))
            scroll_x = int(self.scroll.horizontalScrollBar().value())
            visible_start = max(0.0, scroll_x / pps)
            visible_end = max(visible_start, (scroll_x + max(1, viewport.width())) / pps)
            active = not bool(getattr(canvas, "_edit_active", False))
            if not active:
                canvas._scenegraph_subtitle_rendering = False
                layer.set_visible(False)
                return
            if hasattr(canvas, "visible_segments_for_time_window"):
                visible_segments = canvas.visible_segments_for_time_window(
                    visible_start,
                    visible_end,
                    pad_sec=0.35,
                )
            else:
                visible_segments = getattr(canvas, "segments", []) or []
            rendered_count = layer.set_state(
                segments=visible_segments,
                pps=pps,
                fps=float(canvas._get_fps() if hasattr(canvas, "_get_fps") else getattr(self, "video_fps", 30.0)),
                scroll_x=scroll_x,
                visible_start_sec=visible_start,
                visible_end_sec=visible_end,
                active_start=getattr(canvas, "active_seg_start", None),
                active_line=getattr(canvas, "active_seg_line", None),
                hover_line=getattr(canvas, "_hover_line", None),
                playback_active=bool(canvas._timeline_playback_active()) if hasattr(canvas, "_timeline_playback_active") else False,
                playhead_sec=float(getattr(canvas, "playhead_sec", 0.0) or 0.0),
                quality_filter=str(getattr(canvas, "quality_filter", "all") or "all"),
                speaker_settings=self._timeline_speaker_settings(),
                render_epoch=int(getattr(canvas, "_render_epoch", 0) or 0),
            )
            if int(rendered_count or 0) <= 0:
                canvas._scenegraph_subtitle_rendering = False
                layer.set_visible(False)
                return
            canvas._scenegraph_subtitle_rendering = True
            layer.set_visible(True)
            layer.raise_()
        except RuntimeError:
            pass

    def snap_sec_to_frame(self, sec: float) -> float:
        return snap_sec_to_frame(sec, getattr(self, "video_fps", getattr(self.canvas, "frame_rate", 30.0)))

    def _timeline_fps(self) -> float:
        return normalize_fps(getattr(self, "video_fps", getattr(self.canvas, "frame_rate", 30.0)))

    def _pixels_per_frame(self, pps: float | None = None) -> float:
        pps_value = float(self.canvas.pps if pps is None else pps)
        return max(0.001, pps_value) / max(1.0, self._timeline_fps())

    def _frame_for_sec(self, sec: float) -> int:
        return sec_to_nearest_frame(sec, self._timeline_fps())

    def _sec_for_frame(self, frame: int) -> float:
        return frame_to_sec(frame, self._timeline_fps())

    def _scroll_x_for_sec(self, sec: float, pps: float | None = None) -> int:
        frame = self._frame_for_sec(sec)
        return int(round(frame * self._pixels_per_frame(pps)))

    def _sec_for_scroll_x(self, scroll_x: int | float) -> float:
        frame = int(round(float(scroll_x or 0.0) / max(0.001, self._pixels_per_frame())))
        return self._sec_for_frame(frame)

    def _current_visible_seconds(self) -> float:
        viewport_w = max(1, int(self.scroll.viewport().width()))
        pps = max(0.001, float(getattr(self.canvas, "pps", 1.0) or 1.0))
        return max(1.0, float(viewport_w) / pps)

    def _current_visible_center_sec(self) -> float:
        pps = max(0.001, float(getattr(self.canvas, "pps", 1.0) or 1.0))
        visible_start = float(self.scroll.horizontalScrollBar().value()) / pps
        return max(0.0, visible_start + (self._current_visible_seconds() / 2.0))

    def _apply_edit_window_seconds(
        self,
        seconds: float,
        *,
        center_sec: float | None = None,
    ) -> None:
        try:
            window_seconds = max(1.0, float(seconds or 10.0))
        except Exception:
            window_seconds = 10.0
        anchor_sec = self._editing_window_anchor_sec() if center_sec is None else float(center_sec or 0.0)
        self.show_time_window_seconds(window_seconds, center_sec=anchor_sec)
        self._fit_to_view_locked = False
        self._fit_after_resize_pending = False
        self._manual_zoom_since_fit = True
        self._begin_manual_scroll(hold_sec=1.2)

    def _queue_time_window_seconds_dialog(self, _pos: QPoint | None = None) -> None:
        if bool(getattr(self, "_time_window_dialog_pending", False)):
            return
        self._time_window_dialog_pending = True
        QTimer.singleShot(0, self._show_time_window_seconds_dialog)

    def _restore_toolbar_after_time_window_dialog(self) -> None:
        self._time_window_dialog_pending = False
        for grabber_getter, releaser_name in (
            (QWidget.mouseGrabber, "releaseMouse"),
            (QWidget.keyboardGrabber, "releaseKeyboard"),
        ):
            try:
                grabber = grabber_getter()
            except Exception:
                grabber = None
            if grabber is None:
                continue
            try:
                getattr(grabber, releaser_name)()
            except Exception:
                pass

        self._release_lingering_time_window_dialog_state()

        for btn in list(getattr(self, "_zoom_buttons", []) or []):
            try:
                btn.releaseMouse()
                btn.releaseKeyboard()
                btn.setDown(False)
                btn.clearFocus()
                btn.update()
            except Exception:
                continue
        try:
            owner = self.window()
        except Exception:
            owner = None
        if owner is not None and owner is not self:
            try:
                owner.activateWindow()
            except Exception:
                pass
        try:
            self.setFocus(Qt.FocusReason.OtherFocusReason)
        except Exception:
            pass
        self._sync_focus_border()

    def _release_lingering_time_window_dialog_state(self, dialog: QWidget | None = None) -> None:
        seen: set[int] = set()
        widgets = []
        if dialog is not None:
            widgets.append(dialog)
        for getter in (
            getattr(QApplication, "activePopupWidget", None),
            getattr(QApplication, "activeModalWidget", None),
        ):
            if not callable(getter):
                continue
            try:
                widget = getter()
            except Exception:
                widget = None
            if widget is not None:
                widgets.append(widget)

        for widget in widgets:
            if widget is None:
                continue
            widget_id = id(widget)
            if widget_id in seen:
                continue
            seen.add(widget_id)
            if widget is self:
                continue
            try:
                widget.releaseMouse()
            except Exception:
                pass
            try:
                widget.releaseKeyboard()
            except Exception:
                pass
            try:
                widget.clearFocus()
            except Exception:
                pass
            try:
                widget.hide()
            except Exception:
                pass
            try:
                widget.close()
            except Exception:
                pass

    def _queue_toolbar_restore_after_time_window_dialog(self) -> None:
        self._restore_toolbar_after_time_window_dialog()
        for delay in (0, 40, 120):
            QTimer.singleShot(delay, self._restore_toolbar_after_time_window_dialog)

    def _show_time_window_seconds_dialog(self, _pos: QPoint | None = None) -> None:
        current_seconds = self._current_visible_seconds()
        current_seconds_rounded = max(1, int(round(current_seconds)))
        current_seconds_label = (
            f"{current_seconds:.1f}초"
            if abs(current_seconds - current_seconds_rounded) >= 0.05
            else f"{current_seconds_rounded}초"
        )
        center_sec = self._current_visible_center_sec()
        try:
            owner = self.window()
        except Exception:
            owner = None
        if owner is None:
            owner = self
        dialog = QInputDialog(owner)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        dialog.setWindowTitle("편집 창 시간")
        dialog.setInputMode(QInputDialog.InputMode.IntInput)
        dialog.setLabelText(
            f"현재 표시 시간: {current_seconds_label}\n"
            "표시할 편집 창 시간을 1초 단위로 조정하세요."
        )
        dialog.setIntRange(1, 600)
        dialog.setIntStep(1)
        dialog.setIntValue(current_seconds_rounded)
        dialog.setOkButtonText("적용")
        dialog.setCancelButtonText("취소")
        dialog.setStyleSheet(settings_dialog_stylesheet())
        try:
            if dialog.exec():
                # exec() 종료 직후에도 값을 읽어야 하므로 자동 삭제를 켜지 않는다.
                selected_seconds = float(dialog.intValue())
                self._apply_edit_window_seconds(selected_seconds, center_sec=center_sec)
                self._save_preferred_edit_window_seconds(selected_seconds)
        finally:
            try:
                dialog.releaseMouse()
                dialog.releaseKeyboard()
            except Exception:
                pass
            self._release_lingering_time_window_dialog_state(dialog)
            try:
                dialog.deleteLater()
            except Exception:
                pass
            self._queue_toolbar_restore_after_time_window_dialog()

    def _create_playhead_overlay(self):
        return TimelinePlayheadOverlay(self, self.scroll.viewport())

    def _refresh_canvas_playhead_cache(self) -> None:
        canvas = getattr(self, "canvas", None)
        if canvas is None or not hasattr(canvas, "_x"):
            return
        try:
            canvas._last_playhead_px = canvas._x(float(getattr(canvas, "playhead_sec", 0.0) or 0.0))
        except Exception:
            canvas._last_playhead_px = None
        shadow_sec = getattr(canvas, "shadow_playhead_sec", None)
        try:
            canvas._last_shadow_playhead_px = None if shadow_sec is None else canvas._x(float(shadow_sec or 0.0))
        except Exception:
            canvas._last_shadow_playhead_px = None

    def _canvas_width_for_duration(self, dur: float, pps: float | None = None) -> int:
        pps = float(self.canvas.pps if pps is None else pps)
        total_frames = frame_count(dur, self._timeline_fps())
        end_padding = 96
        return max(int(round(total_frames * self._pixels_per_frame(pps))) + end_padding, self.scroll.width())

    def _fit_reference_width(self) -> int:
        global_canvas = getattr(self, "global_canvas", None)
        if global_canvas is not None:
            try:
                global_width = int(global_canvas.width())
            except RuntimeError:
                global_width = 0
            if global_width > 0:
                return max(1, global_width)
        viewport = self.scroll.viewport()
        viewport_w = viewport.width() if viewport is not None else self.scroll.width()
        return max(1, int(viewport_w))

    def _fit_content_duration(self) -> float:
        if self._selected_clip_idx >= 0 and self._selected_clip_duration > 0:
            return max(0.0, float(self._selected_clip_duration))

        boxes = list(getattr(self.canvas, "_multiclip_boxes", []) or [])
        if boxes:
            return max(0.0, float(boxes[-1].get("end", 0.0) or 0.0))

        total_duration = max(0.0, float(getattr(self.canvas, "total_duration", 0.0) or 0.0))
        cached_duration = getattr(self.canvas, "_segments_content_duration", None)
        if cached_duration is not None:
            try:
                return max(total_duration, max(0.0, float(cached_duration or 0.0)))
            except Exception:
                pass

        seg_end = 0.0
        for seg in list(getattr(self.canvas, "segments", []) or []):
            if not isinstance(seg, dict) or seg.get("is_gap"):
                continue
            try:
                seg_end = max(seg_end, float(seg.get("end", 0.0) or 0.0))
            except Exception:
                continue
        if seg_end > 0.0:
            return max(total_duration, seg_end)

        return total_duration

    def _fit_pps_for_duration(self, dur: float) -> float:
        if dur <= 0:
            return float(self.canvas.pps)
        visible_w = self._fit_reference_width()
        return max(0.001, min(500.0, visible_w / max(0.001, float(dur))))

    def _clamp_scroll_x(self, value: float) -> int:
        sb = self.scroll.horizontalScrollBar()
        return max(0, min(int(value), sb.maximum()))

    def _playhead_zoom_anchor(self, old_pps: float) -> tuple[float, float]:
        dur = max(0.0, float(getattr(self.canvas, "total_duration", 0.0) or 0.0))
        playhead_sec = self.snap_sec_to_frame(max(0.0, min(dur, float(getattr(self.canvas, "playhead_sec", 0.0) or 0.0))))
        viewport_w = max(1, self.scroll.viewport().width())
        current_scroll = float(self.scroll.horizontalScrollBar().value())
        playhead_view_x = float(self._scroll_x_for_sec(playhead_sec, old_pps)) - current_scroll
        if 0 <= playhead_view_x <= viewport_w:
            return playhead_sec, playhead_view_x
        return playhead_sec, viewport_w / 2.0

    def _apply_zoom(self, factor: float, *, anchor_sec: float | None = None, anchor_view_x: float | None = None):
        dur = self.canvas.total_duration
        if dur <= 0:
            return
        old_pps = float(self.canvas.pps)
        min_pps = self._fit_pps_for_duration(dur)
        new_pps = max(min_pps, min(500.0, old_pps * float(factor)))
        if abs(new_pps - old_pps) < 0.01:
            return
        if anchor_sec is None or anchor_view_x is None:
            anchor_sec, anchor_view_x = self._playhead_zoom_anchor(old_pps)

        target_w = self._canvas_width_for_duration(dur, new_pps)
        viewport_w = max(1, int(self.scroll.viewport().width()))
        max_scroll = max(0, int(target_w) - viewport_w)
        new_scroll = int(self._scroll_x_for_sec(float(anchor_sec), new_pps) - float(anchor_view_x))
        new_scroll = max(0, min(new_scroll, max_scroll))
        sb = self.scroll.horizontalScrollBar()
        self.canvas.setUpdatesEnabled(False)
        try:
            self.canvas.pps = new_pps
            if self.canvas.width() != target_w:
                self.canvas.setFixedWidth(target_w)
            sb.setValue(new_scroll)
            self._target_scroll_x = float(new_scroll)
            self._current_scroll_x = float(new_scroll)
        finally:
            self.canvas.setUpdatesEnabled(True)
        self._refresh_canvas_playhead_cache()
        if hasattr(self.canvas, "_update_viewport_region"):
            self.canvas._update_viewport_region()
        else:
            view_w = max(1, int(self.scroll.viewport().width()))
            self.canvas.update(QRect(max(0, new_scroll - 160), 0, view_w + 320, self.canvas.height()))
        self._schedule_vp_sync()
        self._sync_playhead_overlay()

    def _on_canvas_right_clicked(self, start_sec, gpos):
        self.seg_right_clicked.emit(start_sec, gpos)

    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent

        if ev.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self.update()
            self.global_canvas.update()
            QTimer.singleShot(0, self._sync_focus_border)
        return False

    def _has_timeline_focus(self):
        return (
            self.hasFocus()
            or self.canvas.hasFocus()
            or self.global_canvas.hasFocus()
            or self.scroll.hasFocus()
            or self.lock_chk.hasFocus()
            or self.magnet_btn.hasFocus()
            or self.repeat_chk.hasFocus()
        )

    def set_toolbar_tooltips(self, *, lock_tip: str = "", magnet_tip: str = "", repeat_tip: str = "") -> None:
        if hasattr(self, "lock_chk"):
            self.lock_chk.setToolTip(str(lock_tip or ""))
        if hasattr(self, "magnet_btn"):
            self.magnet_btn.setToolTip(str(magnet_tip or ""))
        if hasattr(self, "repeat_chk"):
            self.repeat_chk.setToolTip(str(repeat_tip or ""))

    def _sync_focus_border(self):
        border = getattr(self, "_focus_border", None)
        if border is None:
            return
        border.setGeometry(0, 0, max(1, self.width()), max(1, self.height()))
        visible = self._has_timeline_focus()
        border.setVisible(visible)
        if visible:
            border.raise_()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._apply_responsive_touch_targets()
        self._sync_focus_border()
        self._sync_playhead_overlay()
        self._sync_scenegraph_layer()
        self._schedule_vp_sync()
        if bool(getattr(self, "_fit_to_view_locked", False)):
            self.schedule_fit_to_view()

    def _current_responsive_profile(self):
        try:
            win = self.window()
            override = str(win.property("responsive_profile_override") or self.property("responsive_profile_override") or "")
            width = int(win.width() or self.width() or 0)
            height = int(win.height() or self.height() or 0)
        except Exception:
            override = ""
            width = int(self.width() or 0)
            height = int(self.height() or 0)
        return responsive_profile_for_size(width, height, override=override)

    def _apply_responsive_touch_targets(self):
        profile = self._current_responsive_profile()
        touch_mode = profile.name != "desktop"
        for btn in getattr(self, "_zoom_buttons", []) or []:
            if touch_mode:
                btn.setFixedSize(profile.touch_target, 44)
            else:
                btn.setFixedSize(28, 24)

    def paintEvent(self, ev):
        if bool(getattr(self, "_shutdown_in_progress", False)):
            return
        super().paintEvent(ev)
        self._sync_focus_border()
        if self._has_timeline_focus():
            from PyQt6.QtGui import QColor, QPainter, QPen

            painter = QPainter(self)
            if not painter.isActive():
                return
            painter.setPen(QPen(QColor(FOCUS_BORDER_COLOR), FOCUS_BORDER_WIDTH))
            inset = max(1, FOCUS_BORDER_WIDTH // 2)
            left = inset
            top = inset
            right = max(left, self.width() - FOCUS_BORDER_WIDTH)
            bottom = max(top, self.height() - FOCUS_BORDER_WIDTH)
            painter.drawLine(left, top, right, top)
            painter.drawLine(left, bottom, right, bottom)
            painter.drawLine(left, top, left, bottom)
            painter.drawLine(right, top, right, bottom)
            painter.end()

    def _apply_selected_clip_context(self, clip_idx: int):
        boxes = getattr(self.canvas, "_multiclip_boxes", []) or []
        if clip_idx < 0 or clip_idx >= len(boxes):
            return False
        box = boxes[clip_idx]
        self._selected_clip_idx = int(clip_idx)
        self._selected_clip_offset = float(box.get("start", 0.0))
        self._selected_clip_duration = max(
            0.001,
            float(box.get("end", 0.0)) - float(box.get("start", 0.0)),
        )
        self._selected_clip_label = str(box.get("index", clip_idx + 1))
        self.canvas._active_clip_idx = int(clip_idx)
        self.global_canvas.set_clip_label(self._selected_clip_label)
        return True

    def _global_to_local_sec(self, sec: float) -> float:
        if self._selected_clip_idx >= 0 and self._selected_clip_duration > 0:
            return max(
                0.0,
                min(self._selected_clip_duration, float(sec) - self._selected_clip_offset),
            )
        return max(0.0, float(sec))

    def _viewport_fracs_for_selected_clip(self):
        sb = self.scroll.horizontalScrollBar()
        view_w = self.scroll.viewport().width() if self.scroll.viewport() else self.scroll.width()
        global_start = self._sec_for_scroll_x(sb.value())
        global_end = self._sec_for_scroll_x(sb.value() + view_w)

        if self._selected_clip_idx >= 0 and self._selected_clip_duration > 0:
            clip_start = float(self._selected_clip_offset or 0.0)
            clip_dur = max(0.001, float(self._selected_clip_duration or 0.0))
            local_start = max(0.0, min(clip_dur, global_start - clip_start))
            local_end = max(local_start, min(clip_dur, global_end - clip_start))
            return local_start / clip_dur, local_end / clip_dur

        dur = max(0.001, float(getattr(self.canvas, "total_duration", 0.0)))
        if dur <= 0:
            return 0.0, 1.0
        return max(0.0, min(1.0, global_start / dur)), max(0.0, min(1.0, global_end / dur))


    def _segment_drag_view_freeze_active(self) -> bool:
        try:
            return bool(getattr(self, "_segment_drag_view_freeze", False)) or time.monotonic() < float(getattr(self, "_segment_drag_view_freeze_until", 0.0) or 0.0)
        except Exception:
            return bool(getattr(self, "_segment_drag_view_freeze", False))

    def _snapshot_segment_drag_view(self) -> None:
        try:
            sb = self.scroll.horizontalScrollBar()
            current = int(sb.value())
            self._segment_drag_scroll_x = current
            self._segment_drag_target_x = float(getattr(self, "_target_scroll_x", current))
            self._segment_drag_current_x = float(getattr(self, "_current_scroll_x", current))
        except Exception:
            pass

    def _restore_segment_drag_view(self) -> None:
        try:
            sb = self.scroll.horizontalScrollBar()
            target = int(getattr(self, "_segment_drag_scroll_x", sb.value()))
            target = int(self._clamp_scroll_x(target))
            if self._smooth_scroll_timer.isActive():
                self._smooth_scroll_timer.stop()
            sb.setValue(target)
            self._target_scroll_x = float(target)
            self._current_scroll_x = float(target)
            self._schedule_vp_sync()
            self._sync_playhead_overlay()
        except Exception:
            pass

    def _begin_segment_drag_view_freeze(self) -> None:
        self._segment_drag_view_freeze = True
        self._segment_drag_view_freeze_until = 0.0
        self._snapshot_segment_drag_view()
        try:
            if self._smooth_scroll_timer.isActive():
                self._smooth_scroll_timer.stop()
        except Exception:
            pass
        try:
            self.set_playback_center_lock(False)
        except Exception:
            pass

    def _finish_segment_drag_view_freeze(self) -> None:
        # seg_time_changed -> editor redraw is usually scheduled with QTimer(0).
        # Keep a short grace window so the viewport is restored after that redraw too.
        self._segment_drag_view_freeze = False
        self._segment_drag_view_freeze_until = time.monotonic() + 0.8
        self._restore_segment_drag_view()
        QTimer.singleShot(0, self._restore_segment_drag_view)
        QTimer.singleShot(80, self._restore_segment_drag_view)
        QTimer.singleShot(240, self._restore_segment_drag_view)

    def update_segments(self, segs, active_sec=None, total_dur=0.0, fit_view=False):
        _keep_view_x = None
        _preserve_scroll_x = None
        try:
            if hasattr(self, "_subtitle_resize_keep_view_active") and self._subtitle_resize_keep_view_active():
                _keep_view_x = int(getattr(self, "_subtitle_resize_scroll_x", self.scroll.horizontalScrollBar().value()))
        except Exception:
            _keep_view_x = None
            
        try:
            if hasattr(self, "_segment_drag_view_freeze_active") and self._segment_drag_view_freeze_active():
                _preserve_scroll_x = int(getattr(self, "_segment_drag_scroll_x", self.scroll.horizontalScrollBar().value()))
        except Exception:
            _preserve_scroll_x = None

        seg_end = segs[-1]["end"] if segs else 0.0
        prev_dur = getattr(self.canvas, "total_duration", 0.0)
        dur = max(prev_dur, total_dur or 0.0, seg_end)

        target_w = self._canvas_width_for_duration(dur)
        if self.canvas.width() != target_w:
            self.canvas.setFixedWidth(target_w)
        self.canvas.update_segments(segs, active_sec, dur)
        self.global_canvas.update_segments(
            getattr(self.canvas, "segments", segs),
            dur,
            signature=getattr(self.canvas, "_segments_geometry_signature", None),
            rows=getattr(self.canvas, "segments", None),
        )
        self._sync_scenegraph_layer()
        if _keep_view_x is not None and not fit_view:
            self._restore_subtitle_resize_view()
        if _preserve_scroll_x is not None and not fit_view:
            self._restore_segment_drag_view()
        if fit_view or bool(getattr(self, "_fit_to_view_locked", False)):
            self.fit_to_view()
        elif self._waveform_mode == "multi":
            # 멀티클립에서는 현재 줌(pps) 유지. 최초 전체 로드에서만 fit_to_view 허용.
            pass


    def _subtitle_resize_keep_view_active(self) -> bool:
        """자막 세그먼트 경계 리사이즈 직후 타임라인 위치를 고정해야 하는지 확인."""
        try:
            until = float(getattr(self, "_subtitle_resize_keep_view_until", 0.0) or 0.0)
        except Exception:
            until = 0.0
        return bool(getattr(self, "_subtitle_resize_keep_view", False)) or time.monotonic() < until

    def _snapshot_subtitle_resize_view(self) -> None:
        """현재 타임라인 가로 스크롤 위치를 저장."""
        try:
            sb = self.scroll.horizontalScrollBar()
            x = int(sb.value())
            self._subtitle_resize_scroll_x = x
            self._target_scroll_x = float(x)
            self._current_scroll_x = float(x)
        except Exception:
            pass

    def _restore_subtitle_resize_view(self) -> None:
        """세그먼트 시간 변경 후에도 사용자가 보던 타임라인 위치를 복원."""
        try:
            sb = self.scroll.horizontalScrollBar()
            x = int(getattr(self, "_subtitle_resize_scroll_x", sb.value()))
            x = int(self._clamp_scroll_x(x))
            if self._smooth_scroll_timer.isActive():
                self._smooth_scroll_timer.stop()
            sb.setValue(x)
            self._target_scroll_x = float(x)
            self._current_scroll_x = float(x)
            self._schedule_vp_sync()
            self._sync_playhead_overlay()
        except Exception:
            pass

    def _begin_subtitle_resize_keep_view(self) -> None:
        """타임라인 캔버스 드래그 시작 시 현재 화면 위치 고정."""
        self._subtitle_resize_keep_view = True
        self._subtitle_resize_keep_view_until = 0.0
        self._snapshot_subtitle_resize_view()
        try:
            if self._smooth_scroll_timer.isActive():
                self._smooth_scroll_timer.stop()
        except Exception:
            pass
        try:
            self.set_playback_center_lock(False)
        except Exception:
            pass

    def _finish_subtitle_resize_keep_view(self) -> None:
        """드래그 종료 직후 redraw/set_active가 들어와도 짧은 시간 화면 위치 유지."""
        self._subtitle_resize_keep_view = False
        self._subtitle_resize_keep_view_until = time.monotonic() + 0.8
        self._restore_subtitle_resize_view()
        QTimer.singleShot(0, self._restore_subtitle_resize_view)
        QTimer.singleShot(80, self._restore_subtitle_resize_view)
        QTimer.singleShot(240, self._restore_subtitle_resize_view)

    def set_vad_segments(self, vad_segs: list):
        self.canvas.set_vad_segments(vad_segs)
        self.global_canvas.set_vad_segments(vad_segs)

    def set_voice_activity_segments(self, segments: list[dict]):
        if hasattr(self.canvas, "set_voice_activity_segments"):
            self.canvas.set_voice_activity_segments(segments)

    def set_active(self, sec):
        sec = self.snap_sec_to_frame(sec)
        self.canvas.set_active(sec)
        if bool(getattr(self, "_fit_to_view_locked", False)):
            self._sync_playhead_overlay()
            return
        if sec is not None and not self._segment_drag_view_freeze_active():
            self.ensure_sec_visible(sec, smooth=True, margin_px=96)

    def _sec_visible_in_view(self, sec: float, *, margin_px: int = 96) -> bool:
        try:
            x = float(self._scroll_x_for_sec(sec))
            viewport = self.scroll.viewport()
            viewport_w = int(viewport.width()) if viewport is not None else int(self.scroll.width())
            scroll_x = int(self.scroll.horizontalScrollBar().value())
            margin = max(0, min(int(margin_px), max(0, viewport_w // 3)))
            return (scroll_x + margin) <= x <= (scroll_x + max(1, viewport_w) - margin)
        except Exception:
            return False

    def ensure_sec_visible(self, sec: float, *, smooth: bool = True, margin_px: int = 96) -> None:
        if bool(getattr(self, "_fit_to_view_locked", False)):
            self._sync_playhead_overlay()
            return
        if self._segment_drag_view_freeze_active():
            self._restore_segment_drag_view()
            return
        sec = self.snap_sec_to_frame(sec)
        if self._sec_visible_in_view(sec, margin_px=margin_px):
            self._target_scroll_x = float(self.scroll.horizontalScrollBar().value())
            self._current_scroll_x = self._target_scroll_x
            self._sync_playhead_overlay()
            return
        self.center_to_sec(sec, smooth=smooth)

    def set_playhead(self, sec, *, preserve_center_lock: bool = False):
        sec = self.snap_sec_to_frame(sec)
        if not preserve_center_lock:
            self.set_playback_center_lock(False)
        self.canvas.set_playhead(max(0.0, float(sec or 0.0)))
        self._sync_playhead_overlay()
        self.global_canvas.set_playhead(self._global_to_local_sec(sec))

    def set_shadow_playhead(self, sec: float | None):
        canvas = getattr(self, "canvas", None)
        if canvas is None or not hasattr(canvas, "set_shadow_playhead"):
            return False
        normalized = None if sec is None else self.snap_sec_to_frame(sec)
        if normalized is not None:
            try:
                canvas._shadow_playhead_armed_sec = None
            except Exception:
                pass
        changed = bool(canvas.set_shadow_playhead(normalized))
        if changed:
            self._sync_playhead_overlay()
        return changed

    def clear_shadow_playhead(self):
        return self.set_shadow_playhead(None)

    def arm_shadow_playhead(self, sec: float | None):
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return False
        normalized = None if sec is None else self.snap_sec_to_frame(sec)
        try:
            canvas._shadow_playhead_armed_sec = normalized
        except Exception:
            return False
        self.clear_shadow_playhead()
        return normalized is not None

    def pin_shadow_playhead(self, sec: float | None = None):
        target = getattr(self.canvas, "playhead_sec", 0.0) if sec is None else sec
        return self.set_shadow_playhead(target)

    def follow_playhead(self, sec, *, smooth=True, threshold_px=24.0):
        sec = self.snap_sec_to_frame(sec)
        self.set_playhead(sec)
        if bool(getattr(self, "_fit_to_view_locked", False)):
            self._target_scroll_x = float(self.scroll.horizontalScrollBar().value())
            self._current_scroll_x = self._target_scroll_x
            return
        self._scroll_canvas_to_sec(sec, smooth=smooth, threshold_px=threshold_px)

    def follow_playhead_centered(self, sec, *, smooth=True):
        sec = self.snap_sec_to_frame(sec)
        if bool(getattr(self, "_fit_to_view_locked", False)):
            self.set_playhead(sec)
            self._target_scroll_x = float(self.scroll.horizontalScrollBar().value())
            self._current_scroll_x = self._target_scroll_x
            return
        if self._manual_scroll_active():
            self.set_playhead(sec)
            self._target_scroll_x = float(self.scroll.horizontalScrollBar().value())
            self._current_scroll_x = self._target_scroll_x
            return
        if not getattr(self, "_playback_center_lock", False):
            self.set_playhead(sec)
            viewport = self.scroll.viewport()
            viewport_w = viewport.width() if viewport is not None else self.scroll.width()
            center_x = max(1.0, float(viewport_w) / 2.0)
            current_scroll = float(self.scroll.horizontalScrollBar().value())
            playhead_scroll_x = float(self._scroll_x_for_sec(sec))
            playhead_x = playhead_scroll_x - current_scroll
            target_scroll = float(self._clamp_scroll_x(playhead_scroll_x - center_x))
            if playhead_x < center_x and target_scroll <= current_scroll + 1.0:
                self._pending_playback_center_lock = False
                self._target_scroll_x = current_scroll
                self._current_scroll_x = current_scroll
                return
            if self._pixels_per_frame() >= 10.0 and target_scroll > current_scroll + 1.0:
                self._pending_playback_center_lock = False
                self.set_playback_center_lock(True)
                self.set_playhead(sec, preserve_center_lock=True)
                self._scroll_canvas_to_sec(sec, smooth=smooth, threshold_px=0.0)
                return
            if abs(target_scroll - current_scroll) <= 1.0:
                self._pending_playback_center_lock = False
                self.set_playback_center_lock(True)
                self.set_playhead(sec, preserve_center_lock=True)
                return
            self._pending_playback_center_lock = True
            self._scroll_canvas_to_sec(sec, smooth=smooth, threshold_px=0.0)
            return
        self.set_playback_center_lock(True)
        self.set_playhead(sec, preserve_center_lock=True)
        self._scroll_canvas_to_sec(sec, smooth=smooth, threshold_px=0.0)

    def set_playback_center_lock(self, enabled: bool):
        enabled = bool(enabled)
        if not enabled:
            self._pending_playback_center_lock = False
        if getattr(self, "_playback_center_lock", False) == enabled:
            return
        self._playback_center_lock = enabled
        self._sync_playhead_overlay()

    def _manual_scroll_active(self) -> bool:
        return time.monotonic() < float(getattr(self, "_manual_scroll_until", 0.0) or 0.0)

    def _begin_manual_scroll(self, *, hold_sec: float = 0.9):
        self._manual_scroll_until = time.monotonic() + max(0.1, float(hold_sec or 0.9))
        self._pending_playback_center_lock = False
        self.set_playback_center_lock(False)
        if self._smooth_scroll_timer.isActive():
            self._smooth_scroll_timer.stop()
        current = float(self.scroll.horizontalScrollBar().value())
        self._target_scroll_x = current
        self._current_scroll_x = current

    def apply_manual_horizontal_scroll_delta(self, delta: int | float):
        self._begin_manual_scroll()
        sb = self.scroll.horizontalScrollBar()
        target = self._clamp_scroll_x(float(sb.value()) + float(delta or 0.0))
        sb.setValue(target)
        self._target_scroll_x = float(target)
        self._current_scroll_x = float(target)
        self._schedule_vp_sync()
        self._sync_playhead_overlay()

    def _scroll_canvas_to_sec(self, sec, *, smooth=True, threshold_px=24.0):
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return
        if self._subtitle_resize_keep_view_active():
            self._restore_subtitle_resize_view()
            return
        # _scroll_canvas_to_sec suppressed while segment edge drag is stabilizing.
        if self._segment_drag_view_freeze_active():
            self._restore_segment_drag_view()
            return
        viewport = self.scroll.viewport()
        viewport_w = viewport.width() if viewport is not None else self.scroll.width()
        target_x = max(0, int(self._scroll_x_for_sec(float(sec or 0.0))) - (max(1, viewport_w) // 2))
        target_val = float(self._clamp_scroll_x(target_x))
        current_val = float(self.scroll.horizontalScrollBar().value())
        if abs(target_val - float(getattr(self, "_target_scroll_x", current_val))) <= float(threshold_px):
            return
        self._target_scroll_x = target_val
        if smooth:
            if not self._smooth_scroll_timer.isActive():
                self._current_scroll_x = current_val
                self._smooth_scroll_timer.start()
            return
        self._smooth_scroll_timer.stop()
        self._current_scroll_x = target_val
        self.scroll.horizontalScrollBar().setValue(int(target_val))

    def _sync_playhead_overlay(self):
        overlay = getattr(self, "_playhead_overlay", None)
        if overlay is None:
            return
        viewport = self.scroll.viewport()
        try:
            rect = viewport.rect()
            if overlay.geometry() != rect:
                overlay.setGeometry(rect)
                overlay.setProperty("_timeline_overlay_raised", False)
            if not bool(overlay.property("_timeline_overlay_raised")):
                overlay.raise_()
                overlay.setProperty("_timeline_overlay_raised", True)
            overlay.set_state(
                float(getattr(self.canvas, "playhead_sec", 0.0) or 0.0),
                int(self.scroll.horizontalScrollBar().value()),
                center_locked=bool(getattr(self, "_playback_center_lock", False)),
                busy=bool(getattr(self.canvas, "playhead_busy", False)),
                shadow_sec=getattr(self.canvas, "shadow_playhead_sec", None),
            )
        except RuntimeError:
            pass

    def set_playhead_busy(self, busy: bool):
        busy = bool(busy)
        for canvas in (getattr(self, "canvas", None), getattr(self, "global_canvas", None)):
            if canvas is not None:
                setattr(canvas, "playhead_busy", busy)
                try:
                    canvas.setProperty("playhead_busy", busy)
                except Exception:
                    pass
                try:
                    canvas.update()
                except Exception:
                    pass
        self._sync_playhead_overlay()

    def set_boundary_times(self, times: list[float]):
        rows = list(times or [])
        sig = _boundary_signature(rows)
        current_sig = _boundary_signature(getattr(self.canvas, "boundary_times", []))
        if sig == getattr(self, "_boundary_times_signature", None) and sig == current_sig:
            return False
        self._boundary_times_signature = sig
        self.canvas.boundary_times = rows
        if hasattr(self.canvas, "_scan_boundary_hit_cache"):
            self.canvas._scan_boundary_hit_cache = None
        if hasattr(self.canvas, "_drag_snap_base_cache_key"):
            self.canvas._drag_snap_base_cache_key = None
            self.canvas._drag_snap_base_candidates = []
        if hasattr(self.canvas, "_render_epoch"):
            self.canvas._render_epoch = int(getattr(self.canvas, "_render_epoch", 0) or 0) + 1
        return True

    def set_scan_boundary_times(self, times: list[float]):
        rows = list(times or [])
        sig = _scan_boundary_signature(rows)
        current_sig = _scan_boundary_signature(getattr(self.canvas, "scan_boundary_times", []))
        if sig == getattr(self, "_scan_boundary_times_signature", None) and sig == current_sig:
            return False
        self._scan_boundary_times_signature = sig
        self.canvas.scan_boundary_times = rows
        if hasattr(self.canvas, "_scan_boundary_hit_cache"):
            self.canvas._scan_boundary_hit_cache = None
        if hasattr(self.canvas, "_drag_snap_base_cache_key"):
            self.canvas._drag_snap_base_cache_key = None
            self.canvas._drag_snap_base_candidates = []
        if hasattr(self.canvas, "_paint_index_cache"):
            self.canvas._paint_index_cache.pop("scan_boundaries", None)
        if hasattr(self.canvas, "_render_epoch"):
            self.canvas._render_epoch = int(getattr(self.canvas, "_render_epoch", 0) or 0) + 1
        self._update_scan_boundary_lane()
        return True

    def set_user_alignment_guides(self, times: list[float]):
        if hasattr(self.canvas, "set_user_alignment_guides"):
            return bool(self.canvas.set_user_alignment_guides(list(times or [])))
        return False

    def add_user_alignment_guides(self, times: list[float]):
        if hasattr(self.canvas, "add_user_alignment_guides"):
            return bool(self.canvas.add_user_alignment_guides(list(times or [])))
        return False

    def set_scan_boundary_markers_visible(self, visible: bool):
        visible = bool(visible)
        if bool(getattr(self.canvas, "show_scan_boundary_markers", False)) == visible:
            return False
        self.canvas.show_scan_boundary_markers = visible
        self._update_scan_boundary_lane()
        return True

    def _update_scan_boundary_lane(self):
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return
        try:
            lane_top = max(0, RULER_H + WAVE_H - 2)
            lane_bottom = min(CANVAS_H, max(lane_top + 1, SEG_TOP + 10))
            rect = QRect(0, lane_top, max(1, int(canvas.width())), max(1, lane_bottom - lane_top))
            if hasattr(canvas, "_viewport_paint_clip"):
                rect = canvas._viewport_paint_clip(rect, pad_px=96)
            if rect.isValid() and not rect.isEmpty():
                canvas.update(rect)
            else:
                canvas.update()
        except Exception:
            canvas.update()

    def _update_smooth_scroll(self):
        delta = float(self._target_scroll_x - self._current_scroll_x)
        if abs(delta) <= 1.0:
            final_x = float(self._clamp_scroll_x(self._target_scroll_x))
            self._current_scroll_x = final_x
            self.scroll.horizontalScrollBar().setValue(int(final_x))
            self._smooth_scroll_timer.stop()
            if getattr(self, "_pending_playback_center_lock", False):
                self._pending_playback_center_lock = False
                self.set_playback_center_lock(True)
            return
        self._current_scroll_x = float(self._clamp_scroll_x(self._current_scroll_x + delta * 0.42))
        self.scroll.horizontalScrollBar().setValue(int(self._current_scroll_x))

    def center_to_sec(self, sec, smooth=False):
        sec = self.snap_sec_to_frame(sec)
        if bool(getattr(self, "_fit_to_view_locked", False)):
            self._target_scroll_x = float(self.scroll.horizontalScrollBar().value())
            self._current_scroll_x = self._target_scroll_x
            self._sync_playhead_overlay()
            return
        if hasattr(self, "_subtitle_resize_keep_view_active") and self._subtitle_resize_keep_view_active():
            if hasattr(self, "_restore_subtitle_resize_view"):
                self._restore_subtitle_resize_view()
            return
        # center_to_sec suppressed while segment edge drag is stabilizing.
        if self._segment_drag_view_freeze_active():
            self._restore_segment_drag_view()
            return
        self.set_playback_center_lock(False)
        target_x = self._scroll_x_for_sec(sec)
        half_w = self.scroll.width() // 2
        target_val = int(self._clamp_scroll_x(max(0, target_x - half_w)))

        self._target_scroll_x = float(target_val)
        if smooth and abs(float(target_val) - float(self.scroll.horizontalScrollBar().value())) > 240:
            self._current_scroll_x = float(self.scroll.horizontalScrollBar().value())
            if not self._smooth_scroll_timer.isActive():
                self._smooth_scroll_timer.start()
            return
        self._smooth_scroll_timer.stop()
        self._current_scroll_x = float(target_val)
        self.scroll.horizontalScrollBar().setValue(int(target_val))

    def load_waveform(self, path: str, force: bool = False):
        if self._waveform_mode == "multi" and not force:
            return

        path = str(path or "")
        if not path or path.lower().endswith((".srt", ".vtt", ".ass", ".ssa")):
            return
        path_changed = path != str(getattr(self, "_waveform_path", "") or "")
        if path_changed or force:
            self._reset_single_media_context(clear_duration=True)
            self.canvas.set_waveform(None)
            self.global_canvas.set_waveform(None)
            self._multiclip_waveform_buffer = None

        self._waveform_path = str(path or "")

        if self._mc_worker:
            try:
                self._mc_worker.stop()
                self._mc_worker.wait(1200)
            except Exception:
                pass
            self._mc_worker = None

        if self._wf_worker:
            try:
                self._wf_worker.stop()
                self._wf_worker.wait(1200)
            except Exception:
                pass
            self._wf_worker = None

        self._wf_worker = WaveformWorker(path, self)
        self._wf_worker.ready.connect(self._on_waveform_ready)
        self._wf_worker.start()

    def load_multiclip_waveform(self, clip_boundaries):
        # Guard: skip if already loading multiclip waveform
        if self._waveform_mode == "multi" and self._mc_worker and self._mc_worker.isRunning():
            return
        self._waveform_mode = "multi"
        self._multiclip_waveform_buffer = None

        # 초기 멀티클립 로드 시 선택 컨텍스트를 항상 clip1로 고정
        _boxes = getattr(self.canvas, '_multiclip_boxes', []) or []
        if _boxes:
            self._apply_selected_clip_context(0)
            self.global_canvas.set_clip_label(str(_boxes[0].get('index', 1)))

        if self._wf_worker:
            try:
                self._wf_worker.stop()
                self._wf_worker.wait(1200)
            except Exception:
                pass
            self._wf_worker = None

        if self._mc_worker:
            try:
                self._mc_worker.stop()
                self._mc_worker.wait(1200)
            except Exception:
                pass
            self._mc_worker = None

        self._mc_worker = MultiClipWaveformWorker(clip_boundaries, self)
        self._mc_worker.clip_ready.connect(self._on_clip_waveform_ready)
        self._mc_worker.all_ready.connect(self._on_waveform_ready)
        self._mc_worker.start()

    def _on_clip_waveform_ready(self, clip_idx, start_px, total_px, partial_wf):
        if self._waveform_mode != "multi":
            return
        if self.sender() is not self._mc_worker:
            return

        if self._selected_clip_idx < 0:
            _boxes = getattr(self.canvas, '_multiclip_boxes', []) or []
            if _boxes:
                self._apply_selected_clip_context(0)

        self._multiclip_waveform_buffer = patch_waveform_buffer(
            self._multiclip_waveform_buffer,
            start_px=int(start_px or 0),
            total_px=int(total_px or 0),
            values=partial_wf,
        )
        self.canvas.set_waveform(self._multiclip_waveform_buffer)
        self.global_canvas.set_waveform(self._multiclip_waveform_buffer)
        _boxes = getattr(self.canvas, '_multiclip_boxes', []) or []
        if _boxes:
            self.global_canvas.total_duration = float(_boxes[-1].get("end", self.canvas.total_duration))
        self.global_canvas.set_clip_label(str(self._selected_clip_label or 1))
        self.global_canvas.update()

    def _on_waveform_ready(self, wf, d):
        sender = self.sender()

        if self._waveform_mode == "multi":
            if sender is not self._mc_worker:
                return

            _boxes = getattr(self.canvas, '_multiclip_boxes', []) or []
            if self._selected_clip_idx < 0 and _boxes:
                self._apply_selected_clip_context(0)

            self._multiclip_waveform_buffer = np.asarray(wf, dtype=np.float32)
            self.canvas.set_waveform(self._multiclip_waveform_buffer)
            self.global_canvas.set_waveform(self._multiclip_waveform_buffer)
            self.global_canvas.total_duration = d
            self.global_canvas.update()
            if not self._multiclip_fit_done:
                self.auto_fit_to_view()
                self._multiclip_fit_done = True
            return

        if sender is not self._wf_worker:
            return

        self._apply_single_media_duration(d)
        self.canvas.set_waveform(wf)
        self.global_canvas.set_waveform(wf)
        self.waveform_ready.emit(str(getattr(self, "_waveform_path", "") or ""), float(d or 0.0))
        self.schedule_initial_open_view(mode=None, seconds=None)

    def wheelEvent(self, ev):
        mods = ev.modifiers()

        if mods & Qt.KeyboardModifier.ControlModifier or mods & Qt.KeyboardModifier.MetaModifier:
            dy = ev.angleDelta().y()
            if dy == 0:
                ev.accept()
                return

            dur = self.canvas.total_duration
            min_pps = self._fit_pps_for_duration(dur)
            max_pps = 500.0

            factor = 1.08 if dy > 0 else 1.0 / 1.08
            new_pps = max(min_pps, min(max_pps, self.canvas.pps * factor))

            if abs(new_pps - self.canvas.pps) < 0.01:
                ev.accept()
                return

            self._begin_manual_zoom()
            self._apply_zoom(new_pps / max(0.001, float(self.canvas.pps)))
            ev.accept()
            return

        dy = ev.angleDelta().y()
        dx = ev.angleDelta().x()
        delta = -(dy if dy != 0 else dx)
        self.apply_manual_horizontal_scroll_delta(delta // 2)
        ev.accept()

    def _schedule_vp_sync(self, *args):
        if not self._vp.isActive():
            self._vp.start()

    def _sync_vp(self):
        start_frac, end_frac = self._viewport_fracs_for_selected_clip()
        self.global_canvas.update_viewport(start_frac, end_frac)
        self._sync_scenegraph_layer()

    def _on_global_seek(self, frac):
        if self.canvas.total_duration > 0:
            frac = max(0.0, min(1.0, float(frac)))
            if self._selected_clip_idx >= 0 and self._selected_clip_duration > 0:
                sec = self._selected_clip_offset + (frac * self._selected_clip_duration)
            else:
                sec = frac * self.canvas.total_duration
            sec = self.snap_sec_to_frame(sec)
            self.center_to_sec(sec, smooth=False)
            self.scrub_sec.emit(sec)

    def _on_clip_selected(self, clip_idx):
        boxes = getattr(self.canvas, "_multiclip_boxes", [])
        if clip_idx < 0 or clip_idx >= len(boxes):
            return

        self._apply_selected_clip_context(int(clip_idx))
        self.sig_clip_selected.emit(clip_idx)

    def _on_clip_global_wf_ready(self, wf, dur):
        if self._selected_clip_duration > 0:
            self.global_canvas.total_duration = self._selected_clip_duration
        else:
            self.global_canvas.total_duration = dur
        self.global_canvas.set_waveform(wf)
        _boxes = getattr(self.canvas, '_multiclip_boxes', []) or []
        _label = str(self._selected_clip_label or (_boxes[0].get('index', 1) if _boxes else ''))
        self.global_canvas.set_clip_label(_label)
        self.global_canvas.update()

    def fit_to_view(self):
        boxes = list(getattr(self.canvas, "_multiclip_boxes", []) or [])
        is_multiclip = bool(boxes)
        if is_multiclip:
            dur = max(0.0, float(boxes[-1].get("end", 0.0) or 0.0))
        else:
            dur = self._fit_content_duration()
        if dur <= 0:
            return
        self._fit_to_view_locked = True
        self._fit_after_resize_pending = False
        self._manual_zoom_since_fit = False

        new_pps = self._fit_pps_for_duration(dur)
        total_dur = max(float(getattr(self.canvas, "total_duration", 0.0) or 0.0), dur)
        target_w = self._canvas_width_for_duration(total_dur, new_pps)
        fit_start_sec = 0.0
        if not is_multiclip and self._selected_clip_idx >= 0 and self._selected_clip_duration > 0:
            fit_start_sec = max(0.0, float(self._selected_clip_offset or 0.0))

        viewport_w = max(1, int(self.scroll.viewport().width()))
        max_scroll = max(0, int(target_w) - viewport_w)
        target_scroll = max(0, min(self._scroll_x_for_sec(fit_start_sec, new_pps), max_scroll))
        self.canvas.setUpdatesEnabled(False)
        try:
            self.canvas.pps = new_pps
            if self.canvas.width() != target_w:
                self.canvas.setFixedWidth(target_w)
            self.scroll.horizontalScrollBar().setValue(target_scroll)
            self._target_scroll_x = float(target_scroll)
            self._current_scroll_x = float(target_scroll)
        finally:
            self.canvas.setUpdatesEnabled(True)
        self._refresh_canvas_playhead_cache()
        if hasattr(self.canvas, "_update_viewport_region"):
            self.canvas._update_viewport_region()
        else:
            self.canvas.update()

        if is_multiclip:
            start_frac = 0.0
            end_frac = 1.0
        elif self._selected_clip_idx >= 0 and self._selected_clip_duration > 0:
            clip_dur = max(0.001, float(self._selected_clip_duration or 0.0))
            start_frac = 0.0
            end_frac = max(start_frac, min(1.0, dur / clip_dur))
        else:
            total_for_view = max(0.001, float(getattr(self.canvas, "total_duration", 0.0) or 0.0))
            start_frac = max(0.0, min(1.0, fit_start_sec / total_for_view))
            end_frac = max(start_frac, min(1.0, (fit_start_sec + dur) / total_for_view))
        self.global_canvas.update_viewport(start_frac, end_frac)
        self.global_canvas.update()
        self._schedule_vp_sync()
        self._sync_playhead_overlay()

    def _editing_window_anchor_sec(self) -> float | None:
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return None

        active_line = getattr(canvas, "active_seg_line", None)
        if active_line is not None and hasattr(canvas, "_segment_for_line"):
            seg = canvas._segment_for_line(int(active_line))
            if isinstance(seg, dict):
                try:
                    start = float(seg.get("start", 0.0) or 0.0)
                    end = float(seg.get("end", start) or start)
                    if end > start:
                        return (start + end) / 2.0
                except Exception:
                    pass

        active_start = getattr(canvas, "active_seg_start", None)
        if active_start is not None and hasattr(canvas, "_active_segment_candidates"):
            try:
                candidates = canvas._active_segment_candidates()
            except Exception:
                candidates = []
            for seg in list(candidates or []):
                if not isinstance(seg, dict) or bool(seg.get("is_gap")):
                    continue
                try:
                    start = float(seg.get("start", 0.0) or 0.0)
                    end = float(seg.get("end", start) or start)
                    if end > start:
                        return (start + end) / 2.0
                except Exception:
                    continue
            try:
                return float(active_start)
            except Exception:
                pass

        try:
            playhead = float(getattr(canvas, "playhead_sec", 0.0) or 0.0)
        except Exception:
            playhead = 0.0
        return max(0.0, playhead)

    def show_time_window_seconds(
        self,
        seconds: float = 15.0,
        *,
        center_sec: float | None = None,
        start_sec: float | None = None,
    ) -> None:
        """Show a compact time window for newly opened subtitle/project files."""
        total_dur = max(0.0, float(getattr(self.canvas, "total_duration", 0.0) or 0.0), self._fit_content_duration())
        try:
            window_sec = max(1.0, float(seconds or 15.0))
        except Exception:
            window_sec = 15.0
        if total_dur <= 0.0:
            return
        visible_sec = min(window_sec, max(0.001, total_dur))
        visible_w = max(1, self._fit_reference_width())
        new_pps = max(0.001, min(500.0, float(visible_w) / max(0.001, visible_sec)))
        target_w = self._canvas_width_for_duration(total_dur, new_pps)
        viewport_w = max(1, int(self.scroll.viewport().width()))
        max_scroll = max(0, int(target_w) - viewport_w)

        if center_sec is not None:
            try:
                anchor = max(0.0, min(total_dur, float(center_sec or 0.0)))
            except Exception:
                anchor = 0.0
            view_start_sec = anchor - (visible_sec / 2.0)
        elif start_sec is not None:
            try:
                view_start_sec = float(start_sec or 0.0)
            except Exception:
                view_start_sec = 0.0
        elif self._selected_clip_idx >= 0 and self._selected_clip_duration > 0:
            view_start_sec = max(0.0, float(self._selected_clip_offset or 0.0))
        else:
            view_start_sec = 0.0
        view_start_sec = max(0.0, min(view_start_sec, max(0.0, total_dur - visible_sec)))
        target_scroll = max(0, min(self._scroll_x_for_sec(view_start_sec, new_pps), max_scroll))

        self._fit_to_view_locked = False
        self._fit_after_resize_pending = False
        self._manual_zoom_since_fit = False
        self.canvas.setUpdatesEnabled(False)
        try:
            self.canvas.pps = new_pps
            if self.canvas.width() != target_w:
                self.canvas.setFixedWidth(target_w)
            self.scroll.horizontalScrollBar().setValue(target_scroll)
            self._target_scroll_x = float(target_scroll)
            self._current_scroll_x = float(target_scroll)
        finally:
            self.canvas.setUpdatesEnabled(True)
        self._refresh_canvas_playhead_cache()

        total_for_view = max(0.001, float(getattr(self.canvas, "total_duration", 0.0) or total_dur))
        start_frac = max(0.0, min(1.0, view_start_sec / total_for_view))
        end_frac = max(start_frac, min(1.0, (view_start_sec + visible_sec) / total_for_view))
        self.global_canvas.update_viewport(start_frac, end_frac)
        self.global_canvas.update()
        if hasattr(self.canvas, "_update_viewport_region"):
            self.canvas._update_viewport_region()
        else:
            self.canvas.update()
        self._schedule_vp_sync()
        self._sync_playhead_overlay()

    def show_ten_second_edit_window(self) -> None:
        anchor_sec = self._editing_window_anchor_sec()
        self._apply_edit_window_seconds(self._preferred_edit_window_seconds, center_sec=anchor_sec)

    def preferred_edit_window_seconds(self) -> float:
        try:
            value = float(getattr(self, "_preferred_edit_window_seconds", 10.0) or 10.0)
        except Exception:
            value = 10.0
        return max(1.0, min(600.0, value))

    def _load_preferred_edit_window_seconds(self) -> float:
        try:
            settings = dict(load_settings() or {})
            value = float(settings.get(self.EDIT_WINDOW_SETTINGS_KEY, 10.0) or 10.0)
        except Exception:
            value = 10.0
        return max(1.0, min(600.0, value))

    def _save_preferred_edit_window_seconds(self, seconds: float) -> None:
        try:
            normalized = max(1.0, min(600.0, float(seconds or 10.0)))
        except Exception:
            normalized = 10.0
        rounded_value = int(round(normalized))
        self._preferred_edit_window_seconds = float(rounded_value)
        self._refresh_time_window_button_tooltip()
        try:
            settings = dict(load_settings() or {})
            settings[self.EDIT_WINDOW_SETTINGS_KEY] = rounded_value
            save_settings(settings)
        except Exception:
            pass

    def _refresh_time_window_button_tooltip(self) -> None:
        button = getattr(self, "time_window_btn", None)
        if button is None:
            return
        seconds = int(round(float(getattr(self, "_preferred_edit_window_seconds", 10.0) or 10.0)))
        button.setToolTip(f"캔버스 {seconds}초 편집 창\n우클릭: 현재 시간창 조정")

    def schedule_initial_open_view(
        self,
        delays: tuple[int, ...] | None = None,
        *,
        mode: str | None = "window",
        seconds: float | None = 10.0,
        start_sec: float | None = 0.0,
    ) -> None:
        existing_request = dict(getattr(self, "_initial_open_view_request", None) or {})
        normalized_mode = str(mode or existing_request.get("mode") or "window").strip().lower()
        if normalized_mode == "fit":
            request = {"mode": "fit"}
        elif mode is None and seconds is None:
            request = dict(existing_request)
            if not request:
                return
        else:
            try:
                window_seconds = max(1.0, float(seconds or 10.0))
            except Exception:
                window_seconds = 10.0
            try:
                window_start_sec = max(0.0, float(start_sec or 0.0))
            except Exception:
                window_start_sec = 0.0
            request = {
                "mode": "window",
                "seconds": window_seconds,
                "start_sec": window_start_sec,
            }

        effective_delays = tuple(
            int(delay)
            for delay in (
                delays
                if delays is not None
                else request.get("delays")
                or (0, 120, 280)
            )
        )
        if not effective_delays:
            effective_delays = (0,)
        request["delays"] = effective_delays
        self._initial_open_view_request = dict(request)
        token = object()
        self._initial_open_view_token = token

        def _apply_request(snapshot: dict[str, object]) -> None:
            if getattr(self, "_initial_open_view_token", None) is not token:
                return
            if bool(getattr(self, "_shutdown_in_progress", False)):
                return
            if bool(getattr(self, "_manual_zoom_since_fit", False)):
                return
            try:
                if str(snapshot.get("mode") or "window").strip().lower() == "fit":
                    self.fit_to_view()
                else:
                    self.show_time_window_seconds(
                        float(snapshot.get("seconds", 10.0) or 10.0),
                        start_sec=float(snapshot.get("start_sec", 0.0) or 0.0),
                    )
            except RuntimeError:
                return

        for delay in effective_delays:
            QTimer.singleShot(int(delay), lambda snapshot=dict(request): _apply_request(snapshot))

    def schedule_time_window_seconds(
        self,
        seconds: float = 15.0,
        *,
        center_sec: float | None = None,
        start_sec: float | None = None,
        delays: tuple[int, ...] = (0, 120, 280),
    ) -> None:
        def _apply_window(s: float, c: float | None, st: float | None) -> None:
            if bool(getattr(self, "_shutdown_in_progress", False)):
                return
            if bool(getattr(self, "_manual_zoom_since_fit", False)):
                return
            try:
                self.show_time_window_seconds(s, center_sec=c, start_sec=st)
            except RuntimeError:
                return

        for delay in delays:
            QTimer.singleShot(
                int(delay),
                lambda s=seconds, c=center_sec, st=start_sec: _apply_window(s, c, st),
            )

    def zoom_in(self):
        self._zoom_canvas(1.15)

    def zoom_out(self):
        self._zoom_canvas(1 / 1.15)

    def zoom_to_max(self):
        self._begin_manual_zoom()
        current_pps = max(0.001, float(getattr(self.canvas, "pps", 1.0) or 1.0))
        self._apply_zoom(500.0 / current_pps)

    def _zoom_canvas(self, factor: float):
        self._begin_manual_zoom()
        self._apply_zoom(factor)

    def _begin_manual_zoom(self) -> None:
        self._fit_to_view_locked = False
        self._fit_after_resize_pending = False
        self._manual_zoom_since_fit = True
        self._begin_manual_scroll(hold_sec=1.2)

    def auto_fit_to_view(self) -> bool:
        if bool(getattr(self, "_manual_zoom_since_fit", False)):
            return False
        self.fit_to_view()
        return True

    def schedule_fit_to_view(self, delays: tuple[int, ...] = (0, 80, 180)) -> None:
        if bool(getattr(self, "_manual_zoom_since_fit", False)):
            return
        if self._fit_after_resize_pending:
            return
        self._fit_after_resize_pending = True

        def _run_final_fit():
            self._fit_after_resize_pending = False
            if bool(getattr(self, "_manual_zoom_since_fit", False)):
                return
            self.fit_to_view()

        for delay in delays[:-1]:
            QTimer.singleShot(int(delay), lambda: None if bool(getattr(self, "_manual_zoom_since_fit", False)) else self.fit_to_view())
        QTimer.singleShot(int(delays[-1] if delays else 0), _run_final_fit)
