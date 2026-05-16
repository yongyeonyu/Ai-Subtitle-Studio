"""Tab-key timing actions for subtitle editing UX."""

from __future__ import annotations


class EditorTabTimingMixin:
    """Apply the two Tab timing actions requested for subtitle segment editing."""

    _TAB_DIAMOND_TOLERANCE_SEC = 0.05
    _TAB_DIAMOND_SEARCH_SEC = 2.0

    def _tab_timing_playhead_sec(self) -> float:
        canvas = getattr(getattr(self, "timeline", None), "canvas", None)
        raw_sec = getattr(canvas, "playhead_sec", None)
        if raw_sec is None:
            raw_sec = getattr(getattr(self, "video_player", None), "current_time", 0.0)
        snap = getattr(self, "_snap_to_frame", None)
        try:
            sec = float(raw_sec or 0.0)
        except Exception:
            sec = 0.0
        return float(snap(sec) if callable(snap) else round(sec, 6))

    def _tab_timing_min_span(self) -> float:
        fps_getter = getattr(self, "_current_frame_fps", None)
        try:
            fps = float(fps_getter() if callable(fps_getter) else getattr(self, "video_fps", 30.0))
        except Exception:
            fps = 30.0
        return max(0.02, min(0.1, 1.0 / max(1.0, fps)))

    def _tab_timing_rows(self) -> list[dict]:
        rows_getter = getattr(self, "_get_current_segments", None)
        if not callable(rows_getter):
            return []
        try:
            source_rows = list(rows_getter() or [])
        except Exception:
            return []
        rows: list[dict] = []
        for idx, row in enumerate(source_rows):
            if not isinstance(row, dict):
                continue
            if row.get("is_gap") or row.get("stt_pending") or row.get("_live_stt_preview") or row.get("_live_subtitle_preview"):
                continue
            try:
                start = float(row.get("start", 0.0) or 0.0)
                end = float(row.get("end", start) or start)
            except Exception:
                continue
            if end <= start:
                continue
            normalized = dict(row)
            normalized["start"] = start
            normalized["end"] = end
            try:
                normalized["line"] = int(row.get("line", idx) or idx)
            except Exception:
                normalized["line"] = idx
            rows.append(normalized)
        rows.sort(
            key=lambda row: (
                float(row.get("start", 0.0) or 0.0),
                float(row.get("end", 0.0) or 0.0),
                int(row.get("line", 0) or 0),
            )
        )
        return rows

    def _tab_timing_closest_diamond_pair(self, rows: list[dict], sec: float) -> tuple[int, int] | None:
        best: tuple[float, int, tuple[int, int]] | None = None
        tolerance = float(self._TAB_DIAMOND_TOLERANCE_SEC)
        for idx in range(max(0, len(rows) - 1)):
            left = rows[idx]
            right = rows[idx + 1]
            try:
                boundary = float(left.get("end", 0.0) or 0.0)
                if abs(boundary - float(right.get("start", 0.0) or 0.0)) > tolerance:
                    continue
            except Exception:
                continue
            dist = abs(boundary - sec)
            if dist > float(self._TAB_DIAMOND_SEARCH_SEC):
                continue
            candidate = (dist, idx, (idx, idx + 1))
            if best is None or candidate < best:
                best = candidate
        return best[2] if best is not None else None

    def _tab_timing_playhead_row(self, rows: list[dict], sec: float) -> tuple[int, dict] | None:
        canvas = getattr(getattr(self, "timeline", None), "canvas", None)
        active_line = getattr(canvas, "active_seg_line", None)
        active_start = getattr(canvas, "active_seg_start", None)
        eps = 0.001
        matches: list[tuple[int, float, float, int, dict]] = []
        for idx, row in enumerate(rows):
            start = float(row.get("start", 0.0) or 0.0)
            end = float(row.get("end", start) or start)
            if not (start + eps < sec < end - eps):
                continue
            line_penalty = 0 if active_line is not None and int(row.get("line", -1) or -1) == int(active_line) else 1
            try:
                start_penalty = abs(start - float(active_start))
            except Exception:
                start_penalty = 0.0
            edge_distance = min(sec - start, end - sec)
            matches.append((line_penalty, start_penalty, edge_distance, idx, row))
        if not matches:
            return None
        matches.sort(key=lambda item: item[:4])
        chosen = matches[0]
        return int(chosen[3]), chosen[4]

    def _tab_timing_attached_pair(self, rows: list[dict], row_idx: int, side: str) -> tuple[int, int] | None:
        tolerance = float(self._TAB_DIAMOND_TOLERANCE_SEC)
        if side == "left" and row_idx > 0:
            left = rows[row_idx - 1]
            right = rows[row_idx]
            if abs(float(left.get("end", 0.0) or 0.0) - float(right.get("start", 0.0) or 0.0)) <= tolerance:
                return row_idx - 1, row_idx
        if side == "right" and row_idx + 1 < len(rows):
            left = rows[row_idx]
            right = rows[row_idx + 1]
            if abs(float(left.get("end", 0.0) or 0.0) - float(right.get("start", 0.0) or 0.0)) <= tolerance:
                return row_idx, row_idx + 1
        return None

    def _tab_timing_containing_candidate(
        self,
        rows: list[dict],
        sec: float,
        min_span: float,
    ) -> tuple[str, tuple[int, int] | dict, float | None, float | None, str | None] | None:
        selected = self._tab_timing_playhead_row(rows, sec)
        if selected is None:
            return None
        row_idx, row = selected
        start = float(row.get("start", 0.0) or 0.0)
        end = float(row.get("end", start) or start)
        candidates: list[tuple[float, int, str, tuple[int, int] | None, dict, float, float]] = []
        if end - sec >= min_span:
            candidates.append(
                (
                    sec - start,
                    0,
                    "square_left",
                    self._tab_timing_attached_pair(rows, row_idx, "left"),
                    row,
                    max(0.0, sec),
                    end,
                )
            )
        if sec - start >= min_span:
            candidates.append(
                (
                    end - sec,
                    1,
                    "square_right",
                    self._tab_timing_attached_pair(rows, row_idx, "right"),
                    row,
                    start,
                    sec,
                )
            )
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[:2])
        _dist, _side_order, edge_type, pair, chosen_row, new_start, new_end = candidates[0]
        if pair is not None:
            return "diamond", pair, None, None, None
        return "segment", chosen_row, new_start, new_end, edge_type

    def _tab_timing_extension_candidate(
        self,
        rows: list[dict],
        sec: float,
        min_span: float,
    ) -> tuple[dict, float, float, str] | None:
        canvas = getattr(getattr(self, "timeline", None), "canvas", None)
        try:
            total_duration = float(getattr(canvas, "total_duration", 0.0) or 0.0)
        except Exception:
            total_duration = 0.0
        best: tuple[float, int, dict, float, float, str] | None = None
        eps = 0.001
        for idx, row in enumerate(rows):
            start = float(row.get("start", 0.0) or 0.0)
            end = float(row.get("end", start) or start)
            if sec < start - eps:
                previous_end = float(rows[idx - 1].get("end", 0.0) or 0.0) if idx > 0 else 0.0
                if sec < previous_end - eps:
                    continue
                new_start = max(0.0, sec, previous_end)
                if new_start <= start - eps and end - new_start >= min_span:
                    candidate = (start - sec, 1, row, new_start, end, "square_left")
                    if best is None or candidate[:2] < best[:2]:
                        best = candidate
            elif sec > end + eps:
                next_start = (
                    float(rows[idx + 1].get("start", end) or end)
                    if idx < len(rows) - 1
                    else max(total_duration, sec)
                )
                if sec > next_start + eps:
                    continue
                new_end = min(sec, next_start)
                if new_end >= end + eps and new_end - start >= min_span:
                    candidate = (sec - end, 0, row, start, new_end, "square_right")
                    if best is None or candidate[:2] < best[:2]:
                        best = candidate
        if best is None:
            return None
        return best[2], best[3], best[4], best[5]

    def _tab_timing_push_undo(self) -> None:
        undo = getattr(self, "_undo_mgr", None)
        if undo is not None and hasattr(undo, "push_immediate"):
            undo.push_immediate()

    def _tab_timing_apply_diamond(
        self,
        rows: list[dict],
        pair: tuple[int, int],
        sec: float,
        min_span: float,
        handler,
    ) -> bool:
        left = rows[pair[0]]
        right = rows[pair[1]]
        left_start = float(left.get("start", 0.0) or 0.0)
        right_end = float(right.get("end", left_start) or left_start)
        if right_end - left_start < min_span * 2:
            return False
        boundary = max(left_start + min_span, min(right_end - min_span, sec))
        self._tab_timing_push_undo()
        handler(int(left.get("line", 0) or 0), left_start, boundary, "diamond")
        handler(int(right.get("line", 0) or 0), boundary, right_end, "diamond")
        return True

    def _move_tab_timing_boundary(self) -> bool:
        split_pending = getattr(self, "_timeline_inline_split_pending", None)
        if bool(split_pending() if callable(split_pending) else split_pending):
            return False
        handler = getattr(self, "_on_seg_time_changed", None)
        if not callable(handler):
            return False
        rows = self._tab_timing_rows()
        if not rows:
            return False

        sec = self._tab_timing_playhead_sec()
        min_span = self._tab_timing_min_span()
        snap = getattr(self, "_snap_to_frame", None)
        if callable(snap):
            sec = float(snap(sec))

        containing_candidate = self._tab_timing_containing_candidate(rows, sec, min_span)
        if containing_candidate is not None:
            mode, payload, new_start, new_end, edge_type = containing_candidate
            if mode == "diamond":
                return self._tab_timing_apply_diamond(rows, payload, sec, min_span, handler)
            self._tab_timing_push_undo()
            handler(int(payload.get("line", 0) or 0), new_start, new_end, edge_type)
            return True

        diamond_pair = self._tab_timing_closest_diamond_pair(rows, sec)
        if diamond_pair is not None:
            return self._tab_timing_apply_diamond(rows, diamond_pair, sec, min_span, handler)

        candidate = self._tab_timing_extension_candidate(rows, sec, min_span)
        if candidate is None:
            return False
        row, new_start, new_end, edge_type = candidate
        self._tab_timing_push_undo()
        handler(int(row.get("line", 0) or 0), new_start, new_end, edge_type)
        return True

    def _trigger_magnet(self):
        return self._move_tab_timing_boundary()
