"""Backward-compatible module alias for subtitle text edit UX widgets."""

import sys

from ui.editor.ux import subtitle_text_edit as _impl

sys.modules[__name__] = _impl
