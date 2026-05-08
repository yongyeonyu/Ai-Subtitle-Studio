# Version: 03.24.03
# Phase: PHASE2
"""Application-wide visual feedback for button clicks."""
from __future__ import annotations

from PyQt6.QtCore import QObject, QEvent, QTimer, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QAbstractButton, QGraphicsDropShadowEffect


class ButtonClickFeedbackFilter(QObject):
    """Add a short glow to buttons so clicks are visually confirmed."""

    def eventFilter(self, obj, event):  # noqa: N802 - Qt override name
        try:
            if isinstance(obj, QAbstractButton) and self._is_feedback_event(event):
                self.flash_button(obj)
        except RuntimeError:
            return False
        return False

    def flash_button(self, button: QAbstractButton, *, duration_ms: int = 150) -> None:
        try:
            if not button.isEnabled() or not button.isVisible():
                return
        except RuntimeError:
            return

        restore_timer = getattr(button, "_click_feedback_restore_timer", None)
        if restore_timer is not None:
            try:
                restore_timer.stop()
                restore_timer.deleteLater()
            except RuntimeError:
                pass

        current_effect = button.graphicsEffect()
        feedback_effect = getattr(button, "_click_feedback_effect", None)
        effect = None
        if current_effect is not None and current_effect is not feedback_effect:
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

        timer = QTimer(button)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda b=button, e=effect: self._restore_button(b, e))
        button._click_feedback_restore_timer = timer
        timer.start(max(40, int(duration_ms or 150)))

    def _restore_button(self, button: QAbstractButton, effect: QGraphicsDropShadowEffect | None = None) -> None:
        try:
            restore_timer = getattr(button, "_click_feedback_restore_timer", None)
            if restore_timer is not None:
                restore_timer.deleteLater()
                button._click_feedback_restore_timer = None
            if not bool(getattr(button, "_click_feedback_preserve_existing_effect", False)):
                if effect is None or button.graphicsEffect() is effect:
                    button.setGraphicsEffect(None)
            button._click_feedback_effect = None
            button._click_feedback_preserve_existing_effect = False
            button.setProperty("_click_feedback_active", False)
        except RuntimeError:
            pass

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
