# Version: 02.02.00
# Phase: PHASE1-B
"""
ui/undo_manager.py
[v01.00.01 수정사항]
- _restore: canvas_end_map 복원, 커서 위치 복원, 시그널 해제, UI 갱신 로직 완성
"""
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QTextCursor
from ui.editor.subtitle_text_edit import SubtitleBlockData


class SnapshotState:
    """
    단일 스냅샷.
    blocks: list of (text, spk_id, start_sec, is_gap)
    canvas_end_map: {line_num: end_sec}
    cursor_line: int
    """
    __slots__ = ('blocks', 'canvas_end_map', 'cursor_line')

    def __init__(self, blocks, canvas_end_map, cursor_line):
        self.blocks = blocks
        self.canvas_end_map = canvas_end_map
        self.cursor_line = cursor_line


class UndoManager:
    """
    EditorWidget에 합성(Composition)되어 동작하는 실행취소 관리자.
    editor_widget.__init__에서 self._undo_mgr = UndoManager(self) 로 생성.
    """
    MAX_STACK = 50

    def __init__(self, editor):
        self._editor = editor
        self._undo_stack: list[SnapshotState] = []
        self._redo_stack: list[SnapshotState] = []
        self._is_restoring = False

        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(500)
        self._debounce.timeout.connect(self._do_push)

    # ── Public API ─────────────────────────────────────────────────────────

    def push(self):
        """일반 변경 시 호출 — 500ms debounce 후 저장"""
        if self._is_restoring:
            return
        self._debounce.start()

    def push_immediate(self):
        """드래그 시작처럼 즉시 저장이 필요한 경우"""
        if self._is_restoring:
            return
        self._debounce.stop()
        self._do_push()

    def undo(self):
        if not self._undo_stack:
            return
        current = self._capture()
        self._redo_stack.append(current)
        state = self._undo_stack.pop()
        self._restore(state)

    def redo(self):
        if not self._redo_stack:
            return
        current = self._capture()
        self._undo_stack.append(current)
        state = self._redo_stack.pop()
        self._restore(state)

    # ── Internal ───────────────────────────────────────────────────────────

    def _do_push(self):
        if self._is_restoring:
            return
        state = self._capture()
        if self._undo_stack and self._is_same(self._undo_stack[-1], state):
            return
        self._undo_stack.append(state)
        if len(self._undo_stack) > self.MAX_STACK:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _capture(self) -> SnapshotState:
        """현재 text_edit 블록 + canvas end 시간을 캡처"""
        editor = self._editor
        doc = editor.text_edit.document()

        blocks = []
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            ud = block.userData()
            if isinstance(ud, SubtitleBlockData):
                blocks.append((block.text(), ud.spk_id, ud.start_sec, ud.is_gap))
            else:
                blocks.append((block.text(), '00', 0.0, False))

        canvas_end_map = {}
        if hasattr(editor, 'timeline') and hasattr(editor.timeline, 'canvas'):
            for seg in editor.timeline.canvas.segments:
                line = seg.get('line', -1)
                if line >= 0 and 'end' in seg:
                    canvas_end_map[line] = seg['end']

        cursor_line = editor.text_edit.textCursor().blockNumber()
        return SnapshotState(blocks, canvas_end_map, cursor_line)

    def _restore(self, state: SnapshotState):
        """스냅샷 복원"""
        self._is_restoring = True
        editor = self._editor
        doc = editor.text_edit.document()

        # 시그널 차단
        doc.blockSignals(True)
        editor.text_edit.blockSignals(True)

        cur = QTextCursor(doc)
        cur.beginEditBlock()
        cur.select(QTextCursor.SelectionType.Document)
        cur.removeSelectedText()

        for i, (text, spk_id, start_sec, is_gap) in enumerate(state.blocks):
            if i > 0:
                cur.insertText('\n')
            # \u2028이 포함된 text를 통째로 삽입 — 블록이 쪼개지지 않음
            cur.insertText(text)
            cur.block().setUserData(SubtitleBlockData(spk_id, start_sec, is_gap))

        cur.endEditBlock()

        # ── canvas end 시간 복원 ──────────────────────────────────────
        if hasattr(editor, 'timeline') and hasattr(editor.timeline, 'canvas'):
            for seg in editor.timeline.canvas.segments:
                line = seg.get('line', -1)
                if line in state.canvas_end_map:
                    seg['end'] = state.canvas_end_map[line]

        # ── 커서 위치 복원 ────────────────────────────────────────────
        cursor_block = doc.findBlockByNumber(state.cursor_line)
        if cursor_block.isValid():
            restore_cursor = QTextCursor(cursor_block)
            editor.text_edit.setTextCursor(restore_cursor)

        # ── 시그널 해제 ──────────────────────────────────────────────
        doc.blockSignals(False)
        editor.text_edit.blockSignals(False)

        # ── UI 갱신 ──────────────────────────────────────────────────
        if hasattr(editor.text_edit, 'update_margins'):
            editor.text_edit.update_margins()
        if hasattr(editor.text_edit, 'timestampArea'):
            editor.text_edit.timestampArea.update()
        if hasattr(editor, '_schedule_timeline'):
            editor._schedule_timeline()

        self._is_restoring = False

    @staticmethod
    def _is_same(a: SnapshotState, b: SnapshotState) -> bool:
        return a.blocks == b.blocks and a.canvas_end_map == b.canvas_end_map
