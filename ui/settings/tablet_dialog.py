# Version: 03.20.00
# Phase: PHASE4_iPad
"""Tablet-safe sizing helpers for settings dialogs."""
from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import QDialog, QWidget

from ui.responsive_profile import responsive_profile_for_size


def _owner_for_dialog(dialog: QDialog) -> QWidget:
    parent = dialog.parentWidget()
    return parent if parent is not None else dialog


def apply_tablet_dialog_profile(dialog: QDialog) -> Any:
    """Clamp oversized settings dialogs when opened from tablet-sized windows."""
    owner = _owner_for_dialog(dialog)
    try:
        override = str(owner.property("responsive_profile_override") or dialog.property("responsive_profile_override") or "")
    except Exception:
        override = ""
    try:
        width = int(owner.width() or dialog.width() or 0)
        height = int(owner.height() or dialog.height() or 0)
    except Exception:
        width = int(dialog.width() or 0)
        height = int(dialog.height() or 0)

    profile = responsive_profile_for_size(width, height, override=override)
    dialog._settings_control_height = profile.settings_min_button_height
    dialog.setProperty("responsive_profile_name", profile.name)
    if profile.name == "desktop":
        return profile

    available_width = max(360, width - 32)
    current_min = max(1, int(dialog.minimumWidth() or dialog.width() or 0))
    target_min = max(360, min(current_min, available_width))
    dialog.setMinimumWidth(target_min)
    if dialog.width() > available_width:
        dialog.resize(available_width, dialog.height())
    try:
        dialog.setSizeGripEnabled(True)
    except Exception:
        pass
    return profile
