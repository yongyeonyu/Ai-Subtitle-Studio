# Version: 02.03.03
# Phase: PHASE1-B
"""
Folder/file tree dialog with media selection and auto-detect exclusion marks.
"""
import os
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTreeWidget, QTreeWidgetItem, QLabel,
    QMessageBox
)
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtCore import Qt
import config


class FolderDialog(QDialog):
    def __init__(self, root_path, parent=None, excluded_folders=None):
        super().__init__(parent)
        self.root_path = root_path
        self.selected_files = []
        self.saved_only = False
        self.excluded_folders = set(os.path.normpath(p) for p in (excluded_folders or []))
        self._syncing_checks = False
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
        self.btn_auto_select_all = QPushButton("자동감지 전체 선택")
        self.btn_auto_select_all.setToolTip("모든 폴더를 NAS 자동감지 대상에 포함합니다.")
        self.btn_auto_select_all.setStyleSheet("background: #444; padding: 6px; border-radius: 4px;")
        self.btn_auto_select_all.clicked.connect(lambda: self._set_auto_detect_all(True))
        self.btn_auto_deselect_all = QPushButton("자동감지 전체 해제")
        self.btn_auto_deselect_all.setToolTip("모든 폴더를 NAS 자동감지 대상에서 제외합니다.")
        self.btn_auto_deselect_all.setStyleSheet("background: #444; padding: 6px; border-radius: 4px;")
        self.btn_auto_deselect_all.clicked.connect(lambda: self._set_auto_detect_all(False))
        self.btn_select_all = QPushButton("폴더 전체 선택")
        self.btn_select_all.setStyleSheet("background: #444; padding: 6px; border-radius: 4px;")
        self.btn_select_all.clicked.connect(self._select_all)
        self.btn_deselect_all = QPushButton("폴더 전체 해제")
        self.btn_deselect_all.setStyleSheet("background: #444; padding: 6px; border-radius: 4px;")
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        self.btn_ok = QPushButton("선택 완료")
        self.btn_ok.setStyleSheet(f"background: {config.ACCENT}; color: #000; font-weight: bold; padding: 6px; border-radius: 4px;")
        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_save = QPushButton("저장")
        self.btn_save.setStyleSheet("background: #2F6FED; color: #FFF; font-weight: bold; padding: 6px; border-radius: 4px;")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel = QPushButton("취소")
        self.btn_cancel.setStyleSheet("background: #555; color: #FFF; font-weight: bold; padding: 6px; border-radius: 4px;")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_auto_select_all)
        btn_layout.addWidget(self.btn_auto_deselect_all)
        btn_layout.addWidget(self.btn_select_all)
        btn_layout.addWidget(self.btn_deselect_all)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_save)
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
        self._refresh_disabled_styles()

    def _set_exclude_widget(self, item, folder_path):
        chk = QCheckBox("제외")
        chk.setStyleSheet("QCheckBox { color: #FFFFFF; background: transparent; }")
        chk.setChecked(os.path.normpath(folder_path) in self.excluded_folders)
        self.tree.setItemWidget(item, 0, chk)
        chk.stateChanged.connect(lambda _state, item=item: self._on_exclude_changed(item))

    def _on_item_changed(self, item, column):
        if self._syncing_checks or column != 1:
            return
        self._syncing_checks = True
        try:
            self._set_descendant_selection_state(item, item.checkState(1))
        finally:
            self._syncing_checks = False

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

    def _set_descendant_selection_state(self, item, state):
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(1, state)
            self._set_descendant_selection_state(child, state)

    def _iter_items(self, parent=None):
        parent = parent or self.tree.invisibleRootItem()
        for i in range(parent.childCount()):
            child = parent.child(i)
            yield child
            yield from self._iter_items(child)

    def _set_auto_detect_all(self, enabled: bool):
        checked = Qt.CheckState.Unchecked if enabled else Qt.CheckState.Checked
        for item in self._iter_items():
            chk = self.tree.itemWidget(item, 0)
            if chk is not None:
                chk.blockSignals(True)
                chk.setChecked(checked == Qt.CheckState.Checked)
                chk.blockSignals(False)
        self._refresh_disabled_styles()

    def _on_exclude_changed(self, item):
        self._refresh_disabled_styles()

    def _item_is_excluded(self, item):
        current = item
        while current is not None:
            chk = self.tree.itemWidget(current, 0)
            if chk is not None and chk.isChecked():
                return True
            current = current.parent()
        return False

    def _refresh_disabled_styles(self):
        normal = QBrush(QColor(config.FG))
        muted = QBrush(QColor("#777777"))
        for item in self._iter_items():
            excluded = self._item_is_excluded(item)
            brush = muted if excluded else normal
            item.setForeground(0, brush)
            item.setForeground(1, brush)
            chk = self.tree.itemWidget(item, 0)
            if chk is not None:
                parent_excluded = item.parent() is not None and self._item_is_excluded(item.parent())
                chk.setEnabled(not parent_excluded)
                chk.setStyleSheet(
                    "QCheckBox { color: #777777; background: transparent; }"
                    if excluded else
                    "QCheckBox { color: #FFFFFF; background: transparent; }"
                )

    def _collect_state(self):
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
                        continue
                if child.childCount() == 0:
                    file_path = child.data(1, Qt.ItemDataRole.UserRole)
                    if file_path and child.checkState(1) == Qt.CheckState.Checked and not self._item_is_excluded(child):
                        self.selected_files.append(file_path)
                else:
                    collect(child)
        collect(self.tree.invisibleRootItem())

    def _save_selected_to_tracker(self):
        if not self.selected_files:
            return
        try:
            from core.auto_tracker import AutoTracker
            AutoTracker().sync_with_directory(self.selected_files)
        except Exception:
            pass

    def _on_ok(self):
        self.saved_only = False
        self._collect_state()
        self.accept()

    def _on_save(self):
        self.saved_only = True
        self._collect_state()
        self._save_selected_to_tracker()
        QMessageBox.information(self, "저장 완료", "선택한 항목을 장부에 추가했습니다.")
        self.accept()
