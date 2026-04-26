# Version: 02.03.00
# Phase: PHASE1-B
"""
Folder/file tree dialog with media selection and auto-detect exclusion marks.
"""
import os
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTreeWidget, QTreeWidgetItem, QLabel
)
from PyQt6.QtCore import Qt
import config


class FolderDialog(QDialog):
    def __init__(self, root_path, parent=None, excluded_folders=None):
        super().__init__(parent)
        self.root_path = root_path
        self.selected_files = []
        self.excluded_folders = set(os.path.normpath(p) for p in (excluded_folders or []))
        self.setWindowTitle("폴더 및 파일 선택")
        self.setMinimumSize(680, 540)
        self.setStyleSheet(f"background-color: {config.BG}; color: {config.FG};")
        self._build_ui()
        self._populate_tree()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        lbl = QLabel(f"📂 경로: {self.root_path}")
        lbl.setStyleSheet(f"color: {config.FG2}; font-weight: bold;")
        layout.addWidget(lbl)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["자동감지 제외", "폴더 / 파일"])
        self.tree.setColumnWidth(0, 96)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{ background-color: {config.BG2}; border: 1px solid {config.BG3}; }}
            QTreeWidget::item {{ padding: 4px; }}
            QTreeWidget::item:hover {{ background-color: {config.BG3}; }}
            QHeaderView::section {{ background-color: {config.BG3}; color: {config.FG}; border: none; padding: 4px; }}
        """)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree)
        btn_layout = QHBoxLayout()
        self.btn_select_all = QPushButton("전체 선택")
        self.btn_select_all.setStyleSheet("background: #444; padding: 6px; border-radius: 4px;")
        self.btn_select_all.clicked.connect(self._select_all)
        self.btn_deselect_all = QPushButton("전체 해제")
        self.btn_deselect_all.setStyleSheet("background: #444; padding: 6px; border-radius: 4px;")
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        self.btn_ok = QPushButton("선택 완료")
        self.btn_ok.setStyleSheet(f"background: {config.ACCENT}; color: #000; font-weight: bold; padding: 6px; border-radius: 4px;")
        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_cancel = QPushButton("취소")
        self.btn_cancel.setStyleSheet("background: #555; color: #FFF; font-weight: bold; padding: 6px; border-radius: 4px;")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_select_all)
        btn_layout.addWidget(self.btn_deselect_all)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def _populate_tree(self):
        valid_exts = {'.mp4', '.mov', '.wav', '.m4a', '.m2a', '.mp3', '.aac'}
        self.tree.blockSignals(True)
        def add_nodes(parent_item, current_path):
            try:
                entries = sorted(os.listdir(current_path))
            except PermissionError:
                return False
            has_valid_children = False
            for entry in entries:
                if entry.startswith('.'):
                    continue
                full_path = os.path.join(current_path, entry)
                if os.path.isdir(full_path):
                    dir_item = QTreeWidgetItem(parent_item, ["", f"📁 {entry}"])
                    dir_item.setFlags(dir_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
                    dir_item.setCheckState(1, Qt.CheckState.Unchecked)
                    dir_item.setData(0, Qt.ItemDataRole.UserRole, full_path)
                    dir_item.setData(1, Qt.ItemDataRole.UserRole, full_path)
                    self._set_exclude_widget(dir_item, full_path)
                    if add_nodes(dir_item, full_path):
                        has_valid_children = True
                    else:
                        parent_item.removeChild(dir_item)
                elif os.path.isfile(full_path) and os.path.splitext(entry)[1].lower() in valid_exts:
                    file_item = QTreeWidgetItem(parent_item, ["", f"🎬 {entry}"])
                    file_item.setFlags(file_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    file_item.setCheckState(1, Qt.CheckState.Unchecked)
                    file_item.setData(1, Qt.ItemDataRole.UserRole, full_path)
                    has_valid_children = True
            return has_valid_children
        root_item = QTreeWidgetItem(self.tree, ["", os.path.basename(self.root_path) or self.root_path])
        root_item.setFlags(root_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
        root_item.setCheckState(1, Qt.CheckState.Unchecked)
        root_item.setData(0, Qt.ItemDataRole.UserRole, self.root_path)
        root_item.setData(1, Qt.ItemDataRole.UserRole, self.root_path)
        self._set_exclude_widget(root_item, self.root_path)
        add_nodes(root_item, self.root_path)
        root_item.setExpanded(True)
        self.tree.blockSignals(False)

    def _set_exclude_widget(self, item, folder_path):
        chk = QCheckBox("제외")
        chk.setStyleSheet("QCheckBox { color: #FFFFFF; background: transparent; }")
        chk.setChecked(os.path.normpath(folder_path) in self.excluded_folders)
        self.tree.setItemWidget(item, 0, chk)

    def _on_item_changed(self, item, column):
        pass

    def _select_all(self):
        self._set_check_state_all(self.tree.invisibleRootItem(), Qt.CheckState.Checked, column=1)

    def _deselect_all(self):
        self._set_check_state_all(self.tree.invisibleRootItem(), Qt.CheckState.Unchecked, column=1)

    def _set_check_state_all(self, parent, state, column=1):
        for i in range(parent.childCount()):
            child = parent.child(i)
            try:
                child.setCheckState(column, state)
            except Exception:
                pass
            self._set_check_state_all(child, state, column=column)

    def _on_ok(self):
        self.selected_files = []
        self.excluded_folders = set()
        def collect(parent):
            for i in range(parent.childCount()):
                child = parent.child(i)
                folder_path = child.data(0, Qt.ItemDataRole.UserRole)
                if folder_path and child.childCount() > 0:
                    chk = self.tree.itemWidget(child, 0)
                    if chk is not None and chk.isChecked():
                        self.excluded_folders.add(os.path.normpath(folder_path))
                if child.childCount() == 0:
                    file_path = child.data(1, Qt.ItemDataRole.UserRole)
                    if file_path and child.checkState(1) == Qt.CheckState.Checked:
                        self.selected_files.append(file_path)
                else:
                    collect(child)
        collect(self.tree.invisibleRootItem())
        self.accept()
