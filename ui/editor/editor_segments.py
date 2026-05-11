# Version: 03.14.29
# Phase: PHASE2
"""
ui/editor_segments.py
EditorWidget의 자막 에디터 조작, 큐 처리, 세그먼트 I/O 메서드 모음.
[수정] core 폴더 이동에 따른 데이터 매니저 경로 및 상대 경로 최적화 완료
"""
import hashlib
import json
import os
import re
import threading
import time
from bisect import bisect_left, bisect_right
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QTextCursor

from core.runtime.logger import get_logger
from core.native_swift_timeline import (
    build_live_subtitle_preview_via_swift,
    plan_stt_candidate_selection_via_swift,
    prepare_editor_segments_for_load_via_swift,
)
from core.engine.subtitle_timing import align_stt_preview_to_subtitle_segments
from core.project.project_srt import strip_whisper_control_tokens

# 💡 [경로 수정] editor_data_manager -> core.data_manager
from core.project.data_manager import save_correction as _dm_save_correction

# 수정 — 절대 import로 통일 (editor_widget.py, editor_timeline_video.py와 동일)
from ui.editor.subtitle_text_edit import (
    SubtitleBlockData,
    subtitle_block_data_from_meta,
    subtitle_block_data_to_meta,
)
from ui.editor.editor_helpers import build_segment_lookup, find_segment_for_line_lookup, insert_gap_after
from ui.editor.editor_roughcut_draft import EditorRoughcutDraftMixin

class EditorSegmentsMixin(EditorRoughcutDraftMixin):
    """자막 에디터 조작 / 큐 처리 / 세그먼트 I/O"""
    # ---------------------------------------------------------
    # Common Helpers (여러 Mixin에서 공용)
    # ---------------------------------------------------------
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

    def _set_segment_start_to_playhead(self):
        self._undo_mgr.push_immediate()
        sec = self._snap_to_frame(getattr(self.timeline.canvas, 'playhead_sec', getattr(self.video_player, 'current_time', 0.0)))
        block = self._subtitle_segment_edit_target_block()
        if block is None:
            return
        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or ud.is_gap:
            return

        orig_start = float(ud.start_sec)
        cursor = self.text_edit.textCursor()
        cursor.beginEditBlock()

        first_block = block
        while first_block.previous().isValid():
            prev_data = first_block.previous().userData()
            if isinstance(prev_data, SubtitleBlockData) and not prev_data.is_gap and abs(float(prev_data.start_sec) - orig_start) < 0.05:
                first_block = first_block.previous()
            else:
                break

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

        if hasattr(self.text_edit, "update_margins"):
            self.text_edit.update_margins()
        cursor.endEditBlock()
        if hasattr(self.text_edit, 'timestampArea'):
            self.text_edit.timestampArea.update()
        self._redraw_timeline()

    def _set_segment_end_to_playhead(self):
        self._undo_mgr.push_immediate()
        sec = self._snap_to_frame(getattr(self.timeline.canvas, 'playhead_sec', getattr(self.video_player, 'current_time', 0.0)))
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

        last_block = block
        while True:
            nxt = last_block.next()
            if nxt.isValid():
                next_data = nxt.userData()
                if isinstance(next_data, SubtitleBlockData) and not next_data.is_gap and abs(float(next_data.start_sec) - orig_start) < 0.05:
                    last_block = nxt
                else:
                    break
            else:
                break

        next_block = last_block.next()
        if next_block.isValid() and isinstance(next_block.userData(), SubtitleBlockData) and next_block.userData().is_gap:
            next_block.userData().start_sec = sec
        else:
            insert_gap_after(last_block, sec)

        cursor.endEditBlock()
        if hasattr(self.text_edit, "update_margins"):
            self.text_edit.update_margins()
        if hasattr(self.text_edit, 'timestampArea'):
            self.text_edit.timestampArea.update()
        self._redraw_timeline()

    def _frame_time(self, sec: float) -> float:
        if hasattr(self, "_snap_to_frame"):
            return self._snap_to_frame(sec)
        return round(float(sec), 6)

    def _mark_dirty(self):
        if hasattr(self, "_has_unsaved_changes") and not self._has_unsaved_changes():
            return
        started_editing = False
        if hasattr(self, "sm"):
            if hasattr(self.sm, "start_editing") and not getattr(self.sm, "is_locked", False):
                self.sm.start_editing()
                started_editing = True
            else:
                self.sm.is_dirty = True
        else:
            self._is_dirty = True
        if started_editing and hasattr(self, "_note_editor_foreground_activity"):
            self._note_editor_foreground_activity()
        try:
            main_w = self.window()
            if hasattr(main_w, "_refresh_saved_status_label"):
                main_w._refresh_saved_status_label(is_dirty=True)
        except Exception:
            pass

    def _note_editor_foreground_activity(self):
        self._last_editor_foreground_activity_at = time.monotonic()
        try:
            main_w = self.window()
            reset_idle = getattr(main_w, "_reset_post_completion_idle_timer", None)
            if callable(reset_idle):
                reset_idle()
            pause_lora = getattr(main_w, "_pause_personalization_for_foreground_activity", None)
            if callable(pause_lora):
                pause_lora("subtitle_editor_edit")
        except Exception:
            pass

    def _request_editor_mode_runtime_release(self):
        self._note_editor_foreground_activity()

    def _invalidate_segment_cache(self) -> None:
        self._segment_cache_valid = False
        self._subtitle_memory_cache = None
        self._subtitle_context_window_index_cache = {}
        self._subtitle_memory_visible_window_cache = {}
        self._subtitle_memory_visible_window_last_key = None
        self._subtitle_memory_visible_window_last_result = None
        self._subtitle_context_index_epoch = int(getattr(self, "_subtitle_context_index_epoch", 0) or 0) + 1
        try:
            self._last_segment_cache_block_count = int(self.text_edit.document().blockCount())
        except Exception:
            pass

    def _rebuild_subtitle_memory_cache(self, segments: list[dict] | None = None) -> dict:
        segs = list(segments if segments is not None else self._get_current_segments(force_rebuild=True))
        self._cached_segs = segs
        self._refresh_cached_line_map()
        cache = build_segment_lookup(segs)
        self._subtitle_memory_cache = cache
        self._subtitle_context_window_index_cache = {}
        self._subtitle_memory_visible_window_cache = {}
        self._subtitle_memory_visible_window_last_key = None
        self._subtitle_memory_visible_window_last_result = None
        self._subtitle_context_index_epoch = int(getattr(self, "_subtitle_context_index_epoch", 0) or 0) + 1
        self._segment_cache_valid = True
        try:
            self._last_segment_cache_block_count = int(self.text_edit.document().blockCount())
        except Exception:
            pass
        return cache

    def _refresh_cached_line_map(self) -> dict[int, dict]:
        line_map: dict[int, dict] = {}
        for seg in list(getattr(self, "_cached_segs", []) or []):
            if not isinstance(seg, dict):
                continue
            try:
                line = int(seg.get("line", -1))
            except Exception:
                continue
            if line >= 0:
                line_map[line] = seg
        self._cached_line_map = line_map
        return line_map

    def _subtitle_block_data_from_segment(self, seg: dict | None) -> SubtitleBlockData | None:
        if not isinstance(seg, dict):
            return None
        spk1_id = self.settings.get("spk1_id", "00") if hasattr(self, "settings") else "00"
        try:
            start_sec = self._frame_time(max(0.0, float(seg.get("start", 0.0) or 0.0)))
        except Exception:
            start_sec = 0.0
        try:
            end_sec = self._frame_time(max(start_sec, float(seg.get("end", start_sec) or start_sec)))
        except Exception:
            end_sec = start_sec
        if end_sec <= start_sec:
            end_sec = self._frame_time(start_sec + 0.5)
        speaker = str(seg.get("speaker", seg.get("spk", spk1_id)) or spk1_id)
        clip_idx = seg.get("_clip_idx")
        try:
            clip_idx = int(clip_idx) if clip_idx is not None else None
        except Exception:
            clip_idx = None
        return SubtitleBlockData(
            speaker,
            start_sec,
            bool(seg.get("is_gap", False)),
            end_sec=end_sec,
            stt_mode=bool(seg.get("stt_mode", False)),
            stt_pending=bool(seg.get("stt_pending", False)),
            original_text=str(seg.get("original_text", "") or ""),
            dictated_text=str(seg.get("dictated_text", "") or ""),
            quality=dict(seg.get("quality") or {}),
            quality_history=list(seg.get("quality_history") or []),
            quality_candidates=list(seg.get("quality_candidates") or []),
            quality_signature=str(seg.get("quality_signature", "") or ""),
            clip_idx=clip_idx,
            clip_file=str(seg.get("_clip_file", "") or ""),
            stt_selected_source=str(seg.get("stt_selected_source", "") or ""),
            stt_ensemble_llm_selected_source=str(seg.get("stt_ensemble_llm_selected_source", "") or ""),
            stt_candidates=list(seg.get("stt_candidates") or []),
            stt_ensemble_source=str(seg.get("stt_ensemble_source", "") or ""),
            stt_ensemble_llm_selected_label=str(seg.get("stt_ensemble_llm_selected_label", "") or ""),
            stt_ensemble_similarity=seg.get("stt_ensemble_similarity"),
            stt_ensemble_needs_llm_review=bool(seg.get("stt_ensemble_needs_llm_review", False)),
            stt_ensemble_inserted_from_stt2=bool(seg.get("stt_ensemble_inserted_from_stt2", False)),
            stt_ensemble_word_rover=dict(seg.get("stt_ensemble_word_rover") or {}),
            score=seg.get("score"),
            stt_score=seg.get("stt_score"),
            score_color=str(seg.get("score_color", "") or ""),
            stt_score_color=str(seg.get("stt_score_color", "") or ""),
            stt_score_label=str(seg.get("stt_score_label", "") or ""),
            stt_score_flags=list(seg.get("stt_score_flags") or []),
            stt_score_components=dict(seg.get("stt_score_components") or {}),
            live_preview=bool(seg.get("live_preview", False)),
            live_preview_source=str(seg.get("live_preview_source", "") or ""),
            live_preview_stage=str(seg.get("live_preview_stage", "") or ""),
        )

    @staticmethod
    def _segment_matches_block_text(seg: dict | None, block_text: str) -> bool:
        if not isinstance(seg, dict):
            return False
        seg_text = str(seg.get("text", "") or "").replace("\u2028", "\n").strip()
        block_text = str(block_text or "").replace("\u2028", "\n").strip()
        if not seg_text and not block_text:
            return True
        if not seg_text or not block_text:
            return False
        seg_norm = re.sub(r"\s+", " ", seg_text)
        block_norm = re.sub(r"\s+", " ", block_text)
        return bool(
            seg_norm == block_norm
            or block_norm in seg_norm
            or seg_norm in block_norm
        )

    def _restore_block_user_data_from_cache(self, *, visible_only: bool) -> int:
        text_edit = getattr(self, "text_edit", None)
        if text_edit is None or not hasattr(text_edit, "document"):
            return 0
        cache_valid = bool(getattr(self, "_segment_cache_valid", False))
        if not cache_valid:
            try:
                self._rebuild_subtitle_memory_cache()
                cache_valid = bool(getattr(self, "_segment_cache_valid", False))
            except Exception:
                cache_valid = False
        cached_line_map = getattr(self, "_cached_line_map", None)
        if cache_valid and not isinstance(cached_line_map, dict):
            cached_line_map = self._refresh_cached_line_map()
        elif not isinstance(cached_line_map, dict):
            cached_line_map = {}
        snapshot = getattr(text_edit, "_timestamp_block_meta_snapshot", None)
        if not cached_line_map and not isinstance(snapshot, dict):
            return 0

        doc = text_edit.document()
        if visible_only:
            try:
                start_line, end_line = text_edit.visible_block_number_range(pad_before=32, pad_after=64)
            except Exception:
                start_line = 0
                end_line = max(0, int(doc.blockCount()) - 1)
        else:
            start_line = 0
            end_line = max(0, int(doc.blockCount()) - 1)

        repaired = 0
        block = doc.findBlockByNumber(int(start_line))
        while block.isValid() and block.blockNumber() <= int(end_line):
            current_meta = block.userData()
            seg = cached_line_map.get(int(block.blockNumber()))
            snapshot_meta = None
            if not isinstance(current_meta, SubtitleBlockData) and isinstance(snapshot, dict):
                snapshot_meta = snapshot.get(int(block.blockNumber()))
            if seg is not None and not self._segment_matches_block_text(seg, block.text()):
                block = block.next()
                continue
            needs_repair = not isinstance(current_meta, SubtitleBlockData)
            if cache_valid and isinstance(current_meta, SubtitleBlockData) and isinstance(seg, dict):
                try:
                    seg_start = self._frame_time(max(0.0, float(seg.get("start", 0.0) or 0.0)))
                    needs_repair = abs(float(current_meta.start_sec) - float(seg_start)) > 0.01
                except Exception:
                    needs_repair = False
            if needs_repair:
                meta = self._subtitle_block_data_from_segment(seg) if seg is not None else None
                if meta is None and isinstance(snapshot_meta, dict):
                    meta = subtitle_block_data_from_meta(snapshot_meta)
                if meta is not None:
                    block.setUserData(meta)
                    repaired += 1
            block = block.next()
        return repaired

    def _restore_visible_block_user_data(self) -> int:
        return self._restore_block_user_data_from_cache(visible_only=True)

    def _restore_all_block_user_data(self) -> int:
        return self._restore_block_user_data_from_cache(visible_only=False)

    def _refresh_editor_timestamp_metadata(self, *, full: bool = False) -> int:
        repaired = 0
        try:
            if full:
                repaired = int(self._restore_all_block_user_data() or 0)
            else:
                repaired = int(self._restore_visible_block_user_data() or 0)
        except Exception:
            repaired = 0
        text_edit = getattr(self, "text_edit", None)
        refresher = getattr(text_edit, "refresh_timestamp_layer", None) if text_edit is not None else None
        if callable(refresher):
            try:
                refresher()
            except Exception:
                pass
        else:
            timestamp_area = getattr(text_edit, "timestampArea", None) if text_edit is not None else None
            try:
                if timestamp_area is not None:
                    timestamp_area.show()
                    timestamp_area.raise_()
                    timestamp_area.update()
            except Exception:
                pass
        return repaired

    def _subtitle_memory_segments(self) -> list[dict]:
        cache = getattr(self, "_subtitle_memory_cache", None)
        if not isinstance(cache, dict):
            cached = getattr(self, "_cached_segs", None)
            cache = build_segment_lookup(cached) if cached is not None else self._rebuild_subtitle_memory_cache()
            self._subtitle_memory_cache = cache
        return list(cache.get("segments") or [])

    def _subtitle_memory_visible_segments(self) -> list[dict]:
        cache = getattr(self, "_subtitle_memory_cache", None)
        if not isinstance(cache, dict):
            cached = getattr(self, "_cached_segs", None)
            cache = build_segment_lookup(cached) if cached is not None else self._rebuild_subtitle_memory_cache()
            self._subtitle_memory_cache = cache
        return list(cache.get("visible_segments") or [])

    def _subtitle_context_window_seconds(self) -> tuple[float, float, int]:
        settings = getattr(self, "settings", {}) or {}
        before = settings.get("editor_video_context_before_sec", settings.get("editor_context_before_sec", 75.0))
        after = settings.get("editor_video_context_after_sec", settings.get("editor_context_after_sec", 105.0))
        max_segments = settings.get("editor_video_context_max_segments", settings.get("editor_context_max_segments", 480))
        cache_key = (id(settings), before, after, max_segments)
        if cache_key == getattr(self, "_subtitle_context_window_seconds_cache_key", None):
            cached = getattr(self, "_subtitle_context_window_seconds_cache", None)
            if cached is not None:
                return cached
        try:
            before = float(before)
        except Exception:
            before = 75.0
        try:
            after = float(after)
        except Exception:
            after = 105.0
        try:
            max_segments = int(max_segments)
        except Exception:
            max_segments = 480
        result = (
            max(10.0, min(before, 900.0)),
            max(20.0, min(after, 900.0)),
            max(48, min(max_segments, 3000)),
        )
        self._subtitle_context_window_seconds_cache_key = cache_key
        self._subtitle_context_window_seconds_cache = result
        return result

    def _subtitle_context_center_sec(self, *, local: bool = False) -> float:
        center = getattr(self, "_active_seg_start", None)
        try:
            canvas = getattr(getattr(self, "timeline", None), "canvas", None)
            if canvas is not None:
                center = getattr(canvas, "playhead_sec", center)
        except Exception:
            pass
        try:
            center = float(center if center is not None else 0.0)
        except Exception:
            center = 0.0
        if local and hasattr(self, "_global_to_local_sec"):
            try:
                center = float(self._global_to_local_sec(center))
            except Exception:
                pass
        return max(0.0, center)

    def _subtitle_context_window_from_segments(
        self,
        segments: list[dict] | tuple[dict, ...] | None,
        *,
        center_sec: float | None = None,
    ) -> list[dict]:
        rows, starts = self._subtitle_context_index_for_segments(segments)
        if not rows:
            return []
        before, after, max_segments = self._subtitle_context_window_seconds()
        if center_sec is None:
            center_sec = self._subtitle_context_center_sec()
        try:
            center = max(0.0, float(center_sec or 0.0))
        except Exception:
            center = 0.0
        left_sec = max(0.0, center - before)
        right_sec = center + after
        left = max(0, bisect_left(starts, left_sec) - 1)
        right = min(len(rows), bisect_right(starts, right_sec) + 1)
        window = rows[left:right]
        if len(window) <= max_segments:
            return [seg for seg in window if str(seg.get("text", "") or "").strip()]

        center_idx = min(len(rows) - 1, max(0, bisect_right(starts, center) - 1))
        half = max(1, max_segments // 2)
        trim_left = max(0, center_idx - half)
        trim_right = min(len(rows), trim_left + max_segments)
        trim_left = max(0, trim_right - max_segments)
        return [seg for seg in rows[trim_left:trim_right] if str(seg.get("text", "") or "").strip()]

    def _subtitle_context_index_for_segments(self, segments) -> tuple[list[dict], list[float]]:
        if segments is None:
            source = []
        elif isinstance(segments, (list, tuple)):
            source = segments
        else:
            source = list(segments or [])
        if not source:
            return [], []
        first = source[0] if source else None
        last = source[-1] if source else None
        key = (
            id(segments),
            len(source),
            id(first),
            id(last),
            int(getattr(self, "_subtitle_context_index_epoch", 0) or 0),
        )
        cache = getattr(self, "_subtitle_context_window_index_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._subtitle_context_window_index_cache = cache
        cached = cache.get(key)
        if cached is not None:
            return cached

        rows = [
            seg for seg in source
            if isinstance(seg, dict) and not seg.get("is_gap") and str(seg.get("text", "") or "").strip()
        ]
        starts: list[float] = []
        ordered = rows
        is_sorted = True
        prev = -1.0
        for seg in rows:
            try:
                start = float(seg.get("start", 0.0) or 0.0)
            except Exception:
                start = 0.0
            starts.append(start)
            if start < prev:
                is_sorted = False
            prev = start
        if not is_sorted:
            pairs = sorted(zip(starts, rows), key=lambda item: item[0])
            starts = [item[0] for item in pairs]
            ordered = [item[1] for item in pairs]
        result = (ordered, starts)
        if len(cache) >= 8:
            try:
                cache.pop(next(iter(cache)))
            except Exception:
                cache.clear()
        cache[key] = result
        return result

    def _subtitle_memory_visible_window(self, center_sec: float | None = None) -> list[dict]:
        cache = getattr(self, "_subtitle_memory_cache", None)
        if not isinstance(cache, dict):
            cached = getattr(self, "_cached_segs", None)
            cache = build_segment_lookup(cached) if cached is not None else self._rebuild_subtitle_memory_cache()
            self._subtitle_memory_cache = cache
        rows = cache.get("visible_segments") or []
        starts = cache.get("visible_starts") or []
        if rows and starts and len(rows) == len(starts):
            before, after, max_segments = self._subtitle_context_window_seconds()
            if center_sec is None:
                center_sec = self._subtitle_context_center_sec()
            try:
                center = max(0.0, float(center_sec or 0.0))
            except Exception:
                center = 0.0
            first = rows[0] if rows else None
            last = rows[-1] if rows else None
            hot_key = (
                id(rows),
                len(rows),
                id(first),
                id(last),
                int(getattr(self, "_subtitle_context_index_epoch", 0) or 0),
                round(center, 3),
                round(float(before), 3),
                round(float(after), 3),
                int(max_segments),
            )
            if hot_key == getattr(self, "_subtitle_memory_visible_window_last_key", None):
                hot_result = getattr(self, "_subtitle_memory_visible_window_last_result", None)
                if hot_result is not None:
                    return hot_result
            left_sec = max(0.0, center - before)
            right_sec = center + after
            left = max(0, bisect_left(starts, left_sec) - 1)
            right = min(len(rows), bisect_right(starts, right_sec) + 1)
            if right - left <= max_segments:
                trim_left, trim_right = left, right
            else:
                center_idx = min(len(rows) - 1, max(0, bisect_right(starts, center) - 1))
                half = max(1, max_segments // 2)
                trim_left = max(0, center_idx - half)
                trim_right = min(len(rows), trim_left + max_segments)
                trim_left = max(0, trim_right - max_segments)

            key = (
                id(rows),
                len(rows),
                id(first),
                id(last),
                int(getattr(self, "_subtitle_context_index_epoch", 0) or 0),
                int(trim_left),
                int(trim_right),
                int(max_segments),
            )
            window_cache = getattr(self, "_subtitle_memory_visible_window_cache", None)
            if not isinstance(window_cache, dict):
                window_cache = {}
                self._subtitle_memory_visible_window_cache = window_cache
            cached_window = window_cache.get(key)
            if cached_window is not None:
                self._subtitle_memory_visible_window_last_key = hot_key
                self._subtitle_memory_visible_window_last_result = cached_window
                return cached_window
            result = list(rows[trim_left:trim_right])
            if len(window_cache) >= 16:
                try:
                    window_cache.pop(next(iter(window_cache)))
                except Exception:
                    window_cache.clear()
            window_cache[key] = result
            self._subtitle_memory_visible_window_last_key = hot_key
            self._subtitle_memory_visible_window_last_result = result
            return result
        return self._subtitle_context_window_from_segments(rows, center_sec=center_sec)

    def _schedule_visible_quality_refresh(self) -> None:
        timer = getattr(self, "_visible_quality_refresh_timer", None)
        if timer is None:
            try:
                try:
                    timer = QTimer(self)
                except TypeError:
                    timer = QTimer()
                timer.setSingleShot(True)
                timer.timeout.connect(self._refresh_visible_quality_map)
                self._visible_quality_refresh_timer = timer
            except Exception:
                self._refresh_visible_quality_map()
                return
        try:
            timer.start(48)
        except Exception:
            self._refresh_visible_quality_map()

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
            # Rebuild only when the visible playback set changes. Plain text
            # edits keep the same lookup objects and avoid an O(n) rebuild per
            # keystroke.
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

    def _finalize_edit(self):
        self._invalidate_segment_cache()
        self.text_edit.update_margins()
        if hasattr(self.text_edit, 'timestampArea'):
            try:
                self.text_edit._schedule_timestamp_area_update()
            except Exception:
                self.text_edit.timestampArea.update()
        self._schedule_timeline()

    def _schedule_cursor_video_seek(self, sec: float, delay_ms: int = 72) -> None:
        try:
            self._pending_cursor_video_seek_sec = float(sec or 0.0)
        except Exception:
            self._pending_cursor_video_seek_sec = 0.0
        timer = getattr(self, "_cursor_video_seek_timer", None)
        if timer is None:
            self._flush_cursor_video_seek()
            return
        timer.start(max(0, int(delay_ms or 0)))

    def _flush_cursor_video_seek(self) -> None:
        player = getattr(self, "video_player", None)
        if player is None:
            return
        sec = getattr(self, "_pending_cursor_video_seek_sec", None)
        if sec is None:
            return
        self._pending_cursor_video_seek_sec = None
        try:
            player.seek(float(sec))
        except Exception:
            pass

    def _segment_quality_signature(self, seg: dict) -> str:
        payload = {
            "start": round(float(seg.get("start", 0.0) or 0.0), 3),
            "end": round(float(seg.get("end", seg.get("start", 0.0)) or 0.0), 3),
            "text": str(seg.get("text", "") or ""),
            "speaker": str(seg.get("speaker", seg.get("spk", "")) or ""),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _quality_kwargs_from_segment(self, seg: dict, *, signature: str | None = None) -> dict:
        quality = dict(seg.get("quality") or {})
        history = list(seg.get("quality_history") or [])
        candidates = list(seg.get("quality_candidates") or [])
        return {
            "quality": quality,
            "quality_history": history,
            "quality_candidates": candidates,
            "quality_signature": signature or str(seg.get("quality_signature", "") or ""),
        }

    def _quality_tooltip(self, seg: dict) -> str:
        quality = dict(seg.get("quality") or {})
        stage_confidence = dict(seg.get("subtitle_stage_confidence") or {})
        if not quality and not stage_confidence:
            return ""
        score = quality.get("confidence_score")
        label = str(quality.get("confidence_label") or "gray")
        reason = str(quality.get("confidence_reason") or "")
        flags = ", ".join(str(flag) for flag in (quality.get("flags") or ())[:6])
        candidates = len(seg.get("quality_candidates") or [])
        stale = " / stale" if seg.get("quality_stale") else ""
        score_text = "-" if score is None else f"{float(score):.1f}"
        lines = [f"품질 {label}{stale} · {score_text}점", f"사유: {reason or flags or 'ok'}", f"후보: {candidates}개"]
        stages = dict(stage_confidence.get("stages") or {})
        if stages:
            names = {"cut": "컷", "stt": "STT", "llm": "LLM", "lora": "LoRA", "final": "최종"}
            stage_bits = []
            for key in list(stage_confidence.get("stage_order") or ["cut", "stt", "llm", "lora", "final"]):
                item = dict(stages.get(key) or {})
                if not item:
                    continue
                stage_score = item.get("score")
                stage_score_text = "-" if stage_score is None else f"{float(stage_score):.0f}"
                stage_bits.append(f"{names.get(key, key)} {item.get('label', 'gray')} {stage_score_text}")
            if stage_bits:
                lines.append("단계 신뢰도: " + " · ".join(stage_bits))
        return "\n".join(lines)

    def _bulk_load_segments_to_document(self, segments: list[dict], *, preserve_view: bool = False) -> list[dict] | None:
        """Load already-final subtitle/project rows with one QTextDocument rewrite.

        Live generation still uses the queue path because it needs gap push/pull
        behavior. Project/SRT restore is different: rows are already timed, so a
        single document rewrite avoids thousands of per-row insert/layout/undo
        updates on long files.
        """
        text_edit = getattr(self, "text_edit", None)
        if text_edit is None or not hasattr(text_edit, "setPlainText"):
            return None
        doc = text_edit.document() if hasattr(text_edit, "document") else None
        if doc is None:
            return None

        rows = list(segments or [])
        native_prepared_rows = None
        try:
            native_prepared_rows = prepare_editor_segments_for_load_via_swift(
                segments=rows,
                fps=float(getattr(self, "video_fps", 30.0) or 30.0),
            )
        except Exception:
            native_prepared_rows = None
        native_prepared_by_source: dict[int, dict] = {}
        if isinstance(native_prepared_rows, list):
            for item in native_prepared_rows:
                if not isinstance(item, dict):
                    continue
                try:
                    source_index = int(item.get("sourceIndex", -1))
                except Exception:
                    continue
                if source_index >= 0:
                    native_prepared_by_source[source_index] = item
        block_texts: list[str] = []
        block_meta: list[SubtitleBlockData] = []
        display_rows: list[dict] = []
        spk1_id = self.settings.get("spk1_id", "00") if hasattr(self, "settings") else "00"
        spk2_id = self.settings.get("spk2_id", "01") if hasattr(self, "settings") else "01"
        no_match = re.compile(r"(?!)")
        junk_ts = getattr(self, "_JUNK_TS_RE", no_match)
        junk_three = getattr(self, "_JUNK_NO_BRACKET_3PART", no_match)
        junk_three_end = getattr(self, "_JUNK_NO_BRACKET_3PART_END", no_match)
        junk_start = getattr(self, "_JUNK_START_RE", no_match)

        for idx, raw_seg in enumerate(rows):
            if not isinstance(raw_seg, dict):
                continue
            seg = dict(raw_seg)
            native_prepared = native_prepared_by_source.get(idx)
            if isinstance(native_prepared, dict):
                try:
                    start_sec = float(native_prepared.get("start", 0.0) or 0.0)
                except Exception:
                    start_sec = 0.0
                try:
                    end_sec = float(native_prepared.get("end", start_sec) or start_sec)
                except Exception:
                    end_sec = start_sec
                is_gap = bool(native_prepared.get("isGap", seg.get("is_gap", False)))
                parts = [
                    str(part or "")
                    for part in list(native_prepared.get("parts") or [])
                    if str(part or "")
                ]
                normalized_text = str(native_prepared.get("text", "") or "")
            else:
                try:
                    start_sec = self._frame_time(max(0.0, float(seg.get("start", 0.0) or 0.0)))
                except Exception:
                    start_sec = 0.0
                try:
                    end_sec = self._frame_time(max(start_sec, float(seg.get("end", start_sec) or start_sec)))
                except Exception:
                    end_sec = start_sec
                if end_sec <= start_sec:
                    end_sec = self._frame_time(start_sec + 0.5)
                is_gap = bool(seg.get("is_gap"))
                text = str(seg.get("text", "") or "").replace("\u2028", "\n")
                text = junk_ts.sub("", text)
                text = junk_three.sub("", text)
                text = junk_three_end.sub("", text)
                text = junk_start.sub("", text).strip()
                text = re.sub(r"<[^>]+>", "", text.replace("\r", ""))
                parts = [re.sub(r"[ \t\f\v]+", " ", part).strip() for part in text.split("\n")]
                parts = [part for part in parts if part]
                normalized_text = "\n".join(parts)

            if is_gap:
                first_line = len(block_texts)
                block_texts.append("")
                block_meta.append(SubtitleBlockData("00", start_sec, is_gap=True, end_sec=end_sec))
                display = dict(seg)
                display["line"] = first_line
                display["start"] = start_sec
                display["end"] = end_sec
                display["text"] = str(seg.get("text", "") or "")
                display["is_gap"] = True
                display_rows.append(display)
                continue

            if not parts:
                continue

            spk_list = list(seg.get("speaker_list", []) or [])
            current_spk = str((spk_list[0] if spk_list else seg.get("speaker", seg.get("spk", spk1_id))) or spk1_id)
            stt_kwargs = {
                "stt_mode": bool(seg.get("stt_mode", False)),
                "stt_pending": bool(seg.get("stt_pending", False)),
                "original_text": str(seg.get("original_text", "") or ""),
                "dictated_text": str(seg.get("dictated_text", "") or ""),
                "stt_selected_source": str(seg.get("stt_selected_source", "") or ""),
                "stt_ensemble_llm_selected_source": str(seg.get("stt_ensemble_llm_selected_source", "") or ""),
                "stt_candidates": list(seg.get("stt_candidates") or []),
                "stt_ensemble_source": str(seg.get("stt_ensemble_source", "") or ""),
                "stt_ensemble_llm_selected_label": str(seg.get("stt_ensemble_llm_selected_label", "") or ""),
                "stt_ensemble_similarity": seg.get("stt_ensemble_similarity"),
                "stt_ensemble_needs_llm_review": bool(seg.get("stt_ensemble_needs_llm_review", False)),
                "stt_ensemble_inserted_from_stt2": bool(seg.get("stt_ensemble_inserted_from_stt2", False)),
                "stt_ensemble_word_rover": dict(seg.get("stt_ensemble_word_rover") or {}),
                "score": seg.get("score"),
                "stt_score": seg.get("stt_score"),
                "score_color": str(seg.get("score_color", "") or ""),
                "stt_score_color": str(seg.get("stt_score_color", "") or ""),
                "stt_score_label": str(seg.get("stt_score_label", "") or ""),
                "stt_score_flags": list(seg.get("stt_score_flags") or []),
                "stt_score_components": dict(seg.get("stt_score_components") or {}),
            }
            clip_idx = seg.get("_clip_idx")
            try:
                clip_idx = int(clip_idx) if clip_idx is not None else None
            except Exception:
                clip_idx = None
            clip_kwargs = {
                "clip_idx": clip_idx,
                "clip_file": str(seg.get("_clip_file", "") or ""),
            }
            quality_kwargs = self._quality_kwargs_from_segment(
                seg,
                signature=self._segment_quality_signature(
                    {
                        "start": start_sec,
                        "end": end_sec,
                        "text": parts[0],
                        "speaker": current_spk,
                    }
                ),
            )

            first_line = len(block_texts)
            block_texts.append(parts[0])
            block_meta.append(SubtitleBlockData(current_spk, start_sec, end_sec=end_sec, **stt_kwargs, **quality_kwargs, **clip_kwargs))
            for part in parts[1:]:
                if part.startswith("-"):
                    current_spk = spk2_id if current_spk == spk1_id else spk1_id
                    block_texts.append(part)
                    block_meta.append(SubtitleBlockData(current_spk, start_sec, end_sec=end_sec, **stt_kwargs, **quality_kwargs, **clip_kwargs))
                else:
                    block_texts[-1] = block_texts[-1] + "\u2028" + part

            display = dict(seg)
            display["line"] = first_line
            display["start"] = start_sec
            display["end"] = end_sec
            display["text"] = normalized_text
            display["speaker"] = str(seg.get("speaker", seg.get("spk", current_spk)) or current_spk)
            if clip_idx is not None:
                display["_clip_idx"] = clip_idx
            if clip_kwargs["clip_file"]:
                display["_clip_file"] = clip_kwargs["clip_file"]
            display_rows.append(display)

        prev_text_signals = False
        prev_doc_signals = False
        prev_undo = True
        prev_updates = True
        prev_timestamp_updates = True
        highlighter = getattr(self, "_highlighter", None)
        detached_highlighter = False
        timestamp_area = getattr(text_edit, "timestampArea", None)
        try:
            setattr(text_edit, "_bulk_segment_load_active", True)
            if hasattr(text_edit, "updatesEnabled") and hasattr(text_edit, "setUpdatesEnabled"):
                prev_updates = bool(text_edit.updatesEnabled())
                text_edit.setUpdatesEnabled(False)
            if timestamp_area is not None and hasattr(timestamp_area, "updatesEnabled") and hasattr(timestamp_area, "setUpdatesEnabled"):
                prev_timestamp_updates = bool(timestamp_area.updatesEnabled())
                timestamp_area.setUpdatesEnabled(False)
            if highlighter is not None and hasattr(highlighter, "setDocument"):
                try:
                    if highlighter.document() is doc:
                        highlighter.setDocument(None)
                        detached_highlighter = True
                except Exception:
                    detached_highlighter = False
            prev_text_signals = bool(text_edit.blockSignals(True))
            prev_doc_signals = bool(doc.blockSignals(True))
            if hasattr(text_edit, "isUndoRedoEnabled") and hasattr(text_edit, "setUndoRedoEnabled"):
                prev_undo = bool(text_edit.isUndoRedoEnabled())
                text_edit.setUndoRedoEnabled(False)
            text_edit.setPlainText("\n".join(block_texts))
            block = doc.begin()
            snapshot = {}
            for line_idx, meta in enumerate(block_meta):
                if not block.isValid():
                    break
                block.setUserData(meta)
                snapshot[int(line_idx)] = subtitle_block_data_to_meta(meta)
                block = block.next()
            if snapshot:
                setattr(text_edit, "_timestamp_block_meta_snapshot", snapshot)
            cursor = QTextCursor(doc)
            cursor.movePosition(QTextCursor.MoveOperation.End)
            text_edit.setTextCursor(cursor)
        finally:
            try:
                if hasattr(text_edit, "setUndoRedoEnabled"):
                    text_edit.setUndoRedoEnabled(prev_undo)
            except Exception:
                pass
            try:
                doc.blockSignals(prev_doc_signals)
            except Exception:
                pass
            try:
                text_edit.blockSignals(prev_text_signals)
            except Exception:
                pass
            try:
                if detached_highlighter and highlighter is not None and hasattr(highlighter, "setDocument"):
                    highlighter.setDocument(doc)
            except Exception:
                pass
            try:
                if timestamp_area is not None and hasattr(timestamp_area, "setUpdatesEnabled"):
                    timestamp_area.setUpdatesEnabled(prev_timestamp_updates)
            except Exception:
                pass
            try:
                if hasattr(text_edit, "setUpdatesEnabled"):
                    text_edit.setUpdatesEnabled(prev_updates)
            except Exception:
                pass
            try:
                setattr(text_edit, "_bulk_segment_load_active", False)
            except Exception:
                pass

        try:
            if hasattr(text_edit, "update_margins"):
                text_edit.update_margins()
            refresher = getattr(text_edit, "refresh_timestamp_layer", None)
            if callable(refresher):
                refresher()
            elif timestamp_area is not None and hasattr(timestamp_area, "update"):
                timestamp_area.update()
            quick_sync = getattr(text_edit, "_schedule_quick_layer_sync", None)
            if callable(quick_sync):
                quick_sync()
        except Exception:
            pass
        self._segment_queue.clear()
        self._is_initial_load = False
        if not preserve_view:
            try:
                if hasattr(self, "timeline"):
                    self.timeline.set_playhead(0.0)
                    self.timeline.center_to_sec(0.0, smooth=True)
                if hasattr(self, "video_player"):
                    self.video_player.seek(0.0)
            except Exception:
                pass
        return display_rows

    # ---------------------------------------------------------
    # Segment Queue
    # ---------------------------------------------------------
    def preview_stt_segments(self, segments: list[dict]):
        try:
            if hasattr(self, "status_lbl"):
                self.status_lbl.text()
        except RuntimeError:
            return
        if threading.current_thread() is not threading.main_thread():
            QTimer.singleShot(0, lambda s=list(segments): self.preview_stt_segments(s))
            return

        preview = []
        for seg in segments or []:
            try:
                start = self._frame_time(max(0.0, float(seg.get("start", 0.0) or 0.0)))
                end = self._frame_time(max(start + 0.05, float(seg.get("end", start + 0.5) or start + 0.5)))
            except Exception:
                continue
            text = strip_whisper_control_tokens(str(seg.get("text", "") or ""))
            if not text:
                continue
            item = dict(seg)
            item["start"] = start
            item["end"] = end
            item["text"] = text
            item["stt_preview_source"] = str(
                seg.get("stt_preview_source")
                or seg.get("stt_source")
                or seg.get("stt_ensemble_source")
                or "STT1"
            )
            item["stt_pending"] = True
            item["_live_stt_preview"] = True
            preview.append(item)

        if not preview:
            return

        existing_preview = list(getattr(self, "_live_stt_preview_segments", []) or [])
        existing_preview = self._drop_overlapping_preview(existing_preview, preview, same_source_only=True)
        self._live_stt_preview_segments = existing_preview + preview
        self._redraw_timeline_with_live_preview()
        self._queue_live_editor_preview_segments(preview)
        self._sync_live_preview_playhead_to_video(preview)

    def _sync_live_preview_playhead_to_video(self, preview: list[dict]) -> None:
        """Keep the video pane visibly following the newest live STT draft."""
        if not preview:
            return
        settings = getattr(self, "settings", {}) or {}
        follow_enabled = settings.get("editor_live_stt_preview_follow_video_enabled")
        if follow_enabled is None:
            follow_enabled = True
        if not bool(follow_enabled):
            return
        now = time.monotonic()
        try:
            interval = max(
                0.5,
                float(settings.get("editor_live_stt_preview_follow_interval_sec", 2.0) or 2.0),
            )
        except Exception:
            interval = 2.0
        last_at = float(getattr(self, "_last_live_stt_video_follow_at", 0.0) or 0.0)
        if now - last_at < interval:
            return
        self._last_live_stt_video_follow_at = now
        try:
            latest = max(
                preview,
                key=lambda seg: (
                    float(seg.get("start", 0.0) or 0.0),
                    float(seg.get("end", seg.get("start", 0.0)) or 0.0),
                ),
            )
            global_sec = self._frame_time(max(0.0, float(latest.get("start", 0.0) or 0.0)))
        except Exception:
            return

        self._sync_processing_segment_view(global_sec, show_thumbnail=False)

    def _sync_processing_segment_view(self, global_sec: float, *, show_thumbnail: bool = True) -> None:
        try:
            global_sec = self._frame_time(max(0.0, float(global_sec or 0.0)))
        except Exception:
            return

        last_sec = getattr(self, "_last_processing_video_seek_sec", None)
        try:
            if last_sec is not None and abs(float(last_sec) - global_sec) < 0.04:
                return
        except Exception:
            pass
        self._last_processing_video_seek_sec = global_sec
        self._active_seg_start = global_sec

        timeline = getattr(self, "timeline", None)
        if timeline is not None:
            if hasattr(timeline, "set_active"):
                try:
                    timeline.set_active(global_sec)
                except Exception:
                    pass
            if hasattr(timeline, "set_playhead"):
                try:
                    timeline.set_playhead(global_sec, preserve_center_lock=True)
                except TypeError:
                    try:
                        timeline.set_playhead(global_sec)
                    except Exception:
                        pass
                except Exception:
                    pass
            if hasattr(timeline, "center_to_sec"):
                try:
                    timeline.center_to_sec(global_sec, smooth=True)
                except TypeError:
                    try:
                        timeline.center_to_sec(global_sec)
                    except Exception:
                        pass
                except Exception:
                    pass

        local_sec = global_sec
        player = getattr(self, "video_player", None)
        canvas = getattr(timeline, "canvas", None) if timeline is not None else None
        boxes = list(getattr(canvas, "_multiclip_boxes", []) or [])
        if boxes and hasattr(self, "_resolve_active_context") and hasattr(self, "_apply_active_context"):
            try:
                ctx = self._resolve_active_context(global_sec=global_sec)
            except Exception:
                ctx = None
            if ctx:
                clip_file = str(ctx.get("clip_file", "") or "")
                local_sec = float(ctx.get("local_sec", global_sec) or 0.0)
                current_path = str(getattr(player, "_current_source_path", "") or "") if player is not None else ""
                same_source = bool(clip_file and current_path) and os.path.normpath(clip_file) == os.path.normpath(current_path)
                if clip_file and not same_source:
                    try:
                        self._apply_active_context(ctx, autoplay=False, show_thumbnail=show_thumbnail)
                        return
                    except Exception:
                        pass
                if hasattr(canvas, "_active_clip_idx"):
                    try:
                        canvas._active_clip_idx = int(ctx.get("clip_idx", 0) or 0)
                    except Exception:
                        pass
        elif hasattr(self, "_global_to_local_sec"):
            try:
                local_sec = float(self._global_to_local_sec(global_sec))
            except Exception:
                local_sec = global_sec

        if player is None:
            return
        try:
            if hasattr(player, "seek_direct"):
                player.seek_direct(local_sec)
            elif hasattr(player, "frame_step_seek"):
                player.frame_step_seek(local_sec)
            elif hasattr(player, "preview_seek"):
                player.preview_seek(local_sec)
            elif hasattr(player, "seek"):
                player.seek(local_sec)
            if hasattr(player, "set_subtitle_display_time"):
                player.set_subtitle_display_time(local_sec)
            if show_thumbnail:
                self._show_processing_segment_thumbnail(player, local_sec)
        except Exception:
            pass

    def _show_processing_segment_thumbnail(self, player, local_sec: float) -> None:
        extractor = getattr(player, "_extract_and_show_thumbnail_at", None)
        if not callable(extractor):
            return
        source_path = str(getattr(player, "_current_source_path", "") or getattr(self, "media_path", "") or "")
        if not source_path:
            return
        now = time.monotonic()
        last_at = float(getattr(self, "_last_processing_thumbnail_at", 0.0) or 0.0)
        last_sec = getattr(self, "_last_processing_thumbnail_sec", None)
        try:
            same_near_sec = last_sec is not None and abs(float(last_sec) - float(local_sec)) < 0.20
        except Exception:
            same_near_sec = False
        if same_near_sec and now - last_at < 0.80:
            return
        self._last_processing_thumbnail_at = now
        self._last_processing_thumbnail_sec = float(local_sec)
        try:
            extractor(source_path, float(local_sec))
        except Exception:
            pass

    def _live_editor_preview_key(self, seg: dict) -> tuple:
        try:
            start = round(float(seg.get("start", 0.0) or 0.0), 2)
            end = round(float(seg.get("end", start) or start), 2)
        except Exception:
            start = end = 0.0
        return (
            str(seg.get("stt_preview_source") or seg.get("stt_source") or "STT1").strip().upper(),
            start,
            end,
            str(seg.get("text", "") or "").strip(),
        )

    def _live_editor_preview_match(self, seg: dict, *, same_source_only: bool = True):
        try:
            start = float(seg.get("start", 0.0) or 0.0)
            end = float(seg.get("end", start) or start)
        except Exception:
            return None
        source = str(seg.get("stt_preview_source") or seg.get("stt_source") or "STT1").strip().upper()
        best = None
        block = self.text_edit.document().begin() if hasattr(self, "text_edit") else None
        while block is not None and block.isValid():
            data = block.userData()
            if isinstance(data, SubtitleBlockData) and getattr(data, "live_preview", False):
                preview_source = str(getattr(data, "live_preview_source", "") or "STT1").strip().upper()
                if same_source_only and preview_source != source:
                    block = block.next()
                    continue
                try:
                    block_start = float(getattr(data, "start_sec", 0.0) or 0.0)
                except Exception:
                    block_start = 0.0
                block_end = block_start + max(0.3, end - start)
                stored_index = -1
                for idx, stored in enumerate(list(getattr(self, "_live_editor_preview_segments", []) or [])):
                    stored_source = str(stored.get("stt_preview_source") or stored.get("stt_source") or "STT1").strip().upper()
                    if same_source_only and stored_source != preview_source:
                        continue
                    try:
                        stored_start = float(stored.get("start", 0.0) or 0.0)
                        stored_end = float(stored.get("end", stored_start) or stored_start)
                    except Exception:
                        continue
                    if abs(stored_start - block_start) <= 0.08:
                        stored_index = idx
                        block_end = stored_end
                        break
                overlaps = start < block_end + 0.12 and end > block_start - 0.12
                if overlaps:
                    score = abs(block_start - start)
                    if best is None or score < best[0]:
                        best = (score, block, stored_index)
            block = block.next() if block is not None else None
        if best is None:
            return None
        return best[1], int(best[2])

    def _replace_live_editor_preview_block_text(self, block, text: str) -> None:
        cursor = QTextCursor(block)
        cursor.setPosition(block.position())
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(text.replace("\n", "\u2028"))

    def _update_live_editor_preview_segment(self, seg: dict, *, focus: bool = True) -> bool:
        if not hasattr(self, "text_edit"):
            return False
        text = self._clean_live_editor_preview_text(seg.get("text", ""))
        if not text:
            return False
        match = self._live_editor_preview_match(seg, same_source_only=True)
        if match is None:
            return False
        block, stored_index = match
        if not block.isValid():
            return False
        try:
            start_sec = self._frame_time(max(0.0, float(seg.get("start", 0.0) or 0.0)))
        except Exception:
            start_sec = 0.0
        source = str(seg.get("stt_preview_source") or seg.get("stt_source") or "STT1").strip().upper()

        prev_inline = bool(getattr(self, "_inline_updating", False))
        prev_sync = bool(getattr(self, "_sync_lock", False))
        doc = self.text_edit.document()
        self._inline_updating = True
        self._sync_lock = True
        doc.blockSignals(True)
        try:
            self._replace_live_editor_preview_block_text(block, text)
            data = block.userData()
            spk_id = getattr(data, "spk_id", None) if isinstance(data, SubtitleBlockData) else None
            block.setUserData(
                SubtitleBlockData(
                    str(spk_id or getattr(self, "settings", {}).get("spk1_id", "00") if hasattr(self, "settings") else "00"),
                    start_sec,
                    stt_pending=True,
                    live_preview=True,
                    live_preview_source=source,
                    live_preview_stage=f"{source} 실시간 드래프트 갱신",
                )
            )
        finally:
            doc.blockSignals(False)
            self._sync_lock = prev_sync
            self._inline_updating = prev_inline

        updated = dict(seg)
        updated["start"] = start_sec
        updated["text"] = text
        updated["stt_preview_source"] = source
        previews = list(getattr(self, "_live_editor_preview_segments", []) or [])
        if 0 <= stored_index < len(previews):
            previews[stored_index] = updated
        else:
            previews.append(updated)
        self._live_editor_preview_segments = previews
        self._live_editor_preview_keys = {self._live_editor_preview_key(item) for item in previews}
        try:
            self.text_edit.update_margins()
        except Exception:
            pass
        try:
            if hasattr(self.text_edit, "timestampArea"):
                self.text_edit.timestampArea.update()
        except Exception:
            pass
        self._redraw_timeline_with_live_preview()
        if focus:
            self._focus_editor_block_for_processing_segment(
                {
                    "line": block.blockNumber(),
                    "start": start_sec,
                    "end": updated.get("end", start_sec),
                    "text": text,
                }
            )
        return True

    def _insert_live_editor_preview_segment(self, seg: dict, *, source: str | None = None) -> bool:
        if not hasattr(self, "text_edit"):
            return False
        text = self._clean_live_editor_preview_text(seg.get("text", ""))
        if not text:
            return False
        if self._update_live_editor_preview_segment(seg, focus=True):
            return True
        try:
            start_sec = self._frame_time(max(0.0, float(seg.get("start", 0.0) or 0.0)))
        except Exception:
            start_sec = 0.0
        source_label = str(source or seg.get("stt_preview_source") or seg.get("stt_source") or "WORK").strip().upper()
        prev_inline = bool(getattr(self, "_inline_updating", False))
        prev_sync = bool(getattr(self, "_sync_lock", False))
        doc = self.text_edit.document()
        self._inline_updating = True
        self._sync_lock = True
        doc.blockSignals(True)
        focused_payload = None
        try:
            cursor = QTextCursor(doc)
            cursor.beginEditBlock()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            if doc.blockCount() > 0 and doc.lastBlock().text().strip():
                cursor.insertText("\n")
            cursor.insertText(text.replace("\n", "\u2028"))
            cursor.block().setUserData(
                SubtitleBlockData(
                    str(getattr(self, "settings", {}).get("spk1_id", "00") if hasattr(self, "settings") else "00"),
                    start_sec,
                    stt_pending=True,
                    live_preview=True,
                    live_preview_source=source_label,
                    live_preview_stage=f"{source_label} 실시간 작업 중",
                )
            )
            focused_payload = {
                "line": cursor.block().blockNumber(),
                "start": start_sec,
                "end": seg.get("end", start_sec),
                "text": text,
            }
            cursor.endEditBlock()
        finally:
            doc.blockSignals(False)
            self._sync_lock = prev_sync
            self._inline_updating = prev_inline
        stored = dict(seg)
        stored["start"] = start_sec
        stored["text"] = text
        stored["stt_preview_source"] = source_label
        previews = list(getattr(self, "_live_editor_preview_segments", []) or [])
        previews.append(stored)
        self._live_editor_preview_segments = previews
        self._live_editor_preview_keys = {self._live_editor_preview_key(item) for item in previews}
        self._redraw_timeline_with_live_preview()
        self._focus_editor_block_for_processing_segment(focused_payload, prefer_last=True)
        return True

    def _queue_live_editor_preview_segments(self, preview: list[dict]) -> None:
        if not hasattr(self, "text_edit") or not preview:
            return
        queued = getattr(self, "_live_editor_preview_queue", None)
        if queued is None:
            self._live_editor_preview_queue = []
            queued = self._live_editor_preview_queue
        seen = getattr(self, "_live_editor_preview_keys", None)
        if seen is None:
            self._live_editor_preview_keys = set()
            seen = self._live_editor_preview_keys

        for seg in preview:
            if self._update_live_editor_preview_segment(seg, focus=True):
                continue
            key = self._live_editor_preview_key(seg)
            if key in seen:
                continue
            source = key[0]
            if source not in {"STT1", "STT"} and self._has_live_editor_preview_overlap(seg, prefer_primary=True):
                continue
            seen.add(key)
            queued.append(dict(seg))

        if not queued:
            return
        timer = getattr(self, "_live_editor_preview_timer", None)
        if timer is not None:
            try:
                if not timer.isActive():
                    timer.start(80)
                return
            except Exception:
                pass
        self._flush_live_editor_preview_queue()

    def _focus_editor_block_for_processing_segment(self, payload: dict | None, *, prefer_last: bool = False) -> bool:
        data = dict(payload or {})
        try:
            requested_start = float(data.get("start", 0.0) or 0.0)
        except Exception:
            requested_start = 0.0
        if not hasattr(self, "text_edit"):
            self._sync_processing_segment_view(requested_start, show_thumbnail=True)
            return False
        doc = self.text_edit.document()
        target_block = None
        target_start = None
        try:
            line = int(data.get("line", -1))
        except Exception:
            line = -1
        if line >= 0:
            block = doc.findBlockByNumber(line)
            if block.isValid():
                target_block = block

        requested_text = str(data.get("text", "") or "").replace("\u2028", "\n").strip()
        requested_flat = re.sub(r"\s+", " ", requested_text).strip()

        if target_block is None and (requested_start > 0.0 or requested_flat):
            candidates = []
            block = doc.begin()
            while block.isValid():
                block_data = block.userData()
                block_start = None
                if isinstance(block_data, SubtitleBlockData):
                    try:
                        block_start = float(getattr(block_data, "start_sec", 0.0) or 0.0)
                    except Exception:
                        block_start = None
                block_flat = re.sub(r"\s+", " ", str(block.text() or "").replace("\u2028", "\n")).strip()
                time_diff = abs((block_start if block_start is not None else 0.0) - requested_start)
                text_match = bool(requested_flat and block_flat and (block_flat == requested_flat or requested_flat.startswith(block_flat) or block_flat.startswith(requested_flat)))
                if (block_start is not None and time_diff <= 0.18) or text_match:
                    live_bonus = 0 if bool(getattr(block_data, "live_preview", False)) else 1
                    text_bonus = 0 if text_match else 1
                    candidates.append((live_bonus, text_bonus, time_diff, block.blockNumber(), block, block_start))
                block = block.next()
            if candidates:
                candidates.sort(key=lambda item: item[:4])
                _live_bonus, _text_bonus, _time_diff, _line, target_block, target_start = candidates[0]

        if target_block is None and prefer_last:
            target_block = doc.lastBlock()
        if target_block is None or not target_block.isValid():
            if requested_flat and self._insert_live_editor_preview_segment(data, source="WORK"):
                return True
            self._sync_processing_segment_view(requested_start, show_thumbnail=True)
            return False

        block_data = target_block.userData()
        if target_start is None and isinstance(block_data, SubtitleBlockData):
            try:
                target_start = float(getattr(block_data, "start_sec", 0.0) or 0.0)
            except Exception:
                target_start = None
        if target_start is None:
            target_start = requested_start

        prev_sync = bool(getattr(self, "_sync_lock", False))
        self._sync_lock = True
        try:
            cursor = QTextCursor(target_block)
            self.text_edit.setTextCursor(cursor)
            self.text_edit.ensureCursorVisible()
        finally:
            self._sync_lock = prev_sync

        line_num = target_block.blockNumber()
        highlighter = getattr(self, "_highlighter", None)
        if highlighter is not None and hasattr(highlighter, "set_current_line"):
            try:
                highlighter.set_current_line(line_num)
            except Exception:
                pass
        try:
            self._last_editor_autoscroll_at = time.monotonic()
        except Exception:
            pass
        if target_start is not None:
            self._sync_processing_segment_view(float(target_start), show_thumbnail=True)
        return True

    def _has_live_editor_preview_overlap(self, seg: dict, *, prefer_primary: bool = False) -> bool:
        try:
            start = float(seg.get("start", 0.0) or 0.0)
            end = float(seg.get("end", start) or start)
        except Exception:
            return False
        source = str(seg.get("stt_preview_source") or seg.get("stt_source") or "STT1").strip().upper()
        for existing in list(getattr(self, "_live_editor_preview_segments", []) or []):
            try:
                e_start = float(existing.get("start", 0.0) or 0.0)
                e_end = float(existing.get("end", e_start) or e_start)
            except Exception:
                continue
            if not (start < e_end + 0.05 and end > e_start - 0.05):
                continue
            e_source = str(existing.get("stt_preview_source") or existing.get("stt_source") or "STT1").strip().upper()
            if not prefer_primary or e_source in {"STT1", "STT"} or e_source == source:
                return True
        return False

    def _flush_live_editor_preview_queue(self) -> None:
        if not hasattr(self, "text_edit"):
            return
        queue = list(getattr(self, "_live_editor_preview_queue", []) or [])
        self._live_editor_preview_queue = []
        if not queue:
            return

        drafts = []
        for seg in sorted(queue, key=lambda row: (float(row.get("start", 0.0) or 0.0), float(row.get("end", 0.0) or 0.0))):
            if self._has_live_editor_preview_overlap(seg, prefer_primary=True):
                continue
            text = str(seg.get("text", "") or "").replace("\u2028", "\n").strip()
            if not text:
                continue
            draft = dict(seg)
            draft["text"] = text
            drafts.append(draft)
        if not drafts:
            return

        doc = self.text_edit.document()
        if not hasattr(self, "_live_editor_preview_segments"):
            self._live_editor_preview_segments = []
        prev_inline = bool(getattr(self, "_inline_updating", False))
        prev_sync = bool(getattr(self, "_sync_lock", False))
        self._inline_updating = True
        self._sync_lock = True
        focused_payload = None
        doc.blockSignals(True)
        try:
            cursor = QTextCursor(doc)
            cursor.beginEditBlock()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            if doc.blockCount() > 0 and doc.lastBlock().text().strip():
                cursor.insertText("\n")
            spk_id = str(getattr(self, "settings", {}).get("spk1_id", "00") if hasattr(self, "settings") else "00")
            for index, seg in enumerate(drafts):
                if index > 0:
                    cursor.insertText("\n")
                text = self._clean_live_editor_preview_text(seg.get("text", ""))
                if not text:
                    continue
                try:
                    start_sec = self._frame_time(max(0.0, float(seg.get("start", 0.0) or 0.0)))
                except Exception:
                    start_sec = 0.0
                source = str(seg.get("stt_preview_source") or seg.get("stt_source") or "STT1").strip().upper()
                cursor.insertText(text.replace("\n", "\u2028"))
                cursor.block().setUserData(
                    SubtitleBlockData(
                        spk_id,
                        start_sec,
                        stt_pending=True,
                        live_preview=True,
                        live_preview_source=source,
                        live_preview_stage=f"{source} 실시간 드래프트",
                    )
                )
                stored = dict(seg)
                stored["start"] = start_sec
                stored["stt_preview_source"] = source
                self._live_editor_preview_segments.append(stored)
                focused_payload = {
                    "line": cursor.block().blockNumber(),
                    "start": start_sec,
                    "end": stored.get("end", start_sec),
                    "text": text,
                }
            cursor.endEditBlock()
        finally:
            doc.blockSignals(False)
            self._sync_lock = prev_sync
            self._inline_updating = prev_inline

        try:
            self.text_edit.update_margins()
        except Exception:
            pass
        try:
            if hasattr(self.text_edit, "timestampArea"):
                self.text_edit.timestampArea.update()
        except Exception:
            pass
        self._set_live_preview_status(drafts)
        self._focus_editor_block_for_processing_segment(focused_payload, prefer_last=True)

    def _clean_live_editor_preview_text(self, text: str) -> str:
        text = str(text or "")
        for attr in (
            "_JUNK_TS_RE",
            "_JUNK_NO_BRACKET_3PART",
            "_JUNK_NO_BRACKET_3PART_END",
            "_JUNK_START_RE",
        ):
            pattern = getattr(self, attr, None)
            if pattern is not None and hasattr(pattern, "sub"):
                text = pattern.sub("", text)
        text = text.strip()
        text = re.sub(r"<[^>]+>", "", text)
        parts = [re.sub(r"[ \t\f\v]+", " ", part).strip() for part in text.replace("\r", "").split("\n")]
        return "\n".join(part for part in parts if part)

    def _set_live_preview_status(self, drafts: list[dict]) -> None:
        if not drafts or not hasattr(self, "set_live_processing_stage"):
            return
        sources = sorted({
            str(seg.get("stt_preview_source") or seg.get("stt_source") or "STT1").strip().upper()
            for seg in drafts
        })
        label = "/".join(source for source in sources if source) or "STT"
        self.set_live_processing_stage(f"{label} 실시간 자막 드래프트 표시 중 · {len(drafts)}개 추가")

    def _remove_live_editor_preview_overlapping(self, final_segments: list[dict]) -> None:
        if not hasattr(self, "text_edit") or not final_segments:
            return
        ranges = []
        for seg in final_segments:
            try:
                start = float(seg.get("start", 0.0) or 0.0)
                end = float(seg.get("end", start) or start)
            except Exception:
                continue
            if end > start:
                ranges.append((start, end))
        if not ranges:
            return
        cover_start = min(start for start, _ in ranges)
        cover_end = max(end for _, end in ranges)

        def _covered(start: float, end: float) -> bool:
            return end > cover_start - 0.12 and start < cover_end + 0.12

        doc = self.text_edit.document()
        to_remove = []
        block = doc.begin()
        while block.isValid():
            data = block.userData()
            if isinstance(data, SubtitleBlockData) and getattr(data, "live_preview", False):
                try:
                    start = float(getattr(data, "start_sec", 0.0) or 0.0)
                except Exception:
                    start = 0.0
                end = start + 0.5
                for preview in list(getattr(self, "_live_editor_preview_segments", []) or []):
                    try:
                        p_start = float(preview.get("start", 0.0) or 0.0)
                    except Exception:
                        continue
                    if abs(p_start - start) <= 0.03:
                        try:
                            end = float(preview.get("end", end) or end)
                        except Exception:
                            pass
                        break
                if _covered(start, end):
                    to_remove.append(block.blockNumber())
            block = block.next()
        if not to_remove:
            return

        prev_inline = bool(getattr(self, "_inline_updating", False))
        prev_sync = bool(getattr(self, "_sync_lock", False))
        self._inline_updating = True
        self._sync_lock = True
        doc.blockSignals(True)
        try:
            cursor = QTextCursor(doc)
            cursor.beginEditBlock()
            for line_num in sorted(to_remove, reverse=True):
                block = doc.findBlockByNumber(line_num)
                if not block.isValid():
                    continue
                cursor.setPosition(block.position())
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
                if block.next().isValid():
                    cursor.deleteChar()
                elif block.previous().isValid():
                    cursor.deletePreviousChar()
            cursor.endEditBlock()
        finally:
            doc.blockSignals(False)
            self._sync_lock = prev_sync
            self._inline_updating = prev_inline

        self._live_editor_preview_segments = [
            dict(seg)
            for seg in list(getattr(self, "_live_editor_preview_segments", []) or [])
            if not _covered(float(seg.get("start", 0.0) or 0.0), float(seg.get("end", seg.get("start", 0.0)) or 0.0))
        ]
        self._live_editor_preview_keys = {
            self._live_editor_preview_key(seg)
            for seg in list(getattr(self, "_live_editor_preview_segments", []) or [])
        }
        try:
            self.text_edit.update_margins()
        except Exception:
            pass
        try:
            if hasattr(self.text_edit, "timestampArea"):
                self.text_edit.timestampArea.update()
        except Exception:
            pass

    def _drop_overlapping_preview(self, preview: list[dict], final_segments: list[dict], *, same_source_only: bool = False) -> list[dict]:
        if not preview or not final_segments:
            return list(preview or [])
        ranges = []
        for seg in final_segments or []:
            try:
                ranges.append((
                    float(seg.get("start", 0.0) or 0.0),
                    float(seg.get("end", 0.0) or 0.0),
                    str(
                        seg.get("stt_preview_source")
                        or seg.get("stt_source")
                        or seg.get("stt_selected_source")
                        or seg.get("stt_ensemble_llm_selected_source")
                        or seg.get("stt_ensemble_source")
                        or ""
                    ).upper(),
                ))
            except Exception:
                continue
        if not ranges:
            return list(preview or [])

        kept = []
        for seg in preview:
            try:
                start = float(seg.get("start", 0.0) or 0.0)
                end = float(seg.get("end", start) or start)
                source = str(
                    seg.get("stt_preview_source")
                    or seg.get("stt_source")
                    or seg.get("stt_selected_source")
                    or seg.get("stt_ensemble_llm_selected_source")
                    or seg.get("stt_ensemble_source")
                    or ""
                ).upper()
            except Exception:
                continue
            overlaps = any(
                (not same_source_only or not r_source or not source or r_source == source)
                and start < r_end + 0.05
                and end > r_start - 0.05
                for r_start, r_end, r_source in ranges
            )
            if not overlaps:
                kept.append(seg)
        return kept

    def _build_live_subtitle_preview_segments_native(
        self,
        preview_segments: list[dict],
        confirmed_segments: list[dict] | None = None,
    ) -> list[dict] | None:
        try:
            fps = float(getattr(self, "video_fps", 30.0) or 30.0)
        except Exception:
            fps = 30.0
        rows = build_live_subtitle_preview_via_swift(
            preview_segments=preview_segments,
            confirmed_segments=confirmed_segments or [],
            fps=fps,
        )
        if not isinstance(rows, list):
            return None
        drafts: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized_row = dict(row)
            if "sttPreviewSource" in normalized_row and "stt_preview_source" not in normalized_row:
                normalized_row["stt_preview_source"] = normalized_row.get("sttPreviewSource")
            if "sttSource" in normalized_row and "stt_source" not in normalized_row:
                normalized_row["stt_source"] = normalized_row.get("sttSource")
            if "sttEnsembleSource" in normalized_row and "stt_ensemble_source" not in normalized_row:
                normalized_row["stt_ensemble_source"] = normalized_row.get("sttEnsembleSource")
            try:
                start = self._frame_time(float(normalized_row.get("start", 0.0) or 0.0))
                end = self._frame_time(float(normalized_row.get("end", start) or start))
            except Exception:
                continue
            text = str(normalized_row.get("text", "") or "").strip()
            if not text or end <= start:
                continue
            source = self._stt_candidate_source(normalized_row)
            try:
                score = float(normalized_row.get("sttScore", normalized_row.get("stt_score", normalized_row.get("score", 98.0))) or 98.0)
            except Exception:
                score = 98.0
            score = max(0.0, min(100.0, score if score > 1.0 else score * 100.0))
            candidate = dict(normalized_row)
            candidate["text"] = text
            candidate["source"] = source
            candidate["score"] = score
            candidate["stt_score"] = score
            draft = dict(normalized_row)
            draft["start"] = start
            draft["end"] = end
            draft["text"] = text
            draft["line"] = int(normalized_row.get("line", -1000 - len(drafts)) or (-1000 - len(drafts)))
            draft["_live_subtitle_preview"] = True
            draft["stt_ensemble_source"] = source
            draft["stt_candidates"] = [candidate]
            draft["score"] = score
            draft["stt_score"] = score
            draft["quality"] = {
                "confidence_label": "yellow",
                "confidence_score": score,
                "confidence_reason": f"{source} 실시간 자막 드래프트",
                "flags": ["live_subtitle_preview"],
            }
            drafts.append(draft)
        return drafts

    def _plan_stt_candidate_selection_native(
        self,
        current_segments: list[dict],
        candidate: dict,
    ) -> dict | None:
        try:
            fps = float(getattr(self, "video_fps", 30.0) or 30.0)
        except Exception:
            fps = 30.0
        return plan_stt_candidate_selection_via_swift(
            current_segments=current_segments,
            live_preview_segments=list(getattr(self, "_live_stt_preview_segments", []) or []),
            candidate=candidate,
            fps=fps,
        )

    def _build_live_subtitle_preview_segments(
        self,
        preview_segments: list[dict],
        confirmed_segments: list[dict] | None = None,
    ) -> list[dict]:
        """Build non-persistent subtitle-lane drafts from live STT candidates."""
        native_drafts = self._build_live_subtitle_preview_segments_native(
            preview_segments,
            confirmed_segments,
        )
        if native_drafts is not None:
            return native_drafts
        preview_segments = [dict(seg) for seg in list(preview_segments or []) if isinstance(seg, dict)]
        confirmed_segments = [
            dict(seg) for seg in list(confirmed_segments or [])
            if isinstance(seg, dict) and not seg.get("is_gap") and not seg.get("_live_subtitle_preview")
        ]
        preview_segments = self._drop_overlapping_preview(
            preview_segments,
            confirmed_segments,
            same_source_only=False,
        )
        if not preview_segments:
            return []

        def _as_float(value, default=0.0):
            try:
                return float(value)
            except Exception:
                return default

        def _source_priority(seg: dict) -> int:
            source = self._stt_candidate_source(seg)
            if source == "STT1":
                return 0
            if source in {"STT", ""}:
                return 1
            if source == "STT2":
                return 2
            return 3

        def _overlaps(left: dict, right: dict) -> bool:
            try:
                l_start = float(left.get("start", 0.0) or 0.0)
                l_end = float(left.get("end", l_start) or l_start)
                r_start = float(right.get("start", 0.0) or 0.0)
                r_end = float(right.get("end", r_start) or r_start)
            except Exception:
                return False
            return l_start < r_end + 0.05 and l_end > r_start - 0.05

        drafts: list[dict] = []
        ordered = sorted(
            preview_segments,
            key=lambda seg: (
                _as_float(seg.get("start")),
                _source_priority(seg),
                _as_float(seg.get("end")),
            ),
        )
        for seg in ordered:
            text = str(seg.get("text", "") or "").strip()
            if not text:
                continue
            start = self._frame_time(max(0.0, _as_float(seg.get("start"))))
            end = self._frame_time(max(start + 0.05, _as_float(seg.get("end"), start + 0.5)))
            source = self._stt_candidate_source(seg)
            try:
                score = float(seg.get("stt_score", seg.get("score", 98.0)) or 98.0)
            except Exception:
                score = 98.0
            score = max(0.0, min(100.0, score if score > 1.0 else score * 100.0))
            candidate = dict(seg)
            candidate["text"] = text
            candidate["source"] = source
            candidate["score"] = score
            candidate["stt_score"] = score
            draft = dict(seg)
            draft.pop("stt_pending", None)
            draft.pop("_live_stt_preview", None)
            draft["start"] = start
            draft["end"] = end
            draft["text"] = text
            draft["line"] = -1000 - len(drafts)
            draft["_live_subtitle_preview"] = True
            draft["stt_ensemble_source"] = source
            draft["stt_candidates"] = [candidate]
            draft["score"] = score
            draft["stt_score"] = score
            draft["quality"] = {
                "confidence_label": "yellow",
                "confidence_score": score,
                "confidence_reason": f"{source} 실시간 자막 드래프트",
                "flags": ["live_subtitle_preview"],
            }

            replace_idx = None
            skip = False
            for idx, existing in enumerate(drafts):
                if not _overlaps(draft, existing):
                    continue
                if _source_priority(draft) < _source_priority(existing):
                    replace_idx = idx
                else:
                    skip = True
                break
            if replace_idx is not None:
                drafts[replace_idx] = draft
            elif not skip:
                drafts.append(draft)

        for line, draft in enumerate(sorted(drafts, key=lambda seg: (seg["start"], seg["end"]))):
            draft["line"] = -1000 - line
        return sorted(drafts, key=lambda seg: (seg["start"], seg["end"]))

    def _stt_candidate_source(self, seg: dict) -> str:
        source = (
            seg.get("stt_preview_source")
            or seg.get("stt_source")
            or seg.get("stt_ensemble_source")
            or "STT1"
        )
        return str(source or "STT1").strip().upper()

    def _segment_overlap_ratio(self, left: dict, right: dict) -> float:
        try:
            l_start = float(left.get("start", 0.0) or 0.0)
            l_end = float(left.get("end", l_start) or l_start)
            r_start = float(right.get("start", 0.0) or 0.0)
            r_end = float(right.get("end", r_start) or r_start)
        except Exception:
            return 0.0
        overlap = max(0.0, min(l_end, r_end) - max(l_start, r_start))
        base = max(0.001, min(max(0.001, l_end - l_start), max(0.001, r_end - r_start)))
        return overlap / base

    def _segment_overlaps_time_range(self, seg: dict, start: float, end: float, pad: float = 0.001) -> bool:
        try:
            seg_start = float(seg.get("start", 0.0) or 0.0)
            seg_end = float(seg.get("end", seg_start) or seg_start)
        except Exception:
            return False
        return seg_start < end - pad and seg_end > start + pad

    def _best_final_segment_for_stt_candidate(self, segments: list[dict], candidate: dict) -> dict | None:
        try:
            cand_start = float(candidate.get("start", 0.0) or 0.0)
            cand_end = float(candidate.get("end", cand_start) or cand_start)
        except Exception:
            return None
        if cand_end <= cand_start:
            return None
        cand_dur = max(0.001, cand_end - cand_start)
        cand_center = (cand_start + cand_end) / 2.0
        best_seg = None
        best_score = 0.0
        fps = max(1.0, float(getattr(self, "video_fps", 30.0) or 30.0))
        edge_tol = max(0.18, min(0.45, 6.0 / fps))

        for seg in segments or []:
            if seg.get("is_gap"):
                continue
            try:
                start = float(seg.get("start", 0.0) or 0.0)
                end = float(seg.get("end", start) or start)
            except Exception:
                continue
            if end <= start:
                continue
            seg_dur = max(0.001, end - start)
            overlap = max(0.0, min(end, cand_end) - max(start, cand_start))
            center_bonus = 1.0 if start - edge_tol <= cand_center <= end + edge_tol else 0.0
            edge_bonus = 0.0
            if abs(cand_start - start) <= edge_tol:
                edge_bonus += 0.5
            if abs(cand_end - end) <= edge_tol:
                edge_bonus += 0.5
            if overlap <= 0.0 and not center_bonus:
                continue
            score = (overlap / cand_dur) * 0.55 + (overlap / seg_dur) * 0.30 + center_bonus * 0.10 + edge_bonus * 0.05
            if score > best_score:
                best_score = score
                best_seg = seg

        return dict(best_seg) if best_seg is not None and best_score >= 0.35 else None

    def _fit_stt_candidate_to_final_segment_slot(self, candidate: dict, segments: list[dict]) -> dict:
        placed = dict(candidate or {})
        target = self._best_final_segment_for_stt_candidate(segments, placed)
        if not target:
            placed["_stt_placement_mode"] = "raw"
            return placed

        try:
            cand_start = float(placed.get("start", 0.0) or 0.0)
            cand_end = float(placed.get("end", cand_start) or cand_start)
            target_start = float(target.get("start", 0.0) or 0.0)
            target_end = float(target.get("end", target_start) or target_start)
        except Exception:
            placed["_stt_placement_mode"] = "raw"
            return placed
        if cand_end <= cand_start or target_end <= target_start:
            placed["_stt_placement_mode"] = "raw"
            return placed

        cand_dur = max(0.001, cand_end - cand_start)
        target_dur = max(0.001, target_end - target_start)
        overlap = max(0.0, min(target_end, cand_end) - max(target_start, cand_start))
        cand_coverage = overlap / cand_dur
        target_coverage = overlap / target_dur
        fps = max(1.0, float(getattr(self, "video_fps", 30.0) or 30.0))
        edge_tol = max(0.18, min(0.45, 6.0 / fps))
        near_start = abs(cand_start - target_start) <= edge_tol
        near_end = abs(cand_end - target_end) <= edge_tol
        center = (cand_start + cand_end) / 2.0
        center_in_target = target_start - edge_tol <= center <= target_end + edge_tol

        if (
            (cand_coverage >= 0.80 and target_coverage >= 0.70)
            or (cand_coverage >= 0.75 and near_start and near_end)
            or (target_coverage >= 0.82 and center_in_target)
        ):
            placed["start"] = self._frame_time(target_start)
            placed["end"] = self._frame_time(target_end)
            placed["_stt_placement_mode"] = "replace_original_slot"
        elif overlap > 0.0 and center_in_target:
            placed["start"] = self._frame_time(max(cand_start, target_start))
            placed["end"] = self._frame_time(min(cand_end, target_end))
            placed["_stt_placement_mode"] = "clamp_to_original_slot"
        else:
            placed["_stt_placement_mode"] = "raw"

        placed["_stt_target_line"] = target.get("line")
        placed["_stt_target_start"] = target_start
        placed["_stt_target_end"] = target_end
        for key in ("speaker", "spk", "_clip_idx", "_clip_file"):
            if key in target and key not in placed:
                placed[key] = target[key]
        return placed

    def _trim_final_segments_around_candidate(self, segments: list[dict], candidate: dict) -> list[dict]:
        try:
            cand_start = self._frame_time(float(candidate.get("start", 0.0) or 0.0))
            cand_end = self._frame_time(float(candidate.get("end", cand_start) or cand_start))
        except Exception:
            return list(segments or [])
        min_keep = max(0.08, float(getattr(self, "video_fps", 30.0) and (2.0 / max(1.0, float(getattr(self, "video_fps", 30.0) or 30.0)))))
        trimmed: list[dict] = []
        for seg in segments or []:
            try:
                start = self._frame_time(float(seg.get("start", 0.0) or 0.0))
                end = self._frame_time(float(seg.get("end", start) or start))
            except Exception:
                continue
            if not self._segment_overlaps_time_range(seg, cand_start, cand_end):
                trimmed.append(dict(seg))
                continue
            if start < cand_start and cand_start - start >= min_keep:
                left = dict(seg)
                left["start"] = start
                left["end"] = self._frame_time(cand_start)
                trimmed.append(left)
            if cand_end < end and end - cand_end >= min_keep:
                right = dict(seg)
                right["start"] = self._frame_time(cand_end)
                right["end"] = end
                trimmed.append(right)
        return trimmed

    def _overlapping_final_segments_for_stt_candidate(self, segments: list[dict], candidate: dict) -> list[dict]:
        try:
            cand_start = self._frame_time(float(candidate.get("start", 0.0) or 0.0))
            cand_end = self._frame_time(float(candidate.get("end", cand_start) or cand_start))
        except Exception:
            return []
        overlaps: list[dict] = []
        for seg in segments or []:
            if self._segment_overlaps_time_range(seg, cand_start, cand_end):
                overlaps.append(dict(seg))
        return overlaps

    def _manual_exact_stt_candidate(self, candidate: dict, *, replaced_segments: list[dict]) -> dict:
        exact = dict(candidate or {})
        try:
            raw_start = float(candidate.get("start", 0.0) or 0.0)
            raw_end = float(candidate.get("end", raw_start) or raw_start)
        except Exception:
            raw_start, raw_end = 0.0, 0.0
        exact["start"] = self._frame_time(max(0.0, raw_start))
        exact["end"] = self._frame_time(max(float(exact["start"]) + 0.05, raw_end))
        exact["_stt_placement_mode"] = "manual_exact_candidate_timing"
        exact["_stt_original_candidate_start"] = raw_start
        exact["_stt_original_candidate_end"] = raw_end
        exact["_stt_replaced_segment_count"] = len(list(replaced_segments or []))
        if "start_frame" in candidate:
            exact["_stt_original_start_frame"] = candidate.get("start_frame")
        if "end_frame" in candidate:
            exact["_stt_original_end_frame"] = candidate.get("end_frame")
        return exact

    def _stt_selection_slot_for_candidate(self, segments: list[dict], candidate: dict) -> dict | None:
        target = self._best_final_segment_for_stt_candidate(segments, candidate)
        try:
            cand_start = self._frame_time(float(candidate.get("start", 0.0) or 0.0))
            cand_end = self._frame_time(float(candidate.get("end", cand_start) or cand_start))
        except Exception:
            return None
        if cand_end <= cand_start:
            return None
        fps = max(1.0, float(getattr(self, "video_fps", 30.0) or 30.0))
        edge_tol = max(0.12, min(0.35, 4.0 / fps))
        selected: list[dict] = []
        for seg in segments or []:
            if seg.get("is_gap"):
                continue
            try:
                start = self._frame_time(float(seg.get("start", 0.0) or 0.0))
                end = self._frame_time(float(seg.get("end", start) or start))
            except Exception:
                continue
            if end <= start:
                continue
            overlap = max(0.0, min(end, cand_end) - max(start, cand_start))
            if overlap <= 0.0:
                continue
            same_target = (
                target is not None
                and int(seg.get("line", -999999)) == int(target.get("line", -888888))
                and abs(float(seg.get("start", 0.0) or 0.0) - float(target.get("start", 0.0) or 0.0)) < 0.05
            )
            meaningful = overlap >= min(max(0.001, end - start), max(0.001, cand_end - cand_start)) * 0.35
            if same_target or overlap >= edge_tol or meaningful:
                selected.append(dict(seg))
        if target is not None and not any(
            abs(float(seg.get("start", 0.0) or 0.0) - float(target.get("start", 0.0) or 0.0)) < 0.05
            and abs(float(seg.get("end", 0.0) or 0.0) - float(target.get("end", 0.0) or 0.0)) < 0.05
            for seg in selected
        ):
            selected.append(dict(target))
        if not selected:
            return None
        selected.sort(key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)))
        slot_start = self._frame_time(min(float(seg.get("start", 0.0) or 0.0) for seg in selected))
        slot_end = self._frame_time(max(float(seg.get("end", slot_start) or slot_start) for seg in selected))
        if slot_end <= slot_start:
            return None
        return {"start": slot_start, "end": slot_end, "segments": selected}

    def _stt_slot_candidates_for_source(self, candidate: dict, slot_start: float, slot_end: float) -> list[dict]:
        source = self._stt_candidate_source(candidate)
        rows: list[dict] = []
        for seg in list(getattr(self, "_live_stt_preview_segments", []) or []):
            if not isinstance(seg, dict) or self._stt_candidate_source(seg) != source:
                continue
            try:
                start = float(seg.get("start", 0.0) or 0.0)
                end = float(seg.get("end", start) or start)
            except Exception:
                continue
            if start < slot_end + 0.05 and end > slot_start - 0.05:
                rows.append(dict(seg))
        if not rows:
            rows.append(dict(candidate or {}))
        seen: set[tuple[float, float, str]] = set()
        deduped: list[dict] = []
        for row in sorted(rows, key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0))):
            clean_text = strip_whisper_control_tokens(str(row.get("text", "") or ""))
            if not clean_text:
                continue
            row["text"] = clean_text
            key = (
                round(float(row.get("start", 0.0) or 0.0), 3),
                round(float(row.get("end", 0.0) or 0.0), 3),
                clean_text,
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return deduped

    def _merged_stt_slot_text(self, candidate: dict, slot_start: float, slot_end: float) -> tuple[str, list[dict]]:
        parts = self._stt_slot_candidates_for_source(candidate, slot_start, slot_end)
        texts = [strip_whisper_control_tokens(str(part.get("text", "") or "")) for part in parts]
        texts = [text for text in texts if text]
        if not texts:
            return strip_whisper_control_tokens(str(candidate.get("text", "") or "")), parts
        return " ".join(texts), parts

    def _final_segment_from_stt_candidate(self, candidate: dict) -> dict:
        source = self._stt_candidate_source(candidate)
        start = self._frame_time(max(0.0, float(candidate.get("start", 0.0) or 0.0)))
        end = self._frame_time(max(start + 0.05, float(candidate.get("end", start + 0.5) or start + 0.5)))
        text = strip_whisper_control_tokens(str(candidate.get("text", "") or ""))
        try:
            candidate_score = max(0.0, min(100.0, float(candidate.get("stt_score", candidate.get("score", 98.0)) or 98.0)))
        except Exception:
            candidate_score = 98.0
        candidate_payload = dict(candidate)
        candidate_payload["text"] = text
        candidate_payload["source"] = source
        candidate_payload["score"] = candidate_score
        candidate_payload["stt_score"] = candidate_score
        seg = {
            "start": start,
            "end": end,
            "text": text,
            "speaker": str(candidate.get("speaker", candidate.get("spk", "00")) or "00"),
            "stt_selected_source": source,
            "stt_candidates": [candidate_payload],
            "score": max(candidate_score, 98.0),
            "stt_score": max(candidate_score, 98.0),
            "score_color": "green",
            "manual_stt_candidate_locked": True,
            "manual_stt_candidate_source": source,
            "manual_stt_candidate_start": start,
            "manual_stt_candidate_end": end,
            "_deep_candidate_selector_policy": {
                "task": "manual_stt_candidate_selection",
                "decision": "user_locked_candidate",
                "source": source,
                "preserve_candidate_timing": True,
                "placement_mode": str(candidate.get("_stt_placement_mode") or ""),
                "replaced_segment_count": int(candidate.get("_stt_replaced_segment_count", 0) or 0),
            },
            "_deep_timing_policy": {
                "task": "manual_stt_candidate_timing_lock",
                "locked_source": source,
                "start": start,
                "end": end,
                "preserve_candidate_timing": True,
            },
            "quality": {
                "confidence_label": "green",
                "confidence_score": max(candidate_score, 98.0),
                "confidence_reason": f"{source} 후보 수동 확정",
                "manual_confirmed": True,
                "flags": ["manual_confirmed", "stt_candidate_selected", "manual_stt_candidate_locked"],
            },
        }
        for key in ("_clip_idx", "_clip_file"):
            if key in candidate:
                seg[key] = candidate[key]
        return seg

    def select_stt_candidate_as_subtitle(self, candidate: dict):
        try:
            if hasattr(self, "status_lbl"):
                self.status_lbl.text()
        except RuntimeError:
            return
        if threading.current_thread() is not threading.main_thread():
            QTimer.singleShot(0, lambda c=dict(candidate): self.select_stt_candidate_as_subtitle(c))
            return
        if not candidate:
            return

        # ---------------------------------------------------------
        # 1. 튕김 방지: 현재 스크롤 위치 캡처
        # ---------------------------------------------------------
        saved_h_scroll = None
        saved_v_scroll = 0
        if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
            try:
                saved_h_scroll = int(self.timeline.scroll.horizontalScrollBar().value())
            except Exception:
                saved_h_scroll = None
        if hasattr(self, "text_edit"):
            saved_v_scroll = self.text_edit.verticalScrollBar().value()

        try:
            if hasattr(self, "_undo_mgr"):
                self._undo_mgr.push_immediate()
        except Exception:
            pass

        current = [dict(seg) for seg in self._get_current_segments() if not seg.get("is_gap")]
        
        # ---------------------------------------------------------
        # 2. 클릭한 후보 정보 추출
        # ---------------------------------------------------------
        candidate = dict(candidate)
        cand_text = strip_whisper_control_tokens(str(candidate.get("text", "")))
        candidate["text"] = cand_text
        cand_start = float(candidate.get("start", 0.0) or 0.0)
        
        cand_source = ""
        if hasattr(self, "_stt_candidate_source"):
            cand_source = self._stt_candidate_source(candidate)
        else:
            cand_source = str(candidate.get("stt_preview_source") or candidate.get("stt_source") or candidate.get("stt_ensemble_source") or "").strip().upper()

        if not cand_text or not cand_source:
            return

        # ---------------------------------------------------------
        # 3. 겹치는 최종 자막 슬롯에 후보를 반영
        # ---------------------------------------------------------
        native_plan = self._plan_stt_candidate_selection_native(current, candidate)
        if isinstance(native_plan, dict):
            slot_start_value = native_plan.get("slotStart", native_plan.get("slot_start"))
            slot_end_value = native_plan.get("slotEnd", native_plan.get("slot_end"))
            slot = (
                {
                    "start": float(slot_start_value),
                    "end": float(slot_end_value),
                    "segments": [dict(seg) for seg in list(native_plan.get("replacedSegments", native_plan.get("replaced_segments")) or []) if isinstance(seg, dict)],
                }
                if native_plan.get("usedSlot", native_plan.get("used_slot"))
                and slot_start_value is not None
                and slot_end_value is not None
                else None
            )
            replaced_segments = [dict(seg) for seg in list(native_plan.get("replacedSegments", native_plan.get("replaced_segments")) or []) if isinstance(seg, dict)]
            selected_candidates_native = [
                dict(seg)
                for seg in list(native_plan.get("selectedCandidates", native_plan.get("selected_candidates")) or [])
                if isinstance(seg, dict)
            ]
            self._live_stt_preview_segments = [
                {
                    **dict(seg),
                    **({"stt_preview_source": dict(seg).get("sttPreviewSource")} if dict(seg).get("sttPreviewSource") not in (None, "") else {}),
                    **({"stt_source": dict(seg).get("sttSource")} if dict(seg).get("sttSource") not in (None, "") else {}),
                    **({"stt_ensemble_source": dict(seg).get("sttEnsembleSource")} if dict(seg).get("sttEnsembleSource") not in (None, "") else {}),
                }
                for seg in list(native_plan.get("filteredPreviewSegments", native_plan.get("filtered_preview_segments")) or [])
                if isinstance(seg, dict)
            ]
            slot_parts = []
            merged_text_for_slot = ""
            placed_candidate = dict(selected_candidates_native[0]) if selected_candidates_native else self._manual_exact_stt_candidate(candidate, replaced_segments=replaced_segments)
            selected_segments: list[dict] = []
            replacement_meta = [
                {
                    "start": seg.get("start"),
                    "end": seg.get("end"),
                    "text": seg.get("text"),
                    "line": seg.get("line"),
                }
                for seg in replaced_segments[:8]
            ]
            for native_candidate in selected_candidates_native:
                candidate_payload = dict(candidate)
                candidate_payload["text"] = str(native_candidate.get("text", "") or candidate.get("text", ""))
                candidate_payload["start"] = native_candidate.get("start", candidate.get("start"))
                candidate_payload["end"] = native_candidate.get("end", candidate.get("end"))
                candidate_payload["speaker"] = native_candidate.get("speaker", candidate.get("speaker", candidate.get("spk", "00")))
                candidate_payload["spk"] = native_candidate.get("speaker", candidate.get("spk", candidate.get("speaker", "00")))
                candidate_payload["stt_preview_source"] = native_candidate.get("source", cand_source)
                candidate_payload["stt_source"] = native_candidate.get("source", cand_source)
                candidate_payload["stt_score"] = native_candidate.get("sttScore", native_candidate.get("stt_score", native_candidate.get("score", candidate.get("stt_score", candidate.get("score", 98.0)))))
                candidate_payload["score"] = native_candidate.get("score", candidate_payload["stt_score"])
                if native_candidate.get("clipIndex") is not None:
                    candidate_payload["_clip_idx"] = native_candidate.get("clipIndex")
                if native_candidate.get("clipFile") not in (None, ""):
                    candidate_payload["_clip_file"] = native_candidate.get("clipFile")
                candidate_payload["_stt_placement_mode"] = native_candidate.get("placementMode", native_candidate.get("placement_mode", ""))
                candidate_payload["_stt_original_candidate_start"] = native_candidate.get("originalCandidateStart", native_candidate.get("original_candidate_start", candidate.get("start", cand_start)))
                candidate_payload["_stt_original_candidate_end"] = native_candidate.get("originalCandidateEnd", native_candidate.get("original_candidate_end", candidate.get("end", cand_start)))
                candidate_payload["_stt_replaced_segment_count"] = int(native_candidate.get("replacedSegmentCount", native_candidate.get("replaced_segment_count", len(replaced_segments))) or len(replaced_segments))
                parts = [dict(part) for part in list(native_candidate.get("slotCandidateParts", native_candidate.get("slot_candidate_parts")) or []) if isinstance(part, dict)]
                if parts:
                    candidate_payload["_stt_slot_candidate_parts"] = parts
                if native_candidate.get("slotSplitIndex") is not None:
                    candidate_payload["_stt_slot_split_index"] = int(native_candidate.get("slotSplitIndex"))
                if native_candidate.get("slotSplitTotal") is not None:
                    candidate_payload["_stt_slot_split_total"] = int(native_candidate.get("slotSplitTotal"))
                selected_seg = self._final_segment_from_stt_candidate(candidate_payload)
                if replacement_meta:
                    selected_seg["manual_stt_selection_replaced_segments"] = list(replacement_meta)
                selected_segments.append(selected_seg)
            if not selected_segments:
                selected_seg = self._final_segment_from_stt_candidate(placed_candidate)
                if replacement_meta:
                    selected_seg["manual_stt_selection_replaced_segments"] = list(replacement_meta)
                selected_segments.append(selected_seg)
        else:
            slot = self._stt_selection_slot_for_candidate(current, candidate)
            slot_parts: list[dict] = []
            merged_text_for_slot = ""
            if slot is not None:
                replaced_segments = list(slot.get("segments") or [])
                placed_candidate = self._manual_exact_stt_candidate(candidate, replaced_segments=replaced_segments)
                slot_start = float(slot.get("start") if slot.get("start") is not None else cand_start)
                slot_end = float(slot.get("end") if slot.get("end") is not None else placed_candidate.get("end", slot_start))
                merged_text_for_slot, slot_parts = self._merged_stt_slot_text(candidate, slot_start, slot_end)
                placed_candidate["start"] = self._frame_time(slot_start)
                placed_candidate["end"] = self._frame_time(max(slot_start + 0.05, slot_end))
                placed_candidate["_stt_placement_mode"] = "manual_final_slot_replace"
                placed_candidate["_stt_original_candidate_start"] = float(candidate.get("start", cand_start) or cand_start)
                placed_candidate["_stt_original_candidate_end"] = float(candidate.get("end", slot_end) or slot_end)
                placed_candidate["_stt_replaced_segment_count"] = len(replaced_segments)
                placed_candidate["_stt_slot_candidate_parts"] = [
                    {
                        "source": self._stt_candidate_source(part),
                        "start": part.get("start"),
                        "end": part.get("end"),
                        "text": strip_whisper_control_tokens(str(part.get("text", "") or "")),
                    }
                    for part in slot_parts[:24]
                ]
            else:
                replaced_segments = self._overlapping_final_segments_for_stt_candidate(current, candidate)
                placed_candidate = self._manual_exact_stt_candidate(candidate, replaced_segments=replaced_segments)

        replacement_meta = [
            {
                "start": seg.get("start"),
                "end": seg.get("end"),
                "text": seg.get("text"),
                "line": seg.get("line"),
            }
            for seg in replaced_segments[:8]
        ]
        if not isinstance(native_plan, dict):
            selected_segments: list[dict] = []
            if slot is not None and len(slot_parts) > 1:
                total_parts = len(slot_parts)
                for part_idx, part in enumerate(slot_parts):
                    try:
                        part_start = self._frame_time(max(slot_start, float(part.get("start", slot_start) or slot_start)))
                        part_end = self._frame_time(min(slot_end, float(part.get("end", part_start) or part_start)))
                    except Exception:
                        continue
                    if part_end <= part_start:
                        continue
                    split_candidate = self._manual_exact_stt_candidate(part, replaced_segments=replaced_segments)
                    split_candidate["start"] = part_start
                    split_candidate["end"] = self._frame_time(max(part_start + 0.05, part_end))
                    split_candidate["_stt_placement_mode"] = "manual_final_slot_replace"
                    split_candidate["_stt_original_candidate_start"] = float(part.get("start", part_start) or part_start)
                    split_candidate["_stt_original_candidate_end"] = float(part.get("end", part_end) or part_end)
                    split_candidate["_stt_replaced_segment_count"] = len(replaced_segments)
                    split_candidate["_stt_slot_candidate_parts"] = list(placed_candidate.get("_stt_slot_candidate_parts") or [])
                    split_candidate["_stt_slot_split_index"] = part_idx
                    split_candidate["_stt_slot_split_total"] = total_parts
                    selected_seg = self._final_segment_from_stt_candidate(split_candidate)
                    if replacement_meta:
                        selected_seg["manual_stt_selection_replaced_segments"] = list(replacement_meta)
                    selected_segments.append(selected_seg)
            if not selected_segments:
                if slot is not None:
                    placed_candidate["start"] = self._frame_time(slot_start)
                    placed_candidate["end"] = self._frame_time(max(slot_start + 0.05, slot_end))
                    placed_candidate["text"] = merged_text_for_slot or cand_text
                selected_seg = self._final_segment_from_stt_candidate(placed_candidate)
                if replacement_meta:
                    selected_seg["manual_stt_selection_replaced_segments"] = list(replacement_meta)
                selected_segments.append(selected_seg)

        selected_start = min(float(seg.get("start", cand_start) or cand_start) for seg in selected_segments)
        selected_end = max(float(seg.get("end", selected_start) or selected_start) for seg in selected_segments)
        candidate_anchor_sec = selected_start

        if slot is not None:
            slot_start = float(placed_candidate.get("start") if placed_candidate.get("start") is not None else cand_start)
            slot_end = float(placed_candidate.get("end") if placed_candidate.get("end") is not None else slot_start)
            replaced_keys = {
                (
                    round(float(seg.get("start", 0.0) or 0.0), 3),
                    round(float(seg.get("end", 0.0) or 0.0), 3),
                    str(seg.get("text", "") or ""),
                )
                for seg in replaced_segments
            }
            current = [
                dict(seg)
                for seg in current
                if (
                    round(float(seg.get("start", 0.0) or 0.0), 3),
                    round(float(seg.get("end", 0.0) or 0.0), 3),
                    str(seg.get("text", "") or ""),
                ) not in replaced_keys
            ]
            current = [
                seg
                for seg in current
                if not (
                    float(seg.get("start", 0.0) or 0.0) < slot_end - 0.001
                    and float(seg.get("end", seg.get("start", 0.0)) or 0.0) > slot_start + 0.001
                    and any(
                        abs(float(seg.get("start", 0.0) or 0.0) - float(rep.get("start", 0.0) or 0.0)) < 0.05
                        for rep in replaced_segments
                    )
                )
            ]
        else:
            current = self._trim_final_segments_around_candidate(current, placed_candidate)
        current.extend(selected_segments)
        current.sort(key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)))
        # Keep preview candidates stable for undo/redo and single-candidate
        # workflows, but if multiple overlapping candidates exist for the same
        # slot then drop only the source the user just selected so the
        # remaining alternative stays selectable without a duplicate highlight.
        existing_preview = [dict(seg) for seg in list(getattr(self, "_live_stt_preview_segments", []) or [])]
        has_alternative_overlap = any(
            float(seg.get("start", 0.0) or 0.0) < selected_end + 0.05
            and float(seg.get("end", 0.0) or 0.0) > selected_start - 0.05
            and str(
                seg.get("stt_preview_source")
                or seg.get("stt_source")
                or seg.get("stt_selected_source")
                or seg.get("stt_ensemble_llm_selected_source")
                or seg.get("stt_ensemble_source")
                or ""
            ).strip().upper() != cand_source
            for seg in existing_preview
        )
        if has_alternative_overlap:
            kept_preview = []
            for seg in existing_preview:
                source = str(
                    seg.get("stt_preview_source")
                    or seg.get("stt_source")
                    or seg.get("stt_selected_source")
                    or seg.get("stt_ensemble_llm_selected_source")
                    or seg.get("stt_ensemble_source")
                    or ""
                ).strip().upper()
                overlaps = (
                    float(seg.get("start", 0.0) or 0.0) < selected_end + 0.05
                    and float(seg.get("end", 0.0) or 0.0) > selected_start - 0.05
                )
                if overlaps and source == cand_source:
                    continue
                kept_preview.append(seg)
            self._live_stt_preview_segments = kept_preview
        else:
            self._live_stt_preview_segments = existing_preview

        # ---------------------------------------------------------
        # 4. 화면 반영 및 위치 복원
        # ---------------------------------------------------------
        for line, seg in enumerate(current):
            seg["line"] = line
        self._active_seg_start = candidate_anchor_sec

        if hasattr(self, "text_edit"):
            self.text_edit.blockSignals(True)

        if hasattr(self, "_reload_segments_from_list"):
            self._reload_segments_from_list(current, preserve_view=True)
            self._update_timeline_with_confirmed_and_preview(current)
        else:
            self._rebuild_subtitle_memory_cache(current)
            if hasattr(self, "reload_segments"):
                self.reload_segments()

        if hasattr(self, "text_edit"):
            self.text_edit.blockSignals(False)
            self.text_edit.verticalScrollBar().setValue(saved_v_scroll)
        if hasattr(self, "timeline"):
            try:
                if hasattr(self.timeline, "set_active"):
                    self.timeline.set_active(candidate_anchor_sec)
                if hasattr(self.timeline, "set_playhead"):
                    try:
                        self.timeline.set_playhead(candidate_anchor_sec, preserve_center_lock=True)
                    except TypeError:
                        self.timeline.set_playhead(candidate_anchor_sec)
                if saved_h_scroll is not None:
                    self.timeline.scroll.horizontalScrollBar().setValue(int(saved_h_scroll))
            except Exception:
                pass
        if hasattr(self, "video_player") and hasattr(self.video_player, "seek"):
            try:
                local_sec = (
                    self._global_to_local_sec(candidate_anchor_sec)
                    if hasattr(self, "_global_to_local_sec")
                    else candidate_anchor_sec
                )
                self.video_player.seek(local_sec)
            except Exception:
                pass

    def _update_timeline_with_confirmed_and_preview(self, confirmed_segments: list[dict]):
        if not hasattr(self, "timeline"):
            return
        confirmed = [seg for seg in list(confirmed_segments or []) if not seg.get("is_gap")]
        preview = align_stt_preview_to_subtitle_segments(
            list(getattr(self, "_live_stt_preview_segments", []) or []),
            confirmed,
        )
        subtitle_preview = self._build_live_subtitle_preview_segments(preview, confirmed)
        combined = sorted(
            confirmed + subtitle_preview + preview,
            key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)),
        )
        total_dur = combined[-1]["end"] if combined else 0.0
        if hasattr(self, 'video_player') and self.video_player.total_time > 0.0:
            total_dur = max(total_dur, self.video_player.total_time)
        self.timeline.update_segments(combined, self._active_seg_start, total_dur)
        if getattr(self, "_queue_mode_fit_view", False):
            try:
                setattr(self.timeline, "_manual_zoom_since_fit", False)
                if hasattr(self.timeline, "schedule_fit_to_view"):
                    self.timeline.schedule_fit_to_view((0, 120, 260))
                elif hasattr(self.timeline, "fit_to_view"):
                    QTimer.singleShot(0, self.timeline.fit_to_view)
            except Exception:
                pass

    def _redraw_timeline_with_live_preview(self):
        if not hasattr(self, "timeline"):
            return
        try:
            confirmed = [seg for seg in self._get_current_segments() if not seg.get("is_gap")]
        except Exception:
            confirmed = list(getattr(self, "_cached_segs", []) or [])
        preview = align_stt_preview_to_subtitle_segments(
            list(getattr(self, "_live_stt_preview_segments", []) or []),
            confirmed,
        )
        subtitle_preview = self._build_live_subtitle_preview_segments(preview, confirmed)
        if not preview and not subtitle_preview:
            self._redraw_timeline()
            return
        combined = sorted(
            confirmed + subtitle_preview + preview,
            key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)),
        )
        total_dur = combined[-1]["end"] if combined else 0.0
        if hasattr(self, 'video_player') and self.video_player.total_time > 0.0:
            total_dur = max(total_dur, self.video_player.total_time)
        self.timeline.update_segments(combined, self._active_seg_start, total_dur)

    def append_segments(self, segments: list[dict]):
        try:
            self.status_lbl.text()
        except RuntimeError:
            return
        if threading.current_thread() is not threading.main_thread():
            QTimer.singleShot(0, lambda s=list(segments): self.append_segments(s))
            return
        self._segment_queue.extend(segments)
        if not self._queue_timer.isActive():
            self._queue_timer.start(self._live_append_reschedule_delay_ms(len(self._segment_queue)))

    def _flush_queue(self):
        try:
            self.text_edit.toPlainText()
        except RuntimeError:
            return

        if not self._segment_queue:
            return
        self._remove_live_editor_preview_overlapping(self._segment_queue)
        try:
            from core.engine.subtitle_accuracy_pipeline import repair_subtitle_context_consistency

            repaired_queue, repair_decision = repair_subtitle_context_consistency(
                [dict(seg) for seg in list(self._segment_queue or []) if isinstance(seg, dict)],
                getattr(self, "settings", {}) or {},
            )
            if repair_decision.get("applied"):
                dropped_shadow = int(repair_decision.get("dropped_shadow_duplicates", 0) or 0)
                if dropped_shadow:
                    get_logger().log(f"[자막문맥-자동복구] 에디터 반영 전 부분중복 자막 {dropped_shadow}개 제거")
                self._segment_queue = list(repaired_queue or [])
                if not self._segment_queue:
                    return
        except Exception:
            pass

        self._segment_queue = [
            seg
            for _idx, seg in sorted(
                enumerate(list(self._segment_queue or [])),
                key=lambda pair: (
                    float(pair[1].get("start", 0.0) or 0.0) if isinstance(pair[1], dict) else 0.0,
                    float(pair[1].get("end", pair[1].get("start", 0.0)) or 0.0) if isinstance(pair[1], dict) else 0.0,
                    int(pair[0]),
                ),
            )
            if isinstance(seg, dict)
        ]
        if not self._segment_queue:
            return
        remaining_segments: list[dict] = []
        batch_limit = self._live_append_batch_limit()
        if batch_limit > 0 and len(self._segment_queue) > batch_limit:
            remaining_segments = [dict(seg) for seg in list(self._segment_queue[batch_limit:]) if isinstance(seg, dict)]
            self._segment_queue = [dict(seg) for seg in list(self._segment_queue[:batch_limit]) if isinstance(seg, dict)]
        has_more_pending = bool(remaining_segments)

        cont_thresh = float(self.settings.get("continuous_threshold", 2.0))
        push_rate = float(self.settings.get("gap_push_rate", 0.7))
        pull_rate = max(0.0, min(1.0, 1.0 - push_rate))
        single_ext = float(self.settings.get("single_subtitle_end", 0.2))
        is_initial = getattr(self, '_is_initial_load', False)
        final_gap_ready = bool(self._segment_queue) and all(
            bool(seg.get("_final_gap_settings_applied")) for seg in self._segment_queue
        )

        doc = self.text_edit.document()
        orig_cursor = self.text_edit.textCursor()
        is_at_bottom = (orig_cursor.position() >= doc.characterCount() - 5)

        cur = QTextCursor(doc)
        cur.beginEditBlock()
        cur.movePosition(QTextCursor.MoveOperation.End)

        # 💡 1. [핵심 버그 수정] 꼬리(Gap)를 지우기 전에 이전 자막의 끝 시간을 미리 확보!
        prev_end_orig = -1.0
        has_prev_gap = False
        
        if not is_initial and doc.blockCount() > 0:
            lb = doc.lastBlock()
            ud = lb.userData()
            # 마지막 줄이 빈 줄(Gap)이라면 순수한 끝 시간을 기억합니다.
            if not lb.text().strip() and isinstance(ud, SubtitleBlockData) and ud.is_gap:
                has_prev_gap = True
                prev_end_orig = max(0.0, ud.start_sec - single_ext)

        # 💡 2. 꼬리 지우기 (여기서 기존 Gap 블록이 화면에서 정리됨)
        while doc.blockCount() > 0:
            last_block = doc.lastBlock()
            last_text = last_block.text()
            if not last_text.strip():
                cur.setPosition(last_block.position())
                cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                cur.removeSelectedText()
                if doc.blockCount() > 1:
                    cur.deletePreviousChar()
                else:
                    break
            else:
                break

        cur.movePosition(QTextCursor.MoveOperation.End)

        # 💡 3. [핵심 로직 복구] 삭제된 Gap 정보를 바탕으로 대표님이 설정한 미루기/당기기 비율 적용!
        if has_prev_gap and self._segment_queue and not is_initial:
            curr_start = self._segment_queue[0]['start']
            gap = curr_start - prev_end_orig
            
            if 0 < gap <= cont_thresh:
                new_prev_end = prev_end_orig + gap * push_rate
                # 🎯 드디어 대표님이 설정한 '당기기' 비율만큼 자막 시작 시간이 앞당겨집니다!
                self._segment_queue[0]['start'] = prev_end_orig + gap - (gap * pull_rate)
                
                # 당기고 남은 빈 공간이 있다면 다시 Gap 블록 재생성
                if self._segment_queue[0]['start'] > new_prev_end + 0.05:
                    if doc.lastBlock().text().strip():
                        cur.insertText("\n")
                    cur.insertText("\n")
                    cur.block().setUserData(SubtitleBlockData("00", self._frame_time(new_prev_end), is_gap=True))
                    cur.insertText("\n") # 다음 자막이 쓸 줄 확보
                    
            elif gap > cont_thresh:
                new_prev_end = prev_end_orig + single_ext
                self._segment_queue[0]['start'] = max(0.0, curr_start - single_ext)
                if self._segment_queue[0]['start'] > new_prev_end + 0.05:
                    if doc.lastBlock().text().strip():
                        cur.insertText("\n")
                    cur.insertText("\n")
                    cur.block().setUserData(SubtitleBlockData("00", self._frame_time(new_prev_end), is_gap=True))
                    cur.insertText("\n")

        # 💡 4. 내부 청크들 간의 간격 연산
        last_end = -1.0
        for i in range(len(self._segment_queue)):
            curr = self._segment_queue[i]
            
            if not is_initial and not final_gap_ready:
                if curr['start'] < last_end:
                    curr['start'] = last_end
                
                if i + 1 < len(self._segment_queue):
                    nxt = self._segment_queue[i+1]
                    gap = nxt['start'] - curr['end']
                    if 0 < gap <= cont_thresh:
                        curr['end'] += gap * push_rate
                        nxt['start'] -= gap * pull_rate
                    elif gap > cont_thresh:
                        curr['end'] += min(single_ext, gap / 2.0)
                        nxt['start'] -= min(single_ext, gap / 2.0)
                else: 
                    curr['end'] += single_ext
            elif curr['end'] <= curr['start']:
                curr['end'] = curr['start'] + 0.5
                    
            last_end = curr['end']

        if doc.lastBlock().text().strip():
            cur.insertText("\n")
        added_end = self._segment_queue[-1]['end'] if self._segment_queue else 0.0
        focused_payload = None

        # 💡 [여기서부터 수정: 화자 분리 로직]
        spk1_id = self.settings.get("spk1_id", "00")
        spk2_id = self.settings.get("spk2_id", "01")

        for i in range(len(self._segment_queue)):
            seg = self._segment_queue[i]
            text = str(seg.get("text", "") or "").replace("\u2028", "\n")
            spk_list = seg.get("speaker_list", [spk1_id])
            
            text = self._JUNK_TS_RE.sub('', text)
            text = self._JUNK_NO_BRACKET_3PART.sub('', text)
            text = self._JUNK_NO_BRACKET_3PART_END.sub('', text)
            text = self._JUNK_START_RE.sub('', text).strip()
            text = text.replace('\r', '')
            # ✅ HTML 태그 제거
            text = re.sub(r'<[^>]+>', '', text)

            parts = [re.sub(r'[ \t\f\v]+', ' ', p).strip() for p in text.split('\n')]
            parts = [p for p in parts if p]
            if not parts:
                continue
            
            start_sec = self._frame_time(max(0, seg.get("start", 0)))
            
            # 💡 첫 번째 줄 삽입
            current_spk = spk_list[0] if len(spk_list) > 0 else spk1_id
            stt_kwargs = {
                "stt_mode": bool(seg.get("stt_mode", False)),
                "stt_pending": bool(seg.get("stt_pending", False)),
                "original_text": str(seg.get("original_text", "") or ""),
                "dictated_text": str(seg.get("dictated_text", "") or ""),
                "stt_selected_source": str(seg.get("stt_selected_source", "") or ""),
                "stt_ensemble_llm_selected_source": str(seg.get("stt_ensemble_llm_selected_source", "") or ""),
                "stt_candidates": list(seg.get("stt_candidates") or []),
                "stt_ensemble_source": str(seg.get("stt_ensemble_source", "") or ""),
                "stt_ensemble_llm_selected_label": str(seg.get("stt_ensemble_llm_selected_label", "") or ""),
                "stt_ensemble_similarity": seg.get("stt_ensemble_similarity"),
                "stt_ensemble_needs_llm_review": bool(seg.get("stt_ensemble_needs_llm_review", False)),
                "stt_ensemble_inserted_from_stt2": bool(seg.get("stt_ensemble_inserted_from_stt2", False)),
                "stt_ensemble_word_rover": dict(seg.get("stt_ensemble_word_rover") or {}),
                "score": seg.get("score"),
                "stt_score": seg.get("stt_score"),
                "score_color": str(seg.get("score_color", "") or ""),
                "stt_score_color": str(seg.get("stt_score_color", "") or ""),
                "stt_score_label": str(seg.get("stt_score_label", "") or ""),
                "stt_score_flags": list(seg.get("stt_score_flags") or []),
                "stt_score_components": dict(seg.get("stt_score_components") or {}),
            }
            clip_idx = seg.get("_clip_idx")
            try:
                clip_idx = int(clip_idx) if clip_idx is not None else None
            except Exception:
                clip_idx = None
            clip_kwargs = {
                "clip_idx": clip_idx,
                "clip_file": str(seg.get("_clip_file", "") or ""),
            }
            quality_kwargs = self._quality_kwargs_from_segment(seg, signature=self._segment_quality_signature({
                "start": start_sec,
                "end": seg.get("end", start_sec),
                "text": parts[0],
                "speaker": current_spk,
            }))
            cur.insertText(parts[0])
            cur.block().setUserData(SubtitleBlockData(current_spk, start_sec, **stt_kwargs, **quality_kwargs, **clip_kwargs))
            focused_payload = {
                "line": cur.block().blockNumber(),
                "start": start_sec,
                "end": seg.get("end", start_sec),
                "text": parts[0],
            }
            
            # 💡 두 번째 줄부터의 처리 (- 기호 유무로 완벽 통제)
            for p_idx in range(1, len(parts)):
                line_text = parts[p_idx]
                
                if line_text.startswith('-'):
                    # 🚨 '-' 기호가 있으면: 진짜 엔터(\n)를 쳐서 블록을 나누고 화자를 교체합니다.
                    current_spk = spk2_id if current_spk == spk1_id else spk1_id
                    cur.insertText("\n" + line_text)
                    cur.block().setUserData(SubtitleBlockData(current_spk, start_sec, **stt_kwargs, **quality_kwargs, **clip_kwargs))
                else:
                    # 🚨 '-' 기호가 없으면: 화자를 유지하고 소프트 줄바꿈(\u2028)만 삽입하여 1개의 블록으로 묶습니다.
                    cur.insertText("\u2028" + line_text)
            
            if i + 1 < len(self._segment_queue):
                nxt = self._segment_queue[i+1]
                if seg['end'] < nxt['start'] - 0.05:
                    gap_start = self._frame_time(seg['end'])
                    cur.insertText("\n") 
                    cur.block().setUserData(SubtitleBlockData("00", gap_start, is_gap=True))
                    # 💡 [핵심 해결] 무음 블록(빈 줄)을 확보했으니, 다음 자막이 쓸 새로운 줄을 한 번 더 만들어 줍니다!
                    cur.insertText("\n") 
                else:
                    cur.insertText("\n")
            else:
                gap_start = self._frame_time(seg['end'])
                cur.insertText("\n")
                cur.block().setUserData(SubtitleBlockData("00", gap_start, is_gap=True))

        self._segment_queue.clear()
        self.text_edit.update_margins()
        cur.endEditBlock()

        self._sync_lock = True
        if is_at_bottom:
            self.text_edit.setTextCursor(cur)
        else:
            self.text_edit.setTextCursor(orig_cursor)
        self._sync_lock = False

        self._schedule_timeline()
        if getattr(self, "_queue_mode_fit_view", False) and hasattr(self, "timeline"):
            try:
                setattr(self.timeline, "_manual_zoom_since_fit", False)
                if has_more_pending:
                    pass
                elif hasattr(self.timeline, "schedule_fit_to_view"):
                    self.timeline.schedule_fit_to_view((0, 120, 260))
                elif hasattr(self.timeline, "fit_to_view"):
                    QTimer.singleShot(0, self.timeline.fit_to_view)
            except Exception:
                pass
        if has_more_pending:
            timer = getattr(self, "_video_context_refresh_timer", None)
            if timer is not None:
                try:
                    timer.start(90)
                except Exception:
                    pass
        else:
            self._refresh_video_subtitle_context()

        suppress_autoseek = bool(getattr(self, "_suspend_append_segments_autoseek", False)) or has_more_pending

        if is_initial:
            self._is_initial_load = False
            if hasattr(self, 'timeline'):
                self.timeline.set_playhead(0.0)
                self.timeline.center_to_sec(0.0, smooth=True)
            if hasattr(self, 'video_player'):
                self.video_player.seek(0.0)
        elif added_end > 0.0 and not suppress_autoseek:
            if hasattr(self, 'timeline'):
                self.timeline.set_playhead(added_end)
                self.timeline.center_to_sec(added_end, smooth=True)
            if hasattr(self, 'video_player'):
                self.video_player.seek(added_end)
            self._focus_editor_block_for_processing_segment(focused_payload, prefer_last=True)
            if self.settings.get("subtitle_quality_auto_check_after_generate"):
                scheduler = getattr(self, "_schedule_auto_quality_review", None)
                if callable(scheduler):
                    scheduler(delay_ms=900)
                elif hasattr(self, "_run_quality_review"):
                    QTimer.singleShot(
                        900,
                        lambda: self._run_quality_review(
                            auto_correct=bool(self.settings.get("subtitle_quality_auto_correct_enabled", False))
                        ),
                    )
        if has_more_pending:
            self._segment_queue = list(remaining_segments)
            try:
                self._queue_timer.start(self._live_append_reschedule_delay_ms(len(self._segment_queue)))
            except Exception:
                self._flush_queue()

    # ---------------------------------------------------------
    # Segment I/O
    # ---------------------------------------------------------

    def _get_current_segments(self, force_rebuild: bool = False) -> list[dict]:
        if not force_rebuild:
            cached = getattr(self, "_cached_segs", None)
            if bool(getattr(self, "_segment_cache_valid", False)) and isinstance(cached, list):
                try:
                    block_count = int(self.text_edit.document().blockCount())
                except Exception:
                    block_count = int(getattr(self, "_last_segment_cache_block_count", 0) or 0)
                cached_block_count = int(getattr(self, "_last_segment_cache_block_count", block_count) or block_count)
                if block_count == cached_block_count:
                    return [dict(seg) for seg in cached]
        segments = []
        block = self.text_edit.document().begin()
        line_idx = 0
        
        while block.isValid():
            data = block.userData()
            text = block.text().replace("\u2028", "\n").strip()
            is_gap = getattr(data, 'is_gap', False) if data else False
            
            # ✅ [#1 핵심 수정] 갭 블록도 포함 — 무음구간이 End Time 계산에 반영됩니다
            include_empty_stt = bool(getattr(data, 'stt_pending', False) or getattr(data, 'stt_mode', False))
            if data is not None and getattr(data, "live_preview", False):
                block = block.next()
                line_idx += 1
                continue
            if data is not None and (text or is_gap or include_empty_stt):
                # ✅ 갭 블록은 절대 이전 세그먼트에 병합하지 않음 (갭↔자막 병합 방지)
                if (not is_gap
                    and segments
                    and not segments[-1].get("is_gap")
                    and abs(segments[-1]["start"] - data.start_sec) < 0.05):
                    segments[-1]["text"] += "\n" + text
                else:
                    item = {
                        "line": line_idx,
                        "start": data.start_sec,
                        "end": getattr(data, 'end_sec', None),
                        "text": text,
                        "is_gap": is_gap,
                        "spk": getattr(data, 'spk_id', 'SPEAKER_00'),
                        "stt_mode": bool(getattr(data, 'stt_mode', False)),
                        "stt_pending": bool(getattr(data, 'stt_pending', False)),
                        "original_text": getattr(data, 'original_text', '') or '',
                        "dictated_text": getattr(data, 'dictated_text', '') or '',
                        "stt_selected_source": getattr(data, 'stt_selected_source', '') or '',
                        "stt_ensemble_llm_selected_source": getattr(data, 'stt_ensemble_llm_selected_source', '') or '',
                    }
                    for attr in (
                        "stt_segment_id",
                        "stt_mode_status",
                        "vad_confidence",
                        "vad_confidence_label",
                        "vad_decision",
                        "vad_sources",
                        "start_frame",
                        "end_frame",
                        "timeline_start_frame",
                        "timeline_end_frame",
                        "frame_rate",
                        "timeline_frame_rate",
                        "frame_range",
                        "playback",
                    ):
                        value = getattr(data, attr, None)
                        if value not in (None, "", [], {}):
                            item[attr] = value
                    if item.get("stt_segment_id") and not item.get("id"):
                        item["id"] = str(item["stt_segment_id"])
                    if getattr(data, "stt_candidates", None):
                        item["stt_candidates"] = list(getattr(data, "stt_candidates", []) or [])
                    for attr in (
                        "stt_ensemble_source",
                        "stt_ensemble_llm_selected_label",
                        "stt_ensemble_similarity",
                        "stt_ensemble_needs_llm_review",
                        "stt_ensemble_inserted_from_stt2",
                        "stt_ensemble_word_rover",
                        "score",
                        "stt_score",
                        "score_color",
                        "stt_score_color",
                        "stt_score_label",
                        "stt_score_flags",
                        "stt_score_components",
                    ):
                        value = getattr(data, attr, None)
                        if value not in (None, "", [], {}):
                            item[attr] = value
                    if getattr(data, "clip_idx", None) is not None:
                        item["_clip_idx"] = int(getattr(data, "clip_idx"))
                    if getattr(data, "clip_file", ""):
                        item["_clip_file"] = str(getattr(data, "clip_file", "") or "")
                    if getattr(data, "quality", None):
                        item["quality"] = dict(getattr(data, "quality", {}) or {})
                        item["quality_history"] = list(getattr(data, "quality_history", []) or [])
                        item["quality_candidates"] = list(getattr(data, "quality_candidates", []) or [])
                        signature = self._segment_quality_signature({
                            "start": item["start"],
                            "end": item.get("end") if item.get("end") is not None else item["start"],
                            "text": item["text"],
                            "speaker": item["spk"],
                        })
                        if getattr(data, "quality_signature", "") and signature != getattr(data, "quality_signature", ""):
                            item["quality_stale"] = True
                            quality = dict(item["quality"])
                            flags = list(quality.get("flags") or [])
                            if "quality_stale" not in flags:
                                flags.append("quality_stale")
                            quality["flags"] = flags
                            item["quality"] = quality
                    if getattr(data, "linked_silence_for_line", None) is not None:
                        try:
                            item["linked_silence_for_line"] = int(getattr(data, "linked_silence_for_line"))
                        except Exception:
                            pass
                    segments.append(item)
            
            block = block.next()
            line_idx += 1

        # 2. 끝 시간(End Time) 계산
        for i, seg in enumerate(segments):
            is_last = (i + 1 == len(segments))
            
            if is_last:
                if hasattr(self, 'video_player') and getattr(self.video_player, 'total_time', 0) > seg["start"]:
                    next_start = self.video_player.total_time if seg.get("is_gap") else min(seg["start"] + 3.0, self.video_player.total_time)
                else:
                    next_start = seg["start"] + 3.0
            else:
                next_start = segments[i+1]["start"]
                
            c_end = seg.get("end") 
            if c_end is not None and seg["start"] < c_end <= next_start + 0.05:
                seg["end"] = c_end
            else:
                seg["end"] = next_start
            if seg.get("quality") and not seg.get("quality_signature"):
                seg["quality_signature"] = self._segment_quality_signature(seg)
                
        self._cached_segs = [dict(seg) for seg in segments]
        self._refresh_cached_line_map()
        self._subtitle_memory_cache = build_segment_lookup(self._cached_segs)
        self._segment_cache_valid = True
        try:
            self._last_segment_cache_block_count = int(self.text_edit.document().blockCount())
        except Exception:
            pass
        return [dict(seg) for seg in self._cached_segs]

    # ---------------------------------------------------------
    # Text Editor Event Handlers
    # ---------------------------------------------------------
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

    def _save_correction(self, old_word, new_word):
        _dm_save_correction(self.corrections, old_word, new_word)
        try:
            from core.subtitle_quality.correction_memory import add_correction_memory_item
            add_correction_memory_item(
                old_word,
                new_word,
                source="manual_popup",
                context=self.text_edit.textCursor().block().text()[:500],
            )
        except Exception as exc:
            get_logger().log(f"⚠️ 교정 memory 저장 실패: {exc}")
        get_logger().log(f"🔄 교정 사전 등록 및 저장: {old_word} -> {new_word}")

    def _on_enter_pressed(self, last_word: str, line_num: int):
        self._undo_mgr.push() # 💡 실행취소 스냅샷 추가
        try:
            from utils import add_split_rule
            add_split_rule(last_word)
        except Exception:
            pass
        self._schedule_timeline()

    def _on_backspace_merged(self, removed_word: str):
        self._undo_mgr.push() # 💡 실행취소 스냅샷 추가
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
            if hasattr(self, 'video_player') and not playback_active:
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
            if hasattr(self, 'video_player') and not playback_active:
                self._schedule_cursor_video_seek(seg["start"])
        remember_repeat_segment = getattr(self, "_remember_repeat_segment", None)
        repeat_enabled = getattr(self, "_segment_repeat_enabled", None)
        if callable(remember_repeat_segment) and callable(repeat_enabled) and repeat_enabled():
            remember_repeat_segment(seg)

    def _on_esc_pressed(self):
        if hasattr(self.timeline, 'canvas'):
            self.timeline.canvas.update()

    # ---------------------------------------------------------
    # Timeline Schedule
    # ---------------------------------------------------------
    def _redraw_timeline(self):
        segs = self._get_current_segments()
        if not isinstance(getattr(self, "_subtitle_memory_cache", None), dict):
            self._rebuild_subtitle_memory_cache(segs)
        timeline_segs = segs
        preview = list(getattr(self, "_live_stt_preview_segments", []) or [])
        if preview:
            confirmed = [seg for seg in segs if not seg.get("is_gap")]
            subtitle_preview = self._build_live_subtitle_preview_segments(preview, confirmed)
            timeline_segs = sorted(
                confirmed + subtitle_preview + preview,
                key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)),
            )
        if hasattr(self, "_highlighter"):
            self._refresh_visible_quality_map()
        total_dur = timeline_segs[-1]["end"] if timeline_segs else 0.0
        if hasattr(self, 'video_player') and self.video_player.total_time > 0.0:
            total_dur = max(total_dur, self.video_player.total_time)
        self.timeline.update_segments(timeline_segs, self._active_seg_start, total_dur)
        if hasattr(self, 'video_player') and hasattr(self.video_player, "set_context_segments"):
            _canvas = getattr(getattr(self, "timeline", None), "canvas", None)
            _mc_boxes = list(getattr(_canvas, '_multiclip_boxes', []) or []) if _canvas is not None else []
            if _mc_boxes and hasattr(self, '_resolve_active_context'):
                try:
                    _gsec = float(getattr(_canvas, 'playhead_sec', 0.0) or 0.0)
                    _ctx = self._resolve_active_context(global_sec=_gsec)
                    _local_sec = float(_ctx.get("local_sec", 0.0) or 0.0)
                    self.video_player.set_context_segments(
                        self._subtitle_context_window_from_segments(
                            list(_ctx.get('local_segments', []) or []),
                            center_sec=_local_sec,
                        )
                    )
                except Exception:
                    self.video_player.set_context_segments(self._subtitle_memory_visible_window())
            else:
                self.video_player.set_context_segments(self._subtitle_memory_visible_window())

        # ✅ 최초 로드 시 화면에 맞춤
        if getattr(self, '_needs_fit_view', False) and segs and hasattr(self.timeline, "fit_to_view"):
            auto_fit = getattr(self.timeline, "auto_fit_to_view", None)
            if callable(auto_fit):
                auto_fit()
            else:
                self.timeline.fit_to_view()
            self._needs_fit_view = False

    def _refresh_video_subtitle_context(self):
        if not hasattr(self, 'video_player'):
            return
        segs = self._video_subtitle_context_for_player()
        try:
            if hasattr(self.video_player, 'refresh_subtitle_context'):
                self.video_player.refresh_subtitle_context(segs)
            else:
                self.video_player.set_context_segments(segs)
        except Exception:
            pass

    def _video_subtitle_context_for_player(self):
        cache = getattr(self, "_subtitle_memory_cache", None)
        if not isinstance(cache, dict):
            cached = getattr(self, "_cached_segs", None)
            cache = build_segment_lookup(cached) if cached is not None else self._rebuild_subtitle_memory_cache()
            self._subtitle_memory_cache = cache
        try:
            _mc_boxes = list(getattr(self.timeline.canvas, '_multiclip_boxes', []) or []) if hasattr(self, 'timeline') else []
            if _mc_boxes and hasattr(self, '_resolve_active_context'):
                _gsec = float(getattr(self.timeline.canvas, 'playhead_sec', 0.0) or 0.0)
                ctx = self._resolve_active_context(global_sec=_gsec)
                if ctx:
                    return self._subtitle_context_window_from_segments(
                        list(ctx.get('local_segments', []) or []),
                        center_sec=float(ctx.get("local_sec", 0.0) or 0.0),
                    )
        except Exception:
            pass
        return self._subtitle_memory_visible_window()

    def _schedule_timeline(self):
        if getattr(self, '_inline_updating', False):
            return
        self._timeline_timer.start(120)

    def _live_append_batch_limit(self) -> int:
        try:
            locked = bool(getattr(getattr(self, "sm", None), "is_locked", False))
        except Exception:
            locked = False
        if not locked:
            return 0
        try:
            value = int((getattr(self, "settings", {}) or {}).get("editor_live_append_batch_size", 8) or 8)
        except Exception:
            value = 8
        return max(1, min(24, value))

    def _live_append_reschedule_delay_ms(self, pending_count: int = 0) -> int:
        try:
            locked = bool(getattr(getattr(self, "sm", None), "is_locked", False))
        except Exception:
            locked = False
        if not locked:
            return 80
        backlog = max(0, int(pending_count or 0))
        return 10 if backlog >= 16 else 18

    def _on_drag_started(self): 
        # 💡 드래그를 시작하기 직전의 전체 뷰 스냅샷 저장!
        self._timeline_drag_in_progress = True
        self._undo_mgr.push_immediate()
        
        self._drag_cursor = QTextCursor(self.text_edit.document())
        self._drag_cursor.beginEditBlock()
        
    def _on_drag_finished(self): 
        if hasattr(self, '_drag_cursor') and self._drag_cursor:
            self._drag_cursor.endEditBlock()
            self._drag_cursor = None
        self._timeline_drag_in_progress = False
        self._schedule_timeline()

    # 💡 [신규] 특정 시간대의 블록을 지우고 새 자막으로 교체하는 외과 수술 로직
    # 💡 1. 선제적 삭제 및 위치 기억 (버튼 누르자마자 즉시 실행)
    def clear_segments_in_range(self, target_start: float, target_end: float):
        self._undo_mgr.push_immediate()
        doc = self.text_edit.document()
        cur = QTextCursor(doc)
        
        start_block, end_block = None, None
        for i in range(doc.blockCount()):
            b = doc.findBlockByNumber(i)
            ud = b.userData()
            if ud and hasattr(ud, 'start_sec'):
                if ud.start_sec >= target_start and start_block is None:
                    start_block = b
                if ud.start_sec >= target_end and start_block is not None:
                    end_block = b
                    break
        
        cur.beginEditBlock()
        if start_block:
            # 🚨 [쓰레기 자막 방지] 삭제 후 뒤로 밀려날 블록의 고유 시간 데이터를 백업합니다.
            end_ud = end_block.userData() if end_block else None
            
            cur.setPosition(start_block.position())
            if end_block:
                cur.setPosition(end_block.position(), QTextCursor.MoveMode.KeepAnchor)
            else:
                cur.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
            
            cur.removeSelectedText()
            
            # 단면이 붙지 않게 빈 줄(방화벽) 생성 후 백업 데이터 복구
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
            
            # 삽입될 '절대 위치' 기억
            self._partial_insert_pos = cur.position() 
        else:
            cur.movePosition(QTextCursor.MoveOperation.End)
            if not cur.atBlockStart():
                cur.insertText("\n")
            self._partial_insert_pos = cur.position()
            
        self.text_edit.update_margins()
        cur.endEditBlock()
        self._schedule_timeline()
    
    # 💡 2. 기억된 위치에 정밀 삽입 (자동저장 차단)
    # [ui/editor_segments.py] insert_partial_segments 함수 교체
    def insert_partial_segments(self, new_segments: list[dict]):
        try:
            self._undo_mgr.push_immediate()
            doc = self.text_edit.document()
            cur = QTextCursor(doc)
            if hasattr(self, '_partial_insert_pos'):
                cur.setPosition(self._partial_insert_pos)
            else:
                cur.movePosition(QTextCursor.MoveOperation.End)
                
            cur.beginEditBlock()
            spk1_id = self.settings.get("spk1_id", "00")
            spk2_id = self.settings.get("spk2_id", "01")
            from ui.editor.subtitle_text_edit import SubtitleBlockData
            
            for i, seg in enumerate(new_segments):
                if not cur.atBlockStart():
                    cur.insertBlock()
                text = seg.get("text", "").replace("\r", "")
                parts = [p.strip() for p in text.split('\n') if p.strip()]
                if not parts:
                    continue
                
                start_sec = self._frame_time(seg.get("start", 0))
                current_spk = seg.get("speaker_list", [spk1_id])[0] if seg.get("speaker_list") else spk1_id
                
                cur.insertText(parts[0])
                cur.block().setUserData(SubtitleBlockData(current_spk, start_sec))
                
                # 💡 [복구] 줄바꿈 및 화자 분리 로직 완벽 구현
                for p_idx in range(1, len(parts)):
                    line_text = parts[p_idx]
                    if line_text.startswith('-'):
                        current_spk = spk2_id if current_spk == spk1_id else spk1_id
                        cur.insertBlock() 
                        cur.insertText(line_text)
                        cur.block().setUserData(SubtitleBlockData(current_spk, start_sec))
                    else:
                        cur.insertText("\u2028" + line_text) 
                
                # Gap 처리
                gap_start = self._frame_time(seg['end'])
                if i + 1 < len(new_segments):
                    if seg['end'] < new_segments[i+1]['start'] - 0.05:
                        cur.insertBlock()
                        cur.block().setUserData(SubtitleBlockData("00", gap_start, is_gap=True))
                else:
                    cur.insertBlock()
                    cur.block().setUserData(SubtitleBlockData("00", gap_start, is_gap=True))

            # 💡 [핵심 수정] 상태 머신의 더티 플래그를 활성화합니다!
            self._mark_dirty()
                
            self.text_edit.update_margins()
            cur.endEditBlock()
            self._schedule_timeline()
        except Exception as e:
            from core.runtime.logger import get_logger
            get_logger().log(f"⚠️ 정밀 삽입 오류: {e}")

    
    def split_segment_with_text(self, line_num: int, split_sec: float, cursor: int):
        """
        플레이헤드 시간(split_sec) + 텍스트 커서(cursor) 기준으로
        현재 세그먼트를 2개로 분리한다.

        [v01.00.04]
        - block.text() 직접 사용 (canvas stale 데이터 참조 제거)
        - secondary_block_positions 삭제 로직 제거
          (현재 _get_current_segments()는 블록별 독립 세그먼트로 관리하므로
           같은 start_sec인 인접 블록을 지우면 다른 자막이 삭제되는 버그 발생)
        - '-' 화자 구분자 제거
        """
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
        spk_id    = ud.spk_id
        split_sec = self._frame_time(split_sec)

        # 범위 체크
        try:
            canvas_segs = self.timeline.canvas.segments
            end_map = {s.get("line"): float(s.get("end", 0.0))
                       for s in canvas_segs if s.get("line") is not None}
            end_sec = end_map.get(int(line_num))
            if end_sec is not None:
                if split_sec <= start_sec + 0.05 or split_sec >= end_sec - 0.05:
                    return
            else:
                if split_sec <= start_sec + 0.05:
                    return
        except Exception:
            if split_sec <= start_sec + 0.05:
                return

        # block.text() 직접 사용 (sig_inline_text_changed로 항상 최신 상태 보장)
        full_text = block.text().replace("\u2028", "\n")

        cursor = max(0, min(int(cursor), len(full_text)))
        left  = full_text[:cursor].rstrip()
        right = full_text[cursor:].lstrip()

        # ✅ 수정: right가 비어있으면 "새자막"으로 대체
        if not left:
            return
        if not right:
            right = "새자막"

        def _strip_leading_dash(t: str) -> str:
            lines = [line.strip() for line in t.splitlines() if line.strip()]
            if not lines:
                return ""
            if lines[0].startswith("-"):
                lines[0] = lines[0].lstrip("-").strip()
            return "\n".join(lines)

        left  = _strip_leading_dash(left)
        right = _strip_leading_dash(right)

        # ✅ 수정: right가 비어있으면 "새자막"으로 대체
        if not left:
            return
        if not right:
            right = "새자막"

        left_doc  = left.replace("\n", "\u2028")
        right_doc = right.replace("\n", "\u2028")

        cur = QTextCursor(block)
        cur.beginEditBlock()

        # primary block → left 파트로 교체 (StartOfBlock~EndOfBlock 범위만 선택)
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                         QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        cur.insertText(left_doc)
        cur.block().setUserData(
            SubtitleBlockData(spk_id, start_sec, is_gap=False)
        )

        # 새 블록 삽입 → right 파트
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cur.insertBlock()
        cur.insertText(right_doc)
        cur.block().setUserData(
            SubtitleBlockData(spk_id, split_sec, is_gap=False)
        )

        cur.endEditBlock()

        # 💡 [타임라인 튕김 완벽 방지] 커서 이동 시 화면이 중앙으로 강제 점프하는 것을 잠급니다.
        self._sync_lock = True  # 자동 센터링 방지 잠금
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        self.text_edit.setTextCursor(cur)
        
        self._active_seg_start = split_sec
        if hasattr(self, 'timeline'):
            self.timeline.set_active(self._active_seg_start)
            # 🎯 자막의 중간이 아니라, 대표님이 우클릭한 그 시점(split_sec)을 중앙으로!
            self.timeline.center_to_sec(split_sec, smooth=True)
        self._sync_lock = False

        self._mark_dirty()
        self._finalize_edit()
        arm_snapshot_undo = getattr(self, "_arm_snapshot_undo_routing", None)
        if callable(arm_snapshot_undo):
            arm_snapshot_undo()

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

        def _ensure_dash_prefix(value: str) -> str:
            text = str(value or "").strip()
            if not text:
                return ""
            return text if text.startswith("-") else f"- {text.lstrip('- ').strip()}"

        before_doc = _ensure_dash_prefix(before).replace("\n", "\u2028")
        after_doc = _ensure_dash_prefix(after).replace("\n", "\u2028")
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

        self._mark_dirty()
        self._finalize_edit()
        arm_snapshot_undo = getattr(self, "_arm_snapshot_undo_routing", None)
        if callable(arm_snapshot_undo):
            arm_snapshot_undo()
