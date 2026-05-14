import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.main.main_window import MainWindow


class QueueSignalPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_main_window_accepts_structured_queue_signals(self):
        window = MainWindow()
        try:
            self.assertFalse(hasattr(window, "_sig_update_queue"))
            self.assertFalse(hasattr(window, "_sig_update_queue_header"))
            window.init_queue_list(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4"])
            window._sig_update_queue_payload.emit(
                {
                    "row": 1,
                    "status": "대기 중",
                    "eta": "20",
                    "info": "1920x1080",
                    "duration": "00:10",
                }
            )
            window._sig_update_queue_header_payload.emit(
                {"idx": 2, "total": 2, "pct": 50, "eta": "2분 10초"}
            )

            self.assertEqual(window.queue_table.item(1, 2).text(), "1920x1080")
            self.assertEqual(window.queue_table.item(1, 3).text(), "00:10")
            self.assertEqual(window.queue_table.item(1, 4).text(), "00:20")
            self.assertIn("(2/2) - 50%", window.queue_header_lbl.text())
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
