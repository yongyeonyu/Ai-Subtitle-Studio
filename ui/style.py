# Version: 02.03.17
# Phase: PHASE1-C
"""
Shared UI style tokens for the gradual PHASE1-C refresh.

This module centralizes low-risk button and label styles first. Layout and
behavior stay in each widget so existing signal/slot flows remain untouched.
"""

import config


COLORS = {
    "bg": "#0F1518",
    "sidebar": "#11181C",
    "surface": "#151C20",
    "surface_alt": "#1B2429",
    "control": "#202A31",
    "control_hover": "#2A363F",
    "primary": "#007AFF",
    "primary_hover": "#0066D6",
    "text": "#F5F7FA",
    "muted": "#A9B0B7",
    "danger": "#FF3B30",
    "warning": "#FF9500",
    "info": "#5AC8FA",
    "accent": "#34C759",
    "separator": "#2D3942",
}


def _px(value):
    if isinstance(value, int):
        return f"{value}px"
    return str(value)


def button_style(kind="toolbar", *, font_size=None, padding=None):
    """Return a shared QPushButton stylesheet without changing behavior."""
    if kind == "primary":
        font_size = font_size or "13px"
        padding = padding or "9px 18px"
        return (
            "QPushButton { "
            f"background: {COLORS['primary']}; color: #FFFFFF; border: none; "
            f"padding: {padding}; font-size: {_px(font_size)}; font-weight: bold; "
            "border-radius: 7px; min-height: 38px; "
            "} "
            f"QPushButton:hover {{ background: {COLORS['primary_hover']}; }}"
        )

    if kind == "danger":
        font_size = font_size or "12px"
        padding = padding or "6px 12px"
        return (
            "QPushButton { "
            f"background: {COLORS['danger']}; color: #FFFFFF; border: none; "
            f"padding: {padding}; font-size: {_px(font_size)}; font-weight: bold; "
            "border-radius: 7px; "
            "} "
            "QPushButton:hover { background: #D70015; }"
        )

    font_size = font_size or "11px"
    padding = padding or "6px 10px"
    return (
        "QPushButton { "
        f"background: {COLORS['control']}; color: {COLORS['text']}; border: 1px solid {COLORS['separator']}; "
        f"padding: {padding}; font-size: {_px(font_size)}; border-radius: 7px; "
        "} "
        f"QPushButton:hover {{ background: {COLORS['control_hover']}; }}"
    )


def label_style(tone="text", size=12, *, bold=False):
    color = COLORS.get(tone, COLORS["text"])
    weight = "font-weight: bold;" if bold else ""
    return (
        f"color: {color}; font-size: {_px(size)}; {weight} "
        "border: none; background: transparent;"
    )


def panel_style(kind="surface"):
    bg = COLORS["surface"] if kind == "surface" else COLORS["surface_alt"]
    return (
        f"background: {bg}; border: 1px solid {COLORS['separator']}; "
        "border-radius: 7px;"
    )


def app_stylesheet():
    return (
        f"QWidget {{ background: {COLORS['bg']}; color: {COLORS['text']}; }}"
        "QToolTip { background: #202A31; color: #F5F7FA; border: 1px solid #3A4650; padding: 5px; }"
        f"QTextEdit {{ background: {COLORS['surface']}; color: {COLORS['text']}; border: none; }}"
        f"QScrollArea {{ background: transparent; border: none; }}"
        f"QTableWidget {{ background: {COLORS['surface']}; color: {COLORS['text']}; border: none; gridline-color: {COLORS['separator']}; }}"
        f"QHeaderView::section {{ background: {COLORS['surface_alt']}; color: {COLORS['muted']}; border: none; padding: 8px; }}"
    )
