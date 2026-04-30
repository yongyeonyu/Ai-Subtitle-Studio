# Version: 03.01.15
# Phase: PHASE2
"""Canonical editor workspace modes.

Processing states such as STT or subtitle generation are status values, not
screen modes. Legacy saved values are still accepted for older projects.
"""

EDITOR_MODE = "editor"
ROUGHCUT_MODE = "roughcut"
SHORTFORM_MODE = "shortform"

WORK_MODES = {EDITOR_MODE, ROUGHCUT_MODE, SHORTFORM_MODE}

_LEGACY_MODE_MAP = {
    "": EDITOR_MODE,
    "edit": EDITOR_MODE,
    "editor": EDITOR_MODE,
    "subtitle": EDITOR_MODE,
    "subtitle_generation": EDITOR_MODE,
    "stt": EDITOR_MODE,
    "roughcut": ROUGHCUT_MODE,
    "shortform": SHORTFORM_MODE,
}


def normalize_work_mode(mode: object, default: str = EDITOR_MODE) -> str:
    """Return one of editor/roughcut/shortform while accepting legacy aliases."""
    default_mode = _LEGACY_MODE_MAP.get(str(default or "").strip().lower(), EDITOR_MODE)
    key = str(mode or "").strip().lower()
    return _LEGACY_MODE_MAP.get(key, default_mode)


def is_editor_work_mode(mode: object) -> bool:
    return normalize_work_mode(mode) == EDITOR_MODE
