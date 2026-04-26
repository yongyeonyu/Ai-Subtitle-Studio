# Version: 02.03.00
# Phase: PHASE1-B
"""
ui/editor/undo_manager.py
[v02.02.01]
- Extend snapshot to include multiclip structure for clip add/delete/reorder undo/redo.
"""
from __future__ import annotations

from dataclasses import dataclass
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QTextCursor
from ui.editor.subtitle_text_edit import SubtitleBlockData


@dataclass
class SnapshotState:
    blocks: list
    canvas_end_map: dict
    cursor_line: int
    multiclip_files: list
    multiclip_boundaries: list
    project_boundary_times: list
    active_clip_idx: int


class UndoManager:
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

    def push(self):
        if self._is_restoring:
            return
        self._debounce.start()

    def push_immediate(self):
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

        owner = editor.window() if hasattr(editor, 'window') else None
        multiclip_files = list(getattr(owner, '_multiclip_files', []) or []) if owner else []
        multiclip_boundaries = [dict(x) for x in list(getattr(owner, '_multiclip_boundaries', []) or [])] if owner else []
        project_boundary_times = list(getattr(owner, '_project_boundary_times', []) or []) if owner else []
        active_clip_idx = int(getattr(editor.timeline.canvas, '_active_clip_idx', getattr(owner, '_active_clip_idx', 0)) or 0) if hasattr(editor, 'timeline') else 0
        cursor_line = editor.text_edit.textCursor().blockNumber()
        return SnapshotState(blocks, canvas_end_map, cursor_line, multiclip_files, multiclip_boundaries, project_boundary_times, active_clip_idx)

    def _restore(self, state: SnapshotState):
        self._is_restoring = True
        editor = self._editor
        owner = editor.window() if hasattr(editor, 'window') else None
        doc = editor.text_edit.document()
        doc.blockSignals(True)
        editor.text_edit.blockSignals(True)

        cur = QTextCursor(doc)
        cur.beginEditBlock()
        cur.select(QTextCursor.SelectionType.Document)
        cur.removeSelectedText()
        for i, (text, spk_id, start_sec, is_gap) in enumerate(state.blocks):
            if i > 0:
                cur.insertText('\n')
            cur.insertText(text)
            cur.block().setUserData(SubtitleBlockData(spk_id, start_sec, is_gap))
        cur.endEditBlock()

        if owner is not None:
            owner._multiclip_files = list(state.multiclip_files)
            owner._multiclip_boundaries = [dict(x) for x in state.multiclip_boundaries]
            owner._project_boundary_times = list(state.project_boundary_times)
            owner._active_clip_idx = int(state.active_clip_idx)
            if hasattr(editor, '_apply_multiclip_state_from_owner'):
                try:
                    editor._apply_multiclip_state_from_owner()
                except Exception:
                    pass

        cursor_block = doc.findBlockByNumber(state.cursor_line)
        if cursor_block.isValid():
            editor.text_edit.setTextCursor(QTextCursor(cursor_block))

        doc.blockSignals(False)
        editor.text_edit.blockSignals(False)
        if hasattr(editor.text_edit, 'update_margins'):
            editor.text_edit.update_margins()
        if hasattr(editor.text_edit, 'timestampArea'):
            editor.text_edit.timestampArea.update()
        if hasattr(editor, '_schedule_timeline'):
            editor._schedule_timeline()
        self._is_restoring = False

    @staticmethod
    def _is_same(a: SnapshotState, b: SnapshotState) -> bool:
        return (
            a.blocks == b.blocks and
            a.canvas_end_map == b.canvas_end_map and
            a.multiclip_files == b.multiclip_files and
            a.multiclip_boundaries == b.multiclip_boundaries and
            a.project_boundary_times == b.project_boundary_times and
            a.active_clip_idx == b.active_clip_idx
        )
