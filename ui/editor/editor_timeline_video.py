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

import os
import time
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QTextCursor

from core.frame_time import normalize_fps, snap_sec_to_frame
from ui.editor.subtitle_text_edit import SubtitleBlockData
from ui.editor.editor_scan_cut_core import EditorScanCutCoreMixin
from ui.editor.editor_helpers import (
    find_segment_at, get_sub_block_indices,
    find_segment_at_lookup,
    build_segment_lookup,
    make_gap_ud, delete_block_safely, insert_gap_after,
)



class EditorTimelineVideoMixin(EditorScanCutCoreMixin):
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
            return max(24, min(80, int(settings.get("playhead_active_interval_ms", 45) or 45)))
        except Exception:
            return 45

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
        max_step = max(0.018, min(0.08, now_mono - float(getattr(self, "_last_playhead_smooth_tick", now_mono) or now_mono) + 0.018))
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


    # ---------------------------------------------------------
    # Common: Cursor ↔ Block Sync
    # ---------------------------------------------------------
    def _sync_cursor_to_seg(self, seg, ensure_visible=True, move_cursor=True, *, sync_playhead=True):
        """커서↔블록 동기화: active/하이라이트 + (옵션) 커서 이동"""
        self._active_seg_start = seg["start"]
        # 재생 중에는 set_active()가 내부 smooth scroll을 유발하므로 canvas만 직접 갱신
        player = getattr(getattr(self, 'video_player', None), 'media_player', None)
        is_playing = bool(player and player.playbackState() == player.PlaybackState.PlayingState)
        if is_playing and hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
            self.timeline.canvas.set_active(seg["start"])
        else:
            self.timeline.set_active(seg["start"])
        if sync_playhead and (not is_playing) and hasattr(self, 'timeline') and hasattr(self.timeline, 'set_playhead'):
            self._reset_playhead_smoothing(seg["start"])
            self.timeline.set_playhead(seg["start"])
        line_num = seg.get("line", 0)
        self._highlighter.set_current_line(line_num)
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
            player_state = None
            try:
                player_state = getattr(getattr(getattr(self, "video_player", None), "media_player", None), "playbackState", lambda: None)()
                playing_state = getattr(getattr(getattr(self, "video_player", None), "media_player", None), "PlaybackState", None)
                playing_state = getattr(playing_state, "PlayingState", None)
            except Exception:
                player_state = None
                playing_state = None
            allow_during_playback = settings.get("background_prefetch_during_playback", False)
            if isinstance(allow_during_playback, str):
                allow_during_playback = allow_during_playback.strip().lower() in {"1", "true", "yes", "on"}
            if playing_state is not None and player_state == playing_state and not bool(allow_during_playback):
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
                segments=[dict(seg) for seg in list(segments or []) if isinstance(seg, dict)],
                settings=settings,
            )
            self._last_background_prefetch_request = result
        except Exception:
            pass

    # ---------------------------------------------------------
    # Timeline Segment Events
    # ---------------------------------------------------------

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
            best = None
            for seg in list(cache.get("segments") or []):
                try:
                    start = self._snap_to_frame(float(seg.get("start", 0.0) or 0.0))
                except Exception:
                    continue
                dist = abs(start - click_sec)
                if dist <= 0.15 and (best is None or dist < best[0]):
                    best = (dist, seg)
            if best is not None:
                time_seg = best[1]

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

    def _on_timeline_seg_clicked(self, line_num, start_sec):
        cache = getattr(self, "_subtitle_memory_cache", None)
        seg = self._segment_for_timeline_click(line_num, start_sec, cache)
        lock_edit = self._timeline_lock_edit_enabled()
        if seg:
            target_sec = float(seg.get("start", start_sec) or start_sec or 0.0)
            line_num = int(seg.get("line", line_num) if seg.get("line") is not None else line_num)
            if lock_edit:
                self._active_seg_start = target_sec
                self.timeline.set_active(target_sec)
                if hasattr(self.timeline, "set_playhead"):
                    self._reset_playhead_smoothing(target_sec)
                    self.timeline.set_playhead(target_sec)
            else:
                self._sync_cursor_to_seg(seg)
            target_end = float(seg.get("end", target_sec) or target_sec)
            target_center = (target_sec + target_end) / 2
            if hasattr(self.timeline, "ensure_sec_visible"):
                self.timeline.ensure_sec_visible(target_center, smooth=True, margin_px=96)
            else:
                self.timeline.center_to_sec(target_center, smooth=True)
            if hasattr(self, '_resolve_active_context') and hasattr(self, '_apply_active_context'):
                ctx = self._resolve_active_context(global_sec=target_sec)
                self._apply_active_context(ctx, autoplay=False, show_thumbnail=True)
            elif hasattr(self, 'video_player'):
                self.video_player.pause_video()
                self.video_player.seek_direct(target_sec)
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
        if hasattr(self.timeline, 'canvas') and hasattr(self.timeline.canvas, 'start_inline_edit'):
            self._undo_mgr.push_immediate()
            self.timeline.canvas.start_inline_edit(line_num, start_sec)

    def _sync_playhead(self):
        if not hasattr(self, 'video_player') or not hasattr(self, 'timeline'):
            return
        player = self.video_player.media_player
        if player.playbackState() != player.PlaybackState.PlayingState:
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
        current_sec = self._snap_to_frame(self._local_to_global_sec(local_sec))
        self._playhead_display_sec = current_sec
        self._playhead_anchor_global_sec = current_sec
        self._playhead_anchor_mono = now_mono
        self._schedule_background_prefetch(current_sec)
        if hasattr(self.timeline, "follow_playhead_centered"):
            self.timeline.follow_playhead_centered(current_sec, smooth=True)
        elif hasattr(self.timeline, "follow_playhead"):
            self.timeline.follow_playhead(current_sec, smooth=True, threshold_px=24.0)
        else:
            self.timeline.set_playhead(current_sec)

        # Context sync: skip resolve if within cached clip bounds (C fix v2)
        if hasattr(self, '_resolve_active_context') and hasattr(self, 'video_player'):
            _mc_boxes = list(getattr(self.timeline.canvas, '_multiclip_boxes', []) or []) if hasattr(self, 'timeline') else []
            if _mc_boxes:
                _cb = getattr(self, '_cached_clip_bounds', None)
                last_ctx_at = float(getattr(self, '_last_play_context_sync_at', 0.0) or 0.0)
                if not (_cb and _cb[0] <= current_sec < _cb[1]) and (now_mono - last_ctx_at) >= 0.25:
                    self._last_play_context_sync_at = now_mono
                    ctx = self._resolve_active_context(global_sec=current_sec)
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

        seg = self._segment_at_playback_sec(current_sec, skip_gap=True)
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
        local_display_sec = self._global_to_local_sec(current_sec)
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
        self._reset_playhead_smoothing(global_sec)
        self.timeline.set_playhead(global_sec)
        self.timeline.center_to_sec(global_sec, smooth=False)



    def _on_step_frame(self, direction):
        if not hasattr(self, 'video_player'):
            return

        try:
            direction = 1 if int(direction) > 0 else -1
        except Exception:
            direction = 1

        try:
            self.video_player.pause_video()
        except Exception:
            pass

        fps = self._current_frame_fps()
        current_global = float(getattr(self.timeline.canvas, 'playhead_sec', 0.0) or 0.0)
        local_frame = max(0, int(round(current_global * fps)))
        target_frame = max(0, local_frame + direction)
        global_sec = self._snap_to_frame(target_frame / fps)
        self._manual_frame_idx = max(0, int(round(global_sec * fps)))

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
        self.timeline.center_to_sec(global_sec, smooth=False)

        print(
            f"🎯 [frame-step] local frame {local_frame}->{target_frame} "
            f"{current_global:.3f}s->{target_local:.3f}s",
            flush=True,
        )
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
        ud.start_sec = new_start

        for idx in get_sub_block_indices(doc, line_num, old_start)[1:]:
            u = doc.findBlockByNumber(idx).userData()
            if isinstance(u, SubtitleBlockData):
                u.start_sec = ud.start_sec

        sub_now = get_sub_block_indices(doc, line_num, ud.start_sec)
        last_idx = sub_now[-1] if sub_now else line_num
        last_block = doc.findBlockByNumber(last_idx)

        # ── 앞쪽 Gap 처리 ──
        prev_block = block.previous()
        if prev_block.isValid():
            prev_ud = prev_block.userData()
            if isinstance(prev_ud, SubtitleBlockData):
                if prev_ud.is_gap:
                    if (
                        abs(float(prev_ud.start_sec) - float(ud.start_sec)) < 0.05
                        or float(new_start) <= float(prev_ud.start_sec) + 0.05
                    ):
                        delete_block_safely(prev_block)
                else:
                    if edge_type not in ("diamond", "gap") and float(new_start) > old_start + 0.05:
                        insert_gap_after(prev_block, old_start)

        # ── 뒤쪽 Gap 처리 ──
        next_block = last_block.next()
        if next_block.isValid():
            next_ud = next_block.userData()
            if isinstance(next_ud, SubtitleBlockData):
                if not next_ud.is_gap:
                    is_same = abs(float(next_ud.start_sec) - float(ud.start_sec)) < 0.05
                    if (not is_same
                            and edge_type not in ("diamond", "gap")
                            and float(new_end) < float(next_ud.start_sec) - 0.05):
                        insert_gap_after(last_block, float(new_end))
                else:
                    next_next = next_block.next()
                    if next_next.isValid():
                        nnu = next_next.userData()
                        if (
                            isinstance(nnu, SubtitleBlockData)
                            and float(new_end) >= float(nnu.start_sec) - 0.05
                        ):
                            delete_block_safely(next_block)
                        else:
                            next_ud.start_sec = new_end
                    else:
                        next_ud.start_sec = new_end

        self.text_edit.update_margins()
        cur.endEditBlock()
        self._sync_lock = prev_sync_lock
        if hasattr(self.text_edit, 'timestampArea'):
            self.text_edit.timestampArea.update()
        QTimer.singleShot(0, lambda s=dict(_timeline_resize_view_state): self._redraw_timeline_preserve_resize_view(s))
        timeline = getattr(self, "timeline", None)
        if timeline is not None and hasattr(timeline, "_finish_subtitle_resize_keep_view"):
            timeline._finish_subtitle_resize_keep_view()

    def _on_seg_to_gap(self, line_num: int):
        """자막 세그먼트 → 무음구간(Gap)으로 변환"""
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
        sub_indices = get_sub_block_indices(doc, line_num, seg_start)

        cur = QTextCursor(doc)
        cur.beginEditBlock()

        # 하위 블록 삭제 (첫 번째만 남김)
        for idx in reversed(sub_indices[1:]):
            delete_block_safely(doc.findBlockByNumber(idx))

        # 첫 블록: 텍스트 제거 + Gap 변환
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

    def _remove_live_detection_for_range(self, start_sec: float, end_sec: float):
        start = float(start_sec)
        end = float(end_sec)
        if end <= start:
            return

        live = list(getattr(self, "_live_stt_preview_segments", []) or [])
        if live:
            self._live_stt_preview_segments = self._trim_segments_outside_range(live, start, end)

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
            except Exception:
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

        if gap_start <= 0.05:
            first_block = doc.begin()
            orig_ud = first_block.userData()
            orig_time = orig_ud.start_sec if isinstance(orig_ud, SubtitleBlockData) else gap_end
            orig_spk = orig_ud.spk_id if isinstance(orig_ud, SubtitleBlockData) else self.settings.get("spk1_id", "00")
            if not first_block.text().strip() or (isinstance(orig_ud, SubtitleBlockData) and orig_ud.is_gap):
                cur.setPosition(first_block.position())
                cur.select(QTextCursor.SelectionType.LineUnderCursor)
                cur.insertText("새 자막")
                first_block.setUserData(SubtitleBlockData(self.settings.get("spk1_id", "00"), 0.0, is_gap=False))
            else:
                cur.movePosition(QTextCursor.MoveOperation.Start)
                cur.insertText("새 자막\n")
                doc.findBlockByNumber(0).setUserData(SubtitleBlockData(self.settings.get("spk1_id", "00"), 0.0, is_gap=False))
                doc.findBlockByNumber(1).setUserData(SubtitleBlockData(orig_spk, orig_time, is_gap=False))
                if orig_time > gap_end + 0.05:
                    cur.setPosition(doc.findBlockByNumber(1).position())
                    cur.insertText("\n")
                    doc.findBlockByNumber(1).setUserData(make_gap_ud(gap_end))
                    doc.findBlockByNumber(2).setUserData(SubtitleBlockData(orig_spk, orig_time, is_gap=False))
        else:
            target_idx = None
            for i in range(doc.blockCount()):
                ud = doc.findBlockByNumber(i).userData()
                if isinstance(ud, SubtitleBlockData) and abs(ud.start_sec - gap_start) < 0.05:
                    target_idx = i
                    break
            if target_idx is not None:
                block = doc.findBlockByNumber(target_idx)
                cur.setPosition(block.position())
                cur.select(QTextCursor.SelectionType.LineUnderCursor)
                cur.insertText("새 자막")
                block.setUserData(SubtitleBlockData(self.settings.get("spk1_id", "00"), gap_start, is_gap=False))
                next_b = block.next()
                if not next_b.isValid() or (isinstance(next_b.userData(), SubtitleBlockData) and next_b.userData().start_sec > gap_end + 0.05):
                    cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                    cur.insertText("\n")
                    cur.block().setUserData(make_gap_ud(gap_end))
            else:
                cur.movePosition(QTextCursor.MoveOperation.End)
                if doc.lastBlock().text().strip():
                    cur.insertText("\n")
                cur.insertText("새 자막")
                cur.block().setUserData(SubtitleBlockData(self.settings.get("spk1_id", "00"), gap_start, is_gap=False))
                cur.insertText("\n")
                cur.block().setUserData(make_gap_ud(gap_end))

        cur.endEditBlock()
        self.text_edit.setTextCursor(cur)
        self._finalize_edit()

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
                for idx, (_, text, _) in enumerate(parts):
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

    def _on_diamond_merge(self, left_line: int, right_line: int):
        """다이아몬드 더블클릭: 좌우 자막 세그먼트 1쌍만 병합"""
        self._undo_mgr.push_immediate()
        doc = self.text_edit.document()

        left_block = doc.findBlockByNumber(left_line)
        right_block = doc.findBlockByNumber(right_line)
        if not left_block.isValid() or not right_block.isValid(): return

        left_ud = left_block.userData()
        right_ud = right_block.userData()
        if not isinstance(left_ud, SubtitleBlockData) or not isinstance(right_ud, SubtitleBlockData): return
        if left_ud.is_gap or right_ud.is_gap: return

        left_last = get_sub_block_indices(doc, left_line, left_ud.start_sec)[-1]
        right_last = get_sub_block_indices(doc, right_line, right_ud.start_sec)[-1]

        right_texts = []
        for i in range(right_line, right_last + 1):
            t = doc.findBlockByNumber(i).text()
            if t.strip(): right_texts.append(t)
        if not right_texts: return

        cur = QTextCursor(doc)
        cur.beginEditBlock()

        left_last_block = doc.findBlockByNumber(left_last)
        right_last_block = doc.findBlockByNumber(right_last)

        cur.setPosition(left_last_block.position())
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        right_end = QTextCursor(right_last_block)
        right_end.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cur.setPosition(right_end.position(), QTextCursor.MoveMode.KeepAnchor)

        cur.insertText(" " + " ".join(right_texts))
        cur.endEditBlock()

        self._mark_dirty()
        self._finalize_edit()

    def _on_smart_split(self, line_num: int, split_sec: float, new_on_left: bool):
        """스마트 자막 분할"""
        self._undo_mgr.push_immediate()
        doc = self.text_edit.document()
        block = doc.findBlockByNumber(int(line_num))
        if not block.isValid(): return

        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or ud.is_gap: return

        seg_start = float(ud.start_sec)
        spk_id = ud.spk_id
        seg_start = self._snap_to_frame(seg_start)
        split_sec = self._snap_to_frame(split_sec)
        if split_sec <= seg_start + 0.05: return

        sub_indices = get_sub_block_indices(doc, block.blockNumber(), seg_start)
        full_lines = [doc.findBlockByNumber(idx).text() for idx in sub_indices]
        original_text = "\u2028".join(full_lines)

        cur = QTextCursor(doc)
        cur.beginEditBlock()

        for idx in reversed(sub_indices[1:]):
            b = doc.findBlockByNumber(idx)
            c = QTextCursor(b)
            c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            c.removeSelectedText()
            if doc.blockCount() > 1: c.deletePreviousChar()

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
        if hasattr(self, 'timeline'):
            self.timeline.set_active(self._active_seg_start)
            self.timeline.center_to_sec(split_sec, smooth=True)
        self._sync_lock = False

        self._mark_dirty()
        self._finalize_edit()

from ui.editor.timeline_scan_cut_patches import install_scan_cut_patches

install_scan_cut_patches(EditorTimelineVideoMixin)
