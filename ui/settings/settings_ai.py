# Version: 03.02.15
# Phase: PHASE2
"""
ui/settings_ai.py  ─  ⚙️ AI 엔진 설정 다이얼로그
"""
import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
                             QLabel, QComboBox, QMessageBox, QLineEdit, 
                             QSlider, QPushButton, QCheckBox, QTextEdit,
                             QDoubleSpinBox, QSpinBox, QTabWidget, QWidget,
                             QScrollArea)
from PyQt6.QtCore import Qt
import config
from core.project.data_manager import save_settings, save_default_settings
from ui.settings.settings_common import (
    DEFAULT_ADV_SETTINGS, DEFAULT_WHISPER_MODELS, _fetch_models, _create_bottom_buttons, DATASET_DIR
)
from ui.style import label_style, settings_button_style, settings_dialog_stylesheet
from core.llm.provider_registry import cloud_model_items
from core.llm.secure_keys import get_api_key, set_api_key
from core.audio.audio_presets import load_audio_presets, apply_audio_preset
from core.audio.stt_quality_presets import apply_stt_quality_preset, load_stt_quality_presets, normalize_stt_quality_key
from core.roughcut import DEFAULT_EDITOR_ROUGHCUT_DRAFT_PROMPT, DEFAULT_ROUGHCUT_PROMPT_V1, merge_roughcut_settings


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ AI 엔진 설정")
        # 💡 [수정] 4가지 정보가 한 줄에 다 들어오도록 너비를 700px로 확장
        self.setMinimumWidth(700) 
        self.setStyleSheet(settings_dialog_stylesheet())
        self.result_settings = dict(settings)
        self.stt_quality_presets = load_stt_quality_presets()
        self.audio_presets = load_audio_presets()

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        quick_tab, quick_form = self._make_tab_form()
        editor_tab, editor_form = self._make_tab_form()
        roughcut_tab, roughcut_form = self._make_tab_form()
        ai_tab, ai_form = self._make_tab_form()
        self.tabs.addTab(quick_tab, "빠른 설정")
        self.tabs.addTab(editor_tab, "에디터 LLM")
        self.tabs.addTab(roughcut_tab, "러프컷 LLM")
        self.tabs.addTab(ai_tab, "AI")

        stt_preset_row = QHBoxLayout()
        self.combo_stt_quality_preset = QComboBox()
        for key, preset in self.stt_quality_presets.items():
            desc = preset.get("description", "")
            label = preset.get("label", key)
            self.combo_stt_quality_preset.addItem(f"{label} - {desc}" if desc else label, key)
        self.combo_stt_quality_preset.setMinimumWidth(350)
        stt_preset_row.addWidget(self.combo_stt_quality_preset)
        quick_form.addRow("자막 정확도 프리셋:", stt_preset_row)

        preset_row = QHBoxLayout()
        self.combo_audio_preset = QComboBox()
        self.combo_audio_preset.addItem("직접 설정", "")
        for name, preset in self.audio_presets.items():
            desc = preset.get("description", "")
            self.combo_audio_preset.addItem(f"{name} - {desc}" if desc else name, name)
        self.combo_audio_preset.setMinimumWidth(350)
        preset_row.addWidget(self.combo_audio_preset)
        quick_form.addRow("오디오 프리셋:", preset_row)

        # 1. LLM 모델 (무료/유료 필터 + Ollama 설치/삭제)
        self.llm_filter = settings.get("llm_cost_filter", "all")
        self.models_data = []
        if parent is not None and getattr(parent, "_local_llm_models", None):
            self.models_data = [dict(m) for m in parent._local_llm_models]
        if not self.models_data:
            self.models_data = _fetch_models()

        filter_row = QHBoxLayout()
        self.btn_llm_all = QPushButton("전체")
        self.btn_llm_free = QPushButton("무료")
        self.btn_llm_paid = QPushButton("유료")
        for btn, value in ((self.btn_llm_all, "all"), (self.btn_llm_free, "free"), (self.btn_llm_paid, "paid")):
            btn.setCheckable(True)
            btn.setMinimumWidth(64)
            btn.clicked.connect(lambda _=False, v=value: self._set_llm_filter(v))
            filter_row.addWidget(btn)
        filter_row.addStretch()
        editor_form.addRow("LLM 필터:", filter_row)

        self.combo_llm = QComboBox()
        self.combo_llm.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_llm.setMinimumWidth(350)
        llm_model_row = QHBoxLayout()
        self.btn_ollama_delete = QPushButton("삭제")
        self.btn_ollama_delete.setMinimumWidth(64)
        self.btn_ollama_delete.setStyleSheet(settings_button_style("toolbar", min_width=64))
        self.btn_ollama_delete.clicked.connect(self._delete_current_ollama)
        llm_model_row.addWidget(self.combo_llm)
        llm_model_row.addWidget(self.btn_ollama_delete)
        editor_form.addRow("LLM 모델:", llm_model_row)

        ollama_row = QHBoxLayout()
        self.combo_ollama_catalog = QComboBox()
        self.combo_ollama_catalog.setMinimumWidth(270)
        self.btn_ollama_install = QPushButton("설치")
        self.btn_ollama_refresh = QPushButton("새로고침")
        self.btn_ollama_install.setMinimumWidth(64)
        self.btn_ollama_refresh.setMinimumWidth(82)
        self.btn_ollama_install.setStyleSheet(settings_button_style("toolbar", min_width=64))
        self.btn_ollama_refresh.setStyleSheet(settings_button_style("toolbar", min_width=82))
        self.btn_ollama_install.clicked.connect(self._install_selected_ollama)
        self.btn_ollama_refresh.clicked.connect(self._refresh_ollama_models)
        ollama_row.addWidget(self.combo_ollama_catalog)
        ollama_row.addWidget(self.btn_ollama_install)
        ollama_row.addWidget(self.btn_ollama_refresh)
        editor_form.addRow("미설치 LLM 모델:", ollama_row)

        registry_row = QHBoxLayout()
        self.combo_registry_model = QComboBox()
        self.combo_registry_model.setMinimumWidth(270)
        self.btn_registry_install = QPushButton("설치")
        self.btn_registry_delete = QPushButton("삭제")
        self.btn_registry_required = QPushButton("필수 확인")
        for btn, min_width in (
            (self.btn_registry_install, 64),
            (self.btn_registry_delete, 64),
            (self.btn_registry_required, 82),
        ):
            btn.setMinimumWidth(min_width)
            btn.setStyleSheet(settings_button_style("toolbar", min_width=min_width))
        self.btn_registry_install.clicked.connect(self._install_registry_model)
        self.btn_registry_delete.clicked.connect(self._delete_registry_model)
        self.btn_registry_required.clicked.connect(self._check_required_registry_models)
        self.combo_registry_model.currentIndexChanged.connect(self._update_registry_model_status)
        registry_row.addWidget(self.combo_registry_model)
        registry_row.addWidget(self.btn_registry_install)
        registry_row.addWidget(self.btn_registry_delete)
        registry_row.addWidget(self.btn_registry_required)
        editor_form.addRow("모델 관리:", registry_row)

        self.lbl_registry_model_status = QLabel("")
        self.lbl_registry_model_status.setWordWrap(True)
        self.lbl_registry_model_status.setStyleSheet(label_style("muted", 10) + "padding: 0 5px 8px 5px;")
        editor_form.addRow("", self.lbl_registry_model_status)

        self._reload_ollama_catalog()
        self._reload_registry_models()
        self._rebuild_llm_combo(settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b")))

        # 💡 [레이아웃 조정] LLM 메뉴 바로 밑에 4가지 정보를 한 줄로 표시
        self.lbl_model_info = QLabel()
        self.lbl_model_info.setStyleSheet(label_style("muted", 11) + "padding: 2px 5px 12px 5px;")
        self.lbl_model_info.setWordWrap(False) # 💡 자동 줄바꿈 강제 차단!
        editor_form.addRow("", self.lbl_model_info)
        self.combo_llm.currentIndexChanged.connect(self._update_model_info)
        self._update_model_info()

        # 2. API Keys (OS 보안 저장소)
        self.input_api_key = QLineEdit()
        self.input_api_key.setPlaceholderText("AI Studio 발급 Google API Key 입력")
        self.input_api_key.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.input_api_key.setText(get_api_key("google"))
        editor_form.addRow("Google API Key:", self.input_api_key)

        self.input_openai_api_key = QLineEdit()
        self.input_openai_api_key.setPlaceholderText("OpenAI API Key 입력")
        self.input_openai_api_key.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.input_openai_api_key.setText(get_api_key("openai"))
        editor_form.addRow("OpenAI API Key:", self.input_openai_api_key)

        self._build_editor_llm_prompt_section(editor_form, settings)
        self._build_editor_roughcut_draft_section(editor_form, settings)

        self.spin_editor_llm_threads = QSpinBox()
        self.spin_editor_llm_threads.setRange(1, 16)
        editor_thread_default = DEFAULT_ADV_SETTINGS.get("llm_threads", settings.get("llm_workers", 4))
        self.spin_editor_llm_threads.setValue(int(settings.get("llm_threads", settings.get("llm_workers", editor_thread_default)) or 4))
        editor_form.addRow("에디터 LLM 처리 스레드:", self.spin_editor_llm_threads)

        self._build_roughcut_llm_section(roughcut_form, settings)

        # 3. 자막 묶음 단위 (슬라이더 세팅)
        chunk_layout = QHBoxLayout()
        self.btn_chunk_minus = QPushButton("-")
        self.btn_chunk_minus.setFixedWidth(54)
        self.btn_chunk_minus.setStyleSheet(settings_button_style("toolbar", min_width=30))
        self.btn_chunk_minus.clicked.connect(self._on_chunk_minus)
        
        self.slider_chunk = QSlider(Qt.Orientation.Horizontal)
        self.slider_chunk.setRange(10, 1800)
        self.slider_chunk.setSingleStep(10)
        self.slider_chunk.setPageStep(60)
        self.slider_chunk.valueChanged.connect(self._update_chunk_display)
        
        self.btn_chunk_plus = QPushButton("+")
        self.btn_chunk_plus.setFixedWidth(54)
        self.btn_chunk_plus.setStyleSheet(settings_button_style("toolbar", min_width=30))
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
        editor_form.addRow("자막 묶음 단위:", chunk_layout)
        
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
        for idx, model_name in enumerate(w_models):
            if "ghost613" in model_name:
                self.combo_whisper.setItemText(idx, f"{model_name} (실험)")
        self.combo_whisper.setMinimumWidth(350)
        curr_w = settings.get("selected_whisper_model", getattr(config, "WHISPER_MODEL", w_models[0] if w_models else ""))
        # ── OS에 맞지 않는 저장값이면 기본값으로 교체 ──
        if not config.IS_MAC and "mlx-community" in curr_w:
            curr_w = "large-v3"
        elif config.IS_MAC and curr_w in ("large-v3", "large-v3-turbo", "medium", "small", "base", "tiny"):
            curr_w = "mlx-community/whisper-large-v3-mlx"
        display_values = [self.combo_whisper.itemText(i).replace(" (실험)", "") for i in range(self.combo_whisper.count())]
        if curr_w in display_values:
            self.combo_whisper.setCurrentText(curr_w)
            for i, value in enumerate(display_values):
                if value == curr_w:
                    self.combo_whisper.setCurrentIndex(i)
                    break
        else:
            self.combo_whisper.setCurrentIndex(0)
        self.combo_whisper.blockSignals(False)
        self.combo_whisper.setUpdatesEnabled(True)
        ai_form.addRow("Whisper 모델:", self.combo_whisper)

        # 5. 음성 처리 AI
        self.combo_audio = QComboBox()
        self.audio_map = {"Demucs (스튜디오급 보컬 분리)": "demucs", "DeepFilterNet (AI 노이즈 제거)": "deepfilter", "사용 안함": "none"}
        for k in self.audio_map: self.combo_audio.addItem(k)
        curr_audio = settings.get("selected_audio_ai", "demucs")
        for k, v in self.audio_map.items():
            if v == curr_audio: self.combo_audio.setCurrentText(k); break
        self.combo_audio.setMinimumWidth(350)
        ai_form.addRow("음성 처리 AI:", self.combo_audio)

        # 6. VAD
        self.combo_vad = QComboBox()
        self.vad_map = {"Silero (권장)": "silero", "사용 안 함": "none"}
        for k in self.vad_map: self.combo_vad.addItem(k)
        curr_vad = settings.get("selected_vad", "silero")
        for k, v in self.vad_map.items():
            if v == curr_vad: self.combo_vad.setCurrentText(k); break
        self.combo_vad.setMinimumWidth(350)
        ai_form.addRow("음성 구간 탐지(VAD):", self.combo_vad)
        self._build_subtitle_quality_section(ai_form, settings)
        self._sync_stt_quality_preset_combo(settings.get("stt_quality_preset", "balanced"))
        self._sync_audio_preset_combo(settings.get("audio_preset", ""))
        self._update_editor_roughcut_draft_state()
        self.combo_stt_quality_preset.currentIndexChanged.connect(self._on_stt_quality_preset_changed)
        self.combo_audio_preset.currentIndexChanged.connect(self._on_audio_preset_changed)

        layout.addWidget(self.tabs)
        layout.addSpacing(10)
        layout.addLayout(_create_bottom_buttons(self, self._on_ok, save_callback=self._on_save, save_def_callback=self._on_save_default))   

    def _make_tab_form(self):
        content = QWidget()
        form = QFormLayout(content)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        tab = QScrollArea()
        tab.setWidgetResizable(True)
        tab.setWidget(content)
        return tab, form

    def _is_paid_item(self, item: dict) -> bool:
        details = dict(item.get("details", {}) or {})
        provider = details.get("provider", "ollama")
        billing = str(details.get("billing", "")).lower()
        return provider in ("openai", "google") and "무료" not in billing

    def _all_llm_items(self):
        items = []
        bypass = {"name": "사용 안함 (Whisper 단독 진행)", "size": 0, "details": {"provider": "none", "billing": "무료"}, "display_name": "사용 안함 (Whisper 단독 진행)"}
        items.append(bypass)
        for m in self.models_data:
            item = dict(m)
            details = dict(item.get("details", {}) or {})
            details.setdefault("provider", "ollama")
            details.setdefault("format", "ollama")
            details.setdefault("billing", "무료/로컬")
            item["details"] = details
            item.setdefault("display_name", f"{item.get('name', '')} [무료/로컬]")
            items.append(item)
        items.extend(cloud_model_items())
        return items

    def _reload_registry_models(self, preferred_id: str = ""):
        self.combo_registry_model.blockSignals(True)
        self.combo_registry_model.clear()
        try:
            from core.model_manager import get_available_models
            self._registry_models = get_available_models(include_hidden=True)
        except Exception as e:
            self._registry_models = []
            self.combo_registry_model.addItem(f"모델 목록 로드 실패: {e}", {})
        for model in self._registry_models:
            status = "설치됨" if model.get("installed") else "미설치"
            required = "필수" if model.get("required") else "선택"
            label = f"[{model.get('category', '-')}] {model.get('name', model.get('id', ''))} · {status} · {required}"
            self.combo_registry_model.addItem(label, model)
        if self.combo_registry_model.count() == 0:
            self.combo_registry_model.addItem("현재 OS에서 관리할 모델 없음", {})
        for i in range(self.combo_registry_model.count()):
            data = self.combo_registry_model.itemData(i) or {}
            if preferred_id and data.get("id") == preferred_id:
                self.combo_registry_model.setCurrentIndex(i)
                break
        self.combo_registry_model.blockSignals(False)
        self._update_registry_model_status()

    def _current_registry_model(self) -> dict:
        return dict(self.combo_registry_model.currentData() or {})

    def _update_registry_model_status(self):
        model = self._current_registry_model()
        if not model:
            self.lbl_registry_model_status.setText("현재 OS에서 사용할 모델 항목이 없습니다.")
            self.btn_registry_install.setEnabled(False)
            self.btn_registry_delete.setEnabled(False)
            return

        installed = bool(model.get("installed"))
        required = "필수 모델" if model.get("required") else "선택 모델"
        os_label = ", ".join(model.get("os", []))
        pip_label = ", ".join(model.get("pip_packages", [])) or "외부 앱/파일"
        path_label = model.get("model_path") or "내장/캐시"
        self.lbl_registry_model_status.setText(
            f"{'✅ 설치됨' if installed else '⚠️ 미설치'} · {required} · OS: {os_label} · 패키지: {pip_label} · 경로: {path_label}"
        )
        self.btn_registry_install.setEnabled(not installed)
        self.btn_registry_delete.setEnabled(installed and model.get("id") != "ollama")

    def _install_registry_model(self):
        model = self._current_registry_model()
        if not model:
            return
        if model.get("id") == "ollama":
            QMessageBox.information(self, "모델 관리", "Ollama는 외부 앱 설치가 필요합니다.\nhttps://ollama.com/download")
            return
        if QMessageBox.question(self, "모델 설치", f"{model.get('name', model.get('id'))} 모델을 설치할까요?") != QMessageBox.StandardButton.Yes:
            return
        from core.model_manager import install_model
        ok = install_model(model)
        QMessageBox.information(self, "모델 관리", "설치 완료" if ok else "설치 실패. 터미널 로그를 확인하세요.")
        self._reload_registry_models(model.get("id", ""))

    def _delete_registry_model(self):
        model = self._current_registry_model()
        if not model:
            return
        if QMessageBox.question(self, "모델 삭제", f"{model.get('name', model.get('id'))} 모델을 삭제할까요?") != QMessageBox.StandardButton.Yes:
            return
        from core.model_manager import uninstall_model
        ok = uninstall_model(model)
        QMessageBox.information(self, "모델 관리", "삭제 완료" if ok else "삭제 실패. 터미널 로그를 확인하세요.")
        self._reload_registry_models(model.get("id", ""))

    def _check_required_registry_models(self):
        try:
            from core.model_manager import get_required_models
            missing = get_required_models()
        except Exception as e:
            QMessageBox.warning(self, "필수 모델 확인", f"필수 모델 확인 실패:\n{e}")
            return
        if not missing:
            QMessageBox.information(self, "필수 모델 확인", "현재 OS의 필수 모델이 모두 준비되어 있습니다.")
            return
        lines = [f"- {m.get('name', m.get('id', 'unknown'))}" for m in missing]
        QMessageBox.warning(
            self,
            "필수 모델 확인",
            "현재 OS에서 필요한 모델이 아직 설치되지 않았습니다.\n\n" + "\n".join(lines)
        )

    def _set_llm_filter(self, value):
        self.llm_filter = value
        current = (self.combo_llm.currentData() or {}).get("name", "") if hasattr(self, "combo_llm") else ""
        self._rebuild_llm_combo(current)

    def _sync_llm_filter_buttons(self):
        for btn, value in ((self.btn_llm_all, "all"), (self.btn_llm_free, "free"), (self.btn_llm_paid, "paid")):
            btn.blockSignals(True)
            btn.setChecked(self.llm_filter == value)
            btn.setStyleSheet(settings_button_style("primary" if self.llm_filter == value else "toolbar", min_width=64))
            btn.blockSignals(False)

    def _rebuild_llm_combo(self, preferred_name=""):
        self._sync_llm_filter_buttons()
        self.combo_llm.blockSignals(True)
        self.combo_llm.clear()
        for item in self._all_llm_items():
            paid = self._is_paid_item(item)
            if self.llm_filter == "free" and paid:
                continue
            if self.llm_filter == "paid" and not paid:
                continue
            self.combo_llm.addItem(item.get("display_name", item.get("name", "")), item)
        for i in range(self.combo_llm.count()):
            data = self.combo_llm.itemData(i) or {}
            if data.get("name") == preferred_name or self.combo_llm.itemText(i) == preferred_name:
                self.combo_llm.setCurrentIndex(i)
                break
        self.combo_llm.blockSignals(False)
        if hasattr(self, "lbl_model_info"):
            self._update_model_info()

    def _reload_ollama_catalog(self):
        self.combo_ollama_catalog.clear()
        try:
            from core.model_manager import get_ollama_catalog_models
            for row in get_ollama_catalog_models():
                if row.get("installed"):
                    continue
                self.combo_ollama_catalog.addItem(row.get('label', row['name']), row)
            if self.combo_ollama_catalog.count() == 0:
                self.combo_ollama_catalog.addItem("설치 가능한 미설치 모델 없음", {})
        except Exception as e:
            self.combo_ollama_catalog.addItem(f"Ollama 확인 실패: {e}", {})

    def _sync_audio_preset_combo(self, preset_name: str):
        self.combo_audio_preset.blockSignals(True)
        for i in range(self.combo_audio_preset.count()):
            if self.combo_audio_preset.itemData(i) == preset_name:
                self.combo_audio_preset.setCurrentIndex(i)
                break
        self.combo_audio_preset.blockSignals(False)

    def _sync_stt_quality_preset_combo(self, preset_key: str):
        key = normalize_stt_quality_key(preset_key)
        self.combo_stt_quality_preset.blockSignals(True)
        for i in range(self.combo_stt_quality_preset.count()):
            if self.combo_stt_quality_preset.itemData(i) == key:
                self.combo_stt_quality_preset.setCurrentIndex(i)
                break
        self.combo_stt_quality_preset.blockSignals(False)

    def _set_combo_by_data_value(self, combo, value: str, mapping: dict | None = None):
        if value is None:
            return False
        if mapping:
            for text, data_value in mapping.items():
                if data_value == value:
                    combo.setCurrentText(text)
                    return True
            return False
        for i in range(combo.count()):
            if combo.itemText(i) == value:
                combo.setCurrentIndex(i)
                return True
        return False

    def _set_llm_combo_by_name(self, model_name: str):
        if not model_name:
            return False
        for i in range(self.combo_llm.count()):
            data = self.combo_llm.itemData(i) or {}
            if data.get("name") == model_name or self.combo_llm.itemText(i) == model_name:
                self.combo_llm.setCurrentIndex(i)
                return True
        if self.llm_filter != "all":
            old_filter = self.llm_filter
            self.llm_filter = "all"
            self._rebuild_llm_combo(model_name)
            if self._set_llm_combo_by_name(model_name):
                return True
            self.llm_filter = old_filter
            self._rebuild_llm_combo((self.combo_llm.currentData() or {}).get("name", ""))
        return False

    def _build_roughcut_llm_section(self, form: QFormLayout, settings: dict):
        roughcut_settings = merge_roughcut_settings(settings)
        self.chk_roughcut_llm_enabled = QCheckBox("러프컷 분석에서 LLM 사용")
        self.chk_roughcut_llm_enabled.setChecked(bool(roughcut_settings.get("roughcut_llm_enabled", False)))
        form.addRow("", self.chk_roughcut_llm_enabled)

        self.chk_roughcut_llm_override = QCheckBox("기존 자막 생성 LLM 설정 대신 러프컷 전용 설정 사용")
        self.chk_roughcut_llm_override.setChecked(bool(roughcut_settings.get("roughcut_llm_use_override", False)))
        form.addRow("", self.chk_roughcut_llm_override)

        provider_row = QHBoxLayout()
        self.combo_roughcut_llm_provider = QComboBox()
        for label, value in (("상속", "inherit"), ("Ollama", "ollama"), ("OpenAI", "openai"), ("Gemini", "google"), ("사용 안 함", "none")):
            self.combo_roughcut_llm_provider.addItem(label, value)
        self._set_combo_data(self.combo_roughcut_llm_provider, roughcut_settings.get("roughcut_llm_provider", "inherit"))
        provider_row.addWidget(self.combo_roughcut_llm_provider)

        self.input_roughcut_llm_model = QLineEdit()
        self.input_roughcut_llm_model.setPlaceholderText("inherit 또는 러프컷 전용 모델명")
        self.input_roughcut_llm_model.setText(str(roughcut_settings.get("roughcut_llm_model") or "inherit"))
        provider_row.addWidget(self.input_roughcut_llm_model)
        form.addRow("Provider / Model:", provider_row)

        key_temp_row = QHBoxLayout()
        self.combo_roughcut_api_key_mode = QComboBox()
        for label, value in (("상속", "inherit"), ("별도 저장 키", "separate")):
            self.combo_roughcut_api_key_mode.addItem(label, value)
        self._set_combo_data(self.combo_roughcut_api_key_mode, roughcut_settings.get("roughcut_llm_api_key_mode", "inherit"))
        key_temp_row.addWidget(self.combo_roughcut_api_key_mode)

        self.spin_roughcut_temperature = QDoubleSpinBox()
        self.spin_roughcut_temperature.setRange(0.0, 1.0)
        self.spin_roughcut_temperature.setSingleStep(0.1)
        self.spin_roughcut_temperature.setDecimals(1)
        self.spin_roughcut_temperature.setValue(float(roughcut_settings.get("roughcut_llm_temperature", 0.2) or 0.2))
        key_temp_row.addWidget(QLabel("Temperature"))
        key_temp_row.addWidget(self.spin_roughcut_temperature)
        form.addRow("API Key / 온도:", key_temp_row)

        rows_layout = QHBoxLayout()
        self.spin_roughcut_context_rows = QSpinBox()
        self.spin_roughcut_context_rows.setRange(1, 500)
        self.spin_roughcut_context_rows.setValue(int(roughcut_settings.get("roughcut_llm_max_context_rows", 80) or 80))
        self.spin_roughcut_chunk_rows = QSpinBox()
        self.spin_roughcut_chunk_rows.setRange(1, 100)
        self.spin_roughcut_chunk_rows.setValue(int(roughcut_settings.get("roughcut_llm_chunk_rows", 12) or 12))
        self.spin_roughcut_lookahead_rows = QSpinBox()
        self.spin_roughcut_lookahead_rows.setRange(0, 100)
        self.spin_roughcut_lookahead_rows.setValue(int(roughcut_settings.get("roughcut_llm_lookahead_rows", 8) or 8))
        for label, widget in (
            ("문맥", self.spin_roughcut_context_rows),
            ("묶음", self.spin_roughcut_chunk_rows),
            ("다음", self.spin_roughcut_lookahead_rows),
        ):
            rows_layout.addWidget(QLabel(label))
            rows_layout.addWidget(widget)
        form.addRow("자막 row:", rows_layout)

        prompt_row = QVBoxLayout()
        self.input_roughcut_prompt = QTextEdit()
        self.input_roughcut_prompt.setMinimumHeight(120)
        self.input_roughcut_prompt.setPlainText(str(roughcut_settings.get("roughcut_llm_prompt") or "").strip() or DEFAULT_ROUGHCUT_PROMPT_V1)
        prompt_row.addWidget(self.input_roughcut_prompt)
        prompt_buttons = QHBoxLayout()
        prompt_buttons.addStretch()
        self.btn_roughcut_prompt_default = QPushButton("기본값 복원")
        self.btn_roughcut_prompt_default.setStyleSheet(settings_button_style("toolbar", min_width=96))
        self.btn_roughcut_prompt_default.clicked.connect(lambda: self.input_roughcut_prompt.setPlainText(DEFAULT_ROUGHCUT_PROMPT_V1))
        prompt_buttons.addWidget(self.btn_roughcut_prompt_default)
        prompt_row.addLayout(prompt_buttons)
        form.addRow("러프컷 프롬프트:", prompt_row)

        self.spin_roughcut_llm_threads = QSpinBox()
        self.spin_roughcut_llm_threads.setRange(1, 16)
        self.spin_roughcut_llm_threads.setValue(int(roughcut_settings.get("roughcut_llm_threads", 4) or 4))
        form.addRow("러프컷 LLM 처리 스레드:", self.spin_roughcut_llm_threads)

    def _build_editor_llm_prompt_section(self, form: QFormLayout, settings: dict):
        prompt_layout = QVBoxLayout()
        lbl_sys = QLabel("[시스템 프롬프트] 수정 불가")
        lbl_sys.setStyleSheet(label_style("muted", 11, bold=True))
        prompt_layout.addWidget(lbl_sys)

        self.edit_system_prompt = QTextEdit()
        self.edit_system_prompt.setReadOnly(True)
        self.edit_system_prompt.setMinimumHeight(105)
        self.edit_system_prompt.setPlainText(str(getattr(config, "DEFAULT_LLM_PROMPT", "") or "").strip())
        self.edit_system_prompt.setStyleSheet("color: #8E98A1;")
        prompt_layout.addWidget(self.edit_system_prompt)

        lbl_user = QLabel("[사용자 프롬프트]")
        lbl_user.setStyleSheet(label_style("text", 11, bold=True))
        prompt_layout.addWidget(lbl_user)

        self.edit_user_prompt = QTextEdit()
        self.edit_user_prompt.setMinimumHeight(105)
        self.edit_user_prompt.setPlainText(str(settings.get("user_prompt", settings.get("llm_prompt", "")) or ""))
        self.edit_user_prompt.setPlaceholderText("예: 고유명사는 원문 표기를 유지하고, 차량명/지명은 임의로 바꾸지 마세요.")
        prompt_layout.addWidget(self.edit_user_prompt)
        form.addRow("LLM 프롬프트:", prompt_layout)

    def _build_editor_roughcut_draft_section(self, form: QFormLayout, settings: dict):
        roughcut_settings = merge_roughcut_settings(settings)
        self.chk_editor_roughcut_draft_enabled = QCheckBox("자막 생성 중 러프컷 초안 생성")
        self.chk_editor_roughcut_draft_enabled.setChecked(bool(roughcut_settings.get("editor_roughcut_draft_enabled", False)))
        form.addRow("러프컷 초안:", self.chk_editor_roughcut_draft_enabled)

        prompt_layout = QVBoxLayout()
        self.input_editor_roughcut_draft_prompt = QTextEdit()
        self.input_editor_roughcut_draft_prompt.setMinimumHeight(100)
        self.input_editor_roughcut_draft_prompt.setPlainText(
            str(roughcut_settings.get("editor_roughcut_draft_prompt") or "").strip()
            or DEFAULT_EDITOR_ROUGHCUT_DRAFT_PROMPT
        )
        prompt_layout.addWidget(self.input_editor_roughcut_draft_prompt)
        prompt_buttons = QHBoxLayout()
        prompt_buttons.addStretch()
        self.btn_editor_roughcut_prompt_default = QPushButton("기본값 복원")
        self.btn_editor_roughcut_prompt_default.setStyleSheet(settings_button_style("toolbar", min_width=96))
        self.btn_editor_roughcut_prompt_default.clicked.connect(
            lambda: self.input_editor_roughcut_draft_prompt.setPlainText(DEFAULT_EDITOR_ROUGHCUT_DRAFT_PROMPT)
        )
        prompt_buttons.addWidget(self.btn_editor_roughcut_prompt_default)
        prompt_layout.addLayout(prompt_buttons)
        form.addRow("초안 프롬프트:", prompt_layout)

    def _build_subtitle_quality_section(self, form: QFormLayout, settings: dict):
        section = QLabel("자막 품질")
        section.setStyleSheet(label_style("text", 13, bold=True) + "padding: 10px 5px 2px 5px;")
        form.addRow("", section)

        self.chk_subtitle_quality_enabled = QCheckBox("검사 기능 사용")
        self.chk_subtitle_quality_enabled.setChecked(bool(settings.get("subtitle_quality_enabled", False)))
        form.addRow("자막 품질 검사:", self.chk_subtitle_quality_enabled)

        self.chk_subtitle_quality_auto_check = QCheckBox("자막 생성 후 자동 검사")
        self.chk_subtitle_quality_auto_check.setChecked(bool(settings.get("subtitle_quality_auto_check_after_generate", False)))
        form.addRow("자동 검사:", self.chk_subtitle_quality_auto_check)

        self.chk_subtitle_quality_auto_correct = QCheckBox("자동 교정 허용")
        self.chk_subtitle_quality_auto_correct.setChecked(bool(settings.get("subtitle_quality_auto_correct_enabled", False)))
        form.addRow("자동 교정:", self.chk_subtitle_quality_auto_correct)

        self.chk_correction_memory_enabled = QCheckBox("사용자 교정 memory 사용")
        self.chk_correction_memory_enabled.setChecked(bool(settings.get("correction_memory_enabled", True)))
        form.addRow("교정 memory:", self.chk_correction_memory_enabled)

        self.chk_wrong_answer_memory_enabled = QCheckBox("오답 memory 사용")
        self.chk_wrong_answer_memory_enabled.setChecked(bool(settings.get("wrong_answer_memory_enabled", True)))
        form.addRow("오답 memory:", self.chk_wrong_answer_memory_enabled)

        self.spin_quality_threshold = QSpinBox()
        self.spin_quality_threshold.setRange(70, 100)
        self.spin_quality_threshold.setSuffix(" 점")
        self.spin_quality_threshold.setValue(int(settings.get(
            "review_auto_correct_apply_threshold",
            DEFAULT_ADV_SETTINGS.get("review_auto_correct_apply_threshold", 92),
        ) or 92))
        form.addRow("자동 적용 최소 점수:", self.spin_quality_threshold)

        self.spin_quality_recheck_buffer = QDoubleSpinBox()
        self.spin_quality_recheck_buffer.setRange(0.5, 3.0)
        self.spin_quality_recheck_buffer.setSingleStep(0.1)
        self.spin_quality_recheck_buffer.setDecimals(1)
        self.spin_quality_recheck_buffer.setSuffix(" 초")
        self.spin_quality_recheck_buffer.setValue(float(settings.get(
            "review_recheck_buffer_sec",
            DEFAULT_ADV_SETTINGS.get("review_recheck_buffer_sec", 1.2),
        ) or 1.2))
        form.addRow("재검사 앞뒤 버퍼:", self.spin_quality_recheck_buffer)

    def _set_combo_data(self, combo: QComboBox, value: str):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return True
        return False

    def _on_audio_preset_changed(self, *args):
        preset_name = self.combo_audio_preset.currentData()
        if not preset_name:
            self.result_settings["audio_preset"] = ""
            return

        self.result_settings = apply_audio_preset(self.result_settings, preset_name)
        self._set_combo_by_data_value(self.combo_audio, self.result_settings.get("selected_audio_ai"), self.audio_map)
        self._set_combo_by_data_value(self.combo_vad, self.result_settings.get("selected_vad"), self.vad_map)
        self._set_combo_by_data_value(self.combo_whisper, self.result_settings.get("selected_whisper_model"))
        self._set_llm_combo_by_name(self.result_settings.get("selected_model", ""))
        self._update_model_info()

    def _on_stt_quality_preset_changed(self, *args):
        preset_key = self.combo_stt_quality_preset.currentData() or "balanced"
        self.result_settings = apply_stt_quality_preset(self.result_settings, preset_key)
        self._set_combo_by_data_value(self.combo_whisper, self.result_settings.get("selected_whisper_model"))
        self._set_llm_combo_by_name(self.result_settings.get("selected_model", ""))
        self._update_editor_roughcut_draft_state()
        self._update_model_info()

    def _update_editor_roughcut_draft_state(self):
        if not hasattr(self, "chk_editor_roughcut_draft_enabled"):
            return
        is_fast = (self.combo_stt_quality_preset.currentData() or "") == "fast"
        self.chk_editor_roughcut_draft_enabled.setEnabled(not is_fast)
        self.input_editor_roughcut_draft_prompt.setEnabled(not is_fast)
        self.btn_editor_roughcut_prompt_default.setEnabled(not is_fast)
        if is_fast:
            self.chk_editor_roughcut_draft_enabled.setChecked(False)

    def _refresh_ollama_models(self):
        self.models_data = _fetch_models()
        self._reload_ollama_catalog()
        self._rebuild_llm_combo((self.combo_llm.currentData() or {}).get("name", ""))

    def _install_selected_ollama(self):
        data = self.combo_ollama_catalog.currentData() or {}
        name = data.get("name", "")
        if not name:
            return
        if QMessageBox.question(self, "Ollama 모델 설치", f"{name} 모델을 설치할까요?") != QMessageBox.StandardButton.Yes:
            return
        from core.model_manager import install_ollama_model
        ok = install_ollama_model(name)
        QMessageBox.information(self, "Ollama", "설치 완료" if ok else "설치 실패. 로그를 확인하세요.")
        self._refresh_ollama_models()

    def _delete_current_ollama(self):
        data = self.combo_llm.currentData() or {}
        details = dict(data.get("details", {}) or {})
        name = data.get("name", "")
        if details.get("provider") != "ollama" or not name:
            QMessageBox.information(self, "Ollama", "삭제할 로컬 Ollama 모델을 선택하세요.")
            return
        if QMessageBox.question(self, "Ollama 모델 삭제", f"{name} 모델을 삭제할까요?") != QMessageBox.StandardButton.Yes:
            return
        from core.model_manager import uninstall_ollama_model
        ok = uninstall_ollama_model(name)
        QMessageBox.information(self, "Ollama", "삭제 완료" if ok else "삭제 실패. 로그를 확인하세요.")
        self._refresh_ollama_models()

    # --- [유틸리티 함수] ---
    def _update_chunk_display(self, value):
        self.lbl_chunk_time.setText(f"{value // 60:02d}분 {value % 60:02d}초")

    def _on_chunk_minus(self): self.slider_chunk.setValue(max(10, self.slider_chunk.value() - 10))
    def _on_chunk_plus(self): self.slider_chunk.setValue(min(1800, self.slider_chunk.value() + 10))
    def _on_chunk_all_toggled(self, checked):
        for w in [self.slider_chunk, self.btn_chunk_minus, self.btn_chunk_plus]: w.setEnabled(not checked)
        self.lbl_chunk_time.setText("전체 진행") if checked else self._update_chunk_display(self.slider_chunk.value())
        self.lbl_chunk_time.setStyleSheet(label_style("accent" if checked else "text", 12, bold=True))

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
        billing = details.get('billing', '무료/로컬' if details.get('format') == 'ollama' else '')
        single_line_text = f"📦 <b>용량:</b> {size_gb:.2f} GB &nbsp;&nbsp;|&nbsp;&nbsp; 🧠 <b>패밀리:</b> {details.get('family','Unknown')} &nbsp;&nbsp;|&nbsp;&nbsp; 📊 <b>파라미터:</b> {details.get('parameter_size','Unknown')} &nbsp;&nbsp;|&nbsp;&nbsp; ⚙️ <b>포맷:</b> {details.get('format','gguf').upper()} &nbsp;&nbsp;|&nbsp;&nbsp; 💳 <b>비용:</b> {billing}"
        
        self.lbl_model_info.setText(single_line_text)
    def _collect_settings(self):
        res = dict(self.result_settings)
        m_data = self.combo_llm.currentData() or {}
        provider = (m_data.get('details', {}) or {}).get('provider', 'ollama')
        google_key_saved = set_api_key("google", self.input_api_key.text().strip())
        openai_key_saved = set_api_key("openai", self.input_openai_api_key.text().strip())
        res.update({
            "selected_model": m_data.get('name') or self.combo_llm.currentText(),
            "selected_llm_provider": provider,
            "selected_whisper_model": self.combo_whisper.currentText().replace(" (실험)", ""),
            "selected_audio_ai": self.audio_map[self.combo_audio.currentText()],
            "selected_vad": self.vad_map[self.combo_vad.currentText()],
            "google_api_key_saved": bool(google_key_saved),
            "openai_api_key_saved": bool(openai_key_saved),
            "chunk_time_limit": 99999 if self.chk_chunk_all.isChecked() else self.slider_chunk.value(),
            "llm_cost_filter": self.llm_filter,
            "user_prompt": self.edit_user_prompt.toPlainText().strip(),
            "editor_roughcut_draft_enabled": self.chk_editor_roughcut_draft_enabled.isChecked(),
            "editor_roughcut_draft_prompt": self.input_editor_roughcut_draft_prompt.toPlainText().strip() or DEFAULT_EDITOR_ROUGHCUT_DRAFT_PROMPT,
            "llm_threads": int(self.spin_editor_llm_threads.value()),
            "llm_workers": int(self.spin_editor_llm_threads.value()),
            "audio_preset": self.combo_audio_preset.currentData() or "",
            "stt_quality_preset": self.combo_stt_quality_preset.currentData() or "balanced",
            "subtitle_quality_enabled": bool(self.chk_subtitle_quality_enabled.isChecked()),
            "subtitle_quality_auto_check_after_generate": bool(self.chk_subtitle_quality_auto_check.isChecked()),
            "subtitle_quality_auto_correct_enabled": bool(self.chk_subtitle_quality_auto_correct.isChecked()),
            "correction_memory_enabled": bool(self.chk_correction_memory_enabled.isChecked()),
            "wrong_answer_memory_enabled": bool(self.chk_wrong_answer_memory_enabled.isChecked()),
            "review_auto_correct_apply_threshold": int(self.spin_quality_threshold.value()),
            "review_recheck_buffer_sec": round(float(self.spin_quality_recheck_buffer.value()), 2),
            "roughcut_llm_enabled": self.chk_roughcut_llm_enabled.isChecked(),
            "roughcut_llm_use_override": self.chk_roughcut_llm_override.isChecked(),
            "roughcut_llm_provider": self.combo_roughcut_llm_provider.currentData() or "inherit",
            "roughcut_llm_model": self.input_roughcut_llm_model.text().strip() or "inherit",
            "roughcut_llm_api_key_mode": self.combo_roughcut_api_key_mode.currentData() or "inherit",
            "roughcut_llm_temperature": round(float(self.spin_roughcut_temperature.value()), 2),
            "roughcut_llm_max_context_rows": int(self.spin_roughcut_context_rows.value()),
            "roughcut_llm_chunk_rows": int(self.spin_roughcut_chunk_rows.value()),
            "roughcut_llm_lookahead_rows": int(self.spin_roughcut_lookahead_rows.value()),
            "roughcut_llm_prompt": self.input_roughcut_prompt.toPlainText().strip() or DEFAULT_ROUGHCUT_PROMPT_V1,
            "roughcut_llm_threads": int(self.spin_roughcut_llm_threads.value())
        })
        res.pop("google_api_key", None)
        res.pop("openai_api_key", None)
        return res

    def _on_ok(self): self.result_settings = self._collect_settings(); self.accept()
    def _on_save(self): self.result_settings = self._collect_settings(); save_settings(self.result_settings); QMessageBox.information(self, "완료", "저장되었습니다.")
    def _on_save_default(self): self.result_settings = self._collect_settings(); save_default_settings(self.result_settings); QMessageBox.information(self, "완료", "기본값 저장 완료.")
