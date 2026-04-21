# Version: 02.03.00
# Phase: PHASE1-B
"""
ui/multiclip_editor.py
멀티 클립 정렬 에디터 — 가로 썸네일 카드 + 드래그&드롭 순서 변경
"""
import os
import subprocess
import json
import tempfile
from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QApplication, QFileDialog, QMenu
)
from PyQt6.QtCore import Qt, QMimeData, QPoint, pyqtSignal
from PyQt6.QtGui import QPixmap, QDrag, QPainter, QFont, QColor, QAction

import config
from core.path_manager import get_last_folder


class ClipCard(QFrame):
    """개별 클립 썸네일 카드"""

    def __init__(self, file_path, index, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.index = index
        self.setFixedSize(200, 160)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._selected = False
        self._extract_info()
        self._extract_thumbnail()

    def _extract_info(self):
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", self.file_path],
                capture_output=True, text=True, timeout=10, encoding="utf-8"
            )
            info = json.loads(result.stdout)
            duration = float(info.get("format", {}).get("duration", 0))
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
        self.thumbnail = None
        try:
            tmp = os.path.join(tempfile.gettempdir(), f"mc_thumb_{abs(hash(self.file_path))}.jpg")
            subprocess.run(
                ["ffmpeg", "-y", "-nostdin", "-loglevel", "error",
                 "-i", self.file_path, "-vframes", "1",
                 "-vf", "scale=192:108:force_original_aspect_ratio=decrease,pad=192:108:-1:-1:color=black",
                 tmp],
                capture_output=True, timeout=10
            )
            if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                self.thumbnail = QPixmap(tmp)
                try: os.remove(tmp)
                except: pass
        except Exception:
            pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        border_color = "#4AFF80" if self._selected else "#555555"
        painter.setPen(QColor(border_color))
        painter.setBrush(QColor("#2A2A2A"))
        painter.drawRoundedRect(1, 1, w - 2, h - 2, 6, 6)

        thumb_y = 4
        if self.thumbnail and not self.thumbnail.isNull():
            tx = (w - self.thumbnail.width()) // 2
            painter.drawPixmap(tx, thumb_y, self.thumbnail)
        else:
            painter.fillRect(4, thumb_y, w - 8, 108, QColor("#1a1a1a"))
            painter.setPen(QColor("#666666"))
            painter.drawText(4, thumb_y, w - 8, 108, Qt.AlignmentFlag.AlignCenter, "No Preview")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 180))
        painter.drawRoundedRect(6, 6, 30, 22, 4, 4)
        painter.setPen(QColor("#4AFF80"))
        painter.setFont(QFont("", 11, QFont.Weight.Bold))
        painter.drawText(6, 6, 30, 22, Qt.AlignmentFlag.AlignCenter, str(self.index))

        painter.setFont(QFont("", 9))
        fm = painter.fontMetrics()
        date_w = fm.horizontalAdvance(self.date_str) + 10
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 180))
        painter.drawRoundedRect(w - date_w - 6, 6, date_w, 22, 4, 4)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(w - date_w - 6, 6, date_w, 22, Qt.AlignmentFlag.AlignCenter, self.date_str)

        painter.setFont(QFont("", 10, QFont.Weight.Bold))
        fm = painter.fontMetrics()
        dur_w = fm.horizontalAdvance(self.duration_str) + 10
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 180))
        painter.drawRoundedRect(w - dur_w - 6, 108 - 18, dur_w, 22, 4, 4)
        painter.setPen(QColor("#FFD700"))
        painter.drawText(w - dur_w - 6, 108 - 18, dur_w, 22, Qt.AlignmentFlag.AlignCenter, self.duration_str)

        name = os.path.splitext(os.path.basename(self.file_path))[0]
        painter.setPen(QColor("#CCCCCC"))
        painter.setFont(QFont("", 9))
        elided = painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideMiddle, w - 16)
        painter.drawText(8, 116, w - 16, 40, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, elided)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not hasattr(self, '_drag_start'):
            return
        if (event.pos() - self._drag_start).manhattanLength() < QApplication.startDragDistance():
            return
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(str(self.index - 1))
        drag.setMimeData(mime)
        drag.setPixmap(self.grab().scaled(160, 128, Qt.AspectRatioMode.KeepAspectRatio))
        drag.setHotSpot(QPoint(80, 64))
        drag.exec(Qt.DropAction.MoveAction)
        self.setCursor(Qt.CursorShape.OpenHandCursor)


class AddCard(QFrame):
    """[+] 클립 추가 카드"""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(200, 160)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        painter.setPen(QColor("#555555"))
        painter.setBrush(QColor("#1a1a1a"))
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
    """드래그&드롭 가능한 카드 컨테이너"""
    order_changed = pyqtSignal()

    def __init__(self, parent_dlg):
        super().__init__()
        self.parent_dlg = parent_dlg
        self.setAcceptDrops(True)
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
            card_center = card.pos().x() + card.width() // 2
            if x < card_center:
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

        fp = self.parent_dlg.sorted_files.pop(src_idx)
        self.parent_dlg.sorted_files.insert(dst_idx, fp)
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

        painter.drawPolygon([
            QPoint(x - 6, y_top),
            QPoint(x + 6, y_top),
            QPoint(x, y_top + 8)
        ])

        painter.fillRect(x - 2, y_top + 8, 4, y_bot - y_top - 16, QColor("#4AFF80"))

        painter.drawPolygon([
            QPoint(x - 6, y_bot),
            QPoint(x + 6, y_bot),
            QPoint(x, y_bot - 8)
        ])

        painter.end()


class MultiClipEditor(QDialog):
    """멀티 클립 정렬 에디터 다이얼로그"""

    def __init__(self, file_paths, parent=None, reorder_only=False, show_multiclip=True):
        super().__init__(parent)
        self.setWindowTitle("🎬 멀티 클립 정렬")
        self.setMinimumWidth(850)
        self.setStyleSheet("""
            QDialog { background-color: #121212; color: #FFFFFF; }
            QLabel { color: #FFFFFF; background: transparent; }
        """)

        self.sorted_files = sorted(file_paths, key=lambda p: os.path.basename(p).lower())
        self.cards = []
        self.selected_mode = "fast"
        self._reorder_only = reorder_only
        self._add_card = None
        self._reorder_only = reorder_only
        self._show_multiclip_btn = show_multiclip
        self._add_card = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        self.header_lbl = QLabel(f"<b style='font-size: 15px;'>🎬 멀티 클립 정렬</b>  —  {len(self.sorted_files)}개 클립  |  드래그로 순서 변경")
        header.addWidget(self.header_lbl)
        header.addStretch()

        btn_name = QPushButton("📁 이름순")
        btn_name.setStyleSheet("background:#333; color:#FFF; padding:6px 14px; border-radius:4px; font-weight:bold;")
        btn_name.clicked.connect(self._sort_by_name)

        btn_date = QPushButton("📅 날짜순")
        btn_date.setStyleSheet("background:#333; color:#FFF; padding:6px 14px; border-radius:4px; font-weight:bold;")
        btn_date.clicked.connect(self._sort_by_date)

        header.addWidget(btn_name)
        header.addWidget(btn_date)
        layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(200)
        self.scroll.setStyleSheet("QScrollArea { border: 1px solid #333; background: #1a1a1a; border-radius: 6px; }")

        self.container = ClipContainer(self)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("취소")
        btn_cancel.setStyleSheet("background:#444; color:#FFF; padding:8px 24px; font-weight:bold; border-radius:4px;")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        if self._reorder_only:
            btn_ok = QPushButton(f"✅ 확인 ({len(self.sorted_files)}개)")
            btn_ok.setStyleSheet("background:#4AFF80; color:#000; padding:8px 24px; font-weight:bold; border-radius:4px;")
            btn_ok.clicked.connect(self.accept)
            btn_layout.addWidget(btn_ok)
        else:
            btn_fast = QPushButton(f"⚡ 빠른모드 ({len(self.sorted_files)}개)")
            btn_fast.setStyleSheet("background:#FFD700; color:#000; padding:8px 24px; font-weight:bold; border-radius:4px;")
            btn_fast.clicked.connect(self._accept_fast)

            btn_quality = QPushButton(f"🧠 품질모드 ({len(self.sorted_files)}개)")
            btn_quality.setStyleSheet("background:#4AFF80; color:#000; padding:8px 24px; font-weight:bold; border-radius:4px;")
            btn_quality.clicked.connect(self._accept_quality)

            btn_multiclip = QPushButton(f"🎬 멀티클립 편집 ({len(self.sorted_files)}개)")
            btn_multiclip.setStyleSheet("background:#4fc3f7; color:#000; padding:8px 24px; font-weight:bold; border-radius:4px;")
            btn_multiclip.clicked.connect(self._accept_multiclip)

            btn_layout.addWidget(btn_fast)
            btn_layout.addWidget(btn_quality)
            if getattr(self, '_show_multiclip_btn', True):
                btn_layout.addWidget(btn_multiclip)

        layout.addLayout(btn_layout)
        self._rebuild_cards()

    def _rebuild_cards(self):
        existing = {card.file_path: card for card in self.cards}

        while self.container.layout.count():
            self.container.layout.takeAt(0)

        new_cards = []
        for i, fp in enumerate(self.sorted_files):
            if fp in existing:
                card = existing.pop(fp)
                card.index = i + 1
                card.update()
            else:
                card = ClipCard(fp, i + 1, self.container)
            new_cards.append(card)
            self.container.layout.addWidget(card)

        for card in existing.values():
            card.deleteLater()
        self.cards = new_cards

        # [+] 추가 카드
        if self._add_card:
            self._add_card.deleteLater()
        self._add_card = AddCard(self.container)
        self._add_card.clicked.connect(self._on_add_clip)
        self.container.layout.addWidget(self._add_card)

        self.container.layout.addStretch()

        # 헤더 갱신
        self.header_lbl.setText(f"<b style='font-size: 15px;'>🎬 멀티 클립 정렬</b>  —  {len(self.sorted_files)}개 클립  |  드래그로 순서 변경")

    def _on_add_clip(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "클립 추가", get_last_folder() or os.path.expanduser("~"),
            "Media Files (*.mp4 *.mov *.MOV *.MP4 *.wav *.m4a *.m2a *.mp3 *.aac)"
        )
        if not paths:
            return
        for p in paths:
            if p not in self.sorted_files:
                self.sorted_files.append(p)
        self._rebuild_cards()

    def _sort_by_name(self):
        self.sorted_files.sort(key=lambda p: os.path.basename(p).lower())
        self._rebuild_cards()

    def _sort_by_date(self):
        self.sorted_files.sort(key=lambda p: os.path.getmtime(p))
        self._rebuild_cards()

    def _accept_fast(self):
        self.selected_mode = "fast"
        self.accept()

    def _accept_quality(self):
        self.selected_mode = "quality"
        self.accept()

    def _accept_multiclip(self):
        self.selected_mode = "multiclip"
        self.accept()