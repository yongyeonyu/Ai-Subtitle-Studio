"""Low-level block targeting and playhead surgery helpers for editor segments."""

from __future__ import annotations

from core.project.nle_dual_write import apply_caption_resize_dual_write_pilot
from ui.editor.editor_helpers import insert_gap_after
from ui.editor.subtitle_text_edit import SubtitleBlockData


class EditorSegmentsBlockSurgeryMixin:
    def _timeline_inline_split_pending(self) -> bool:
        canvas = getattr(getattr(self, "timeline", None), "canvas", None)
        return bool(
            canvas is not None
            and getattr(canvas, "_edit_active", False)
            and hasattr(canvas, "_pending_split_sec")
        )

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

    def _nle_shortcut_resize_neighbor_shape(
        self,
        block,
        *,
        direction: str,
        current_start: float,
        new_value: float,
    ) -> bool:
        if direction == "start":
            first_block = self._contiguous_segment_first_block(block, start_sec=current_start)
            last_block = self._contiguous_segment_last_block(block, start_sec=current_start)
            if first_block != block or last_block != block:
                return False
            prev_block = first_block.previous()
            if not prev_block.isValid():
                return True
            prev_data = prev_block.userData()
            if not isinstance(prev_data, SubtitleBlockData) or not prev_data.is_gap:
                return False
            return float(new_value) <= float(current_start)
        if direction == "end":
            first_block = self._contiguous_segment_first_block(block, start_sec=current_start)
            last_block = self._contiguous_segment_last_block(block, start_sec=current_start)
            if first_block != block or last_block != block:
                return False
            next_block = last_block.next()
            if not next_block.isValid():
                return True
            next_data = next_block.userData()
            if not isinstance(next_data, SubtitleBlockData) or not next_data.is_gap:
                return False
            return float(new_value) >= float(getattr(block.userData(), "end_sec", current_start) or current_start)
        return False

    def _try_nle_shortcut_resize_to_playhead(
        self,
        *,
        block,
        ud: SubtitleBlockData,
        new_start: float,
        new_end: float,
        direction: str,
    ) -> bool:
        if not callable(getattr(self, "_reload_segments_from_list", None)):
            return False
        project_builder = getattr(self, "_nle_live_editor_project_from_rows", None)
        caption_id_for_line = getattr(self, "_nle_live_editor_caption_id_for_line", None)
        if not callable(project_builder) or not callable(caption_id_for_line):
            return False
        if bool(
            getattr(ud, "is_gap", False)
            or getattr(ud, "stt_pending", False)
            or getattr(ud, "stt_mode", False)
            or getattr(ud, "live_preview", False)
        ):
            return False
        raw_text = block.text().replace("\u2028", "\n").strip()
        if not raw_text:
            return False

        try:
            line_num = int(block.blockNumber())
            current_start = float(getattr(ud, "start_sec"))
        except Exception:
            return False
        if not self._nle_shortcut_resize_neighbor_shape(
            block,
            direction=direction,
            current_start=current_start,
            new_value=float(new_start if direction == "start" else new_end),
        ):
            return False

        try:
            current_segments = list(self._get_current_segments(force_rebuild=True))
        except Exception:
            return False
        target_row = None
        for row in current_segments:
            if not isinstance(row, dict):
                continue
            try:
                if int(row.get("line", -1)) != line_num:
                    continue
                if abs(float(row.get("start", 0.0) or 0.0) - current_start) >= 0.05:
                    continue
            except Exception:
                continue
            target_row = row
            break
        if not isinstance(target_row, dict):
            return False
        if bool(
            target_row.get("is_gap")
            or target_row.get("stt_pending")
            or target_row.get("stt_mode")
            or target_row.get("_live_stt_preview")
            or target_row.get("_live_subtitle_preview")
        ):
            return False
        try:
            current_end = float(target_row.get("end", current_start) or current_start)
            target_new_start = float(new_start)
            target_new_end = float(new_end)
        except Exception:
            return False
        if target_new_end <= target_new_start:
            return False

        project = project_builder(current_segments)
        caption_id = caption_id_for_line(
            project,
            line_num=line_num,
            start_sec=current_start,
            end_sec=current_end,
        )
        if not caption_id:
            return False
        commit_source = (
            "shortcut_start_to_playhead"
            if direction == "start"
            else "shortcut_end_to_playhead"
        )
        edge = "square_left" if direction == "start" else "square_right"
        try:
            nle_result = apply_caption_resize_dual_write_pilot(
                project,
                caption_id=caption_id,
                new_start=target_new_start,
                new_end=target_new_end,
                edge=edge,
                project_path=str(getattr(self, "_linked_project_path_for_srt", "") or ""),
            )
        except Exception:
            return False

        projected_rows = [dict(row) for row in nle_result.projected_rows]
        self._reload_segments_from_list(projected_rows, preserve_view=True, mark_dirty=True)
        cache_rows = getattr(self, "_cache_current_segments", None)
        if callable(cache_rows):
            cache_rows(projected_rows)
        operation = nle_result.operation.to_dict()
        metadata = dict(operation.get("metadata") or {})
        metadata.update(
            {
                "commit_boundary": "release",
                "commit_source": commit_source,
                "qtextblock_shape": "single_block_shortcut",
            }
        )
        operation["metadata"] = metadata
        self._last_nle_block_surgery_operation = operation
        self._last_nle_block_surgery_projection = nle_result.after_projection.to_dict()
        return True

    def _set_segment_start_to_playhead(self):
        if self._timeline_inline_split_pending():
            return
        self._undo_mgr.push_immediate()
        sec = self._snap_to_frame(getattr(self.timeline.canvas, "playhead_sec", getattr(self.video_player, "current_time", 0.0)))
        block = self._subtitle_segment_edit_target_block()
        if block is None:
            return
        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or ud.is_gap:
            return

        orig_start = float(ud.start_sec)
        current_end = getattr(ud, "end_sec", None)
        if current_end is not None:
            try:
                if self._try_nle_shortcut_resize_to_playhead(
                    block=block,
                    ud=ud,
                    new_start=sec,
                    new_end=float(current_end),
                    direction="start",
                ):
                    return
            except Exception:
                pass

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
        if self._timeline_inline_split_pending():
            return
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

        current_end = getattr(ud, "end_sec", None)
        if current_end is not None:
            try:
                if self._try_nle_shortcut_resize_to_playhead(
                    block=block,
                    ud=ud,
                    new_start=orig_start,
                    new_end=sec,
                    direction="end",
                ):
                    return
            except Exception:
                pass

        cursor = self.text_edit.textCursor()
        cursor.beginEditBlock()
        last_block = self._contiguous_segment_last_block(block, start_sec=orig_start)
        next_block = last_block.next()
        if next_block.isValid() and isinstance(next_block.userData(), SubtitleBlockData) and next_block.userData().is_gap:
            next_block.userData().start_sec = sec
        else:
            insert_gap_after(last_block, sec)

        self._finish_block_surgery_edit(cursor)
