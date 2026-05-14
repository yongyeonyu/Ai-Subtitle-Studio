"""Text replace, cache line mutation, and popup helpers for editor segments."""

from __future__ import annotations

from bisect import bisect_left, bisect_right

from PyQt6.QtGui import QTextCursor

from ui.editor.editor_helpers import build_segment_lookup
from ui.editor.subtitle_text_edit import SubtitleBlockData


class EditorSegmentsTextOpsMixin:
    def _refresh_visible_quality_map(self) -> None:
        highlighter = getattr(self, "_highlighter", None)
        text_edit = getattr(self, "text_edit", None)
        if highlighter is None or text_edit is None or not hasattr(highlighter, "set_quality_map"):
            return
        cache = getattr(self, "_subtitle_memory_cache", None)
        if not isinstance(cache, dict):
            cached = getattr(self, "_cached_segs", None)
            cache = build_segment_lookup(cached) if cached is not None else self._rebuild_subtitle_memory_cache()
            self._subtitle_memory_cache = cache
        try:
            start_line, end_line = text_edit.visible_block_number_range(pad_before=42, pad_after=96)
            visible_lines = range(int(start_line), int(end_line) + 1)
        except Exception:
            start_line, end_line = 0, 512
            visible_lines = range(start_line, end_line + 1)

        line_map = cache.get("line_map") or {}
        line_numbers = cache.get("line_numbers") or []
        left = bisect_left(line_numbers, int(start_line))
        right = bisect_right(line_numbers, int(end_line))
        quality_map: dict[int, dict] = {}
        for line in line_numbers[left:right]:
            seg = line_map.get(int(line))
            if isinstance(seg, dict) and seg.get("quality"):
                quality_map[int(line)] = seg.get("quality") or {}

        try:
            current_line = int(text_edit.textCursor().blockNumber())
            seg = line_map.get(current_line)
            if isinstance(seg, dict) and seg.get("quality"):
                quality_map[current_line] = seg.get("quality") or {}
        except Exception:
            pass

        try:
            highlighter.set_quality_map(quality_map, visible_lines=visible_lines)
        except TypeError:
            highlighter.set_quality_map(quality_map)

    def _update_subtitle_memory_line_text(self, line_num: int, text: str) -> bool:
        visible_text = str(text or "").replace("\u2028", "\n").strip()
        changed = False
        found = False
        visibility_changed = False
        try:
            line_key = int(line_num)
        except Exception:
            line_key = -1

        cached_line_map = getattr(self, "_cached_line_map", None)
        if not isinstance(cached_line_map, dict):
            cached_line_map = self._refresh_cached_line_map()
        seg = cached_line_map.get(line_key)
        if isinstance(seg, dict):
            found = True
            old_text = str(seg.get("text", "") or "")
            changed = old_text != visible_text
            visibility_changed = bool(old_text.strip()) != bool(visible_text.strip())
            seg["text"] = visible_text
            if changed and seg.get("quality"):
                seg["quality_stale"] = True

        cache = getattr(self, "_subtitle_memory_cache", None)
        if isinstance(cache, dict):
            lookup_seg = (cache.get("line_map") or {}).get(line_key)
            if isinstance(lookup_seg, dict):
                found = True
                lookup_old_text = str(lookup_seg.get("text", "") or "")
                changed = changed or lookup_old_text != visible_text
                visibility_changed = visibility_changed or (bool(lookup_old_text.strip()) != bool(visible_text.strip()))
                lookup_seg["text"] = visible_text
                if changed and lookup_seg.get("quality"):
                    lookup_seg["quality_stale"] = True
            if changed and visibility_changed:
                self._subtitle_memory_cache = build_segment_lookup(getattr(self, "_cached_segs", []) or [])
                self._refresh_cached_line_map()
                self._subtitle_context_window_index_cache = {}
                self._subtitle_memory_visible_window_cache = {}
                self._subtitle_memory_visible_window_last_key = None
                self._subtitle_memory_visible_window_last_result = None
                self._subtitle_context_index_epoch = int(getattr(self, "_subtitle_context_index_epoch", 0) or 0) + 1
        self._segment_cache_valid = bool(found)
        self._subtitle_text_visibility_changed = bool(visibility_changed)
        try:
            self._last_segment_cache_block_count = int(self.text_edit.document().blockCount())
        except Exception:
            pass
        return changed or not found

    def _update_timeline_segment_text_line(self, line_num: int, text: str) -> bool:
        timeline = getattr(self, "timeline", None)
        canvas = getattr(timeline, "canvas", None)
        if canvas is None:
            return False
        try:
            line_key = int(line_num)
        except Exception:
            return False
        visible_text = str(text or "").replace("\u2028", "\n")
        try:
            seg = canvas._segment_for_line(line_key) if hasattr(canvas, "_segment_for_line") else None
        except Exception:
            seg = None
        if not isinstance(seg, dict):
            for item in list(getattr(canvas, "segments", []) or []):
                try:
                    if int(item.get("line", -999999)) == line_key:
                        seg = item
                        break
                except Exception:
                    continue
        if not isinstance(seg, dict):
            return False
        if str(seg.get("text", "") or "") == visible_text:
            return False
        try:
            dirty = canvas._segment_repaint_rect(seg, margin=72) if hasattr(canvas, "_segment_repaint_rect") else None
        except Exception:
            dirty = None
        seg["text"] = visible_text
        if seg.get("quality"):
            seg["quality_stale"] = True
        if hasattr(canvas, "_segment_visual_style_cache"):
            try:
                canvas._segment_visual_style_cache = {}
            except Exception:
                pass
        try:
            if dirty is not None and hasattr(canvas, "_update_dirty_rect"):
                canvas._update_dirty_rect(dirty)
            else:
                canvas.update()
        except Exception:
            pass
        return True

    def _trigger_editor_popup(self, word, anchor, end_c, gpos):
        self.editor_popup.trigger(word, anchor, end_c, gpos)

    def _replace_text_in_all_subtitles(self, old_text: str, new_text: str, *, anchor=None, end_cursor=None) -> int:
        old_text = str(old_text or "")
        new_text = str(new_text or "")
        if not old_text or old_text == new_text or not hasattr(self, "text_edit"):
            return 0

        doc = self.text_edit.document()
        matches_by_line: dict[int, list[int]] = {}
        block = doc.begin()
        while block.isValid():
            ud = block.userData()
            if isinstance(ud, SubtitleBlockData) and not getattr(ud, "is_gap", False):
                text = block.text()
                positions = []
                start = text.find(old_text)
                while start >= 0:
                    positions.append(start)
                    start = text.find(old_text, start + len(old_text))
                if positions:
                    matches_by_line[int(block.blockNumber())] = positions
            block = block.next()

        replace_count = sum(len(v) for v in matches_by_line.values())
        if replace_count <= 0:
            return 0

        selected_line = -1
        selected_offset = 0
        cursor_ref = anchor if anchor is not None else end_cursor
        if cursor_ref is not None:
            try:
                anchor_block = doc.findBlock(cursor_ref.position())
                if anchor_block.isValid():
                    selected_line = int(anchor_block.blockNumber())
                    selected_offset = int(cursor_ref.position() - anchor_block.position())
            except Exception:
                selected_line = -1

        try:
            if hasattr(self, "_undo_mgr"):
                self._undo_mgr.push_immediate()
        except Exception:
            pass

        prev_inline = bool(getattr(self, "_inline_updating", False))
        self._inline_updating = True
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        try:
            for line_num in sorted(matches_by_line.keys(), reverse=True):
                block = doc.findBlockByNumber(line_num)
                if not block.isValid():
                    continue
                base_pos = int(block.position())
                for offset in sorted(matches_by_line[line_num], reverse=True):
                    cur.setPosition(base_pos + offset)
                    cur.setPosition(base_pos + offset + len(old_text), QTextCursor.MoveMode.KeepAnchor)
                    cur.insertText(new_text)
        finally:
            cur.endEditBlock()
            self._inline_updating = prev_inline

        if selected_line >= 0:
            try:
                selected_block = doc.findBlockByNumber(selected_line)
                if selected_block.isValid():
                    before_selected = sum(1 for offset in matches_by_line.get(selected_line, []) if offset < selected_offset)
                    adjusted_offset = selected_offset + before_selected * (len(new_text) - len(old_text))
                    cur = QTextCursor(selected_block)
                    cur.setPosition(selected_block.position() + max(0, adjusted_offset) + len(new_text))
                    self.text_edit.setTextCursor(cur)
            except Exception:
                pass

        hl = getattr(self, "_highlighter", None)
        if hl and hasattr(hl, "mark_edited"):
            for line_num in matches_by_line:
                hl.mark_edited(line_num)
        if hasattr(self.text_edit, "update_margins"):
            self.text_edit.update_margins()
        if hasattr(self.text_edit, "timestampArea"):
            self.text_edit.timestampArea.update()

        try:
            self._rebuild_subtitle_memory_cache()
        except Exception:
            pass
        if hasattr(self, "_mark_dirty"):
            self._mark_dirty()
        if hasattr(self, "_schedule_timeline"):
            self._schedule_timeline()
        if hasattr(self, "_refresh_video_subtitle_context"):
            self._refresh_video_subtitle_context()
        return replace_count
