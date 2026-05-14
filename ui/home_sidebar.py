# Version: 03.14.26
# Phase: PHASE2
"""Home sidebar status, preset, and model-selection helpers."""

import os
import re
import sys
import time
from html import escape

from PyQt6.QtCore import Qt, QTimer, QSize, QDateTime
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSizePolicy, QMenu, QDialog,
    QVBoxLayout, QDialogButtonBox, QPlainTextEdit,
)

from core.runtime import config
from core.settings import load_settings, save_settings
from core.path_manager import load_settings as _path_load_settings, save_settings as _path_save_settings
from core.pipeline_status import generation_stage_keys, generation_stage_keys_all, generation_stage_label
from core.audio.stt_quality_presets import (
    STT_QUALITY_PRESET_ORDER,
    apply_recommended_stt_quality_defaults,
    load_stt_quality_presets,
    normalize_stt_quality_key,
    save_stt_quality_user_preset,
    stt_quality_label,
)
from core.mode_policy import stt_quality_to_mode
from core.roughcut.model_capability import roughcut_llm_is_capable, roughcut_llm_parameter_b
from core.settings_simplifier import apply_simple_operation_mode
from ui.home_sidebar_presets import sync_sidebar_preset_panel
from ui.dialogs.qml_popup import show_context_menu
from ui.queue.queue_formatting import (
    normalize_queue_header_text,
    plain_queue_status,
)
from ui.queue.queue_dispatch import queue_active_row_index, queue_progress_state
from ui.settings.settings_common import filter_available_whisper_models, whisper_model_display_name
from ui.style import line_icon


def _runtime_load_settings():
    owner = sys.modules.get("ui.home_ui")
    return getattr(owner, "load_settings", load_settings)()


def _runtime_save_settings(settings):
    owner = sys.modules.get("ui.home_ui")
    return getattr(owner, "save_settings", save_settings)(settings)


class SidebarComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.view().setMinimumWidth(104)

    def setCurrentIndex(self, index: int) -> None:
        same_index = int(index) == self.currentIndex()
        super().setCurrentIndex(index)
        if same_index and not self.signalsBlocked():
            self.currentIndexChanged.emit(int(index))


class HomeSidebarMixin:
    def _is_auto_start_enabled(self):
        return bool(_runtime_load_settings().get("auto_start_enabled", True))

    def _current_status_time_text(self) -> str:
        text = QDateTime.currentDateTime().toString("AP h:mm")
        return text.replace("AM", "오전").replace("PM", "오후")

    def _ensure_sidebar_queue_panel(self):
        from ui.queue.sidebar_queue_panel import SidebarQueuePanel

        panel = getattr(self, "sidebar_queue_panel", None)
        if panel is not None:
            try:
                if panel.parent() is None:
                    panel.setParent(self.home_page)
                self._sync_sidebar_queue_panel()
                return panel
            except RuntimeError:
                pass
        panel = SidebarQueuePanel(self.home_page)
        self.sidebar_queue_panel = panel
        self._sync_sidebar_queue_panel()
        return panel

    def _queue_sidebar_header_text(self) -> str:
        helper = getattr(self, "queue_sidebar_header_text", None)
        if callable(helper):
            try:
                return str(helper() or "")
            except Exception:
                pass
        label = getattr(self, "queue_header_lbl", None)
        raw = ""
        if label is not None:
            try:
                raw = str(label.text() or "")
            except RuntimeError:
                raw = ""
        if not raw:
            raw = str(getattr(self, "_sidebar_queue_cache_header", "") or "")
        progress = queue_progress_state(self)
        total = int(progress["total"] or 0)
        current = int(progress["current"] or 0)
        pct = int(progress["pct"] or 0)
        return normalize_queue_header_text(raw, current=current, total=total, pct=pct)

    def _sidebar_queue_items(self) -> list[dict]:
        helper = getattr(self, "queue_sidebar_items", None)
        if callable(helper):
            try:
                return list(helper() or [])
            except Exception:
                pass
        return list(getattr(self, "_sidebar_queue_cache_items", []) or [])

    def _active_queue_row_index(self) -> int:
        return queue_active_row_index(self)

    def _plain_queue_status(self, status: str) -> str:
        return plain_queue_status(status)

    def _sync_sidebar_queue_panel(self):
        panel = getattr(self, "sidebar_queue_panel", None)
        if panel is None:
            return
        try:
            panel.set_queue(self._queue_sidebar_header_text(), self._sidebar_queue_items())
        except RuntimeError:
            self.sidebar_queue_panel = None

    def _sidebar_preset_combo_style(self) -> str:
        return (
            "QComboBox { background:#11181C; color:#F5F7FA; border:1px solid #2D3942; "
            "border-radius:5px; padding:1px 5px; font-size:9px; font-weight:700; "
            "min-height:18px; max-height:18px; } "
            "QComboBox:hover { border-color:#465663; background:#151C20; } "
            "QComboBox::drop-down { width:16px; border:none; } "
            "QComboBox QAbstractItemView { background:#151C20; color:#F5F7FA; "
            "selection-background-color:#0B84FF; border:1px solid #2D3942; }"
        )

    def _ensure_sidebar_preset_panel(self):
        for attr in (
            "sidebar_preset_panel",
            "sidebar_stt_quality_combo",
            "sidebar_audio_preset_combo",
            "sidebar_auto_preset_btn",
        ):
            if hasattr(self, attr):
                try:
                    obj = getattr(self, attr)
                    if hasattr(obj, "setParent"):
                        obj.setParent(None)
                except RuntimeError:
                    pass
                try:
                    delattr(self, attr)
                except Exception:
                    pass
        return None

    def _sidebar_subtitle_quality_combo_style(self) -> str:
        return (
            "QComboBox { background:#0E1A20; color:#F5F7FA; border:1px solid #2D3942; "
            "border-radius:4px; padding:1px 17px 1px 9px; font-size:10px; font-weight:700; } "
            "QComboBox:hover { border-color:#3F8CFF; background:#14242B; } "
            "QComboBox::drop-down { border:none; width:16px; } "
            "QAbstractItemView { background:#11181C; color:#F5F7FA; selection-background-color:#1A84FF; "
            "selection-color:#FFFFFF; border:1px solid #2D3942; padding:4px; outline:0; } "
            "QAbstractItemView::item { min-height:22px; padding:3px 16px 3px 16px; }"
        )

    def _subtitle_quality_preset_items(self) -> list[tuple[str, str]]:
        presets = load_stt_quality_presets()
        return [
            (str(presets.get(key, {}).get("label") or stt_quality_label(key)), key)
            for key in STT_QUALITY_PRESET_ORDER
        ]

    def _register_subtitle_quality_combo(self, combo: QComboBox) -> QComboBox:
        combos = list(getattr(self, "_subtitle_quality_combos", []) or [])
        combos = [item for item in combos if item is not combo]
        combos.append(combo)
        self._subtitle_quality_combos = combos
        return combo

    def _sync_subtitle_quality_combos(self, preset_key: str | None = None):
        self._sync_subtitle_quality_combos_for_scope("workspace", preset_key)

    def _subtitle_quality_scope_key(self, scope: str | None) -> str:
        scope = str(scope or "workspace").strip().lower()
        if scope == "icloud":
            return "icloud_stt_quality_preset"
        if scope == "nas":
            return "nas_stt_quality_preset"
        return "stt_quality_preset"

    def _subtitle_quality_scope_default(self, scope: str | None) -> str:
        scope = str(scope or "workspace").strip().lower()
        if scope == "icloud":
            return "fast"
        if scope == "nas":
            return "balanced"
        return "balanced"

    def _subtitle_quality_key_for_scope(self, scope: str | None = None) -> str:
        scope = str(scope or "workspace").strip().lower()
        default = self._subtitle_quality_scope_default(scope)
        if scope in {"icloud", "nas"}:
            try:
                return normalize_stt_quality_key(_path_load_settings().get(self._subtitle_quality_scope_key(scope), default))
            except Exception:
                return normalize_stt_quality_key(default)
        return normalize_stt_quality_key(_runtime_load_settings().get("stt_quality_preset", default))

    def _save_subtitle_quality_key_for_scope(self, scope: str | None, preset_key: str | None):
        scope = str(scope or "workspace").strip().lower()
        key = normalize_stt_quality_key(preset_key or self._subtitle_quality_scope_default(scope))
        if scope in {"icloud", "nas"}:
            settings = _path_load_settings()
            settings[self._subtitle_quality_scope_key(scope)] = key
            _path_save_settings(settings)
            self._sync_subtitle_quality_combos_for_scope(scope, key)
            return key
        self._apply_subtitle_quality_preset(key)
        return key

    def _sync_subtitle_quality_combos_for_scope(self, scope: str | None = None, preset_key: str | None = None):
        requested_scope = str(scope or "workspace").strip().lower()
        key = normalize_stt_quality_key(preset_key or self._subtitle_quality_key_for_scope(requested_scope))
        alive = []
        for combo in list(getattr(self, "_subtitle_quality_combos", []) or []):
            try:
                combo_scope = str(combo.property("subtitleQualityScope") or "workspace").strip().lower()
                if combo_scope != requested_scope:
                    alive.append(combo)
                    continue
                combo.blockSignals(True)
                combo_key = key if combo_scope == requested_scope else self._subtitle_quality_key_for_scope(combo_scope)
                for idx in range(combo.count()):
                    if combo.itemData(idx) == combo_key:
                        combo.setCurrentIndex(idx)
                        break
                combo.blockSignals(False)
                alive.append(combo)
            except RuntimeError:
                continue
        self._subtitle_quality_combos = alive

    def _make_subtitle_quality_combo(self, parent=None, *, width: int = 92, height: int = 24, scope: str = "workspace") -> QComboBox:
        combo = SidebarComboBox(parent)
        scope = str(scope or "workspace").strip().lower()
        combo.setProperty("subtitleQualityScope", scope)
        for label, key in self._subtitle_quality_preset_items():
            combo.addItem(label, key)
        combo.setFixedHeight(height)
        combo.setMinimumContentsLength(5)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        if width > 0:
            combo.setFixedWidth(width)
        else:
            combo.setFixedWidth(96)
            combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        combo.setCursor(Qt.CursorShape.PointingHandCursor)
        combo.setStyleSheet(self._sidebar_subtitle_quality_combo_style())
        combo.setToolTip("Mode")
        combo.currentIndexChanged.connect(self._on_subtitle_quality_combo_changed)
        self._register_subtitle_quality_combo(combo)
        self._sync_subtitle_quality_combos_for_scope(scope)
        return combo

    def _apply_subtitle_quality_preset(self, preset_key: str | None, *, announce: bool = False):
        key = normalize_stt_quality_key(preset_key)
        settings = apply_simple_operation_mode(_runtime_load_settings(), stt_quality_to_mode(key))
        self._apply_ai_settings(settings)
        self._sync_subtitle_quality_combos_for_scope("workspace", key)
        if announce:
            try:
                from core.runtime.logger import get_logger

                get_logger().log(f"💾 Mode 저장: {stt_quality_label(key)}")
            except Exception:
                pass
        return settings

    def _on_subtitle_quality_combo_changed(self, *args):
        combo = self.sender()
        if combo is None or not hasattr(combo, "currentData"):
            return
        scope = str(combo.property("subtitleQualityScope") or "workspace").strip().lower()
        self._save_subtitle_quality_key_for_scope(scope, combo.currentData())

    def _on_sidebar_subtitle_quality_save(self):
        combo = getattr(self, "sidebar_subtitle_quality_combo", None)
        key = normalize_stt_quality_key(
            combo.currentData() if combo is not None else _runtime_load_settings().get("stt_quality_preset")
        )
        settings = save_stt_quality_user_preset(_runtime_load_settings(), key)
        self._apply_ai_settings(settings)
        self._sync_subtitle_quality_combos_for_scope("workspace", key)
        try:
            from core.runtime.logger import get_logger

            get_logger().log(f"💾 Mode 프리셋 저장: {stt_quality_label(key)}")
        except Exception:
            pass

    def _on_sidebar_subtitle_quality_default(self):
        combo = getattr(self, "sidebar_subtitle_quality_combo", None)
        key = normalize_stt_quality_key(
            combo.currentData() if combo is not None else _runtime_load_settings().get("stt_quality_preset")
        )
        mode = stt_quality_to_mode(key)
        settings = dict(_runtime_load_settings() or {})
        settings = apply_recommended_stt_quality_defaults(settings, key)
        settings["_ignore_saved_quality_preset_once"] = True
        settings = apply_simple_operation_mode(settings, mode)
        settings = save_stt_quality_user_preset(settings, key)
        self._apply_ai_settings(settings)
        try:
            from core.project.data_manager import save_default_settings

            save_default_settings(settings)
        except Exception:
            pass
        self._sync_subtitle_quality_combos_for_scope("workspace", key)
        try:
            from core.runtime.logger import get_logger

            get_logger().log(f"⭐ Mode 기본값 지정: {stt_quality_label(key)} 추천값 적용")
        except Exception:
            pass

    def _create_sidebar_subtitle_quality_row(self, parent=None) -> QWidget:
        row = QWidget(parent)
        row.setObjectName("SidebarSubtitleQualityRow")
        row.setStyleSheet("QWidget#SidebarSubtitleQualityRow { background: transparent; border: none; }")
        row.setFixedHeight(24)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        label = QLabel("Mode", row)
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setStyleSheet("color:#00D46A; font-size:10px; font-weight:800; background:transparent; border:none;")
        layout.addWidget(label)

        combo = self._make_subtitle_quality_combo(row, width=78, height=22, scope="workspace")
        self.sidebar_subtitle_quality_combo = combo
        layout.addWidget(combo)
        layout.addStretch(1)

        button_style = (
            "QPushButton { background:#24313A; color:#F5F7FA; border:1px solid #344652; "
            "border-radius:4px; padding:0 4px; font-size:9px; font-weight:800; } "
            "QPushButton:hover { background:#2D3D47; border-color:#3F8CFF; } "
            "QPushButton:pressed { background:#1A84FF; color:#FFFFFF; }"
        )
        save_btn = QPushButton("저장", row)
        save_btn.setIcon(line_icon("save", "#F5F7FA", 16))
        save_btn.setIconSize(QSize(9, 9))
        save_btn.setFixedSize(40, 22)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setToolTip("현재 Mode 설정 저장")
        save_btn.setStyleSheet(button_style)
        save_btn.clicked.connect(self._on_sidebar_subtitle_quality_save)
        self.sidebar_subtitle_quality_save_btn = save_btn
        layout.addWidget(save_btn, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        default_btn = QPushButton("기본값", row)
        default_btn.setFixedSize(48, 22)
        default_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        default_btn.setToolTip("선택한 모델은 유지하고 현재 Mode를 벤치 추천 기본값으로 지정")
        default_btn.setStyleSheet(button_style)
        default_btn.clicked.connect(self._on_sidebar_subtitle_quality_default)
        self.sidebar_subtitle_quality_default_btn = default_btn
        layout.addWidget(default_btn, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return row

    def _settings_for_subtitle_quality_scope(self, scope: str | None) -> dict:
        key = self._subtitle_quality_key_for_scope(scope)
        return apply_simple_operation_mode(_runtime_load_settings(), stt_quality_to_mode(key))

    def _set_runtime_quality_override_for_scope(self, scope: str | None):
        self._runtime_settings_override = self._settings_for_subtitle_quality_scope(scope)
        return self._runtime_settings_override

    def _clear_runtime_quality_override(self):
        self._runtime_settings_override = None

    def _sidebar_preset_row(self, label_text: str, combo: QComboBox) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background:transparent; border:none;")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        label = QLabel(label_text)
        label.setFixedWidth(42)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        label.setStyleSheet("color:#A9B0B7; font-size:9px; font-weight:800; border:none; background:transparent;")
        lay.addWidget(label)
        lay.addWidget(combo, stretch=0)
        row.setFixedWidth(42 + 6 + combo.width())
        return row

    def _set_combo_data_silent(self, combo: QComboBox | None, value: str) -> None:
        if combo is None:
            return
        try:
            combo.blockSignals(True)
            for i in range(combo.count()):
                if combo.itemData(i) == value:
                    combo.setCurrentIndex(i)
                    break
            combo.blockSignals(False)
        except RuntimeError:
            pass
    def _sync_sidebar_preset_panel(self, settings: dict | None = None):
        sync_sidebar_preset_panel(self, settings)
    def _apply_sidebar_settings_update(self, updates: dict | None = None, preset_applier=None):
        settings = dict(_runtime_load_settings())
        if callable(preset_applier):
            settings = dict(preset_applier(settings))
        if updates:
            settings.update(updates)
        self._apply_ai_settings(settings)
        self._sync_sidebar_preset_panel(settings)
        return settings

    def _current_editor_media_path(self) -> str:
        editor = self._active_editor()
        return str(
            getattr(editor, "media_path", "")
            or getattr(getattr(editor, "sm", None), "current_file", "")
            or ""
        )

    def _is_workspace_dirty(self) -> bool:
        editor = self._active_editor()
        if editor is None:
            return bool(getattr(self, "_is_dirty", False))
        dirty_checker = getattr(editor, "_has_unsaved_changes", None)
        if callable(dirty_checker):
            try:
                return bool(dirty_checker())
            except Exception:
                pass
        state_manager = getattr(editor, "sm", None)
        if state_manager is not None:
            return bool(getattr(state_manager, "is_dirty", False))
        return bool(getattr(editor, "_is_dirty", False))

    def _is_subtitle_generation_running(self) -> bool:
        editor = self._active_editor()
        if editor is not None:
            state_manager = getattr(editor, "sm", None)
            if state_manager is not None:
                if str(getattr(state_manager, "state", "") or "") == "ST_PROC":
                    return True
                if bool(getattr(state_manager, "is_locked", False)):
                    return True
            if bool(getattr(editor, "_is_ai_processing", False)):
                return True
        backend = getattr(self, "backend", None)
        for attr in ("_active", "is_running", "running"):
            value = getattr(backend, attr, False)
            if callable(value):
                try:
                    value = value()
                except Exception:
                    value = False
            if bool(value):
                return True
        return bool(getattr(self, "_auto_processing_active", False))

    def _subtitle_status_text(self) -> str:
        if self._is_subtitle_generation_running():
            return "생성 중"
        editor = self._active_editor()
        if editor is not None:
            state_manager = getattr(editor, "sm", None)
            state = str(getattr(state_manager, "state", "") or "")
            if state in {"ST_COMP", "ST_SAVED"}:
                return "완료"
        return "대기"

    def _sidebar_parse_clock_seconds(self, value) -> float | None:
        parser = getattr(self, "_parse_queue_seconds_value", None)
        if callable(parser):
            try:
                parsed = parser(value)
            except Exception:
                parsed = None
            if parsed is not None:
                return float(parsed)
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return float(text)
        except (TypeError, ValueError):
            pass
        if ":" not in text:
            return None
        parts = [part.strip() for part in text.split(":")]
        if not parts or any(not part.isdigit() for part in parts):
            return None
        units = [int(part) for part in parts]
        if len(units) == 2:
            minutes, seconds = units
            return float((minutes * 60) + seconds)
        if len(units) == 3:
            hours, minutes, seconds = units
            return float((hours * 3600) + (minutes * 60) + seconds)
        return None

    def _sidebar_format_clock(self, seconds: float) -> str:
        formatter = getattr(self, "_format_queue_clock", None)
        if callable(formatter):
            try:
                return str(formatter(seconds))
            except Exception:
                pass
        total = max(0, int(round(float(seconds or 0.0))))
        hours, rem = divmod(total, 3600)
        minutes, secs = divmod(rem, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def _sidebar_generation_active_row(self) -> int:
        getter = getattr(self, "_current_queue_active_row", None)
        if callable(getter):
            try:
                return int(getter())
            except Exception:
                pass
        queue_getter = getattr(self, "queue_active_row_index", None)
        if callable(queue_getter):
            try:
                return int(queue_getter())
            except Exception:
                pass
        row_counter = getattr(self, "queue_row_count", None)
        if callable(row_counter):
            try:
                row_count = max(0, int(row_counter() or 0))
            except Exception:
                row_count = 0
        else:
            row_count = len(list(getattr(self, "_sidebar_queue_cache_items", []) or []))
        row = queue_active_row_index(self)
        if row_count > 0:
            return row if 0 <= row < row_count else -1
        return max(-1, row)

    def _sidebar_generation_row_status(self, row: int) -> str:
        getter = getattr(self, "queue_row_status_text", None)
        if callable(getter):
            try:
                return str(getter(int(row)) or "")
            except Exception:
                pass
        if row < 0:
            return ""
        cache = list(getattr(self, "_sidebar_queue_cache_items", []) or [])
        if 0 <= int(row) < len(cache):
            item = dict(cache[int(row)] or {})
            return str(item.get("statusRaw", item.get("statusDisplay", item.get("status", ""))) or "")
        return ""

    def _sidebar_generation_row_expected_seconds(self, row: int) -> float:
        getter = getattr(self, "queue_row_expected_seconds", None)
        if callable(getter):
            try:
                return max(0.0, float(getter(int(row)) or 0.0))
            except Exception:
                pass
        try:
            expected = float((getattr(self, "_expected_seconds", {}) or {}).get(int(row), 0.0) or 0.0)
        except Exception:
            expected = 0.0
        if expected > 0:
            return expected
        if row < 0:
            return 0.0
        cache = list(getattr(self, "_sidebar_queue_cache_items", []) or [])
        if 0 <= int(row) < len(cache):
            item = dict(cache[int(row)] or {})
            eta_text = str(item.get("etaRaw", "") or "")
            duration_text = str(item.get("duration", "") or "")
        else:
            eta_text = ""
            duration_text = ""
        labeler = getattr(self, "_queue_expected_time_label", None)
        if callable(labeler):
            try:
                eta_text = str(labeler(int(row), eta_text, duration_text) or eta_text or duration_text)
            except Exception:
                eta_text = eta_text or duration_text
        else:
            eta_text = eta_text or duration_text
        parsed = self._sidebar_parse_clock_seconds(eta_text)
        return max(0.0, float(parsed or 0.0))

    def _sidebar_generation_row_elapsed_seconds(self, row: int, now_ts: float) -> float:
        getter = getattr(self, "queue_row_elapsed_seconds", None)
        if callable(getter):
            try:
                return max(0.0, float(getter(int(row), now_ts=now_ts) or 0.0))
            except Exception:
                pass
        start_times = dict(getattr(self, "_file_start_times", {}) or {})
        complete_times = dict(getattr(self, "_file_complete_times", {}) or {})
        started_at = float(start_times.get(int(row), 0.0) or 0.0)
        if started_at <= 0.0:
            return 0.0
        ended_at = float(complete_times.get(int(row), 0.0) or 0.0)
        if ended_at <= 0.0:
            ended_at = float(now_ts)
        return max(0.0, ended_at - started_at)

    def _sidebar_generation_stage_text(self) -> str:
        editor = self._active_editor()
        stt_ensemble_enabled = bool(getattr(editor, "settings", {}) and getattr(editor, "settings", {}).get("stt_ensemble_enabled", False))
        status_candidates: list[str] = []
        if editor is not None:
            label = getattr(editor, "status_lbl", None)
            if label is not None:
                try:
                    status_candidates.append(str(label.text() or ""))
                except Exception:
                    pass
            state_manager = getattr(editor, "sm", None)
            if state_manager is not None:
                for attr in ("custom_status", "_custom_status", "status_text"):
                    try:
                        value = str(getattr(state_manager, attr, "") or "")
                    except Exception:
                        value = ""
                    if value:
                        status_candidates.append(value)
        active_row = self._sidebar_generation_active_row()
        if active_row >= 0:
            status_candidates.append(self._sidebar_generation_row_status(active_row))
        for raw in status_candidates:
            text = str(raw or "").strip()
            if not text:
                continue
            if "오류" in text or "실패" in text or "중단" in text:
                return "오류"
            if "저장" in text:
                return "저장"
            if "완료" in text:
                return "완료"
            stage = generation_stage_label(text, stt_ensemble_enabled=stt_ensemble_enabled)
            if stage:
                return stage
            plain = self._plain_queue_status(text)
            if plain and plain not in {"-", "대기 중"}:
                return plain
        if self._is_subtitle_generation_running():
            return "진행 중"
        progress = queue_progress_state(self)
        return "완료" if int(progress["pct"] or 0) >= 100 else "대기"

    def _sidebar_generation_completion_quality_score(self) -> float | None:
        editor = self._active_editor()
        if editor is None:
            return None
        summary = getattr(editor, "_quality_summary", None)
        score = None
        if isinstance(summary, dict):
            score = summary.get("overall_score", summary.get("score"))
        else:
            score = getattr(summary, "overall_score", None)
        if isinstance(score, (int, float)):
            return float(score)

        getter = getattr(editor, "_get_current_segments", None)
        if not callable(getter):
            return None
        try:
            segments = list(getter() or [])
        except Exception:
            return None
        for seg in segments:
            if not isinstance(seg, dict) or bool(seg.get("is_gap")):
                continue
            payload = dict(seg.get("subtitle_quality_self_review_summary") or {})
            score = payload.get("overall_score", payload.get("score"))
            if isinstance(score, (int, float)):
                return float(score)
        return None

    def _generation_progress_snapshot(self) -> dict:
        running = self._is_subtitle_generation_running()
        now_ts = time.time()
        metrics_getter = getattr(self, "queue_progress_metrics", None)
        if callable(metrics_getter):
            try:
                metrics = dict(metrics_getter(now_ts=now_ts, running=running) or {})
            except Exception:
                metrics = {}
        else:
            metrics = {}
        if not metrics:
            active_row = self._sidebar_generation_active_row()
            row_counter = getattr(self, "queue_row_count", None)
            if callable(row_counter):
                try:
                    row_count = max(0, int(row_counter() or 0))
                except Exception:
                    row_count = 0
            else:
                row_count = len(list(getattr(self, "_sidebar_queue_cache_items", []) or []))
            progress = queue_progress_state(self)
            total_files = max(row_count, int(progress["total"] or 0))
            total_expected = 0.0
            total_elapsed = 0.0
            progress_elapsed = 0.0
            known_expected_rows = 0
            all_done = total_files > 0

            flagger = getattr(self, "_queue_status_flags", None)
            for row in range(total_files):
                status_text = self._sidebar_generation_row_status(row)
                if callable(flagger):
                    try:
                        row_done, row_error, _row_active = flagger(status_text)
                    except Exception:
                        row_done = row_error = False
                else:
                    row_done = "완료" in status_text
                    row_error = any(token in status_text for token in ("오류", "실패", "중단"))
                expected = self._sidebar_generation_row_expected_seconds(row)
                elapsed = self._sidebar_generation_row_elapsed_seconds(row, now_ts)
                if elapsed > 0.0:
                    total_elapsed += elapsed
                if expected > 0.0:
                    total_expected += expected
                    known_expected_rows += 1
                    if row_done:
                        progress_elapsed += expected
                    elif row == active_row and running:
                        progress_elapsed += min(elapsed, expected)
                if not row_done and not row_error:
                    all_done = False

            percent = float(progress["pct"] or 0.0)
            if total_expected > 0.0 and known_expected_rows >= total_files and total_files > 0:
                percent = (progress_elapsed / total_expected) * 100.0
            if all_done and total_files > 0:
                percent = 100.0
            elif running:
                percent = min(percent, 99.0)
            percent = max(0.0, min(100.0, percent))
            metrics = {
                "active_row": active_row,
                "row_count": row_count,
                "total_files": total_files,
                "total_expected": total_expected,
                "total_elapsed": total_elapsed,
                "progress_elapsed": progress_elapsed,
                "known_expected_rows": known_expected_rows,
                "all_done": all_done,
                "percent": percent,
            }
        total_expected = float(metrics.get("total_expected", 0.0) or 0.0)
        total_elapsed = float(metrics.get("total_elapsed", 0.0) or 0.0)
        percent = float(metrics.get("percent", 0.0) or 0.0)

        stage_text = self._sidebar_generation_stage_text()
        title = f"자막 생성 | {stage_text}"
        progress_text = f"{int(round(percent))}%"
        subtitle = ""
        if running or percent > 0.0 or total_expected > 0.0:
            elapsed_text = self._sidebar_format_clock(total_elapsed)
            expected_text = self._sidebar_format_clock(total_expected) if total_expected > 0.0 else "--:--"
            subtitle = f"{elapsed_text} / {expected_text}"
            if not running and int(round(percent)) >= 100:
                quality_score = self._sidebar_generation_completion_quality_score()
                if isinstance(quality_score, (int, float)):
                    subtitle = f"{subtitle} · {float(quality_score):.2f}"
        tooltip_lines = [title, progress_text]
        if subtitle:
            tooltip_lines.append(subtitle)
        return {
            "running": running,
            "title": title,
            "subtitle": subtitle,
            "percent": int(round(percent)),
            "percentValue": float(percent),
            "progressText": progress_text,
            "tooltip": "\n".join(line for line in tooltip_lines if line),
        }

    def _sidebar_generation_nav_item(self) -> dict:
        snapshot = self._generation_progress_snapshot()
        return {
            "id": "generation_status",
            "title": snapshot["title"],
            "subtitle": snapshot["subtitle"],
            "badge": "AI",
            "accent": "#00D46A" if snapshot["running"] or snapshot["percent"] > 0 else "#34C759",
            "active": False,
            "enabled": True,
            "progressVisible": True,
            "progressPercent": snapshot["percent"],
            "progressText": snapshot["progressText"],
            "fillColor": "#153A25",
            "height": 38,
            "tooltip": snapshot["tooltip"],
        }

    def _roughcut_status_text(self) -> str:
        editor = self._active_editor()
        if editor is None:
            return "대기"
        if not bool(getattr(editor, "_roughcut_draft_runtime_enabled", lambda: False)()):
            return "비활성"
        status = str(getattr(editor, "_roughcut_draft_status", "") or "")
        count = getattr(editor, "_last_roughcut_draft_major_count", None)
        if status == "queued":
            return "예약"
        if status == "running":
            return "생성 중"
        if status == "saving":
            return "저장 중"
        if status == "failed":
            return "실패"
        if status == "done":
            return f"완료 {count}개" if count is not None else "완료"
        if count is not None:
            return f"완료 {count}개"
        return "대기"

    def _ensure_saved_status_blink_timer(self):
        if hasattr(self, "_saved_status_blink_timer"):
            return
        self._saved_status_blink_on = True
        self._saved_status_blink_timer = QTimer(self)
        self._saved_status_blink_timer.setInterval(1000)
        self._saved_status_blink_timer.timeout.connect(self._tick_saved_status_blink)

    def _tick_saved_status_blink(self):
        self._saved_status_blink_on = not bool(getattr(self, "_saved_status_blink_on", True))
        self._refresh_saved_status_label(is_dirty=getattr(self, "_last_saved_status_dirty", None))
        if getattr(self, "sidebar_settings_label", None) is not None:
            self._refresh_sidebar_engine_info()

    def _sync_saved_status_blink_timer(self, active: bool, *, interval_ms: int = 1000):
        self._ensure_saved_status_blink_timer()
        timer = self._saved_status_blink_timer
        try:
            interval = max(100, int(interval_ms or 1000))
        except Exception:
            interval = 1000
        if active:
            if int(timer.interval()) != interval:
                timer.setInterval(interval)
            if not timer.isActive():
                self._saved_status_blink_on = True
                timer.start()
        else:
            if timer.isActive():
                timer.stop()
            self._saved_status_blink_on = True

    def _refresh_saved_status_label(self, is_dirty=None, touch_saved_time=False):
        label = getattr(self, "saved_status_label", None)
        if label is None:
            return
        dirty = self._is_workspace_dirty() if is_dirty is None else bool(is_dirty)
        self._last_saved_status_dirty = dirty
        if not hasattr(self, "_last_saved_status_time"):
            self._last_saved_status_time = self._current_status_time_text()
        if not dirty and touch_saved_time:
            self._last_saved_status_time = self._current_status_time_text()

        generating = self._is_subtitle_generation_running()
        trainer = getattr(self, "_personalization_idle_trainer", None)
        learning_status = {}
        if trainer is not None:
            status_getter = getattr(trainer, "learning_status", None)
            if callable(status_getter):
                try:
                    learning_status = dict(status_getter() or {})
                except Exception:
                    learning_status = {}
        learning = bool(learning_status.get("active")) and not generating
        blink_interval = int(learning_status.get("blink_interval_ms", 1000) or 1000) if learning else 1000
        self._sync_saved_status_blink_timer(generating or learning, interval_ms=1000 if generating else blink_interval)
        if generating:
            dot_color = "#FF453A" if bool(getattr(self, "_saved_status_blink_on", True)) else "#5A1F24"
            tooltip = "자막 생성 중입니다."
        elif learning:
            dot_color = "#0A84FF" if bool(getattr(self, "_saved_status_blink_on", True)) else "#06335F"
            mode = str(learning_status.get("mode") or "lite").lower()
            tooltip = (
                "Heavy learning is running. Mouse or keyboard input stops learning."
                if mode == "heavy"
                else "Lite learning is running. Mouse or keyboard input stops learning."
            )
        else:
            dot_color = "#FF453A" if dirty else "#34C759"
            tooltip = "저장되지 않은 변경사항이 있습니다." if dirty else "저장된 상태입니다."
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(False)
        label.setMinimumHeight(22)
        from core.runtime.config import APP_VERSION
        title_color = self._runtime_title_status_color()
        label.setText(
            "<table width='100%' cellspacing='0' cellpadding='0' style='margin:0; padding:0;'>"
            "<tr>"
            "<td style='padding:0; margin:0; text-align:left; white-space:nowrap;'>"
            f"<span style='color:{dot_color}; font-size:12px;'>●</span> "
            f"<span style='color:{title_color}; font-size:13px; font-weight:700;'>AI Subtitle Studio</span>"
            "</td>"
            "<td style='padding:0; margin:0; text-align:right; white-space:nowrap;'>"
            f"<span style='color:#D1D1D6; font-size:10px; font-weight:600;'>v{APP_VERSION}</span>"
            "</td>"
            "</tr>"
            "</table>"
        )
        label.setToolTip(tooltip)
        refresher = getattr(self, "_refresh_sidebar_nav_menu", None)
        if callable(refresher):
            try:
                refresher()
            except Exception:
                pass

    def _runtime_title_status_color(self) -> str:
        snapshot = dict(getattr(self, "_runtime_resource_snapshot", {}) or {})
        if not snapshot:
            return "#FFFFFF"
        coordinator = getattr(self, "_runtime_resource_coordinator", None)
        if coordinator is not None and hasattr(coordinator, "status_color"):
            try:
                return str(coordinator.status_color(snapshot) or "#FFFFFF")
            except Exception:
                pass
        stage = str(snapshot.get("pressure_stage", "normal") or "normal")
        return {
            "normal": "#34C759",
            "warning": "#FFD60A",
            "critical": "#FF453A",
            "exit": "#FF9500",
        }.get(stage, "#34C759")

    def _format_engine_info_text(self, text: str) -> str:
        lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        return "\n".join(lines)

    def _short_model_name(self, model: str) -> str:
        text = str(model or "").strip()
        if not text:
            return "미사용"
        if "사용 안함" in text:
            return "미사용"
        display_name = whisper_model_display_name(text)
        if display_name and display_name != text:
            return display_name
        lowered = text.lower()
        if lowered == "whisper-medium-komixv2":
            return "KomixV2 · 별칭"
        if lowered == "youngouk/whisper-medium-komixv2-mlx":
            return "KomixV2 · MLX"
        if lowered == "seastar105/whisper-medium-komixv2":
            return "KomixV2 · HF 원본"
        for prefix in ("whisper.cpp:", "whisper_cpp:", "whisper-cpp:"):
            if lowered.startswith(prefix):
                return f"whisper.cpp · {text[len(prefix):] or 'default'}"
        for prefix in ("mlx-community/", "Systran/", "youngouk/", "ghost613/", "o0dimplz0o/"):
            text = text.replace(prefix, "")
        text = text.replace("-mlx", "")
        return text

    def _audio_model_name(self, settings: dict) -> str:
        label = {
            "deepfilter": "DeepFilter",
            "rnnoise": "RNNoise",
            "resemble_enhance": "Resemble",
            "clearvoice": "ClearVoice",
            "none": "미사용",
        }.get(settings.get("selected_audio_ai", "none"), "미사용")
        if bool(settings.get("_runtime_auto_audio_ai_selected")):
            return f"{label} 자동"
        return label

    def _vad_model_name(self, settings: dict) -> tuple[str, str]:
        vad_model = {
            "silero": "Silero",
            "ten_vad": "TEN VAD",
            "webrtc": "WebRTC",
            "pyannote": "Pyannote",
            "none": "미사용",
        }.get(settings.get("selected_vad", "none"), "미사용")
        vad_disabled = vad_model == "미사용"
        if bool(settings.get("_runtime_auto_vad_selected")):
            vad_model = f"{vad_model} 자동"
        if vad_disabled:
            return vad_model, "검수 안 함"
        if settings.get("vad_pre_split_enabled", False):
            return vad_model, "STT 선분할"
        if settings.get("vad_post_stt_align_enabled", True):
            return vad_model, "자막 위치 재계산"
        return vad_model, "자막/음성 겹침 검수"

    def _roughcut_llm_name(self, settings: dict, subtitle_llm: str) -> tuple[str, str]:
        if not self._cut_boundary_enabled(settings):
            return "미사용", "러프컷 규칙 기반"
        if not bool(settings.get("roughcut_llm_enabled", False)):
            return "미사용", "러프컷 규칙 기반"
        model = str(settings.get("roughcut_llm_model", "") or "").strip()
        if not model or model.lower() == "inherit" or "사용 안함" in model:
            return "미사용", "러프컷 규칙 기반"
        return self._short_model_name(model), "러프컷 전용"

    def _cut_boundary_enabled(self, settings: dict) -> bool:
        try:
            from core.cut_boundary import cut_boundary_level

            return str(cut_boundary_level(settings or {})).strip().lower() != "off"
        except Exception:
            return bool(
                (settings or {}).get(
                    "cut_boundary_detection_enabled",
                    (settings or {}).get("scan_cut_enabled", True),
                )
            )

    def _subtitle_llm_enabled(self, settings: dict) -> bool:
        model = str((settings or {}).get("selected_model", "") or "").strip()
        provider = str((settings or {}).get("selected_llm_provider", "ollama") or "ollama").strip().lower()
        if not model:
            return True
        if provider == "none":
            return False
        return "사용 안함" not in model

    def _roughcut_llm_effective_enabled(self, settings: dict) -> bool:
        if not self._cut_boundary_enabled(settings):
            return False
        if not bool((settings or {}).get("roughcut_llm_enabled", False)):
            return False
        model = str((settings or {}).get("roughcut_llm_model", "") or "").strip()
        provider = str((settings or {}).get("roughcut_llm_provider", "ollama") or "ollama").strip().lower()
        if not model or provider == "none":
            return False
        return "사용 안함" not in model

    def _cut_boundary_sidebar_label(self, settings: dict) -> str:
        """Return sidebar display label for cut-boundary level."""
        try:
            from core.cut_boundary import cut_boundary_level
            level = cut_boundary_level(settings or {})
        except Exception:
            enabled = bool(
                (settings or {}).get(
                    "cut_boundary_detection_enabled",
                    (settings or {}).get("scan_cut_enabled", True),
                )
            )
            level = "medium" if enabled else "off"

        return {
            "off": "미사용",
        }.get(str(level or "medium"), "사용")

    def _pipeline_model_labels(self, settings: dict) -> dict[str, str]:
        short_name = getattr(self, "_short_model_name", lambda value: value)
        subtitle_llm = str(
            settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "기본"))
            or "기본"
        )
        subtitle_llm_label = (
            "미사용"
            if not self._subtitle_llm_enabled(settings)
            else short_name(subtitle_llm)
        )
        vad_model, _ = getattr(self, "_vad_model_name", lambda value: ("기본", ""))(settings)
        roughcut_resolver = getattr(self, "_roughcut_llm_name", None)
        roughcut_llm = "기본"
        if callable(roughcut_resolver):
            try:
                roughcut_llm, _ = roughcut_resolver(settings, subtitle_llm)
            except Exception:
                roughcut_llm = "기본"
        stt1_model = short_name(
            settings.get(
                "selected_whisper_model",
                getattr(config, "WHISPER_MODEL", "기본"),
            )
        )
        stt2_model = "미사용"
        if settings.get("stt_ensemble_enabled"):
            stt2_model = short_name(settings.get("selected_whisper_model_secondary", ""))
        return {
            "subtitle_llm": subtitle_llm_label,
            "roughcut_llm": roughcut_llm,
            "stt1": stt1_model,
            "stt2": stt2_model,
            "vad": vad_model,
        }

    def _pipeline_rows(self, settings: dict) -> list[tuple[str, str, str]]:
        model_labels = self._pipeline_model_labels(settings)
        cut_label = self._cut_boundary_sidebar_label(settings)
        lora_buckets = settings.get("subtitle_lora_quality_buckets")
        if isinstance(lora_buckets, (list, tuple)) and lora_buckets:
            lora_label = "/".join(str(item) for item in lora_buckets)
        elif bool(settings.get("editor_lora_runtime_enabled", settings.get("subtitle_bundle_lora_enabled", True))):
            lora_label = "선택 적용"
        else:
            lora_label = "미사용"
        if bool(settings.get("deep_subtitle_policy_enabled", True)) or bool(settings.get("deep_segment_setting_policy_enabled", True)):
            deep_label = "선택 적용" if settings.get("simple_operation_mode") == "auto" else "사용"
        else:
            deep_label = "미사용"

        return [
            ("cut_boundary", "컷 경계", cut_label),
            ("preprocess", "전처리", "FFMPEG"),
            ("audio", "음성", getattr(self, "_audio_model_name", lambda s: "기본")(settings)),
            ("stt1", "STT 1", model_labels["stt1"]),
            ("stt2", "STT 2", model_labels["stt2"]),
            ("vad", "VAD", model_labels["vad"]),
            ("subtitle_llm", "자막 LLM", model_labels["subtitle_llm"]),
            ("roughcut_llm", "러프컷 LLM", model_labels["roughcut_llm"]),
            ("lora", "LoRA", lora_label),
            ("deep_learning", "딥러닝", deep_label),
        ]
    def _pipeline_status_blob(self) -> str:
        parts = []
        for attr in ("queue_header_lbl", "saved_status_label"):
            label = getattr(self, attr, None)
            if label is None:
                continue
            try:
                parts.append(str(label.text() or ""))
            except RuntimeError:
                pass
        for attr in ("log_text",):
            widget = getattr(self, attr, None)
            if widget is None:
                continue
            try:
                if hasattr(widget, "toPlainText"):
                    text = str(widget.toPlainText() or "")
                elif hasattr(widget, "text"):
                    text = str(widget.text() or "")
                else:
                    text = ""
                if text:
                    parts.append(text[-16000:])
            except RuntimeError:
                pass
        editor = self._active_editor()
        if editor is not None:
            # `engine_lbl` is a static settings summary like `[STT]`, `[VAD]`, `[음성]`.
            # Treating it as a live pipeline source causes freshly opened files to
            # look like they are already running/completed, so only runtime status
            # labels should feed stage detection.
            for attr in ("status_label", "status_lbl"):
                label = getattr(editor, attr, None)
                if label is None:
                    continue
                try:
                    if hasattr(label, "text"):
                        parts.append(str(label.text() or ""))
                except RuntimeError:
                    pass
        queue_probe = getattr(self, "queue_status_probe_parts", None)
        if callable(queue_probe):
            try:
                parts.extend(str(part or "") for part in list(queue_probe(0, (0, 2, 4)) or []) if str(part or ""))
            except Exception:
                pass
        else:
            cache = list(getattr(self, "_sidebar_queue_cache_items", []) or [])
            if cache:
                item = dict(cache[0] or {})
                for key in ("statusRaw", "infoRaw", "etaRaw"):
                    value = str(item.get(key, "") or "")
                    if value:
                        parts.append(value)
        return "\n".join(parts)

    def _pipeline_cached_stage_keys(self, blob: str) -> set[str]:
        text = str(blob or "").lower()
        if not text:
            return set()

        cached: set[str] = set()
        cache_tokens = ("캐시", "캐쉬", "cache")
        reuse_tokens = ("재사용", "재활용", "reuse", "reused")
        if any(token in text for token in cache_tokens) and any(token in text for token in reuse_tokens):
            if "[전처리]" in text or "ffmpeg 오디오 캐시" in text or "오디오 캐시" in text:
                cached.add("preprocess")
                cached.add("audio")
            if "[음성]" in text or "음성필터" in text or "음성 필터" in text or "deepfilter" in text:
                cached.add("audio")
            if "[vad" in text or "vad 캐시" in text:
                cached.add("vad")
        return cached

    def _cut_boundary_scan_line_confirmed(self, row) -> bool:
        if not isinstance(row, dict):
            return True
        status = str(row.get("status", "") or "").strip().lower()
        return (
            status in {"verified", "confirmed", "accepted", "done"}
            or bool(row.get("verified"))
            or bool(row.get("confirmed"))
        )

    def _cut_boundary_scan_pending(self, editor) -> bool:
        if editor is None:
            return False
        if bool(getattr(editor, "_auto_cut_boundary_scan_active", False)):
            return True
        provisional_lines = list(getattr(editor, "_auto_cut_boundary_scan_lines", []) or [])
        return any(not self._cut_boundary_scan_line_confirmed(row) for row in provisional_lines)

    def _cut_boundary_status_lines(self, blob: str) -> list[str]:
        normalized = str(blob or "").replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
        lines = [line.strip() for line in normalized.splitlines() if str(line or "").strip()]
        return [
            line
            for line in lines
            if any(
                token in line.lower()
                for token in (
                    "[컷 경계]",
                    "컷 경계",
                    "scan-cut",
                    "scan cut",
                    "cut boundary",
                    "cut_boundary",
                )
            )
        ]

    def _cut_boundary_line_is_pending(self, line: str) -> bool:
        text = str(line or "").lower()
        return any(
            token in text
            for token in (
                "완료 대기",
                "완료대기",
                "대기 중",
                "대기중",
                "진행 중",
                "진행중",
                "분석 중",
                "분석중",
                "탐색 중",
                "탐색중",
                "확인 중",
                "확인중",
                "임시선",
                "재배치",
                "선발대",
                "후발대",
                "rollback",
                "검증 중",
                "검증중",
                "waiting",
                "pending",
                "running",
            )
        )

    def _cut_boundary_log_pending(self, blob: str) -> bool:
        for line in reversed(self._cut_boundary_status_lines(blob)):
            if self._cut_boundary_line_is_pending(line):
                return True
            if self._cut_boundary_line_is_complete(line):
                return False
        return False

    def _cut_boundary_line_is_complete(self, line: str) -> bool:
        text = str(line or "")
        return any(
            token in text
            for token in (
                "컷 경계 완료",
                "컷 경계 자동 분석 완료",
                "STT 시작 전 자동 분석 완료",
                "캐시 재사용",
            )
        )

    def _cut_boundary_scan_completed(self, editor, blob: str) -> bool:
        for line in reversed(self._cut_boundary_status_lines(blob)):
            if self._cut_boundary_line_is_pending(line):
                return False
            if self._cut_boundary_line_is_complete(line):
                return True
        if editor is None:
            return False
        if bool(getattr(editor, "_cut_boundary_prescan_completed", False)):
            return True
        lines = list(getattr(editor, "_auto_cut_boundary_scan_lines", []) or [])
        if lines and all(self._cut_boundary_scan_line_confirmed(row) for row in lines):
            return True
        return bool(getattr(self, "_project_boundary_times", []) or [])

    def _roughcut_draft_status_value(self) -> str:
        editor = self._active_editor()
        if editor is None:
            return ""
        return str(getattr(editor, "_roughcut_draft_status", "") or "")

    def _pipeline_current_stage_keys(self, settings: dict) -> set[str]:
        roughcut_status = self._roughcut_draft_status_value()
        if roughcut_status in {"queued", "running", "saving"}:
            return {"roughcut_llm"}
        if not self._is_subtitle_generation_running():
            return set()

        blob = self._pipeline_status_blob()
        keys = generation_stage_keys_all(
            blob,
            stt_ensemble_enabled=bool(settings.get("stt_ensemble_enabled", False)),
        )
        if not keys:
            keys = generation_stage_keys(
                blob,
                stt_ensemble_enabled=bool(settings.get("stt_ensemble_enabled", False)),
            )
        return keys

    def _pipeline_completed_stage_keys(self, settings: dict, current_keys: set[str]) -> set[str]:
        completed: set[str] = set()
        blob = self._pipeline_status_blob()
        blob_lower = str(blob or "").lower()
        editor = self._active_editor()
        state_value = str(getattr(getattr(editor, "sm", None), "state", "") or "") if editor is not None else ""
        queue_done = False
        completion_getter = getattr(self, "queue_completion_state", None)
        if callable(completion_getter):
            try:
                queue_done = bool(dict(completion_getter() or {}).get("all_done"))
            except Exception:
                queue_done = False
        else:
            cached_items = list(getattr(self, "_sidebar_queue_cache_items", []) or [])
            if cached_items:
                queue_done = all(bool(dict(item or {}).get("done")) for item in cached_items)
        stage_now = set(current_keys or set())
        live_stage_active = bool(stage_now & {
            "cut_boundary",
            "preprocess",
            "audio",
            "stt1",
            "stt2",
            "vad",
            "subtitle_llm",
        })
        generation_done = (
            not live_stage_active
            and (
                "자막 생성 완료" in blob
                or queue_done
                or state_value in {"ST_COMP", "ST_SAVED"}
                or bool(getattr(editor, "_subtitle_generation_completed", False))
            )
        )
        cut_boundary_pending = self._cut_boundary_scan_pending(editor) or self._cut_boundary_log_pending(blob)
        cut_boundary_done = self._cut_boundary_scan_completed(editor, blob)
        cached_stages = self._pipeline_cached_stage_keys(blob)
        completed.update(cached_stages)
        cut_boundary_enabled = self._cut_boundary_enabled(settings)
        vad_enabled = settings.get("selected_vad", "none") != "none"
        stt2_enabled = bool(settings.get("stt_ensemble_enabled", False))
        subtitle_llm_enabled = self._subtitle_llm_enabled(settings)
        roughcut_enabled = self._roughcut_llm_effective_enabled(settings)
        editor_roughcut_count = getattr(editor, "_last_roughcut_draft_major_count", None) if editor is not None else None
        roughcut_status = self._roughcut_draft_status_value()
        explicit_save_done = any(
            token in blob_lower
            for token in (
                "프로젝트 저장 완료",
                "저장 완료:",
                ".srt 저장 완료",
                "💾 저장 완료",
                "📦 프로젝트 저장 완료",
            )
        )
        roughcut_started = (
            "roughcut_llm" in stage_now
            or roughcut_status in {"queued", "running", "saving", "done"}
            or editor_roughcut_count is not None
        )

        if not cut_boundary_enabled:
            completed.add("cut_boundary")
        if not stt2_enabled:
            completed.add("stt2")
        if not vad_enabled:
            completed.add("vad")
        if not subtitle_llm_enabled:
            completed.add("subtitle_llm")
        if not roughcut_enabled:
            completed.add("roughcut_llm")
        if not bool(settings.get("editor_lora_runtime_enabled", settings.get("subtitle_bundle_lora_enabled", True))):
            completed.add("lora")
        if not (bool(settings.get("deep_subtitle_policy_enabled", True)) or bool(settings.get("deep_segment_setting_policy_enabled", True))):
            completed.add("deep_learning")

        if generation_done:
            completed.update({"preprocess", "audio", "stt1", "lora", "deep_learning"})
            if cut_boundary_enabled:
                completed.add("cut_boundary")
            if stt2_enabled:
                completed.add("stt2")
            if vad_enabled:
                completed.add("vad")
            if subtitle_llm_enabled:
                completed.add("subtitle_llm")
        elif explicit_save_done:
            completed.update({"preprocess", "audio", "stt1", "lora", "deep_learning"})
            if cut_boundary_enabled:
                completed.add("cut_boundary")
            if stt2_enabled:
                completed.add("stt2")
            if vad_enabled:
                completed.add("vad")
            if subtitle_llm_enabled:
                completed.add("subtitle_llm")
        else:
            later_than_cut = {"preprocess", "audio", "stt1", "stt2", "vad", "subtitle_llm", "lora", "deep_learning"}
            later_than_preprocess = {"audio", "stt1", "stt2", "vad", "subtitle_llm", "lora", "deep_learning"}
            later_than_audio = {"stt1", "stt2", "vad", "subtitle_llm", "lora", "deep_learning"}
            later_than_stt = {"vad", "subtitle_llm", "lora", "deep_learning"}
            later_than_vad = {"subtitle_llm", "lora", "deep_learning"}

            if cut_boundary_enabled and stage_now & later_than_cut and not cut_boundary_pending:
                completed.add("cut_boundary")
            if cut_boundary_enabled and cut_boundary_done:
                completed.add("cut_boundary")
            if stage_now & later_than_preprocess:
                completed.add("preprocess")
            if stage_now & later_than_audio:
                completed.add("audio")
            stt_still_active = bool(stage_now & {"stt1", "stt2"})
            if stage_now & later_than_stt and not stt_still_active:
                completed.add("stt1")
                if stt2_enabled:
                    completed.add("stt2")
            if vad_enabled and stage_now & later_than_vad and "vad" not in stage_now:
                completed.add("vad")
            if stage_now & {"deep_learning"}:
                completed.add("lora")
            if stage_now & {"lora", "deep_learning"}:
                completed.update({"preprocess", "audio", "stt1"})
            if roughcut_started:
                completed.update({"preprocess", "audio", "stt1", "lora", "deep_learning"})
                if cut_boundary_enabled:
                    completed.add("cut_boundary")
                if stt2_enabled:
                    completed.add("stt2")
                if vad_enabled:
                    completed.add("vad")
                if subtitle_llm_enabled:
                    completed.add("subtitle_llm")

        editor_count = getattr(editor, "_last_roughcut_draft_major_count", None) if editor is not None else None
        if roughcut_enabled and (roughcut_status == "done" or editor_count is not None):
            completed.add("roughcut_llm")
        if roughcut_enabled and self._roughcut_status_text().startswith("완료"):
            completed.add("roughcut_llm")
        if roughcut_enabled and generation_done:
            completed.add("roughcut_llm")

        if cut_boundary_enabled and cut_boundary_pending and not cut_boundary_done:
            completed.discard("cut_boundary")
        return completed

    def _pipeline_model_link(self, key: str, text: str, *, current: bool = False, completed: bool = False) -> str:
        color = "#00D46A" if completed else ("#FFD60A" if current else "#F5F7FA")
        dropdown_icon = " ▾" if key in {"cut_boundary", "stt1", "stt2", "subtitle_llm", "roughcut_llm"} else ""
        return (
            f"<a href='model:{escape(key)}' "
            f"style='color:{color}; text-decoration:none; font-family:Menlo, Monaco, Consolas, monospace; font-weight:400;'>"
            f"{escape(text)}<span style='color:#8EA4B8; font-weight:400;'>{dropdown_icon}</span></a>"
        )

    def _pipeline_prompt_link(self, key: str) -> str:
        return (
            f"<a href='prompt:{escape(key)}' "
            "style='color:#8EA4B8; text-decoration:none; margin-left:4px; font-size:10px;'>"
            "&#9881;</a>"
        )

    def _pipeline_info_html(self, settings: dict) -> str:
        rows = []
        model_links = {
            "컷 경계": "cut_boundary",
            "STT 1": "stt1",
            "STT 2": "stt2",
            "자막 LLM": "subtitle_llm",
            "러프컷 LLM": "roughcut_llm",
        }
        current_keys = self._pipeline_current_stage_keys(settings)
        completed_keys = self._pipeline_completed_stage_keys(settings, current_keys)
        for idx, (key, stage, model) in enumerate(self._pipeline_rows(settings), 1):
            completed = key in completed_keys
            current = key in current_keys and not completed
            bg_style = " background-color:#12362A;" if current else ""
            num_color = "#00D46A" if completed else ("#FFD60A" if current else "#F5F7FA")
            stage_color = num_color if (completed or current) else "#F5F7FA"
            model_color = num_color if (completed or current) else "#F5F7FA"
            model_html = (
                self._pipeline_model_link(model_links[stage], model, current=current, completed=completed)
                if stage in model_links
                else escape(model)
            )
            if key in {"subtitle_llm", "roughcut_llm"}:
                model_html = f"{model_html}&nbsp;{self._pipeline_prompt_link(key)}"
            rows.append(
                "<tr>"
                f"<td style='color:{num_color}; padding:0 5px 0 0; font-weight:400;{bg_style}'>{idx}</td>"
                f"<td style='color:{stage_color}; padding:0 8px 0 0; font-weight:400;{bg_style}'>{escape(stage)}</td>"
                f"<td style='color:{model_color}; padding:0; font-family:Menlo, Monaco, Consolas, monospace; font-weight:400;{bg_style}'>{model_html}</td>"
                "</tr>"
            )
        return (
            "<table cellspacing='0' cellpadding='0' style='font-size:8px; line-height:100%; margin-top:1px;'>"
            + "".join(rows)
            + "</table>"
        )

    def _pipeline_info_plain(self, settings: dict) -> str:
        return "\n".join(
            f"{idx}. [{stage}] {model}"
            for idx, (_key, stage, model) in enumerate(self._pipeline_rows(settings), 1)
        )

    def _current_engine_info_text(self) -> str:
        settings = self._settings_with_runtime_audio_tune(_runtime_load_settings())
        return self._pipeline_info_html(settings)

    def _refresh_sidebar_engine_info(self, text=None, settings: dict | None = None):
        label = getattr(self, "sidebar_settings_label", None)
        if label is None:
            return
        settings = self._settings_with_runtime_audio_tune(dict(settings or _runtime_load_settings()))
        formatted = self._pipeline_info_html(settings)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        label.setOpenExternalLinks(False)
        try:
            label.linkActivated.disconnect(self._on_sidebar_model_link)
        except Exception:
            pass
        label.linkActivated.connect(self._on_sidebar_model_link)
        label.setText(formatted)
        tooltip = self._pipeline_info_plain(settings)
        runtime_tip = self._runtime_audio_tune_tooltip()
        if runtime_tip:
            tooltip = f"{tooltip}\n{runtime_tip}"
        label.setToolTip(tooltip)
        refresher = getattr(self, "_refresh_sidebar_nav_menu", None)
        if callable(refresher):
            try:
                refresher()
            except Exception:
                pass
        self._sync_sidebar_preset_panel(settings)
        self._sync_subtitle_quality_combos(settings.get("stt_quality_preset"))
        self._refresh_sidebar_runtime_monitor()

    def _runtime_monitor_tooltip(self) -> str:
        snapshot = dict(getattr(self, "_runtime_resource_snapshot", {}) or {})
        if not snapshot:
            return "런타임 모니터 대기 중"
        coordinator = getattr(self, "_runtime_resource_coordinator", None)
        if coordinator is not None and hasattr(coordinator, "status_plain"):
            try:
                return str(coordinator.status_plain(snapshot))
            except Exception:
                pass
        return "런타임 모니터 활성"

    def _refresh_sidebar_runtime_monitor(self):
        label = getattr(self, "sidebar_runtime_label", None)
        if label is None:
            return
        snapshot = dict(getattr(self, "_runtime_resource_snapshot", {}) or {})
        if not snapshot:
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setText(
                "<div style='margin-top:3px; padding-top:3px; border-top:1px solid #22313A;'>"
                "<div style='color:#6E8594; font-size:8px;'>CPU -- · PROC -- · RAM --</div>"
                "</div>"
            )
            label.setToolTip("런타임 모니터 대기 중")
            return
        coordinator = getattr(self, "_runtime_resource_coordinator", None)
        if coordinator is not None and hasattr(coordinator, "status_html"):
            try:
                html = str(coordinator.status_html(snapshot))
            except Exception:
                html = ""
        else:
            html = ""
        if not html:
            html = (
                "<div style='margin-top:3px; padding-top:3px; border-top:1px solid #22313A;'>"
                f"<div style='color:#DCE7F3; font-size:8px;'>CPU {float(snapshot.get('system_cpu_percent', 0.0)):.0f}% · "
                f"PROC {float(snapshot.get('process_cpu_percent', 0.0)):.0f}% · "
                f"RAM {float(snapshot.get('rss_gb', 0.0)):.2f}GB</div>"
                "</div>"
            )
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setText(html)
        label.setToolTip(self._runtime_monitor_tooltip())

    def _settings_with_runtime_audio_tune(self, settings: dict | None) -> dict:
        out = dict(settings or {})
        tune = dict(getattr(self, "_runtime_auto_audio_tune", {}) or {})
        if not tune:
            return out
        if "selected_audio_ai" in tune:
            out["selected_audio_ai"] = tune.get("selected_audio_ai")
            out["_runtime_auto_audio_ai_selected"] = True
        if "selected_vad" in tune:
            out["selected_vad"] = tune.get("selected_vad")
            out["_runtime_auto_vad_selected"] = True
        for key in (
            "vad_pre_split_enabled",
            "vad_post_stt_align_enabled",
            "vad_threshold",
            "ten_vad_threshold",
            "vad_min_speech",
            "vad_min_silence",
            "vad_speech_pad",
        ):
            if key in tune:
                out[key] = tune.get(key)
        return out

    def _runtime_audio_tune_tooltip(self) -> str:
        tune = dict(getattr(self, "_runtime_auto_audio_tune", {}) or {})
        if not tune:
            return ""
        media_path = str(getattr(self, "_runtime_auto_audio_file", "") or "")
        file_name = os.path.basename(media_path) if media_path else "현재 파일"
        decision = dict(getattr(self, "_runtime_auto_audio_decision", {}) or {})
        reason = str(decision.get("audio_tune_reason") or decision.get("reason") or "").strip()
        if reason:
            return f"오토 오디오 적용: {file_name}\n근거: {reason}"
        return f"오토 오디오 적용: {file_name}"

    def _set_runtime_audio_tune_display(self, media_path: str = "", payload=None):
        payload = dict(payload or {}) if isinstance(payload, dict) else {}
        if "tune" in payload or "settings" in payload:
            tune = dict(payload.get("tune") or payload.get("settings") or {})
        else:
            tune = dict(payload or {})
        self._runtime_auto_audio_file = str(media_path or "")
        self._runtime_auto_audio_tune = tune
        self._runtime_auto_audio_decision = dict(payload.get("decision") or {})
        self._refresh_sidebar_engine_info()

    def _apply_ai_settings(self, settings: dict):
        _runtime_save_settings(settings)
        editor = self._active_editor()
        if editor is not None:
            try:
                editor.settings = dict(settings)
                editor.selected_model = settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"))
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
        if "selected_whisper_model_secondary" in updates or "stt_ensemble_enabled" in updates:
            settings["stt_ensemble_user_selected"] = True
        if "selected_model" in updates or "selected_llm_provider" in updates:
            model = str(settings.get("selected_model") or "").strip()
            provider = str(settings.get("selected_llm_provider") or "").strip().lower()
            settings["subtitle_llm_user_selected"] = bool(model and "사용 안함" not in model and provider != "none")
        key = normalize_stt_quality_key(settings.get("stt_quality_preset") or "precise")
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
            self._open_sidebar_prompt_dialog(str(href or "").replace("prompt:", "", 1))
            return
        key = str(href or "").replace("model:", "", 1)
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
            ensemble = bool(settings.get("stt_ensemble_enabled", False))
            current1 = settings.get("selected_whisper_model", "")
            current2 = settings.get("selected_whisper_model_secondary", "")
            if key == "stt2":
                _push_item(
                    "stt2:ensemble",
                    "STT2 앙상블 사용",
                    {"stt_ensemble_enabled": not ensemble, "stt_ensemble_user_selected": True},
                    checked=ensemble,
                    accent="#34C759",
                )
                items.append({"separator": True})
            models = self._stt1_model_items() if key in {"stt", "stt1"} else self._stt2_model_items()
            for idx, model in enumerate(models):
                label = self._short_model_name(model)
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
                    {
                        "selected_whisper_model_secondary": model,
                        "stt_ensemble_enabled": True,
                        "stt_ensemble_user_selected": True,
                    },
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
