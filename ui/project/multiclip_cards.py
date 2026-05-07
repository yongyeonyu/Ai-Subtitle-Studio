"""
Reusable widgets for the multi-clip editor.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import datetime

from PyQt6.QtCore import QPoint, QRect, QMimeData, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDrag, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QWidget

from core.media_info import probe_media
from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs
from ui.gpu_rendering import configure_lightweight_paint


class ClipCard(QFrame):
    remove_clicked = pyqtSignal(int)

    def __init__(self, file_path, index, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.index = index
        self._selected = False
        self.thumbnail = None
        self.duration_str = "?"
        self.date_str = "?"
        self._delete_rect = QRect()
        self.setFixedSize(240, 206)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        configure_lightweight_paint(self, opaque=True)
        self._extract_info()
        self._extract_thumbnail()

    def _extract_info(self):
        try:
            info = probe_media(self.file_path)
            duration = float(info.get("duration", 0.0) or 0.0)
            mins, secs = divmod(int(duration), 60)
            hours, mins = divmod(mins, 60)
            self.duration_str = f"{hours}:{mins:02d}:{secs:02d}" if hours else f"{mins}:{secs:02d}"
        except Exception:
            self.duration_str = "?"
        try:
            mtime = os.path.getmtime(self.file_path)
            self.date_str = datetime.fromtimestamp(mtime).strftime("%y/%m/%d %H:%M:%S")
        except Exception:
            self.date_str = "?"

    def _extract_thumbnail(self):
        try:
            tmp = os.path.join(tempfile.gettempdir(), f"mc_thumb_{abs(hash(self.file_path))}.jpg")
            subprocess.run(
                [
                    ffmpeg_binary(),
                    "-y",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-i",
                    self.file_path,
                    "-vframes",
                    "1",
                    "-vf",
                    "scale=224:126:force_original_aspect_ratio=decrease,pad=224:126:-1:-1:color=black",
                    tmp,
                ],
                capture_output=True,
                timeout=10,
                **hidden_subprocess_kwargs(),
            )
            if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                pixmap = QPixmap(tmp)
                if not pixmap.isNull():
                    self.thumbnail = pixmap
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
        except Exception:
            self.thumbnail = None

    def release_resources(self):
        self.thumbnail = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        painter.setPen(QColor("#4AFF80" if self._selected else "#555555"))
        painter.setBrush(QColor("#2A2A2A"))
        painter.drawRoundedRect(1, 1, w - 2, h - 2, 6, 6)

        thumb_y = 4
        thumb_h = 126
        if self.thumbnail and not self.thumbnail.isNull():
            tx = (w - self.thumbnail.width()) // 2
            painter.drawPixmap(tx, thumb_y, self.thumbnail)
        else:
            painter.fillRect(4, thumb_y, w - 8, thumb_h, QColor("#1A1A1A"))
            painter.setPen(QColor("#666666"))
            painter.setFont(QFont("", 11))
            painter.drawText(4, thumb_y, w - 8, thumb_h, Qt.AlignmentFlag.AlignCenter, "No Preview")

        painter.setFont(QFont("", 11, QFont.Weight.Bold))
        x_text = "[X]"
        x_w = painter.fontMetrics().horizontalAdvance(x_text) + 12
        num_w = 32
        self._delete_rect = QRect(6, 6, x_w, 24)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#661111"))
        painter.drawRoundedRect(self._delete_rect, 4, 4)
        painter.setPen(QColor("#FF8080"))
        painter.drawText(self._delete_rect, Qt.AlignmentFlag.AlignCenter, x_text)
        num_x = 6 + x_w + 4
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 200))
        painter.drawRoundedRect(num_x, 6, num_w, 24, 4, 4)
        painter.setPen(QColor("#4AFF80"))
        painter.setFont(QFont("", 13, QFont.Weight.Bold))
        painter.drawText(num_x, 6, num_w, 24, Qt.AlignmentFlag.AlignCenter, str(self.index))

        painter.setFont(QFont("", 10, QFont.Weight.Bold))
        date_w = painter.fontMetrics().horizontalAdvance(self.date_str) + 12
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 210))
        painter.drawRoundedRect(w - date_w - 6, 6, date_w, 24, 4, 4)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(w - date_w - 6, 6, date_w, 24, Qt.AlignmentFlag.AlignCenter, self.date_str)

        painter.setFont(QFont("", 12, QFont.Weight.Bold))
        dur_w = painter.fontMetrics().horizontalAdvance(self.duration_str) + 14
        panel_x = w - dur_w - 6
        panel_y = thumb_y + thumb_h - 26
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 210))
        painter.drawRoundedRect(panel_x, panel_y, dur_w, 24, 4, 4)
        painter.setPen(QColor("#FFD700"))
        painter.drawText(panel_x, panel_y, dur_w, 24, Qt.AlignmentFlag.AlignCenter, self.duration_str)

        name = os.path.splitext(os.path.basename(self.file_path))[0]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 160))
        painter.drawRoundedRect(4, thumb_y + thumb_h + 2, w - 8, 44, 3, 3)
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("", 9, QFont.Weight.Bold))
        painter.drawText(
            8,
            thumb_y + thumb_h + 4,
            w - 16,
            40,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            name,
        )
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._delete_rect.contains(event.pos()):
                self.remove_clicked.emit(self.index - 1)
                event.accept()
                return
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.pos() - getattr(self, "_drag_start_pos", event.pos())).manhattanLength() < QApplication.startDragDistance():
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(str(self.index - 1))
        drag.setMimeData(mime)
        drag.setHotSpot(event.pos())
        drag.exec(Qt.DropAction.MoveAction)


class AddCard(QFrame):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(240, 190)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        configure_lightweight_paint(self, opaque=True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        painter.setPen(QColor("#555555"))
        painter.setBrush(QColor("#1A1A1A"))
        pen = painter.pen()
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawRoundedRect(2, 2, w - 4, h - 4, 6, 6)
        painter.setPen(QColor("#4AFF80"))
        painter.setFont(QFont("", 36, QFont.Weight.Bold))
        painter.drawText(0, 0, w, h - 20, Qt.AlignmentFlag.AlignCenter, "+")
        painter.setFont(QFont("", 10))
        painter.setPen(QColor("#888888"))
        painter.drawText(0, h - 40, w, 30, Qt.AlignmentFlag.AlignCenter, "클립 추가")
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class ClipContainer(QWidget):
    order_changed = pyqtSignal()

    def __init__(self, parent_dlg):
        super().__init__()
        self.parent_dlg = parent_dlg
        self.setAcceptDrops(True)
        configure_lightweight_paint(self, opaque=True)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(4, 8, 8, 8)
        self.layout.setSpacing(6)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._drop_indicator_idx = -1

    def _calc_drop_index(self, x):
        cards = self.parent_dlg.cards
        if not cards:
            return 0
        for i, card in enumerate(cards):
            if x < card.pos().x() + (card.width() // 2):
                return i
        return len(cards)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        new_idx = self._calc_drop_index(event.position().x())
        if new_idx != self._drop_indicator_idx:
            self._drop_indicator_idx = new_idx
            self.update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._drop_indicator_idx = -1
        self.update()

    def dropEvent(self, event):
        self._drop_indicator_idx = -1
        self.update()
        if not event.mimeData().hasText():
            return
        src_idx = int(event.mimeData().text())
        dst_idx = self._calc_drop_index(event.position().x())
        if dst_idx > src_idx:
            dst_idx -= 1
        if src_idx == dst_idx:
            event.acceptProposedAction()
            return
        file_path = self.parent_dlg.sorted_files.pop(src_idx)
        self.parent_dlg.sorted_files.insert(dst_idx, file_path)
        self.parent_dlg._rebuild_cards()
        event.acceptProposedAction()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drop_indicator_idx < 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cards = self.parent_dlg.cards
        if not cards:
            painter.end()
            return
        if self._drop_indicator_idx < len(cards):
            x = cards[self._drop_indicator_idx].pos().x() - 3
        else:
            last = cards[-1]
            x = last.pos().x() + last.width() + 3
        y_top = 4
        y_bot = self.height() - 4
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#4AFF80"))
        painter.drawPolygon([QPoint(x - 6, y_top), QPoint(x + 6, y_top), QPoint(x, y_top + 8)])
        painter.fillRect(x - 2, y_top + 8, 4, y_bot - y_top - 16, QColor("#4AFF80"))
        painter.drawPolygon([QPoint(x - 6, y_bot), QPoint(x + 6, y_bot), QPoint(x, y_bot - 8)])
        painter.end()
