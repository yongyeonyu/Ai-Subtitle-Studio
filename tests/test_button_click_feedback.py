# Version: 03.24.03
# Phase: PHASE2
import unittest

from PyQt6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QPushButton

from ui.button_feedback import ButtonClickFeedbackFilter, install_button_click_feedback
from ui.style import button_style, settings_button_style, tool_button_style


class ButtonClickFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_install_button_click_feedback_is_idempotent(self):
        first = install_button_click_feedback(self.app)
        second = install_button_click_feedback(self.app)

        self.assertIs(first, second)

    def test_flash_button_marks_click_feedback_then_restores(self):
        button = QPushButton("실행")
        button.show()
        self.app.processEvents()
        feedback = ButtonClickFeedbackFilter()

        feedback.flash_button(button, duration_ms=1000)

        self.assertTrue(button.property("_click_feedback_active"))
        self.assertIsNotNone(button.graphicsEffect())

        feedback._restore_button(button, button.graphicsEffect())

        self.assertFalse(button.property("_click_feedback_active"))
        self.assertIsNone(button.graphicsEffect())
        button.close()
        button.deleteLater()

    def test_flash_button_preserves_existing_graphics_effect(self):
        button = QPushButton("효과 있음")
        existing = QGraphicsDropShadowEffect(button)
        button.setGraphicsEffect(existing)
        button.show()
        self.app.processEvents()
        feedback = ButtonClickFeedbackFilter()

        feedback.flash_button(button, duration_ms=1000)

        self.assertTrue(button.property("_click_feedback_active"))
        self.assertIs(button.graphicsEffect(), existing)

        feedback._restore_button(button)

        self.assertFalse(button.property("_click_feedback_active"))
        self.assertIs(button.graphicsEffect(), existing)
        button.close()
        button.deleteLater()

    def test_shared_button_styles_include_pressed_feedback(self):
        self.assertIn("QPushButton:pressed", button_style("toolbar"))
        self.assertIn("QPushButton:pressed", button_style("primary"))
        self.assertIn("QPushButton:pressed", settings_button_style("toolbar"))
        self.assertIn("QToolButton:pressed", tool_button_style("toolbar"))


if __name__ == "__main__":
    unittest.main()
