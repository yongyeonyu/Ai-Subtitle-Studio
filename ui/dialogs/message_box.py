# Version: 03.24.01
# Phase: PHASE8_QMLPopupRefresh
"""
Shared QML-backed message boxes.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox

from ui.dialogs.qml_popup import exec_message_box, install_qmessagebox_hooks


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
    return exec_message_box(
        parent,
        title,
        text,
        icon=icon,
        buttons=buttons,
        default=default,
        labels=labels,
    )


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


__all__ = [
    "ask_yes_no",
    "confirm_save_changes",
    "install_qmessagebox_hooks",
    "show_message",
]
