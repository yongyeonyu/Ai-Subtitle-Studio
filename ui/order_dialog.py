# Version: 01.00.04
"""
ui/order_dialog.py
영상 순서 편집 다이얼로그 (썸네일 + 길이 표시)
"""
import os, subprocess, tempfile
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QPixmap, QIcon
import config


class OrderDialog(QDialog):
    def __init__(self, files: list, parent=None, title="영상 순서 편집"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(580, 480)
        self.setStyleSheet(f"background-color: {config.BG}; color: {config.FG};")
        self.ordered_files = []
        self._durations = {}
        self._thumb_cache = {}

        for f in files:
            self._durations[f] = self._get_duration(f)

        self._build_ui(files)

        self._thumb_queue = list(files)
        QTimer.singleShot(100, self._load_next_thumb)

    # ── UI ──

    def _build_ui(self, files):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        info = QLabel("🎬 영상 순서를 정해주세요 (위→아래 순서로 자막 생성)")
        info.setStyleSheet(f"color: {config.FG}; font-size: 13px; font-weight: bold;")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(128, 72))
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background: {config.BG2}; color: {config.FG};
                border: 1px solid {config.BG3}; border-radius: 6px;
                font-size: 13px; padding: 4px;
            }}
            QListWidget::item {{
                padding: 6px 8px; border-bottom: 1px solid {config.BG3};
                min-height: 72px;
            }}
            QListWidget::item:selected {{
                background: #333333; border: 1px solid #4AFF80;
            }}
        """)

        for i, f in enumerate(files):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, f)
            item.setSizeHint(QSize(-1, 80))
            name = os.path.basename(f)
            dur = self._durations.get(f, 0)
            item.setText(f"  {i+1}.  {name}    ({self._fmt(dur)})")
            self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)

        # 버튼
        btn_row = QHBoxLayout()
        for text, slot in [("▲ 위로", self._move_up), ("▼ 아래로", self._move_down)]:
            b = QPushButton(text)
            b.setStyleSheet(f"background:{config.BG3};color:{config.FG};padding:8px 16px;border-radius:4px;font-weight:bold;")
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        btn_row.addStretch()
        b_rm = QPushButton("🗑️ 제거")
        b_rm.setStyleSheet("background:#882222;color:#FFF;padding:8px 16px;border-radius:4px;font-weight:bold;")
        b_rm.clicked.connect(self._remove_selected)
        btn_row.addWidget(b_rm)
        layout.addLayout(btn_row)

        # 하단
        bottom = QHBoxLayout()
        self._count_lbl = QLabel(f"총 {len(files)}개")
        self._count_lbl.setStyleSheet(f"color:{config.FG2};font-size:12px;")
        total_dur = sum(self._durations.values())
        self._total_lbl = QLabel(f"총 길이: {self._fmt(total_dur)}")
        self._total_lbl.setStyleSheet(f"color:{config.ACCENT};font-size:12px;font-weight:bold;")

        btn_cancel = QPushButton("취소")
        btn_cancel.setStyleSheet(f"background:{config.BG3};color:{config.FG};padding:8px 20px;border-radius:4px;")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("✅ 이 순서로 자막 생성")
        btn_ok.setStyleSheet(f"background:{config.ACCENT};color:#000;font-weight:bold;padding:8px 20px;border-radius:4px;")
        btn_ok.clicked.connect(self._confirm)

        bottom.addWidget(self._count_lbl)
        bottom.addWidget(self._total_lbl)
        bottom.addStretch()
        bottom.addWidget(btn_cancel)
        bottom.addWidget(btn_ok)
        layout.addLayout(bottom)

    # ── 썸네일 / 길이 ──

    def _fmt(self, sec):
        if sec <= 0: return "--:--"
        m, s = divmod(int(sec), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    def _get_duration(self, fp):
        try:
            r = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', fp],
                capture_output=True, text=True, timeout=5)
            return float(r.stdout.strip())
        except Exception:
            return 0.0

    def _extract_thumbnail(self, fp):
        audio_exts = {'.wav', '.m4a', '.mp3', '.aac', '.m2a'}
        if os.path.splitext(fp)[1].lower() in audio_exts:
            return None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            tmp_path = tmp.name
            tmp.close()
            subprocess.run(
                ['ffmpeg', '-y', '-i', fp, '-vframes', '1', '-q:v', '5',
                 '-vf', 'scale=160:-1', tmp_path],
                capture_output=True, timeout=5)
            px = QPixmap(tmp_path)
            try: os.unlink(tmp_path)
            except Exception: pass
            return px if not px.isNull() else None
        except Exception:
            return None

    def _load_next_thumb(self):
        if not self._thumb_queue:
            return
        path = self._thumb_queue.pop(0)
        px = self._extract_thumbnail(path)
        if px:
            self._thumb_cache[path] = px
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == path:
                    item.setIcon(QIcon(px))
                    break
        if self._thumb_queue:
            QTimer.singleShot(50, self._load_next_thumb)

    # ── 순서 변경 ──

    def _refresh_numbers(self):
        total_dur = 0
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            path = item.data(Qt.ItemDataRole.UserRole)
            dur = self._durations.get(path, 0)
            total_dur += dur
            item.setText(f"  {i+1}.  {os.path.basename(path)}    ({self._fmt(dur)})")
        self._count_lbl.setText(f"총 {self.list_widget.count()}개")
        self._total_lbl.setText(f"총 길이: {self._fmt(total_dur)}")

    def _move_up(self):
        r = self.list_widget.currentRow()
        if r <= 0: return
        it = self.list_widget.takeItem(r)
        self.list_widget.insertItem(r - 1, it)
        self.list_widget.setCurrentRow(r - 1)
        self._refresh_numbers()

    def _move_down(self):
        r = self.list_widget.currentRow()
        if r < 0 or r >= self.list_widget.count() - 1: return
        it = self.list_widget.takeItem(r)
        self.list_widget.insertItem(r + 1, it)
        self.list_widget.setCurrentRow(r + 1)
        self._refresh_numbers()

    def _remove_selected(self):
        r = self.list_widget.currentRow()
        if r >= 0:
            self.list_widget.takeItem(r)
            self._refresh_numbers()

    def _confirm(self):
        self.ordered_files = [
            self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.list_widget.count())
        ]
        if self.ordered_files:
            self.accept()