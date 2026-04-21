# Version: 01.00.02
"""
ui/timeline_widget.py
타임라인 위젯의 최종 조립을 담당하는 껍데기 파일
[v01.00.02] set_boundary_times 추가 (멀티 영상 경계선)
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QHBoxLayout, QScrollArea, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint

from ui.timeline_constants import CANVAS_H
from ui.timeline_canvas import TimelineCanvas
from ui.timeline_global import GlobalCanvas
from ui.timeline_waveform import WaveformWorker, MultiClipWaveformWorker

class TimelineWidget(QWidget):
    seg_clicked             = pyqtSignal(int, float)
    seg_right_clicked       = pyqtSignal(float, QPoint)
    seg_double_clicked      = pyqtSignal(int, float)
    seg_time_changed        = pyqtSignal(int, float, float, str)
    diamond_merge           = pyqtSignal(int, int)       # ✅ [#9]
    sig_smart_split         = pyqtSignal(int, float, bool)  # ✅ [#6, #10]
    seg_to_gap              = pyqtSignal(int)
    gap_activated           = pyqtSignal(float, float)
    gap_to_segs             = pyqtSignal(float, float)
    scrub_sec               = pyqtSignal(float)
    drag_started            = pyqtSignal()
    drag_finished           = pyqtSignal()
    step_frame              = pyqtSignal(int)
    sig_inline_text_changed = pyqtSignal(int, str)
    sig_editing_mode        = pyqtSignal(bool)
    playhead_menu_requested = pyqtSignal(QPoint, float)
    sig_clip_selected       = pyqtSignal(int)   # ← 추가
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(CANVAS_H + 55)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True) 

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 1)
        lay.setSpacing(1)

        self.lock_chk = QCheckBox("편집 고정")
        self.lock_chk.setStyleSheet("""
            QCheckBox { color: #FFFF00; font-size: 12px; font-weight: bold; background: transparent; }
            QCheckBox::indicator { width: 14px; height: 14px; border: 1.5px solid #FFFF00; background: transparent; border-radius: 2px; }
            QCheckBox::indicator:checked { background: #FFFF00; border: 1.5px solid #FFFF00; }
        """)
        lock_row = QHBoxLayout()
        lock_row.setContentsMargins(0, 0, 0, 0)
        lock_row.addWidget(self.lock_chk)
        lock_row.addStretch()
        lay.addLayout(lock_row)

        self.canvas = TimelineCanvas()
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(False)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(CANVAS_H + 16)
        self.scroll.setStyleSheet("QScrollArea{border:none;}")

        self._vp = QTimer(); self._vp.setInterval(16)
        self._vp.timeout.connect(self._sync_vp); self._vp.start()

        lay.addWidget(self.scroll)
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
        self.canvas.scrub_sec.connect(self.scrub_sec)
        self.canvas.drag_started.connect(self.drag_started)
        self.canvas.drag_finished.connect(self.drag_finished)
        self.canvas.sig_clip_selected.connect(self._on_clip_selected)
        self.canvas.sig_inline_text_changed.connect(self.sig_inline_text_changed.emit)
        self.canvas.sig_editing_mode.connect(self.sig_editing_mode.emit)
        self.canvas.playhead_menu_requested.connect(self.playhead_menu_requested.emit)
        
        # 기존 canvas 시그널 포워딩들 근처에 추가
        self.canvas.diamond_merge.connect(self.diamond_merge)
        self.canvas.sig_smart_split.connect(self.sig_smart_split)

        self.global_canvas.seek_frac.connect(self._on_global_seek)
        self._wf_worker = None
        self.canvas.step_frame.connect(self.step_frame) 

        self._target_scroll_x = 0.0
        self._current_scroll_x = 0.0
        self._smooth_scroll_timer = QTimer(self)
        self._smooth_scroll_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._smooth_scroll_timer.setInterval(10) 
        self._smooth_scroll_timer.timeout.connect(self._update_smooth_scroll)
        self._smooth_scroll_timer.start()

    def _on_canvas_right_clicked(self, start_sec, gpos):
        if hasattr(self, 'seg_right_clicked'):
            self.seg_right_clicked.emit(start_sec, gpos)

    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent
        if ev.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self.update()
        return super().eventFilter(obj, ev)
        
    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self.hasFocus() or self.canvas.hasFocus() or self.global_canvas.hasFocus() or self.scroll.hasFocus():
            from PyQt6.QtGui import QPainter, QPen, QColor
            p = QPainter(self)
            p.setPen(QPen(QColor("#FFFF00"), 2))
            p.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def update_segments(self, segs, active_sec=None, total_dur=0.0):
        dur = total_dur or (segs[-1]["end"] if segs else 0.0)
        tw = int(dur * self.canvas.pps) + self.scroll.width()
        self.canvas.setFixedWidth(max(tw, self.scroll.width()))
        self.canvas.update_segments(segs, active_sec, dur)
        self.global_canvas.update_segments(segs, dur) 

    def set_vad_segments(self, vad_segs: list):
        self.canvas.set_vad_segments(vad_segs)
        self.global_canvas.set_vad_segments(vad_segs)

    def set_active(self, sec):
        self.canvas.set_active(sec)
        if sec is not None:
            self.center_to_sec(sec, smooth=True)

    def set_playhead(self, sec):
        self.canvas.set_playhead(sec); self.global_canvas.set_playhead(sec)

    # 🆕 멀티 영상 경계 시간 설정
    def set_boundary_times(self, times: list[float]):
        """멀티 영상 경계 시간 설정 — 타임라인에 초록색 세로선 표시"""
        self.canvas.boundary_times = times or []
        self.canvas.update()

    def _update_smooth_scroll(self):
        if abs(self._target_scroll_x - self._current_scroll_x) > 0.5:
            self._current_scroll_x += (self._target_scroll_x - self._current_scroll_x) * 0.15
            self.scroll.horizontalScrollBar().setValue(int(self._current_scroll_x))

    def center_to_sec(self, sec, smooth=False):
        tx = int(sec * self.canvas.pps)
        hw = self.scroll.width() // 2
        target_val = max(0, tx - hw)
        
        if smooth:
            self._target_scroll_x = float(target_val) 
        else:
            self._target_scroll_x = float(target_val)
            self._current_scroll_x = float(target_val)
            self.scroll.horizontalScrollBar().setValue(target_val)

    def load_waveform(self, path: str):
        if self._wf_worker: self._wf_worker.quit()
        self._wf_worker = WaveformWorker(path, self)
        self._wf_worker.ready.connect(self._on_waveform_ready)
        self._wf_worker.start()

    def load_multiclip_waveform(self, clip_boundaries):
        """멀티클립: 클립별 부분 파형을 순차 로드하여 합성"""
        if self._wf_worker:
            self._wf_worker.quit()
        self._mc_worker = MultiClipWaveformWorker(clip_boundaries, self)
        self._mc_worker.clip_ready.connect(self._on_clip_waveform_ready)
        self._mc_worker.all_ready.connect(self._on_waveform_ready)
        self._mc_worker.start()

    def _on_clip_waveform_ready(self, clip_idx, partial_wf):
        """클립 하나 완료 → 즉시 파형 갱신 (줌/크기 유지)"""
        self.canvas.set_waveform(partial_wf)
        self.global_canvas.set_waveform(partial_wf)
        # duration만 갱신, pps/줌은 건드리지 않음
        if hasattr(self, '_mc_worker') and self._mc_worker._clips:
            total_dur = self._mc_worker._clips[-1]["end"]
            self.global_canvas.total_duration = total_dur
            if self.canvas.total_duration < total_dur:
                self.canvas.total_duration = total_dur
            self.global_canvas.update()

    def _on_waveform_ready(self, wf, d):
        self.canvas.set_waveform(wf)
        self.global_canvas.set_waveform(wf)
        # 멀티클립일 때는 duration/pps 건드리지 않음
        if not getattr(self, '_mc_worker', None):
            self.global_canvas.total_duration = d

    def wheelEvent(self, ev):
        mods = ev.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier or mods & Qt.KeyboardModifier.MetaModifier:
            dy = ev.angleDelta().y()
            if dy == 0:
                ev.accept()
                return

            dur = self.canvas.total_duration
            min_pps = 5.0
            if dur > 0:
                min_pps = (self.scroll.width() - 20) / dur
            max_pps = 500.0

            # ✅ 부드러운 확대: 1.08배 (기존 1.2배 → 점프감 제거)
            factor = 1.08 if dy > 0 else 1.0 / 1.08
            new_pps = max(min_pps, min(max_pps, self.canvas.pps * factor))

            if abs(new_pps - self.canvas.pps) < 0.01:
                ev.accept()
                return

            # ✅ 마우스 커서 위치 기준 줌 (커서 아래의 시간이 고정됨)
            mouse_x = ev.position().x()
            sb = self.scroll.horizontalScrollBar()
            old_scroll = sb.value()
            # 마우스 커서가 가리키는 시간(초)
            sec_at_cursor = (old_scroll + mouse_x) / self.canvas.pps

            old_pps = self.canvas.pps
            self.canvas.pps = new_pps

            tw = int(dur * new_pps) + self.scroll.width()
            self.canvas.setFixedWidth(max(tw, self.scroll.width()))
            self.canvas.update()

            # ✅ 줌 후에도 같은 시간이 마우스 커서 아래에 오도록 스크롤 보정
            new_scroll = int(sec_at_cursor * new_pps - mouse_x)
            new_scroll = max(0, min(new_scroll, sb.maximum()))
            sb.setValue(new_scroll)
            self._target_scroll_x = float(new_scroll)
            self._current_scroll_x = float(new_scroll)

            ev.accept()
            return

        dy, dx = ev.angleDelta().y(), ev.angleDelta().x()
        delta = -(dy if dy != 0 else dx)
        self.scroll.horizontalScrollBar().setValue(
            self.scroll.horizontalScrollBar().value() + delta // 2
        )
        ev.accept()

    def _sync_vp(self):
        sb = self.scroll.horizontalScrollBar()
        sw = max(1, self.scroll.width())
        dur = self.canvas.total_duration
        if dur > 0:
            s_frac = (sb.value() / self.canvas.pps) / dur
            e_frac = ((sb.value() + sw) / self.canvas.pps) / dur
            self.global_canvas.update_viewport(s_frac, e_frac)

    def _on_global_seek(self, frac):
        if self.canvas.total_duration > 0:
            sec = frac * self.canvas.total_duration
            self.center_to_sec(sec, smooth=False) 
            self.scrub_sec.emit(sec)

    def _on_clip_selected(self, clip_idx):
        """클립 선택 → 글로벌 캔버스 해당 클립 파형으로 전환"""
        boxes = getattr(self.canvas, '_multiclip_boxes', [])
        if clip_idx < 0 or clip_idx >= len(boxes):
            return

        box = boxes[clip_idx]
        clip_file = box.get("file", "")

        # 글로벌 캔버스를 해당 클립 파형으로 전환
        if clip_file:
            if self._wf_worker:
                self._wf_worker.quit()
            self._wf_worker = WaveformWorker(clip_file, self)
            self._wf_worker.ready.connect(self._on_clip_global_wf_ready)
            self._wf_worker.start()

        # 시그널 전달 (에디터에서 비디오 전환용)
        self.sig_clip_selected.emit(clip_idx)

    def _on_clip_global_wf_ready(self, wf, dur):
        self.global_canvas.set_waveform(wf)
        self.global_canvas.update()