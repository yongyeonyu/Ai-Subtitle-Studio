"""Backward-compatible module alias for editor video-control UX helpers."""

import sys

from ui.editor.ux import editor_video_controls as _impl

sys.modules[__name__] = _impl
