# Version: 01.00.01
import sys
import os
import json
import subprocess
import urllib.request

# 💡 [핵심 해결] 현재 실행되는 main.py의 절대 경로를 찾아서 시스템 경로(sys.path) 맨 앞에 추가합니다.
# 이 코드가 있어야 파이썬이 'core' 폴더를 패키지로 인식할 수 있습니다.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# PyQt6 내부 비디오 플레이어(QtMultimedia/FFmpeg)의 불필요한 로그 차단
os.environ["QT_LOGGING_RULES"] = "qt.multimedia.*=false;qt.multimedia.ffmpeg.*=false;qt.qpa.fonts=false"
os.environ["AV_LOG_LEVEL"] = "16"

import socket  # 💡 [추가] 네트워크 포트를 이용한 락 기능
from PyQt6.QtWidgets import QApplication, QMessageBox  # 💡 QMessageBox 추가
from PyQt6.QtCore import Qt
import config
from logger import get_logger

# 💡 [추가] 가비지 컬렉터에 의해 삭제되지 않도록 전역 변수로 유지합니다.
_instance_socket = None 

def check_single_instance():
    """프로그램 중복 실행을 완벽하게 차단하는 함수"""
    global _instance_socket
    _instance_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 이 프로그램만의 고유한 비밀 포트(47291)를 점유합니다.
        _instance_socket.bind(('127.0.0.1', 47291))
    except socket.error:
        # 이미 다른 창이 이 포트를 점유하고 있다면 (즉, 이미 켜져 있다면)
        app = QApplication.instance() or QApplication(sys.argv)
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("중복 실행 방지")
        msg.setText("AI PD Studio가 이미 실행 중입니다.\n기존에 열려있는 창을 확인해 주세요.")
        msg.exec()
        sys.exit(0) # 새 프로그램은 경고창만 띄우고 조용히 종료합니다.

# 💡 [경로 수정] MainWindow 내부에서 core.path_manager를 사용하므로
# MainWindow를 임포트하기 전에 core 폴더가 경로에 잡혀있어야 합니다.
from ui.main_window import MainWindow

# [main.py] 27번 라인 근처
# 수정 전: from folder_manager import get_recent_folders, add_recent_folder 
# 수정 후:
from core.path_manager import get_recent_folders, add_recent_folder

def main():
    app = QApplication(sys.argv)

    # UI 스타일 설정 (config.py 색상 기반)
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
    # 💡 [순서 조정] 데이터를 먼저 채워넣습니다.
    win.recent_folders = get_recent_folders() 
    win.add_recent_folder_callback = add_recent_folder

    # 💡 [핵심] 데이터가 들어온 후 '홈 화면'을 다시 그리라고 명령합니다.
    win.show_home() 

    # CoreBackend 연결
    from core.backend import CoreBackend
    backend = CoreBackend(win)
    win.backend = backend

    # win.resize(1400, 900)
    # 💡 [수정] 앱 시작 시 작업표시줄 유지하며 최대화
    win.showMaximized()

    # Ollama 서버 자동 실행 확인
    try:
        req = urllib.request.Request("http://localhost:11434/")
        with urllib.request.urlopen(req, timeout=1) as response:
            if response.status == 200:
                get_logger().log("✅ AI 엔진(Ollama) 실행 중")
    except Exception:
        get_logger().log("⚠️ AI 엔진(Ollama)이 꺼져있습니다. 필요시 터미널에서 'ollama serve'를 실행하세요.")

    sys.exit(app.exec())


if __name__ == "__main__":
    check_single_instance()  # 💡 [추가] 본격적인 화면을 띄우기 전에 중복 실행부터 차단!
    main()