"""Manual edit event and partial insert helpers for editor segments."""

from __future__ import annotations

from PyQt6.QtGui import QTextCursor

from core.runtime.logger import get_logger
from ui.editor.editor_helpers import build_segment_lookup, find_segment_for_line_lookup
from ui.editor.subtitle_text_edit import SubtitleBlockData


class EditorSegmentsManualEditsMixin:
    def _on_selection_changed(self):
        if hasattr(self, "_timeline_lock_edit_enabled") and self._timeline_lock_edit_enabled():
            cur = self.text_edit.textCursor()
            if cur.hasSelection():
                cur.clearSelection()
                self.text_edit.setTextCursor(cur)
            return
        if self.text_edit.textCursor().hasSelection():
            self._on_cursor_moved()
        elif self.editor_popup.is_visible():
            self.editor_popup.close_popup()

    def _on_enter_pressed(self, last_word: str, line_num: int):
        self._undo_mgr.push()
        try:
            from utils import add_split_rule
            add_split_rule(last_word)
        except Exception:
            pass
        self._schedule_timeline()

    def _on_backspace_merged(self, removed_word: str):
        self._undo_mgr.push()
        try:
            from utils import remove_split_rule
            remove_split_rule(removed_word)
        except Exception:
            pass
        self._schedule_timeline()

    def _on_cursor_moved(self):
        if self._sync_lock:
            return
        if bool(getattr(self, "_timeline_drag_in_progress", False)):
            return
        if hasattr(self, "_timeline_lock_edit_enabled") and self._timeline_lock_edit_enabled():
            return
        line_num = self.text_edit.textCursor().blockNumber()
        cache = getattr(self, "_subtitle_memory_cache", None)
        if not isinstance(cache, dict):
            cached = getattr(self, "_cached_segs", None)
            cache = build_segment_lookup(cached) if cached is not None else self._rebuild_subtitle_memory_cache()
            self._subtitle_memory_cache = cache
        seg = find_segment_for_line_lookup(cache, line_num)
        if not seg:
            return
        if self._active_seg_start != seg["start"]:
            try:
                playback_active = bool(self._is_video_playback_active()) if hasattr(self, "_is_video_playback_active") else False
            except Exception:
                playback_active = False
            if hasattr(self, "video_player") and not playback_active:
                self.video_player.pause_video()
            self._active_seg_start = seg["start"]
            self.timeline.set_active(seg["start"])
            self.timeline.set_playhead(seg["start"])
            target_sec = (seg["start"] + seg["end"]) / 2
            if hasattr(self.timeline, "ensure_sec_visible"):
                self.timeline.ensure_sec_visible(target_sec, smooth=False, margin_px=128)
            else:
                self.timeline.center_to_sec(target_sec, smooth=True)
            self._highlighter.set_current_line(line_num)
            self._schedule_visible_quality_refresh()
            tip = self._quality_tooltip(seg)
            if tip:
                self.text_edit.setToolTip(tip)
            else:
                self.text_edit.setToolTip("")
            if hasattr(self, "video_player") and not playback_active:
                self._schedule_cursor_video_seek(seg["start"])
        remember_repeat_segment = getattr(self, "_remember_repeat_segment", None)
        repeat_enabled = getattr(self, "_segment_repeat_enabled", None)
        if callable(remember_repeat_segment) and callable(repeat_enabled) and repeat_enabled():
            remember_repeat_segment(seg)

    def _on_esc_pressed(self):
        if hasattr(self.timeline, "canvas"):
            self.timeline.canvas.update()

    def _partial_insert_target_blocks(self, target_start: float, target_end: float):
        doc = self.text_edit.document()
        start_block, end_block = None, None
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            ud = block.userData()
            if ud and hasattr(ud, "start_sec"):
                if ud.start_sec >= target_start and start_block is None:
                    start_block = block
                if ud.start_sec >= target_end and start_block is not None:
                    end_block = block
                    break
        return doc, start_block, end_block

    def clear_segments_in_range(self, target_start: float, target_end: float):
        self._undo_mgr.push_immediate()
        doc, start_block, end_block = self._partial_insert_target_blocks(target_start, target_end)
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        if start_block:
            end_ud = end_block.userData() if end_block else None
            cur.setPosition(start_block.position())
            if end_block:
                cur.setPosition(end_block.position(), QTextCursor.MoveMode.KeepAnchor)
            else:
                cur.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
            cur.removeSelectedText()
            if end_block:
                cur.insertText("\n")
                if end_ud:
                    cur.block().setUserData(
                        SubtitleBlockData(
                            end_ud.spk_id,
                            end_ud.start_sec,
                            end_ud.is_gap,
                            end_sec=getattr(end_ud, "end_sec", None),
                        )
                    )
                cur.movePosition(QTextCursor.MoveOperation.PreviousBlock)
            else:
                while cur.block().text().strip() == "" and doc.blockCount() > 1:
                    cur.deletePreviousChar()
            self._partial_insert_pos = cur.position()
        else:
            cur.movePosition(QTextCursor.MoveOperation.End)
            if not cur.atBlockStart():
                cur.insertText("\n")
            self._partial_insert_pos = cur.position()

        self.text_edit.update_margins()
        cur.endEditBlock()
        if hasattr(self, "_invalidate_segment_cache"):
            self._invalidate_segment_cache()
        self._schedule_timeline()

    def _partial_insert_segment_parts(self, seg: dict) -> tuple[float, list[str], str]:
        text = str(seg.get("text", "") or "").replace("\r", "")
        parts = [part.strip() for part in text.split("\n") if part.strip()]
        start_sec = self._frame_time(seg.get("start", 0))
        current_spk = seg.get("speaker_list", [self.settings.get("spk1_id", "00")])[0] if seg.get("speaker_list") else self.settings.get("spk1_id", "00")
        return start_sec, parts, current_spk

    def _partial_insert_write_segment(self, cur: QTextCursor, seg: dict, *, current_spk: str, parts: list[str], spk1_id: str, spk2_id: str) -> None:
        cur.insertText(parts[0])
        cur.block().setUserData(SubtitleBlockData(current_spk, self._frame_time(seg.get("start", 0))))
        for line_text in parts[1:]:
            if line_text.startswith("-"):
                current_spk = spk2_id if current_spk == spk1_id else spk1_id
                cur.insertBlock()
                cur.insertText(line_text)
                cur.block().setUserData(SubtitleBlockData(current_spk, self._frame_time(seg.get("start", 0))))
            else:
                cur.insertText("\u2028" + line_text)

    def _partial_insert_gap_after_segment(self, cur: QTextCursor, seg: dict, next_seg: dict | None) -> None:
        gap_start = self._frame_time(seg["end"])
        if isinstance(next_seg, dict):
            if seg["end"] < next_seg["start"] - 0.05:
                gap_end = self._frame_time(next_seg["start"])
                cur.insertBlock()
                cur.block().setUserData(SubtitleBlockData("00", gap_start, is_gap=True, end_sec=gap_end))
            return
        gap_end = None
        try:
            total_time = float(getattr(getattr(self, "video_player", None), "total_time", 0.0) or 0.0)
            if total_time > gap_start + 0.001:
                gap_end = self._frame_time(total_time)
        except Exception:
            gap_end = None
        cur.insertBlock()
        cur.block().setUserData(SubtitleBlockData("00", gap_start, is_gap=True, end_sec=gap_end))

    def insert_partial_segments(self, new_segments: list[dict]):
        try:
            new_segments = self._clamp_segments_to_clip_duration(new_segments, log_changes=False)
            if not new_segments:
                return
            self._undo_mgr.push_immediate()
            doc = self.text_edit.document()
            cur = QTextCursor(doc)
            if hasattr(self, "_partial_insert_pos"):
                cur.setPosition(self._partial_insert_pos)
            else:
                cur.movePosition(QTextCursor.MoveOperation.End)

            cur.beginEditBlock()
            spk1_id = self.settings.get("spk1_id", "00")
            spk2_id = self.settings.get("spk2_id", "01")
            for idx, seg in enumerate(new_segments):
                if not cur.atBlockStart():
                    cur.insertBlock()
                start_sec, parts, current_spk = self._partial_insert_segment_parts(seg)
                end_sec = self._frame_time(seg.get("end", start_sec))
                if not parts:
                    continue
                cur.insertText(parts[0])
                cur.block().setUserData(SubtitleBlockData(current_spk, start_sec, end_sec=end_sec))
                for line_text in parts[1:]:
                    if line_text.startswith("-"):
                        current_spk = spk2_id if current_spk == spk1_id else spk1_id
                        cur.insertBlock()
                        cur.insertText(line_text)
                        cur.block().setUserData(SubtitleBlockData(current_spk, start_sec, end_sec=end_sec))
                    else:
                        cur.insertText("\u2028" + line_text)
                next_seg = new_segments[idx + 1] if idx + 1 < len(new_segments) else None
                self._partial_insert_gap_after_segment(cur, seg, next_seg)

            if hasattr(self, "_invalidate_segment_cache"):
                self._invalidate_segment_cache()
            self._mark_dirty()
            self.text_edit.update_margins()
            cur.endEditBlock()
            self._schedule_timeline()
        except Exception as exc:
            get_logger().log(f"⚠️ 정밀 삽입 오류: {exc}")

    def _split_text_without_leading_dash(self, text: str) -> str:
        lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        if not lines:
            return ""
        if lines[0].startswith("-"):
            lines[0] = lines[0].lstrip("-").strip()
        return "\n".join(lines)

    def _set_split_cursor_and_timeline_focus(self, cur: QTextCursor, *, active_start: float, center_sec: float) -> None:
        self._sync_lock = True
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        self.text_edit.setTextCursor(cur)
        self._active_seg_start = active_start
        if hasattr(self, "timeline"):
            self.timeline.set_active(self._active_seg_start)
            self.timeline.center_to_sec(center_sec, smooth=True)
        self._sync_lock = False

    def _finalize_manual_edit_snapshot(self) -> None:
        self._mark_dirty()
        self._finalize_edit()
        arm_snapshot_undo = getattr(self, "_arm_snapshot_undo_routing", None)
        if callable(arm_snapshot_undo):
            arm_snapshot_undo()

    def split_segment_with_text(self, line_num: int, split_sec: float, cursor: int):
        doc = self.text_edit.document()
        block = doc.findBlockByNumber(int(line_num))
        if not block.isValid():
            return

        try:
            self._undo_mgr.push_immediate()
        except Exception:
            pass

        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData):
            return

        start_sec = self._frame_time(ud.start_sec)
        spk_id = ud.spk_id
        split_sec = self._frame_time(split_sec)

        try:
            canvas_segs = self.timeline.canvas.segments
            end_map = {s.get("line"): float(s.get("end", 0.0)) for s in canvas_segs if s.get("line") is not None}
            end_sec = end_map.get(int(line_num))
            if end_sec is not None:
                if split_sec <= start_sec + 0.05 or split_sec >= end_sec - 0.05:
                    return
            elif split_sec <= start_sec + 0.05:
                return
        except Exception:
            if split_sec <= start_sec + 0.05:
                return

        full_text = block.text().replace("\u2028", "\n")
        cursor = max(0, min(int(cursor), len(full_text)))
        left = full_text[:cursor].rstrip()
        right = full_text[cursor:].lstrip()
        if not left:
            return
        if not right:
            right = "새자막"

        left = self._split_text_without_leading_dash(left)
        right = self._split_text_without_leading_dash(right)
        if not left:
            return
        if not right:
            right = "새자막"

        left_doc = left.replace("\n", "\u2028")
        right_doc = right.replace("\n", "\u2028")

        cur = QTextCursor(block)
        cur.beginEditBlock()
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        cur.insertText(left_doc)
        cur.block().setUserData(SubtitleBlockData(spk_id, start_sec, is_gap=False))
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cur.insertBlock()
        cur.insertText(right_doc)
        cur.block().setUserData(SubtitleBlockData(spk_id, split_sec, is_gap=False))
        cur.endEditBlock()

        self._set_split_cursor_and_timeline_focus(cur, active_start=split_sec, center_sec=split_sec)
        self._finalize_manual_edit_snapshot()

    def _ensure_speaker_split_dash(self, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        return text if text.startswith("-") else f"- {text.lstrip('- ').strip()}"

    def split_speaker_segment_with_text(self, line_num: int, cursor: int):
        doc = self.text_edit.document()
        block = doc.findBlockByNumber(int(line_num))
        if not block.isValid():
            return

        try:
            self._undo_mgr.push_immediate()
        except Exception:
            pass

        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or getattr(ud, "is_gap", False):
            return

        start_sec = self._frame_time(ud.start_sec)
        current_spk = str(getattr(ud, "spk_id", "00") or "00")
        spk1_id = str(getattr(self, "settings", {}).get("spk1_id", "00") if hasattr(self, "settings") else "00")
        spk2_id = str(getattr(self, "settings", {}).get("spk2_id", "01") if hasattr(self, "settings") else "01")
        next_spk = spk2_id if current_spk == spk1_id else spk1_id

        full_text = block.text().replace("\u2028", "\n")
        cursor = max(0, min(int(cursor), len(full_text)))
        before = full_text[:cursor].strip()
        after = full_text[cursor:].strip()
        if not before or not after:
            return

        before_doc = self._ensure_speaker_split_dash(before).replace("\n", "\u2028")
        after_doc = self._ensure_speaker_split_dash(after).replace("\n", "\u2028")
        if not before_doc or not after_doc:
            return

        cur = QTextCursor(block)
        cur.beginEditBlock()
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        cur.insertText(before_doc)
        cur.block().setUserData(SubtitleBlockData(current_spk, start_sec, is_gap=False))
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cur.insertBlock()
        cur.insertText(after_doc)
        cur.block().setUserData(SubtitleBlockData(next_spk, start_sec, is_gap=False))
        cur.endEditBlock()

        self._sync_lock = True
        self.text_edit.setTextCursor(cur)
        if hasattr(self, "timeline"):
            self.timeline.set_active(start_sec)
            self.timeline.center_to_sec(start_sec, smooth=True)
        self._sync_lock = False
        self._finalize_manual_edit_snapshot()
