# Version: 03.14.31
# Phase: PHASE2
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel, QTextEdit

from core.audio.live_stt import LiveSTTResult
from ui.editor.editor_stt_mode import EditorSTTModeMixin
from ui.editor.subtitle_text_edit import SubtitleBlockData


class _FakeMicSession(QObject):
    waveform_changed = pyqtSignal(object)
    finished = pyqtSignal(str, bool, str, float)
    last_instance = None

    def __init__(self, parent=None, **_kwargs):
        super().__init__(parent)
        self.started = False
        self.stopped = False
        _FakeMicSession.last_instance = self

    def start(self):
        self.started = True
        return True

    def stop(self):
        self.stopped = True


class _CanvasStub:
    def __init__(self):
        self.begin_calls = []
        self.waveform_updates = []
        self.end_calls = 0
        self._is_listening = False

    def begin_mic_visualization(self, line_num=None):
        self._is_listening = True
        self.begin_calls.append(line_num)

    def update_mic_visualization(self, samples):
        self.waveform_updates.append(list(samples or []))

    def end_mic_visualization(self):
        self._is_listening = False
        self.end_calls += 1

    def update(self):
        pass


class _DummyEditor(EditorSTTModeMixin, QObject):
    sig_live_stt_result = pyqtSignal(str)
    sig_stt_vad_segments = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.status_lbl = QLabel()
        self.timeline = SimpleNamespace(canvas=_CanvasStub())
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText("대기")
        block = self.text_edit.document().findBlockByNumber(0)
        block.setUserData(SubtitleBlockData("00", 0.0, stt_mode=True, stt_pending=True))
        self._stt_applied_texts = []
        self._mark_dirty_called = 0
        self._refresh_calls = 0
        self._video_context_refreshes = 0
        self.settings = {"stt_mode_text_input_provider": "desktop_mic_optional"}
        self._init_stt_mode_state()
        self._stt_mode_enabled = True
        self.sig_live_stt_result.connect(self._apply_stt_text_to_current)
        self.sig_live_stt_result.connect(self._capture_text)

    def _capture_text(self, text: str):
        self._stt_applied_texts.append(str(text or ""))

    def _mark_dirty(self):
        self._mark_dirty_called += 1

    def _refresh_stt_visuals(self):
        self._refresh_calls += 1

    def _refresh_video_subtitle_context(self):
        self._video_context_refreshes += 1


class EditorSTTModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_handle_stt_enter_uses_live_mic_session_and_updates_waveform(self):
        editor = _DummyEditor()
        temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_wav.close()
        try:
            with patch(
                "ui.editor.live_microphone_session.LiveMicrophoneSession",
                _FakeMicSession,
            ), patch(
                "core.audio.live_stt.transcribe_wav_file",
                return_value=LiveSTTResult(
                    text="마이크 자막",
                    engine="local-whisper",
                    model="mlx-community/whisper-large-v3-mlx",
                    elapsed=0.42,
                ),
            ):
                editor._handle_stt_enter()

                self.assertTrue(editor._stt_recording)
                self.assertEqual(editor.timeline.canvas.begin_calls, [0])
                self.assertIs(editor._stt_mic_capture_session, _FakeMicSession.last_instance)

                _FakeMicSession.last_instance.waveform_changed.emit([0.1, -0.4, 0.25])
                self.app.processEvents()
                self.assertEqual(editor.timeline.canvas.waveform_updates[-1], [0.1, -0.4, 0.25])

                _FakeMicSession.last_instance.finished.emit(temp_wav.name, True, "", 0.3)
                QTest.qWait(120)
                self.app.processEvents()

                self.assertIn("마이크 자막", editor._stt_applied_texts)
                self.assertFalse(editor._stt_recording)
                self.assertEqual(editor.timeline.canvas.end_calls, 1)
                self.assertEqual(editor.text_edit.toPlainText().strip(), "마이크 자막")
                self.assertIn("STT", editor.status_lbl.text())
                self.assertIn(editor._stt_state, {"finished", "next_segment_ready"})
        finally:
            if os.path.exists(temp_wav.name):
                os.remove(temp_wav.name)
            editor.text_edit.close()
            editor.text_edit.deleteLater()
            editor.status_lbl.deleteLater()
            self.app.processEvents()

    def test_default_enter_confirms_manual_text_without_live_mic(self):
        editor = _DummyEditor()
        editor.settings = {"stt_mode_text_input_provider": "manual"}
        try:
            with patch("ui.editor.live_microphone_session.LiveMicrophoneSession", _FakeMicSession):
                editor._handle_stt_enter()

            self.assertFalse(editor._stt_recording)
            self.assertIsNone(editor._stt_mic_capture_session)
            self.assertEqual(editor.text_edit.toPlainText().strip(), "대기")
            self.assertEqual(editor.text_edit.document().findBlockByNumber(0).userData().stt_pending, False)
        finally:
            editor.text_edit.close()
            editor.text_edit.deleteLater()
            editor.status_lbl.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
