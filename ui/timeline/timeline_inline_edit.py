# Version: 03.06.20
# Phase: PHASE2
"""
ui/timeline_inline_edit.py
Timeline inline edit mixin
"""
import os
import threading

from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtGui import QFont, QFontMetrics

from core.runtime import config
from ui.timeline.timeline_constants import HANDLE_R, SEG_TOP


NEW_SUBTITLE_PLACEHOLDER = "새자막"


class TimelineInlineEditMixin:
    def _inline_edit_repaint_rect(self, line_num=None) -> QRect:
        line = self._edit_line if line_num is None else line_num
        rect = QRect()
        if hasattr(self, "_segment_repaint_rect_for_line"):
            rect = self._segment_repaint_rect_for_line(int(line), margin=110)
        if getattr(self, "_is_listening", False):
            rect = rect.adjusted(0, 0, 180, 0)
        return rect

    def _update_inline_edit_region(self, line_num=None):
        rect = self._inline_edit_repaint_rect(line_num)
        if hasattr(self, "_update_dirty_rect"):
            self._update_dirty_rect(rect)
        else:
            self.update()

    def start_inline_edit(self, line_num, start_sec):
        old_line = getattr(self, "_edit_line", -1)
        self.active_seg_start = start_sec

        seg = next((s for s in self.segments if s.get("line") == line_num), None)
        if not seg:
            return

        text = seg.get("text", "")
        clear_placeholder = str(text or "").strip() == NEW_SUBTITLE_PLACEHOLDER

        self._edit_active = True
        self._edit_line = line_num
        self._edit_text = "" if clear_placeholder else text
        self._edit_orig = "" if clear_placeholder else text

        if clear_placeholder:
            seg["text"] = ""
            self._inline_commit_in_progress = True
            try:
                self.sig_inline_text_changed.emit(line_num, "")
            finally:
                self._inline_commit_in_progress = False
            text = ""

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
        dirty = self._inline_edit_repaint_rect(line_num)
        if old_line >= 0:
            dirty = dirty.united(self._inline_edit_repaint_rect(old_line))
        if hasattr(self, "_update_dirty_rect"):
            self._update_dirty_rect(dirty)
        else:
            self.update()

    def _blink_cursor(self):
        if self._edit_active:
            self._cursor_vis = not self._cursor_vis
            self._update_inline_edit_region()

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

        self._inline_commit_in_progress = True
        try:
            self.sig_inline_text_changed.emit(line, safe_for_editor)
        finally:
            self._inline_commit_in_progress = False

        if hasattr(self, "_pending_split_sec"):
            del self._pending_split_sec

        self._end_inline_edit()

    def _end_inline_edit(self):
        line = self._edit_line
        self._edit_active = False
        self._edit_line = -1
        self._edit_text = ""
        self._edit_orig = ""
        self._ime_preedit = ""
        self._cursor_vis = False
        self._cursor_timer.stop()
        self.sig_editing_mode.emit(False)
        self._update_inline_edit_region(line)
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
                self._update_inline_edit_region()
                return
            if key == Qt.Key.Key_Right:
                self._edit_cursor = len(self._edit_text)
                self._cursor_vis = True
                self._update_inline_edit_region()
                return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._edit_text = text[:cur] + "\n" + text[cur:]
                self._edit_cursor = cur + 1
            else:
                if hasattr(self, "_pending_split_sec"):
                    safe_text = self._edit_text.replace("\n", "\u2028")
                    self._inline_commit_in_progress = True
                    try:
                        self.sig_inline_text_changed.emit(self._edit_line, safe_text)
                        self.sig_split_request.emit(
                            int(self._edit_line),
                            float(self._pending_split_sec),
                            int(self._edit_cursor),
                        )
                    finally:
                        self._inline_commit_in_progress = False
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
        self._update_inline_edit_region()

    def _cancel_inline_edit(self):
        if not self._edit_active:
            return

        for seg in self.segments:
            if seg.get("line") == self._edit_line:
                seg["text"] = self._edit_orig
                break

        safe_orig = self._edit_orig.replace("\n", "\u2028")
        self._inline_commit_in_progress = True
        try:
            self.sig_inline_text_changed.emit(self._edit_line, safe_orig)
        finally:
            self._inline_commit_in_progress = False

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
        self._update_inline_edit_region()

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
            act = menu.addAction("🎤 음성으로 입력 (고품질)")
            act.triggered.connect(lambda: self._start_listening("quality"))
            fast_act = menu.addAction("⚡ 음성으로 입력 (빠름)")
            fast_act.triggered.connect(lambda: self._start_listening("fast"))

        menu.exec(gpos)

    def _show_speaker_learn_menu(self, line_num, gpos):
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #151C20; color: #F5F7FA; border: 1px solid #2D3942; "
            "font-size: 13px; padding: 4px; } "
            "QMenu::item { padding: 7px 22px 7px 10px; border-radius: 4px; } "
            "QMenu::item:selected { background-color: #1F3A56; }"
        )
        learn_menu = menu.addMenu("음성으로 화자 학습")
        for _spk_i in range(1, 4):
            _act = learn_menu.addAction(f"화자 {_spk_i}")
            _act.triggered.connect(lambda checked=False, idx=_spk_i, ln=line_num: self._learn_speaker_from_segment(idx, ln))
        menu.exec(gpos)

    def _learn_speaker_from_segment(self, spk_idx, line_num=None):
        target_line = self._edit_line if line_num is None else line_num
        seg = next((s for s in self.segments if s.get("line") == target_line), None)
        if not seg:
            return

        import os, subprocess
        from PyQt6.QtWidgets import QInputDialog
        from core.runtime import config
        from core.runtime.logger import get_logger

        start_sec = seg["start"]
        end_sec = seg["end"]
        duration = end_sec - start_sec
        if duration < 0.3:
            get_logger().log("voice learn skipped: segment too short")
            return

        owner_settings = {}
        owner_for_settings = self.parent()
        while owner_for_settings and not hasattr(owner_for_settings, "settings"):
            owner_for_settings = owner_for_settings.parent()
        if owner_for_settings is not None:
            owner_settings = getattr(owner_for_settings, "settings", {}) or {}
        speaker_name = str(owner_settings.get(f"spk{spk_idx}_name", "") or f"화자_{spk_idx}")
        safe_name = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in speaker_name).strip("_") or f"speaker_{spk_idx}"
        default_name = f"spk{spk_idx}_{safe_name}"
        name, ok = QInputDialog.getText(
            self,
            "화자 음성 저장",
            "파일 이름 (확장자 제외):",
            text=default_name,
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        if not name.endswith(".wav"):
            name += ".wav"

        owner = self.parent()
        while owner and not hasattr(owner, "media_path"):
            owner = owner.parent()

        if not owner:
            get_logger().log("voice learn failed: media_path owner not found")
            return

        media_path = getattr(owner, "media_path", "") or ""
        if not media_path:
            get_logger().log("voice learn failed: media_path empty")
            return

        base_name = os.path.splitext(os.path.basename(media_path))[0]
        cleaned_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}_cleaned.wav")
        src = cleaned_wav if os.path.exists(cleaned_wav) else media_path

        voice_dir = getattr(config, "VOICE_DATA_DIR", os.path.join(config.BASE_DIR, "voice_data"))
        os.makedirs(voice_dir, exist_ok=True)
        voice_path = os.path.join(voice_dir, name)

        try:
            proc = subprocess.run(
                [
                    "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
                    "-ss", str(start_sec), "-t", str(duration),
                    "-i", src,
                    "-ac", "1", "-ar", "16000",
                    "-acodec", "pcm_s16le",
                    voice_path,
                ],
                capture_output=True,
                timeout=30,
            )

            if proc.returncode != 0:
                err = (proc.stderr or b"").decode("utf-8", errors="ignore") if isinstance(proc.stderr, (bytes, bytearray)) else str(proc.stderr or "")
                get_logger().log(f"voice learn failed spk{spk_idx}: {err[:300]}")
                return

            if not os.path.exists(voice_path) or os.path.getsize(voice_path) <= 0:
                get_logger().log(f"voice learn failed spk{spk_idx}: wav not created -> {voice_path}")
                return

            get_logger().log(f"voice learned spk{spk_idx}: {name} ({duration:.1f}s) -> {voice_path}")

        except Exception as e:
            get_logger().log(f"voice learn failed spk{spk_idx}: {e}")

    def _start_listening(self, profile="quality"):
        if self._is_listening:
            return

        self._is_listening = True
        self._speech_stop_requested = False
        session = None
        try:
            from ui.editor.live_microphone_session import LiveMicrophoneSession

            session = LiveMicrophoneSession(self)
        except Exception as e:
            self._is_listening = False
            from core.runtime.logger import get_logger
            get_logger().log(f"⚠️ 마이크 캡처 초기화 실패: {e}")
            self._update_inline_edit_region()
            return
        self._mic_capture_session = session
        if hasattr(self, "begin_mic_visualization"):
            self.begin_mic_visualization(getattr(self, "_edit_line", None))
        session.waveform_changed.connect(self.update_mic_visualization if hasattr(self, "update_mic_visualization") else (lambda _samples: None))
        self._update_inline_edit_region()

        def _listen(captured_wav: str, has_audio: bool, error_text: str, _elapsed: float):
            try:
                from core.audio.live_stt import transcribe_wav_file
                from core.runtime.logger import get_logger

                if not has_audio or not captured_wav:
                    if error_text:
                        get_logger().log(f"⚠️ 마이크 STT 실패: {error_text}")
                    return
                result = transcribe_wav_file(captured_wav, profile=profile)
                if result.text:
                    get_logger().log(
                        f"🎙️ 마이크 STT 완료: {result.engine} / {result.model} / {result.elapsed:.1f}s"
                    )
                    self.sig_speech_result.emit(result.text)
                else:
                    get_logger().log("🎙️ 마이크 STT 결과 없음")

            except Exception as e:
                try:
                    from core.runtime.logger import get_logger
                    get_logger().log(f"⚠️ 마이크 STT 실패: {e}")
                except Exception:
                    pass
            finally:
                try:
                    if captured_wav and os.path.exists(captured_wav):
                        os.remove(captured_wav)
                except Exception:
                    pass
                self._is_listening = False
                self._speech_stop_requested = False
                def _cleanup():
                    self._mic_capture_session = None
                    if hasattr(self, "end_mic_visualization"):
                        self.end_mic_visualization()
                    self._update_inline_edit_region()
                QTimer.singleShot(0, _cleanup)

        def _on_capture_finished(captured_wav: str, has_audio: bool, error_text: str, elapsed: float):
            threading.Thread(
                target=_listen,
                args=(captured_wav, has_audio, error_text, elapsed),
                daemon=True,
                name="timeline-inline-mic-transcribe",
            ).start()

        session.finished.connect(_on_capture_finished)
        if not session.start():
            self._is_listening = False
            self._speech_stop_requested = False
            self._mic_capture_session = None
            if hasattr(self, "end_mic_visualization"):
                self.end_mic_visualization()
            self._update_inline_edit_region()

    def _stop_listening(self):
        self._speech_stop_requested = True
        session = getattr(self, "_mic_capture_session", None)
        if session is not None and hasattr(session, "stop"):
            session.stop()
            return
        self._is_listening = False
        if hasattr(self, "end_mic_visualization"):
            self.end_mic_visualization()
        self._update_inline_edit_region()

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
        self._update_inline_edit_region()
