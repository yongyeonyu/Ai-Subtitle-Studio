"""
ui/settings/settings_dictionary.py
Correction dictionary manager dialog.
"""

from __future__ import annotations

from functools import cmp_to_key

from PyQt6.QtCore import QCollator, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.correction_dictionary_db import load_corrections, save_corrections
from core.runtime import config
from ui.settings.settings_common import _create_bottom_buttons
from ui.settings.tablet_dialog import apply_tablet_dialog_profile
from ui.style import COLORS, button_style, label_style, settings_dialog_stylesheet
from ui.ux.apple_popup_theme import apple_popup_dialog_stylesheet


def _dictionary_dialog_stylesheet() -> str:
    return (
        "#correctionDictionaryRow { background: transparent; } "
        f"#correctionDictionaryPath {{ color: {COLORS['muted']}; font-size: 11px; font-weight: 700; }} "
        f"#correctionDictionaryPreviewText {{ color: {COLORS['text']}; font-size: 13px; font-weight: 700; }} "
        f"#correctionDictionaryPreviewHint {{ color: {COLORS['muted']}; font-size: 11px; font-weight: 700; }} "
    )


class CorrectionDictionaryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("자막 교정사전")
        self.setObjectName("correctionDictionaryDialog")
        self.setMinimumWidth(980)
        self.setMinimumHeight(640)
        apply_tablet_dialog_profile(self)
        self.setStyleSheet(
            settings_dialog_stylesheet()
            + apple_popup_dialog_stylesheet("correctionDictionaryDialog", accent=COLORS["accent"])
            + _dictionary_dialog_stylesheet()
        )

        self._collator = QCollator()
        self._collator.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        try:
            self._collator.setIgnorePunctuation(True)
        except Exception:
            pass
        try:
            self._collator.setNumericMode(True)
        except Exception:
            pass

        self._correction_path = str(getattr(config, "CORRECTIONS_FILE", ""))
        self._corrections = dict(load_corrections(self._correction_path))
        self.result = dict(self._corrections)
        self._selected_key: str | None = None
        self._dirty = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(12)

        hero_card = QFrame(self)
        hero_card.setObjectName("applePopupHeroCard")
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(18, 16, 18, 16)
        hero_layout.setSpacing(8)
        hero_eyebrow = QLabel("CORRECTION DICTIONARY")
        hero_eyebrow.setObjectName("applePopupHeroEyebrow")
        hero_layout.addWidget(hero_eyebrow)
        hero_title = QLabel("자막 교정사전")
        hero_title.setObjectName("applePopupHeroTitle")
        hero_layout.addWidget(hero_title)
        hero_subtitle = QLabel(
            "자막 생성 후 최종 텍스트에 적용되는 교정 항목을 가나다 순으로 관리합니다. "
            "추가/수정/삭제 내용은 확인을 누를 때 저장됩니다."
        )
        hero_subtitle.setObjectName("applePopupHeroSubtitle")
        hero_subtitle.setWordWrap(True)
        hero_layout.addWidget(hero_subtitle)
        layout.addWidget(hero_card)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(12)

        list_card = QFrame(self)
        list_card.setObjectName("applePopupSectionCard")
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(16, 16, 16, 16)
        list_layout.setSpacing(10)

        list_title = QLabel("교정 항목")
        list_title.setObjectName("applePopupSectionTitle")
        list_layout.addWidget(list_title)

        list_hint = QLabel("원문 또는 교정어를 검색할 수 있고, 목록은 항상 가나다 순으로 다시 정렬됩니다.")
        list_hint.setObjectName("applePopupSectionHint")
        list_hint.setWordWrap(True)
        list_layout.addWidget(list_hint)

        list_toolbar = QHBoxLayout()
        list_toolbar.setContentsMargins(0, 0, 0, 0)
        list_toolbar.setSpacing(8)

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("원문 / 교정어 검색")
        self.search_edit.textChanged.connect(self._rebuild_list)
        list_toolbar.addWidget(self.search_edit, stretch=1)

        self.count_pill = QLabel("")
        self.count_pill.setObjectName("applePopupInfoPill")
        list_toolbar.addWidget(self.count_pill)
        list_layout.addLayout(list_toolbar)

        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        list_layout.addWidget(self.list_widget, stretch=1)

        path_label = QLabel(self._correction_path)
        path_label.setObjectName("correctionDictionaryPath")
        path_label.setWordWrap(True)
        list_layout.addWidget(path_label)

        editor_card = QFrame(self)
        editor_card.setObjectName("applePopupSectionCard")
        editor_layout = QVBoxLayout(editor_card)
        editor_layout.setContentsMargins(16, 16, 16, 16)
        editor_layout.setSpacing(10)

        editor_header = QHBoxLayout()
        editor_header.setContentsMargins(0, 0, 0, 0)
        editor_header.setSpacing(8)

        editor_title = QLabel("항목 편집")
        editor_title.setObjectName("applePopupSectionTitle")
        editor_header.addWidget(editor_title, stretch=1)

        self.status_pill = QLabel("")
        self.status_pill.setObjectName("applePopupInfoPill")
        editor_header.addWidget(self.status_pill)
        editor_layout.addLayout(editor_header)

        editor_hint = QLabel("선택한 항목을 수정하거나 새 항목을 추가할 수 있습니다. 빈 값과 중복 원문은 저장되지 않습니다.")
        editor_hint.setObjectName("applePopupSectionHint")
        editor_hint.setWordWrap(True)
        editor_layout.addWidget(editor_hint)

        original_label = QLabel("원문")
        original_label.setStyleSheet(label_style("muted", 11, bold=True))
        editor_layout.addWidget(original_label)
        self.original_edit = QLineEdit(self)
        self.original_edit.setPlaceholderText("예: 사품핑")
        self.original_edit.textChanged.connect(self._update_preview)
        editor_layout.addWidget(self.original_edit)

        corrected_label = QLabel("교정")
        corrected_label.setStyleSheet(label_style("muted", 11, bold=True))
        editor_layout.addWidget(corrected_label)
        self.corrected_edit = QLineEdit(self)
        self.corrected_edit.setPlaceholderText("예: 사뿐핑")
        self.corrected_edit.textChanged.connect(self._update_preview)
        editor_layout.addWidget(self.corrected_edit)

        preview_card = QFrame(self)
        preview_card.setObjectName("applePopupPreview")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(14, 12, 14, 12)
        preview_layout.setSpacing(6)
        preview_title = QLabel("미리보기")
        preview_title.setObjectName("applePopupSectionHint")
        preview_layout.addWidget(preview_title)
        self.preview_before = QLabel("")
        self.preview_before.setObjectName("correctionDictionaryPreviewText")
        self.preview_before.setWordWrap(True)
        preview_layout.addWidget(self.preview_before)
        self.preview_after = QLabel("")
        self.preview_after.setObjectName("correctionDictionaryPreviewText")
        self.preview_after.setWordWrap(True)
        preview_layout.addWidget(self.preview_after)
        preview_hint = QLabel("원문 문자열이 포함된 자막 문장에 교정값이 그대로 치환됩니다.")
        preview_hint.setObjectName("correctionDictionaryPreviewHint")
        preview_hint.setWordWrap(True)
        preview_layout.addWidget(preview_hint)
        editor_layout.addWidget(preview_card)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)

        self.new_button = QPushButton("새 항목")
        self.new_button.setStyleSheet(button_style("toolbar", font_size="11px", padding="6px 12px"))
        self.new_button.clicked.connect(self._prepare_new_entry)
        action_row.addWidget(self.new_button)

        self.save_button = QPushButton("선택 저장")
        self.save_button.setStyleSheet(button_style("primary", font_size="11px", padding="6px 12px"))
        self.save_button.clicked.connect(self._save_current_entry)
        action_row.addWidget(self.save_button)

        self.delete_button = QPushButton("삭제")
        self.delete_button.setStyleSheet(button_style("danger", font_size="11px", padding="6px 12px"))
        self.delete_button.clicked.connect(self._delete_current_entry)
        action_row.addWidget(self.delete_button)
        action_row.addStretch(1)
        editor_layout.addLayout(action_row)

        content_row.addWidget(list_card, stretch=1)
        content_row.addWidget(editor_card, stretch=1)
        layout.addLayout(content_row, stretch=1)
        layout.addLayout(_create_bottom_buttons(self, self._commit_and_accept))

        self._rebuild_list()
        self._prepare_new_entry()

    def _sorted_items(self, items: dict[str, str] | None = None) -> list[tuple[str, str]]:
        source = dict(items or self._corrections)
        values = list(source.items())

        def _compare(left: tuple[str, str], right: tuple[str, str]) -> int:
            primary = self._collator.compare(left[0], right[0])
            if primary != 0:
                return primary
            return self._collator.compare(left[1], right[1])

        values.sort(key=cmp_to_key(_compare))
        return values

    def _visible_items(self) -> list[tuple[str, str]]:
        keyword = str(self.search_edit.text() or "").strip().lower()
        items = self._sorted_items()
        if not keyword:
            return items
        return [
            (wrong, correct)
            for wrong, correct in items
            if keyword in wrong.lower() or keyword in correct.lower()
        ]

    def _rebuild_list(self) -> None:
        preserve_key = self._selected_key
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for wrong, correct in self._visible_items():
            item = QListWidgetItem(f"{wrong}  →  {correct}")
            item.setData(Qt.ItemDataRole.UserRole, wrong)
            item.setToolTip(f"{wrong} -> {correct}")
            self.list_widget.addItem(item)
            if preserve_key and wrong == preserve_key:
                self.list_widget.setCurrentItem(item)
        self.list_widget.blockSignals(False)
        if preserve_key and self.list_widget.currentItem() is None:
            self._selected_key = None
        self._refresh_count_pill()
        if self.list_widget.currentItem() is None and self.list_widget.count() > 0 and not preserve_key:
            self.list_widget.setCurrentRow(0)

    def _refresh_count_pill(self) -> None:
        total = len(self._corrections)
        visible = self.list_widget.count()
        self.count_pill.setText(f"{visible}/{total}개")
        self.status_pill.setText("저장 전 변경" if self._dirty else "변경 없음")

    def _prepare_new_entry(self) -> None:
        self._selected_key = None
        self.list_widget.blockSignals(True)
        self.list_widget.clearSelection()
        self.list_widget.setCurrentRow(-1)
        self.list_widget.blockSignals(False)
        self.original_edit.setText("")
        self.corrected_edit.setText("")
        self.original_edit.setFocus()
        self.delete_button.setEnabled(False)
        self._update_preview()
        self._refresh_count_pill()

    def _on_selection_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        del previous
        if current is None:
            self._prepare_new_entry()
            return
        key = str(current.data(Qt.ItemDataRole.UserRole) or "").strip()
        self._selected_key = key or None
        self.original_edit.setText(key)
        self.corrected_edit.setText(str(self._corrections.get(key, "") or ""))
        self.delete_button.setEnabled(bool(self._selected_key))
        self._update_preview()
        self._refresh_count_pill()

    def _update_preview(self) -> None:
        wrong = str(self.original_edit.text() or "").strip()
        correct = str(self.corrected_edit.text() or "").strip()
        preview_source = wrong or "원문 예시"
        preview_target = correct or "교정 결과"
        self.preview_before.setText(f"입력: {preview_source}")
        self.preview_after.setText(f"적용: {preview_target}")

    def _mark_dirty(self) -> None:
        self._dirty = True
        self.result = dict(self._corrections)
        self._refresh_count_pill()

    def _save_current_entry(self) -> None:
        wrong = str(self.original_edit.text() or "").strip()
        correct = str(self.corrected_edit.text() or "").strip()
        if not wrong:
            QMessageBox.warning(self, "교정사전", "원문을 입력해 주세요.")
            self.original_edit.setFocus()
            return
        if not correct:
            QMessageBox.warning(self, "교정사전", "교정 텍스트를 입력해 주세요.")
            self.corrected_edit.setFocus()
            return

        next_map = dict(self._corrections)
        previous_key = str(self._selected_key or "").strip()
        if previous_key and previous_key != wrong:
            next_map.pop(previous_key, None)
        duplicate_key = wrong in next_map and wrong != previous_key
        if duplicate_key:
            QMessageBox.warning(self, "교정사전", "같은 원문 항목이 이미 있습니다.")
            return

        next_map[wrong] = correct
        self._corrections = next_map
        self._selected_key = wrong
        self._mark_dirty()
        self._rebuild_list()
        self._select_key(wrong)

    def _select_key(self, key: str) -> None:
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if str(item.data(Qt.ItemDataRole.UserRole) or "") == key:
                self.list_widget.setCurrentItem(item)
                return

    def _delete_current_entry(self) -> None:
        key = str(self._selected_key or self.original_edit.text() or "").strip()
        if not key or key not in self._corrections:
            QMessageBox.information(self, "교정사전", "삭제할 항목을 먼저 선택해 주세요.")
            return
        answer = QMessageBox.question(
            self,
            "교정사전",
            f"'{key}' 항목을 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        next_map = dict(self._corrections)
        next_map.pop(key, None)
        self._corrections = next_map
        self._selected_key = None
        self._mark_dirty()
        self._rebuild_list()
        self._prepare_new_entry()

    def _commit_and_accept(self) -> None:
        try:
            saved = save_corrections(self._corrections, self._correction_path)
        except Exception as exc:
            QMessageBox.critical(self, "교정사전", f"교정사전을 저장하지 못했습니다.\n{exc}")
            return
        self._corrections = dict(saved)
        self.result = dict(saved)
        self._dirty = False
        self.accept()

