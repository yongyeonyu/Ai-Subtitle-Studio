"""
Backward-compatible shim for the centralized subtitle-segment editing mixin.
"""

from ui.timeline.timeline_subtitle_segment_editing import (
    NEW_SUBTITLE_PLACEHOLDER,
    TimelineInlineEditMixin,
    TimelineSubtitleSegmentEditingMixin,
)

__all__ = [
    "NEW_SUBTITLE_PLACEHOLDER",
    "TimelineInlineEditMixin",
    "TimelineSubtitleSegmentEditingMixin",
]
