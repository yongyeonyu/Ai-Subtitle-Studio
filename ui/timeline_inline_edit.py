# Version: 02.02.00
# Phase: PHASE1-B
"""
ui/timeline_inline_edit.py
Timeline inline edit mixin
"""
import threading

from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtGui import QFont, QFontMetrics

import config
from ui.timeline_constants import HANDLE_R, SEG_BOT, SEG_TOP


class TimelineInlineEditMixin:
    def start_inline_edit(self, line_num, start_sec):
        self.active_seg_start = start_sec

        seg = next((s for s in self.segments if s.get("line") == line_num), None)
        if not seg:
            return

        text = seg.get("text", "")

        self._edit_active = True
        self._edit_line = line_num
        self._edit_text = text
        self._edit_orig = text

        click_x = getattr(self, "_last_click_x", None)
        click_y = getattr(self, "_last_click_y", None)

        if click_x is not None and click_y is not None:
            text_start_x = self._x(seg["start"]) + HANDLE_R + 6
            rel_x = click_x - text_start_x
            rel_y = click_y - (SEG_TOP + 5)

            fm = QFontMetrics(QFont(config.FONT, 14))
            line_h = fm.height() + 4
            lines = text.split("\n")

            click_line = max(0, int(rel_y / line_h))
            if click_line >= len(lines):
                click_line = len(lines) - 1

            target_line_text = lines[click_line]

            if rel_x <= 0:
                cursor_col = 0
            else:
                cursor_col = len(target_line_text)
                for i in range(1, len(target_line_text) + 1):
                    if fm.horizontalAdvance(target_line_text[:i]) > rel_x:
                        w_prev = fm.horizontalAdvance(target_line_text[: i - 1])
                        w_curr = fm.horizontalAdvance(target_line_text[:i])
                        cursor_col = i - 1 if (rel_x - w_prev) < (w_curr - rel_x) else i
                        break

            self._edit_cursor = sum(len(line) + 1 for line in lines[:click_line]) + cursor_col
            self._last_click_x = None
            self._last_click_y = None
        else:
            self._edit_cursor = len(text)

        self._cursor_vis = True
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

        if not self._edit_text.strip():
            line = self._edit_line
            self._end_inline_edit()
            self.seg_to_gap.emit(line)
            return

        safe_for_editor = self._edit_text.replace("\n", "\u2028")
        line = self._edit_line

        for seg in self.segments:
            if seg.get("line") == line:
                seg["text"] = self._edit_text
                break

        self.sig_inline_text_changed.emit(line, safe_for_editor)

        if hasattr(self, "_pending_split_sec"):
            del self._pending_split_sec

        self._end_inline_edit()

    def _end_inline_edit(self):
        self._edit_active = False
        self._edit_line = -1
        self._edit_text = ""
        self._edit_orig = ""
        self._cursor_timer.stop()
        self.sig_editing_mode.emit(False)
        self.update()
        self.setFocus()

    def _handle_edit_key(self, ev):
        key = ev.key()
        text = self._edit_text
        cur = self._edit_cursor
        mods = ev.modifiers()

        def _row_col(value, cursor):
            lines = value.split("\n")
            row = 0
            col = cursor

            for i, line in enumerate(lines):
                if col <= len(line):
                    row = i
                    break
                col -= len(line) + 1
            else:
                row = len(lines) - 1
                col = max(0, col)

            return row, col, lines

        if mods & (Qt.KeyboardModifier.MetaModifier | Qt.KeyboardModifier.ControlModifier):
            if key == Qt.Key.Key_Left:
                self._edit_cursor = 0
                self._cursor_vis = True
                self.update()
                return
            if key == Qt.Key.Key_Right:
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
                    self.sig_split_request.emit(
                        int(self._edit_line),
                        float(self._pending_split_sec),
                        int(self._edit_cursor),
                    )
                    del self._pending_split_sec
                    self._end_inline_edit()
                    return

                self._commit_inline_edit()
                return

        elif key == Qt.Key.Key_Escape:
            self._edit_text = self._edit_orig
            self._end_inline_edit()
            return

        elif key == Qt.Key.Key_Backspace:
            if cur > 0:
                self._edit_text = text[: cur - 1] + text[cur:]
                self._edit_cursor = cur - 1

        elif key == Qt.Key.Key_Delete:
            if cur < len(text):
                self._edit_text = text[:cur] + text[cur + 1 :]

        elif key == Qt.Key.Key_Left:
            self._edit_cursor = max(0, cur - 1)

        elif key == Qt.Key.Key_Right:
            self._edit_cursor = min(len(self._edit_text), cur + 1)

        elif key == Qt.Key.Key_Up:
            row, col, lines = _row_col(text, cur)
            if row > 0:
                self._edit_cursor = sum(len(line) + 1 for line in lines[: row - 1]) + min(col, len(lines[row - 1]))
            else:
                self._edit_cursor = 0

        elif key == Qt.Key.Key_Down:
            row, col, lines = _row_col(text, cur)
            if row < len(lines) - 1:
                self._edit_cursor = sum(len(line) + 1 for line in lines[: row + 1]) + min(col, len(lines[row + 1]))
            else:
                self._edit_cursor = len(text)

        elif key == Qt.Key.Key_Home:
            row, _, lines = _row_col(text, cur)
            self._edit_cursor = sum(len(line) + 1 for line in lines[:row])

        elif key == Qt.Key.Key_End:
            row, _, lines = _row_col(text, cur)
            self._edit_cursor = sum(len(line) + 1 for line in lines[:row]) + len(lines[row])

        elif key == Qt.Key.Key_Space:
            self._edit_text = text[:cur] + " " + text[cur:]
            self._edit_cursor = cur + 1

        else:
            ch = ev.text()
            if ch and ch.isprintable():
                self._edit_text = text[:cur] + ch + text[cur:]
                self._edit_cursor = cur + len(ch)

        if self._edit_text.strip():
            for seg in self.segments:
                if seg.get("line") == self._edit_line:
                    seg["text"] = self._edit_text
                    break

            safe_text = self._edit_text.replace("\n", "\u2028")
            self.sig_inline_text_changed.emit(self._edit_line, safe_text)

        self._cursor_vis = True
        self.update()

    def _cancel_inline_edit(self):
        if not self._edit_active:
            return

        for seg in self.segments:
            if seg.get("line") == self._edit_line:
                seg["text"] = self._edit_orig
                break

        safe_orig = self._edit_orig.replace("\n", "\u2028")
        self.sig_inline_text_changed.emit(self._edit_line, safe_orig)

        if hasattr(self, "_pending_split_sec"):
            del self._pending_split_sec

        self._end_inline_edit()

    def inputMethodEvent(self, ev):
        if not self._edit_active:
            super().inputMethodEvent(ev)
            return

        commit = ev.commitString()
        preedit = ev.preeditString()
        self._ime_preedit = preedit

        if commit:
            cur = self._edit_cursor
            self._edit_text = self._edit_text[:cur] + commit + self._edit_text[cur:]
            self._edit_cursor = cur + len(commit)

            actual = self._edit_text.replace(" / ", "\n")
            for seg in self.segments:
                if seg.get("line") == self._edit_line:
                    seg["text"] = actual
                    break

            safe_text = actual.replace("\n", "\u2028")
            self.sig_inline_text_changed.emit(self._edit_line, safe_text)

        self._cursor_vis = True
        self.update()

    def inputMethodQuery(self, query):
        from PyQt6.QtCore import Qt as _Qt

        if self._edit_active and query == _Qt.InputMethodQuery.ImCursorRectangle:
            seg = next((s for s in self.segments if s.get("line") == self._edit_line), None)
            if seg:
                return QRect(self._x(seg["start"]), SEG_TOP + 5, 1, 20)

        return super().inputMethodQuery(query)

    def _show_mic_menu(self, gpos):
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

                text = recognizer.recognize_google(audio, language="ko-KR")
                if text and text.strip():
                    self.sig_speech_result.emit(text.strip())

            except Exception:
                pass
            finally:
                self._is_listening = False
                QTimer.singleShot(0, self.update)

        threading.Thread(target=_listen, daemon=True).start()

    def _stop_listening(self):
        self._is_listening = False
        self.update()

    def _on_speech_result(self, text):
        if not self._edit_active:
            return

        cur = self._edit_cursor
        self._edit_text = self._edit_text[:cur] + text + self._edit_text[cur:]
        self._edit_cursor = cur + len(text)

        for seg in self.segments:
            if seg.get("line") == self._edit_line:
                seg["text"] = self._edit_text
                break

        safe_text = self._edit_text.replace("\n", "\u2028")
        self.sig_inline_text_changed.emit(self._edit_line, safe_text)
        self._cursor_vis = True
        self.update()