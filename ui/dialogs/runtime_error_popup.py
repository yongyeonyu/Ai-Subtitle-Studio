from __future__ import annotations

import os
import time
import traceback

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMessageBox

from ui.dialogs.message_box import show_message

_POPUP_DEDUP_WINDOW_SEC = 4.0
_LAST_POPUP_SIGNATURE = ""
_LAST_POPUP_AT = 0.0
_RUNTIME_POPUP_BRIDGE = None


class _RuntimeErrorPopupBridge(QObject):
    popup_requested = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.popup_requested.connect(self._show_popup, Qt.ConnectionType.QueuedConnection)

    def _show_popup(self, title: str, text: str) -> None:
        _show_popup_message(title, text)


def _runtime_popup_available() -> bool:
    app = QApplication.instance()
    if app is None:
        return False
    try:
        platform_name = str(app.platformName() or "").strip().lower()
    except Exception:
        return False
    return platform_name not in {"offscreen", "minimal"}


def _error_summary_and_action(exc_type, exc_value) -> tuple[str, str]:
    try:
        if issubclass(exc_type, FileNotFoundError):
            return (
                "필요한 파일이나 폴더를 찾지 못했습니다.",
                "선택한 파일이 이동되었거나 삭제되었는지 확인해 주세요.",
            )
        if issubclass(exc_type, PermissionError):
            return (
                "파일 또는 폴더 접근 권한이 부족합니다.",
                "읽기/쓰기 권한과 저장 위치를 확인해 주세요.",
            )
        if issubclass(exc_type, TimeoutError):
            return (
                "응답을 기다리다가 시간이 초과되었습니다.",
                "잠시 후 다시 시도하거나 동시에 실행 중인 작업 수를 줄여 주세요.",
            )
        if issubclass(exc_type, ConnectionError):
            return (
                "네트워크 또는 로컬 서비스 연결에 실패했습니다.",
                "Ollama, 외부 API, 또는 로컬 보조 서비스가 실행 중인지 확인해 주세요.",
            )
        if issubclass(exc_type, MemoryError):
            return (
                "메모리가 부족해 작업을 계속하지 못했습니다.",
                "다른 무거운 앱이나 모델을 정리한 뒤 다시 시도해 주세요.",
            )
        if issubclass(exc_type, OSError):
            return (
                "파일 또는 시스템 자원 처리 중 문제가 발생했습니다.",
                "경로 유효성, 디스크 상태, 또는 외부 장치 연결 상태를 확인해 주세요.",
            )
    except Exception:
        pass
    detail = str(exc_value or "").strip().lower()
    if "cuda" in detail or "metal" in detail or "mps" in detail:
        return (
            "가속 장치 초기화 또는 연동 중 문제가 발생했습니다.",
            "가속 설정을 다시 확인하거나 앱을 재실행한 뒤 다시 시도해 주세요.",
        )
    return (
        "앱 내부에서 예상치 못한 오류가 발생했습니다.",
        "같은 작업에서 반복되면 아래 로그 파일과 함께 알려 주시면 원인 추적이 빨라집니다.",
    )


def _compact_error_message(exc_value) -> str:
    message = " ".join(str(exc_value or "").split())
    if not message:
        return "예외 메시지가 비어 있습니다."
    if len(message) > 260:
        return message[:257] + "..."
    return message


def _trace_location(exc_traceback) -> str:
    if exc_traceback is None:
        return ""
    try:
        frames = traceback.extract_tb(exc_traceback)
    except Exception:
        return ""
    if not frames:
        return ""
    last = frames[-1]
    filename = os.path.basename(str(last.filename or ""))
    function_name = str(last.name or "<module>")
    return f"{filename}:{int(last.lineno)} ({function_name})"


def build_runtime_error_message(
    exc_type,
    exc_value,
    exc_traceback,
    *,
    source: str = "ui",
    thread_name: str = "",
    log_path: str = "",
) -> tuple[str, str]:
    summary, action = _error_summary_and_action(exc_type, exc_value)
    message = _compact_error_message(exc_value)
    location = _trace_location(exc_traceback)
    stage = "앱 동작 중"
    title = "앱 오류 안내"
    if source == "thread":
        stage = f"백그라운드 작업({thread_name or 'worker'}) 중"
        title = "백그라운드 작업 오류"
    elif source == "unraisable":
        stage = "정리 또는 종료 처리 중"
        title = "앱 정리 중 오류"
    lines = [
        f"{stage} 문제가 발생했습니다.",
        "",
        "무슨 문제인가요?",
        f"- {summary}",
        "",
        "확인된 오류 정보",
        f"- 오류 유형: {getattr(exc_type, '__name__', str(exc_type))}",
        f"- 오류 메시지: {message}",
    ]
    if location:
        lines.append(f"- 위치: {location}")
    lines.extend(
        [
            "",
            "영향 가능성",
            "- 현재 작업 일부가 끝까지 반영되지 않았을 수 있습니다.",
            "- 앱은 가능한 범위에서 계속 실행을 시도합니다.",
            "",
            "어떻게 하면 되나요?",
            f"- {action}",
            "- 같은 작업에서 반복되면 앱을 다시 실행한 뒤 다시 시도해 주세요.",
        ]
    )
    if log_path:
        lines.append(f"- 로그 파일: {log_path}")
    return title, "\n".join(lines)


def install_runtime_error_popup_bridge(app=None):
    global _RUNTIME_POPUP_BRIDGE
    current_app = app or QApplication.instance()
    if current_app is None:
        return None
    if _RUNTIME_POPUP_BRIDGE is None:
        _RUNTIME_POPUP_BRIDGE = _RuntimeErrorPopupBridge(parent=current_app)
    return _RUNTIME_POPUP_BRIDGE


def _show_popup_message(title: str, text: str) -> None:
    show_message(
        None,
        title,
        text,
        icon=QMessageBox.Icon.Critical,
        buttons=QMessageBox.StandardButton.Ok,
        default=QMessageBox.StandardButton.Ok,
    )


def _should_suppress_duplicate_popup(signature: str) -> bool:
    global _LAST_POPUP_SIGNATURE, _LAST_POPUP_AT
    now = time.monotonic()
    if signature == _LAST_POPUP_SIGNATURE and (now - _LAST_POPUP_AT) < _POPUP_DEDUP_WINDOW_SEC:
        return True
    _LAST_POPUP_SIGNATURE = signature
    _LAST_POPUP_AT = now
    return False


def show_runtime_error_popup(title: str, text: str) -> bool:
    app = QApplication.instance()
    if app is None or not _runtime_popup_available():
        return False
    signature = f"{title}\n{text}"
    if _should_suppress_duplicate_popup(signature):
        return False
    bridge = install_runtime_error_popup_bridge(app)
    if bridge is None:
        return False
    try:
        if app.thread() == QThread.currentThread():
            bridge._show_popup(title, text)
        else:
            bridge.popup_requested.emit(title, text)
    except Exception:
        return False
    return True


def show_captured_exception_popup(
    exc_type,
    exc_value,
    exc_traceback,
    *,
    source: str = "ui",
    thread_name: str = "",
    log_path: str = "",
) -> bool:
    title, text = build_runtime_error_message(
        exc_type,
        exc_value,
        exc_traceback,
        source=source,
        thread_name=thread_name,
        log_path=log_path,
    )
    return show_runtime_error_popup(title, text)


def _reset_runtime_error_popup_state_for_tests() -> None:
    global _LAST_POPUP_SIGNATURE, _LAST_POPUP_AT, _RUNTIME_POPUP_BRIDGE
    _LAST_POPUP_SIGNATURE = ""
    _LAST_POPUP_AT = 0.0
    _RUNTIME_POPUP_BRIDGE = None


__all__ = [
    "build_runtime_error_message",
    "install_runtime_error_popup_bridge",
    "show_captured_exception_popup",
    "show_runtime_error_popup",
]
