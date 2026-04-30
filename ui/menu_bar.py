# Version: 03.01.05
# Phase: PHASE2
"""
Global bottom menu bar.

This replaces duplicated sidebar/editor action menus while keeping the editor's
existing button/state-machine objects alive behind the scenes.
"""
from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QWidget

from ui.style import label_style, line_icon, tool_button_style


class StatusRail(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._last_state_text = ""
        self._flash_left = 0
        self._flash_on = False
        self._flash_timer = QTimer(self)
        self._flash_timer.setInterval(200)
        self._flash_timer.timeout.connect(self._tick_flash)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 2, 0, 4)
        layout.setHorizontalSpacing(0)
        layout.setVerticalSpacing(4)
        self.state_button = self._rail_button("에디터 | 검토", "edit")
        layout.addWidget(self.state_button, 0, 0)
        layout.setColumnStretch(0, 1)

    def _rail_button(self, text, icon):
        btn = QToolButton()
        btn.setText(text)
        btn.setIcon(line_icon(icon, "#A9B0B7", 20))
        btn.setIconSize(QSize(15, 15))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setMinimumHeight(34)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.setCursor(Qt.CursorShape.ArrowCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setStyleSheet(self._state_style(False))
        return btn

    def refresh_from_editor(self, editor):
        mode_key = str(getattr(self.window(), "_current_work_mode", "edit") or "edit")
        if editor is not None and mode_key not in ("roughcut", "shortform"):
            mode = str(getattr(editor, "current_mode", "") or "").lower()
            status_text = self._editor_status_text(editor)
            processing = bool(getattr(editor, "_is_ai_processing", False))
            if getattr(editor, "_stt_mode_enabled", False):
                mode_key = "stt"
            elif processing or "생성" in status_text or "mode_ai" in mode or "mode_auto" in mode:
                mode_key = "subtitle"
            else:
                mode_key = "edit"

        mode_meta = {
            "subtitle": ("자막생성", "subtitle", "#007AFF"),
            "edit": ("편집", "edit", "#34C759"),
            "stt": ("STT", "mic", "#FF453A"),
            "roughcut": ("러프컷", "roughcut", "#FF9500"),
            "shortform": ("숏폼", "shortform", "#A678F4"),
        }
        mode_text, mode_icon, mode_color = mode_meta.get(mode_key, mode_meta["edit"])
        stage_text = self._stage_text(mode_key, editor)
        text = f"{mode_text} | {stage_text}"
        self._apply_button_state(self.state_button, text, mode_icon, mode_color)
        if text != self._last_state_text:
            self._last_state_text = text
            self._start_flash()

    def _stage_text(self, mode_key: str, editor) -> str:
        if mode_key == "roughcut":
            return self._roughcut_stage_text()
        if mode_key == "shortform":
            return "준비"
        if editor is None:
            return "파일열기" if mode_key in ("edit", "subtitle", "stt") else "대기"

        status_text = self._editor_status_text(editor)
        status_l = status_text.lower()
        state = str(getattr(editor, "current_state", "") or "").lower()
        mode = str(getattr(editor, "current_mode", "") or "").lower()
        processing = bool(getattr(editor, "_is_ai_processing", False))

        if mode_key == "stt":
            if bool(getattr(editor, "_stt_recording", False)):
                return "녹음중"
            if bool(getattr(editor, "_stt_vad_running", False)):
                return "VAD생성"
            if "적용 완료" in status_text:
                return "STT완료"
            if "결과 없음" in status_text:
                return "STT확인"
            if "세그먼트" in status_text:
                return "STT분할"
            return "STT대기"

        if "렌더" in status_text or "출력" in status_text:
            return "렌더중"
        if "저장" in status_text and ("중" in status_text or "자동" in status_text):
            return "저장중"
        if "저장" in status_text and "완료" in status_text:
            return "저장완료"
        if "saved" in state:
            return "저장완료"
        if "완료" in status_text:
            return "완료"
        if "llm" in status_l or "교정" in status_text or "최적화" in status_text:
            return "LLM교정"
        if "whisper" in status_l or "인식" in status_text or "transcrib" in status_l:
            return "Whisper"
        if "vad" in status_l or "음성 구간" in status_text or "검토" in status_text:
            return "VAD검토"
        if "세그먼트" in status_text or "분할" in status_text:
            return "세그먼트"
        if processing or "생성" in status_text or "처리" in status_text or "processing" in state:
            return "생성중"
        if self._editor_has_segments(editor):
            return "편집중" if bool(getattr(editor, "_is_dirty", False)) else "자막로드"
        if "mode_ai" in mode or "mode_auto" in mode:
            return "생성대기"
        return "대기"

    def _editor_status_text(self, editor) -> str:
        label = getattr(editor, "status_lbl", None)
        if label is None:
            return ""
        try:
            return str(label.text() or "")
        except Exception:
            return ""

    def _editor_has_segments(self, editor) -> bool:
        getter = getattr(editor, "_get_current_segments", None)
        if callable(getter):
            try:
                return bool(getter())
            except Exception:
                pass
        try:
            canvas = editor.timeline.canvas
            return bool(getattr(canvas, "segments", None))
        except Exception:
            return False

    def _roughcut_stage_text(self) -> str:
        main = self.window()
        widget = getattr(main, "_roughcut_widget", None)
        if widget is None:
            panel = getattr(main, "bottom_roughcut_page", None)
            widget = getattr(panel, "_roughcut_widget", None)
        if widget is None:
            return "분석대기"
        try:
            preview_row = int(getattr(widget, "_preview_row", -1) or -1)
        except Exception:
            preview_row = -1
        if preview_row >= 0:
            return "구간재생"
        result = getattr(widget, "_result", None)
        if result is None:
            return "분석대기"
        review_count = 0
        try:
            for chapter in getattr(result, "chapters", []) or []:
                if str(getattr(chapter, "status", "") or "") == "review":
                    review_count += 1
        except Exception:
            review_count = 0
        if review_count:
            return "러프컷검토"
        return "러프컷완료"

    def _apply_button_state(self, btn, text, icon, color):
        btn.setText(text)
        btn.setIcon(line_icon(icon, color, 20))
        btn.setStyleSheet(self._state_style(self._flash_on))

    def _state_style(self, flash=False):
        bg = "#27486C" if flash else "#1F3A56"
        return (
            "QToolButton { "
            f"background: {bg}; color: #D7EBFF; border: 1px solid #007AFF; "
            "border-radius: 7px; padding: 6px 8px; font-size: 12px; font-weight: 700; "
            "text-align: left; "
            "} "
            "QToolButton:hover { "
            f"background: {bg}; color: #D7EBFF; border: 1px solid #007AFF; "
            "} "
            "QToolButton::menu-indicator { image: none; }"
        )

    def _start_flash(self):
        self._flash_left = 6
        self._flash_on = True
        self.state_button.setStyleSheet(self._state_style(True))
        self._flash_timer.start()

    def _tick_flash(self):
        self._flash_left -= 1
        self._flash_on = not self._flash_on
        self.state_button.setStyleSheet(self._state_style(self._flash_on))
        if self._flash_left <= 0:
            self._flash_timer.stop()
            self._flash_on = False
            self.state_button.setStyleSheet(self._state_style(False))


class GlobalMenuBar(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.editor = None
        self.status_rail = None
        self._tool_buttons = []
        self.setFixedHeight(74)
        self.setObjectName("GlobalMenuBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "QWidget#GlobalMenuBar { "
            "background: #151C20; border: 1px solid #2D3942; border-radius: 7px; "
            "} "
            "QWidget#MenuBarGroup { background: transparent; border: none; }"
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 5, 8, 5)
        root.setSpacing(6)

        self.left_group = QWidget()
        self.left_group.setObjectName("MenuBarGroup")
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
        self.center_group.setObjectName("MenuBarGroup")
        center = QHBoxLayout(self.center_group)
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(6)
        self.btn_start = self._action_button("시작", "play", self._click_start)
        self.btn_undo = self._action_button("Undo", "undo", self._click_undo)
        self.btn_redo = self._action_button("Redo", "redo", self._click_redo)
        self.btn_save = self._action_button("저장", "save", self._click_save)
        for btn in (self.btn_start, self.btn_undo, self.btn_redo, self.btn_save):
            center.addWidget(btn)
        root.addWidget(self.center_group, stretch=0, alignment=Qt.AlignmentFlag.AlignCenter)

        self.right_group = QWidget()
        self.right_group.setObjectName("MenuBarGroup")
        right = QHBoxLayout(self.right_group)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(5)
        self.btn_auto_start = self._wide_button("자동", "sliders", self._toggle_auto_start)
        self.btn_help = self._wide_button("도움말", "help", self._open_help)
        self.btn_log = self._wide_button("터미널", "terminal", self._toggle_log)
        self.btn_auto_settings = self._wide_button("자동설정", "settings", self._open_auto_settings, min_width=96)
        self.btn_cache_clear = self._wide_button("캐쉬삭제", "trash", self._clear_cache, min_width=96)
        right.addWidget(self.btn_auto_settings)
        right.addWidget(self.btn_cache_clear)
        right.addWidget(self.btn_auto_start)
        right.addWidget(self.btn_help)
        right.addWidget(self.btn_log)
        right.addWidget(self._wide_button("종료", "power", self._quit, kind="danger"))
        root.addWidget(self.right_group, stretch=1, alignment=Qt.AlignmentFlag.AlignRight)

        self.engine_label = QLabel("", self)
        self.engine_label.setMinimumWidth(132)
        self.engine_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.engine_label.setStyleSheet(label_style("muted", 10, bold=True))
        self.engine_label.setVisible(False)

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
        btn.setIcon(line_icon(icon_name, "#FF3B30" if kind == "danger" else "#A9B0B7", 24))
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
            engine_text = engine.text() if engine is not None else ""
            self.engine_label.setText(engine_text)
        else:
            self.btn_start.setText("시작")
            engine_text = ""
            self.engine_label.setText("")
        if hasattr(self.main_window, "_refresh_sidebar_engine_info"):
            self.main_window._refresh_sidebar_engine_info(engine_text or None)
        self._sync_start_icon()
        if self.status_rail is not None:
            self.status_rail.refresh_from_editor(editor)
        stt_on = bool(getattr(editor, "_stt_mode_enabled", False)) if editor is not None else False
        if hasattr(self, "btn_stt_mode"):
            stt_color = "#FF453A" if stt_on else "#8B949E"
            self.btn_stt_mode.setText("STT")
            self.btn_stt_mode.setIcon(line_icon("mic", stt_color, 24))
            self.btn_stt_mode.setToolTip("STT 모드 ON" if stt_on else "STT 모드 OFF")
            self.btn_stt_mode.setStyleSheet(tool_button_style("toolbar", checked=stt_on))
        main = self.main_window
        auto_on = bool(getattr(main, "_auto_start_on", True))
        self.btn_auto_start.setText("자동")
        auto_color = "#34C759" if auto_on else "#8B949E"
        self.btn_auto_start.setIcon(line_icon("auto", auto_color, 24))
        self.btn_auto_start.setStyleSheet(tool_button_style("toolbar", checked=auto_on))
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
                elif btn in (self.btn_auto_start, self.btn_help, self.btn_log, self.btn_auto_settings, self.btn_cache_clear):
                    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                    btn.setMinimumSize(int(btn.property("expandedMinWidth") or 72), 52)
                    btn.setMaximumWidth(16777215)
                else:
                    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                    btn.setMinimumSize(54, 52)
                    btn.setMaximumWidth(16777215)

    def _sync_start_icon(self):
        text = str(self.btn_start.text() or "")
        if "처리" in text:
            icon_name = "stop"
        elif "재시작" in text:
            icon_name = "refresh"
        else:
            icon_name = "play"
        self.btn_start.setIcon(line_icon(icon_name, "#F5F7FA", 28))

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
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_on_save"):
            editor._on_save(skip_auto_next=True)
        else:
            self._click_editor_button("btn_save")
        self.refresh()

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

    def _open_help(self):
        if hasattr(self.main_window, "open_help_dialog"):
            self.main_window.open_help_dialog()

    def _toggle_log(self):
        if hasattr(self.main_window, "_toggle_log"):
            self.main_window._toggle_log()
        self.refresh()

    def _quit(self):
        if hasattr(self.main_window, "_quick_exit"):
            self.main_window._quick_exit()
        else:
            self.main_window.close()
