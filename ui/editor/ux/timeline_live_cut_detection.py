# Version: 03.14.03
# Phase: PHASE2
"""Live cut-boundary detection helpers for subtitle segment dragging."""

from __future__ import annotations

import os
import time

try:
    from core.native_cut_boundary import live_cut_scores as _native_live_cut_scores
except Exception:  # pragma: no cover - optional native extension.
    _native_live_cut_scores = None


class TimelineLiveCutDetectionMixin:
    def _detect_live_cut_boundary_record(
        self,
        media_path: str,
        local_sec: float,
        fps: float,
        *,
        direction: int = 1,
        search_start_local_sec: float | None = None,
        search_end_local_sec: float | None = None,
    ) -> dict | None:
        media_path = os.path.abspath(os.path.expanduser(str(media_path or "")))
        if not media_path or not os.path.exists(media_path):
            return None
        fps = max(1.0, float(fps or self._get_fps()))
        target_local_sec = max(0.0, float(local_sec or 0.0))
        target_frame = max(1, int(round(target_local_sec * fps)))
        if search_start_local_sec is None or search_end_local_sec is None:
            search_start_local_sec, search_end_local_sec = self._live_cut_search_window_secs(target_local_sec, direction)
        search_start_local_sec = max(0.0, float(search_start_local_sec or 0.0))
        search_end_local_sec = max(search_start_local_sec, float(search_end_local_sec or search_start_local_sec))
        search_start_frame = max(0, int(round(search_start_local_sec * fps)))
        search_end_frame = max(search_start_frame + 2, int(round(search_end_local_sec * fps)))
        cache = getattr(self, "_live_cut_snap_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._live_cut_snap_cache = cache

        for payload in list(cache.values()):
            if not isinstance(payload, dict):
                continue
            if payload.get("path") != media_path:
                continue
            try:
                payload_fps = float(payload.get("fps", fps) or fps)
                first_frame = int(payload.get("first_frame", -1))
                last_frame = int(payload.get("last_frame", -1))
            except Exception:
                continue
            if abs(payload_fps - fps) > 0.01:
                continue
            if first_frame <= search_start_frame and last_frame >= search_end_frame:
                window_scores = self._filter_live_cut_scores(
                    payload.get("scores"),
                    search_start_frame,
                    search_end_frame,
                )
                candidates = self._live_cut_candidates_from_scores(window_scores, fps)
                if candidates:
                    return min(
                        candidates,
                        key=lambda item: (
                            abs(int(item.get("frame", target_frame)) - target_frame),
                            -float(item.get("score", 0.0) or 0.0),
                        ),
                    )
                return None

        now = time.monotonic()
        last_compute = float(getattr(self, "_live_cut_snap_last_compute_mono", 0.0) or 0.0)
        if now - last_compute < 0.024:
            return None
        self._live_cut_snap_last_compute_mono = now

        bucket_frames = max(1, int(round(fps * 0.50)))
        base_pad_frames = max(bucket_frames, int(round(fps * 0.50)))
        forward_pad_frames = max(base_pad_frames, int(round(fps * 1.50)))
        if int(direction) < 0:
            scan_start_frame = max(0, search_start_frame - forward_pad_frames)
            scan_end_frame = max(search_end_frame + base_pad_frames, scan_start_frame + 2)
        else:
            scan_start_frame = max(0, search_start_frame - base_pad_frames)
            scan_end_frame = max(search_end_frame + forward_pad_frames, scan_start_frame + 2)
        key = (
            media_path,
            round(fps, 3),
            scan_start_frame // bucket_frames,
            scan_end_frame // bucket_frames,
        )
        payload = cache.get(key)
        if not isinstance(payload, dict) or int(payload.get("first_frame", -1)) > search_start_frame or int(payload.get("last_frame", -1)) < search_end_frame:
            scores = self._compute_live_cut_boundary_scores(
                media_path,
                scan_start_frame,
                scan_end_frame,
                fps,
            )
            payload = {
                "path": media_path,
                "fps": fps,
                "first_frame": scan_start_frame,
                "last_frame": scan_end_frame,
                "scores": scores,
                "search_start_local_sec": search_start_local_sec,
                "search_end_local_sec": search_end_local_sec,
            }
            cache[key] = payload

        window_scores = self._filter_live_cut_scores(
            payload.get("scores") if isinstance(payload, dict) else [],
            search_start_frame,
            search_end_frame,
        )
        candidates = self._live_cut_candidates_from_scores(window_scores, fps)
        payload = {
            **(payload if isinstance(payload, dict) else {}),
            "last_candidates": candidates,
        }
        cache[key] = payload
        if len(cache) > 160:
            try:
                cache.pop(next(iter(cache)))
            except (StopIteration, RuntimeError, TypeError):
                pass
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda item: (
                abs(int(item.get("frame", target_frame)) - target_frame),
                -float(item.get("score", 0.0) or 0.0),
            ),
        )

    def _filter_live_cut_scores(self, scored, start_frame: int, end_frame: int) -> list[tuple[float, int]]:
        filtered: list[tuple[float, int]] = []
        for item in list(scored or []):
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            try:
                score = float(item[0])
                frame_no = int(item[1])
            except (TypeError, ValueError):
                continue
            if int(start_frame) <= frame_no <= int(end_frame):
                filtered.append((score, frame_no))
        return filtered

    def _live_cut_snap_capture(self, media_path: str, cv2_mod):
        record = getattr(self, "_live_cut_snap_capture_record", None)
        if isinstance(record, dict) and record.get("path") == media_path:
            cap = record.get("cap")
            try:
                if cap is not None and cap.isOpened():
                    return cap
            except (RuntimeError, AttributeError, TypeError):
                pass
        if isinstance(record, dict):
            old_cap = record.get("cap")
            try:
                if old_cap is not None:
                    old_cap.release()
            except (RuntimeError, AttributeError, TypeError):
                pass
            self._live_cut_snap_thumb_cache = {}
        cap = cv2_mod.VideoCapture(media_path)
        try:
            opened = bool(cap.isOpened())
        except (RuntimeError, AttributeError, TypeError):
            opened = False
        if not opened:
            try:
                cap.release()
            except (RuntimeError, AttributeError, TypeError):
                pass
            self._live_cut_snap_capture_record = None
            return None
        self._live_cut_snap_capture_record = {"path": media_path, "cap": cap}
        return cap

    def _live_cut_candidates_from_scores(self, scored: list[tuple[float, int]], fps: float) -> list[dict]:
        clean_scores: list[tuple[float, int]] = []
        for score, frame_no in list(scored or []):
            try:
                clean_scores.append((float(score), int(frame_no)))
            except Exception:
                continue
        if not clean_scores:
            return []

        values = sorted(float(score) for score, _frame in clean_scores)
        mid = len(values) // 2
        if len(values) % 2:
            median_score = values[mid]
        else:
            median_score = (values[mid - 1] + values[mid]) / 2.0
        threshold = max(12.0, median_score + 7.0)
        strong_scored = [(float(score), int(frame_no)) for score, frame_no in clean_scores if float(score) >= threshold]
        if not strong_scored:
            top_score, top_frame = max(clean_scores, key=lambda item: item[0])
            if float(top_score) >= 18.0:
                strong_scored.append((float(top_score), int(top_frame)))
        if not strong_scored:
            return []

        cluster_gap = max(1, int(round(max(1.0, float(fps or 30.0)) * 0.04)))
        strong_scored.sort(key=lambda item: item[1])
        clustered: list[tuple[float, int]] = []
        cluster_scores: list[tuple[float, int]] = []
        for score, frame_no in strong_scored:
            if not cluster_scores or frame_no - cluster_scores[-1][1] <= cluster_gap:
                cluster_scores.append((score, frame_no))
                continue
            clustered.append(max(cluster_scores, key=lambda item: item[0]))
            cluster_scores = [(score, frame_no)]
        if cluster_scores:
            clustered.append(max(cluster_scores, key=lambda item: item[0]))

        candidates: list[dict] = []
        for score, frame_no in clustered:
            candidates.append(
                {
                    "local_sec": self._snap_to_frame(frame_no / max(1.0, float(fps or 30.0))),
                    "frame": int(frame_no),
                    "score": round(float(score), 3),
                    "median_score": round(float(median_score), 3),
                    "score_margin": round(float(score) - float(median_score), 3),
                    "score_ratio": round(float(score) / max(1.0, float(median_score)), 3),
                }
            )
        return candidates

    def _compute_live_cut_boundary_scores(
        self,
        media_path: str,
        search_start_frame: int,
        search_end_frame: int,
        fps: float,
    ) -> list[tuple[float, int]]:
        try:
            import cv2  # type: ignore
        except Exception:
            return []

        cap = self._live_cut_snap_capture(media_path, cv2)
        if cap is None:
            return []

        first_frame = max(0, int(search_start_frame))
        last_frame = max(first_frame + 2, int(search_end_frame))

        def _thumb(frame):
            if frame is None:
                return None
            try:
                height, width = frame.shape[:2]
                if height <= 0 or width <= 0:
                    return None
                target_w = 96
                target_h = max(18, min(54, int(round(height * target_w / max(1, width)))))
                small = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                return gray, small
            except Exception:
                return None

        thumb_cache = getattr(self, "_live_cut_snap_thumb_cache", None)
        if not isinstance(thumb_cache, dict):
            thumb_cache = {}
            self._live_cut_snap_thumb_cache = thumb_cache

        frames_by_no: dict[int, tuple[object, object]] = {}
        missing_ranges: list[tuple[int, int]] = []
        missing_start: int | None = None
        for frame_no in range(first_frame, last_frame + 1):
            cached = thumb_cache.get((media_path, frame_no))
            if cached is not None:
                frames_by_no[frame_no] = cached
                if missing_start is not None:
                    missing_ranges.append((missing_start, frame_no - 1))
                    missing_start = None
                continue
            if missing_start is None:
                missing_start = frame_no
        if missing_start is not None:
            missing_ranges.append((missing_start, last_frame))

        for range_start, range_end in missing_ranges:
            try:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(range_start))
            except Exception:
                continue
            for frame_no in range(int(range_start), int(range_end) + 1):
                ok, frame = cap.read()
                if not ok:
                    break
                item = _thumb(frame)
                if item is None:
                    continue
                gray, color = item
                pair = (gray, color)
                frames_by_no[frame_no] = pair
                thumb_cache[(media_path, frame_no)] = pair

        if len(thumb_cache) > 360:
            overflow = len(thumb_cache) - 360
            for key in list(thumb_cache.keys())[:overflow]:
                try:
                    thumb_cache.pop(key, None)
                except Exception:
                    pass

        frames: list[tuple[int, object, object]] = [
            (frame_no, item[0], item[1])
            for frame_no, item in sorted(frames_by_no.items())
            if first_frame <= int(frame_no) <= last_frame
        ]
        if len(frames) < 3:
            return []

        frame_numbers = [int(frame_no) for frame_no, _gray, _color in frames]
        gray_frames = [gray for _frame_no, gray, _color in frames]
        color_frames = [color for _frame_no, _gray, color in frames]
        if _native_live_cut_scores is not None:
            native_scores = _native_live_cut_scores(gray_frames, color_frames, frame_numbers)
            if isinstance(native_scores, list):
                return [(float(score), int(frame_no)) for score, frame_no in native_scores]

        try:
            import numpy as np  # type: ignore
        except Exception:
            return []

        scored: list[tuple[float, int]] = []
        for prev, cur in zip(frames, frames[1:]):
            _prev_no, prev_gray, prev_color = prev
            cur_no, cur_gray, cur_color = cur
            try:
                gray_score = float(np.mean(np.abs(cur_gray.astype(np.int16) - prev_gray.astype(np.int16))))
                color_score = float(np.mean(np.abs(cur_color.astype(np.int16) - prev_color.astype(np.int16))))
                score = max(gray_score, color_score * 0.85)
            except Exception:
                continue
            scored.append((score, int(cur_no)))
        return scored

    def _compute_live_cut_boundary_candidates(
        self,
        media_path: str,
        search_start_frame: int,
        search_end_frame: int,
        fps: float,
    ) -> list[dict]:
        scores = self._compute_live_cut_boundary_scores(media_path, search_start_frame, search_end_frame, fps)
        return self._live_cut_candidates_from_scores(scores, fps)
