"""Dedicated NAS/iCloud auto-processing settings UX."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.audio.stt_quality_presets import stt_quality_label
from ui.style import COLORS, line_icon

AUTO_SOURCE_QUALITY_KEYS = ("fast", "balanced", "precise")


def normalize_auto_source_quality_key(value: str | None) -> str:
    key = str(value or "").strip().lower()
    if key in AUTO_SOURCE_QUALITY_KEYS:
        return key
    return "balanced"


def auto_source_quality_items() -> list[tuple[str, str]]:
    return [(stt_quality_label(key), key) for key in AUTO_SOURCE_QUALITY_KEYS]


def auto_source_toggle_stylesheet() -> str:
    return (
        "QCheckBox { "
        "background:#11181C; color:#F5F7FA; border:1px solid #2D3942; "
        "border-radius:7px; padding:2px 8px; font-size:10px; font-weight:800; spacing:5px; "
        "} "
        "QCheckBox:hover { background:#151F24; border-color:#3F8CFF; } "
        "QCheckBox:checked { border-color:#34C759; } "
        "QCheckBox::indicator { "
        "width:13px; height:13px; border-radius:3px; border:1px solid #465663; background:transparent; "
        "} "
        "QCheckBox::indicator:checked { background:#34C759; border-color:#34C759; }"
    )


def auto_source_icon_button_stylesheet() -> str:
    return (
        "QPushButton { "
        "background:#11181C; border:1px solid #2D3942; border-radius:7px; padding:0; min-width:22px; "
        "} "
        "QPushButton:hover { background:#151F24; border-color:#3F8CFF; } "
        "QPushButton:pressed { background:#0F1418; border-color:#34C759; }"
    )


def auto_source_dialog_stylesheet() -> str:
    return (
        "QDialog { background:#0C1114; } "
        "#AutoSourceRoot { background:#0C1114; } "
        "#AutoSourceHero { background:#11181C; border:1px solid #27343D; border-radius:18px; } "
        "#AutoSourceCard { background:#141D22; border:1px solid #27343D; border-radius:16px; } "
        "#AutoSourceTitle { color:#F5F7FA; font-size:18px; font-weight:900; } "
        "#AutoSourceHint { color:#8B949E; font-size:11px; font-weight:700; } "
        "#AutoSourceFieldLabel { color:#D9E2EC; font-size:12px; font-weight:800; } "
        "QLineEdit { background:#0F1518; color:#F5F7FA; border:1px solid #33414A; border-radius:12px; padding:10px 12px; font-size:12px; } "
        "QLineEdit:focus { border-color:#3F8CFF; } "
        "QComboBox { background:#0F1518; color:#F5F7FA; border:1px solid #33414A; border-radius:12px; padding:8px 12px; font-size:12px; font-weight:800; min-height:20px; } "
        "QComboBox:hover { border-color:#3F8CFF; } "
        "QComboBox::drop-down { width:22px; border:none; } "
        "QComboBox QAbstractItemView { background:#11181C; color:#F5F7FA; selection-background-color:#1A84FF; border:1px solid #27343D; } "
        + auto_source_toggle_stylesheet()
        + " "
        "QPushButton#AutoSourcePrimary { background:#1A84FF; color:#FFFFFF; border:none; border-radius:12px; padding:10px 18px; font-size:12px; font-weight:900; } "
        "QPushButton#AutoSourcePrimary:hover { background:#3F9BFF; } "
        "QPushButton#AutoSourceSecondary { background:#141D22; color:#D9E2EC; border:1px solid #33414A; border-radius:12px; padding:10px 18px; font-size:12px; font-weight:900; } "
        "QPushButton#AutoSourceSecondary:hover { border-color:#3F8CFF; background:#182229; } "
    )


class AutoSourceSettingsDialog(QDialog):
    def __init__(self, scope: str, state: dict | None = None, parent=None):
        super().__init__(parent)
        self.scope = "nas" if str(scope or "").strip().lower() == "nas" else "icloud"
        self.state = dict(state or {})
        self.setModal(True)
        self.resize(540, 340)
        self.setWindowTitle(f"{self._scope_title()} 자동 처리 설정")
        self.setStyleSheet(auto_source_dialog_stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        shell = QWidget(self)
        shell.setObjectName("AutoSourceRoot")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(14)
        root.addWidget(shell)

        shell_layout.addWidget(self._build_hero())
        shell_layout.addWidget(self._build_card())
        shell_layout.addStretch(1)
        shell_layout.addLayout(self._build_buttons())

    def _scope_title(self) -> str:
        return "NAS" if self.scope == "nas" else "iCloud"

    def _scope_hint(self) -> str:
        if self.scope == "nas":
            return "NAS 경로, 자동 처리, 처리 모드를 여기서 따로 관리합니다."
        return "iCloud 경로, 자동 처리, 처리 모드를 여기서 따로 관리합니다."

    def _scope_path_label(self) -> str:
        return "NAS 루트 경로" if self.scope == "nas" else "iCloud 루트 경로"

    def _scope_path_placeholder(self) -> str:
        return "smb:// 또는 마운트 경로" if self.scope == "nas" else "iCloud 동기화 경로"

    def _build_hero(self) -> QWidget:
        card = QWidget(self)
        card.setObjectName("AutoSourceHero")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        icon = QLabel(card)
        icon_name = "nas" if self.scope == "nas" else "cloud"
        icon.setPixmap(line_icon(icon_name, "#F5F7FA", 22).pixmap(22, 22))
        icon.setFixedSize(28, 28)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(4)

        title = QLabel(f"{self._scope_title()} 자동 처리", card)
        title.setObjectName("AutoSourceTitle")
        text_col.addWidget(title)

        hint = QLabel(self._scope_hint(), card)
        hint.setObjectName("AutoSourceHint")
        hint.setWordWrap(True)
        text_col.addWidget(hint)
        layout.addLayout(text_col, 1)
        return card

    def _field_row(self, label_text: str, field: QWidget) -> QWidget:
        row = QWidget(self)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(label_text, row)
        label.setObjectName("AutoSourceFieldLabel")
        layout.addWidget(label)
        layout.addWidget(field)
        return row

    def _build_card(self) -> QWidget:
        card = QWidget(self)
        card.setObjectName("AutoSourceCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        self.path_input = QLineEdit(card)
        self.path_input.setPlaceholderText(self._scope_path_placeholder())
        self.path_input.setText(str(self.state.get("path", "") or ""))
        layout.addWidget(self._field_row(self._scope_path_label(), self.path_input))

        self.auto_checkbox = QCheckBox(f"{self._scope_title()} 자동처리 활성화", card)
        self.auto_checkbox.setChecked(bool(self.state.get("auto_enabled", False)))
        layout.addWidget(self.auto_checkbox)

        self.mode_combo = QComboBox(card)
        for label, key in auto_source_quality_items():
            self.mode_combo.addItem(label, key)
        current_mode = normalize_auto_source_quality_key(self.state.get("mode_key"))
        for idx in range(self.mode_combo.count()):
            if self.mode_combo.itemData(idx) == current_mode:
                self.mode_combo.setCurrentIndex(idx)
                break
        layout.addWidget(self._field_row("처리 모드", self.mode_combo))

        note = QLabel("사이드바 카드의 Mode/자동 상태와 항상 같은 값을 사용합니다.", card)
        note.setObjectName("AutoSourceHint")
        note.setWordWrap(True)
        layout.addWidget(note)
        return card

    def _build_buttons(self):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addStretch(1)

        cancel_btn = QPushButton("취소", self)
        cancel_btn.setObjectName("AutoSourceSecondary")
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(cancel_btn)

        save_btn = QPushButton("저장", self)
        save_btn.setObjectName("AutoSourcePrimary")
        save_btn.clicked.connect(self.accept)
        row.addWidget(save_btn)
        return row

    def result_payload(self) -> dict:
        return {
            "path": str(self.path_input.text().strip()),
            "auto_enabled": bool(self.auto_checkbox.isChecked()),
            "mode_key": normalize_auto_source_quality_key(self.mode_combo.currentData()),
        }
