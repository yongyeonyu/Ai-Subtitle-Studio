# Version: 03.01.37
# Phase: PHASE1-B
"""
ui/project/multiclip_panel.py
Multi-clip sorting editor
"""
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
)

import config
from core.path_manager import get_last_folder
from ui.project.multiclip_cards import AddCard, ClipCard, ClipContainer


MEDIA_FILTER = "Media Files (*.mp4 *.mov *.MOV *.MP4 *.wav *.m4a *.m2a *.mp3 *.aac *.lrf)"


class MultiClipEditor(QDialog):
    def __init__(self, file_paths, parent=None, reorder_only=False, show_multiclip=True):
        super().__init__(parent)

        self.setWindowTitle("멀티 클립 정렬")
        self.setMinimumWidth(1050)
        self.setStyleSheet(
            """
            QDialog { background-color: #121212; color: #FFFFFF; }
            QLabel { color: #FFFFFF; background: transparent; }
            """
        )

        self.sorted_files = sorted(file_paths, key=lambda p: os.path.basename(p).lower())
        self.cards = []
        self.selected_mode = "fast"
        self._reorder_only = reorder_only
        self._show_multiclip_btn = show_multiclip
        self._add_card = None

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        header = QHBoxLayout()

        self.header_lbl = QLabel(
            f"<b style='font-size: 15px;'>멀티 클립 정렬</b>  —  {len(self.sorted_files)}개 클립  |  드래그로 순서 변경"
        )
        header.addWidget(self.header_lbl)
        header.addStretch()

        btn_name = QPushButton("이름순")
        btn_name.setStyleSheet(
            "background:#333; color:#FFF; padding:6px 14px; border-radius:4px; font-weight:bold;"
        )
        btn_name.clicked.connect(self._sort_by_name)

        btn_date = QPushButton("날짜순")
        btn_date.setStyleSheet(
            "background:#333; color:#FFF; padding:6px 14px; border-radius:4px; font-weight:bold;"
        )
        btn_date.clicked.connect(self._sort_by_date)

        header.addWidget(btn_name)
        header.addWidget(btn_date)
        layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(240)
        self.scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #333; background: #1a1a1a; border-radius: 6px; }"
        )

        self.container = ClipContainer(self)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("취소")
        btn_cancel.setStyleSheet(
            "background:#444; color:#FFF; padding:8px 24px; font-weight:bold; border-radius:4px;"
        )
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        if self._reorder_only:
            btn_ok = QPushButton("확인")
            btn_ok.setStyleSheet(
                "background:#4AFF80; color:#000; padding:8px 24px; font-weight:bold; border-radius:4px;"
            )
            btn_ok.clicked.connect(self.accept)
            btn_layout.addWidget(btn_ok)
        else:
            btn_fast = QPushButton("빠른모드")
            btn_fast.setStyleSheet(
                "background:#FFD700; color:#000; padding:8px 24px; font-weight:bold; border-radius:4px;"
            )
            btn_fast.clicked.connect(self._accept_fast)

            btn_quality = QPushButton("품질모드")
            btn_quality.setStyleSheet(
                "background:#4AFF80; color:#000; padding:8px 24px; font-weight:bold; border-radius:4px;"
            )
            btn_quality.clicked.connect(self._accept_quality)

            btn_multiclip = QPushButton("멀티클립 편집")
            btn_multiclip.setStyleSheet(
                "background:#4FC3F7; color:#000; padding:8px 24px; font-weight:bold; border-radius:4px;"
            )
            btn_multiclip.clicked.connect(self._accept_multiclip)

            btn_layout.addWidget(btn_fast)
            btn_layout.addWidget(btn_quality)

            if self._show_multiclip_btn:
                btn_layout.addWidget(btn_multiclip)

        layout.addLayout(btn_layout)
        self._rebuild_cards()

    def _remove_clip(self, idx):
        if idx < 0 or idx >= len(self.sorted_files):
            return
        self.sorted_files.pop(idx)
        self._rebuild_cards()

    def _rebuild_cards(self):
        existing = {card.file_path: card for card in self.cards}

        while self.container.layout.count():
            self.container.layout.takeAt(0)

        new_cards = []
        for i, file_path in enumerate(self.sorted_files):
            if file_path in existing:
                card = existing.pop(file_path)
                card.index = i + 1
                card.update()
            else:
                card = ClipCard(file_path, i + 1, self.container)
                card.remove_clicked.connect(self._remove_clip)

            new_cards.append(card)
            self.container.layout.addWidget(card)

        for card in existing.values():
            card.deleteLater()

        self.cards = new_cards

        if self._add_card:
            self._add_card.deleteLater()

        self._add_card = AddCard(self.container)
        self._add_card.clicked.connect(self._on_add_clip)
        self.container.layout.addWidget(self._add_card)
        self.container.layout.addStretch()

        self.header_lbl.setText(
            f"<b style='font-size: 15px;'>멀티 클립 정렬</b>  —  {len(self.sorted_files)}개 클립  |  드래그로 순서 변경"
        )

    def _on_add_clip(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "클립 추가",
            get_last_folder() or os.path.expanduser("~"),
            MEDIA_FILTER,
        )
        if not paths:
            return

        for path in paths:
            if path not in self.sorted_files:
                self.sorted_files.append(path)

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
