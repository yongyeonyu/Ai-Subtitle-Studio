# Version: 01.00.06
"""
ui/timeline_canvas.py
[v01.00.06 수정사항]
- boundary_times 속성 추가 (멀티 영상 경계선 초록색 1px)
- paintEvent에 경계선 렌더링 추가
- 룰러 HH:MM:SS 형식으로 변경
"""

import threading
import numpy as np
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QCursor, QPolygon, QBrush
from ui.editor_helpers import find_segment_at

import config
from ui.timeline_constants import (
    RULER_H, WAVE_H, SEG_TOP, SEG_BOT, CANVAS_H,
    WAVE_MID, WAVE_HALF, ICON_SZ, HANDLE_R, _build_gaps
)

class TimelineCanvas(QWidget):
    seg_clicked             = pyqtSignal(int, float)
    seg_right_clicked       = pyqtSignal(float, QPoint)
    seg_double_clicked      = pyqtSignal(int, float)
    seg_time_changed        = pyqtSignal(int, float, float, str)
    seg_to_gap              = pyqtSignal(int)
    gap_activated           = pyqtSignal(float, float)
    gap_to_segs             = pyqtSignal(float, float)
    scrub_sec               = pyqtSignal(float)
    drag_started            = pyqtSignal()
    drag_finished           = pyqtSignal()
    step_frame              = pyqtSignal(int)
    sig_inline_text_changed = pyqtSignal(int, str)
    sig_editing_mode        = pyqtSignal(bool)
    sig_split_request       = pyqtSignal(int, float, int)
    playhead_menu_requested = pyqtSignal(QPoint, float)
    # ✅ [#9] 다이아몬드 더블클릭 → 좌우 자막 병합
    diamond_merge           = pyqtSignal(int, int)
    # ✅ [#6, #10] 웨이브폼/인라인 우클릭 → 스마트 분할
    sig_smart_split         = pyqtSignal(int, float, bool)
    sig_speech_result       = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.re_recog_zone = None
        self.re_recog_progress = None
        self.setMinimumHeight(CANVAS_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.focus_mode = "segment"
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self._ime_preedit = ""
        self.sig_speech_result.connect(self._on_speech_result)
        self._is_listening = False

        self.pps = 200.0   # ✅ [#11] 에디터 시작 시 확대 (최대 500.0까지 확대 가능)
        self.segments:     list[dict] = []
        self.gap_segments: list[dict] = []
        self.vad_segments: list[dict] = []
        self.total_duration: float = 0.0
        self.active_seg_start: float | None = None
        self.playhead_sec: float = 0.0
        self._waveform = None
        self.boundary_times: list[float] = []  # 🆕 멀티 영상 경계 시간

        self._hover_line:  int | None = None
        self._hover_handle: tuple | None = None  

        self._drag_seg:   dict | None = None
        self._drag_edge:  str  | None = None
        self._drag_adj_l: dict | None = None
        self._drag_adj_r: dict | None = None
        self._drag_x0:    int  = 0
        self._drag_s0_start: float = 0.0
        self._drag_s0_end:   float = 0.0
        self._drag_adj_orig_start_l: float = 0.0
        self._drag_adj_orig_end_l:   float = 0.0
        self._drag_adj_orig_start_r: float = 0.0
        self._drag_adj_orig_end_r:   float = 0.0

        self._snap_lines = []
        self._is_scrubbing = False
        self._is_panning = False

        self._edit_active   = False
        self._edit_line     = -1
        self._edit_text     = ""
        self._edit_orig     = ""
        self._edit_cursor   = 0
        self._cursor_vis    = True
        self._cursor_timer  = QTimer(self)
        self._cursor_timer.setInterval(500)
        self._cursor_timer.timeout.connect(self._blink_cursor)

        self._speech_mask: np.ndarray | None = None
        self._speech_mask_wf_len: int = 0

    def start_inline_edit(self, line_num: int, start_sec: float):
        self.active_seg_start = start_sec
        seg = next((s for s in self.segments if s.get("line") == line_num), None)
        if not seg: return
        text = seg.get("text", "")
        self._edit_active = True
        self._edit_line   = line_num
        self._edit_text   = text
        self._edit_orig   = text

        click_x = getattr(self, '_last_click_x', None)
        click_y = getattr(self, '_last_click_y', None)
        
        if click_x is not None and click_y is not None:
            text_start_x = self._x(seg["start"]) + HANDLE_R + 6
            rel_x = click_x - text_start_x
            rel_y = click_y - (SEG_TOP + 5)
            
            from PyQt6.QtGui import QFontMetrics, QFont
            import config
            fm = QFontMetrics(QFont(config.FONT, 14))
            line_h = fm.height() + 4
            
            lines = text.split('\n')
            click_line = max(0, int(rel_y / line_h))
            if click_line >= len(lines): click_line = len(lines) - 1
            
            target_line_text = lines[click_line]
            
            if rel_x <= 0: 
                cursor_col = 0
            else:
                cursor_col = len(target_line_text)
                for i in range(1, len(target_line_text) + 1):
                    if fm.horizontalAdvance(target_line_text[:i]) > rel_x:
                        w_prev = fm.horizontalAdvance(target_line_text[:i-1])
                        w_curr = fm.horizontalAdvance(target_line_text[:i])
                        if (rel_x - w_prev) < (w_curr - rel_x): cursor_col = i - 1
                        else: cursor_col = i
                        break
                        
            self._edit_cursor = sum(len(l) + 1 for l in lines[:click_line]) + cursor_col
            self._last_click_x = None
            self._last_click_y = None
        else:
            self._edit_cursor = len(text) 
            
        self._cursor_vis  = True
        self._cursor_timer.start()
        self.sig_editing_mode.emit(True) 
        self.update()

    def _blink_cursor(self):
        if self._edit_active:
            self._cursor_vis = not self._cursor_vis
            self.update()

    def _commit_inline_edit(self):
        if not self._edit_active:
            return

        # ✅ 텍스트가 비어있으면 → 무음구간(Gap)으로 변환
        if not self._edit_text.strip():
            line = self._edit_line
            self._end_inline_edit()
            self.seg_to_gap.emit(line)
            return

        safe_for_editor = self._edit_text.replace("\n", "\u2028")
        line = self._edit_line

        for s in self.segments:
            if s.get("line") == line:
                s["text"] = self._edit_text
                break

        self.sig_inline_text_changed.emit(line, safe_for_editor)

        if hasattr(self, "_pending_split_sec"):
            del self._pending_split_sec

        self._end_inline_edit()

    def _end_inline_edit(self):
        self._edit_active = False; self._edit_line = -1
        self._edit_text = ""; self._edit_orig = ""
        self._cursor_timer.stop()
        self.sig_editing_mode.emit(False)
        self.update(); self.setFocus()

    def _handle_edit_key(self, ev):
        key  = ev.key()
        text = self._edit_text
        cur  = self._edit_cursor
        mods = ev.modifiers()

        def _row_col(t, c):
            lines = t.split('\n')
            r = 0; col = c
            for i, ln in enumerate(lines):
                if col <= len(ln): r = i; break
                col -= (len(ln) + 1)
            else:
                r = len(lines) - 1
                col = max(0, col)
            return r, col, lines

        # ✅ [#8] ⌘+← 커서 맨앞 / ⌘+→ 커서 맨뒤
        if mods & (Qt.KeyboardModifier.MetaModifier | Qt.KeyboardModifier.ControlModifier):
            if key == Qt.Key.Key_Left:
                self._edit_cursor = 0
                self._cursor_vis = True
                self.update()
                return
            elif key == Qt.Key.Key_Right:
                self._edit_cursor = len(self._edit_text)
                self._cursor_vis = True
                self.update()
                return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._edit_text = text[:cur] + "\n" + text[cur:]
                self._edit_cursor = cur + 1
            else:
                if hasattr(self, "_pending_split_sec"):
                    safe_text = self._edit_text.replace("\n", "\u2028")
                    self.sig_inline_text_changed.emit(self._edit_line, safe_text)
                    self.sig_split_request.emit(int(self._edit_line),
                                                float(self._pending_split_sec),
                                                int(self._edit_cursor))
                    del self._pending_split_sec
                    self._end_inline_edit()
                    return
                else:
                    self._commit_inline_edit()
                    return

        elif key == Qt.Key.Key_Escape:
            self._edit_text = self._edit_orig
            self._end_inline_edit()
            return

        elif key == Qt.Key.Key_Backspace:
            if cur > 0:
                self._edit_text = text[:cur - 1] + text[cur:]
                self._edit_cursor = cur - 1
            # ✅ 빈 상태여도 편집 모드 유지 — 여기서 절대 return/종료 안 함

        elif key == Qt.Key.Key_Delete:
            if cur < len(text):
                self._edit_text = text[:cur] + text[cur + 1:]

        elif key == Qt.Key.Key_Left:
            self._edit_cursor = max(0, cur - 1)

        elif key == Qt.Key.Key_Right:
            self._edit_cursor = min(len(self._edit_text), cur + 1)

        elif key == Qt.Key.Key_Up:
            r, col, lines = _row_col(text, cur)
            if r > 0:
                new_col = min(col, len(lines[r - 1]))
                self._edit_cursor = sum(len(l) + 1 for l in lines[:r - 1]) + new_col
            else:
                self._edit_cursor = 0

        elif key == Qt.Key.Key_Down:
            r, col, lines = _row_col(text, cur)
            if r < len(lines) - 1:
                new_col = min(col, len(lines[r + 1]))
                self._edit_cursor = sum(len(l) + 1 for l in lines[:r + 1]) + new_col
            else:
                self._edit_cursor = len(text)

        elif key == Qt.Key.Key_Home:
            r, col, lines = _row_col(text, cur)
            self._edit_cursor = sum(len(l) + 1 for l in lines[:r])

        elif key == Qt.Key.Key_End:
            r, col, lines = _row_col(text, cur)
            self._edit_cursor = sum(len(l) + 1 for l in lines[:r]) + len(lines[r])

        elif key == Qt.Key.Key_Space:
            self._edit_text = text[:cur] + " " + text[cur:]
            self._edit_cursor = cur + 1

        else:
            ch = ev.text()
            if ch and ch.isprintable():
                self._edit_text = text[:cur] + ch + text[cur:]
                self._edit_cursor = cur + len(ch)

        # ✅ 텍스트가 있을 때만 에디터에 동기화 (빈 상태에서는 캔버스만 갱신)
        if self._edit_text.strip():
            for s in self.segments:
                if s.get("line") == self._edit_line:
                    s["text"] = self._edit_text
                    break
            safe_text = self._edit_text.replace("\n", "\u2028")
            self.sig_inline_text_changed.emit(self._edit_line, safe_text)

        self._cursor_vis = True
        self.update()

    def _cancel_inline_edit(self):
        if not self._edit_active:
            return
        for s in self.segments:
            if s.get("line") == self._edit_line:
                s["text"] = self._edit_orig
                break
        safe_orig = self._edit_orig.replace("\n", "\u2028")
        self.sig_inline_text_changed.emit(self._edit_line, safe_orig)
        if hasattr(self, "_pending_split_sec"):
            del self._pending_split_sec
        self._end_inline_edit()

    def _emit_smart_split_at_playhead(self):
        sec = self.playhead_sec
        seg = find_segment_at(self.segments, sec, skip_gap=True)
        if not seg:
            return
        if sec <= seg["start"] + 0.05 or sec >= seg["end"] - 0.05:
            return
        mid = (seg["start"] + seg["end"]) / 2.0
        new_on_left = (sec < mid)
        self.sig_smart_split.emit(seg.get("line", 0), float(sec), new_on_left)

    def _show_mic_menu(self, gpos):
        """인라인 편집 중 우클릭 → 마이크 메뉴"""
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #2C2C2C; color: #FFFFFF; border: 1px solid #555; "
            "font-size: 14px; padding: 4px; } "
            "QMenu::item { padding: 8px 20px; } "
            "QMenu::item:selected { background-color: #444444; }"
        )
        if self._is_listening:
            act = menu.addAction("🔴 음성인식 중지")
            act.triggered.connect(self._stop_listening)
        else:
            act = menu.addAction("🎤 음성으로 입력")
            act.triggered.connect(self._start_listening)
        menu.exec(gpos)

    def _start_listening(self):
        """백그라운드 스레드에서 음성인식 시작"""
        if self._is_listening:
            return
        self._is_listening = True
        self.update()

        def _listen():
            try:
                import speech_recognition as sr
                recognizer = sr.Recognizer()
                recognizer.energy_threshold = 300
                recognizer.dynamic_energy_threshold = True
                with sr.Microphone() as source:
                    recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    audio = recognizer.listen(source, timeout=10, phrase_time_limit=30)
                text = recognizer.recognize_google(audio, language='ko-KR')
                if text and text.strip():
                    self.sig_speech_result.emit(text.strip())
            except Exception as e:
                # 타임아웃, 인식 실패 등 — 조용히 종료
                pass
            finally:
                self._is_listening = False
                QTimer.singleShot(0, self.update)

        threading.Thread(target=_listen, daemon=True).start()

    def _stop_listening(self):
        """음성인식 중지 (플래그만 — 실제 중단은 타임아웃으로 처리)"""
        self._is_listening = False
        self.update()

    def _on_speech_result(self, text: str):
        """음성인식 결과를 인라인 편집에 삽입"""
        if not self._edit_active:
            return
        cur = self._edit_cursor
        self._edit_text = self._edit_text[:cur] + text + self._edit_text[cur:]
        self._edit_cursor = cur + len(text)

        # 에디터에 동기화
        for s in self.segments:
            if s.get("line") == self._edit_line:
                s["text"] = self._edit_text
                break
        safe_text = self._edit_text.replace("\n", "\u2028")
        self.sig_inline_text_changed.emit(self._edit_line, safe_text)
        self._cursor_vis = True
        self.update()

    def inputMethodEvent(self, ev):
        if not self._edit_active: super().inputMethodEvent(ev); return
        commit = ev.commitString(); preedit = ev.preeditString()
        self._ime_preedit = preedit
        if commit:
            cur = self._edit_cursor
            self._edit_text = self._edit_text[:cur] + commit + self._edit_text[cur:]
            self._edit_cursor = cur + len(commit)
            actual = self._edit_text.replace(" / ", "\n")
            for s in self.segments:
                if s.get("line") == self._edit_line: s["text"] = actual; break
            safe_text = actual.replace("\n", "\u2028")
            self.sig_inline_text_changed.emit(self._edit_line, safe_text)
        self._cursor_vis = True; self.update()

    def inputMethodQuery(self, query):
        from PyQt6.QtCore import Qt as _Qt
        if self._edit_active and query == _Qt.InputMethodQuery.ImCursorRectangle:
            seg = next((s for s in self.segments if s.get("line") == self._edit_line), None)
            if seg:
                from PyQt6.QtCore import QRect
                return QRect(self._x(seg["start"]), SEG_TOP + 5, 1, 20)
        return super().inputMethodQuery(query)

    def focusNextPrevChild(self, next: bool) -> bool:
        self._snap_closest_diamond(); return False

    def keyPressEvent(self, ev):
        if self._edit_active:
            self._handle_edit_key(ev)
            ev.accept()
            return
            
        if ev.key() in (Qt.Key.Key_F2, Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.active_seg_start is not None:
            seg = next((s for s in self.segments if abs(s["start"] - self.active_seg_start) < 0.5), None)
            if seg: self.start_inline_edit(seg.get("line", 0), seg["start"])
            ev.accept(); return

        if ev.key() == Qt.Key.Key_Tab:
            self._snap_closest_diamond(); ev.accept(); return
        if ev.key() == Qt.Key.Key_Up:
            self.focus_mode = "waveform"; self.update(); ev.accept(); return
        elif ev.key() == Qt.Key.Key_Down:
            self.focus_mode = "segment"; self.update(); ev.accept(); return

        if getattr(self, 'focus_mode', '') == "waveform":
            if ev.key() == Qt.Key.Key_Left:
                if ev.isAutoRepeat(): self.step_frame.emit(-4)
                else: self.step_frame.emit(-1)
                ev.accept(); return
            elif ev.key() == Qt.Key.Key_Right:
                if ev.isAutoRepeat(): self.step_frame.emit(4)
                else: self.step_frame.emit(1)
                ev.accept(); return
        else:
            if ev.key() == Qt.Key.Key_Left:
                if ev.isAutoRepeat(): self.step_frame.emit(-4) 
                else: self._jump_to_prev_segment()
                ev.accept(); return
            elif ev.key() == Qt.Key.Key_Right:
                if ev.isAutoRepeat(): self.step_frame.emit(4) 
                else: self._jump_to_next_segment()
                ev.accept(); return
        super().keyPressEvent(ev)

    def _jump_to_prev_segment(self):
        if not self.segments: return
        target = None
        for s in reversed(self.segments):
            if s["start"] < self.playhead_sec - 0.1:
                target = s["start"]; break
        if target is not None: self.scrub_sec.emit(target)
        else: self.scrub_sec.emit(0.0)

    def _jump_to_next_segment(self):
        if not self.segments: return
        target = None
        for s in self.segments:
            if s["start"] > self.playhead_sec + 0.1:
                target = s["start"]; break
        if target is not None: self.scrub_sec.emit(target)
        else: self.scrub_sec.emit(self.total_duration)

    def set_zoom(self, new_pps: float):
        self.pps = max(5.0, min(500.0, new_pps)); self.update()

    def update_segments(self, segs: list[dict], active_sec: float | None, total_dur: float):
        self.segments = [s for s in segs if not s.get("is_gap")]
        self.total_duration = total_dur or (segs[-1]["end"] if segs else 0)
        new_gaps = _build_gaps(self.segments, self.total_duration)
        old_active = {(g["start"], g["end"]) for g in self.gap_segments if g.get("active")}
        for g in new_gaps:
            if (g["start"], g["end"]) in old_active: g["active"] = True
        self.gap_segments = new_gaps
        if active_sec is not None: self.active_seg_start = active_sec
        self.update()

    def _get_fps(self) -> float:
        w = self.parent()
        while w:
            if hasattr(w, 'video_fps'): return float(w.video_fps)
            w = w.parent()
        return 30.0

    def _snap_to_frame(self, sec: float) -> float:
        fps = self._get_fps()
        if fps <= 0: fps = 30.0
        return round(round(sec * fps) / fps, 3)

    def _snap_closest_diamond(self):
        if self.playhead_sec <= 0: return
        closest_seg_idx = None; closest_edge = None; min_dist = float('inf')

        for i, seg in enumerate(self.segments):
            dist_start = abs(seg["start"] - self.playhead_sec)
            if dist_start < min_dist:
                min_dist = dist_start; closest_seg_idx = i; closest_edge = "start"
            dist_end = abs(seg["end"] - self.playhead_sec)
            if dist_end < min_dist:
                min_dist = dist_end; closest_seg_idx = i; closest_edge = "end"

        if closest_seg_idx is not None and min_dist <= 2.0:
            seg = self.segments[closest_seg_idx]
            new_boundary = self._snap_to_frame(self.playhead_sec)
            min_len = self._snap_to_frame(0.1) 

            is_joint = False; joint_seg_idx = None
            
            if closest_edge == "start" and closest_seg_idx > 0:
                prev_seg = self.segments[closest_seg_idx - 1]
                if abs(prev_seg["end"] - seg["start"]) < 0.05:
                    is_joint = True; joint_seg_idx = closest_seg_idx - 1
            elif closest_edge == "end" and closest_seg_idx < len(self.segments) - 1:
                next_seg = self.segments[closest_seg_idx + 1]
                if abs(seg["end"] - next_seg["start"]) < 0.05:
                    is_joint = True; joint_seg_idx = closest_seg_idx + 1

            if is_joint:
                if closest_edge == "start": s1, s2 = self.segments[joint_seg_idx], seg
                else: s1, s2 = seg, self.segments[joint_seg_idx]
                new_boundary = max(self._snap_to_frame(s1["start"] + min_len), min(self._snap_to_frame(s2["end"] - min_len), new_boundary))
                s1["end"] = s2["start"] = new_boundary
                self.seg_time_changed.emit(s2.get("line", 0), s2["start"], s2["end"], "diamond")
            else:
                if closest_edge == "start":
                    limit_l = 0.0
                    if closest_seg_idx > 0: limit_l = self.segments[closest_seg_idx - 1]["end"]
                    new_boundary = max(self._snap_to_frame(limit_l), min(self._snap_to_frame(seg["end"] - min_len), new_boundary))
                    seg["start"] = new_boundary
                    self.seg_time_changed.emit(seg.get("line", 0), seg["start"], seg["end"], "square_left")
                else: 
                    limit_r = self.total_duration
                    if closest_seg_idx < len(self.segments) - 1: limit_r = self.segments[closest_seg_idx + 1]["start"]
                    new_boundary = max(self._snap_to_frame(seg["start"] + min_len), min(self._snap_to_frame(limit_r), new_boundary))
                    seg["end"] = new_boundary
                    self.seg_time_changed.emit(seg.get("line", 0), seg["start"], seg["end"], "square_right")

            self.gap_segments = _build_gaps(self.segments, self.total_duration)
            self.update()

    def set_vad_segments(self, vad_segs: list):
        self.vad_segments = vad_segs
        self._speech_mask = None
        self.update()

    def set_active(self, sec: float | None):
        self.active_seg_start = sec; self.update()

    def set_playhead(self, sec):
        if self.playhead_sec == sec: return
        self.playhead_sec = sec; self.update()

    def set_waveform(self, wf: np.ndarray):
        self._waveform = wf
        self._speech_mask = None
        self.update()

    def _x(self, sec: float) -> int: return int(sec * self.pps)
    def total_width(self) -> int: return max(self.width(), int(self.total_duration * self.pps) + self.width())

    def _icon_rect(self, x1: int, x2: int) -> QRect:
        return QRect(x1 + (x2 - x1) // 2 - (ICON_SZ // 2), SEG_BOT + 1, ICON_SZ, ICON_SZ)

    def _plus_rect(self, x1: int, x2: int) -> QRect: 
        return QRect(x1 + (x2 - x1) // 2 - (ICON_SZ // 2), SEG_BOT + 1, ICON_SZ, ICON_SZ)

    def _seg_at(self, x: int) -> dict | None:
        for s in self.segments:
            if self._x(s["start"]) <= x <= self._x(s["end"]): return s
        return None

    def _get_prev_seg(self, seg: dict) -> dict | None:
        segs = sorted(self.segments, key=lambda s: s["start"])
        try: idx = segs.index(seg); return segs[idx-1] if idx > 0 else None
        except ValueError: return None

    def _get_next_seg(self, seg: dict) -> dict | None:
        segs = sorted(self.segments, key=lambda s: s["start"])
        try: idx = segs.index(seg); return segs[idx+1] if idx + 1 < len(segs) else None
        except ValueError: return None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        total_w = self.total_width()
        total_secs = self.total_duration + 2
        sec_f = 0.0

        def _fmt_ruler(sec):
            s = int(sec)
            h, rem = divmod(s, 3600)
            m, sc = divmod(rem, 60)
            if h > 0: return f"{h}:{m:02d}:{sc:02d}"
            return f"{m:02d}:{sc:02d}"

        ruler_font = QFont(config.FONT, 12)
        ruler_font.setBold(True)
        p.setFont(ruler_font)

        while sec_f <= total_secs:
            tx = self._x(sec_f); sec_i = sec_f
            if abs(sec_i - round(sec_i, 0)) < 0.01:
                sec_i = round(sec_i)
                if sec_i % 5 == 0 and sec_i != 0:
                    p.setPen(QColor("#BBBBBB")); p.drawLine(tx, 0, tx, 15)
                    p.drawText(tx + 5, RULER_H - 5, _fmt_ruler(sec_i))
                elif sec_i % 1 == 0:
                    p.setPen(QColor("#666666")); p.drawLine(tx, 0, tx, 8)
                    if sec_i > 0: p.drawText(tx + 2, RULER_H - 2, _fmt_ruler(sec_i))
            elif abs(sec_i * 2 - round(sec_i * 2)) < 0.01: p.setPen(QColor("#444444")); p.drawLine(tx, 0, tx, 5)
            else: p.setPen(QColor("#333333")); p.drawLine(tx, 0, tx, 3)
            sec_f = round(sec_f + 0.1, 1)

        p.fillRect(QRect(0, RULER_H, total_w, WAVE_H), QColor("#0a0a0a"))

        if self._waveform is not None:
            wf = self._waveform
            wf_len = len(wf)

            p.setPen(QPen(QColor("#333333"), 1))
            p.drawLine(0, WAVE_MID, total_w, WAVE_MID)

            if self._speech_mask is None or self._speech_mask_wf_len != wf_len:
                mask = np.zeros(wf_len, dtype=bool)
                for vs in self.vad_segments:
                    s_idx = max(0, int(vs["start"] * 100))
                    e_idx = min(wf_len, int(vs["end"] * 100) + 1)
                    mask[s_idx:e_idx] = True
                self._speech_mask = mask
                self._speech_mask_wf_len = wf_len
            speech_mask = self._speech_mask

            clip      = event.rect()
            x_start   = max(0, clip.left())
            x_end     = min(total_w, clip.right() + 1)

            pen_top_norm  = QPen(QColor(100, 220, 255), 1)
            pen_bot_norm  = QPen(QColor( 40, 130, 170), 1)
            pen_top_loud  = QPen(QColor(160, 255, 255), 1)
            pen_bot_loud  = QPen(QColor( 80, 180, 210), 1)
            pen_top_sil   = QPen(QColor( 75,  75,  75), 1)
            pen_bot_sil   = QPen(QColor( 45,  45,  45), 1)

            for x in range(x_start, x_end):
                idx = int((x / self.pps) * 100)
                if idx >= wf_len:
                    break
                val = wf[idx]
                if val < 0.008:
                    continue

                h = min(int(val * WAVE_HALF * 2.0), WAVE_HALF - 1)
                in_sp = speech_mask[idx]

                if in_sp:
                    if val > 0.6:
                        p.setPen(pen_top_loud); p.drawLine(x, WAVE_MID,     x, WAVE_MID - h)
                        p.setPen(pen_bot_loud); p.drawLine(x, WAVE_MID + 1, x, WAVE_MID + h)
                    else:
                        p.setPen(pen_top_norm); p.drawLine(x, WAVE_MID,     x, WAVE_MID - h)
                        p.setPen(pen_bot_norm); p.drawLine(x, WAVE_MID + 1, x, WAVE_MID + h)
                else:
                    p.setPen(pen_top_sil); p.drawLine(x, WAVE_MID,     x, WAVE_MID - h)
                    p.setPen(pen_bot_sil); p.drawLine(x, WAVE_MID + 1, x, WAVE_MID + h)

        if self.vad_segments:
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(255, 200, 0, 40))
            for vs in self.vad_segments:
                vx1 = self._x(vs["start"]); vx2 = self._x(vs["end"])
                p.drawRect(QRect(vx1, RULER_H, vx2 - vx1, WAVE_H))

        if self.re_recog_zone:
            rs, re_sec = self.re_recog_zone
            rp = self.re_recog_progress if self.re_recog_progress is not None else rs
            yx1 = self._x(rs); yx2 = self._x(rp)
            if yx2 > yx1:
                p.fillRect(QRect(yx1, RULER_H, yx2 - yx1, WAVE_H), QColor(255, 255, 0, 100))
            gx1 = self._x(max(rs, rp)); gx2 = self._x(re_sec)
            if gx2 > gx1:
                p.fillRect(QRect(gx1, RULER_H, gx2 - gx1, WAVE_H), QColor(0, 255, 0, 70))

        for g in self.gap_segments:
            x1, x2 = self._x(g["start"]), self._x(g["end"]); sw = max(4, x2 - x1)
            rect = QRect(x1, SEG_TOP, sw, SEG_BOT - SEG_TOP)
            p.fillRect(rect, QColor("#0d0d0d"))
            is_active = g.get("active", False)
            if is_active:
                p.setPen(QPen(QColor("#FFFFFF"), 2)); p.drawRect(rect); ir = self._icon_rect(x1, x2)
                p.fillRect(ir, QColor("#442222")); p.setPen(QColor("#FF8888")); p.setFont(QFont(config.FONT, 9, QFont.Weight.Bold))
                p.drawText(ir, Qt.AlignmentFlag.AlignCenter, "✕")
            else:
                p.setPen(QPen(QColor("#888888"), 1, Qt.PenStyle.DotLine)); p.drawRect(rect)
                if sw >= ICON_SZ + 8:
                    ir = self._plus_rect(x1, x2); p.fillRect(ir, QColor("#112233")); p.setPen(QColor("#6699CC"))
                    p.setFont(QFont(config.FONT, 18, QFont.Weight.Bold)); p.drawText(ir, Qt.AlignmentFlag.AlignCenter, "+")

        seg_font = QFont(config.FONT, 14); p.setFont(seg_font)
        for seg in self.segments:
            x1, x2 = self._x(seg["start"]), self._x(seg["end"]); sw = max(10, x2 - x1)
            rect = QRect(x1, SEG_TOP, sw, SEG_BOT - SEG_TOP)
            is_active = (self.active_seg_start is not None and abs(seg["start"] - self.active_seg_start) < 0.5)
            is_hover  = self._hover_line == seg.get("line")
            fill   = (QColor("#1a3a1a") if is_active else QColor("#3a3a00") if is_hover else QColor("#2C2C2C"))
            border = QColor("#FFFF00") if is_active else QColor(config.ACCENT)
            bw = 2 if is_active else (2 if is_hover else 1)

            p.fillRect(rect, fill); p.setPen(QPen(border, bw)); p.drawRect(rect); p.setFont(seg_font)
            text_rect = QRect(x1 + HANDLE_R + 6, SEG_TOP + 5, sw - (HANDLE_R * 2) - 12, SEG_BOT - SEG_TOP - 10)
            is_editing = (self._edit_active and self._edit_line == seg.get("line"))

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
                p.fillRect(text_rect, QColor("#002200"))
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
                p.setPen(QColor("#FFFFFF"))
                p.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, seg.get("text", ""))

            ir = self._icon_rect(x1, x2)
            if sw > ICON_SZ + HANDLE_R + 4:
                p.fillRect(ir, QColor("#550000")); p.setPen(QColor("#FF6666")); p.setFont(QFont(config.FONT, 18, QFont.Weight.Bold))
                p.drawText(ir, Qt.AlignmentFlag.AlignCenter, "✕")

            hovered = self._hover_handle
            lh = hovered and hovered[0] is seg and hovered[1] == "left"
            rh = hovered and hovered[0] is seg and hovered[1] == "right"
            self._draw_handle(p, x1, True,  QColor("#44FF88") if lh else QColor("#888888"))
            self._draw_handle(p, x2, False, QColor("#44FF88") if rh else QColor("#888888"))

        if hasattr(self, '_snap_lines') and self._snap_lines:
            p.setPen(QPen(QColor("#FF4444"), 4))
            for sx in self._snap_lines: p.drawLine(sx, SEG_TOP, sx, SEG_BOT)

        for i in range(len(self.segments) - 1):
            s1 = self.segments[i]; s2 = self.segments[i+1]
            if abs(s1["end"] - s2["start"]) < 0.05:
                bx = self._x(s1["end"]); w = int(HANDLE_R * 1.2) * 2; h = 10; cy = SEG_BOT - (h // 2)
                rect = QRect(int(bx - w/2), int(cy - h/2), w, h)
                is_hover = (getattr(self, '_hover_diamond', None) == i)
                color = QColor("#FFD700") if is_hover else QColor("#AAAAAA")
                p.setPen(QPen(QColor("#000000"), 1)); p.setBrush(QBrush(color)); p.drawRoundedRect(rect, 4, 4); p.setBrush(Qt.BrushStyle.NoBrush)

        # 멀티 영상 경계선
        if self.boundary_times:
            pen_boundary = QPen(QColor("#4AFF80"), 1)
            for bt in self.boundary_times:
                bx = self._x(bt)
                p.setPen(pen_boundary)
                p.drawLine(bx, 0, bx, CANVAS_H)

        # 음성인식 중 표시
        if getattr(self, '_is_listening', False) and self._edit_active:
            seg = next((s for s in self.segments if s.get("line") == self._edit_line), None)
            if seg:
                mic_x = self._x(seg["end"]) + 8
                mic_y = SEG_TOP + 5
                p.setFont(QFont(config.FONT, 18))
                p.setPen(QColor("#FF4444"))
                p.drawText(mic_x, mic_y + 20, "🎤")
                p.setFont(QFont(config.FONT, 10))
                p.setPen(QColor("#FF8888"))
                p.drawText(mic_x + 24, mic_y + 18, "음성인식 중...")

        # 플레이헤드
        if self.playhead_sec >= 0:
            ph_color = QColor("#4AFF80") if getattr(self, 'focus_mode', 'segment') == "waveform" else QColor("#FF4444")
            p.setPen(QPen(ph_color, 2)); px = self._x(self.playhead_sec); p.drawLine(px, 0, px, CANVAS_H)
            handle_r = 7
            self._playhead_handle_rect = QRect(int(px - handle_r), 2, handle_r * 2, handle_r * 2)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(QBrush(QColor("#FFCC00")))
            p.setPen(QPen(QColor("#FFFFFF"), 1))
            p.drawEllipse(self._playhead_handle_rect)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    def _draw_handle(self, p: QPainter, bx: int, is_left: bool, color: QColor):
        cy = SEG_TOP + (SEG_BOT - SEG_TOP) // 2
        w = HANDLE_R; hw = HANDLE_R // 2; hh = 12; th = 4             
        if is_left:
            bx += 2
            pts = QPolygon([QPoint(bx, cy), QPoint(bx + hw, cy - hh), QPoint(bx + hw, cy - th), QPoint(bx + w, cy - th), QPoint(bx + w, cy + th), QPoint(bx + hw, cy + th), QPoint(bx + hw, cy + hh)])
        else:
            bx -= 2
            pts = QPolygon([QPoint(bx, cy), QPoint(bx - hw, cy - hh), QPoint(bx - hw, cy - th), QPoint(bx - w, cy - th), QPoint(bx - w, cy + th), QPoint(bx - hw, cy + th), QPoint(bx - hw, cy + hh)])
        p.setPen(QPen(QColor("#000000"), 1)); p.setBrush(QBrush(color)); p.drawPolygon(pts); p.setBrush(Qt.BrushStyle.NoBrush)

    def wheelEvent(self, event):
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier or mods & Qt.KeyboardModifier.MetaModifier:
            event.ignore(); return
        dy, dx = event.angleDelta().y(), event.angleDelta().x(); delta  = -(dy if dy != 0 else dx)
        w = self.parent()
        from PyQt6.QtWidgets import QScrollArea as _SA
        while w and not isinstance(w, _SA): w = w.parent()
        if w: sb = w.horizontalScrollBar(); sb.setValue(sb.value() + delta // 2)
        event.accept()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton or ev.button() == Qt.MouseButton.RightButton:
            if hasattr(self, '_playhead_handle_rect') and self._playhead_handle_rect.contains(ev.pos()):
                self.playhead_menu_requested.emit(ev.globalPosition().toPoint(), self.playhead_sec)
                return

        x, y = ev.pos().x(), ev.pos().y()
        self._last_click_x = x
        self._last_click_y = y

        # ✅ 인라인 편집 중
        if self._edit_active:
            if ev.button() == Qt.MouseButton.RightButton:
                # 마이크 메뉴
                self._show_mic_menu(ev.globalPosition().toPoint())
                return

            # 좌클릭: 세그먼트 안이면 커서 이동, 밖이면 편집 종료
            if ev.button() == Qt.MouseButton.LeftButton:
                seg = next((s for s in self.segments if s.get("line") == self._edit_line), None)
                is_inside = False
                if seg and SEG_TOP <= y <= SEG_BOT:
                    x1, x2 = self._x(seg["start"]), self._x(seg["end"])
                    if x1 + HANDLE_R < x < x2 - HANDLE_R:
                        is_inside = True
                        from PyQt6.QtGui import QFontMetrics, QFont as _QFont
                        fm   = QFontMetrics(_QFont(config.FONT, 14))
                        lh   = fm.height() + 4
                        tx0  = x1 + HANDLE_R + 6
                        rel_x = x - tx0
                        rel_y = y - (SEG_TOP + 5)
                        lines = self._edit_text.split('\n')
                        cl    = max(0, min(int(rel_y / lh), len(lines) - 1))
                        ln_txt = lines[cl]
                        if rel_x <= 0:
                            col = 0
                        else:
                            col = len(ln_txt)
                            for i in range(1, len(ln_txt) + 1):
                                if fm.horizontalAdvance(ln_txt[:i]) > rel_x:
                                    wp = fm.horizontalAdvance(ln_txt[:i - 1])
                                    wc = fm.horizontalAdvance(ln_txt[:i])
                                    col = i - 1 if (rel_x - wp) < (wc - rel_x) else i
                                    break
                        self._edit_cursor = sum(len(l) + 1 for l in lines[:cl]) + col
                        self._cursor_vis  = True
                        self.update()

                # ✅ 세그먼트 바깥 클릭 → 편집 커밋 후 종료
                if not is_inside:
                    self._commit_inline_edit()
                    # 클릭 이벤트를 다시 처리하지 않고 여기서 끝냄
                    # (다음 클릭에서 세그먼트 선택/스크럽 등 정상 동작)
                return
            return

        self._just_committed = False
        self.setFocus()

        if ev.button() == Qt.MouseButton.RightButton:
            # 웨이브폼/룰러 영역 우클릭 → 스마트 분할
            if y < SEG_TOP:
                self._emit_smart_split_at_playhead()
                return
            # 세그먼트 영역 우클릭 → 인라인 편집 + 분할 대기
            if SEG_TOP <= y <= SEG_BOT:
                seg = self._seg_at(x)
                if seg:
                    self._last_click_x = x
                    self._last_click_y = y
                    self._pending_split_sec = float(self.playhead_sec)
                    self.start_inline_edit(seg.get("line", 0), seg["start"])
            return

        if ev.button() != Qt.MouseButton.LeftButton:
            return

        self.focus_mode = "waveform" if y <= SEG_TOP else "segment"
        self.update()

        for seg in self.segments:
            x1, x2 = self._x(seg["start"]), self._x(seg["end"]); sw = x2 - x1
            if sw > 20 and self._icon_rect(x1, x2).adjusted(-5, -5, 5, 5).contains(x, y):
                self.seg_to_gap.emit(seg.get("line", 0)); return

        for g in self.gap_segments:
            gx1, gx2 = self._x(g["start"]), self._x(g["end"])
            if self._plus_rect(gx1, gx2).adjusted(-5, -5, 5, 5).contains(x, y):
                if g.get("active"): self.gap_to_segs.emit(g["start"], g["end"])
                else: g["active"] = True; self.update(); self.gap_activated.emit(g["start"], g["end"])
                return

        if y < SEG_TOP:
            self._is_panning = True; self._pan_last_x = ev.globalPosition().x()
            self.setCursor(Qt.CursorShape.ClosedHandCursor); self.scrub_sec.emit(max(0.0, x / self.pps)); return

        if SEG_TOP <= y <= SEG_BOT:
            for g in self.gap_segments:
                if g.get("active"): continue
                gx1, gx2 = self._x(g["start"]), self._x(g["end"])
                if gx2 - gx1 >= ICON_SZ + 8 and self._plus_rect(gx1, gx2).contains(x, y):
                    g["active"] = True; self.update(); self.gap_activated.emit(g["start"], g["end"]); return

        for i in range(len(self.segments) - 1):
            s1 = self.segments[i]; s2 = self.segments[i+1]
            if abs(s1["end"] - s2["start"]) < 0.05:
                bx = self._x(s1["end"]); r = int(HANDLE_R * 1.2); cy = SEG_BOT - (r // 2); rect = QRect(bx - r, cy - r, r * 2, r * 2)
                if rect.contains(x, y):
                    self.drag_started.emit(); self._drag_edge = "diamond"; self._drag_diamond_idx = i; self._drag_diamond_orig = s1["end"]; self._drag_x0 = x
                    self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor)); return

        best_dist = 25; best_click = None
        for s in self.segments:
            x1, x2 = self._x(s["start"]), self._x(s["end"]); mid_y = SEG_TOP + (SEG_BOT - SEG_TOP) // 2
            hx1 = min(x1 + 2 + HANDLE_R // 2, (x1 + x2) // 2); hx2 = max(x2 - 2 - HANDLE_R // 2, (x1 + x2) // 2)
            if abs(y - mid_y) <= 25:
                dist_l = abs(x - hx1)
                if dist_l < best_dist: best_dist = dist_l; best_click = (s, "square_left")
                dist_r = abs(x - hx2)
                if dist_r < best_dist: best_dist = dist_r; best_click = (s, "square_right")

        if best_click: self._setup_drag(best_click[0], best_click[1], x); return

        for s in self.segments:
            x1, x2 = self._x(s["start"]), self._x(s["end"])
            if self.active_seg_start is not None and abs(s["start"] - self.active_seg_start) < 0.5:
                if x1 + 25 < x < x2 - 25 and SEG_TOP <= y <= SEG_BOT:
                    self._setup_drag(s, "center", x); self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor)); return

        seg = self._seg_at(x)
        if seg: self.seg_clicked.emit(seg.get("line", 0), seg["start"]); return

        self._is_scrubbing = True; self.scrub_sec.emit(max(0.0, x / self.pps))

    def _setup_drag(self, s, edge, x):
        self.drag_started.emit(); self._drag_seg, self._drag_edge = s, edge; self._drag_x0 = x
        self._drag_s0_start, self._drag_s0_end = s["start"], s["end"]
        self._drag_adj_l = self._get_prev_seg(s); self._drag_adj_r = self._get_next_seg(s)
        self._drag_adj_orig_start_l = self._drag_adj_l["start"] if self._drag_adj_l else 0.0
        self._drag_adj_orig_end_l = self._drag_adj_l["end"] if self._drag_adj_l else 0.0
        self._drag_adj_orig_start_r = self._drag_adj_r["start"] if self._drag_adj_r else 0.0
        self._drag_adj_orig_end_r = self._drag_adj_r["end"] if self._drag_adj_r else 0.0
        if edge != "center": self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))

    def mouseDoubleClickEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        if self._edit_active:
            self._commit_inline_edit()
            return
        x, y = ev.pos().x(), ev.pos().y()

        # ✅ [#9 버그 수정] 다이아몬드 더블클릭 → 드래그 상태 정리 후 병합
        for i in range(len(self.segments) - 1):
            s1 = self.segments[i]
            s2 = self.segments[i + 1]
            if abs(s1["end"] - s2["start"]) < 0.05:
                bx = self._x(s1["end"])
                w = int(HANDLE_R * 1.2) * 2
                h = 10
                cy = SEG_BOT - (h // 2)
                rect = QRect(int(bx - w / 2), int(cy - h / 2), w, h)
                if rect.adjusted(-5, -5, 5, 5).contains(x, y):
                    # ✅ 첫 클릭에서 시작된 diamond drag 정리
                    self._drag_seg = None
                    self._drag_edge = None
                    self._drag_diamond_idx = None
                    self._snap_lines = []
                    self.unsetCursor()
                    self.drag_finished.emit()   # beginEditBlock 짝 맞춤
                    # ✅ 드래그 정리 완료 후 병합 시그널
                    self.diamond_merge.emit(s1.get("line", 0), s2.get("line", 0))
                    return

        # 기존: 세그먼트 더블클릭 → 인라인 편집
        if SEG_TOP <= y <= SEG_BOT:
            seg = next(
                (s for s in self.segments if self._x(s["start"]) <= x <= self._x(s["end"])),
                None
            )
            if seg:
                self.seg_double_clicked.emit(seg.get("line", 0), seg["start"])

    def mouseMoveEvent(self, ev):
        x, y = ev.pos().x(), ev.pos().y()

        if self._edit_active:
            seg = next((s for s in self.segments if s.get("line") == self._edit_line), None)
            if seg and SEG_TOP <= y <= SEG_BOT and self._x(seg["start"]) + HANDLE_R < x < self._x(seg["end"]) - HANDLE_R:
                self.setCursor(Qt.CursorShape.IBeamCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if getattr(self, '_is_panning', False) and (ev.buttons() & Qt.MouseButton.LeftButton):
            current_x = ev.globalPosition().x(); delta_x = self._pan_last_x - current_x
            w = self.parent()
            from PyQt6.QtWidgets import QScrollArea
            while w and not isinstance(w, QScrollArea): w = w.parent()
            if w: w.horizontalScrollBar().setValue(int(w.horizontalScrollBar().value() + delta_x))
            self._pan_last_x = current_x; return

        if getattr(self, '_is_scrubbing', False) and (ev.buttons() & Qt.MouseButton.LeftButton):
            self.scrub_sec.emit(max(0.0, x / self.pps)); return

        if self._drag_seg or getattr(self, '_drag_edge', None) == "diamond":
            if ev.buttons() & Qt.MouseButton.LeftButton: self._apply_drag((x - self._drag_x0) / self.pps)
            return

        hover_dia = None
        for i in range(len(self.segments) - 1):
            s1 = self.segments[i]; s2 = self.segments[i+1]
            if abs(s1["end"] - s2["start"]) < 0.05:
                bx = self._x(s1["end"]); r = HANDLE_R; cy = SEG_BOT - r + 2
                if abs(x - bx) <= r + 5 and abs(y - cy) <= r + 5: hover_dia = i; break
                    
        if getattr(self, '_hover_diamond', None) != hover_dia: self._hover_diamond = hover_dia; self.update()
        if hover_dia is not None: self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor)); return

        hover_handle = False; hover_center = False; new_hh = None
        best_dist = 25 
        for s in self.segments:
            x1, x2 = self._x(s["start"]), self._x(s["end"]); mid_y = SEG_TOP + (SEG_BOT - SEG_TOP) // 2
            hx1 = min(x1 + 2 + HANDLE_R // 2, (x1 + x2) // 2); hx2 = max(x2 - 2 - HANDLE_R // 2, (x1 + x2) // 2)
            if abs(y - mid_y) <= 25:
                dist_l = abs(x - hx1)
                if dist_l < best_dist: best_dist = dist_l; new_hh = (s, "left")
                dist_r = abs(x - hx2)
                if dist_r < best_dist: best_dist = dist_r; new_hh = (s, "right")

        if new_hh: hover_handle = True
        else:
            for s in self.segments:
                x1, x2 = self._x(s["start"]), self._x(s["end"])
                if self.active_seg_start is not None and abs(s["start"] - self.active_seg_start) < 0.5:
                    if x1 + 25 < x < x2 - 25 and SEG_TOP <= y <= SEG_BOT: hover_center = True; break

        if self._hover_handle != new_hh: self._hover_handle = new_hh; self.update()
        
        if hover_handle: self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        elif hover_center: self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        else: self.unsetCursor()

        seg2 = self._seg_at(x); new_h = seg2.get("line") if seg2 else None
        if new_h != self._hover_line: self._hover_line = new_h; self.update()
        
    def mouseReleaseEvent(self, ev):
        if getattr(self, '_is_panning', False): self._is_panning = False; self.unsetCursor(); return
        if getattr(self, '_is_scrubbing', False): self._is_scrubbing = False; return

        if getattr(self, '_drag_edge', None) == "diamond":
            idx = getattr(self, '_drag_diamond_idx', None)
            if idx is not None and idx + 1 < len(self.segments):
                s2 = self.segments[idx+1]
                self.seg_time_changed.emit(s2.get("line", 0), s2["start"], s2["end"], "diamond")
            self.drag_finished.emit()
            self._drag_seg = self._drag_edge = self._drag_adj_l = self._drag_adj_r = None
            self._drag_diamond_idx = None; self._snap_lines = []; self.unsetCursor()
            self.gap_segments = _build_gaps(self.segments, self.total_duration); self.update(); return

        if self._drag_seg:
            edge = str(self._drag_edge) if self._drag_edge else ""
            self.seg_time_changed.emit(self._drag_seg.get("line", 0), self._drag_seg["start"], self._drag_seg["end"], edge)
            # ✅ [수정] center 드래그 시 인접 세그먼트 변경 금지 — square_left만 허용
            if self._drag_adj_l and self._drag_edge == "square_left":
                self.seg_time_changed.emit(self._drag_adj_l.get("line", 0), self._drag_adj_l["start"], self._drag_adj_l["end"], edge)
            self.drag_finished.emit()
            self._drag_seg = self._drag_edge = self._drag_adj_l = self._drag_adj_r = None
            self._snap_lines = []; self.unsetCursor()
            self.gap_segments = _build_gaps(self.segments, self.total_duration); self.update()    

    def _apply_drag(self, delta: float):
        if delta == 0: return
        edge = getattr(self, '_drag_edge', None); self._snap_lines = []; playhead_snap = 5.0 / self.pps 

        if edge == "diamond":
            idx = getattr(self, '_drag_diamond_idx', None)
            if idx is not None and idx + 1 < len(self.segments):
                s1, s2 = self.segments[idx], self.segments[idx+1]
                orig_boundary = getattr(self, '_drag_diamond_orig', 0.0); new_boundary = self._snap_to_frame(orig_boundary + delta)
                if self.playhead_sec > 0 and abs(new_boundary - self.playhead_sec) <= playhead_snap:
                    new_boundary = self._snap_to_frame(self.playhead_sec); self._snap_lines.append(self._x(new_boundary))
                new_boundary = max(self._snap_to_frame(s1["start"] + 0.1), min(self._snap_to_frame(s2["end"] - 0.1), new_boundary))
                s1["end"] = s2["start"] = new_boundary
                self.gap_segments = _build_gaps(self.segments, self.total_duration); self.update()
            return

        seg = self._drag_seg; MIN = self._snap_to_frame(0.1)

        if edge == "square_right":
            new_end = self._snap_to_frame(self._drag_s0_end + delta)
            limit = self._drag_adj_orig_start_r if self._drag_adj_r else self.total_duration
            if self.playhead_sec > 0 and abs(new_end - self.playhead_sec) <= playhead_snap: new_end = self._snap_to_frame(self.playhead_sec)
            seg["end"] = max(self._snap_to_frame(seg["start"] + MIN), min(new_end, limit))
            if abs(seg["end"] - limit) < 0.05 or (self.playhead_sec > 0 and abs(seg["end"] - self.playhead_sec) < 0.05): self._snap_lines.append(self._x(seg["end"]))

        elif edge == "square_left":
            new_start = self._snap_to_frame(self._drag_s0_start + delta)
            limit = self._drag_adj_orig_end_l if self._drag_adj_l else 0.0
            if self.playhead_sec > 0 and abs(new_start - self.playhead_sec) <= playhead_snap: new_start = self._snap_to_frame(self.playhead_sec)
            seg["start"] = min(self._snap_to_frame(seg["end"] - MIN), max(new_start, limit))
            if self.active_seg_start is not None: self.active_seg_start = seg["start"]
            if abs(seg["start"] - limit) < 0.05 or (self.playhead_sec > 0 and abs(seg["start"] - self.playhead_sec) < 0.05): self._snap_lines.append(self._x(seg["start"]))
            
        elif edge == "center":
            dur = self._drag_s0_end - self._drag_s0_start; new_start = self._snap_to_frame(self._drag_s0_start + delta)
            limit_l = self._drag_adj_orig_end_l if self._drag_adj_l else 0.0
            limit_r = self._drag_adj_orig_start_r if self._drag_adj_r else self.total_duration
            snapped_to_playhead = False
            if self.playhead_sec > 0:
                if abs(new_start - self.playhead_sec) <= playhead_snap:
                    new_start = self._snap_to_frame(self.playhead_sec); snapped_to_playhead = True
                elif abs(new_start + dur - self.playhead_sec) <= playhead_snap:
                    new_start = self._snap_to_frame(self.playhead_sec - dur); snapped_to_playhead = True

            if not snapped_to_playhead:
                if self._drag_adj_l and abs(new_start - limit_l) <= 0.2: new_start = limit_l
                elif self._drag_adj_r and abs(new_start + dur - limit_r) <= 0.2: new_start = self._snap_to_frame(limit_r - dur)
                elif not self._drag_adj_l and abs(new_start - 0.0) <= 0.2: new_start = 0.0
                elif not self._drag_adj_r and abs(new_start + dur - self.total_duration) <= 0.2: new_start = self._snap_to_frame(self.total_duration - dur)
            
            new_start = max(limit_l, min(new_start, self._snap_to_frame(limit_r - dur)))
            seg["start"] = new_start; seg["end"] = self._snap_to_frame(new_start + dur)
            if self.active_seg_start is not None: self.active_seg_start = seg["start"]
            
            if abs(seg["start"] - limit_l) < 0.05 or (self.playhead_sec > 0 and abs(seg["start"] - self.playhead_sec) < 0.05) or (not self._drag_adj_l and abs(seg["start"] - 0.0) < 0.05):
                self._snap_lines.append(self._x(seg["start"]))
            if abs(seg["end"] - limit_r) < 0.05 or (self.playhead_sec > 0 and abs(seg["end"] - self.playhead_sec) < 0.05) or (not self._drag_adj_r and abs(seg["end"] - self.total_duration) < 0.05):
                self._snap_lines.append(self._x(seg["end"]))

        self.gap_segments = _build_gaps(self.segments, self.total_duration); self.update()