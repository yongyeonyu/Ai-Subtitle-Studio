# Version: 03.01.08
# Phase: PHASE2
"""
Shared UI style tokens for the gradual PHASE1-C refresh.

This module centralizes low-risk button and label styles first. Layout and
behavior stay in each widget so existing signal/slot flows remain untouched.
"""

from pathlib import Path

from PyQt6.QtCore import QPointF, Qt, QRectF
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
try:
    from PyQt6.QtSvg import QSvgRenderer
except Exception:
    QSvgRenderer = None



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

_LINE_ICON_CACHE = {}
_ICON_ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "icons" / "ui"
_ICON_ALIASES = {
    "briefcase": "project",
    "document": "file",
    "done": "check",
    "gap": "sliders",
    "question": "help",
    "reload": "refresh",
    "restart": "refresh",
    "stt": "mic",
    "voice": "speaker",
    "write": "edit",
    "x": "cancel",
}


def _canonical_icon_name(name):
    icon_name = str(name)
    return _ICON_ALIASES.get(icon_name, icon_name)


def _svg_icon_from_asset(name, color, size):
    if QSvgRenderer is None:
        return None
    svg_path = _ICON_ASSET_DIR / f"{_canonical_icon_name(name)}.svg"
    if not svg_path.exists():
        return None
    try:
        svg_text = svg_path.read_text(encoding="utf-8").replace("currentColor", str(color))
        renderer = QSvgRenderer(svg_text.encode("utf-8"))
    except Exception:
        return None
    if not renderer.isValid():
        return None

    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return QIcon(pix)


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
            "border-radius: 7px; min-height: 34px; min-width: 72px; "
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
            "border-radius: 7px; min-height: 28px; min-width: 64px; "
            "} "
            "QPushButton:hover { background: #D70015; }"
        )

    font_size = font_size or "11px"
    padding = padding or "6px 10px"
    return (
        "QPushButton { "
        f"background: {COLORS['control']}; color: {COLORS['text']}; border: 1px solid {COLORS['separator']}; "
        f"padding: {padding}; font-size: {_px(font_size)}; border-radius: 7px; "
        "min-height: 28px; min-width: 64px; "
        "} "
        f"QPushButton:hover {{ background: {COLORS['control_hover']}; }}"
    )


def settings_button_style(kind="toolbar", *, font_size="12px", min_width=72, min_height=40):
    """Return equal-height QPushButton styles for settings dialogs."""
    bg = COLORS["control"]
    border = COLORS["separator"]
    color = COLORS["text"]
    hover = COLORS["control_hover"]
    if kind == "primary":
        bg = COLORS["primary"]
        border = COLORS["primary"]
        color = "#FFFFFF"
        hover = COLORS["primary_hover"]
    elif kind == "danger":
        bg = "#2D1718"
        border = "#5B2528"
        color = "#FFB1AB"
        hover = "#3A1D20"
    return (
        "QPushButton { "
        f"background: {bg}; color: {color}; border: 1px solid {border}; "
        "border-radius: 7px; padding: 0 12px; "
        f"font-size: {_px(font_size)}; font-weight: 700; "
        f"min-height: {_px(min_height)}; max-height: {_px(min_height)}; "
        f"min-width: {_px(min_width)}; "
        "} "
        f"QPushButton:hover {{ background: {hover}; border-color: #465663; }} "
        "QPushButton:disabled { color: #6F767D; background: #151A1E; border-color: #222A31; }"
    )


def tool_button_style(kind="toolbar", *, checked=False):
    bg = COLORS["surface_alt"]
    border = COLORS["separator"]
    color = COLORS["text"]
    if checked:
        bg = "#1F3A56"
        border = COLORS["primary"]
        color = "#D7EBFF"
    if kind == "primary":
        bg = COLORS["primary"]
        border = COLORS["primary"]
        color = "#FFFFFF"
    if kind == "danger":
        bg = "#2D1718"
        border = "#5B2528"
        color = "#FFB1AB"
    return (
        "QToolButton { "
        f"background: {bg}; color: {color}; border: 1px solid {border}; "
        "border-radius: 7px; padding: 6px 8px; font-size: 11px; font-weight: 600; "
        "} "
        f"QToolButton:hover {{ background: {COLORS['control_hover']}; border-color: #465663; }} "
        "QToolButton:disabled { color: #666C72; background: #151A1E; border-color: #222A31; }"
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


def named_panel_style(object_name, kind="surface", *, radius=7):
    """Return an object-name scoped panel style so child widgets keep their own styles."""
    bg = COLORS["surface"] if kind == "surface" else COLORS.get(kind, COLORS["surface_alt"])
    return (
        f"#{object_name} {{ "
        f"background: {bg}; border: 1px solid {COLORS['separator']}; "
        f"border-radius: {int(radius)}px; "
        "} "
    )


def settings_dialog_stylesheet():
    return (
        f"QDialog {{ background: {COLORS['bg']}; color: {COLORS['text']}; font-size: 13px; }}"
        f"QWidget {{ background: {COLORS['bg']}; color: {COLORS['text']}; }}"
        "QLabel { color: #DCE3EA; background: transparent; font-weight: 600; }"
        f"QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ "
        f"background: {COLORS['surface']}; color: {COLORS['text']}; "
        f"border: 1px solid {COLORS['separator']}; border-radius: 7px; "
        "padding: 7px 9px; selection-background-color: #2E75D4; "
        "}"
        f"QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ "
        f"border: 1px solid {COLORS['primary']}; "
        "}"
        f"QComboBox::drop-down {{ border: none; width: 24px; }}"
        f"QComboBox QAbstractItemView {{ background: {COLORS['surface_alt']}; color: {COLORS['text']}; "
        f"border: 1px solid {COLORS['separator']}; selection-background-color: #1F3A56; }}"
        f"QPushButton {{ background: {COLORS['control']}; color: {COLORS['text']}; "
        f"border: 1px solid {COLORS['separator']}; border-radius: 7px; "
        "padding: 6px 10px; font-weight: 700; min-height: 28px; min-width: 64px; }"
        f"QPushButton:hover {{ background: {COLORS['control_hover']}; border-color: #465663; }}"
        f"QPushButton:checked {{ background: #1F3A56; border-color: {COLORS['primary']}; color: #D7EBFF; }}"
        "QPushButton:disabled { color: #6F767D; background: #151A1E; border-color: #222A31; }"
        f"QCheckBox {{ color: {COLORS['text']}; background: transparent; spacing: 8px; }}"
        f"QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid #64717B; "
        "border-radius: 4px; background: #10161A; }"
        f"QCheckBox::indicator:checked {{ background: {COLORS['primary']}; border-color: {COLORS['primary']}; }}"
        f"QSlider::groove:horizontal {{ height: 5px; background: #2A343C; border-radius: 3px; }}"
        f"QSlider::sub-page:horizontal {{ background: {COLORS['primary']}; border-radius: 3px; }}"
        "QSlider::handle:horizontal { background: #DCE3EA; width: 14px; margin: -5px 0; border-radius: 7px; }"
        f"QTabWidget::pane {{ border: 1px solid {COLORS['separator']}; border-radius: 7px; top: -1px; "
        f"background: {COLORS['surface']}; }}"
        f"QTabBar::tab {{ background: {COLORS['control']}; color: {COLORS['muted']}; "
        f"border: 1px solid {COLORS['separator']}; border-bottom: none; padding: 8px 14px; "
        "min-height: 26px; min-width: 68px; border-top-left-radius: 7px; border-top-right-radius: 7px; }"
        f"QTabBar::tab:selected {{ background: {COLORS['surface_alt']}; color: {COLORS['text']}; "
        f"border-color: {COLORS['primary']}; }}"
        f"QTabBar::tab:hover:!selected {{ background: {COLORS['control_hover']}; color: {COLORS['text']}; }}"
        f"QGroupBox {{ border: 1px solid {COLORS['separator']}; border-radius: 7px; margin-top: 12px; "
        f"padding: 12px 8px 8px 8px; background: {COLORS['surface']}; }}"
        "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #DCE3EA; }"
        f"QScrollArea {{ background: transparent; border: none; }}"
        f"QScrollBar:vertical, QScrollBar:horizontal {{ background: #10161A; border: none; width: 8px; height: 8px; }}"
        f"QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{ background: #465663; border-radius: 4px; }}"
        "QToolTip { background: #202A31; color: #F5F7FA; border: 1px solid #3A4650; padding: 6px; }"
    )


def line_icon(name, color=None, size=28):
    """Small reusable line icons for the PHASE1-C dark UI."""
    color = color or COLORS["muted"]
    cache_key = (str(name), str(color), int(size))
    cached = _LINE_ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached

    svg_icon = _svg_icon_from_asset(name, color, size)
    if svg_icon is not None:
        _LINE_ICON_CACHE[cache_key] = svg_icon
        return svg_icon

    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), max(1.8, size / 15), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    r = QRectF(size * 0.2, size * 0.2, size * 0.6, size * 0.6)

    def draw_reference_curve_arrow(is_redo=False):
        arrow_pen = QPen(
            QColor(color),
            max(4.0, size * 0.15),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.FlatCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.setPen(arrow_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        if is_redo:
            path.moveTo(QPointF(size * 0.61, size * 0.38))
            path.cubicTo(
                QPointF(size * 0.47, size * 0.25),
                QPointF(size * 0.26, size * 0.30),
                QPointF(size * 0.22, size * 0.50),
            )
            path.cubicTo(
                QPointF(size * 0.19, size * 0.65),
                QPointF(size * 0.32, size * 0.76),
                QPointF(size * 0.50, size * 0.75),
            )
            head = QPolygonF(
                [
                    QPointF(size * 0.83, size * 0.38),
                    QPointF(size * 0.60, size * 0.23),
                    QPointF(size * 0.60, size * 0.55),
                ]
            )
        else:
            path.moveTo(QPointF(size * 0.39, size * 0.38))
            path.cubicTo(
                QPointF(size * 0.53, size * 0.25),
                QPointF(size * 0.74, size * 0.30),
                QPointF(size * 0.78, size * 0.50),
            )
            path.cubicTo(
                QPointF(size * 0.81, size * 0.65),
                QPointF(size * 0.68, size * 0.76),
                QPointF(size * 0.50, size * 0.75),
            )
            head = QPolygonF(
                [
                    QPointF(size * 0.17, size * 0.38),
                    QPointF(size * 0.40, size * 0.23),
                    QPointF(size * 0.40, size * 0.55),
                ]
            )

        painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPolygon(head)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    if name == "home":
        painter.drawLine(int(size * 0.2), int(size * 0.48), int(size * 0.5), int(size * 0.24))
        painter.drawLine(int(size * 0.5), int(size * 0.24), int(size * 0.8), int(size * 0.48))
        painter.drawRoundedRect(QRectF(size * 0.3, size * 0.46, size * 0.4, size * 0.34), 3, 3)
    elif name == "clock":
        painter.drawEllipse(r)
        painter.drawLine(int(size * 0.5), int(size * 0.5), int(size * 0.5), int(size * 0.32))
        painter.drawLine(int(size * 0.5), int(size * 0.5), int(size * 0.64), int(size * 0.58))
    elif name in ("settings", "ai"):
        painter.drawEllipse(r)
        painter.drawEllipse(QRectF(size * 0.42, size * 0.42, size * 0.16, size * 0.16))
        for dx, dy in ((0.5, 0.12), (0.5, 0.88), (0.12, 0.5), (0.88, 0.5)):
            painter.drawLine(int(size * 0.5), int(size * 0.5), int(size * dx), int(size * dy))
    elif name in ("speaker", "voice"):
        painter.drawRoundedRect(QRectF(size * 0.2, size * 0.35, size * 0.2, size * 0.3), 2, 2)
        painter.drawLine(int(size * 0.4), int(size * 0.35), int(size * 0.58), int(size * 0.24))
        painter.drawLine(int(size * 0.4), int(size * 0.65), int(size * 0.58), int(size * 0.76))
        painter.drawArc(QRectF(size * 0.52, size * 0.32, size * 0.22, size * 0.36), -45 * 16, 90 * 16)
    elif name in ("mic", "stt"):
        painter.drawRoundedRect(QRectF(size * 0.38, size * 0.18, size * 0.24, size * 0.42), 5, 5)
        painter.drawArc(QRectF(size * 0.28, size * 0.36, size * 0.44, size * 0.28), 200 * 16, 140 * 16)
        painter.drawLine(int(size * 0.5), int(size * 0.66), int(size * 0.5), int(size * 0.78))
        painter.drawLine(int(size * 0.38), int(size * 0.78), int(size * 0.62), int(size * 0.78))
    elif name in ("sliders", "gap"):
        for y, x in ((0.32, 0.38), (0.5, 0.62), (0.68, 0.48)):
            painter.drawLine(int(size * 0.18), int(size * y), int(size * 0.82), int(size * y))
            painter.drawEllipse(QRectF(size * x - 3, size * y - 3, 6, 6))
    elif name == "auto":
        painter.drawEllipse(QRectF(size * 0.22, size * 0.22, size * 0.56, size * 0.56))
        painter.drawLine(int(size * 0.50), int(size * 0.15), int(size * 0.50), int(size * 0.30))
        painter.drawLine(int(size * 0.50), int(size * 0.70), int(size * 0.50), int(size * 0.85))
        painter.drawLine(int(size * 0.15), int(size * 0.50), int(size * 0.30), int(size * 0.50))
        painter.drawLine(int(size * 0.70), int(size * 0.50), int(size * 0.85), int(size * 0.50))
        painter.drawEllipse(QRectF(size * 0.42, size * 0.42, size * 0.16, size * 0.16))
    elif name in ("timeline", "subtitle"):
        painter.drawRoundedRect(QRectF(size * 0.18, size * 0.28, size * 0.64, size * 0.44), 3, 3)
        painter.drawLine(int(size * 0.3), int(size * 0.42), int(size * 0.7), int(size * 0.42))
        painter.drawLine(int(size * 0.3), int(size * 0.56), int(size * 0.6), int(size * 0.56))
    elif name == "video":
        painter.drawRoundedRect(r, 3, 3)
        painter.drawLine(int(size * 0.46), int(size * 0.38), int(size * 0.64), int(size * 0.5))
        painter.drawLine(int(size * 0.64), int(size * 0.5), int(size * 0.46), int(size * 0.62))
        painter.drawLine(int(size * 0.46), int(size * 0.38), int(size * 0.46), int(size * 0.62))
    elif name == "play":
        painter.drawLine(int(size * 0.38), int(size * 0.28), int(size * 0.70), int(size * 0.50))
        painter.drawLine(int(size * 0.70), int(size * 0.50), int(size * 0.38), int(size * 0.72))
        painter.drawLine(int(size * 0.38), int(size * 0.28), int(size * 0.38), int(size * 0.72))
    elif name == "stop":
        painter.drawRoundedRect(QRectF(size * 0.32, size * 0.32, size * 0.36, size * 0.36), 2, 2)
    elif name in ("export", "folder"):
        painter.drawRoundedRect(QRectF(size * 0.18, size * 0.35, size * 0.64, size * 0.34), 3, 3)
        painter.drawLine(int(size * 0.28), int(size * 0.35), int(size * 0.42), int(size * 0.24))
        painter.drawLine(int(size * 0.42), int(size * 0.24), int(size * 0.58), int(size * 0.35))
        if name == "export":
            painter.drawLine(int(size * 0.5), int(size * 0.62), int(size * 0.5), int(size * 0.22))
            painter.drawLine(int(size * 0.38), int(size * 0.34), int(size * 0.5), int(size * 0.22))
            painter.drawLine(int(size * 0.62), int(size * 0.34), int(size * 0.5), int(size * 0.22))
    elif name in ("file", "document"):
        painter.drawRoundedRect(QRectF(size * 0.28, size * 0.18, size * 0.44, size * 0.64), 3, 3)
        painter.drawLine(int(size * 0.58), int(size * 0.18), int(size * 0.72), int(size * 0.32))
        painter.drawLine(int(size * 0.72), int(size * 0.32), int(size * 0.58), int(size * 0.32))
        painter.drawLine(int(size * 0.36), int(size * 0.48), int(size * 0.64), int(size * 0.48))
        painter.drawLine(int(size * 0.36), int(size * 0.60), int(size * 0.58), int(size * 0.60))
    elif name in ("cancel", "x"):
        painter.drawLine(int(size * 0.30), int(size * 0.30), int(size * 0.70), int(size * 0.70))
        painter.drawLine(int(size * 0.70), int(size * 0.30), int(size * 0.30), int(size * 0.70))
    elif name in ("refresh", "reload"):
        painter.drawArc(r, 35 * 16, 285 * 16)
        painter.drawLine(int(size * 0.70), int(size * 0.24), int(size * 0.78), int(size * 0.42))
        painter.drawLine(int(size * 0.70), int(size * 0.24), int(size * 0.52), int(size * 0.28))
    elif name == "undo":
        draw_reference_curve_arrow(is_redo=False)
    elif name == "redo":
        draw_reference_curve_arrow(is_redo=True)
    elif name == "trash":
        painter.drawLine(int(size * 0.32), int(size * 0.3), int(size * 0.68), int(size * 0.3))
        painter.drawRoundedRect(QRectF(size * 0.35, size * 0.36, size * 0.3, size * 0.4), 2, 2)
        painter.drawLine(int(size * 0.43), int(size * 0.44), int(size * 0.43), int(size * 0.68))
        painter.drawLine(int(size * 0.57), int(size * 0.44), int(size * 0.57), int(size * 0.68))
    elif name == "terminal":
        painter.drawRoundedRect(r, 3, 3)
        painter.drawLine(int(size * 0.32), int(size * 0.43), int(size * 0.43), int(size * 0.5))
        painter.drawLine(int(size * 0.43), int(size * 0.5), int(size * 0.32), int(size * 0.57))
        painter.drawLine(int(size * 0.5), int(size * 0.6), int(size * 0.68), int(size * 0.6))
    elif name in ("help", "question"):
        painter.drawEllipse(r)
        painter.setFont(QFont("Arial", max(10, int(size * 0.48)), QFont.Weight.Bold))
        painter.drawText(QRectF(0, size * 0.12, size, size * 0.74), Qt.AlignmentFlag.AlignCenter, "?")
    elif name == "power":
        power_pen = QPen(
            QColor(color),
            max(4.2, size * 0.16),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.setPen(power_pen)
        painter.drawArc(QRectF(size * 0.24, size * 0.27, size * 0.52, size * 0.54), 130 * 16, 280 * 16)
        painter.drawLine(int(size * 0.5), int(size * 0.15), int(size * 0.5), int(size * 0.43))
        painter.setPen(pen)
    elif name == "review":
        painter.drawEllipse(QRectF(size * 0.22, size * 0.30, size * 0.56, size * 0.38))
        painter.drawEllipse(QRectF(size * 0.43, size * 0.43, size * 0.14, size * 0.14))
    elif name == "llm":
        painter.drawRoundedRect(QRectF(size * 0.24, size * 0.24, size * 0.52, size * 0.52), 5, 5)
        painter.drawEllipse(QRectF(size * 0.36, size * 0.36, size * 0.08, size * 0.08))
        painter.drawEllipse(QRectF(size * 0.56, size * 0.36, size * 0.08, size * 0.08))
        painter.drawLine(int(size * 0.38), int(size * 0.60), int(size * 0.62), int(size * 0.60))
    elif name == "roughcut":
        painter.drawRoundedRect(QRectF(size * 0.20, size * 0.30, size * 0.60, size * 0.40), 3, 3)
        painter.drawLine(int(size * 0.32), int(size * 0.28), int(size * 0.32), int(size * 0.72))
        painter.drawLine(int(size * 0.50), int(size * 0.28), int(size * 0.50), int(size * 0.72))
        painter.drawLine(int(size * 0.68), int(size * 0.28), int(size * 0.68), int(size * 0.72))
    elif name == "shortform":
        painter.drawRoundedRect(QRectF(size * 0.34, size * 0.18, size * 0.32, size * 0.64), 4, 4)
        painter.drawLine(int(size * 0.43), int(size * 0.68), int(size * 0.57), int(size * 0.68))
    elif name in ("prev", "next"):
        x1, x2 = (0.65, 0.35) if name == "prev" else (0.35, 0.65)
        painter.drawLine(int(size * x1), int(size * 0.25), int(size * x2), int(size * 0.5))
        painter.drawLine(int(size * x2), int(size * 0.5), int(size * x1), int(size * 0.75))
        painter.drawLine(int(size * (x1 + (0.16 if name == "prev" else -0.16))), int(size * 0.25), int(size * (x2 + (0.16 if name == "prev" else -0.16))), int(size * 0.5))
        painter.drawLine(int(size * (x2 + (0.16 if name == "prev" else -0.16))), int(size * 0.5), int(size * (x1 + (0.16 if name == "prev" else -0.16))), int(size * 0.75))
    elif name == "restart":
        painter.drawArc(r, 30 * 16, 290 * 16)
        painter.drawLine(int(size * 0.28), int(size * 0.34), int(size * 0.2), int(size * 0.2))
        painter.drawLine(int(size * 0.28), int(size * 0.34), int(size * 0.44), int(size * 0.32))
    elif name == "save":
        painter.drawRoundedRect(r, 3, 3)
        painter.drawLine(int(size * 0.32), int(size * 0.24), int(size * 0.68), int(size * 0.24))
        painter.drawRoundedRect(QRectF(size * 0.34, size * 0.54, size * 0.32, size * 0.18), 2, 2)
    elif name in ("edit", "write"):
        painter.drawLine(int(size * 0.30), int(size * 0.70), int(size * 0.66), int(size * 0.34))
        painter.drawLine(int(size * 0.58), int(size * 0.26), int(size * 0.74), int(size * 0.42))
        painter.drawLine(int(size * 0.66), int(size * 0.34), int(size * 0.74), int(size * 0.42))
        painter.drawLine(int(size * 0.26), int(size * 0.74), int(size * 0.38), int(size * 0.70))
    elif name in ("check", "done"):
        painter.drawLine(int(size * 0.24), int(size * 0.52), int(size * 0.43), int(size * 0.70))
        painter.drawLine(int(size * 0.43), int(size * 0.70), int(size * 0.78), int(size * 0.32))
    elif name == "search":
        painter.drawEllipse(QRectF(size * 0.24, size * 0.24, size * 0.36, size * 0.36))
        painter.drawLine(int(size * 0.56), int(size * 0.56), int(size * 0.76), int(size * 0.76))
    elif name == "more":
        for x in (0.32, 0.5, 0.68):
            painter.drawEllipse(QRectF(size * x - 2, size * 0.5 - 2, 4, 4))
    elif name == "home":
        painter.drawLine(int(size * 0.2), int(size * 0.48), int(size * 0.5), int(size * 0.22))
        painter.drawLine(int(size * 0.5), int(size * 0.22), int(size * 0.8), int(size * 0.48))
        painter.drawRoundedRect(QRectF(size * 0.3, size * 0.48, size * 0.4, size * 0.3), 2, 2)
    elif name in ("project", "briefcase"):
        painter.drawRoundedRect(QRectF(size * 0.2, size * 0.34, size * 0.6, size * 0.4), 3, 3)
        painter.drawRoundedRect(QRectF(size * 0.38, size * 0.24, size * 0.24, size * 0.14), 2, 2)
    else:
        painter.drawRoundedRect(r, 4, 4)

    painter.end()
    icon = QIcon(pix)
    _LINE_ICON_CACHE[cache_key] = icon
    return icon


def app_stylesheet():
    return (
        f"QWidget {{ background: {COLORS['bg']}; color: {COLORS['text']}; }}"
        "QToolTip { background: #202A31; color: #F5F7FA; border: 1px solid #3A4650; padding: 5px; }"
        f"QTextEdit {{ background: {COLORS['surface']}; color: {COLORS['text']}; border: none; }}"
        f"QScrollArea {{ background: transparent; border: none; }}"
        f"QTableWidget {{ background: {COLORS['surface']}; color: {COLORS['text']}; border: none; gridline-color: {COLORS['separator']}; }}"
        f"QHeaderView::section {{ background: {COLORS['surface_alt']}; color: {COLORS['muted']}; border: none; padding: 8px; }}"
    )
