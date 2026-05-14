"""Low-level block targeting and playhead surgery helpers for editor segments."""

from __future__ import annotations

from ui.editor.editor_helpers import insert_gap_after
from ui.editor.subtitle_text_edit import SubtitleBlockData


class EditorSegmentsBlockSurgeryMixin:
    def _subtitle_segment_edit_target_block(self):
        doc = getattr(getattr(self, "text_edit", None), "document", lambda: None)()
        if doc is None:
            return None

        def _editable_block(block):
            if block is None or not block.isValid():
                return None
            data = block.userData()
            if isinstance(data, SubtitleBlockData) and not data.is_gap:
                return block
            return None

        canvas = getattr(getattr(self, "timeline", None), "canvas", None)
        active_line = getattr(canvas, "active_seg_line", None) if canvas is not None else None
        if active_line is not None:
            block = _editable_block(doc.findBlockByNumber(int(active_line)))
            if block is not None:
                return block

        active_start = getattr(canvas, "active_seg_start", None) if canvas is not None else None
        if active_start is not None:
            try:
                target_start = float(active_start)
            except Exception:
                target_start = None
            if target_start is not None:
                rows = list(getattr(self, "_cached_segs", None) or [])
                if not rows and hasattr(self, "_get_current_segments"):
                    try:
                        rows = list(self._get_current_segments())
                    except Exception:
                        rows = []
                for seg in rows:
                    if not isinstance(seg, dict) or seg.get("is_gap"):
                        continue
                    try:
                        start = float(seg.get("start", 0.0) or 0.0)
                        line = int(seg.get("line", -1))
                    except Exception:
                        continue
                    if abs(start - target_start) < 0.05 and line >= 0:
                        block = _editable_block(doc.findBlockByNumber(line))
                        if block is not None:
                            return block

        cursor = getattr(self.text_edit, "textCursor", lambda: None)()
        block = cursor.block() if cursor is not None else None
        return _editable_block(block)

    def _frame_time(self, sec: float) -> float:
        if hasattr(self, "_snap_to_frame"):
            return self._snap_to_frame(sec)
        return round(float(sec), 6)

    def _contiguous_segment_first_block(self, block, *, start_sec: float):
        first_block = block
        while first_block.previous().isValid():
            prev_data = first_block.previous().userData()
            if isinstance(prev_data, SubtitleBlockData) and not prev_data.is_gap and abs(float(prev_data.start_sec) - start_sec) < 0.05:
                first_block = first_block.previous()
            else:
                break
        return first_block

    def _contiguous_segment_last_block(self, block, *, start_sec: float):
        last_block = block
        while True:
            nxt = last_block.next()
            if nxt.isValid():
                next_data = nxt.userData()
                if isinstance(next_data, SubtitleBlockData) and not next_data.is_gap and abs(float(next_data.start_sec) - start_sec) < 0.05:
                    last_block = nxt
                    continue
            break
        return last_block

    def _finish_block_surgery_edit(self, cursor) -> None:
        if hasattr(self.text_edit, "update_margins"):
            self.text_edit.update_margins()
        cursor.endEditBlock()
        if hasattr(self.text_edit, "timestampArea"):
            self.text_edit.timestampArea.update()
        self._redraw_timeline()

    def _set_segment_start_to_playhead(self):
        self._undo_mgr.push_immediate()
        sec = self._snap_to_frame(getattr(self.timeline.canvas, "playhead_sec", getattr(self.video_player, "current_time", 0.0)))
        block = self._subtitle_segment_edit_target_block()
        if block is None:
            return
        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or ud.is_gap:
            return

        orig_start = float(ud.start_sec)
        cursor = self.text_edit.textCursor()
        cursor.beginEditBlock()

        first_block = self._contiguous_segment_first_block(block, start_sec=orig_start)
        prev_block = first_block.previous()
        if sec > orig_start and prev_block.isValid():
            prev_data = prev_block.userData()
            if isinstance(prev_data, SubtitleBlockData) and not prev_data.is_gap:
                insert_gap_after(prev_block, orig_start)

        current = first_block
        while current.isValid():
            current_data = current.userData()
            if isinstance(current_data, SubtitleBlockData) and not current_data.is_gap and abs(float(current_data.start_sec) - orig_start) < 0.05:
                current_data.start_sec = sec
                current = current.next()
            else:
                break

        self._finish_block_surgery_edit(cursor)

    def _set_segment_end_to_playhead(self):
        self._undo_mgr.push_immediate()
        sec = self._snap_to_frame(getattr(self.timeline.canvas, "playhead_sec", getattr(self.video_player, "current_time", 0.0)))
        block = self._subtitle_segment_edit_target_block()
        if block is None:
            return
        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or ud.is_gap:
            return

        orig_start = float(ud.start_sec)
        if sec <= orig_start:
            return

        cursor = self.text_edit.textCursor()
        cursor.beginEditBlock()
        last_block = self._contiguous_segment_last_block(block, start_sec=orig_start)
        next_block = last_block.next()
        if next_block.isValid() and isinstance(next_block.userData(), SubtitleBlockData) and next_block.userData().is_gap:
            next_block.userData().start_sec = sec
        else:
            insert_gap_after(last_block, sec)

        self._finish_block_surgery_edit(cursor)
