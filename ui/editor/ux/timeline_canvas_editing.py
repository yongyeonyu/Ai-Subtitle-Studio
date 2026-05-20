"""
Timeline canvas editing helpers.

This file owns the inline subtitle edit mixin plus the timing-drag helper used
by the canvas so edit-specific behavior stays separate from generic pointer
and navigation routing.
"""

from __future__ import annotations

import os
import threading

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import QApplication

from core.native_swift_timeline import apply_timing_drag_via_swift
from core.runtime import config
from ui.dialogs.qml_popup import show_context_menu
from ui.editor.ux.timeline_inline_text_editor import TimelineInlineTextEdit
from ui.timeline.timeline_segment_style import subtitle_segment_visual_style
from ui.timeline.timeline_constants import HANDLE_R, SUBTITLE_BOT, SUBTITLE_TOP


NEW_SUBTITLE_PLACEHOLDER = "새자막"
SUBTITLE_SEGMENT_FONT_PT = 13
STT_PREVIEW_FONT_PT = SUBTITLE_SEGMENT_FONT_PT


def apply_timing_drag(canvas, delta: float) -> None:
    if delta == 0:
        return
    before_rect = getattr(canvas, "_drag_last_paint_rect", None) or canvas._drag_visual_rect()
    edge = getattr(canvas, "_drag_edge", None)
    drag_duration = max(
        0.0,
        float(getattr(canvas, "_drag_s0_end", 0.0) or 0.0)
        - float(getattr(canvas, "_drag_s0_start", 0.0) or 0.0),
    )
    canvas._clear_drag_guides(update=False)
    snap_candidates = list(getattr(canvas, "_drag_snap_candidates_cache", []) or [])
    if not snap_candidates:
        snap_candidates = canvas._drag_snap_candidates()
        canvas._drag_snap_candidates_cache = snap_candidates
    snap_threshold = canvas._drag_snap_threshold_sec()

    def _native_snapped(result: dict | None) -> dict | None:
        if not isinstance(result, dict):
            return None
        try:
            snapped_time = result.get("snappedTime", None)
            if snapped_time is None:
                return None
            return {
                "time": canvas._snap_to_frame(float(snapped_time)),
                "kind": str(result.get("snappedKind", "") or ""),
            }
        except Exception:
            return None

    def _consume_shadow_snap(snapped: dict | None) -> None:
        consumer = getattr(canvas, "_consume_shadow_playhead_snap", None)
        if callable(consumer):
            try:
                consumer(snapped)
            except Exception:
                pass

    if edge == "diamond":
        pair = getattr(canvas, "_drag_diamond_pair", None)
        if pair is not None and pair[0] < len(canvas.segments) and pair[1] < len(canvas.segments):
            s1, s2 = canvas.segments[pair[0]], canvas.segments[pair[1]]
            orig = getattr(canvas, "_drag_diamond_orig", 0.0)
            requested_boundary = canvas._snap_to_frame(float(orig or 0.0) + float(delta or 0.0))
            live_cut_provider = getattr(canvas, "_drag_live_cut_snap_candidates", None)
            if callable(live_cut_provider):
                try:
                    live_cut_candidates = live_cut_provider(requested_boundary, edge="diamond")
                except Exception:
                    live_cut_candidates = []
                if live_cut_candidates:
                    snap_candidates = [*snap_candidates, *live_cut_candidates]

            native_candidates = []
            for candidate in snap_candidates:
                if not isinstance(candidate, dict):
                    continue
                try:
                    candidate_time = float(candidate.get("time", 0.0) or 0.0)
                except Exception:
                    continue
                native_candidates.append(
                    {
                        "time": canvas._snap_to_frame(candidate_time),
                        "kind": str(candidate.get("kind", "") or ""),
                        "threshold": float(canvas._snap_candidate_threshold_sec(candidate, snap_threshold)),
                    }
                )
            native = apply_timing_drag_via_swift(
                edge="diamond",
                delta=float(delta),
                original_start=float(s1.get("start", 0.0) or 0.0),
                original_end=float(orig or 0.0),
                min_value=float(s1.get("start", 0.0) or 0.0) + 0.1,
                max_value=float(s2.get("end", 0.0) or 0.0) - 0.1,
                frame_rate=float(canvas._get_fps() if hasattr(canvas, "_get_fps") else 30.0),
                snap_threshold=float(snap_threshold),
                candidates=native_candidates,
            )
            if native:
                boundary = canvas._snap_to_frame(float(native.get("start", orig) or orig))
                snapped = _native_snapped(native)
                s1["end"] = s2["start"] = boundary
                canvas._set_drag_guides(boundary, snapped)
                _consume_shadow_snap(snapped)
                canvas._update_drag_visual_rect(before_rect)
                return
            next_boundary = canvas._snap_to_frame(orig + delta)
            next_boundary = max(canvas._snap_to_frame(s1["start"] + 0.1), min(canvas._snap_to_frame(s2["end"] - 0.1), next_boundary))
            next_boundary, snapped = canvas._snap_drag_time(
                next_boundary,
                snap_candidates,
                snap_threshold,
                s1["start"] + 0.1,
                s2["end"] - 0.1,
            )
            s1["end"] = s2["start"] = next_boundary
            canvas._set_drag_guides(next_boundary, snapped)
            _consume_shadow_snap(snapped)
            canvas._update_drag_visual_rect(before_rect)
        return

    native_candidates = []
    for candidate in snap_candidates:
        if not isinstance(candidate, dict):
            continue
        try:
            candidate_time = float(candidate.get("time", 0.0) or 0.0)
        except Exception:
            continue
        native_candidates.append(
            {
                "time": canvas._snap_to_frame(candidate_time),
                "kind": str(candidate.get("kind", "") or ""),
                "threshold": float(canvas._snap_candidate_threshold_sec(candidate, snap_threshold)),
            }
        )

    seg = getattr(canvas, "_drag_seg", None)
    min_span = canvas._snap_to_frame(0.1)
    if not isinstance(seg, dict):
        return

    def _restore_adjacent_segments() -> None:
        adj_l = getattr(canvas, "_drag_adj_l", None)
        if isinstance(adj_l, dict):
            adj_l["start"] = canvas._snap_to_frame(float(getattr(canvas, "_drag_adj_orig_start_l", adj_l.get("start", 0.0)) or 0.0))
            adj_l["end"] = canvas._snap_to_frame(float(getattr(canvas, "_drag_adj_orig_end_l", adj_l.get("end", 0.0)) or 0.0))
        adj_r = getattr(canvas, "_drag_adj_r", None)
        if isinstance(adj_r, dict):
            adj_r["start"] = canvas._snap_to_frame(float(getattr(canvas, "_drag_adj_orig_start_r", adj_r.get("start", 0.0)) or 0.0))
            adj_r["end"] = canvas._snap_to_frame(float(getattr(canvas, "_drag_adj_orig_end_r", adj_r.get("end", 0.0)) or 0.0))

    def _sync_adjacent_segments_for_live_drag() -> None:
        _restore_adjacent_segments()
        edge_name = str(getattr(canvas, "_drag_edge", "") or "")
        if edge_name == "square_left":
            adj_l = getattr(canvas, "_drag_adj_l", None)
            if not isinstance(adj_l, dict):
                return
            original_shared = canvas._snap_to_frame(float(getattr(canvas, "_drag_s0_start", seg.get("start", 0.0)) or 0.0))
            original_adj_end = canvas._snap_to_frame(float(getattr(canvas, "_drag_adj_orig_end_l", adj_l.get("end", 0.0)) or 0.0))
            original_adj_start = canvas._snap_to_frame(float(getattr(canvas, "_drag_adj_orig_start_l", adj_l.get("start", 0.0)) or 0.0))
            if abs(original_adj_end - original_shared) >= 0.05:
                return
            if float(seg.get("start", original_shared) or original_shared) >= original_adj_end - 0.001:
                return
            requested_shared = canvas._snap_to_frame(float(seg.get("start", original_shared) or original_shared))
            if requested_shared <= original_adj_start + min_span:
                shared = original_adj_start
            else:
                min_prev_end = canvas._snap_to_frame(original_adj_start + min_span)
                shared = max(min_prev_end, requested_shared)
            shared = min(shared, canvas._snap_to_frame(float(seg.get("end", shared) or shared) - min_span))
            adj_l["end"] = shared
            seg["start"] = shared
        elif edge_name == "square_right":
            adj_r = getattr(canvas, "_drag_adj_r", None)
            if not isinstance(adj_r, dict):
                return
            original_shared = canvas._snap_to_frame(float(getattr(canvas, "_drag_s0_end", seg.get("end", 0.0)) or 0.0))
            original_adj_start = canvas._snap_to_frame(float(getattr(canvas, "_drag_adj_orig_start_r", adj_r.get("start", 0.0)) or 0.0))
            original_adj_end = canvas._snap_to_frame(float(getattr(canvas, "_drag_adj_orig_end_r", adj_r.get("end", 0.0)) or 0.0))
            if abs(original_adj_start - original_shared) >= 0.05:
                return
            if float(seg.get("end", original_shared) or original_shared) <= original_adj_start + 0.001:
                return
            requested_shared = canvas._snap_to_frame(float(seg.get("end", original_shared) or original_shared))
            if requested_shared >= original_adj_end - min_span:
                shared = original_adj_end
            else:
                max_next_start = canvas._snap_to_frame(original_adj_end - min_span)
                shared = min(max_next_start, requested_shared)
            shared = max(shared, canvas._snap_to_frame(float(seg.get("start", 0.0) or 0.0) + min_span))
            adj_r["start"] = shared
            seg["end"] = shared

    if edge == "square_right":
        limit = float(getattr(canvas, "total_duration", 0.0) or 0.0)
        min_end = canvas._snap_to_frame(float(seg.get("start", 0.0) or 0.0) + min_span)
        native = apply_timing_drag_via_swift(
            edge="square_right",
            delta=float(delta),
            original_start=float(canvas._drag_s0_start),
            original_end=float(canvas._drag_s0_end),
            min_value=float(min_end),
            max_value=float(limit),
            frame_rate=float(canvas._get_fps() if hasattr(canvas, "_get_fps") else 30.0),
            snap_threshold=float(snap_threshold),
            candidates=native_candidates,
        )
        if native:
            seg["end"] = canvas._snap_to_frame(float(native.get("end", seg.get("end", min_end)) or min_end))
            _sync_adjacent_segments_for_live_drag()
            snapped = _native_snapped(native)
            canvas._set_drag_guides(seg["end"], snapped)
            _consume_shadow_snap(snapped)
            canvas._update_drag_visual_rect(before_rect)
            return

    elif edge == "square_left":
        limit = 0.0
        max_start = canvas._snap_to_frame(float(seg.get("end", 0.0) or 0.0) - min_span)
        native = apply_timing_drag_via_swift(
            edge="square_left",
            delta=float(delta),
            original_start=float(canvas._drag_s0_start),
            original_end=float(canvas._drag_s0_end),
            min_value=float(limit),
            max_value=float(max_start),
            frame_rate=float(canvas._get_fps() if hasattr(canvas, "_get_fps") else 30.0),
            snap_threshold=float(snap_threshold),
            candidates=native_candidates,
        )
        if native:
            seg["start"] = canvas._snap_to_frame(float(native.get("start", seg.get("start", limit)) or limit))
            _sync_adjacent_segments_for_live_drag()
            if canvas.active_seg_start is not None:
                canvas.active_seg_start = seg["start"]
            if hasattr(canvas, "_sync_active_segment_key"):
                canvas._sync_active_segment_key(seg=seg)
            snapped = _native_snapped(native)
            canvas._set_drag_guides(seg["start"], snapped)
            _consume_shadow_snap(snapped)
            canvas._update_drag_visual_rect(before_rect)
            return

    elif edge == "center":
        total_limit = max(
            drag_duration,
            float(getattr(canvas, "total_duration", 0.0) or 0.0),
        )
        native = apply_timing_drag_via_swift(
            edge="center",
            delta=float(delta),
            original_start=float(canvas._drag_s0_start),
            original_end=float(canvas._drag_s0_end),
            min_value=0.0,
            max_value=float(total_limit),
            frame_rate=float(canvas._get_fps() if hasattr(canvas, "_get_fps") else 30.0),
            snap_threshold=float(snap_threshold),
            candidates=native_candidates,
        )
        if native:
            seg["start"] = canvas._snap_to_frame(float(native.get("start", seg.get("start", 0.0)) or 0.0))
            seg["end"] = canvas._snap_to_frame(float(native.get("end", seg.get("end", total_limit)) or total_limit))
            if canvas.active_seg_start is not None:
                canvas.active_seg_start = seg["start"]
            if hasattr(canvas, "_sync_active_segment_key"):
                canvas._sync_active_segment_key(seg=seg)
            guide_time = canvas._snap_to_frame(float(native.get("guideTime", seg["start"]) or seg["start"]))
            snapped = _native_snapped(native)
            canvas._set_drag_guides(guide_time, snapped)
            _consume_shadow_snap(snapped)
            canvas._update_drag_visual_rect(before_rect)
            return

    if edge == "square_right":
        next_end = canvas._snap_to_frame(canvas._drag_s0_end + delta)
        limit = canvas.total_duration
        min_end = canvas._snap_to_frame(seg["start"] + min_span)
        next_end = max(min_end, min(next_end, limit))
        seg["end"], snapped = canvas._snap_drag_time(next_end, snap_candidates, snap_threshold, min_end, limit)
        _sync_adjacent_segments_for_live_drag()
        canvas._set_drag_guides(seg["end"], snapped)
        _consume_shadow_snap(snapped)

    elif edge == "square_left":
        next_start = canvas._snap_to_frame(canvas._drag_s0_start + delta)
        limit = 0.0
        max_start = canvas._snap_to_frame(seg["end"] - min_span)
        next_start = min(max_start, max(next_start, limit))
        seg["start"], snapped = canvas._snap_drag_time(next_start, snap_candidates, snap_threshold, limit, max_start)
        _sync_adjacent_segments_for_live_drag()
        if canvas.active_seg_start is not None:
            canvas.active_seg_start = seg["start"]
        if hasattr(canvas, "_sync_active_segment_key"):
            canvas._sync_active_segment_key(seg=seg)
        canvas._set_drag_guides(seg["start"], snapped)
        _consume_shadow_snap(snapped)

    elif edge == "center":
        duration = drag_duration
        next_start = canvas._snap_to_frame(canvas._drag_s0_start + delta)
        left_limit = 0.0
        right_limit = max(duration, float(getattr(canvas, "total_duration", 0.0) or 0.0))
        next_start = max(left_limit, min(next_start, canvas._snap_to_frame(right_limit - duration)))
        next_start, guide_time, snapped = canvas._snap_drag_span(
            next_start,
            duration,
            snap_candidates,
            snap_threshold,
            left_limit,
            right_limit,
        )
        seg["start"] = next_start
        seg["end"] = canvas._snap_to_frame(next_start + duration)
        if canvas.active_seg_start is not None:
            canvas.active_seg_start = seg["start"]
        if hasattr(canvas, "_sync_active_segment_key"):
            canvas._sync_active_segment_key(seg=seg)
        canvas._set_drag_guides(guide_time, snapped)
        _consume_shadow_snap(snapped)

    canvas._update_drag_visual_rect(before_rect)


class TimelineInlineEditMixin:
    def _smart_split_edit_active(self) -> bool:
        return bool(getattr(self, "_edit_active", False) and hasattr(self, "_pending_split_sec"))

    def _subtitle_segment_font(self) -> QFont:
        return QFont(config.FONT, SUBTITLE_SEGMENT_FONT_PT)

    def _stt_preview_font(self) -> QFont:
        return QFont(config.FONT, STT_PREVIEW_FONT_PT)

    def _ensure_inline_editor(self):
        editor = getattr(self, "_inline_editor", None)
        if editor is None:
            editor = TimelineInlineTextEdit(self)
            self._inline_editor = editor
        editor.document().setDefaultFont(self._subtitle_segment_font())
        editor.setFont(self._subtitle_segment_font())
        return editor

    def _native_inline_editor_active(self) -> bool:
        editor = getattr(self, "_inline_editor", None)
        return bool(editor is not None and editor.isVisible() and self._edit_active)

    def _request_canvas_pause_playback(self) -> bool:
        owner = self
        visited: set[int] = set()
        while owner is not None and id(owner) not in visited:
            visited.add(id(owner))
            pause_handler = getattr(owner, "_pause_playback_for_keyboard_edit", None)
            if callable(pause_handler):
                try:
                    pause_handler()
                    return True
                except Exception:
                    return False
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
        return False

    def _request_canvas_play_pause_toggle(self) -> bool:
        owner = self
        visited: set[int] = set()
        while owner is not None and id(owner) not in visited:
            visited.add(id(owner))
            repeat_handler = getattr(owner, "_handle_repeat_play_pause_shortcut", None)
            if callable(repeat_handler):
                try:
                    repeat_handler("canvas_space")
                    return True
                except Exception:
                    return False
            toggle = getattr(owner, "_toggle_video_play", None)
            if callable(toggle):
                try:
                    toggle()
                    return True
                except Exception:
                    return False
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
        return False

    def _subtitle_segment_text_body_bounds(self, seg: dict | None = None) -> tuple[int, int]:
        if not isinstance(seg, dict):
            seg = self._segment_for_line(self._edit_line) if hasattr(self, "_segment_for_line") else None
        if not isinstance(seg, dict):
            return 0, 0
        x1 = self._x(float(seg.get("start", 0.0) or 0.0))
        x2 = self._x(float(seg.get("end", seg.get("start", 0.0)) or 0.0))
        handle_clearance = HANDLE_R + 12
        body_left = int(x1 + handle_clearance)
        body_right = int(x2 - handle_clearance)
        if (body_right - body_left) < 24:
            body_left = int(x1 + HANDLE_R + 6)
            body_right = int(x2 - HANDLE_R - 6)
        if body_right <= body_left:
            body_left = int(x1 + 6)
            body_right = int(x2 - 6)
        return body_left, body_right

    def _inline_editor_geometry(self, seg: dict | None = None) -> QRect:
        if not isinstance(seg, dict):
            seg = self._segment_for_line(self._edit_line) if hasattr(self, "_segment_for_line") else None
        if not isinstance(seg, dict):
            return QRect()
        body_left, body_right = self._subtitle_segment_text_body_bounds(seg)
        width = max(1, body_right - body_left)
        top = int(SUBTITLE_TOP) + 6
        bottom = int(SUBTITLE_BOT) - 6
        height = max(20, bottom - top)
        return QRect(body_left, top, width, height)

    def _sync_inline_editor_geometry(self) -> None:
        if not self._edit_active:
            return
        editor = self._ensure_inline_editor()
        rect = self._inline_editor_geometry()
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            editor.hide()
            return
        if editor.geometry() != rect:
            editor.setGeometry(rect)
        seg = self._segment_for_line(self._edit_line) if hasattr(self, "_segment_for_line") else None
        if isinstance(seg, dict):
            # macOS compositing is stable only when the child text editor paints
            # an opaque segment body instead of letting canvas text show through.
            style = subtitle_segment_visual_style(
                seg,
                active=True,
                hover=False,
                quality_filter=getattr(self, "quality_filter", "all"),
            )
            if hasattr(editor, "set_segment_background"):
                editor.set_segment_background(str(style.get("fill") or "#163223"))
        editor.raise_()
        if not editor.isVisible():
            editor.show()

    def _set_inline_editor_cursor_from_canvas_point(self, click_x: int | None, click_y: int | None) -> bool:
        editor = getattr(self, "_inline_editor", None)
        if editor is None:
            return False
        if click_x is None or click_y is None:
            cursor = editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            editor.setTextCursor(cursor)
            self._sync_inline_editor_state_from_widget(text_changed=False)
            return True
        editor_point = editor.mapFrom(self, QPoint(int(click_x), int(click_y)))
        viewport = editor.viewport()
        local_point = viewport.mapFrom(editor, editor_point)
        if viewport.width() > 0:
            local_point.setX(max(0, min(viewport.width() - 1, local_point.x())))
        if viewport.height() > 0:
            local_point.setY(max(0, min(viewport.height() - 1, local_point.y())))
        cursor = editor.cursorForPosition(local_point)
        editor.setTextCursor(cursor)
        self._sync_inline_editor_state_from_widget(text_changed=False)
        return True

    def _route_inline_editor_click(self, click_x: int, click_y: int) -> bool:
        editor = getattr(self, "_inline_editor", None)
        if editor is None:
            return False
        seg = self._segment_for_line(self._edit_line) if hasattr(self, "_segment_for_line") else next((s for s in self.segments if s.get("line") == self._edit_line), None)
        if not isinstance(seg, dict):
            return False
        seg_left = self._x(float(seg.get("start", 0.0) or 0.0))
        seg_right = self._x(float(seg.get("end", seg.get("start", 0.0)) or 0.0))
        if not (SUBTITLE_TOP <= int(click_y) <= SUBTITLE_BOT and seg_left <= int(click_x) <= seg_right):
            return False
        editor.setFocus(Qt.FocusReason.MouseFocusReason)
        editor_point = editor.mapFrom(self, QPoint(int(click_x), int(click_y)))
        viewport = editor.viewport()
        local_point = viewport.mapFrom(editor, editor_point)
        if viewport.width() > 0:
            local_point.setX(max(0, min(viewport.width() - 1, local_point.x())))
        if viewport.height() > 0:
            local_point.setY(max(0, min(viewport.height() - 1, local_point.y())))
        cursor = editor.cursorForPosition(local_point)
        editor.setTextCursor(cursor)
        self._sync_inline_editor_state_from_widget(text_changed=False)
        return True

    def _sync_inline_editor_state_from_widget(self, *, text_changed: bool) -> None:
        editor = getattr(self, "_inline_editor", None)
        if editor is None or getattr(self, "_inline_editor_syncing", False):
            return
        self._edit_text = editor.toPlainText()
        self._edit_cursor = int(editor.textCursor().position())
        self._ime_preedit = ""
        if not text_changed:
            return
        if self._edit_text.strip():
            for seg in self.segments:
                if seg.get("line") == self._edit_line:
                    seg["text"] = self._edit_text
                    break
            safe_text = self._edit_text.replace("\n", "\u2028")
            self.sig_inline_text_changed.emit(self._edit_line, safe_text)
        self._update_inline_edit_region()

    def _maybe_commit_inline_edit_from_focus_out(self) -> None:
        if not self._edit_active:
            return
        if bool(getattr(self, "_inline_editor_context_menu_open", False)):
            return
        if self._smart_split_edit_active():
            return
        editor = getattr(self, "_inline_editor", None)
        if editor is None or editor.hasFocus():
            return
        focus = QApplication.focusWidget()
        if focus is not None and editor.isAncestorOf(focus):
            return
        self._commit_inline_edit()

    def _commit_inline_edit_or_split(self) -> None:
        if not self._edit_active:
            return
        editor = getattr(self, "_inline_editor", None)
        if editor is not None:
            self._sync_inline_editor_state_from_widget(text_changed=False)
        if hasattr(self, "_pending_split_sec"):
            safe_text = self._edit_text.replace("\n", "\u2028")
            self._inline_commit_in_progress = True
            try:
                self.sig_inline_text_changed.emit(self._edit_line, safe_text)
                self.sig_split_request.emit(
                    int(self._edit_line),
                    float(self._pending_split_sec),
                    int(self._edit_cursor),
                )
            finally:
                self._inline_commit_in_progress = False
            del self._pending_split_sec
            self._end_inline_edit()
            return
        self._commit_inline_edit()

    def _inline_edit_repaint_rect(self, line_num=None) -> QRect:
        line = self._edit_line if line_num is None else line_num
        rect = QRect()
        if hasattr(self, "_segment_repaint_rect_for_line"):
            rect = self._segment_repaint_rect_for_line(int(line), margin=110)
        if getattr(self, "_is_listening", False):
            rect = rect.adjusted(0, 0, 180, 0)
        return rect

    def _update_inline_edit_region(self, line_num=None):
        if self._edit_active:
            self._sync_inline_editor_geometry()
        rect = self._inline_edit_repaint_rect(line_num)
        if hasattr(self, "_update_dirty_rect"):
            self._update_dirty_rect(rect)
        else:
            self.update()

    def _set_pending_split_from_playhead(self, seg: dict | None, *, enabled: bool) -> None:
        if hasattr(self, "_pending_split_sec"):
            del self._pending_split_sec
        if not enabled or not isinstance(seg, dict):
            return
        try:
            split_sec = self._snap_to_frame(float(getattr(self, "playhead_sec", 0.0) or 0.0))
            seg_start = self._snap_to_frame(float(seg.get("start", 0.0) or 0.0))
            seg_end = self._snap_to_frame(float(seg.get("end", seg_start) or seg_start))
        except Exception:
            return
        if split_sec <= seg_start + 0.05 or split_sec >= seg_end - 0.05:
            return
        self._pending_split_sec = float(split_sec)

    def start_inline_edit(self, line_num, start_sec, *, split_at_playhead: bool = False):
        old_line = getattr(self, "_edit_line", -1)
        self.active_seg_start = start_sec

        seg = next((s for s in self.segments if s.get("line") == line_num), None)
        if not seg:
            return
        self._set_pending_split_from_playhead(seg, enabled=bool(split_at_playhead))
        if split_at_playhead and not hasattr(self, "_pending_split_sec"):
            return

        text = seg.get("text", "")
        clear_placeholder = str(text or "").strip() == NEW_SUBTITLE_PLACEHOLDER

        self._edit_active = True
        self._edit_line = line_num
        self._edit_text = "" if clear_placeholder else text
        self._edit_orig = "" if clear_placeholder else text

        if clear_placeholder:
            seg["text"] = ""
            self._inline_commit_in_progress = True
            try:
                self.sig_inline_text_changed.emit(line_num, "")
            finally:
                self._inline_commit_in_progress = False
            text = ""
        editor = self._ensure_inline_editor()
        self._sync_inline_editor_geometry()
        self._inline_editor_syncing = True
        try:
            editor.setPlainText(self._edit_text)
        finally:
            self._inline_editor_syncing = False

        click_x = getattr(self, "_last_click_x", None)
        click_y = getattr(self, "_last_click_y", None)
        if click_x is not None and click_y is not None:
            self._set_inline_editor_cursor_from_canvas_point(click_x, click_y)
            self._last_click_x = None
            self._last_click_y = None
        else:
            self._set_inline_editor_cursor_from_canvas_point(None, None)

        self._cursor_vis = True
        self._cursor_timer.stop()
        self.sig_editing_mode.emit(True)
        editor.show()
        editor.raise_()
        editor.setFocus(Qt.FocusReason.MouseFocusReason if click_x is not None else Qt.FocusReason.OtherFocusReason)
        dirty = self._inline_edit_repaint_rect(line_num)
        if old_line >= 0:
            dirty = dirty.united(self._inline_edit_repaint_rect(old_line))
        if hasattr(self, "_update_dirty_rect"):
            self._update_dirty_rect(dirty)
        else:
            self.update()

    def _blink_cursor(self):
        if self._edit_active and not self._native_inline_editor_active():
            self._cursor_vis = not self._cursor_vis
            self._update_inline_edit_region()

    def _commit_inline_edit(self):
        if not self._edit_active:
            return
        editor = getattr(self, "_inline_editor", None)
        if editor is not None:
            self._sync_inline_editor_state_from_widget(text_changed=False)

        if not self._edit_text.strip():
            line = self._edit_line
            self._end_inline_edit()
            self.seg_to_gap.emit(line)
            return

        safe_for_editor = self._edit_text.replace("\n", "\u2028")
        line = self._edit_line

        for seg in self.segments:
            if seg.get("line") == line:
                seg["text"] = self._edit_text
                break

        self._inline_commit_in_progress = True
        try:
            self.sig_inline_text_changed.emit(line, safe_for_editor)
        finally:
            self._inline_commit_in_progress = False

        if hasattr(self, "_pending_split_sec"):
            del self._pending_split_sec

        self._end_inline_edit()

    def _end_inline_edit(self):
        line = self._edit_line
        editor = getattr(self, "_inline_editor", None)
        self._edit_active = False
        self._edit_line = -1
        self._edit_text = ""
        self._edit_orig = ""
        self._ime_preedit = ""
        self._cursor_vis = False
        self._cursor_timer.stop()
        if editor is not None:
            editor.clearFocus(); editor.hide()
        self._update_inline_edit_region(line)
        # 편집 종료 신호 전에 canvas 포커스를 회복해야 전역 Space 재생 단축키가 다시 켜진다.
        self.setFocus(); self.sig_editing_mode.emit(False)

    def _handle_edit_key(self, ev):
        if ev.key() == Qt.Key.Key_Space and not (ev.modifiers() & ~Qt.KeyboardModifier.ShiftModifier):
            if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                pass
            else:
                self._request_canvas_play_pause_toggle()
                return
        editor = getattr(self, "_inline_editor", None)
        if editor is not None and self._native_inline_editor_active():
            if ev.key() == Qt.Key.Key_Escape:
                self._cancel_inline_edit()
            elif ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (ev.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self._commit_inline_edit_or_split()
            else:
                QApplication.sendEvent(editor, ev)
            return
        key = ev.key()
        text = self._edit_text
        cur = self._edit_cursor
        mods = ev.modifiers()

        def _row_col(value, cursor):
            lines = value.split("\n")
            row = 0
            col = cursor

            for i, line in enumerate(lines):
                if col <= len(line):
                    row = i
                    break
                col -= len(line) + 1
            else:
                row = len(lines) - 1
                col = max(0, col)

            return row, col, lines

        if mods & (Qt.KeyboardModifier.MetaModifier | Qt.KeyboardModifier.ControlModifier):
            if key == Qt.Key.Key_Left:
                self._edit_cursor = 0
                self._cursor_vis = True
                self._update_inline_edit_region()
                return
            if key == Qt.Key.Key_Right:
                self._edit_cursor = len(self._edit_text)
                self._cursor_vis = True
                self._update_inline_edit_region()
                return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._edit_text = text[:cur] + "\n" + text[cur:]
                self._edit_cursor = cur + 1
            else:
                self._commit_inline_edit_or_split()
                return

        elif key == Qt.Key.Key_Escape:
            self._edit_text = self._edit_orig
            self._end_inline_edit()
            return

        elif key == Qt.Key.Key_Backspace:
            if cur > 0:
                self._edit_text = text[: cur - 1] + text[cur:]
                self._edit_cursor = cur - 1

        elif key == Qt.Key.Key_Delete:
            if cur < len(text):
                self._edit_text = text[:cur] + text[cur + 1 :]

        elif key == Qt.Key.Key_Left:
            self._edit_cursor = max(0, cur - 1)

        elif key == Qt.Key.Key_Right:
            self._edit_cursor = min(len(self._edit_text), cur + 1)

        elif key == Qt.Key.Key_Up:
            row, col, lines = _row_col(text, cur)
            if row > 0:
                self._edit_cursor = sum(len(line) + 1 for line in lines[: row - 1]) + min(col, len(lines[row - 1]))
            else:
                self._edit_cursor = 0

        elif key == Qt.Key.Key_Down:
            row, col, lines = _row_col(text, cur)
            if row < len(lines) - 1:
                self._edit_cursor = sum(len(line) + 1 for line in lines[: row + 1]) + min(col, len(lines[row + 1]))
            else:
                self._edit_cursor = len(text)

        elif key == Qt.Key.Key_Home:
            row, _, lines = _row_col(text, cur)
            self._edit_cursor = sum(len(line) + 1 for line in lines[:row])

        elif key == Qt.Key.Key_End:
            row, _, lines = _row_col(text, cur)
            self._edit_cursor = sum(len(line) + 1 for line in lines[:row]) + len(lines[row])

        elif key == Qt.Key.Key_Space:
            if mods & Qt.KeyboardModifier.ShiftModifier:
                self._edit_text = text[:cur] + " " + text[cur:]
                self._edit_cursor = cur + 1
            else:
                self._request_canvas_play_pause_toggle()
                return

        else:
            ch = ev.text()
            if ch and ch.isprintable():
                self._edit_text = text[:cur] + ch + text[cur:]
                self._edit_cursor = cur + len(ch)

        if self._edit_text.strip():
            for seg in self.segments:
                if seg.get("line") == self._edit_line:
                    seg["text"] = self._edit_text
                    break

            safe_text = self._edit_text.replace("\n", "\u2028")
            self.sig_inline_text_changed.emit(self._edit_line, safe_text)

        self._cursor_vis = True
        self._update_inline_edit_region()

    def _cancel_inline_edit(self):
        if not self._edit_active:
            return
        editor = getattr(self, "_inline_editor", None)
        if editor is not None:
            self._sync_inline_editor_state_from_widget(text_changed=False)

        for seg in self.segments:
            if seg.get("line") == self._edit_line:
                seg["text"] = self._edit_orig
                break

        safe_orig = self._edit_orig.replace("\n", "\u2028")
        self._inline_commit_in_progress = True
        try:
            self.sig_inline_text_changed.emit(self._edit_line, safe_orig)
        finally:
            self._inline_commit_in_progress = False

        if hasattr(self, "_pending_split_sec"):
            del self._pending_split_sec

        self._end_inline_edit()

    def inputMethodEvent(self, ev):
        editor = getattr(self, "_inline_editor", None)
        if self._edit_active and editor is not None and self._native_inline_editor_active():
            ev.accept()
            return
        if not self._edit_active:
            super().inputMethodEvent(ev)
            return

        commit = ev.commitString()
        preedit = ev.preeditString()
        self._ime_preedit = preedit

        if commit:
            cur = self._edit_cursor
            self._edit_text = self._edit_text[:cur] + commit + self._edit_text[cur:]
            self._edit_cursor = cur + len(commit)

            actual = self._edit_text.replace(" / ", "\n")
            for seg in self.segments:
                if seg.get("line") == self._edit_line:
                    seg["text"] = actual
                    break

            safe_text = actual.replace("\n", "\u2028")
            self.sig_inline_text_changed.emit(self._edit_line, safe_text)

        self._cursor_vis = True
        self._update_inline_edit_region()

    def inputMethodQuery(self, query):
        from PyQt6.QtCore import Qt as _Qt

        if self._edit_active and query == _Qt.InputMethodQuery.ImCursorRectangle:
            editor = getattr(self, "_inline_editor", None)
            if editor is not None and editor.isVisible():
                rect = editor.cursorRect()
                return QRect(editor.x() + rect.x(), editor.y() + rect.y(), rect.width(), rect.height())
            seg = next((s for s in self.segments if s.get("line") == self._edit_line), None)
            if seg:
                return QRect(self._x(seg["start"]), SEG_TOP + 5, 1, 20)

        return super().inputMethodQuery(query)

    def _show_mic_menu(self, gpos):
        items = []
        if self._is_listening:
            items.append({"id": "stop", "label": "음성인식 중지", "danger": True, "accent": "#FF453A"})
        else:
            items.extend(
                [
                    {"id": "quality", "label": "음성으로 입력 (고품질)", "accent": "#34C759"},
                    {"id": "fast", "label": "음성으로 입력 (빠름)", "accent": "#5AC8FA"},
                ]
            )

        chosen = show_context_menu(self, gpos, items)
        if chosen == "stop":
            self._stop_listening()
        elif chosen == "quality":
            self._start_listening("quality")
        elif chosen == "fast":
            self._start_listening("fast")

    def _show_speaker_learn_menu(self, line_num, gpos):
        items = []
        for spk_i in range(1, 4):
            items.append(
                {
                    "id": f"speaker_{spk_i}",
                    "label": f"화자 {spk_i}로 학습",
                    "accent": "#34C759",
                }
            )
        chosen = show_context_menu(self, gpos, items)
        if chosen and chosen.startswith("speaker_"):
            try:
                spk_idx = int(chosen.rsplit("_", 1)[-1])
            except Exception:
                spk_idx = 0
            if spk_idx > 0:
                self._learn_speaker_from_segment(spk_idx, line_num)

    def _learn_speaker_from_segment(self, spk_idx, line_num=None):
        target_line = self._edit_line if line_num is None else line_num
        seg = next((s for s in self.segments if s.get("line") == target_line), None)
        if not seg:
            return

        import os, subprocess
        from PyQt6.QtWidgets import QInputDialog
        from core.runtime import config
        from core.runtime.logger import get_logger

        start_sec = seg["start"]
        end_sec = seg["end"]
        duration = end_sec - start_sec
        if duration < 0.3:
            get_logger().log("voice learn skipped: segment too short")
            return

        owner_settings = {}
        owner_for_settings = self.parent()
        while owner_for_settings and not hasattr(owner_for_settings, "settings"):
            owner_for_settings = owner_for_settings.parent()
        if owner_for_settings is not None:
            owner_settings = getattr(owner_for_settings, "settings", {}) or {}
        speaker_name = str(owner_settings.get(f"spk{spk_idx}_name", "") or f"화자_{spk_idx}")
        safe_name = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in speaker_name).strip("_") or f"speaker_{spk_idx}"
        default_name = f"spk{spk_idx}_{safe_name}"
        name, ok = QInputDialog.getText(
            self,
            "화자 음성 저장",
            "파일 이름 (확장자 제외):",
            text=default_name,
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        if not name.endswith(".wav"):
            name += ".wav"

        owner = self.parent()
        while owner and not hasattr(owner, "media_path"):
            owner = owner.parent()

        if not owner:
            get_logger().log("voice learn failed: media_path owner not found")
            return

        media_path = getattr(owner, "media_path", "") or ""
        if not media_path:
            get_logger().log("voice learn failed: media_path empty")
            return

        base_name = os.path.splitext(os.path.basename(media_path))[0]
        cleaned_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}_cleaned.wav")
        src = cleaned_wav if os.path.exists(cleaned_wav) else media_path

        voice_dir = getattr(config, "VOICE_DATA_DIR", os.path.join(config.BASE_DIR, "voice_data"))
        os.makedirs(voice_dir, exist_ok=True)
        voice_path = os.path.join(voice_dir, name)

        try:
            proc = subprocess.run(
                [
                    "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
                    "-ss", str(start_sec), "-t", str(duration),
                    "-i", src,
                    "-ac", "1", "-ar", "16000",
                    "-acodec", "pcm_s16le",
                    voice_path,
                ],
                capture_output=True,
                timeout=30,
            )

            if proc.returncode != 0:
                err = (proc.stderr or b"").decode("utf-8", errors="ignore") if isinstance(proc.stderr, (bytes, bytearray)) else str(proc.stderr or "")
                get_logger().log(f"voice learn failed spk{spk_idx}: {err[:300]}")
                return

            if not os.path.exists(voice_path) or os.path.getsize(voice_path) <= 0:
                get_logger().log(f"voice learn failed spk{spk_idx}: wav not created -> {voice_path}")
                return

            get_logger().log(f"voice learned spk{spk_idx}: {name} ({duration:.1f}s) -> {voice_path}")

        except Exception as e:
            get_logger().log(f"voice learn failed spk{spk_idx}: {e}")

    def _start_listening(self, profile="quality"):
        if self._is_listening:
            return

        self._is_listening = True
        self._speech_stop_requested = False
        session = None
        try:
            from ui.editor.live_microphone_session import LiveMicrophoneSession

            session = LiveMicrophoneSession(self)
        except Exception as e:
            self._is_listening = False
            from core.runtime.logger import get_logger
            get_logger().log(f"⚠️ 마이크 캡처 초기화 실패: {e}")
            self._update_inline_edit_region()
            return
        self._mic_capture_session = session
        if hasattr(self, "begin_mic_visualization"):
            self.begin_mic_visualization(getattr(self, "_edit_line", None))
        session.waveform_changed.connect(self.update_mic_visualization if hasattr(self, "update_mic_visualization") else (lambda _samples: None))
        self._update_inline_edit_region()

        def _listen(captured_wav: str, has_audio: bool, error_text: str, _elapsed: float):
            try:
                from core.audio.live_stt import transcribe_wav_file
                from core.runtime.logger import get_logger

                if not has_audio or not captured_wav:
                    if error_text:
                        get_logger().log(f"⚠️ 마이크 STT 실패: {error_text}")
                    return
                result = transcribe_wav_file(captured_wav, profile=profile)
                if result.text:
                    get_logger().log(
                        f"🎙️ 마이크 STT 완료: {result.engine} / {result.model} / {result.elapsed:.1f}s"
                    )
                    self.sig_speech_result.emit(result.text)
                else:
                    get_logger().log("🎙️ 마이크 STT 결과 없음")

            except Exception as e:
                try:
                    from core.runtime.logger import get_logger
                    get_logger().log(f"⚠️ 마이크 STT 실패: {e}")
                except Exception:
                    pass
            finally:
                try:
                    if captured_wav and os.path.exists(captured_wav):
                        os.remove(captured_wav)
                except Exception:
                    pass
                self._is_listening = False
                self._speech_stop_requested = False
                def _cleanup():
                    self._mic_capture_session = None
                    if hasattr(self, "end_mic_visualization"):
                        self.end_mic_visualization()
                    self._update_inline_edit_region()
                QTimer.singleShot(0, _cleanup)

        def _on_capture_finished(captured_wav: str, has_audio: bool, error_text: str, elapsed: float):
            threading.Thread(
                target=_listen,
                args=(captured_wav, has_audio, error_text, elapsed),
                daemon=True,
                name="timeline-inline-mic-transcribe",
            ).start()

        session.finished.connect(_on_capture_finished)
        if not session.start():
            self._is_listening = False
            self._speech_stop_requested = False
            self._mic_capture_session = None
            if hasattr(self, "end_mic_visualization"):
                self.end_mic_visualization()
            self._update_inline_edit_region()

    def _stop_listening(self):
        self._speech_stop_requested = True
        session = getattr(self, "_mic_capture_session", None)
        if session is not None and hasattr(session, "stop"):
            session.stop()
            return
        self._is_listening = False
        if hasattr(self, "end_mic_visualization"):
            self.end_mic_visualization()
        self._update_inline_edit_region()

    def _on_speech_result(self, text):
        if not self._edit_active:
            return

        cur = self._edit_cursor
        self._edit_text = self._edit_text[:cur] + text + self._edit_text[cur:]
        self._edit_cursor = cur + len(text)

        for seg in self.segments:
            if seg.get("line") == self._edit_line:
                seg["text"] = self._edit_text
                break

        safe_text = self._edit_text.replace("\n", "\u2028")
        self.sig_inline_text_changed.emit(self._edit_line, safe_text)
        self._cursor_vis = True
        self._update_inline_edit_region()
