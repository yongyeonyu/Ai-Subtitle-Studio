"""Backward-compatible module alias for editor subtitle assist UX helpers."""

import sys

from ui.editor.ux import editor_subtitle_assist as _impl

sys.modules[__name__] = _impl
