# Version: 02.02.01
# Phase: PHASE1-B
"""
ui/settings/settings_speaker.py
Speaker settings dialog with voice-data management for speaker 1/2/3.
"""
import glob
import os
import shutil

import config
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from ui.settings.settings_common import DATASET_DIR, _create_bottom_buttons


class SpeakerDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("화자 설정")
        self.setMinimumWidth(900)
        self.setStyleSheet(
            """
            QDialog { background-color: #121212; color: #FFFFFF; }
            QLabel { color: #FFFFFF; background: transparent; font-weight: bold; }
            QLineEdit {
                background-color: #2A2A2A; color: #FFFFFF;
                border: 1px solid #555555; padding: 4px; border-radius: 3px;
            }
            QCheckBox {
                color: #FFFFFF; font-weight: bold; background: transparent;
                spacing: 8px; padding-right: 10px;
            }
            QCheckBox::indicator {
                width: 16px; height: 16px; border: 2px solid #FFFFFF;
                border-radius: 3px; background-color: transparent;
            }
            QCheckBox::indicator:checked {
                background-color: #4AFF80; border: 2px solid #4AFF80;
            }
            QPushButton {
                background-color: #444444; color: #FFFFFF; border: none;
                font-weight: bold; border-radius: 4px; padding: 6px 10px;
            }
            """
        )

        self.result = dict(settings)
        os.makedirs(config.VOICE_DATA_DIR, exist_ok=True)
        self._migrate_legacy_voice()

        self._voice_labels = {}
        self._play_buttons = {}
        self._del_buttons = {}
        self._preview_idx = None
        self._preview = QSoundEffect(self)
        self._preview.setLoopCount(1)
        self._preview.setVolume(1.0)
        self._preview.playingChanged.connect(self._on_preview_playing_changed)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        def create_row(idx, default_id, default_color, show_chk=True):
            row_w = QWidget()
            row_w.setStyleSheet("background-color: transparent;")
            h = QHBoxLayout(row_w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)

            txt_id = QLineEdit(self.result.get(f"spk{idx}_id", default_id))
            txt_id.setFixedWidth(50)

            btn_color = QPushButton()
            color_val = self.result.get(f"spk{idx}_color", default_color)
            btn_color.setStyleSheet(
                f"background-color: {color_val}; border: 1px solid #777; border-radius: 4px;"
            )
            btn_color.setFixedSize(24, 24)
            btn_color.setCursor(Qt.CursorShape.PointingHandCursor)

            def pick_color(btn, key, fallback):
                color = QColorDialog.getColor(parent=self)
                if color.isValid():
                    hex_color = color.name()
                    self.result[key] = hex_color
                    btn.setStyleSheet(
                        f"background-color: {hex_color}; border: 1px solid #777; border-radius: 4px;"
                    )
                else:
                    self.result.setdefault(key, fallback)

            btn_color.clicked.connect(
                lambda _, b=btn_color, k=f"spk{idx}_color", d=default_color: pick_color(b, k, d)
            )

            h.addWidget(QLabel("ID(숫자):"))
            h.addWidget(txt_id)
            h.addWidget(QLabel("색상:"))
            h.addWidget(btn_color)

            btn_voice = QPushButton("목소리학습")
            btn_voice.setStyleSheet(
                "background-color: #444; color: #FFF; font-size: 11px; padding: 6px; border-radius: 3px;"
            )

            voice_label = QLabel("")
            voice_label.setFixedWidth(90)
            voice_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            voice_label.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
            self._voice_labels[idx] = voice_label

            btn_play = QPushButton("▶")
            btn_play.setFixedWidth(34)
            btn_play.setFixedHeight(28)
            btn_play.setEnabled(False)
            btn_play.setToolTip("재생 / 정지")
            btn_play.setStyleSheet(
                "QPushButton { background-color: #444444; color: #FFFFFF; "
                "font-weight: bold; border-radius: 4px; padding: 0 0 0 1px; text-align: center; }"
            )
            btn_play.clicked.connect(lambda _, i=idx: self._toggle_preview(i))
            self._play_buttons[idx] = btn_play

            def learn_voice():
                import subprocess, sys
                vd = config.VOICE_DATA_DIR
                os.makedirs(vd, exist_ok=True)
                if sys.platform == 'win32': os.startfile(vd)
                elif sys.platform == 'darwin': subprocess.Popen(['open', vd])
                else: subprocess.Popen(['xdg-open', vd])
                return
                path, _ = QFileDialog.getOpenFileName(
                    self,
                    "학습할 음성/영상 파일 선택",
                    "",
                    "Audio/Video (*.wav *.m4a *.mp3 *.aac *.mp4 *.mov *.MOV)",
                )
                if not path:
                    return

                default_name = f"spk{idx}_voice"
                name, ok = QInputDialog.getText(
                    self,
                    "화자 음성 저장",
                    "파일 이름 (확장자 제외):",
                    text=default_name,
                )
                if not ok or not name.strip():
                    return

                name = name.strip()
                if not name.endswith(".wav"):
                    name += ".wav"

                dst = os.path.join(config.VOICE_DATA_DIR, name)
                try:
                    os.makedirs(config.VOICE_DATA_DIR, exist_ok=True)
                    shutil.copy(path, dst)
                    self._refresh_voice_row(idx)
                    QMessageBox.information(
                        self,
                        "학습 저장",
                        f"화자 {idx} 학습 파일 저장 완료\n{dst}",
                    )
                except Exception as e:
                    QMessageBox.warning(self, "오류", f"파일 저장 실패:\n{e}")

            btn_voice.clicked.connect(learn_voice)

            btn_del_voice = QPushButton('X')
            btn_del_voice.setFixedWidth(28)
            btn_del_voice.setFixedHeight(28)
            btn_del_voice.setToolTip('학습 데이터 사용 해제 (파일 유지)')
            btn_del_voice.setStyleSheet('QPushButton { background-color: #661111; color: #FF8080; font-weight: bold; border-radius: 4px; padding: 0px; }')
            btn_del_voice.setEnabled(False)
            btn_del_voice.clicked.connect(lambda _, i=idx: self._toggle_voice_disable(i))
            
            self._del_buttons[idx] = btn_del_voice

            h.addWidget(btn_voice)
            h.addWidget(voice_label)
            h.addWidget(btn_del_voice)
            h.addWidget(btn_play)

            chk = None
            if show_chk:
                chk = QCheckBox("사용")
                chk.setMinimumWidth(70)
                chk.setChecked(self.result.get(f"spk{idx}_enabled", False))
                h.addWidget(chk)
            else:
                spacer = QWidget()
                spacer.setFixedWidth(70)
                spacer.setStyleSheet("background: transparent;")
                h.addWidget(spacer)

            h.addStretch()
            return row_w, txt_id, chk

        self.row1, self.txt1, _ = create_row(1, "00", "#FFFFFF", False)
        self.row2, self.txt2, self.chk2 = create_row(2, "01", "#FFFF00", True)
        self.row3, self.txt3, self.chk3 = create_row(3, "02", "#00FFFF", True)

        form.addRow("화자 1:", self.row1)
        form.addRow("화자 2:", self.row2)
        form.addRow("화자 3:", self.row3)

        note = QLabel(
            "화자 ID는 diarize 결과 번호(00, 01, 02)에 맞춰 사용합니다.\n"
            "voice_data 폴더의 spk1_/spk2_/spk3_ 접두 wav 파일이 학습 데이터로 사용됩니다.\n"
            "[X] 버튼은 파일을 삭제하지 않고 앱에서만 사용 해제합니다."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            "color: #CCCCCC; font-size: 11px; background: transparent; margin-top: 10px;"
        )
        form.addRow("", note)

        layout.addLayout(form)
        layout.addLayout(_create_bottom_buttons(self, self._on_ok))

        self._refresh_voice_row(1)
        self._refresh_voice_row(2)
        self._refresh_voice_row(3)

    def _migrate_legacy_voice(self):
        old_voice = os.path.join(DATASET_DIR, "my_voice.wav")
        if not os.path.exists(old_voice):
            return

        backup_dir = os.path.join(config.VOICE_DATA_DIR, "voice_backup")
        os.makedirs(backup_dir, exist_ok=True)

        backup_path = os.path.join(backup_dir, "my_voice_00.wav")
        if not os.path.exists(backup_path):
            shutil.copy2(old_voice, backup_path)

        new_voice = os.path.join(config.VOICE_DATA_DIR, "spk1_voice.wav")
        if not os.path.exists(new_voice):
            shutil.move(old_voice, new_voice)
        else:
            try:
                os.remove(old_voice)
            except Exception:
                pass

    def _list_voice_files(self, idx: int):
        pattern = os.path.join(config.VOICE_DATA_DIR, f"spk{idx}_*.wav")
        return sorted(os.path.basename(p) for p in glob.glob(pattern))

    def _primary_voice_path(self, idx: int):
        files = self._list_voice_files(idx)
        if not files:
            return None
        return os.path.join(config.VOICE_DATA_DIR, files[0])

    # ── [X] 버튼: disable/enable 토글 (파일 삭제 안 함) ──
    def _toggle_voice_disable(self, idx: int):
        """파일을 삭제하지 않고 앱 내부에서만 사용/해제를 토글합니다."""
        key = f"spk{idx}_voice_disabled"
        current = self.result.get(key, False)
        self.result[key] = not current
        self._refresh_voice_row(idx)

    # ── row UI 새로고침 ───────────────────────────────────
    def _refresh_voice_row(self, idx: int):
        label = self._voice_labels[idx]
        btn_play = self._play_buttons[idx]
        btn_del = self._del_buttons.get(idx)
        files = self._list_voice_files(idx)
        disabled = self.result.get(f"spk{idx}_voice_disabled", False)

        if files and not disabled:
            label.setText(files[0])
            label.setStyleSheet("color: #4AFF80; font-size: 10px; background: transparent;")
            btn_play.setEnabled(True)
            if btn_del:
                btn_del.setEnabled(True)
                btn_del.setText("X")
                btn_del.setToolTip("학습 데이터 사용 해제 (파일 유지)")
                btn_del.setStyleSheet(
                    "QPushButton { background-color: #661111; color: #FF8080; "
                    "font-weight: bold; border-radius: 4px; padding: 0px; }"
                )
        elif files and disabled:
            label.setText("사용 안 함")
            label.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
            btn_play.setEnabled(False)
            btn_play.setText("▶")
            if btn_del:
                btn_del.setEnabled(True)
                btn_del.setText("↩")
                btn_del.setToolTip("학습 데이터 다시 사용")
                btn_del.setStyleSheet(
                    "QPushButton { background-color: #114411; color: #4AFF80; "
                    "font-weight: bold; border-radius: 4px; padding: 0px; }"
                )
        else:
            label.setText("학습 데이터 없음")
            label.setStyleSheet("color: #888888; font-size: 10px; background: transparent;")
            btn_play.setEnabled(False)
            btn_play.setText("▶")
            if btn_del:
                btn_del.setEnabled(False)
                btn_del.setText("X")
                btn_del.setToolTip("학습 데이터 사용 해제 (파일 유지)")
                btn_del.setStyleSheet(
                    "QPushButton { background-color: #661111; color: #FF8080; "
                    "font-weight: bold; border-radius: 4px; padding: 0px; }"
                )

    def _toggle_preview(self, idx: int):
        path = self._primary_voice_path(idx)
        if not path or not os.path.exists(path):
            self._refresh_voice_row(idx)
            return

        if self._preview_idx == idx and self._preview.isPlaying():
            self._preview.stop()
            self._preview_idx = None
            self._refresh_preview_buttons()
            return

        self._preview.stop()
        self._preview_idx = idx
        self._preview.setSource(QUrl.fromLocalFile(path))
        self._preview.play()
        self._refresh_preview_buttons()

    def _on_preview_playing_changed(self):
        if not self._preview.isPlaying():
            self._preview_idx = None
        self._refresh_preview_buttons()

    def _refresh_preview_buttons(self):
        for idx, btn in self._play_buttons.items():
            if self._preview_idx == idx and self._preview.isPlaying():
                btn.setText("■")
            else:
                btn.setText("▶")

    def _on_ok(self):
        self.result["spk1_id"] = self.txt1.text().strip()
        self.result["spk2_id"] = self.txt2.text().strip()
        self.result["spk3_id"] = self.txt3.text().strip()
        self.result["spk2_enabled"] = self.chk2.isChecked()
        self.result["spk3_enabled"] = self.chk3.isChecked()

        max_spk = 1
        if self.chk2.isChecked():
            max_spk = 2
        if self.chk3.isChecked():
            max_spk = 3

        self.result["max_speakers"] = max_spk
        self.result["min_speakers"] = 1
        self.accept()
