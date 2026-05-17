"""Shared timeline playhead mode helpers for input and rendering."""

from __future__ import annotations

from PyQt6.QtCore import Qt

from ui.timeline.timeline_constants import SEG_TOP


PLAYHEAD_MODE_SEGMENT_NAV = "waveform"
PLAYHEAD_MODE_FRAME_STEP = "segment"
PLAYHEAD_MODE_SEGMENT_COLOR = "#4AFF80"
PLAYHEAD_MODE_FRAME_COLOR = "#FF4444"


def normalize_playhead_focus_mode(mode: str | None) -> str:
    value = str(mode or "").strip().lower()
    if value == PLAYHEAD_MODE_SEGMENT_NAV:
        return PLAYHEAD_MODE_SEGMENT_NAV
    return PLAYHEAD_MODE_FRAME_STEP


def is_segment_navigation_mode(mode: str | None) -> bool:
    return normalize_playhead_focus_mode(mode) == PLAYHEAD_MODE_SEGMENT_NAV


def playhead_line_color_hex(mode: str | None) -> str:
    if is_segment_navigation_mode(mode):
        return PLAYHEAD_MODE_SEGMENT_COLOR
    return PLAYHEAD_MODE_FRAME_COLOR


def playhead_focus_mode_for_key(key) -> str | None:
    if key == Qt.Key.Key_Up:
        return PLAYHEAD_MODE_SEGMENT_NAV
    if key == Qt.Key.Key_Down:
        return PLAYHEAD_MODE_FRAME_STEP
    return None


def playhead_focus_mode_for_y(y: int | float) -> str:
    try:
        return PLAYHEAD_MODE_SEGMENT_NAV if int(y) <= int(SEG_TOP) else PLAYHEAD_MODE_FRAME_STEP
    except Exception:
        return PLAYHEAD_MODE_FRAME_STEP


def set_playhead_focus_mode(target, mode: str | None) -> bool:
    normalized = normalize_playhead_focus_mode(mode)
    current = normalize_playhead_focus_mode(getattr(target, "focus_mode", None))
    if current == normalized:
        return False
    setattr(target, "focus_mode", normalized)
    updater = getattr(target, "update", None)
    if callable(updater):
        updater()
    return True


def set_playhead_focus_mode_from_key(target, key) -> bool:
    mode = playhead_focus_mode_for_key(key)
    if mode is None:
        return False
    set_playhead_focus_mode(target, mode)
    return True


def set_playhead_focus_mode_from_y(target, y: int | float) -> bool:
    return set_playhead_focus_mode(target, playhead_focus_mode_for_y(y))


def dispatch_playhead_arrow_step(target, direction: int) -> bool:
    try:
        raw_direction = int(direction or 0)
    except Exception:
        raw_direction = 0
    if raw_direction == 0:
        return False

    mode = normalize_playhead_focus_mode(getattr(target, "focus_mode", None))
    if is_segment_navigation_mode(mode):
        jump_name = "_jump_to_next_segment" if raw_direction > 0 else "_jump_to_prev_segment"
        jumper = getattr(target, jump_name, None)
        if not callable(jumper):
            return False
        moved = False
        for _ in range(max(1, abs(raw_direction))):
            if not bool(jumper()):
                break
            moved = True
        return moved

    dispatcher = getattr(target, "_dispatch_frame_step", None)
    if not callable(dispatcher):
        return False
    return bool(dispatcher(raw_direction))
