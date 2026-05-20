# Version: 03.10.02
# Phase: PHASE2

import os
import re
import time

from PyQt6.QtWidgets import QTextEdit
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QMimeData, QRect, QUrl, QTimer
from PyQt6.QtGui import (
    QTextCursor, QTextCharFormat, QColor, QFont,
    QSyntaxHighlighter, QTextDocument, QKeyEvent, QTextBlockUserData
)
from core.runtime import config
from core.runtime.logger import get_logger
from ui.editor.ux.timestamp_area import TimestampArea
from ui.gpu_rendering import gpu_backend_name, make_accelerated_viewport, scenegraph_enabled
from ui.style import COLORS


def _is_deleted_qt_runtime_error(exc: BaseException) -> bool:
    text = str(exc or "")
    return "wrapped C/C++ object" in text and "has been deleted" in text


def _log_text_edit_nonfatal(step: str, exc: BaseException) -> None:
    if _is_deleted_qt_runtime_error(exc):
        return
    try:
        get_logger().log(
            f"⚠️ 자막 텍스트 편집기 UI 단계 실패 [{step}]: {exc}",
            level="WARN",
            stage="ui",
        )
    except Exception:
        pass


def _run_text_edit_ui_step(step: str, callback, *, default=None, ignore_deleted_qt: bool = True):
    try:
        return callback()
    except RuntimeError as exc:
        if ignore_deleted_qt and _is_deleted_qt_runtime_error(exc):
            return default
        _log_text_edit_nonfatal(step, exc)
        return default
    except Exception as exc:
        _log_text_edit_nonfatal(step, exc)
        return default


def _qt_best_effort_getattr(target, attr: str, default=None, *, step: str | None = None):
    if target is None:
        return default
    return _run_text_edit_ui_step(
        step or f"getattr:{attr}",
        lambda: getattr(target, attr, default),
        default=default,
    )

class SubtitleBlockData(QTextBlockUserData):
    def __init__(
        self,
        spk_id: str,
        start_sec: float,
        is_gap: bool = False,
        *,
        end_sec: float | None = None,
        stt_mode: bool = False,
        stt_pending: bool = False,
        original_text: str = "",
        dictated_text: str = "",
        quality: dict | None = None,
        quality_history: list | None = None,
        quality_candidates: list | None = None,
        quality_signature: str = "",
        clip_idx: int | None = None,
        clip_file: str = "",
        stt_selected_source: str = "",
        stt_ensemble_llm_selected_source: str = "",
        stt_candidates: list | None = None,
        stt_ensemble_source: str = "",
        stt_ensemble_llm_selected_label: str = "",
        stt_ensemble_similarity: float | None = None,
        stt_ensemble_needs_llm_review: bool = False,
        stt_ensemble_inserted_from_stt2: bool = False,
        stt_ensemble_word_rover: dict | None = None,
        score: float | None = None,
        stt_score: float | None = None,
        score_color: str = "",
        stt_score_color: str = "",
        stt_score_label: str = "",
        stt_score_flags: list | None = None,
        stt_score_components: dict | None = None,
        live_preview: bool = False,
        live_preview_source: str = "",
        live_preview_stage: str = "",
    ):
        super().__init__()
        self.spk_id = spk_id
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.is_gap = is_gap
        self.stt_mode = bool(stt_mode)
        self.stt_pending = bool(stt_pending)
        self.original_text = original_text
        self.dictated_text = dictated_text
        self.quality = dict(quality or {})
        self.quality_history = list(quality_history or [])
        self.quality_candidates = list(quality_candidates or [])
        self.quality_signature = str(quality_signature or "")
        self.clip_idx = clip_idx
        self.clip_file = str(clip_file or "")
        self.stt_selected_source = str(stt_selected_source or "")
        self.stt_ensemble_llm_selected_source = str(stt_ensemble_llm_selected_source or "")
        self.stt_candidates = list(stt_candidates or [])
        self.stt_ensemble_source = str(stt_ensemble_source or "")
        self.stt_ensemble_llm_selected_label = str(stt_ensemble_llm_selected_label or "")
        self.stt_ensemble_similarity = stt_ensemble_similarity
        self.stt_ensemble_needs_llm_review = bool(stt_ensemble_needs_llm_review)
        self.stt_ensemble_inserted_from_stt2 = bool(stt_ensemble_inserted_from_stt2)
        self.stt_ensemble_word_rover = dict(stt_ensemble_word_rover or {})
        self.score = score
        self.stt_score = stt_score
        self.score_color = str(score_color or "")
        self.stt_score_color = str(stt_score_color or "")
        self.stt_score_label = str(stt_score_label or "")
        self.stt_score_flags = list(stt_score_flags or [])
        self.stt_score_components = dict(stt_score_components or {})
        self.live_preview = bool(live_preview)
        self.live_preview_source = str(live_preview_source or "")
        self.live_preview_stage = str(live_preview_stage or "")


def subtitle_block_data_to_meta(ud: SubtitleBlockData) -> dict:
    return {
        "spk_id": getattr(ud, "spk_id", "00"),
        "start_sec": getattr(ud, "start_sec", 0.0),
        "end_sec": getattr(ud, "end_sec", None),
        "is_gap": bool(getattr(ud, "is_gap", False)),
        "stt_mode": bool(getattr(ud, "stt_mode", False)),
        "stt_pending": bool(getattr(ud, "stt_pending", False)),
        "original_text": str(getattr(ud, "original_text", "") or ""),
        "dictated_text": str(getattr(ud, "dictated_text", "") or ""),
        "quality": dict(getattr(ud, "quality", {}) or {}),
        "quality_history": list(getattr(ud, "quality_history", []) or []),
        "quality_candidates": list(getattr(ud, "quality_candidates", []) or []),
        "quality_signature": str(getattr(ud, "quality_signature", "") or ""),
        "clip_idx": getattr(ud, "clip_idx", None),
        "clip_file": str(getattr(ud, "clip_file", "") or ""),
        "stt_selected_source": str(getattr(ud, "stt_selected_source", "") or ""),
        "stt_ensemble_llm_selected_source": str(getattr(ud, "stt_ensemble_llm_selected_source", "") or ""),
        "stt_candidates": list(getattr(ud, "stt_candidates", []) or []),
        "stt_ensemble_source": str(getattr(ud, "stt_ensemble_source", "") or ""),
        "stt_ensemble_llm_selected_label": str(getattr(ud, "stt_ensemble_llm_selected_label", "") or ""),
        "stt_ensemble_similarity": getattr(ud, "stt_ensemble_similarity", None),
        "stt_ensemble_needs_llm_review": bool(getattr(ud, "stt_ensemble_needs_llm_review", False)),
        "stt_ensemble_inserted_from_stt2": bool(getattr(ud, "stt_ensemble_inserted_from_stt2", False)),
        "stt_ensemble_word_rover": dict(getattr(ud, "stt_ensemble_word_rover", {}) or {}),
        "score": getattr(ud, "score", None),
        "stt_score": getattr(ud, "stt_score", None),
        "score_color": str(getattr(ud, "score_color", "") or ""),
        "stt_score_color": str(getattr(ud, "stt_score_color", "") or ""),
        "stt_score_label": str(getattr(ud, "stt_score_label", "") or ""),
        "stt_score_flags": list(getattr(ud, "stt_score_flags", []) or []),
        "stt_score_components": dict(getattr(ud, "stt_score_components", {}) or {}),
        "live_preview": bool(getattr(ud, "live_preview", False)),
        "live_preview_source": str(getattr(ud, "live_preview_source", "") or ""),
        "live_preview_stage": str(getattr(ud, "live_preview_stage", "") or ""),
    }


def subtitle_block_data_from_meta(meta: dict) -> SubtitleBlockData:
    return SubtitleBlockData(
        str(meta.get("spk_id", "00") or "00"),
        float(meta.get("start_sec", 0.0) or 0.0),
        bool(meta.get("is_gap", False)),
        end_sec=meta.get("end_sec"),
        stt_mode=bool(meta.get("stt_mode", False)),
        stt_pending=bool(meta.get("stt_pending", False)),
        original_text=str(meta.get("original_text", "") or ""),
        dictated_text=str(meta.get("dictated_text", "") or ""),
        quality=dict(meta.get("quality") or {}),
        quality_history=list(meta.get("quality_history") or []),
        quality_candidates=list(meta.get("quality_candidates") or []),
        quality_signature=str(meta.get("quality_signature", "") or ""),
        clip_idx=meta.get("clip_idx"),
        clip_file=str(meta.get("clip_file", "") or ""),
        stt_selected_source=str(meta.get("stt_selected_source", "") or ""),
        stt_ensemble_llm_selected_source=str(meta.get("stt_ensemble_llm_selected_source", "") or ""),
        stt_candidates=list(meta.get("stt_candidates") or []),
        stt_ensemble_source=str(meta.get("stt_ensemble_source", "") or ""),
        stt_ensemble_llm_selected_label=str(meta.get("stt_ensemble_llm_selected_label", "") or ""),
        stt_ensemble_similarity=meta.get("stt_ensemble_similarity"),
        stt_ensemble_needs_llm_review=bool(meta.get("stt_ensemble_needs_llm_review", False)),
        stt_ensemble_inserted_from_stt2=bool(meta.get("stt_ensemble_inserted_from_stt2", False)),
        stt_ensemble_word_rover=dict(meta.get("stt_ensemble_word_rover") or {}),
        score=meta.get("score"),
        stt_score=meta.get("stt_score"),
        score_color=str(meta.get("score_color", "") or ""),
        stt_score_color=str(meta.get("stt_score_color", "") or ""),
        stt_score_label=str(meta.get("stt_score_label", "") or ""),
        stt_score_flags=list(meta.get("stt_score_flags") or []),
        stt_score_components=dict(meta.get("stt_score_components") or {}),
        live_preview=bool(meta.get("live_preview", False)),
        live_preview_source=str(meta.get("live_preview_source", "") or ""),
        live_preview_stage=str(meta.get("live_preview_stage", "") or ""),
    )

class SubtitleHighlighter(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument):
        super().__init__(document)
        self._edited_lines: set[int] = set()
        self._current_line: int = -1
        self._gpu_overlay_active = False
        self.speaker_colors = {} 
        self.quality_by_line: dict[int, dict] = {}
        self.quality_filter = "all"
        self._quality_colors = {
            "green": QColor(31, 88, 55, 84),
            "yellow": QColor(255, 214, 10, 90),
            "red": QColor(120, 34, 34, 106),
            "gray": QColor(80, 86, 94, 80),
        }

    def mark_edited(self, line: int): 
        self._edited_lines.add(line); self.rehighlight()
        
    def set_current_line(self, line: int):
        if self._current_line != line:
            self._current_line = line

    def set_quality_map(self, quality_by_line: dict[int, dict] | None, visible_lines=None):
        next_map = dict(quality_by_line or {})
        if next_map == self.quality_by_line:
            return
        previous_map = self.quality_by_line
        self.quality_by_line = next_map
        if visible_lines is None:
            self.rehighlight()
            return
        try:
            line_set = {int(line) for line in visible_lines}
        except Exception:
            line_set = set()
        added_or_changed = {
            int(line)
            for line, quality in next_map.items()
            if previous_map.get(line) != quality
        }
        removed = {int(line) for line in previous_map.keys() if line not in next_map}
        if line_set:
            changed_lines = {line for line in added_or_changed.union(removed) if line in line_set or line in next_map}
        else:
            changed_lines = added_or_changed.union(removed)
        if not changed_lines or len(changed_lines) > 900:
            if len(changed_lines) > 900:
                self.rehighlight()
            return
        doc = self.document()
        for line in sorted(changed_lines):
            block = doc.findBlockByNumber(int(line))
            if block.isValid():
                self.rehighlightBlock(block)

    def set_quality_filter(self, key: str):
        self.quality_filter = str(key or "all")
        self.rehighlight()

    def set_gpu_overlay_active(self, active: bool):
        active = bool(active)
        if self._gpu_overlay_active == active:
            return
        self._gpu_overlay_active = active
        self.rehighlight()

    def _quality_color(self, label: str) -> QColor | None:
        return self._quality_colors.get(str(label or ""))

    def _matches_filter(self, quality: dict) -> bool:
        key = str(self.quality_filter or "all")
        if key == "all":
            return True
        label = str(quality.get("confidence_label") or "gray")
        flags = set(quality.get("flags") or ())
        if key == "needs_review":
            return label in {"red", "gray"} or bool(flags.intersection({"non_speech_hallucination_risk", "high_no_speech_prob", "outside_vad_speech"}))
        if key == "auto_corrected":
            return "auto_corrected" in flags
        return label == key

    def highlightBlock(self, text: str):
        if self._gpu_overlay_active:
            return
        block_num = self.currentBlock().blockNumber()
        quality = self.quality_by_line.get(block_num) or {}
        if quality and len(text) > 0:
            label = str(quality.get("confidence_label") or "gray")
            bg = self._quality_color(label)
            if bg is not None:
                fmt = QTextCharFormat()
                fmt.setBackground(bg)
                self.setFormat(0, len(text), fmt)
            if not self._matches_filter(quality):
                muted = QTextCharFormat()
                muted.setForeground(QColor("#69727A"))
                muted.setBackground(QColor(20, 24, 27, 120))
                self.setFormat(0, len(text), muted)

        if block_num in self._edited_lines:
            fmt = QTextCharFormat(); fmt.setBackground(QColor("#1E4D2B"))
            self.setFormat(0, len(text), fmt)
            
        ud = self.currentBlock().userData()
        spk_color = "#FFFFFF"
        if isinstance(ud, SubtitleBlockData):
            spk_color = self.speaker_colors.get(ud.spk_id, "#FFFFFF")
            if getattr(ud, "live_preview", False):
                spk_color = "#A8B2BD"
            elif getattr(ud, "stt_pending", False):
                spk_color = "#8A8F98"

        if len(text) > 0:
            cfmt = QTextCharFormat()
            cfmt.setForeground(QColor(spk_color))
            if isinstance(ud, SubtitleBlockData):
                if getattr(ud, "live_preview", False):
                    cfmt.setBackground(QColor(32, 48, 56, 88))
                    cfmt.setFontItalic(True)
                elif getattr(ud, "stt_pending", False):
                    cfmt.setBackground(QColor(72, 40, 40, 80))
            self.setFormat(0, len(text), cfmt)

class SubtitleTextEdit(QTextEdit):
    enter_pressed    = pyqtSignal(str, int)    
    backspace_merged = pyqtSignal(str)         
    cursor_moved     = pyqtSignal()
    esc_pressed      = pyqtSignal()
    tab_pressed      = pyqtSignal()
    word_selected    = pyqtSignal(str, QTextCursor, QTextCursor, QPoint) 
    
    timestamp_clicked = pyqtSignal(int, float)
    timestamp_deleted = pyqtSignal(int)
    speaker_circle_clicked = pyqtSignal(int, str, QPoint)
    speaker_circle_dropped = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        accelerated_viewport = make_accelerated_viewport(self, feature="editor")
        if accelerated_viewport is not None:
            self.setViewport(accelerated_viewport)
        self.render_backend = gpu_backend_name("editor")
        self.setFont(QFont(config.FONT, 13))
        self._base_stylesheet = self._editor_stylesheet("#DDE3EA", "#11181C")
        self._locked_stylesheet = self._editor_stylesheet("#8E8E93", "#1C1C1E")
        self._overlay_stylesheet = self._editor_stylesheet("transparent", "#11181C")
        self._overlay_locked_stylesheet = self._editor_stylesheet("transparent", "#1C1C1E")
        self.setStyleSheet(self._base_stylesheet)
        self._selection_locked = False
        self._gpu_document_overlay_active = False
        self._last_user_scroll_at = 0.0
        self._timestamp_block_meta_snapshot = {}
        self.setUndoRedoEnabled(True)
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setCursorWidth(3)
        self.timestampArea = TimestampArea(self)
        try:
            self.timestampArea.show()
            self.timestampArea.raise_()
        except Exception:
            pass
        self.document().documentLayout().documentSizeChanged.connect(self._update_margin)
        self._margin_update_timer = QTimer(self)
        self._margin_update_timer.setSingleShot(True)
        self._margin_update_timer.timeout.connect(self.update_margins)
        self._timestamp_update_timer = QTimer(self)
        self._timestamp_update_timer.setSingleShot(True)
        self._timestamp_update_timer.timeout.connect(self._flush_timestamp_area_update)
        self._scroll_repaint_timer = QTimer(self)
        self._scroll_repaint_timer.setSingleShot(True)
        self._scroll_repaint_timer.timeout.connect(self._repaint_timestamp_layer_only)
        self._scroll_idle_refresh_timer = QTimer(self)
        self._scroll_idle_refresh_timer.setSingleShot(True)
        self._scroll_idle_refresh_timer.timeout.connect(self._flush_scroll_idle_refresh)
        self.verticalScrollBar().valueChanged.connect(self._on_vertical_scroll_changed)
        self.verticalScrollBar().actionTriggered.connect(self._mark_user_scroll_activity)
        self.verticalScrollBar().sliderPressed.connect(self._mark_user_scroll_activity)
        self.textChanged.connect(self._schedule_timestamp_area_update)
        self.cursorPositionChanged.connect(self._schedule_timestamp_area_update)
        
        self._key_press_time = {} 
        self._cursor_moved_timer = QTimer(self)
        self._cursor_moved_timer.setSingleShot(True)
        self._cursor_moved_timer.timeout.connect(self._emit_cursor_moved_debounced)
        self.cursorPositionChanged.connect(self._schedule_cursor_moved)
        self._update_margin()
        self._quick_layer = self._create_quick_layer()
        if self._quick_layer is not None:
            self._quick_layer_timer = QTimer(self)
            self._quick_layer_timer.setSingleShot(True)
            self._quick_layer_timer.timeout.connect(self._sync_quick_layer)
            self.textChanged.connect(self._schedule_quick_layer_sync)
            self.cursorPositionChanged.connect(self._schedule_quick_layer_sync)
            self._schedule_quick_layer_sync()
        else:
            self._quick_layer_timer = None
        self._refresh_gpu_document_overlay_mode()

    @staticmethod
    def _editor_stylesheet(text_color: str, background_color: str) -> str:
        return (
            "QTextEdit { "
            f"background: {background_color}; color: {text_color}; border: none; "
            "border-radius: 0px; padding: 10px 12px; line-height: 1.35; "
            "selection-background-color: rgba(52, 199, 89, 0.18); "
            f"selection-color: {text_color}; "
            "}"
            "QScrollBar:vertical { background: #11181C; border: none; width: 8px; margin: 0px; }"
            "QScrollBar::handle:vertical { background: #465663; border: none; border-radius: 0px; min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; border: none; background: transparent; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; border: none; }"
        )

    def _schedule_timestamp_area_update(self):
        if bool(getattr(self, "_bulk_segment_load_active", False)):
            return
        timer = getattr(self, "_timestamp_update_timer", None)
        if timer is None:
            self._flush_timestamp_area_update()
            return
        timer.start(24)

    def _on_vertical_scroll_changed(self, *_args):
        if bool(getattr(self, "_bulk_segment_load_active", False)):
            return
        repaint_timer = getattr(self, "_scroll_repaint_timer", None)
        if repaint_timer is None:
            self._repaint_timestamp_layer_only()
        else:
            repaint_timer.start(0)
        if getattr(self, "_quick_layer", None) is not None:
            self._schedule_quick_layer_sync(delay_ms=40)
        idle_timer = getattr(self, "_scroll_idle_refresh_timer", None)
        if idle_timer is not None:
            idle_timer.start(140)

    def _repaint_timestamp_layer_only(self):
        area = getattr(self, "timestampArea", None)
        if area is None:
            return
        try:
            cr = self.contentsRect()
            target = QRect(cr.left(), cr.top(), area.sizeHint().width(), cr.height())
            if area.geometry() != target:
                area.setGeometry(target)
            if not area.isVisible():
                area.show()
            area.update()
        except RuntimeError:
            return
        except Exception:
            try:
                area.update()
            except Exception:
                pass

    def _flush_scroll_idle_refresh(self):
        if bool(getattr(self, "_bulk_segment_load_active", False)):
            return
        self._flush_timestamp_area_update()

    def _flush_timestamp_area_update(self):
        parent = getattr(self, "_parent_widget", None)
        repairer = getattr(parent, "_restore_visible_block_user_data", None)
        repaired = 0
        if callable(repairer):
            try:
                repaired = int(repairer() or 0)
            except Exception:
                repaired = 0
        if repaired:
            try:
                self.update_margins()
            except Exception:
                pass
        self.refresh_timestamp_layer()

    def refresh_timestamp_layer(self) -> bool:
        """Keep the timestamp/speaker margin visible after bulk SRT/project loads."""
        area = getattr(self, "timestampArea", None)
        if area is None:
            return False
        try:
            self._refresh_timestamp_meta_snapshot()
            self._update_margin()
            cr = self.contentsRect()
            area.setGeometry(QRect(cr.left(), cr.top(), area.sizeHint().width(), cr.height()))
            area.show()
            area.raise_()
            area.update()
            self.viewport().update()
            return True
        except RuntimeError:
            return False
        except Exception:
            try:
                area.update()
            except Exception:
                pass
            return False

    def _refresh_timestamp_meta_snapshot(self) -> None:
        """Keep a fallback copy so imported SRT time tags survive viewport refreshes."""
        try:
            doc = self.document()
            snapshot = {}
            block = doc.begin()
            while block.isValid():
                ud = block.userData()
                if isinstance(ud, SubtitleBlockData):
                    snapshot[int(block.blockNumber())] = subtitle_block_data_to_meta(ud)
                block = block.next()
            if snapshot:
                self._timestamp_block_meta_snapshot = snapshot
        except RuntimeError:
            return
        except Exception:
            return

    def _schedule_cursor_moved(self):
        timer = getattr(self, "_cursor_moved_timer", None)
        if timer is None:
            self.cursor_moved.emit()
            return
        timer.start(24)

    def _emit_cursor_moved_debounced(self):
        self.cursor_moved.emit()

    def _schedule_quick_layer_sync(self, delay_ms: int = 16):
        if bool(getattr(self, "_bulk_segment_load_active", False)):
            return
        timer = getattr(self, "_quick_layer_timer", None)
        if timer is None:
            self._sync_quick_layer()
            return
        try:
            delay = max(0, int(delay_ms))
        except Exception:
            delay = 16
        timer.start(delay)

    def _schedule_visible_margin_update(self):
        timer = getattr(self, "_margin_update_timer", None)
        if timer is None:
            self.update_margins()
            return
        timer.start(32)

    def _mark_user_scroll_activity(self, *_args):
        now = time.monotonic()
        self._last_user_scroll_at = now
        parent = getattr(self, "_parent_widget", None)
        if parent is not None:
            try:
                parent._last_editor_manual_scroll_at = now
            except Exception:
                pass
            refresher = getattr(parent, "_schedule_visible_quality_refresh", None)
            if callable(refresher):
                try:
                    refresher()
                except Exception:
                    pass

    def apply_wheel_scroll_event(self, event) -> bool:
        """Scroll the editor even when text interaction is locked or focusless."""
        bar = self.verticalScrollBar()
        if bar is None:
            return False
        try:
            pixel_delta = event.pixelDelta()
        except Exception:
            pixel_delta = QPoint()
        try:
            angle_delta = event.angleDelta()
        except Exception:
            angle_delta = QPoint()

        delta_y = int(pixel_delta.y() or 0)
        if delta_y:
            scroll_delta = -delta_y
        else:
            angle_y = int(angle_delta.y() or 0)
            if not angle_y:
                return False
            step_px = max(12, int(bar.singleStep() or 20) * 3)
            scroll_delta = int(round((-angle_y / 120.0) * step_px))

        if not scroll_delta:
            return False
        current = int(bar.value())
        target = max(int(bar.minimum()), min(int(bar.maximum()), current + scroll_delta))
        if target == current and int(bar.maximum()) <= int(bar.minimum()):
            return False
        self._mark_user_scroll_activity()
        bar.setValue(target)
        try:
            event.accept()
        except Exception:
            pass
        return True

    def focusInEvent(self, event):
        if self._selection_locked:
            event.ignore()
            parent = getattr(self, "_parent_widget", None)
            canvas = getattr(getattr(parent, "timeline", None), "canvas", None)
            if canvas is not None:
                canvas.setFocus()
            return
        parent = _qt_best_effort_getattr(self, "_parent_widget", None, step="focusInEvent parent widget")
        shortcut = _qt_best_effort_getattr(parent, "space_shortcut", None, step="focusInEvent space shortcut")
        if shortcut is not None:
            # 텍스트 편집 중 Space는 공백 입력이므로 창 재생 단축키가 영상을 시작하지 못하게 잠시 끈다.
            _run_text_edit_ui_step("focusInEvent disable space shortcut", lambda: shortcut.setEnabled(False))
        # 💡 [클릭 오지랖 완벽 삭제] 창이 켜지면서 커서가 잡힐 때 상태가 바뀌는 것을 원천 차단!
        # ✅ 수정
        qt_parent = self.parent()
        if hasattr(qt_parent, '_undo_mgr'):
            qt_parent._undo_mgr.push_immediate()
        super().focusInEvent(event)
        self._refresh_gpu_document_overlay_mode()

    # 💡 [추가] 에디터 바깥을 클릭 시 다시 켜기
    def focusOutEvent(self, e):
        _run_text_edit_ui_step(
            "focusOutEvent",
            lambda: QTextEdit.focusOutEvent(self, e),
        )
        parent = _qt_best_effort_getattr(
            self,
            "_parent_widget",
            None,
            step="focusOutEvent parent widget",
        )
        shortcut = _qt_best_effort_getattr(
            parent,
            "space_shortcut",
            None,
            step="focusOutEvent space shortcut",
        )
        if shortcut is not None:
            _run_text_edit_ui_step(
                "focusOutEvent enable space shortcut",
                lambda: shortcut.setEnabled(True),
            )
        _run_text_edit_ui_step(
            "focusOutEvent overlay refresh",
            self._refresh_gpu_document_overlay_mode,
        )

    def set_selection_locked(self, locked: bool):
        self._selection_locked = bool(locked)
        if locked:
            cur = self.textCursor()
            if cur.hasSelection():
                cur.clearSelection()
                self.setTextCursor(cur)
            self.setReadOnly(True)
            self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            self.setStyleSheet(self._locked_stylesheet)
            self.clearFocus()
        else:
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            self.setReadOnly(False)
            self.viewport().unsetCursor()
        self._refresh_gpu_document_overlay_mode()
        self._sync_quick_layer()

    def is_selection_locked(self) -> bool:
        return bool(self._selection_locked)

    def _visible_margin_line_range(self, block_count: int) -> tuple[int, int]:
        try:
            top_cursor = self.cursorForPosition(QPoint(8, 4))
            bottom_cursor = self.cursorForPosition(QPoint(8, max(4, self.viewport().height() - 8)))
            start_line = max(0, int(top_cursor.blockNumber()) - 80)
            end_line = min(block_count - 1, int(bottom_cursor.blockNumber()) + 120)
        except Exception:
            start_line = 0
            end_line = min(block_count - 1, 512)
        try:
            current_line = int(self.textCursor().blockNumber())
            start_line = min(start_line, max(0, current_line - 120))
            end_line = max(end_line, min(block_count - 1, current_line + 160))
        except Exception:
            pass
        return max(0, start_line), max(0, end_line)

    def visible_block_number_range(self, *, pad_before: int = 24, pad_after: int = 48) -> tuple[int, int]:
        doc = self.document()
        block_count = int(doc.blockCount())
        if block_count <= 0:
            return 0, 0
        try:
            top_cursor = self.cursorForPosition(QPoint(8, 4))
            bottom_cursor = self.cursorForPosition(QPoint(8, max(4, self.viewport().height() - 8)))
            start_line = max(0, int(top_cursor.blockNumber()) - int(pad_before))
            end_line = min(block_count - 1, int(bottom_cursor.blockNumber()) + int(pad_after))
        except Exception:
            start_line = 0
            end_line = min(block_count - 1, 256)
        try:
            current_line = int(self.textCursor().blockNumber())
            start_line = min(start_line, max(0, current_line - int(pad_before)))
            end_line = max(end_line, min(block_count - 1, current_line + int(pad_after)))
        except Exception:
            pass
        return max(0, start_line), max(0, end_line)

    def visible_block_numbers(self, *, pad_before: int = 24, pad_after: int = 48) -> range:
        start_line, end_line = self.visible_block_number_range(pad_before=pad_before, pad_after=pad_after)
        return range(int(start_line), int(end_line) + 1)

    def update_margins(self):
        parent = getattr(self, "_parent_widget", None)
        suspend_restore = bool(getattr(parent, "_suspend_block_user_data_restore", False)) if parent is not None else False
        if not bool(getattr(self, "_bulk_segment_load_active", False)) and not suspend_restore:
            repairer = getattr(parent, "_restore_visible_block_user_data", None)
            if callable(repairer):
                try:
                    repairer()
                except Exception:
                    pass
        doc = self.document()
        prev_doc_signals = bool(doc.blockSignals(True))  # margin changes must not look like text edits
        cur = None
        edit_open = False
        try:
            prev_start = -1.0
            block_count = int(doc.blockCount())
            virtual_threshold = int(os.environ.get("AI_SUBTITLE_EDITOR_MARGIN_VIRTUALIZE_THRESHOLD", "900") or "900")
            if block_count > virtual_threshold:
                start_line, end_line = self._visible_margin_line_range(block_count)
                if start_line > 0:
                    prev_block = doc.findBlockByNumber(start_line - 1)
                    prev_ud = prev_block.userData() if prev_block.isValid() else None
                    if isinstance(prev_ud, SubtitleBlockData) and not prev_ud.is_gap:
                        prev_start = prev_ud.start_sec
                block = doc.findBlockByNumber(start_line)
            else:
                start_line, end_line = 0, max(0, block_count - 1)
                block = doc.begin()

            while block.isValid() and block.blockNumber() <= end_line:
                ud = block.userData()
                fmt = block.blockFormat()
                target_margin = 0.0
                
                if isinstance(ud, SubtitleBlockData):
                    if ud.is_gap:
                        target_margin = 0.0
                        prev_start = -1.0
                    else:
                        if abs(ud.start_sec - prev_start) > 0.05:
                            if block.blockNumber() > 0:
                                target_margin = 5.0
                        prev_start = ud.start_sec
                else:
                    prev_start = -1.0

                if abs(float(fmt.topMargin()) - float(target_margin)) > 0.01:
                    if cur is None:
                        cur = QTextCursor(doc)
                        cur.beginEditBlock()
                        edit_open = True
                    fmt.setTopMargin(target_margin)
                    cur.setPosition(block.position())
                    cur.setBlockFormat(fmt)

                block = block.next()
        finally:
            if cur is not None and edit_open:
                try:
                    cur.endEditBlock()
                except Exception:
                    pass
            try:
                doc.blockSignals(prev_doc_signals)
            except Exception:
                pass

    def _update_margin(self):
        self.setViewportMargins(self.timestampArea.sizeHint().width(), 0, 0, 0)

    def _create_quick_layer(self):
        # Keep the subtitle text editor on the native QTextEdit path by default.
        # QQuickWidget overlays can steal scroll/composition time on macOS/Metal
        # and make long subtitle navigation feel stuck. It remains available as
        # an explicit diagnostic opt-in.
        if str(os.environ.get("AI_SUBTITLE_EDITOR_TEXT_QML", "")).strip().lower() not in {"1", "true", "yes", "on"}:
            return None
        if not scenegraph_enabled("editor"):
            return None
        qml_path = os.path.join(os.path.dirname(__file__), "subtitle_text_editor.qml")
        if not os.path.exists(qml_path):
            return None
        try:
            from PyQt6.QtQuickWidgets import QQuickWidget
        except Exception:
            return None
        try:
            layer = QQuickWidget(self)
            layer.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
            layer.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            layer.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, True)
            layer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            layer.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            layer.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            layer.setClearColor(QColor(0, 0, 0, 0))
            layer.setSource(QUrl.fromLocalFile(qml_path))
            if layer.status() == QQuickWidget.Status.Error:
                layer.deleteLater()
                return None
            layer.setGeometry(self.rect())
            layer.show()
            layer.raise_()
            return layer
        except Exception:
            return None

    def _quick_layer_overlay_text_active(self) -> bool:
        return bool(getattr(self, "_quick_layer", None) is not None)

    def _refresh_gpu_document_overlay_mode(self):
        def _apply_overlay_state():
            active = self._quick_layer_overlay_text_active()
            stylesheet = self._overlay_locked_stylesheet if self._selection_locked else self._overlay_stylesheet
            if not active:
                stylesheet = self._locked_stylesheet if self._selection_locked else self._base_stylesheet
            self._gpu_document_overlay_active = active
            if self.styleSheet() != stylesheet:
                self.setStyleSheet(stylesheet)
            parent = _qt_best_effort_getattr(
                self,
                "_parent_widget",
                None,
                step="overlay parent widget",
            )
            highlighter = _qt_best_effort_getattr(
                parent,
                "_highlighter",
                None,
                step="overlay parent highlighter",
            )
            setter = _qt_best_effort_getattr(
                highlighter,
                "set_gpu_overlay_active",
                None,
                step="overlay highlighter setter",
            )
            if callable(setter):
                setter(active)

        _run_text_edit_ui_step("overlay mode apply", _apply_overlay_state)

    @staticmethod
    def _format_quick_line_timecode(start_sec: float) -> str:
        try:
            total_ms = max(0, int(round(float(start_sec or 0.0) * 1000.0)))
        except Exception:
            total_ms = 0
        total_sec = total_ms // 1000
        minutes = total_sec // 60
        seconds = total_sec % 60
        millis = total_ms % 1000
        return f"{minutes:02d}:{seconds:02d}.{millis // 10:02d}"

    def _collect_quick_layer_visible_lines(self) -> list[dict]:
        if getattr(self, "_quick_layer", None) is None:
            return []
        doc = self.document()
        if doc is None:
            return []
        parent = getattr(self, "_parent_widget", None)
        repairer = getattr(parent, "_restore_visible_block_user_data", None)
        if callable(repairer):
            try:
                repairer()
            except Exception:
                pass
        lines: list[dict] = []
        try:
            top_cursor = self.cursorForPosition(QPoint(8, 4))
            bottom_cursor = self.cursorForPosition(QPoint(8, max(4, self.viewport().height() - 8)))
            start_line = max(0, int(top_cursor.blockNumber()) - 1)
            end_line = max(start_line, int(bottom_cursor.blockNumber()) + 2)
        except Exception:
            start_line = 0
            end_line = max(0, int(doc.blockCount()) - 1)
        block = doc.findBlockByNumber(start_line)
        limit = min(max(start_line, end_line), int(doc.blockCount()) - 1)
        while block.isValid() and block.blockNumber() <= limit and len(lines) < 384:
            try:
                rect = self.cursorRect(QTextCursor(block))
            except Exception:
                block = block.next()
                continue
            top = int(rect.top())
            height = max(int(rect.height()), int(self.fontMetrics().height() * 1.35))
            if top + height < -height:
                block = block.next()
                continue
            if top > self.viewport().height() + height:
                break
            ud = block.userData()
            timestamp = ""
            accent = "#465663"
            bg_fill = "transparent"
            italic = False
            show_circle = False
            delete_visible = False
            if isinstance(ud, SubtitleBlockData):
                if not getattr(ud, "is_gap", False):
                    timestamp = self._format_quick_line_timecode(getattr(ud, "start_sec", 0.0))
                    show_circle = True
                if getattr(ud, "live_preview", False):
                    accent = "#64D2FF"
                    bg_fill = "#16303C"
                    italic = True
                elif getattr(ud, "stt_pending", False):
                    accent = COLORS["warning"]
                    bg_fill = COLORS["warning_surface"]
                elif getattr(ud, "is_gap", False):
                    accent = "#5E5E64"
            active = block.blockNumber() == self.textCursor().blockNumber()
            if active:
                bg_fill = "#1B2C34"
                accent = "#34C759"
                delete_visible = bool(isinstance(ud, SubtitleBlockData) and not getattr(ud, "is_gap", False))
            text = block.text().replace("\u2028", "\n")
            lines.append(
                {
                    "line": int(block.blockNumber()),
                    "text": text,
                    "timestamp": timestamp,
                    "y": top,
                    "height": height,
                    "active": bool(active),
                    "accent": accent,
                    "fill": bg_fill,
                    "italic": bool(italic),
                    "showCircle": bool(show_circle),
                    "deleteVisible": bool(delete_visible),
                    "deleteHovered": False,
                }
            )
            block = block.next()
        return lines

    def _sync_quick_layer(self):
        layer = getattr(self, "_quick_layer", None)
        if layer is None:
            return
        try:
            root = layer.rootObject()
            if root is None:
                return
            root.setProperty("locked", bool(self._selection_locked))
            root.setProperty("editorFocused", bool(self.hasFocus()))
            root.setProperty("contentLeft", int(self.timestampArea.sizeHint().width()))
            root.setProperty("visibleLines", self._collect_quick_layer_visible_lines())
        except RuntimeError:
            self._quick_layer = None
        except Exception:
            pass

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not self.refresh_timestamp_layer():
            return

        # 💡 [신규] 오버스크롤(Overscroll) 적용: 마지막 줄이 화면 중간에 오도록 하단 여백 추가!
        doc = self.document()
        try:
            doc.blockSignals(True)  # 💡 [핵심 추가] 창 크기가 변할 때 '편집 중'으로 넘어가는 오작동 완벽 차단!
            root_fmt = doc.rootFrame().frameFormat()
            # 현재 보이는 에디터 화면 높이의 딱 절반( // 2 )만큼 아래쪽에 투명한 쿠션을 깔아줍니다.
            root_fmt.setBottomMargin(max(0, self.viewport().height() // 2))
            doc.rootFrame().setFrameFormat(root_fmt)
        finally:
            try:
                doc.blockSignals(False) # 💡 [신호 복구]
            except Exception:
                pass
        layer = getattr(self, "_quick_layer", None)
        if layer is not None:
            try:
                layer.setGeometry(self.rect())
                QTimer.singleShot(0, layer.raise_)
            except RuntimeError:
                self._quick_layer = None
            except Exception:
                pass
        self._schedule_timestamp_area_update()
        self._refresh_gpu_document_overlay_mode()
        self._schedule_quick_layer_sync()

    def createMimeDataFromSelection(self) -> QMimeData:
        return super().createMimeDataFromSelection()

    def insertFromMimeData(self, source):
        if source.hasText():
            text = source.text()
            text = re.sub(r'[\[［<{\(]\s*\d{1,3}\s*[:.]\s*\d{1,2}\s*(?:[:.]\s*\d+)?\s*[\]］>}\)]\s*', '', text)
            self.insertPlainText(text)

    def mouseMoveEvent(self, event):
        if self._selection_locked:
            event.accept()
            return
        super().mouseMoveEvent(event)
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._clear_hover(); return
        if self.textCursor().hasSelection(): return
        cur = self.cursorForPosition(event.pos())
        cur.select(QTextCursor.SelectionType.WordUnderCursor)
        word = cur.selectedText().strip()
        if word:
            hc = getattr(self, "_hover_cur", None)
            if (hc and hc.selectedText() == cur.selectedText() and hc.selectionStart() == cur.selectionStart()): return
            self._clear_hover()
            self._hover_cur = QTextCursor(cur)
            sel = QTextEdit.ExtraSelection(); sel.cursor = cur
            fmt = QTextCharFormat(); fmt.setBackground(QColor("#443300")); sel.format = fmt
            self._hover_sel = sel; self._apply_extras()
        else: self._clear_hover()

    def _clear_hover(self):
        self._hover_cur = None; self._hover_sel = None; self._apply_extras()

    def _apply_extras(self):
        extras = []
        hs = getattr(self, "_hover_sel", None)
        if hs: extras.append(hs)
        self.setExtraSelections(extras)

    def mouseLeaveEvent(self, event):
        super().leaveEvent(event); self._clear_hover()

    def mousePressEvent(self, event):
        if self._selection_locked:
            self._clear_hover()
            event.accept()
            return
        self._clear_hover(); super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._selection_locked:
            event.accept()
            return
        super().mouseReleaseEvent(event)
        # 💡 [수정] 왼쪽 버튼 드래그 후 마우스를 뗄 때 팝업을 띄우던 로직을 완전히 제거했습니다.
        # 이제 드래그만 해서는 아무 일도 일어나지 않습니다.

    def wheelEvent(self, event):
        if self.apply_wheel_scroll_event(event):
            return
        self._mark_user_scroll_activity()
        super().wheelEvent(event)

    def contextMenuEvent(self, event):
        if self._selection_locked:
            event.accept()
            return
        # 현재 에디터의 메인 커서(드래그된 선택 영역 포함)를 가져옵니다.
        main_cur = self.textCursor()
        click_pos = self.cursorForPosition(event.pos()).position()

        # 💡 1. 이미 드래그한 선택 영역이 있고, 우클릭한 위치가 그 영역 안일 경우 -> 기존 선택 영역 유지
        if main_cur.hasSelection() and main_cur.selectionStart() <= click_pos <= main_cur.selectionEnd():
            cur = main_cur
        # 💡 2. 선택 영역이 없거나 다른 곳을 우클릭했을 경우 -> 클릭한 위치의 단어를 자동 선택
        else:
            cur = self.cursorForPosition(event.pos())
            cur.select(QTextCursor.SelectionType.WordUnderCursor)
            self.setTextCursor(cur) # 선택된 단어로 커서 업데이트

        text = cur.selectedText().strip()
        if text:
            gpos = event.globalPos()
            anchor = QTextCursor(cur); anchor.setPosition(cur.selectionStart())
            end_c = QTextCursor(cur); end_c.setPosition(cur.selectionEnd())
            
            # 여기서 팝업창을 호출합니다.
            self.word_selected.emit(text, anchor, end_c, gpos)
            
        event.accept()

    def keyReleaseEvent(self, e: QKeyEvent):
        if not e.isAutoRepeat(): self._key_press_time.pop(e.key(), None)
        super().keyReleaseEvent(e)

    def _pause_parent_playback_for_keyboard_edit(self) -> None:
        parent = getattr(self, "_parent_widget", None)
        pause_handler = getattr(parent, "_pause_playback_for_keyboard_edit", None)
        if callable(pause_handler):
            try:
                pause_handler()
            except Exception:
                pass

    def _should_pause_playback_for_keypress(self, e: QKeyEvent) -> bool:
        key = e.key()
        if key in (
            Qt.Key.Key_Shift,
            Qt.Key.Key_Control,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
            Qt.Key.Key_AltGr,
            Qt.Key.Key_CapsLock,
            Qt.Key.Key_NumLock,
            Qt.Key.Key_ScrollLock,
            Qt.Key.Key_Escape,
        ):
            return False
        return True

    def keyPressEvent(self, e: QKeyEvent):
        if self._selection_locked:
            e.accept()
            return
        key = e.key()
        mod = e.modifiers()
        cur = self.textCursor()

        parent_widget = getattr(self, "_parent_widget", None)
        if parent_widget and hasattr(parent_widget, "editor_popup"):
            popup = parent_widget.editor_popup
            if popup.is_visible() and getattr(popup, "_mode", "") == "menu":
                if key == Qt.Key.Key_Right: popup.execute_action(0); return
                elif key == Qt.Key.Key_Down: popup.navigate(1); return
                elif key == Qt.Key.Key_Up: popup.navigate(-1); return
                elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter): popup.confirm(); return
                elif key == Qt.Key.Key_Escape: popup.close_popup(refocus=True); return

        if key == Qt.Key.Key_Shift and not e.isAutoRepeat():
            e.accept()
            return

        if self._should_pause_playback_for_keypress(e):
            self._pause_parent_playback_for_keyboard_edit()

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            parent = getattr(self, "_parent_widget", None)
            if parent and getattr(parent, "_stt_mode_enabled", False) and hasattr(parent, "_handle_stt_enter"):
                parent._handle_stt_enter()
                return
            if mod & Qt.KeyboardModifier.ControlModifier or mod & Qt.KeyboardModifier.MetaModifier:
                self._handle_speaker_split()
                return
            elif mod & Qt.KeyboardModifier.ShiftModifier:
                self._handle_simple_break()
                return
            self._handle_enter()
            return
            
        if key == Qt.Key.Key_Left and cur.atBlockStart() and not cur.hasSelection():
            e.accept(); return 
        if key == Qt.Key.Key_Right and cur.atBlockEnd() and not cur.hasSelection():
            e.accept(); return 
        # 💡 [신규 복구] 위/아래 스마트 커서 이동 (맨 앞/뒤에서 매끄럽게 넘어갑니다)
        if key == Qt.Key.Key_Up:
            if cur.atBlockStart() and not cur.hasSelection():
                cur.movePosition(QTextCursor.MoveOperation.PreviousBlock)
                cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                self.setTextCursor(cur)
                return
        if key == Qt.Key.Key_Down:
            if cur.atBlockEnd() and not cur.hasSelection():
                cur.movePosition(QTextCursor.MoveOperation.NextBlock)
                cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                self.setTextCursor(cur)
                return
        if key == Qt.Key.Key_Escape: self.esc_pressed.emit(); return
        if key == Qt.Key.Key_Space and not cur.hasSelection():
            parent = getattr(self, "_parent_widget", None)
            if parent and getattr(parent, "_stt_mode_enabled", False) and hasattr(parent, "_handle_stt_space"):
                parent._handle_stt_space()
                return
        if key == Qt.Key.Key_Tab: self.tab_pressed.emit(); e.accept(); return
        if key == Qt.Key.Key_A and (mod & Qt.KeyboardModifier.ControlModifier or mod & Qt.KeyboardModifier.MetaModifier): self.selectAll(); return
        if key == Qt.Key.Key_C and (mod & Qt.KeyboardModifier.ControlModifier or mod & Qt.KeyboardModifier.MetaModifier): super().keyPressEvent(e); return
        
        if key == Qt.Key.Key_Backspace: self._handle_backspace(e); return
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Clear): self._handle_delete(e); return

        super().keyPressEvent(e)

    def _handle_speaker_split(self):
        cur = self.textCursor()
        block = cur.block()
        ud = block.userData()
        start_sec = ud.start_sec if isinstance(ud, SubtitleBlockData) else 0.0
        spk = ud.spk_id if isinstance(ud, SubtitleBlockData) else "00"
        
        parent = getattr(self, "_parent_widget", None)
        spk1_id = "00"; spk2_id = "01"
        if parent and hasattr(parent, "settings"):
            spk1_id = parent.settings.get("spk1_id", "00")
            spk2_id = parent.settings.get("spk2_id", "01")
            
        next_spk = spk2_id if spk == spk1_id else spk1_id
        col = cur.columnNumber()
        line_text = block.text()
        before = line_text[:col].strip()
        after = line_text[col:].strip()
        
        if before and not before.startswith("-"): before = "- " + before.lstrip("- ")
        if after and not after.startswith("-"): after = "- " + after.lstrip("- ")
            
        cur.beginEditBlock() 
        cur.select(QTextCursor.SelectionType.LineUnderCursor)
        cur.removeSelectedText()
        
        cur.insertText(before)
        cur.block().setUserData(SubtitleBlockData(spk, start_sec))
        cur.insertText("\n")
        cur.insertText(after)
        cur.block().setUserData(SubtitleBlockData(next_spk, start_sec)) 
        
        self.update_margins() 
        cur.endEditBlock()
        
        # 💡 [핵심 수정] 화자 분리 시점(start_sec)을 기점으로 화면 정렬
        parent = getattr(self, "_parent_widget", None)
        if parent:
            parent._sync_lock = True
            self.setTextCursor(cur)
            if hasattr(parent, 'timeline'):
                # 🎯 화자 분리가 일어난 현재 시점을 중앙으로 고정
                parent.timeline.center_to_sec(start_sec, smooth=True)
            parent._sync_lock = False
        
        if parent and hasattr(parent, "_highlighter"):
            parent._highlighter.rehighlight()
        self._schedule_timestamp_area_update()
        self._schedule_quick_layer_sync()
    
    def _handle_simple_break(self):
        """Shift + Enter: 동일 자막 세그먼트 내에서 줄바꿈 (구조적 통일)"""
        cur = self.textCursor()
        cur.beginEditBlock()
        # 💡 핵심: 블록을 쪼개지 않고 소프트 줄바꿈(\u2028)을 삽입합니다.
        # 이렇게 하면 하나의 SubtitleBlockData(시간 정보)를 공유하게 됩니다. 
        cur.insertText("\u2028") 
        cur.endEditBlock()
        
        self.setTextCursor(cur)
        # 💡 UndoManager 스냅샷 즉시 저장 
        parent = getattr(self, "_parent_widget", None)
        if parent and hasattr(parent, "_undo_mgr"):
            parent._undo_mgr.push_immediate()
        self._schedule_timestamp_area_update()
        self._schedule_quick_layer_sync()

    def _handle_enter(self):
        cur = self.textCursor()
        block = cur.block()
        ud = block.userData()
        start_sec = ud.start_sec if isinstance(ud, SubtitleBlockData) else 0.0
        spk = ud.spk_id if isinstance(ud, SubtitleBlockData) else "00"
        
        col = cur.columnNumber()
        line_text = block.text()
        before, after = line_text[:col].strip(), line_text[col:].strip()
        
        if not before: return
        if not after:
            cur.movePosition(QTextCursor.MoveOperation.NextBlock)
            self.setTextCursor(cur)
            return

        end_sec = start_sec + 3.0
        doc = self.document()
        for i in range(block.blockNumber() + 1, doc.blockCount()):
            next_ud = doc.findBlockByNumber(i).userData()
            if isinstance(next_ud, SubtitleBlockData) and not next_ud.is_gap:
                end_sec = next_ud.start_sec
                break
                
        total_len = len(before) + len(after)
        new_sec = start_sec + (end_sec - start_sec) * (len(before) / total_len) if total_len > 0 else start_sec
        parent = getattr(self, "_parent_widget", None)
        if parent is not None and hasattr(parent, "_snap_to_frame"):
            new_sec = parent._snap_to_frame(new_sec)
        else:
            new_sec = round(new_sec, 6)
        
        cur.beginEditBlock() 
        cur.select(QTextCursor.SelectionType.LineUnderCursor)
        cur.removeSelectedText()
        
        cur.insertText(before)
        cur.block().setUserData(SubtitleBlockData(spk, start_sec))
        
        cur.insertText("\n")
        cur.insertText(after)
        cur.block().setUserData(SubtitleBlockData(spk, new_sec))
        
        self.update_margins() 
        cur.endEditBlock()
        
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        
        # 💡 [구조 개선] 커서 이동 명령어는 밖으로 빼고, 타임라인 잠금만 parent로 감쌉니다.
        if parent: parent._sync_lock = True
        
        self.setTextCursor(cur)  # 👈 parent가 없어도 무조건 커서는 이동하도록 밖으로 분리!
        
        if parent:
            parent._active_seg_start = new_sec
            if hasattr(parent, 'timeline'):
                parent.timeline.set_active(new_sec)
                # 🎯 엔터로 생성된 새 지점(new_sec)을 타임라인 중앙으로!
                parent.timeline.center_to_sec(new_sec, smooth=True)
            parent._sync_lock = False
        
        last_word = before.split()[-1] if before else ""
        if last_word: 
            self.enter_pressed.emit(last_word, block.blockNumber())

    def _handle_delete(self, e: QKeyEvent):
        cur = self.textCursor()
        if cur.hasSelection():
            super().keyPressEvent(e); return
            
        curr_block = cur.block()
        col = cur.columnNumber()
        text_after_cursor = curr_block.text()[col:]
        
        if not text_after_cursor.strip() and curr_block.blockNumber() < self.document().blockCount() - 1:
            next_block = curr_block.next()
            if not next_block.isValid(): return
            
            ud = curr_block.userData()
            old_spk = ud.spk_id if isinstance(ud, SubtitleBlockData) else "00"
            old_start = ud.start_sec if isinstance(ud, SubtitleBlockData) else 0.0
            
            c_curr = curr_block.text()[:col].strip() 
            
            def clean_h(t):
                if t.startswith("- "): return t[2:].strip()
                return t[1:].strip() if t.startswith("-") else t
            
            n_curr = clean_h(next_block.text().strip())
            joined = c_curr + (" " + n_curr if c_curr and n_curr else n_curr)
            
            restore_pos = curr_block.position() + len(c_curr)
            if c_curr and n_curr: restore_pos += 1  
            
            cur.beginEditBlock() 
            cur.setPosition(curr_block.position())
            cur.movePosition(QTextCursor.MoveOperation.NextBlock, QTextCursor.MoveMode.KeepAnchor)
            cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            
            cur.insertText(joined)
            cur.block().setUserData(SubtitleBlockData(old_spk, old_start))
            
            self.update_margins()
            cur.endEditBlock()
            
            f_cur = self.textCursor()
            f_cur.setPosition(restore_pos)
            self.setTextCursor(f_cur)
            return
            
        super().keyPressEvent(e)

    # (위쪽에는 _handle_delete 함수 코드가 있습니다)
    def _handle_backspace(self, e):
        """백스페이스: 복사 버그 방지를 위해 시스템 기본 동작 활용 후 데이터 갱신"""
        cur = self.textCursor()
        if cur.hasSelection():
            super().keyPressEvent(e)
            return

        # 블록의 맨 앞에서 백스페이스를 눌러 이전 자막과 합쳐지는 경우만 제어
        if cur.atBlockStart() and cur.block().blockNumber() > 0:
            cur.beginEditBlock()
            # 💡 수동 합치기 대신, 이전 블록과의 구분자(엔터)만 삭제하여 자연스럽게 병합 
            cur.deletePreviousChar() 
            cur.endEditBlock()
            self.setTextCursor(cur)
            
            # 병합 후 즉시 데이터 동기화 및 스냅샷 저장
            self.backspace_merged.emit("") 
            return

        super().keyPressEvent(e)
