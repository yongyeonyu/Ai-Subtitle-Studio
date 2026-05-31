"""Runtime activity, cache invalidation, and context-window helpers for editor segments."""

from __future__ import annotations

import re
import time
from bisect import bisect_left, bisect_right

from PyQt6.QtCore import QTimer

from core.frame_time import clamp_segments_to_duration
from core.runtime.logger import get_logger
from ui.editor.editor_helpers import build_segment_lookup
from ui.editor.subtitle_text_edit import SubtitleBlockData, subtitle_block_data_from_meta


class EditorSegmentsRuntimeCacheMixin:
    def _segment_clip_total_duration(self) -> float:
        player = getattr(self, "video_player", None)
        try:
            return max(0.0, float(getattr(player, "total_time", 0.0) or 0.0))
        except Exception:
            return 0.0

    def _clamp_segments_to_clip_duration(
        self,
        segments: list[dict] | None,
        *,
        log_changes: bool = True,
    ) -> list[dict]:
        rows = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
        total_duration = self._segment_clip_total_duration()
        if total_duration <= 0.0 or not rows:
            return rows
        clamped = clamp_segments_to_duration(
            rows,
            total_duration,
            fps=getattr(self, "video_fps", 30.0),
            preserve_order=True,
        )
        changed = len(clamped) != len(rows) or any(
            abs(float(before.get("start", 0.0) or 0.0) - float(after.get("start", 0.0) or 0.0)) > 1e-6
            or abs(float(before.get("end", 0.0) or 0.0) - float(after.get("end", 0.0) or 0.0)) > 1e-6
            for before, after in zip(rows, clamped)
        )
        if log_changes and changed:
            log_key = (
                round(float(total_duration), 3),
                len(rows),
                len(clamped),
                round(float(rows[-1].get("end", 0.0) or 0.0), 3) if rows else 0.0,
                round(float(clamped[-1].get("end", 0.0) or 0.0), 3) if clamped else 0.0,
            )
            now = time.monotonic()
            last_key = getattr(self, "_last_segment_clip_log_key", None)
            last_at = float(getattr(self, "_last_segment_clip_log_at", 0.0) or 0.0)
            # repaint/status 경로에서 같은 초과 세그먼트를 반복 정리하므로 로그만 dedupe해서 진행 상태를 오염시키지 않는다.
            if log_key != last_key or now - last_at > 30.0:
                self._last_segment_clip_log_key = log_key
                self._last_segment_clip_log_at = now
                get_logger().log(
                    "[세그먼트정리] "
                    f"clip={total_duration:.3f}s input={len(rows)} output={len(clamped)} "
                    "클립 길이 초과 세그먼트를 정리했습니다."
                )
        for line, seg in enumerate(clamped):
            seg["line"] = line
        return clamped

    def _mark_dirty(self):
        if hasattr(self, "_has_unsaved_changes") and not self._has_unsaved_changes():
            return
        self._skip_prev_confirm_once = False
        started_editing = False
        if hasattr(self, "sm"):
            if hasattr(self.sm, "start_editing") and not getattr(self.sm, "is_locked", False):
                self.sm.start_editing()
                started_editing = True
            else:
                setter = getattr(self, "_set_shared_dirty_state", None)
                if callable(setter):
                    setter(True, refresh_status=False)
                else:
                    self.sm.is_dirty = True
        setter = getattr(self, "_set_shared_dirty_state", None)
        if callable(setter):
            setter(True, refresh_status=True, broadcast=not started_editing)
        else:
            self._is_dirty = True
        if started_editing and hasattr(self, "_note_editor_foreground_activity"):
            self._note_editor_foreground_activity()

    def _note_editor_foreground_activity(self):
        self._last_editor_foreground_activity_at = time.monotonic()
        cancel_roughcut = getattr(self, "_cancel_post_generation_roughcut_draft", None)
        if callable(cancel_roughcut):
            try:
                cancel_roughcut(reason="편집 시작")
            except Exception:
                pass
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

    def _timestamp_restore_line_map_from_timeline(self) -> dict[int, dict]:
        canvas = getattr(getattr(self, "timeline", None), "canvas", None)
        rows = getattr(canvas, "segments", None) if canvas is not None else None
        if not isinstance(rows, (list, tuple)):
            return {}
        line_map: dict[int, dict] = {}
        for fallback_line, seg in enumerate(rows):
            if not isinstance(seg, dict):
                continue
            source = str(seg.get("stt_preview_source", seg.get("source", "")) or "").strip().upper()
            if bool(seg.get("_live_stt_preview")) or source in {"STT1", "STT2"}:
                continue
            try:
                line = int(seg.get("line", fallback_line))
            except Exception:
                line = int(fallback_line)
            if line >= 0:
                line_map[line] = seg
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
        return bool(seg_norm == block_norm or block_norm in seg_norm or seg_norm in block_norm)

    def _restore_block_user_data_from_cache(self, *, visible_only: bool) -> int:
        text_edit = getattr(self, "text_edit", None)
        if text_edit is None or not hasattr(text_edit, "document"):
            return 0
        canonical_snapshot = getattr(text_edit, "_canonical_timestamp_block_meta_snapshot", None)
        canonical_text_snapshot = getattr(text_edit, "_canonical_timestamp_block_text_snapshot", None)
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
        timeline_line_map = self._timestamp_restore_line_map_from_timeline()
        if timeline_line_map:
            merged_line_map = dict(timeline_line_map)
            merged_line_map.update(cached_line_map)
            cached_line_map = merged_line_map
            if not getattr(self, "_cached_line_map", None):
                self._cached_line_map = dict(cached_line_map)
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
        normalize_text = getattr(self, "_editor_sync_normalized_block_text", None)
        if not callable(normalize_text):
            normalize_text = lambda value: re.sub(r"\s+", " ", str(value or "").replace("\u2028", "\n").strip())
        block = doc.findBlockByNumber(int(start_line))
        while block.isValid() and block.blockNumber() <= int(end_line):
            current_meta = block.userData()
            line_number = int(block.blockNumber())
            current_text = normalize_text(block.text())
            canonical_meta = None
            if isinstance(canonical_snapshot, dict):
                canonical_meta = canonical_snapshot.get(line_number)
            canonical_text = None
            if isinstance(canonical_text_snapshot, dict):
                canonical_text = canonical_text_snapshot.get(line_number)
            if isinstance(canonical_meta, dict):
                canonical_text_ok = canonical_text is None or normalize_text(canonical_text) == current_text
                if canonical_text_ok:
                    needs_canonical_repair = not isinstance(current_meta, SubtitleBlockData)
                    if isinstance(current_meta, SubtitleBlockData):
                        try:
                            canonical_start = float(canonical_meta.get("start_sec", 0.0) or 0.0)
                            current_start = float(getattr(current_meta, "start_sec", 0.0) or 0.0)
                            canonical_end = canonical_meta.get("end_sec")
                            current_end = getattr(current_meta, "end_sec", None)
                            canonical_gap = bool(canonical_meta.get("is_gap", False))
                            current_gap = bool(getattr(current_meta, "is_gap", False))
                            needs_canonical_repair = (
                                abs(canonical_start - current_start) > 0.01
                                or canonical_gap != current_gap
                                or (canonical_end is None) != (current_end is None)
                                or (
                                    canonical_end is not None
                                    and current_end is not None
                                    and abs(float(canonical_end) - float(current_end)) > 0.01
                                )
                            )
                        except Exception:
                            needs_canonical_repair = False
                    if needs_canonical_repair:
                        block.setUserData(subtitle_block_data_from_meta(canonical_meta))
                        repaired += 1
                        block = block.next()
                        continue
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
                    seg_end = self._frame_time(max(seg_start, float(seg.get("end", seg_start) or seg_start)))
                    current_end_raw = getattr(current_meta, "end_sec", None)
                    current_end = (
                        float(current_end_raw)
                        if current_end_raw is not None
                        else float(current_meta.start_sec)
                    )
                    # 변경 금지: 자막 에디터/세그먼트 싱크 복구는 start뿐 아니라
                    # end도 반드시 비교해야 한다. 우측 화살표 병합/지우기 뒤에는
                    # 텍스트와 start가 같아도 end만 바뀌는 경우가 있어, end 비교가
                    # 빠지면 에디터는 0-1초, 타임라인은 0-2초처럼 서로 갈라진다.
                    needs_repair = (
                        abs(float(current_meta.start_sec) - float(seg_start)) > 0.01
                        or abs(float(current_end) - float(seg_end)) > 0.01
                    )
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
