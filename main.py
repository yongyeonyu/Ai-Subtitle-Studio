# Version: 03.09.02
# Phase: PHASE1-B
import sys
import os
import socket

os.environ.setdefault(
    "QT_LOGGING_RULES",
    "qt.multimedia.*=false;qt.multimedia.ffmpeg.*=false;qt.qpa.fonts=false",
)
os.environ.setdefault("AV_LOG_LEVEL", "16")

from core.runtime import config
from core.performance import configure_qt_gpu_rendering_before_app, configure_qt_runtime
from core.platform_compat import cleanup_app_runtime_processes, cleanup_stale_preview_proxy_processes

configure_qt_gpu_rendering_before_app()

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt
from core.runtime.logger import get_logger

_instance_socket = None

def check_single_instance():
    """프로그램 중복 실행을 완벽하게 차단하는 함수"""
    global _instance_socket
    _instance_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        _instance_socket.bind(('127.0.0.1', config.INSTANCE_PORT))
    except socket.error:
        app = QApplication.instance() or QApplication(sys.argv)
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("중복 실행 방지")
        msg.setText(f"{config.APP_NAME}가 이미 실행 중입니다.\n기존에 열려있는 창을 확인해 주세요.")
        msg.exec()
        sys.exit(0)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from ui.main.main_window import MainWindow
from core.path_manager import get_recent_folders, add_recent_folder
from core.llm.ollama_provider import ensure_ollama_server


def main():
    app = QApplication(sys.argv)
    configure_qt_runtime()
    cleaned_preview_jobs = cleanup_stale_preview_proxy_processes(timeout_sec=0.2)
    app.aboutToQuit.connect(lambda: cleanup_app_runtime_processes(logger=get_logger(), timeout_sec=0.2))

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
        QToolTip {{
            background: #333333; color: #ffffff;
            border: 1px solid #555555; padding: 4px;
            font-size: 13px;
        }}
    """)

    win = MainWindow()
    if cleaned_preview_jobs:
        get_logger().log(f"🧹 이전 미리보기 프록시 ffmpeg {cleaned_preview_jobs}개 정리 완료")

    # ✅ 1순위 수정: 백엔드 먼저 연결
    from core.pipeline.backend_core import CoreBackend
    backend = CoreBackend(win)
    win.backend = backend

    # 데이터 채우기
    win.recent_folders = get_recent_folders()
    win.add_recent_folder_callback = add_recent_folder

    # 화면 그리기 (마지막)
    win.show_home()

    win.showMaximized()

    ensure_ollama_server(logger=get_logger(), wait_sec=5.0)

    sys.exit(app.exec())


if __name__ == "__main__":
    check_single_instance()
    main()
