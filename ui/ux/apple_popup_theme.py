"""Reusable Apple-style black popup theming helpers."""

from __future__ import annotations

from ui.style import COLORS


def apple_popup_dialog_stylesheet(object_name: str, *, accent: str | None = None) -> str:
    accent = str(accent or COLORS["primary"])
    return (
        f"#{object_name} {{ background: {COLORS['bg']}; }} "
        "QScrollArea { background: transparent; border: none; } "
        f"QGroupBox {{ background: {COLORS['surface']}; border: 1px solid {COLORS['separator']}; "
        "border-radius: 16px; margin-top: 14px; padding: 16px 14px 14px 14px; "
        f"font-size: 13px; font-weight: 800; color: {COLORS['text']}; }} "
        f"QGroupBox::title {{ color: {COLORS['text']}; padding: 0 8px; }} "
        f"QListWidget {{ background: {COLORS['sidebar']}; color: {COLORS['text']}; border: 1px solid {COLORS['separator']}; "
        "border-radius: 14px; padding: 8px; } "
        f"QListWidget::item {{ padding: 8px 10px; border-radius: 10px; margin: 2px 0; color: {COLORS['text']}; }} "
        f"QListWidget::item:selected {{ background: rgba(10, 132, 255, 46); color: {COLORS['text']}; }} "
        f"QTabWidget::pane {{ background: {COLORS['surface']}; border: 1px solid {COLORS['separator']}; border-radius: 16px; top: -1px; }} "
        f"QTabBar::tab {{ background: {COLORS['control']}; color: {COLORS['muted']}; border: 1px solid {COLORS['separator']}; "
        "border-radius: 12px; padding: 8px 14px; margin-right: 6px; font-size: 12px; font-weight: 800; min-height: 34px; } "
        f"QTabBar::tab:selected {{ background: {COLORS['surface_alt']}; color: {COLORS['text']}; border-color: {accent}; }} "
        f"QTabBar::tab:hover:!selected {{ background: {COLORS['control_hover']}; color: {COLORS['text']}; }} "
        f"#applePopupHeroCard {{ background: {COLORS['surface_alt']}; border: 1px solid {COLORS['separator']}; border-radius: 18px; }} "
        f"#applePopupSectionCard {{ background: {COLORS['surface']}; border: 1px solid {COLORS['separator']}; border-radius: 16px; }} "
        f"#applePopupHeroEyebrow {{ color: {accent}; font-size: 11px; font-weight: 800; }} "
        f"#applePopupHeroTitle {{ color: {COLORS['text']}; font-size: 27px; font-weight: 900; }} "
        f"#applePopupHeroSubtitle {{ color: #CFD8E1; font-size: 13px; font-weight: 600; }} "
        f"#applePopupSectionTitle {{ color: {COLORS['text']}; font-size: 17px; font-weight: 900; }} "
        f"#applePopupSectionHint {{ color: {COLORS['muted']}; font-size: 12px; font-weight: 700; }} "
        f"#applePopupInfoPill {{ background: rgba(100, 210, 255, 26); border: 1px solid rgba(100, 210, 255, 71); "
        "border-radius: 11px; padding: 8px 12px; color: #D8EEFA; font-size: 12px; font-weight: 700; } "
        f"#applePopupNote {{ color: {COLORS['muted']}; font-size: 12px; font-weight: 700; }} "
        f"#applePopupPreview {{ background: {COLORS['sidebar']}; border: 1px solid {COLORS['separator']}; border-radius: 12px; }} "
    )


def apple_popup_card_style(kind: str = "surface", *, radius: int = 16) -> str:
    bg = COLORS["surface_alt"] if kind == "surface_alt" else COLORS["surface"]
    return f"background: {bg}; border: 1px solid {COLORS['separator']}; border-radius: {int(radius)}px;"


def apple_popup_color_button_style(hex_color: str) -> str:
    color = str(hex_color or "#FFFFFF")
    return (
        f"background: {color}; color: {'#0B0F13' if color.upper() in {'#FFFFFF', '#FFF1A6', '#FFD60A'} else '#F5F7FA'}; "
        f"border: 1px solid {COLORS['separator']}; border-radius: 8px; padding: 5px 8px;"
    )
