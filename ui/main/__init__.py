# Version: 02.03.00
# Phase: PHASE1-B

# Phase: PHASE1-B
"""
ui/main/__init__.py
Main 패키지 — MainWindow 재수출

Keep the package export lazy so importing leaf mixins like ``ui.home_ui`` does
not immediately loop back into ``ui.main.main_window`` during test collection.
"""

__all__ = ["MainWindow"]


def __getattr__(name):
    if name == "MainWindow":
        from ui.main.main_window import MainWindow

        return MainWindow
    raise AttributeError(name)
