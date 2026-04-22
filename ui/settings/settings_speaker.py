# Version: 02.02.00
# Phase: PHASE1-B
"""
ui/settings_speaker.py  ─  🗣️ 화자 설정 다이얼로그
"""
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QLineEdit, QCheckBox, QWidget, QMessageBox
)
from PyQt6.QtCore import Qt
from ui.settings.settings_common import DATASET_DIR, _create_bottom_buttons


class SpeakerDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🗣️ 화자 설정")
        self.setMinimumWidth(600)
        self.setStyleSheet("""
            QDialog { background-color: #121212; color: #FFFFFF; }
            QLabel { color: #FFFFFF; background: transparent; font-weight: bold; }
            QLineEdit { background-color: #2A2A2A; color: #FFFFFF; border: 1px solid #555555; padding: 4px; border-radius: 3px; }
            QCheckBox { color: #FFFFFF; font-weight: bold; background: transparent; spacing: 8px; padding-right: 10px; }
            QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid #FFFFFF; border-radius: 3px; background-color: transparent; }
            QCheckBox::indicator:checked { background-color: #4AFF80; border: 2px solid #4AFF80; }
            QPushButton { background-color: #444444; color: #FFFFFF; border: none; font-weight: bold; border-radius: 4px; }
        """)
        self.result = dict(settings)
        layout = QVBoxLayout(self)
        form   = QFormLayout()

        def create_row(idx, default_id, default_color, show_chk=True):
            row_w = QWidget(); row_w.setStyleSheet("background-color: transparent;")
            h = QHBoxLayout(row_w); h.setContentsMargins(0, 0, 0, 0)

            txt_id    = QLineEdit(self.result.get(f"spk{idx}_id", default_id)); txt_id.setFixedWidth(50)
            btn_color = QPushButton()
            color_val = self.result.get(f"spk{idx}_color", default_color)
            btn_color.setStyleSheet(f"background-color: {color_val}; border: 1px solid #777; border-radius: 4px;")
            btn_color.setFixedSize(24, 24); btn_color.setCursor(Qt.CursorShape.PointingHandCursor)

            def pick_color(btn, key):
                from PyQt6.QtWidgets import QColorDialog
                from PyQt6.QtGui import QColor
                color = QColorDialog.getColor(QColor(self.result.get(key, default_color)), self)
                if color.isValid():
                    hex_color = color.name()
                    self.result[key] = hex_color
                    btn.setStyleSheet(f"background-color: {hex_color}; border: 1px solid #777; border-radius: 4px;")

            btn_color.clicked.connect(lambda _, b=btn_color, k=f"spk{idx}_color": pick_color(b, k))

            h.addWidget(QLabel("ID (숫자):")); h.addWidget(txt_id)
            h.addSpacing(10); h.addWidget(QLabel("색상:")); h.addWidget(btn_color); h.addSpacing(15)

            if idx == 1:
                btn_voice = QPushButton("🎙️ 목소리 학습")
                voice_path = os.path.join(DATASET_DIR, "my_voice.wav")
                if os.path.exists(voice_path):
                    btn_voice.setText("✅ 학습 완료")
                    btn_voice.setStyleSheet("background-color: #4AFF80; color: #000; font-size: 11px; padding: 6px; border-radius: 3px; font-weight: bold;")
                else:
                    btn_voice.setStyleSheet("background-color: #444; color: #FFF; font-size: 11px; padding: 6px; border-radius: 3px;")

                def _learn_voice():
                    from PyQt6.QtWidgets import QFileDialog
                    import shutil
                    path, _ = QFileDialog.getOpenFileName(
                        self, "대표님 목소리가 깨끗하게 담긴 파일 선택", "",
                        "Audio/Video (*.wav *.m4a *.mp3 *.mp4 *.mov *.MOV)"
                    )
                    if path:
                        try:
                            os.makedirs(DATASET_DIR, exist_ok=True)
                            shutil.copy(path, voice_path)
                            btn_voice.setText("✅ 학습 완료")
                            btn_voice.setStyleSheet("background-color: #4AFF80; color: #000; font-size: 11px; padding: 6px; border-radius: 3px; font-weight: bold;")
                            QMessageBox.information(self, "학습 완료", "대표님 목소리가 등록되었습니다!\n이제부터 영상에서 화자 1번으로 자동 추적됩니다.")
                        except Exception as e:
                            QMessageBox.warning(self, "오류", f"파일 복사 실패:\n{e}")

                btn_voice.clicked.connect(_learn_voice)
                h.addWidget(btn_voice)

            chk = None
            if show_chk:
                chk = QCheckBox("사용")
                chk.setMinimumWidth(80)
                chk.setChecked(self.result.get(f"spk{idx}_enabled", False))
                h.addWidget(chk)
            h.addStretch()
            return row_w, txt_id, chk

        self.row1, self.txt1, _         = create_row(1, "00", "#FFFFFF", False)
        self.row2, self.txt2, self.chk2 = create_row(2, "01", "#FFFF00", True)
        self.row3, self.txt3, self.chk3 = create_row(3, "02", "#00FFFF", True)

        form.addRow("▶ 화자 1:", self.row1)
        form.addRow("▶ 화자 2:", self.row2)
        form.addRow("▶ 화자 3:", self.row3)

        note = QLabel("💡 팁: 화자 분리 AI가 감지한 번호(00, 01 등)를 ID에 입력하세요.")
        note.setStyleSheet("color: #CCCCCC; font-size: 11px; background: transparent; margin-top: 10px;")
        form.addRow("", note)

        layout.addLayout(form)
        layout.addLayout(_create_bottom_buttons(self, self._on_ok))

    def _on_ok(self):
        self.result["spk1_id"] = self.txt1.text().strip()
        self.result["spk2_id"] = self.txt2.text().strip()
        self.result["spk3_id"] = self.txt3.text().strip()
        self.result["spk2_enabled"] = self.chk2.isChecked()
        self.result["spk3_enabled"] = self.chk3.isChecked()
        max_spk = 1
        if self.chk2.isChecked(): max_spk = 2
        if self.chk3.isChecked(): max_spk = 3
        self.result["max_speakers"] = max_spk
        self.result["min_speakers"] = 1
        self.accept()
