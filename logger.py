# Version: 02.02.01
# Phase: PHASE1-B
"""
logger.py - PyQt6 버전 (크PD 변환)
싱글톤 AppLogger: pyqtSignal로 UI 스레드에 안전하게 전달
tkinter root.after() → QObject + pyqtSignal 패턴으로 교체
"""
import threading
from PyQt6.QtCore import QObject, pyqtSignal


class _LogEmitter(QObject):
    """UI 스레드로 로그를 안전하게 emit하기 위한 QObject"""
    log_signal = pyqtSignal(str)


class AppLogger:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._emitter = _LogEmitter()
                inst._ui_callback = None
                cls._instance = inst
        return cls._instance

    def set_ui_callback(self, callback):
        """MainWindow.append_log 등록. 중복 방지."""
        if self._ui_callback:
            try:
                self._emitter.log_signal.disconnect(self._ui_callback)
            except Exception:
                pass
        self._ui_callback = callback
        self._emitter.log_signal.connect(callback)

    def clear_ui_callback(self):
        if self._ui_callback:
            try:
                self._emitter.log_signal.disconnect(self._ui_callback)
            except Exception:
                pass
            self._ui_callback = None

    def log(self, msg: str):
        print(msg)
        try:
            self._emitter.log_signal.emit(msg)
        except Exception:
            pass

    def info(self, msg: str):  self.log(msg)
    def error(self, msg: str): self.log(msg)
    def warning(self, msg: str): self.log(msg)


def get_logger() -> AppLogger:
    return AppLogger()
