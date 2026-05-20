# Version: 03.13.04
# Phase: PHASE2
"""
ui/editor_timeline_video.py
[v01.01.00] 리팩토링: editor_helpers 통합 + probe_media 적용
- Gap 헬퍼 → editor_helpers.py로 완전 이관
- ffprobe 직호출 → core.media_info.probe_media() 통합
- find_segment_at / get_sub_block_indices / _sync_cursor_to_seg 적용
- _mark_dirty / _finalize_edit 공용 메서드 활용
"""

from bisect import bisect_left
import os
import time
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.QtMultimedia import QMediaPlayer

from core.frame_time import frame_to_sec, normalize_fps, sec_to_nearest_frame, snap_sec_to_frame
from core.native_swift_timeline import plan_subtitle_timing_edit_via_swift
from ui.editor.timeline_scan_cut_patches import install_scan_cut_patches
from ui.editor.ux.editor_timeline_gap_split import EditorTimelineGapSplitMixin
from ui.editor.ux.editor_timeline_segment_merge import EditorTimelineSegmentMergeMixin
from ui.editor.ux.subtitle_text_edit import SubtitleBlockData
from ui.editor.editor_scan_cut_core import EditorScanCutCoreMixin
from ui.editor.editor_helpers import (
    find_segment_at, get_sub_block_indices,
    find_segment_at_lookup,
    build_segment_lookup,
)



class EditorTimelineVideoMixin(
    EditorTimelineGapSplitMixin,
    EditorTimelineSegmentMergeMixin,
    EditorScanCutCoreMixin,
):
    """타임라인/비디오 동기화 / 화자 관리 / 단축키 액션"""

    def _timeline_lock_edit_enabled(self) -> bool:
        lock_box = getattr(getattr(self, "timeline", None), "lock_chk", None)
        try:
            return bool(lock_box is not None and lock_box.isChecked())
        except RuntimeError:
            return False

    def _current_frame_fps(self) -> float:
        return normalize_fps(getattr(self, "video_fps", 30.0) or 30.0)

    def _playhead_active_interval_ms(self) -> int:
        try:
            settings = getattr(self, "settings", {}) or {}
            return max(16, min(80, int(settings.get("playhead_active_interval_ms", 24) or 24)))
        except Exception:
            return 24

    def _snap_to_frame(self, sec: float) -> float:
        return snap_sec_to_frame(sec, self._current_frame_fps())

    def _set_editor_frame_rate(self, fps: float):
        self.video_fps = normalize_fps(fps)
        if hasattr(self, "timeline") and hasattr(self.timeline, "set_frame_rate"):
            self.timeline.set_frame_rate(self.video_fps)
        if hasattr(self, "video_player") and hasattr(self.video_player, "set_frame_rate"):
            self.video_player.set_frame_rate(self.video_fps)

    def _reset_playhead_smoothing(self, sec: float | None = None):
        base_sec = self._snap_to_frame(float(sec if sec is not None else getattr(self.timeline.canvas, "playhead_sec", 0.0) or 0.0))
        self._playhead_display_sec = max(0.0, base_sec)
        self._playhead_anchor_global_sec = max(0.0, base_sec)
        self._playhead_anchor_mono = time.monotonic()

    def _smooth_playhead_sec(self, raw_global_sec: float, now_mono: float, dur_sec: float) -> float:
        raw_global_sec = max(0.0, float(raw_global_sec or 0.0))
        dur_sec = max(0.0, float(dur_sec or 0.0))
        display = getattr(self, "_playhead_display_sec", None)
        anchor_sec = getattr(self, "_playhead_anchor_global_sec", None)
        anchor_mono = getattr(self, "_playhead_anchor_mono", None)
        if display is None or anchor_sec is None or anchor_mono is None:
            self._reset_playhead_smoothing(raw_global_sec)
            return raw_global_sec

        predicted = float(anchor_sec) + max(0.0, now_mono - float(anchor_mono))
        if dur_sec > 0:
            predicted = min(predicted, dur_sec + self._multiclip_active_offset())

        drift = raw_global_sec - predicted
        if abs(drift) >= 0.35:
            smoothed = raw_global_sec
        elif drift >= 0.0:
            smoothed = predicted + drift * 0.35
        else:
            smoothed = predicted + drift * 0.08

        previous = float(display)
        reset_jump = abs(drift) >= 0.35 or abs(raw_global_sec - previous) >= 0.35
        if not reset_jump:
            max_step = max(
                0.018,
                min(0.08, now_mono - float(getattr(self, "_last_playhead_smooth_tick", now_mono) or now_mono) + 0.018),
            )
            if smoothed < previous and previous - smoothed < 0.18:
                smoothed = previous
            elif smoothed > previous + max_step:
                smoothed = previous + max_step

        self._last_playhead_smooth_tick = now_mono
        self._playhead_display_sec = self._snap_to_frame(max(0.0, smoothed))
        self._playhead_anchor_global_sec = raw_global_sec
        self._playhead_anchor_mono = now_mono
        return self._playhead_display_sec

    def _multiclip_active_offset(self) -> float:
        owner = self.window()
        bounds = list(getattr(owner, '_multiclip_boundaries', []) or [])
        if not bounds:
            return 0.0
        clip_idx = int(getattr(self.timeline.canvas, '_active_clip_idx', getattr(owner, '_active_clip_idx', 0)) or 0)
        clip_idx = max(0, min(clip_idx, len(bounds) - 1))
        return float(bounds[clip_idx].get('start', 0.0))

    def _global_to_local_sec(self, sec: float) -> float:
        return max(0.0, float(sec) - self._multiclip_active_offset())

    def _local_to_global_sec(self, sec: float) -> float:
        return max(0.0, float(sec) + self._multiclip_active_offset())

    def _current_video_local_frame_sec(self, player) -> float:
        video_player = getattr(self, "video_player", None)
        if video_player is not None and hasattr(video_player, "current_playback_frame_time"):
            _frame, local_sec = video_player.current_playback_frame_time()
            return float(local_sec)
        return self._snap_to_frame(player.position() / 1000.0)

    def _is_player_playing(self, player) -> bool:
        if player is None:
            return False
        try:
            state = player.playbackState()
        except Exception:
            return False
        try:
            if state == QMediaPlayer.PlaybackState.PlayingState:
                return True
        except Exception:
            pass
        try:
            playback_state = getattr(player, "PlaybackState", None)
            playing_state = getattr(playback_state, "PlayingState", None)
            if playing_state is not None:
                return state == playing_state
        except Exception:
            pass
        return False


    # ---------------------------------------------------------
    # Common: Cursor ↔ Block Sync
    # ---------------------------------------------------------
    def _sync_cursor_to_seg(self, seg, ensure_visible=True, move_cursor=True, *, sync_playhead=True):
        """커서↔블록 동기화: active/하이라이트 + (옵션) 커서 이동"""
        self._active_seg_start = seg["start"]
        # 재생 중 타임라인 active 강조는 그래픽 잔상/깨짐을 유발할 수 있어 비활성화한다.
        player = getattr(getattr(self, 'video_player', None), 'media_player', None)
        is_playing = self._is_player_playing(player)
        if is_playing and hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
            clear_active_visual = getattr(self.timeline.canvas, "clear_active_visual", None)
            if callable(clear_active_visual):
                clear_active_visual()
        else:
            self.timeline.set_active(seg["start"])
        if sync_playhead and (not is_playing) and hasattr(self, 'timeline') and hasattr(self.timeline, 'set_playhead'):
            self._reset_playhead_smoothing(seg["start"])
            self.timeline.set_playhead(seg["start"])
            # 선택/자동화 경로도 비디오 overlay가 같은 자막 시간을 즉시 보도록 맞춘다.
            player_widget = getattr(self, "video_player", None)
            if player_widget is not None and hasattr(player_widget, "set_subtitle_display_time"):
                local_sec = float(seg.get("start", 0.0) or 0.0)
                if hasattr(self, "_global_to_local_sec"):
                    try:
                        local_sec = float(self._global_to_local_sec(local_sec))
                    except Exception:
                        local_sec = float(seg.get("start", 0.0) or 0.0)
                try:
                    player_widget.set_subtitle_display_time(local_sec)
                except Exception:
                    pass
        line_num = seg.get("line", 0)
        self._highlighter.set_current_line(line_num)
        remember_repeat_segment = getattr(self, "_remember_repeat_segment", None)
        repeat_enabled = getattr(self, "_segment_repeat_enabled", None)
        if callable(remember_repeat_segment) and callable(repeat_enabled) and repeat_enabled():
            remember_repeat_segment(seg)
        if not move_cursor:
            return
        block = self.text_edit.document().findBlockByNumber(line_num)
        if block.isValid():
            needs_scroll = bool(ensure_visible and not self._editor_block_visible(block))
            try:
                already_on_line = int(self.text_edit.textCursor().blockNumber()) == int(line_num)
            except Exception:
                already_on_line = False
            if already_on_line and not needs_scroll:
                return
            self._sync_lock = True
            try:
                if not already_on_line:
                    cur = QTextCursor(block)
                    self.text_edit.setTextCursor(cur)
                if needs_scroll:
                    self.text_edit.ensureCursorVisible()
            finally:
                self._sync_lock = False

    def _editor_block_visible(self, block, *, margin_px: int = 24) -> bool:
        text_edit = getattr(self, "text_edit", None)
        if text_edit is None or not block.isValid():
            return False
        try:
            cursor = QTextCursor(block)
            rect = text_edit.cursorRect(cursor)
            viewport = text_edit.viewport()
            top_limit = -int(margin_px)
            bottom_limit = int(viewport.height()) + int(margin_px)
            return rect.top() >= top_limit and rect.bottom() <= bottom_limit
        except Exception:
            return False

    def _editor_manual_scroll_recent(self, now_mono: float | None = None, *, hold_sec: float = 1.15) -> bool:
        now = time.monotonic() if now_mono is None else float(now_mono)
        text_edit = getattr(self, "text_edit", None)
        markers = [
            float(getattr(self, "_last_editor_manual_scroll_at", 0.0) or 0.0),
            float(getattr(text_edit, "_last_user_scroll_at", 0.0) or 0.0) if text_edit is not None else 0.0,
        ]
        return any(marker > 0.0 and (now - marker) < hold_sec for marker in markers)

    def _playback_can_move_editor_cursor(self) -> bool:
        """Allow playback follow unless the user is actively editing/selecting."""
        if not hasattr(self, "text_edit"):
            return False
        if self._timeline_lock_edit_enabled():
            return False
        canvas = getattr(getattr(self, "timeline", None), "canvas", None)
        if bool(getattr(canvas, "_edit_active", False)):
            return False
        popup = getattr(self, "editor_popup", None)
        try:
            if popup is not None and popup.is_visible():
                return False
        except Exception:
            pass
        try:
            if self.text_edit.textCursor().hasSelection():
                return False
        except Exception:
            return False
        return True

    def _segment_at_playback_sec(self, sec: float, *, skip_gap: bool = True):
        cache = getattr(self, "_subtitle_memory_cache", None)
        seg = find_segment_at_lookup(cache, sec, skip_gap=skip_gap)
        if seg is not None:
            return seg
        segs = getattr(self, '_cached_segs', None)
        if segs is None:
            if hasattr(self, "_rebuild_subtitle_memory_cache"):
                cache = self._rebuild_subtitle_memory_cache()
                seg = find_segment_at_lookup(cache, sec, skip_gap=skip_gap)
                if seg is not None:
                    return seg
                segs = list(cache.get("segments") or [])
            else:
                segs = self._get_current_segments()
                self._cached_segs = segs
        return find_segment_at(segs, sec, skip_gap=skip_gap)

    def _schedule_background_prefetch(self, current_sec: float, segments: list[dict] | None = None) -> None:
        try:
            settings = dict(getattr(self, "settings", {}) or {})
            if not settings.get("background_prefetch_enabled", True):
                return
            try:
                player_obj = getattr(getattr(self, "video_player", None), "media_player", None)
                playing_now = self._is_player_playing(player_obj)
            except Exception:
                playing_now = False
            allow_during_playback = settings.get("background_prefetch_during_playback", False)
            if isinstance(allow_during_playback, str):
                allow_during_playback = allow_during_playback.strip().lower() in {"1", "true", "yes", "on"}
            if playing_now and not bool(allow_during_playback):
                return
            media_path = str(getattr(self, "media_path", "") or "")
            if not media_path:
                player = getattr(self, "video_player", None)
                media_path = str(getattr(player, "path", "") or getattr(player, "media_path", "") or "")
            bucket_sec = max(1.0, float(settings.get("background_prefetch_bucket_sec", 6.0) or 6.0))
            min_interval = max(0.1, float(settings.get("background_prefetch_min_interval_sec", 0.75) or 0.75))
            now_mono = time.monotonic()
            key = f"{os.path.abspath(str(media_path or ''))}|{int(float(current_sec or 0.0) // bucket_sec)}"
            if (
                key == str(getattr(self, "_last_background_prefetch_gate_key", "") or "")
                and now_mono - float(getattr(self, "_last_background_prefetch_gate_at", 0.0) or 0.0) < min_interval
            ):
                return
            self._last_background_prefetch_gate_key = key
            self._last_background_prefetch_gate_at = now_mono
            if segments is None:
                segments = getattr(self, "_cached_segs", None)
            if segments is None:
                segments = []
            manager = getattr(self, "_background_prefetch_manager", None)
            if manager is None:
                from core.pipeline.background_prefetch import BackgroundPrefetchManager

                manager = BackgroundPrefetchManager()
                self._background_prefetch_manager = manager
            result = manager.request(
                media_path=media_path,
                current_sec=float(current_sec or 0.0),
                segments=segments or (),
                settings=settings,
            )
            self._last_background_prefetch_request = result
        except Exception:
            pass

    # ---------------------------------------------------------
    # Timeline Segment Events
    # ---------------------------------------------------------

    def _segment_from_timeline_canvas_click(self, line_num, click_sec: float):
        canvas = getattr(getattr(self, "timeline", None), "canvas", None)
        rows = list(getattr(canvas, "segments", []) or []) if canvas is not None else []
        if not rows:
            return None
        best: tuple[tuple[int, float], dict] | None = None
        try:
            line_key = int(line_num)
        except Exception:
            line_key = -1
        for seg in rows:
            if not isinstance(seg, dict) or seg.get("is_gap"):
                continue
            try:
                start = self._snap_to_frame(float(seg.get("start", 0.0) or 0.0))
                end = self._snap_to_frame(float(seg.get("end", start) or start))
                seg_line = int(seg.get("line", -1))
            except Exception:
                continue
            contains_click = start <= click_sec < end
            near_start = abs(start - click_sec) <= 0.15
            score = None
            if seg_line == line_key and (contains_click or near_start):
                score = (0, abs(start - click_sec))
            elif contains_click:
                score = (1, abs(start - click_sec))
            elif near_start:
                score = (2, abs(start - click_sec))
            if score is None:
                continue
            if best is None or score < best[0]:
                best = (score, seg)
        return best[1] if best is not None else None

    def _segment_for_timeline_click(self, line_num, start_sec, cache: dict | None = None):
        try:
            click_sec = self._snap_to_frame(float(start_sec or 0.0))
        except Exception:
            click_sec = 0.0
        if not isinstance(cache, dict):
            cached = getattr(self, "_cached_segs", None)
            if cached is not None:
                cache = build_segment_lookup(cached)
            elif hasattr(self, "_rebuild_subtitle_memory_cache"):
                cache = self._rebuild_subtitle_memory_cache()
            else:
                cache = build_segment_lookup(self._get_current_segments())
            self._subtitle_memory_cache = cache

        line_seg = None
        try:
            line_seg = (cache.get("line_map") or {}).get(int(line_num))
        except Exception:
            line_seg = None

        time_seg = find_segment_at_lookup(cache, click_sec, skip_gap=False)
        if time_seg is None:
            time_seg = self._nearest_segment_start_match(cache, click_sec, tolerance=0.15)
        canvas_seg = self._segment_from_timeline_canvas_click(line_num, click_sec)

        if isinstance(canvas_seg, dict):
            return canvas_seg

        if isinstance(line_seg, dict):
            try:
                line_start = self._snap_to_frame(float(line_seg.get("start", 0.0) or 0.0))
            except Exception:
                line_start = click_sec
            if click_sec <= 0.001 or abs(line_start - click_sec) <= 0.15:
                return line_seg
        if isinstance(time_seg, dict):
            return time_seg
        return line_seg

    def _nearest_segment_start_match(self, cache: dict | None, click_sec: float, tolerance: float = 0.15):
        if not isinstance(cache, dict):
            return None
        segments = cache.get("segments") or ()
        starts = cache.get("starts") or ()
        if not segments or not starts:
            return None
        try:
            now = float(click_sec or 0.0)
        except Exception:
            now = 0.0
        limit = max(0.0, float(tolerance or 0.0))
        idx = bisect_left(starts, now)
        best = None
        for candidate_idx in (idx - 1, idx, idx + 1):
            if candidate_idx < 0 or candidate_idx >= len(segments):
                continue
            seg = segments[candidate_idx]
            if not isinstance(seg, dict):
                continue
            try:
                start = self._snap_to_frame(float(seg.get("start", 0.0) or 0.0))
            except Exception:
                continue
            dist = abs(start - now)
            if dist <= limit and (best is None or dist < best[0]):
                best = (dist, seg)
        return best[1] if best is not None else None

    def _on_timeline_seg_clicked(self, line_num, start_sec):
        click_sec = self._snap_to_frame(float(start_sec or 0.0))
        cache = getattr(self, "_subtitle_memory_cache", None)
        seg = self._segment_for_timeline_click(line_num, click_sec, cache)
        lock_edit = self._timeline_lock_edit_enabled()
        if hasattr(self, "timeline") and hasattr(self.timeline, "set_playhead"):
            self._reset_playhead_smoothing(click_sec)
            self.timeline.set_playhead(click_sec)
        if seg:
            target_sec = float(seg.get("start", click_sec) or click_sec or 0.0)
            line_num = int(seg.get("line", line_num) if seg.get("line") is not None else line_num)
            if lock_edit:
                self._active_seg_start = target_sec
                self.timeline.set_active(target_sec)
            else:
                self._sync_cursor_to_seg(seg, sync_playhead=False)
            target_end = float(seg.get("end", target_sec) or target_sec)
            target_view_sec = min(max(click_sec, target_sec), target_end)
            if hasattr(self.timeline, "ensure_sec_visible"):
                self.timeline.ensure_sec_visible(target_view_sec, smooth=True, margin_px=96)
            else:
                self.timeline.center_to_sec(target_view_sec, smooth=True)
            if hasattr(self, '_resolve_active_context') and hasattr(self, '_apply_active_context'):
                ctx = self._resolve_active_context(global_sec=click_sec)
                self._apply_active_context(ctx, autoplay=False, show_thumbnail=True)
            elif hasattr(self, 'video_player'):
                self.video_player.pause_video()
                self.video_player.seek_direct(click_sec)
            remember_repeat_segment = getattr(self, "_remember_repeat_segment", None)
            repeat_enabled = getattr(self, "_segment_repeat_enabled", None)
            if callable(remember_repeat_segment) and callable(repeat_enabled) and repeat_enabled():
                remember_repeat_segment(seg)
        if lock_edit:
            if hasattr(self.timeline, "canvas"):
                self.timeline.canvas.setFocus()
        else:
            self.text_edit.setFocus()


    def _on_timeline_seg_double_clicked(self, line_num, start_sec):
        seg = self._segment_for_timeline_click(line_num, start_sec, getattr(self, "_subtitle_memory_cache", None))
        if isinstance(seg, dict):
            start_sec = float(seg.get("start", start_sec) or start_sec or 0.0)
            line_num = int(seg.get("line", line_num) if seg.get("line") is not None else line_num)
        self._active_seg_start = start_sec
        self.timeline.set_active(start_sec)
        if hasattr(self, '_resolve_active_context') and hasattr(self, '_apply_active_context'):
            ctx = self._resolve_active_context(global_sec=float(start_sec))
            self._apply_active_context(ctx, autoplay=False, show_thumbnail=True)
        elif hasattr(self, 'video_player'):
            self.video_player.pause_video()
            self.video_player.seek_direct(float(start_sec))
        remember_repeat_segment = getattr(self, "_remember_repeat_segment", None)
        repeat_enabled = getattr(self, "_segment_repeat_enabled", None)
        if callable(remember_repeat_segment) and callable(repeat_enabled) and repeat_enabled() and isinstance(seg, dict):
            remember_repeat_segment(seg)
        if hasattr(self.timeline, 'canvas') and hasattr(self.timeline.canvas, 'start_inline_edit'):
            self._undo_mgr.push_immediate()
            self.timeline.canvas.start_inline_edit(line_num, start_sec, split_at_playhead=False)

    def _sync_playhead(self):
        if not hasattr(self, 'video_player') or not hasattr(self, 'timeline'):
            return
        player = self.video_player.media_player
        if not self._is_player_playing(player):
            self._set_playhead_timer_interval(80)
            if not bool(getattr(self, "_playhead_idle_synced", False)):
                if hasattr(self.timeline, "set_playback_center_lock"):
                    self.timeline.set_playback_center_lock(False)
                self._reset_playhead_smoothing(getattr(self.timeline.canvas, "playhead_sec", 0.0))
                self._playhead_idle_synced = True
            return
        self._playhead_idle_synced = False
        self._set_playhead_timer_interval(self._playhead_active_interval_ms())
        dur_ms = player.duration()
        if dur_ms <= 0:
            return

        now_mono = time.monotonic()
        local_sec = self._current_video_local_frame_sec(player)
        raw_current_sec = self._snap_to_frame(self._local_to_global_sec(local_sec))
        maybe_repeat = getattr(self, "_maybe_loop_selected_segment", None)
        if callable(maybe_repeat):
            looped_sec = maybe_repeat(raw_current_sec)
            if looped_sec is not None:
                raw_current_sec = self._snap_to_frame(looped_sec)
        display_sec = self._smooth_playhead_sec(raw_current_sec, now_mono, dur_ms / 1000.0)
        self._schedule_background_prefetch(raw_current_sec)
        if hasattr(self.timeline, "follow_playhead_centered"):
            self.timeline.follow_playhead_centered(display_sec, smooth=True)
        elif hasattr(self.timeline, "follow_playhead"):
            self.timeline.follow_playhead(display_sec, smooth=True, threshold_px=24.0)
        else:
            self.timeline.set_playhead(display_sec)

        # Context sync: skip resolve if within cached clip bounds (C fix v2)
        if hasattr(self, '_resolve_active_context') and hasattr(self, 'video_player'):
            _mc_boxes = list(getattr(self.timeline.canvas, '_multiclip_boxes', []) or []) if hasattr(self, 'timeline') else []
            if _mc_boxes:
                _cb = getattr(self, '_cached_clip_bounds', None)
                last_ctx_at = float(getattr(self, '_last_play_context_sync_at', 0.0) or 0.0)
                if not (_cb and _cb[0] <= raw_current_sec < _cb[1]) and (now_mono - last_ctx_at) >= 0.25:
                    self._last_play_context_sync_at = now_mono
                    ctx = self._resolve_active_context(global_sec=raw_current_sec)
                    _cidx = int(ctx.get('clip_idx', 0))
                    self._cached_clip_bounds = (float(ctx.get('clip_start', 0.0)), float(ctx.get('clip_end', 0.0)))
                    if _cidx != getattr(self, '_last_sync_clip_idx', -1):
                        self._last_sync_clip_idx = _cidx
                        local_segments = list(ctx.get('local_segments', []) or [])
                        if hasattr(self, "_subtitle_context_window_from_segments"):
                            local_segments = self._subtitle_context_window_from_segments(
                                local_segments,
                                center_sec=float(ctx.get("local_sec", 0.0) or 0.0),
                            )
                        self.video_player.set_context_segments(local_segments)

        seg = self._segment_at_playback_sec(raw_current_sec, skip_gap=True)
        if seg and self._active_seg_start != seg["start"]:
            can_move_editor = self._playback_can_move_editor_cursor()
            if can_move_editor and not self._editor_manual_scroll_recent(now_mono):
                self._last_play_cursor_sync_at = now_mono
                self._last_editor_autoscroll_at = now_mono
                self._sync_cursor_to_seg(seg, ensure_visible=True, move_cursor=True)
            else:
                last_cursor_at = float(getattr(self, '_last_play_cursor_sync_at', 0.0) or 0.0)
                if (now_mono - last_cursor_at) >= 0.10:
                    self._last_play_cursor_sync_at = now_mono
                    self._sync_cursor_to_seg(seg, ensure_visible=False, move_cursor=False)
        elif seg:
            last_scroll_at = float(getattr(self, '_last_editor_autoscroll_at', 0.0) or 0.0)
            if (
                self._playback_can_move_editor_cursor()
                and not self._editor_manual_scroll_recent(now_mono)
                and (now_mono - last_scroll_at) >= 0.60
            ):
                self._last_editor_autoscroll_at = now_mono
                self._sync_cursor_to_seg(seg, ensure_visible=True, move_cursor=True)
        local_display_sec = self._global_to_local_sec(raw_current_sec)
        if hasattr(self.video_player, 'set_subtitle_display_time'):
            self.video_player.set_subtitle_display_time(local_display_sec)
        elif hasattr(self.video_player, 'refresh_subtitle_context'):
            self.video_player.refresh_subtitle_context()


    def _set_playhead_timer_interval(self, interval_ms: int) -> None:
        timer = getattr(self, "_playhead_timer", None)
        if timer is None:
            return
        try:
            interval_ms = max(16, int(interval_ms))
            if int(timer.interval()) != interval_ms:
                timer.setInterval(interval_ms)
        except Exception:
            pass


    def _on_scrub(self, sec):
        if hasattr(self, "_scan_should_block_user_timeline_input") and self._scan_should_block_user_timeline_input():
            try:
                self.video_player.info_label.setText("컷 경계 탐색 중에는 타임라인 입력이 잠깁니다.")
            except Exception:
                pass
            return

        sec = self._snap_to_frame(sec)
        self._reset_playhead_smoothing(sec)
        self._playhead_idle_synced = False
        self.timeline.set_playhead(sec)
        self._pending_scrub_sec = sec
        self._schedule_scrub_preview(sec)
        self._schedule_scrub_settle()

    def _on_timing_drag_preview(self, sec: float) -> None:
        if hasattr(self, "_scan_should_block_user_timeline_input") and self._scan_should_block_user_timeline_input():
            return
        sec = self._snap_to_frame(sec)
        self._reset_playhead_smoothing(sec)
        self._playhead_idle_synced = False
        timeline = getattr(self, "timeline", None)
        if timeline is not None:
            try:
                timeline.set_playhead(sec, preserve_center_lock=True)
            except TypeError:
                timeline.set_playhead(sec)
        self._pending_scrub_sec = sec
        self._schedule_scrub_preview(sec)

    def _make_scrub_timer(self):
        try:
            return QTimer(self)
        except TypeError:
            return QTimer()

    def _ensure_scrub_timers(self) -> None:
        if not hasattr(self, "_scrub_preview_timer"):
            timer = self._make_scrub_timer()
            timer.setSingleShot(True)
            timer.timeout.connect(self._apply_pending_scrub_preview)
            self._scrub_preview_timer = timer
        if not hasattr(self, "_scrub_settle_timer"):
            timer = self._make_scrub_timer()
            timer.setSingleShot(True)
            timer.timeout.connect(self._apply_settled_scrub)
            self._scrub_settle_timer = timer

    def _schedule_scrub_preview(self, sec: float) -> None:
        self._ensure_scrub_timers()
        now = time.monotonic()
        interval = max(0.030, float(getattr(self, "_scrub_preview_interval_sec", 0.075) or 0.075))
        last = float(getattr(self, "_last_scrub_preview_at", 0.0) or 0.0)
        if now - last >= interval:
            self._apply_scrub_preview(sec)
            return
        delay_ms = max(1, int((interval - (now - last)) * 1000))
        try:
            self._scrub_preview_timer.start(delay_ms)
        except Exception:
            pass

    def _schedule_scrub_settle(self) -> None:
        self._ensure_scrub_timers()
        delay_ms = max(80, int(getattr(self, "_scrub_settle_delay_ms", 180) or 180))
        try:
            self._scrub_settle_timer.start(delay_ms)
        except Exception:
            pass

    def _apply_pending_scrub_preview(self) -> None:
        sec = getattr(self, "_pending_scrub_sec", None)
        if sec is None:
            return
        self._apply_scrub_preview(float(sec))

    def _preview_seek_video_player(self, sec: float) -> None:
        player = getattr(self, "video_player", None)
        if player is None:
            return
        if hasattr(player, "preview_seek"):
            player.preview_seek(sec)
        elif hasattr(player, "frame_step_seek"):
            player.frame_step_seek(sec)
        elif hasattr(player, "seek_direct"):
            player.seek_direct(sec)

    def _apply_scrub_preview(self, sec: float) -> None:
        sec = self._snap_to_frame(sec)
        self._last_scrub_preview_at = time.monotonic()

        timeline = getattr(self, "timeline", None)
        canvas = getattr(timeline, "canvas", None)
        boxes = list(getattr(canvas, "_multiclip_boxes", []) or [])
        if boxes and hasattr(self, "_resolve_active_context") and hasattr(self, "_apply_active_context"):
            ctx = self._resolve_active_context(global_sec=sec)
            clip_file = str(ctx.get("clip_file", "") or "")
            current_path = str(getattr(getattr(self, "video_player", None), "_current_source_path", "") or "")
            same_source = bool(clip_file and current_path) and os.path.normpath(clip_file) == os.path.normpath(current_path)
            if same_source:
                if hasattr(self.timeline, "canvas"):
                    self.timeline.canvas._active_clip_idx = int(ctx.get("clip_idx", 0) or 0)
                self._preview_seek_video_player(float(ctx.get("local_sec", sec) or 0.0))
            else:
                self._apply_active_context(ctx, autoplay=False, show_thumbnail=False)
        else:
            self._preview_seek_video_player(sec)

        local_display_sec = self._global_to_local_sec(sec) if hasattr(self, "_global_to_local_sec") else sec
        player = getattr(self, "video_player", None)
        if player is not None and hasattr(player, "set_subtitle_display_time"):
            player.set_subtitle_display_time(local_display_sec)

    def _apply_settled_scrub(self) -> None:
        sec = getattr(self, "_pending_scrub_sec", None)
        if sec is None:
            return
        sec = self._snap_to_frame(float(sec))
        self._apply_scrub_preview(sec)
        segs = getattr(self, "_cached_segs", None)
        if segs is not None:
            self._schedule_background_prefetch(sec, segs)
        else:
            self._schedule_background_prefetch(sec, [])
        seg = self._segment_at_playback_sec(sec, skip_gap=False)
        if seg and self._active_seg_start != seg["start"]:
            canvas = getattr(getattr(self, "timeline", None), "canvas", None)
            move_editor = (
                not self._timeline_lock_edit_enabled()
                and not bool(getattr(canvas, "_edit_active", False))
                and not self._editor_manual_scroll_recent()
            )
            self._sync_cursor_to_seg(seg, ensure_visible=move_editor, move_cursor=move_editor, sync_playhead=False)
        remember_repeat_segment = getattr(self, "_remember_repeat_segment", None)
        repeat_enabled = getattr(self, "_segment_repeat_enabled", None)
        if callable(remember_repeat_segment) and callable(repeat_enabled) and repeat_enabled() and isinstance(seg, dict):
            remember_repeat_segment(seg)
        self._pending_scrub_sec = None

    def _manual_global_sec_from_player(self) -> float:
        fps = self._current_frame_fps()
        timeline_sec = self._snap_to_frame(float(getattr(self.timeline.canvas, "playhead_sec", 0.0) or 0.0))
        try:
            local_sec = self._snap_to_frame(float(self.video_player.media_player.position() or 0) / 1000.0)
            global_sec = self._snap_to_frame(self._local_to_global_sec(local_sec))
            if abs(global_sec - timeline_sec) <= max(0.30, 10.0 / max(1.0, fps)):
                return global_sec
        except Exception:
            pass
        return timeline_sec

    def _seek_global_exact(self, global_sec: float) -> bool:
        global_sec = self._snap_to_frame(max(0.0, float(global_sec or 0.0)))
        if not hasattr(self, "video_player"):
            return False

        if hasattr(self, "_resolve_active_context") and hasattr(self, "_apply_active_context"):
            ctx = self._resolve_active_context(global_sec=global_sec)
            clip_file = str(ctx.get("clip_file", "") or "")
            current_path = str(getattr(self.video_player, "_current_source_path", "") or "")
            same_source = bool(clip_file and current_path) and os.path.normpath(clip_file) == os.path.normpath(current_path)
            if not same_source:
                return False
            if hasattr(self.timeline, "canvas"):
                self.timeline.canvas._active_clip_idx = int(ctx.get("clip_idx", 0) or 0)
            local_sec = float(ctx.get("local_sec", global_sec) or 0.0)
        else:
            local_sec = global_sec

        if hasattr(self.video_player, "frame_step_seek"):
            self.video_player.frame_step_seek(local_sec)
        else:
            self.video_player.seek_direct(local_sec)
        return True

    def _sync_after_manual_seek(self, global_sec: float):
        global_sec = self._snap_to_frame(max(0.0, float(global_sec or 0.0)))
        segs = self._get_current_segments()
        seg = find_segment_at(segs, global_sec, skip_gap=False)
        if seg and getattr(self, "_active_seg_start", None) != seg.get("start"):
            self._sync_cursor_to_seg(seg, sync_playhead=False)
        remember_repeat_segment = getattr(self, "_remember_repeat_segment", None)
        repeat_enabled = getattr(self, "_segment_repeat_enabled", None)
        if callable(remember_repeat_segment) and callable(repeat_enabled) and repeat_enabled() and isinstance(seg, dict):
            remember_repeat_segment(seg)
        self._reset_playhead_smoothing(global_sec)
        self.timeline.set_playhead(global_sec)
        self.timeline.center_to_sec(global_sec, smooth=False)



    def _on_step_frame(self, direction):
        if not hasattr(self, 'video_player'):
            return

        try:
            raw_direction = int(direction)
        except Exception:
            raw_direction = 1
        if raw_direction == 0:
            return
        direction = 1 if raw_direction > 0 else -1
        frame_delta = max(1, abs(raw_direction))

        try:
            self.video_player.pause_video()
        except Exception:
            pass

        fps = self._current_frame_fps()
        current_global = float(getattr(self.timeline.canvas, 'playhead_sec', 0.0) or 0.0)
        local_frame = None
        cached_manual_frame = getattr(self, "_manual_frame_idx", None)
        if cached_manual_frame is not None:
            try:
                cached_manual_frame = max(0, int(cached_manual_frame))
                cached_manual_sec = frame_to_sec(cached_manual_frame, fps)
                if abs(cached_manual_sec - current_global) <= max(1.5 / max(fps, 1e-6), 0.030):
                    local_frame = cached_manual_frame
            except Exception:
                local_frame = None
        if local_frame is None:
            local_frame = max(0, sec_to_nearest_frame(current_global, fps))
        target_frame = max(0, local_frame + (direction * frame_delta))
        global_sec = self._snap_to_frame(frame_to_sec(target_frame, fps))
        self._manual_frame_idx = max(0, int(target_frame))

        if hasattr(self, '_resolve_active_context') and hasattr(self, '_apply_active_context'):
            ctx = self._resolve_active_context(global_sec=global_sec)
            clip_file = str(ctx.get('clip_file', '') or '')
            current_path = str(getattr(self.video_player, '_current_source_path', '') or '')
            same_source = bool(clip_file and current_path) and os.path.normpath(clip_file) == os.path.normpath(current_path)

            if same_source:
                if hasattr(self.timeline, 'canvas'):
                    self.timeline.canvas._active_clip_idx = int(ctx.get('clip_idx', 0) or 0)
                target_local = float(ctx.get('local_sec', global_sec) or 0.0)
                try:
                    if hasattr(self.video_player, "frame_step_seek"):
                        self.video_player.frame_step_seek(target_local)
                    else:
                        self.video_player.seek_direct(target_local)
                except Exception as e:
                    print(f"⚠️ [frame-step] player seek failed: {e}", flush=True)
                    return
            else:
                try:
                    self._apply_active_context(ctx, autoplay=False, show_thumbnail=False)
                except Exception as e:
                    print(f"⚠️ [frame-step] context switch failed: {e}", flush=True)
                    return
                target_local = float(ctx.get('local_sec', global_sec) or 0.0)
        else:
            target_local = global_sec
            try:
                if hasattr(self.video_player, "frame_step_seek"):
                    self.video_player.frame_step_seek(target_local)
                else:
                    self.video_player.seek_direct(target_local)
            except Exception as e:
                print(f"⚠️ [frame-step] player seek failed: {e}", flush=True)
                return

        try:
            segs = self._get_current_segments()
            seg = find_segment_at(segs, global_sec, skip_gap=False)
            if seg and getattr(self, "_active_seg_start", None) != seg.get("start"):
                self._sync_cursor_to_seg(seg, sync_playhead=False)
        except Exception:
            pass

        self._reset_playhead_smoothing(global_sec)
        self.timeline.set_playhead(global_sec)
        arm_shadow = getattr(self.timeline, "arm_shadow_playhead", None)
        if callable(arm_shadow):
            try:
                arm_shadow(global_sec)
            except Exception:
                pass
        else:
            canvas = getattr(self.timeline, "canvas", None)
            if canvas is not None:
                try:
                    canvas._shadow_playhead_armed_sec = global_sec
                except Exception:
                    pass
            clear_shadow = getattr(self.timeline, "clear_shadow_playhead", None)
            if callable(clear_shadow):
                try:
                    clear_shadow()
                except Exception:
                    pass
        self.timeline.center_to_sec(global_sec, smooth=False)

    def _snapshot_timeline_view_for_resize(self) -> dict:
        """자막 세그먼트 리사이즈 전 타임라인 뷰포트 상태 저장."""
        timeline = getattr(self, "timeline", None)
        if timeline is None or not hasattr(timeline, "scroll"):
            return {}
        try:
            sb = timeline.scroll.horizontalScrollBar()
            return {
                "scroll_x": int(sb.value()),
                "target_x": float(getattr(timeline, "_target_scroll_x", sb.value())),
                "current_x": float(getattr(timeline, "_current_scroll_x", sb.value())),
            }
        except Exception:
            return {}

    def _restore_timeline_view_for_resize(self, state: dict) -> None:
        """자막 세그먼트 리사이즈 후 타임라인 위치 복원."""
        if not state:
            return
        timeline = getattr(self, "timeline", None)
        if timeline is None or not hasattr(timeline, "scroll"):
            return
        try:
            sb = timeline.scroll.horizontalScrollBar()
            x = int(state.get("scroll_x", sb.value()))
            if hasattr(timeline, "_clamp_scroll_x"):
                x = int(timeline._clamp_scroll_x(x))
            if hasattr(timeline, "_smooth_scroll_timer") and timeline._smooth_scroll_timer.isActive():
                timeline._smooth_scroll_timer.stop()
            sb.setValue(x)
            timeline._target_scroll_x = float(x)
            timeline._current_scroll_x = float(x)
            if hasattr(timeline, "_schedule_vp_sync"):
                timeline._schedule_vp_sync()
            if hasattr(timeline, "_sync_playhead_overlay"):
                timeline._sync_playhead_overlay()
        except Exception:
            pass

    def _redraw_timeline_preserve_resize_view(self, state: dict) -> None:
        """타임라인 redraw를 수행하되, 리사이즈 전 화면 위치를 유지."""
        self._redraw_timeline()
        self._restore_timeline_view_for_resize(state)
        QTimer.singleShot(0, lambda s=dict(state): self._restore_timeline_view_for_resize(s))
        QTimer.singleShot(80, lambda s=dict(state): self._restore_timeline_view_for_resize(s))
        QTimer.singleShot(240, lambda s=dict(state): self._restore_timeline_view_for_resize(s))

    def _on_seg_time_changed(self, line_num: int, new_start: float, new_end: float, edge_type: str = ""):
        new_start = self._snap_to_frame(new_start)
        new_end = self._snap_to_frame(new_end)
        if new_end <= new_start:
            min_span = max(0.02, min(0.1, 1.0 / max(1.0, self._current_frame_fps())))
            new_end = self._snap_to_frame(new_start + min_span)
        _timeline_resize_view_state = self._snapshot_timeline_view_for_resize()
        timeline = getattr(self, "timeline", None)
        if timeline is not None and hasattr(timeline, "_begin_subtitle_resize_keep_view"):
            timeline._begin_subtitle_resize_keep_view()
        doc = self.text_edit.document()
        cur = QTextCursor(doc)
        prev_sync_lock = bool(getattr(self, "_sync_lock", False))
        self._sync_lock = True
        cur.beginEditBlock()

        block = doc.findBlockByNumber(line_num)
        if not block.isValid():
            cur.endEditBlock()
            self._sync_lock = prev_sync_lock
            return

        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData):
            cur.endEditBlock()
            self._sync_lock = prev_sync_lock
            return

        old_start = float(ud.start_sec)
        old_end = float(ud.end_sec if ud.end_sec is not None else old_start)
        eps = 0.001
        min_span = max(0.02, min(0.1, 1.0 / max(1.0, self._current_frame_fps())))
        trim_previous_subtitles = edge_type in {"square_left", "center"} and new_start < old_start - eps
        trim_next_subtitles = edge_type in {"square_right", "center"} and new_end > old_end + eps
        get_current_segments = getattr(self, "_get_current_segments", None)
        if callable(get_current_segments):
            try:
                current_segments = list(get_current_segments())
            except Exception:
                current_segments = []
        else:
            current_segments = []
        native_timing_plan = None
        if current_segments and edge_type != "diamond":
            native_timing_plan = plan_subtitle_timing_edit_via_swift(
                segments=current_segments,
                line=int(line_num),
                new_start=float(new_start),
                new_end=float(new_end),
                edge=str(edge_type or ""),
                fps=float(self._current_frame_fps()),
            )

        def _sub_indices_for_block(block_ref):
            block_ud = block_ref.userData()
            if not isinstance(block_ud, SubtitleBlockData):
                return []
            return get_sub_block_indices(
                doc,
                block_ref.blockNumber(),
                float(block_ud.start_sec),
            )

        def _delete_block_group(block_ref):
            block_ud = block_ref.userData()
            if not isinstance(block_ud, SubtitleBlockData):
                return
            for idx in reversed(get_sub_block_indices(doc, block_ref.blockNumber(), float(block_ud.start_sec))):
                victim = doc.findBlockByNumber(idx)
                if not victim.isValid():
                    continue
                delete_cursor = QTextCursor(doc)
                start_pos = victim.position()
                next_block = victim.next()
                if next_block.isValid():
                    end_pos = next_block.position()
                else:
                    end_pos = victim.position() + max(0, victim.length() - 1)
                    start_pos = max(0, start_pos - 1)
                delete_cursor.setPosition(start_pos)
                delete_cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
                delete_cursor.removeSelectedText()

        def _set_group_end(block_ref, end_sec: float):
            block_ud = block_ref.userData()
            if not isinstance(block_ud, SubtitleBlockData):
                return
            end_sec = self._snap_to_frame(float(end_sec))
            for idx in get_sub_block_indices(doc, block_ref.blockNumber(), float(block_ud.start_sec)):
                u = doc.findBlockByNumber(idx).userData()
                if isinstance(u, SubtitleBlockData):
                    u.end_sec = end_sec

        def _set_group_start(block_ref, start_sec: float):
            block_ud = block_ref.userData()
            if not isinstance(block_ud, SubtitleBlockData):
                return
            old_group_start = float(block_ud.start_sec)
            start_sec = self._snap_to_frame(float(start_sec))
            for idx in get_sub_block_indices(doc, block_ref.blockNumber(), old_group_start):
                u = doc.findBlockByNumber(idx).userData()
                if isinstance(u, SubtitleBlockData):
                    u.start_sec = start_sec

        def _trim_previous_overwritten_blocks(anchor_block):
            prev = anchor_block.previous()
            while prev.isValid():
                prev_ud = prev.userData()
                if not isinstance(prev_ud, SubtitleBlockData):
                    break
                prev_start = float(prev_ud.start_sec)
                prev_end = float(prev_ud.end_sec if prev_ud.end_sec is not None else prev_start)
                if prev_ud.is_gap:
                    if edge_type == "gap":
                        break
                    if prev_end <= new_start + eps:
                        break
                    before = prev.previous()
                    if new_start <= prev_start + 0.05:
                        _delete_block_group(prev)
                        prev = before
                        continue
                    prev_ud.end_sec = new_start
                    break
                if not trim_previous_subtitles:
                    break
                if prev_end <= new_start + eps:
                    break
                before = prev.previous()
                if new_start <= prev_start + min_span:
                    _delete_block_group(prev)
                    prev = before
                    continue
                _set_group_end(prev, new_start)
                break

        def _trim_next_overwritten_blocks(anchor_block):
            indices = _sub_indices_for_block(anchor_block)
            last_block = doc.findBlockByNumber(indices[-1] if indices else anchor_block.blockNumber())
            nxt = last_block.next()
            while nxt.isValid():
                next_ud = nxt.userData()
                if not isinstance(next_ud, SubtitleBlockData):
                    break
                next_start = float(next_ud.start_sec)
                next_end = float(next_ud.end_sec if next_ud.end_sec is not None else next_start)
                if next_ud.is_gap:
                    if edge_type == "gap":
                        break
                    if next_start >= new_end - eps:
                        break
                    after = nxt.next()
                    if new_end >= next_end - 0.05:
                        _delete_block_group(nxt)
                        nxt = after
                        continue
                    next_ud.start_sec = new_end
                    break
                if not trim_next_subtitles:
                    break
                if next_start >= new_end - eps:
                    break
                after = nxt.next()
                if new_end >= next_end - min_span:
                    _delete_block_group(nxt)
                    nxt = after
                    continue
                _set_group_start(nxt, new_end)
                break

        if isinstance(native_timing_plan, dict) and isinstance(native_timing_plan.get("segments"), list):
            plan_rows = {}
            for item in list(native_timing_plan.get("segments") or []):
                if not isinstance(item, dict):
                    continue
                try:
                    row_line = int(item.get("line"))
                    row_start = self._snap_to_frame(float(item.get("start", 0.0) or 0.0))
                    row_end = self._snap_to_frame(float(item.get("end", row_start) or row_start))
                except Exception:
                    continue
                plan_rows[row_line] = (row_start, row_end)

            deleted_lines: list[int] = []
            for value in list(native_timing_plan.get("deletedLines") or []):
                try:
                    deleted_lines.append(int(value))
                except Exception:
                    continue

            if int(line_num) not in plan_rows:
                plan_rows = {}

            group_indices_by_line: dict[int, list[int]] = {}
            for seg in current_segments:
                try:
                    seg_line = int(seg.get("line"))
                except Exception:
                    continue
                block_ref = doc.findBlockByNumber(seg_line)
                block_ud = block_ref.userData() if block_ref.isValid() else None
                if block_ref.isValid() and isinstance(block_ud, SubtitleBlockData):
                    group_indices_by_line[seg_line] = get_sub_block_indices(
                        doc,
                        block_ref.blockNumber(),
                        float(block_ud.start_sec),
                    )

            for row_line, (row_start, row_end) in plan_rows.items():
                indices = list(group_indices_by_line.get(int(row_line)) or [])
                for idx in indices:
                    u = doc.findBlockByNumber(idx).userData()
                    if isinstance(u, SubtitleBlockData):
                        u.start_sec = row_start
                        u.end_sec = row_end

            if plan_rows:
                for victim_line in sorted(set(deleted_lines), reverse=True):
                    victim_block = doc.findBlockByNumber(int(victim_line))
                    if victim_block.isValid():
                        _delete_block_group(victim_block)
            else:
                sub_indices = get_sub_block_indices(doc, line_num, old_start)
                for idx in sub_indices:
                    u = doc.findBlockByNumber(idx).userData()
                    if isinstance(u, SubtitleBlockData):
                        u.start_sec = new_start
                        u.end_sec = new_end

                _trim_previous_overwritten_blocks(block)
                _trim_next_overwritten_blocks(block)
        else:
            sub_indices = get_sub_block_indices(doc, line_num, old_start)
            for idx in sub_indices:
                u = doc.findBlockByNumber(idx).userData()
                if isinstance(u, SubtitleBlockData):
                    u.start_sec = new_start
                    u.end_sec = new_end

            # ── 앞쪽 Gap 처리 ──
            _trim_previous_overwritten_blocks(block)

            # ── 뒤쪽 Gap 처리 ──
            _trim_next_overwritten_blocks(block)

        if hasattr(self, "_invalidate_segment_cache"):
            self._invalidate_segment_cache()
        prev_suspend_restore = bool(getattr(self, "_suspend_block_user_data_restore", False))
        self._suspend_block_user_data_restore = True
        try:
            self.text_edit.update_margins()
        finally:
            self._suspend_block_user_data_restore = prev_suspend_restore
        cur.endEditBlock()
        self._sync_lock = prev_sync_lock
        cache_rebuilt = False
        if hasattr(self, "_rebuild_subtitle_memory_cache"):
            try:
                self._rebuild_subtitle_memory_cache()
                cache_rebuilt = True
            except Exception:
                cache_rebuilt = False
        if not cache_rebuilt and hasattr(self, "_invalidate_segment_cache"):
            self._invalidate_segment_cache()
        if hasattr(self, "_apply_manual_confirmed_quality_to_line"):
            try:
                self._apply_manual_confirmed_quality_to_line(
                    int(line_num),
                    reason="manual_timing_edit",
                )
            except Exception:
                pass
        snapshot_refresher = getattr(self.text_edit, "_refresh_timestamp_meta_snapshot", None)
        if callable(snapshot_refresher):
            try:
                snapshot_refresher()
            except Exception:
                pass
        if hasattr(self.text_edit, 'timestampArea'):
            self.text_edit.timestampArea.update()
        if hasattr(self, "_mark_dirty"):
            self._mark_dirty()
        QTimer.singleShot(0, lambda s=dict(_timeline_resize_view_state): self._redraw_timeline_preserve_resize_view(s))
        timeline = getattr(self, "timeline", None)
        if timeline is not None and hasattr(timeline, "_finish_subtitle_resize_keep_view"):
            timeline._finish_subtitle_resize_keep_view()

install_scan_cut_patches(EditorTimelineVideoMixin)
