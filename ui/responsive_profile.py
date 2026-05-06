# Version: 03.20.00
# Phase: PHASE4_iPad
"""Responsive layout hints shared by desktop and tablet-sized UI surfaces."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResponsiveProfile:
    name: str
    touch_target: int
    menu_bar_height: int
    menu_button_height: int
    menu_icon_only_width: int
    editor_compact_width: int
    settings_min_button_height: int
    sidebar_min_width: int
    sidebar_max_width: int
    sidebar_width_ratio: float
    reason: str


DESKTOP_PROFILE = ResponsiveProfile(
    name="desktop",
    touch_target=44,
    menu_bar_height=54,
    menu_button_height=44,
    menu_icon_only_width=760,
    editor_compact_width=1100,
    settings_min_button_height=40,
    sidebar_min_width=204,
    sidebar_max_width=218,
    sidebar_width_ratio=0.14,
    reason="desktop_default",
)

TABLET_LANDSCAPE_PROFILE = ResponsiveProfile(
    name="tablet_landscape",
    touch_target=48,
    menu_bar_height=58,
    menu_button_height=48,
    menu_icon_only_width=920,
    editor_compact_width=1180,
    settings_min_button_height=44,
    sidebar_min_width=218,
    sidebar_max_width=260,
    sidebar_width_ratio=0.20,
    reason="tablet_landscape_size",
)

TABLET_PORTRAIT_PROFILE = ResponsiveProfile(
    name="tablet_portrait",
    touch_target=48,
    menu_bar_height=60,
    menu_button_height=48,
    menu_icon_only_width=980,
    editor_compact_width=1260,
    settings_min_button_height=44,
    sidebar_min_width=176,
    sidebar_max_width=214,
    sidebar_width_ratio=0.24,
    reason="tablet_portrait_size",
)


_PROFILE_BY_NAME = {
    DESKTOP_PROFILE.name: DESKTOP_PROFILE,
    TABLET_LANDSCAPE_PROFILE.name: TABLET_LANDSCAPE_PROFILE,
    TABLET_PORTRAIT_PROFILE.name: TABLET_PORTRAIT_PROFILE,
}


def _int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(float(value)))
    except Exception:
        return default


def responsive_profile_for_size(
    width: Any,
    height: Any = 0,
    *,
    touch_capable: bool = False,
    platform: str = "",
    override: str | None = None,
) -> ResponsiveProfile:
    """Return conservative UI sizing hints for a window or viewport size.

    The app is still a desktop PyQt app, so iPad work starts as tablet-sized
    and touch-safe layout readiness rather than assuming a native iOS runtime.
    """
    forced = str(override or "").strip().lower()
    if forced in _PROFILE_BY_NAME:
        return _PROFILE_BY_NAME[forced]

    w = _int(width)
    h = _int(height)
    if w <= 0 and h <= 0:
        return DESKTOP_PROFILE
    if w <= 0:
        w = h
    if h <= 0:
        h = w

    shortest = min(w, h)
    longest = max(w, h)
    platform_key = str(platform or "").lower()
    looks_like_ipad = (
        "ipad" in platform_key
        or "tablet" in platform_key
        or ("ios" in platform_key and shortest >= 700)
    )
    looks_like_tablet = bool(touch_capable) or bool(looks_like_ipad)
    if not looks_like_tablet:
        return DESKTOP_PROFILE
    if h > w:
        return TABLET_PORTRAIT_PROFILE
    return TABLET_LANDSCAPE_PROFILE


def profile_name_for_size(width: Any, height: Any = 0, **kwargs: Any) -> str:
    return responsive_profile_for_size(width, height, **kwargs).name


def responsive_sidebar_width(total_width: Any, profile: ResponsiveProfile) -> int:
    total = max(1, _int(total_width, 1))
    target = int(round(total * float(profile.sidebar_width_ratio)))
    return max(profile.sidebar_min_width, min(profile.sidebar_max_width, target))
