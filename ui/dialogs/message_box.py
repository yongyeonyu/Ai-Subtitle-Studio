# Version: 02.07.00
# Phase: PHASE1-C
"""
Shared Apple-style message boxes.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox

from ui.style import COLORS


def message_box_stylesheet() -> str:
    return (
        f"QMessageBox {{ background: {COLORS['bg']}; color: {COLORS['text']}; font-size: 13px; }}"
        f"QMessageBox QLabel {{ color: {COLORS['text']}; background: transparent; font-size: 13px; }}"
        f"QMessageBox QPushButton {{ background: {COLORS['control']}; color: {COLORS['text']}; "
        f"border: 1px solid {COLORS['separator']}; border-radius: 7px; "
        "padding: 7px 14px; min-width: 72px; min-height: 30px; font-weight: 700; }"
        f"QMessageBox QPushButton:hover {{ background: {COLORS['control_hover']}; border-color: #465663; }}"
        f"QMessageBox QPushButton:default {{ background: {COLORS['primary']}; color: #FFFFFF; "
        f"border-color: {COLORS['primary']}; }}"
    )


def show_message(
    parent,
    title: str,
    text: str,
    *,
    icon: QMessageBox.Icon = QMessageBox.Icon.Question,
    buttons=QMessageBox.StandardButton.Ok,
    default=QMessageBox.StandardButton.Ok,
    labels: dict[QMessageBox.StandardButton, str] | None = None,
) -> QMessageBox.StandardButton:
    box = QMessageBox(parent)
    box.setOption(QMessageBox.Option.DontUseNativeDialog, True)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(icon)
    box.setStandardButtons(buttons)
    box.setDefaultButton(default)
    box.setStyleSheet(message_box_stylesheet())
    for standard_button, label in (labels or {}).items():
        btn = box.button(standard_button)
        if btn is not None:
            btn.setText(label)
    return box.exec()


def ask_yes_no(parent, title: str, text: str, *, default_no: bool = True) -> bool:
    default = QMessageBox.StandardButton.No if default_no else QMessageBox.StandardButton.Yes
    reply = show_message(
        parent,
        title,
        text,
        icon=QMessageBox.Icon.Question,
        buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        default=default,
        labels={
            QMessageBox.StandardButton.Yes: "예",
            QMessageBox.StandardButton.No: "아니요",
        },
    )
    return reply == QMessageBox.StandardButton.Yes


def confirm_save_changes(parent, *, title: str = "저장 확인") -> QMessageBox.StandardButton:
    return show_message(
        parent,
        title,
        "저장되지 않은 변경사항이 있습니다.\n저장하시겠습니까?",
        icon=QMessageBox.Icon.Warning,
        buttons=(
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel
        ),
        default=QMessageBox.StandardButton.Yes,
        labels={
            QMessageBox.StandardButton.Yes: "예",
            QMessageBox.StandardButton.No: "아니요",
            QMessageBox.StandardButton.Cancel: "취소",
        },
    )
