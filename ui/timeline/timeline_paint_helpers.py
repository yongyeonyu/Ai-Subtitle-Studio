from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPen, QPolygon

from core.runtime import config
from ui.timeline.timeline_constants import HANDLE_R, SEG_TOP
from ui.timeline.timeline_segment_style import speaker_segment_fill_hex, speaker_segment_text_hex


def should_paint_subtitle_segment_text(
    *,
    native_inline_active: bool,
    rect_width: int,
    dense_segment_mode: bool,
    focus_detail: bool,
) -> bool:
    if native_inline_active:
        return False
    return int(rect_width) >= 44 and (not bool(dense_segment_mode) or bool(focus_detail))


def stt_preview_selection_badge_rect(rect: QRect, badge_width: int) -> QRect:
    badge_w = max(1, int(badge_width or 1))
    return QRect(rect.right() - badge_w - 3, rect.y() + 6, badge_w, 18)


def draw_timeline_segment_handle(painter, bx, is_left, color) -> None:
    cy = SEG_TOP + 32
    w = HANDLE_R
    hw = HANDLE_R // 2
    hh = 12
    th = 4
    if is_left:
        bx += 2
        pts = QPolygon([
            QPoint(bx, cy),
            QPoint(bx + hw, cy - hh),
            QPoint(bx + hw, cy - th),
            QPoint(bx + w, cy - th),
            QPoint(bx + w, cy + th),
            QPoint(bx + hw, cy + th),
            QPoint(bx + hw, cy + hh),
        ])
    else:
        bx -= 2
        pts = QPolygon([
            QPoint(bx, cy),
            QPoint(bx - hw, cy - hh),
            QPoint(bx - hw, cy - th),
            QPoint(bx - w, cy - th),
            QPoint(bx - w, cy + th),
            QPoint(bx - hw, cy + th),
            QPoint(bx - hw, cy + hh),
        ])
    painter.setPen(QPen(QColor("#000000"), 1))
    painter.setBrush(QBrush(color))
    painter.drawPolygon(pts)
    painter.setBrush(Qt.BrushStyle.NoBrush)


def speaker_row_rects(rect: QRect, rows: list[dict] | None) -> list[tuple[dict, QRect]]:
    visible_rows = [dict(row or {}) for row in list(rows or [])[:2]]
    if not visible_rows:
        visible_rows = [{"name": "", "color": "#8E8E93"}]
    count = max(1, len(visible_rows))
    top = int(rect.y())
    height = max(1, int(rect.height()))
    out: list[tuple[dict, QRect]] = []
    for idx, row in enumerate(visible_rows):
        row_top = top + int(round(height * idx / count))
        row_bot = top + int(round(height * (idx + 1) / count))
        out.append((row, QRect(rect.x(), row_top, max(1, rect.width()), max(1, row_bot - row_top))))
    return out


def fill_speaker_rows(painter, rect: QRect, rows: list[dict] | None) -> None:
    row_rects = speaker_row_rects(rect, rows)
    painter.save()
    for row, row_rect in row_rects:
        painter.fillRect(row_rect, QColor(speaker_segment_fill_hex(str(row.get("color") or "#8E8E93"))))
    if len(row_rects) > 1:
        painter.setPen(QPen(QColor(0, 0, 0, 120), 1))
        for _row, row_rect in row_rects[:-1]:
            painter.drawLine(row_rect.left(), row_rect.bottom(), row_rect.right(), row_rect.bottom())
    painter.restore()


def draw_speaker_names(painter, rect: QRect, color: QColor, names: list[str], rows: list[dict] | None = None) -> None:
    row_entries = [dict(row or {}) for row in list(rows or [])[:2]]
    if not row_entries:
        row_entries = [
            {"name": str(name).strip(), "color": color.name()}
            for name in list(names or [])[:2]
            if str(name).strip()
        ]
    names = [str(row.get("name", "") or "").strip() for row in row_entries if str(row.get("name", "") or "").strip()]
    if not names:
        return

    visible_rows = [
        row
        for row in row_entries[:2]
        if str(row.get("name", "") or "").strip()
    ]
    visible_names = [str(row.get("name", "") or "").strip() for row in visible_rows]
    font_size = 7 if len(visible_names) > 1 else 8
    painter.save()
    painter.setFont(QFont(config.FONT, font_size, QFont.Weight.Bold))
    fm = painter.fontMetrics()
    text_pad = 7
    for row, row_rect in speaker_row_rects(rect, visible_rows):
        name = str(row.get("name", "") or "").strip()
        if not name:
            continue
        painter.setPen(QColor(speaker_segment_text_hex(str(row.get("color") or color.name()))))
        text_rect = row_rect.adjusted(text_pad, 0, -text_pad, 0)
        max_text_w = max(8, text_rect.width())
        text = fm.elidedText(name, Qt.TextElideMode.ElideRight, max_text_w)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
    painter.restore()


def hover_handle_matches(hovered, seg, edge: str) -> bool:
    if not hovered or len(hovered) < 2 or hovered[1] != edge:
        return False
    hover_seg = hovered[0]
    if hover_seg is seg:
        return True
    try:
        return (
            hover_seg.get("line") == seg.get("line")
            and abs(float(hover_seg.get("start", -1.0)) - float(seg.get("start", -2.0))) < 0.001
            and abs(float(hover_seg.get("end", -1.0)) - float(seg.get("end", -2.0))) < 0.001
        )
    except Exception:
        return False
