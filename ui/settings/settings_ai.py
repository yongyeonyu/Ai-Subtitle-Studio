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
                             QDoubleSpinBox, QSpinBox, QWidget, QFrame,
                             QScrollArea, QSizePolicy)
from PyQt6.QtCore import Qt
from core.runtime import config
from core.project.data_manager import save_settings, save_default_settings
from ui.settings.settings_common import (
    DEFAULT_ADV_SETTINGS, DEFAULT_WHISPER_MODELS,
    _fetch_models, _create_bottom_buttons, filter_available_whisper_models,
    is_experimental_whisper_model, whisper_model_display_name,
)
from ui.settings.tablet_dialog import apply_tablet_dialog_profile
from ui.style import COLORS, label_style, settings_button_style, settings_dialog_stylesheet, line_icon
from core.llm.provider_registry import cloud_model_items
from core.llm.secure_keys import get_api_key, set_api_key
from core.audio import audio_presets as _audio_presets
from core.audio.preset_auto_classifier import auto_classify_media_presets, apply_auto_classified_presets
from core.personalization.runtime_personalization import personalization_settings_override_for_media
from core.audio.stt_quality_presets import (
    VAD_MODE_AUTOMATION_NOTE,
    load_stt_quality_presets,
    normalize_stt_quality_key,
    save_stt_quality_user_preset,
    stt_quality_label,
)
from core.accuracy_policy import apply_accuracy_first_runtime_settings
from core.mode_manager import mode_to_stt_quality, selected_mode_from_settings
from core.mode_policy import mode_stt_support_flags
from core.settings_profiles import sanitize_persisted_settings
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


def _ai_settings_panel_stylesheet() -> str:
    return (
        "#AiSettingsSectionCard {"
        f"background: {COLORS['surface']}; border: 1px solid {COLORS['separator']}; border-radius: 14px;"
        "}"
        "#AiSettingsSectionTitle {"
        f"color: {COLORS['text']}; font-size: 16px; font-weight: 900;"
        "}"
        "#AiSettingsSectionHint {"
        f"color: {COLORS['muted']}; font-size: 11px; font-weight: 700;"
        "}"
        "#AiModelDownloadPanel {"
        "background: transparent; border: none;"
        "}"
        "#AiRegistryModelStatus, #AiModelInfoLabel {"
        "background: rgba(0, 122, 255, 0.08);"
        "border: 1px solid rgba(0, 122, 255, 0.24);"
        "border-radius: 12px; padding: 8px 10px;"
        f"color: #D8E9FF;"
        "}"
        "#AiApiSectionLabel {"
        f"color: {COLORS['text']}; font-size: 13px; font-weight: 900;"
        "}"
        "#GoogleApiKeyInput, #OpenAiApiKeyInput, #HuggingFaceTokenInput {"
        "padding-left: 10px; font-size: 12px;"
        "}"
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


def stt2_whisper_model_candidates(models):
    return filter_available_whisper_models(models)


_LORA_GAP_SETTING_LABELS = {
    "continuous_threshold": "연속자막 기준",
    "gap_push_rate": "자막간격 조정",
    "single_subtitle_end": "단일자막 유지",
    "split_length_threshold": "분할 기준 글자 수",
    "sub_min_duration": "초단문 무시",
    "sub_max_duration": "최대 자막 길이",
    "sub_max_cps": "최대 CPS",
    "sub_dedup_window": "말더듬 환각 제거",
    "sub_gap_break_sec": "강제 줄바꿈 무음",
}


class SettingsDialog(QDialog, SettingsRoughcutMixin):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ AI 엔진 설정")
        self.setMinimumWidth(780)
        profile = apply_tablet_dialog_profile(self)
        if getattr(profile, "name", "desktop") == "desktop":
            self._settings_control_height = 36
        else:
            self._settings_control_height = min(int(getattr(self, "_settings_control_height", 44) or 44), 40)
        self.setStyleSheet(settings_dialog_stylesheet() + _ai_settings_panel_stylesheet())
        self.result_settings = dict(settings)
        self.stt_quality_presets = load_stt_quality_presets()
        self.audio_presets = _audio_presets.load_audio_presets()

        layout = QVBoxLayout(self)
        settings_body, settings_form = self._make_tab_form()

        self.combo_stt_quality_preset = QComboBox()
        for key, label, summary in simple_operation_mode_items():
            self.combo_stt_quality_preset.addItem(f"{label} - {summary}" if summary else label, key)
        self.combo_stt_quality_preset.setMinimumWidth(240)

        self.combo_audio_preset = QComboBox()
        self.combo_audio_preset.addItem("직접 설정", "")
        self.combo_audio_preset.addItem("기본값 적용", "__default__")
        for name in _audio_presets.curated_audio_preset_names():
            preset = self.audio_presets.get(name)
            if not isinstance(preset, dict):
                continue
            desc = preset.get("description", "")
            self.combo_audio_preset.addItem(f"{name} - {desc}" if desc else name, name)
        self.combo_audio_preset.setMinimumWidth(240)

        self._build_subtitle_quality_section(settings_form, settings)

        self._build_chunk_bundle_section(settings_form, settings)
        self._build_roughcut_llm_section(settings_form, settings)
        self._build_model_management_section(settings_form, settings)
        self._build_api_keys_section(settings_form)
        self._build_stt_support_section(settings_form, settings)
        self._build_audio_vad_section(settings_form, settings)
        self._sync_stt_quality_preset_combo(selected_mode_from_settings(settings))
        self._sync_audio_preset_combo(settings.get("audio_preset", ""))
        self._sync_auto_preset_button_state()
        self._update_editor_roughcut_draft_state()
        self.combo_audio_preset.currentIndexChanged.connect(self._on_audio_preset_changed)

        self._build_auto_settings_section(settings_form, settings)

        layout.addWidget(settings_body)
        layout.addSpacing(10)
        layout.addLayout(_create_bottom_buttons(self, self._on_ok, save_callback=self._on_save, save_def_callback=self._on_save_default))

    def _build_model_management_section(self, form: QFormLayout, settings: dict):
        # 1. 모델 관리
        self.llm_filter = "all"
        self.models_data = []
        parent = self.parent()
        if parent is not None and getattr(parent, "_local_llm_models", None):
            self.models_data = [dict(m) for m in parent._local_llm_models]
        if not self.models_data:
            self.models_data = _fetch_models()

        model_card, model_card_layout = self._make_section_card(
            "모델 관리:",
            "설치된 LLM, 추천 로컬 모델, 필수 STT 모델을 한 번에 확인하고 정리합니다.",
        )
        model_panel = QWidget()
        model_panel.setObjectName("AiModelDownloadPanel")
        model_grid = QGridLayout(model_panel)
        model_grid.setContentsMargins(0, 2, 0, 0)
        model_grid.setHorizontalSpacing(12)
        model_grid.setVerticalSpacing(10)
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
        self.lbl_registry_model_status.setObjectName("AiRegistryModelStatus")
        model_grid.addWidget(self.lbl_registry_model_status, 3, 1, 1, 2)

        self._reload_ollama_catalog()
        self._reload_registry_models()
        self._rebuild_llm_combo(settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b")))

        self.lbl_model_info = QLabel()
        self.lbl_model_info.setWordWrap(True)
        self.lbl_model_info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.lbl_model_info.setObjectName("AiModelInfoLabel")
        model_grid.addWidget(self.lbl_model_info, 4, 1, 1, 2)
        model_card_layout.addWidget(model_panel)
        form.addRow(model_card)
        self.combo_llm.currentIndexChanged.connect(self._update_model_info)
        self._update_model_info()

    def _build_api_keys_section(self, form: QFormLayout):
        api_card, api_card_layout = self._make_section_card(
            "클라우드 API 키",
            "Google, OpenAI, Hugging Face 연동 키를 저장하고 교체합니다.",
        )
        api_form = self._make_card_form()

        self.input_api_key = QLineEdit()
        self.input_api_key.setObjectName("GoogleApiKeyInput")
        self.input_api_key.setPlaceholderText("AI Studio 발급 Google API Key 입력")
        self.input_api_key.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.input_api_key.setText(get_api_key("google"))
        api_form.addRow("Google API Key:", self.input_api_key)

        self.input_openai_api_key = QLineEdit()
        self.input_openai_api_key.setObjectName("OpenAiApiKeyInput")
        self.input_openai_api_key.setPlaceholderText("OpenAI API Key 입력")
        self.input_openai_api_key.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.input_openai_api_key.setText(get_api_key("openai"))
        api_form.addRow("OpenAI API Key:", self.input_openai_api_key)

        self.input_huggingface_token = QLineEdit()
        self.input_huggingface_token.setObjectName("HuggingFaceTokenInput")
        self.input_huggingface_token.setPlaceholderText("Hugging Face HF_TOKEN 입력")
        self.input_huggingface_token.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.input_huggingface_token.setText(get_api_key("huggingface"))
        api_form.addRow("Hugging Face Token:", self.input_huggingface_token)
        api_card_layout.addLayout(api_form)
        form.addRow(api_card)

    def _build_chunk_bundle_section(self, form: QFormLayout, settings: dict):
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
            form.addRow("자막 묶음:", chunk_hint)
        else:
            form.addRow("자막 묶음 단위:", chunk_layout)
        
        curr_chunk = int(settings.get("chunk_time_limit", settings.get("subtitle_bundle_target_sec", 180)) or 180)
        if curr_chunk >= 99999:
            self.chk_chunk_all.setChecked(True)
            self.slider_chunk.setValue(int(settings.get("subtitle_bundle_target_sec", 180) or 180))
        else:
            self.chk_chunk_all.setChecked(False)
            self.slider_chunk.setValue(curr_chunk)
        self._update_chunk_display(self.slider_chunk.value())

    def _build_stt_support_section(self, form: QFormLayout, settings: dict):
        # 4. Whisper 모델
        self.combo_whisper = QComboBox()
        w_models = list(DEFAULT_WHISPER_MODELS)
        curr_w = settings.get("selected_whisper_model", getattr(config, "WHISPER_MODEL", w_models[0] if w_models else ""))
        curr_w2 = settings.get(
            "selected_whisper_model_secondary",
            getattr(config, "MLX_FALLBACK_MODEL", "mlx-community/whisper-large-v3-turbo"),
        )

        hf_cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
        if os.path.exists(hf_cache_dir):
            for folder_name in os.listdir(hf_cache_dir):
                if folder_name.startswith("models--") and "whisper" in folder_name.lower():
                    repo_name = folder_name.replace("models--", "", 1).replace("--", "/", 1)
                    if repo_name not in w_models:
                        w_models.append(repo_name)
        w_models = filter_available_whisper_models(w_models)
        for selected_model in (curr_w, curr_w2):
            if (
                selected_model
                and filter_available_whisper_models([selected_model])
                and selected_model not in w_models
            ):
                w_models.append(selected_model)
        stt1_models = list(dict.fromkeys(w_models))
        stt2_models = list(dict.fromkeys(w_models))

        self.combo_whisper.setUpdatesEnabled(False)
        self.combo_whisper.blockSignals(True)
        for model_name in stt1_models:
            label = whisper_model_display_name(model_name)
            if is_experimental_whisper_model(model_name):
                label = f"{label} (실험)"
            self.combo_whisper.addItem(label, model_name)
        self._fit_model_combo(self.combo_whisper)
        for i in range(self.combo_whisper.count()):
            self._set_combo_item_tooltip(self.combo_whisper, i, str(self.combo_whisper.itemData(i) or ""))
        if not self._set_combo_by_data_value(self.combo_whisper, curr_w) and self.combo_whisper.count() > 0:
            self.combo_whisper.setCurrentIndex(0)
        self.combo_whisper.blockSignals(False)
        self.combo_whisper.setUpdatesEnabled(True)
        self.combo_whisper_secondary = QComboBox()
        self.combo_whisper_secondary.setUpdatesEnabled(False)
        self.combo_whisper_secondary.blockSignals(True)
        for model_name in stt2_models:
            label = whisper_model_display_name(model_name)
            if is_experimental_whisper_model(model_name):
                label = f"{label} (실험)"
            self.combo_whisper_secondary.addItem(label, model_name)
        self._fit_model_combo(self.combo_whisper_secondary)
        for i in range(self.combo_whisper_secondary.count()):
            self._set_combo_item_tooltip(self.combo_whisper_secondary, i, str(self.combo_whisper_secondary.itemData(i) or ""))
        if not self._set_combo_by_data_value(self.combo_whisper_secondary, curr_w2) and self.combo_whisper_secondary.count() > 0:
            self.combo_whisper_secondary.setCurrentIndex(0)
        self.combo_whisper_secondary.blockSignals(False)
        self.combo_whisper_secondary.setUpdatesEnabled(True)

        stt_card, stt_card_layout = self._make_section_card(
            "STT 보조",
            "STT2 사용과 후보 판정은 Mode에 따라 자동 적용됩니다. 여기서는 사용할 모델만 선택합니다.",
        )
        stt_form = self._make_card_form()
        stt_form.addRow("STT1 음성 모델:", self.combo_whisper)
        stt_form.addRow("STT2 음성 모델:", self.combo_whisper_secondary)
        stt_card_layout.addLayout(stt_form)
        form.addRow(stt_card)

    def _build_audio_vad_section(self, form: QFormLayout, settings: dict):
        self.combo_audio = None
        self.audio_map = {}
        audio_card, audio_card_layout = self._make_section_card(
            "음성/VAD 자동 처리",
            VAD_MODE_AUTOMATION_NOTE,
        )
        audio_form = self._make_card_form()
        audio_note = QLabel("음성 필터와 VAD는 Fast/Auto/High Mode 기준 벤치 프로필로 자동 적용됩니다.")
        audio_note.setWordWrap(True)
        audio_note.setStyleSheet(label_style("muted", 11))
        audio_form.addRow("음성/VAD:", audio_note)
        audio_card_layout.addLayout(audio_form)
        form.addRow(audio_card)

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
        form.setContentsMargins(14, 14, 14, 14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(9)
        tab = QScrollArea()
        tab.setFrameShape(QScrollArea.Shape.NoFrame)
        tab.setWidgetResizable(True)
        tab.setWidget(content)
        return tab, form

    def _make_section_card(self, title: str, hint: str = ""):
        card = QFrame()
        card.setObjectName("AiSettingsSectionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("AiSettingsSectionTitle")
        layout.addWidget(title_label)

        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("AiSettingsSectionHint")
            hint_label.setWordWrap(True)
            layout.addWidget(hint_label)
        return card, layout

    def _make_card_form(self):
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        return form

    def _model_grid_label(self, text: str):
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        label.setMinimumWidth(106)
        label.setStyleSheet(label_style("text", 11, bold=True))
        return label

    def _fit_action_button(self, button: QPushButton, width: int):
        button.setFixedWidth(width)
        height = int(getattr(self, "_settings_control_height", 36) or 36)
        button.setMinimumHeight(height)
        button.setMaximumHeight(height)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _fit_model_combo(self, combo: QComboBox, *, min_contents: int = 24):
        combo.setMinimumContentsLength(min_contents)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        height = int(getattr(self, "_settings_control_height", 36) or 36)
        combo.setMinimumHeight(height)
        combo.setMaximumHeight(height)
        combo.setMaxVisibleItems(10)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _settings_button_style(self, kind: str = "toolbar", *, min_width: int = 72):
        height = int(getattr(self, "_settings_control_height", 36) or 36)
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
            self._registry_models = get_available_models(include_hidden=True, include_runtime_discovered=True)
        except Exception as e:
            self._registry_models = []
            self.combo_registry_model.addItem(f"모델 목록 로드 실패: {e}", {})
            self._set_combo_item_tooltip(self.combo_registry_model, self.combo_registry_model.count() - 1, str(e))
        for model in self._registry_models:
            status = "설치됨" if model.get("installed") else "미설치"
            required = "필수" if model.get("required") else "선택"
            extra = " · 실설치" if model.get("discovered") else ""
            label = f"[{model.get('category', '-')}] {model.get('name', model.get('id', ''))} · {status} · {required}{extra}"
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
        details = dict(model.get("details", {}) or {})
        discovered = " · 실설치 스캔" if model.get("discovered") else ""
        size_bytes = int(model.get("size_bytes", 0) or 0)
        size_label = f" · 용량: {size_bytes / (1024 ** 3):.2f} GB" if size_bytes > 0 else ""
        provider_label = str(details.get("format") or details.get("provider") or "").strip()
        provider_text = f" · 형식: {provider_label}" if provider_label else ""
        self.lbl_registry_model_status.setText(
            f"{'✅ 설치됨' if installed else '⚠️ 미설치'} · {required}{discovered} · OS: {os_label} · 패키지: {pip_label} · 경로: {path_label}{provider_text}{size_label}"
        )
        self.btn_registry_install.setEnabled(not installed)
        self.btn_registry_delete.setEnabled(installed and (model.get("id") != "ollama" or model.get("binary_check") == "ollama_model"))

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
            if (
                combo.itemData(i) == value
                or combo.itemText(i) == value
                or combo.itemText(i).replace(" (실험)", "") == value
            ):
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
        self.input_auto_nas_path = QLineEdit()
        self.input_auto_icloud_path = QLineEdit()
        self.chk_auto_icloud_detect = QCheckBox("iCloud 자동감지 및 처리 활성화")
        self.chk_auto_nas_detect = QCheckBox("NAS 자동감지 및 처리 활성화")
        current_mode = normalize_stt_quality_key(
            path_settings.get("auto_start_mode", mode_to_stt_quality(selected_mode_from_settings(settings)))
        )
        self.combo_auto_start_mode = QComboBox()
        self.chk_auto_start_enabled = QCheckBox("자동시작 사용")
        self.input_auto_nas_path.setText(str(path_settings.get("nas_path", get_nas_path()) or ""))
        self.input_auto_icloud_path.setText(str(path_settings.get("icloud_path", get_icloud_path()) or ""))
        self.chk_auto_icloud_detect.setChecked(bool(path_settings.get("icloud_auto_detect", get_icloud_auto_detect())))
        self.chk_auto_nas_detect.setChecked(bool(path_settings.get("nas_auto_detect", get_nas_auto_detect())))
        self.chk_auto_start_enabled.setChecked(bool(path_settings.get("icloud_auto_detect", False) or path_settings.get("nas_auto_detect", False)))
        for key in ("fast", "balanced", "precise", "stt"):
            self.combo_auto_start_mode.addItem(stt_quality_label(key), key)
        for idx in range(self.combo_auto_start_mode.count()):
            if self.combo_auto_start_mode.itemData(idx) == current_mode:
                self.combo_auto_start_mode.setCurrentIndex(idx)
                break

        lora_gap_row = QWidget()
        lora_gap_layout = QHBoxLayout(lora_gap_row)
        lora_gap_layout.setContentsMargins(0, 0, 0, 0)
        lora_gap_layout.setSpacing(8)
        lora_gap_hint = QLabel("학습 데이터가 있으면 현재 영상에 맞는 간격 값을 반영합니다.")
        lora_gap_hint.setWordWrap(True)
        lora_gap_hint.setStyleSheet(label_style("muted", 11))
        lora_gap_layout.addWidget(lora_gap_hint, 1)
        self.btn_lora_gap_auto = QPushButton("자동설정")
        self.btn_lora_gap_auto.setStyleSheet(self._settings_button_style("primary", min_width=88))
        self.btn_lora_gap_auto.clicked.connect(self._on_lora_gap_auto_apply)
        lora_gap_layout.addWidget(self.btn_lora_gap_auto)
        form.addRow("LoRA 간격:", lora_gap_row)

    def _build_subtitle_quality_section(self, form: QFormLayout, settings: dict):
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

    def _on_lora_gap_auto_apply(self):
        media_path = self._current_media_path()
        if not media_path:
            QMessageBox.information(self, "LoRA 자동설정", "현재 열려 있는 영상이 없어서 간격 자동설정을 진행할 수 없습니다.")
            return
        try:
            recommended = personalization_settings_override_for_media(media_path)
        except Exception as e:
            QMessageBox.warning(self, "LoRA 자동설정 실패", str(e))
            return

        applied = []
        for key, label in _LORA_GAP_SETTING_LABELS.items():
            if key not in recommended:
                continue
            self.result_settings[key] = recommended.get(key)
            applied.append(label)

        if not applied:
            QMessageBox.information(self, "LoRA 자동설정", "아직 적용할 수 있는 LoRA 간격 학습값이 없습니다.")
            return

        QMessageBox.information(
            self,
            "LoRA 자동설정 완료",
            "학습된 LoRA 값을 설정에 반영했습니다.\n\n" + " · ".join(applied),
        )

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

    def _on_chunk_minus(self):
        self.slider_chunk.setValue(max(10, self.slider_chunk.value() - 10))

    def _on_chunk_plus(self):
        self.slider_chunk.setValue(min(1800, self.slider_chunk.value() + 10))

    def _on_chunk_all_toggled(self, checked):
        for widget in (self.slider_chunk, self.btn_chunk_minus, self.btn_chunk_plus):
            widget.setEnabled(not checked)
        if checked:
            self.lbl_chunk_time.setText("전체 진행")
        else:
            self._update_chunk_display(self.slider_chunk.value())
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
        path_settings = dict(load_path_settings() or {})
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
        simple_mode = normalize_simple_operation_mode(self.combo_stt_quality_preset.currentData() or "auto")
        auto_start_mode = normalize_stt_quality_key(path_settings.get("auto_start_mode", mode_to_stt_quality(simple_mode)))
        icloud_auto_detect = bool(path_settings.get("icloud_auto_detect", get_icloud_auto_detect()))
        nas_auto_detect = bool(path_settings.get("nas_auto_detect", get_nas_auto_detect()))
        auto_start_enabled = bool(icloud_auto_detect or nas_auto_detect)
        nas_path = str(path_settings.get("nas_path", get_nas_path()) or "")
        icloud_path = str(path_settings.get("icloud_path", get_icloud_path()) or "")
        icloud_preset = normalize_stt_quality_key(path_settings.get("icloud_stt_quality_preset", auto_start_mode))
        nas_preset = normalize_stt_quality_key(path_settings.get("nas_stt_quality_preset", auto_start_mode))
        multiclip_preset = normalize_stt_quality_key(path_settings.get("multiclip_stt_quality_preset", auto_start_mode))
        auto_correct_enabled = bool(self.chk_subtitle_quality_auto_correct.isChecked())
        stt_support_flags = mode_stt_support_flags(simple_mode)
        chunk_time_limit = 99999 if self.chk_chunk_all.isChecked() else self.slider_chunk.value()
        if bool(res.get("subtitle_bundle_autopilot_enabled", True)):
            chunk_time_limit = int(res.get("subtitle_bundle_target_sec", res.get("chunk_time_limit", 180)) or 180)

        res.update({
            "selected_model": selected_llm_name,
            "selected_llm_provider": provider,
            "subtitle_llm_user_selected": subtitle_llm_user_selected,
            "selected_whisper_model": str(
                self.combo_whisper.currentData()
                or self.combo_whisper.currentText().replace(" (실험)", "")
            ),
            "selected_whisper_model_secondary": str(
                self.combo_whisper_secondary.currentData()
                or self.combo_whisper_secondary.currentText().replace(" (실험)", "")
            ),
            **stt_support_flags,
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
            "nas_path": nas_path,
            "icloud_path": icloud_path,
            "icloud_auto_detect": icloud_auto_detect,
            "nas_auto_detect": nas_auto_detect,
            "icloud_stt_quality_preset": icloud_preset,
            "nas_stt_quality_preset": nas_preset,
            "multiclip_stt_quality_preset": multiclip_preset,
        })
        selected_stt_model = str(res.get("selected_whisper_model") or "").strip()
        selected_stt2_model = str(res.get("selected_whisper_model_secondary") or "").strip()
        res = apply_simple_operation_mode(res, simple_mode)
        res = apply_accuracy_first_runtime_settings(res)
        if selected_stt_model:
            res["selected_whisper_model"] = selected_stt_model
        if selected_stt2_model:
            res["selected_whisper_model_secondary"] = selected_stt2_model
        res = save_stt_quality_user_preset(res, mode_to_stt_quality(simple_mode))
        auto_start_mode = normalize_stt_quality_key(res.get("auto_start_mode", auto_start_mode) or auto_start_mode)
        path_settings.update({
            "nas_path": nas_path,
            "icloud_path": icloud_path,
            "icloud_auto_detect": icloud_auto_detect,
            "nas_auto_detect": nas_auto_detect,
            "auto_start_mode": auto_start_mode,
            "auto_start_enabled": auto_start_enabled,
            "icloud_stt_quality_preset": icloud_preset,
            "nas_stt_quality_preset": nas_preset,
            "multiclip_stt_quality_preset": multiclip_preset,
        })
        save_path_settings(path_settings)
        return sanitize_persisted_settings(res)

    def _notify_runtime_settings_applied(self):
        parent = self.parent()
        if parent is None:
            return
        if hasattr(parent, "_apply_ai_settings"):
            parent._apply_ai_settings(self.result_settings)
            self._refresh_connected_video_player_audio()
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
            self._refresh_connected_video_player_audio()
        except Exception:
            pass

    def _refresh_connected_video_player_audio(self):
        parent = self.parent()
        visited: set[int] = set()
        owners = []
        if parent is not None:
            owners.append(parent)
            try:
                main_w = parent.window() if hasattr(parent, "window") else None
            except Exception:
                main_w = None
            if main_w is not None:
                owners.append(main_w)
                active_editor = getattr(main_w, "_active_editor", None)
                if callable(active_editor):
                    try:
                        owner = active_editor()
                        if owner is not None:
                            owners.append(owner)
                    except Exception:
                        pass
        for owner in owners:
            if owner is None or id(owner) in visited:
                continue
            visited.add(id(owner))
            video_player = getattr(owner, "video_player", None)
            refresh = getattr(video_player, "refresh_audio_output_routing", None)
            if callable(refresh):
                try:
                    refresh(reason="settings_changed")
                    return
                except Exception:
                    pass

    def _on_ok(self):
        self.result_settings = self._collect_settings()
        self._refresh_connected_video_player_audio()
        self.accept()

    def _on_save(self):
        self.result_settings = self._collect_settings()
        save_settings(self.result_settings)
        self._notify_runtime_settings_applied()
        QMessageBox.information(self, "완료", "저장되었습니다.")

    def _on_save_default(self):
        self.result_settings = self._collect_settings()
        save_default_settings(self.result_settings)
        QMessageBox.information(self, "완료", "기본값 저장 완료.")
