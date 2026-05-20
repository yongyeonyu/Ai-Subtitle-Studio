# Version: 03.14.31
# Phase: PHASE2
"""
ui/timeline_input.py
Timeline input mixin
"""
from bisect import bisect_left, bisect_right
import time

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QCursor, QFont, QFontMetrics, QIcon, QPainter, QPixmap, QPolygon
from PyQt6.QtWidgets import QApplication

from core.coerce import safe_float as _as_float
from core.runtime import config
from core.speaker_profile_settings import visible_speaker_slots
from ui.dialogs.qml_popup import show_context_menu
from ui.editor.editor_helpers import find_segment_at
from ui.editor.ux.timeline_playhead_mode import (
    dispatch_playhead_arrow_step,
    set_playhead_focus_mode_from_key,
)
from ui.responsive_profile import responsive_profile_for_size
from ui.editor.ux.timeline_canvas_editing import apply_timing_drag
from ui.style import COLORS

from ui.timeline.speaker_labels import current_speaker_settings, speaker_labels_for_segment
from ui.timeline.timeline_constants import (
    DIAMOND_Y,
    HANDLE_R,
    ICON_SZ,
    RULER_H,
    SEG_BOT,
    SEG_TOP,
    SEGMENT_HANDLE_MIN_WIDTH,
    SPEAKER_BOT,
    SPEAKER_TOP,
    STT1_BOT,
    STT1_TOP,
    STT2_BOT,
    STT2_TOP,
    VOICE_ACTIVITY_BOT,
    VOICE_ACTIVITY_TOP,
    WAVE_H,
    _build_gaps,
)

class TimelineInputMixin:
    _REVIEW_FLAGS = {
        "non_speech_hallucination_risk",
        "high_no_speech_prob",
        "outside_vad_speech",
        "high_cps",
        "quality_stale",
    }

    def _segment_needs_manual_review(self, seg: dict) -> bool:
        quality = dict(seg.get("quality") or {})
        label = str(quality.get("confidence_label") or "")
        flags = set(str(flag) for flag in (quality.get("flags") or ()))
        manually_confirmed = bool(quality.get("manual_confirmed")) or "manual_confirmed" in flags
        return (
            bool(quality)
            and (
                manually_confirmed
                or label in {"red", "gray"}
                or bool(flags.intersection(self._REVIEW_FLAGS))
                or bool(seg.get("quality_stale"))
            )
        )

    def _smart_split_ready_for_segment(self, seg: dict | None) -> bool:
        if not isinstance(seg, dict):
            return False
        try:
            playhead = self._snap_to_frame(float(getattr(self, "playhead_sec", 0.0) or 0.0))
            start = self._snap_to_frame(float(seg.get("start", 0.0) or 0.0))
            end = self._snap_to_frame(float(seg.get("end", start) or start))
        except Exception:
            return False
        return bool(start + 0.05 < playhead < end - 0.05)

    def _show_segment_context_menu(self, seg: dict, gpos, *, click_x: int, click_y: int) -> None:
        if not isinstance(seg, dict):
            return
        if hasattr(self, "_pending_timeline_review_action"):
            del self._pending_timeline_review_action
        items = []
        if self._segment_needs_manual_review(seg):
            quality = dict(seg.get("quality") or {})
            flags = set(str(flag) for flag in (quality.get("flags") or ()))
            manually_confirmed = bool(quality.get("manual_confirmed")) or "manual_confirmed" in flags
            items.append(
                {
                    "id": "primary",
                    "label": "임시자막" if manually_confirmed else "자막 확정",
                    "accent": "#34C759",
                }
            )
        items.append(
            {
                "id": "split",
                "label": "자막 분할",
                "enabled": self._smart_split_ready_for_segment(seg),
                "accent": COLORS["warning"],
            }
        )
        if self._segment_needs_manual_review(seg):
            items.append(
                {
                    "id": "delete",
                    "label": "자막 삭제",
                    "danger": True,
                    "accent": "#FF453A",
                }
            )
        chosen = show_context_menu(self, gpos, items)
        if chosen in {"primary", "delete"}:
            self._pending_timeline_review_action = str(chosen)
            self.seg_right_clicked.emit(float(seg.get("start", 0.0) or 0.0), gpos)
            return
        if chosen == "split":
            self._last_click_x = int(click_x)
            self._last_click_y = int(click_y)
            self.start_inline_edit(seg.get("line", 0), seg["start"], split_at_playhead=True)

    def _timeline_input_locked(self) -> bool:
        return bool(
            getattr(self, "_scan_cut_input_locked", False)
            or getattr(self, "_editor_processing_input_locked", False)
        )

    def _emit_diamond_pair_time_changed(self, pair) -> None:
        if pair is None:
            return
        seen: set[int] = set()
        for raw_idx in tuple(pair)[:2]:
            try:
                idx = int(raw_idx)
            except Exception:
                continue
            if idx in seen or idx < 0 or idx >= len(self.segments):
                continue
            seen.add(idx)
            seg = self.segments[idx]
            if isinstance(seg, dict):
                self.seg_time_changed.emit(seg.get("line", 0), seg["start"], seg["end"], "diamond")

    def _drag_release_guide_secs(self) -> list[float]:
        guides: list[float] = []
        edge = getattr(self, "_drag_edge", None)
        if edge == "diamond":
            pair = getattr(self, "_drag_diamond_pair", None)
            if pair is not None and pair[0] < len(self.segments):
                current = self._snap_to_frame(float(self.segments[pair[0]].get("end", 0.0) or 0.0))
                original = self._snap_to_frame(float(getattr(self, "_drag_diamond_orig", current) or current))
                if abs(current - original) >= 0.001:
                    guides.append(current)
        else:
            seg = getattr(self, "_drag_seg", None)
            if isinstance(seg, dict):
                current_start = self._snap_to_frame(float(seg.get("start", 0.0) or 0.0))
                current_end = self._snap_to_frame(float(seg.get("end", current_start) or current_start))
                original_start = self._snap_to_frame(float(getattr(self, "_drag_s0_start", current_start) or current_start))
                original_end = self._snap_to_frame(float(getattr(self, "_drag_s0_end", current_end) or current_end))
                if edge == "square_left":
                    if abs(current_start - original_start) >= 0.001:
                        guides.append(current_start)
                elif edge == "square_right":
                    if abs(current_end - original_end) >= 0.001:
                        guides.append(current_end)
                else:
                    if abs(current_start - original_start) >= 0.001:
                        guides.append(current_start)
                    if abs(current_end - original_end) >= 0.001:
                        guides.append(current_end)
        deduped: list[float] = []
        for sec in guides:
            snapped = self._snap_to_frame(sec)
            if any(abs(snapped - prev) < 0.001 for prev in deduped):
                continue
            deduped.append(snapped)
        return deduped

    def _remember_drag_release_guides(self, secs: list[float]) -> None:
        if not secs:
            return
        try:
            if hasattr(self, "set_user_alignment_guides"):
                self.set_user_alignment_guides(list(secs))
            elif hasattr(self, "add_user_alignment_guides"):
                self.add_user_alignment_guides(list(secs))
        except Exception:
            pass

    def _timeline_widget_owner(self):
        owner = self.parent()
        while owner is not None:
            if hasattr(owner, "set_shadow_playhead") or hasattr(owner, "pin_shadow_playhead"):
                return owner
            try:
                owner = owner.parent()
            except Exception:
                owner = None
        return None

    def _shadow_playhead_sec(self) -> float | None:
        value = getattr(self, "shadow_playhead_sec", None)
        if value is None:
            return None
        try:
            return self._snap_to_frame(float(value or 0.0))
        except Exception:
            return None

    def _armed_shadow_playhead_sec(self) -> float | None:
        value = getattr(self, "_shadow_playhead_armed_sec", None)
        if value is None:
            return None
        try:
            return self._snap_to_frame(float(value or 0.0))
        except Exception:
            return None

    def _set_shadow_playhead(self, sec: float | None) -> bool:
        owner = self._timeline_widget_owner()
        setter = getattr(owner, "set_shadow_playhead", None) if owner is not None else None
        if not callable(setter):
            setter = getattr(self, "set_shadow_playhead", None)
        if not callable(setter):
            return False
        if sec is not None:
            self._disarm_shadow_playhead()
        try:
            return bool(setter(sec))
        except Exception:
            return False

    def _arm_shadow_playhead(self, sec: float | None, *, clear_visible: bool = True) -> bool:
        if sec is None:
            self._disarm_shadow_playhead()
            if clear_visible:
                self._clear_shadow_playhead()
            return False
        try:
            armed_sec = self._snap_to_frame(float(sec or 0.0))
        except Exception:
            return False
        setattr(self, "_shadow_playhead_armed_sec", armed_sec)
        if clear_visible:
            self._clear_shadow_playhead()
        return True

    def _disarm_shadow_playhead(self) -> bool:
        if getattr(self, "_shadow_playhead_armed_sec", None) is None:
            return False
        self._shadow_playhead_armed_sec = None
        return True

    def _show_armed_shadow_playhead(self) -> bool:
        armed_sec = self._armed_shadow_playhead_sec()
        if armed_sec is None:
            return False
        self._shadow_playhead_armed_sec = None
        return self._set_shadow_playhead(armed_sec)

    def _pin_shadow_playhead(self, sec: float | None = None) -> bool:
        owner = self._timeline_widget_owner()
        pinner = getattr(owner, "pin_shadow_playhead", None) if owner is not None else None
        if callable(pinner):
            try:
                return bool(pinner(sec))
            except Exception:
                return False
        target = getattr(self, "playhead_sec", 0.0) if sec is None else sec
        return self._set_shadow_playhead(target)

    def _clear_shadow_playhead(self) -> bool:
        owner = self._timeline_widget_owner()
        clearer = getattr(owner, "clear_shadow_playhead", None) if owner is not None else None
        if not callable(clearer):
            clearer = getattr(self, "clear_shadow_playhead", None)
        if not callable(clearer):
            return False
        try:
            return bool(clearer())
        except Exception:
            return False

    def _remember_shadow_before_playhead_move(self, sec: float, *, force: bool = False) -> bool:
        try:
            current_sec = self._snap_to_frame(float(getattr(self, "playhead_sec", 0.0) or 0.0))
            target_sec = self._snap_to_frame(float(sec or 0.0))
        except Exception:
            return False
        if not force and abs(target_sec - current_sec) < 0.001:
            return False
        armed_sec = self._armed_shadow_playhead_sec()
        if armed_sec is None:
            return False
        if not force and abs(current_sec - armed_sec) >= 0.001:
            return False
        return self._show_armed_shadow_playhead()

    def _consume_shadow_playhead_snap(self, snapped: dict | None) -> bool:
        if not isinstance(snapped, dict):
            return False
        if str(snapped.get("kind") or "") != "shadow_playhead":
            return False
        self._disarm_shadow_playhead()
        self._clear_shadow_playhead()
        return True

    def _emit_scrub_with_shadow(self, sec: float, *, remember_shadow: bool = True) -> None:
        target_sec = self._snap_to_frame(float(sec or 0.0))
        if remember_shadow:
            self._remember_shadow_before_playhead_move(target_sec)
        self.scrub_sec.emit(target_sec)

    def _begin_playhead_handle_scrub(self) -> None:
        self._clear_pending_center_drag()
        self._is_scrubbing = True
        self._playhead_handle_scrubbing = True
        self._playhead_cut_magnet_locked_sec = None
        try:
            origin = self._snap_to_frame(float(getattr(self, "playhead_sec", 0.0) or 0.0))
        except Exception:
            origin = 0.0
        self._playhead_cut_magnet_origin_sec = origin
        self._playhead_cut_magnet_previous_sec = origin

    def _finish_playhead_handle_scrub(self) -> None:
        self._playhead_handle_scrubbing = False
        self._playhead_cut_magnet_locked_sec = None
        self._playhead_cut_magnet_origin_sec = None
        self._playhead_cut_magnet_previous_sec = None

    def _emit_scrub_with_playhead_cut_magnet(self, sec: float) -> None:
        if getattr(self, "_playhead_cut_magnet_locked_sec", None) is not None:
            return
        target_sec = self._snap_to_frame(float(sec or 0.0))
        snapper = getattr(self, "_playhead_auto_cut_snap_sec", None)
        if callable(snapper):
            try:
                previous_sec = self._snap_to_frame(
                    float(getattr(self, "_playhead_cut_magnet_previous_sec", getattr(self, "playhead_sec", target_sec)) or target_sec)
                )
                snapped = snapper(target_sec, previous_sec)
            except Exception:
                snapped = None
            if isinstance(snapped, tuple) and len(snapped) >= 2 and bool(snapped[1]):
                snap_sec = self._snap_to_frame(float(snapped[0] or target_sec))
                self._playhead_cut_magnet_locked_sec = snap_sec
                self._playhead_cut_magnet_previous_sec = snap_sec
                self._set_shadow_playhead(snap_sec)  # 컷 자석 경계를 세그먼트 스냅 기준으로 보존.
                self._emit_scrub_with_shadow(snap_sec, remember_shadow=False)
                return

        self._playhead_cut_magnet_previous_sec = target_sec
        self._emit_scrub_with_shadow(target_sec)

    def _timing_drag_preview_sec(self) -> float | None:
        edge = getattr(self, "_drag_edge", None)
        if edge == "diamond":
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
        seg = getattr(self, "_drag_seg", None)
        if not isinstance(seg, dict):
            return None
        try:
            if edge == "square_left":
                return self._snap_to_frame(float(seg.get("start", 0.0) or 0.0))
            if edge == "square_right":
                return self._snap_to_frame(float(seg.get("end", 0.0) or 0.0))
            if edge == "center":
                return self._snap_to_frame(float(seg.get("start", 0.0) or 0.0))
        except Exception:
            return None
        return None

    def _finish_timing_drag_cleanup(self, dirty: QRect | None = None) -> None:
        self.drag_finished.emit()
        self._drag_seg = self._drag_edge = self._drag_adj_l = self._drag_adj_r = None
        self._drag_diamond_idx = None
        self._drag_diamond_pair = None
        self._clear_drag_guides()
        self.unsetCursor()
        self._drag_snap_candidates_cache = []
        if bool(getattr(self, "auto_generate_gap_segments", True)):
            self.gap_segments = _build_gaps(self.segments, self.total_duration, self._get_fps())
        else:
            self.gap_segments = [
                dict(gap)
                for gap in list(getattr(self, "gap_segments", []) or [])
                if bool(gap.get("_explicit_gap"))
            ]
        if hasattr(self, "_invalidate_render_cache"):
            self._invalidate_render_cache()
        if dirty is not None:
            self._update_dirty_rect(dirty.adjusted(-8, -8, 8, 8))
        else:
            self.update()

    def _gap_insert_controls_enabled(self) -> bool:
        return bool(getattr(self, "show_gap_insert_controls", True))

    def _current_responsive_profile(self):
        try:
            win = self.window()
            override = str(win.property("responsive_profile_override") or self.property("responsive_profile_override") or "")
            width = int(win.width() or self.width() or 0)
            height = int(win.height() or self.height() or 0)
        except Exception:
            override = ""
            width = int(self.width() or 0)
            height = int(self.height() or 0)
        return responsive_profile_for_size(width, height, override=override)

    def _touch_hit_slop(self, visual_px: int) -> int:
        profile = self._current_responsive_profile()
        if profile.name == "desktop":
            return 0
        return max(0, int((profile.touch_target - max(1, int(visual_px))) / 2))

    def _clear_pending_center_drag(self) -> None:
        self._pending_center_drag_seg = None
        self._pending_center_drag_x = 0
        self._pending_center_drag_y = 0

    def _is_stt_preview_segment(self, seg: dict) -> bool:
        return bool(seg.get("stt_pending") or seg.get("_live_stt_preview") or seg.get("_live_subtitle_preview"))

    def _stt_preview_source(self, seg: dict) -> str:
        source = (
            seg.get("stt_preview_source")
            or seg.get("stt_source")
            or seg.get("stt_ensemble_source")
            or "STT1"
        )
        return str(source or "STT1").strip().upper()

    def _is_readonly_analysis_lane_y(self, y: int) -> bool:
        return VOICE_ACTIVITY_TOP <= int(y) <= VOICE_ACTIVITY_BOT

    def focusNextPrevChild(self, next):
        if bool(next):
            signal = getattr(self, "tab_timing_requested", None)
            if signal is not None and hasattr(signal, "emit"):
                signal.emit()
        return False

    def _arrow_key_hold_repeat_interval_ms(self) -> int:
        return 24

    def _arrow_key_hold_repeat_delay_sec(self) -> float:
        return 0.12

    def _arrow_key_hold_speed_multiplier(self, elapsed_sec: float) -> int:
        try:
            elapsed = max(0.0, float(elapsed_sec or 0.0))
        except Exception:
            elapsed = 0.0
        stage = max(0, min(6, int(elapsed // 0.5)))
        return int(1 << stage)

    def _dispatch_frame_step(self, step: int) -> bool:
        try:
            step = int(step or 0)
        except Exception:
            step = 0
        if step == 0:
            return False
        owner = self
        visited: set[int] = set()
        while owner is not None and id(owner) not in visited:
            visited.add(id(owner))
            handler = getattr(owner, "_on_step_frame", None)
            if callable(handler):
                try:
                    handler(step)
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
        try:
            self.step_frame.emit(step)
            return True
        except Exception:
            return False

    def _begin_arrow_key_hold(self, direction: int) -> None:
        try:
            direction = 1 if int(direction) > 0 else -1
        except Exception:
            direction = 1
        self._arrow_key_hold_direction = direction
        self._arrow_key_hold_started_mono = time.monotonic()
        self._arrow_key_hold_repeat_active = False
        timer = getattr(self, "_arrow_key_hold_timer", None)
        if timer is not None:
            try:
                timer.setInterval(self._arrow_key_hold_repeat_interval_ms())
            except Exception:
                pass
            timer.start()

    def _stop_arrow_key_hold(self) -> None:
        timer = getattr(self, "_arrow_key_hold_timer", None)
        if timer is not None:
            timer.stop()
        self._arrow_key_hold_direction = 0
        self._arrow_key_hold_started_mono = 0.0
        self._arrow_key_hold_repeat_active = False

    def _emit_arrow_key_hold_step(self) -> None:
        try:
            direction = int(getattr(self, "_arrow_key_hold_direction", 0) or 0)
        except Exception:
            direction = 0
        if direction == 0:
            self._stop_arrow_key_hold()
            return

        started_mono = float(getattr(self, "_arrow_key_hold_started_mono", 0.0) or 0.0)
        if started_mono <= 0.0:
            self._stop_arrow_key_hold()
            return

        elapsed = max(0.0, time.monotonic() - started_mono)
        if elapsed < self._arrow_key_hold_repeat_delay_sec():
            return

        self._arrow_key_hold_repeat_active = True
        dispatch_playhead_arrow_step(self, direction * self._arrow_key_hold_speed_multiplier(elapsed))

    def keyPressEvent(self, ev):
        if bool(getattr(self, "_editor_processing_input_locked", False)):
            ev.accept()
            return
        if self._edit_active:
            self._handle_edit_key(ev); ev.accept(); return

        if ev.key() == Qt.Key.Key_Space and ev.modifiers() == Qt.KeyboardModifier.NoModifier:
            play_toggle = getattr(self, "_request_canvas_play_pause_toggle", None)
            if callable(play_toggle) and play_toggle(): ev.accept(); return
        if ev.key() in (Qt.Key.Key_F2, Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.active_seg_start is not None:
            candidates = self._active_segment_candidates() if hasattr(self, "_active_segment_candidates") else self.segments
            seg = next(
                (
                    s for s in candidates
                    if not self._is_stt_preview_segment(s)
                    and abs(s["start"] - self.active_seg_start) < 0.5
                ),
                None,
            )
            if seg: self.start_inline_edit(seg.get("line", 0), seg["start"])
            ev.accept(); return

        if ev.key() == Qt.Key.Key_Tab:
            signal = getattr(self, "tab_timing_requested", None)
            if signal is not None and hasattr(signal, "emit"):
                signal.emit()
            ev.accept()
            return
        if set_playhead_focus_mode_from_key(self, ev.key()):
            ev.accept()
            return

        if ev.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            direction = -1 if ev.key() == Qt.Key.Key_Left else 1
            if ev.isAutoRepeat():
                ev.accept()
                return
            dispatch_playhead_arrow_step(self, direction)
            self._begin_arrow_key_hold(direction)
            ev.accept()
            return
        super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev):
        if ev.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            if not ev.isAutoRepeat():
                self._stop_arrow_key_hold()
            ev.accept()
            return
        super().keyReleaseEvent(ev)

    def focusOutEvent(self, ev):
        self._stop_arrow_key_hold()
        super().focusOutEvent(ev)

    def _jump_to_prev_segment(self):
        if not self.segments:
            return False

        target = None
        for seg in reversed(self._editable_segments_sorted() if hasattr(self, "_editable_segments_sorted") else self.segments):
            if self._is_stt_preview_segment(seg):
                continue
            if seg["start"] < self.playhead_sec - 0.1:
                target = seg["start"]
                break

        target_sec = self._snap_to_frame(target if target is not None else 0.0)
        current_sec = self._snap_to_frame(float(getattr(self, "playhead_sec", 0.0) or 0.0))
        if abs(target_sec - current_sec) < (self._frame_step_sec() / 2.0):
            return False
        self.scrub_sec.emit(target_sec)
        return True

    def _jump_to_next_segment(self):
        if not self.segments:
            return False

        target = None
        for seg in self._editable_segments_sorted() if hasattr(self, "_editable_segments_sorted") else self.segments:
            if self._is_stt_preview_segment(seg):
                continue
            if seg["start"] > self.playhead_sec + 0.1:
                target = seg["start"]
                break

        target_sec = self._snap_to_frame(target if target is not None else self.total_duration)
        current_sec = self._snap_to_frame(float(getattr(self, "playhead_sec", 0.0) or 0.0))
        if abs(target_sec - current_sec) < (self._frame_step_sec() / 2.0):
            return False
        self.scrub_sec.emit(target_sec)
        return True

    def _emit_smart_split_at_playhead(self):
        sec = self._snap_to_frame(self.playhead_sec)
        candidates = self._visible_items_for_paint(self.segments, "segments", sec, sec, pad_sec=0.02) if hasattr(self, "_visible_items_for_paint") else self.segments
        seg = find_segment_at([s for s in candidates if not self._is_stt_preview_segment(s)], sec, skip_gap=True)
        if not seg: return
        if sec <= seg["start"] + 0.05 or sec >= seg["end"] - 0.05: return
        mid = (seg["start"] + seg["end"]) / 2.0
        self.sig_smart_split.emit(seg.get("line", 0), float(sec), sec < mid)

    def wheelEvent(self, event):
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier or mods & Qt.KeyboardModifier.MetaModifier:
            event.ignore()
            return

        dy = event.angleDelta().y()
        dx = event.angleDelta().x()
        delta = -(dy if dy != 0 else dx)

        widget = self.parent()
        while widget:
            if hasattr(widget, "apply_manual_horizontal_scroll_delta"):
                widget.apply_manual_horizontal_scroll_delta(delta // 2)
                event.accept()
                return
            widget = widget.parent()

        widget = self.parent()
        from PyQt6.QtWidgets import QScrollArea as _ScrollArea

        while widget and not isinstance(widget, _ScrollArea):
            widget = widget.parent()

        if widget:
            scrollbar = widget.horizontalScrollBar()
            scrollbar.setValue(scrollbar.value() + delta // 2)

        event.accept()

    def _hit_multiclip_box(self, x: int):
        if not self._multiclip_boxes:
            return None
        boxes = self._multiclip_boxes_near_x_for_hit(x, pad_px=12) if hasattr(self, "_multiclip_boxes_near_x_for_hit") else self._multiclip_boxes
        for box in boxes:
            bx1, bx2 = self._x(box["start"]), self._x(box["end"])
            if bx1 <= x <= bx2:
                return box
        return None

    def _speaker_lane_rect_for_seg(self, seg):
        return QRect(
            self._x(seg["start"]),
            SPEAKER_TOP,
            max(1, self._x(seg["end"]) - self._x(seg["start"])),
            SPEAKER_BOT - SPEAKER_TOP,
        )

    def _speaker_lane_hit_rect_for_seg(self, seg):
        rect = self._speaker_lane_rect_for_seg(seg)
        settings = self._speaker_settings_for_hit_test()
        try:
            start_ms = int(round(float(seg.get("start", 0.0) or 0.0) * 1000.0))
            end_ms = int(round(float(seg.get("end", seg.get("start", 0.0)) or 0.0) * 1000.0))
            line_key = int(seg.get("line", -1))
        except Exception:
            start_ms = end_ms = line_key = -1
        settings_key = getattr(self, "_speaker_hit_settings_cache_key", None)
        owner_key = (
            self._segment_index_cache_key() if hasattr(self, "_segment_index_cache_key") else id(getattr(self, "segments", None)),
            settings_key,
            round(float(getattr(self, "pps", 0.0) or 0.0), 3),
        )
        cache = getattr(self, "_speaker_hit_rect_cache", None)
        if not isinstance(cache, dict) or getattr(self, "_speaker_hit_rect_cache_key", None) != owner_key:
            cache = {}
            self._speaker_hit_rect_cache = cache
            self._speaker_hit_rect_cache_key = owner_key
        cache_key = (
            id(seg),
            line_key,
            start_ms,
            end_ms,
            str(seg.get("speaker", seg.get("spk_id", "")) or ""),
        )
        cached = cache.get(cache_key)
        if isinstance(cached, QRect):
            return QRect(cached)

        names = [str(name).strip() for name in speaker_labels_for_segment(settings, seg) if str(name).strip()]
        if not names:
            target_w = min(rect.width(), 42)
            result = QRect(rect.center().x() - target_w // 2, rect.y(), max(1, target_w), rect.height())
            cache[cache_key] = QRect(result)
            return result

        visible_names = names[:2]
        multi_line = len(visible_names) > 1
        font_size = 7 if multi_line else 8
        fm = QFontMetrics(QFont(config.FONT, font_size, QFont.Weight.Bold))
        line_h = fm.height()
        gap = 0 if multi_line else 1
        dot = 6 if multi_line else 8
        text_gap = 5 if multi_line else 6
        row_h = max(dot, line_h)
        total_h = len(visible_names) * row_h + max(0, len(visible_names) - 1) * gap
        max_row_w = max(dot + text_gap + fm.horizontalAdvance(name) for name in visible_names)

        draw_y = rect.y() + max(0, (rect.height() - total_h) // 2)
        pad_y = 5
        ideal_w = max_row_w + 12
        max_center_w = max(36, min(96, int(rect.width() * 0.64)))
        target_w = max(1, min(rect.width(), ideal_w, max_center_w))
        left = max(rect.left(), rect.center().x() - target_w // 2)
        right = min(rect.right() + 1, left + target_w)
        left = max(rect.left(), right - target_w)
        top = max(rect.top(), draw_y - pad_y)
        bottom = min(rect.bottom() + 1, draw_y + total_h + pad_y)
        result = QRect(left, top, max(1, right - left), max(1, bottom - top))
        if len(cache) > 4096:
            cache.clear()
        cache[cache_key] = QRect(result)
        return result

    def _speaker_lane_seg_at(self, x: int, y: int):
        candidates = self._segments_near_x_for_hit(x, pad_px=14) if hasattr(self, "_segments_near_x_for_hit") else self.segments
        for seg in candidates:
            if self._is_stt_preview_segment(seg):
                continue
            if self._speaker_lane_hit_rect_for_seg(seg).contains(x, y):
                return seg
        return None

    def _stt_candidate_at(self, x: int, y: int):
        if STT1_TOP <= y < STT1_BOT:
            lane_source = "STT1"
        elif STT2_TOP <= y < STT2_BOT:
            lane_source = "STT2"
        else:
            return None
        candidates = self._segments_near_x_for_hit(x, pad_px=12) if hasattr(self, "_segments_near_x_for_hit") else self.segments
        for seg in candidates:
            if not self._is_stt_preview_segment(seg):
                continue
            source = self._stt_preview_source(seg)
            if lane_source == "STT1" and source == "STT2":
                continue
            if lane_source == "STT2" and source != "STT2":
                continue
            try:
                x1 = self._x(float(seg.get("start", 0.0) or 0.0))
                x2 = self._x(float(seg.get("end", 0.0) or 0.0))
            except Exception:
                continue
            if x1 <= x <= x2:
                return seg
        return None

    def _gap_at(self, x: int, y: int):
        if not self._gap_insert_controls_enabled():
            return None
        if not (SEG_TOP <= y <= SEG_BOT):
            return None
        candidates = self._gaps_near_x_for_hit(x, pad_px=12) if hasattr(self, "_gaps_near_x_for_hit") else getattr(self, "gap_segments", []) or []
        for gap in candidates:
            try:
                gx1 = self._x(float(gap.get("start", 0.0) or 0.0))
                gx2 = self._x(float(gap.get("end", 0.0) or 0.0))
            except Exception:
                continue
            if gx1 <= x <= gx2:
                return gap
        return None

    def _roughcut_major_lane_contains(self, x: int, y: int) -> bool:
        lane_top = RULER_H + WAVE_H + 5
        lane_h = max(18, SEG_TOP - lane_top - 7)
        if not (lane_top <= int(y) <= lane_top + lane_h):
            return False
        try:
            markers = self.roughcut_major_markers_cached() if hasattr(self, "roughcut_major_markers_cached") else []
        except Exception:
            markers = []
        for marker in list(markers or []):
            try:
                x1 = self._x(float(marker.get("start", 0.0) or 0.0))
                x2 = self._x(float(marker.get("end", marker.get("start", 0.0)) or 0.0))
            except Exception:
                continue
            if x1 <= int(x) <= x2:
                return True
        return False

    def _scan_boundary_sec(self, item) -> float | None:
        try:
            if isinstance(item, dict):
                return float(item.get("timeline_sec", item.get("time", item.get("start", 0.0))) or 0.0)
            return float(item or 0.0)
        except Exception:
            return None

    def _scan_boundary_hit_at(self, x: int, y: int, *, margin: int = 5):
        lane_top = RULER_H + WAVE_H + 5
        lane_h = max(18, SEG_TOP - lane_top - 7)
        if not (lane_top <= int(y) <= lane_top + lane_h):
            return None
        margin = max(int(margin), self._touch_hit_slop(2))
        best = None
        best_dist = max(1, int(margin)) + 1
        items = list(getattr(self, "scan_boundary_times", []) or [])
        if len(items) >= 64:
            key = (id(getattr(self, "scan_boundary_times", None)), len(items), int(getattr(self, "_render_epoch", 0) or 0))
            cache = getattr(self, "_scan_boundary_hit_cache", None)
            if not cache or cache.get("key") != key:
                rows = []
                for idx, item in enumerate(items):
                    sec = self._scan_boundary_sec(item)
                    if sec is None or sec <= 0.0:
                        continue
                    rows.append((float(sec), int(idx), item))
                rows.sort(key=lambda row: (row[0], row[1]))
                cache = {"key": key, "rows": rows, "secs": [row[0] for row in rows]}
                self._scan_boundary_hit_cache = cache
            rows = list(cache.get("rows") or [])
            secs = list(cache.get("secs") or [])
            pps = max(0.001, float(getattr(self, "pps", 1.0) or 1.0))
            center = float(x or 0.0) / pps
            pad = max(0.02, (int(margin) + 8) / pps)
            start_idx = bisect_left(secs, center - pad)
            end_idx = bisect_right(secs, center + pad)
            candidates = ((idx, item, sec) for sec, idx, item in rows[start_idx:end_idx])
        else:
            candidates = ((idx, item, self._scan_boundary_sec(item)) for idx, item in enumerate(items))

        for idx, item, sec in candidates:
            if sec is None or sec <= 0.0:
                continue
            bx = self._x(sec)
            dist = abs(int(x) - int(bx))
            if dist <= margin and dist < best_dist:
                best = {"index": int(idx), "sec": float(sec), "item": item}
                best_dist = dist
        return best

    def _set_hover_scan_boundary(self, hit) -> bool:
        idx = int(hit["index"]) if hit is not None else None
        if getattr(self, "_hover_scan_boundary_idx", None) == idx:
            return False
        self._hover_scan_boundary_idx = idx
        return True

    def _show_scan_boundary_menu(self, hit, gpos):
        if not hit:
            return
        chosen = show_context_menu(
            self,
            gpos,
            [{"id": "delete", "label": "삭제", "danger": True, "accent": "#FF453A"}],
        )
        if chosen == "delete":
            self.provisional_cut_boundary_delete_requested.emit(int(hit["index"]), float(hit["sec"]))

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
        candidates = self._segments_near_x_for_hit(x, pad_px=HANDLE_R + 8 + touch_slop) if hasattr(self, "_segments_near_x_for_hit") else self.segments
        hits: list[tuple[tuple[int, int, int, int, int], dict, str]] = []

        def _append_hit(seg: dict, edge: str, boundary_x: int) -> None:
            is_active = self._is_active_segment(seg) if hasattr(self, "_is_active_segment") else (
                self.active_seg_start is not None and abs(float(seg.get("start", 0.0) or 0.0) - float(self.active_seg_start)) < 0.5
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
                self.active_seg_start is not None and abs(float(seg.get("start", 0.0) or 0.0) - float(self.active_seg_start)) < 0.5
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
                target_h = max(HANDLE_R + handle_vertical_pad * 2, self._current_responsive_profile().touch_target if touch_slop > 0 else HANDLE_R + handle_vertical_pad * 2)
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
                self.active_seg_start is not None and abs(float(seg.get("start", 0.0) or 0.0) - float(self.active_seg_start)) < 0.5
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
        r = 5 + max(0, int(margin))
        return QRect(int(bx - r), int(DIAMOND_Y - r), r * 2, r * 2)

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

    def _find_owner_with_settings(self):
        owner = self.parent()
        while owner and not hasattr(owner, "settings"):
            owner = owner.parent()
        return owner

    def _speaker_settings_for_hit_test(self) -> dict:
        owner = self._find_owner_with_settings()
        settings = getattr(owner, "settings", {}) if owner is not None else {}
        keys = (
            "spk1_enabled", "spk1_id", "spk1_name", "spk1_color",
            "spk1_voice_disabled", "spk1_voice_file",
            "spk2_enabled", "spk2_id", "spk2_name", "spk2_color",
            "spk2_voice_disabled", "spk2_voice_file",
            "spk3_enabled", "spk3_id", "spk3_name", "spk3_color",
            "spk3_voice_disabled", "spk3_voice_file",
            "speaker_diarization_auto_enabled",
        )
        key = tuple((name, str((settings or {}).get(name, ""))) for name in keys)
        if key == getattr(self, "_speaker_hit_settings_cache_key", None):
            cached = getattr(self, "_speaker_hit_settings_cache", None)
            if isinstance(cached, dict):
                return cached
        merged = current_speaker_settings(settings)
        self._speaker_hit_settings_cache_key = key
        self._speaker_hit_settings_cache = dict(merged or {})
        return self._speaker_hit_settings_cache

    def _speaker_options(self):
        owner = self._find_owner_with_settings()
        settings = getattr(owner, "settings", {}) if owner is not None else {}
        options = []
        for row in visible_speaker_slots(current_speaker_settings(settings)):
            options.append(
                (
                    str(row.get("id", "00") or "00"),
                    str(row.get("name", "") or "화자"),
                    str(row.get("color", "#FFFFFF") or "#FFFFFF"),
                )
            )
        return options

    def _speaker_icon(self, color_hex):
        pix = QPixmap(20, 20)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color_hex))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, 12, 12)
        painter.end()
        return QIcon(pix)

    def _show_speaker_select_menu(self, seg, gpos):
        line = int(seg.get("line", 0))
        current = str(seg.get("speaker", seg.get("spk_id", "")) or "")
        if current.startswith("SPEAKER_"):
            current = current.replace("SPEAKER_", "")
        items = []
        for spk_id, name, color in self._speaker_options():
            items.append(
                {
                    "id": spk_id,
                    "label": name,
                    "checked": spk_id == current,
                    "accent": color,
                }
            )
        chosen = show_context_menu(self, gpos, items)
        if chosen:
            self.speaker_changed.emit(line, chosen)

    def _gap_menu_pivot_sec(self, gap, click_x: int) -> float:
        start = float(gap.get("start", 0.0) or 0.0)
        end = float(gap.get("end", start) or start)
        playhead = self._snap_to_frame(float(getattr(self, "playhead_sec", 0.0) or 0.0))
        if start < playhead < end:
            return playhead
        clicked = self._snap_to_frame(max(start, min(end, self._sec_from_x(click_x))))
        return clicked

    def _gap_generation_scope_for_pivot(self, gap, pivot_sec: float) -> tuple[float, float] | None:
        gap_start = self._snap_to_frame(float(gap.get("start", 0.0) or 0.0))
        gap_end = self._snap_to_frame(float(gap.get("end", gap_start) or gap_start))
        if gap_end <= gap_start:
            return None

        try:
            if hasattr(self, "generation_silence_markers_cached"):
                markers = self.generation_silence_markers_cached()
            else:
                markers = []
        except Exception:
            markers = []
        silence_ranges: list[tuple[float, float]] = []
        for marker in list(markers or []):
            kind = str(marker.get("kind", "") or "").strip().lower()
            label = str(marker.get("label", "") or "").strip()
            if kind not in {"generation_silence", "linked_silence"} and label not in {"무음구간", "무음"}:
                continue
            start = self._snap_to_frame(float(marker.get("start", 0.0) or 0.0))
            end = self._snap_to_frame(float(marker.get("end", start) or start))
            start = max(gap_start, start)
            end = min(gap_end, end)
            if end > start:
                silence_ranges.append((start, end))

        if not silence_ranges:
            return gap_start, gap_end

        pivot = self._snap_to_frame(float(pivot_sec))
        containing = [item for item in silence_ranges if item[0] - 0.001 <= pivot <= item[1] + 0.001]
        if containing:
            return min(containing, key=lambda item: item[1] - item[0])
        return min(silence_ranges, key=lambda item: min(abs(pivot - item[0]), abs(pivot - item[1])))

    def _show_gap_generate_menu(self, gap, gpos, click_x: int):
        if not self._gap_insert_controls_enabled():
            return
        start = self._snap_to_frame(float(gap.get("start", 0.0) or 0.0))
        end = self._snap_to_frame(float(gap.get("end", start) or start))
        if end <= start:
            return

        pivot = self._gap_menu_pivot_sec(gap, click_x)
        scope = self._gap_generation_scope_for_pivot(gap, pivot)
        if scope is None:
            return
        scope_start, scope_end = scope
        pivot = self._snap_to_frame(max(scope_start, min(scope_end, pivot)))
        min_span = max(0.02, min(0.1, 1.0 / max(1.0, float(self._get_fps()))))
        enabled = scope_end > scope_start + min_span
        chosen = show_context_menu(
            self,
            gpos,
            [
                {"id": "delete", "label": "자막 세그먼트 삭제", "enabled": True, "accent": "#FF453A"},
                {"id": "to", "label": "여기까지 자막 생성", "enabled": enabled, "accent": "#34C759"},
                {"id": "from", "label": "여기부터 자막 생성", "enabled": enabled, "accent": "#5AC8FA"},
            ],
        )
        if chosen == "delete":
            self.gap_to_segs.emit(start, end)
        elif chosen == "to":
            self.gap_generate_requested.emit(start, end, pivot, "to")
        elif chosen == "from":
            self.gap_generate_requested.emit(start, end, pivot, "from")

    def _timeline_fit_to_view_locked(self) -> bool:
        widget = self.parent()
        while widget is not None:
            if hasattr(widget, "_fit_to_view_locked"):
                try:
                    return bool(getattr(widget, "_fit_to_view_locked", False))
                except Exception:
                    return False
            widget = widget.parent()
        return False

    def _playhead_handle_hit_rect(self) -> QRect:
        handle_r = 7
        px = self._x(float(getattr(self, "playhead_sec", 0.0) or 0.0))
        slop = self._touch_hit_slop(handle_r * 2)
        return QRect(int(px - handle_r), 2, handle_r * 2, handle_r * 2).adjusted(-slop, -slop, slop, slop)

    def mousePressEvent(self, ev):
        if self._timeline_input_locked():
            ev.accept()
            return
        if self._playhead_handle_hit_rect().contains(ev.pos()):
            if ev.button() == Qt.MouseButton.RightButton:
                self.playhead_menu_requested.emit(ev.globalPosition().toPoint(), self.playhead_sec)
                return
            if ev.button() == Qt.MouseButton.LeftButton:
                x, y = ev.pos().x(), ev.pos().y()
                self._last_click_x = x
                self._last_click_y = y
                self._begin_playhead_handle_scrub()
                self._emit_scrub_with_playhead_cut_magnet(self.playhead_sec)
                return

        x, y = ev.pos().x(), ev.pos().y()
        self._last_click_x = x; self._last_click_y = y
        click_sec = self._snap_to_frame(max(0.0, self._sec_from_x(x)))

        if ev.button() == Qt.MouseButton.LeftButton:
            for clip_idx, rect in getattr(self, '_clip_delete_rects', []) or []:
                if rect.contains(x, y):
                    self._clear_pending_center_drag()
                    self.sig_clip_delete_requested.emit(int(clip_idx))
                    ev.accept()
                    return
            if hasattr(self, '_clip_add_rect') and getattr(self, '_clip_add_rect', QRect()).contains(x, y):
                self._clear_pending_center_drag()
                self.sig_clip_add_requested.emit()
                ev.accept()
                return

        # 멀티클립 박스 클릭 감지 (단일 경로)
        hit_box = self._hit_multiclip_box(x) if ev.button() == Qt.MouseButton.LeftButton else None
        if hit_box is not None:
            self._clear_pending_center_drag()
            new_idx = hit_box.get("index", 1) - 1
            if new_idx != self._active_clip_idx:
                self._active_clip_idx = new_idx
                self.sig_clip_selected.emit(new_idx)
                self.update()

        if self._edit_active:
            if hasattr(self, "_smart_split_edit_active") and self._smart_split_edit_active():
                if ev.button() == Qt.MouseButton.LeftButton:
                    if hasattr(self, "_route_inline_editor_click") and self._route_inline_editor_click(x, y):
                        return
                    editor = getattr(self, "_inline_editor", None)
                    if editor is not None:
                        editor.setFocus(Qt.FocusReason.MouseFocusReason)
                ev.accept()
                return
            if self._is_readonly_analysis_lane_y(y):
                if ev.button() == Qt.MouseButton.LeftButton:
                    self._commit_inline_edit()
                ev.accept()
                return
            if ev.button() == Qt.MouseButton.RightButton:
                self._show_mic_menu(ev.globalPosition().toPoint()); return
            if ev.button() == Qt.MouseButton.LeftButton:
                if hasattr(self, "_route_inline_editor_click") and self._route_inline_editor_click(x, y):
                    return
                # 바깥 클릭 → 커밋 후 정상 클릭 동작으로 fall-through
                self._commit_inline_edit()
            else:
                return

        self._just_committed = False; self.setFocus()

        if self._is_readonly_analysis_lane_y(y):
            self._clear_pending_center_drag()
            self._clear_active_gaps_for_segment_drag()
            if ev.button() == Qt.MouseButton.LeftButton:
                self._emit_scrub_with_shadow(click_sec)
            ev.accept()
            return

        # 멀티클립 박스 클릭은 상단 단일 경로에서만 처리

        if ev.button() == Qt.MouseButton.RightButton:
            self._clear_pending_center_drag()
            scan_boundary_hit = self._scan_boundary_hit_at(x, y, margin=7)
            if scan_boundary_hit:
                self._set_hover_scan_boundary(scan_boundary_hit)
                self.update()
                self._show_scan_boundary_menu(scan_boundary_hit, ev.globalPosition().toPoint())
                return
            if self._roughcut_major_lane_contains(x, y):
                self.provisional_cut_boundary_requested.emit(self._snap_to_frame(max(0.0, self._sec_from_x(x))))
                return
            candidate = self._stt_candidate_at(x, y)
            if candidate:
                self.stt_candidate_selected.emit(dict(candidate))
                return
            speaker_seg = self._speaker_lane_seg_at(x, y)
            if speaker_seg:
                self._show_speaker_learn_menu(int(speaker_seg.get("line", 0)), ev.globalPosition().toPoint())
                return
            gap = self._gap_at(x, y)
            if gap:
                self._show_gap_generate_menu(gap, ev.globalPosition().toPoint(), x)
                return
            if y < SEG_TOP:
                ev.accept()
                return
            if SEG_TOP <= y <= SEG_BOT:
                seg = self._seg_at(x)
                if seg:
                    self._show_segment_context_menu(seg, ev.globalPosition().toPoint(), click_x=x, click_y=y)
            return

        if ev.button() != Qt.MouseButton.LeftButton: return

        diamond_margin = 7 if abs(int(y) - int(DIAMOND_Y)) <= 10 else 5
        diamond_idx = self._diamond_index_at(x, y, margin=diamond_margin)
        if diamond_idx is not None:
            pair = self._diamond_pair_for_index(diamond_idx)
            if pair is None:
                self._clear_pending_center_drag()
                return
            left_idx, right_idx, s1, _ = pair
            self._clear_pending_center_drag()
            self.drag_started.emit(); self._drag_edge = "diamond"; self._drag_diamond_idx = diamond_idx
            self._drag_diamond_pair = (left_idx, right_idx)
            self._drag_diamond_orig = s1["end"]; self._drag_x0 = x
            self._clear_active_gaps_for_segment_drag()
            self._drag_snap_candidates_cache = self._drag_snap_candidates()
            self._drag_last_paint_rect = self._drag_visual_rect()
            self._emit_scrub_with_shadow(click_sec)
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor)); return

        candidate = self._stt_candidate_at(x, y)
        if candidate:
            self._clear_pending_center_drag()
            self._emit_scrub_with_shadow(click_sec)
            self.stt_candidate_selected.emit(dict(candidate))
            return

        speaker_seg = self._speaker_lane_seg_at(x, y)
        if speaker_seg:
            self._clear_pending_center_drag()
            self._emit_scrub_with_shadow(click_sec)
            self._show_speaker_select_menu(speaker_seg, ev.globalPosition().toPoint())
            return

        if y < SEG_TOP:
            self._clear_pending_center_drag()
            self._is_panning = True; self._pan_last_x = ev.globalPosition().x()
            self.setCursor(Qt.CursorShape.ClosedHandCursor); self._emit_scrub_with_shadow(click_sec); return

        handle_hit = self._handle_drag_at(x, y)
        if handle_hit:
            self._clear_pending_center_drag()
            self._emit_scrub_with_shadow(click_sec)
            self._setup_drag(handle_hit[0], handle_hit[1], x)
            return

        gap_candidates = []
        if self._gap_insert_controls_enabled():
            gap_candidates = self._gaps_near_x_for_hit(x, pad_px=ICON_SZ + 10) if hasattr(self, "_gaps_near_x_for_hit") else self.gap_segments
        for g in gap_candidates:
            gx1, gx2 = self._x(g["start"]), self._x(g["end"])
            if self._plus_rect(gx1, gx2).adjusted(-5, -5, 5, 5).contains(x, y):
                self._clear_pending_center_drag()
                if self._timeline_fit_to_view_locked():
                    self._is_scrubbing = True
                    self._emit_scrub_with_shadow(click_sec)
                    return
                self._emit_scrub_with_shadow(click_sec)
                if g.get("active"): self.gap_to_segs.emit(g["start"], g["end"])
                else: g["active"] = True; self.update(); self.gap_activated.emit(g["start"], g["end"])
                return

        if SEG_TOP <= y <= SEG_BOT:
            for g in gap_candidates:
                if g.get("active"): continue
                gx1, gx2 = self._x(g["start"]), self._x(g["end"])
                if gx2 - gx1 >= ICON_SZ + 8 and self._plus_rect(gx1, gx2).contains(x, y):
                    self._clear_pending_center_drag()
                    self._emit_scrub_with_shadow(click_sec)
                    if self._timeline_fit_to_view_locked():
                        self._is_scrubbing = True
                        return
                    g["active"] = True; self.update(); self.gap_activated.emit(g["start"], g["end"]); return

        drag_candidate = self._center_drag_candidate_at(x, y, active_only=False)
        if drag_candidate is not None:
            is_active = self._is_active_segment(drag_candidate) if hasattr(self, "_is_active_segment") else (
                self.active_seg_start is not None and abs(float(drag_candidate.get("start", 0.0) or 0.0) - float(self.active_seg_start)) < 0.5
            )
            if is_active:
                self._clear_pending_center_drag()
                self._emit_scrub_with_shadow(click_sec)
                self._setup_drag(drag_candidate, "center", x); self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor)); return
            self._pending_center_drag_seg = drag_candidate
            self._pending_center_drag_x = int(x)
            self._pending_center_drag_y = int(y)
            self._emit_scrub_with_shadow(click_sec)
            self.seg_clicked.emit(drag_candidate.get("line", 0), click_sec)
            return

        self._clear_pending_center_drag()
        seg = self._seg_at(x)
        if seg:
            self._emit_scrub_with_shadow(click_sec)
            self.seg_clicked.emit(seg.get("line", 0), click_sec)
            return
        self._is_scrubbing = True; self._emit_scrub_with_shadow(click_sec)

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
        self.drag_started.emit(); self._drag_seg, self._drag_edge = s, edge; self._drag_x0 = x
        self.active_seg_start = float(s.get("start", 0.0) or 0.0)
        if hasattr(self, "_sync_active_segment_key"):
            self._sync_active_segment_key(seg=s)
        self._drag_s0_start, self._drag_s0_end = s["start"], s["end"]
        self._drag_adj_l = self._get_prev_seg(s); self._drag_adj_r = self._get_next_seg(s)
        self._drag_adj_orig_start_l = self._drag_adj_l["start"] if self._drag_adj_l else 0.0
        self._drag_adj_orig_end_l = self._drag_adj_l["end"] if self._drag_adj_l else 0.0
        self._drag_adj_orig_start_r = self._drag_adj_r["start"] if self._drag_adj_r else 0.0
        self._drag_adj_orig_end_r = self._drag_adj_r["end"] if self._drag_adj_r else 0.0
        self._clear_active_gaps_for_segment_drag()
        self._drag_snap_candidates_cache = self._drag_snap_candidates()
        self._drag_last_paint_rect = self._drag_visual_rect()
        if edge != "center": self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))

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

    def mouseDoubleClickEvent(self, ev):
        if bool(getattr(self, "_editor_processing_input_locked", False)):
            ev.accept()
            return
        if ev.button() != Qt.MouseButton.LeftButton: return
        if self._edit_active:
            if hasattr(self, "_smart_split_edit_active") and self._smart_split_edit_active():
                ev.accept()
                return
            self._commit_inline_edit()
            return
        x, y = ev.pos().x(), ev.pos().y()

        if self._is_readonly_analysis_lane_y(y):
            ev.accept()
            return

        diamond_idx = self._diamond_index_at(x, y, margin=5)
        if diamond_idx is not None:
            pair = self._diamond_pair_for_index(diamond_idx)
            if pair is None:
                return
            _, _, s1, s2 = pair
            self._drag_seg = None; self._drag_edge = None; self._drag_diamond_idx = None
            self._drag_diamond_pair = None
            self._clear_drag_guides(); self.unsetCursor()
            self.drag_finished.emit()
            self.diamond_merge.emit(s1.get("line", 0), s2.get("line", 0)); return

        if SEG_TOP <= y <= SEG_BOT:
            seg = self._seg_at(x)
            if seg: self.seg_double_clicked.emit(seg.get("line", 0), seg["start"])

    def mouseMoveEvent(self, ev):
        if bool(getattr(self, "_editor_processing_input_locked", False)):
            self._is_panning = False
            self._is_scrubbing = False
            self.unsetCursor()
            return
        x, y = ev.pos().x(), ev.pos().y()

        if self._edit_active:
            seg = self._segment_for_line(self._edit_line) if hasattr(self, "_segment_for_line") else next((s for s in self.segments if s.get("line") == self._edit_line), None)
            if seg and SEG_TOP <= y <= SEG_BOT and self._x(seg["start"]) + HANDLE_R < x < self._x(seg["end"]) - HANDLE_R:
                self.setCursor(Qt.CursorShape.IBeamCursor)
            else: self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if self._is_readonly_analysis_lane_y(y):
            if (
                self._hover_handle is not None
                or getattr(self, "_hover_diamond", None) is not None
                or self._hover_line is not None
                or getattr(self, "_hover_scan_boundary_idx", None) is not None
            ):
                self._hover_handle = None
                self._hover_diamond = None
                self._hover_line = None
                self._hover_scan_boundary_idx = None
                self.update()
            self.unsetCursor()
            return

        if getattr(self, '_is_panning', False) and (ev.buttons() & Qt.MouseButton.LeftButton):
            current_x = ev.globalPosition().x(); delta_x = self._pan_last_x - current_x
            w = self.parent()
            from PyQt6.QtWidgets import QScrollArea
            while w and not isinstance(w, QScrollArea): w = w.parent()
            if w: w.horizontalScrollBar().setValue(int(w.horizontalScrollBar().value() + delta_x))
            self._pan_last_x = current_x; return

        if getattr(self, '_is_scrubbing', False) and (ev.buttons() & Qt.MouseButton.LeftButton):
            scrub_sec = self._snap_to_frame(max(0.0, self._sec_from_x(x)))
            if getattr(self, "_playhead_handle_scrubbing", False):
                self._emit_scrub_with_playhead_cut_magnet(scrub_sec)
            else:
                self.scrub_sec.emit(scrub_sec)
            return

        pending_center_drag = getattr(self, "_pending_center_drag_seg", None)
        if pending_center_drag is not None:
            if not (ev.buttons() & Qt.MouseButton.LeftButton):
                self._clear_pending_center_drag()
            else:
                threshold = max(2, int(QApplication.startDragDistance() or 4))
                moved_x = abs(int(x) - int(getattr(self, "_pending_center_drag_x", x)))
                moved_y = abs(int(y) - int(getattr(self, "_pending_center_drag_y", y)))
                if moved_x >= threshold or moved_y >= threshold:
                    press_x = int(getattr(self, "_pending_center_drag_x", x))
                    self._setup_drag(pending_center_drag, "center", press_x)
                    self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
                    if self._drag_seg:
                        self._apply_drag(self._sec_delta_from_pixels(x - self._drag_x0))
                    return

        if self._drag_seg or getattr(self, '_drag_edge', None) == "diamond":
            if ev.buttons() & Qt.MouseButton.LeftButton: self._apply_drag(self._sec_delta_from_pixels(x - self._drag_x0))
            return

        scan_boundary_hit = self._scan_boundary_hit_at(x, y, margin=7)
        if scan_boundary_hit is not None:
            changed = self._set_hover_scan_boundary(scan_boundary_hit)
            if self._hover_handle is not None:
                self._hover_handle = None
                changed = True
            if getattr(self, '_hover_diamond', None) is not None:
                self._hover_diamond = None
                changed = True
            if self._hover_line is not None:
                self._hover_line = None
                changed = True
            if changed:
                self.update()
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            return
        if self._set_hover_scan_boundary(None):
            self.update()

        new_hh = self._handle_hover_at(x, y)
        if new_hh is not None:
            changed = False
            if getattr(self, '_hover_diamond', None) is not None:
                self._hover_diamond = None
                changed = True
            if self._hover_handle != new_hh:
                self._hover_handle = new_hh
                changed = True
            if changed:
                self.update()
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            return

        hover_dia = self._diamond_index_at(x, y, margin=7 if abs(int(y) - int(DIAMOND_Y)) <= 10 else 5)
        if hover_dia is not None and abs(int(y) - int(DIAMOND_Y)) <= 12:
            changed = False
            if self._hover_handle is not None:
                self._hover_handle = None
                changed = True
            if getattr(self, '_hover_diamond', None) != hover_dia:
                self._hover_diamond = hover_dia
                changed = True
            if changed:
                self.update()
            self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor)); return
        if getattr(self, '_hover_diamond', None) != hover_dia: self._hover_diamond = hover_dia; self.update()

        hover_handle = bool(new_hh)
        hover_center = False
        if not hover_handle:
            hover_center = self._center_drag_candidate_at(x, y, active_only=False) is not None

        if self._hover_handle != new_hh: self._hover_handle = new_hh; self.update()
        if hover_handle: self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        elif hover_center: self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        else: self.unsetCursor()

        seg2 = self._seg_at(x); new_h = seg2.get("line") if seg2 else None
        if new_h != self._hover_line: self._hover_line = new_h; self.update()

    def mouseReleaseEvent(self, ev):
        if bool(getattr(self, "_editor_processing_input_locked", False)):
            self._is_panning = False
            self._is_scrubbing = False
            self.unsetCursor()
            self._clear_pending_center_drag()
            return
        if getattr(self, '_is_panning', False): self._is_panning = False; self.unsetCursor(); self._clear_pending_center_drag(); return
        if getattr(self, '_is_scrubbing', False):
            self._is_scrubbing = False
            self._finish_playhead_handle_scrub()
            self._clear_pending_center_drag()
            return

        if getattr(self, '_drag_edge', None) == "diamond":
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
            guide_secs = self._drag_release_guide_secs()
            self.seg_time_changed.emit(self._drag_seg.get("line", 0), self._drag_seg["start"], self._drag_seg["end"], edge)
            self._finish_timing_drag_cleanup(dirty)
            self._remember_drag_release_guides(guide_secs)
            self._clear_pending_center_drag()
            return

        self._clear_pending_center_drag()

    def _apply_drag(self, delta):
        apply_timing_drag(self, delta)
        preview_sec = self._timing_drag_preview_sec()
        if preview_sec is not None:
            try:
                self.drag_preview_sec.emit(float(preview_sec))
            except Exception:
                pass

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
