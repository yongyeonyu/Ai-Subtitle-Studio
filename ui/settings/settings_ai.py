# Version: 02.02.00
# Phase: PHASE1-B
"""
ui/settings_ai.py  ─  ⚙️ AI 엔진 설정 다이얼로그
"""
import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
                             QLabel, QComboBox, QMessageBox, QLineEdit, 
                             QSlider, QPushButton, QCheckBox)
from PyQt6.QtCore import Qt
import config
from core.data_manager import save_settings, save_default_settings
from ui.settings.settings_common import (
    DEFAULT_WHISPER_MODELS, _fetch_models, _create_bottom_buttons, DATASET_DIR
)


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ AI 엔진 설정")
        # 💡 [수정] 4가지 정보가 한 줄에 다 들어오도록 너비를 700px로 확장
        self.setMinimumWidth(700) 
        self.setStyleSheet("""
            QDialog { background-color: #121212; color: #FFFFFF; }
            QLabel { color: #FFFFFF; background: transparent; font-weight: bold; }
            QLineEdit { background-color: #2A2A2A; color: #FFFFFF; border: 1px solid #555555; padding: 4px; border-radius: 3px; }
            QCheckBox { color: #FFFFFF; font-weight: bold; background: transparent; padding-right: 5px; }
            QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid #FFFFFF; border-radius: 3px; background-color: transparent; }
            QCheckBox::indicator:checked { background-color: #4AFF80; border: 2px solid #4AFF80; }
            QPushButton { background-color: #444444; color: #FFFFFF; border: none; font-weight: bold; border-radius: 4px; }
            QPushButton:hover { background-color: #555555; }
            QComboBox { background-color: #2A2A2A; color: #FFFFFF; border: 1px solid #444444; padding: 6px; border-radius: 4px; }
            QComboBox QAbstractItemView { background-color: #121212; color: #FFFFFF; selection-background-color: #4AFF80; selection-color: #000000; border: 1px solid #4AFF80; }
            QSlider::groove:horizontal { border: 1px solid #444444; height: 8px; background: #2A2A2A; margin: 2px 0; border-radius: 4px; }
            QSlider::handle:horizontal { background: #4AFF80; border: 1px solid #4AFF80; width: 14px; margin: -4px 0; border-radius: 7px; }
        """)
        self.result_settings = dict(settings)

        layout = QVBoxLayout(self)
        form   = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 1. LLM 모델 (제미나이 포함)
        self.models_data = []
        if parent is not None and getattr(parent, "_local_llm_models", None):
            self.models_data = [dict(m) for m in parent._local_llm_models]

        if not self.models_data:
            self.models_data = _fetch_models()

        self.combo_llm = QComboBox()
        bypass_item = {"name": "사용 안함 (Whisper 단독 진행)", "size": 0, "details": {}}
        self.combo_llm.addItem(bypass_item["name"], bypass_item)
        
        for m in self.models_data:
            self.combo_llm.addItem(m['name'], m)
            
        gemini_pro = {"name": "Gemini 2.5 Pro (API)", "size": 0, "details": {"family": "Google API", "parameter_size": "Cloud", "format": "api"}}
        gemini_flash = {"name": "Gemini 2.5 Flash (API)", "size": 0, "details": {"family": "Google API", "parameter_size": "Cloud", "format": "api"}}
        self.combo_llm.addItem(gemini_pro["name"], gemini_pro)
        self.combo_llm.addItem(gemini_flash["name"], gemini_flash)

        self.combo_llm.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_llm.setMinimumWidth(350)
        curr_llm = settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"))
        idx = self.combo_llm.findText(curr_llm)
        if idx >= 0: self.combo_llm.setCurrentIndex(idx)
        form.addRow("LLM 모델:", self.combo_llm)

        # 💡 [레이아웃 조정] LLM 메뉴 바로 밑에 4가지 정보를 한 줄로 표시
        self.lbl_model_info = QLabel()
        self.lbl_model_info.setStyleSheet("color: #AAAAAA; font-size: 11px; padding: 2px 5px 12px 5px; background: transparent;")
        self.lbl_model_info.setWordWrap(False) # 💡 자동 줄바꿈 강제 차단!
        form.addRow("", self.lbl_model_info)
        self.combo_llm.currentIndexChanged.connect(self._update_model_info)
        self._update_model_info()

        # 2. Google API Key
        self.input_api_key = QLineEdit()
        self.input_api_key.setPlaceholderText("AI Studio 발급 API Key 입력")
        self.input_api_key.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.input_api_key.setText(settings.get("google_api_key", ""))
        form.addRow("Google API Key:", self.input_api_key)

        # 3. 자막 묶음 단위 (슬라이더 세팅)
        chunk_layout = QHBoxLayout()
        self.btn_chunk_minus = QPushButton("-")
        self.btn_chunk_minus.setFixedSize(28, 28)
        self.btn_chunk_minus.clicked.connect(self._on_chunk_minus)
        
        self.slider_chunk = QSlider(Qt.Orientation.Horizontal)
        self.slider_chunk.setRange(10, 1800)
        self.slider_chunk.setSingleStep(10)
        self.slider_chunk.setPageStep(60)
        self.slider_chunk.valueChanged.connect(self._update_chunk_display)
        
        self.btn_chunk_plus = QPushButton("+")
        self.btn_chunk_plus.setFixedSize(28, 28)
        self.btn_chunk_plus.clicked.connect(self._on_chunk_plus)
        
        self.lbl_chunk_time = QLabel("01분 00초")
        self.lbl_chunk_time.setFixedWidth(75)
        self.lbl_chunk_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.chk_chunk_all = QCheckBox("전체")
        self.chk_chunk_all.toggled.connect(self._on_chunk_all_toggled)
        
        chunk_layout.addWidget(self.btn_chunk_minus)
        chunk_layout.addWidget(self.slider_chunk)
        chunk_layout.addWidget(self.btn_chunk_plus)
        chunk_layout.addWidget(self.lbl_chunk_time)
        chunk_layout.addWidget(self.chk_chunk_all)
        form.addRow("자막 묶음 단위:", chunk_layout)
        
        curr_chunk = int(settings.get("chunk_time_limit", 60))
        if curr_chunk >= 99999:
            self.chk_chunk_all.setChecked(True)
            self.slider_chunk.setValue(60)
        else:
            self.chk_chunk_all.setChecked(False)
            self.slider_chunk.setValue(curr_chunk)
        self._update_chunk_display(self.slider_chunk.value())

        # 4. Whisper 모델
        self.combo_whisper = QComboBox()
        w_models = list(DEFAULT_WHISPER_MODELS)

        hf_cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
        if os.path.exists(hf_cache_dir):
            for folder_name in os.listdir(hf_cache_dir):
                if folder_name.startswith("models--") and "whisper" in folder_name.lower():
                    repo_name = folder_name.replace("models--", "", 1).replace("--", "/", 1)
                    if repo_name not in w_models: w_models.append(repo_name)
        self.combo_whisper.setUpdatesEnabled(False)
        self.combo_whisper.blockSignals(True)
        self.combo_whisper.addItems(w_models)
        self.combo_whisper.setMinimumWidth(350)
        curr_w = settings.get("selected_whisper_model", getattr(config, "WHISPER_MODEL", w_models[0] if w_models else ""))
        # ── OS에 맞지 않는 저장값이면 기본값으로 교체 ──
        if not config.IS_MAC and "mlx-community" in curr_w:
            curr_w = "large-v3"
        elif config.IS_MAC and curr_w in ("large-v3", "large-v3-turbo", "medium", "small", "base", "tiny"):
            curr_w = "mlx-community/whisper-large-v3-mlx"
        if curr_w in w_models:
            self.combo_whisper.setCurrentText(curr_w)
        else:
            self.combo_whisper.setCurrentIndex(0)
        self.combo_whisper.blockSignals(False)
        self.combo_whisper.setUpdatesEnabled(True)
        form.addRow("Whisper 모델:", self.combo_whisper)

        # 5. 음성 처리 AI
        self.combo_audio = QComboBox()
        self.audio_map = {"Demucs (스튜디오급 보컬 분리)": "demucs", "DeepFilterNet (AI 노이즈 제거)": "deepfilter", "사용 안함": "none"}
        for k in self.audio_map: self.combo_audio.addItem(k)
        curr_audio = settings.get("selected_audio_ai", "demucs")
        for k, v in self.audio_map.items():
            if v == curr_audio: self.combo_audio.setCurrentText(k); break
        self.combo_audio.setMinimumWidth(350)
        form.addRow("음성 처리 AI:", self.combo_audio)

        # 6. VAD
        self.combo_vad = QComboBox()
        self.vad_map = {"Silero (권장)": "silero", "사용 안 함": "none"}
        for k in self.vad_map: self.combo_vad.addItem(k)
        curr_vad = settings.get("selected_vad", "silero")
        for k, v in self.vad_map.items():
            if v == curr_vad: self.combo_vad.setCurrentText(k); break
        self.combo_vad.setMinimumWidth(350)
        form.addRow("음성 구간 탐지(VAD):", self.combo_vad)

        layout.addLayout(form)
        layout.addSpacing(10)
        layout.addLayout(_create_bottom_buttons(self, self._on_ok, save_callback=self._on_save, save_def_callback=self._on_save_default))   

    # --- [유틸리티 함수] ---
    def _update_chunk_display(self, value):
        self.lbl_chunk_time.setText(f"{value // 60:02d}분 {value % 60:02d}초")

    def _on_chunk_minus(self): self.slider_chunk.setValue(max(10, self.slider_chunk.value() - 10))
    def _on_chunk_plus(self): self.slider_chunk.setValue(min(1800, self.slider_chunk.value() + 10))
    def _on_chunk_all_toggled(self, checked):
        for w in [self.slider_chunk, self.btn_chunk_minus, self.btn_chunk_plus]: w.setEnabled(not checked)
        self.lbl_chunk_time.setText("전체 진행") if checked else self._update_chunk_display(self.slider_chunk.value())
        self.lbl_chunk_time.setStyleSheet("color: #4AFF80; font-weight: bold;" if checked else "color: #FFFFFF;")

    def _update_model_info(self):
        m_data = self.combo_llm.currentData()
        if not m_data or m_data.get('name') == "사용 안함 (Whisper 단독 진행)":
            self.lbl_model_info.setText("💡 <b>LLM 미사용:</b> AI 교정을 생략하고 가장 빠르게 작업합니다.")
            return
        if 'size' not in m_data: 
            self.lbl_model_info.setText("")
            return
            
        size_gb = m_data['size'] / (1024**3)
        details = m_data.get('details', {})
        
        # 💡 [핵심] 줄바꿈 기호 없이 완벽하게 가로 한 줄로 하드코딩!
        single_line_text = f"📦 <b>용량:</b> {size_gb:.2f} GB &nbsp;&nbsp;|&nbsp;&nbsp; 🧠 <b>패밀리:</b> {details.get('family','Unknown')} &nbsp;&nbsp;|&nbsp;&nbsp; 📊 <b>파라미터:</b> {details.get('parameter_size','Unknown')} &nbsp;&nbsp;|&nbsp;&nbsp; ⚙️ <b>포맷:</b> {details.get('format','gguf').upper()}"
        
        self.lbl_model_info.setText(single_line_text)
    def _collect_settings(self):
        res = dict(self.result_settings)
        res.update({
            "selected_model": self.combo_llm.currentText(),
            "selected_whisper_model": self.combo_whisper.currentText(),
            "selected_audio_ai": self.audio_map[self.combo_audio.currentText()],
            "selected_vad": self.vad_map[self.combo_vad.currentText()],
            "google_api_key": self.input_api_key.text().strip(),
            "chunk_time_limit": 99999 if self.chk_chunk_all.isChecked() else self.slider_chunk.value()
        })
        return res

    def _on_ok(self): self.result_settings = self._collect_settings(); self.accept()
    def _on_save(self): self.result_settings = self._collect_settings(); save_settings(self.result_settings); QMessageBox.information(self, "완료", "저장되었습니다.")
    def _on_save_default(self): self.result_settings = self._collect_settings(); save_default_settings(self.result_settings); QMessageBox.information(self, "완료", "기본값 저장 완료.")