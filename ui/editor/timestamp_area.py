"""Backward-compatible module alias for subtitle timestamp gutter widgets."""

import sys

from ui.editor.ux import timestamp_area as _impl

sys.modules[__name__] = _impl
