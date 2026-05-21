from ui.editor.editor_automation import EditorAutomationMixin


class _FakeCursor:
    def __init__(self):
        self._position = 0

    def setPosition(self, value):
        self._position = int(value)

    def position(self):
        return int(self._position)


class _FakeInlineEditor:
    def __init__(self, text):
        self._text = str(text)
        self._cursor = _FakeCursor()

    def toPlainText(self):
        return self._text

    def textCursor(self):
        return self._cursor

    def setTextCursor(self, cursor):
        self._cursor = cursor

    def setFocus(self):
        return None


class _FakeCanvas:
    def __init__(self):
        self.total_duration = 4.0
        self.playhead_sec = 1.5
        self.active_seg_line = None
        self.active_seg_start = None
        self._edit_active = False
        self._inline_editor = None
        self._pending_split_sec = None
        self.committed_cursor = None

    def start_inline_edit(self, line, start, *, split_at_playhead=False):
        self.active_seg_line = int(line)
        self.active_seg_start = float(start)
        self._edit_active = True
        self._pending_split_sec = float(self.playhead_sec) if split_at_playhead else None
        self._inline_editor = _FakeInlineEditor("둘째 줄")

    def _commit_inline_edit_or_split(self):
        self.committed_cursor = self._inline_editor.textCursor().position()
        self._edit_active = False
        self._pending_split_sec = None


class _FakeTimeline:
    def __init__(self, canvas):
        self.canvas = canvas

    def set_active(self, start):
        self.canvas.active_seg_start = float(start)

    def center_to_sec(self, _sec, smooth=False):
        return None

    def set_playhead(self, sec):
        self.canvas.playhead_sec = float(sec)


class _FakeEditor(EditorAutomationMixin):
    def __init__(self):
        self._segments = [
            {"line": 0, "start": 0.0, "end": 1.0, "text": "첫째 줄"},
            {"line": 1, "start": 1.0, "end": 3.0, "text": "둘째 줄"},
        ]
        self.timeline = _FakeTimeline(_FakeCanvas())

    def _get_current_segments(self, force_rebuild=False):
        return list(self._segments)


def test_inline_cursor_restores_last_smart_split_request_after_layout_reset():
    editor = _FakeEditor()
    editor.automation_begin_smart_split_at_playhead(line=1)

    editor.timeline.canvas._edit_active = False
    editor.timeline.canvas._inline_editor = None
    editor.timeline.canvas.playhead_sec = 0.0

    result = editor.automation_set_inline_edit_cursor(2)

    assert result["cursor"] == 2
    assert result["editor_runtime"]["inline_edit_active"] is True
    assert result["editor_runtime"]["inline_edit_cursor"] == 2
    assert editor.timeline.canvas.playhead_sec == 1.5


def test_inline_commit_restores_last_cursor_after_layout_reset():
    editor = _FakeEditor()
    editor.automation_begin_smart_split_at_playhead(line=1)
    editor.automation_set_inline_edit_cursor(2)

    editor.timeline.canvas._edit_active = False
    editor.timeline.canvas._inline_editor = None

    result = editor.automation_commit_inline_edit()

    assert result["editor_runtime"]["inline_edit_active"] is False
    assert editor.timeline.canvas.committed_cursor == 2
