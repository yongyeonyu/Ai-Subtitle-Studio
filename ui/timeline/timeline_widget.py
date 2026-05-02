# Version: 03.06.17
# Phase: PHASE1-C
"""
ui/timeline_widget.py
Timeline widget container
"""
from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.timeline.timeline_constants import CANVAS_H, FOCUS_BORDER_COLOR, FOCUS_BORDER_WIDTH
from ui.timeline.timeline_canvas import TimelineCanvas
from ui.timeline.timeline_global import GlobalCanvas
from ui.timeline.timeline_waveform import WaveformWorker, MultiClipWaveformWorker
from ui.style import button_style
from core.frame_time import normalize_fps, snap_sec_to_frame


class TimelinePlayheadOverlay(QWidget):
    """Paint the moving playhead without invalidating the heavy timeline body."""

    def __init__(self, timeline, parent=None):
        super().__init__(parent)
        self._timeline = timeline
        self._sec = 0.0
        self._scroll_x = 0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

    def set_state(self, sec: float, scroll_x: int):
        self._sec = max(0.0, float(sec or 0.0))
        self._scroll_x = max(0, int(scroll_x or 0))
        self.update()

    def paintEvent(self, event):
        timeline = self._timeline
        canvas = getattr(timeline, "canvas", None)
        if canvas is None or float(getattr(canvas, "total_duration", 0.0) or 0.0) <= 0:
            return
        px = int(self._sec * float(getattr(canvas, "pps", 1.0) or 1.0)) - self._scroll_x
        if px < -16 or px > self.width() + 16:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        color = QColor("#4AFF80") if getattr(canvas, "focus_mode", "segment") == "waveform" else QColor("#FF4444")
        painter.setPen(QPen(color, 2))
        painter.drawLine(px, 0, px, self.height())
        handle_r = 7
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QBrush(QColor("#FFCC00")))
        painter.setPen(QPen(QColor("#FFFFFF"), 1))
        painter.drawEllipse(px - handle_r, 2, handle_r * 2, handle_r * 2)
        painter.end()


class TimelineWidget(QWidget):
    seg_clicked = pyqtSignal(int, float)
    seg_right_clicked = pyqtSignal(float, QPoint)
    seg_double_clicked = pyqtSignal(int, float)
    seg_time_changed = pyqtSignal(int, float, float, str)
    diamond_merge = pyqtSignal(int, int)
    sig_smart_split = pyqtSignal(int, float, bool)
    seg_to_gap = pyqtSignal(int)
    gap_activated = pyqtSignal(float, float)
    gap_to_segs = pyqtSignal(float, float)
    gap_generate_requested = pyqtSignal(float, float, float, str)
    scrub_sec = pyqtSignal(float)
    drag_started = pyqtSignal()
    drag_finished = pyqtSignal()
    step_frame = pyqtSignal(int)
    sig_inline_text_changed = pyqtSignal(int, str)
    sig_editing_mode = pyqtSignal(bool)
    playhead_menu_requested = pyqtSignal(QPoint, float)
    sig_clip_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMinimumHeight(CANVAS_H + 55)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 1)
        lay.setSpacing(1)

        self.lock_chk = QCheckBox("Lock Edit")
        self.lock_chk.setStyleSheet(
            """
            QCheckBox {
                color: #FFFF00;
                font-size: 12px;
                font-weight: bold;
                background: transparent;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1.5px solid #FFFF00;
                background: transparent;
                border-radius: 2px;
            }
            QCheckBox::indicator:checked {
                background: #FFFF00;
                border: 1.5px solid #FFFF00;
            }
            """
        )

        lock_row = QHBoxLayout()
        lock_row.setContentsMargins(0, 0, 0, 0)
        lock_row.addWidget(self.lock_chk)
        lock_row.addStretch()
        for text, tip, slot in (
            ("+", "캔버스 확대", self.zoom_in),
            ("-", "캔버스 축소", self.zoom_out),
            ("ㅁ", "캔버스 화면 너비에 맞춤", self.fit_to_view),
        ):
            btn = QPushButton(text)
            btn.setFixedSize(28, 24)
            btn.setToolTip(tip)
            btn.setStyleSheet(button_style("toolbar", font_size="11px", padding="2px 6px"))
            btn.clicked.connect(slot)
            lock_row.addWidget(btn)
        lay.addLayout(lock_row)

        self.canvas = TimelineCanvas()

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(False)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(CANVAS_H + 16)
        self.scroll.setStyleSheet("QScrollArea{border:none;}")

        lay.addWidget(self.scroll)
        self._playhead_overlay = self._create_playhead_overlay()
        self._playhead_overlay.setGeometry(self.scroll.viewport().rect())
        self._playhead_overlay.raise_()
        self.canvas._external_playhead_overlay = True

        self.global_canvas = GlobalCanvas()
        lay.addWidget(self.global_canvas)

        self.canvas.installEventFilter(self)
        self.global_canvas.installEventFilter(self)
        self.scroll.installEventFilter(self)
        self.lock_chk.installEventFilter(self)

        self.canvas.seg_clicked.connect(self.seg_clicked)
        self.canvas.seg_right_clicked.connect(self._on_canvas_right_clicked)
        self.canvas.seg_double_clicked.connect(self.seg_double_clicked)
        self.canvas.seg_time_changed.connect(self.seg_time_changed)
        self.canvas.seg_to_gap.connect(self.seg_to_gap)
        self.canvas.gap_activated.connect(self.gap_activated)
        self.canvas.gap_to_segs.connect(self.gap_to_segs)
        self.canvas.gap_generate_requested.connect(self.gap_generate_requested.emit)
        self.canvas.scrub_sec.connect(self.scrub_sec)
        self.canvas.drag_started.connect(self.drag_started)
        self.canvas.drag_finished.connect(self.drag_finished)
        self.canvas.sig_clip_selected.connect(self._on_clip_selected)
        self.canvas.sig_inline_text_changed.connect(self.sig_inline_text_changed.emit)
        self.canvas.sig_editing_mode.connect(self.sig_editing_mode.emit)
        self.canvas.playhead_menu_requested.connect(self.playhead_menu_requested.emit)
        self.canvas.diamond_merge.connect(self.diamond_merge)
        self.canvas.sig_smart_split.connect(self.sig_smart_split)
        self.canvas.step_frame.connect(self.step_frame)

        self.global_canvas.seek_frac.connect(self._on_global_seek)

        self._wf_worker = None
        self._mc_worker = None
        self._waveform_mode = "single"
        self._selected_clip_idx = -1
        self._selected_clip_offset = 0.0
        self._selected_clip_duration = 0.0
        self._selected_clip_label = ""
        self._multiclip_fit_done = False

        self._vp = QTimer(self)
        self._vp.setSingleShot(True)
        self._vp.setInterval(0)
        self._vp.timeout.connect(self._sync_vp)
        self.scroll.horizontalScrollBar().valueChanged.connect(self._schedule_vp_sync)
        self.scroll.horizontalScrollBar().valueChanged.connect(lambda *_: self._sync_playhead_overlay())

        self._target_scroll_x = 0.0
        self._current_scroll_x = 0.0

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
        self._sync_focus_border()

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

    def closeEvent(self, event):
        self.stop_waveform_workers()
        super().closeEvent(event)

    def set_frame_rate(self, fps: float):
        fps = normalize_fps(fps)
        self.video_fps = fps
        if hasattr(self, "canvas"):
            self.canvas.set_frame_rate(fps)
        if hasattr(self, "global_canvas"):
            setattr(self.global_canvas, "frame_rate", fps)

    def snap_sec_to_frame(self, sec: float) -> float:
        return snap_sec_to_frame(sec, getattr(self, "video_fps", getattr(self.canvas, "frame_rate", 30.0)))

    def _create_playhead_overlay(self):
        # QQuickWidget transparency can cover the QWidget viewport with black on macOS.
        # Keep the playhead separated, but use a native transparent QWidget overlay here.
        return TimelinePlayheadOverlay(self, self.scroll.viewport())

    def _canvas_width_for_duration(self, dur: float, pps: float | None = None) -> int:
        pps = float(self.canvas.pps if pps is None else pps)
        end_padding = 96
        return max(int(float(dur) * pps) + end_padding, self.scroll.width())

    def _fit_pps_for_duration(self, dur: float) -> float:
        if dur <= 0:
            return float(self.canvas.pps)
        visible_w = max(1, self.scroll.viewport().width() - 20)
        return max(0.001, min(500.0, visible_w / max(0.001, float(dur))))

    def _clamp_scroll_x(self, value: float) -> int:
        sb = self.scroll.horizontalScrollBar()
        return max(0, min(int(value), sb.maximum()))

    def _playhead_zoom_anchor(self, old_pps: float) -> tuple[float, float]:
        dur = max(0.0, float(getattr(self.canvas, "total_duration", 0.0) or 0.0))
        playhead_sec = self.snap_sec_to_frame(max(0.0, min(dur, float(getattr(self.canvas, "playhead_sec", 0.0) or 0.0))))
        viewport_w = max(1, self.scroll.viewport().width())
        current_scroll = float(self.scroll.horizontalScrollBar().value())
        playhead_view_x = (playhead_sec * max(0.001, old_pps)) - current_scroll
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

        self.canvas.pps = new_pps
        target_w = self._canvas_width_for_duration(dur, new_pps)
        if self.canvas.width() != target_w:
            self.canvas.setFixedWidth(target_w)
        self.canvas.update()
        self._sync_playhead_overlay()

        new_scroll = int(float(anchor_sec) * new_pps - float(anchor_view_x))
        new_scroll = self._clamp_scroll_x(new_scroll)
        sb = self.scroll.horizontalScrollBar()
        sb.setValue(new_scroll)
        self._target_scroll_x = float(new_scroll)
        self._current_scroll_x = float(new_scroll)
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
        )

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
        self._sync_focus_border()
        self._sync_playhead_overlay()
        self._schedule_vp_sync()

    def paintEvent(self, ev):
        super().paintEvent(ev)
        self._sync_focus_border()
        if self._has_timeline_focus():
            from PyQt6.QtGui import QColor, QPainter, QPen

            painter = QPainter(self)
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
        dur = max(0.001, float(getattr(self.canvas, "total_duration", 0.0)))
        if dur <= 0:
            return 0.0, 1.0

        sb = self.scroll.horizontalScrollBar()
        view_w = self.scroll.viewport().width() if self.scroll.viewport() else self.scroll.width()
        global_start = float(sb.value()) / max(0.001, float(self.canvas.pps))
        global_end = float(sb.value() + view_w) / max(0.001, float(self.canvas.pps))

        return max(0.0, min(1.0, global_start / dur)), max(0.0, min(1.0, global_end / dur))

    def update_segments(self, segs, active_sec=None, total_dur=0.0, fit_view=False):
        seg_end = segs[-1]["end"] if segs else 0.0
        prev_dur = getattr(self.canvas, "total_duration", 0.0)
        dur = max(prev_dur, total_dur or 0.0, seg_end)

        target_w = self._canvas_width_for_duration(dur)
        if self.canvas.width() != target_w:
            self.canvas.setFixedWidth(target_w)
        self.canvas.update_segments(segs, active_sec, dur)
        self.global_canvas.update_segments(segs, dur)

        if fit_view:
            self.fit_to_view()
        elif self._waveform_mode == "multi":
            # 멀티클립에서는 현재 줌(pps) 유지. 최초 전체 로드에서만 fit_to_view 허용.
            pass

    def set_vad_segments(self, vad_segs: list):
        self.canvas.set_vad_segments(vad_segs)
        self.global_canvas.set_vad_segments(vad_segs)

    def set_active(self, sec):
        sec = self.snap_sec_to_frame(sec)
        self.canvas.set_active(sec)
        if sec is not None:
            self.center_to_sec(sec, smooth=True)

    def set_playhead(self, sec):
        sec = self.snap_sec_to_frame(sec)
        self.canvas.playhead_sec = max(0.0, float(sec or 0.0))
        self._sync_playhead_overlay()
        self.global_canvas.set_playhead(sec)

    def follow_playhead(self, sec, *, smooth=True, threshold_px=24.0):
        sec = self.snap_sec_to_frame(sec)
        self.set_playhead(sec)
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return
        viewport = self.scroll.viewport()
        viewport_w = viewport.width() if viewport is not None else self.scroll.width()
        target_x = max(0, int(float(sec or 0.0) * float(canvas.pps or 0.0)) - (max(1, viewport_w) // 2))
        target_val = float(self._clamp_scroll_x(target_x))
        current_val = float(self.scroll.horizontalScrollBar().value())
        if abs(target_val - float(getattr(self, "_target_scroll_x", current_val))) < float(threshold_px):
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
            overlay.setGeometry(viewport.rect())
            overlay.raise_()
            overlay.set_state(
                float(getattr(self.canvas, "playhead_sec", 0.0) or 0.0),
                int(self.scroll.horizontalScrollBar().value()),
            )
        except RuntimeError:
            pass

    def set_boundary_times(self, times: list[float]):
        self.canvas.boundary_times = times or []
        self.canvas.update()

    def _update_smooth_scroll(self):
        delta = float(self._target_scroll_x - self._current_scroll_x)
        if abs(delta) <= 1.0:
            final_x = float(self._clamp_scroll_x(self._target_scroll_x))
            self._current_scroll_x = final_x
            self.scroll.horizontalScrollBar().setValue(int(final_x))
            self._smooth_scroll_timer.stop()
            return
        self._current_scroll_x = float(self._clamp_scroll_x(self._current_scroll_x + delta * 0.42))
        self.scroll.horizontalScrollBar().setValue(int(self._current_scroll_x))

    def center_to_sec(self, sec, smooth=False):
        sec = self.snap_sec_to_frame(sec)
        target_x = int(sec * self.canvas.pps)
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

        self._waveform_mode = "single"

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

    def _on_clip_waveform_ready(self, clip_idx, partial_wf):
        if self._waveform_mode != "multi":
            return
        if self.sender() is not self._mc_worker:
            return

        if self._selected_clip_idx < 0:
            _boxes = getattr(self.canvas, '_multiclip_boxes', []) or []
            if _boxes:
                self._apply_selected_clip_context(0)

        self.canvas.set_waveform(partial_wf)
        self.global_canvas.set_waveform(partial_wf)
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

            self.canvas.set_waveform(wf)
            self.global_canvas.set_waveform(wf)
            self.global_canvas.total_duration = d
            self.global_canvas.update()
            if not self._multiclip_fit_done:
                self.fit_to_view()
                self._multiclip_fit_done = True
            return

        if sender is not self._wf_worker:
            return

        self.canvas.set_waveform(wf)
        self.global_canvas.set_waveform(wf)
        self.global_canvas.total_duration = d

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

            self._apply_zoom(new_pps / max(0.001, float(self.canvas.pps)))
            ev.accept()
            return

        dy = ev.angleDelta().y()
        dx = ev.angleDelta().x()
        delta = -(dy if dy != 0 else dx)
        self.scroll.horizontalScrollBar().setValue(
            self.scroll.horizontalScrollBar().value() + delta // 2
        )
        self._schedule_vp_sync()
        self._sync_playhead_overlay()
        ev.accept()

    def _schedule_vp_sync(self, *args):
        if not self._vp.isActive():
            self._vp.start()

    def _sync_vp(self):
        start_frac, end_frac = self._viewport_fracs_for_selected_clip()
        self.global_canvas.update_viewport(start_frac, end_frac)

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

        box = boxes[clip_idx]
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
        dur = self.canvas.total_duration
        if dur <= 0:
            return

        new_pps = self._fit_pps_for_duration(dur)
        self.canvas.pps = new_pps

        target_w = self._canvas_width_for_duration(dur, new_pps)
        if self.canvas.width() != target_w:
            self.canvas.setFixedWidth(target_w)
        self.canvas.update()

        self.scroll.horizontalScrollBar().setValue(0)
        self._target_scroll_x = 0.0
        self._current_scroll_x = 0.0
        self.global_canvas.update_viewport(0.0, 1.0)
        self.global_canvas.update()

    def zoom_in(self):
        self._zoom_canvas(1.15)

    def zoom_out(self):
        self._zoom_canvas(1 / 1.15)

    def _zoom_canvas(self, factor: float):
        self._apply_zoom(factor)
