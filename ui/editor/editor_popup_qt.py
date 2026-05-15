"""Backward-compatible module alias for editor popup UX helpers."""

import sys

from ui.editor.ux import editor_popup_qt as _impl

sys.modules[__name__] = _impl
