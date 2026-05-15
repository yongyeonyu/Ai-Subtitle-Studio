"""Backward-compatible module alias for timeline subtitle segment editing UX helpers."""

import sys

from ui.editor.ux import timeline_subtitle_segment_editing as _impl

sys.modules[__name__] = _impl
