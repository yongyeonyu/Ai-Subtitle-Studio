# Version: 03.14.13
# Phase: PHASE2
"""Compatibility no-ops for the removed sidebar preset menu."""

from __future__ import annotations


def sync_sidebar_preset_panel(host, settings: dict | None = None) -> None:
    """The old manual preset panel was removed; audio is decided per clip at runtime."""
    return None
