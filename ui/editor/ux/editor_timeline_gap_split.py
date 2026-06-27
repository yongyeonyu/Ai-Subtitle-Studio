"""Dedicated gap/split interaction scenarios for the editor timeline."""

from __future__ import annotations

from PyQt6.QtGui import QTextCursor

from ui.editor.ux.subtitle_text_edit import SubtitleBlockData
from ui.editor.editor_helpers import delete_block_safely, get_sub_block_indices, make_gap_ud


class EditorTimelineGapSplitMixin:
    def _arm_gap_snapshot_undo_routing(self) -> None:
        arm_snapshot_undo = getattr(self, "_arm_snapshot_undo_routing", None)
        if callable(arm_snapshot_undo):
            # 갭/자막 생성은 QTextEdit 내부 undo가 아니라 앱 스냅샷 undo로 한 번에 되돌린다.
            arm_snapshot_undo()

    def _on_seg_to_gap(self, line_num: int):
        """Convert a subtitle segment into an editable silence gap."""
        self._undo_mgr.push_immediate()
        doc = self.text_edit.document()
        block = doc.findBlockByNumber(line_num)
        if not block.isValid():
            return

        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or ud.is_gap:
            return

        seg_start = float(ud.start_sec)
        seg_end = None
        try:
            for seg in self._get_current_segments():
                if int(seg.get("line", -1)) == int(line_num) and not seg.get("is_gap"):
                    seg_end = float(seg.get("end", seg_start) or seg_start)
                    break
        except Exception:
            seg_end = None
        get_current_segments = getattr(self, "_get_current_segments", None)
        nle_delete_result = None
        if callable(get_current_segments) and seg_end is not None and seg_end > seg_start:
            try:
                current_segments = list(get_current_segments())
            except Exception:
                current_segments = []
            nle_delete = getattr(self, "_nle_live_editor_caption_delete_result", None)
            if callable(nle_delete):
                nle_delete_result = nle_delete(
                    current_segments=current_segments,
                    line_num=int(line_num),
                    start_sec=float(seg_start),
                    end_sec=float(seg_end),
                )
        reloader = getattr(self, "_reload_segments_from_list", None)
        if nle_delete_result is not None and callable(reloader):
            self._active_seg_start = float(seg_start)
            self._last_nle_live_editor_operation = nle_delete_result.operation.to_dict()
            self._last_nle_live_editor_projection = nle_delete_result.after_projection.to_dict()
            reloader([dict(row) for row in nle_delete_result.projected_rows], preserve_view=True, mark_dirty=True)
            self._remove_live_detection_for_range(seg_start, seg_end)
            self._arm_gap_snapshot_undo_routing()
            return

        sub_indices = get_sub_block_indices(doc, line_num, seg_start)

        cur = QTextCursor(doc)
        cur.beginEditBlock()

        for idx in reversed(sub_indices[1:]):
            delete_block_safely(doc.findBlockByNumber(idx))

        block = doc.findBlockByNumber(line_num)
        cur.setPosition(block.position())
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        block.setUserData(make_gap_ud(seg_start))

        cur.endEditBlock()
        self.text_edit.setTextCursor(cur)
        if seg_end is not None and seg_end > seg_start:
            self._remove_live_detection_for_range(seg_start, seg_end)
        if hasattr(self, "_invalidate_segment_cache"):
            self._invalidate_segment_cache()
        self._finalize_edit()
        self._arm_gap_snapshot_undo_routing()

    def _remove_live_detection_for_range(self, start_sec: float, end_sec: float):
        start = float(start_sec)
        end = float(end_sec)
        if end <= start:
            return

        timeline = getattr(self, "timeline", None)
        canvas = getattr(timeline, "canvas", None)
        if canvas is not None:
            try:
                canvas.voice_activity_segments = self._trim_segments_outside_range(
                    list(getattr(canvas, "voice_activity_segments", []) or []),
                    start,
                    end,
                )
                if hasattr(canvas, "_invalidate_marker_caches"):
                    canvas._invalidate_marker_caches()
                canvas.update()
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass

    def _trim_segments_outside_range(self, segments: list[dict], start_sec: float, end_sec: float) -> list[dict]:
        start = float(start_sec)
        end = float(end_sec)
        if end <= start:
            return list(segments or [])
        trimmed: list[dict] = []
        min_len = max(0.02, min(0.1, 1.0 / max(1.0, self._current_frame_fps())))
        for seg in list(segments or []):
            try:
                seg_start = float(seg.get("start", 0.0) or 0.0)
                seg_end = float(seg.get("end", seg_start) or seg_start)
            except Exception:
                continue
            if seg_end <= start + 0.001 or seg_start >= end - 0.001:
                trimmed.append(dict(seg))
                continue
            if seg_start < start - min_len:
                left = dict(seg)
                left["end"] = self._snap_to_frame(start)
                trimmed.append(left)
            if seg_end > end + min_len:
                right = dict(seg)
                right["start"] = self._snap_to_frame(end)
                trimmed.append(right)
        return trimmed

    def _on_gap_activated(self, gap_start: float, gap_end: float):
        self._undo_mgr.push_immediate()
        gap_start = self._snap_to_frame(gap_start)
        gap_end = self._snap_to_frame(gap_end)
        doc = self.text_edit.document()
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        subtitle_idx = self._apply_gap_generation_parts(gap_start, [("subtitle", "새 자막", gap_start)])
        cur.endEditBlock()
        self._finalize_edit()
        block = doc.findBlockByNumber(subtitle_idx)
        if block.isValid():
            ud = block.userData()
            if isinstance(ud, SubtitleBlockData):
                ud.end_sec = gap_end
            cursor = QTextCursor(block)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            self.text_edit.setTextCursor(cursor)
        self._arm_gap_snapshot_undo_routing()

    def _delete_gap_blocks_in_range(self, gap_start: float, gap_end: float) -> int:
        """Remove document gap blocks inside a deleted silence range."""
        doc = self.text_edit.document()
        start = self._snap_to_frame(float(gap_start))
        end = self._snap_to_frame(float(gap_end))
        if end <= start:
            return 0

        gap_lines: list[int] = []
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            ud = block.userData()
            if not isinstance(ud, SubtitleBlockData) or not ud.is_gap:
                continue
            gap_sec = self._snap_to_frame(float(ud.start_sec))
            if start - 0.05 <= gap_sec <= end + 0.05:
                gap_lines.append(i)

        if not gap_lines:
            return 0

        cur = QTextCursor(doc)
        cur.beginEditBlock()
        removed = 0
        for line in reversed(gap_lines):
            block = doc.findBlockByNumber(line)
            if block.isValid():
                delete_block_safely(block)
                removed += 1
        cur.endEditBlock()

        if hasattr(self.text_edit, "update_margins"):
            self.text_edit.update_margins()
        if hasattr(self.text_edit, "timestampArea"):
            self.text_edit.timestampArea.update()
        if hasattr(self, "_invalidate_segment_cache"):
            self._invalidate_segment_cache()
        return removed

    def _on_gap_to_segs(self, gap_start: float, gap_end: float):
        self._undo_mgr.push_immediate()
        gap_start = self._snap_to_frame(gap_start)
        gap_end = self._snap_to_frame(gap_end)
        gap_dur = self._snap_to_frame(gap_end - gap_start)
        if gap_dur <= 0:
            return
        push = float(self.settings.get("gap_push_rate", 0.7))
        push = max(0.0, min(1.0, push))
        canvas_segments = [
            s for s in getattr(getattr(self.timeline, "canvas", None), "segments", []) or []
            if isinstance(s, dict) and not s.get("is_gap")
        ]
        left = max((s for s in canvas_segments if s["end"] <= gap_start + 0.1), key=lambda s: s["end"], default=None)
        right = min((s for s in canvas_segments if s["start"] >= gap_end - 0.1), key=lambda s: s["start"], default=None)
        min_len = max(0.02, min(0.1, 1.0 / max(1.0, self._current_frame_fps())))
        if left:
            if right:
                boundary = self._snap_to_frame(gap_start + gap_dur * push)
                boundary_min = self._snap_to_frame(float(left["start"]) + min_len)
                boundary_max = self._snap_to_frame(float(right["end"]) - min_len)
                if boundary_min <= boundary_max:
                    boundary = max(boundary_min, min(boundary_max, boundary))
                left["end"] = boundary
            else:
                left["end"] = gap_end
            self._on_seg_time_changed(left.get("line", 0), left["start"], left["end"], "gap")
        if right:
            if left:
                right["start"] = left["end"]
            else:
                right["start"] = gap_start
            self._on_seg_time_changed(right.get("line", 0), right["start"], right["end"], "gap")

        self._delete_gap_blocks_in_range(gap_start, gap_end)
        self._remove_live_detection_for_range(gap_start, gap_end)
        self._finalize_edit()
        self._arm_gap_snapshot_undo_routing()

    def _gap_part_user_data(self, kind: str, start_sec: float) -> SubtitleBlockData:
        if kind == "gap":
            return make_gap_ud(start_sec)
        return SubtitleBlockData(self.settings.get("spk1_id", "00"), self._snap_to_frame(start_sec), is_gap=False)

    def _find_gap_block_near(self, doc, gap_start: float):
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            ud = block.userData()
            if isinstance(ud, SubtitleBlockData) and ud.is_gap and abs(float(ud.start_sec) - float(gap_start)) < 0.05:
                return block
        return None

    def _find_previous_timed_block(self, doc, sec: float):
        previous = None
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            ud = block.userData()
            if isinstance(ud, SubtitleBlockData) and float(ud.start_sec) <= float(sec) + 0.05:
                previous = block
            elif isinstance(ud, SubtitleBlockData) and float(ud.start_sec) > float(sec) + 0.05:
                break
        return previous

    def _apply_gap_generation_parts(self, gap_start: float, parts: list[tuple[str, str, float]]) -> int:
        doc = self.text_edit.document()
        gap_block = self._find_gap_block_near(doc, gap_start)
        cur = QTextCursor(doc)

        if gap_block is not None and gap_block.isValid():
            first_idx = gap_block.blockNumber()
            cur.setPosition(gap_block.position())
            cur.select(QTextCursor.SelectionType.LineUnderCursor)
            cur.removeSelectedText()
            cur.insertText("\n".join(text for _, text, _ in parts))
        else:
            previous = self._find_previous_timed_block(doc, gap_start)
            if previous is not None and previous.isValid():
                cur = QTextCursor(previous)
                cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                first_idx = previous.blockNumber() + 1
                for _idx, (_kind, text, _start_sec) in enumerate(parts):
                    cur.insertBlock()
                    if text:
                        cur.insertText(text)
            else:
                first = doc.begin()
                first_idx = 0
                cur.setPosition(first.position())
                suffix = "" if (not first.isValid() or (not first.text().strip() and first.userData() is None)) else "\n"
                cur.insertText("\n".join(text for _, text, _ in parts) + suffix)

        subtitle_idx = first_idx
        for offset, (kind, _text, start_sec) in enumerate(parts):
            block = doc.findBlockByNumber(first_idx + offset)
            if not block.isValid():
                continue
            block.setUserData(self._gap_part_user_data(kind, start_sec))
            if kind != "gap":
                subtitle_idx = first_idx + offset
        return subtitle_idx

    def _gap_generation_silence_scope(self, gap_start: float, gap_end: float, pivot_sec: float) -> tuple[float, float] | None:
        timeline = getattr(self, "timeline", None)
        canvas = getattr(timeline, "canvas", None)
        if canvas is None:
            return gap_start, gap_end
        try:
            markers = canvas.generation_silence_markers_cached() if hasattr(canvas, "generation_silence_markers_cached") else []
        except Exception:
            markers = []
        silence_ranges: list[tuple[float, float]] = []
        for marker in list(markers or []):
            kind = str(marker.get("kind", "") or "").strip().lower()
            label = str(marker.get("label", "") or "").strip()
            if kind not in {"generation_silence", "linked_silence"} and label not in {"무음구간", "무음"}:
                continue
            try:
                start = self._snap_to_frame(float(marker.get("start", 0.0) or 0.0))
                end = self._snap_to_frame(float(marker.get("end", start) or start))
            except Exception:
                continue
            start = max(gap_start, start)
            end = min(gap_end, end)
            if end > start:
                silence_ranges.append((start, end))

        if not silence_ranges:
            return gap_start, gap_end

        pivot = self._snap_to_frame(float(pivot_sec))
        containing = [item for item in silence_ranges if item[0] - 0.001 <= pivot <= item[1] + 0.001]
        if containing:
            return min(containing, key=lambda item: item[1] - item[0])
        return min(silence_ranges, key=lambda item: min(abs(pivot - item[0]), abs(pivot - item[1])))

    def _on_gap_generate_requested(self, gap_start: float, gap_end: float, pivot_sec: float, mode: str):
        self._undo_mgr.push_immediate()
        gap_start = self._snap_to_frame(gap_start)
        gap_end = self._snap_to_frame(gap_end)
        pivot_sec = self._snap_to_frame(pivot_sec)
        pivot_sec = max(gap_start, min(gap_end, pivot_sec))
        scope = self._gap_generation_silence_scope(gap_start, gap_end, pivot_sec)
        if scope is None:
            return
        scope_start, scope_end = scope
        pivot_sec = max(scope_start, min(scope_end, pivot_sec))
        min_span = max(0.02, min(0.1, 1.0 / max(1.0, self._current_frame_fps())))
        if mode == "to":
            pivot_sec = min(scope_end, max(scope_start + min_span, pivot_sec))
            sub_start, sub_end = scope_start, pivot_sec
        else:
            pivot_sec = max(scope_start, min(scope_end - min_span, pivot_sec))
            sub_start, sub_end = pivot_sec, scope_end
        if sub_end < sub_start + (min_span * 0.5):
            return

        parts: list[tuple[str, str, float]] = []
        if sub_start > gap_start + 0.02:
            parts.append(("gap", "", gap_start))
        parts.append(("subtitle", "새자막", sub_start))
        if sub_end < gap_end - 0.02:
            parts.append(("gap", "", sub_end))

        get_current_segments = getattr(self, "_get_current_segments", None)
        nle_gap_generate_result = None
        if callable(get_current_segments):
            try:
                current_segments = list(get_current_segments())
            except Exception:
                current_segments = []
            nle_gap_generate = getattr(self, "_nle_live_editor_gap_generate_result", None)
            if callable(nle_gap_generate):
                nle_gap_generate_result = nle_gap_generate(
                    current_segments=current_segments,
                    gap_start=float(gap_start),
                    gap_end=float(gap_end),
                    sub_start=float(sub_start),
                    sub_end=float(sub_end),
                    mode=str(mode or ""),
                )
        reloader = getattr(self, "_reload_segments_from_list", None)
        if nle_gap_generate_result is not None and callable(reloader):
            self._active_seg_start = float(sub_start)
            self._last_nle_live_editor_operation = nle_gap_generate_result.operation.to_dict()
            self._last_nle_live_editor_projection = nle_gap_generate_result.after_projection.to_dict()
            reloader([dict(row) for row in nle_gap_generate_result.projected_rows], preserve_view=True, mark_dirty=True)
            self._remove_live_detection_for_range(sub_start, sub_end)
            target_line = None
            for row in nle_gap_generate_result.projected_rows:
                if not isinstance(row, dict) or bool(row.get("is_gap")):
                    continue
                try:
                    if abs(float(row.get("start", 0.0) or 0.0) - float(sub_start)) < 0.05:
                        target_line = int(row.get("line", 0) or 0)
                        break
                except Exception:
                    continue
            if target_line is not None:
                block = self.text_edit.document().findBlockByNumber(target_line)
                if block.isValid():
                    cursor = QTextCursor(block)
                    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                    self.text_edit.setTextCursor(cursor)
            timeline = getattr(self, "timeline", None)
            if timeline is not None:
                if hasattr(timeline, "set_active"):
                    timeline.set_active(sub_start)
                if hasattr(timeline, "set_playhead"):
                    timeline.set_playhead(sub_start)
                if hasattr(timeline, "center_to_sec"):
                    timeline.center_to_sec(sub_start, smooth=True)
            video_player = getattr(self, "video_player", None)
            if video_player is not None and hasattr(video_player, "seek"):
                video_player.seek(self._global_to_local_sec(sub_start) if hasattr(self, "_global_to_local_sec") else sub_start)
            if hasattr(self.text_edit, "update_margins"):
                self.text_edit.update_margins()
            if hasattr(self.text_edit, "timestampArea"):
                self.text_edit.timestampArea.update()
            self._arm_gap_snapshot_undo_routing()
            return

        cur = QTextCursor(self.text_edit.document())
        cur.beginEditBlock()
        subtitle_idx = self._apply_gap_generation_parts(gap_start, parts)
        cur.endEditBlock()
        self._remove_live_detection_for_range(sub_start, sub_end)

        block = self.text_edit.document().findBlockByNumber(subtitle_idx)
        if block.isValid():
            cursor = QTextCursor(block)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            self.text_edit.setTextCursor(cursor)
            self._active_seg_start = sub_start
            timeline = getattr(self, "timeline", None)
            if timeline is not None:
                if hasattr(timeline, "set_active"):
                    timeline.set_active(sub_start)
                if hasattr(timeline, "set_playhead"):
                    timeline.set_playhead(sub_start)
                if hasattr(timeline, "center_to_sec"):
                    timeline.center_to_sec(sub_start, smooth=True)
            video_player = getattr(self, "video_player", None)
            if video_player is not None and hasattr(video_player, "seek"):
                video_player.seek(self._global_to_local_sec(sub_start) if hasattr(self, "_global_to_local_sec") else sub_start)
        if hasattr(self.text_edit, "update_margins"):
            self.text_edit.update_margins()
        if hasattr(self.text_edit, "timestampArea"):
            self.text_edit.timestampArea.update()
        self._finalize_edit()
        self._arm_gap_snapshot_undo_routing()

    def _on_smart_split(self, line_num: int, split_sec: float, new_on_left: bool):
        """Split the current subtitle into two editable timeline rows."""
        self._undo_mgr.push_immediate()
        doc = self.text_edit.document()
        block = doc.findBlockByNumber(int(line_num))
        if not block.isValid():
            return

        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or ud.is_gap:
            return

        seg_start = float(ud.start_sec)
        spk_id = ud.spk_id
        seg_start = self._snap_to_frame(seg_start)
        split_sec = self._snap_to_frame(split_sec)
        if split_sec <= seg_start + 0.05:
            return

        sub_indices = get_sub_block_indices(doc, block.blockNumber(), seg_start)
        full_lines = [doc.findBlockByNumber(idx).text() for idx in sub_indices]
        original_text = "\u2028".join(full_lines)

        nle_split = getattr(self, "_nle_live_editor_caption_split_result", None)
        reloader = getattr(self, "_reload_segments_from_list", None)
        if callable(nle_split) and callable(reloader):
            try:
                current_segments = list(self._get_current_segments(force_rebuild=True))
            except Exception:
                current_segments = []
            seg_end = getattr(ud, "end_sec", None)
            try:
                seg_end = float(seg_end) if seg_end is not None else None
            except Exception:
                seg_end = None
            if seg_end is None or split_sec >= self._snap_to_frame(seg_end):
                for seg in current_segments:
                    if not isinstance(seg, dict):
                        continue
                    try:
                        if int(seg.get("line", -1)) != int(line_num):
                            continue
                        seg_end = float(seg.get("end", seg_start) or seg_start)
                        break
                    except Exception:
                        continue
            left_text = "새자막" if new_on_left else original_text.replace("\u2028", "\n")
            right_text = original_text.replace("\u2028", "\n") if new_on_left else "새자막"
            if seg_end is not None and split_sec < self._snap_to_frame(seg_end):
                nle_result = nle_split(
                    current_segments=current_segments,
                    line_num=int(line_num),
                    start_sec=float(seg_start),
                    end_sec=float(seg_end),
                    split_sec=float(split_sec),
                    left_text=left_text,
                    right_text=right_text,
                    commit_source="timeline_smart_split",
                )
                if nle_result is not None:
                    self._last_nle_live_editor_operation = nle_result.operation.to_dict()
                    self._last_nle_live_editor_projection = nle_result.after_projection.to_dict()
                    reloader(list(nle_result.projected_rows), preserve_view=True, mark_dirty=True)
                    self._sync_lock = True
                    try:
                        self._active_seg_start = split_sec
                        target_line = None
                        for row in nle_result.projected_rows:
                            if not isinstance(row, dict) or bool(row.get("is_gap")):
                                continue
                            try:
                                if abs(float(row.get("start", 0.0) or 0.0) - float(split_sec)) < 0.05:
                                    target_line = int(row.get("line", 0) or 0)
                                    break
                            except Exception:
                                continue
                        if target_line is not None:
                            target_block = self.text_edit.document().findBlockByNumber(target_line)
                            if target_block.isValid():
                                cur = QTextCursor(target_block)
                                cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                                self.text_edit.setTextCursor(cur)
                        if hasattr(self, "timeline"):
                            self.timeline.set_active(self._active_seg_start)
                            self.timeline.center_to_sec(split_sec, smooth=True)
                    finally:
                        self._sync_lock = False
                    if hasattr(self.text_edit, "update_margins"):
                        self.text_edit.update_margins()
                    if hasattr(self.text_edit, "timestampArea"):
                        self.text_edit.timestampArea.update()
                    self._arm_gap_snapshot_undo_routing()
                    return

        cur = QTextCursor(doc)
        cur.beginEditBlock()

        for idx in reversed(sub_indices[1:]):
            block_ref = doc.findBlockByNumber(idx)
            block_cursor = QTextCursor(block_ref)
            block_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            block_cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            block_cursor.removeSelectedText()
            if doc.blockCount() > 1:
                block_cursor.deletePreviousChar()

        block = doc.findBlockByNumber(sub_indices[0])
        cur.setPosition(block.position())
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()

        if new_on_left:
            cur.insertText("새자막")
            cur.block().setUserData(SubtitleBlockData(spk_id, seg_start, is_gap=False))
            cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            cur.insertBlock()
            cur.insertText(original_text)
            cur.block().setUserData(SubtitleBlockData(spk_id, split_sec, is_gap=False))
        else:
            cur.insertText(original_text)
            cur.block().setUserData(SubtitleBlockData(spk_id, seg_start, is_gap=False))
            cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            cur.insertBlock()
            cur.insertText("새자막")
            cur.block().setUserData(SubtitleBlockData(spk_id, split_sec, is_gap=False))

        cur.endEditBlock()

        self._sync_lock = True
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        self.text_edit.setTextCursor(cur)
        self._active_seg_start = split_sec
        if hasattr(self, "timeline"):
            self.timeline.set_active(self._active_seg_start)
            self.timeline.center_to_sec(split_sec, smooth=True)
        self._sync_lock = False

        self._mark_dirty()
        self._finalize_edit()
        arm_snapshot_undo = getattr(self, "_arm_snapshot_undo_routing", None)
        if callable(arm_snapshot_undo):
            arm_snapshot_undo()


__all__ = ["EditorTimelineGapSplitMixin"]
