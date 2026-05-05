# Version: 02.04.00
# Phase: PHASE1-B
"""
ui/settings_export.py  ─  📤 자막 파일 출력 다이얼로그 (비디오 메뉴)
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)
from PyQt6.QtCore import Qt
from ui.settings.qml_panel import create_settings_header
from ui.style import button_style, label_style, settings_dialog_stylesheet

class ExportDialog(QDialog):
    def __init__(self, subtitles=None, parent=None):
        super().__init__(parent)
        self.subtitles = subtitles or []
        self.setWindowTitle("📤 자막 파일 출력")
        self.setMinimumWidth(400)
        self.setStyleSheet(settings_dialog_stylesheet())
        
        layout = QVBoxLayout(self)
        self._qml_header = create_settings_header(
            self,
            title="자막 파일 출력",
            subtitle="SRT 저장과 후속 자동 영상 출력을 위한 설정 패널입니다.",
            badge="QML",
        )
        if self._qml_header is not None:
            layout.addWidget(self._qml_header)
        
        layout.addWidget(QLabel(f"<b>현재 불러온 자막 수: {len(self.subtitles)}개</b>"))
        
        self.lbl_error = QLabel("자막이 없습니다.")
        self.lbl_error.setStyleSheet(label_style("danger", 14, bold=True))
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_error.hide()
        layout.addWidget(self.lbl_error)
        
        btn_export = QPushButton("자막 파일 저장 (.srt)")
        btn_export.setStyleSheet(button_style("primary", padding="10px 14px"))
        btn_export.clicked.connect(self._on_export)
        layout.addWidget(btn_export)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_cancel = QPushButton("닫기")
        btn_cancel.setStyleSheet(button_style("toolbar"))
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        
        layout.addLayout(btn_layout)

    def _on_export(self):
        if not self.subtitles:
            print("자막이 없습니다")
            self.lbl_error.show()
            return
        self.accept()
