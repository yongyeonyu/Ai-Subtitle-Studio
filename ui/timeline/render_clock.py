# Version: 03.14.31
# Phase: PHASE2
"""Display-refresh helpers for lightweight timeline animation."""

from __future__ import annotations

import os


def _refresh_hz_override() -> float | None:
    raw = str(os.environ.get("AI_SUBTITLE_UI_REFRESH_HZ", "") or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if value <= 0:
        return None
    return value


def display_refresh_hz(widget=None, *, fallback: float = 60.0) -> float:
    """Return the active screen refresh rate, clamped for Qt timer use."""
    override = _refresh_hz_override()
    if override is not None:
        return max(30.0, min(240.0, override))

    rate = 0.0
    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        screen = None
        if widget is not None:
            try:
                handle = widget.windowHandle()
                screen = handle.screen() if handle is not None else None
            except Exception:
                screen = None
            if screen is None:
                try:
                    rect = widget.rect()
                    screen = QApplication.screenAt(widget.mapToGlobal(rect.center()))
                except Exception:
                    screen = None
        if screen is None and app is not None:
            screen = app.primaryScreen()
        if screen is not None:
            rate = float(screen.refreshRate() or 0.0)
    except Exception:
        rate = 0.0

    if rate <= 0.0:
        rate = float(fallback or 60.0)
    return max(30.0, min(240.0, rate))


def display_frame_interval_ms(widget=None, *, fallback_hz: float = 60.0) -> int:
    hz = display_refresh_hz(widget, fallback=fallback_hz)
    return max(4, min(34, int(round(1000.0 / hz))))
