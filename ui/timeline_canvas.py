# Version: 01.00.01
"""
ui/timeline_canvas.py
[v01.00.01 수정사항]
- _end_inline_edit 중복 정의 제거 (버그 수정)
- 웨이브폼 렌더링 개선: 노이즈 컷 0.008, 진폭 ×2.0, VAD 기반 음성 구간 청록색 강조
"""
import numpy as np
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QCursor, QPolygon, QBrush

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
    # 💡 [신규 추가] 플레이헤드 메뉴 요청 시그널 (글로벌 좌표, 클릭된 시간)
    playhead_menu_requested = pyqtSignal(QPoint, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 💡 [신규] 재인식 구간 및 진행률 저장 변수
        self.re_recog_zone = None      # (start_sec, end_sec)
        self.re_recog_progress = None  # 현재 완료된 지점 (sec)
        self.setMinimumHeight(CANVAS_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.focus_mode = "segment"
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self._ime_preedit = ""

        self.pps = 50.0  
        self.segments:     list[dict] = []
        self.gap_segments: list[dict] = []
        self.vad_segments: list[dict] = []
        self.total_duration: float = 0.0
        self.active_seg_start: float | None = None
        self.playhead_sec: float = 0.0
        self._waveform = None

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
        # 💡 [신규 추가] 재인식 구간 시각화를 위한 변수
        self.re_recog_zone = None
        self.re_recog_progress = None

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
            
            # 💡 [핵심] 줄바꿈을 기준으로 텍스트를 나누고 어느 줄을 클릭했는지 계산
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
                        
            # 몇 번째 줄인지까지 더해서 최종 1차원 커서 인덱스 도출
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
        if not self._edit_active: return
        safe_for_editor = self._edit_text.replace("\n", "\u2028") 
        line = self._edit_line
        
        for s in self.segments:
            if s.get("line") == line:
                s["text"] = self._edit_text 
                break
                
        self.sig_inline_text_changed.emit(line, safe_for_editor)
        self._end_inline_edit()

    def _end_inline_edit(self):
        self._edit_active = False; self._edit_line = -1
        self._edit_text = ""; self._edit_orig = ""
        self._cursor_timer.stop()
        self.sig_editing_mode.emit(False)
        self.update(); self.setFocus()
    # ----------------------------------


    # 💡 [여기서부터 수정됨] 인라인 에디터 키보드 제어 (엔터, Shift+Enter, 스페이스)
    def _handle_edit_key(self, ev):
        key  = ev.key(); text = self._edit_text; cur  = self._edit_cursor
        
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                ch = "\n"
                self._edit_text = text[:cur] + ch + text[cur:]
                self._edit_cursor = cur + 1
            else:
                self._commit_inline_edit(); return
        elif key == Qt.Key.Key_Space:
            ch = " "
            self._edit_text = text[:cur] + ch + text[cur:]
            self._edit_cursor = cur + 1
        elif key == Qt.Key.Key_Escape:
            self._cancel_inline_edit(); return
        else:
            # 💡 [핵심] 현재 커서가 몇 번째 줄의 몇 번째 칸인지 계산
            lines = text.split('\n')
            r = 0; c = cur
            for i, line in enumerate(lines):
                if c <= len(line): r = i; break
                c -= (len(line) + 1)

            if key == Qt.Key.Key_Backspace:
                if cur > 0: self._edit_text = text[:cur-1] + text[cur:]; self._edit_cursor = cur - 1
            elif key == Qt.Key.Key_Delete:
                if cur < len(text): self._edit_text = text[:cur] + text[cur+1:]
            elif key == Qt.Key.Key_Left: 
                self._edit_cursor = max(0, cur - 1)
            elif key == Qt.Key.Key_Right: 
                self._edit_cursor = min(len(self._edit_text), cur + 1)
            elif key == Qt.Key.Key_Up: # 💡 윗 줄로 이동
                if r > 0:
                    new_c = min(c, len(lines[r-1]))
                    self._edit_cursor = sum(len(l) + 1 for l in lines[:r-1]) + new_c
                else: self._edit_cursor = 0
            elif key == Qt.Key.Key_Down: # 💡 아랫 줄로 이동
                if r < len(lines) - 1:
                    new_c = min(c, len(lines[r+1]))
                    self._edit_cursor = sum(len(l) + 1 for l in lines[:r+1]) + new_c
                else: self._edit_cursor = len(text)
            elif key == Qt.Key.Key_Home: # 💡 줄 맨 앞으로
                self._edit_cursor = sum(len(l) + 1 for l in lines[:r])
            elif key == Qt.Key.Key_End:  # 💡 줄 맨 뒤로
                self._edit_cursor = sum(len(l) + 1 for l in lines[:r]) + len(lines[r])
            else:
                ch = ev.text()
                if ch and ch.isprintable():
                    self._edit_text = text[:cur] + ch + text[cur:]; self._edit_cursor = cur + len(ch)

        for s in self.segments:
            if s.get("line") == self._edit_line: s["text"] = self._edit_text; break
            
        safe_text = self._edit_text.replace("\n", "\u2028")
        self.sig_inline_text_changed.emit(self._edit_line, safe_text)
        
        self._cursor_vis = True; self.update()
    # ----------------------------------

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
                
            # 🚨 [핵심 방어선] 한글 조합이 끝나고 에디터로 보낼 때도 완벽하게 세탁!
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
        # 💡 [추가] 편집 중일 때는 무조건 모든 키보드 입력을 텍스트 수정으로 넘깁니다.
        if self._edit_active:
            self._handle_edit_key(ev)
            ev.accept()
            return
            
        # 💡 [수정] F2뿐만 아니라 Enter(Return) 키를 눌러도 편집 모드로 진입합니다!
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
        self.vad_segments = vad_segs; self.update()

    def set_active(self, sec: float | None):
        self.active_seg_start = sec; self.update()

    def set_playhead(self, sec):
        if self.playhead_sec == sec: return
        self.playhead_sec = sec; self.update()

    def set_waveform(self, wf: np.ndarray):
        self._waveform = wf; self.update()

    def _x(self, sec: float) -> int: return int(sec * self.pps)
    def total_width(self) -> int: return max(self.width(), int(self.total_duration * self.pps) + self.width())

    def _icon_rect(self, x1: int, x2: int) -> QRect: 
        # 💡 [변경] 자막 상자 맨 아래 테두리(SEG_BOT) 바깥쪽 하단 중앙에 배치합니다.
        return QRect(x1 + (x2 - x1) // 2 - (ICON_SZ // 2), SEG_BOT + 8, ICON_SZ, ICON_SZ)

    def _plus_rect(self, x1: int, x2: int) -> QRect: 
        return QRect(x1 + (x2 - x1) // 2 - (ICON_SZ // 2), SEG_BOT + 8, ICON_SZ, ICON_SZ)

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
        
        # 💡 [아래 코드로 교체하세요]
        total_secs = self.total_duration + 2
        sec_f = 0.0
        
        # 폰트 설정 (여기서 크기를 결정합니다)
        ruler_font = QFont(config.FONT, 12) # 12pt로 시원하게 키웠습니다.
        ruler_font.setBold(True)
        p.setFont(ruler_font)
        
        while sec_f <= total_secs:
            tx = self._x(sec_f); sec_i = sec_f
            if abs(sec_i - round(sec_i, 0)) < 0.01:
                sec_i = round(sec_i)
                if sec_i % 5 == 0 and sec_i != 0:
                    p.setPen(QColor("#BBBBBB")); p.drawLine(tx, 0, tx, 15); p.drawText(tx + 5, RULER_H - 5, f"{int(sec_i)}s")
                elif sec_i % 1 == 0:
                    p.setPen(QColor("#666666")); p.drawLine(tx, 0, tx, 8)
                    if sec_i > 0: p.drawText(tx + 2, RULER_H - 2, f"{int(sec_i)}")
            elif abs(sec_i * 2 - round(sec_i * 2)) < 0.01: p.setPen(QColor("#444444")); p.drawLine(tx, 0, tx, 5)
            else: p.setPen(QColor("#333333")); p.drawLine(tx, 0, tx, 3)
            sec_f = round(sec_f + 0.1, 1)

        # 1. 파형 배경 그리기
        p.fillRect(QRect(0, RULER_H, self.total_width(), WAVE_H), QColor("#0a0a0a"))

        if self._waveform is not None:
            wf = self._waveform
            wf_len = len(wf)

            # A. 0점 가이드 라인
            p.setPen(QPen(QColor("#333333"), 1))
            p.drawLine(0, WAVE_MID, self.total_width(), WAVE_MID)

            # B. VAD 구간별 speech_mask 사전 계산 (음성 구간 강조)
            # 웨이브폼 샘플링: 100 samples/sec
            speech_mask: np.ndarray | None = None
            if self.vad_segments and wf_len > 0:
                speech_mask = np.zeros(wf_len, dtype=bool)
                for vs in self.vad_segments:
                    s_idx = max(0, int(vs["start"] * 100))
                    e_idx = min(wf_len, int(vs["end"]   * 100) + 1)
                    speech_mask[s_idx:e_idx] = True

            for x in range(0, self.total_width(), 1):
                idx = int((x / self.pps) * 100)
                if idx >= wf_len:
                    break
                val = wf[idx]
                if val < 0.008:   # 노이즈 컷 (이전 0.03 → 0.008, 더 디테일)
                    continue

                # 진폭 2.0배 확대 (이전 1.4배)
                h = int(val * WAVE_HALF * 2.0)
                h = min(h, WAVE_HALF - 1)

                # 음성 구간: 밝은 청록 / 비음성 구간: 어두운 회색
                in_speech = (speech_mask is not None and speech_mask[idx])
                if in_speech:
                    top_color = QColor(100, 220, 255)   # 밝은 청록
                    bot_color = QColor( 40, 130, 170)   # 어두운 청록
                    # 매우 큰 진폭(loud)은 더 밝게 강조
                    if val > 0.6:
                        top_color = QColor(160, 255, 255)
                        bot_color = QColor( 80, 180, 210)
                else:
                    top_color = QColor(75, 75, 75)
                    bot_color = QColor(45, 45, 45)

                p.setPen(QPen(top_color, 1))
                p.drawLine(x, WAVE_MID,     x, WAVE_MID - h)
                p.setPen(QPen(bot_color, 1))
                p.drawLine(x, WAVE_MID + 1, x, WAVE_MID + h)

        # 2. VAD 섹터 (기본 배경)
        if self.vad_segments:
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(255, 200, 0, 40)) 
            for vs in self.vad_segments:
                vx1 = self._x(vs["start"]); vx2 = self._x(vs["end"])
                p.drawRect(QRect(vx1, RULER_H, vx2 - vx1, WAVE_H))

        # 💡 [핵심] 3. 재인식 모드 시각화 (초록색 타겟 + 노란색 진행률)
        if self.re_recog_zone:
            rs, re_sec = self.re_recog_zone
            rp = self.re_recog_progress if self.re_recog_progress is not None else rs

            # A. 진행 완료 구역 (노란색)
            yx1 = self._x(rs); yx2 = self._x(rp)
            if yx2 > yx1:
                p.fillRect(QRect(yx1, RULER_H, yx2 - yx1, WAVE_H), QColor(255, 255, 0, 100))

            # B. 남은 타겟 구역 (초록색)
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

            # ui/timeline_canvas.py 의 paintEvent 내 수정 부분
            if is_editing:
                disp_text = self._edit_text
                preedit = getattr(self, '_ime_preedit', '')
                cur = self._edit_cursor
                
                # 한글 조합중인 글자를 렌더링용 텍스트에 임시 삽입
                if preedit:
                    disp_text = disp_text[:cur] + preedit + disp_text[cur:]
                    
                lines = disp_text.split('\n')
                fm = p.fontMetrics()
                line_h = fm.height()
                tx0 = text_rect.x(); ty0 = text_rect.y() + fm.ascent()
                
                p.fillRect(text_rect, QColor("#002200"))
                
                # 시각적 커서 위치 계산
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
                        
                        # 커서 깜빡임 (실제 텍스트 길이 위치에 정확히 그림!)
                        if self._cursor_vis and i == r:
                            cx = tx0 + fm.horizontalAdvance(line[:c])
                            cursor_top = curr_y - fm.ascent()
                            cursor_bot = cursor_top + line_h
                            p.setPen(QPen(QColor("#FFFFFF"), 1))
                            p.drawLine(cx, cursor_top, cx, cursor_bot)
                            
                        curr_y += line_h + 4

            # 💡 [핵심 복구] 편집 중이 아닐 때 일반 자막을 그리는 로직! (이게 빠져있었습니다)
            else:
                p.setPen(QColor("#FFFFFF"))
                # 줄바꿈(\n)이 포함된 다중 줄 텍스트를 평상시에도 예쁘게 출력합니다.
                p.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, seg.get("text", ""))

            # -------------------------------------------------------------
            
            ir = self._icon_rect(x1, x2) # 이 아래로는 기존 코드 그대로 유지!
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
                    
        if self.playhead_sec >= 0:
            ph_color = QColor("#4AFF80") if getattr(self, 'focus_mode', 'segment') == "waveform" else QColor("#FF4444")
            p.setPen(QPen(ph_color, 2)); px = self._x(self.playhead_sec); p.drawLine(px, 0, px, CANVAS_H)
            # 💡 [신규] 플레이헤드 윗부분에 메뉴 호출용 동그란 핸들 그리기
            handle_r = 7
            self._playhead_handle_rect = QRect(int(px - handle_r), 2, handle_r * 2, handle_r * 2)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(QBrush(QColor("#FFCC00")))  # 눈에 잘 띄는 노란색
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

    def mouseDoubleClickEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton: return
        
        if self._edit_active:
            self._commit_inline_edit()
            return
            
        x, y = ev.pos().x(), ev.pos().y()
        self._last_click_x = x
        self._last_click_y = y  # 💡 클릭한 Y좌표(몇 번째 줄인지) 저장
        
        if SEG_TOP <= y <= SEG_BOT:
            seg = next((s for s in self.segments if self._x(s["start"]) <= x <= self._x(s["end"])), None)
            if seg: self.seg_double_clicked.emit(seg.get("line", 0), seg["start"])

    def mousePressEvent(self, ev):
        # 💡 [신규] 플레이헤드 노란색 원 클릭 감지
        if ev.button() == Qt.MouseButton.LeftButton or ev.button() == Qt.MouseButton.RightButton:
            if hasattr(self, '_playhead_handle_rect') and self._playhead_handle_rect.contains(ev.pos()):
                self.playhead_menu_requested.emit(ev.globalPosition().toPoint(), self.playhead_sec)
                return

        x, y = ev.pos().x(), ev.pos().y()

        # 💡 [핵심 수정] 편집 모드일 때 클릭 처리
        if self._edit_active:
            seg = next((s for s in self.segments if s.get("line") == self._edit_line), None)
            
            if seg and SEG_TOP <= y <= SEG_BOT:
                x1, x2 = self._x(seg["start"]), self._x(seg["end"])
                if x1 + HANDLE_R < x < x2 - HANDLE_R:
                    text_start_x = x1 + HANDLE_R + 6
                    rel_x = x - text_start_x
                    rel_y = y - (SEG_TOP + 5)
                    
                    from PyQt6.QtGui import QFontMetrics, QFont
                    import config
                    fm = QFontMetrics(QFont(config.FONT, 14))
                    line_h = fm.height() + 4
                    
                    # 💡 클릭한 줄 높이 계산 적용
                    lines = self._edit_text.split('\n')
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
                    self._cursor_vis = True
                    self.update()
            return

        # --- 아래는 편집 모드가 아닐 때의 기존 로직 ---
        self._just_committed = False     
        self.setFocus() 
        if ev.button() == Qt.MouseButton.RightButton:
            if SEG_TOP <= y <= SEG_BOT:
                seg = self._seg_at(x)
                if seg: self.seg_right_clicked.emit(seg["start"], ev.globalPosition().toPoint())
            return
        if ev.button() != Qt.MouseButton.LeftButton: return

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

    def mouseMoveEvent(self, ev):
        x, y = ev.pos().x(), ev.pos().y()

        # 💡 편집 모드일 때 마우스 커서를 '텍스트 입력(I-Beam)' 모양으로 고정
        if self._edit_active:
            seg = next((s for s in self.segments if s.get("line") == self._edit_line), None)
            if seg and SEG_TOP <= y <= SEG_BOT and self._x(seg["start"]) + HANDLE_R < x < self._x(seg["end"]) - HANDLE_R:
                self.setCursor(Qt.CursorShape.IBeamCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        # --- 아래는 기존 마우스 이동 로직 (편집 아닐 때) ---
        # (기존의 panning, scrubbing, hover_diamond 처리 등 유지)

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
        
        # 💡 [추가] 편집 모드일 때 마우스 커서를 '텍스트 입력(I-Beam)' 모양으로 변경!
        if self._edit_active:
            seg = next((s for s in self.segments if s.get("line") == self._edit_line), None)
            # 마우스가 텍스트 영역(핸들 안쪽)에 있는지 확인
            if seg and SEG_TOP <= y <= SEG_BOT and self._x(seg["start"]) + HANDLE_R < x < self._x(seg["end"]) - HANDLE_R:
                self.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
                return

        # 기존 마우스 모양 로직
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
            if self._drag_adj_l and self._drag_edge in ("square_left", "center"):
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