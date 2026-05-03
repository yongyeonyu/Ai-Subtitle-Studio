# Version: 03.13.03
# Phase: PHASE2
"""Home sidebar status, preset, and model-selection helpers."""

import os
import re
import sys
from html import escape

from PyQt6.QtCore import Qt, QTimer, QSize, QDateTime
from PyQt6.QtGui import QIcon, QColor, QCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QComboBox, QMessageBox,
    QToolButton, QSizePolicy, QMenu, QGridLayout,
)

from core.runtime import config
from core.settings import load_settings, save_settings
from core.pipeline_status import generation_stage_keys
from core.audio import audio_presets as _audio_presets
from core.audio.preset_auto_classifier import auto_classify_media_presets, apply_auto_classified_presets
from core.audio.stt_quality_presets import (
    apply_stt_quality_preset,
    load_stt_quality_presets,
    normalize_stt_quality_key,
)
from ui.home_sidebar_presets import sync_sidebar_preset_panel
from ui.style import button_style, label_style, line_icon, tool_button_style


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
        items = []
        try:
            for row in range(table.rowCount()):
                status_item = table.item(row, 0)
                file_item = table.item(row, 1)
                eta_item = table.item(row, 4)
                status = self._plain_queue_status(str(status_item.text() if status_item else "-"))
                display_status = "완료" if "완료" in status else status
                items.append({
                    "order": str(row + 1),
                    "status": status,
                    "statusDisplay": display_status,
                    "done": "완료" in status,
                    "file": str(file_item.text() if file_item else "-"),
                    "eta": str(eta_item.text() if eta_item else "-"),
                })
        except RuntimeError:
            return list(getattr(self, "_sidebar_queue_cache_items", []) or [])
        if not items:
            cached = list(getattr(self, "_sidebar_queue_cache_items", []) or [])
            if cached:
                return cached
        return items

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
        panel = getattr(self, "sidebar_preset_panel", None)
        if panel is not None:
            try:
                if panel.parent() is None:
                    panel.setParent(self.home_page)
                self._sync_sidebar_preset_panel()
                return panel
            except RuntimeError:
                pass
            self.sidebar_preset_panel = None

        panel = QWidget(self.home_page)
        panel.setObjectName("SidebarPresetPanel")
        panel.setStyleSheet("QWidget#SidebarPresetPanel { background:#151C20; border:1px solid #2D3942; border-radius:7px; }")

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(0)

        grid_wrap = QWidget(panel)
        grid_wrap.setStyleSheet("background:transparent; border:none;")
        grid = QGridLayout(grid_wrap)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)

        self.sidebar_stt_quality_combo = SidebarComboBox(panel)
        for key, preset in load_stt_quality_presets().items():
            label = str(preset.get("label") or key)
            self.sidebar_stt_quality_combo.addItem(label, key)
            desc = str(preset.get("description") or "")
            if desc:
                self.sidebar_stt_quality_combo.setItemData(self.sidebar_stt_quality_combo.count() - 1, desc, Qt.ItemDataRole.ToolTipRole)
        self.sidebar_stt_quality_combo.setStyleSheet(self._sidebar_preset_combo_style())
        self.sidebar_stt_quality_combo.setFixedWidth(88)
        self.sidebar_stt_quality_combo.setFixedHeight(18)
        self.sidebar_stt_quality_combo.currentIndexChanged.connect(self._on_sidebar_stt_quality_changed)
        stt_row = self._sidebar_preset_row("정밀인식", self.sidebar_stt_quality_combo)
        grid.addWidget(stt_row, 0, 0)

        self.sidebar_audio_preset_combo = SidebarComboBox(panel)
        self.sidebar_audio_preset_combo.addItem("직접 설정", "")
        self.sidebar_audio_preset_combo.addItem("기본값 적용", "__default__")
        curated_audio_presets = _audio_presets.curated_audio_preset_names()
        loaded_audio_presets = _audio_presets.load_audio_presets()
        for name in curated_audio_presets:
            preset = loaded_audio_presets.get(name)
            if not isinstance(preset, dict):
                continue
            desc = str(preset.get("description") or "")
            self.sidebar_audio_preset_combo.addItem(name, name)
            if desc:
                self.sidebar_audio_preset_combo.setItemData(self.sidebar_audio_preset_combo.count() - 1, desc, Qt.ItemDataRole.ToolTipRole)
        self.sidebar_audio_preset_combo.setStyleSheet(self._sidebar_preset_combo_style())
        self.sidebar_audio_preset_combo.setFixedWidth(88)
        self.sidebar_audio_preset_combo.setFixedHeight(18)
        self.sidebar_audio_preset_combo.currentIndexChanged.connect(self._on_sidebar_audio_preset_changed)
        audio_row = self._sidebar_preset_row("오디오", self.sidebar_audio_preset_combo)
        grid.addWidget(audio_row, 1, 0)

        self.sidebar_auto_preset_btn = QToolButton(panel)
        self.sidebar_auto_preset_btn.setText("")
        self.sidebar_auto_preset_btn.setAutoRaise(False)
        self.sidebar_auto_preset_btn.setIcon(self._nav_icon("auto", "#A9B0B7"))
        self.sidebar_auto_preset_btn.setIconSize(QSize(15, 15))
        self.sidebar_auto_preset_btn.setFixedSize(34, 34)
        self.sidebar_auto_preset_btn.setStyleSheet(
            "QToolButton { background:#202A31; border:1px solid #2D3942; border-radius:7px; padding:0; margin:0; } "
            "QToolButton:hover { background:#2A363F; border-color:#465663; }"
        )
        self.sidebar_auto_preset_btn.clicked.connect(self._on_sidebar_auto_preset_detect)
        self.sidebar_auto_preset_btn.setToolTip("영상 기준 자동 판정")
        grid.addWidget(self.sidebar_auto_preset_btn, 0, 1, 2, 1, alignment=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)
        grid.setColumnStretch(0, 0)
        grid.setColumnMinimumWidth(1, 34)
        lay.addWidget(grid_wrap)

        panel.setMaximumHeight(60)

        self.sidebar_preset_panel = panel
        self._sync_sidebar_preset_panel()
        return panel
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

    def _on_sidebar_stt_quality_changed(self, *args):
        combo = getattr(self, "sidebar_stt_quality_combo", None)
        if combo is None:
            return
        self._apply_sidebar_settings_update(
            preset_applier=lambda settings: apply_stt_quality_preset(
                settings,
                combo.currentData() or "balanced",
            )
        )

    def _on_sidebar_audio_preset_changed(self, *args):
        combo = getattr(self, "sidebar_audio_preset_combo", None)
        if combo is None:
            return
        preset_name = combo.currentData() or ""
        if preset_name == "__default__":
            default_applier = getattr(_audio_presets, "apply_default_audio_preset", None)
            if callable(default_applier):
                self._apply_sidebar_settings_update(preset_applier=default_applier)
            else:
                self._apply_sidebar_settings_update({"audio_preset": ""})
        elif preset_name:
            self._apply_sidebar_settings_update(
                preset_applier=lambda settings: _audio_presets.apply_audio_preset(settings, preset_name)
            )
        else:
            self._apply_sidebar_settings_update({"audio_preset": ""})

    def _on_sidebar_auto_preset_detect(self, *args):
        media_path = self._current_editor_media_path()
        if not media_path:
            QMessageBox.information(self, "자동 판정", "현재 에디터에 열린 영상이 없어서 자동 판정을 진행할 수 없습니다.")
            return
        settings = dict(_runtime_load_settings())
        try:
            decision = auto_classify_media_presets(media_path, settings=settings)
            updated = apply_auto_classified_presets(settings, decision)
            self._apply_ai_settings(updated)
            self._sync_sidebar_preset_panel(updated)
            QMessageBox.information(
                self,
                "자동 판정 완료",
                (
                    f"오디오: {decision['audio_preset']}\n"
                    f"정밀인식: {decision['stt_quality_preset']}\n"
                    f"신뢰도: {int(round(float(decision.get('confidence', 0.0)) * 100))}%\n\n"
                    f"{decision.get('reason', '')}"
                ),
            )
        except Exception as e:
            QMessageBox.warning(self, "자동 판정 실패", str(e))

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
        from core.runtime.config import APP_VERSION
        label.setText(
            f"<span style='color:{dot_color}; font-size:13px;'>●</span> "
            f"<span style='color:#FFFFFF; font-size:14px; font-weight:700;'>AI Subtitle Studio</span> "
            f"<span style='color:#D1D1D6; font-size:11px; font-weight:600;'>v{APP_VERSION}</span>"
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
        if not bool(settings.get("roughcut_llm_enabled", False)):
            return "미사용", "러프컷 규칙 기반"
        model = str(settings.get("roughcut_llm_model", "") or "").strip()
        if not model or model.lower() == "inherit" or "사용 안함" in model:
            return "미사용", "러프컷 규칙 기반"
        return self._short_model_name(model), "러프컷 전용"

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
            "off": "사용안함",
            "low": "낮음",
            "medium": "중간",
        }.get(str(level or "medium"), "중간")

    def _pipeline_rows(self, settings: dict) -> list[tuple[str, str, str]]:
        subtitle_llm = str(settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "기본")) or "기본")
        vad_model, _vad_role = getattr(self, "_vad_model_name", lambda s: ("기본", ""))(settings)
        roughcut_llm, _roughcut_role = getattr(self, "_roughcut_llm_name", lambda s, l: ("기본", ""))(settings, subtitle_llm)
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
            ("subtitle_llm", "자막 LLM", getattr(self, "_short_model_name", lambda s: s)(subtitle_llm)),
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

        return generation_stage_keys(
            self._pipeline_status_blob(),
            stt_ensemble_enabled=bool(settings.get("stt_ensemble_enabled", False)),
        )

    def _pipeline_completed_stage_keys(self, settings: dict, current_keys: set[str]) -> set[str]:
        completed: set[str] = set()
        blob = self._pipeline_status_blob()
        editor = self._active_editor()
        generation_running = self._is_subtitle_generation_running()
        state_value = str(getattr(getattr(editor, "sm", None), "state", "") or "") if editor is not None else ""
        queue_done = "100% 완료" in blob
        try:
            table = getattr(self, "queue_table", None)
            if table is not None and table.rowCount() > 0:
                done_rows = 0
                for row in range(table.rowCount()):
                    item = table.item(row, 0)
                    text = str(item.text() if item is not None else "")
                    if "완료" in text or "기존자막" in text:
                        done_rows += 1
                queue_done = queue_done or done_rows >= table.rowCount()
        except RuntimeError:
            pass
        generation_done = (
            not generation_running
            and (
                "자막 생성 완료" in blob
                or queue_done
                or state_value in {"ST_COMP", "ST_SAVED"}
                or bool(getattr(editor, "_subtitle_generation_completed", False))
            )
        )
        cut_scan_active = bool(getattr(editor, "_auto_cut_boundary_scan_active", False)) if editor is not None else False
        provisional_cut_lines = list(getattr(editor, "_auto_cut_boundary_scan_lines", []) or []) if editor is not None else []
        cut_boundary_pending = cut_scan_active or any(
            str((row or {}).get("status", "") if isinstance(row, dict) else "provisional").lower() != "verified"
            for row in provisional_cut_lines
        )
        stage_now = set(current_keys or set())
        vad_enabled = settings.get("selected_vad", "none") != "none"
        stt2_enabled = bool(settings.get("stt_ensemble_enabled", False))

        if generation_done:
            completed.update({"cut_boundary", "preprocess", "audio", "stt1", "subtitle_llm"})
            if stt2_enabled:
                completed.add("stt2")
            if vad_enabled:
                completed.add("vad")
        else:
            later_than_cut = {"preprocess", "audio", "stt1", "stt2", "vad", "subtitle_llm"}
            later_than_preprocess = {"audio", "stt1", "stt2", "vad", "subtitle_llm"}
            later_than_audio = {"stt1", "stt2", "vad", "subtitle_llm"}
            later_than_stt = {"vad", "subtitle_llm"}
            later_than_vad = {"subtitle_llm"}

            if stage_now & later_than_cut and not cut_boundary_pending:
                completed.add("cut_boundary")
            if stage_now & later_than_preprocess:
                completed.add("preprocess")
            if stage_now & later_than_audio:
                completed.add("audio")
            if stage_now & later_than_stt:
                completed.add("stt1")
                if stt2_enabled:
                    completed.add("stt2")
            if vad_enabled and stage_now & later_than_vad:
                completed.add("vad")

        roughcut_status = self._roughcut_draft_status_value()
        editor_count = getattr(editor, "_last_roughcut_draft_major_count", None) if editor is not None else None
        if roughcut_status == "done" or editor_count is not None:
            completed.add("roughcut_llm")
        if self._roughcut_status_text().startswith("완료"):
            completed.add("roughcut_llm")
        if generation_done:
            completed.add("roughcut_llm")

        if cut_boundary_pending:
            completed.discard("cut_boundary")

        if not stt2_enabled:
            completed.discard("stt2")
        if not vad_enabled:
            completed.discard("vad")
        return completed

    def _pipeline_model_link(self, key: str, text: str, *, current: bool = False, completed: bool = False) -> str:
        color = "#00D46A" if completed else ("#FFD60A" if current else "#F5F7FA")
        dropdown_icon = " ▾" if key in {"cut_boundary", "audio", "stt1", "stt2", "vad", "subtitle_llm", "roughcut_llm"} else ""
        return (
            f"<a href='model:{escape(key)}' "
            f"style='color:{color}; text-decoration:none; font-family:Menlo, Monaco, Consolas, monospace; font-weight:400;'>"
            f"{escape(text)}<span style='color:#8EA4B8; font-weight:400;'>{dropdown_icon}</span></a>"
        )

    def _pipeline_info_html(self, settings: dict) -> str:
        rows = []
        model_links = {
            "컷 경계": "cut_boundary",
            "음성": "audio",
            "STT 1": "stt1",
            "STT 2": "stt2",
            "VAD": "vad",
            "자막 LLM": "subtitle_llm",
            "러프컷 LLM": "roughcut_llm",
        }
        current_keys = self._pipeline_current_stage_keys(settings)
        completed_keys = self._pipeline_completed_stage_keys(settings, current_keys)
        for idx, (key, stage, model) in enumerate(self._pipeline_rows(settings), 1):
            current = key in current_keys
            completed = key in completed_keys
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
            "<table cellspacing='0' cellpadding='0' style='font-size:9px;'>"
            "<tr>"
            "<td></td>"
            "<td style='color:#00D46A; padding:0 10px 2px 0; font-weight:400;'>단계</td>"
            "<td style='color:#00D46A; padding:0 0 2px 0; font-family:Menlo, Monaco, Consolas, monospace; font-weight:400;'>모델</td>"
            "</tr>"
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
        self._apply_sidebar_settings_update(updates)

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
                ("사용안함", "off"),
                ("낮음", "low"),
                ("중간", "medium"),
            ]

            labels = {
                "off": "사용안함",
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
