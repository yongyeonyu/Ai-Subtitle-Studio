"""Text replace, cache line mutation, and popup helpers for editor segments."""

from __future__ import annotations

from bisect import bisect_left, bisect_right

from PyQt6.QtGui import QTextCursor

from ui.editor.editor_helpers import build_segment_lookup
from ui.editor.subtitle_text_edit import (
    SubtitleBlockData,
    subtitle_block_data_from_meta,
    subtitle_block_data_to_meta,
)


_EDIT_CONFIRM_CLEAR_FLAGS = {
    "non_speech_hallucination_risk",
    "high_no_speech_prob",
    "outside_vad_speech",
    "high_cps",
    "quality_stale",
    "manual_temporary",
}


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

    def _manual_confirmed_quality_for_user_edit(
        self,
        quality: dict | None,
        *,
        reason: str = "user_edit_confirmed",
    ) -> tuple[dict, bool]:
        previous = dict(quality or {})
        flags: list[str] = []
        for raw_flag in list(previous.get("flags") or []):
            flag = str(raw_flag or "").strip()
            if not flag or flag in _EDIT_CONFIRM_CLEAR_FLAGS:
                continue
            if flag not in flags:
                flags.append(flag)
        if "manual_confirmed" not in flags:
            flags.append("manual_confirmed")
        updated = dict(previous)
        updated["flags"] = flags
        updated["confidence_label"] = "green"
        updated["confidence_reason"] = str(reason or "user_edit_confirmed")
        updated["manual_confirmed"] = True
        updated.pop("manual_temporary", None)
        return updated, updated != previous

    def _update_subtitle_memory_line_quality(
        self,
        line_num: int,
        quality: dict,
        *,
        quality_history: list[dict] | None = None,
        quality_signature: str | None = None,
    ) -> bool:
        found = False
        try:
            line_key = int(line_num)
        except Exception:
            return False
        next_quality = dict(quality or {})

        cached_line_map = getattr(self, "_cached_line_map", None)
        if not isinstance(cached_line_map, dict):
            cached_line_map = self._refresh_cached_line_map()
        seg = cached_line_map.get(line_key)
        if isinstance(seg, dict):
            found = True
            seg["quality"] = dict(next_quality)
            if quality_history is not None:
                seg["quality_history"] = list(quality_history or [])
            if quality_signature is not None:
                seg["quality_signature"] = str(quality_signature or "")
            seg.pop("quality_stale", None)

        cache = getattr(self, "_subtitle_memory_cache", None)
        if isinstance(cache, dict):
            lookup_seg = (cache.get("line_map") or {}).get(line_key)
            if isinstance(lookup_seg, dict):
                found = True
                lookup_seg["quality"] = dict(next_quality)
                if quality_history is not None:
                    lookup_seg["quality_history"] = list(quality_history or [])
                if quality_signature is not None:
                    lookup_seg["quality_signature"] = str(quality_signature or "")
                lookup_seg.pop("quality_stale", None)
        self._segment_cache_valid = bool(found)
        return found

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

    def _update_timeline_segment_quality_line(
        self,
        line_num: int,
        quality: dict,
        *,
        quality_signature: str | None = None,
    ) -> bool:
        timeline = getattr(self, "timeline", None)
        canvas = getattr(timeline, "canvas", None)
        if canvas is None:
            return False
        try:
            line_key = int(line_num)
        except Exception:
            return False
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
        next_quality = dict(quality or {})
        next_signature = None if quality_signature is None else str(quality_signature or "")
        current_signature = str(seg.get("quality_signature", "") or "")
        if dict(seg.get("quality") or {}) == next_quality and next_signature == current_signature and not seg.get("quality_stale"):
            return False
        try:
            dirty = canvas._segment_repaint_rect(seg, margin=72) if hasattr(canvas, "_segment_repaint_rect") else None
        except Exception:
            dirty = None
        seg["quality"] = dict(next_quality)
        if quality_signature is not None:
            seg["quality_signature"] = next_signature
        seg.pop("quality_stale", None)
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

    def _apply_manual_confirmed_quality_to_line(
        self,
        line_num: int,
        *,
        reason: str = "user_edit_confirmed",
    ) -> bool:
        text_edit = getattr(self, "text_edit", None)
        if text_edit is None:
            return False
        block = text_edit.document().findBlockByNumber(int(line_num))
        if not block.isValid():
            return False
        data = block.userData()
        if not isinstance(data, SubtitleBlockData) or bool(getattr(data, "is_gap", False)):
            return False

        meta = subtitle_block_data_to_meta(data)
        previous_quality = dict(meta.get("quality") or {})
        next_quality, changed = self._manual_confirmed_quality_for_user_edit(previous_quality, reason=reason)

        line_text = block.text().replace("\u2028", "\n")
        current_seg = self._segment_for_line(int(line_num)) if hasattr(self, "_segment_for_line") else None
        end_sec = meta.get("end_sec")
        if end_sec is None and isinstance(current_seg, dict):
            end_sec = current_seg.get("end", meta.get("start_sec"))
        signature = str(meta.get("quality_signature", "") or "")
        if hasattr(self, "_segment_quality_signature"):
            signature = self._segment_quality_signature(
                {
                    "start": meta.get("start_sec", getattr(data, "start_sec", 0.0)),
                    "end": end_sec if end_sec is not None else meta.get("start_sec", getattr(data, "start_sec", 0.0)),
                    "text": line_text,
                    "speaker": meta.get("spk_id", getattr(data, "spk_id", "")),
                }
            )

        if not changed and signature == str(meta.get("quality_signature", "") or ""):
            return False

        history = list(meta.get("quality_history") or [])
        if changed and previous_quality and previous_quality != next_quality:
            history.append(dict(previous_quality))
        meta["quality"] = dict(next_quality)
        meta["quality_history"] = history
        meta["quality_signature"] = signature
        if end_sec is not None:
            meta["end_sec"] = end_sec
        block.setUserData(subtitle_block_data_from_meta(meta))

        self._update_subtitle_memory_line_quality(
            int(line_num),
            next_quality,
            quality_history=history,
            quality_signature=signature,
        )
        self._update_timeline_segment_quality_line(
            int(line_num),
            next_quality,
            quality_signature=signature,
        )
        refresher = getattr(self, "_refresh_visible_quality_map", None)
        if callable(refresher):
            try:
                refresher()
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
