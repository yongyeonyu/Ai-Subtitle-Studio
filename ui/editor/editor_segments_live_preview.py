"""Backward-compatible module alias for editor live-preview UX helpers."""

import sys

from ui.editor.ux import editor_segments_live_preview as _impl

sys.modules[__name__] = _impl
