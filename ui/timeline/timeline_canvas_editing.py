"""Backward-compatible module alias for timeline canvas editing UX helpers."""

import sys

from ui.editor.ux import timeline_canvas_editing as _impl

sys.modules[__name__] = _impl
