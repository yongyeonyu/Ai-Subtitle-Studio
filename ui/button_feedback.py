# Version: 03.24.03
# Phase: PHASE2
"""Application-wide visual feedback for button clicks."""
from __future__ import annotations

import sys

from PyQt6.QtCore import QObject, QEvent, QEventLoop, QTimer, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QAbstractButton, QGraphicsDropShadowEffect


class ButtonClickFeedbackFilter(QObject):
    """Add a short glow to buttons so clicks are visually confirmed."""

    def __init__(self, parent=None, *, native_fast: bool | None = None):
        super().__init__(parent)
        self.native_fast = sys.platform == "darwin" if native_fast is None else bool(native_fast)
        self._flushing_press = False

    def eventFilter(self, obj, event):  # noqa: N802 - Qt override name
        try:
            if isinstance(obj, QAbstractButton):
                self._prepare_button(obj)
                if self._is_feedback_event(event):
                    self.flash_button(obj)
                elif self.native_fast and self._is_release_event(event):
                    self._flush_button_pressed_paint(obj)
        except RuntimeError:
            return False
        return False

    def flash_button(self, button: QAbstractButton, *, duration_ms: int = 150) -> None:
        try:
            if not button.isEnabled() or not button.isVisible():
                return
        except RuntimeError:
            return
        self._prepare_button(button)

        restore_timer = getattr(button, "_click_feedback_restore_timer", None)
        if restore_timer is not None:
            try:
                restore_timer.stop()
            except RuntimeError:
                pass
        else:
            restore_timer = QTimer(button)
            restore_timer.setSingleShot(True)
            restore_timer.timeout.connect(
                lambda b=button: self._restore_button(
                    b,
                    getattr(b, "_click_feedback_restore_effect", None),
                )
            )
            button._click_feedback_restore_timer = restore_timer

        current_effect = button.graphicsEffect()
        feedback_effect = getattr(button, "_click_feedback_effect", None)
        effect = None
        if self.native_fast:
            button._click_feedback_preserve_existing_effect = current_effect is not None
        elif current_effect is not None and current_effect is not feedback_effect:
            button._click_feedback_preserve_existing_effect = True
        else:
            button._click_feedback_preserve_existing_effect = False
            effect = QGraphicsDropShadowEffect(button)
            effect.setBlurRadius(24)
            effect.setOffset(0, 0)
            effect.setColor(QColor(116, 169, 255, 220))
            button._click_feedback_effect = effect
            button.setGraphicsEffect(effect)
        button.setProperty("_click_feedback_active", True)
        if self.native_fast:
            self._flush_button_pressed_paint(button)

        button._click_feedback_restore_effect = effect
        restore_timer.start(max(40, int(duration_ms or 150)))

    def _restore_button(self, button: QAbstractButton, effect: QGraphicsDropShadowEffect | None = None) -> None:
        try:
            restore_timer = getattr(button, "_click_feedback_restore_timer", None)
            if restore_timer is not None:
                restore_timer.stop()
            if not bool(getattr(button, "_click_feedback_preserve_existing_effect", False)):
                if effect is None or button.graphicsEffect() is effect:
                    button.setGraphicsEffect(None)
            button._click_feedback_effect = None
            button._click_feedback_restore_effect = None
            button._click_feedback_preserve_existing_effect = False
            button.setProperty("_click_feedback_active", False)
        except RuntimeError:
            pass

    def _prepare_button(self, button: QAbstractButton) -> None:
        if not self.native_fast:
            return
        try:
            if bool(getattr(button, "_mac_fast_button_prepared", False)):
                return
            button.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            button.setMouseTracking(True)
            button._mac_fast_button_prepared = True
        except RuntimeError:
            pass

    def _flush_button_pressed_paint(self, button: QAbstractButton) -> None:
        if self._flushing_press:
            return
        app = QApplication.instance()
        if app is None:
            return
        self._flushing_press = True
        try:
            button.repaint()
            app.processEvents(
                QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
                | QEventLoop.ProcessEventsFlag.ExcludeSocketNotifiers,
                1,
            )
        except RuntimeError:
            pass
        except Exception:
            pass
        finally:
            self._flushing_press = False

    def _is_feedback_event(self, event) -> bool:
        event_type = event.type()
        if event_type == QEvent.Type.MouseButtonPress:
            try:
                return event.button() == Qt.MouseButton.LeftButton
            except Exception:
                return True
        if event_type == QEvent.Type.KeyPress:
            try:
                return event.key() in (
                    Qt.Key.Key_Space,
                    Qt.Key.Key_Return,
                    Qt.Key.Key_Enter,
                )
            except Exception:
                return False
        return False

    def _is_release_event(self, event) -> bool:
        event_type = event.type()
        if event_type == QEvent.Type.MouseButtonRelease:
            try:
                return event.button() == Qt.MouseButton.LeftButton
            except Exception:
                return True
        if event_type == QEvent.Type.KeyRelease:
            try:
                return event.key() in (
                    Qt.Key.Key_Space,
                    Qt.Key.Key_Return,
                    Qt.Key.Key_Enter,
                )
            except Exception:
                return False
        return False


def install_button_click_feedback(app: QApplication | None = None) -> ButtonClickFeedbackFilter | None:
    """Install the shared button feedback filter once per QApplication."""
    app = app or QApplication.instance()
    if app is None:
        return None
    existing = getattr(app, "_button_click_feedback_filter", None)
    if isinstance(existing, ButtonClickFeedbackFilter):
        return existing
    feedback_filter = ButtonClickFeedbackFilter(app)
    app.installEventFilter(feedback_filter)
    app._button_click_feedback_filter = feedback_filter
    return feedback_filter


__all__ = ["ButtonClickFeedbackFilter", "install_button_click_feedback"]
