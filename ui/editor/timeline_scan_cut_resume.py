# Version: 03.13.05
# Phase: PHASE2
"""Scan-cut resume-after-found patch installer."""

from __future__ import annotations


def install_scan_cut_resume_patch(EditorTimelineVideoMixin):
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
