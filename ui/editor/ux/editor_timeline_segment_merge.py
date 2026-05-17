from __future__ import annotations

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QCursor, QTextCursor
from PyQt6.QtWidgets import QApplication

from ui.dialogs.qml_popup import show_context_menu
from ui.editor.editor_helpers import get_sub_block_indices
from ui.editor.ux.subtitle_text_edit import SubtitleBlockData


class EditorTimelineSegmentMergeMixin:
    """Popup-driven segment merge/delete UX for full adjacent-segment merges."""

    def _segment_merge_menu_items(self, left_line: int, right_line: int) -> list[dict]:
        _ = (left_line, right_line)
        return [
            {"id": "merge", "label": "합치기", "accent": "#34C759"},
            {"id": "delete", "label": "지우기", "accent": "#FF9500"},
        ]

    def _segment_merge_popup_enabled(self) -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        try:
            platform_name = str(app.platformName() or "").strip().lower()
        except Exception:
            platform_name = ""
        if platform_name in {"offscreen", "minimal"}:
            return False
        return bool(getattr(self, "_allow_segment_merge_popup", True))

    def _choose_diamond_merge_action(
        self,
        left_line: int,
        right_line: int,
        *,
        global_pos: QPoint | None = None,
    ) -> str | None:
        override = getattr(self, "_diamond_merge_action_override", None)
        if callable(override):
            try:
                chosen = override(int(left_line), int(right_line), global_pos)
            except TypeError:
                chosen = override(int(left_line), int(right_line))
            chosen = str(chosen or "").strip().lower()
            if chosen in {"merge", "delete"}:
                return chosen
            if chosen in {"cancel", "none"}:
                return None

        if not self._segment_merge_popup_enabled():
            return "merge"

        pos = QPoint(global_pos) if isinstance(global_pos, QPoint) else QCursor.pos()
        chosen = show_context_menu(self, pos, self._segment_merge_menu_items(left_line, right_line))
        chosen = str(chosen or "").strip().lower()
        return chosen if chosen in {"merge", "delete"} else None

    def _on_diamond_merge_requested(
        self,
        left_line: int,
        right_line: int,
        global_pos: QPoint | None = None,
    ) -> None:
        action = self._choose_diamond_merge_action(
            int(left_line),
            int(right_line),
            global_pos=global_pos,
        )
        if action == "delete":
            self._on_diamond_delete(int(left_line), int(right_line))
        elif action == "merge":
            self._on_diamond_merge(int(left_line), int(right_line))

    def _resolve_diamond_merge_context(self, left_line: int, right_line: int) -> dict | None:
        text_edit = getattr(self, "text_edit", None)
        if text_edit is None:
            return None
        doc = text_edit.document()
        left_block = doc.findBlockByNumber(int(left_line))
        right_block = doc.findBlockByNumber(int(right_line))
        if not left_block.isValid() or not right_block.isValid():
            return None

        left_ud = left_block.userData()
        right_ud = right_block.userData()
        if not isinstance(left_ud, SubtitleBlockData) or not isinstance(right_ud, SubtitleBlockData):
            return None
        if bool(left_ud.is_gap) or bool(right_ud.is_gap):
            return None

        left_start_sec = float(getattr(left_ud, "start_sec", 0.0) or 0.0)
        right_start_sec = float(getattr(right_ud, "start_sec", 0.0) or 0.0)
        left_indices = get_sub_block_indices(doc, int(left_line), left_start_sec)
        right_indices = get_sub_block_indices(doc, int(right_line), right_start_sec)
        if not left_indices or not right_indices:
            return None

        right_end_sec = float(
            getattr(
                right_ud,
                "end_sec",
                getattr(left_ud, "end_sec", left_start_sec),
            )
            or left_start_sec
        )
        return {
            "doc": doc,
            "left_block": left_block,
            "right_block": right_block,
            "left_ud": left_ud,
            "right_ud": right_ud,
            "left_start_sec": left_start_sec,
            "right_start_sec": right_start_sec,
            "left_indices": left_indices,
            "right_indices": right_indices,
            "left_last": int(left_indices[-1]),
            "right_last": int(right_indices[-1]),
            "right_end_sec": right_end_sec,
        }

    def _set_block_group_end(self, doc, line_num: int, start_sec: float, end_sec: float) -> None:
        snap_to_frame = getattr(self, "_snap_to_frame", None)
        resolved_end = float(end_sec)
        if callable(snap_to_frame):
            try:
                resolved_end = float(snap_to_frame(resolved_end))
            except Exception:
                resolved_end = float(end_sec)
        for idx in get_sub_block_indices(doc, int(line_num), float(start_sec)):
            block = doc.findBlockByNumber(int(idx))
            ud = block.userData() if block.isValid() else None
            if isinstance(ud, SubtitleBlockData):
                ud.end_sec = resolved_end

    def _set_block_group_start(self, doc, line_num: int, start_sec: float, new_start_sec: float) -> None:
        snap_to_frame = getattr(self, "_snap_to_frame", None)
        resolved_start = float(new_start_sec)
        if callable(snap_to_frame):
            try:
                resolved_start = float(snap_to_frame(resolved_start))
            except Exception:
                resolved_start = float(new_start_sec)
        for idx in get_sub_block_indices(doc, int(line_num), float(start_sec)):
            block = doc.findBlockByNumber(int(idx))
            ud = block.userData() if block.isValid() else None
            if isinstance(ud, SubtitleBlockData):
                ud.start_sec = resolved_start

    def _delete_block_group(self, doc, line_num: int, start_sec: float) -> None:
        for idx in reversed(get_sub_block_indices(doc, int(line_num), float(start_sec))):
            block = doc.findBlockByNumber(int(idx))
            if not block.isValid():
                continue
            delete_cursor = QTextCursor(doc)
            start_pos = block.position()
            next_block = block.next()
            if next_block.isValid():
                end_pos = next_block.position()
            else:
                end_pos = block.position() + max(0, block.length() - 1)
                start_pos = max(0, start_pos - 1)
            delete_cursor.setPosition(start_pos)
            delete_cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
            delete_cursor.removeSelectedText()

    def _group_texts(self, doc, first_line: int, last_line: int) -> list[str]:
        texts: list[str] = []
        for idx in range(int(first_line), int(last_line) + 1):
            block = doc.findBlockByNumber(int(idx))
            if not block.isValid():
                continue
            text = str(block.text() or "").strip()
            if text:
                texts.append(text)
        return texts

    def _finish_segment_merge_edit(self) -> None:
        if hasattr(self, "_invalidate_segment_cache"):
            self._invalidate_segment_cache()
        if hasattr(self, "_mark_dirty"):
            self._mark_dirty()
        refresher = getattr(self, "_reload_segments_refresh_runtime", None)
        get_current_segments = getattr(self, "_get_current_segments", None)
        if callable(refresher) and callable(get_current_segments):
            try:
                rows = list(get_current_segments(force_rebuild=True))
            except TypeError:
                rows = list(get_current_segments())
            except Exception:
                rows = []
            if rows:
                try:
                    refresher(rows, mark_dirty=False)
                except Exception:
                    pass
        if hasattr(self, "_finalize_edit"):
            self._finalize_edit()

    def _diamond_delete_keep_line(self, left_line: int, right_line: int) -> int:
        """Keep the segment being dragged; default diamond clicks keep the left side."""
        valid_lines = {int(left_line), int(right_line)}
        explicit = getattr(self, "_diamond_delete_keep_line_override", None)
        if explicit is not None:
            try:
                explicit_line = int(explicit)
                if explicit_line in valid_lines:
                    return explicit_line
            except Exception:
                pass

        timeline = getattr(self, "timeline", None)
        canvas = getattr(timeline, "canvas", None) if timeline is not None else None
        drag_seg = getattr(canvas, "_drag_seg", None)
        drag_edge = str(getattr(canvas, "_drag_edge", "") or "")
        drag_pair = tuple(getattr(canvas, "_drag_merge_pair", ()) or ())
        if (
            isinstance(drag_seg, dict)
            and drag_edge in {"square_left", "square_right"}
            and len(drag_pair) == 2
        ):
            try:
                pair = (int(drag_pair[0]), int(drag_pair[1]))
                drag_line = int(drag_seg.get("line", -1))
            except Exception:
                pair = ()
                drag_line = -1
            if pair == (int(left_line), int(right_line)) and drag_line in valid_lines:
                return drag_line
        return int(left_line)

    def _on_diamond_merge(self, left_line: int, right_line: int) -> None:
        ctx = self._resolve_diamond_merge_context(int(left_line), int(right_line))
        if ctx is None:
            return
        right_texts = self._group_texts(ctx["doc"], int(right_line), ctx["right_last"])
        if not right_texts:
            return

        self._undo_mgr.push_immediate()
        cur = QTextCursor(ctx["doc"])
        cur.beginEditBlock()

        left_last_block = ctx["doc"].findBlockByNumber(ctx["left_last"])
        right_last_block = ctx["doc"].findBlockByNumber(ctx["right_last"])
        cur.setPosition(left_last_block.position())
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        right_end = QTextCursor(right_last_block)
        right_end.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cur.setPosition(right_end.position(), QTextCursor.MoveMode.KeepAnchor)
        cur.insertText(" " + " ".join(right_texts))
        self._set_block_group_end(
            ctx["doc"],
            int(left_line),
            float(ctx["left_start_sec"]),
            float(ctx["right_end_sec"]),
        )
        cur.endEditBlock()

        self._finish_segment_merge_edit()

    def _on_diamond_delete(self, left_line: int, right_line: int) -> None:
        ctx = self._resolve_diamond_merge_context(int(left_line), int(right_line))
        if ctx is None:
            return

        keep_line = self._diamond_delete_keep_line(int(left_line), int(right_line))
        self._undo_mgr.push_immediate()
        cur = QTextCursor(ctx["doc"])
        cur.beginEditBlock()
        if keep_line == int(right_line):
            self._set_block_group_start(
                ctx["doc"],
                int(right_line),
                float(ctx["right_start_sec"]),
                float(ctx["left_start_sec"]),
            )
            self._delete_block_group(
                ctx["doc"],
                int(left_line),
                float(ctx["left_start_sec"]),
            )
        else:
            self._set_block_group_end(
                ctx["doc"],
                int(left_line),
                float(ctx["left_start_sec"]),
                float(ctx["right_end_sec"]),
            )
            self._delete_block_group(
                ctx["doc"],
                int(right_line),
                float(ctx["right_start_sec"]),
            )
        cur.endEditBlock()

        self._finish_segment_merge_edit()


__all__ = ["EditorTimelineSegmentMergeMixin"]
