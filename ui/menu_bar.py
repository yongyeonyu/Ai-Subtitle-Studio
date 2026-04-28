# Version: 02.07.00
# Phase: PHASE1-D
"""
Global bottom menu bar.

This replaces duplicated sidebar/editor action menus while keeping the editor's
existing button/state-machine objects alive behind the scenes.
"""
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QWidget

from ui.style import label_style, line_icon, tool_button_style


class StatusRail(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 2, 0, 4)
        layout.setHorizontalSpacing(4)
        layout.setVerticalSpacing(4)
        self.status_buttons = {}
        for idx, (key, text, icon) in enumerate([
            ("generate", "생성", "subtitle"),
            ("editing", "편집", "edit"),
            ("stt", "STT", "mic"),
            ("saved", "저장", "check"),
            ("export", "출력", "export"),
            ("exit", "종료", "power"),
        ]):
            btn = QToolButton()
            btn.setText(text)
            btn.setIcon(line_icon(icon, "#A9B0B7", 20))
            btn.setIconSize(QSize(15, 15))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setFixedSize(60, 28)
            btn.setCursor(Qt.CursorShape.ArrowCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setStyleSheet(tool_button_style("toolbar"))
            self.status_buttons[key] = btn
            layout.addWidget(btn, idx // 3, idx % 3)

    def refresh_from_editor(self, editor):
        active_key = None
        if editor is not None:
            state = str(getattr(editor, "current_state", "") or "").lower()
            status_text = ""
            label = getattr(editor, "status_lbl", None)
            if label is not None:
                try:
                    status_text = str(label.text() or "")
                except Exception:
                    status_text = ""
            dirty = bool(getattr(editor, "_is_dirty", False))
            processing = bool(getattr(editor, "_is_ai_processing", False))
            if processing or "생성" in status_text or "처리" in status_text or "processing" in state:
                active_key = "generate"
            elif "저장" in status_text or "saved" in state:
                active_key = "saved"
            elif "출력" in status_text or "export" in state:
                active_key = "export"
            elif getattr(editor, "_stt_mode_enabled", False):
                active_key = "stt"
            elif dirty or editor is not None:
                active_key = "editing"

        icon_map = {
            "generate": "subtitle",
            "editing": "edit",
            "stt": "mic",
            "saved": "check",
            "export": "export",
            "exit": "power",
        }
        for key, btn in self.status_buttons.items():
            active = key == active_key
            color = "#34C759" if key == "saved" else "#007AFF" if active else "#A9B0B7"
            if key == "exit":
                color = "#FF8A80" if active else "#A9B0B7"
            btn.setIcon(line_icon(icon_map[key], color, 20))
            btn.setStyleSheet(tool_button_style("toolbar", checked=active))


class GlobalMenuBar(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.editor = None
        self.status_rail = None
        self._tool_buttons = []
        self.setFixedHeight(74)
        self.setStyleSheet("background: #151C20; border-top: none;")

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(8)

        self.left_group = QWidget()
        left = QHBoxLayout(self.left_group)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(5)
        for text, icon, slot, color in [
            ("AI", "ai", self._open_ai, "#34C759"),
            ("설정", "settings", self._open_advanced, "#A9B0B7"),
            ("화자", "speaker", self._open_speaker, "#A678F4"),
            ("화각", "sliders", self._open_angle_placeholder, "#FF9500"),
            ("간격", "timeline", self._open_gap, "#579DFF"),
            ("비디오", "video", self._toggle_video, "#579DFF"),
            ("자막", "export", self._open_export, "#34C759"),
            ("STT", "mic", self._toggle_stt_mode, "#FF453A"),
        ]:
            btn = self._small_button(text, icon, slot, color)
            if text == "STT":
                self.btn_stt_mode = btn
            left.addWidget(btn)
        root.addWidget(self.left_group, stretch=1, alignment=Qt.AlignmentFlag.AlignLeft)

        self.center_group = QWidget()
        center = QHBoxLayout(self.center_group)
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(6)
        self.btn_start = self._action_button("시작", "restart", self._click_start)
        self.btn_undo = self._action_button("취소", "undo", self._click_undo)
        self.btn_redo = self._action_button("복귀", "redo", self._click_redo)
        self.btn_save = self._action_button("저장", "save", self._click_save)
        for btn in (self.btn_start, self.btn_undo, self.btn_redo, self.btn_save):
            center.addWidget(btn)
        root.addWidget(self.center_group, stretch=0, alignment=Qt.AlignmentFlag.AlignCenter)

        self.right_group = QWidget()
        right = QHBoxLayout(self.right_group)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(5)
        self.btn_auto_start = self._wide_button("자동", "sliders", self._toggle_auto_start)
        self.btn_log = self._wide_button("터미널", "terminal", self._toggle_log)
        self.btn_auto_settings = self._wide_button("자동설정", "settings", self._open_auto_settings, min_width=96)
        self.btn_cache_clear = self._wide_button("캐쉬삭제", "trash", self._clear_cache, min_width=96)
        right.addWidget(self.btn_auto_settings)
        right.addWidget(self.btn_cache_clear)
        right.addWidget(self.btn_auto_start)
        right.addWidget(self.btn_log)
        right.addWidget(self._wide_button("종료", "power", self._quit, kind="danger"))
        root.addWidget(self.right_group, stretch=1, alignment=Qt.AlignmentFlag.AlignRight)

        self.engine_label = QLabel("")
        self.engine_label.setMinimumWidth(132)
        self.engine_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.engine_label.setStyleSheet(label_style("muted", 10, bold=True))
        root.addWidget(self.engine_label)

        self.refresh()

    def _small_button(self, text, icon_name, slot, color="#A9B0B7"):
        btn = QToolButton()
        btn.setText(text)
        btn.setIcon(line_icon(icon_name, color, 24))
        btn.setIconSize(QSize(20, 20))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setMinimumSize(54, 52)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(tool_button_style("toolbar"))
        btn.clicked.connect(slot)
        self._tool_buttons.append(btn)
        return btn

    def _wide_button(self, text, icon_name, slot, *, kind="toolbar", min_width=72):
        btn = QToolButton()
        btn.setText(text)
        btn.setIcon(line_icon(icon_name, "#FF8A80" if kind == "danger" else "#A9B0B7", 24))
        btn.setIconSize(QSize(18, 18))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setMinimumSize(min_width, 52)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(tool_button_style(kind))
        btn.setProperty("expandedMinWidth", min_width)
        btn.clicked.connect(slot)
        self._tool_buttons.append(btn)
        return btn

    def _action_button(self, text, icon_name, slot):
        btn = QToolButton()
        btn.setText(text)
        btn.setIcon(line_icon(icon_name, "#F5F7FA", 28))
        btn.setIconSize(QSize(24, 24))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setMinimumSize(92, 58)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(tool_button_style("toolbar"))
        btn.clicked.connect(slot)
        self._tool_buttons.append(btn)
        return btn

    def set_status_rail(self, status_rail):
        self.status_rail = status_rail
        self.refresh()

    def bind_editor(self, editor):
        self.editor = editor
        self.refresh()

    def clear_editor(self):
        self.editor = None
        self.refresh()

    def sync_from_editor(self, editor=None):
        if editor is not None:
            self.editor = editor
        self.refresh()

    def refresh(self):
        editor = self._active_editor()
        has_editor = editor is not None
        for btn in (self.btn_start, self.btn_undo, self.btn_redo, self.btn_save):
            btn.setEnabled(has_editor)
        if has_editor:
            src = getattr(editor, "btn_start", None)
            if src is not None:
                self.btn_start.setText(src.text())
                self.btn_start.setEnabled(src.isEnabled())
            engine = getattr(editor, "engine_lbl", None)
            self.engine_label.setText(engine.text() if engine is not None else "")
        else:
            self.btn_start.setText("시작")
            self.engine_label.setText("")
        if self.status_rail is not None:
            self.status_rail.refresh_from_editor(editor)
        stt_on = bool(getattr(editor, "_stt_mode_enabled", False)) if editor is not None else False
        if hasattr(self, "btn_stt_mode"):
            self.btn_stt_mode.setText("STT ON" if stt_on else "STT OFF")
            self.btn_stt_mode.setToolTip("STT 모드 ON" if stt_on else "STT 모드 OFF")
            self.btn_stt_mode.setStyleSheet(tool_button_style("toolbar", checked=stt_on))
        main = self.main_window
        auto_on = bool(getattr(main, "_auto_start_on", True))
        self.btn_auto_start.setText("자동")
        self.btn_auto_start.setToolTip("자동시작 ON" if auto_on else "자동시작 OFF")
        log_visible = bool(getattr(main, "_log_visible", False))
        self.btn_log.setText("터미널")
        self.btn_log.setToolTip("터미널 로그 숨기기" if log_visible else "터미널 로그 켜기")

        compact = self._should_icon_only()
        for btn in self._tool_buttons:
            if compact:
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                btn.setFixedWidth(max(38, btn.iconSize().width() + 18))
            else:
                if btn in (self.btn_start, self.btn_undo, self.btn_redo, self.btn_save):
                    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                    btn.setMinimumSize(92, 58)
                    btn.setMaximumWidth(16777215)
                elif btn in (self.btn_auto_start, self.btn_log, self.btn_auto_settings, self.btn_cache_clear):
                    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                    btn.setMinimumSize(int(btn.property("expandedMinWidth") or 72), 52)
                    btn.setMaximumWidth(16777215)
                else:
                    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                    btn.setMinimumSize(54, 52)
                    btn.setMaximumWidth(16777215)

    def _should_icon_only(self):
        win = self.window()
        try:
            screen_w = win.screen().availableGeometry().width()
            return win.width() <= int(screen_w * 0.55)
        except Exception:
            return self.width() <= 1000

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh()

    def _active_editor(self):
        editor = self.editor or getattr(self.main_window, "_editor_widget", None)
        if editor is None:
            return None
        try:
            if editor.parent() is None:
                return None
        except Exception:
            pass
        return editor

    def _click_editor_button(self, attr):
        editor = self._active_editor()
        if editor is None:
            return
        btn = getattr(editor, attr, None)
        if btn is not None and btn.isEnabled():
            btn.click()
        self.refresh()

    def _open_ai(self):
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_show_settings"):
            editor._show_settings()
        elif hasattr(self.main_window, "_open_main_ai_settings"):
            self.main_window._open_main_ai_settings()

    def _open_advanced(self):
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_show_adv_settings"):
            editor._show_adv_settings()
        elif hasattr(self.main_window, "_open_main_adv_settings"):
            self.main_window._open_main_adv_settings()

    def _open_speaker(self):
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_show_speaker_settings"):
            editor._show_speaker_settings()
        elif hasattr(self.main_window, "_open_main_speaker_settings"):
            self.main_window._open_main_speaker_settings()

    def _open_gap(self):
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_show_gap_settings"):
            editor._show_gap_settings()
        elif hasattr(self.main_window, "_open_main_gap_settings"):
            self.main_window._open_main_gap_settings()

    def _toggle_video(self):
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_toggle_video"):
            editor._toggle_video()
        elif hasattr(self.main_window, "_toggle_main_video"):
            self.main_window._toggle_main_video()

    def _open_export(self):
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_show_export_dialog"):
            editor._show_export_dialog()
        elif hasattr(self.main_window, "_open_main_export_dialog"):
            self.main_window._open_main_export_dialog()

    def _toggle_stt_mode(self):
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_toggle_stt_mode"):
            editor._toggle_stt_mode()
        self.refresh()

    def _open_angle_placeholder(self):
        if hasattr(self.main_window, "_dummy_action"):
            self.main_window._dummy_action()

    def _click_start(self):
        self._click_editor_button("btn_start")

    def _click_undo(self):
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_route_undo"):
            editor._route_undo()
        self.refresh()

    def _click_redo(self):
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_route_redo"):
            editor._route_redo()
        self.refresh()

    def _click_save(self):
        self._click_editor_button("btn_save")

    def _open_auto_settings(self):
        if hasattr(self.main_window, "_show_path_settings"):
            self.main_window._show_path_settings()

    def _toggle_auto_start(self):
        if hasattr(self.main_window, "_toggle_auto_start_enabled"):
            self.main_window._toggle_auto_start_enabled()
        self.refresh()

    def _clear_cache(self):
        if hasattr(self.main_window, "_clear_cache"):
            self.main_window._clear_cache()

    def _toggle_log(self):
        if hasattr(self.main_window, "_toggle_log"):
            self.main_window._toggle_log()
        self.refresh()

    def _quit(self):
        self.main_window.close()
