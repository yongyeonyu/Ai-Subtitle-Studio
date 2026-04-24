# Version: 02.02.01
# Phase: PHASE1-B
"""
ui/settings_export.py  ─  📤 자막 파일 출력 다이얼로그 (비디오 메뉴)
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)
from PyQt6.QtCore import Qt

class ExportDialog(QDialog):
    def __init__(self, subtitles=None, parent=None):
        super().__init__(parent)
        self.subtitles = subtitles or []
        self.setWindowTitle("📤 자막 파일 출력")
        self.setMinimumWidth(400)
        self.setStyleSheet("""
            QDialog { background-color: #121212; color: #FFFFFF; }
            QLabel { color: #FFFFFF; background: transparent; }
        """)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel(f"<b>현재 불러온 자막 수: {len(self.subtitles)}개</b>"))
        
        self.lbl_error = QLabel("자막이 없습니다.")
        self.lbl_error.setStyleSheet("color: #FF5555; font-weight: bold; font-size: 14px;")
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_error.hide()
        layout.addWidget(self.lbl_error)
        
        btn_export = QPushButton("자막 파일 저장 (.srt)")
        btn_export.setStyleSheet("""
            QPushButton {
                background-color: #4AFF80; 
                color: #000000; 
                font-weight: bold; 
                padding: 10px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #3AE070; }
        """)
        btn_export.clicked.connect(self._on_export)
        layout.addWidget(btn_export)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_cancel = QPushButton("닫기")
        btn_cancel.setStyleSheet("background-color: #444444; color: #FFFFFF; padding: 6px 16px; font-weight: bold; border-radius: 4px;")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        
        layout.addLayout(btn_layout)

    def _on_export(self):
        if not self.subtitles:
            print("자막이 없습니다")
            self.lbl_error.show()
            return
        self.accept()
