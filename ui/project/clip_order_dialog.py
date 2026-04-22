# Version: 02.02.00
# Phase: PHASE1-B
"""
ui/order_dialog.py
Clip order dialog
"""
import os
import subprocess
import tempfile

from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

import config


class OrderDialog(QDialog):
    def __init__(self, files: list[str], parent=None, title="영상 순서 편집"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(580, 480)
        self.setStyleSheet(f"background-color: {config.BG}; color: {config.FG};")

        self.ordered_files: list[str] = []
        self._durations: dict[str, float] = {}
        self._thumb_cache: dict[str, QPixmap] = {}

        for file_path in files:
            self._durations[file_path] = self._get_duration(file_path)

        self._build_ui(files)

        self._thumb_queue = list(files)
        QTimer.singleShot(100, self._load_next_thumb)

    def _build_ui(self, files: list[str]):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        info = QLabel("영상 순서를 정해 주세요. 위에서 아래 순서대로 자막이 생성됩니다.")
        info.setStyleSheet(
            f"color: {config.FG}; font-size: 13px; font-weight: bold;"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(128, 72))
        self.list_widget.setStyleSheet(
            f"""
            QListWidget {{
                background: {config.BG2};
                color: {config.FG};
                border: 1px solid {config.BG3};
                border-radius: 6px;
                font-size: 13px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-bottom: 1px solid {config.BG3};
                min-height: 72px;
            }}
            QListWidget::item:selected {{
                background: #333333;
                border: 1px solid #4AFF80;
            }}
            """
        )

        for idx, file_path in enumerate(files):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, file_path)
            item.setSizeHint(QSize(-1, 80))

            name = os.path.basename(file_path)
            dur = self._durations.get(file_path, 0.0)
            item.setText(f"  {idx + 1}.  {name}    ({self._fmt(dur)})")
            self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()

        move_buttons = [
            ("위로", self._move_up),
            ("아래로", self._move_down),
        ]
        for text, slot in move_buttons:
            button = QPushButton(text)
            button.setStyleSheet(
                f"background:{config.BG3};"
                f"color:{config.FG};"
                f"padding:8px 16px;"
                f"border-radius:4px;"
                f"font-weight:bold;"
            )
            button.clicked.connect(slot)
            btn_row.addWidget(button)

        btn_row.addStretch()

        remove_btn = QPushButton("선택 제거")
        remove_btn.setStyleSheet(
            "background:#882222;color:#FFF;padding:8px 16px;border-radius:4px;font-weight:bold;"
        )
        remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(remove_btn)

        layout.addLayout(btn_row)

        bottom = QHBoxLayout()

        self._count_lbl = QLabel(f"총 {len(files)}개")
        self._count_lbl.setStyleSheet(f"color:{config.FG2};font-size:12px;")

        total_dur = sum(self._durations.values())
        self._total_lbl = QLabel(f"총 길이: {self._fmt(total_dur)}")
        self._total_lbl.setStyleSheet(
            f"color:{config.ACCENT};font-size:12px;font-weight:bold;"
        )

        cancel_btn = QPushButton("취소")
        cancel_btn.setStyleSheet(
            f"background:{config.BG3};color:{config.FG};padding:8px 20px;border-radius:4px;"
        )
        cancel_btn.clicked.connect(self.reject)

        ok_btn = QPushButton("이 순서로 자막 생성")
        ok_btn.setStyleSheet(
            f"background:{config.ACCENT};color:#000;font-weight:bold;padding:8px 20px;border-radius:4px;"
        )
        ok_btn.clicked.connect(self._confirm)

        bottom.addWidget(self._count_lbl)
        bottom.addWidget(self._total_lbl)
        bottom.addStretch()
        bottom.addWidget(cancel_btn)
        bottom.addWidget(ok_btn)

        layout.addLayout(bottom)

    def _fmt(self, sec: float) -> str:
        if sec <= 0:
            return "--:--"

        minutes, seconds = divmod(int(sec), 60)
        hours, minutes = divmod(minutes, 60)

        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _get_duration(self, file_path: str) -> float:
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    file_path,
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    def _extract_thumbnail(self, file_path: str) -> QPixmap | None:
        audio_exts = {".wav", ".m4a", ".mp3", ".aac", ".m2a"}
        if os.path.splitext(file_path)[1].lower() in audio_exts:
            return None

        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tmp_path = tmp.name
            tmp.close()

            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    file_path,
                    "-vframes",
                    "1",
                    "-q:v",
                    "5",
                    "-vf",
                    "scale=160:-1",
                    tmp_path,
                ],
                capture_output=True,
                timeout=5,
            )

            pixmap = QPixmap(tmp_path)

            try:
                os.unlink(tmp_path)
            except Exception:
                pass

            if pixmap.isNull():
                return None
            return pixmap

        except Exception:
            return None

    def _load_next_thumb(self):
        if not self._thumb_queue:
            return

        path = self._thumb_queue.pop(0)
        pixmap = self._extract_thumbnail(path)

        if pixmap:
            self._thumb_cache[path] = pixmap
            for idx in range(self.list_widget.count()):
                item = self.list_widget.item(idx)
                if item.data(Qt.ItemDataRole.UserRole) == path:
                    item.setIcon(QIcon(pixmap))
                    break

        if self._thumb_queue:
            QTimer.singleShot(50, self._load_next_thumb)

    def _refresh_numbers(self):
        total_dur = 0.0

        for idx in range(self.list_widget.count()):
            item = self.list_widget.item(idx)
            path = item.data(Qt.ItemDataRole.UserRole)
            dur = self._durations.get(path, 0.0)
            total_dur += dur
            item.setText(f"  {idx + 1}.  {os.path.basename(path)}    ({self._fmt(dur)})")

        self._count_lbl.setText(f"총 {self.list_widget.count()}개")
        self._total_lbl.setText(f"총 길이: {self._fmt(total_dur)}")

    def _move_up(self):
        row = self.list_widget.currentRow()
        if row <= 0:
            return

        item = self.list_widget.takeItem(row)
        self.list_widget.insertItem(row - 1, item)
        self.list_widget.setCurrentRow(row - 1)
        self._refresh_numbers()

    def _move_down(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= self.list_widget.count() - 1:
            return

        item = self.list_widget.takeItem(row)
        self.list_widget.insertItem(row + 1, item)
        self.list_widget.setCurrentRow(row + 1)
        self._refresh_numbers()

    def _remove_selected(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            self.list_widget.takeItem(row)
            self._refresh_numbers()

    def _confirm(self):
        self.ordered_files = [
            self.list_widget.item(idx).data(Qt.ItemDataRole.UserRole)
            for idx in range(self.list_widget.count())
        ]
        if self.ordered_files:
            self.accept()