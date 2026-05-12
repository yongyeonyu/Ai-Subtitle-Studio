# Version: 03.13.04
# Phase: PHASE2
"""Roughcut-related controls for the AI settings dialog."""

from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit

from core.roughcut import merge_roughcut_settings
from ui.style import label_style


class SettingsRoughcutMixin:
    def _build_roughcut_llm_section(self, form: QFormLayout, settings: dict):
        roughcut_settings = merge_roughcut_settings(settings)
        self.chk_roughcut_llm_enabled = QCheckBox("")
        roughcut_model = str(roughcut_settings.get("roughcut_llm_model") or "").strip()
        roughcut_provider = str(roughcut_settings.get("roughcut_llm_provider") or "none")
        roughcut_enabled = (
            bool(roughcut_settings.get("roughcut_llm_enabled", False))
            and roughcut_provider not in {"inherit", "none"}
            and roughcut_model
            and roughcut_model.lower() != "inherit"
            and "사용 안함" not in roughcut_model
        )
        self.chk_roughcut_llm_enabled.setChecked(roughcut_enabled)
        self._hidden_roughcut_llm_enabled = self.chk_roughcut_llm_enabled

        self.chk_roughcut_llm_override = QCheckBox("")
        self.chk_roughcut_llm_override.setChecked(roughcut_enabled)
        self._hidden_roughcut_llm_override = self.chk_roughcut_llm_override

        provider_row = QHBoxLayout()
        self.combo_roughcut_llm_provider = QComboBox()
        for label, value in (
            ("사용 안 함", "none"),
            ("llama.cpp / GGUF", "llama_cpp"),
            ("Ollama", "ollama"),
            ("OpenAI API / ChatGPT CLI", "openai"),
            ("Gemini", "google"),
        ):
            self.combo_roughcut_llm_provider.addItem(label, value)
        self._set_combo_data(self.combo_roughcut_llm_provider, roughcut_provider if roughcut_enabled else "none")
        provider_row.addWidget(self.combo_roughcut_llm_provider)

        self.input_roughcut_llm_model = QLineEdit()
        self.input_roughcut_llm_model.setPlaceholderText("사이드바에서 러프컷 LLM 모델을 선택하세요")
        self.input_roughcut_llm_model.setText(roughcut_model if roughcut_enabled else "사용 안함")
        provider_row.addWidget(self.input_roughcut_llm_model)
        self._hidden_roughcut_provider_row = provider_row

        key_temp_row = QHBoxLayout()
        self.combo_roughcut_api_key_mode = QComboBox()
        for label, value in (("공통 API 키", "inherit"), ("별도 저장 키", "separate")):
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
        self._hidden_roughcut_key_temp_row = key_temp_row

        prompt_info = QLabel("자막 row 문맥/묶음/다음 범위는 LoRA·딥러닝·컷 경계 밀도로 자동 최적화합니다.")
        prompt_info.setWordWrap(True)
        prompt_info.setStyleSheet(label_style("muted", 11))
        form.addRow("러프컷 프롬프트:", prompt_info)

    def _update_editor_roughcut_draft_state(self):
        return

    def _sync_roughcut_llm_controls(self):
        provider = str(self.result_settings.get("roughcut_llm_provider", "none") or "none")
        model_name = str(self.result_settings.get("roughcut_llm_model", "사용 안함") or "사용 안함")
        enabled = (
            bool(self.result_settings.get("roughcut_llm_enabled", False))
            and provider not in {"inherit", "none"}
            and model_name
            and "사용 안함" not in model_name
        )
        self.chk_roughcut_llm_enabled.setChecked(enabled)
        self.chk_roughcut_llm_override.setChecked(enabled)
        self._set_combo_data(self.combo_roughcut_llm_provider, provider if enabled else "none")
        self.input_roughcut_llm_model.setText(model_name if enabled else "사용 안함")

    def _collect_cut_boundary_settings_snapshot(self) -> dict:
        settings = {}
        try:
            from core.settings import load_settings

            settings.update(load_settings())
        except Exception:
            pass
        settings.update(dict(self.result_settings))
        return settings

    def _cut_boundary_auto_roughcut_enabled(self) -> bool:
        try:
            from core.cut_boundary import cut_boundary_enabled

            return bool(cut_boundary_enabled(self._collect_cut_boundary_settings_snapshot()))
        except Exception:
            return bool(self.result_settings.get("cut_boundary_detection_enabled", self.result_settings.get("scan_cut_enabled", True)))

    def _editor_roughcut_draft_enabled_setting(self) -> bool:
        if "editor_roughcut_draft_enabled" in self.result_settings:
            return bool(self.result_settings.get("editor_roughcut_draft_enabled"))
        return self._cut_boundary_auto_roughcut_enabled()

    def _roughcut_llm_enabled_from_widgets(self) -> bool:
        return (
            bool(self.chk_roughcut_llm_enabled.isChecked())
            and (self.combo_roughcut_llm_provider.currentData() or "none") != "none"
            and "사용 안함" not in (self.input_roughcut_llm_model.text().strip() or "")
        )

    def _collect_roughcut_llm_settings(self) -> dict:
        enabled = self._roughcut_llm_enabled_from_widgets()
        return {
            "roughcut_llm_enabled": enabled,
            "roughcut_llm_use_override": enabled,
            "roughcut_run_after_subtitle_generation": bool(enabled),
            "roughcut_llm_provider": self.combo_roughcut_llm_provider.currentData() if enabled else "none",
            "roughcut_llm_model": self.input_roughcut_llm_model.text().strip() if enabled else "사용 안함",
            "roughcut_llm_api_key_mode": self.combo_roughcut_api_key_mode.currentData() or "inherit",
            "roughcut_llm_temperature": round(float(self.spin_roughcut_temperature.value()), 2),
            "roughcut_llm_rows_auto_enabled": True,
            "roughcut_llm_rows_lora_enabled": True,
            "roughcut_llm_prompt": "",
            "roughcut_llm_threads_auto_enabled": True,
        }
