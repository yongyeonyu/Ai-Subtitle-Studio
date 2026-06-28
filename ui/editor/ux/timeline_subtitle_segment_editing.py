"""
Centralized subtitle-segment canvas editing helpers.

This module gathers the timeline behaviors that are specific to subtitle
segment editing so future canvas edit work lands in one place. The legacy
inline-edit mixin stays as the compatibility base, while this mixin layers
segment-resize/diamond/snap/drag/merge-preview behavior on top.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
import os
import threading
import time

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QCursor, QPolygon

from core.coerce import safe_float as _as_float
from core.native_swift_timeline import (
    build_subtitle_drag_snap_base_via_swift,
    compute_subtitle_merge_preview_via_swift,
)

try:
    from core.native_cut_boundary import live_cut_scores as _native_live_cut_scores
except Exception:  # pragma: no cover - optional native extension.
    _native_live_cut_scores = None

from ui.editor.editor_helpers import find_segment_at
from ui.editor.ux.timeline_live_cut_detection import TimelineLiveCutDetectionMixin
from ui.editor.ux.timeline_canvas_editing import (
    NEW_SUBTITLE_PLACEHOLDER,
    TimelineInlineEditMixin as _LegacyTimelineInlineEditMixin,
    apply_timing_drag as _legacy_apply_timing_drag,
)
from ui.timeline.timeline_constants import (
    DIAMOND_Y,
    HANDLE_R,
    SEG_BOT,
    SEG_TOP,
    SEGMENT_HANDLE_MIN_WIDTH,
)


def _live_cut_candidates_from_scores_standalone(scored: list[tuple[float, int]], fps: float) -> list[dict]:
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
    median_score = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2.0
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

    return [
        {
            "local_sec": float(frame_no) / max(1.0, float(fps or 30.0)),
            "frame": int(frame_no),
            "score": round(float(score), 3),
            "median_score": round(float(median_score), 3),
            "score_margin": round(float(score) - float(median_score), 3),
            "score_ratio": round(float(score) / max(1.0, float(median_score)), 3),
        }
        for score, frame_no in clustered
    ]


def _select_live_cut_candidate_from_scores_standalone(
    scored: list[tuple[float, int]],
    fps: float,
    *,
    search_start_frame: int,
    search_end_frame: int,
    origin_frame: int,
    target_frame: int,
    direction: int,
) -> dict | None:
    candidates = _live_cut_candidates_from_scores_standalone(scored, fps)
    if not candidates:
        return None
    lo = min(int(search_start_frame), int(search_end_frame))
    hi = max(int(search_start_frame), int(search_end_frame))
    origin_exclusion_frames = max(2, int(round(max(1.0, float(fps or 30.0)) * 0.025)))
    filtered: list[dict] = []
    for item in candidates:
        try:
            frame_no = int(item.get("frame", -1))
        except Exception:
            continue
        if frame_no < lo or frame_no > hi:
            continue
        if int(direction) >= 0 and frame_no <= int(origin_frame) + origin_exclusion_frames:
            continue
        if int(direction) < 0 and frame_no >= int(origin_frame) - origin_exclusion_frames:
            continue
        filtered.append(item)
    if not filtered:
        return None
    return max(
        filtered,
        key=lambda item: (
            float(item.get("score", 0.0) or 0.0),
            -abs(int(item.get("frame", target_frame)) - int(target_frame)),
        ),
    )


def _open_live_cut_capture_standalone(media_path: str, cv2_mod, *, use_gpu: bool):
    if use_gpu and hasattr(cv2_mod, "CAP_PROP_HW_ACCELERATION"):
        try:
            params = [
                int(cv2_mod.CAP_PROP_HW_ACCELERATION),
                int(getattr(cv2_mod, "VIDEO_ACCELERATION_ANY", 1)),
            ]
            cap = cv2_mod.VideoCapture(media_path, int(getattr(cv2_mod, "CAP_FFMPEG", 0)), params)
            if cap is not None and cap.isOpened():
                return cap
            if cap is not None:
                cap.release()
        except Exception:
            pass
    return cv2_mod.VideoCapture(media_path)


def _compute_live_cut_boundary_scores_standalone(
    media_path: str,
    search_start_frame: int,
    search_end_frame: int,
    *,
    use_gpu: bool = True,
) -> list[tuple[float, int]]:
    try:
        import cv2  # type: ignore
    except Exception:
        return []

    try:
        import numpy as np  # type: ignore
    except Exception:
        np = None

    media_path = os.path.abspath(os.path.expanduser(str(media_path or "")))
    if not media_path or not os.path.exists(media_path):
        return []
    first_frame = max(0, int(search_start_frame))
    last_frame = max(first_frame + 2, int(search_end_frame))

    cap = _open_live_cut_capture_standalone(media_path, cv2, use_gpu=bool(use_gpu))
    try:
        if not cap or not cap.isOpened():
            return []
        if use_gpu:
            try:
                if bool(cv2.ocl.haveOpenCL()):
                    cv2.ocl.setUseOpenCL(True)
            except Exception:
                pass

        frames: list[tuple[int, object, object]] = []
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(first_frame))
        for frame_no in range(first_frame, last_frame + 1):
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            try:
                height, width = frame.shape[:2]
                if height <= 0 or width <= 0:
                    continue
                target_w = 96
                target_h = max(18, min(54, int(round(height * target_w / max(1, width)))))
                small = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                frames.append((int(frame_no), gray, small))
            except Exception:
                continue
        if len(frames) < 3:
            return []

        frame_numbers = [int(frame_no) for frame_no, _gray, _color in frames]
        gray_frames = [gray for _frame_no, gray, _color in frames]
        color_frames = [color for _frame_no, _gray, color in frames]
        if _native_live_cut_scores is not None:
            native_scores = _native_live_cut_scores(gray_frames, color_frames, frame_numbers)
            if isinstance(native_scores, list):
                return [(float(score), int(frame_no)) for score, frame_no in native_scores]

        if np is None:
            return []
        scored: list[tuple[float, int]] = []
        for prev, cur in zip(frames, frames[1:]):
            _prev_no, prev_gray, prev_color = prev
            cur_no, cur_gray, cur_color = cur
            try:
                gray_score = float(np.mean(np.abs(cur_gray.astype(np.int16) - prev_gray.astype(np.int16))))
                color_score = float(np.mean(np.abs(cur_color.astype(np.int16) - prev_color.astype(np.int16))))
                scored.append((max(gray_score, color_score * 0.85), int(cur_no)))
            except Exception:
                continue
        return scored
    finally:
        try:
            cap.release()
        except Exception:
            pass


class TimelineSubtitleSegmentEditingMixin(TimelineLiveCutDetectionMixin, _LegacyTimelineInlineEditMixin):
    def _clear_pending_center_drag(self) -> None:
        self._pending_center_drag_seg = None
        self._pending_center_drag_x = 0
        self._pending_center_drag_y = 0

    def _emit_smart_split_at_playhead(self):
        sec = self._snap_to_frame(self.playhead_sec)
        candidates = (
            self._visible_items_for_paint(self.segments, "segments", sec, sec, pad_sec=0.02)
            if hasattr(self, "_visible_items_for_paint")
            else self.segments
        )
        seg = find_segment_at([s for s in candidates if not self._is_stt_preview_segment(s)], sec, skip_gap=True)
        if not seg:
            return
        if sec <= seg["start"] + 0.05 or sec >= seg["end"] - 0.05:
            return
        mid = (seg["start"] + seg["end"]) / 2.0
        self.sig_smart_split.emit(seg.get("line", 0), float(sec), sec < mid)

    def _handle_polygon(self, bx: int, is_left: bool) -> QPolygon:
        cy = SEG_TOP + 32
        w = HANDLE_R
        hw = HANDLE_R // 2
        hh = 12
        th = 4
        if is_left:
            bx += 2
            return QPolygon([
                QPoint(bx, cy),
                QPoint(bx + hw, cy - hh),
                QPoint(bx + hw, cy - th),
                QPoint(bx + w, cy - th),
                QPoint(bx + w, cy + th),
                QPoint(bx + hw, cy + th),
                QPoint(bx + hw, cy + hh),
            ])
        bx -= 2
        return QPolygon([
            QPoint(bx, cy),
            QPoint(bx - hw, cy - hh),
            QPoint(bx - hw, cy - th),
            QPoint(bx - w, cy - th),
            QPoint(bx - w, cy + th),
            QPoint(bx - hw, cy + th),
            QPoint(bx - hw, cy + hh),
        ])

    def _handle_drag_at(self, x: int, y: int):
        point = QPoint(x, y)
        touch_slop = self._touch_hit_slop(HANDLE_R)
        desktop_slop = 3
        boundary_capture_slop = 2
        handle_vertical_pad = 4
        candidates = (
            self._segments_near_x_for_hit(x, pad_px=HANDLE_R + 8 + touch_slop)
            if hasattr(self, "_segments_near_x_for_hit")
            else self.segments
        )
        hits: list[tuple[tuple[int, int, int, int, int], dict, str]] = []

        def _append_hit(seg: dict, edge: str, boundary_x: int) -> None:
            is_active = self._is_active_segment(seg) if hasattr(self, "_is_active_segment") else (
                self.active_seg_start is not None
                and abs(float(seg.get("start", 0.0) or 0.0) - float(self.active_seg_start)) < 0.5
            )
            inside_bias = 0
            if edge == "square_left" and int(x) < int(boundary_x):
                inside_bias = 1
            elif edge == "square_right" and int(x) > int(boundary_x):
                inside_bias = 1
            score = (
                0 if is_active else 1,
                inside_bias,
                abs(int(x) - int(boundary_x)),
                0 if edge == "square_right" else 1,
                int(seg.get("line", 0) or 0),
            )
            hits.append((score, seg, edge))

        for seg in candidates:
            if self._is_stt_preview_segment(seg):
                continue
            is_active = self._is_active_segment(seg) if hasattr(self, "_is_active_segment") else (
                self.active_seg_start is not None
                and abs(float(seg.get("start", 0.0) or 0.0) - float(self.active_seg_start)) < 0.5
            )
            x1, x2 = self._x(seg["start"]), self._x(seg["end"])
            compact_width = x2 - x1 < SEGMENT_HANDLE_MIN_WIDTH
            if compact_width:
                cy = SEG_TOP + 32
                vertical_slop = max(HANDLE_R, touch_slop)
                near_left = abs(x - x1) <= HANDLE_R + 4 + touch_slop
                near_right = abs(x - x2) <= HANDLE_R + 4 + touch_slop
                if abs(y - cy) <= vertical_slop and (near_left or near_right):
                    if abs(x - x2) < abs(x - x1):
                        _append_hit(seg, "square_right", x2)
                    else:
                        _append_hit(seg, "square_left", x1)
                    continue
            if self._handle_polygon(x1, True).containsPoint(point, Qt.FillRule.OddEvenFill):
                _append_hit(seg, "square_left", x1)
            if self._handle_polygon(x2, False).containsPoint(point, Qt.FillRule.OddEvenFill):
                _append_hit(seg, "square_right", x2)
            cy = SEG_TOP + 32
            boundary_vertical_slop = HANDLE_R + handle_vertical_pad
            prev_seg = self._get_prev_seg(seg) if hasattr(self, "_get_prev_seg") else None
            prev_end = float(prev_seg.get("end", 0.0) or 0.0) if isinstance(prev_seg, dict) else None
            seg_start = float(seg.get("start", 0.0) or 0.0)
            no_shared_left_neighbor = prev_end is None or prev_end < (seg_start - 0.05)
            if no_shared_left_neighbor and abs(x - x1) <= boundary_capture_slop and abs(y - cy) <= boundary_vertical_slop:
                _append_hit(seg, "square_left", x1)
            extra_slop = touch_slop if touch_slop > 0 else (desktop_slop if is_active else 0)
            if extra_slop > 0:
                target_h = max(
                    HANDLE_R + handle_vertical_pad * 2,
                    self._current_responsive_profile().touch_target
                    if touch_slop > 0
                    else HANDLE_R + handle_vertical_pad * 2,
                )
                left_extra = max(extra_slop, 0)
                right_extra = max(extra_slop, 0)
                top = int(cy - (target_h / 2))
                left_rect = QRect(int(x1 - left_extra), top, int(HANDLE_R + left_extra + 6), target_h)
                right_rect = QRect(int(x2 - HANDLE_R - 6), top, int(HANDLE_R + right_extra + 6), target_h)
                if left_rect.contains(x, y):
                    _append_hit(seg, "square_left", x1)
                if right_rect.contains(x, y):
                    _append_hit(seg, "square_right", x2)
        if not hits:
            return None
        hits.sort(key=lambda item: item[0])
        _score, seg, edge = hits[0]
        return seg, edge

    def _handle_hover_at(self, x: int, y: int):
        hit = self._handle_drag_at(x, y)
        if not hit:
            return None
        seg, edge = hit
        return seg, "left" if edge == "square_left" else "right"

    def _center_drag_hit(self, seg: dict, x: int, y: int) -> bool:
        if not isinstance(seg, dict):
            return False
        if self._is_stt_preview_segment(seg) or not (SEG_TOP <= y <= SEG_BOT):
            return False
        x1, x2 = self._x(seg["start"]), self._x(seg["end"])
        if x <= x1 or x >= x2:
            return False
        width = max(1, x2 - x1)
        if width < SEGMENT_HANDLE_MIN_WIDTH:
            center_x = (x1 + x2) // 2
            return abs(int(x) - int(center_x)) <= max(3, width // 6)
        point = QPoint(x, y)
        if self._handle_polygon(x1, True).containsPoint(point, Qt.FillRule.OddEvenFill):
            return False
        if self._handle_polygon(x2, False).containsPoint(point, Qt.FillRule.OddEvenFill):
            return False
        edge_inset = 4 if width < SEGMENT_HANDLE_MIN_WIDTH else 8
        left = x1 + edge_inset
        right = x2 - edge_inset
        if right <= left:
            center_x = (x1 + x2) // 2
            return abs(int(x) - int(center_x)) <= max(2, width // 4)
        return left < x < right

    def _center_drag_candidate_at(self, x: int, y: int, *, active_only: bool = False):
        candidates = self._segments_near_x_for_hit(x, pad_px=20) if hasattr(self, "_segments_near_x_for_hit") else self.segments
        matches: list[tuple[tuple[int, int, int], dict]] = []
        for seg in candidates:
            if self._is_stt_preview_segment(seg):
                continue
            is_active = self._is_active_segment(seg) if hasattr(self, "_is_active_segment") else (
                self.active_seg_start is not None
                and abs(float(seg.get("start", 0.0) or 0.0) - float(self.active_seg_start)) < 0.5
            )
            if active_only and not is_active:
                continue
            if not self._center_drag_hit(seg, x, y):
                continue
            x1, x2 = self._x(seg["start"]), self._x(seg["end"])
            center_x = (x1 + x2) // 2
            matches.append(
                (
                    (
                        0 if is_active else 1,
                        abs(int(x) - int(center_x)),
                        -max(1, x2 - x1),
                    ),
                    seg,
                )
            )
        if not matches:
            return None
        matches.sort(key=lambda item: item[0])
        return matches[0][1]

    def _diamond_hit_rect(self, bx: int, *, margin: int = 5) -> QRect:
        x_radius = 5 + max(0, int(margin))
        y_radius = 8 + max(0, int(margin))
        return QRect(int(bx - x_radius), int(DIAMOND_Y - y_radius), x_radius * 2, y_radius * 2)

    def _diamond_pairs(self):
        key = self._segment_index_cache_key() if hasattr(self, "_segment_index_cache_key") else (
            id(getattr(self, "segments", None)),
            len(getattr(self, "segments", []) or []),
        )
        if getattr(self, "_diamond_pairs_cache_key", None) == key:
            return list((getattr(self, "_diamond_pairs_cache", {}) or {}).get("pairs") or [])

        if hasattr(self, "_editable_segments_with_indices_sorted"):
            editable = self._editable_segments_with_indices_sorted()
        else:
            editable = []
            for raw_idx, seg in enumerate(self.segments):
                if self._is_stt_preview_segment(seg) or bool(seg.get("is_gap")):
                    continue
                if "start" not in seg or "end" not in seg:
                    continue
                editable.append((raw_idx, seg))
            editable.sort(key=lambda item: (float(item[1].get("start", 0.0) or 0.0), int(item[0])))

        pairs = []
        ends = []
        for left, right in zip(editable, editable[1:]):
            left_idx, s1 = left
            right_idx, s2 = right
            touches = (
                self._segments_share_frame_boundary(s1, s2)
                if hasattr(self, "_segments_share_frame_boundary")
                else abs(float(s1.get("end", 0.0) or 0.0) - float(s2.get("start", 0.0) or 0.0)) < 0.001
            )
            if touches:
                pairs.append((left_idx, right_idx, s1, s2))
                ends.append(float(s1.get("end", 0.0) or 0.0))
        self._diamond_pairs_cache_key = key
        self._diamond_pairs_cache = {"pairs": pairs, "ends": ends}
        return pairs

    def _diamond_pair_for_index(self, pair_idx):
        if pair_idx is None:
            return None
        pairs = self._diamond_pairs()
        if 0 <= int(pair_idx) < len(pairs):
            return pairs[int(pair_idx)]
        return None

    def _diamond_index_at(self, x: int, y: int, *, margin: int = 5):
        margin = max(int(margin), self._touch_hit_slop(10))
        x_radius = 5 + max(0, int(margin))
        y_radius = 8 + max(0, int(margin))
        if int(y) < int(DIAMOND_Y - y_radius) or int(y) >= int(DIAMOND_Y + y_radius):
            return None
        pairs = self._diamond_pairs()
        if len(pairs) >= 64:
            cache = getattr(self, "_diamond_pairs_cache", {}) or {}
            ends = list(cache.get("ends") or [])
            pps = max(0.001, float(getattr(self, "pps", 1.0) or 1.0))
            center = float(x or 0.0) / pps
            pad = max(0.02, (int(margin) + 8) / pps)
            start_idx = bisect_left(ends, center - pad)
            end_idx = bisect_right(ends, center + pad)
            candidates = ((idx, pairs[idx]) for idx in range(start_idx, min(end_idx, len(pairs))))
        else:
            candidates = enumerate(pairs)
        for pair_idx, (_, _, s1, _) in candidates:
            bx = int(self._x(s1["end"]))
            if bx - x_radius <= int(x) < bx + x_radius:
                return pair_idx
        return None

    def _clear_active_gaps_for_segment_drag(self):
        changed = False
        for gap in getattr(self, "gap_segments", []) or []:
            if gap.get("active"):
                gap["active"] = False
                changed = True
        if changed:
            self.update()

    def _setup_drag(self, s, edge, x):
        self._clear_pending_center_drag()
        if getattr(self, "_edit_active", False):
            self._commit_inline_edit()
        self._ime_preedit = ""
        self._cursor_vis = False
        if hasattr(self, "_cursor_timer"):
            self._cursor_timer.stop()
        self.drag_started.emit()
        self._drag_seg, self._drag_edge = s, edge
        self._drag_x0 = x
        self.active_seg_start = float(s.get("start", 0.0) or 0.0)
        if hasattr(self, "_sync_active_segment_key"):
            self._sync_active_segment_key(seg=s)
        self._drag_s0_start, self._drag_s0_end = s["start"], s["end"]
        self._drag_adj_l = self._get_prev_seg(s)
        self._drag_adj_r = self._get_next_seg(s)
        self._drag_adj_orig_start_l = self._drag_adj_l["start"] if self._drag_adj_l else 0.0
        self._drag_adj_orig_end_l = self._drag_adj_l["end"] if self._drag_adj_l else 0.0
        self._drag_adj_orig_start_r = self._drag_adj_r["start"] if self._drag_adj_r else 0.0
        self._drag_adj_orig_end_r = self._drag_adj_r["end"] if self._drag_adj_r else 0.0
        self._drag_center_reorder_direction = None
        self._set_drag_merge_preview_pair(None)
        clearer = getattr(self, "clear_drag_shadow_playhead", None)
        if callable(clearer):
            try:
                clearer()
            except Exception:
                pass
        self._clear_active_gaps_for_segment_drag()
        self._drag_snap_candidates_cache = self._drag_snap_candidates()
        self._drag_last_paint_rect = self._drag_visual_rect()
        if edge == "diamond":
            self._begin_drag_live_cut_session()
        else:
            self._finish_drag_live_cut_session(clear_shadow=False)
        if edge != "center":
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))

    def _drag_visual_rect(self) -> QRect:
        edge = getattr(self, "_drag_edge", None)
        margin = 80
        top = max(0, SEG_TOP - 12)
        height = max(1, SEG_BOT - top + 12)

        if edge == "diamond":
            pair = getattr(self, "_drag_diamond_pair", None)
            if pair is not None and pair[0] < len(self.segments):
                x = self._x(self.segments[pair[0]]["end"])
                rect = QRect(x - margin, top, margin * 2, height)
            else:
                rect = QRect(0, top, 1, height)
        else:
            seg = getattr(self, "_drag_seg", None)
            if not seg:
                rect = QRect(0, top, 1, height)
            elif edge == "square_left":
                x = self._x(seg["start"])
                ox = self._x(getattr(self, "_drag_s0_start", seg["start"]))
                left = min(x, ox) - margin
                right = max(x, ox) + margin
                rect = QRect(left, top, max(1, right - left), height)
            elif edge == "square_right":
                x = self._x(seg["end"])
                ox = self._x(getattr(self, "_drag_s0_end", seg["end"]))
                left = min(x, ox) - margin
                right = max(x, ox) + margin
                rect = QRect(left, top, max(1, right - left), height)
            else:
                x1 = self._x(seg["start"])
                x2 = self._x(seg["end"])
                rect = QRect(min(x1, x2) - 16, top, abs(x2 - x1) + 32, height)

        for sx in getattr(self, "_snap_lines", []) or []:
            rect = rect.united(QRect(int(sx) - 4, top, 8, height))
        guide_x = getattr(self, "_drag_guide_x", None)
        if guide_x is not None:
            rect = rect.united(QRect(int(guide_x) - 4, 0, 8, self.height()))
        if hasattr(self, "_segment_repaint_rect"):
            related = [
                getattr(self, "_drag_seg", None),
                getattr(self, "_drag_adj_l", None),
                getattr(self, "_drag_adj_r", None),
            ]
            pair = getattr(self, "_drag_diamond_pair", None)
            if pair is not None:
                for idx in pair:
                    try:
                        related.append(self.segments[int(idx)])
                    except Exception:
                        pass
            merge_pair = tuple(getattr(self, "_drag_merge_pair", ()) or ())
            if merge_pair:
                for line in merge_pair:
                    seg = self._segment_for_line(int(line)) if hasattr(self, "_segment_for_line") else None
                    if isinstance(seg, dict):
                        related.append(seg)
            for seg in related:
                if isinstance(seg, dict):
                    rect = rect.united(self._segment_repaint_rect(seg, margin=64, full_height=False))
        return rect.adjusted(-4, -4, 4, 4).intersected(QRect(0, 0, self.width(), self.height()))

    def _update_drag_visual_rect(self, before: QRect):
        after = self._drag_visual_rect()
        dirty = before.united(after).intersected(QRect(0, 0, self.width(), self.height()))
        if dirty.isValid() and not dirty.isEmpty():
            self.update(dirty)
        else:
            self.update()
        if hasattr(self, "_notify_scenegraph_layer"):
            self._notify_scenegraph_layer()
        self._drag_last_paint_rect = after

    def _merge_preview_tolerance_sec(self) -> float:
        fps = max(1.0, float(self._get_fps() if hasattr(self, "_get_fps") else 30.0))
        return max(0.001, 1.1 / fps)

    def _merge_preview_repaint_rect(self, pair) -> QRect:
        rect = QRect()
        if not pair:
            return rect
        if not hasattr(self, "_segment_repaint_rect") or not hasattr(self, "_segment_for_line"):
            return rect
        for raw_line in tuple(pair)[:2]:
            try:
                line = int(raw_line)
            except Exception:
                continue
            seg = self._segment_for_line(line)
            if isinstance(seg, dict):
                rect = rect.united(self._segment_repaint_rect(seg, margin=64, full_height=False))
        return rect

    def _set_drag_merge_preview_pair(self, pair) -> None:
        normalized = None
        if pair and len(tuple(pair)) >= 2:
            try:
                left = int(tuple(pair)[0])
                right = int(tuple(pair)[1])
                if left != right:
                    normalized = (left, right)
            except Exception:
                normalized = None
        current = getattr(self, "_drag_merge_pair", None)
        if current == normalized:
            return
        before = self._merge_preview_repaint_rect(current)
        self._drag_merge_pair = normalized
        after = self._merge_preview_repaint_rect(normalized)
        dirty = before.united(after).intersected(QRect(0, 0, self.width(), self.height()))
        if dirty.isValid() and not dirty.isEmpty():
            self.update(dirty.adjusted(-4, -4, 4, 4))
        else:
            self.update()

    def _is_merge_preview_segment(self, seg: dict) -> bool:
        if not isinstance(seg, dict):
            return False
        pair = tuple(getattr(self, "_drag_merge_pair", ()) or ())
        if not pair:
            return False
        try:
            line = int(seg.get("line", -999999))
        except Exception:
            return False
        return line in pair

    def _sync_drag_merge_preview(self) -> None:
        edge = str(getattr(self, "_drag_edge", "") or "")
        seg = getattr(self, "_drag_seg", None)
        if edge not in {"square_left", "square_right"} or not isinstance(seg, dict):
            self._set_drag_merge_preview_pair(None)
            return

        prev_seg = getattr(self, "_drag_adj_l", None)
        next_seg = getattr(self, "_drag_adj_r", None)
        pair = None
        native = compute_subtitle_merge_preview_via_swift(
            edge=edge,
            current_start=float(seg.get("start", 0.0) or 0.0),
            current_end=float(seg.get("end", seg.get("start", 0.0)) or 0.0),
            previous_start=None if not isinstance(prev_seg, dict) else float(prev_seg.get("start", 0.0) or 0.0),
            previous_end=None if not isinstance(prev_seg, dict) else float(prev_seg.get("end", prev_seg.get("start", 0.0)) or 0.0),
            next_start=None if not isinstance(next_seg, dict) else float(next_seg.get("start", 0.0) or 0.0),
            next_end=None if not isinstance(next_seg, dict) else float(next_seg.get("end", next_seg.get("start", 0.0)) or 0.0),
            frame_rate=float(self._get_fps() if hasattr(self, "_get_fps") else 30.0),
        )
        target = str((native or {}).get("target", "") or "").strip().lower()
        if target == "previous" and isinstance(prev_seg, dict) and not self._is_stt_preview_segment(prev_seg):
            pair = (int(prev_seg.get("line", -1)), int(seg.get("line", -1)))
        elif target == "next" and isinstance(next_seg, dict) and not self._is_stt_preview_segment(next_seg):
            pair = (int(seg.get("line", -1)), int(next_seg.get("line", -1)))
        else:
            tolerance = self._merge_preview_tolerance_sec()
            if (
                edge == "square_left"
                and isinstance(prev_seg, dict)
                and not self._is_stt_preview_segment(prev_seg)
                and not bool(prev_seg.get("is_gap"))
            ):
                prev_start = float(prev_seg.get("start", 0.0) or 0.0)
                prev_end = float(prev_seg.get("end", prev_start) or prev_start)
                current_start = float(seg.get("start", 0.0) or 0.0)
                current_end = float(seg.get("end", current_start) or current_start)
                if abs(current_start - prev_start) <= tolerance and current_end > prev_end + (tolerance * 0.5):
                    pair = (int(prev_seg.get("line", -1)), int(seg.get("line", -1)))
            elif (
                edge == "square_right"
                and isinstance(next_seg, dict)
                and not self._is_stt_preview_segment(next_seg)
                and not bool(next_seg.get("is_gap"))
            ):
                next_start = float(next_seg.get("start", 0.0) or 0.0)
                next_end = float(next_seg.get("end", next_start) or next_start)
                current_start = float(seg.get("start", 0.0) or 0.0)
                current_end = float(seg.get("end", current_start) or current_start)
                if abs(current_end - next_end) <= tolerance and current_start < next_start - (tolerance * 0.5):
                    pair = (int(seg.get("line", -1)), int(next_seg.get("line", -1)))
        if pair and (pair[0] < 0 or pair[1] < 0):
            pair = None
        self._set_drag_merge_preview_pair(pair)

    def _apply_drag(self, delta):
        try:
            self._drag_last_delta = float(delta or 0.0)
        except Exception:
            self._drag_last_delta = 0.0
        _legacy_apply_timing_drag(self, delta)
        preview_sec = self._timing_drag_preview_sec() if hasattr(self, "_timing_drag_preview_sec") else None
        if preview_sec is not None:
            try:
                self.drag_preview_sec.emit(float(preview_sec))
            except Exception:
                pass
        self._sync_drag_merge_preview()

    def _clear_drag_guides(self, *, update: bool = False):
        self._snap_lines = []
        self._drag_guide_x = None
        self._drag_snap_candidate = None
        if update:
            self.update()

    def _set_drag_guides(self, guide_sec: float, snapped: dict | None = None):
        guide_sec = self._snap_to_frame(guide_sec)
        self._drag_guide_x = self._x(guide_sec)
        self._drag_snap_candidate = dict(snapped) if snapped else None
        self._snap_lines = [self._x(float(snapped["time"]))] if snapped else []

    def _drag_snap_threshold_sec(self) -> float:
        fps = max(1.0, float(self._get_fps() if hasattr(self, "_get_fps") else 30.0))
        frame = 1.0 / fps
        pixel = 8.0 / max(1.0, float(getattr(self, "pps", 1.0) or 1.0))
        return max(frame, pixel)

    def _add_snap_candidate(self, candidates: list[dict], sec, kind: str, source=None):
        if isinstance(sec, dict):
            raw_value = _as_float(
                sec.get("timeline_sec", sec.get("time", sec.get("start", sec.get("timeline_start", -1.0)))),
                -1.0,
            )
        else:
            raw_value = _as_float(sec, -1.0)
        if raw_value < 0.0:
            return
        value = self._snap_to_frame(raw_value)
        total = max(0.0, _as_float(getattr(self, "total_duration", 0.0), 0.0))
        if value < 0.0 or (total > 0.0 and value > total):
            return
        candidates.append({"time": value, "kind": kind, "source": source})

    def _snap_row_is_silence_gap(self, row) -> bool:
        if not isinstance(row, dict):
            return False
        if bool(row.get("is_gap")) or bool(row.get("_explicit_gap")):
            return True
        quality = row.get("quality")
        if isinstance(quality, dict) and bool(quality.get("linked_silence")):
            return True
        if row.get("linked_silence_for_line") is not None:
            return True
        text = " ".join(
            str(row.get(key, "") or "").lower()
            for key in ("kind", "source", "label", "text", "lane")
        )
        if "무음" in text:
            return True
        silence_tokens = (
            "silence",
            "silent",
            "non_speech",
            "non-speech",
            "generation_silence",
            "linked_silence",
        )
        if any(token in text for token in silence_tokens):
            return True
        return str(row.get("kind", "") or "").lower() == "gap"

    def _snap_source_for_candidate(self, kind: str, time_value: float):
        if kind not in {"gap", "vad", "voice_activity"}:
            return None
        source_name = {
            "gap": "gap_segments",
            "vad": "vad_segments",
            "voice_activity": "voice_activity_segments",
        }.get(kind)
        if not source_name:
            return None
        try:
            target = self._snap_to_frame(float(time_value or 0.0))
        except Exception:
            return None
        fps = max(1.0, float(self._get_fps() if hasattr(self, "_get_fps") else 30.0))
        epsilon = max(0.001, 0.5 / fps)
        matches: list[dict] = []
        for row in list(getattr(self, source_name, []) or []):
            if not isinstance(row, dict):
                continue
            try:
                start = self._snap_to_frame(float(row.get("start", 0.0) or 0.0))
                end = self._snap_to_frame(float(row.get("end", start) or start))
            except Exception:
                continue
            if abs(start - target) <= epsilon or abs(end - target) <= epsilon:
                matches.append(row)
        if not matches:
            return None
        for row in matches:
            if self._snap_row_is_silence_gap(row):
                return row
        return matches[0]

    def _drag_snap_base_key(self) -> tuple:
        segment_key = self._segment_index_cache_key() if hasattr(self, "_segment_index_cache_key") else (
            id(getattr(self, "segments", None)),
            len(getattr(self, "segments", []) or []),
        )
        roughcut_key = None
        try:
            markers = self.roughcut_major_markers_cached() if hasattr(self, "roughcut_major_markers_cached") else []
            roughcut_key = (
                len(markers or []),
                id(markers[0]) if markers else None,
                id(markers[-1]) if markers else None,
            )
        except Exception:
            roughcut_key = None
        return (
            segment_key,
            id(getattr(self, "gap_segments", None)),
            len(getattr(self, "gap_segments", []) or []),
            bool(getattr(self, "show_gap_insert_controls", True)),
            id(getattr(self, "vad_segments", None)),
            len(getattr(self, "vad_segments", []) or []),
            id(getattr(self, "voice_activity_segments", None)),
            len(getattr(self, "voice_activity_segments", []) or []),
            id(getattr(self, "boundary_times", None)),
            len(getattr(self, "boundary_times", []) or []),
            id(getattr(self, "scan_boundary_times", None)),
            len(getattr(self, "scan_boundary_times", []) or []),
            tuple(round(float(sec or 0.0), 3) for sec in list(getattr(self, "user_alignment_guides", []) or [])),
            None if getattr(self, "shadow_playhead_sec", None) is None else round(float(getattr(self, "shadow_playhead_sec", 0.0) or 0.0), 3),
            int(round(float(getattr(self, "total_duration", 0.0) or 0.0) * 1000.0)),
            round(float(self._get_fps() if hasattr(self, "_get_fps") else 30.0), 3),
            roughcut_key,
        )

    def _build_drag_snap_base_candidates(self) -> list[dict]:
        key = self._drag_snap_base_key()
        if key == getattr(self, "_drag_snap_base_cache_key", None):
            cached = getattr(self, "_drag_snap_base_candidates", None)
            if isinstance(cached, list):
                return cached

        try:
            roughcut_ranges = list((self.roughcut_major_markers_cached() if hasattr(self, "roughcut_major_markers_cached") else []) or [])
        except Exception:
            roughcut_ranges = []

        native_candidates = build_subtitle_drag_snap_base_via_swift(
            segments=list(getattr(self, "segments", []) or []),
            gap_segments=list(getattr(self, "gap_segments", []) or []),
            vad_segments=list(getattr(self, "vad_segments", []) or []),
            voice_activity_segments=list(getattr(self, "voice_activity_segments", []) or []),
            boundary_times=list(getattr(self, "boundary_times", []) or []),
            scan_boundary_times=[
                bt.get("timeline_sec", bt.get("time", bt.get("start", 0.0))) if isinstance(bt, dict) else bt
                for bt in list(getattr(self, "scan_boundary_times", []) or [])
            ],
            user_guides=list(getattr(self, "user_alignment_guides", []) or []),
            roughcut_ranges=roughcut_ranges,
            total_duration=float(getattr(self, "total_duration", 0.0) or 0.0),
            fps=float(self._get_fps() if hasattr(self, "_get_fps") else 30.0),
            include_gap_controls=bool(self._gap_insert_controls_enabled()),
        )
        if isinstance(native_candidates, list):
            prepared: list[dict] = []
            for item in native_candidates:
                if not isinstance(item, dict):
                    continue
                try:
                    time_value = self._snap_to_frame(float(item.get("time", 0.0) or 0.0))
                except Exception:
                    continue
                row: dict = {
                    "time": time_value,
                    "kind": str(item.get("kind", "") or ""),
                    "source": None,
                }
                source_line = item.get("sourceLine")
                if source_line is not None and hasattr(self, "_segment_for_line"):
                    try:
                        row["source"] = self._segment_for_line(int(source_line))
                    except Exception:
                        row["source"] = None
                if row["source"] is None:
                    row["source"] = self._snap_source_for_candidate(row["kind"], time_value)
                prepared.append(row)
            shadow_sec = getattr(self, "shadow_playhead_sec", None)
            if shadow_sec is not None:
                self._add_snap_candidate(prepared, shadow_sec, "shadow_playhead", None)
            self._drag_snap_base_cache_key = key
            self._drag_snap_base_candidates = prepared
            return prepared

        candidates: list[dict] = []
        for seg in list(getattr(self, "segments", []) or []):
            if not isinstance(seg, dict) or bool(seg.get("is_gap")):
                continue
            if self._is_stt_preview_segment(seg):
                continue
            kind = "subtitle"
            self._add_snap_candidate(candidates, seg.get("start"), kind, seg)
            self._add_snap_candidate(candidates, seg.get("end"), kind, seg)
        if self._gap_insert_controls_enabled():
            for gap in list(getattr(self, "gap_segments", []) or []):
                self._add_snap_candidate(candidates, gap.get("start"), "gap", gap)
                self._add_snap_candidate(candidates, gap.get("end"), "gap", gap)
        for vad in list(getattr(self, "vad_segments", []) or []):
            self._add_snap_candidate(candidates, vad.get("start"), "vad", vad)
            self._add_snap_candidate(candidates, vad.get("end"), "vad", vad)
        for va in list(getattr(self, "voice_activity_segments", []) or []):
            self._add_snap_candidate(candidates, va.get("start"), "voice_activity", va)
            self._add_snap_candidate(candidates, va.get("end"), "voice_activity", va)
        for bt in list(getattr(self, "boundary_times", []) or []):
            self._add_snap_candidate(candidates, bt, "cut_official", None)
        for bt in list(getattr(self, "scan_boundary_times", []) or []):
            sec = bt.get("timeline_sec", bt.get("time", bt.get("start", 0.0))) if isinstance(bt, dict) else bt
            self._add_snap_candidate(candidates, sec, "cut_temporary", bt)
        for guide_sec in list(getattr(self, "user_alignment_guides", []) or []):
            self._add_snap_candidate(candidates, guide_sec, "user_guide", None)
        shadow_sec = getattr(self, "shadow_playhead_sec", None)
        if shadow_sec is not None:
            self._add_snap_candidate(candidates, shadow_sec, "shadow_playhead", None)
        try:
            markers = self.roughcut_major_markers_cached() if hasattr(self, "roughcut_major_markers_cached") else []
        except Exception:
            markers = []
        for marker in list(markers or []):
            self._add_snap_candidate(candidates, marker.get("start"), "roughcut", marker)
            self._add_snap_candidate(candidates, marker.get("end"), "roughcut", marker)
        self._add_snap_candidate(candidates, 0.0, "timeline", None)
        self._add_snap_candidate(candidates, getattr(self, "total_duration", 0.0), "timeline", None)
        self._drag_snap_base_cache_key = key
        self._drag_snap_base_candidates = candidates
        return candidates

    def _drag_snap_candidates(self) -> list[dict]:
        candidates: list[dict] = []
        dragged = getattr(self, "_drag_seg", None)
        drag_original_edges = {
            self._snap_to_frame(getattr(self, "_drag_s0_start", -1.0)),
            self._snap_to_frame(getattr(self, "_drag_s0_end", -1.0)),
        }
        if getattr(self, "_drag_edge", None) == "diamond":
            drag_original_edges.add(self._snap_to_frame(getattr(self, "_drag_diamond_orig", -1.0)))

        for item in self._build_drag_snap_base_candidates():
            source = item.get("source")
            if source is dragged:
                continue
            snapped_edge = self._snap_to_frame(_as_float(item.get("time"), -1.0))
            if getattr(self, "_drag_edge", None) == "diamond" and any(
                abs(snapped_edge - original) < 0.05
                for original in drag_original_edges
            ):
                continue
            if item.get("kind") in {"gap", "user_guide", "shadow_playhead"}:
                if any(abs(snapped_edge - original) < 0.05 for original in drag_original_edges):
                    continue
            candidates.append(item)

        priority = {
            "shadow_playhead": 14,
            "user_guide": 13,
            "cut_live": 15,
            "cut_official": 12,
            "cut_temporary": 11,
            "subtitle": 10,
            "stt1": 9,
            "stt2": 9,
            "voice_activity": 8,
            "gap": 8,
            "vad": 7,
            "roughcut": 6,
            "timeline": 5,
        }
        deduped: dict[float, dict] = {}
        for item in candidates:
            t = float(item.get("time", 0.0) or 0.0)
            prev = deduped.get(t)
            if prev is None or priority.get(str(item.get("kind")), 0) > priority.get(str(prev.get("kind")), 0):
                deduped[t] = item
        return list(deduped.values())

    def _segment_move_suppresses_gap_candidate_attachment(self, target_start: float) -> bool:
        if str(getattr(self, "_drag_edge", "") or "") != "center":
            return False
        dragged = getattr(self, "_drag_seg", None)
        if not isinstance(dragged, dict):
            return False
        try:
            original_start = self._snap_to_frame(float(getattr(self, "_drag_s0_start", dragged.get("start", 0.0)) or 0.0))
            original_end = self._snap_to_frame(float(getattr(self, "_drag_s0_end", dragged.get("end", original_start)) or original_start))
            requested_start = self._snap_to_frame(float(target_start or 0.0))
        except Exception:
            return False
        fps = max(1.0, float(self._get_fps() if hasattr(self, "_get_fps") else 30.0))
        epsilon = max(0.001, 0.5 / fps)
        moving_right = requested_start > original_start + epsilon
        moving_left = requested_start < original_start - epsilon
        if not moving_right and not moving_left:
            return False

        gap_rows = [
            dict(gap)
            for gap in list(getattr(self, "gap_segments", []) or [])
            if isinstance(gap, dict)
        ]
        for seg in list(getattr(self, "segments", []) or []):
            if isinstance(seg, dict) and bool(seg.get("is_gap")):
                gap_rows.append(dict(seg))
        for row in list(getattr(self, "voice_activity_segments", []) or []):
            if isinstance(row, dict) and self._snap_row_is_silence_gap(row):
                gap_rows.append(dict(row))
        for row in list(getattr(self, "vad_segments", []) or []):
            if isinstance(row, dict) and self._snap_row_is_silence_gap(row):
                gap_rows.append(dict(row))

        def _bounds(row: dict) -> tuple[float, float] | None:
            try:
                start = self._snap_to_frame(float(row.get("start", 0.0) or 0.0))
                end = self._snap_to_frame(float(row.get("end", start) or start))
            except Exception:
                return None
            if end <= start:
                return None
            return start, end

        if moving_right:
            next_real = getattr(self, "_drag_adj_r", None)
            try:
                next_start = self._snap_to_frame(float(next_real.get("start", 0.0))) if isinstance(next_real, dict) else None
            except Exception:
                next_start = None
            for gap in gap_rows:
                bounds = _bounds(gap)
                if bounds is None:
                    continue
                gap_start, gap_end = bounds
                if gap_end <= original_end + epsilon:
                    continue
                if next_start is not None and gap_start >= next_start - epsilon:
                    continue
                return True
            return False

        previous_real = getattr(self, "_drag_adj_l", None)
        try:
            previous_end = self._snap_to_frame(float(previous_real.get("end", 0.0))) if isinstance(previous_real, dict) else None
        except Exception:
            previous_end = None
        for gap in gap_rows:
            bounds = _bounds(gap)
            if bounds is None:
                continue
            gap_start, gap_end = bounds
            if gap_start >= original_start - epsilon:
                continue
            if previous_end is not None and gap_end <= previous_end + epsilon:
                continue
            return True
        return False

    def _filter_segment_move_snap_candidates(self, candidates: list[dict], *, target_start: float) -> list[dict]:
        suppress_gap = self._segment_move_suppresses_gap_candidate_attachment(target_start)
        self._drag_suppresses_gap_candidate_attachment = bool(suppress_gap)
        if not suppress_gap:
            return list(candidates or [])

        def _is_suppressed_gap_candidate(candidate: dict) -> bool:
            kind = str((candidate or {}).get("kind", "") or "")
            if kind == "gap":
                return True
            if kind in {"vad", "voice_activity"}:
                return self._snap_row_is_silence_gap((candidate or {}).get("source"))
            return False

        return [
            candidate
            for candidate in list(candidates or [])
            if not _is_suppressed_gap_candidate(candidate or {})
        ]

    def _iter_live_cut_snap_owners(self):
        seen: set[int] = set()
        owner = self
        while owner is not None and id(owner) not in seen:
            seen.add(id(owner))
            yield owner
            next_owner = None
            try:
                next_owner = owner.parentWidget()
            except Exception:
                next_owner = None
            if next_owner is None:
                try:
                    next_owner = owner.parent()
                except Exception:
                    next_owner = None
            owner = next_owner
        try:
            window = self.window()
        except Exception:
            window = None
        if window is not None and id(window) not in seen:
            yield window

    def _set_drag_live_cut_shadow(self, sec: float | None) -> None:
        setter_name = "set_drag_shadow_playhead" if sec is not None else "clear_drag_shadow_playhead"
        setter = getattr(self, setter_name, None)
        if not callable(setter):
            return
        try:
            if sec is None:
                setter()
            else:
                setter(float(sec))
        except Exception:
            pass

    def _current_diamond_boundary_sec(self) -> float | None:
        pair = getattr(self, "_drag_diamond_pair", None)
        if pair is None:
            return None
        try:
            left_idx = int(pair[0])
        except Exception:
            return None
        if left_idx < 0 or left_idx >= len(self.segments):
            return None
        seg = self.segments[left_idx]
        if not isinstance(seg, dict):
            return None
        try:
            return self._snap_to_frame(float(seg.get("end", 0.0) or 0.0))
        except Exception:
            return None

    def _live_cut_drag_direction(self, target_global_sec: float) -> int:
        target_global_sec = self._snap_to_frame(float(target_global_sec or 0.0))
        current_boundary = self._current_diamond_boundary_sec()
        if current_boundary is None:
            current_boundary = self._snap_to_frame(float(getattr(self, "_drag_diamond_orig", target_global_sec) or target_global_sec))
        epsilon = max(0.001, 1.0 / max(1.0, float(self._get_fps())))
        if target_global_sec > current_boundary + epsilon:
            return 1
        if target_global_sec < current_boundary - epsilon:
            return -1
        original_boundary = self._snap_to_frame(float(getattr(self, "_drag_diamond_orig", current_boundary) or current_boundary))
        if target_global_sec > original_boundary + epsilon:
            return 1
        if target_global_sec < original_boundary - epsilon:
            return -1
        return 1

    def _live_cut_search_window_secs(self, local_sec: float, direction: int) -> tuple[float, float]:
        target_local_sec = max(0.0, float(local_sec or 0.0))
        if direction < 0:
            search_start = target_local_sec
            search_end = target_local_sec + 1.0
        else:
            search_end = target_local_sec
            search_start = max(0.0, target_local_sec - 1.0)
        return (round(search_start, 4), round(max(search_start, search_end), 4))

    def _live_cut_snap_settings_enabled(self) -> bool:
        for owner in self._iter_live_cut_snap_owners():
            settings = getattr(owner, "settings", None)
            if not isinstance(settings, dict):
                continue
            if settings.get("timeline_live_cut_snap_enabled") is False:
                return False
            if settings.get("subtitle_diamond_live_cut_snap_enabled") is False:
                return False
        return True

    def _drag_live_cut_settings(self) -> dict:
        settings: dict = {}
        for owner in self._iter_live_cut_snap_owners():
            owner_settings = getattr(owner, "settings", None)
            if isinstance(owner_settings, dict):
                settings.update(owner_settings)
        return settings

    def _drag_live_cut_async_delay_ms(self) -> int:
        settings = self._drag_live_cut_settings()
        raw = settings.get(
            "subtitle_diamond_live_cut_snap_async_delay_ms",
            settings.get("timeline_live_cut_snap_async_delay_ms", 45),
        )
        try:
            return max(8, min(180, int(raw)))
        except Exception:
            return 45

    def _drag_live_cut_gpu_enabled(self) -> bool:
        settings = self._drag_live_cut_settings()
        if "subtitle_diamond_live_cut_snap_gpu_enabled" in settings:
            return bool(settings.get("subtitle_diamond_live_cut_snap_gpu_enabled"))
        return bool(settings.get("timeline_live_cut_snap_gpu_enabled", True))

    def _begin_drag_live_cut_session(self) -> None:
        self._drag_live_cut_session_id = int(getattr(self, "_drag_live_cut_session_id", 0) or 0) + 1
        self._drag_live_cut_pending_request = None
        self._drag_live_cut_async_candidate = None
        self._drag_live_cut_async_busy = False
        self._drag_live_cut_async_token = 0
        self._drag_live_cut_last_completed_signature = None
        self._set_drag_live_cut_shadow(None)

    def _finish_drag_live_cut_session(self, *, clear_shadow: bool = True) -> None:
        self._drag_live_cut_session_id = int(getattr(self, "_drag_live_cut_session_id", 0) or 0) + 1
        timer = getattr(self, "_drag_live_cut_async_timer", None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
        self._drag_live_cut_pending_request = None
        self._drag_live_cut_async_candidate = None
        self._drag_live_cut_async_busy = False
        self._drag_live_cut_last_completed_signature = None
        if clear_shadow:
            self._set_drag_live_cut_shadow(None)

    def _build_drag_live_cut_async_request(self, global_sec: float, ctx: dict) -> dict | None:
        try:
            media_path = os.path.abspath(os.path.expanduser(str(ctx.get("media_path") or "")))
        except Exception:
            media_path = ""
        if not media_path:
            return None
        fps = max(1.0, float(ctx.get("fps") or self._get_fps()))
        clip_start = float(ctx.get("clip_start", 0.0) or 0.0)
        target_local_sec = max(0.0, float(ctx.get("local_sec", 0.0) or 0.0))
        origin_global = getattr(self, "_drag_diamond_orig", None)
        if origin_global is None:
            origin_global = self._current_diamond_boundary_sec()
        try:
            origin_local_sec = max(0.0, float(origin_global if origin_global is not None else global_sec) - clip_start)
        except Exception:
            origin_local_sec = target_local_sec

        frame_sec = 1.0 / fps
        if target_local_sec > origin_local_sec + frame_sec:
            direction = 1
        elif target_local_sec < origin_local_sec - frame_sec:
            direction = -1
        else:
            direction = self._live_cut_drag_direction(float(global_sec or 0.0))

        search_start_local_sec = min(origin_local_sec, target_local_sec)
        search_end_local_sec = max(origin_local_sec, target_local_sec)
        search_start_frame = max(0, int(round(search_start_local_sec * fps)))
        search_end_frame = max(search_start_frame, int(round(search_end_local_sec * fps)))
        if search_end_frame - search_start_frame < 2:
            return None
        origin_frame = max(0, int(round(origin_local_sec * fps)))
        target_frame = max(0, int(round(target_local_sec * fps)))
        score_start_frame = max(0, search_start_frame - 1)
        session_id = int(getattr(self, "_drag_live_cut_session_id", 0) or 0)
        return {
            "media_path": media_path,
            "fps": fps,
            "clip_start": clip_start,
            "target_global_sec": self._snap_to_frame(float(global_sec or 0.0)),
            "target_local_sec": target_local_sec,
            "origin_local_sec": origin_local_sec,
            "search_start_local_sec": round(search_start_local_sec, 4),
            "search_end_local_sec": round(search_end_local_sec, 4),
            "score_start_frame": score_start_frame,
            "search_start_frame": search_start_frame,
            "search_end_frame": search_end_frame,
            "origin_frame": origin_frame,
            "target_frame": target_frame,
            "direction": int(direction),
            "session_id": session_id,
            "signature": (
                media_path,
                round(fps, 3),
                search_start_frame,
                search_end_frame,
                origin_frame,
                target_frame,
            ),
        }

    def _drag_live_cut_cached_candidates(self, request: dict) -> list[dict]:
        candidate = getattr(self, "_drag_live_cut_async_candidate", None)
        if not isinstance(candidate, dict):
            return []
        source = candidate.get("source")
        if not isinstance(source, dict):
            return []
        try:
            if os.path.abspath(str(source.get("media_path") or "")) != str(request.get("media_path") or ""):
                return []
            fps = max(1.0, float(request.get("fps") or self._get_fps()))
            source_fps = max(1.0, float(source.get("fps") or fps))
            frame_no = int(source.get("frame"))
            search_start_frame = int(request.get("search_start_frame", 0))
            search_end_frame = int(request.get("search_end_frame", search_start_frame))
            origin_frame = int(request.get("origin_frame", 0))
            direction = int(request.get("direction", 1))
            target_global_sec = float(request.get("target_global_sec", 0.0) or 0.0)
            cut_sec = self._snap_to_frame(float(candidate.get("time", 0.0) or 0.0))
        except Exception:
            return []
        if abs(source_fps - fps) > 0.01:
            return []
        if frame_no < min(search_start_frame, search_end_frame) or frame_no > max(search_start_frame, search_end_frame):
            return []
        exclusion = max(2, int(round(fps * 0.025)))
        if direction >= 0 and frame_no <= origin_frame + exclusion:
            return []
        if direction < 0 and frame_no >= origin_frame - exclusion:
            return []
        span_sec = abs(float(request.get("search_end_local_sec", 0.0) or 0.0) - float(request.get("search_start_local_sec", 0.0) or 0.0))
        max_distance = max(0.20, min(1.0, span_sec + (2.0 / fps)))
        if abs(cut_sec - self._snap_to_frame(target_global_sec)) > max_distance:
            return []
        cached = dict(candidate)
        cached["time"] = cut_sec
        self._set_drag_live_cut_shadow(cut_sec)
        return [cached]

    def _schedule_drag_live_cut_async(self, request: dict) -> None:
        signature = request.get("signature")
        if signature is not None and signature == getattr(self, "_drag_live_cut_last_completed_signature", None):
            return
        pending = getattr(self, "_drag_live_cut_pending_request", None)
        if isinstance(pending, dict) and pending.get("signature") == signature:
            return
        self._drag_live_cut_pending_request = dict(request)
        if bool(getattr(self, "_drag_live_cut_async_busy", False)):
            return
        timer = getattr(self, "_drag_live_cut_async_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._start_drag_live_cut_async_worker)
            self._drag_live_cut_async_timer = timer
        try:
            active = bool(timer.isActive())
        except Exception:
            active = False
        if not active:
            timer.start(self._drag_live_cut_async_delay_ms())

    def _start_drag_live_cut_async_worker(self) -> None:
        if bool(getattr(self, "_drag_live_cut_async_busy", False)):
            return
        request = getattr(self, "_drag_live_cut_pending_request", None)
        if not isinstance(request, dict):
            return
        self._drag_live_cut_pending_request = None
        self._drag_live_cut_async_busy = True
        token = int(getattr(self, "_drag_live_cut_async_token", 0) or 0) + 1
        self._drag_live_cut_async_token = token
        use_gpu = self._drag_live_cut_gpu_enabled()
        signal = getattr(self, "drag_live_cut_async_result", None)

        def _run() -> None:
            payload = {
                "session_id": int(request.get("session_id", 0) or 0),
                "token": token,
                "request": request,
                "candidate": None,
                "scores": [],
            }
            try:
                scores = _compute_live_cut_boundary_scores_standalone(
                    str(request.get("media_path") or ""),
                    int(request.get("score_start_frame", request.get("search_start_frame", 0)) or 0),
                    int(request.get("search_end_frame", 0) or 0),
                    use_gpu=use_gpu,
                )
                payload["scores"] = scores
                payload["candidate"] = _select_live_cut_candidate_from_scores_standalone(
                    scores,
                    float(request.get("fps", 30.0) or 30.0),
                    search_start_frame=int(request.get("search_start_frame", 0) or 0),
                    search_end_frame=int(request.get("search_end_frame", 0) or 0),
                    origin_frame=int(request.get("origin_frame", 0) or 0),
                    target_frame=int(request.get("target_frame", 0) or 0),
                    direction=int(request.get("direction", 1) or 1),
                )
            except Exception as exc:
                payload["error"] = str(exc)
            try:
                if signal is not None:
                    signal.emit(payload)
            except Exception:
                pass

        thread = threading.Thread(target=_run, name="timeline-live-cut-snap", daemon=True)
        thread.start()

    def _cache_drag_live_cut_scores(self, request: dict, scores: list[tuple[float, int]]) -> None:
        if not isinstance(request, dict) or not scores:
            return
        cache = getattr(self, "_live_cut_snap_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._live_cut_snap_cache = cache
        try:
            media_path = str(request.get("media_path") or "")
            fps = max(1.0, float(request.get("fps") or self._get_fps()))
            first_frame = int(request.get("score_start_frame", request.get("search_start_frame", 0)) or 0)
            last_frame = int(request.get("search_end_frame", first_frame) or first_frame)
        except Exception:
            return
        key = ("drag_async", media_path, round(fps, 3), first_frame, last_frame)
        cache[key] = {
            "path": media_path,
            "fps": fps,
            "first_frame": first_frame,
            "last_frame": last_frame,
            "scores": list(scores),
            "search_start_local_sec": float(request.get("search_start_local_sec", 0.0) or 0.0),
            "search_end_local_sec": float(request.get("search_end_local_sec", 0.0) or 0.0),
        }
        if len(cache) > 160:
            try:
                cache.pop(next(iter(cache)))
            except (StopIteration, RuntimeError, TypeError):
                pass

    def _on_drag_live_cut_async_result(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        try:
            session_id = int(payload.get("session_id", -1))
            current_session_id = int(getattr(self, "_drag_live_cut_session_id", 0) or 0)
        except Exception:
            return
        if session_id != current_session_id:
            return
        self._drag_live_cut_async_busy = False
        request = payload.get("request")
        if not isinstance(request, dict):
            return
        scores = payload.get("scores")
        if isinstance(scores, list):
            self._cache_drag_live_cut_scores(request, scores)
        self._drag_live_cut_last_completed_signature = request.get("signature")
        if str(getattr(self, "_drag_edge", "") or "") != "diamond":
            self._finish_drag_live_cut_session(clear_shadow=True)
            return

        candidate = payload.get("candidate")
        if isinstance(candidate, dict):
            try:
                fps = max(1.0, float(request.get("fps") or self._get_fps()))
                clip_start = float(request.get("clip_start", 0.0) or 0.0)
                local_cut_sec = float(candidate.get("local_sec", 0.0) or 0.0)
                cut_sec = self._snap_to_frame(clip_start + max(0.0, local_cut_sec))
                source = dict(candidate)
                source.update(
                    {
                        "media_path": str(request.get("media_path") or ""),
                        "local_sec": local_cut_sec,
                        "clip_start": clip_start,
                        "fps": fps,
                        "direction": int(request.get("direction", 1) or 1),
                        "search_start_local_sec": float(request.get("search_start_local_sec", 0.0) or 0.0),
                        "search_end_local_sec": float(request.get("search_end_local_sec", 0.0) or 0.0),
                        "async": True,
                    }
                )
                self._drag_live_cut_async_candidate = {"time": cut_sec, "kind": "cut_live", "source": source}
                self._set_drag_live_cut_shadow(cut_sec)
                if getattr(self, "_drag_diamond_pair", None) is not None:
                    self._apply_drag(float(getattr(self, "_drag_last_delta", 0.0) or 0.0))
            except Exception:
                self._drag_live_cut_async_candidate = None
                self._set_drag_live_cut_shadow(None)
        else:
            self._drag_live_cut_async_candidate = None
            self._set_drag_live_cut_shadow(None)

        if isinstance(getattr(self, "_drag_live_cut_pending_request", None), dict):
            timer = getattr(self, "_drag_live_cut_async_timer", None)
            if timer is None:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(self._start_drag_live_cut_async_worker)
                self._drag_live_cut_async_timer = timer
            try:
                if not timer.isActive():
                    timer.start(8)
            except Exception:
                pass

    def _playhead_auto_cut_magnet_enabled(self) -> bool:
        for owner in self._iter_live_cut_snap_owners():
            settings = getattr(owner, "settings", None)
            if not isinstance(settings, dict):
                continue
            if settings.get("timeline_live_cut_snap_enabled") is False:
                return False
            if "playhead_auto_cut_magnet_enabled" in settings:
                return bool(settings.get("playhead_auto_cut_magnet_enabled"))
        try:
            from core.settings import load_settings

            settings = load_settings() or {}
            if settings.get("timeline_live_cut_snap_enabled") is False:
                return False
            return bool(settings.get("playhead_auto_cut_magnet_enabled", True))
        except Exception:
            return True

    def _playhead_auto_cut_magnet_settings(self) -> dict:
        merged: dict = {}
        try:
            from core.settings import load_settings

            loaded = load_settings() or {}
            if isinstance(loaded, dict):
                merged.update(loaded)
        except Exception:
            pass
        for owner in self._iter_live_cut_snap_owners():
            settings = getattr(owner, "settings", None)
            if isinstance(settings, dict):
                merged.update(settings)
        return merged

    def _playhead_cut_candidate_is_confident(self, candidate: dict) -> bool:
        try:
            score = float(candidate.get("score", 0.0) or 0.0)
            median_score = float(candidate.get("median_score", 0.0) or 0.0)
        except Exception:
            return False
        margin = score - median_score
        ratio = score / max(1.0, median_score)
        return bool(score >= 18.0 and margin >= 7.0 and ratio >= 1.35)

    def _playhead_cut_magnet_verify_candidate(
        self,
        media_path: str,
        fps: float,
        candidate: dict,
    ) -> dict | None:
        settings = self._playhead_auto_cut_magnet_settings()
        if settings.get("playhead_auto_cut_magnet_strict_verify_enabled") is False:
            return dict(candidate)
        if not self._playhead_cut_candidate_is_confident(candidate):
            return None

        try:
            import cv2  # type: ignore
            import core.cut_boundary as cut_boundary
        except Exception:
            return None

        media_path = os.path.abspath(os.path.expanduser(str(media_path or "")))
        cap = self._live_cut_snap_capture(media_path, cv2)
        if cap is None:
            return None
        try:
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        except Exception:
            frame_count = 0
        if frame_count <= 1:
            return None

        try:
            coarse_frame = int(candidate.get("frame"))
        except Exception:
            return None
        fps = max(1.0, float(fps or self._get_fps()))
        verify_cache = getattr(self, "_playhead_cut_magnet_verify_cache", None)
        if not isinstance(verify_cache, dict):
            verify_cache = {}
            self._playhead_cut_magnet_verify_cache = verify_cache
        cache_key = (media_path, round(fps, 3), int(coarse_frame))
        if cache_key in verify_cache:
            cached = verify_cache.get(cache_key)
            return dict(cached) if isinstance(cached, dict) else None

        verify_settings = dict(settings)
        strict_multiplier = float(verify_settings.get("playhead_auto_cut_magnet_strict_multiplier", 1.22) or 1.22)
        try:
            existing_multiplier = float(verify_settings.get("scan_cut_follower_strict_multiplier", 1.08) or 1.08)
        except Exception:
            existing_multiplier = 1.08
        verify_settings["scan_cut_follower_strict_multiplier"] = max(existing_multiplier, strict_multiplier)
        verify_settings["scan_cut_auto_verify_rollback_window_sec"] = float(
            verify_settings.get("playhead_auto_cut_magnet_verify_window_sec", 0.42) or 0.42
        )
        verify_settings["scan_cut_auto_verify_forward_window_sec"] = float(
            verify_settings.get("playhead_auto_cut_magnet_verify_window_sec", 0.42) or 0.42
        )
        verify_settings["scan_cut_auto_verify_window_stages"] = [8, 4, 2, 1]
        verify_settings["scan_cut_follower_strict_region_bonus"] = max(
            2,
            int(verify_settings.get("scan_cut_follower_strict_region_bonus", 1) or 1),
        )
        verify_settings["scan_cut_follower_gray_agreement_frames"] = max(1, int(round(fps * 0.06)))
        verify_settings["scan_cut_follower_gray_color_agreement_frames"] = max(1, int(round(fps * 0.08)))

        profile = None
        try:
            profiles = getattr(cut_boundary, "CUT_BOUNDARY_GRID_PROFILES", {}) or {}
            profile = dict(profiles.get("medium") or {})
        except Exception:
            profile = None
        if not profile:
            try:
                profile = dict(cut_boundary.cut_boundary_scan_profile(verify_settings))
            except Exception:
                profile = None

        try:
            verifier = getattr(cut_boundary, "_auto_grid_v3_manual_verify_strict", None)
            if not callable(verifier):
                return None
            verified = verifier(
                cap,
                cv2,
                fps=fps,
                frame_count=frame_count,
                coarse_frame=coarse_frame,
                settings=verify_settings,
                scan_profile=profile,
                sample_positions=None,
            )
        except Exception:
            verified = None

        if not isinstance(verified, dict) or not bool(verified.get("passed")):
            verify_cache[cache_key] = None
            return None

        try:
            verified_frame = int(verified.get("frame"))
        except Exception:
            verify_cache[cache_key] = None
            return None
        max_shift_frames = max(2, int(round(fps * 0.16)))
        if abs(verified_frame - coarse_frame) > max_shift_frames:
            verify_cache[cache_key] = None
            return None

        out = dict(candidate)
        out.update(
            {
                "frame": int(verified_frame),
                "local_sec": self._snap_to_frame(float(verified_frame) / fps),
                "strict_verified": True,
                "strict_mode": str(verified.get("mode") or verified.get("reason") or "strict_visual_verify"),
                "strict_score": float(verified.get("score", 0.0) or 0.0),
                "strict_regions": int(verified.get("regions", 0) or 0),
                "strict_color_score": float(verified.get("color_score", 0.0) or 0.0),
                "strict_color_regions": int(verified.get("color_regions", 0) or 0),
            }
        )
        verify_cache[cache_key] = out
        if len(verify_cache) > 128:
            try:
                verify_cache.pop(next(iter(verify_cache)))
            except (StopIteration, RuntimeError, TypeError):
                pass
        return out

    def _playhead_confirmed_cut_boundary_secs(self) -> list[float]:
        rows: list = []

        def _extend(value) -> None:
            if isinstance(value, (list, tuple)):
                rows.extend(list(value))

        for owner in self._iter_live_cut_snap_owners():
            _extend(getattr(owner, "boundary_times", None))
            _extend(getattr(owner, "_project_boundary_times", None))
            timeline = getattr(owner, "timeline", None)
            if timeline is not None:
                _extend(getattr(timeline, "boundary_times", None))
                canvas = getattr(timeline, "canvas", None)
                if canvas is not None:
                    _extend(getattr(canvas, "boundary_times", None))
            canvas = getattr(owner, "canvas", None)
            if canvas is not None:
                _extend(getattr(canvas, "boundary_times", None))

        secs: list[float] = []
        seen: set[int] = set()
        for item in rows:
            try:
                if isinstance(item, dict):
                    visible = item.get("visible", True) is not False and item.get("hidden", False) is not True
                    if not visible:
                        continue
                    sec = float(item.get("timeline_sec", item.get("time", item.get("start", 0.0))) or 0.0)
                else:
                    sec = float(item or 0.0)
            except Exception:
                continue
            if sec <= 0.0:
                continue
            key = int(round(sec * 1000.0))
            if key in seen:
                continue
            seen.add(key)
            secs.append(self._snap_to_frame(sec))
        secs.sort()
        return secs

    def _playhead_confirmed_cut_boundary_snap_sec(
        self,
        target_global_sec: float,
        previous_global_sec: float,
        direction: int,
        fps: float,
    ) -> float | None:
        boundaries = self._playhead_confirmed_cut_boundary_secs()
        if not boundaries:
            return None
        fps = max(1.0, float(fps or self._get_fps()))
        epsilon = max(0.001, 1.0 / fps)
        pps = max(1.0, float(getattr(self, "pps", 100.0) or 100.0))
        near_threshold = max(4.0 / fps, min(0.12, 18.0 / pps))
        target_global_sec = self._snap_to_frame(float(target_global_sec or 0.0))
        previous_global_sec = self._snap_to_frame(float(previous_global_sec or target_global_sec))
        origin_global = getattr(self, "_playhead_cut_magnet_origin_sec", previous_global_sec)
        try:
            origin_global = self._snap_to_frame(float(origin_global or previous_global_sec))
        except Exception:
            origin_global = previous_global_sec
        origin_exclusion = max(0.02, 2.0 / fps)

        if int(direction) > 0:
            candidates = [
                sec
                for sec in boundaries
                if sec > previous_global_sec + epsilon
                and sec <= target_global_sec + near_threshold
                and abs(sec - origin_global) > origin_exclusion
            ]
            return min(candidates) if candidates else None
        candidates = [
            sec
            for sec in boundaries
            if sec < previous_global_sec - epsilon
            and sec >= target_global_sec - near_threshold
            and abs(sec - origin_global) > origin_exclusion
        ]
        return max(candidates) if candidates else None

    def _playhead_auto_cut_snap_sec(self, target_global_sec: float, previous_global_sec: float) -> tuple[float, bool]:
        target_global_sec = self._snap_to_frame(float(target_global_sec or 0.0))
        previous_global_sec = self._snap_to_frame(float(previous_global_sec or target_global_sec))
        if not self._playhead_auto_cut_magnet_enabled():
            return target_global_sec, False

        fps = max(1.0, float(self._get_fps() if hasattr(self, "_get_fps") else 30.0))
        epsilon = max(0.001, 1.0 / fps)
        if target_global_sec > previous_global_sec + epsilon:
            direction = 1
        elif target_global_sec < previous_global_sec - epsilon:
            direction = -1
        else:
            return target_global_sec, False

        confirmed_sec = self._playhead_confirmed_cut_boundary_snap_sec(
            target_global_sec,
            previous_global_sec,
            direction,
            fps,
        )
        if confirmed_sec is not None:
            return self._snap_to_frame(float(confirmed_sec)), True

        ctx = self._resolve_live_cut_snap_context(target_global_sec)
        if not isinstance(ctx, dict):
            return target_global_sec, False
        media_path = str(ctx.get("media_path") or "").strip()
        if not media_path:
            return target_global_sec, False

        local_sec = float(ctx.get("local_sec", target_global_sec) or 0.0)
        clip_start = float(ctx.get("clip_start", 0.0) or 0.0)
        fps = max(1.0, float(ctx.get("fps") or fps))
        search_start, search_end = self._live_cut_search_window_secs(local_sec, direction)

        # When a drag starts exactly on a cut, ignore that starting cut so a
        # second drag can move onward instead of snapping back to the same frame.
        origin_global = getattr(self, "_playhead_cut_magnet_origin_sec", previous_global_sec)
        try:
            origin_local = max(0.0, float(origin_global or 0.0) - clip_start)
        except Exception:
            origin_local = local_sec
        exclusion = max(0.02, 2.0 / fps)
        if direction > 0:
            search_start = max(float(search_start), origin_local + exclusion)
        else:
            search_end = min(float(search_end), max(0.0, origin_local - exclusion))
        if search_end <= search_start + epsilon:
            return target_global_sec, False

        detected = self._detect_live_cut_boundary_record(
            media_path,
            local_sec,
            fps,
            direction=direction,
            search_start_local_sec=search_start,
            search_end_local_sec=search_end,
        )
        if detected is None:
            return target_global_sec, False
        verified = self._playhead_cut_magnet_verify_candidate(media_path, fps, detected)
        if verified is None:
            return target_global_sec, False
        detected = verified
        local_cut_sec = detected.get("local_sec") if isinstance(detected, dict) else detected
        try:
            cut_sec = self._snap_to_frame(clip_start + max(0.0, float(local_cut_sec)))
        except Exception:
            return target_global_sec, False
        if direction > 0 and cut_sec <= previous_global_sec + epsilon:
            return target_global_sec, False
        if direction < 0 and cut_sec >= previous_global_sec - epsilon:
            return target_global_sec, False
        distance_limit = max(0.20, min(1.20, abs(float(search_end) - float(search_start)) + (2.0 / fps)))
        if abs(cut_sec - target_global_sec) > distance_limit:
            return target_global_sec, False
        return cut_sec, True

    def _resolve_live_cut_snap_context(self, global_sec: float) -> dict | None:
        global_sec = float(global_sec or 0.0)
        for owner in self._iter_live_cut_snap_owners():
            resolver = getattr(owner, "_resolve_active_context", None)
            if not callable(resolver):
                continue
            try:
                ctx = resolver(global_sec=global_sec)
            except Exception:
                ctx = None
            if not isinstance(ctx, dict):
                continue
            media_path = str(ctx.get("clip_file") or ctx.get("media_path") or "").strip()
            if not media_path:
                continue
            return {
                "media_path": media_path,
                "local_sec": float(ctx.get("local_sec", global_sec) or 0.0),
                "clip_start": float(ctx.get("clip_start", 0.0) or 0.0),
                "fps": float(ctx.get("fps") or self._get_fps()),
            }

        for owner in self._iter_live_cut_snap_owners():
            media_path = str(getattr(owner, "media_path", "") or "").strip()
            if not media_path:
                sm = getattr(owner, "sm", None)
                media_path = str(getattr(sm, "current_file", "") or "").strip()
            if not media_path:
                continue
            local_sec = global_sec
            converter = getattr(owner, "_global_to_local_sec", None)
            if callable(converter):
                try:
                    local_sec = float(converter(global_sec))
                except Exception:
                    local_sec = global_sec
            return {
                "media_path": media_path,
                "local_sec": float(local_sec or 0.0),
                "clip_start": max(0.0, global_sec - float(local_sec or 0.0)),
                "fps": float(self._get_fps()),
            }
        return None

    def _drag_live_cut_snap_candidates(self, global_sec: float, *, edge: str = "") -> list[dict]:
        if str(edge or "") != "diamond":
            self._set_drag_live_cut_shadow(None)
            return []
        if not self._live_cut_snap_settings_enabled():
            self._set_drag_live_cut_shadow(None)
            return []
        ctx = self._resolve_live_cut_snap_context(global_sec)
        if not isinstance(ctx, dict):
            self._set_drag_live_cut_shadow(None)
            return []
        media_path = str(ctx.get("media_path") or "").strip()
        if not media_path:
            self._set_drag_live_cut_shadow(None)
            return []
        request = self._build_drag_live_cut_async_request(global_sec, ctx)
        if not isinstance(request, dict):
            self._set_drag_live_cut_shadow(None)
            return []
        cached = self._drag_live_cut_cached_candidates(request)
        if cached:
            self._schedule_drag_live_cut_async(request)
            return cached
        self._schedule_drag_live_cut_async(request)
        return []

    def _snap_candidate_threshold_sec(self, candidate: dict, base_threshold: float) -> float:
        kind = str((candidate or {}).get("kind") or "")
        if kind == "cut_live":
            pps = max(1.0, float(getattr(self, "pps", 1.0) or 1.0))
            fps = max(1.0, float(self._get_fps() if hasattr(self, "_get_fps") else 30.0))
            return max(base_threshold, min(0.20, 24.0 / pps), 6.0 / fps)
        if kind not in {"user_guide", "shadow_playhead"}:
            return base_threshold
        pps = max(1.0, float(getattr(self, "pps", 1.0) or 1.0))
        expanded_px = (22.0 if kind == "shadow_playhead" else 18.0) / pps
        fps = max(1.0, float(self._get_fps() if hasattr(self, "_get_fps") else 30.0))
        return max(base_threshold, expanded_px, (3.0 if kind == "shadow_playhead" else 2.0) / fps)

    def _snap_drag_time(self, value: float, candidates: list[dict], threshold: float, min_value: float, max_value: float) -> tuple[float, dict | None]:
        value = self._snap_to_frame(value)
        min_value = self._snap_to_frame(min_value)
        max_value = self._snap_to_frame(max_value)
        best = None
        best_dist = float("inf")
        for candidate in candidates:
            t = self._snap_to_frame(candidate.get("time", 0.0))
            if t < min_value or t > max_value:
                continue
            dist = abs(t - value)
            local_threshold = self._snap_candidate_threshold_sec(candidate, threshold)
            if dist <= local_threshold and dist < best_dist:
                best = candidate
                best_dist = dist
        if best:
            return self._snap_to_frame(best["time"]), best
        return max(min_value, min(value, max_value)), None

    def _snap_drag_span(self, start: float, duration: float, candidates: list[dict], threshold: float, min_start: float, max_end: float) -> tuple[float, float, dict | None]:
        start = self._snap_to_frame(start)
        duration = max(0.0, self._snap_to_frame(duration))
        min_start = self._snap_to_frame(min_start)
        max_start = self._snap_to_frame(max_end - duration)
        start = max(min_start, min(start, max_start))
        anchors = (("start", start), ("end", self._snap_to_frame(start + duration)))
        best = None
        best_dist = float("inf")
        best_start = start
        best_guide = start
        for anchor_name, anchor_time in anchors:
            for candidate in candidates:
                t = self._snap_to_frame(candidate.get("time", 0.0))
                next_start = t if anchor_name == "start" else self._snap_to_frame(t - duration)
                if next_start < min_start or next_start > max_start:
                    continue
                dist = abs(t - anchor_time)
                local_threshold = self._snap_candidate_threshold_sec(candidate, threshold)
                if dist <= local_threshold and dist < best_dist:
                    best = candidate
                    best_dist = dist
                    best_start = next_start
                    best_guide = t
        if best:
            return self._snap_to_frame(best_start), self._snap_to_frame(best_guide), best
        return start, start, None

    def _commit_inline_edit_with_speaker_split(self) -> None:
        if not self._edit_active:
            return
        editor = getattr(self, "_inline_editor", None)
        if editor is not None:
            self._sync_inline_editor_state_from_widget(text_changed=False)
        if not self._edit_text.strip():
            return

        safe_text = self._edit_text.replace("\n", "\u2028")
        line = int(self._edit_line)
        cursor = int(self._edit_cursor)
        for seg in self.segments:
            if seg.get("line") == line:
                seg["text"] = self._edit_text
                break
        self._inline_commit_in_progress = True
        try:
            self.sig_inline_text_changed.emit(line, safe_text)
        finally:
            self._inline_commit_in_progress = False
        if hasattr(self, "_pending_split_sec"):
            del self._pending_split_sec
        if hasattr(self, "sig_speaker_split_request"):
            self.sig_speaker_split_request.emit(line, cursor)
        self._end_inline_edit()

    def _handle_edit_key(self, ev):
        if (
            ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and ev.modifiers() & (Qt.KeyboardModifier.MetaModifier | Qt.KeyboardModifier.ControlModifier)
            and not (ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        ):
            self._commit_inline_edit_with_speaker_split()
            return
        super()._handle_edit_key(ev)

    def _finish_timing_drag_cleanup(self, dirty: QRect | None = None) -> None:
        preview_rect = self._merge_preview_repaint_rect(getattr(self, "_drag_merge_pair", None))
        self._drag_merge_pair = None
        self._drag_suppresses_gap_candidate_attachment = False
        self._drag_center_reorder_direction = None
        self._finish_drag_live_cut_session(clear_shadow=True)
        self._set_drag_live_cut_shadow(None)
        if preview_rect.isValid() and not preview_rect.isEmpty():
            dirty = preview_rect if dirty is None else dirty.united(preview_rect)
        super()._finish_timing_drag_cleanup(dirty)

    def mouseReleaseEvent(self, ev):
        if getattr(self, "_is_panning", False):
            self._is_panning = False
            self.unsetCursor()
            self._clear_pending_center_drag()
            return
        if getattr(self, "_is_scrubbing", False):
            self._is_scrubbing = False
            finisher = getattr(self, "_finish_playhead_handle_scrub", None)
            if callable(finisher):
                finisher()
            self._clear_pending_center_drag()
            return

        if getattr(self, "_drag_edge", None) == "diamond":
            dirty = getattr(self, "_drag_last_paint_rect", None) or self._drag_visual_rect()
            pair = getattr(self, "_drag_diamond_pair", None)
            guide_secs = self._drag_release_guide_secs()
            self._emit_diamond_pair_time_changed(pair)
            self._finish_timing_drag_cleanup(dirty)
            self._remember_drag_release_guides(guide_secs)
            self._clear_pending_center_drag()
            return

        if self._drag_seg:
            dirty = getattr(self, "_drag_last_paint_rect", None) or self._drag_visual_rect()
            edge = str(self._drag_edge) if self._drag_edge else ""
            merge_pair = tuple(getattr(self, "_drag_merge_pair", ()) or ())
            guide_secs = self._drag_release_guide_secs()
            if edge in {"square_left", "square_right"} and len(merge_pair) == 2:
                # 변경 금지: 화살표 병합/지우기 메뉴는 드래그 중 열린 QTextCursor
                # edit block을 먼저 닫은 뒤 실행해야 한다. 닫기 전에 자막 블록
                # userData(start/end)를 쓰면 Qt가 블록 병합 정리 과정에서 원래
                # 시간으로 되돌려 자막 세그먼트와 에디터 싱크가 어긋난다.
                self.drag_finished.emit()
                self.diamond_merge.emit(int(merge_pair[0]), int(merge_pair[1]))
                self._suppress_next_drag_finished_emit = True
            else:
                emit_edge = edge
                if edge == "center":
                    reorder_direction = str(getattr(self, "_drag_center_reorder_direction", "") or "")
                    if reorder_direction in {"left", "right"}:
                        emit_edge = f"center_reorder_{reorder_direction}"
                self.seg_time_changed.emit(
                    self._drag_seg.get("line", 0),
                    self._drag_seg["start"],
                    self._drag_seg["end"],
                    emit_edge,
                )
            self._finish_timing_drag_cleanup(dirty)
            self._remember_drag_release_guides(guide_secs)
            self._clear_pending_center_drag()
            return

        self._clear_pending_center_drag()


TimelineInlineEditMixin = TimelineSubtitleSegmentEditingMixin


__all__ = [
    "NEW_SUBTITLE_PLACEHOLDER",
    "TimelineInlineEditMixin",
    "TimelineSubtitleSegmentEditingMixin",
]
