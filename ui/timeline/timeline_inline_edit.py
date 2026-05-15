"""Backward-compatible shim for centralized subtitle-segment editing mixins."""

from ui.editor.ux.timeline_subtitle_segment_editing import (
    NEW_SUBTITLE_PLACEHOLDER,
    TimelineInlineEditMixin,
    TimelineSubtitleSegmentEditingMixin,
)

__all__ = [
    "NEW_SUBTITLE_PLACEHOLDER",
    "TimelineInlineEditMixin",
    "TimelineSubtitleSegmentEditingMixin",
]
