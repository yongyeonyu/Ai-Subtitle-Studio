# Version: 03.14.26
# Phase: PHASE2
"""Model and prompt menu helpers for the home sidebar."""

from __future__ import annotations

import os
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QMenu, QPlainTextEdit, QVBoxLayout

from core.runtime import config
from core.settings import load_settings, save_settings
from core.audio.stt_quality_presets import normalize_stt_quality_key, save_stt_quality_user_preset
from core.mode_manager import selected_mode_from_settings, stt_quality_to_mode
from core.mode_policy import mode_stt_support_flags
from core.roughcut.model_capability import roughcut_llm_is_capable, roughcut_llm_parameter_b
from core.settings_simplifier import apply_simple_operation_mode
from ui.dialogs.qml_popup import show_context_menu
from ui.settings.settings_common import filter_available_whisper_models


def _runtime_load_settings():
    sidebar_owner = sys.modules.get("ui.home_sidebar")
    sidebar_loader = getattr(sidebar_owner, "_runtime_load_settings", None) if sidebar_owner is not None else None
    if callable(sidebar_loader):
        return sidebar_loader()
    owner = sys.modules.get("ui.home_ui")
    return getattr(owner, "load_settings", load_settings)()


def _runtime_save_settings(settings):
    sidebar_owner = sys.modules.get("ui.home_sidebar")
    sidebar_saver = getattr(sidebar_owner, "_runtime_save_settings", None) if sidebar_owner is not None else None
    if callable(sidebar_saver):
        return sidebar_saver(settings)
    owner = sys.modules.get("ui.home_ui")
    return getattr(owner, "save_settings", save_settings)(settings)


class HomeSidebarModelMenuMixin:
    def _apply_ai_settings(self, settings: dict):
        _runtime_save_settings(settings)
        editor = self._active_editor()
        if editor is not None:
            try:
                editor.settings = dict(settings)
                editor.selected_model = settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"))
                video_player = getattr(editor, "video_player", None)
                refresh_audio = getattr(video_player, "refresh_audio_output_routing", None)
                if callable(refresh_audio):
                    refresh_audio(reason="ai_settings_applied")
                if hasattr(editor, "_update_engine_label_text"):
                    editor._update_engine_label_text()
                    engine_label = getattr(editor, "engine_lbl", None)
                    if engine_label is not None:
                        self._refresh_sidebar_engine_info(engine_label.text(), settings=settings)
                        return
            except Exception:
                pass
        self._refresh_sidebar_engine_info()

    def _sidebar_prompt_config(self, key: str, settings: dict | None = None) -> dict | None:
        settings = dict(settings or _runtime_load_settings() or {})
        if key == "subtitle_llm":
            return {
                "title": "자막 LLM 프롬프트",
                "description": "현재 기본 프롬프트는 읽기 전용입니다. 사용자 추가 프롬프트만 저장합니다.",
                "sections": [
                    {
                        "setting_key": "default_llm_prompt",
                        "label": "기본 프롬프트 (JSON: default_llm_prompt)",
                        "value": str(settings.get("default_llm_prompt") or getattr(config, "DEFAULT_LLM_PROMPT", "") or ""),
                        "editable": False,
                    },
                    {
                        "setting_key": "user_prompt",
                        "label": "사용자 추가 프롬프트 (JSON: user_prompt)",
                        "value": str(settings.get("user_prompt") or settings.get("llm_prompt") or ""),
                        "editable": True,
                        "placeholder": "예: 특정 채널 말투 유지, 특정 용어 우선 보정 등",
                    },
                ],
            }
        if key == "roughcut_llm":
            from core.roughcut.editor_draft import DEFAULT_EDITOR_ROUGHCUT_DRAFT_PROMPT
            from core.roughcut.roughcut_prompts import DEFAULT_ROUGHCUT_PROMPT_V1

            return {
                "title": "러프컷 LLM 프롬프트",
                "description": "비워 두면 기본 프롬프트를 사용합니다. 저장 값은 JSON 설정에 반영됩니다.",
                "sections": [
                    {
                        "setting_key": "roughcut_llm_prompt",
                        "label": "러프컷 액션 프롬프트 (JSON: roughcut_llm_prompt)",
                        "value": str(settings.get("roughcut_llm_prompt") or ""),
                        "editable": True,
                        "placeholder": DEFAULT_ROUGHCUT_PROMPT_V1,
                    },
                    {
                        "setting_key": "editor_roughcut_draft_prompt",
                        "label": "에디터 러프컷 초안 프롬프트 (JSON: editor_roughcut_draft_prompt)",
                        "value": str(settings.get("editor_roughcut_draft_prompt") or ""),
                        "editable": True,
                        "placeholder": DEFAULT_EDITOR_ROUGHCUT_DRAFT_PROMPT,
                    },
                ],
            }
        return None

    def _apply_sidebar_prompt_updates(self, updates: dict) -> dict:
        settings = dict(_runtime_load_settings() or {})
        settings.update(dict(updates or {}))
        if "user_prompt" in updates:
            settings["llm_prompt"] = str(settings.get("user_prompt") or "")
        self._apply_ai_settings(settings)
        return settings

    def _open_sidebar_prompt_dialog(self, key: str) -> None:
        config_payload = self._sidebar_prompt_config(key)
        if not config_payload:
            return

        dialog = QDialog(getattr(self, "home_page", None) or self)
        dialog.setWindowTitle(str(config_payload.get("title") or "LLM 프롬프트"))
        dialog.resize(880, 720)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        description = QLabel(str(config_payload.get("description") or ""), dialog)
        description.setWordWrap(True)
        description.setStyleSheet("color:#AFC7DB; font-size:12px;")
        layout.addWidget(description)

        editors: dict[str, QPlainTextEdit] = {}
        for section in list(config_payload.get("sections") or []):
            label = QLabel(str(section.get("label") or ""), dialog)
            label.setWordWrap(True)
            label.setStyleSheet("color:#F5F7FA; font-weight:600; font-size:12px;")
            layout.addWidget(label)

            editor = QPlainTextEdit(dialog)
            editor.setObjectName(f"SidebarPromptEditor_{section.get('setting_key')}")
            editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            editor.setPlaceholderText(str(section.get("placeholder") or ""))
            editor.setPlainText(str(section.get("value") or ""))
            editor.setReadOnly(not bool(section.get("editable", False)))
            editor.setMinimumHeight(140 if section.get("editable", False) else 220)
            editor.setStyleSheet(
                "QPlainTextEdit {"
                "background:#0F171F; color:#F5F7FA; border:1px solid #2C4458; border-radius:8px; padding:10px;"
                "font-family:Menlo, Monaco, Consolas, monospace; font-size:12px; }"
            )
            layout.addWidget(editor, 1 if not bool(section.get("editable", False)) else 0)
            editors[str(section.get("setting_key") or "")] = editor

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return

        updates: dict[str, str] = {}
        for section in list(config_payload.get("sections") or []):
            if not bool(section.get("editable", False)):
                continue
            setting_key = str(section.get("setting_key") or "")
            editor = editors.get(setting_key)
            if editor is None:
                continue
            updates[setting_key] = editor.toPlainText().strip()
        if updates:
            self._apply_sidebar_prompt_updates(updates)

    def _whisper_model_items(self) -> list[str]:
        try:
            from ui.settings.settings_common import DEFAULT_WHISPER_MODELS
            models = list(DEFAULT_WHISPER_MODELS)
        except Exception:
            models = [getattr(config, "WHISPER_MODEL", "large-v3")]
        hf_cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
        if os.path.exists(hf_cache_dir):
            try:
                for folder_name in os.listdir(hf_cache_dir):
                    if folder_name.startswith("models--") and "whisper" in folder_name.lower():
                        repo_name = folder_name.replace("models--", "", 1).replace("--", "/", 1)
                        if repo_name not in models:
                            models.append(repo_name)
            except Exception:
                pass
        return filter_available_whisper_models(models)

    def _stt1_model_items(self) -> list[str]:
        return filter_available_whisper_models(self._whisper_model_items())

    def _stt2_model_items(self) -> list[str]:
        return filter_available_whisper_models(self._whisper_model_items())

    def _llm_model_items(self) -> list[dict]:
        items = [
            {
                "name": "사용 안함 (Whisper 단독 진행)",
                "display_name": "사용 안함 (Whisper 단독 진행)",
                "details": {"provider": "none"},
            }
        ]
        try:
            from ui.settings.settings_common import _fetch_models
            for item in _fetch_models():
                row = dict(item)
                details = dict(row.get("details", {}) or {})
                details.setdefault("provider", "ollama")
                row["details"] = details
                row.setdefault("display_name", row.get("name", ""))
                items.append(row)
        except Exception:
            pass
        try:
            from core.llm.provider_registry import cloud_model_items
            items.extend(cloud_model_items())
        except Exception:
            pass
        return items

    def _roughcut_llm_parameter_b(self, item: dict) -> float | None:
        return roughcut_llm_parameter_b(item)

    def _roughcut_llm_is_capable(self, item: dict) -> bool:
        return roughcut_llm_is_capable(item)

    def _roughcut_llm_items(self) -> list[dict]:
        return [item for item in self._llm_model_items() if self._roughcut_llm_is_capable(item)]

    def _apply_sidebar_model_selection(self, updates: dict):
        settings = dict(_runtime_load_settings())
        if updates:
            settings.update(updates)
        settings.update(mode_stt_support_flags(selected_mode_from_settings(settings)))
        if "selected_model" in updates or "selected_llm_provider" in updates:
            model = str(settings.get("selected_model") or "").strip()
            provider = str(settings.get("selected_llm_provider") or "").strip().lower()
            settings["subtitle_llm_user_selected"] = bool(model and "사용 안함" not in model and provider != "none")
        key = normalize_stt_quality_key(settings.get("stt_quality_preset") or "precise")
        settings = apply_simple_operation_mode(settings, stt_quality_to_mode(key))
        settings = save_stt_quality_user_preset(settings, key)
        self._apply_ai_settings(settings)
        self._sync_sidebar_preset_panel(settings)
        return settings

    def _add_action(self, menu: QMenu, label: str, callback, *, checked: bool = False):
        action = menu.addAction(label)
        action.setCheckable(True)
        action.setChecked(bool(checked))
        action.triggered.connect(callback)
        return action

    def _on_sidebar_model_link(self, href: str):
        if str(href or "").startswith("prompt:"):
            self._queue_sidebar_prompt_dialog(str(href or "").replace("prompt:", "", 1))
            return
        key = str(href or "").replace("model:", "", 1)
        if key not in {"stt", "stt1", "stt2", "subtitle_llm", "roughcut_llm"}:
            return
        settings = _runtime_load_settings()
        items: list[dict] = []
        updates_by_id: dict[str, dict] = {}

        def _push_item(item_id: str, label: str, updates: dict, *, checked: bool = False, accent: str = "#34C759", enabled: bool = True, danger: bool = False):
            items.append(
                {
                    "id": item_id,
                    "label": label,
                    "checked": checked,
                    "accent": accent,
                    "enabled": enabled,
                    "danger": danger,
                }
            )
            updates_by_id[item_id] = dict(updates or {})

        if key == "cut_boundary":
            try:
                from core.cut_boundary import cut_boundary_level
                current = cut_boundary_level(settings)
            except Exception:
                current = "medium" if bool(settings.get("cut_boundary_detection_enabled", settings.get("scan_cut_enabled", True))) else "off"
            current = "off" if str(current or "").strip().lower() == "off" else "auto"

            choices = [
                ("미사용", "off"),
                ("사용", "auto"),
            ]

            labels = {
                "off": "미사용",
                "auto": "사용",
            }
            masks = {
                "off": "off",
                "auto": "auto",
            }

            def _cut_boundary_updates(level: str) -> dict:
                level = str(level or "auto")
                if level != "off":
                    level = "auto"
                enabled = level != "off"
                return {
                    "scan_cut_boundary_level": level,
                    "cut_boundary_level": level,
                    "scan_cut_level": level,
                    "cut_boundary_adaptive_level_enabled": enabled,

                    # 기존 boolean 설정과 호환
                    "cut_boundary_detection_enabled": enabled,
                    "scan_cut_enabled": enabled,
                    "scan_cut_auto_enabled": enabled,
                    "cut_boundary_enabled": enabled,

                    # detector profile 보조 저장
                    "scan_cut_boundary_label": labels.get(level, labels["auto"]),
                    "scan_cut_grid_mask": masks.get(level, "auto"),
                    **(
                        {
                            "roughcut_llm_enabled": False,
                            "roughcut_llm_use_override": True,
                            "roughcut_llm_provider": "none",
                            "roughcut_llm_model": "사용 안함",
                        }
                        if not enabled else {}
                    ),
                }

            for label, value in choices:
                item_id = f"cut_boundary:{value}"
                _push_item(
                    item_id,
                    label,
                    _cut_boundary_updates(value),
                    checked=value == current,
                    accent="#34C759" if value != "off" else "#A9B0B7",
                )

        elif key == "audio":
            choices = [
                ("DeepFilter", "deepfilter"),
                ("RNNoise", "rnnoise"),
                ("Resemble Enhance", "resemble_enhance"),
                ("ClearVoice", "clearvoice"),
                ("미사용", "none"),
            ]
            current = settings.get("selected_audio_ai", "none")
            for label, value in choices:
                _push_item(
                    f"audio:{value}",
                    label,
                    {"selected_audio_ai": value},
                    checked=value == current,
                    accent="#34C759" if value != "none" else "#A9B0B7",
                )

        elif key == "vad":
            choices = [("Silero", "silero"), ("TEN VAD", "ten_vad"), ("미사용", "none")]
            current = settings.get("selected_vad", "silero")
            for label, value in choices:
                _push_item(
                    f"vad:{value}",
                    label,
                    {"selected_vad": value},
                    checked=value == current,
                    accent="#34C759" if value != "none" else "#A9B0B7",
                )

        elif key in {"stt", "stt1", "stt2"}:
            current1 = settings.get("selected_whisper_model", "")
            current2 = settings.get("selected_whisper_model_secondary", "")
            models = self._stt1_model_items() if key in {"stt", "stt1"} else self._stt2_model_items()
            for idx, model in enumerate(models):
                label = self._short_model_name(model, include_recommendations=True)
                if key in {"stt", "stt1"}:
                    _push_item(
                        f"stt1:model:{idx}",
                        label,
                        {"selected_whisper_model": model},
                        checked=model == current1,
                        accent="#5AC8FA",
                    )
                    continue
                _push_item(
                    f"stt2:model:{idx}",
                    label,
                    {"selected_whisper_model_secondary": model},
                    checked=model == current2,
                    accent="#5AC8FA",
                )

        elif key in {"subtitle_llm", "roughcut_llm"}:
            if key == "roughcut_llm":
                _push_item(
                    "roughcut_llm:none",
                    "사용 안함",
                    {
                        "roughcut_llm_enabled": False,
                        "roughcut_llm_use_override": True,
                        "roughcut_llm_provider": "none",
                        "roughcut_llm_model": "사용 안함",
                    },
                    checked=not bool(settings.get("roughcut_llm_enabled", False)),
                    accent="#A9B0B7",
                )
                items.append({"separator": True})

            current = settings.get("selected_model", "") if key == "subtitle_llm" else settings.get("roughcut_llm_model", "")
            model_items = self._roughcut_llm_items() if key == "roughcut_llm" else self._llm_model_items()
            for idx, item in enumerate(model_items):
                name = str(item.get("name") or "")
                label = str(item.get("display_name") or name)
                provider = str((item.get("details", {}) or {}).get("provider") or "ollama")
                if key == "subtitle_llm":
                    updates = {"selected_model": name, "selected_llm_provider": provider}
                else:
                    updates = {
                        "roughcut_llm_enabled": True,
                        "roughcut_llm_use_override": True,
                        "roughcut_llm_provider": provider,
                        "roughcut_llm_model": name,
                    }
                _push_item(
                    f"{key}:model:{idx}",
                    label,
                    updates,
                    checked=name == current,
                    accent="#34C759",
                )

        chosen = show_context_menu(getattr(self, "home_page", None), QCursor.pos(), items)
        if chosen and chosen in updates_by_id:
            self._apply_sidebar_model_selection(updates_by_id[chosen])

    def _queue_sidebar_prompt_dialog(self, key: str) -> None:
        key = str(key or "").strip()
        if not key:
            return
        if bool(getattr(self, "_sidebar_prompt_dialog_pending", False)):
            self._sidebar_prompt_dialog_pending_key = key
            return
        self._sidebar_prompt_dialog_pending = True
        self._sidebar_prompt_dialog_pending_key = key

        def _open_deferred() -> None:
            pending_key = str(getattr(self, "_sidebar_prompt_dialog_pending_key", "") or "")
            self._sidebar_prompt_dialog_pending = False
            self._sidebar_prompt_dialog_pending_key = ""
            if not pending_key:
                return
            # Opening a modal dialog directly from QLabel.linkActivated can crash Qt/Cocoa.
            self._open_sidebar_prompt_dialog(pending_key)

        QTimer.singleShot(0, _open_deferred)
