from __future__ import annotations

import os

from PyQt6.QtCore import QObject, QPoint, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics
from PyQt6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QVBoxLayout, QWidget

from ui.style import COLORS

QML_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "qml")
MESSAGE_QML = os.path.join(QML_DIR, "app_message_dialog.qml")
MENU_QML = os.path.join(QML_DIR, "app_context_menu.qml")

_HOOKS_INSTALLED = False
_ORIGINAL_QMESSAGEBOX_METHODS: dict[str, object] = {}


class _PopupBridge(QObject):
    triggered = pyqtSignal(str)


def _quick_available(qml_path: str) -> bool:
    if not os.path.exists(qml_path):
        return False
    app = QApplication.instance()
    if app is None:
        return False
    try:
        platform_name = str(app.platformName() or "").strip().lower()
    except Exception:
        platform_name = ""
    return platform_name not in {"offscreen", "minimal"}


def _platform_name() -> str:
    app = QApplication.instance()
    if app is None:
        return ""
    try:
        return str(app.platformName() or "").strip().lower()
    except Exception:
        return ""


def _widget_parent(parent):
    return parent if isinstance(parent, QWidget) else None


def _button_bits(buttons) -> list[QMessageBox.StandardButton]:
    candidates = [
        QMessageBox.StandardButton.Ok,
        QMessageBox.StandardButton.Yes,
        QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Save,
        QMessageBox.StandardButton.Discard,
        QMessageBox.StandardButton.Close,
        QMessageBox.StandardButton.Apply,
        QMessageBox.StandardButton.Reset,
        QMessageBox.StandardButton.Abort,
        QMessageBox.StandardButton.Retry,
        QMessageBox.StandardButton.Ignore,
    ]
    resolved: list[QMessageBox.StandardButton] = []
    try:
        button_flags = int(buttons)
    except Exception:
        button_flags = int(QMessageBox.StandardButton.Ok)
    for candidate in candidates:
        try:
            if button_flags & int(candidate):
                resolved.append(candidate)
        except Exception:
            continue
    return resolved or [QMessageBox.StandardButton.Ok]


def _button_label(button: QMessageBox.StandardButton, labels: dict | None = None) -> str:
    if labels and button in labels:
        return str(labels.get(button) or "")
    default_labels = {
        QMessageBox.StandardButton.Ok: "확인",
        QMessageBox.StandardButton.Yes: "예",
        QMessageBox.StandardButton.No: "아니요",
        QMessageBox.StandardButton.Cancel: "취소",
        QMessageBox.StandardButton.Save: "저장",
        QMessageBox.StandardButton.Discard: "삭제",
        QMessageBox.StandardButton.Close: "닫기",
        QMessageBox.StandardButton.Apply: "적용",
        QMessageBox.StandardButton.Reset: "초기화",
        QMessageBox.StandardButton.Abort: "중단",
        QMessageBox.StandardButton.Retry: "재시도",
        QMessageBox.StandardButton.Ignore: "무시",
    }
    return default_labels.get(button, str(button).split(".")[-1])


def _button_kind(button: QMessageBox.StandardButton, *, default: QMessageBox.StandardButton, icon) -> str:
    if button in {QMessageBox.StandardButton.No, QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Close}:
        return "secondary"
    if button in {QMessageBox.StandardButton.Discard, QMessageBox.StandardButton.Abort}:
        return "danger"
    if button == default:
        if icon == QMessageBox.Icon.Warning:
            return "warning"
        if icon == QMessageBox.Icon.Critical:
            return "danger"
        return "primary"
    return "secondary"


def _icon_kind(icon) -> str:
    if icon == QMessageBox.Icon.Warning:
        return "warning"
    if icon == QMessageBox.Icon.Critical:
        return "danger"
    if icon == QMessageBox.Icon.Information:
        return "info"
    return "question"


def _estimate_message_dialog_size(title: str, text: str, button_count: int) -> tuple[int, int]:
    app = QApplication.instance()
    fm = QFontMetrics(app.font()) if app is not None else None
    lines = [str(title or "").strip()] + [line for line in str(text or "").splitlines() if line.strip()]
    if fm is None:
        width = 560
    else:
        max_width = max((fm.horizontalAdvance(line) for line in lines), default=360)
        width = min(860, max(460, max_width + 180))
    line_count = max(1, len(str(text or "").splitlines()))
    height = max(230, 150 + line_count * 28 + (60 if button_count else 0))
    return width, height


class _QuickMessageDialog(QDialog):
    def __init__(self, parent, *, title: str, text: str, icon, buttons, default, labels: dict | None = None):
        super().__init__(parent)
        self._selected = QMessageBox.StandardButton.Cancel
        self._button_map: dict[str, QMessageBox.StandardButton] = {}
        self._bridge = _PopupBridge()
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setObjectName("quickMessageDialog")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        from PyQt6.QtQuickWidgets import QQuickWidget

        quick = QQuickWidget(self)
        quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        quick.setClearColor(QColor(0, 0, 0, 0))
        quick.setStyleSheet("background: transparent; border: none;")
        quick.rootContext().setContextProperty("popupBridge", self._bridge)
        quick.setSource(QUrl.fromLocalFile(MESSAGE_QML))
        layout.addWidget(quick)
        root = quick.rootObject()
        if root is None:
            raise RuntimeError("QML message dialog root is unavailable")
        button_specs = []
        for idx, button in enumerate(_button_bits(buttons)):
            button_id = f"btn_{idx}"
            self._button_map[button_id] = button
            button_specs.append(
                {
                    "id": button_id,
                    "label": _button_label(button, labels),
                    "kind": _button_kind(button, default=default, icon=icon),
                    "default": button == default,
                }
            )
        root.setProperty("titleText", str(title or "알림"))
        root.setProperty("messageText", str(text or ""))
        root.setProperty("iconKind", _icon_kind(icon))
        root.setProperty("buttonsModel", button_specs)
        width, height = _estimate_message_dialog_size(title, text, len(button_specs))
        self.resize(width, height)
        self._bridge.triggered.connect(self._on_triggered)
        QTimer.singleShot(0, self._center_on_parent)

    def _center_on_parent(self):
        parent = self.parentWidget()
        if parent is not None:
            geo = parent.frameGeometry()
            self.move(geo.center() - self.rect().center())
            return
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.move(available.center() - self.rect().center())

    def _on_triggered(self, button_id: str):
        self._selected = self._button_map.get(str(button_id or ""), QMessageBox.StandardButton.Cancel)
        self.accept()

    def selected_button(self) -> QMessageBox.StandardButton:
        return self._selected


class _QuickContextMenuDialog(QDialog):
    def __init__(self, parent, items: list[dict]):
        super().__init__(parent)
        self._selected_id: str | None = None
        self._bridge = _PopupBridge()
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        from PyQt6.QtQuickWidgets import QQuickWidget

        quick = QQuickWidget(self)
        quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        quick.setClearColor(QColor(0, 0, 0, 0))
        quick.setStyleSheet("background: transparent; border: none;")
        quick.rootContext().setContextProperty("popupBridge", self._bridge)
        quick.setSource(QUrl.fromLocalFile(MENU_QML))
        layout.addWidget(quick)
        root = quick.rootObject()
        if root is None:
            raise RuntimeError("QML context menu root is unavailable")
        normalized = [dict(item or {}) for item in list(items or [])]
        root.setProperty("menuItems", normalized)
        width, height = self._estimate_menu_size(normalized)
        self.resize(width, height)
        self._bridge.triggered.connect(self._on_triggered)

    def _estimate_menu_size(self, items: list[dict]) -> tuple[int, int]:
        app = QApplication.instance()
        fm = QFontMetrics(app.font()) if app is not None else None
        visible_labels = [str(item.get("label") or "") for item in items if not bool(item.get("separator"))]
        if fm is None:
            width = 260
        else:
            width = min(420, max(220, max((fm.horizontalAdvance(label) for label in visible_labels), default=120) + 92))
        rows = sum(1 for item in items if not bool(item.get("separator")))
        separators = sum(1 for item in items if bool(item.get("separator")))
        height = max(48, rows * 40 + separators * 10 + 20)
        return width, height

    def _on_triggered(self, item_id: str):
        self._selected_id = str(item_id or "")
        self.accept()

    def selected_id(self) -> str | None:
        return self._selected_id


def exec_message_box(
    parent,
    title: str,
    text: str,
    *,
    icon: QMessageBox.Icon = QMessageBox.Icon.Question,
    buttons=QMessageBox.StandardButton.Ok,
    default=QMessageBox.StandardButton.Ok,
    labels: dict[QMessageBox.StandardButton, str] | None = None,
) -> QMessageBox.StandardButton:
    parent_widget = _widget_parent(parent)
    if _quick_available(MESSAGE_QML):
        try:
            dialog = _QuickMessageDialog(
                parent_widget,
                title=title,
                text=text,
                icon=icon,
                buttons=buttons,
                default=default,
                labels=labels,
            )
            dialog.exec()
            return dialog.selected_button()
        except Exception:
            pass
    if _platform_name() in {"offscreen", "minimal"}:
        if default and int(buttons) & int(default):
            return default
        resolved = _button_bits(buttons)
        return resolved[0] if resolved else QMessageBox.StandardButton.Ok
    box = QMessageBox(parent_widget)
    box.setOption(QMessageBox.Option.DontUseNativeDialog, True)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(icon)
    box.setStandardButtons(buttons)
    box.setDefaultButton(default)
    for standard_button, label in (labels or {}).items():
        btn = box.button(standard_button)
        if btn is not None:
            btn.setText(label)
    return box.exec()


def _fallback_qmenu(parent, global_pos: QPoint, items: list[dict]) -> str | None:
    menu = QMenu(_widget_parent(parent))
    menu.setStyleSheet(
        f"QMenu {{ background:{COLORS['surface']}; color:{COLORS['text']}; border:1px solid {COLORS['separator']}; border-radius:8px; }}"
        f"QMenu::item {{ padding:7px 22px 7px 12px; border-radius:4px; }}"
        "QMenu::item:selected { background:#1F3A56; }"
        "QMenu::item:disabled { color:#65717A; }"
    )
    action_map = {}
    for item in list(items or []):
        if bool(item.get("separator")):
            menu.addSeparator()
            continue
        action = menu.addAction(str(item.get("label") or ""))
        action.setEnabled(bool(item.get("enabled", True)))
        if "checked" in item:
            action.setCheckable(True)
            action.setChecked(bool(item.get("checked")))
        action_map[action] = str(item.get("id") or "")
    chosen = menu.exec(global_pos)
    return action_map.get(chosen)


def show_context_menu(parent, global_pos: QPoint, items: list[dict]) -> str | None:
    normalized = [dict(item or {}) for item in list(items or [])]
    if not normalized:
        return None
    if _quick_available(MENU_QML):
        try:
            dialog = _QuickContextMenuDialog(_widget_parent(parent), normalized)
            dialog.move(QPoint(global_pos))
            dialog.exec()
            return dialog.selected_id()
        except Exception:
            pass
    return _fallback_qmenu(parent, global_pos, normalized)


def install_qmessagebox_hooks() -> None:
    global _HOOKS_INSTALLED
    if _HOOKS_INSTALLED:
        return

    def _wrap(icon):
        def _runner(parent=None, title="", text="", buttons=QMessageBox.StandardButton.Ok, defaultButton=QMessageBox.StandardButton.NoButton):
            if defaultButton != QMessageBox.StandardButton.NoButton:
                default = defaultButton
            else:
                resolved = _button_bits(buttons)
                default = resolved[0] if resolved else QMessageBox.StandardButton.Ok
            return exec_message_box(parent, str(title or ""), str(text or ""), icon=icon, buttons=buttons, default=default)

        return _runner

    for name in ("information", "warning", "critical", "question"):
        _ORIGINAL_QMESSAGEBOX_METHODS[name] = getattr(QMessageBox, name)
    QMessageBox.information = staticmethod(_wrap(QMessageBox.Icon.Information))
    QMessageBox.warning = staticmethod(_wrap(QMessageBox.Icon.Warning))
    QMessageBox.critical = staticmethod(_wrap(QMessageBox.Icon.Critical))
    QMessageBox.question = staticmethod(_wrap(QMessageBox.Icon.Question))
    _HOOKS_INSTALLED = True
