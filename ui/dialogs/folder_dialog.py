# Version: 03.14.23
# Phase: PHASE1-B
"""Folder/file tree dialogs for normal folder loading and NAS auto-detect setup."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from core.runtime import config
from core.settings import load_settings, save_settings
from core.audio.stt_quality_presets import (
    STT_QUALITY_PRESET_ORDER,
    apply_stt_quality_preset,
    load_stt_quality_presets,
    normalize_stt_quality_key,
)


class FolderDialog(QDialog):
    """Media file picker used by the regular folder-open flow."""

    _thumbnail_ready = pyqtSignal(str, str)

    def __init__(self, root_path, parent=None, excluded_folders=None, show_auto_detect=False):
        super().__init__(parent)
        self.root_path = str(root_path or "")
        self.selected_files = []
        self.saved_only = False
        self.processing_mode = "individual"
        self.export_subtitle_video = False
        self.stt_quality_preset = normalize_stt_quality_key(load_settings().get("stt_quality_preset", "precise"))
        self.show_auto_detect = bool(show_auto_detect)
        self.excluded_folders = set(os.path.normpath(p) for p in (excluded_folders or []))
        self.exclude_col = 0 if self.show_auto_detect else None
        self.select_col = 1 if self.show_auto_detect else 0
        self.thumb_col = 2 if self.show_auto_detect else 1
        self.name_col = 3 if self.show_auto_detect else 2
        self._syncing_checks = False
        self._closing = False
        self._file_items = {}
        self._thumb_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="folder-thumb")

        self.setWindowTitle("폴더 및 파일 선택")
        self.setMinimumSize(760, 560)
        self.setStyleSheet(f"background-color: {config.BG}; color: {config.FG};")
        self._thumbnail_ready.connect(self._apply_thumbnail)
        self._build_ui()
        self._populate_tree()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        lbl = QLabel(f"📂 경로: {self.root_path}")
        lbl.setStyleSheet(f"color: {config.FG2}; font-weight: bold;")
        layout.addWidget(lbl)

        option_box = QGroupBox("처리 옵션")
        option_box.setStyleSheet(
            f"QGroupBox {{ color: {config.FG}; border: 1px solid {config.BG3}; "
            "border-radius: 4px; margin-top: 8px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
        )
        option_layout = QHBoxLayout(option_box)
        mode_lbl = QLabel("개별 처리")
        mode_lbl.setToolTip("선택한 파일을 큐테이블에 하나씩 넣고 순서대로 처리합니다.")
        mode_lbl.setStyleSheet("QLabel { color:#FFFFFF; background:transparent; font-weight:bold; }")
        option_layout.addWidget(mode_lbl)
        option_layout.addSpacing(18)
        self.export_video_chk = QCheckBox("자막영상 출력")
        self.export_video_chk.setToolTip("자막 생성 후 투명 자막 MOV까지 자동으로 출력합니다.")
        self.export_video_chk.setStyleSheet("QCheckBox { color: #FFFFFF; background: transparent; }")
        option_layout.addWidget(self.export_video_chk)
        option_layout.addSpacing(18)
        quality_lbl = QLabel("자막품질")
        quality_lbl.setStyleSheet("QLabel { color: #FFFFFF; background: transparent; font-weight: bold; }")
        option_layout.addWidget(quality_lbl)
        self.combo_subtitle_quality = QComboBox()
        self.combo_subtitle_quality.setToolTip("선택한 자막품질 프리셋을 이번 처리와 전체 설정에 적용합니다.")
        for key in STT_QUALITY_PRESET_ORDER:
            preset = load_stt_quality_presets().get(key, {})
            self.combo_subtitle_quality.addItem(str(preset.get("label") or key), key)
        self.combo_subtitle_quality.setFixedWidth(92)
        self.combo_subtitle_quality.setStyleSheet(
            "QComboBox { color:#FFFFFF; background:#222; border:1px solid #444; border-radius:4px; padding:4px 18px 4px 8px; } "
            "QComboBox::drop-down { border:none; width:16px; } "
            "QAbstractItemView { background:#222; color:#FFFFFF; selection-background-color:#1A84FF; }"
        )
        self._sync_subtitle_quality_combo()
        self.combo_subtitle_quality.currentIndexChanged.connect(self._on_subtitle_quality_changed)
        option_layout.addWidget(self.combo_subtitle_quality)
        option_layout.addStretch()
        layout.addWidget(option_box)

        self.tree = QTreeWidget()
        if self.show_auto_detect:
            self.tree.setHeaderLabels(["자동감지 제외", "선택", "미리보기", "폴더 / 파일"])
            self.tree.setColumnWidth(self.exclude_col, 96)
        else:
            self.tree.setHeaderLabels(["선택", "미리보기", "폴더 / 파일"])
        self.tree.setColumnWidth(self.select_col, 54)
        self.tree.setColumnWidth(self.thumb_col, 92)
        self.tree.setTreePosition(self.name_col)
        self.tree.setIndentation(16)
        self.tree.setIconSize(QSize(78, 44))
        self.tree.setStyleSheet(f"""
            QTreeWidget {{ background-color: {config.BG2}; border: 1px solid {config.BG3}; }}
            QTreeWidget::item {{ padding: 4px; }}
            QTreeWidget::item:hover {{ background-color: {config.BG3}; }}
            QHeaderView::section {{ background-color: {config.BG3}; color: {config.FG}; border: none; padding: 4px; }}
        """)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree)

        btn_layout = QHBoxLayout()
        if self.show_auto_detect:
            self.btn_auto_select_all = self._bottom_button("자동감지 전체 선택")
            self.btn_auto_select_all.setToolTip("모든 폴더를 NAS 자동감지 대상에 포함합니다.")
            self.btn_auto_select_all.clicked.connect(lambda: self._set_auto_detect_all(True))
            self.btn_auto_deselect_all = self._bottom_button("자동감지 전체 해제")
            self.btn_auto_deselect_all.setToolTip("모든 폴더를 NAS 자동감지 대상에서 제외합니다.")
            self.btn_auto_deselect_all.clicked.connect(lambda: self._set_auto_detect_all(False))
            btn_layout.addWidget(self.btn_auto_select_all)
            btn_layout.addWidget(self.btn_auto_deselect_all)

        self.btn_select_all = self._bottom_button("폴더 전체 선택")
        self.btn_select_all.clicked.connect(self._select_all)
        self.btn_deselect_all = self._bottom_button("폴더 전체 해제")
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        self.btn_ok = QPushButton("확인")
        self.btn_ok.setStyleSheet(
            f"background: {config.ACCENT}; color: #000; font-weight: bold; padding: 6px; border-radius: 4px;"
        )
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

    def _bottom_button(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setStyleSheet("background: #444; padding: 6px; border-radius: 4px;")
        return btn

    def _row_values(self, name: str) -> list[str]:
        return ["", "", "", name] if self.show_auto_detect else ["", "", name]

    def _populate_tree(self):
        valid_exts = {".mp4", ".mov", ".wav", ".m4a", ".m2a", ".mp3", ".aac"}
        self.tree.blockSignals(True)

        def add_nodes(parent_item, current_path):
            try:
                entries = sorted(os.listdir(current_path))
            except PermissionError:
                return False
            has_valid_children = False
            for entry in entries:
                if entry.startswith("."):
                    continue
                full_path = os.path.join(current_path, entry)
                if os.path.isdir(full_path):
                    dir_item = QTreeWidgetItem(parent_item, self._row_values(f"📁 {entry}"))
                    dir_item.setFlags(dir_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    dir_item.setCheckState(self.select_col, Qt.CheckState.Unchecked)
                    if self.exclude_col is not None:
                        dir_item.setData(self.exclude_col, Qt.ItemDataRole.UserRole, full_path)
                    dir_item.setData(self.name_col, Qt.ItemDataRole.UserRole, full_path)
                    self._set_exclude_widget(dir_item, full_path)
                    if add_nodes(dir_item, full_path):
                        has_valid_children = True
                    else:
                        parent_item.removeChild(dir_item)
                elif os.path.isfile(full_path) and os.path.splitext(entry)[1].lower() in valid_exts:
                    file_item = QTreeWidgetItem(parent_item, self._row_values(entry))
                    file_item.setFlags(file_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    file_item.setCheckState(self.select_col, Qt.CheckState.Unchecked)
                    file_item.setData(self.name_col, Qt.ItemDataRole.UserRole, full_path)
                    file_item.setTextAlignment(self.thumb_col, Qt.AlignmentFlag.AlignCenter)
                    self._set_placeholder_thumbnail(file_item, full_path)
                    has_valid_children = True
            return has_valid_children

        root_item = QTreeWidgetItem(self.tree, self._row_values(os.path.basename(self.root_path) or self.root_path))
        root_item.setFlags(root_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        root_item.setCheckState(self.select_col, Qt.CheckState.Unchecked)
        if self.exclude_col is not None:
            root_item.setData(self.exclude_col, Qt.ItemDataRole.UserRole, self.root_path)
        root_item.setData(self.name_col, Qt.ItemDataRole.UserRole, self.root_path)
        self._set_exclude_widget(root_item, self.root_path)
        add_nodes(root_item, self.root_path)
        root_item.setExpanded(True)
        self.tree.blockSignals(False)
        self._refresh_disabled_styles()

    def _set_placeholder_thumbnail(self, item, file_path: str):
        ext = os.path.splitext(file_path)[1].lower()
        item.setText(self.thumb_col, "🎞" if ext in {".mp4", ".mov"} else "♪")
        self._file_items[file_path] = item
        if ext in {".mp4", ".mov"}:
            self._request_thumbnail(file_path)

    def _request_thumbnail(self, file_path: str):
        def worker():
            try:
                from core.roughcut.thumbnail_cache import default_thumbnail_cache_dir, ensure_thumbnail

                result = ensure_thumbnail(
                    file_path,
                    0.5,
                    cache_dir=default_thumbnail_cache_dir(),
                    width=180,
                )
                if result.path and not getattr(self, "_closing", False):
                    self._thumbnail_ready.emit(file_path, result.path)
            except Exception:
                pass

        try:
            self._thumb_executor.submit(worker)
        except Exception:
            pass

    def _apply_thumbnail(self, file_path: str, thumbnail_path: str):
        item = self._file_items.get(file_path)
        if item is None or not thumbnail_path or not os.path.exists(thumbnail_path):
            return
        pixmap = QPixmap(thumbnail_path)
        if pixmap.isNull():
            return
        item.setText(self.thumb_col, "")
        item.setIcon(
            self.thumb_col,
            QIcon(
                pixmap.scaled(
                    78,
                    44,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            ),
        )

    def _set_exclude_widget(self, item, folder_path):
        if self.exclude_col is None:
            return
        chk = QCheckBox("제외")
        chk.setStyleSheet("QCheckBox { color: #FFFFFF; background: transparent; }")
        chk.setChecked(os.path.normpath(folder_path) in self.excluded_folders)
        self.tree.setItemWidget(item, self.exclude_col, chk)
        chk.stateChanged.connect(lambda _state, item=item: self._on_exclude_changed(item))

    def _on_item_changed(self, item, column):
        if self._syncing_checks or column != self.select_col:
            return
        self._syncing_checks = True
        try:
            state = item.checkState(self.select_col)
            if item.childCount() > 0 and state != Qt.CheckState.PartiallyChecked:
                self._set_descendant_selection_state(item, state)
            self._refresh_ancestor_selection_state(item.parent())
        finally:
            self._syncing_checks = False

    def _select_all(self):
        self._set_all_selection_state(Qt.CheckState.Checked)

    def _deselect_all(self):
        self._set_all_selection_state(Qt.CheckState.Unchecked)

    def _set_all_selection_state(self, state):
        self._syncing_checks = True
        try:
            self._set_check_state_all(self.tree.invisibleRootItem(), state)
        finally:
            self._syncing_checks = False

    def _set_check_state_all(self, parent, state):
        for i in range(parent.childCount()):
            child = parent.child(i)
            child.setCheckState(self.select_col, state)
            self._set_check_state_all(child, state)

    def _set_descendant_selection_state(self, item, state):
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(self.select_col, state)
            self._set_descendant_selection_state(child, state)

    def _refresh_ancestor_selection_state(self, item):
        while item is not None:
            child_states = [
                item.child(i).checkState(self.select_col)
                for i in range(item.childCount())
            ]
            if child_states and all(state == Qt.CheckState.Checked for state in child_states):
                state = Qt.CheckState.Checked
            elif child_states and all(state == Qt.CheckState.Unchecked for state in child_states):
                state = Qt.CheckState.Unchecked
            else:
                state = Qt.CheckState.PartiallyChecked
            item.setCheckState(self.select_col, state)
            item = item.parent()

    def _iter_items(self, parent=None):
        parent = parent or self.tree.invisibleRootItem()
        for i in range(parent.childCount()):
            child = parent.child(i)
            yield child
            yield from self._iter_items(child)

    def _set_auto_detect_all(self, enabled: bool):
        if self.exclude_col is None:
            return
        checked = Qt.CheckState.Unchecked if enabled else Qt.CheckState.Checked
        for item in self._iter_items():
            chk = self.tree.itemWidget(item, self.exclude_col)
            if chk is not None:
                chk.blockSignals(True)
                chk.setChecked(checked == Qt.CheckState.Checked)
                chk.blockSignals(False)
        self._refresh_disabled_styles()

    def _on_exclude_changed(self, item):
        self._refresh_disabled_styles()

    def _item_is_excluded(self, item):
        if self.exclude_col is None:
            return False
        current = item
        while current is not None:
            chk = self.tree.itemWidget(current, self.exclude_col)
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
            for col in range(self.tree.columnCount()):
                item.setForeground(col, brush)
            chk = self.tree.itemWidget(item, self.exclude_col) if self.exclude_col is not None else None
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
        self.processing_mode = "individual"
        self.export_subtitle_video = bool(self.export_video_chk.isChecked())
        self.stt_quality_preset = normalize_stt_quality_key(self.combo_subtitle_quality.currentData() or "precise")

        def collect(parent):
            for i in range(parent.childCount()):
                child = parent.child(i)
                path = child.data(self.name_col, Qt.ItemDataRole.UserRole)
                if path and child.childCount() > 0:
                    chk = self.tree.itemWidget(child, self.exclude_col) if self.exclude_col is not None else None
                    if chk is not None and chk.isChecked():
                        self.excluded_folders.add(os.path.normpath(path))
                        continue
                if child.childCount() == 0:
                    file_path = child.data(self.name_col, Qt.ItemDataRole.UserRole)
                    if file_path and child.checkState(self.select_col) == Qt.CheckState.Checked and not self._item_is_excluded(child):
                        self.selected_files.append(file_path)
                else:
                    collect(child)

        collect(self.tree.invisibleRootItem())

    def _on_ok(self):
        self.saved_only = False
        self._collect_state()
        self._persist_subtitle_quality()
        self.accept()

    def _on_save(self):
        self._on_ok()

    def _sync_subtitle_quality_combo(self):
        key = normalize_stt_quality_key(self.stt_quality_preset)
        self.combo_subtitle_quality.blockSignals(True)
        for idx in range(self.combo_subtitle_quality.count()):
            if self.combo_subtitle_quality.itemData(idx) == key:
                self.combo_subtitle_quality.setCurrentIndex(idx)
                break
        self.combo_subtitle_quality.blockSignals(False)

    def _on_subtitle_quality_changed(self, *args):
        self.stt_quality_preset = normalize_stt_quality_key(self.combo_subtitle_quality.currentData() or "precise")
        self._persist_subtitle_quality()

    def _persist_subtitle_quality(self):
        settings = apply_stt_quality_preset(load_settings(), self.stt_quality_preset)
        save_settings(settings)
        parent = self.parent()
        if parent is not None and hasattr(parent, "_apply_ai_settings"):
            parent._apply_ai_settings(settings)

    def closeEvent(self, event):
        try:
            self._closing = True
            self._thumb_executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        super().closeEvent(event)


class NasFolderDialog(FolderDialog):
    """Folder picker used by NAS open; keeps auto-detect exclusion controls isolated."""

    def __init__(self, root_path, parent=None, excluded_folders=None):
        super().__init__(
            root_path,
            parent=parent,
            excluded_folders=excluded_folders,
            show_auto_detect=True,
        )
