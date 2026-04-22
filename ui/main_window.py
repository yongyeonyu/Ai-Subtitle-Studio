# Version: 02.02.00
# Phase: PHASE1-B
"""
ui/main_window.py
하위 호환 shim — 기존 `from ui.main_window import MainWindow` 유지
실제 구현은 ui/main/ 패키지로 이전됨
"""
from ui.main.main_window import MainWindow  # noqa: F401

__all__ = ["MainWindow"]
