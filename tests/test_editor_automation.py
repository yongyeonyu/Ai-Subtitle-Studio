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


class _FakeRect:
    def __init__(self, x, y, width, height):
        self._x = int(x)
        self._y = int(y)
        self._width = int(width)
        self._height = int(height)

    def x(self):
        return self._x

    def y(self):
        return self._y

    def width(self):
        return self._width

    def height(self):
        return self._height

    def right(self):
        return self._x + self._width - 1

    def bottom(self):
        return self._y + self._height - 1


class _FakeWidget:
    def __init__(self, x=1, y=2, width=30, height=40, *, visible=True, enabled=True):
        self._rect = _FakeRect(x, y, width, height)
        self._visible = bool(visible)
        self._enabled = bool(enabled)

    def geometry(self):
        return self._rect

    def isVisible(self):
        return self._visible

    def isEnabled(self):
        return self._enabled


class _FakeSplitter(_FakeWidget):
    def __init__(self, sizes):
        super().__init__(width=sum(sizes), height=40)
        self._sizes = list(sizes)

    def sizes(self):
        return list(self._sizes)


class _FakeCanvas:
    def __init__(self):
        self.total_duration = 4.0
        self.playhead_sec = 1.5
        self.active_seg_line = None
        self.active_seg_start = None
        self.segments = [
            {"line": 0, "start": 0.0, "end": 1.0, "text": "첫째 줄"},
            {"line": 1, "start": 1.0, "end": 3.0, "text": "둘째 줄"},
        ]
        self._edit_active = False
        self._inline_editor = None
        self._pending_split_sec = None
        self.committed_cursor = None
        self.reject_split_start = False

    def start_inline_edit(self, line, start, *, split_at_playhead=False):
        self.active_seg_line = int(line)
        self.active_seg_start = float(start)
        if split_at_playhead and self.reject_split_start:
            return
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


def test_smart_split_moves_from_tiny_fragment_to_nearest_splittable_segment():
    editor = _FakeEditor()
    editor._segments = [
        {"line": 0, "start": 0.0, "end": 0.04, "text": "짧음"},
        {"line": 1, "start": 1.0, "end": 3.0, "text": "충분히 긴 자막"},
    ]
    editor.timeline.canvas.playhead_sec = 0.02

    result = editor.automation_begin_smart_split_at_playhead(line=0)

    assert result["line"] == 1
    assert result["selection_source"] == "nearest_splittable_fallback"
    assert result["split_sec"] == 2.0
    assert editor.timeline.canvas.active_seg_line == 1


def test_smart_split_recovers_when_playhead_is_outside_all_segments():
    editor = _FakeEditor()
    editor.timeline.canvas.playhead_sec = 9.0

    result = editor.automation_begin_smart_split_at_playhead(at_playhead=True)

    assert result["line"] == 1
    assert result["selection_source"] == "nearest_splittable_fallback"
    assert result["split_sec"] == 2.0


def test_smart_split_uses_canvas_line_when_editor_line_drifted():
    editor = _FakeEditor()
    editor._segments = [
        {"line": 1, "start": 1.0, "end": 3.0, "text": "둘째 줄"},
    ]
    editor.timeline.canvas.segments = [
        {"line": 40, "start": 4.0, "end": 5.0, "text": "다른 줄"},
        {"line": 42, "start": 1.0, "end": 3.0, "text": "둘째 줄"},
    ]

    result = editor.automation_begin_smart_split_at_playhead(line=1)

    assert result["line"] == 1
    assert editor.timeline.canvas.active_seg_line == 42
    assert editor.timeline.canvas.active_seg_start == 1.0
    assert result["split_sec"] == 1.5


def test_smart_split_recovers_when_canvas_rejects_split_mode_entry():
    editor = _FakeEditor()
    editor.timeline.canvas.reject_split_start = True

    result = editor.automation_begin_smart_split_at_playhead(line=1)

    assert result["line"] == 1
    assert editor.timeline.canvas.active_seg_line == 1
    assert editor.timeline.canvas._edit_active is True
    assert editor.timeline.canvas._pending_split_sec == 1.5


def test_set_playhead_syncs_active_segment_to_target_time():
    editor = _FakeEditor()
    editor.timeline.canvas.active_seg_line = 0
    editor.timeline.canvas.active_seg_start = 0.0

    result = editor.automation_set_playhead(1.5)

    assert result["playhead_sec"] == 1.5
    assert editor.timeline.canvas.playhead_sec == 1.5
    assert editor.timeline.canvas.active_seg_line == 1
    assert editor.timeline.canvas.active_seg_start == 1.0
    assert result["editor_runtime"]["active_segment"]["line"] == 1
    assert result["editor_runtime"]["active_segment"]["text"] == "둘째 줄"


def test_geometry_snapshot_serializes_widget_rects_for_source_app_proof():
    editor = _FakeEditor()
    editor.video_frame = _FakeWidget(10, 20, 300, 170)
    editor.timeline_frame = _FakeWidget(10, 200, 300, 120)
    editor.splitter = _FakeSplitter([180, 300])

    snapshot = editor.automation_editor_state_snapshot()

    assert snapshot["geometry"]["video_frame"]["width"] == 300
    assert snapshot["geometry"]["video_frame"]["bottom"] == 189
    assert snapshot["geometry"]["timeline_frame"]["y"] == 200
    assert snapshot["geometry"]["editor_splitter_sizes"] == [180, 300]
