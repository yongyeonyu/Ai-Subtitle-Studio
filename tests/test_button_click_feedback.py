# Version: 03.24.03
# Phase: PHASE2
import unittest
from pathlib import Path

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
        self.assertIn("border: 2px solid #D7EBFF", tool_button_style("toolbar"))

    def test_global_menu_qml_has_immediate_press_feedback(self):
        qml_path = Path(__file__).resolve().parents[1] / "ui" / "qml" / "global_menu_bar.qml"
        qml = qml_path.read_text(encoding="utf-8")

        self.assertIn("property string activeActionId", qml)
        self.assertIn("function flashAction", qml)
        self.assertIn("onPressed: root.flashAction", qml)
        self.assertIn("function pressFillFor", qml)
        self.assertIn("activePress ? 0.91", qml)
        self.assertIn('border.color: activePress ? "#D7EBFF"', qml)

    def test_global_menu_qml_has_hover_feedback(self):
        qml_path = Path(__file__).resolve().parents[1] / "ui" / "qml" / "global_menu_bar.qml"
        qml = qml_path.read_text(encoding="utf-8")

        self.assertIn("function hoverFillFor", qml)
        self.assertIn("function hoverBorderFor", qml)
        self.assertIn("property bool hoverActive", qml)
        self.assertEqual(qml.count("hoverEnabled: true"), 3)
        self.assertEqual(qml.count("cursorShape: Qt.PointingHandCursor"), 3)
        self.assertIn("hoverActive ? 1.035 : 1.0", qml)
        self.assertIn("hoverActive ? root.hoverBorderFor", qml)

    def test_global_menu_qml_uses_single_colored_korean_label(self):
        qml_path = Path(__file__).resolve().parents[1] / "ui" / "qml" / "global_menu_bar.qml"
        qml = qml_path.read_text(encoding="utf-8")

        self.assertIn("function labelColorFor", qml)
        self.assertNotIn("function badgeFor", qml)
        self.assertNotIn("centerBadge", qml)
        self.assertNotIn("root.badgeFor", qml)
        self.assertIn("color: root.labelColorFor(leftButtonRoot, modelData)", qml)
        self.assertIn("color: root.labelColorFor(centerButtonRoot, modelData)", qml)
        self.assertIn("color: root.labelColorFor(rightButtonRoot, modelData)", qml)

    def test_global_menu_bar_user_labels_are_korean(self):
        menu_path = Path(__file__).resolve().parents[1] / "ui" / "menu_bar.py"
        source = menu_path.read_text(encoding="utf-8")

        self.assertIn('("음성", "mic"', source)
        self.assertIn('self._action_button("실행취소"', source)
        self.assertIn('self._action_button("다시실행"', source)
        self.assertNotIn('self._action_button("Undo"', source)
        self.assertNotIn('self._action_button("Redo"', source)


if __name__ == "__main__":
    unittest.main()
