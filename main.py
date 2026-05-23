# Version: 03.09.02
# Phase: PHASE1-B
# ruff: noqa: E402
import sys
import os
import socket
import faulthandler
import threading
import time
import warnings
import traceback

try:
    faulthandler.enable(all_threads=True)
except Exception:
    pass

os.environ.setdefault(
    "QT_LOGGING_RULES",
    "qt.multimedia.*=false;qt.multimedia.ffmpeg.*=false;qt.qpa.fonts=false",
)
os.environ.setdefault("AV_LOG_LEVEL", "16")

# PyQt can be configured externally to abort the whole process when a Python
# slot raises. That is useful for local debugger sessions but too dangerous for
# the app: one recoverable UI exception becomes a macOS crash report. Keep the
# explicit opt-in for debugging, otherwise force the production-safe behavior.
if str(os.environ.get("AI_SUBTITLE_ALLOW_PYQT_FATAL_EXCEPTIONS", "") or "").strip().lower() not in {
    "1",
    "true",
    "yes",
    "on",
}:
    os.environ.pop("PYQT_FATAL_EXCEPTIONS", None)

_STDERR_NOISE_FILTER_INSTALLED = False
_STDERR_NOISE_FILTER_ORIGINAL_FD = None
_STDERR_NOISE_PATTERNS = (
    b"TSM AdjustCapsLockLEDForKeyTransitionHandling",
    b"error messaging the mach port for IMKCFRunLoopWakeUpReliable",
    b"Color primaries reserved is not supported.",
)
_PREV_SYS_EXCEPTHOOK = sys.excepthook


def _runtime_exception_log_path() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    folder = os.path.join(base, "output", "runtime")
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception:
        folder = base
    return os.path.join(folder, "qt_slot_exceptions.log")


def _log_uncaught_exception(exc_type, exc_value, exc_traceback) -> None:
    try:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        with open(_runtime_exception_log_path(), "a", encoding="utf-8") as handle:
            handle.write("\n--- uncaught Python/Qt exception ---\n")
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")
    except Exception:
        pass


def _safe_excepthook(exc_type, exc_value, exc_traceback) -> None:
    _log_uncaught_exception(exc_type, exc_value, exc_traceback)
    try:
        if _PREV_SYS_EXCEPTHOOK is not None and _PREV_SYS_EXCEPTHOOK is not _safe_excepthook:
            _PREV_SYS_EXCEPTHOOK(exc_type, exc_value, exc_traceback)
            return
    except Exception:
        pass
    try:
        traceback.print_exception(exc_type, exc_value, exc_traceback)
    except Exception:
        pass


sys.excepthook = _safe_excepthook


def _env_flag_enabled(name: str, default: bool = True) -> bool:
    value = str(os.environ.get(name, "") or "").strip().lower()
    if not value:
        return bool(default)
    if value in {"1", "true", "yes", "on", "enabled", "enable"}:
        return True
    if value in {"0", "false", "no", "off", "disabled", "disable"}:
        return False
    return bool(default)


def _install_macos_stderr_noise_filter() -> None:
    """Drop noisy macOS stderr lines while preserving real errors."""
    global _STDERR_NOISE_FILTER_INSTALLED, _STDERR_NOISE_FILTER_ORIGINAL_FD
    if _STDERR_NOISE_FILTER_INSTALLED:
        return
    if sys.platform != "darwin":
        return
    if not _env_flag_enabled("AI_SUBTITLE_SUPPRESS_MACOS_TSM_LOG", True):
        return
    try:
        read_fd, write_fd = os.pipe()
        original_fd = os.dup(2)
        os.set_inheritable(read_fd, False)
        os.set_inheritable(write_fd, False)
        os.set_inheritable(original_fd, False)
        os.dup2(write_fd, 2)
        os.close(write_fd)
        _STDERR_NOISE_FILTER_ORIGINAL_FD = original_fd
        _STDERR_NOISE_FILTER_INSTALLED = True
    except Exception:
        return

    def _drain_stderr_pipe() -> None:
        import select

        pending = b""
        try:
            while True:
                readable, _, _ = select.select([read_fd], [], [], 0.25)
                if not readable:
                    if pending and not any(pattern in pending for pattern in _STDERR_NOISE_PATTERNS):
                        os.write(original_fd, pending)
                        pending = b""
                    continue
                chunk = os.read(read_fd, 4096)
                if not chunk:
                    break
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    if any(pattern in line for pattern in _STDERR_NOISE_PATTERNS):
                        continue
                    os.write(original_fd, line + b"\n")
                if len(pending) > 8192:
                    if not any(pattern in pending for pattern in _STDERR_NOISE_PATTERNS):
                        os.write(original_fd, pending)
                    pending = b""
            if pending and not any(pattern in pending for pattern in _STDERR_NOISE_PATTERNS):
                os.write(original_fd, pending)
        except Exception:
            pass
        finally:
            try:
                os.dup2(original_fd, 2)
            except Exception:
                pass
            try:
                os.close(read_fd)
            except Exception:
                pass

    threading.Thread(
        target=_drain_stderr_pipe,
        daemon=True,
        name="macos-stderr-noise-filter",
    ).start()


_install_macos_stderr_noise_filter()

warnings.filterwarnings(
    "ignore",
    message=r".*pynvml package is deprecated.*",
    category=FutureWarning,
)

from core.runtime import config
from core.automation.app_command_protocol import build_command_payload, send_command_to_app
from core.automation.app_command_server import LocalAppCommandServer

if getattr(config, "MACBOOK_ONLY_APP", False) and not getattr(config, "IS_MAC", False):
    sys.stderr.write("AI Subtitle Studio macOS native branch requires macOS.\n")
    sys.exit(78)

from core.performance import (
    configure_native_runtime,
    configure_qt_gpu_rendering_before_app,
    configure_qt_runtime,
    configure_qt_tooltip_theme,
    qt_tooltip_stylesheet,
)
from core.platform_compat import (
    cleanup_app_child_processes,
    cleanup_app_runtime_processes,
    cleanup_stale_preview_proxy_processes,
)

try:
    from core.settings import load_settings as _load_runtime_settings

    _NATIVE_RUNTIME_META = configure_native_runtime(_load_runtime_settings())
except Exception:
    _NATIVE_RUNTIME_META = configure_native_runtime()

configure_qt_gpu_rendering_before_app()

from PyQt6.QtCore import QTimer, qInstallMessageHandler
from PyQt6.QtWidgets import QApplication
from core.runtime.logger import get_logger
from ui.button_feedback import install_button_click_feedback
from ui.dialogs.message_box import install_qmessagebox_hooks

try:
    get_logger().install_stream_capture()
except Exception:
    pass

_QT_APP_SHUTTING_DOWN = False
_PREV_QT_MESSAGE_HANDLER = None
_instance_command_server = None


def _qt_message_handler(mode, context, message):
    text = str(message or "")
    if _QT_APP_SHUTTING_DOWN:
        if text.startswith("QObject::disconnect: wildcard call disconnects from destroyed signal of QFFmpeg::"):
            return
        if text.startswith("QUnifiedTimer::stopAnimationDriver: driver is not running"):
            return
        if text.startswith("QPainter::") and (
            "Painter not active" in text or "Paint device returned engine == 0" in text
        ):
            return
    if _PREV_QT_MESSAGE_HANDLER is not None:
        _PREV_QT_MESSAGE_HANDLER(mode, context, message)

_instance_socket = None


def _activate_existing_instance() -> None:
    try:
        send_command_to_app(build_command_payload("show-home"), timeout_sec=0.35)
    except Exception:
        pass


def check_single_instance():
    """프로그램 중복 실행을 완벽하게 차단하는 함수"""
    global _instance_socket, _instance_command_server
    _instance_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        _instance_socket.bind(('127.0.0.1', config.INSTANCE_PORT))
        _instance_command_server = LocalAppCommandServer(_instance_socket)
        _instance_command_server.start()
    except socket.error:
        try:
            _instance_socket.close()
        except Exception:
            pass
        _instance_socket = None
        _activate_existing_instance()
        try:
            sys.stderr.write(f"{config.APP_NAME} is already running; duplicate launcher exiting.\n")
        except Exception:
            pass
        sys.exit(0)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from ui.main.main_window import MainWindow
from core.path_manager import get_recent_folders, add_recent_folder


def _start_ollama_runtime_for_app_launch() -> None:
    def _run():
        try:
            from core.llm.ollama_provider import ensure_ollama_server

            ensure_ollama_server(logger=get_logger(), wait_sec=8.0)
        except Exception as exc:
            try:
                get_logger().log(f"⚠️ 앱 시작: Ollama 자동 실행 실패: {exc}")
            except Exception:
                pass

    try:
        threading.Thread(
            target=_run,
            daemon=True,
            name="app-start-ollama-runtime",
        ).start()
    except Exception:
        _run()


def _cleanup_stale_preview_proxy_processes_for_app_launch_async() -> None:
    def _run():
        try:
            cleaned = cleanup_stale_preview_proxy_processes(timeout_sec=0.05 if getattr(config, "IS_MAC", False) else 0.2)
            if cleaned:
                get_logger().log(f"🧹 이전 미리보기 프록시 ffmpeg {cleaned}개 정리 완료")
        except Exception:
            pass

    try:
        threading.Thread(
            target=_run,
            daemon=True,
            name="app-start-preview-proxy-cleanup",
        ).start()
    except Exception:
        _run()


def main():
    launch_started = time.perf_counter()
    logger = get_logger()
    logger.log_perf(
        "app.main",
        event="enter",
        stage="runtime",
        offscreen=str(os.environ.get("QT_QPA_PLATFORM", "")).lower() == "offscreen",
        argv=len(sys.argv),
    )
    global _PREV_QT_MESSAGE_HANDLER
    app = QApplication(sys.argv)
    logger.log_perf("app.main", event="qapplication_ready", elapsed_ms=(time.perf_counter() - launch_started) * 1000.0)
    install_qmessagebox_hooks()
    _PREV_QT_MESSAGE_HANDLER = qInstallMessageHandler(_qt_message_handler)
    configure_qt_runtime()
    logger.log_perf("app.main", event="qt_runtime_ready", elapsed_ms=(time.perf_counter() - launch_started) * 1000.0)
    _cleanup_stale_preview_proxy_processes_for_app_launch_async()
    try:
        profile = _NATIVE_RUNTIME_META.get("profile", "balanced")
        threads = _NATIVE_RUNTIME_META.get("native_threads", "-")
        get_logger().log(f"⚙️ 네이티브 런타임 프로필: {profile}, threads={threads}")
    except Exception:
        pass

    app.setStyleSheet(f"""
        QWidget {{
            background-color: {config.BG};
            color: {config.FG};
            font-family: "{config.FONT}";
        }}
        QScrollBar:vertical {{
            background: {config.BG2}; width: 8px; border-radius: 4px;
        }}
        QScrollBar::handle:vertical {{
            background: #555555; border-radius: 4px; min-height: 20px;
        }}
        QScrollBar:horizontal {{
            background: {config.BG2}; height: 8px; border-radius: 4px;
        }}
        QScrollBar::handle:horizontal {{
            background: #555555; border-radius: 4px; min-width: 20px;
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{ background: none; }}
        QSplitter::handle {{ background: {config.BG3}; }}
        QPushButton:pressed, QToolButton:pressed {{
            border: 1px solid #74A9FF;
            padding-top: 1px;
        }}
        {qt_tooltip_stylesheet()}
    """)
    configure_qt_tooltip_theme()
    install_button_click_feedback(app)

    win = MainWindow()
    logger.log_perf("app.main", event="main_window_ready", elapsed_ms=(time.perf_counter() - launch_started) * 1000.0)
    if _instance_command_server is not None:
        _instance_command_server.set_handler(
            lambda payload: win.dispatch_external_app_command(payload, timeout_sec=15.0)
        )
    def _shutdown_runtime_in_order():
        global _QT_APP_SHUTTING_DOWN
        _QT_APP_SHUTTING_DOWN = True
        schedule_forced_exit = getattr(win, "_schedule_forced_exit_for_busy_about_to_quit", None)
        if callable(schedule_forced_exit):
            try:
                schedule_forced_exit()
            except Exception:
                pass
        cleanup_runtime = getattr(win, "_start_runtime_cleanup_for_app_exit_async", None)
        if callable(cleanup_runtime):
            cleanup_runtime(timeout_sec=0.08 if getattr(config, "IS_MAC", False) else 0.15)
            return
        pause_runtime = getattr(win, "_pause_all_runtime_work_for_exit", None)
        if callable(pause_runtime):
            pause_runtime(context="앱 종료")

        def _fallback_cleanup():
            try:
                win._shutdown_personalization_idle_trainer(
                    timeout_sec=0.0,
                    cleanup=False,
                    recover=False,
                )
            except Exception:
                pass
            try:
                cleanup_app_child_processes(timeout_sec=0.0)
                cleanup_stale_preview_proxy_processes(timeout_sec=0.0)
                cleanup_app_runtime_processes(logger=get_logger(), timeout_sec=0.15)
            except Exception:
                pass

        try:
            threading.Thread(
                target=_fallback_cleanup,
                daemon=True,
                name="app-about-to-quit-cleanup",
            ).start()
        except Exception:
            _fallback_cleanup()

    app.aboutToQuit.connect(_shutdown_runtime_in_order)
    # ✅ 1순위 수정: 백엔드 먼저 연결
    from core.pipeline.backend_core import CoreBackend
    backend = CoreBackend(win)
    win.backend = backend
    logger.log_perf("app.main", event="backend_ready", elapsed_ms=(time.perf_counter() - launch_started) * 1000.0)

    # 데이터 채우기
    win.recent_folders = get_recent_folders()
    win.add_recent_folder_callback = add_recent_folder

    # 화면을 먼저 띄우고, 무거운 시작 작업은 MainWindow.showEvent 이후로 넘긴다.
    win.showMaximized()
    ollama_delay_ms = 700 if getattr(config, "IS_MAC", False) else 0
    logger.log_perf("app.main", event="window_shown", elapsed_ms=(time.perf_counter() - launch_started) * 1000.0)
    QTimer.singleShot(ollama_delay_ms, _start_ollama_runtime_for_app_launch)
    logger.log_perf(
        "app.main",
        event="event_loop_enter",
        elapsed_ms=(time.perf_counter() - launch_started) * 1000.0,
        ollama_delay_ms=ollama_delay_ms,
    )

    sys.exit(app.exec())


if __name__ == "__main__":
    check_single_instance()
    main()
