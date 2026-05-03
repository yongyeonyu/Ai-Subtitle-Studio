# Version: 03.13.04
# Phase: PHASE2
"""Core scan-cut helpers for the editor timeline/video mixin."""

from __future__ import annotations

import json
import os
from datetime import datetime

from PyQt6.QtCore import QTimer

from core.cut_boundary import sync_project_cut_boundaries


class EditorScanCutCoreMixin:
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
        if not times:
            self._auto_cut_boundary_scan_lines = []
            timeline = getattr(self, "timeline", None)
            if timeline is not None and hasattr(timeline, "set_scan_boundary_times"):
                timeline.set_scan_boundary_times([])
            return

        def _normalise_row(item):
            if isinstance(item, dict):
                row = dict(item)
                try:
                    sec = self._snap_to_frame(float(row.get("timeline_sec", row.get("time", row.get("start", 0.0))) or 0.0))
                except Exception:
                    return None
                if sec <= 0.0:
                    return None
                row["timeline_sec"] = sec
                row["time"] = sec
                row["status"] = str(row.get("status", "") or "provisional").lower()
                return row
            try:
                sec = self._snap_to_frame(float(item or 0.0))
            except Exception:
                return None
            if sec <= 0.0:
                return None
            return {"timeline_sec": sec, "time": sec, "status": "provisional"}

        cleaned = []
        for item in list(times or []):
            row = _normalise_row(item)
            if row is not None:
                cleaned.append(row)
        try:
            merged = []

            def _is_verified_row(row) -> bool:
                status = str(row.get("status", "") or "").lower()
                return status in {"verified", "confirmed"} or bool(row.get("verified"))

            def _status_rank(row):
                return 2 if _is_verified_row(row) else 1

            def _upsert(row):
                sec = float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0)
                if sec <= 0.0:
                    return
                match_idx = None
                for idx, old in enumerate(merged):
                    old_sec = float(old.get("timeline_sec", old.get("time", 0.0)) or 0.0)
                    if abs(old_sec - sec) <= 0.055:
                        match_idx = idx
                        break
                if match_idx is None:
                    merged.append(row)
                    return
                old = merged[match_idx]
                if _status_rank(row) >= _status_rank(old):
                    # Once a candidate is verified, later provisional scan updates must not
                    # turn the visual marker back into the teal "unchecked" state.
                    if _status_rank(old) > _status_rank(row):
                        return
                    merged[match_idx] = {**old, **row}

            for item in list(getattr(self, "_auto_cut_boundary_scan_lines", []) or []):
                row = _normalise_row(item)
                if row is not None:
                    _upsert(row)
            for row in cleaned:
                _upsert(row)

            dedup = {}
            for row in merged:
                key = round(float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0), 3)
                old = dedup.get(key)
                if old is None:
                    dedup[key] = row
                    continue
                if _status_rank(row) >= _status_rank(old):
                    dedup[key] = row
            cleaned = [dedup[key] for key in sorted(dedup.keys()) if key > 0.0]
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
