# Version: 03.14.17
# Phase: PHASE2
"""
ui/settings_ai.py  ─  ⚙️ AI 엔진 설정 다이얼로그
"""
import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QGridLayout,
                             QLabel, QComboBox, QMessageBox, QLineEdit, 
                             QSlider, QPushButton, QCheckBox, QTextEdit,
                             QDoubleSpinBox, QSpinBox, QTabWidget, QWidget,
                             QScrollArea, QSizePolicy)
from PyQt6.QtCore import Qt
from core.runtime import config
from core.project.data_manager import save_settings, save_default_settings
from ui.settings.settings_common import (
    DEFAULT_ADV_SETTINGS, DEFAULT_WHISPER_MODELS, WINDOWS_WHISPER_MODELS,
    _fetch_models, _create_bottom_buttons, filter_available_whisper_models,
)
from ui.settings.qml_panel import create_settings_header
from ui.settings.tablet_dialog import apply_tablet_dialog_profile
from ui.style import label_style, settings_button_style, settings_dialog_stylesheet, line_icon
from core.llm.provider_registry import cloud_model_items
from core.llm.secure_keys import get_api_key, set_api_key
from core.audio import audio_presets as _audio_presets
from core.audio.preset_auto_classifier import auto_classify_media_presets, apply_auto_classified_presets
from core.audio.stt_quality_presets import (
    STT_QUALITY_PRESET_ORDER,
    load_stt_quality_presets,
    normalize_stt_quality_key,
    stt_quality_label,
)
from core.accuracy_policy import apply_accuracy_first_runtime_settings
from core.mode_policy import mode_to_stt_quality, selected_mode_from_settings
from core.settings_simplifier import (
    apply_simple_operation_mode,
    normalize_simple_operation_mode,
    simple_operation_mode_items,
    simple_operation_mode_summary,
)
from ui.settings.settings_roughcut import SettingsRoughcutMixin
from core.path_manager import (
    get_icloud_auto_detect,
    get_icloud_path,
    get_nas_auto_detect,
    get_nas_path,
    load_settings as load_path_settings,
    save_settings as save_path_settings,
)


def _resolve_audio_preset_combo_data(settings: dict | None) -> str:
    resolver = getattr(_audio_presets, "resolve_audio_preset_combo_data", None)
    if callable(resolver):
        return str(resolver(settings))

    data = dict(settings or {})
    preset_name = str(data.get("audio_preset", "") or "").strip()
    if preset_name:
        return preset_name

    default_apply_data = dict(getattr(_audio_presets, "DEFAULT_AUDIO_APPLY_DATA", {}) or {})
    if default_apply_data and all(data.get(key) == value for key, value in default_apply_data.items()):
        return "__default__"
    return ""


class SettingsDialog(QDialog, SettingsRoughcutMixin):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ AI 엔진 설정")
        self.setMinimumWidth(860)
        apply_tablet_dialog_profile(self)
        self.setStyleSheet(settings_dialog_stylesheet())
        self.result_settings = dict(settings)
        self.stt_quality_presets = load_stt_quality_presets()
        self.audio_presets = _audio_presets.load_audio_presets()

        layout = QVBoxLayout(self)
        self._qml_header = create_settings_header(
            self,
            title="AI 엔진 설정",
            subtitle="자막 검수, 러프컷, 모델/API, 자동 설정을 SceneGraph 헤더로 구성합니다.",
            badge="QML",
        )
        if self._qml_header is not None:
            layout.addWidget(self._qml_header)
        self.tabs = QTabWidget()
        editor_tab, editor_form = self._make_tab_form()
        roughcut_tab, roughcut_form = self._make_tab_form()
        ai_tab, ai_form = self._make_tab_form()
        auto_tab, auto_form = self._make_tab_form()
        self.tabs.addTab(editor_tab, "자막 검수")
        self.tabs.addTab(roughcut_tab, "중분류")
        self.tabs.addTab(ai_tab, "모델/API")
        self.tabs.addTab(auto_tab, "자동 설정")
        self.tabs.setDocumentMode(True)

        self.combo_stt_quality_preset = QComboBox()
        for key, label, summary in simple_operation_mode_items():
            self.combo_stt_quality_preset.addItem(f"{label} - {summary}" if summary else label, key)
        self.combo_stt_quality_preset.setMinimumWidth(280)

        self.combo_audio_preset = QComboBox()
        self.combo_audio_preset.addItem("직접 설정", "")
        self.combo_audio_preset.addItem("기본값 적용", "__default__")
        for name in _audio_presets.curated_audio_preset_names():
            preset = self.audio_presets.get(name)
            if not isinstance(preset, dict):
                continue
            desc = preset.get("description", "")
            self.combo_audio_preset.addItem(f"{name} - {desc}" if desc else name, name)
        self.combo_audio_preset.setMinimumWidth(280)

        self._build_subtitle_quality_section(editor_form, settings)

        # 1. 모델 관리
        self.llm_filter = "all"
        self.models_data = []
        if parent is not None and getattr(parent, "_local_llm_models", None):
            self.models_data = [dict(m) for m in parent._local_llm_models]
        if not self.models_data:
            self.models_data = _fetch_models()

        model_panel = QWidget()
        model_panel.setObjectName("AiModelDownloadPanel")
        model_grid = QGridLayout(model_panel)
        model_grid.setContentsMargins(0, 0, 0, 4)
        model_grid.setHorizontalSpacing(10)
        model_grid.setVerticalSpacing(8)
        model_grid.setColumnMinimumWidth(0, 132)
        model_grid.setColumnStretch(1, 1)
        model_grid.setColumnStretch(2, 0)

        self.combo_llm = QComboBox()
        self._fit_model_combo(self.combo_llm)
        self.btn_llm_info = QPushButton("정보 확인")
        self.btn_ollama_delete = QPushButton("삭제")
        self._fit_action_button(self.btn_llm_info, 96)
        self._fit_action_button(self.btn_ollama_delete, 78)
        self.btn_llm_info.setStyleSheet(self._settings_button_style("toolbar", min_width=82))
        self.btn_ollama_delete.setStyleSheet(self._settings_button_style("toolbar", min_width=64))
        self.btn_llm_info.clicked.connect(self._update_model_info)
        self.btn_ollama_delete.clicked.connect(self._delete_current_ollama)
        installed_buttons = QHBoxLayout()
        installed_buttons.setContentsMargins(0, 0, 0, 0)
        installed_buttons.setSpacing(8)
        installed_buttons.addWidget(self.btn_llm_info)
        installed_buttons.addWidget(self.btn_ollama_delete)
        model_grid.addWidget(self._model_grid_label("LLM 모델 정보:"), 0, 0)
        model_grid.addWidget(self.combo_llm, 0, 1)
        model_grid.addLayout(installed_buttons, 0, 2)

        ollama_buttons = QHBoxLayout()
        ollama_buttons.setContentsMargins(0, 0, 0, 0)
        ollama_buttons.setSpacing(8)
        self.combo_ollama_catalog = QComboBox()
        self._fit_model_combo(self.combo_ollama_catalog)
        self.btn_ollama_install = QPushButton("설치")
        self.btn_ollama_refresh = QPushButton("새로고침")
        self._fit_action_button(self.btn_ollama_install, 78)
        self._fit_action_button(self.btn_ollama_refresh, 96)
        self.btn_ollama_install.setStyleSheet(self._settings_button_style("toolbar", min_width=64))
        self.btn_ollama_refresh.setStyleSheet(self._settings_button_style("toolbar", min_width=82))
        self.btn_ollama_install.clicked.connect(self._install_selected_ollama)
        self.btn_ollama_refresh.clicked.connect(self._refresh_ollama_models)
        ollama_buttons.addWidget(self.btn_ollama_install)
        ollama_buttons.addWidget(self.btn_ollama_refresh)
        model_grid.addWidget(self._model_grid_label("설치 가능한 LLM:"), 1, 0)
        model_grid.addWidget(self.combo_ollama_catalog, 1, 1)
        model_grid.addLayout(ollama_buttons, 1, 2)

        registry_buttons = QHBoxLayout()
        registry_buttons.setContentsMargins(0, 0, 0, 0)
        registry_buttons.setSpacing(8)
        self.combo_registry_model = QComboBox()
        self._fit_model_combo(self.combo_registry_model)
        self.btn_registry_install = QPushButton("설치")
        self.btn_registry_delete = QPushButton("삭제")
        self.btn_registry_required = QPushButton("필수 확인")
        for btn, width, min_width in (
            (self.btn_registry_install, 78, 64),
            (self.btn_registry_delete, 78, 64),
            (self.btn_registry_required, 96, 82),
        ):
            self._fit_action_button(btn, width)
            btn.setStyleSheet(self._settings_button_style("toolbar", min_width=min_width))
        self.btn_registry_install.clicked.connect(self._install_registry_model)
        self.btn_registry_delete.clicked.connect(self._delete_registry_model)
        self.btn_registry_required.clicked.connect(self._check_required_registry_models)
        self.combo_registry_model.currentIndexChanged.connect(self._update_registry_model_status)
        registry_buttons.addWidget(self.btn_registry_install)
        registry_buttons.addWidget(self.btn_registry_delete)
        registry_buttons.addWidget(self.btn_registry_required)
        model_grid.addWidget(self._model_grid_label("필수/STT 모델:"), 2, 0)
        model_grid.addWidget(self.combo_registry_model, 2, 1)
        model_grid.addLayout(registry_buttons, 2, 2)

        self.lbl_registry_model_status = QLabel("")
        self.lbl_registry_model_status.setWordWrap(True)
        self.lbl_registry_model_status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.lbl_registry_model_status.setStyleSheet(label_style("muted", 10) + "padding: 0 2px 2px 2px;")
        model_grid.addWidget(self.lbl_registry_model_status, 3, 1, 1, 2)

        self._reload_ollama_catalog()
        self._reload_registry_models()
        self._rebuild_llm_combo(settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b")))

        self.lbl_model_info = QLabel()
        self.lbl_model_info.setWordWrap(True)
        self.lbl_model_info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.lbl_model_info.setStyleSheet(label_style("muted", 10) + "padding: 0 2px 10px 2px;")
        model_grid.addWidget(self.lbl_model_info, 4, 1, 1, 2)
        ai_form.addRow("모델 관리:", model_panel)
        self.combo_llm.currentIndexChanged.connect(self._update_model_info)
        self._update_model_info()

        api_section = QLabel("클라우드 API 키")
        api_section.setStyleSheet(label_style("text", 13, bold=True) + "padding: 10px 5px 2px 5px;")
        ai_form.addRow("", api_section)

        self.input_api_key = QLineEdit()
        self.input_api_key.setObjectName("GoogleApiKeyInput")
        self.input_api_key.setPlaceholderText("AI Studio 발급 Google API Key 입력")
        self.input_api_key.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.input_api_key.setText(get_api_key("google"))
        ai_form.addRow("Google API Key:", self.input_api_key)

        self.input_openai_api_key = QLineEdit()
        self.input_openai_api_key.setObjectName("OpenAiApiKeyInput")
        self.input_openai_api_key.setPlaceholderText("OpenAI API Key 입력")
        self.input_openai_api_key.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.input_openai_api_key.setText(get_api_key("openai"))
        ai_form.addRow("OpenAI API Key:", self.input_openai_api_key)

        self.input_huggingface_token = QLineEdit()
        self.input_huggingface_token.setObjectName("HuggingFaceTokenInput")
        self.input_huggingface_token.setPlaceholderText("Hugging Face HF_TOKEN 입력")
        self.input_huggingface_token.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.input_huggingface_token.setText(get_api_key("huggingface"))
        ai_form.addRow("Hugging Face Token:", self.input_huggingface_token)

        self._build_roughcut_llm_section(roughcut_form, settings)

        # 3. 자막 묶음 단위 (슬라이더 세팅)
        chunk_layout = QHBoxLayout()
        self.btn_chunk_minus = QPushButton("-")
        self.btn_chunk_minus.setFixedWidth(54)
        self.btn_chunk_minus.setStyleSheet(self._settings_button_style("toolbar", min_width=30))
        self.btn_chunk_minus.clicked.connect(self._on_chunk_minus)
        
        self.slider_chunk = QSlider(Qt.Orientation.Horizontal)
        self.slider_chunk.setRange(10, 1800)
        self.slider_chunk.setSingleStep(10)
        self.slider_chunk.setPageStep(60)
        self.slider_chunk.valueChanged.connect(self._update_chunk_display)
        
        self.btn_chunk_plus = QPushButton("+")
        self.btn_chunk_plus.setFixedWidth(54)
        self.btn_chunk_plus.setStyleSheet(self._settings_button_style("toolbar", min_width=30))
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
        self._manual_chunk_layout = chunk_layout
        if bool(settings.get("settings_simplified_ui_enabled", True)):
            chunk_hint = QLabel("LoRA·딥러닝·정식/임시 컷 경계가 자막 생성마다 묶음 범위를 자동으로 정합니다.")
            chunk_hint.setWordWrap(True)
            chunk_hint.setStyleSheet(label_style("muted", 11))
            editor_form.addRow("자막 묶음:", chunk_hint)
        else:
            editor_form.addRow("자막 묶음 단위:", chunk_layout)
        
        curr_chunk = int(settings.get("chunk_time_limit", settings.get("subtitle_bundle_target_sec", 180)) or 180)
        if curr_chunk >= 99999:
            self.chk_chunk_all.setChecked(True)
            self.slider_chunk.setValue(int(settings.get("subtitle_bundle_target_sec", 180) or 180))
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
        w_models = filter_available_whisper_models(w_models)
        stt1_models = [
            model for model in w_models
            if "ghost613" not in model.lower() and "zeroth" not in model.lower()
        ]
        stt2_models = [
            model for model in w_models
            if "ghost613" in model.lower() or "zeroth" in model.lower() or model.startswith("coreml:")
        ]

        self.combo_whisper.setUpdatesEnabled(False)
        self.combo_whisper.blockSignals(True)
        self.combo_whisper.addItems(stt1_models)
        for idx, model_name in enumerate(stt1_models):
            if "ghost613" in model_name or "Zeroth-KO" in model_name or model_name.startswith("o0dimplz0o/") or model_name.startswith("coreml:"):
                self.combo_whisper.setItemText(idx, f"{model_name} (실험)")
        self._fit_model_combo(self.combo_whisper)
        curr_w = settings.get("selected_whisper_model", getattr(config, "WHISPER_MODEL", stt1_models[0] if stt1_models else ""))
        # ── OS에 맞지 않는 저장값이면 기본값으로 교체 ──
        if not config.IS_MAC and ("mlx-community" in curr_w or curr_w.startswith("youngouk/")):
            curr_w = "large-v3"
        elif config.IS_MAC and curr_w in WINDOWS_WHISPER_MODELS:
            curr_w = "mlx-community/whisper-large-v3-mlx"
        if curr_w not in stt1_models and stt1_models:
            curr_w = stt1_models[0]
        display_values = [self.combo_whisper.itemText(i).replace(" (실험)", "") for i in range(self.combo_whisper.count())]
        for i in range(self.combo_whisper.count()):
            self._set_combo_item_tooltip(self.combo_whisper, i, self.combo_whisper.itemText(i).replace(" (실험)", ""))
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
        stt_section = QLabel("STT 보조")
        stt_section.setStyleSheet(label_style("text", 13, bold=True) + "padding: 10px 5px 2px 5px;")
        ai_form.addRow("", stt_section)

        self.chk_stt_ensemble = QCheckBox("STT2 병렬 인식 사용 (STT1 우선, STT2는 누락 보강용)")
        self.chk_stt_ensemble.setChecked(bool(settings.get("stt_ensemble_enabled", False)))

        self.combo_whisper_secondary = QComboBox()
        self.combo_whisper_secondary.setUpdatesEnabled(False)
        self.combo_whisper_secondary.blockSignals(True)
        self.combo_whisper_secondary.addItems(stt2_models)
        for idx, model_name in enumerate(stt2_models):
            if "ghost613" in model_name or "Zeroth-KO" in model_name or model_name.startswith("o0dimplz0o/") or model_name.startswith("coreml:"):
                self.combo_whisper_secondary.setItemText(idx, f"{model_name} (실험)")
        self._fit_model_combo(self.combo_whisper_secondary)
        curr_w2 = settings.get(
            "selected_whisper_model_secondary",
            "youngouk/ghost613-turbo-korean-4bit-mlx" if config.IS_MAC else "ghost613/faster-whisper-large-v3-turbo-korean",
        )
        if not config.IS_MAC and ("mlx-community" in curr_w2 or curr_w2.startswith("youngouk/")):
            curr_w2 = "ghost613/faster-whisper-large-v3-turbo-korean"
        elif config.IS_MAC and curr_w2 in WINDOWS_WHISPER_MODELS:
            curr_w2 = "youngouk/ghost613-turbo-korean-4bit-mlx"
        if curr_w2 not in stt2_models and stt2_models:
            curr_w2 = stt2_models[0]
        display_values2 = [self.combo_whisper_secondary.itemText(i).replace(" (실험)", "") for i in range(self.combo_whisper_secondary.count())]
        for i in range(self.combo_whisper_secondary.count()):
            self._set_combo_item_tooltip(self.combo_whisper_secondary, i, self.combo_whisper_secondary.itemText(i).replace(" (실험)", ""))
        if curr_w2 in display_values2:
            for i, value in enumerate(display_values2):
                if value == curr_w2:
                    self.combo_whisper_secondary.setCurrentIndex(i)
                    break
        else:
            self.combo_whisper_secondary.setCurrentIndex(0)
        self.combo_whisper_secondary.blockSignals(False)
        self.combo_whisper_secondary.setUpdatesEnabled(True)

        self.chk_stt_ensemble_llm = QCheckBox("LLM 후보 판정 사용")
        self.chk_stt_ensemble_llm.setChecked(bool(settings.get("stt_ensemble_llm_judge_enabled", True)))
        ai_form.addRow("STT1 음성 모델:", self.combo_whisper)
        ai_form.addRow("STT2 사용:", self.chk_stt_ensemble)
        ai_form.addRow("STT2 음성 모델:", self.combo_whisper_secondary)
        ai_form.addRow("STT 후보 판정:", self.chk_stt_ensemble_llm)

        # 5. 음성 처리 AI
        self.combo_audio = QComboBox()
        self.audio_map = {
            "DeepFilterNet (AI 노이즈 제거)": "deepfilter",
            "RNNoise (빠른 노이즈 제거/실험)": "rnnoise",
            "Resemble Enhance (음성 향상/실험)": "resemble_enhance",
            "ClearVoice MossFormer2 (음성 향상/실험)": "clearvoice",
            "사용 안함": "none",
        }
        for k in self.audio_map: self.combo_audio.addItem(k)
        curr_audio = settings.get("selected_audio_ai", "deepfilter")
        for k, v in self.audio_map.items():
            if v == curr_audio: self.combo_audio.setCurrentText(k); break
        self._fit_model_combo(self.combo_audio)

        # 6. VAD
        self.combo_vad = QComboBox()
        self.vad_map = {"Silero (검수용)": "silero", "TEN VAD (저지연/실험)": "ten_vad", "사용 안 함": "none"}
        for k in self.vad_map: self.combo_vad.addItem(k)
        curr_vad = settings.get("selected_vad", "silero")
        for k, v in self.vad_map.items():
            if v == curr_vad: self.combo_vad.setCurrentText(k); break
        self._fit_model_combo(self.combo_vad)
        self.chk_vad_post_align = QCheckBox("VAD로 STT/앙상블 자막 위치 재계산")
        self.chk_vad_post_align.setChecked(bool(settings.get("vad_post_stt_align_enabled", True)))
        audio_section = QLabel("음성/VAD")
        audio_section.setStyleSheet(label_style("text", 13, bold=True) + "padding: 10px 5px 2px 5px;")
        ai_form.addRow("", audio_section)
        ai_form.addRow("음성 처리 모델:", self.combo_audio)
        ai_form.addRow("VAD 모델:", self.combo_vad)
        ai_form.addRow("VAD 보정:", self.chk_vad_post_align)
        self._sync_stt_quality_preset_combo(selected_mode_from_settings(settings))
        self._sync_audio_preset_combo(settings.get("audio_preset", ""))
        self._sync_auto_preset_button_state()
        self._update_editor_roughcut_draft_state()
        self.combo_audio_preset.currentIndexChanged.connect(self._on_audio_preset_changed)

        self._build_auto_settings_section(auto_form, settings)

        layout.addWidget(self.tabs)
        layout.addSpacing(10)
        layout.addLayout(_create_bottom_buttons(self, self._on_ok, save_callback=self._on_save, save_def_callback=self._on_save_default))   

    def _build_simple_operation_section(self, form: QFormLayout, settings: dict):
        section = QLabel("Mode")
        section.setStyleSheet(label_style("text", 13, bold=True) + "padding: 10px 5px 2px 5px;")
        form.addRow("", section)

        mode_layout = QVBoxLayout()
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(6)
        current_mode = selected_mode_from_settings(settings)
        self._sync_stt_quality_preset_combo(current_mode)
        self.combo_stt_quality_preset.currentIndexChanged.connect(self._on_stt_quality_preset_changed)
        mode_layout.addWidget(self.combo_stt_quality_preset)

        self.lbl_simple_operation_summary = QLabel(simple_operation_mode_summary(current_mode))
        self.lbl_simple_operation_summary.setWordWrap(True)
        self.lbl_simple_operation_summary.setStyleSheet(label_style("muted", 11))
        mode_layout.addWidget(self.lbl_simple_operation_summary)

        form.addRow("Mode:", mode_layout)

    def _on_simple_operation_mode_changed(self, *args):
        mode = normalize_simple_operation_mode(self.combo_stt_quality_preset.currentData() or "auto")
        if hasattr(self, "lbl_simple_operation_summary"):
            self.lbl_simple_operation_summary.setText(simple_operation_mode_summary(mode))
        self.result_settings = apply_simple_operation_mode(self.result_settings, mode)

    def _make_tab_form(self):
        content = QWidget()
        form = QFormLayout(content)
        form.setContentsMargins(18, 18, 18, 18)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        tab = QScrollArea()
        tab.setFrameShape(QScrollArea.Shape.NoFrame)
        tab.setWidgetResizable(True)
        tab.setWidget(content)
        return tab, form

    def _model_grid_label(self, text: str):
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        label.setMinimumWidth(118)
        label.setStyleSheet(label_style("text", 11, bold=True))
        return label

    def _fit_action_button(self, button: QPushButton, width: int):
        button.setFixedWidth(width)
        height = int(getattr(self, "_settings_control_height", 40) or 40)
        button.setMinimumHeight(height)
        button.setMaximumHeight(height)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _fit_model_combo(self, combo: QComboBox, *, min_contents: int = 24):
        combo.setMinimumContentsLength(min_contents)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        height = int(getattr(self, "_settings_control_height", 40) or 40)
        combo.setMinimumHeight(height)
        combo.setMaximumHeight(height)
        combo.setMaxVisibleItems(14)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _settings_button_style(self, kind: str = "toolbar", *, min_width: int = 72):
        height = int(getattr(self, "_settings_control_height", 40) or 40)
        return settings_button_style(kind, min_width=min_width, min_height=height)

    def _set_combo_item_tooltip(self, combo: QComboBox, index: int, text: str):
        if index >= 0:
            combo.setItemData(index, text, Qt.ItemDataRole.ToolTipRole)

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
            self._set_combo_item_tooltip(self.combo_registry_model, self.combo_registry_model.count() - 1, str(e))
        for model in self._registry_models:
            status = "설치됨" if model.get("installed") else "미설치"
            required = "필수" if model.get("required") else "선택"
            label = f"[{model.get('category', '-')}] {model.get('name', model.get('id', ''))} · {status} · {required}"
            self.combo_registry_model.addItem(label, model)
            self._set_combo_item_tooltip(self.combo_registry_model, self.combo_registry_model.count() - 1, label)
        if self.combo_registry_model.count() == 0:
            self.combo_registry_model.addItem("현재 OS에서 관리할 모델 없음", {})
            self._set_combo_item_tooltip(self.combo_registry_model, 0, "현재 OS에서 관리할 모델 없음")
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
        buttons = (
            (getattr(self, "btn_llm_all", None), "all"),
            (getattr(self, "btn_llm_free", None), "free"),
            (getattr(self, "btn_llm_paid", None), "paid"),
        )
        for btn, value in buttons:
            if btn is None:
                continue
            btn.blockSignals(True)
            btn.setChecked(self.llm_filter == value)
            btn.setStyleSheet(self._settings_button_style("primary" if self.llm_filter == value else "toolbar", min_width=64))
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
            label = item.get("display_name", item.get("name", ""))
            self.combo_llm.addItem(label, item)
            self._set_combo_item_tooltip(self.combo_llm, self.combo_llm.count() - 1, label)
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
                label = row.get('label', row['name'])
                self.combo_ollama_catalog.addItem(label, row)
                self._set_combo_item_tooltip(self.combo_ollama_catalog, self.combo_ollama_catalog.count() - 1, label)
            if self.combo_ollama_catalog.count() == 0:
                self.combo_ollama_catalog.addItem("설치 가능한 미설치 모델 없음", {})
                self._set_combo_item_tooltip(self.combo_ollama_catalog, 0, "설치 가능한 미설치 모델 없음")
        except Exception as e:
            self.combo_ollama_catalog.addItem(f"Ollama 확인 실패: {e}", {})
            self._set_combo_item_tooltip(self.combo_ollama_catalog, 0, str(e))

    def _sync_audio_preset_combo(self, preset_name: str):
        combo_value = _resolve_audio_preset_combo_data(
            {
                **dict(self.result_settings or {}),
                "audio_preset": preset_name,
            }
        )
        self.combo_audio_preset.blockSignals(True)
        matched = False
        for i in range(self.combo_audio_preset.count()):
            if self.combo_audio_preset.itemData(i) == combo_value:
                self.combo_audio_preset.setCurrentIndex(i)
                matched = True
                break
        if not matched:
            self.combo_audio_preset.setCurrentIndex(0)
        self.combo_audio_preset.blockSignals(False)

    def _sync_stt_quality_preset_combo(self, preset_key: str):
        key = normalize_simple_operation_mode(preset_key)
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

    def _build_editor_llm_prompt_section(self, form: QFormLayout, settings: dict):
        section = QLabel("프롬프트 참고")
        section.setStyleSheet(label_style("text", 13, bold=True) + "padding: 18px 5px 2px 5px;")
        form.addRow("", section)

        prompt_layout = QVBoxLayout()
        prompt_layout.setContentsMargins(0, 0, 0, 0)
        prompt_layout.setSpacing(8)
        lbl_sys = QLabel("시스템 프롬프트 · 읽기 전용")
        lbl_sys.setStyleSheet(label_style("muted", 11, bold=True))
        prompt_layout.addWidget(lbl_sys)

        self.edit_system_prompt = QTextEdit()
        self.edit_system_prompt.setReadOnly(True)
        self.edit_system_prompt.setMinimumHeight(150)
        self.edit_system_prompt.setMaximumHeight(220)
        self.edit_system_prompt.setPlainText(str(getattr(config, "DEFAULT_LLM_PROMPT", "") or "").strip())
        self.edit_system_prompt.setStyleSheet("color: #8E98A1;")
        prompt_layout.addWidget(self.edit_system_prompt)

        info = QLabel("텍스트 LoRA와 교정 memory를 우선 적용합니다. 추가 프롬프트 입력은 중복 기능이라 제거했고, 이 영역은 현재 적용되는 기본 지시문 확인용입니다.")
        info.setWordWrap(True)
        info.setStyleSheet(label_style("muted", 11))
        prompt_layout.addWidget(info)
        form.addRow("기본 지시문:", prompt_layout)

    def _build_auto_settings_section(self, form: QFormLayout, settings: dict):
        path_settings = load_path_settings()

        section = QLabel("자동 처리")
        section.setStyleSheet(label_style("text", 13, bold=True) + "padding: 10px 5px 2px 5px;")
        form.addRow("", section)

        self.input_auto_nas_path = QLineEdit()
        self.input_auto_nas_path.setPlaceholderText("NAS 루트 경로 또는 smb:// 경로")
        self.input_auto_nas_path.setText(get_nas_path())
        form.addRow("NAS 루트 경로:", self.input_auto_nas_path)

        self.input_auto_icloud_path = QLineEdit()
        self.input_auto_icloud_path.setPlaceholderText("iCloud 동기화 경로")
        self.input_auto_icloud_path.setText(get_icloud_path())
        form.addRow("iCloud 경로:", self.input_auto_icloud_path)

        self.chk_auto_icloud_detect = QCheckBox("iCloud 자동감지 및 처리 활성화")
        self.chk_auto_icloud_detect.setChecked(get_icloud_auto_detect())
        form.addRow("iCloud 자동 처리:", self.chk_auto_icloud_detect)

        self.chk_auto_nas_detect = QCheckBox("NAS 자동감지 및 처리 활성화")
        self.chk_auto_nas_detect.setChecked(get_nas_auto_detect())
        form.addRow("NAS 자동 처리:", self.chk_auto_nas_detect)

        self.combo_auto_start_mode = QComboBox()
        for key in STT_QUALITY_PRESET_ORDER:
            self.combo_auto_start_mode.addItem(stt_quality_label(key), key)
        current_mode = normalize_stt_quality_key(
            path_settings.get("auto_start_mode")
            or path_settings.get("nas_stt_quality_preset")
            or path_settings.get("icloud_stt_quality_preset")
            or settings.get("auto_start_mode")
            or "precise"
        )
        self._set_combo_data(self.combo_auto_start_mode, current_mode)
        form.addRow("자동 처리 모드:", self.combo_auto_start_mode)

        self.chk_auto_start_enabled = QCheckBox("자동시작 사용")
        self.chk_auto_start_enabled.setChecked(bool(path_settings.get("auto_start_enabled", settings.get("auto_start_enabled", True))))
        form.addRow("자동시작:", self.chk_auto_start_enabled)

    def _build_subtitle_quality_section(self, form: QFormLayout, settings: dict):
        section = QLabel("자막 품질")
        section.setStyleSheet(label_style("text", 13, bold=True) + "padding: 10px 5px 2px 5px;")
        form.addRow("", section)

        self.chk_subtitle_quality_auto_check = QCheckBox("자막 생성 후 자동 검사")
        self.chk_subtitle_quality_auto_check.setChecked(bool(settings.get(
            "subtitle_quality_auto_check_after_generate",
            DEFAULT_ADV_SETTINGS.get("subtitle_quality_auto_check_after_generate", True),
        )))
        self.chk_subtitle_quality_auto_correct = QCheckBox("자동 교정 허용 (LoRA/개인화 적용)")
        self.chk_subtitle_quality_auto_correct.setChecked(bool(settings.get(
            "subtitle_quality_auto_correct_enabled",
            DEFAULT_ADV_SETTINGS.get("subtitle_quality_auto_correct_enabled", True),
        )))

        memory_info = QLabel(
            "자동 검사, LoRA 교정, STT 저점 재검사, 자동 적용 점수는 user_settings.json에 저장되고 "
            "LoRA 점수 인덱스가 더 정확하다고 판단하면 영상별로 자동 적용합니다."
        )
        memory_info.setWordWrap(True)
        memory_info.setStyleSheet(label_style("muted", 11))
        form.addRow("자동 관리:", memory_info)

        self.chk_stt_low_score_recheck = QCheckBox("STT1/STT2 둘 다 낮은 점수일 때 해당 구간만 재검사")
        self.chk_stt_low_score_recheck.setChecked(bool(settings.get(
            "stt_low_score_recheck_enabled",
            DEFAULT_ADV_SETTINGS.get("stt_low_score_recheck_enabled", True),
        )))

        self.spin_stt_low_score_recheck_threshold = QSpinBox()
        self.spin_stt_low_score_recheck_threshold.setRange(0, 100)
        self.spin_stt_low_score_recheck_threshold.setSuffix(" 점")
        self.spin_stt_low_score_recheck_threshold.setValue(int(settings.get(
            "stt_low_score_recheck_threshold",
            DEFAULT_ADV_SETTINGS.get("stt_low_score_recheck_threshold", 60),
        ) or 60))

        self.spin_quality_threshold = QSpinBox()
        self.spin_quality_threshold.setRange(70, 100)
        self.spin_quality_threshold.setSuffix(" 점")
        self.spin_quality_threshold.setValue(int(settings.get(
            "review_auto_correct_apply_threshold",
            DEFAULT_ADV_SETTINGS.get("review_auto_correct_apply_threshold", 94),
        ) or 94))

        self.spin_quality_recheck_buffer = QDoubleSpinBox()
        self.spin_quality_recheck_buffer.setRange(0.5, 3.0)
        self.spin_quality_recheck_buffer.setSingleStep(0.1)
        self.spin_quality_recheck_buffer.setDecimals(1)
        self.spin_quality_recheck_buffer.setSuffix(" 초")
        self.spin_quality_recheck_buffer.setValue(float(settings.get(
            "review_recheck_buffer_sec",
            DEFAULT_ADV_SETTINGS.get("review_recheck_buffer_sec", 1.5),
        ) or 1.5))

    def _set_combo_data(self, combo: QComboBox, value: str):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return True
        return False

    def _on_audio_preset_changed(self, *args):
        preset_name = self.combo_audio_preset.currentData()
        if preset_name == "__default__":
            default_applier = getattr(_audio_presets, "apply_default_audio_preset", None)
            if callable(default_applier):
                self.result_settings = default_applier(self.result_settings)
            else:
                self.result_settings = dict(self.result_settings)
                self.result_settings["audio_preset"] = ""
        elif not preset_name:
            self.result_settings["audio_preset"] = ""
            return
        else:
            self.result_settings = _audio_presets.apply_audio_preset(self.result_settings, preset_name)
        self._update_model_info()

    def _on_stt_quality_preset_changed(self, *args):
        mode = normalize_simple_operation_mode(self.combo_stt_quality_preset.currentData() or "auto")
        if hasattr(self, "lbl_simple_operation_summary"):
            self.lbl_simple_operation_summary.setText(simple_operation_mode_summary(mode))
        self.result_settings = apply_simple_operation_mode(self.result_settings, mode)
        self._set_combo_by_data_value(self.combo_whisper, self.result_settings.get("selected_whisper_model"))
        self._set_llm_combo_by_name(self.result_settings.get("selected_model", ""))
        self._update_editor_roughcut_draft_state()
        self._update_model_info()

    def _on_auto_audio_preset_detect(self):
        media_path = self._current_media_path()
        if not media_path:
            QMessageBox.information(self, "자동 판정", "현재 열려 있는 영상이 없어서 자동 판정을 진행할 수 없습니다.")
            return
        try:
            decision = auto_classify_media_presets(media_path, settings=self._collect_settings())
            self.result_settings = apply_auto_classified_presets(self.result_settings, decision)
            self._sync_audio_preset_combo(self.result_settings.get("audio_preset", ""))
            self._set_combo_by_data_value(self.combo_audio, self.result_settings.get("selected_audio_ai"), self.audio_map)
            self._set_combo_by_data_value(self.combo_vad, self.result_settings.get("selected_vad"), self.vad_map)
            self._update_model_info()
            self._sync_auto_preset_button_state()
            QMessageBox.information(
                self,
                "자동 판정 완료",
                (
                    f"오디오: {decision['audio_preset']}\n"
                    f"추천 자막품질(미적용): {stt_quality_label(decision.get('stt_quality_preset'))}\n"
                    f"신뢰도: {int(round(float(decision.get('confidence', 0.0)) * 100))}%\n\n"
                    f"{decision.get('reason', '')}"
                ),
            )
        except Exception as e:
            QMessageBox.warning(self, "자동 판정 실패", str(e))

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
            text = "💡 <b>LLM 미사용:</b> AI 교정을 생략하고 가장 빠르게 작업합니다."
            self.lbl_model_info.setText(text)
            self.lbl_model_info.setToolTip("LLM 미사용: AI 교정을 생략하고 가장 빠르게 작업합니다.")
            return
        if 'size' not in m_data: 
            self.lbl_model_info.setText("")
            self.lbl_model_info.setToolTip("")
            return
            
        size_gb = m_data['size'] / (1024**3)
        details = m_data.get('details', {})
        billing = details.get('billing', '무료/로컬' if details.get('format') == 'ollama' else '')
        parts = [
            f"📦 <b>용량:</b> {size_gb:.2f} GB",
            f"🧠 <b>패밀리:</b> {details.get('family', 'Unknown')}",
            f"📊 <b>파라미터:</b> {details.get('parameter_size', 'Unknown')}",
            f"⚙️ <b>포맷:</b> {details.get('format', 'gguf').upper()}",
            f"💳 <b>비용:</b> {billing}",
        ]
        plain_parts = [
            f"용량: {size_gb:.2f} GB",
            f"패밀리: {details.get('family', 'Unknown')}",
            f"파라미터: {details.get('parameter_size', 'Unknown')}",
            f"포맷: {details.get('format', 'gguf').upper()}",
            f"비용: {billing}",
        ]
        self.lbl_model_info.setText("  |  ".join(parts))
        self.lbl_model_info.setToolTip(" / ".join(plain_parts))

    def _sync_auto_preset_button_state(self):
        if not hasattr(self, "btn_auto_audio_preset"):
            return
        decision = dict(self.result_settings.get("audio_preset_auto_decision") or {})
        highlighted = bool(decision.get("audio_preset") and decision.get("stt_quality_preset"))
        icon_color = "#34C759" if highlighted else "#A9B0B7"
        self.btn_auto_audio_preset.setIcon(line_icon("auto", icon_color, 16))
        self.btn_auto_audio_preset.setToolTip(
            str(decision.get("reason") or "영상 기준 자동 판정")
            if highlighted else
            "영상 기준 자동 판정"
        )

    def _current_media_path(self) -> str:
        owner = self.parent()
        for candidate in (owner, getattr(owner, "window", lambda: None)()):
            if candidate is None:
                continue
            editor_getter = getattr(candidate, "_active_editor", None)
            if callable(editor_getter):
                try:
                    editor = editor_getter()
                except Exception:
                    editor = None
            else:
                editor = None
            media_path = str(
                getattr(editor, "media_path", "")
                or getattr(getattr(editor, "sm", None), "current_file", "")
                or getattr(candidate, "media_path", "")
                or ""
            )
            if media_path:
                return media_path
        return ""
    def _collect_settings(self):
        res = dict(self.result_settings)
        m_data = self.combo_llm.currentData() or {}
        provider = (m_data.get('details', {}) or {}).get('provider', 'ollama')
        selected_llm_name = m_data.get('name') or self.combo_llm.currentText()
        subtitle_llm_user_selected = bool(
            str(selected_llm_name or "").strip()
            and "사용 안함" not in str(selected_llm_name or "")
            and str(provider or "").strip().lower() != "none"
        )
        google_key_saved = set_api_key("google", self.input_api_key.text().strip())
        openai_key_saved = set_api_key("openai", self.input_openai_api_key.text().strip())
        huggingface_token_saved = set_api_key("huggingface", self.input_huggingface_token.text().strip())
        auto_start_mode = normalize_stt_quality_key(self.combo_auto_start_mode.currentData() or "precise")
        auto_start_enabled = bool(self.chk_auto_start_enabled.isChecked())
        auto_correct_enabled = bool(self.chk_subtitle_quality_auto_correct.isChecked())
        simple_mode = normalize_simple_operation_mode(self.combo_stt_quality_preset.currentData() or "auto")
        chunk_time_limit = 99999 if self.chk_chunk_all.isChecked() else self.slider_chunk.value()
        if bool(res.get("subtitle_bundle_autopilot_enabled", True)):
            chunk_time_limit = int(res.get("subtitle_bundle_target_sec", res.get("chunk_time_limit", 180)) or 180)

        res.update({
            "selected_model": selected_llm_name,
            "selected_llm_provider": provider,
            "subtitle_llm_user_selected": subtitle_llm_user_selected,
            "selected_whisper_model": self.combo_whisper.currentText().replace(" (실험)", ""),
            "stt_ensemble_enabled": bool(self.chk_stt_ensemble.isChecked()),
            "selected_whisper_model_secondary": self.combo_whisper_secondary.currentText().replace(" (실험)", ""),
            "stt_ensemble_llm_judge_enabled": bool(self.chk_stt_ensemble_llm.isChecked()),
            "selected_audio_ai": self.audio_map[self.combo_audio.currentText()],
            "selected_vad": self.vad_map[self.combo_vad.currentText()],
            "vad_post_stt_align_enabled": bool(self.chk_vad_post_align.isChecked()),
            "google_api_key_saved": bool(google_key_saved),
            "openai_api_key_saved": bool(openai_key_saved),
            "huggingface_token_saved": bool(huggingface_token_saved),
            "chunk_time_limit": chunk_time_limit,
            "llm_cost_filter": self.llm_filter,
            "user_prompt": "",
            "editor_roughcut_draft_enabled": self._editor_roughcut_draft_enabled_setting(),
            "editor_roughcut_draft_prompt": "",
            "llm_threads_auto_enabled": True,
            "llm_workers_auto_enabled": True,
            "audio_preset": "" if self.combo_audio_preset.currentData() == "__default__" else (self.combo_audio_preset.currentData() or ""),
            "stt_quality_preset": mode_to_stt_quality(simple_mode),
            "stt_candidate_scoring_enabled": True,
            "stt_low_score_recheck_enabled": bool(self.chk_stt_low_score_recheck.isChecked()),
            "stt_low_score_recheck_threshold": int(self.spin_stt_low_score_recheck_threshold.value()),
            "subtitle_quality_enabled": False,
            "subtitle_quality_auto_check_after_generate": bool(self.chk_subtitle_quality_auto_check.isChecked()),
            "subtitle_quality_auto_correct_enabled": auto_correct_enabled,
            "editor_lora_runtime_enabled": auto_correct_enabled,
            "correction_memory_enabled": auto_correct_enabled,
            "wrong_answer_memory_enabled": auto_correct_enabled,
            "review_auto_correct_apply_threshold": int(self.spin_quality_threshold.value()),
            "review_recheck_buffer_sec": round(float(self.spin_quality_recheck_buffer.value()), 2),
            "settings_simplified_ui_enabled": True,
            "simple_operation_mode": simple_mode,
            "subtitle_mode": simple_mode,
            **self._collect_roughcut_llm_settings(),
            "auto_start_mode": auto_start_mode,
            "auto_start_enabled": auto_start_enabled,
            "nas_path": self.input_auto_nas_path.text().strip(),
            "icloud_path": self.input_auto_icloud_path.text().strip(),
            "icloud_auto_detect": bool(self.chk_auto_icloud_detect.isChecked()),
            "nas_auto_detect": bool(self.chk_auto_nas_detect.isChecked()),
            "icloud_stt_quality_preset": auto_start_mode,
            "nas_stt_quality_preset": auto_start_mode,
        })
        res = apply_simple_operation_mode(res, simple_mode)
        res = apply_accuracy_first_runtime_settings(res)
        auto_start_mode = normalize_stt_quality_key(res.get("auto_start_mode", auto_start_mode) or auto_start_mode)
        path_settings = load_path_settings()
        path_settings.update({
            "nas_path": self.input_auto_nas_path.text().strip(),
            "icloud_path": self.input_auto_icloud_path.text().strip(),
            "icloud_auto_detect": bool(self.chk_auto_icloud_detect.isChecked()),
            "nas_auto_detect": bool(self.chk_auto_nas_detect.isChecked()),
            "auto_start_mode": auto_start_mode,
            "auto_start_enabled": auto_start_enabled,
            "icloud_stt_quality_preset": auto_start_mode,
            "nas_stt_quality_preset": auto_start_mode,
        })
        save_path_settings(path_settings)
        res.pop("google_api_key", None)
        res.pop("openai_api_key", None)
        return res

    def _notify_runtime_settings_applied(self):
        parent = self.parent()
        if parent is None:
            return
        if hasattr(parent, "_apply_ai_settings"):
            parent._apply_ai_settings(self.result_settings)
            return
        try:
            if hasattr(parent, "settings"):
                parent.settings = dict(self.result_settings)
            if hasattr(parent, "selected_model"):
                parent.selected_model = self.result_settings.get(
                    "selected_model",
                    getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"),
                )
            if hasattr(parent, "_update_engine_label_text"):
                parent._update_engine_label_text()
            main_w = parent.window() if hasattr(parent, "window") else None
            if hasattr(main_w, "_refresh_sidebar_engine_info"):
                engine_label = getattr(parent, "engine_lbl", None)
                main_w._refresh_sidebar_engine_info(engine_label.text() if engine_label is not None else None)
            if hasattr(main_w, "_auto_start_on"):
                main_w._auto_start_on = bool(self.result_settings.get("auto_start_enabled", True))
            if hasattr(main_w, "_is_icloud_auto_mode"):
                main_w._is_icloud_auto_mode = bool(get_icloud_auto_detect())
            if hasattr(main_w, "_is_nas_auto_mode"):
                main_w._is_nas_auto_mode = bool(get_nas_auto_detect())
            if hasattr(main_w, "_sync_subtitle_quality_combos_for_scope"):
                main_w._sync_subtitle_quality_combos_for_scope("icloud")
                main_w._sync_subtitle_quality_combos_for_scope("nas")
            if hasattr(main_w, "_start_configured_watchers"):
                main_w._start_configured_watchers()
            if hasattr(main_w, "_refresh_work_mode_ui"):
                main_w._refresh_work_mode_ui()
        except Exception:
            pass

    def _on_ok(self): self.result_settings = self._collect_settings(); self.accept()
    def _on_save(self): self.result_settings = self._collect_settings(); save_settings(self.result_settings); self._notify_runtime_settings_applied(); QMessageBox.information(self, "완료", "저장되었습니다.")
    def _on_save_default(self): self.result_settings = self._collect_settings(); save_default_settings(self.result_settings); QMessageBox.information(self, "완료", "기본값 저장 완료.")
