"""
Centralized subtitle-segment canvas editing helpers.

This module gathers the timeline behaviors that are specific to subtitle
segment editing so future canvas edit work lands in one place. The legacy
inline-edit mixin stays as the compatibility base, while this mixin layers
segment-resize/diamond/snap/drag/merge-preview behavior on top.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QCursor, QPolygon

from core.coerce import safe_float as _as_float
from core.native_swift_timeline import (
    build_subtitle_drag_snap_base_via_swift,
    compute_subtitle_merge_preview_via_swift,
)
from ui.editor.editor_helpers import find_segment_at
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

class TimelineSubtitleSegmentEditingMixin(_LegacyTimelineInlineEditMixin):
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
            if self._diamond_hit_rect(self._x(s1["end"]), margin=margin).contains(x, y):
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
        self._set_drag_merge_preview_pair(None)
        self._clear_active_gaps_for_segment_drag()
        self._drag_snap_candidates_cache = self._drag_snap_candidates()
        self._drag_last_paint_rect = self._drag_visual_rect()
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

        for item in self._build_drag_snap_base_candidates():
            source = item.get("source")
            if source is dragged:
                continue
            if item.get("kind") in {"gap", "user_guide", "shadow_playhead"}:
                snapped_edge = self._snap_to_frame(_as_float(item.get("time"), -1.0))
                if any(abs(snapped_edge - original) < 0.05 for original in drag_original_edges):
                    continue
            candidates.append(item)

        priority = {
            "shadow_playhead": 14,
            "user_guide": 13,
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

    def _snap_candidate_threshold_sec(self, candidate: dict, base_threshold: float) -> float:
        kind = str((candidate or {}).get("kind") or "")
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
                self.diamond_merge.emit(int(merge_pair[0]), int(merge_pair[1]))
            else:
                self.seg_time_changed.emit(
                    self._drag_seg.get("line", 0),
                    self._drag_seg["start"],
                    self._drag_seg["end"],
                    edge,
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
