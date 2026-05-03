# Version: 03.13.02
# Phase: PHASE2
"""Cut-boundary topicless segment patch installers for PipelineHelpersMixin."""

import os

from core.runtime.logger import get_logger


def install_topicless_segment_helpers(PipelineHelpersMixin):
    # === PIPELINE FULL TOPICLESS FRAME SPLIT START ===

    def _pipeline_topicless_middle_label(index: int) -> str:
        try:
            index = max(1, int(index))
        except Exception:
            index = 1

        letters = ""
        while index:
            index, rem = divmod(index - 1, 26)
            letters = chr(65 + rem) + letters
        return letters


    def _pipeline_topicless_fps_from_detected(self, detected, files=None, default: float = 30.0) -> float:
        from core.frame_time import normalize_fps

        for row in list(detected or []):
            if not isinstance(row, dict):
                continue
            for key in ("fps", "frame_rate", "timeline_frame_rate"):
                try:
                    value = float(row.get(key) or 0.0)
                    if value > 1.0:
                        return normalize_fps(value)
                except Exception:
                    pass

        # 컷이 아직 없어도 원본 영상 fps를 사용
        try:
            from core.media_info import probe_media
            for path in list(files or []):
                info = probe_media(path)
                fps = float(info.get("fps", 0.0) or 0.0)
                if fps > 1.0:
                    return normalize_fps(fps)
        except Exception:
            pass

        return normalize_fps(default)


    def _pipeline_topicless_frame_from_row(row, fps: float) -> int | None:
        from core.frame_time import sec_to_frame

        if isinstance(row, dict):
            for key in ("timeline_frame", "frame", "start_frame", "timeline_start_frame"):
                try:
                    value = row.get(key)
                    if value is not None:
                        frame = int(value)
                        if frame > 0:
                            return frame
                except Exception:
                    pass

            for key in ("timeline_sec", "time", "start", "timeline_start"):
                try:
                    sec = float(row.get(key) or 0.0)
                    if sec > 0.0:
                        return sec_to_frame(sec, fps)
                except Exception:
                    pass

        return None


    def _pipeline_topicless_row(index: int, start_frame: int, end_frame: int, fps: float) -> dict:
        from core.frame_time import frame_to_sec

        start_frame = max(0, int(start_frame))
        end_frame = max(start_frame, int(end_frame))

        start = frame_to_sec(start_frame, fps)
        end = frame_to_sec(end_frame, fps)

        major_label = _pipeline_topicless_middle_label(index)
        internal_id = f"cut_topicless_middle_{major_label}"

        return {
            "id": major_label,
            "segment_id": major_label,
            "chapter_id": major_label,
            "major_id": major_label,

            "internal_id": internal_id,
            "source_id": internal_id,

            "fps": fps,
            "frame_rate": fps,
            "timeline_frame_rate": fps,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "timeline_start_frame": start_frame,
            "timeline_end_frame": end_frame,
            "frame_range": {
                "unit": "frame",
                "start": start_frame,
                "end": end_frame,
                "timeline_frame_rate": fps,
            },

            "start": start,
            "end": end,
            "timeline_start": start,
            "timeline_end": end,

            "title": "주제없음",
            "name": "주제없음",
            "display_title": f"{major_label} 주제없음",
            "display_name": f"{major_label} 주제없음",
            "label": f"{major_label} 주제없음",

            "summary": "컷 경계 기반으로 자동 생성된 임시 중분류 세그먼트입니다.",
            "llm_summary": "",

            "tags": ["컷경계", "주제없음"],
            "source": "cut_boundary",
            "story_role": "topicless_placeholder",
            "narrative_function": "cut_boundary_placeholder",

            "level": "middle",
            "segment_type": "middle",
            "roughcut_level": "middle",
            "category": "middle",
            "is_middle_segment": True,

            "is_topicless_placeholder": True,
            "is_cut_boundary_placeholder": True,
            "topicless": True,

            "color_role": "topicless",
            "display_color": "gray",
            "ui_color": "gray",
            "color": "#9CA3AF",

            "needs_review": True,
            "status": "needs_review",
            "safety": "acceptable",
            "importance": 0.0,
            "importance_score": 0.0,
            "boundary_confidence": 1.0,

            "can_move": True,
            "can_trim": True,
            "can_remove": True,
            "move_risk": "low",
            "dependencies": [],
        }


    def _patched_build_cut_boundary_topicless_rows(self, detected, *, files=None, done: bool = False) -> list[dict]:
        """
        컷 경계 기반 회색 주제없음 중분류 rows 생성.

        컷 경계 체크 ON이면:
        - detected가 비어도 전체 A 주제없음 생성
        - detected가 늘어나면 frame 기준으로 A/B/C split
        """
        from core.frame_time import sec_to_frame

        fps = _pipeline_topicless_fps_from_detected(self, detected, files=files)

        duration = self._cut_boundary_placeholder_duration(files)
        duration_frame = 0
        try:
            if duration > 0.0:
                duration_frame = sec_to_frame(float(duration), fps)
        except Exception:
            duration_frame = 0

        cut_frames = []
        for row in list(detected or []):
            frame = _pipeline_topicless_frame_from_row(row, fps)
            if frame is not None and frame > 0:
                cut_frames.append(int(frame))

        cut_frames = sorted(set(cut_frames))

        # 컷이 아직 없어도 전체 A 생성
        if not cut_frames:
            if duration_frame > 0:
                return [_pipeline_topicless_row(1, 0, duration_frame, fps)]
            return []

        boundary_frames = [0] + cut_frames

        # duration을 알면 마지막 컷~영상끝 구간도 항상 생성
        if duration_frame > boundary_frames[-1]:
            boundary_frames.append(duration_frame)

        rows = []
        for i in range(len(boundary_frames) - 1):
            start_frame = int(boundary_frames[i])
            end_frame = int(boundary_frames[i + 1])
            if end_frame <= start_frame:
                continue
            rows.append(_pipeline_topicless_row(i + 1, start_frame, end_frame, fps))

        return rows


    PipelineHelpersMixin._build_cut_boundary_topicless_rows = _patched_build_cut_boundary_topicless_rows

    # === PIPELINE FULL TOPICLESS FRAME SPLIT END ===


    # === PIPELINE TOPICLESS SPLIT LOG PATCH START ===

    def _pipeline_topicless_split_log_emit(message: str) -> None:
        try:
            get_logger().log(message)
        except Exception:
            try:
                print(message, flush=True)
            except Exception:
                pass


    def _pipeline_topicless_split_row_meta(row: dict) -> tuple[str, int, int, float, float, float]:
        try:
            label = str(row.get("major_id") or row.get("segment_id") or row.get("id") or "?")
        except Exception:
            label = "?"

        try:
            fps = float(row.get("fps", row.get("frame_rate", row.get("timeline_frame_rate", 30.0))) or 30.0)
        except Exception:
            fps = 30.0

        try:
            start_frame = int(row.get("timeline_start_frame", row.get("start_frame")))
        except Exception:
            try:
                start_frame = int(round(float(row.get("start", row.get("timeline_start", 0.0)) or 0.0) * fps))
            except Exception:
                start_frame = 0

        try:
            end_frame = int(row.get("timeline_end_frame", row.get("end_frame")))
        except Exception:
            try:
                end_frame = int(round(float(row.get("end", row.get("timeline_end", 0.0)) or 0.0) * fps))
            except Exception:
                end_frame = start_frame

        try:
            start_sec = float(row.get("start", row.get("timeline_start", start_frame / fps)) or 0.0)
        except Exception:
            start_sec = start_frame / fps

        try:
            end_sec = float(row.get("end", row.get("timeline_end", end_frame / fps)) or 0.0)
        except Exception:
            end_sec = end_frame / fps

        return label, start_frame, end_frame, start_sec, end_sec, fps


    def _pipeline_log_topicless_split_rows(rows, *, context: str = "pipeline") -> None:
        return


    _pipeline_original_force_cut_boundary_topicless_segments_to_project = (
        PipelineHelpersMixin._force_cut_boundary_topicless_segments_to_project
    )


    def _patched_force_cut_boundary_topicless_segments_to_project_with_log(
        self,
        project_path: str,
        detected,
        *,
        files=None,
        done: bool = False,
    ):
        rows = _pipeline_original_force_cut_boundary_topicless_segments_to_project(
            self,
            project_path,
            detected,
            files=files,
            done=done,
        )

        try:
            _pipeline_log_topicless_split_rows(
                rows,
                context=f"force-save done={bool(done)} cuts={len(list(detected or []))}",
            )
        except Exception as exc:
            try:
                get_logger().log(f"  ⚠️ [컷 경계] split 로그 실패: {exc}")
            except Exception:
                pass

        return rows


    PipelineHelpersMixin._force_cut_boundary_topicless_segments_to_project = (
        _patched_force_cut_boundary_topicless_segments_to_project_with_log
    )

    # === PIPELINE TOPICLESS SPLIT LOG PATCH END ===


    # === PIPELINE VIDEO FPS TOPICLESS OVERRIDE START ===

    def _pipeline_video_fps_from_files(files=None, default: float = 30.0) -> float:
        from core.frame_time import normalize_fps

        try:
            default = normalize_fps(float(default or 30.0))
        except Exception:
            default = 30.0

        try:
            from core.media_info import probe_media
            for path in list(files or []):
                if not path or not os.path.exists(str(path)):
                    continue
                info = probe_media(str(path))
                fps = float(info.get("fps", 0.0) or 0.0)
                if fps > 1.0:
                    return normalize_fps(fps)
        except Exception:
            pass

        return default


    def _pipeline_topicless_fps_from_detected(self, detected=None, files=None, default: float = 30.0) -> float:
        from core.frame_time import normalize_fps

        # 1) detected row fps
        for row in list(detected or []):
            if not isinstance(row, dict):
                continue

            for key in ("fps", "frame_rate", "timeline_frame_rate", "source_fps", "video_fps"):
                try:
                    fps = float(row.get(key) or 0.0)
                    if fps > 1.0:
                        return normalize_fps(fps)
                except Exception:
                    pass

            # 2) row source_path probe
            try:
                path = str(row.get("source_path", "") or row.get("clip_file", "") or "")
            except Exception:
                path = ""
            if path:
                fps = _pipeline_video_fps_from_files([path], default=default)
                if abs(float(fps) - float(default)) > 0.001 or fps > 30.1:
                    return fps

        # 3) current files probe
        return _pipeline_video_fps_from_files(files, default=default)


    def _pipeline_topicless_middle_label(index: int) -> str:
        try:
            index = max(1, int(index))
        except Exception:
            index = 1

        letters = ""
        while index:
            index, rem = divmod(index - 1, 26)
            letters = chr(65 + rem) + letters
        return letters


    def _pipeline_topicless_frame_from_row(row, fps: float) -> int | None:
        from core.frame_time import sec_to_frame

        if isinstance(row, dict):
            for key in ("timeline_frame", "frame", "start_frame", "timeline_start_frame"):
                try:
                    value = row.get(key)
                    if value is not None:
                        frame = int(value)
                        if frame > 0:
                            return frame
                except Exception:
                    pass

            for key in ("timeline_sec", "time", "start", "timeline_start"):
                try:
                    sec = float(row.get(key) or 0.0)
                    if sec > 0.0:
                        return sec_to_frame(sec, fps)
                except Exception:
                    pass

        return None


    def _pipeline_topicless_row(index: int, start_frame: int, end_frame: int, fps: float) -> dict:
        from core.frame_time import frame_to_sec

        start_frame = max(0, int(start_frame))
        end_frame = max(start_frame, int(end_frame))

        start = frame_to_sec(start_frame, fps)
        end = frame_to_sec(end_frame, fps)

        major_label = _pipeline_topicless_middle_label(index)
        internal_id = f"cut_topicless_middle_{major_label}"

        return {
            "id": major_label,
            "segment_id": major_label,
            "chapter_id": major_label,
            "major_id": major_label,

            "internal_id": internal_id,
            "source_id": internal_id,

            "fps": fps,
            "frame_rate": fps,
            "timeline_frame_rate": fps,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "timeline_start_frame": start_frame,
            "timeline_end_frame": end_frame,
            "frame_range": {
                "unit": "frame",
                "start": start_frame,
                "end": end_frame,
                "timeline_frame_rate": fps,
            },

            "start": start,
            "end": end,
            "timeline_start": start,
            "timeline_end": end,

            "title": "주제없음",
            "name": "주제없음",
            "display_title": f"{major_label} 주제없음",
            "display_name": f"{major_label} 주제없음",
            "label": f"{major_label} 주제없음",

            "summary": "컷 경계 기반으로 자동 생성된 임시 중분류 세그먼트입니다.",
            "llm_summary": "",

            "tags": ["컷경계", "주제없음"],
            "source": "cut_boundary",
            "story_role": "topicless_placeholder",
            "narrative_function": "cut_boundary_placeholder",

            "level": "middle",
            "segment_type": "middle",
            "roughcut_level": "middle",
            "category": "middle",
            "is_middle_segment": True,

            "is_topicless_placeholder": True,
            "is_cut_boundary_placeholder": True,
            "topicless": True,

            "color_role": "topicless",
            "display_color": "gray",
            "ui_color": "gray",
            "color": "#9CA3AF",

            "needs_review": True,
            "status": "needs_review",
            "safety": "acceptable",
            "importance": 0.0,
            "importance_score": 0.0,
            "boundary_confidence": 1.0,

            "can_move": True,
            "can_trim": True,
            "can_remove": True,
            "move_risk": "low",
            "dependencies": [],
        }


    def _patched_build_cut_boundary_topicless_rows(self, detected, *, files=None, done: bool = False) -> list[dict]:
        from core.frame_time import sec_to_frame

        fps = _pipeline_topicless_fps_from_detected(self, detected, files=files)

        duration = self._cut_boundary_placeholder_duration(files)
        duration_frame = 0
        try:
            if duration > 0.0:
                duration_frame = sec_to_frame(float(duration), fps)
        except Exception:
            duration_frame = 0

        cut_frames = []
        for row in list(detected or []):
            frame = _pipeline_topicless_frame_from_row(row, fps)
            if frame is not None and frame > 0:
                cut_frames.append(int(frame))

        cut_frames = sorted(set(cut_frames))

        # 컷이 없어도 전체 A 생성
        if not cut_frames:
            if duration_frame > 0:
                rows = [_pipeline_topicless_row(1, 0, duration_frame, fps)]
            else:
                rows = []
        else:
            boundaries = [0] + cut_frames
            if duration_frame > boundaries[-1]:
                boundaries.append(duration_frame)

            rows = []
            for i in range(len(boundaries) - 1):
                start_frame = int(boundaries[i])
                end_frame = int(boundaries[i + 1])
                if end_frame <= start_frame:
                    continue
                rows.append(_pipeline_topicless_row(i + 1, start_frame, end_frame, fps))

        try:
            current_keys = [
                (
                    str(row.get("major_id") or ""),
                    int(row.get("timeline_start_frame") or 0),
                    int(row.get("timeline_end_frame") or 0),
                )
                for row in rows
            ]
            previous_keys = list(getattr(self, "_cut_boundary_topicless_logged_keys", []) or [])

            should_reset = False
            if not previous_keys:
                should_reset = True
            elif len(current_keys) < len(previous_keys):
                should_reset = True
            elif current_keys:
                prev_first = previous_keys[0] if previous_keys else None
                prev_last = previous_keys[-1] if previous_keys else None
                if prev_first != current_keys[0] or prev_last != current_keys[-1]:
                    should_reset = True

            if should_reset:
                previous_seen = set()
            else:
                previous_seen = set(previous_keys)

            new_rows = []
            for row, key in zip(rows, current_keys):
                if key not in previous_seen:
                    new_rows.append(row)

            setattr(self, "_cut_boundary_topicless_logged_keys", current_keys)

            for row in new_rows:
                get_logger().log(
                    f"  ▒ [컷 경계] split {row.get('major_id')} {row.get('title')} "
                    f"frame={row.get('timeline_start_frame')}->{row.get('timeline_end_frame')} "
                    f"time={float(row.get('timeline_start', 0.0) or 0.0):.3f}s->{float(row.get('timeline_end', 0.0) or 0.0):.3f}s "
                    f"fps={fps:.3f}"
                )
        except Exception:
            pass

        return rows


    PipelineHelpersMixin._build_cut_boundary_topicless_rows = _patched_build_cut_boundary_topicless_rows

    # === PIPELINE VIDEO FPS TOPICLESS OVERRIDE END ===
