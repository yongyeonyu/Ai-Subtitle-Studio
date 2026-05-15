"""Backward-compatible module alias for editor timeline/video UX helpers."""

import sys

from ui.editor.ux import editor_timeline_video as _impl

sys.modules[__name__] = _impl
