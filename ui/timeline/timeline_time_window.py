# Version: 03.14.03
# Phase: PHASE2
"""Time-window zoom helpers for TimelineWidget."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QInputDialog, QWidget

from core.settings import load_settings, save_settings
from ui.style import settings_dialog_stylesheet


def _timeline_widget_attr(name: str, fallback):
    import sys

    module = sys.modules.get("ui.timeline.timeline_widget")
    if module is not None and hasattr(module, name):
        return getattr(module, name)
    return fallback


def _timeline_qapplication():
    return _timeline_widget_attr("QApplication", QApplication)


def _timeline_qinput_dialog():
    return _timeline_widget_attr("QInputDialog", QInputDialog)


def _timeline_load_settings():
    return _timeline_widget_attr("load_settings", load_settings)()


def _timeline_save_settings(settings: dict) -> None:
    _timeline_widget_attr("save_settings", save_settings)(settings)


class TimelineTimeWindowMixin:
    def _apply_edit_window_seconds(
        self,
        seconds: float,
        *,
        center_sec: float | None = None,
    ) -> None:
        try:
            window_seconds = max(1.0, float(seconds or 10.0))
        except Exception:
            window_seconds = 10.0
        anchor_sec = self._editing_window_anchor_sec() if center_sec is None else float(center_sec or 0.0)
        self.show_time_window_seconds(window_seconds, center_sec=anchor_sec)
        self._fit_to_view_locked = False
        self._fit_after_resize_pending = False
        self._manual_zoom_since_fit = True
        self._begin_manual_scroll(hold_sec=1.2)

    def _queue_time_window_seconds_dialog(self, _pos: QPoint | None = None) -> None:
        if bool(getattr(self, "_time_window_dialog_pending", False)):
            return
        self._time_window_dialog_pending = True
        QTimer.singleShot(0, self._show_time_window_seconds_dialog)

    def _restore_toolbar_after_time_window_dialog(self) -> None:
        self._time_window_dialog_pending = False
        app_cls = _timeline_qapplication()
        # 변경 금지: 편집 창 시간 QInputDialog는 macOS/Qt에서 취소 직후
        # mouse/keyboard grab, override cursor, focus가 버튼 위에 남을 수 있다.
        # 이 상태가 남으면 다른 툴바 버튼까지 먹통처럼 보이므로 모든 잔여
        # dialog 상태를 여기서 반드시 해제한다.
        for _ in range(4):
            try:
                app_cls.restoreOverrideCursor()
            except Exception:
                break
        for grabber_getter, releaser_name in (
            (QWidget.mouseGrabber, "releaseMouse"),
            (QWidget.keyboardGrabber, "releaseKeyboard"),
        ):
            try:
                grabber = grabber_getter()
            except Exception:
                grabber = None
            if grabber is None:
                continue
            try:
                getattr(grabber, releaser_name)()
            except Exception:
                pass

        self._release_lingering_time_window_dialog_state()

        try:
            self.setEnabled(True)
        except Exception:
            pass
        for btn in list(getattr(self, "_zoom_buttons", []) or []):
            try:
                btn.releaseMouse()
                btn.releaseKeyboard()
                btn.setDown(False)
                btn.clearFocus()
                btn.setEnabled(True)
                btn.update()
            except Exception:
                continue
        try:
            owner = self.window()
        except Exception:
            owner = None
        if owner is not None and owner is not self:
            try:
                owner.setEnabled(True)
            except Exception:
                pass
            try:
                owner.activateWindow()
            except Exception:
                pass
        try:
            for top_level in list(app_cls.topLevelWidgets() or []):
                try:
                    top_level.releaseMouse()
                except Exception:
                    pass
                try:
                    top_level.releaseKeyboard()
                except Exception:
                    pass
                try:
                    top_level.setEnabled(True)
                except Exception:
                    pass
                try:
                    top_level.clearFocus()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.setFocus(Qt.FocusReason.OtherFocusReason)
        except Exception:
            pass
        try:
            app_cls.processEvents()
        except Exception:
            pass
        self._sync_focus_border()

    def _release_lingering_time_window_dialog_state(self, dialog: QWidget | None = None) -> None:
        app_cls = _timeline_qapplication()
        seen: set[int] = set()
        widgets = []
        if dialog is not None:
            widgets.append(dialog)
        tracked_dialog = getattr(self, "_time_window_dialog", None)
        if tracked_dialog is not None:
            widgets.append(tracked_dialog)
        for getter in (
            getattr(app_cls, "activePopupWidget", None),
            getattr(app_cls, "activeModalWidget", None),
        ):
            if not callable(getter):
                continue
            try:
                widget = getter()
            except Exception:
                widget = None
            if widget is not None:
                widgets.append(widget)

        for widget in widgets:
            if widget is None:
                continue
            widget_id = id(widget)
            if widget_id in seen:
                continue
            seen.add(widget_id)
            if widget is self:
                continue
            try:
                widget.releaseMouse()
            except Exception:
                pass
            try:
                widget.releaseKeyboard()
            except Exception:
                pass
            try:
                widget.clearFocus()
            except Exception:
                pass
            if isinstance(widget, QDialog):
                try:
                    widget.setModal(False)
                except Exception:
                    pass
                try:
                    widget.setWindowModality(Qt.WindowModality.NonModal)
                except Exception:
                    pass
                try:
                    widget.reject()
                except Exception:
                    pass
                try:
                    widget.done(0)
                except Exception:
                    pass
            try:
                widget.hide()
            except Exception:
                pass
            try:
                widget.close()
            except Exception:
                pass

    def _queue_toolbar_restore_after_time_window_dialog(self) -> None:
        self._restore_toolbar_after_time_window_dialog()
        for delay in (0, 40, 120):
            QTimer.singleShot(delay, self._restore_toolbar_after_time_window_dialog)

    def _show_time_window_seconds_dialog(self, _pos: QPoint | None = None) -> None:
        current_seconds = self._current_visible_seconds()
        current_seconds_rounded = max(1, int(round(current_seconds)))
        current_seconds_label = (
            f"{current_seconds:.1f}초"
            if abs(current_seconds - current_seconds_rounded) >= 0.05
            else f"{current_seconds_rounded}초"
        )
        center_sec = self._current_visible_center_sec()
        try:
            owner = self.window()
        except Exception:
            owner = None
        if owner is None:
            owner = self
        dialog_cls = _timeline_qinput_dialog()
        dialog = dialog_cls(owner)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        dialog.setWindowTitle("편집 창 시간")
        dialog.setInputMode(dialog_cls.InputMode.IntInput)
        dialog.setLabelText(
            f"현재 표시 시간: {current_seconds_label}\n"
            "표시할 편집 창 시간을 1초 단위로 조정하세요."
        )
        dialog.setIntRange(1, 600)
        dialog.setIntStep(1)
        dialog.setIntValue(current_seconds_rounded)
        dialog.setOkButtonText("적용")
        dialog.setCancelButtonText("취소")
        dialog.setStyleSheet(settings_dialog_stylesheet())
        self._time_window_dialog = dialog
        try:
            if dialog.exec():
                # exec() 종료 직후에도 값을 읽어야 하므로 자동 삭제를 켜지 않는다.
                selected_seconds = float(dialog.intValue())
                self._apply_edit_window_seconds(selected_seconds, center_sec=center_sec)
                self._save_preferred_edit_window_seconds(selected_seconds)
        finally:
            try:
                dialog.releaseMouse()
                dialog.releaseKeyboard()
            except Exception:
                pass
            self._release_lingering_time_window_dialog_state(dialog)
            try:
                dialog.deleteLater()
            except Exception:
                pass
            self._time_window_dialog = None
            self._queue_toolbar_restore_after_time_window_dialog()

    def _editing_window_anchor_sec(self) -> float | None:
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return None

        active_line = getattr(canvas, "active_seg_line", None)
        if active_line is not None and hasattr(canvas, "_segment_for_line"):
            seg = canvas._segment_for_line(int(active_line))
            if isinstance(seg, dict):
                try:
                    start = float(seg.get("start", 0.0) or 0.0)
                    end = float(seg.get("end", start) or start)
                    if end > start:
                        return (start + end) / 2.0
                except Exception:
                    pass

        active_start = getattr(canvas, "active_seg_start", None)
        if active_start is not None and hasattr(canvas, "_active_segment_candidates"):
            try:
                candidates = canvas._active_segment_candidates()
            except Exception:
                candidates = []
            for seg in list(candidates or []):
                if not isinstance(seg, dict) or bool(seg.get("is_gap")):
                    continue
                try:
                    start = float(seg.get("start", 0.0) or 0.0)
                    end = float(seg.get("end", start) or start)
                    if end > start:
                        return (start + end) / 2.0
                except Exception:
                    continue
            try:
                return float(active_start)
            except Exception:
                pass

        try:
            playhead = float(getattr(canvas, "playhead_sec", 0.0) or 0.0)
        except Exception:
            playhead = 0.0
        return max(0.0, playhead)

    def show_time_window_seconds(
        self,
        seconds: float = 15.0,
        *,
        center_sec: float | None = None,
        start_sec: float | None = None,
    ) -> None:
        """Show a compact time window for newly opened subtitle/project files."""
        total_dur = max(0.0, float(getattr(self.canvas, "total_duration", 0.0) or 0.0), self._fit_content_duration())
        try:
            window_sec = max(1.0, float(seconds or 15.0))
        except Exception:
            window_sec = 15.0
        if total_dur <= 0.0:
            return
        visible_sec = min(window_sec, max(0.001, total_dur))
        visible_w = max(1, self._fit_reference_width())
        new_pps = max(0.001, min(500.0, float(visible_w) / max(0.001, visible_sec)))
        target_w = self._canvas_width_for_duration(total_dur, new_pps)
        viewport_w = max(1, int(self.scroll.viewport().width()))
        max_scroll = max(0, int(target_w) - viewport_w)

        if center_sec is not None:
            try:
                anchor = max(0.0, min(total_dur, float(center_sec or 0.0)))
            except Exception:
                anchor = 0.0
            view_start_sec = anchor - (visible_sec / 2.0)
        elif start_sec is not None:
            try:
                view_start_sec = float(start_sec or 0.0)
            except Exception:
                view_start_sec = 0.0
        elif self._selected_clip_idx >= 0 and self._selected_clip_duration > 0:
            view_start_sec = max(0.0, float(self._selected_clip_offset or 0.0))
        else:
            view_start_sec = 0.0
        view_start_sec = max(0.0, min(view_start_sec, max(0.0, total_dur - visible_sec)))
        target_scroll = max(0, min(self._scroll_x_for_sec(view_start_sec, new_pps), max_scroll))

        self._fit_to_view_locked = False
        self._fit_after_resize_pending = False
        self._manual_zoom_since_fit = False
        self.canvas.setUpdatesEnabled(False)
        try:
            self.canvas.pps = new_pps
            if self.canvas.width() != target_w:
                self.canvas.setFixedWidth(target_w)
            self.scroll.horizontalScrollBar().setValue(target_scroll)
            self._target_scroll_x = float(target_scroll)
            self._current_scroll_x = float(target_scroll)
        finally:
            self.canvas.setUpdatesEnabled(True)
        self._refresh_canvas_playhead_cache()

        total_for_view = max(0.001, float(getattr(self.canvas, "total_duration", 0.0) or total_dur))
        start_frac = max(0.0, min(1.0, view_start_sec / total_for_view))
        end_frac = max(start_frac, min(1.0, (view_start_sec + visible_sec) / total_for_view))
        self.global_canvas.update_viewport(start_frac, end_frac)
        self.global_canvas.update()
        if hasattr(self.canvas, "_update_viewport_region"):
            self.canvas._update_viewport_region()
        else:
            self.canvas.update()
        self._schedule_vp_sync()
        self._sync_playhead_overlay()

    def show_ten_second_edit_window(self) -> None:
        anchor_sec = self._editing_window_anchor_sec()
        self._apply_edit_window_seconds(self._preferred_edit_window_seconds, center_sec=anchor_sec)

    def preferred_edit_window_seconds(self) -> float:
        try:
            value = float(getattr(self, "_preferred_edit_window_seconds", 10.0) or 10.0)
        except Exception:
            value = 10.0
        return max(1.0, min(600.0, value))

    def _load_preferred_edit_window_seconds(self) -> float:
        try:
            settings = dict(_timeline_load_settings() or {})
            value = float(settings.get(self.EDIT_WINDOW_SETTINGS_KEY, 10.0) or 10.0)
        except Exception:
            value = 10.0
        return max(1.0, min(600.0, value))

    def _save_preferred_edit_window_seconds(self, seconds: float) -> None:
        try:
            normalized = max(1.0, min(600.0, float(seconds or 10.0)))
        except Exception:
            normalized = 10.0
        rounded_value = int(round(normalized))
        self._preferred_edit_window_seconds = float(rounded_value)
        self._refresh_time_window_button_tooltip()
        try:
            settings = dict(_timeline_load_settings() or {})
            settings[self.EDIT_WINDOW_SETTINGS_KEY] = rounded_value
            _timeline_save_settings(settings)
        except Exception:
            pass

    def _refresh_time_window_button_tooltip(self) -> None:
        button = getattr(self, "time_window_btn", None)
        if button is None:
            return
        seconds = int(round(float(getattr(self, "_preferred_edit_window_seconds", 10.0) or 10.0)))
        button.setToolTip(f"캔버스 {seconds}초 편집 창\n우클릭: 현재 시간창 조정")
