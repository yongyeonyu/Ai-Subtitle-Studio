"""Deterministic editor automation helpers used by remote verification flows."""

from __future__ import annotations

from typing import Any

from ui.editor.editor_helpers import find_segment_at


class EditorAutomationMixin:
    _AUTOMATION_SEGMENT_TOLERANCE_SEC = 0.05

    def _automation_canvas(self):
        timeline = getattr(self, "timeline", None)
        return getattr(timeline, "canvas", None) if timeline is not None else None

    def _automation_total_duration(self) -> float:
        canvas = self._automation_canvas()
        total = float(getattr(canvas, "total_duration", 0.0) or 0.0) if canvas is not None else 0.0
        if total > 0.0:
            return total
        video_player = getattr(self, "video_player", None)
        return max(0.0, float(getattr(video_player, "total_time", 0.0) or 0.0))

    def _automation_playhead_sec(self) -> float:
        canvas = self._automation_canvas()
        playhead = float(getattr(canvas, "playhead_sec", 0.0) or 0.0) if canvas is not None else 0.0
        return self._automation_snap_sec(playhead)

    def _automation_snap_sec(self, sec: float) -> float:
        snapper = getattr(self, "_snap_to_frame", None)
        if callable(snapper):
            try:
                return float(snapper(float(sec or 0.0)) or 0.0)
            except Exception:
                return float(sec or 0.0)
        return float(sec or 0.0)

    def _automation_min_span_sec(self) -> float:
        fps_getter = getattr(self, "_current_frame_fps", None)
        try:
            fps = float(fps_getter() if callable(fps_getter) else getattr(self, "video_fps", 30.0) or 30.0)
        except Exception:
            fps = 30.0
        return max(0.02, min(0.1, 1.0 / max(1.0, fps)))

    def _automation_segments(self, *, force_rebuild: bool = False) -> list[dict[str, Any]]:
        getter = getattr(self, "_get_current_segments", None)
        if not callable(getter):
            return []
        try:
            rows = getter(force_rebuild=bool(force_rebuild))
        except TypeError:
            rows = getter()
        except Exception:
            return []
        out: list[dict[str, Any]] = []
        for item in list(rows or []):
            if isinstance(item, dict):
                out.append(dict(item))
        return out

    def _automation_segment_line(self, seg: dict[str, Any] | None) -> int | None:
        if not isinstance(seg, dict):
            return None
        try:
            line = int(seg.get("line", -1))
        except Exception:
            return None
        return line if line >= 0 else None

    def _automation_segment_start(self, seg: dict[str, Any] | None) -> float | None:
        if not isinstance(seg, dict):
            return None
        try:
            return float(seg.get("start", 0.0) or 0.0)
        except Exception:
            return None

    def _automation_segment_text(self, seg: dict[str, Any] | None, *, limit: int = 120) -> str:
        if not isinstance(seg, dict):
            return ""
        text = str(seg.get("text", "") or "").strip()
        return text[:limit] if len(text) > limit else text

    def _automation_locate_segment(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        line: int | None = None,
        start_sec: float | None = None,
        at_playhead: bool = False,
    ) -> dict[str, Any] | None:
        segments = list(rows or self._automation_segments(force_rebuild=True))
        editable = [seg for seg in segments if isinstance(seg, dict) and not bool(seg.get("is_gap"))]
        if not editable:
            return None

        if line is not None:
            for seg in editable:
                if self._automation_segment_line(seg) == int(line):
                    return dict(seg)

        if start_sec is not None:
            target = self._automation_snap_sec(float(start_sec))
            for seg in editable:
                start = self._automation_segment_start(seg)
                if start is not None and abs(start - target) < self._AUTOMATION_SEGMENT_TOLERANCE_SEC:
                    return dict(seg)

        if at_playhead:
            seg = find_segment_at(editable, self._automation_playhead_sec(), skip_gap=True)
            return dict(seg) if isinstance(seg, dict) else None

        return None

    def _automation_active_segment(self, *, rows: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
        segments = list(rows or self._automation_segments(force_rebuild=True))
        canvas = self._automation_canvas()
        active_line = getattr(canvas, "active_seg_line", None) if canvas is not None else None
        seg = self._automation_locate_segment(rows=segments, line=active_line)
        if seg is not None:
            return seg

        active_start = getattr(canvas, "active_seg_start", None) if canvas is not None else None
        try:
            active_start_sec = float(active_start)
        except Exception:
            active_start_sec = None
        if active_start_sec is not None:
            seg = self._automation_locate_segment(rows=segments, start_sec=active_start_sec)
            if seg is not None:
                return seg

        seg = self._automation_locate_segment(rows=segments, at_playhead=True)
        if seg is not None:
            return seg
        return None

    def _automation_segment_index(self, rows: list[dict[str, Any]], target: dict[str, Any] | None) -> int | None:
        if not isinstance(target, dict):
            return None
        target_line = self._automation_segment_line(target)
        target_start = self._automation_segment_start(target)
        for idx, seg in enumerate(list(rows or [])):
            if not isinstance(seg, dict):
                continue
            if target_line is not None and self._automation_segment_line(seg) == target_line:
                return idx
            start = self._automation_segment_start(seg)
            if target_start is not None and start is not None and abs(start - target_start) < self._AUTOMATION_SEGMENT_TOLERANCE_SEC:
                return idx
        return None

    def _automation_pair_payload(self, left: dict[str, Any], right: dict[str, Any], *, side: str) -> dict[str, Any]:
        return {
            "side": str(side or ""),
            "boundary_sec": self._automation_snap_sec(float(left.get("end", 0.0) or 0.0)),
            "left": self._automation_segment_summary(left),
            "right": self._automation_segment_summary(right),
        }

    def _automation_diamond_pairs(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        active: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        segments = list(rows or self._automation_segments(force_rebuild=True))
        target = dict(active or self._automation_active_segment(rows=segments) or {})
        idx = self._automation_segment_index(segments, target)
        if idx is None:
            return {}

        out: dict[str, dict[str, Any]] = {}
        tol = self._AUTOMATION_SEGMENT_TOLERANCE_SEC
        if idx > 0:
            left = segments[idx - 1]
            right = segments[idx]
            if (
                isinstance(left, dict)
                and isinstance(right, dict)
                and not bool(left.get("is_gap"))
                and not bool(right.get("is_gap"))
                and abs(float(left.get("end", 0.0) or 0.0) - float(right.get("start", 0.0) or 0.0)) < tol
            ):
                out["left"] = self._automation_pair_payload(left, right, side="left")
        if idx + 1 < len(segments):
            left = segments[idx]
            right = segments[idx + 1]
            if (
                isinstance(left, dict)
                and isinstance(right, dict)
                and not bool(left.get("is_gap"))
                and not bool(right.get("is_gap"))
                and abs(float(left.get("end", 0.0) or 0.0) - float(right.get("start", 0.0) or 0.0)) < tol
            ):
                out["right"] = self._automation_pair_payload(left, right, side="right")
        return out

    def _automation_choose_diamond_pair(
        self,
        *,
        side: str = "closest",
        rows: list[dict[str, Any]] | None = None,
        active: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        pairs = self._automation_diamond_pairs(rows=rows, active=active)
        normalized = str(side or "closest").strip().lower()
        if normalized in {"left", "right"}:
            return dict(pairs.get(normalized) or {}) or None
        if normalized != "closest":
            raise ValueError("invalid_diamond_side")
        if not pairs:
            return None
        if len(pairs) == 1:
            return dict(next(iter(pairs.values())))
        playhead = self._automation_playhead_sec()
        ordered = sorted(
            pairs.values(),
            key=lambda item: abs(float(item.get("boundary_sec", 0.0) or 0.0) - playhead),
        )
        return dict(ordered[0]) if ordered else None

    def _automation_segment_summary(self, seg: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(seg, dict):
            return {}
        return {
            "line": self._automation_segment_line(seg),
            "start": self._automation_segment_start(seg),
            "end": float(seg.get("end", seg.get("start", 0.0)) or 0.0),
            "text": self._automation_segment_text(seg),
            "is_gap": bool(seg.get("is_gap")),
        }

    def _automation_split_candidate_near_playhead(
        self,
        rows: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, float]:
        playhead = self._automation_playhead_sec()
        min_margin = max(0.05, self._automation_min_span_sec())
        candidates: list[tuple[float, dict[str, Any], float]] = []
        for seg in list(rows or []):
            if not isinstance(seg, dict) or bool(seg.get("is_gap")):
                continue
            try:
                start = float(seg.get("start", 0.0) or 0.0)
                end = float(seg.get("end", 0.0) or 0.0)
            except Exception:
                continue
            if end - start <= min_margin * 2.0:
                continue
            split_sec = playhead if start + min_margin < playhead < end - min_margin else (start + end) / 2.0
            distance = 0.0 if split_sec == playhead else abs(((start + end) / 2.0) - playhead)
            candidates.append((distance, dict(seg), self._automation_snap_sec(split_sec)))
        if not candidates:
            return None, playhead
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1], candidates[0][2]

    def _automation_inline_editor_state(self) -> tuple[str, int | None]:
        canvas = self._automation_canvas()
        editor = getattr(canvas, "_inline_editor", None) if canvas is not None else None
        if editor is None or not bool(getattr(canvas, "_edit_active", False)):
            return "", None
        try:
            text = str(editor.toPlainText() or "")
        except Exception:
            text = ""
        try:
            cursor = int(editor.textCursor().position())
        except Exception:
            cursor = None
        return text, cursor

    def automation_editor_state_snapshot(self) -> dict[str, Any]:
        rows = self._automation_segments(force_rebuild=True)
        canvas = self._automation_canvas()
        active = self._automation_active_segment(rows=rows)
        idx = self._automation_segment_index(rows, active)
        prev_seg = rows[idx - 1] if idx is not None and idx > 0 else None
        next_seg = rows[idx + 1] if idx is not None and (idx + 1) < len(rows) else None
        total_duration = self._automation_total_duration()
        playhead = self._automation_playhead_sec()
        left_pair = self._automation_choose_diamond_pair(side="left", rows=rows, active=active)
        right_pair = self._automation_choose_diamond_pair(side="right", rows=rows, active=active)
        timeline = getattr(self, "timeline", None)
        scroll = getattr(timeline, "scroll", None) if timeline is not None else None
        scrollbar = scroll.horizontalScrollBar() if scroll is not None and hasattr(scroll, "horizontalScrollBar") else None
        timeline_scroll_x = float(scrollbar.value() or 0.0) if scrollbar is not None else 0.0
        try:
            smart_split_ready = bool(
                active is not None
                and float(active.get("start", 0.0) or 0.0) + 0.05 < playhead < float(active.get("end", 0.0) or 0.0) - 0.05
            )
        except Exception:
            smart_split_ready = False
        split_pending_sec = None
        if canvas is not None and hasattr(canvas, "_pending_split_sec"):
            try:
                split_pending_sec = float(getattr(canvas, "_pending_split_sec", 0.0) or 0.0)
            except Exception:
                split_pending_sec = None
        inline_edit_mode = "smart_split" if split_pending_sec is not None else ("plain" if bool(getattr(canvas, "_edit_active", False)) else "")
        inline_edit_text, inline_edit_cursor = self._automation_inline_editor_state()
        video_player = getattr(self, "video_player", None)
        try:
            video_visible = bool(video_player is not None and video_player.isVisible())
        except Exception:
            video_visible = False
        return {
            "playhead_sec": playhead,
            "shadow_playhead_sec": None if getattr(canvas, "shadow_playhead_sec", None) is None else float(getattr(canvas, "shadow_playhead_sec", 0.0) or 0.0),
            "shadow_playhead_active": getattr(canvas, "shadow_playhead_sec", None) is not None if canvas is not None else False,
            "total_duration": total_duration,
            "active_seg_line": getattr(canvas, "active_seg_line", None) if canvas is not None else None,
            "active_seg_start": float(getattr(canvas, "active_seg_start", 0.0) or 0.0) if getattr(canvas, "active_seg_start", None) is not None else None,
            "segment_count": len([seg for seg in rows if not bool(seg.get("is_gap"))]),
            "gap_count": len([seg for seg in rows if bool(seg.get("is_gap"))]),
            "active_segment": self._automation_segment_summary(active),
            "previous_segment": self._automation_segment_summary(prev_seg),
            "next_segment": self._automation_segment_summary(next_seg),
            "diamond_left": dict(left_pair or {}),
            "diamond_right": dict(right_pair or {}),
            "smart_split_ready": smart_split_ready,
            "inline_edit_active": bool(getattr(canvas, "_edit_active", False)) if canvas is not None else False,
            "inline_edit_mode": inline_edit_mode,
            "inline_edit_text": self._automation_segment_text({"text": inline_edit_text}, limit=240) if inline_edit_text else "",
            "inline_edit_text_length": len(inline_edit_text),
            "inline_edit_cursor": inline_edit_cursor,
            "split_pending_sec": split_pending_sec,
            "timeline_pps": float(getattr(canvas, "pps", 0.0) or 0.0) if canvas is not None else 0.0,
            "timeline_scroll_x": timeline_scroll_x,
            "timeline_fit_locked": bool(getattr(timeline, "_fit_to_view_locked", False)) if timeline is not None else False,
            "playback_center_lock": bool(getattr(timeline, "_playback_center_lock", False)) if timeline is not None else False,
            "video_visible": video_visible,
            "active_footer_menu_id": str(getattr(self, "_active_footer_menu_id", "") or ""),
        }

    def automation_set_playhead(self, sec: float, *, center: bool = False, sync_video: bool = True) -> dict[str, Any]:
        timeline = getattr(self, "timeline", None)
        if timeline is None or not hasattr(timeline, "set_playhead"):
            raise ValueError("timeline_unavailable")
        total = self._automation_total_duration()
        target = max(0.0, float(sec or 0.0))
        if total > 0.0:
            target = min(target, total)
        target = self._automation_snap_sec(target)
        resetter = getattr(self, "_reset_playhead_smoothing", None)
        if callable(resetter):
            resetter(target)
        timeline.set_playhead(target)
        if center and hasattr(timeline, "center_to_sec"):
            timeline.center_to_sec(target, smooth=False)
        elif hasattr(timeline, "ensure_sec_visible"):
            timeline.ensure_sec_visible(target, smooth=False)
        if sync_video:
            video_player = getattr(self, "video_player", None)
            seeker = getattr(video_player, "seek", None)
            if callable(seeker):
                localizer = getattr(self, "_global_to_local_sec", None)
                local_sec = localizer(target) if callable(localizer) else target
                seeker(local_sec)
        return {"playhead_sec": target, "editor_runtime": self.automation_editor_state_snapshot()}

    def automation_pin_shadow_playhead(self, sec: float | None = None) -> dict[str, Any]:
        timeline = getattr(self, "timeline", None)
        if timeline is None:
            raise ValueError("timeline_unavailable")
        if sec is None:
            pinner = getattr(timeline, "pin_shadow_playhead", None)
            if not callable(pinner):
                raise ValueError("shadow_playhead_unavailable")
            changed = bool(pinner())
        else:
            setter = getattr(timeline, "set_shadow_playhead", None)
            if not callable(setter):
                raise ValueError("shadow_playhead_unavailable")
            changed = bool(setter(self._automation_snap_sec(float(sec or 0.0))))
        return {
            "changed": changed,
            "shadow_playhead_sec": getattr(getattr(timeline, "canvas", None), "shadow_playhead_sec", None),
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_clear_shadow_playhead(self) -> dict[str, Any]:
        timeline = getattr(self, "timeline", None)
        clearer = getattr(timeline, "clear_shadow_playhead", None) if timeline is not None else None
        if not callable(clearer):
            raise ValueError("shadow_playhead_unavailable")
        changed = bool(clearer())
        return {
            "changed": changed,
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_zoom_max(self) -> dict[str, Any]:
        timeline = getattr(self, "timeline", None)
        if timeline is None:
            raise ValueError("timeline_unavailable")
        zoomer = getattr(timeline, "zoom_to_max", None)
        if callable(zoomer):
            zoomer()
        elif hasattr(timeline, "_apply_zoom") and hasattr(timeline, "canvas"):
            current_pps = max(0.001, float(getattr(timeline.canvas, "pps", 1.0) or 1.0))
            timeline._apply_zoom(500.0 / current_pps)
        else:
            raise ValueError("zoom_unavailable")
        return {
            "timeline_pps": float(getattr(getattr(timeline, "canvas", None), "pps", 0.0) or 0.0),
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_set_video_visible(self, action: str) -> dict[str, Any]:
        toggler = getattr(self, "_toggle_video", None)
        if not callable(toggler):
            raise ValueError("video_toggle_unavailable")
        state = self.automation_editor_state_snapshot()
        visible = bool(state.get("video_visible"))
        normalized = str(action or "toggle").strip().lower() or "toggle"
        if normalized not in {"toggle", "show", "hide"}:
            raise ValueError("invalid_video_action")
        should_toggle = (
            normalized == "toggle"
            or (normalized == "show" and not visible)
            or (normalized == "hide" and visible)
        )
        if should_toggle:
            toggler()
        runtime = self.automation_editor_state_snapshot()
        return {
            "action": normalized,
            "video_visible": bool(runtime.get("video_visible")),
            "active_footer_menu_id": str(runtime.get("active_footer_menu_id", "") or ""),
            "editor_runtime": runtime,
        }

    def automation_set_playback_state(self, action: str) -> dict[str, Any]:
        video_player = getattr(self, "video_player", None)
        media_player = getattr(video_player, "media_player", None) if video_player is not None else None
        if video_player is None or media_player is None:
            raise ValueError("video_player_unavailable")
        normalized = str(action or "").strip().lower()
        if normalized not in {"play", "pause", "toggle"}:
            raise ValueError("invalid_playback_action")
        is_playing = False
        try:
            state = media_player.playbackState()
            playing_state = getattr(getattr(media_player, "PlaybackState", None), "PlayingState", None)
            if playing_state is not None:
                is_playing = state == playing_state
        except Exception:
            is_playing = False
        if normalized == "toggle":
            if hasattr(video_player, "toggle_play"):
                video_player.toggle_play()
            else:
                raise ValueError("playback_control_unavailable")
        elif normalized == "play":
            if not is_playing:
                if hasattr(video_player, "toggle_play"):
                    video_player.toggle_play()
                elif hasattr(media_player, "play"):
                    media_player.play()
                else:
                    raise ValueError("playback_control_unavailable")
        else:
            if is_playing:
                if hasattr(video_player, "pause_video"):
                    video_player.pause_video()
                elif hasattr(media_player, "pause"):
                    media_player.pause()
                else:
                    raise ValueError("playback_control_unavailable")
        return {
            "action": normalized,
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_select_segment(
        self,
        *,
        line: int | None = None,
        start_sec: float | None = None,
        at_playhead: bool = False,
        center: bool = False,
        sync_playhead: bool = False,
    ) -> dict[str, Any]:
        rows = self._automation_segments(force_rebuild=True)
        target = self._automation_locate_segment(
            rows=rows,
            line=line,
            start_sec=start_sec,
            at_playhead=at_playhead or (line is None and start_sec is None),
        )
        if target is None:
            raise ValueError("segment_not_found")
        sync = getattr(self, "_sync_cursor_to_seg", None)
        if callable(sync):
            sync(target, ensure_visible=True, move_cursor=True, sync_playhead=bool(sync_playhead))
        else:
            self._active_seg_start = float(target.get("start", 0.0) or 0.0)
            timeline = getattr(self, "timeline", None)
            if timeline is not None and hasattr(timeline, "set_active"):
                timeline.set_active(self._active_seg_start)
            if sync_playhead and timeline is not None and hasattr(timeline, "set_playhead"):
                timeline.set_playhead(self._active_seg_start)
        timeline = getattr(self, "timeline", None)
        if center and timeline is not None and hasattr(timeline, "center_to_sec"):
            start = float(target.get("start", 0.0) or 0.0)
            end = float(target.get("end", start) or start)
            timeline.center_to_sec((start + end) / 2.0, smooth=False)
        return {
            "selected_line": self._automation_segment_line(target),
            "selected_start": self._automation_segment_start(target),
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def _automation_reselect_line(self, line: int | None) -> None:
        if line is None:
            return
        try:
            self.automation_select_segment(line=int(line), center=False, sync_playhead=False)
        except Exception:
            return

    def automation_move_segment_boundary_to_playhead(self, edge: str) -> dict[str, Any]:
        normalized_edge = str(edge or "").strip().lower()
        if normalized_edge not in {"left", "right"}:
            raise ValueError("invalid_segment_edge")
        rows = self._automation_segments(force_rebuild=True)
        active = self._automation_active_segment(rows=rows)
        if active is None:
            raise ValueError("active_segment_missing")
        idx = self._automation_segment_index(rows, active)
        if idx is None:
            raise ValueError("active_segment_missing")
        playhead = self._automation_playhead_sec()
        min_span = self._automation_min_span_sec()
        start = float(active.get("start", 0.0) or 0.0)
        end = float(active.get("end", start) or start)
        if normalized_edge == "left":
            prev_end = float(rows[idx - 1].get("end", 0.0) or 0.0) if idx > 0 else 0.0
            new_start = self._automation_snap_sec(max(prev_end, min(end - min_span, playhead)))
            if new_start >= end:
                raise ValueError("segment_boundary_invalid")
            undo = getattr(self, "_undo_mgr", None)
            if undo is not None and hasattr(undo, "push_immediate"):
                undo.push_immediate()
            self._on_seg_time_changed(int(active.get("line", 0) or 0), new_start, end, "square_left")
            self._automation_reselect_line(self._automation_segment_line(active))
            return {
                "edge": "left",
                "boundary_sec": new_start,
                "line": self._automation_segment_line(active),
                "editor_runtime": self.automation_editor_state_snapshot(),
            }
        next_start = float(rows[idx + 1].get("start", end) or end) if idx + 1 < len(rows) else self._automation_total_duration()
        if next_start <= 0.0:
            next_start = max(end, self._automation_total_duration())
        new_end = self._automation_snap_sec(max(start + min_span, min(next_start, playhead)))
        if new_end <= start:
            raise ValueError("segment_boundary_invalid")
        undo = getattr(self, "_undo_mgr", None)
        if undo is not None and hasattr(undo, "push_immediate"):
            undo.push_immediate()
        self._on_seg_time_changed(int(active.get("line", 0) or 0), start, new_end, "square_right")
        self._automation_reselect_line(self._automation_segment_line(active))
        return {
            "edge": "right",
            "boundary_sec": new_end,
            "line": self._automation_segment_line(active),
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_move_diamond_to_playhead(self, *, side: str = "closest") -> dict[str, Any]:
        rows = self._automation_segments(force_rebuild=True)
        active = self._automation_active_segment(rows=rows)
        if active is None:
            raise ValueError("active_segment_missing")
        pair = self._automation_choose_diamond_pair(side=side, rows=rows, active=active)
        if pair is None:
            raise ValueError("diamond_pair_missing")
        left = dict(pair.get("left") or {})
        right = dict(pair.get("right") or {})
        left_start = float(left.get("start", 0.0) or 0.0)
        right_end = float(right.get("end", left_start) or left_start)
        min_span = self._automation_min_span_sec()
        lower = left_start + min_span
        upper = right_end - min_span
        if upper <= lower:
            raise ValueError("diamond_pair_too_small")
        boundary = self._automation_snap_sec(max(lower, min(upper, self._automation_playhead_sec())))
        undo = getattr(self, "_undo_mgr", None)
        if undo is not None and hasattr(undo, "push_immediate"):
            undo.push_immediate()
        self._on_seg_time_changed(int(left.get("line", 0) or 0), left_start, boundary, "diamond")
        self._on_seg_time_changed(int(right.get("line", 0) or 0), boundary, right_end, "diamond")
        target_line = self._automation_segment_line(active)
        if target_line is None:
            target_line = int(right.get("line", left.get("line", 0)) or 0)
        self._automation_reselect_line(target_line)
        return {
            "side": str(pair.get("side", side) or side),
            "boundary_sec": boundary,
            "left_line": int(left.get("line", 0) or 0),
            "right_line": int(right.get("line", 0) or 0),
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_merge_diamond(self, *, side: str = "closest") -> dict[str, Any]:
        rows = self._automation_segments(force_rebuild=True)
        active = self._automation_active_segment(rows=rows)
        if active is None:
            raise ValueError("active_segment_missing")
        pair = self._automation_choose_diamond_pair(side=side, rows=rows, active=active)
        if pair is None:
            raise ValueError("diamond_pair_missing")
        left = dict(pair.get("left") or {})
        right = dict(pair.get("right") or {})
        self._on_diamond_merge(int(left.get("line", 0) or 0), int(right.get("line", 0) or 0))
        self._automation_reselect_line(int(left.get("line", 0) or 0))
        return {
            "side": str(pair.get("side", side) or side),
            "left_line": int(left.get("line", 0) or 0),
            "right_line": int(right.get("line", 0) or 0),
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_begin_smart_split_at_playhead(
        self,
        *,
        line: int | None = None,
        start_sec: float | None = None,
        at_playhead: bool = False,
    ) -> dict[str, Any]:
        rows = self._automation_segments(force_rebuild=True)
        active = self._automation_locate_segment(
            rows=rows,
            line=line,
            start_sec=start_sec,
            at_playhead=at_playhead or (line is None and start_sec is None),
        )
        selection_source = "requested"
        if active is None:
            active, split_sec = self._automation_split_candidate_near_playhead(rows)
            if active is not None:
                self.automation_set_playhead(split_sec, center=True, sync_video=False)
                selection_source = "nearest_splittable_fallback"
            else:
                raise ValueError("segment_not_found")
        playhead = self._automation_playhead_sec()

        def _ready_for_segment(seg: dict[str, Any] | None) -> bool:
            if seg is None:
                return False
            try:
                start = float(seg.get("start", 0.0) or 0.0)
                end = float(seg.get("end", 0.0) or 0.0)
                return start + 0.05 < playhead < end - 0.05
            except Exception:
                return False

        if not _ready_for_segment(active):
            fallback = self._automation_locate_segment(rows=rows, line=None, start_sec=None, at_playhead=True)
            if fallback is not None and fallback != active and _ready_for_segment(fallback):
                active = fallback
                selection_source = "playhead_fallback"
        if not _ready_for_segment(active):
            fallback, fallback_split_sec = self._automation_split_candidate_near_playhead(rows)
            if fallback is not None:
                # Automation hot path: coverage scripts may land on a tiny SRT
                # fragment; move to the nearest splittable segment instead of
                # reporting a false feature failure.
                self.automation_set_playhead(fallback_split_sec, center=True, sync_video=False)
                playhead = self._automation_playhead_sec()
                active = fallback
                selection_source = "nearest_splittable_fallback"
        canvas = self._automation_canvas()
        starter = getattr(canvas, "start_inline_edit", None) if canvas is not None else None
        if not callable(starter):
            raise ValueError("inline_edit_unavailable")
        if canvas is not None:
            line_num = int(active.get("line", 0) or 0)
            start = float(active.get("start", 0.0) or 0.0)
            center_sec = (start + float(active.get("end", start) or start)) / 2.0
            timeline = getattr(self, "timeline", None)
            if timeline is not None and hasattr(timeline, "set_active"):
                timeline.set_active(start)
            if timeline is not None and hasattr(timeline, "center_to_sec"):
                timeline.center_to_sec(center_sec, smooth=False)
            starter(line_num, start, split_at_playhead=True)
            if not bool(getattr(canvas, "_edit_active", False)) or not hasattr(canvas, "_pending_split_sec"):
                raise ValueError("smart_split_unavailable")
            setattr(
                self,
                "_automation_last_inline_edit_request",
                {
                    "mode": "smart_split",
                    "line": line_num,
                    "start": start,
                    "split_sec": float(getattr(canvas, "_pending_split_sec", playhead) or playhead),
                },
            )
        return {
            "line": int(active.get("line", 0) or 0),
            "start": float(active.get("start", 0.0) or 0.0),
            "selection_source": selection_source,
            "split_sec": float(getattr(canvas, "_pending_split_sec", 0.0) or 0.0) if canvas is not None else 0.0,
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def _automation_restore_inline_edit_request(self) -> bool:
        request = getattr(self, "_automation_last_inline_edit_request", None)
        if not isinstance(request, dict) or str(request.get("mode") or "") != "smart_split":
            return False
        try:
            split_sec = float(request.get("split_sec", 0.0) or 0.0)
        except (TypeError, ValueError):
            split_sec = 0.0
        if split_sec > 0.0:
            try:
                self.automation_set_playhead(split_sec, center=False, sync_video=False)
            except Exception as exc:
                _ = exc
        try:
            self.automation_begin_smart_split_at_playhead(
                line=int(request.get("line")) if request.get("line") is not None else None,
                start_sec=float(request.get("start")) if request.get("start") is not None else None,
                at_playhead=False,
            )
        except Exception:
            return False
        cursor_position = request.get("cursor")
        if cursor_position is not None:
            canvas = self._automation_canvas()
            editor = getattr(canvas, "_inline_editor", None) if canvas is not None else None
            if editor is not None:
                try:
                    text = str(editor.toPlainText() or "")
                    cursor = editor.textCursor()
                    cursor.setPosition(max(0, min(int(cursor_position), len(text))))
                    editor.setTextCursor(cursor)
                except Exception as exc:
                    _ = exc
        # Automation hot path: app layout/media refresh can steal inline focus
        # between appctl commands, so keep the last target available for commit.
        restored = dict(getattr(self, "_automation_last_inline_edit_request", {}) or {})
        restored.update({key: value for key, value in request.items() if key in {"cursor"}})
        setattr(self, "_automation_last_inline_edit_request", restored)
        return True

    def automation_set_inline_edit_cursor(self, position: int) -> dict[str, Any]:
        canvas = self._automation_canvas()
        editor = getattr(canvas, "_inline_editor", None) if canvas is not None else None
        if canvas is None or editor is None or not bool(getattr(canvas, "_edit_active", False)):
            if self._automation_restore_inline_edit_request():
                canvas = self._automation_canvas()
                editor = getattr(canvas, "_inline_editor", None) if canvas is not None else None
        if canvas is None or editor is None or not bool(getattr(canvas, "_edit_active", False)):
            raise ValueError("inline_edit_inactive")
        try:
            text = str(editor.toPlainText() or "")
        except Exception:
            text = ""
        target = int(position)
        if target < 0:
            target = len(text) + target
        target = max(0, min(target, len(text)))
        cursor = editor.textCursor()
        cursor.setPosition(target)
        editor.setTextCursor(cursor)
        sync = getattr(canvas, "_sync_inline_editor_state_from_widget", None)
        if callable(sync):
            sync(text_changed=False)
        editor.setFocus()
        request = getattr(self, "_automation_last_inline_edit_request", None)
        if isinstance(request, dict):
            request["cursor"] = target
            setattr(self, "_automation_last_inline_edit_request", request)
        return {
            "cursor": target,
            "text_length": len(text),
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_commit_inline_edit(self) -> dict[str, Any]:
        canvas = self._automation_canvas()
        if canvas is None or not bool(getattr(canvas, "_edit_active", False)):
            if self._automation_restore_inline_edit_request():
                canvas = self._automation_canvas()
        if canvas is None or not bool(getattr(canvas, "_edit_active", False)):
            raise ValueError("inline_edit_inactive")
        committer = getattr(canvas, "_commit_inline_edit_or_split", None)
        if not callable(committer):
            raise ValueError("inline_edit_unavailable")
        committer()
        setattr(self, "_automation_last_inline_edit_request", None)
        return {
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_smart_split_at_playhead(self) -> dict[str, Any]:
        state = self.automation_editor_state_snapshot()
        if not bool(state.get("inline_edit_active")) or str(state.get("inline_edit_mode", "") or "") != "smart_split":
            active_line = state.get("active_seg_line")
            if active_line is not None:
                self.automation_begin_smart_split_at_playhead(line=int(active_line))
            else:
                self.automation_begin_smart_split_at_playhead(at_playhead=True)
        data = self.automation_commit_inline_edit()
        data["split_sec"] = float((data.get("editor_runtime") or {}).get("playhead_sec", self._automation_playhead_sec()) or 0.0)
        return data
