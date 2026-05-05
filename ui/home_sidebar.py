# Version: 03.14.26
# Phase: PHASE2
"""Home sidebar status, preset, and model-selection helpers."""

import os
import re
import sys
from html import escape

from PyQt6.QtCore import Qt, QTimer, QSize, QDateTime
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSizePolicy, QMenu,
)

from core.runtime import config
from core.settings import load_settings, save_settings
from core.path_manager import load_settings as _path_load_settings, save_settings as _path_save_settings
from core.pipeline_status import generation_stage_keys, generation_stage_keys_all
from core.audio.stt_quality_presets import (
    STT_QUALITY_PRESET_ORDER,
    apply_stt_quality_preset,
    load_stt_quality_presets,
    normalize_stt_quality_key,
    save_stt_quality_user_preset,
    stt_quality_label,
)
from ui.home_sidebar_presets import sync_sidebar_preset_panel
from ui.style import line_icon


ROUGHCUT_LLM_MIN_PARAMETERS_B = 7.0
ROUGHCUT_LLM_MIN_SIZE_BYTES = 3_500_000_000
ROUGHCUT_CAPABLE_CLOUD_TOKENS = (
    "gemini 2.5 pro",
    "gpt-5.2",
    "gpt-5.5",
)
ROUGHCUT_BLOCKED_CLOUD_TOKENS = (
    "flash",
    "nano",
    "mini",
)
ROUGHCUT_CAPABLE_LOCAL_LATEST = (
    "exaone3.5:latest",
    "gemma2:latest",
    "llama3:latest",
    "llama3.1:latest",
    "mistral:latest",
    "qwen2.5:latest",
)


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
        label = getattr(self, "queue_header_lbl", None)
        raw = ""
        if label is not None:
            try:
                raw = str(label.text() or "")
            except RuntimeError:
                raw = ""
        if not raw:
            raw = str(getattr(self, "_sidebar_queue_cache_header", "") or "")
        if raw:
            raw = raw.replace("📋 처리할 파일 리스트", "큐 리스트").replace("진행 중", "").strip()
            raw = raw.replace("  ", " ")
            return raw
        total = int(getattr(self, "_total_files", 0) or 0)
        current = int(getattr(self, "_current_file_idx", 0) or 0)
        pct = int(getattr(self, "_real_pct", 0) or 0)
        return f"큐 리스트 : ({current}/{total}) - {pct}% 완료"

    def _sidebar_queue_items(self) -> list[dict]:
        table = getattr(self, "queue_table", None)
        if table is None:
            return list(getattr(self, "_sidebar_queue_cache_items", []) or [])
        try:
            if table.rowCount() == 0:
                return []
        except RuntimeError:
            return list(getattr(self, "_sidebar_queue_cache_items", []) or [])
        items = []
        try:
            active_row = int(getattr(self, "_current_file_idx", 1) or 1) - 1
        except Exception:
            active_row = 0
        try:
            for row in range(table.rowCount()):
                status_item = table.item(row, 0)
                file_item = table.item(row, 1)
                duration_item = table.item(row, 3)
                eta_item = table.item(row, 4)
                raw_status = str(status_item.text() if status_item else "-")
                status = self._plain_queue_status(raw_status)
                flagger = getattr(self, "_queue_status_flags", None)
                if callable(flagger):
                    done, error, status_active = flagger(raw_status)
                else:
                    stripped = raw_status.strip()
                    stage_done_only = "컷 경계" in stripped and "완료" in stripped
                    done = (
                        not stage_done_only
                        and "미완료" not in stripped
                        and (
                            stripped in {"완료", "✅기존자막", "기존자막"}
                            or stripped.startswith("✅")
                            and "완료" in stripped
                            or "기존자막" in stripped
                        )
                    )
                    error = any(token in status for token in ("오류", "실패", "중단"))
                    status_active = not done and not error and not any(token in status for token in ("대기", "-"))
                active = status_active and row == active_row
                display_status = "완료" if done else status
                items.append({
                    "order": str(row + 1),
                    "status": status,
                    "statusDisplay": display_status,
                    "done": done,
                    "active": active,
                    "error": error,
                    "file": str(file_item.text() if file_item else "-"),
                    "eta": self._queue_sidebar_time_text(
                        str(eta_item.text() if eta_item else "-"),
                        str(duration_item.text() if duration_item else "-"),
                    ),
                })
        except RuntimeError:
            return list(getattr(self, "_sidebar_queue_cache_items", []) or [])
        return items

    def _queue_sidebar_time_text(self, eta_text: str, duration_text: str) -> str:
        formatter = getattr(self, "_queue_card_time_text", None)
        if callable(formatter):
            return formatter(eta_text, duration_text)
        eta = str(eta_text or "-").strip() or "-"
        if eta in {"?", "계산 중", "분석 중..", "예상불가"}:
            eta = "-"
        if "/" in eta:
            left, right = [part.strip() for part in eta.split("/", 1)]
            left = left or "00:00"
            right = "-" if right in {"", "?", "계산 중", "분석 중..", "예상불가"} else right
            return f"{left} / {right}"
        if eta == "-":
            return "-"
        return f"00:00 / {eta}"

    def _plain_queue_status(self, status: str) -> str:
        text = str(status or "").strip()
        text = re.sub(r"^[^\w가-힣\[]+\s*", "", text)
        text = re.sub(r"[\u2600-\u27BF\U0001F300-\U0001FAFF]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text or "-"

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
        return "precise"

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
        if width > 0:
            combo.setFixedWidth(width)
        else:
            combo.setMinimumWidth(60)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.setCursor(Qt.CursorShape.PointingHandCursor)
        combo.setStyleSheet(self._sidebar_subtitle_quality_combo_style())
        combo.setToolTip("자막품질 프리셋")
        combo.currentIndexChanged.connect(self._on_subtitle_quality_combo_changed)
        self._register_subtitle_quality_combo(combo)
        self._sync_subtitle_quality_combos_for_scope(scope)
        return combo

    def _apply_subtitle_quality_preset(self, preset_key: str | None, *, announce: bool = False):
        key = normalize_stt_quality_key(preset_key)
        settings = apply_stt_quality_preset(_runtime_load_settings(), key)
        self._apply_ai_settings(settings)
        self._sync_subtitle_quality_combos_for_scope("workspace", key)
        if announce:
            try:
                from core.runtime.logger import get_logger

                get_logger().log(f"💾 자막품질 저장: {stt_quality_label(key)}")
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

            get_logger().log(f"💾 자막품질 프리셋 저장: {stt_quality_label(key)}")
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

        label = QLabel("자막품질", row)
        label.setFixedWidth(54)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        label.setStyleSheet("color:#00D46A; font-size:10px; font-weight:800; background:transparent; border:none;")
        layout.addWidget(label)

        combo = self._make_subtitle_quality_combo(row, width=0, height=22, scope="workspace")
        self.sidebar_subtitle_quality_combo = combo
        layout.addWidget(combo, stretch=1)

        save_btn = QPushButton("저장", row)
        save_btn.setIcon(line_icon("save", "#F5F7FA", 16))
        save_btn.setIconSize(QSize(9, 9))
        save_btn.setFixedSize(44, 22)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setToolTip("현재 자막품질 설정 저장")
        save_btn.setStyleSheet(
            "QPushButton { background:#24313A; color:#F5F7FA; border:1px solid #344652; "
            "border-radius:4px; padding:0 4px; font-size:9px; font-weight:800; } "
            "QPushButton:hover { background:#2D3D47; border-color:#3F8CFF; } "
            "QPushButton:pressed { background:#1A84FF; color:#FFFFFF; }"
        )
        save_btn.clicked.connect(self._on_sidebar_subtitle_quality_save)
        self.sidebar_subtitle_quality_save_btn = save_btn
        layout.addWidget(save_btn)
        layout.addStretch(1)
        return row

    def _settings_for_subtitle_quality_scope(self, scope: str | None) -> dict:
        key = self._subtitle_quality_key_for_scope(scope)
        settings = apply_stt_quality_preset(_runtime_load_settings(), key)
        settings["stt_quality_preset"] = key
        return settings

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

    def _sync_saved_status_blink_timer(self, active: bool):
        self._ensure_saved_status_blink_timer()
        timer = self._saved_status_blink_timer
        if active:
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
        self._sync_saved_status_blink_timer(generating)
        if generating:
            dot_color = "#FF453A" if bool(getattr(self, "_saved_status_blink_on", True)) else "#5A1F24"
            tooltip = "자막 생성 중입니다."
        else:
            dot_color = "#FF453A" if dirty else "#34C759"
            tooltip = "저장되지 않은 변경사항이 있습니다." if dirty else "저장된 상태입니다."
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(False)
        label.setMinimumHeight(22)
        from core.runtime.config import APP_VERSION
        label.setText(
            f"<span style='color:{dot_color}; font-size:12px;'>●</span> "
            f"<span style='color:#FFFFFF; font-size:13px; font-weight:700;'>AI Subtitle Studio</span> "
            f"<span style='color:#D1D1D6; font-size:10px; font-weight:600;'>v{APP_VERSION}</span>"
        )
        label.setToolTip(tooltip)

    def _format_engine_info_text(self, text: str) -> str:
        lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        return "\n".join(lines)

    def _short_model_name(self, model: str) -> str:
        text = str(model or "").strip()
        if not text:
            return "미사용"
        if "사용 안함" in text:
            return "미사용"
        for prefix in ("mlx-community/", "Systran/", "youngouk/", "ghost613/", "o0dimplz0o/"):
            text = text.replace(prefix, "")
        text = text.replace("-mlx", "")
        return text

    def _audio_model_name(self, settings: dict) -> str:
        return {
            "deepfilter": "DeepFilter",
            "rnnoise": "RNNoise",
            "resemble_enhance": "Resemble",
            "clearvoice": "ClearVoice",
            "none": "미사용",
        }.get(settings.get("selected_audio_ai", "none"), "미사용")

    def _vad_model_name(self, settings: dict) -> tuple[str, str]:
        vad_model = {
            "silero": "Silero",
            "ten_vad": "TEN VAD",
            "webrtc": "WebRTC",
            "pyannote": "Pyannote",
            "none": "미사용",
        }.get(settings.get("selected_vad", "none"), "미사용")
        if vad_model == "미사용":
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
            "low": "낮음",
            "medium": "중간",
        }.get(str(level or "medium"), "중간")

    def _pipeline_rows(self, settings: dict) -> list[tuple[str, str, str]]:
        subtitle_llm = str(settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "기본")) or "기본")
        subtitle_llm_label = "미사용" if not self._subtitle_llm_enabled(settings) else getattr(self, "_short_model_name", lambda s: s)(subtitle_llm)
        vad_model, _vad_role = getattr(self, "_vad_model_name", lambda s: ("기본", ""))(settings)
        roughcut_llm, _roughcut_role = getattr(
            self,
            "_roughcut_llm_name",
            lambda settings_arg, subtitle_arg: ("기본", ""),
        )(settings, subtitle_llm)
        stt1_model = getattr(self, "_short_model_name", lambda s: s)(settings.get("selected_whisper_model", getattr(config, "WHISPER_MODEL", "기본")))
        stt2_model = "미사용"
        if settings.get("stt_ensemble_enabled"):
            stt2_model = getattr(self, "_short_model_name", lambda s: s)(settings.get("selected_whisper_model_secondary", ""))

        cut_label = self._cut_boundary_sidebar_label(settings)

        return [
            ("cut_boundary", "컷 경계", cut_label),
            ("preprocess", "전처리", "FFMPEG"),
            ("audio", "음성", getattr(self, "_audio_model_name", lambda s: "기본")(settings)),
            ("stt1", "STT 1", stt1_model),
            ("stt2", "STT 2", stt2_model),
            ("vad", "VAD", vad_model),
            ("subtitle_llm", "자막 LLM", subtitle_llm_label),
            ("roughcut_llm", "러프컷 LLM", roughcut_llm),
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
            for attr in ("engine_lbl", "status_label", "status_lbl"):
                label = getattr(editor, attr, None)
                if label is None:
                    continue
                try:
                    if hasattr(label, "text"):
                        parts.append(str(label.text() or ""))
                except RuntimeError:
                    pass
        table = getattr(self, "queue_table", None)
        if table is not None:
            try:
                if table.rowCount() > 0:
                    for col in (0, 2, 4):
                        item = table.item(0, col)
                        if item is not None:
                            parts.append(str(item.text() or ""))
            except RuntimeError:
                pass
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

    def _cut_boundary_scan_completed(self, editor, blob: str) -> bool:
        if (
            "컷 경계 완료" in blob
            or "컷 경계 자동 분석 완료" in blob
            or "STT 시작 전 자동 분석 완료" in blob
            or "캐시 재사용" in blob and "[컷 경계]" in blob
        ):
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
        try:
            table = getattr(self, "queue_table", None)
            if table is not None and table.rowCount() > 0:
                done_rows = 0
                for row in range(table.rowCount()):
                    item = table.item(row, 0)
                    raw_text = str(item.text() if item is not None else "")
                    flagger = getattr(self, "_queue_status_flags", None)
                    if callable(flagger):
                        row_done = bool(flagger(raw_text)[0])
                    else:
                        stripped = raw_text.strip()
                        stage_done_only = "컷 경계" in stripped and "완료" in stripped
                        row_done = (
                            not stage_done_only
                            and "미완료" not in stripped
                            and (
                                stripped in {"완료", "✅기존자막", "기존자막"}
                                or stripped.startswith("✅")
                                and "완료" in stripped
                                or "기존자막" in stripped
                            )
                        )
                    if row_done:
                        done_rows += 1
                queue_done = queue_done or done_rows >= table.rowCount()
        except RuntimeError:
            pass
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
        cut_boundary_pending = self._cut_boundary_scan_pending(editor)
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

        if generation_done:
            completed.update({"preprocess", "audio", "stt1"})
            if cut_boundary_enabled:
                completed.add("cut_boundary")
            if stt2_enabled:
                completed.add("stt2")
            if vad_enabled:
                completed.add("vad")
            if subtitle_llm_enabled:
                completed.add("subtitle_llm")
        elif explicit_save_done:
            completed.update({"preprocess", "audio", "stt1"})
            if cut_boundary_enabled:
                completed.add("cut_boundary")
            if stt2_enabled:
                completed.add("stt2")
            if vad_enabled:
                completed.add("vad")
            if subtitle_llm_enabled:
                completed.add("subtitle_llm")
        else:
            later_than_cut = {"preprocess", "audio", "stt1", "stt2", "vad", "subtitle_llm"}
            later_than_preprocess = {"audio", "stt1", "stt2", "vad", "subtitle_llm"}
            later_than_audio = {"stt1", "stt2", "vad", "subtitle_llm"}
            later_than_stt = {"vad", "subtitle_llm"}
            later_than_vad = {"subtitle_llm"}

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
            if roughcut_started:
                completed.update({"preprocess", "audio", "stt1"})
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
            rows.append(
                "<tr>"
                f"<td style='color:{num_color}; padding:1px 6px 1px 0; font-weight:400;{bg_style}'>{idx}</td>"
                f"<td style='color:{stage_color}; padding:1px 10px 1px 0; font-weight:400;{bg_style}'>{escape(stage)}</td>"
                f"<td style='color:{model_color}; padding:1px 0; font-family:Menlo, Monaco, Consolas, monospace; font-weight:400;{bg_style}'>{model_html}</td>"
                "</tr>"
            )
        return (
            "<table cellspacing='0' cellpadding='0' style='font-size:8px; margin-top:3px;'>"
            + "".join(rows)
            + "</table>"
        )

    def _pipeline_info_plain(self, settings: dict) -> str:
        return "\n".join(
            f"{idx}. [{stage}] {model}"
            for idx, (_key, stage, model) in enumerate(self._pipeline_rows(settings), 1)
        )

    def _current_engine_info_text(self) -> str:
        settings = _runtime_load_settings()
        return self._pipeline_info_html(settings)

    def _refresh_sidebar_engine_info(self, text=None, settings: dict | None = None):
        label = getattr(self, "sidebar_settings_label", None)
        if label is None:
            return
        settings = dict(settings or _runtime_load_settings())
        formatted = self._pipeline_info_html(settings)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        label.setOpenExternalLinks(False)
        try:
            label.linkActivated.disconnect()
        except Exception:
            pass
        label.linkActivated.connect(self._on_sidebar_model_link)
        label.setText(formatted)
        label.setToolTip(self._pipeline_info_plain(settings))
        self._sync_sidebar_preset_panel(settings)
        self._sync_subtitle_quality_combos(settings.get("stt_quality_preset"))

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
        return models

    def _stt1_model_items(self) -> list[str]:
        blocked = ("ghost613", "zeroth")
        return [
            model for model in self._whisper_model_items()
            if not any(token in str(model).lower() for token in blocked)
        ]

    def _stt2_model_items(self) -> list[str]:
        picked = []
        for model in self._whisper_model_items():
            model_l = str(model).lower()
            if "ghost613" not in model_l and "zeroth" not in model_l:
                continue
            if model not in picked:
                picked.append(model)
        return picked

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
        details = item.get("details", {}) or {}
        parts = [
            str(item.get("name") or ""),
            str(item.get("display_name") or ""),
            str(details.get("parameter_size") or ""),
            str(details.get("family") or ""),
        ]
        for text in parts:
            for match in re.finditer(r"(?<!\d)(\d+(?:\.\d+)?)\s*b\b", text.lower()):
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        return None

    def _roughcut_llm_is_capable(self, item: dict) -> bool:
        details = item.get("details", {}) or {}
        provider = str(details.get("provider") or "ollama").lower()
        name = str(item.get("name") or "")
        display_name = str(item.get("display_name") or name)
        label_l = f"{name} {display_name}".lower()
        if provider == "none" or "사용 안함" in label_l:
            return False

        if provider in {"google", "openai"}:
            if any(re.search(rf"\b{re.escape(token)}\b", label_l) for token in ROUGHCUT_BLOCKED_CLOUD_TOKENS):
                return False
            return any(token in label_l for token in ROUGHCUT_CAPABLE_CLOUD_TOKENS) or "gpt-5" in label_l

        params_b = self._roughcut_llm_parameter_b(item)
        if params_b is not None:
            return params_b >= ROUGHCUT_LLM_MIN_PARAMETERS_B

        if any(token in label_l for token in ROUGHCUT_CAPABLE_LOCAL_LATEST):
            return True

        try:
            return int(item.get("size") or 0) >= ROUGHCUT_LLM_MIN_SIZE_BYTES
        except (TypeError, ValueError):
            return False

    def _roughcut_llm_items(self) -> list[dict]:
        return [item for item in self._llm_model_items() if self._roughcut_llm_is_capable(item)]

    def _apply_sidebar_model_selection(self, updates: dict):
        settings = dict(_runtime_load_settings())
        if updates:
            settings.update(updates)
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
        key = str(href or "").replace("model:", "", 1)
        settings = _runtime_load_settings()
        menu = QMenu(getattr(self, "home_page", None))

        if key == "cut_boundary":
            try:
                from core.cut_boundary import cut_boundary_level
                current = cut_boundary_level(settings)
            except Exception:
                current = "medium" if bool(settings.get("cut_boundary_detection_enabled", settings.get("scan_cut_enabled", True))) else "off"

            choices = [
                ("미사용", "off"),
                ("낮음", "low"),
                ("중간", "medium"),
            ]

            labels = {
                "off": "미사용",
                "low": "낮음 - 3초 간격",
                "medium": "중간 - 2초 간격",
            }
            masks = {
                "off": "off",
                "low": "cross4",
                "medium": "cross5",
            }

            def _cut_boundary_updates(level: str) -> dict:
                level = str(level or "medium")
                if level == "high":
                    level = "medium"
                enabled = level != "off"
                return {
                    "scan_cut_boundary_level": level,
                    "cut_boundary_level": level,
                    "scan_cut_level": level,

                    # 기존 boolean 설정과 호환
                    "cut_boundary_detection_enabled": enabled,
                    "scan_cut_enabled": enabled,
                    "scan_cut_auto_enabled": enabled,
                    "cut_boundary_enabled": enabled,

                    # detector profile 보조 저장
                    "scan_cut_boundary_label": labels.get(level, labels["medium"]),
                    "scan_cut_grid_mask": masks.get(level, "cross5"),
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
                self._add_action(
                    menu,
                    label,
                    lambda _=False, v=value: self._apply_sidebar_model_selection(_cut_boundary_updates(v)),
                    checked=value == current,
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
                self._add_action(
                    menu,
                    label,
                    lambda _=False, v=value: self._apply_sidebar_model_selection({"selected_audio_ai": v}),
                    checked=value == current,
                )

        elif key == "vad":
            choices = [("Silero", "silero"), ("TEN VAD", "ten_vad"), ("미사용", "none")]
            current = settings.get("selected_vad", "silero")
            for label, value in choices:
                self._add_action(
                    menu,
                    label,
                    lambda _=False, v=value: self._apply_sidebar_model_selection({"selected_vad": v}),
                    checked=value == current,
                )

        elif key in {"stt", "stt1", "stt2"}:
            ensemble = bool(settings.get("stt_ensemble_enabled", False))
            current1 = settings.get("selected_whisper_model", "")
            current2 = settings.get("selected_whisper_model_secondary", "")
            if key == "stt2":
                self._add_action(
                    menu,
                    "STT2 앙상블 사용",
                    lambda checked=False: self._apply_sidebar_model_selection({"stt_ensemble_enabled": bool(checked)}),
                    checked=ensemble,
                )
                menu.addSeparator()
            models = self._stt1_model_items() if key in {"stt", "stt1"} else self._stt2_model_items()
            for model in models:
                label = self._short_model_name(model)
                if key in {"stt", "stt1"}:
                    self._add_action(
                        menu,
                        label,
                        lambda _=False, m=model: self._apply_sidebar_model_selection({"selected_whisper_model": m}),
                        checked=model == current1,
                    )
                    continue
                self._add_action(
                    menu,
                    label,
                    lambda _=False, m=model: self._apply_sidebar_model_selection({"selected_whisper_model_secondary": m, "stt_ensemble_enabled": True}),
                    checked=model == current2,
                )

        elif key in {"subtitle_llm", "roughcut_llm"}:
            if key == "roughcut_llm":
                self._add_action(
                    menu,
                    "사용 안함",
                    lambda _=False: self._apply_sidebar_model_selection({
                        "roughcut_llm_enabled": False,
                        "roughcut_llm_use_override": True,
                        "roughcut_llm_provider": "none",
                        "roughcut_llm_model": "사용 안함",
                    }),
                    checked=not bool(settings.get("roughcut_llm_enabled", False)),
                )
                menu.addSeparator()

            current = settings.get("selected_model", "") if key == "subtitle_llm" else settings.get("roughcut_llm_model", "")
            model_items = self._roughcut_llm_items() if key == "roughcut_llm" else self._llm_model_items()
            for item in model_items:
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
                self._add_action(
                    menu,
                    label,
                    lambda _=False, u=updates: self._apply_sidebar_model_selection(u),
                    checked=name == current,
                )

        if menu.actions():
            menu.exec(QCursor.pos())
