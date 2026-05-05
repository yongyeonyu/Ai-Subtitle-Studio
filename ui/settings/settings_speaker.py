# Version: 03.01.05
# Phase: PHASE1-B
"""
ui/settings/settings_speaker.py
Speaker settings dialog with voice-data management for speaker 1/2/3.
"""
import glob
import os
import re
import shutil

from core.runtime import config
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
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
from ui.settings.qml_panel import create_settings_header
from ui.style import button_style, label_style, settings_dialog_stylesheet


class SpeakerDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("화자 설정")
        self.setMinimumWidth(760)
        self.setStyleSheet(settings_dialog_stylesheet())

        self.result = dict(settings)
        os.makedirs(config.VOICE_DATA_DIR, exist_ok=True)
        self._migrate_legacy_voice()

        self._voice_labels = {}
        self._play_buttons = {}
        self._del_buttons = {}
        self._name_buttons = {}
        self._preview_idx = None
        self._preview = QSoundEffect(self)
        self._preview.setLoopCount(1)
        self._preview.setVolume(1.0)
        self._preview.playingChanged.connect(self._on_preview_playing_changed)

        layout = QVBoxLayout(self)
        self._qml_header = create_settings_header(
            self,
            title="화자 설정",
            subtitle="화자 ID, 색상, 목소리 학습 데이터를 QML 패널 헤더 아래에서 관리합니다.",
            badge="QML",
        )
        if self._qml_header is not None:
            layout.addWidget(self._qml_header)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(0)
        form.setVerticalSpacing(6)

        def create_row(idx, default_id, default_color, show_chk=True):
            row_w = QWidget()
            row_w.setStyleSheet("background-color: transparent;")
            h = QHBoxLayout(row_w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(6)

            btn_name = QPushButton(self._speaker_name(idx))
            btn_name.setFixedSize(96, 30)
            btn_name.setToolTip("클릭해서 화자 이름 변경")
            btn_name.setStyleSheet(button_style("toolbar", font_size="11px", padding="4px 8px"))
            btn_name.clicked.connect(lambda _, i=idx: self._rename_speaker(i))
            self._name_buttons[idx] = btn_name

            txt_id = QLineEdit(self.result.get(f"spk{idx}_id", default_id))
            txt_id.setFixedSize(46, 30)

            btn_color = QPushButton()
            color_val = self.result.get(f"spk{idx}_color", default_color)
            btn_color.setStyleSheet(
                f"background-color: {color_val}; border: 1px solid #777; border-radius: 4px;"
            )
            btn_color.setFixedSize(28, 28)
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

            h.addWidget(btn_name)
            h.addWidget(QLabel("ID"))
            h.addWidget(txt_id)
            h.addWidget(QLabel("색상"))
            h.addWidget(btn_color)

            btn_voice = QPushButton("목소리학습")
            btn_voice.setFixedHeight(30)
            btn_voice.setStyleSheet(button_style("toolbar", font_size="11px", padding="5px 9px"))

            voice_label = QLabel("")
            voice_label.setFixedWidth(150)
            voice_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            voice_label.setStyleSheet(label_style("muted", 10))
            self._voice_labels[idx] = voice_label

            btn_play = QPushButton("▶")
            btn_play.setFixedWidth(34)
            btn_play.setFixedHeight(30)
            btn_play.setEnabled(False)
            btn_play.setToolTip("재생 / 정지")
            btn_play.setStyleSheet(button_style("toolbar", font_size="12px", padding="0 0 0 1px"))
            btn_play.clicked.connect(lambda _, i=idx: self._toggle_preview(i))
            self._play_buttons[idx] = btn_play

            def learn_voice():
                import subprocess, sys
                vd = config.VOICE_DATA_DIR
                os.makedirs(vd, exist_ok=True)
                if sys.platform == 'win32': os.startfile(vd)
                elif sys.platform == 'darwin': subprocess.Popen(['open', vd])
                else: subprocess.Popen(['xdg-open', vd])

            btn_voice.clicked.connect(learn_voice)

            btn_del_voice = QPushButton('X')
            btn_del_voice.setFixedWidth(28)
            btn_del_voice.setFixedHeight(30)
            btn_del_voice.setToolTip('학습 데이터 사용 해제 (파일 유지)')
            btn_del_voice.setStyleSheet(button_style("danger", font_size="12px", padding="0"))
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
                chk.setFixedWidth(58)
                chk.setChecked(self.result.get(f"spk{idx}_enabled", False))
                h.addWidget(chk)
            else:
                spacer = QWidget()
                spacer.setFixedWidth(58)
                spacer.setStyleSheet("background: transparent;")
                h.addWidget(spacer)

            h.addStretch()
            return row_w, txt_id, chk

        self.row1, self.txt1, _ = create_row(1, "00", "#FFFFFF", False)
        self.row2, self.txt2, self.chk2 = create_row(2, "01", "#FFFF00", True)
        self.row3, self.txt3, self.chk3 = create_row(3, "02", "#00FFFF", True)

        form.addRow("", self.row1)
        form.addRow("", self.row2)
        form.addRow("", self.row3)

        note = QLabel(
            "화자 ID는 diarize 결과 번호(00, 01, 02)에 맞춰 사용합니다.\n"
            "voice_data 폴더의 spk1_/spk2_/spk3_ 접두 wav 파일이 학습 데이터로 사용됩니다.\n"
            "[X] 버튼은 파일을 삭제하지 않고 앱에서만 사용 해제합니다."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            label_style("muted", 11) + "margin-top: 10px;"
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

    def _speaker_name(self, idx: int) -> str:
        return str(self.result.get(f"spk{idx}_name", "") or f"화자 {idx}").strip()

    def _safe_voice_stem(self, text: str) -> str:
        text = re.sub(r'[\\/:*?"<>|]+', "_", str(text or "").strip())
        text = re.sub(r"\s+", "_", text)
        text = text.strip("._ ")
        return text or "speaker"

    def _voice_filename_for(self, idx: int, name: str, suffix: str = "") -> str:
        stem = self._safe_voice_stem(name)
        suffix = f"_{suffix}" if suffix else ""
        return f"spk{idx}_{stem}{suffix}.wav"

    def _dedupe_voice_path(self, target_path: str, existing_src: str | None = None) -> str:
        base, ext = os.path.splitext(target_path)
        candidate = target_path
        n = 2
        while os.path.exists(candidate) and os.path.abspath(candidate) != os.path.abspath(existing_src or ""):
            candidate = f"{base}_{n}{ext}"
            n += 1
        return candidate

    def _rename_voice_files_for_speaker(self, idx: int, name: str) -> list[tuple[str, str]]:
        files = self._list_voice_files(idx)
        planned = []
        for order, filename in enumerate(files):
            src = os.path.join(config.VOICE_DATA_DIR, filename)
            dst_name = self._voice_filename_for(idx, name, "" if order == 0 else str(order + 1))
            dst = self._dedupe_voice_path(os.path.join(config.VOICE_DATA_DIR, dst_name), src)
            if os.path.abspath(src) == os.path.abspath(dst):
                continue
            planned.append((src, dst))
        renamed = []
        try:
            for src, dst in planned:
                os.replace(src, dst)
                renamed.append((src, dst))
        except Exception:
            for src, dst in reversed(renamed):
                try:
                    if os.path.exists(dst) and not os.path.exists(src):
                        os.replace(dst, src)
                except Exception:
                    pass
            raise
        if files:
            primary = self._list_voice_files(idx)[0]
            self.result[f"spk{idx}_voice_file"] = primary
        return renamed

    def _rename_speaker(self, idx: int):
        current = self._speaker_name(idx)
        name, ok = QInputDialog.getText(
            self,
            "화자 이름 변경",
            f"화자 {idx} 이름:",
            text=current,
        )
        if not ok:
            return
        name = str(name or "").strip()
        if not name:
            QMessageBox.warning(self, "화자 이름", "화자 이름을 입력해주세요.")
            return
        try:
            self._rename_voice_files_for_speaker(idx, name)
        except Exception as exc:
            QMessageBox.warning(self, "화자 이름", f"학습 데이터 파일명 변경 실패:\n{exc}\n\n원본 파일은 유지됩니다.")
            return
        self.result[f"spk{idx}_name"] = name
        self._name_buttons[idx].setText(name)
        self._refresh_voice_row(idx)

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
            label.setStyleSheet(label_style("accent", 10, bold=True))
            btn_play.setEnabled(True)
            if btn_del:
                btn_del.setEnabled(True)
                btn_del.setText("X")
                btn_del.setToolTip("학습 데이터 사용 해제 (파일 유지)")
                btn_del.setStyleSheet(button_style("danger", font_size="12px", padding="0"))
        elif files and disabled:
            label.setText("사용 안 함")
            label.setStyleSheet(label_style("muted", 10))
            btn_play.setEnabled(False)
            btn_play.setText("▶")
            if btn_del:
                btn_del.setEnabled(True)
                btn_del.setText("↩")
                btn_del.setToolTip("학습 데이터 다시 사용")
                btn_del.setStyleSheet(button_style("primary", font_size="12px", padding="0"))
        else:
            label.setText("학습 데이터 없음")
            label.setStyleSheet(label_style("muted", 10))
            btn_play.setEnabled(False)
            btn_play.setText("▶")
            if btn_del:
                btn_del.setEnabled(False)
                btn_del.setText("X")
                btn_del.setToolTip("학습 데이터 사용 해제 (파일 유지)")
                btn_del.setStyleSheet(button_style("danger", font_size="12px", padding="0"))

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
        for idx, btn in self._name_buttons.items():
            self.result[f"spk{idx}_name"] = btn.text().strip() or f"화자 {idx}"
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
