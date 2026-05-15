"""Backward-compatible module alias for timeline input UX helpers."""

import sys

from ui.editor.ux import timeline_input as _impl

sys.modules[__name__] = _impl
