# Version: 02.02.00
# Phase: PHASE1-B
"""
[Version History]
- v0.1.0 (Build 00.01.00) : 최초 생성. 계층형 폴더/파일 트리 및 일괄 선택 기능 구현
"""
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTreeWidget, QTreeWidgetItem, QLabel
)
from PyQt6.QtCore import Qt
import config

class FolderDialog(QDialog):
    def __init__(self, root_path, parent=None):
        super().__init__(parent)
        self.root_path = root_path
        self.selected_files = []
        self.setWindowTitle("폴더 및 파일 선택")
        self.setMinimumSize(600, 500)
        self.setStyleSheet(f"background-color: {config.BG}; color: {config.FG};")
        self._build_ui()
        self._populate_tree()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        lbl = QLabel(f"📂 경로: {self.root_path}")
        lbl.setStyleSheet(f"color: {config.FG2}; font-weight: bold;")
        layout.addWidget(lbl)

        # 트리 위젯 설정
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{ background-color: {config.BG2}; border: 1px solid {config.BG3}; }}
            QTreeWidget::item {{ padding: 4px; }}
            QTreeWidget::item:hover {{ background-color: {config.BG3}; }}
        """)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree)

        # 하단 버튼
        btn_layout = QHBoxLayout()
        
        self.btn_select_all = QPushButton("전체 선택")
        self.btn_select_all.setStyleSheet(f"background: #444; padding: 6px; border-radius: 4px;")
        self.btn_select_all.clicked.connect(self._select_all)
        
        self.btn_deselect_all = QPushButton("전체 해제")
        self.btn_deselect_all.setStyleSheet(f"background: #444; padding: 6px; border-radius: 4px;")
        self.btn_deselect_all.clicked.connect(self._deselect_all)

        self.btn_ok = QPushButton("선택 완료")
        self.btn_ok.setStyleSheet(f"background: {config.ACCENT}; color: #000; font-weight: bold; padding: 6px; border-radius: 4px;")
        self.btn_ok.clicked.connect(self._on_ok)

        btn_layout.addWidget(self.btn_select_all)
        btn_layout.addWidget(self.btn_deselect_all)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_ok)

        layout.addLayout(btn_layout)

    def _populate_tree(self):
        valid_exts = {'.mp4', '.mov', '.wav', '.m4a', '.m2a', '.mp3', '.aac'}
        
        def add_nodes(parent_item, current_path):
            try:
                entries = sorted(os.listdir(current_path))
            except PermissionError:
                return

            has_valid_children = False
            for entry in entries:
                if entry.startswith('.'): continue
                full_path = os.path.join(current_path, entry)
                
                if os.path.isdir(full_path):
                    dir_item = QTreeWidgetItem(parent_item, [f"📁 {entry}"])
                    dir_item.setFlags(dir_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
                    dir_item.setCheckState(0, Qt.CheckState.Unchecked)
                    dir_item.setData(0, Qt.ItemDataRole.UserRole, full_path)
                    
                    if add_nodes(dir_item, full_path):
                        has_valid_children = True
                    else:
                        parent_item.removeChild(dir_item) # 빈 폴더 제거
                        
                elif os.path.isfile(full_path) and os.path.splitext(entry)[1].lower() in valid_exts:
                    file_item = QTreeWidgetItem(parent_item, [f"🎬 {entry}"])
                    file_item.setFlags(file_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    file_item.setCheckState(0, Qt.CheckState.Unchecked)
                    file_item.setData(0, Qt.ItemDataRole.UserRole, full_path)
                    has_valid_children = True
                    
            return has_valid_children

        root_item = QTreeWidgetItem(self.tree, [os.path.basename(self.root_path) or self.root_path])
        root_item.setFlags(root_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
        root_item.setCheckState(0, Qt.CheckState.Unchecked)
        add_nodes(root_item, self.root_path)
        root_item.setExpanded(True)  # 최상위(루트) 폴더 1개만 열어두고 하위는 모두 닫음
        
    def _on_item_changed(self, item, column):
        pass # QTreeWidget의 ItemIsAutoTristate가 하위 항목 체크를 자동 관리함

    def _select_all(self):
        self._set_check_state_all(self.tree.invisibleRootItem(), Qt.CheckState.Checked)

    def _deselect_all(self):
        self._set_check_state_all(self.tree.invisibleRootItem(), Qt.CheckState.Unchecked)

    def _set_check_state_all(self, parent, state):
        for i in range(parent.childCount()):
            child = parent.child(i)
            child.setCheckState(0, state)
            self._set_check_state_all(child, state)

    def _on_ok(self):
        self.selected_files = []
        def collect_files(parent):
            for i in range(parent.childCount()):
                child = parent.child(i)
                if child.childCount() == 0: # 파일인 경우
                    if child.checkState(0) == Qt.CheckState.Checked:
                        self.selected_files.append(child.data(0, Qt.ItemDataRole.UserRole))
                else:
                    collect_files(child) # 폴더인 경우 재귀 탐색
                    
        collect_files(self.tree.invisibleRootItem())
        self.accept()