import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def pytest_configure(config):
    try:
        from PyQt6.QtWidgets import QWidget
    except Exception:
        return
    if getattr(QWidget, "_ai_subtitle_studio_safe_delete_later", False):
        return

    def _safe_test_delete_later(widget):
        try:
            widget.close()
        except RuntimeError:
            return
        try:
            widget.setParent(None)
        except RuntimeError:
            pass

    QWidget._ai_subtitle_studio_safe_delete_later = True
    QWidget._ai_subtitle_studio_original_delete_later = QWidget.deleteLater
    QWidget.deleteLater = _safe_test_delete_later
