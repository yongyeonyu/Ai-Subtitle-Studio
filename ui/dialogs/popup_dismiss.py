from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QEvent, QObject, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QWidget


class OutsideClickDismissFilter(QObject):
    """Dismiss transient popup widgets when the user clicks outside them."""

    def __init__(self, popup: QWidget, close_callback: Callable[[], None] | None = None, *, consume: bool = True):
        super().__init__(popup)
        self._popup = popup
        self._close_callback = close_callback
        self._consume = bool(consume)
        self._installed = False
        self._closing = False

    def install(self) -> None:
        if self._installed:
            return
        app = QApplication.instance()
        if app is None:
            return
        app.installEventFilter(self)
        self._installed = True

    def uninstall(self) -> None:
        if not self._installed:
            return
        app = QApplication.instance()
        if app is not None:
            try:
                app.removeEventFilter(self)
            except RuntimeError:
                pass
        self._installed = False

    def _global_pos(self, event):
        if hasattr(event, "globalPosition"):
            try:
                return event.globalPosition().toPoint()
            except Exception:
                pass
        if hasattr(event, "globalPos"):
            try:
                return event.globalPos()
            except Exception:
                pass
        return None

    def _dismiss(self) -> None:
        if self._closing:
            return
        popup = self._popup
        if popup is None or not popup.isVisible():
            return
        self._closing = True

        def _close_now() -> None:
            try:
                callback = self._close_callback
                if callback is not None:
                    callback()
                else:
                    popup.close()
            finally:
                self._closing = False

        QTimer.singleShot(0, _close_now)

    def eventFilter(self, watched, event):  # noqa: N802 - Qt override
        event_type = event.type()
        popup = self._popup
        if popup is None or not popup.isVisible():
            return False

        if event_type in {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonDblClick,
            QEvent.Type.TouchBegin,
        }:
            pos = self._global_pos(event)
            if pos is not None and not popup.frameGeometry().contains(pos):
                self._dismiss()
                return self._consume
        elif event_type == QEvent.Type.WindowDeactivate and popup.windowType() == Qt.WindowType.Popup:
            self._dismiss()
        return False


def install_outside_click_dismiss(
    popup: QWidget,
    close_callback: Callable[[], None] | None = None,
    *,
    consume: bool = True,
) -> OutsideClickDismissFilter:
    existing = getattr(popup, "_outside_click_dismiss_filter", None)
    if existing is not None and hasattr(existing, "uninstall"):
        existing.uninstall()
    event_filter = OutsideClickDismissFilter(popup, close_callback, consume=consume)
    setattr(popup, "_outside_click_dismiss_filter", event_filter)
    event_filter.install()
    try:
        popup.destroyed.connect(event_filter.uninstall)
    except Exception:
        pass
    return event_filter


def uninstall_outside_click_dismiss(popup: QWidget) -> None:
    event_filter = getattr(popup, "_outside_click_dismiss_filter", None)
    if event_filter is not None and hasattr(event_filter, "uninstall"):
        event_filter.uninstall()
    try:
        setattr(popup, "_outside_click_dismiss_filter", None)
    except Exception:
        pass
