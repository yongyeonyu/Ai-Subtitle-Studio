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
        # 변경 금지: 메뉴가 떠 있는 동안 타임라인 repaint/이벤트가 돌아도
        # "지우기"는 화살표로 끌어온 원본 세그먼트를 유지하고 덮인 세그먼트만 제거해야 한다.
        delete_keep_line = self._diamond_delete_keep_line(int(left_line), int(right_line))
        action = self._choose_diamond_merge_action(
            int(left_line),
            int(right_line),
            global_pos=global_pos,
        )
        if action == "delete":
            self._on_diamond_delete(int(left_line), int(right_line), keep_line=delete_keep_line)
        elif action == "merge":
            self._on_diamond_merge(int(left_line), int(right_line))

    def _canvas_for_diamond_merge(self):
        timeline = getattr(self, "timeline", None)
        return getattr(timeline, "canvas", None) if timeline is not None else None

    def _canvas_drag_segment_for_line(self, line_num: int) -> dict | None:
        canvas = self._canvas_for_diamond_merge()
        if canvas is None:
            return None

        drag_sources = (
            ("_drag_seg", "_drag_s0_start", "_drag_s0_end"),
            ("_drag_adj_l", "_drag_adj_orig_start_l", "_drag_adj_orig_end_l"),
            ("_drag_adj_r", "_drag_adj_orig_start_r", "_drag_adj_orig_end_r"),
        )
        for seg_attr, start_attr, end_attr in drag_sources:
            seg = getattr(canvas, seg_attr, None)
            if not isinstance(seg, dict):
                continue
            try:
                if int(seg.get("line", -999999)) != int(line_num):
                    continue
            except Exception:
                continue
            resolved = dict(seg)
            try:
                resolved["start"] = float(getattr(canvas, start_attr))
            except Exception:
                pass
            try:
                resolved["end"] = float(getattr(canvas, end_attr))
            except Exception:
                pass
            return resolved
        return None

    def _canvas_segment_for_merge_line(self, line_num: int) -> dict | None:
        dragged = self._canvas_drag_segment_for_line(int(line_num))
        if isinstance(dragged, dict):
            return dragged

        canvas = self._canvas_for_diamond_merge()
        if canvas is None:
            return None
        getter = getattr(canvas, "_segment_for_line", None)
        if callable(getter):
            try:
                seg = getter(int(line_num))
            except Exception:
                seg = None
            if isinstance(seg, dict):
                return dict(seg)
        for seg in list(getattr(canvas, "segments", []) or []):
            if not isinstance(seg, dict):
                continue
            try:
                if int(seg.get("line", -999999)) == int(line_num):
                    return dict(seg)
            except Exception:
                continue
        return None

    def _normalized_merge_text(self, text: str) -> str:
        return " ".join(str(text or "").replace("\u2028", "\n").split())

    def _first_block_line_for_subtitle_group(
        self,
        doc,
        line_num: int,
        start_sec: float,
        end_sec: float | None,
    ) -> int:
        line = int(line_num)
        while line > 0:
            previous = doc.findBlockByNumber(line - 1)
            previous_ud = previous.userData() if previous.isValid() else None
            if not isinstance(previous_ud, SubtitleBlockData) or bool(previous_ud.is_gap):
                break
            try:
                if abs(float(previous_ud.start_sec) - float(start_sec)) >= 0.05:
                    break
            except Exception:
                break
            previous_end = getattr(previous_ud, "end_sec", None)
            if end_sec is not None and previous_end is not None:
                try:
                    if abs(float(previous_end) - float(end_sec)) >= 0.05:
                        break
                except Exception:
                    break
            line -= 1
        return line

    def _find_document_line_for_canvas_segment(self, doc, segment: dict) -> int | None:
        try:
            target_start = float(segment.get("start", 0.0) or 0.0)
        except Exception:
            return None
        try:
            target_end = float(segment.get("end", target_start) or target_start)
        except Exception:
            target_end = target_start
        target_text = self._normalized_merge_text(str(segment.get("text", "") or ""))

        candidates: list[tuple[float, int]] = []
        seen_group_lines: set[int] = set()
        for idx in range(doc.blockCount()):
            block = doc.findBlockByNumber(idx)
            ud = block.userData() if block.isValid() else None
            if not isinstance(ud, SubtitleBlockData) or bool(ud.is_gap):
                continue
            try:
                start_diff = abs(float(ud.start_sec) - target_start)
            except Exception:
                continue
            if start_diff >= 0.05:
                continue
            block_end = getattr(ud, "end_sec", None)
            end_diff = 0.0
            if block_end is not None:
                try:
                    end_diff = abs(float(block_end) - target_end)
                except Exception:
                    end_diff = 0.0
            group_line = self._first_block_line_for_subtitle_group(
                doc,
                idx,
                float(ud.start_sec),
                float(block_end) if block_end is not None else None,
            )
            if group_line in seen_group_lines:
                continue
            seen_group_lines.add(group_line)

            indices = get_sub_block_indices(doc, group_line, float(ud.start_sec))
            last_line = int(indices[-1]) if indices else group_line
            group_text = self._normalized_merge_text(" ".join(self._group_texts(doc, group_line, last_line)))
            score = 0.0
            if target_text:
                if group_text == target_text:
                    score += 10.0
                elif group_text and (group_text in target_text or target_text in group_text):
                    score += 4.0
            if end_diff < 0.05:
                score += 2.0
            score -= start_diff
            candidates.append((score, group_line))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return int(candidates[0][1])

    def _resolve_diamond_line_ref(self, doc, line_num: int) -> dict | None:
        raw_line = int(line_num)
        actual_line: int | None = None
        canvas_segment = self._canvas_segment_for_merge_line(raw_line)
        if isinstance(canvas_segment, dict):
            actual_line = self._find_document_line_for_canvas_segment(doc, canvas_segment)

        if actual_line is None:
            actual_line = raw_line
        block = doc.findBlockByNumber(int(actual_line))
        if not block.isValid():
            return None
        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or bool(ud.is_gap):
            return None

        start_sec = float(getattr(ud, "start_sec", 0.0) or 0.0)
        end_value = getattr(ud, "end_sec", None)
        end_sec = float(end_value) if end_value is not None else start_sec
        group_line = self._first_block_line_for_subtitle_group(doc, int(actual_line), start_sec, end_sec)
        group_block = doc.findBlockByNumber(group_line)
        group_ud = group_block.userData() if group_block.isValid() else None
        if not isinstance(group_ud, SubtitleBlockData) or bool(group_ud.is_gap):
            return None
        group_start_sec = float(getattr(group_ud, "start_sec", start_sec) or start_sec)
        group_end_value = getattr(group_ud, "end_sec", None)
        group_end_sec = float(group_end_value) if group_end_value is not None else group_start_sec
        indices = get_sub_block_indices(doc, group_line, group_start_sec)
        if not indices:
            return None
        return {
            "raw_line": raw_line,
            "line": int(group_line),
            "block": group_block,
            "ud": group_ud,
            "start_sec": group_start_sec,
            "end_sec": group_end_sec,
            "indices": indices,
            "last": int(indices[-1]),
        }

    def _resolve_diamond_merge_context(self, left_line: int, right_line: int) -> dict | None:
        text_edit = getattr(self, "text_edit", None)
        if text_edit is None:
            return None
        doc = text_edit.document()
        left_ref = self._resolve_diamond_line_ref(doc, int(left_line))
        right_ref = self._resolve_diamond_line_ref(doc, int(right_line))
        if left_ref is None or right_ref is None or int(left_ref["line"]) == int(right_ref["line"]):
            return None
        ordered_refs = sorted(
            (left_ref, right_ref),
            key=lambda ref: (float(ref["start_sec"]), int(ref["line"])),
        )
        left_ref, right_ref = ordered_refs[0], ordered_refs[1]
        return {
            "doc": doc,
            "left_raw_line": int(left_ref["raw_line"]),
            "right_raw_line": int(right_ref["raw_line"]),
            "left_line": int(left_ref["line"]),
            "right_line": int(right_ref["line"]),
            "left_block": left_ref["block"],
            "right_block": right_ref["block"],
            "left_ud": left_ref["ud"],
            "right_ud": right_ref["ud"],
            "left_start_sec": float(left_ref["start_sec"]),
            "left_end_sec": float(left_ref["end_sec"]),
            "right_start_sec": float(right_ref["start_sec"]),
            "left_indices": list(left_ref["indices"]),
            "right_indices": list(right_ref["indices"]),
            "left_last": int(left_ref["last"]),
            "right_last": int(right_ref["last"]),
            "right_end_sec": float(right_ref["end_sec"]),
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

    def _retimed_diamond_delete_row(self, row: dict, start_sec: float, end_sec: float) -> dict:
        item = dict(row)
        snap_to_frame = getattr(self, "_snap_to_frame", None)
        start = float(start_sec)
        end = float(end_sec)
        if callable(snap_to_frame):
            try:
                start = float(snap_to_frame(start))
                end = float(snap_to_frame(end))
            except Exception:
                start = float(start_sec)
                end = float(end_sec)
        item["start"] = start
        item["end"] = max(start, end)
        item["timeline_start"] = item["start"]
        item["timeline_end"] = item["end"]
        for key in ("start_frame", "end_frame", "timeline_start_frame", "timeline_end_frame", "frame_range"):
            item.pop(key, None)
        return item

    def _nle_diamond_delete_commit_plan(self, ctx: dict, *, keep_raw_line: int) -> dict | None:
        get_current_segments = getattr(self, "_get_current_segments", None)
        if not callable(get_current_segments):
            return None
        try:
            current_segments = list(get_current_segments(force_rebuild=True))
        except TypeError:
            current_segments = list(get_current_segments())
        except Exception:
            current_segments = []
        if not current_segments:
            return None

        keep_right = int(keep_raw_line) == int(ctx["right_raw_line"])
        keep_line = int(ctx["right_line"] if keep_right else ctx["left_line"])
        remove_line = int(ctx["left_line"] if keep_right else ctx["right_line"])
        new_start = float(ctx["left_start_sec"])
        new_end = float(ctx["right_end_sec"])
        committed: list[dict] = []
        found_keep = False
        found_remove = False
        for seg in current_segments:
            if not isinstance(seg, dict):
                continue
            try:
                seg_line = int(seg.get("line", -1))
            except Exception:
                committed.append(dict(seg))
                continue
            if seg_line == remove_line:
                found_remove = True
                continue
            if seg_line == keep_line:
                found_keep = True
                committed.append(self._retimed_diamond_delete_row(seg, new_start, new_end))
                continue
            committed.append(dict(seg))
        if not found_keep or not found_remove:
            return None
        return {
            "current_segments": current_segments,
            "committed_rows": committed,
            "keep_line": keep_line,
            "new_start": new_start,
            "new_end": new_end,
            "commit_mode": "diamond_delete_keep_right" if keep_right else "diamond_delete_keep_left",
        }

    def _try_nle_diamond_delete(self, ctx: dict, *, keep_raw_line: int) -> bool:
        nle_commit = getattr(self, "_nle_live_editor_caption_move_commit_result", None)
        reloader = getattr(self, "_reload_segments_from_list", None)
        if not callable(nle_commit) or not callable(reloader):
            return False
        plan = self._nle_diamond_delete_commit_plan(ctx, keep_raw_line=int(keep_raw_line))
        if not isinstance(plan, dict):
            return False
        nle_result = nle_commit(
            current_segments=list(plan["current_segments"]),
            committed_rows=list(plan["committed_rows"]),
            line_num=int(plan["keep_line"]),
            new_start=float(plan["new_start"]),
            new_end=float(plan["new_end"]),
            edge_type="diamond_delete",
            commit_source="diamond_delete",
            commit_mode=str(plan["commit_mode"]),
        )
        if nle_result is None:
            return False
        undo_mgr = getattr(self, "_undo_mgr", None)
        if undo_mgr is not None and hasattr(undo_mgr, "push_immediate"):
            undo_mgr.push_immediate()
        self._last_nle_live_editor_operation = nle_result.operation.to_dict()
        self._last_nle_live_editor_projection = nle_result.after_projection.to_dict()
        reloader([dict(row) for row in nle_result.projected_rows], preserve_view=True, mark_dirty=True)
        return True

    def _on_diamond_merge(self, left_line: int, right_line: int) -> None:
        ctx = self._resolve_diamond_merge_context(int(left_line), int(right_line))
        if ctx is None:
            return
        right_texts = self._group_texts(ctx["doc"], int(ctx["right_line"]), ctx["right_last"])
        if not right_texts:
            return
        left_texts = self._group_texts(ctx["doc"], int(ctx["left_line"]), ctx["left_last"])
        merged_text = " ".join(left_texts + right_texts).strip()

        get_current_segments = getattr(self, "_get_current_segments", None)
        nle_merge_result = None
        if callable(get_current_segments) and merged_text:
            try:
                current_segments = list(get_current_segments())
            except Exception:
                current_segments = []
            nle_merge = getattr(self, "_nle_live_editor_caption_merge_result", None)
            if callable(nle_merge):
                nle_merge_result = nle_merge(
                    current_segments=current_segments,
                    left_line=int(ctx["left_line"]),
                    right_line=int(ctx["right_line"]),
                    left_start=float(ctx["left_start_sec"]),
                    left_end=float(ctx["left_end_sec"]),
                    right_start=float(ctx["right_start_sec"]),
                    right_end=float(ctx["right_end_sec"]),
                    merged_text=merged_text,
                )
        reloader = getattr(self, "_reload_segments_from_list", None)
        if nle_merge_result is not None and callable(reloader):
            undo_mgr = getattr(self, "_undo_mgr", None)
            if undo_mgr is not None and hasattr(undo_mgr, "push_immediate"):
                undo_mgr.push_immediate()
            self._last_nle_live_editor_operation = nle_merge_result.operation.to_dict()
            self._last_nle_live_editor_projection = nle_merge_result.after_projection.to_dict()
            reloader([dict(row) for row in nle_merge_result.projected_rows], preserve_view=True, mark_dirty=True)
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
            int(ctx["left_line"]),
            float(ctx["left_start_sec"]),
            float(ctx["right_end_sec"]),
        )
        cur.endEditBlock()

        self._finish_segment_merge_edit()

    def _on_diamond_delete(self, left_line: int, right_line: int, *, keep_line: int | None = None) -> None:
        ctx = self._resolve_diamond_merge_context(int(left_line), int(right_line))
        if ctx is None:
            return

        if keep_line is None:
            keep_line = self._diamond_delete_keep_line(int(left_line), int(right_line))
        try:
            keep_raw_line = int(keep_line)
        except Exception:
            keep_raw_line = int(ctx["left_raw_line"])
        if self._try_nle_diamond_delete(ctx, keep_raw_line=int(keep_raw_line)):
            return
        self._undo_mgr.push_immediate()
        cur = QTextCursor(ctx["doc"])
        cur.beginEditBlock()
        if keep_raw_line == int(ctx["right_raw_line"]):
            self._delete_block_group(
                ctx["doc"],
                int(ctx["left_line"]),
                float(ctx["left_start_sec"]),
            )
            # 변경 금지: QTextDocument는 앞 블록 삭제 시 살아남은 블록의
            # userData를 다시 붙이면서, 삭제 전에 쓴 start/end 값을 되돌릴 수 있다.
            # 그래서 "지우기"는 삭제 후 남은 블록을 다시 찾아 시간을 확정한다.
            retained_line = max(0, int(ctx["right_line"]) - len(ctx["left_indices"]))
            retained_block = ctx["doc"].findBlockByNumber(retained_line)
            retained_ud = retained_block.userData() if retained_block.isValid() else None
            retained_start = (
                float(getattr(retained_ud, "start_sec", ctx["right_start_sec"]) or ctx["right_start_sec"])
                if isinstance(retained_ud, SubtitleBlockData)
                else float(ctx["right_start_sec"])
            )
            self._set_block_group_start(
                ctx["doc"],
                int(retained_line),
                retained_start,
                float(ctx["left_start_sec"]),
            )
        else:
            self._delete_block_group(
                ctx["doc"],
                int(ctx["right_line"]),
                float(ctx["right_start_sec"]),
            )
            retained_line = min(int(ctx["left_line"]), max(0, ctx["doc"].blockCount() - 1))
            retained_block = ctx["doc"].findBlockByNumber(retained_line)
            retained_ud = retained_block.userData() if retained_block.isValid() else None
            retained_start = (
                float(getattr(retained_ud, "start_sec", ctx["left_start_sec"]) or ctx["left_start_sec"])
                if isinstance(retained_ud, SubtitleBlockData)
                else float(ctx["left_start_sec"])
            )
            self._set_block_group_end(
                ctx["doc"],
                int(retained_line),
                retained_start,
                float(ctx["right_end_sec"]),
            )
        cur.endEditBlock()

        self._finish_segment_merge_edit()


__all__ = ["EditorTimelineSegmentMergeMixin"]
