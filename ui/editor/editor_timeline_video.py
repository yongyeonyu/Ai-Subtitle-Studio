# Version: 03.10.02
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
import json
import time
from datetime import datetime
import subprocess
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication

from core.frame_time import normalize_fps, snap_sec_to_frame
from core.cut_boundary import sync_project_cut_boundaries
from ui.editor.subtitle_text_edit import SubtitleBlockData
from ui.editor.editor_helpers import (
    find_segment_at, get_sub_block_indices,
    make_gap_ud, delete_block_safely, insert_gap_after,
    merge_adjacent_gaps_around
)



class EditorTimelineVideoMixin:
    """타임라인/비디오 동기화 / 화자 관리 / 단축키 액션"""

    def _timeline_lock_edit_enabled(self) -> bool:
        lock_box = getattr(getattr(self, "timeline", None), "lock_chk", None)
        try:
            return bool(lock_box is not None and lock_box.isChecked())
        except RuntimeError:
            return False

    def _current_frame_fps(self) -> float:
        return normalize_fps(getattr(self, "video_fps", 30.0) or 30.0)

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
    def _sync_cursor_to_seg(self, seg, ensure_visible=True, move_cursor=True):
        """커서↔블록 동기화: active/하이라이트 + (옵션) 커서 이동"""
        self._active_seg_start = seg["start"]
        # 재생 중에는 set_active()가 내부 smooth scroll을 유발하므로 canvas만 직접 갱신
        player = getattr(getattr(self, 'video_player', None), 'media_player', None)
        is_playing = bool(player and player.playbackState() == player.PlaybackState.PlayingState)
        if is_playing and hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
            self.timeline.canvas.set_active(seg["start"])
        else:
            self.timeline.set_active(seg["start"])
        if (not is_playing) and hasattr(self, 'timeline') and hasattr(self.timeline, 'set_playhead'):
            self._reset_playhead_smoothing(seg["start"])
            self.timeline.set_playhead(seg["start"])
        line_num = seg.get("line", 0)
        self._highlighter.set_current_line(line_num)
        if not move_cursor:
            return
        block = self.text_edit.document().findBlockByNumber(line_num)
        if block.isValid():
            self._sync_lock = True
            cur = QTextCursor(block)
            self.text_edit.setTextCursor(cur)
            if ensure_visible:
                self.text_edit.ensureCursorVisible()
            self._sync_lock = False

    # ---------------------------------------------------------
    # Timeline Segment Events
    # ---------------------------------------------------------

    def _on_timeline_seg_clicked(self, line_num, start_sec):
        segs = self._get_current_segments()
        seg = next((s for s in segs if s["line"] == line_num), None)
        lock_edit = self._timeline_lock_edit_enabled()
        if seg:
            if lock_edit:
                self._active_seg_start = seg["start"]
                self.timeline.set_active(seg["start"])
                if hasattr(self.timeline, "set_playhead"):
                    self._reset_playhead_smoothing(seg["start"])
                    self.timeline.set_playhead(seg["start"])
            else:
                self._sync_cursor_to_seg(seg)
            self.timeline.center_to_sec((seg["start"] + seg["end"]) / 2, smooth=True)
            if hasattr(self, '_resolve_active_context') and hasattr(self, '_apply_active_context'):
                ctx = self._resolve_active_context(global_sec=float(start_sec))
                self._apply_active_context(ctx, autoplay=False, show_thumbnail=True)
            elif hasattr(self, 'video_player'):
                self.video_player.pause_video()
                self.video_player.seek_direct(float(start_sec))
        if lock_edit:
            if hasattr(self.timeline, "canvas"):
                self.timeline.canvas.setFocus()
        else:
            self.text_edit.setFocus()


    def _on_timeline_seg_double_clicked(self, line_num, start_sec):
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
            if hasattr(self.timeline, "set_playback_center_lock"):
                self.timeline.set_playback_center_lock(False)
            self._reset_playhead_smoothing(getattr(self.timeline.canvas, "playhead_sec", 0.0))
            return
        pos_ms = player.position()
        dur_ms = player.duration()
        if dur_ms <= 0:
            return

        now_mono = time.monotonic()
        local_sec = self._current_video_local_frame_sec(player)
        current_sec = self._snap_to_frame(self._local_to_global_sec(local_sec))
        self._playhead_display_sec = current_sec
        self._playhead_anchor_global_sec = current_sec
        self._playhead_anchor_mono = now_mono
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
                        self.video_player.set_context_segments(list(ctx.get('local_segments', []) or []))

        segs = getattr(self, '_cached_segs', None) or self._get_current_segments()
        seg = find_segment_at(segs, current_sec, skip_gap=True)
        if seg and self._active_seg_start != seg["start"]:
            editing_active = bool(getattr(self.timeline.canvas, '_edit_active', False)) if hasattr(self.timeline, 'canvas') else False
            can_move_editor = (not self.text_edit.hasFocus()) and (not editing_active)
            if can_move_editor:
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
            editing_active = bool(getattr(self.timeline.canvas, '_edit_active', False)) if hasattr(self.timeline, 'canvas') else False
            if (not self.text_edit.hasFocus()) and (not editing_active) and (now_mono - last_scroll_at) >= 0.25:
                self._last_editor_autoscroll_at = now_mono
                self._sync_cursor_to_seg(seg, ensure_visible=True, move_cursor=True)
        local_display_sec = self._global_to_local_sec(current_sec)
        if hasattr(self.video_player, 'set_subtitle_display_time'):
            self.video_player.set_subtitle_display_time(local_display_sec)
        elif hasattr(self.video_player, 'refresh_subtitle_context'):
            self.video_player.refresh_subtitle_context()



    def _on_scrub(self, sec):
        if hasattr(self, "_scan_should_block_user_timeline_input") and self._scan_should_block_user_timeline_input():
            try:
                self.video_player.info_label.setText("컷 경계 탐색 중에는 타임라인 입력이 잠깁니다.")
            except Exception:
                pass
            return

        sec = self._snap_to_frame(sec)
        self._reset_playhead_smoothing(sec)
        self.timeline.set_playhead(sec)
        if hasattr(self, '_resolve_active_context') and hasattr(self, '_apply_active_context'):
            ctx = self._resolve_active_context(global_sec=sec)
            self._apply_active_context(ctx, autoplay=False, show_thumbnail=True)
        elif hasattr(self, 'video_player'):
            self.video_player.pause_video()
            self.video_player.seek_direct(sec)
        segs = getattr(self, '_cached_segs', None) or self._get_current_segments()
        seg = find_segment_at(segs, sec, skip_gap=False)
        if seg and self._active_seg_start != seg["start"]:
            self._sync_cursor_to_seg(seg)
            self.timeline.center_to_sec(sec, smooth=True)

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
            self._sync_cursor_to_seg(seg)
        self._reset_playhead_smoothing(global_sec)
        self.timeline.set_playhead(global_sec)
        self.timeline.center_to_sec(global_sec, smooth=False)



    def _scan_capture_image(self) -> bytes | None:
        """기존 호출부 호환용. 현재 위치 프레임을 OpenCV로 직접 읽는다."""
        try:
            sec = self._manual_global_sec_from_player()
        except Exception:
            try:
                sec = float(getattr(getattr(self, "timeline", None).canvas, "playhead_sec", 0.0) or 0.0)
            except Exception:
                sec = 0.0
        return self._scan_capture_image_at_global(sec)



    def _scan_image_delta(self, prev_image, next_image) -> float:
        deltas = self._scan_region_deltas(prev_image, next_image)
        if not deltas:
            self._scan_last_region_deltas = []
            self._scan_last_region_hits = 0
            return 0.0

        region_threshold = self._scan_region_threshold()
        hits = sum(1 for d in deltas if d >= region_threshold)
        self._scan_last_region_deltas = list(deltas)
        self._scan_last_region_hits = int(hits)

        ranked = sorted(deltas, reverse=True)
        top_n = ranked[: min(3, len(ranked))]
        return sum(top_n) / float(len(top_n) or 1)

    def _scan_get_cv2_module(self):
        """scan-cut 전용 OpenCV lazy import."""
        cv2_mod = getattr(self, "_scan_cv2_mod", None)
        if cv2_mod and cv2_mod is not False:
            return cv2_mod
        if cv2_mod is False:
            return None
        try:
            cv2_mod = __import__("cv2")
            self._scan_cv2_mod = cv2_mod
            return cv2_mod
        except Exception as exc:
            self._scan_cv2_mod = False
            print(f"⚠️ [scan-cut] OpenCV 사용 불가: {exc}", flush=True)
            return None

    def _scan_get_context_for_global_sec(self, global_sec: float) -> dict:
        """global sec 기준 멀티클립 context 확인."""
        if hasattr(self, "_resolve_active_context"):
            try:
                ctx = self._resolve_active_context(global_sec=float(global_sec))
                if isinstance(ctx, dict):
                    return ctx
            except Exception:
                pass
        return {"global_sec": float(global_sec), "local_sec": float(global_sec)}

    def _scan_source_and_local_sec(self, global_sec: float):
        """global sec에서 source path / local sec 추출."""
        ctx = self._scan_get_context_for_global_sec(global_sec)
        source = str(ctx.get("clip_file", "") or ctx.get("source_path", "") or "")
        if not source:
            vp = getattr(self, "video_player", None)
            source = str(getattr(vp, "_current_source_path", "") or "")

        try:
            local_sec = float(ctx.get("local_sec", global_sec) or global_sec)
        except Exception:
            local_sec = float(global_sec)

        return source, max(0.0, local_sec), ctx

    def _scan_get_cv2_capture(self, source_path: str):
        """같은 영상 파일은 VideoCapture를 계속 재사용한다."""
        if not source_path or not os.path.exists(source_path):
            return None

        cv2_mod = self._scan_get_cv2_module()
        if not cv2_mod:
            return None

        try:
            norm_path = os.path.normpath(str(source_path))
        except Exception:
            norm_path = str(source_path)

        cap = getattr(self, "_scan_cv2_capture", None)
        current_path = getattr(self, "_scan_cv2_source_path", None)

        if cap is not None and current_path == norm_path:
            try:
                if cap.isOpened():
                    return cap
            except Exception:
                pass

        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass

        try:
            cap = cv2_mod.VideoCapture(norm_path)
            if not cap or not cap.isOpened():
                print(f"⚠️ [scan-cut] VideoCapture open 실패: {norm_path}", flush=True)
                return None
            self._scan_cv2_capture = cap
            self._scan_cv2_source_path = norm_path
            self._scan_cv2_last_frame_idx = None
            return cap
        except Exception as exc:
            print(f"⚠️ [scan-cut] VideoCapture 예외: {exc}", flush=True)
            return None


    def _scan_image_backend_label(self) -> str:
        return "opencv-gray-cross"

    def _scan_frames_per_tick(self) -> int:
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_FRAMES_PER_TICK", settings.get("scan_cut_frames_per_tick", 16))
        try:
            return max(1, min(120, int(raw)))
        except Exception:
            return 16

    def _scan_preview_every_frames(self) -> int:
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_PREVIEW_EVERY_FRAMES", settings.get("scan_cut_preview_every_frames", 12))
        try:
            return max(1, min(240, int(raw)))
        except Exception:
            return 12

    def _scan_region_threshold(self) -> float:
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_REGION_THRESHOLD", settings.get("scan_cut_region_threshold", 18.0))
        try:
            return max(1.0, float(raw))
        except Exception:
            return 18.0

    def _scan_cross_regions_required(self) -> int:
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_CROSS_REGIONS_REQUIRED", settings.get("scan_cut_cross_regions_required", 3))
        try:
            return max(1, min(5, int(raw)))
        except Exception:
            return 3

    def _scan_cut_is_running(self) -> bool:
        return bool(getattr(self, "_scan_cut_state", None) or getattr(self, "_auto_cut_boundary_scan_active", False))

    def _scan_should_block_user_timeline_input(self) -> bool:
        return self._scan_cut_is_running()

    def _scan_set_timeline_input_locked(self, locked: bool) -> None:
        try:
            timeline = getattr(self, "timeline", None)
            canvas = getattr(timeline, "canvas", None)
            if canvas is not None:
                canvas._scan_cut_input_locked = bool(locked)
                canvas.setProperty("scan_cut_input_locked", bool(locked))
        except Exception:
            pass

    def _set_auto_cut_boundary_scan_active(self, active: bool) -> None:
        self._auto_cut_boundary_scan_active = bool(active)
        self._scan_set_timeline_input_locked(bool(active))
        try:
            if hasattr(self, "timeline") and hasattr(self.timeline, "set_playback_center_lock"):
                self.timeline.set_playback_center_lock(False)
        except Exception:
            pass
        if not active:
            try:
                vp = getattr(self, "video_player", None)
                if vp is not None and hasattr(vp, "info_label"):
                    vp.info_label.setText("")
            except Exception:
                pass

    def _set_auto_cut_boundary_scan_lines(self, times) -> None:
        cleaned = []
        for item in list(times or []):
            try:
                sec = self._snap_to_frame(float(item or 0.0))
            except Exception:
                continue
            if sec > 0.0:
                cleaned.append(sec)
        try:
            cleaned = sorted({round(float(sec), 6) for sec in cleaned})
        except Exception:
            cleaned = list(cleaned)
        self._auto_cut_boundary_scan_lines = list(cleaned)
        timeline = getattr(self, "timeline", None)
        if timeline is None or not hasattr(timeline, "set_scan_boundary_times"):
            return
        timeline.set_scan_boundary_times(list(cleaned))
        try:
            if hasattr(timeline, "canvas"):
                timeline.canvas.update()
            timeline.update()
        except Exception:
            pass

    def _preview_auto_cut_boundary_scan(self, current_sec: float, next_sec: float = 0.0) -> None:
        self._set_auto_cut_boundary_scan_active(True)
        self._scan_preview_global_sec(float(current_sec or 0.0))
        try:
            source_path, _, _ctx = self._scan_source_and_local_sec(float(next_sec or current_sec or 0.0))
            vp = getattr(self, "video_player", None)
            if vp is not None and source_path and hasattr(vp, "prefetch_thumbnail_at"):
                target_sec = float(next_sec or current_sec or 0.0)
                try:
                    local_sec = float((_ctx or {}).get("local_sec", target_sec) or target_sec)
                except Exception:
                    local_sec = target_sec
                vp.prefetch_thumbnail_at(source_path, local_sec, width=self._scan_preview_thumbnail_size()[0])
        except Exception:
            pass


    def _scan_fast_thumbnail_enabled(self) -> bool:
        """
        scan-cut 진행 중 비디오 플레이어 seek 대신 OpenCV 썸네일을 빠르게 표시할지 여부.
        """
        settings = getattr(self, "settings", {}) or {}
        raw = settings.get("scan_cut_preview_thumbnail_enabled", True)
        try:
            if isinstance(raw, str):
                return raw.strip().lower() not in ("0", "false", "no", "off")
            return bool(raw)
        except Exception:
            return True

    def _scan_preview_thumbnail_size(self) -> tuple[int, int]:
        """
        scan-cut preview thumbnail 최대 크기.
        너무 크게 뽑으면 느려지므로 기본 640x360.
        """
        settings = getattr(self, "settings", {}) or {}
        try:
            w = int(settings.get("scan_cut_preview_thumbnail_width", 640))
            h = int(settings.get("scan_cut_preview_thumbnail_height", 360))
        except Exception:
            w, h = 640, 360
        return max(160, min(w, 1280)), max(90, min(h, 720))

    def _scan_extract_preview_pixmap_at_global(self, global_sec: float):
        """
        OpenCV로 global_sec 위치의 프레임을 빠르게 읽어 QPixmap으로 변환한다.

        목적:
        - 컷 탐색 중 QMediaPlayer seek 비용을 줄인다.
        - 탐색 위치를 비디오 화면에 썸네일처럼 빠르게 표시한다.
        """
        try:
            from PyQt6.QtGui import QImage, QPixmap
            from PyQt6.QtCore import Qt
        except Exception:
            return None

        cv2_mod = self._scan_get_cv2_module() if hasattr(self, "_scan_get_cv2_module") else None
        if not cv2_mod:
            return None

        try:
            source_path, local_sec, _ctx = self._scan_source_and_local_sec(float(global_sec))
        except Exception:
            return None

        if not source_path:
            return None

        cap = self._scan_get_cv2_capture(source_path) if hasattr(self, "_scan_get_cv2_capture") else None
        if cap is None:
            return None

        try:
            fps = float(cap.get(cv2_mod.CAP_PROP_FPS) or 0.0)
        except Exception:
            fps = 0.0

        if fps <= 1.0:
            fps = self._current_frame_fps()

        frame_idx = max(0, int(round(float(local_sec) * fps)))

        try:
            current_pos = int(cap.get(cv2_mod.CAP_PROP_POS_FRAMES) or 0)
            if current_pos != frame_idx:
                cap.set(cv2_mod.CAP_PROP_POS_FRAMES, frame_idx)

            ok, frame = cap.read()
            if not ok or frame is None:
                return None

            max_w, max_h = self._scan_preview_thumbnail_size()
            h, w = frame.shape[:2]
            if w <= 0 or h <= 0:
                return None

            scale = min(max_w / float(w), max_h / float(h), 1.0)
            if scale < 1.0:
                nw = max(1, int(w * scale))
                nh = max(1, int(h * scale))
                frame = cv2_mod.resize(frame, (nw, nh), interpolation=cv2_mod.INTER_AREA)

            rgb = cv2_mod.cvtColor(frame, cv2_mod.COLOR_BGR2RGB)
            hh, ww = rgb.shape[:2]
            bytes_per_line = int(rgb.strides[0])
            qimg = QImage(rgb.data, ww, hh, bytes_per_line, QImage.Format.Format_RGB888).copy()
            return QPixmap.fromImage(qimg)
        except Exception:
            return None

    def _scan_show_fast_thumbnail_at_global(self, global_sec: float) -> bool:
        """
        scan-cut 진행 중 OpenCV 썸네일을 비디오 화면에 즉시 표시한다.
        성공하면 True.
        """
        if not self._scan_fast_thumbnail_enabled():
            return False

        pixmap = self._scan_extract_preview_pixmap_at_global(global_sec)
        if pixmap is None or pixmap.isNull():
            return False

        vp = getattr(self, "video_player", None)
        if vp is None:
            return False

        try:
            if hasattr(vp, "thumb_label"):
                vp.thumb_label.set_pixmap(pixmap)
            if hasattr(vp, "video_stack") and hasattr(vp, "thumb_label"):
                vp.video_stack.setCurrentWidget(vp.thumb_label)

            try:
                source_path, local_sec, ctx = self._scan_source_and_local_sec(float(global_sec))
            except Exception:
                source_path, local_sec, ctx = "", float(global_sec), {}
            try:
                vp.current_time = float(local_sec)
                clip_total = float((ctx or {}).get("duration", 0.0) or 0.0)
                if clip_total > 0.0:
                    vp.total_time = clip_total
                if hasattr(vp, "_last_time_label_ms"):
                    vp._last_time_label_ms = -250
                if hasattr(vp, "_ui_tick"):
                    vp._ui_tick()
            except Exception:
                pass

            try:
                if hasattr(vp, "set_subtitle_display_time"):
                    # global/local 차이가 있어도 preview 표시용이므로 실패해도 무시
                    vp.set_subtitle_display_time(float(global_sec), refresh=True)
            except Exception:
                pass

            try:
                if hasattr(vp, "info_label"):
                    vp.info_label.setText(f"컷 경계 탐색 중 · {float(global_sec):.3f}s")
            except Exception:
                pass

            return True
        except Exception:
            return False


    def _scan_preview_global_sec(self, global_sec: float) -> None:
        """
        scan-cut 진행 중 preview.

        변경점:
        - 플레이헤드는 계속 움직인다.
        - 비디오 화면은 QMediaPlayer seek보다 빠른 OpenCV 썸네일 표시를 우선한다.
        - 썸네일 표시 실패 시에만 기존 비디오 seek 방식으로 fallback한다.
        """
        try:
            global_sec = self._snap_to_frame(float(global_sec))
        except Exception:
            return

        # 1) 플레이헤드 이동
        try:
            self._reset_playhead_smoothing(global_sec)
        except Exception:
            pass

        try:
            if hasattr(self, "timeline"):
                self.timeline.set_playback_center_lock(False)
                self.timeline.set_playhead(global_sec)
        except Exception:
            pass

        # 2) 캐시 썸네일 우선: 같은 시점을 반복 방문해도 ffmpeg/OpenCV 비용이 덜 든다.
        try:
            source_path, local_sec, _ctx = self._scan_source_and_local_sec(global_sec)
            vp = getattr(self, "video_player", None)
            if vp is not None and source_path and hasattr(vp, "show_cached_thumbnail_at"):
                if vp.show_cached_thumbnail_at(source_path, local_sec, width=self._scan_preview_thumbnail_size()[0]):
                    if hasattr(vp, "info_label"):
                        vp.info_label.setText(f"컷 경계 탐색 중 · {float(global_sec):.3f}s")
                    try:
                        if hasattr(vp, "_last_time_label_ms"):
                            vp._last_time_label_ms = -250
                        vp.current_time = float(local_sec)
                        clip_total = float((_ctx or {}).get("duration", 0.0) or 0.0)
                        if clip_total > 0.0:
                            vp.total_time = clip_total
                        vp._ui_tick()
                    except Exception:
                        pass
                    return
        except Exception:
            pass

        # 3) 제일 빠른 실시간 경로: OpenCV 썸네일을 video 화면에 표시
        try:
            if self._scan_show_fast_thumbnail_at_global(global_sec):
                return
        except Exception:
            pass

        # 4) fallback: 기존 비디오 플레이어 seek
        try:
            if hasattr(self, "_resolve_active_context"):
                ctx = self._resolve_active_context(global_sec=global_sec)
                if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
                    try:
                        self.timeline.canvas._active_clip_idx = int(ctx.get("clip_idx", 0) or 0)
                    except Exception:
                        pass
                local_sec = float(ctx.get("local_sec", global_sec) or 0.0)
                if hasattr(self, "video_player"):
                    if hasattr(self.video_player, "pause_video"):
                        self.video_player.pause_video()
                    if hasattr(self.video_player, "frame_step_seek"):
                        self.video_player.frame_step_seek(local_sec)
                    elif hasattr(self.video_player, "seek_direct"):
                        self.video_player.seek_direct(local_sec)
            elif hasattr(self, "video_player"):
                if hasattr(self.video_player, "pause_video"):
                    self.video_player.pause_video()
                if hasattr(self.video_player, "frame_step_seek"):
                    self.video_player.frame_step_seek(global_sec)
                elif hasattr(self.video_player, "seek_direct"):
                    self.video_player.seek_direct(global_sec)
        except Exception:
            pass

        try:
            if hasattr(self, "_sync_after_manual_seek"):
                self._sync_after_manual_seek(global_sec)
        except Exception:
            pass

    def _scan_make_cross_region_thumbnails(self, frame, cv2_mod, scale_w: int, scale_h: int):
        try:
            h, w = frame.shape[:2]
        except Exception:
            return None
        if w <= 0 or h <= 0:
            return None

        xs = [0, int(w / 3), int(w * 2 / 3), w]
        ys = [0, int(h / 3), int(h * 2 / 3), h]

        cells = [
            (1, 0),  # top center
            (0, 1),  # mid left
            (1, 1),  # center
            (2, 1),  # mid right
            (1, 2),  # bottom center
        ]

        result = []
        for cx, cy in cells:
            roi = frame[ys[cy]:ys[cy + 1], xs[cx]:xs[cx + 1]]
            if roi is None or roi.size == 0:
                return None
            gray = cv2_mod.cvtColor(roi, cv2_mod.COLOR_BGR2GRAY)
            small = cv2_mod.resize(gray, (int(scale_w), int(scale_h)), interpolation=cv2_mod.INTER_AREA)
            result.append(small.tobytes())
        return tuple(result)

    def _scan_delta_bytes(self, a: bytes, b: bytes) -> float:
        if not a or not b:
            return 0.0
        n = min(len(a), len(b))
        if n <= 0:
            return 0.0
        settings = getattr(self, "settings", {}) or {}
        try:
            target_samples = int(settings.get("scan_cut_target_samples", 64))
        except Exception:
            target_samples = 64
        target_samples = max(16, min(256, target_samples))
        step = max(1, n // target_samples)
        total = 0
        count = 0
        for i in range(0, n, step):
            total += abs(a[i] - b[i])
            count += 1
        return total / float(count or 1)

    def _scan_region_deltas(self, prev_image, next_image):
        if not prev_image or not next_image:
            return []
        if isinstance(prev_image, (tuple, list)) and isinstance(next_image, (tuple, list)):
            n = min(len(prev_image), len(next_image))
            return [self._scan_delta_bytes(prev_image[i], next_image[i]) for i in range(n)]
        return [self._scan_delta_bytes(prev_image, next_image)]



    def _scan_capture_image_at_global(self, global_sec: float):
        cv2_mod = self._scan_get_cv2_module()
        if not cv2_mod:
            return None

        source_path, local_sec, _ctx = self._scan_source_and_local_sec(global_sec)
        if not source_path:
            return None

        cap = self._scan_get_cv2_capture(source_path)
        if cap is None:
            return None

        settings = getattr(self, "settings", {}) or {}
        try:
            scale_w = int(settings.get("scan_cut_sample_width", 18))
            scale_h = int(settings.get("scan_cut_sample_height", 10))
        except Exception:
            scale_w, scale_h = 18, 10

        scale_w = max(8, min(scale_w, 48))
        scale_h = max(6, min(scale_h, 27))

        try:
            source_fps = float(cap.get(cv2_mod.CAP_PROP_FPS) or 0.0)
        except Exception:
            source_fps = 0.0
        if source_fps <= 1.0:
            source_fps = self._current_frame_fps()

        frame_idx = max(0, int(round(float(local_sec) * source_fps)))

        try:
            current_pos = int(cap.get(cv2_mod.CAP_PROP_POS_FRAMES) or 0)
            if current_pos != frame_idx:
                cap.set(cv2_mod.CAP_PROP_POS_FRAMES, frame_idx)

            ok, frame = cap.read()
            if not ok or frame is None:
                return None

            h, w = frame.shape[:2]
            if w <= 0 or h <= 0:
                return None

            if not bool(getattr(self, "_scan_logged_capture_resolution", False)):
                self._scan_logged_capture_resolution = True
                print(
                    f"🔎 [scan-cut] source_resolution={w}x{h} "
                    f"sample_region=3x3-cross sample_each={scale_w}x{scale_h} mode=cross9",
                    flush=True,
                )

            return self._scan_make_cross_region_thumbnails(frame, cv2_mod, scale_w, scale_h)
        except Exception:
            return None


    def _scan_hard_threshold(self) -> float:
        """
        즉시 컷으로 판단할 hard threshold.
        이 값 이상이면 연속 hit 없이 바로 컷으로 본다.
        """
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_HARD_THRESHOLD", settings.get("scan_cut_hard_threshold", 45.0))
        try:
            return max(1.0, float(raw))
        except Exception:
            return 45.0


    def _scan_consecutive_hits_required(self) -> int:
        """
        작은 움직임 한 번으로 멈추지 않게 하기 위한 연속 hit 필요 개수.
        """
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_CONSECUTIVE_HITS", settings.get("scan_cut_consecutive_hits", 2))
        try:
            return max(1, int(raw))
        except Exception:
            return 2


    def _scan_threshold(self) -> float:
        """
        scan-cut 픽셀 변화량 threshold.

        기존 8.0은 너무 낮아서 조명 변화/움직임에도 멈출 수 있다.
        기본값을 24.0으로 올려서 확실한 컷에서만 멈추게 한다.
        환경변수 AI_SUBTITLE_SCAN_CUT_THRESHOLD 또는 settings["scan_cut_threshold"]로 조정 가능.
        """
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_THRESHOLD", settings.get("scan_cut_threshold", 24.0))
        try:
            return max(1.0, float(raw))
        except Exception:
            return 24.0

    def _scan_interval_ms(self) -> int:
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_INTERVAL_MS", settings.get("scan_cut_interval_ms", 1))
        try:
            return max(1, int(raw))
        except Exception:
            return 1


    def _scan_max_frames(self) -> int:
        """
        scan-cut 최대 탐색 프레임 수.

        0이면 제한 없음.
        기존 기본값 1800은 60fps에서 약 30초라 긴 컷 탐색에 너무 짧다.
        """
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_MAX_FRAMES", settings.get("scan_cut_max_frames", 0))
        try:
            return max(0, int(raw))
        except Exception:
            return 0

    def _set_scan_cut_button_active(self, direction: int):
        try:
            video_player = getattr(self, "video_player", None)
            if video_player is not None and hasattr(video_player, "set_scan_cut_active"):
                video_player.set_scan_cut_active(direction)
        except Exception:
            pass

    def _cancel_scan_cut(self, reason: str = "cancelled", *, update_label: bool = True):
        try:
            if hasattr(self, "_scan_cut_timer"):
                self._scan_cut_timer.stop()
        except Exception:
            pass

        self._scan_cut_state = None
        self._set_scan_cut_button_active(0)

        if update_label:
            try:
                self.video_player.info_label.setText("컷 경계 탐색 취소")
            except Exception:
                pass

        print(f"🟢 [scan-cut] CANCEL reason={reason}", flush=True)



    def _on_scan_cut_requested(self, direction: int):
        try:
            scan_enabled = bool((getattr(self, "settings", {}) or {}).get(
                "cut_boundary_detection_enabled",
                (getattr(self, "settings", {}) or {}).get("scan_cut_enabled", True),
            ))
        except Exception:
            scan_enabled = True

        if not scan_enabled:
            try:
                self.video_player.info_label.setText("컷 경계 탐색 미사용")
            except Exception:
                pass
            print("⏭️ [scan-cut] SKIP disabled by cut_boundary_detection_enabled=False", flush=True)
            return

        if not hasattr(self, "video_player"):
            print("🎬 [scan-cut] video_player 없음", flush=True)
            return

        try:
            direction = 1 if int(direction) > 0 else -1
        except Exception:
            direction = 1

        current_state = getattr(self, "_scan_cut_state", None)
        if current_state:
            active_dir = int(current_state.get("direction", 0) or 0)
            if active_dir == direction:
                self._cancel_scan_cut("same-button-toggle")
                return
            self._cancel_scan_cut("switch-direction", update_label=False)

        if hasattr(self.video_player, "pause_video"):
            self.video_player.pause_video()

        fps = self._current_frame_fps()
        start_sec = self._manual_global_sec_from_player()
        start_frame = max(0, int(round(start_sec * fps)))
        threshold = self._scan_threshold()
        interval = self._scan_interval_ms()
        max_frames = self._scan_max_frames()
        start_image = self._scan_capture_image_at_global(start_sec)

        print(
            f"🎬 [scan-cut] START dir={direction} start_frame={start_frame} "
            f"start={start_frame / fps:.3f}s fps={fps:.3f} threshold={threshold:.2f} "
            f"interval={interval}ms max_frames={max_frames} "
            f"image={self._scan_image_backend_label() if start_image is not None else 'NONE'}",
            flush=True,
        )

        if start_image is None:
            try:
                self.video_player.info_label.setText("컷 경계 탐색 실패 · 프레임 없음")
            except Exception:
                pass
            return

        self._scan_cut_state = {
            "direction": direction,
            "last_frame": start_frame,
            "last_image": start_image,
            "frames": 0,
            "threshold": threshold,
            "hard_threshold": self._scan_hard_threshold(),
            "consecutive_hits_required": self._scan_consecutive_hits_required(),
            "consecutive_hits": 0,
            "first_hit_frame": None,
            "first_hit_sec": None,
            "max_frames": max_frames,
            "busy": False,
        }

        if not hasattr(self, "_scan_cut_timer"):
            self._scan_cut_timer = QTimer(self)
            self._scan_cut_timer.timeout.connect(self._scan_cut_tick)

        try:
            self.video_player.info_label.setText("컷 경계 탐색 중...")
        except Exception:
            pass

        self._scan_set_timeline_input_locked(True)
        self._set_scan_cut_button_active(direction)
        self._scan_cut_timer.stop()
        self._scan_cut_timer.setInterval(interval)
        self._scan_cut_timer.start()




    def _scan_show_cut_thumbnail(self, global_sec: float) -> None:
        """
        컷 경계 확정 후 해당 컷 직전 프레임을 비디오 화면에 썸네일로 고정 표시한다.
        """
        try:
            global_sec = self._snap_to_frame(float(global_sec))
        except Exception:
            return

        try:
            if self._scan_show_fast_thumbnail_at_global(global_sec):
                print(f"🖼️ [scan-cut] thumbnail shown fast global={global_sec:.3f}s", flush=True)
                return
        except Exception:
            pass

        # fallback
        try:
            self._scan_preview_global_sec(global_sec)
        except Exception:
            pass


    def _project_file_for_cut_boundary_save(self) -> str:
        """
        현재 에디터가 연결된 프로젝트 JSON 경로를 최대한 안전하게 찾는다.
        프로젝트가 없으면 빈 문자열을 반환한다.
        """
        candidates = [
            "project_file",
            "project_path",
            "_project_file",
            "_project_path",
            "current_project_file",
            "current_project_path",
        ]

        for obj in (self, self.window() if hasattr(self, "window") else None):
            if obj is None:
                continue
            for attr in candidates:
                try:
                    value = str(getattr(obj, attr, "") or "")
                except Exception:
                    value = ""
                if value and value.endswith(".json") and os.path.exists(value):
                    return value

        try:
            state = getattr(self, "project_state", None) or getattr(self, "_project_state", None)
            if isinstance(state, dict):
                for key in ("path", "project_file", "project_path"):
                    value = str(state.get(key, "") or "")
                    if value and value.endswith(".json") and os.path.exists(value):
                        return value
        except Exception:
            pass

        return ""

    def _scan_cut_source_context(self, global_sec: float) -> dict:
        try:
            if hasattr(self, "_scan_get_context_for_global_sec"):
                ctx = self._scan_get_context_for_global_sec(float(global_sec))
                if isinstance(ctx, dict):
                    return dict(ctx)
        except Exception:
            pass
        try:
            if hasattr(self, "_resolve_active_context"):
                ctx = self._resolve_active_context(global_sec=float(global_sec))
                if isinstance(ctx, dict):
                    return dict(ctx)
        except Exception:
            pass
        return {}

    def _save_cut_boundary_to_project(self, global_sec: float, frame: int | None = None, score: float | None = None, regions: int | None = None, reason: str = "manual_scan") -> None:
        """
        scan-cut으로 찾은 컷 경계를 프로젝트 JSON의 analysis.cut_boundaries에 누적 저장한다.

        저장 위치:
        project["analysis"]["cut_boundaries"]
        """
        project_path = self._project_file_for_cut_boundary_save()
        if not project_path:
            try:
                print("⚠️ [scan-cut] 프로젝트 파일 경로를 찾지 못해 컷 경계를 JSON에 저장하지 못했습니다.", flush=True)
            except Exception:
                pass
            return

        try:
            global_sec = self._snap_to_frame(float(global_sec))
        except Exception:
            global_sec = float(global_sec or 0.0)

        try:
            fps = self._current_frame_fps()
        except Exception:
            fps = 30.0

        if frame is None:
            try:
                frame = int(round(global_sec * fps))
            except Exception:
                frame = 0

        ctx = self._scan_cut_source_context(global_sec)

        try:
            source_path = str(ctx.get("clip_file", "") or ctx.get("source_path", "") or "")
            local_sec = float(ctx.get("local_sec", global_sec) or global_sec)
            clip_idx = int(ctx.get("clip_idx", 0) or 0)
        except Exception:
            source_path = ""
            local_sec = global_sec
            clip_idx = 0

        record = {
            "schema": "cut_boundary.v1",
            "id": f"cut_{int(frame):08d}",
            "time": global_sec,
            "timeline_sec": global_sec,
            "frame": int(frame),
            "timeline_frame": int(frame),
            "fps": float(fps),
            "clip_idx": clip_idx,
            "clip_local_sec": local_sec,
            "source_path": source_path,
            "score": None if score is None else float(score),
            "regions": None if regions is None else int(regions),
            "reason": str(reason or "manual_scan"),
            "detector": "opencv-gray-pyramid60",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

        try:
            with open(project_path, "r", encoding="utf-8") as f:
                project = json.load(f)
        except Exception as exc:
            print(f"⚠️ [scan-cut] 프로젝트 파일 읽기 실패: {exc}", flush=True)
            return

        analysis = project.setdefault("analysis", {})
        analysis["cut_boundary_schema"] = "cut_boundaries.v1"
        boundaries = analysis.setdefault("cut_boundaries", [])

        # 같은 frame 근처 중복 저장 방지
        replaced = False
        for idx, item in enumerate(list(boundaries)):
            try:
                old_frame = int(item.get("timeline_frame", item.get("frame", -999999)) or -999999)
            except Exception:
                old_frame = -999999
            if abs(old_frame - int(frame)) <= 1:
                boundaries[idx] = record
                replaced = True
                break

        if not replaced:
            boundaries.append(record)

        boundaries.sort(key=lambda item: float(item.get("timeline_sec", item.get("time", 0.0)) or 0.0))

        analysis["cut_boundary_settings"] = {
            "enabled": True,
            "detector": "opencv-gray-pyramid60",
            "count": len(boundaries),
            "absolute": True,
            "locked": True,
        }

        try:
            sync_project_cut_boundaries(
                project,
                settings=getattr(self, "settings", {}) or {},
                primary_fps=fps,
            )
        except Exception as exc:
            print(f"⚠️ [scan-cut] 컷 경계 editor_state 동기화 실패: {exc}", flush=True)

        project["updated_at"] = datetime.now().isoformat()

        try:
            with open(project_path, "w", encoding="utf-8") as f:
                json.dump(project, f, ensure_ascii=False, indent=2)
            print(
                f"💾 [scan-cut] project cut boundary saved frame={frame} time={global_sec:.3f}s count={len(boundaries)}",
                flush=True,
            )
        except Exception as exc:
            print(f"⚠️ [scan-cut] 프로젝트 컷 경계 저장 실패: {exc}", flush=True)


    def _scan_cut_tick(self):
        state = getattr(self, "_scan_cut_state", None)
        if not state:
            if hasattr(self, "_scan_cut_timer"):
                self._scan_cut_timer.stop()
            return

        if bool(state.get("busy")):
            return

        state["busy"] = True

        try:
            fps = self._current_frame_fps()
            direction = int(state.get("direction", 1) or 1)
            threshold = float(state.get("threshold", 24.0) or 24.0)
            hard_threshold = float(state.get("hard_threshold", 45.0) or 45.0)
            consecutive_required = int(state.get("consecutive_hits_required", 2) or 2)
            max_frames = int(state.get("max_frames", 0) or 0)
            frames_per_tick = self._scan_frames_per_tick()
            preview_every = self._scan_preview_every_frames()
            required_regions = self._scan_cross_regions_required()

            for _ in range(frames_per_tick):
                last_frame = max(0, int(state.get("last_frame", 0) or 0))
                next_frame = max(0, last_frame + direction)
                last_sec = last_frame / fps
                next_sec = next_frame / fps
                frame_count = int(state.get("frames", 0) or 0)

                if next_frame == last_frame or (max_frames > 0 and frame_count >= max_frames):
                    self._scan_cut_timer.stop()
                    self._scan_cut_state = None
                    self._set_scan_cut_button_active(0)
                    self._scan_set_timeline_input_locked(False)
                    self._scan_preview_global_sec(last_sec)
                    return

                if hasattr(self, "_scan_same_source") and not self._scan_same_source(last_sec, next_sec):
                    self._scan_cut_timer.stop()
                    self._scan_cut_state = None
                    self._set_scan_cut_button_active(0)
                    self._scan_set_timeline_input_locked(False)
                    self._scan_preview_global_sec(last_sec)
                    self._scan_show_cut_thumbnail(last_sec)  # SCAN_THUMBNAIL_ON_BOUNDARY_PATCH
                    print(f"🛑 [scan-cut] CLIP BOUNDARY stop_frame={last_frame} stop={last_sec:.3f}s", flush=True)
                    return

                prev_image = state.get("last_image") or self._scan_capture_image_at_global(last_sec)
                next_image = self._scan_capture_image_at_global(next_sec)
                score = self._scan_image_delta(prev_image, next_image)
                region_hits = int(getattr(self, "_scan_last_region_hits", 0) or 0)
                region_deltas = list(getattr(self, "_scan_last_region_deltas", []) or [])
                new_count = frame_count + 1

                if new_count == 1 or new_count % preview_every == 0:
                    self._scan_preview_global_sec(next_sec)

                is_hard_cut = score >= hard_threshold and region_hits >= max(1, min(2, required_regions))
                is_soft_hit = score >= threshold and region_hits >= required_regions

                consecutive_hits = int(state.get("consecutive_hits", 0) or 0)
                if is_soft_hit:
                    if consecutive_hits <= 0:
                        state["first_hit_frame"] = last_frame
                        state["first_hit_sec"] = last_sec
                    consecutive_hits += 1
                else:
                    consecutive_hits = 0
                    state["first_hit_frame"] = None
                    state["first_hit_sec"] = None

                state["consecutive_hits"] = consecutive_hits

                if new_count == 1 or new_count % 30 == 0 or is_soft_hit or is_hard_cut:
                    delta_text = ",".join(f"{d:.1f}" for d in region_deltas[:5])
                    print(
                        f"📊 [scan-cut] frame={new_count} delta={score:.2f}/{threshold:.2f} "
                        f"regions={region_hits}/{required_regions} hit={consecutive_hits}/{consecutive_required} "
                        f"frame {last_frame}->{next_frame} {last_sec:.3f}s->{next_sec:.3f}s "
                        f"img={self._scan_image_backend_label() if next_image is not None else 'NONE'} "
                        f"cross=[{delta_text}]",
                        flush=True,
                    )

                if next_image is None:
                    self._scan_cut_timer.stop()
                    self._scan_cut_state = None
                    self._set_scan_cut_button_active(0)
                    self._scan_set_timeline_input_locked(False)
                    self._scan_preview_global_sec(last_sec)
                    return

                if is_hard_cut or consecutive_hits >= consecutive_required:
                    stop_frame = last_frame
                    stop_sec = last_sec
                    if not is_hard_cut:
                        stop_frame = int(state.get("first_hit_frame", last_frame) or last_frame)
                        stop_sec = float(state.get("first_hit_sec", last_sec) or last_sec)

                    self._scan_cut_timer.stop()
                    self._scan_cut_state = None
                    self._set_scan_cut_button_active(0)
                    self._scan_set_timeline_input_locked(False)
                    self._scan_preview_global_sec(stop_sec)
                    self._scan_show_cut_thumbnail(stop_sec)

                    reason = "hard" if is_hard_cut else f"{consecutive_hits}/{consecutive_required}"
                    print(
                        f"🛑 [scan-cut] CUT FOUND reason={reason} stop_frame={stop_frame} "
                        f"stop={stop_sec:.3f}s delta={score:.2f} regions={region_hits}/{required_regions}",
                        flush=True,
                    )
                    try:
                        self.video_player.info_label.setText(f"컷 경계 정지 · 변화량 {score:.1f}")
                    except Exception:
                        pass
                    return

                state["last_frame"] = next_frame
                state["last_image"] = next_image
                state["frames"] = new_count
                state["busy"] = False

        except Exception as exc:
            try:
                self._scan_cut_timer.stop()
            except Exception:
                pass
            self._scan_cut_state = None
            self._set_scan_cut_button_active(0)
            self._scan_set_timeline_input_locked(False)
            print(f"❌ [scan-cut] tick error: {exc}", flush=True)
        finally:
            state = getattr(self, "_scan_cut_state", None)
            if state:
                state["busy"] = False

    def _scan_cut_after_seek(self, next_frame):
        state = getattr(self, "_scan_cut_state", None)
        if not state:
            print("🎬 [scan-cut] after-seek skipped no-state", flush=True)
            return

        fps = self._current_frame_fps()
        next_frame = max(0, int(next_frame or 0))
        prev_frame = max(0, int(state.get("probe_prev_frame", state.get("last_frame", next_frame)) or 0))
        prev_sec = prev_frame / fps
        next_sec = next_frame / fps

        next_image = self._scan_capture_image(next_sec)
        prev_image = state.get("last_image")
        score = self._scan_image_delta(prev_image, next_image)
        threshold = float(state.get("threshold", 12.0) or 12.0)
        frame_count = int(state.get("frames", 0) or 0) + 1

        if frame_count == 1 or frame_count % 30 == 0 or score >= threshold:
            print(
                f"📊 [scan-cut] frame={frame_count} delta={score:.2f}/{threshold:.2f} "
                f"frame {prev_frame}->{next_frame} {prev_sec:.3f}s->{next_sec:.3f}s "
                f"img={(next_image.get('kind') if isinstance(next_image, dict) else ('QIMAGE' if next_image is not None else 'NONE'))}",
                flush=True,
            )

        if score >= threshold:
            if hasattr(self, "_scan_cut_timer"):
                self._scan_cut_timer.stop()
            self._scan_cut_state = None
            self._set_scan_cut_button_active(0)
            self._seek_global_exact(prev_sec)
            self._sync_after_manual_seek(prev_sec)
            print(f"🛑 [scan-cut] CUT FOUND stop_frame={prev_frame} stop={prev_sec:.3f}s delta={score:.2f}", flush=True)
            try:
                self.video_player.info_label.setText(f"컷 경계 정지 · 변화량 {score:.1f}")
            except Exception:
                pass
            return

        state["last_frame"] = next_frame
        state["last_image"] = next_image
        state["frames"] = frame_count
        state["busy"] = False

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
                self._sync_cursor_to_seg(seg)
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
        cur.beginEditBlock()

        block = doc.findBlockByNumber(line_num)
        if not block.isValid():
            cur.endEditBlock()
            return

        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData):
            cur.endEditBlock()
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
                    if abs(float(prev_ud.start_sec) - float(ud.start_sec)) < 0.05:
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
                        if isinstance(nnu, SubtitleBlockData) and abs(float(new_end) - float(nnu.start_sec)) < 0.05:
                            delete_block_safely(next_block)
                        else:
                            next_ud.start_sec = new_end
                    else:
                        next_ud.start_sec = new_end

        self.text_edit.update_margins()
        cur.endEditBlock()
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

        # 인접 Gap 병합
        merge_adjacent_gaps_around(block)

        cur.endEditBlock()
        self.text_edit.setTextCursor(cur)
        self._finalize_edit()

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

    def _on_gap_to_segs(self, gap_start: float, gap_end: float):
        self._undo_mgr.push_immediate()
        gap_start = self._snap_to_frame(gap_start)
        gap_end = self._snap_to_frame(gap_end)
        gap_dur = self._snap_to_frame(gap_end - gap_start)
        push = float(self.settings.get("gap_push_rate", 0.7))
        pull = max(0.0, min(1.0, 1.0 - push))
        left = max((s for s in self.timeline.canvas.segments if s["end"] <= gap_start + 0.1), key=lambda s: s["end"], default=None)
        right = min((s for s in self.timeline.canvas.segments if s["start"] >= gap_end - 0.1), key=lambda s: s["start"], default=None)
        self.text_edit.textCursor().beginEditBlock()
        if left:
            left["end"] = self._snap_to_frame(left["end"] + gap_dur * push)
            self._on_seg_time_changed(left.get("line", 0), left["start"], left["end"], "gap")
        if right:
            right["start"] = self._snap_to_frame(right["start"] - gap_dur * pull)
            self._on_seg_time_changed(right.get("line", 0), right["start"], right["end"], "gap")

        self.text_edit.textCursor().endEditBlock()
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

    def _on_gap_generate_requested(self, gap_start: float, gap_end: float, pivot_sec: float, mode: str):
        self._undo_mgr.push_immediate()
        gap_start = self._snap_to_frame(gap_start)
        gap_end = self._snap_to_frame(gap_end)
        pivot_sec = self._snap_to_frame(pivot_sec)
        pivot_sec = max(gap_start, min(gap_end, pivot_sec))
        if mode == "to":
            sub_start, sub_end = gap_start, pivot_sec
        else:
            sub_start, sub_end = pivot_sec, gap_end
        if sub_end <= sub_start + max(0.02, min(0.1, 1.0 / max(1.0, self._current_frame_fps()))):
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


# === SCAN CUT RELATIVE CHANGE MONKEY PATCH START ===

def _rel_scan_get_cv2_module(self):
    cv2_mod = getattr(self, "_scan_cv2_mod", None)
    if cv2_mod and cv2_mod is not False:
        return cv2_mod
    if cv2_mod is False:
        return None
    try:
        import cv2 as cv2_mod
        self._scan_cv2_mod = cv2_mod
        return cv2_mod
    except Exception as exc:
        self._scan_cv2_mod = False
        print(f"⚠️ [scan-cut-relative] OpenCV 사용 불가: {exc}", flush=True)
        return None


def _rel_scan_get_context_for_global_sec(self, global_sec: float) -> dict:
    if hasattr(self, "_resolve_active_context"):
        try:
            ctx = self._resolve_active_context(global_sec=float(global_sec))
            if isinstance(ctx, dict):
                return dict(ctx)
        except Exception:
            pass
    return {"global_sec": float(global_sec), "local_sec": float(global_sec)}


def _rel_scan_source_and_local_sec(self, global_sec: float):
    ctx = _rel_scan_get_context_for_global_sec(self, global_sec)
    source = str(ctx.get("clip_file", "") or ctx.get("source_path", "") or "")
    if not source:
        try:
            source = str(getattr(getattr(self, "video_player", None), "_current_source_path", "") or "")
        except Exception:
            source = ""
    try:
        local_sec = float(ctx.get("local_sec", global_sec) or global_sec)
    except Exception:
        local_sec = float(global_sec)
    return source, max(0.0, local_sec), ctx


def _rel_scan_get_cv2_capture(self, source_path: str):
    if not source_path or not os.path.exists(source_path):
        return None

    cv2_mod = _rel_scan_get_cv2_module(self)
    if not cv2_mod:
        return None

    norm_path = os.path.normpath(str(source_path))
    cap = getattr(self, "_scan_cv2_capture", None)
    current_path = getattr(self, "_scan_cv2_source_path", None)

    if cap is not None and current_path == norm_path:
        try:
            if cap.isOpened():
                return cap
        except Exception:
            pass

    try:
        if cap is not None:
            cap.release()
    except Exception:
        pass

    try:
        cap = cv2_mod.VideoCapture(norm_path)
        if not cap or not cap.isOpened():
            print(f"⚠️ [scan-cut-relative] VideoCapture open 실패: {norm_path}", flush=True)
            return None
        self._scan_cv2_capture = cap
        self._scan_cv2_source_path = norm_path
        return cap
    except Exception as exc:
        print(f"⚠️ [scan-cut-relative] VideoCapture 예외: {exc}", flush=True)
        return None


def _rel_scan_threshold(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(1.0, float(settings.get("scan_cut_threshold", 24.0)))
    except Exception:
        return 24.0


def _rel_scan_region_threshold(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(1.0, float(settings.get("scan_cut_region_threshold", 18.0)))
    except Exception:
        return 18.0


def _rel_scan_coarse_stride_frames(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(3, min(120, int(settings.get("scan_cut_relative_stride_frames", settings.get("scan_cut_coarse_stride_frames", 30)))))
    except Exception:
        return 30


def _rel_scan_rollback_frames(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(15, min(180, int(settings.get("scan_cut_relative_rollback_frames", settings.get("scan_cut_rollback_frames", 90)))))
    except Exception:
        return 90


def _rel_scan_refine_stages(self) -> list[int]:
    settings = getattr(self, "settings", {}) or {}
    raw = settings.get("scan_cut_relative_stages", settings.get("scan_cut_pyramid_stages", [24, 12, 6, 3, 1]))
    if isinstance(raw, str):
        try:
            out = [max(1, int(x.strip())) for x in raw.split(",") if x.strip()]
            return out or [24, 12, 6, 3, 1]
        except Exception:
            return [24, 12, 6, 3, 1]
    if isinstance(raw, (list, tuple)):
        out = []
        for x in raw:
            try:
                out.append(max(1, int(x)))
            except Exception:
                pass
        return out or [24, 12, 6, 3, 1]
    return [24, 12, 6, 3, 1]


def _rel_scan_frames_per_tick(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(1, min(32, int(settings.get("scan_cut_frames_per_tick", 6))))
    except Exception:
        return 6


def _rel_scan_preview_every_frames(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(1, min(600, int(settings.get("scan_cut_preview_every_frames", 90))))
    except Exception:
        return 90


def _rel_scan_min_delta(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_relative_min_delta", 3.0))
    except Exception:
        return 3.0


def _rel_scan_ratio(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_relative_ratio", 1.35))
    except Exception:
        return 1.35


def _rel_scan_prominence(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_relative_prominence", 1.0))
    except Exception:
        return 1.0


def _rel_scan_drop_ratio(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_relative_drop_ratio", 0.55))
    except Exception:
        return 0.55


def _rel_scan_final_min_delta(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_relative_final_min_delta", 2.5))
    except Exception:
        return 2.5


def _rel_scan_backend_label(self) -> str:
    return "opencv-gray-relative"


def _rel_region_mode_for_stage(stage: int) -> str:
    try:
        stage = int(stage)
    except Exception:
        stage = 1
    if stage <= 1:
        return "full9"
    if stage <= 6:
        return "cross5"
    return "fast4"


def _rel_make_region_thumbnails(self, frame, cv2_mod, scale_w: int, scale_h: int, mode: str = "fast4"):
    try:
        h, w = frame.shape[:2]
    except Exception:
        return None

    if w <= 0 or h <= 0:
        return None

    xs = [0, int(w / 3), int(w * 2 / 3), w]
    ys = [0, int(h / 3), int(h * 2 / 3), h]
    mode = str(mode or "fast4").lower()

    if mode == "full9":
        cells = [
            (0, 0), (1, 0), (2, 0),
            (0, 1), (1, 1), (2, 1),
            (0, 2), (1, 2), (2, 2),
        ]
    elif mode == "cross5":
        cells = [(1, 0), (0, 1), (1, 1), (2, 1), (1, 2)]
    else:
        cells = [(1, 0), (0, 1), (2, 1), (1, 2)]

    result = []
    for cx, cy in cells:
        roi = frame[ys[cy]:ys[cy + 1], xs[cx]:xs[cx + 1]]
        if roi is None or roi.size == 0:
            return None
        gray = cv2_mod.cvtColor(roi, cv2_mod.COLOR_BGR2GRAY)
        small = cv2_mod.resize(gray, (int(scale_w), int(scale_h)), interpolation=cv2_mod.INTER_AREA)
        result.append(small.tobytes())
    return tuple(result)


def _rel_capture_image_at_global(self, global_sec: float, region_mode: str = "fast4", include_center=None):
    cv2_mod = _rel_scan_get_cv2_module(self)
    if not cv2_mod:
        return None

    source_path, local_sec, _ctx = _rel_scan_source_and_local_sec(self, global_sec)
    if not source_path:
        return None

    cap = _rel_scan_get_cv2_capture(self, source_path)
    if cap is None:
        return None

    settings = getattr(self, "settings", {}) or {}

    try:
        scale_w = int(settings.get("scan_cut_sample_width", 18))
        scale_h = int(settings.get("scan_cut_sample_height", 10))
    except Exception:
        scale_w, scale_h = 18, 10

    scale_w = max(8, min(scale_w, 64))
    scale_h = max(6, min(scale_h, 36))

    try:
        source_fps = float(cap.get(cv2_mod.CAP_PROP_FPS) or 0.0)
    except Exception:
        source_fps = 0.0

    if source_fps <= 1.0:
        source_fps = self._current_frame_fps()

    frame_idx = max(0, int(round(float(local_sec) * source_fps)))

    try:
        current_pos = int(cap.get(cv2_mod.CAP_PROP_POS_FRAMES) or 0)
        if current_pos != frame_idx:
            cap.set(cv2_mod.CAP_PROP_POS_FRAMES, frame_idx)

        ok, frame = cap.read()
        if not ok or frame is None:
            return None

        h, w = frame.shape[:2]
        if w <= 0 or h <= 0:
            return None

        if not bool(getattr(self, "_scan_logged_relative_resolution", False)):
            self._scan_logged_relative_resolution = True
            print(
                f"🔎 [scan-cut-relative] source_resolution={w}x{h} "
                f"stride={_rel_scan_coarse_stride_frames(self)} "
                f"rollback={_rel_scan_rollback_frames(self)} "
                f"stages={_rel_scan_refine_stages(self)} "
                f"sample_each={scale_w}x{scale_h} mode=relative-change",
                flush=True,
            )

        return _rel_make_region_thumbnails(self, frame, cv2_mod, scale_w, scale_h, mode=region_mode)
    except Exception:
        return None


def _rel_delta_bytes(self, a: bytes, b: bytes) -> float:
    if not a or not b:
        return 0.0

    n = min(len(a), len(b))
    if n <= 0:
        return 0.0

    settings = getattr(self, "settings", {}) or {}
    try:
        target_samples = int(settings.get("scan_cut_target_samples", 64))
    except Exception:
        target_samples = 64

    target_samples = max(16, min(256, target_samples))
    step = max(1, n // target_samples)

    total = 0
    count = 0
    for i in range(0, n, step):
        total += abs(a[i] - b[i])
        count += 1

    return total / float(count or 1)


def _rel_region_deltas(self, prev_image, next_image):
    if not prev_image or not next_image:
        return []

    if isinstance(prev_image, (tuple, list)) and isinstance(next_image, (tuple, list)):
        n = min(len(prev_image), len(next_image))
        return [_rel_delta_bytes(self, prev_image[i], next_image[i]) for i in range(n)]

    return [_rel_delta_bytes(self, prev_image, next_image)]


def _rel_image_delta(self, prev_image, next_image) -> float:
    deltas = _rel_region_deltas(self, prev_image, next_image)
    if not deltas:
        self._scan_last_region_deltas = []
        self._scan_last_region_hits = 0
        return 0.0

    threshold = _rel_scan_region_threshold(self)
    hits = sum(1 for d in deltas if d >= threshold)
    self._scan_last_region_deltas = list(deltas)
    self._scan_last_region_hits = int(hits)

    ranked = sorted(deltas, reverse=True)

    if len(ranked) >= 9:
        top_n = ranked[:5]
    elif len(ranked) >= 5:
        top_n = ranked[:3]
    else:
        top_n = ranked[:2]

    return sum(top_n) / float(len(top_n) or 1)


def _rel_is_candidate(self, score: float, baseline: float, previous_score: float) -> tuple[bool, str]:
    abs_threshold = _rel_scan_threshold(self)
    min_delta = _rel_scan_min_delta(self)
    ratio = _rel_scan_ratio(self)
    prominence = _rel_scan_prominence(self)

    if score >= abs_threshold:
        return True, "absolute"

    if score >= min_delta and score >= max(baseline * ratio, baseline + prominence):
        return True, "relative"

    if previous_score >= min_delta and previous_score >= max(baseline * ratio, baseline + prominence):
        if score <= previous_score * _rel_scan_drop_ratio(self):
            return True, "relative_drop"

    return False, ""


def _rel_refine_boundary(self, start_frame: int, end_frame: int, fps: float, reason: str):
    try:
        fps = float(fps or self._current_frame_fps())
    except Exception:
        return None

    rollback = _rel_scan_rollback_frames(self)
    stages = _rel_scan_refine_stages(self)

    lo = max(0, min(int(start_frame), int(end_frame)) - rollback)
    hi = max(int(start_frame), int(end_frame)) + max(stages)

    best_frame = None
    best_score = -1.0
    best_regions = 0
    best_deltas = []

    for stage in stages:
        stage = max(1, int(stage))
        mode = _rel_region_mode_for_stage(stage)

        local_best_frame = None
        local_best_score = -1.0
        local_best_regions = 0
        local_best_deltas = []

        # 촘촘한 후보 탐색: stage 간격의 절반만큼 이동하면서 f -> f+stage 비교
        step = max(1, stage // 2)
        f = int(lo)
        end = max(f + 1, int(hi))

        while f < end:
            sec_a = f / fps
            sec_b = (f + stage) / fps

            img_a = _rel_capture_image_at_global(self, sec_a, region_mode=mode)
            img_b = _rel_capture_image_at_global(self, sec_b, region_mode=mode)

            if img_a is not None and img_b is not None:
                score = _rel_image_delta(self, img_a, img_b)
                regions = int(getattr(self, "_scan_last_region_hits", 0) or 0)
                deltas = list(getattr(self, "_scan_last_region_deltas", []) or [])

                if score > local_best_score:
                    local_best_frame = f
                    local_best_score = score
                    local_best_regions = regions
                    local_best_deltas = deltas

            f += step

        if local_best_frame is None:
            continue

        best_frame = int(local_best_frame)
        best_score = float(local_best_score)
        best_regions = int(local_best_regions)
        best_deltas = list(local_best_deltas)

        lo = max(0, best_frame - stage)
        hi = best_frame + stage

        delta_text = ",".join(f"{d:.1f}" for d in local_best_deltas[:9])
        print(
            f"🔍 [scan-cut-relative] REFINE stage={stage} mode={mode} "
            f"best_frame={best_frame} score={best_score:.2f} "
            f"regions={best_regions} range={lo}-{hi} deltas=[{delta_text}]",
            flush=True,
        )

    if best_frame is None:
        return None

    final_score = best_score
    final_regions = best_regions
    final_threshold = _rel_scan_final_min_delta(self)

    if final_score < final_threshold:
        print(
            f"⚠️ [scan-cut-relative] REJECT frame={best_frame} "
            f"score={final_score:.2f}/{final_threshold:.2f}",
            flush=True,
        )
        return None

    stop_frame = int(best_frame)
    stop_sec = stop_frame / fps

    delta_text = ",".join(f"{d:.1f}" for d in best_deltas[:9])
    print(
        f"🎯 [scan-cut-relative] FINAL reason={reason} "
        f"stop_frame={stop_frame} stop={stop_sec:.3f}s "
        f"score={final_score:.2f} regions={final_regions} deltas=[{delta_text}]",
        flush=True,
    )

    return stop_frame, stop_sec, final_score, final_regions, reason


def _rel_scan_cut_tick(self):
    state = getattr(self, "_scan_cut_state", None)

    if not state:
        try:
            self._scan_cut_timer.stop()
        except Exception:
            pass
        return

    if bool(state.get("busy")):
        return

    state["busy"] = True

    try:
        fps = self._current_frame_fps()
        direction = int(state.get("direction", 1) or 1)
        max_frames = int(state.get("max_frames", 0) or 0)

        frames_per_tick = _rel_scan_frames_per_tick(self)
        preview_every = _rel_scan_preview_every_frames(self)
        stride = _rel_scan_coarse_stride_frames(self)

        for _ in range(frames_per_tick):
            last_frame = max(0, int(state.get("last_frame", 0) or 0))
            next_frame = max(0, last_frame + direction * stride)
            last_sec = last_frame / fps
            next_sec = next_frame / fps
            frame_count = int(state.get("frames", 0) or 0)

            if next_frame == last_frame or (max_frames > 0 and frame_count >= max_frames):
                self._scan_cut_timer.stop()
                self._scan_cut_state = None
                self._set_scan_cut_button_active(0)
                if hasattr(self, "_scan_set_timeline_input_locked"):
                    self._scan_set_timeline_input_locked(False)
                self._scan_preview_global_sec(last_sec)
                return

            if hasattr(self, "_scan_same_source") and not self._scan_same_source(last_sec, next_sec):
                self._scan_cut_timer.stop()
                self._scan_cut_state = None
                self._set_scan_cut_button_active(0)
                if hasattr(self, "_scan_set_timeline_input_locked"):
                    self._scan_set_timeline_input_locked(False)
                self._scan_preview_global_sec(last_sec)
                print(f"🛑 [scan-cut-relative] CLIP BOUNDARY stop_frame={last_frame} stop={last_sec:.3f}s", flush=True)
                return

            # 중요: adjacent가 아니라 last_frame -> next_frame 구간 비교
            img_a = _rel_capture_image_at_global(self, last_sec, region_mode="fast4")
            img_b = _rel_capture_image_at_global(self, next_sec, region_mode="fast4")
            score = _rel_image_delta(self, img_a, img_b)

            previous_score = float(state.get("previous_score", 0.0) or 0.0)
            baseline = float(state.get("score_baseline", score) or score)

            # baseline은 변화가 천천히 반영되게 해서 sudden rise를 상대적으로 감지
            baseline_for_decision = baseline
            state["score_baseline"] = baseline * 0.90 + score * 0.10
            state["previous_score"] = score

            new_count = frame_count + stride

            if new_count == stride or (new_count // preview_every) != (frame_count // preview_every):
                self._scan_preview_global_sec(next_sec)

            is_candidate, reason = _rel_is_candidate(self, score, baseline_for_decision, previous_score)

            deltas = list(getattr(self, "_scan_last_region_deltas", []) or [])
            delta_text = ",".join(f"{d:.1f}" for d in deltas[:4])

            if new_count == stride or new_count % max(stride * 2, 1) == 0 or is_candidate:
                print(
                    f"📊 [scan-cut-relative] frame={new_count} "
                    f"delta={score:.2f} baseline={baseline_for_decision:.2f} "
                    f"prev={previous_score:.2f} stride={stride} "
                    f"reason={reason or '-'} "
                    f"frame {last_frame}->{next_frame} "
                    f"{last_sec:.3f}s->{next_sec:.3f}s "
                    f"img={_rel_scan_backend_label(self)} fast4=[{delta_text}]",
                    flush=True,
                )

            if img_a is None or img_b is None:
                self._scan_cut_timer.stop()
                self._scan_cut_state = None
                self._set_scan_cut_button_active(0)
                if hasattr(self, "_scan_set_timeline_input_locked"):
                    self._scan_set_timeline_input_locked(False)
                self._scan_preview_global_sec(last_sec)
                return

            if is_candidate:
                print(
                    f"↩️ [scan-cut-relative] RELATIVE ROLLBACK START reason={reason} "
                    f"candidate={last_frame}->{next_frame} "
                    f"{last_sec:.3f}s->{next_sec:.3f}s score={score:.2f}",
                    flush=True,
                )

                # drop 후보면 직전 구간을 더 강하게 의심
                refine_start = last_frame - stride if reason == "relative_drop" else last_frame
                refine_end = next_frame

                refined = _rel_refine_boundary(self, refine_start, refine_end, fps, reason)

                if refined:
                    stop_frame, stop_sec, final_score, final_regions, final_reason = refined

                    self._scan_cut_timer.stop()
                    self._scan_cut_state = None
                    self._set_scan_cut_button_active(0)

                    if hasattr(self, "_scan_set_timeline_input_locked"):
                        self._scan_set_timeline_input_locked(False)

                    self._scan_preview_global_sec(stop_sec)

                    try:
                        if hasattr(self, "_scan_show_cut_thumbnail"):
                            self._scan_show_cut_thumbnail(stop_sec)
                    except Exception:
                        pass

                    try:
                        if hasattr(self, "_save_cut_boundary_to_project"):
                            self._save_cut_boundary_to_project(
                                stop_sec,
                                frame=stop_frame,
                                score=final_score,
                                regions=final_regions,
                                reason=f"relative_{final_reason}",
                            )
                    except Exception as save_exc:
                        print(f"⚠️ [scan-cut-relative] project save failed: {save_exc}", flush=True)

                    print(
                        f"🛑 [scan-cut-relative] CUT FOUND reason=relative_{final_reason} "
                        f"stop_frame={stop_frame} stop={stop_sec:.3f}s "
                        f"delta={final_score:.2f} regions={final_regions}",
                        flush=True,
                    )

                    try:
                        self.video_player.info_label.setText(f"컷 경계 정지 · 상대변화 {final_score:.1f}")
                    except Exception:
                        pass

                    return

                print("↪️ [scan-cut-relative] relative rollback rejected; continue", flush=True)

            state["last_frame"] = next_frame
            state["last_image"] = img_b
            state["frames"] = new_count
            state["busy"] = False

    except Exception as exc:
        try:
            self._scan_cut_timer.stop()
        except Exception:
            pass
        self._scan_cut_state = None
        try:
            self._set_scan_cut_button_active(0)
        except Exception:
            pass
        if hasattr(self, "_scan_set_timeline_input_locked"):
            self._scan_set_timeline_input_locked(False)
        print(f"❌ [scan-cut-relative] tick error: {exc}", flush=True)
    finally:
        state = getattr(self, "_scan_cut_state", None)
        if state:
            state["busy"] = False


# 실제 클래스 메서드 강제 교체
EditorTimelineVideoMixin._scan_get_cv2_module = _rel_scan_get_cv2_module
EditorTimelineVideoMixin._scan_get_context_for_global_sec = _rel_scan_get_context_for_global_sec
EditorTimelineVideoMixin._scan_source_and_local_sec = _rel_scan_source_and_local_sec
EditorTimelineVideoMixin._scan_get_cv2_capture = _rel_scan_get_cv2_capture
EditorTimelineVideoMixin._scan_threshold = _rel_scan_threshold
EditorTimelineVideoMixin._scan_region_threshold = _rel_scan_region_threshold
EditorTimelineVideoMixin._scan_coarse_stride_frames = _rel_scan_coarse_stride_frames
EditorTimelineVideoMixin._scan_image_backend_label = _rel_scan_backend_label
EditorTimelineVideoMixin._scan_make_cross_region_thumbnails = _rel_make_region_thumbnails
EditorTimelineVideoMixin._scan_capture_image_at_global = _rel_capture_image_at_global
EditorTimelineVideoMixin._scan_image_delta = _rel_image_delta
EditorTimelineVideoMixin._scan_cut_tick = _rel_scan_cut_tick

# === SCAN CUT RELATIVE CHANGE MONKEY PATCH END ===


# === SCAN CUT RELATIVE ACCEPTANCE GUARD START ===

def _rel_abs_final_threshold(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        # absolute 후보는 마지막 full9가 충분히 강해야 확정한다.
        return float(settings.get("scan_cut_absolute_final_threshold", 18.0))
    except Exception:
        return 18.0


def _rel_abs_final_regions_required(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(0, min(9, int(settings.get("scan_cut_absolute_final_regions_required", 1))))
    except Exception:
        return 1


def _rel_final_decision_thresholds(self, reason: str):
    reason = str(reason or "")
    if reason == "absolute":
        return _rel_abs_final_threshold(self), _rel_abs_final_regions_required(self)

    # relative / relative_drop은 페이드 감지용이라 낮은 final score를 허용한다.
    return _rel_scan_final_min_delta(self), 0


def _rel_refine_boundary(self, start_frame: int, end_frame: int, fps: float, reason: str):
    """
    Relative scan-cut refine.

    수정점:
    - absolute 후보는 final full9 결과가 약하면 reject한다.
    - relative 후보만 낮은 final threshold를 허용한다.
    """
    try:
        fps = float(fps or self._current_frame_fps())
    except Exception:
        return None

    rollback = _rel_scan_rollback_frames(self)
    stages = _rel_scan_refine_stages(self)

    lo = max(0, min(int(start_frame), int(end_frame)) - rollback)
    hi = max(int(start_frame), int(end_frame)) + max(stages)

    best_frame = None
    best_score = -1.0
    best_regions = 0
    best_deltas = []

    for stage in stages:
        stage = max(1, int(stage))
        mode = _rel_region_mode_for_stage(stage)

        local_best_frame = None
        local_best_score = -1.0
        local_best_regions = 0
        local_best_deltas = []

        # stage 간격의 절반씩 훑어서 피크를 놓치지 않게 한다.
        step = max(1, stage // 2)
        f = int(lo)
        end = max(f + 1, int(hi))

        while f < end:
            sec_a = f / fps
            sec_b = (f + stage) / fps

            img_a = _rel_capture_image_at_global(self, sec_a, region_mode=mode)
            img_b = _rel_capture_image_at_global(self, sec_b, region_mode=mode)

            if img_a is not None and img_b is not None:
                score = _rel_image_delta(self, img_a, img_b)
                regions = int(getattr(self, "_scan_last_region_hits", 0) or 0)
                deltas = list(getattr(self, "_scan_last_region_deltas", []) or [])

                if score > local_best_score:
                    local_best_frame = f
                    local_best_score = score
                    local_best_regions = regions
                    local_best_deltas = deltas

            f += step

        if local_best_frame is None:
            continue

        best_frame = int(local_best_frame)
        best_score = float(local_best_score)
        best_regions = int(local_best_regions)
        best_deltas = list(local_best_deltas)

        lo = max(0, best_frame - stage)
        hi = best_frame + stage

        delta_text = ",".join(f"{d:.1f}" for d in local_best_deltas[:9])
        print(
            f"🔍 [scan-cut-relative] REFINE stage={stage} mode={mode} "
            f"best_frame={best_frame} score={best_score:.2f} "
            f"regions={best_regions} range={lo}-{hi} deltas=[{delta_text}]",
            flush=True,
        )

    if best_frame is None:
        return None

    # 최종 검증은 full9, 1프레임 기준으로 다시 수행한다.
    final_img_a = _rel_capture_image_at_global(self, best_frame / fps, region_mode="full9")
    final_img_b = _rel_capture_image_at_global(self, (best_frame + 1) / fps, region_mode="full9")
    final_score = _rel_image_delta(self, final_img_a, final_img_b)
    final_regions = int(getattr(self, "_scan_last_region_hits", 0) or 0)
    final_deltas = list(getattr(self, "_scan_last_region_deltas", []) or [])

    final_threshold, final_regions_required = _rel_final_decision_thresholds(self, reason)

    if final_score < final_threshold or final_regions < final_regions_required:
        print(
            f"⚠️ [scan-cut-relative] REJECT reason={reason} frame={best_frame} "
            f"score={final_score:.2f}/{final_threshold:.2f} "
            f"regions={final_regions}/{final_regions_required}",
            flush=True,
        )
        return None

    stop_frame = int(best_frame)
    stop_sec = stop_frame / fps

    delta_text = ",".join(f"{d:.1f}" for d in final_deltas[:9])
    print(
        f"🎯 [scan-cut-relative] FINAL reason={reason} "
        f"stop_frame={stop_frame} stop={stop_sec:.3f}s "
        f"score={final_score:.2f} regions={final_regions}/{final_regions_required} "
        f"deltas=[{delta_text}]",
        flush=True,
    )

    return stop_frame, stop_sec, final_score, final_regions, reason

# 기존 _rel_scan_cut_tick은 전역 _rel_refine_boundary 이름을 런타임에 참조하므로,
# 여기서 같은 이름을 다시 정의하면 다음 호출부터 이 안전판이 적용된다.

# === SCAN CUT RELATIVE ACCEPTANCE GUARD END ===


# === SCAN CUT RELATIVE SENSITIVITY PATCH START ===

def _rel_ignore_initial_seconds(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_ignore_initial_seconds", 3.0))
    except Exception:
        return 3.0


def _rel_absolute_coarse_threshold(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_absolute_coarse_threshold", 40.0))
    except Exception:
        return 40.0


def _rel_absolute_coarse_regions_required(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(0, min(4, int(settings.get("scan_cut_absolute_coarse_regions_required", 2))))
    except Exception:
        return 2


def _rel_recent_reject_window_frames(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(1, int(settings.get("scan_cut_recent_reject_window_frames", 90)))
    except Exception:
        return 90


def _rel_is_recently_rejected(self, frame: int) -> bool:
    rejected = list(getattr(self, "_scan_relative_rejected_frames", []) or [])
    window = _rel_recent_reject_window_frames(self)
    try:
        frame = int(frame)
    except Exception:
        return False
    return any(abs(frame - int(item)) <= window for item in rejected)


def _rel_mark_rejected(self, frame: int) -> None:
    rejected = list(getattr(self, "_scan_relative_rejected_frames", []) or [])
    try:
        rejected.append(int(frame))
    except Exception:
        return
    self._scan_relative_rejected_frames = rejected[-12:]


def _rel_is_candidate(self, score: float, baseline: float, previous_score: float) -> tuple[bool, str]:
    """
    상대 변화량 후보 판정 v2.

    absolute:
    - coarse 구간 변화가 아주 커야 함
    - fast4 영역 hit도 일정 수 이상이어야 함

    relative:
    - baseline 대비 충분히 튀어야 함
    - 페이드/완만 전환용
    """
    try:
        score = float(score)
        baseline = float(baseline)
        previous_score = float(previous_score)
    except Exception:
        return False, ""

    region_hits = int(getattr(self, "_scan_last_region_hits", 0) or 0)

    # hard/absolute 후보는 많이 보수적으로.
    abs_threshold = _rel_absolute_coarse_threshold(self)
    abs_regions = _rel_absolute_coarse_regions_required(self)
    if score >= abs_threshold and region_hits >= abs_regions:
        return True, "absolute"

    # relative 후보는 baseline 대비 충분히 튀어야 함.
    min_delta = _rel_scan_min_delta(self)
    ratio = _rel_scan_ratio(self)
    prominence = _rel_scan_prominence(self)

    # baseline이 너무 낮으면 ratio가 과하게 민감해지므로 floor 적용.
    baseline_floor = 4.0
    effective_baseline = max(baseline, baseline_floor)

    if score >= min_delta and score >= max(effective_baseline * ratio, effective_baseline + prominence):
        return True, "relative"

    # 변화가 확 튄 다음 떨어지는 지점도 후보로 볼 수 있지만,
    # previous_score 자체가 충분히 커야 한다.
    drop_ratio = _rel_scan_drop_ratio(self)
    if (
        previous_score >= max(min_delta * 2.0, effective_baseline * ratio)
        and score <= previous_score * drop_ratio
    ):
        return True, "relative_drop"

    return False, ""


def _rel_scan_cut_tick(self):
    state = getattr(self, "_scan_cut_state", None)

    if not state:
        try:
            self._scan_cut_timer.stop()
        except Exception:
            pass
        return

    if bool(state.get("busy")):
        return

    state["busy"] = True

    try:
        fps = self._current_frame_fps()
        direction = int(state.get("direction", 1) or 1)
        max_frames = int(state.get("max_frames", 0) or 0)

        frames_per_tick = _rel_scan_frames_per_tick(self)
        preview_every = _rel_scan_preview_every_frames(self)
        stride = _rel_scan_coarse_stride_frames(self)

        for _ in range(frames_per_tick):
            last_frame = max(0, int(state.get("last_frame", 0) or 0))
            next_frame = max(0, last_frame + direction * stride)
            last_sec = last_frame / fps
            next_sec = next_frame / fps
            frame_count = int(state.get("frames", 0) or 0)

            if next_frame == last_frame or (max_frames > 0 and frame_count >= max_frames):
                self._scan_cut_timer.stop()
                self._scan_cut_state = None
                self._set_scan_cut_button_active(0)
                if hasattr(self, "_scan_set_timeline_input_locked"):
                    self._scan_set_timeline_input_locked(False)
                self._scan_preview_global_sec(last_sec)
                return

            if hasattr(self, "_scan_same_source") and not self._scan_same_source(last_sec, next_sec):
                self._scan_cut_timer.stop()
                self._scan_cut_state = None
                self._set_scan_cut_button_active(0)
                if hasattr(self, "_scan_set_timeline_input_locked"):
                    self._scan_set_timeline_input_locked(False)
                self._scan_preview_global_sec(last_sec)
                print(f"🛑 [scan-cut-relative] CLIP BOUNDARY stop_frame={last_frame} stop={last_sec:.3f}s", flush=True)
                return

            img_a = _rel_capture_image_at_global(self, last_sec, region_mode="fast4")
            img_b = _rel_capture_image_at_global(self, next_sec, region_mode="fast4")
            score = _rel_image_delta(self, img_a, img_b)

            previous_score = float(state.get("previous_score", 0.0) or 0.0)
            baseline = float(state.get("score_baseline", score) or score)

            baseline_for_decision = baseline
            state["score_baseline"] = baseline * 0.92 + score * 0.08
            state["previous_score"] = score

            new_count = frame_count + stride

            if new_count == stride or (new_count // preview_every) != (frame_count // preview_every):
                self._scan_preview_global_sec(next_sec)

            is_candidate = False
            reason = ""

            # 시작 직후는 로고/흔들림/노출 안정화가 많으므로 무시
            if last_sec >= _rel_ignore_initial_seconds(self):
                is_candidate, reason = _rel_is_candidate(self, score, baseline_for_decision, previous_score)

            # 최근 reject 주변은 반복 rollback 방지
            if is_candidate and _rel_is_recently_rejected(self, last_frame):
                is_candidate = False
                reason = "recent_reject_skip"

            deltas = list(getattr(self, "_scan_last_region_deltas", []) or [])
            region_hits = int(getattr(self, "_scan_last_region_hits", 0) or 0)
            delta_text = ",".join(f"{d:.1f}" for d in deltas[:4])

            if new_count == stride or new_count % max(stride * 2, 1) == 0 or is_candidate or reason == "recent_reject_skip":
                print(
                    f"📊 [scan-cut-relative] frame={new_count} "
                    f"delta={score:.2f} baseline={baseline_for_decision:.2f} "
                    f"prev={previous_score:.2f} regions={region_hits} stride={stride} "
                    f"reason={reason or '-'} "
                    f"frame {last_frame}->{next_frame} "
                    f"{last_sec:.3f}s->{next_sec:.3f}s "
                    f"img={_rel_scan_backend_label(self)} fast4=[{delta_text}]",
                    flush=True,
                )

            if img_a is None or img_b is None:
                self._scan_cut_timer.stop()
                self._scan_cut_state = None
                self._set_scan_cut_button_active(0)
                if hasattr(self, "_scan_set_timeline_input_locked"):
                    self._scan_set_timeline_input_locked(False)
                self._scan_preview_global_sec(last_sec)
                return

            if is_candidate:
                print(
                    f"↩️ [scan-cut-relative] RELATIVE ROLLBACK START reason={reason} "
                    f"candidate={last_frame}->{next_frame} "
                    f"{last_sec:.3f}s->{next_sec:.3f}s score={score:.2f}",
                    flush=True,
                )

                refine_start = last_frame - stride if reason == "relative_drop" else last_frame
                refine_end = next_frame

                refined = _rel_refine_boundary(self, refine_start, refine_end, fps, reason)

                if refined:
                    stop_frame, stop_sec, final_score, final_regions, final_reason = refined

                    self._scan_cut_timer.stop()
                    self._scan_cut_state = None
                    self._set_scan_cut_button_active(0)

                    if hasattr(self, "_scan_set_timeline_input_locked"):
                        self._scan_set_timeline_input_locked(False)

                    self._scan_preview_global_sec(stop_sec)

                    try:
                        if hasattr(self, "_scan_show_cut_thumbnail"):
                            self._scan_show_cut_thumbnail(stop_sec)
                    except Exception:
                        pass

                    try:
                        if hasattr(self, "_save_cut_boundary_to_project"):
                            self._save_cut_boundary_to_project(
                                stop_sec,
                                frame=stop_frame,
                                score=final_score,
                                regions=final_regions,
                                reason=f"relative_{final_reason}",
                            )
                    except Exception as save_exc:
                        print(f"⚠️ [scan-cut-relative] project save failed: {save_exc}", flush=True)

                    print(
                        f"🛑 [scan-cut-relative] CUT FOUND reason=relative_{final_reason} "
                        f"stop_frame={stop_frame} stop={stop_sec:.3f}s "
                        f"delta={final_score:.2f} regions={final_regions}",
                        flush=True,
                    )

                    try:
                        self.video_player.info_label.setText(f"컷 경계 정지 · 상대변화 {final_score:.1f}")
                    except Exception:
                        pass

                    return

                # reject된 주변은 다시 검사하지 않음
                _rel_mark_rejected(self, last_frame)
                print("↪️ [scan-cut-relative] relative rollback rejected; continue", flush=True)

            state["last_frame"] = next_frame
            state["last_image"] = img_b
            state["frames"] = new_count
            state["busy"] = False

    except Exception as exc:
        try:
            self._scan_cut_timer.stop()
        except Exception:
            pass
        self._scan_cut_state = None
        try:
            self._set_scan_cut_button_active(0)
        except Exception:
            pass
        if hasattr(self, "_scan_set_timeline_input_locked"):
            self._scan_set_timeline_input_locked(False)
        print(f"❌ [scan-cut-relative] tick error: {exc}", flush=True)
    finally:
        state = getattr(self, "_scan_cut_state", None)
        if state:
            state["busy"] = False


# monkey patch를 다시 고정
EditorTimelineVideoMixin._scan_cut_tick = _rel_scan_cut_tick

# === SCAN CUT RELATIVE SENSITIVITY PATCH END ===


# === SCAN CUT RELATIVE DROP GUARD START ===

def _rel_final_window_frames(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(2, min(60, int(settings.get("scan_cut_relative_final_window_frames", 12))))
    except Exception:
        return 12


def _rel_relative_window_threshold(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_relative_window_threshold", 4.5))
    except Exception:
        return 4.5


def _rel_is_candidate(self, score: float, baseline: float, previous_score: float) -> tuple[bool, str]:
    """
    상대 변화량 후보 판정 v3.

    핵심:
    - relative rise는 후보로 보지 않는다.
    - peak가 나온 뒤 다음 샘플에서 확 떨어지는 relative_drop만 후보로 본다.
    - absolute는 coarse 기준을 매우 보수적으로 둔다.
    """
    try:
        score = float(score)
        baseline = float(baseline)
        previous_score = float(previous_score)
    except Exception:
        return False, ""

    region_hits = int(getattr(self, "_scan_last_region_hits", 0) or 0)

    # absolute 후보는 진짜 강한 구간만.
    abs_threshold = _rel_absolute_coarse_threshold(self)
    abs_regions = _rel_absolute_coarse_regions_required(self)
    if score >= abs_threshold and region_hits >= abs_regions:
        return True, "absolute"

    # relative는 올라가는 순간이 아니라 떨어지는 순간만 잡는다.
    min_delta = _rel_scan_min_delta(self)
    ratio = _rel_scan_ratio(self)
    prominence = _rel_scan_prominence(self)
    drop_ratio = _rel_scan_drop_ratio(self)

    baseline_floor = 2.5
    effective_baseline = max(baseline, baseline_floor)

    peak_threshold = max(
        min_delta,
        effective_baseline * ratio,
        effective_baseline + prominence,
    )

    if previous_score >= peak_threshold and score <= previous_score * drop_ratio:
        return True, "relative_drop"

    return False, ""


def _rel_refine_boundary(self, start_frame: int, end_frame: int, fps: float, reason: str):
    """
    Relative scan-cut refine v3.

    absolute:
    - 최종 1프레임 full9가 충분히 강해야 확정.

    relative_drop:
    - 최종 1프레임이 약해도 됨.
    - 대신 best_frame 주변 window full9 변화량이 충분해야 확정.
    """
    try:
        fps = float(fps or self._current_frame_fps())
    except Exception:
        return None

    rollback = _rel_scan_rollback_frames(self)
    stages = _rel_scan_refine_stages(self)

    lo = max(0, min(int(start_frame), int(end_frame)) - rollback)
    hi = max(int(start_frame), int(end_frame)) + max(stages)

    best_frame = None
    best_score = -1.0
    best_regions = 0
    best_deltas = []

    for stage in stages:
        stage = max(1, int(stage))
        mode = _rel_region_mode_for_stage(stage)

        local_best_frame = None
        local_best_score = -1.0
        local_best_regions = 0
        local_best_deltas = []

        step = max(1, stage // 2)
        f = int(lo)
        end = max(f + 1, int(hi))

        while f < end:
            sec_a = f / fps
            sec_b = (f + stage) / fps

            img_a = _rel_capture_image_at_global(self, sec_a, region_mode=mode)
            img_b = _rel_capture_image_at_global(self, sec_b, region_mode=mode)

            if img_a is not None and img_b is not None:
                score = _rel_image_delta(self, img_a, img_b)
                regions = int(getattr(self, "_scan_last_region_hits", 0) or 0)
                deltas = list(getattr(self, "_scan_last_region_deltas", []) or [])

                if score > local_best_score:
                    local_best_frame = f
                    local_best_score = score
                    local_best_regions = regions
                    local_best_deltas = deltas

            f += step

        if local_best_frame is None:
            continue

        best_frame = int(local_best_frame)
        best_score = float(local_best_score)
        best_regions = int(local_best_regions)
        best_deltas = list(local_best_deltas)

        lo = max(0, best_frame - stage)
        hi = best_frame + stage

        delta_text = ",".join(f"{d:.1f}" for d in local_best_deltas[:9])
        print(
            f"🔍 [scan-cut-relative] REFINE stage={stage} mode={mode} "
            f"best_frame={best_frame} score={best_score:.2f} "
            f"regions={best_regions} range={lo}-{hi} deltas=[{delta_text}]",
            flush=True,
        )

    if best_frame is None:
        return None

    # absolute 후보는 1프레임 full9로 강하게 검증
    if reason == "absolute":
        final_img_a = _rel_capture_image_at_global(self, best_frame / fps, region_mode="full9")
        final_img_b = _rel_capture_image_at_global(self, (best_frame + 1) / fps, region_mode="full9")
        final_score = _rel_image_delta(self, final_img_a, final_img_b)
        final_regions = int(getattr(self, "_scan_last_region_hits", 0) or 0)
        final_deltas = list(getattr(self, "_scan_last_region_deltas", []) or [])

        final_threshold, final_regions_required = _rel_final_decision_thresholds(self, reason)

        if final_score < final_threshold or final_regions < final_regions_required:
            print(
                f"⚠️ [scan-cut-relative] REJECT reason={reason} frame={best_frame} "
                f"score={final_score:.2f}/{final_threshold:.2f} "
                f"regions={final_regions}/{final_regions_required}",
                flush=True,
            )
            return None

        stop_frame = int(best_frame)
        stop_sec = stop_frame / fps
        delta_text = ",".join(f"{d:.1f}" for d in final_deltas[:9])
        print(
            f"🎯 [scan-cut-relative] FINAL reason={reason} "
            f"stop_frame={stop_frame} stop={stop_sec:.3f}s "
            f"score={final_score:.2f} regions={final_regions}/{final_regions_required} "
            f"deltas=[{delta_text}]",
            flush=True,
        )
        return stop_frame, stop_sec, final_score, final_regions, reason

    # relative_drop 후보는 window full9로 검증
    window = _rel_final_window_frames(self)
    a_frame = max(0, int(best_frame) - window)
    b_frame = int(best_frame) + window

    win_img_a = _rel_capture_image_at_global(self, a_frame / fps, region_mode="full9")
    win_img_b = _rel_capture_image_at_global(self, b_frame / fps, region_mode="full9")
    window_score = _rel_image_delta(self, win_img_a, win_img_b)
    window_regions = int(getattr(self, "_scan_last_region_hits", 0) or 0)
    window_deltas = list(getattr(self, "_scan_last_region_deltas", []) or [])

    threshold = _rel_relative_window_threshold(self)

    if window_score < threshold:
        print(
            f"⚠️ [scan-cut-relative] REJECT reason={reason} frame={best_frame} "
            f"window_score={window_score:.2f}/{threshold:.2f} "
            f"window={a_frame}->{b_frame}",
            flush=True,
        )
        return None

    stop_frame = int(best_frame)
    stop_sec = stop_frame / fps
    delta_text = ",".join(f"{d:.1f}" for d in window_deltas[:9])

    print(
        f"🎯 [scan-cut-relative] FINAL reason={reason} "
        f"stop_frame={stop_frame} stop={stop_sec:.3f}s "
        f"window_score={window_score:.2f} regions={window_regions} "
        f"window={a_frame}->{b_frame} deltas=[{delta_text}]",
        flush=True,
    )

    return stop_frame, stop_sec, window_score, window_regions, reason


# 기존 monkey patch가 전역 _rel_is_candidate / _rel_refine_boundary 이름을 참조하므로
# 여기서 재정의하면 다음 scan부터 바로 적용된다.

# === SCAN CUT RELATIVE DROP GUARD END ===


# === SCAN CUT STRONG WINDOW PATCH START ===

def _rel_strong_window_threshold(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_strong_window_threshold", 75.0))
    except Exception:
        return 75.0


def _rel_strong_window_regions_required(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(1, min(4, int(settings.get("scan_cut_strong_window_regions_required", 4))))
    except Exception:
        return 4


def _rel_is_candidate(self, score: float, baseline: float, previous_score: float) -> tuple[bool, str]:
    """
    후보 판정 v4.

    더 이상 relative_drop으로 멈추지 않는다.
    30프레임 window 변화량이 충분히 크고,
    fast4 영역 대부분이 같이 바뀔 때만 후보로 본다.
    """
    try:
        score = float(score)
    except Exception:
        return False, ""

    region_hits = int(getattr(self, "_scan_last_region_hits", 0) or 0)

    if score >= _rel_strong_window_threshold(self) and region_hits >= _rel_strong_window_regions_required(self):
        return True, "strong_window"

    return False, ""


def _rel_refine_boundary(self, start_frame: int, end_frame: int, fps: float, reason: str):
    """
    strong-window refine.

    24/12/6/3/1로 위치를 좁히되,
    최종 컷 인정 여부는 마지막 1프레임 delta가 아니라
    앞 단계 window 변화량이 충분히 강했는지로 판단한다.

    이유:
    - 페이드/디졸브는 한 프레임 delta가 작을 수 있음.
    - 33초 전환처럼 30프레임 window score가 90 이상이면 컷 후보로 인정해야 함.
    """
    try:
        fps = float(fps or self._current_frame_fps())
    except Exception:
        return None

    rollback = _rel_scan_rollback_frames(self)
    stages = _rel_scan_refine_stages(self)

    lo = max(0, min(int(start_frame), int(end_frame)) - rollback)
    hi = max(int(start_frame), int(end_frame)) + max(stages)

    best_frame = None
    best_score = -1.0
    best_regions = 0
    best_deltas = []

    strongest_window_score = -1.0
    strongest_window_regions = 0

    for stage in stages:
        stage = max(1, int(stage))
        mode = _rel_region_mode_for_stage(stage)

        local_best_frame = None
        local_best_score = -1.0
        local_best_regions = 0
        local_best_deltas = []

        step = max(1, stage // 2)
        f = int(lo)
        end = max(f + 1, int(hi))

        while f < end:
            sec_a = f / fps
            sec_b = (f + stage) / fps

            img_a = _rel_capture_image_at_global(self, sec_a, region_mode=mode)
            img_b = _rel_capture_image_at_global(self, sec_b, region_mode=mode)

            if img_a is not None and img_b is not None:
                score = _rel_image_delta(self, img_a, img_b)
                regions = int(getattr(self, "_scan_last_region_hits", 0) or 0)
                deltas = list(getattr(self, "_scan_last_region_deltas", []) or [])

                if score > local_best_score:
                    local_best_frame = f
                    local_best_score = score
                    local_best_regions = regions
                    local_best_deltas = deltas

            f += step

        if local_best_frame is None:
            continue

        best_frame = int(local_best_frame)
        best_score = float(local_best_score)
        best_regions = int(local_best_regions)
        best_deltas = list(local_best_deltas)

        # stage=1은 위치 보정용. 컷 인정 점수로 쓰지 않는다.
        if stage >= 3 and best_score > strongest_window_score:
            strongest_window_score = best_score
            strongest_window_regions = best_regions

        lo = max(0, best_frame - stage)
        hi = best_frame + stage

        delta_text = ",".join(f"{d:.1f}" for d in local_best_deltas[:9])
        print(
            f"🔍 [scan-cut-relative] REFINE stage={stage} mode={mode} "
            f"best_frame={best_frame} score={best_score:.2f} "
            f"regions={best_regions} range={lo}-{hi} deltas=[{delta_text}]",
            flush=True,
        )

    if best_frame is None:
        return None

    threshold = _rel_strong_window_threshold(self)
    required_regions = _rel_strong_window_regions_required(self)

    if strongest_window_score < threshold or strongest_window_regions < required_regions:
        print(
            f"⚠️ [scan-cut-relative] REJECT reason={reason} frame={best_frame} "
            f"window_score={strongest_window_score:.2f}/{threshold:.2f} "
            f"regions={strongest_window_regions}/{required_regions}",
            flush=True,
        )
        return None

    stop_frame = int(best_frame)
    stop_sec = stop_frame / fps

    delta_text = ",".join(f"{d:.1f}" for d in best_deltas[:9])
    print(
        f"🎯 [scan-cut-relative] FINAL reason=strong_window "
        f"stop_frame={stop_frame} stop={stop_sec:.3f}s "
        f"window_score={strongest_window_score:.2f} "
        f"regions={strongest_window_regions}/{required_regions} "
        f"last_score={best_score:.2f} deltas=[{delta_text}]",
        flush=True,
    )

    return stop_frame, stop_sec, strongest_window_score, strongest_window_regions, "strong_window"


# 기존 _rel_scan_cut_tick은 전역 _rel_is_candidate / _rel_refine_boundary 이름을 런타임에 참조하므로
# 여기서 재정의하면 다음 실행부터 바로 적용된다.

# === SCAN CUT STRONG WINDOW PATCH END ===


# === SCAN CUT RESUME AFTER FOUND PATCH START ===

def _scan_resume_skip_seconds(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(0.2, min(5.0, float(settings.get("scan_cut_resume_skip_seconds", 1.5))))
    except Exception:
        return 1.5


def _scan_duplicate_found_window_frames(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(1, min(180, int(settings.get("scan_cut_duplicate_found_window_frames", 18))))
    except Exception:
        return 18


_scan_original_show_cut_thumbnail = getattr(EditorTimelineVideoMixin, "_scan_show_cut_thumbnail", None)
_scan_original_on_scan_cut_requested = getattr(EditorTimelineVideoMixin, "_on_scan_cut_requested", None)


def _scan_show_cut_thumbnail_with_resume(self, global_sec: float) -> None:
    """
    컷 발견 후:
    - 화면은 컷 위치 썸네일을 보여준다.
    - 다음 탐색 시작점은 컷 뒤쪽으로 넘겨 저장한다.
    """
    try:
        fps = self._current_frame_fps()
        cut_sec = self._snap_to_frame(float(global_sec))
        cut_frame = int(round(cut_sec * fps))
        skip_frames = max(1, int(round(_scan_resume_skip_seconds(self) * fps)))
        resume_frame = cut_frame + skip_frames
        resume_sec = self._snap_to_frame(resume_frame / fps)

        self._scan_last_found_cut_frame = cut_frame
        self._scan_last_found_cut_sec = cut_sec
        self._scan_resume_after_cut_frame = resume_frame
        self._scan_resume_after_cut_sec = resume_sec

        print(
            f"⏭️ [scan-cut] next search will resume after found cut "
            f"cut={cut_frame} {cut_sec:.3f}s "
            f"resume={resume_frame} {resume_sec:.3f}s "
            f"skip={skip_frames}f",
            flush=True,
        )
    except Exception:
        pass

    if callable(_scan_original_show_cut_thumbnail):
        return _scan_original_show_cut_thumbnail(self, global_sec)


def _on_scan_cut_requested_resume_safe(self, direction: int):
    """
    같은 디졸브/페이드 경계를 반복해서 찾지 않도록,
    현재 플레이헤드가 직전에 찾은 컷 근처면 다음 탐색 시작점을 컷 뒤로 넘긴다.
    """
    try:
        direction_i = 1 if int(direction) > 0 else -1
    except Exception:
        direction_i = 1

    # 이미 탐색 중이면 기존 cancel/toggle 동작 유지
    try:
        state = getattr(self, "_scan_cut_state", None)
        timer = getattr(self, "_scan_cut_timer", None)
        if state and timer is not None and timer.isActive():
            if callable(_scan_original_on_scan_cut_requested):
                return _scan_original_on_scan_cut_requested(self, direction)
    except Exception:
        pass

    try:
        fps = self._current_frame_fps()
        current_sec = float(getattr(getattr(self, "timeline", None).canvas, "playhead_sec", 0.0) or 0.0)
        current_frame = int(round(current_sec * fps))

        last_frame = getattr(self, "_scan_last_found_cut_frame", None)
        resume_frame = getattr(self, "_scan_resume_after_cut_frame", None)

        if direction_i > 0 and last_frame is not None and resume_frame is not None:
            window = _scan_duplicate_found_window_frames(self)

            # 현재 위치가 방금 찾은 컷 근처면 다음 탐색 시작점을 뒤로 넘긴다.
            if abs(current_frame - int(last_frame)) <= window:
                resume_sec = self._snap_to_frame(int(resume_frame) / fps)

                print(
                    f"⏭️ [scan-cut] skip duplicate dissolve boundary "
                    f"current={current_frame} last={int(last_frame)} "
                    f"start_next={int(resume_frame)} {resume_sec:.3f}s",
                    flush=True,
                )

                try:
                    self._reset_playhead_smoothing(resume_sec)
                except Exception:
                    pass

                try:
                    if hasattr(self, "timeline"):
                        self.timeline.set_playhead(resume_sec)
                except Exception:
                    pass

                try:
                    if hasattr(self, "_scan_preview_global_sec"):
                        self._scan_preview_global_sec(resume_sec)
                except Exception:
                    pass
    except Exception as exc:
        print(f"⚠️ [scan-cut] duplicate skip check failed: {exc}", flush=True)

    if callable(_scan_original_on_scan_cut_requested):
        return _scan_original_on_scan_cut_requested(self, direction)


EditorTimelineVideoMixin._scan_show_cut_thumbnail = _scan_show_cut_thumbnail_with_resume
EditorTimelineVideoMixin._on_scan_cut_requested = _on_scan_cut_requested_resume_safe

# === SCAN CUT RESUME AFTER FOUND PATCH END ===
