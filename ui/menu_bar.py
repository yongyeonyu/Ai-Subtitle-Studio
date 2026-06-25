# Version: 03.07.04
# Phase: PHASE2
"""
Global bottom menu bar.

This replaces duplicated sidebar/editor action menus while keeping the editor's
existing button/state-machine objects alive behind the scenes.
"""
import os

from PyQt6.QtCore import QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QMessageBox, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from core.runtime import config
from core.pipeline_status import generation_stage_label, process_mode_label
from core.work_mode import EDITOR_MODE, ROUGHCUT_MODE, SHORTFORM_MODE, normalize_work_mode
from ui.gpu_rendering import scenegraph_enabled
from ui.dialogs.message_box import ask_yes_no, show_message
from ui.responsive_profile import responsive_profile_for_size
from ui.style import COLORS, label_style, line_icon, tool_button_style

MENU_BAR_HEIGHT = 48
MENU_BUTTON_HEIGHT = 38
MENU_SMALL_WIDTH = 54
MENU_ACTION_WIDTH = 78
MENU_WIDE_WIDTH = 62
MENU_CACHE_WIDTH = 82
MENU_SMALL_ICON = 17
MENU_WIDE_ICON = 16
MENU_ACTION_ICON = 18
MENU_TEXT_UNDER_ICON_PADDING = "3px 5px 1px 5px"
MENU_PANEL_RADIUS = 7
MENU_LEFT_ACCENT = "#29D7FF"
MENU_CENTER_ACCENT = "#4AA3FF"
MENU_RIGHT_ACCENT = "#29D7FF"


def panel_visual_height_for_profile(profile) -> int:
    return max(
        MENU_BUTTON_HEIGHT,
        int(getattr(profile, "menu_button_height", MENU_BUTTON_HEIGHT) or MENU_BUTTON_HEIGHT),
    )


def panel_outer_height_for_profile(profile) -> int:
    return panel_visual_height_for_profile(profile)


class StatusRail(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(26)
        self._last_state_text = ""
        self._flash_left = 0
        self._flash_on = False
        self._flash_timer = QTimer(self)
        self._flash_timer.setInterval(200)
        self._flash_timer.timeout.connect(self._tick_flash)
        self._quick_mode_text = "에디터"
        self._quick_stage_text = "검토"
        self._quick_icon_text = "ED"
        self._quick_color = COLORS["accent"]
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(0)
        layout.setVerticalSpacing(0)
        self.state_button = self._rail_button("에디터 | 검토", "edit")
        layout.addWidget(self.state_button, 0, 0)
        layout.setColumnStretch(0, 1)
        self._quick_shell = self._create_quick_shell()
        self._sync_quick_shell()

    def _rail_button(self, text, icon):
        btn = QToolButton()
        btn.setText(text)
        btn.setIcon(line_icon(icon, COLORS["muted"], 20))
        btn.setIconSize(QSize(15, 15))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setFixedHeight(26)
        btn.setMinimumWidth(0)
        btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        btn.setCursor(Qt.CursorShape.ArrowCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setStyleSheet(self._state_style(False))
        return btn

    def refresh_from_editor(self, editor):
        mode_key = normalize_work_mode(getattr(self.window(), "_current_work_mode", EDITOR_MODE))

        mode_text, mode_icon, mode_color = self._mode_meta(mode_key, editor)
        stage_text = self._stage_text(mode_key, editor)
        text = f"{mode_text} | {stage_text}"
        self._apply_button_state(self.state_button, text, mode_icon, mode_color)
        if text != self._last_state_text:
            self._last_state_text = text
            self._start_flash()

    def _mode_meta(self, mode_key: str, editor) -> tuple[str, str, str]:
        mode_key = normalize_work_mode(mode_key)
        status_text = self._editor_status_text(editor) if editor is not None else ""
        label = process_mode_label(
            screen_mode=mode_key,
            process_mode=getattr(editor, "current_mode", "") if editor is not None else "",
            state=getattr(editor, "current_state", "") if editor is not None else "",
            status_text=status_text,
            processing=bool(getattr(editor, "_is_ai_processing", False)) if editor is not None else False,
            stt_mode_enabled=bool(getattr(editor, "_stt_mode_enabled", False)) if editor is not None else False,
        )
        meta = {
            "에디터": ("에디터", "edit", COLORS["accent"]),
            "러프컷": ("러프컷", "roughcut", "#FF9F0A"),
            "숏폼": ("숏폼", "shortform", COLORS["purple"]),
            "STT": ("STT", "mic", COLORS["danger"]),
            "자동 처리": ("자동 처리", "ai", COLORS["accent"]),
            "구간 생성": ("구간 생성", "timeline", COLORS["info"]),
            "이후 생성": ("이후 생성", "timeline", COLORS["info"]),
            "자막 생성": ("자막 생성", "ai", COLORS["accent"]),
        }
        return meta.get(label, meta["에디터"])

    def _stage_text(self, mode_key: str, editor) -> str:
        mode_key = normalize_work_mode(mode_key)
        if mode_key == ROUGHCUT_MODE:
            return self._roughcut_stage_text()
        if mode_key == SHORTFORM_MODE:
            return "준비"
        if editor is None:
            return "파일열기" if mode_key == EDITOR_MODE else "대기"

        status_text = self._editor_status_text(editor)
        state = str(getattr(editor, "current_state", "") or "").lower()
        mode = str(getattr(editor, "current_mode", "") or "").lower()
        processing = bool(getattr(editor, "_is_ai_processing", False))
        stt_ensemble_enabled = bool(getattr(editor, "settings", {}) and getattr(editor, "settings", {}).get("stt_ensemble_enabled", False))

        if bool(getattr(editor, "_stt_mode_enabled", False)):
            return self._stt_stage_text(editor, status_text)

        if "렌더" in status_text or "출력" in status_text:
            return "렌더"
        if "저장" in status_text and ("중" in status_text or "자동" in status_text):
            return "저장"
        if "저장" in status_text and "완료" in status_text:
            return "완료"
        if "saved" in state:
            return "완료"
        if "comp" in state:
            return "완료"
        if "완료" in status_text:
            return "완료"
        stage_label = generation_stage_label(status_text, stt_ensemble_enabled=stt_ensemble_enabled)
        if stage_label:
            return stage_label
        if "검토" in status_text:
            return "검토"
        if "세그먼트" in status_text or "분할" in status_text:
            return "분할"
        if processing or "생성" in status_text or "처리" in status_text or "processing" in state:
            return "생성"
        if self._editor_has_segments(editor):
            dirty_flags = getattr(editor, "_dirty_state_from_flags", None)
            is_dirty = bool(dirty_flags()) if callable(dirty_flags) else bool(getattr(editor, "_is_dirty", False))
            return "편집" if is_dirty else "검토"
        if "mode_ai" in mode or "mode_auto" in mode:
            return "대기"
        return "대기"

    def _stt_stage_text(self, editor, status_text: str) -> str:
        if bool(getattr(editor, "_stt_recording", False)):
            return "녹음"
        if bool(getattr(editor, "_stt_vad_running", False)):
            return "VAD"
        if "적용 완료" in status_text:
            return "완료"
        if "결과 없음" in status_text:
            return "확인"
        if "세그먼트" in status_text:
            return "분할"
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
            return "대기"
        status_label = getattr(widget, "render_status_lbl", None)
        try:
            status_text = str(status_label.text() or "")
        except Exception:
            status_text = ""
        if "렌더" in status_text or "출력" in status_text:
            return "렌더"
        try:
            preview_row = int(getattr(widget, "_preview_row", -1) or -1)
        except Exception:
            preview_row = -1
        if preview_row >= 0:
            return "검토"
        result = getattr(widget, "_result", None)
        if result is None:
            return "대기"
        review_count = 0
        try:
            for chapter in getattr(result, "chapters", []) or []:
                if str(getattr(chapter, "status", "") or "") == "review":
                    review_count += 1
        except Exception:
            review_count = 0
        if review_count:
            return "검토"
        return "완료"

    def _apply_button_state(self, btn, text, icon, color):
        btn.setText(text)
        btn.setIcon(line_icon(icon, color, 20))
        btn.setStyleSheet(self._state_style(self._flash_on))
        parts = [segment.strip() for segment in str(text or "").split("|", 1)]
        self._quick_mode_text = parts[0] if parts else ""
        self._quick_stage_text = parts[1] if len(parts) > 1 else ""
        self._quick_icon_text = {
            "edit": "ED",
            "roughcut": "RC",
            "shortform": "SF",
            "mic": "STT",
            "ai": "AI",
            "timeline": "CUT",
        }.get(str(icon or ""), "AI")
        self._quick_color = str(color or COLORS["accent"])
        self._sync_quick_shell()

    def _state_style(self, flash=False):
        bg = COLORS["accent_surface_hover"] if flash else COLORS["accent_surface"]
        return (
            "QToolButton { "
            f"background: {bg}; color: #D9FFE3; border: 1px solid {COLORS['accent']}; "
            "border-radius: 7px; padding: 3px 8px; font-size: 11px; font-weight: 700; "
            "text-align: left; "
            "} "
            "QToolButton:hover { "
            f"background: {bg}; color: #D9FFE3; border: 1px solid {COLORS['accent']}; "
            "} "
            "QToolButton::menu-indicator { image: none; }"
        )

    def _start_flash(self):
        self._flash_left = 6
        self._flash_on = True
        self.state_button.setStyleSheet(self._state_style(True))
        self._sync_quick_shell()
        self._flash_timer.start()

    def _tick_flash(self):
        self._flash_left -= 1
        self._flash_on = not self._flash_on
        self.state_button.setStyleSheet(self._state_style(self._flash_on))
        if self._flash_left <= 0:
            self._flash_timer.stop()
            self._flash_on = False
            self.state_button.setStyleSheet(self._state_style(False))
        self._sync_quick_shell()

    def _create_quick_shell(self):
        if not scenegraph_enabled("general"):
            return None
        qml_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "qml", "status_rail.qml"))
        if not os.path.exists(qml_path):
            return None
        try:
            from PyQt6.QtQuickWidgets import QQuickWidget
        except Exception:
            return None
        try:
            shell = QQuickWidget(self)
            shell.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
            shell.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            shell.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            shell.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            shell.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            shell.setClearColor(QColor(0, 0, 0, 0))
            shell.setSource(QUrl.fromLocalFile(qml_path))
            if shell.status() == QQuickWidget.Status.Error:
                shell.deleteLater()
                return None
            shell.setGeometry(self.rect())
            shell.show()
            shell.raise_()
            return shell
        except Exception:
            return None

    def _sync_quick_shell(self):
        shell = getattr(self, "_quick_shell", None)
        if shell is None:
            return
        try:
            root = shell.rootObject()
            if root is None:
                return
            root.setProperty("modeText", str(getattr(self, "_quick_mode_text", "에디터") or "에디터"))
            root.setProperty("stageText", str(getattr(self, "_quick_stage_text", "대기") or "대기"))
            root.setProperty("iconText", str(getattr(self, "_quick_icon_text", "AI") or "AI"))
            root.setProperty("accentColor", QColor(str(getattr(self, "_quick_color", COLORS["accent"]) or COLORS["accent"])))
            root.setProperty("flashOn", bool(getattr(self, "_flash_on", False)))
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        shell = getattr(self, "_quick_shell", None)
        if shell is not None:
            shell.setGeometry(self.rect())
            shell.raise_()


class GlobalMenuBar(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.editor = None
        self.status_rail = None
        self._tool_buttons = []
        self._quick_action_buttons = {}
        self._left_qml_buttons = []
        self._center_qml_buttons = []
        self._right_qml_buttons = []
        self._responsive_profile = responsive_profile_for_size(0, 0)
        self.setFixedHeight(MENU_BAR_HEIGHT)
        self.setObjectName("GlobalMenuBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "QWidget#GlobalMenuBar { background: transparent; border: none; } "
            "QWidget#GlobalMenuBarShell { "
            f"background: {COLORS['surface']}; border: 1px solid {COLORS['separator']}; border-radius: {MENU_PANEL_RADIUS}px; "
            "} "
            "QWidget#MenuBarGroup { background: transparent; border: none; }"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._outer_layout = outer

        self._panel_shell = QWidget(self)
        self._panel_shell.setObjectName("GlobalMenuBarShell")
        self._panel_shell.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer.addWidget(self._panel_shell)

        root = QHBoxLayout(self._panel_shell)
        root.setContentsMargins(8, 0, 8, 0)
        root.setSpacing(6)
        self._root_layout = root

        self.left_group = QWidget()
        self.left_group.setObjectName("MenuBarGroup")
        left = QHBoxLayout(self.left_group)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(5)
        for text, icon, slot, color in [
            ("설정", "settings", self._open_ai, MENU_LEFT_ACCENT),
            *([("개인화", "ai", self._open_personalization, MENU_LEFT_ACCENT)] if config.IS_MAC else []),
            ("화자", "speaker", self._open_speaker, MENU_LEFT_ACCENT),
            ("사전", "review", self._open_dictionary, MENU_LEFT_ACCENT),
            ("비디오", "video", self._toggle_video, MENU_LEFT_ACCENT),
            ("자막", "export", self._open_export, MENU_LEFT_ACCENT),
            ("음성", "mic", self._toggle_stt_mode, MENU_LEFT_ACCENT),
            ("정밀", "review", self._run_precision_refine, MENU_LEFT_ACCENT),
        ]:
            btn = self._small_button(text, icon, slot, color)
            self._register_qml_button(
                btn,
                action_id=f"left_{text}",
                badge=self._button_badge_text(icon, text),
                accent=color,
                section="left",
            )
            if text == "음성":
                self.btn_stt_mode = btn
            if text == "정밀":
                self.btn_precision_refine = btn
            left.addWidget(btn)
        root.addWidget(self.left_group, stretch=1, alignment=Qt.AlignmentFlag.AlignLeft)

        self.center_group = QWidget()
        self.center_group.setObjectName("MenuBarGroup")
        center = QHBoxLayout(self.center_group)
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(6)
        self.btn_start = self._action_button("시작", "play", self._click_start, accent=MENU_CENTER_ACCENT)
        self.btn_undo = self._action_button("실행취소", "undo", self._click_undo, accent=MENU_CENTER_ACCENT)
        self.btn_redo = self._action_button("다시실행", "redo", self._click_redo, accent=MENU_CENTER_ACCENT)
        self.btn_save = self._action_button("저장", "save", self._click_save, accent=MENU_CENTER_ACCENT)
        self._register_qml_button(self.btn_start, action_id="center_start", badge="", accent=MENU_CENTER_ACCENT, section="center", kind="primary")
        self._register_qml_button(self.btn_undo, action_id="center_undo", badge="", accent=MENU_CENTER_ACCENT, section="center")
        self._register_qml_button(self.btn_redo, action_id="center_redo", badge="", accent=MENU_CENTER_ACCENT, section="center")
        self._register_qml_button(self.btn_save, action_id="center_save", badge="", accent=MENU_CENTER_ACCENT, section="center")
        for btn in (self.btn_start, self.btn_undo, self.btn_redo, self.btn_save):
            center.addWidget(btn)
        root.addWidget(self.center_group, stretch=0, alignment=Qt.AlignmentFlag.AlignCenter)

        self.right_group = QWidget()
        self.right_group.setObjectName("MenuBarGroup")
        right = QHBoxLayout(self.right_group)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(5)
        self.btn_auto_start = self._wide_button("자동", "sliders", self._toggle_auto_start, accent=MENU_RIGHT_ACCENT)
        self.btn_help = self._wide_button("도움말", "help", self._open_help, accent=MENU_RIGHT_ACCENT)
        self.btn_cache_clear = self._wide_button("캐쉬삭제", "trash", self._clear_cache, min_width=MENU_CACHE_WIDTH, accent=MENU_RIGHT_ACCENT)
        self.btn_quit = self._wide_button("종료", "power", self._quit, accent=MENU_RIGHT_ACCENT)
        self._register_qml_button(self.btn_cache_clear, action_id="right_cache", badge="", accent=MENU_RIGHT_ACCENT, section="right")
        self._register_qml_button(self.btn_auto_start, action_id="right_auto", badge="", accent=MENU_RIGHT_ACCENT, section="right")
        self._register_qml_button(self.btn_help, action_id="right_help", badge="", accent=MENU_RIGHT_ACCENT, section="right")
        self._register_qml_button(self.btn_quit, action_id="right_quit", badge="", accent=MENU_RIGHT_ACCENT, section="right")
        right.addWidget(self.btn_cache_clear)
        right.addWidget(self.btn_auto_start)
        right.addWidget(self.btn_help)
        right.addWidget(self.btn_quit)
        root.addWidget(self.right_group, stretch=1, alignment=Qt.AlignmentFlag.AlignRight)

        self.engine_label = QLabel("", self)
        self.engine_label.setMinimumWidth(132)
        self.engine_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.engine_label.setStyleSheet(label_style("muted", 10, bold=True))
        self.engine_label.setVisible(False)
        self._quick_shell = self._create_quick_shell()

        self.refresh()

    def _menu_button_style(self, accent: str, *, checked: bool = False, emphasis: str = "toolbar") -> str:
        accent = str(accent or COLORS["accent"])
        if emphasis == "action":
            bg = "#162432" if checked else "#141E27"
            hover = "#1B2C3B"
            pressed = "#10324A"
            text = "#EEF7FF"
        else:
            bg = "#141C23" if checked else "#131A20"
            hover = "#18232C"
            pressed = "#0F2D42"
            text = "#DCEEFF"
        return (
            "QToolButton { "
            f"background: {bg}; color: {text}; border: 1px solid {accent}; "
            f"border-radius: 10px; padding: {MENU_TEXT_UNDER_ICON_PADDING}; font-size: 11px; font-weight: 700; "
            "} "
            f"QToolButton:hover {{ background: {hover}; color: #F7FBFF; border-color: {accent}; }} "
            f"QToolButton:pressed {{ background: {pressed}; color: #FFFFFF; border: 1px solid {accent}; padding: {MENU_TEXT_UNDER_ICON_PADDING}; }} "
            "QToolButton:disabled { color: #66727D; background: #11171C; border-color: #22303A; }"
        )

    def _apply_menu_button_style(self, btn, *, checked: bool = False):
        accent = str(btn.property("menuAccent") or COLORS["accent"])
        emphasis = str(btn.property("menuEmphasis") or "toolbar")
        btn.setStyleSheet(self._menu_button_style(accent, checked=checked, emphasis=emphasis))

    def _small_button(self, text, icon_name, slot, color=None):
        accent = str(color or MENU_LEFT_ACCENT)
        btn = QToolButton()
        btn.setText(text)
        btn.setIcon(line_icon(icon_name, accent, 22))
        btn.setIconSize(QSize(MENU_SMALL_ICON, MENU_SMALL_ICON))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setFixedHeight(MENU_BUTTON_HEIGHT)
        btn.setFixedWidth(MENU_SMALL_WIDTH)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("menuAccent", accent)
        btn.setProperty("menuEmphasis", "toolbar")
        self._apply_menu_button_style(btn)
        btn.clicked.connect(slot)
        self._tool_buttons.append(btn)
        return btn

    def _wide_button(self, text, icon_name, slot, *, kind="toolbar", min_width=MENU_WIDE_WIDTH, accent=MENU_RIGHT_ACCENT):
        accent = str(accent or MENU_RIGHT_ACCENT)
        btn = QToolButton()
        btn.setText(text)
        btn.setIcon(line_icon(icon_name, accent, 22))
        btn.setIconSize(QSize(MENU_WIDE_ICON, MENU_WIDE_ICON))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setFixedHeight(MENU_BUTTON_HEIGHT)
        btn.setFixedWidth(min_width)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("menuAccent", accent)
        btn.setProperty("menuEmphasis", "toolbar")
        self._apply_menu_button_style(btn)
        btn.setProperty("expandedMinWidth", min_width)
        btn.clicked.connect(slot)
        self._tool_buttons.append(btn)
        return btn

    def _action_button(self, text, icon_name, slot, *, accent=MENU_CENTER_ACCENT):
        accent = str(accent or MENU_CENTER_ACCENT)
        btn = QToolButton()
        btn.setText(text)
        btn.setIcon(line_icon(icon_name, "#F5F7FA", 24))
        btn.setIconSize(QSize(MENU_ACTION_ICON, MENU_ACTION_ICON))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setFixedHeight(MENU_BUTTON_HEIGHT)
        btn.setFixedWidth(MENU_ACTION_WIDTH)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("menuAccent", accent)
        btn.setProperty("menuEmphasis", "action")
        self._apply_menu_button_style(btn)
        btn.clicked.connect(slot)
        self._tool_buttons.append(btn)
        return btn

    def _button_badge_text(self, icon_name: str, text: str) -> str:
        icon_name = str(icon_name or "").strip().lower()
        text = str(text or "").strip()
        return ""

    def _register_qml_button(self, btn, *, action_id: str, badge: str, accent: str, section: str, kind: str = "toolbar"):
        btn.setProperty("qmlActionId", action_id)
        btn.setProperty("qmlBadge", badge)
        btn.setProperty("qmlAccent", accent)
        btn.setProperty("qmlSection", section)
        btn.setProperty("qmlKind", kind)
        self._quick_action_buttons[action_id] = btn
        if section == "left":
            self._left_qml_buttons.append(btn)
        elif section == "center":
            self._center_qml_buttons.append(btn)
        else:
            self._right_qml_buttons.append(btn)

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
        profile = self._current_responsive_profile()
        self._sync_panel_height(profile)
        editor = self._active_editor()
        has_editor = editor is not None
        mode = normalize_work_mode(getattr(self.main_window, "_current_work_mode", EDITOR_MODE))
        for btn in (self.btn_start, self.btn_undo, self.btn_redo, self.btn_save):
            btn.setEnabled(has_editor)
        if mode == ROUGHCUT_MODE:
            roughcut = getattr(self.main_window, "_roughcut_widget", None)
            self.btn_start.setText("분석")
            self.btn_start.setEnabled(has_editor and roughcut is not None)
            engine_text = ""
            if roughcut is not None:
                engine_text = str(getattr(getattr(roughcut, "source_lbl", None), "text", lambda: "")() or "")
            self.engine_label.setText(engine_text)
        elif has_editor:
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
        self._sync_quick_shell()
        stt_on = bool(getattr(editor, "_stt_mode_enabled", False)) if editor is not None else False
        if hasattr(self, "btn_stt_mode"):
            stt_color = "#F5FBFF" if stt_on else MENU_LEFT_ACCENT
            self.btn_stt_mode.setText("음성")
            self.btn_stt_mode.setIcon(line_icon("mic", stt_color, 22))
            self.btn_stt_mode.setToolTip("STT 모드 ON" if stt_on else "STT 모드 OFF")
            self._apply_menu_button_style(self.btn_stt_mode, checked=stt_on)
        if hasattr(self, "btn_precision_refine"):
            precision_enabled = self._precision_refine_available_for_editor(editor)
            precision_color = MENU_LEFT_ACCENT if precision_enabled else "#66727D"
            self.btn_precision_refine.setText("정밀")
            self.btn_precision_refine.setEnabled(precision_enabled)
            self.btn_precision_refine.setIcon(line_icon("review", precision_color, 22))
            self.btn_precision_refine.setToolTip(
                "정밀 자막 작업" if precision_enabled else "자막 생성 완료 후 사용할 수 있습니다."
            )
            self._apply_menu_button_style(self.btn_precision_refine, checked=False)
        main = self.main_window
        auto_on = bool(getattr(main, "_auto_start_on", True))
        self.btn_auto_start.setText("자동")
        auto_color = "#F5FBFF" if auto_on else MENU_RIGHT_ACCENT
        self.btn_auto_start.setIcon(line_icon("auto", auto_color, 22))
        self._apply_menu_button_style(self.btn_auto_start, checked=auto_on)
        self.btn_auto_start.setToolTip("NAS/iCloud 자동시작 ON" if auto_on else "NAS/iCloud 자동시작 OFF")

        compact = self._should_icon_only()
        for btn in self._tool_buttons:
            if compact:
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                btn.setIconSize(QSize(MENU_WIDE_ICON, MENU_WIDE_ICON))
                btn.setFixedHeight(profile.menu_button_height)
                btn.setFixedWidth(max(profile.touch_target, btn.iconSize().width() + 16))
            else:
                if btn in (self.btn_start, self.btn_undo, self.btn_redo, self.btn_save):
                    btn.setIconSize(QSize(MENU_ACTION_ICON, MENU_ACTION_ICON))
                    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                    btn.setFixedHeight(profile.menu_button_height)
                    btn.setFixedWidth(max(profile.touch_target, MENU_ACTION_WIDTH))
                elif btn in (self.btn_auto_start, self.btn_help, self.btn_cache_clear):
                    btn.setIconSize(QSize(MENU_WIDE_ICON, MENU_WIDE_ICON))
                    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                    btn.setFixedHeight(profile.menu_button_height)
                    btn.setFixedWidth(max(profile.touch_target, int(btn.property("expandedMinWidth") or MENU_WIDE_WIDTH)))
                else:
                    btn.setIconSize(QSize(MENU_SMALL_ICON, MENU_SMALL_ICON))
                    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                    btn.setFixedHeight(profile.menu_button_height)
                    btn.setFixedWidth(max(profile.touch_target, MENU_SMALL_WIDTH))

    def _sync_panel_height(self, profile):
        panel_height = panel_visual_height_for_profile(profile)
        full_height = panel_outer_height_for_profile(profile)
        if self.height() != full_height:
            self.setFixedHeight(full_height)
        panel_shell = getattr(self, "_panel_shell", None)
        if panel_shell is not None and panel_shell.height() != panel_height:
            panel_shell.setFixedHeight(panel_height)
        outer_layout = getattr(self, "_outer_layout", None)
        if outer_layout is not None:
            outer_margins = outer_layout.contentsMargins()
            if (
                outer_margins.left() != 0
                or outer_margins.top() != 0
                or outer_margins.right() != 0
                or outer_margins.bottom() != 0
            ):
                outer_layout.setContentsMargins(0, 0, 0, 0)
        layout = getattr(self, "_root_layout", None)
        if layout is not None:
            margins = layout.contentsMargins()
            if margins.top() != 0 or margins.bottom() != 0:
                layout.setContentsMargins(8, 0, 8, 0)

    def visual_panel_height(self) -> int:
        panel_shell = getattr(self, "_panel_shell", None)
        if panel_shell is not None:
            return int(panel_shell.height() or 0)
        return int(self.height() or 0)

    def _current_responsive_profile(self):
        win = self.window()
        try:
            override = str(win.property("responsive_profile_override") or "")
        except Exception:
            override = ""
        try:
            width = int(win.width())
            height = int(win.height())
        except Exception:
            width = int(self.width() or 0)
            height = int(self.height() or 0)
        profile = responsive_profile_for_size(width, height, override=override)
        self._responsive_profile = profile
        return profile

    def _sync_start_icon(self):
        text = str(self.btn_start.text() or "")
        mode = normalize_work_mode(getattr(self.main_window, "_current_work_mode", EDITOR_MODE))
        if mode == ROUGHCUT_MODE:
            icon_name = "refresh"
        elif "처리" in text or "정지" in text:
            icon_name = "stop"
        elif "재시작" in text:
            icon_name = "refresh"
        else:
            icon_name = "play"
        self.btn_start.setIcon(line_icon(icon_name, "#F5F7FA", 24))

    def _should_icon_only(self):
        win = self.window()
        profile = self._current_responsive_profile()
        try:
            screen_w = win.screen().availableGeometry().width()
            return self.width() <= profile.menu_icon_only_width or win.width() <= int(screen_w * 0.55)
        except Exception:
            return self.width() <= profile.menu_icon_only_width

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh()
        shell = getattr(self, "_quick_shell", None)
        if shell is not None:
            shell.setGeometry(self.rect())
            shell.raise_()

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
        self._open_ai()

    def _open_speaker(self):
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_show_speaker_settings"):
            editor._show_speaker_settings()
        elif hasattr(self.main_window, "_open_main_speaker_settings"):
            self.main_window._open_main_speaker_settings()

    def _open_dictionary(self):
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_show_correction_dictionary"):
            editor._show_correction_dictionary()
        elif hasattr(self.main_window, "_open_main_correction_dictionary"):
            self.main_window._open_main_correction_dictionary()

    def _open_personalization(self):
        if hasattr(self.main_window, "_open_main_personalization_learning"):
            self.main_window._open_main_personalization_learning()

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
        self._open_export_dialog()

    def _open_export_dialog(self, output_mode: str | None = None, initial_tab: str | None = None):
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_show_export_dialog"):
            editor._show_export_dialog(output_mode=output_mode, initial_tab=initial_tab)
        elif hasattr(self.main_window, "_open_main_export_dialog"):
            self.main_window._open_main_export_dialog()

    def _toggle_stt_mode(self):
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_toggle_stt_mode"):
            editor._toggle_stt_mode()
        self.refresh()

    def _precision_refine_available_for_editor(self, editor) -> bool:
        if editor is None:
            return False
        checker = getattr(editor, "_precision_refine_available", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:
                return False
        getter = getattr(editor, "_get_current_segments", None)
        if callable(getter):
            try:
                return any(
                    isinstance(seg, dict)
                    and not bool(seg.get("is_gap"))
                    and bool(str(seg.get("text", "") or "").strip())
                    for seg in list(getter() or [])
                )
            except Exception:
                return False
        try:
            canvas = editor.timeline.canvas
            return bool(getattr(canvas, "segments", None))
        except Exception:
            return False

    def _run_precision_refine(self):
        editor = self._active_editor()
        if not self._precision_refine_available_for_editor(editor):
            self.refresh()
            return
        answer = ask_yes_no(
            self.window() or self,
            "정밀 작업",
            "정밀 작업 실행 할까요?",
            default_no=True,
        )
        if not answer:
            self.refresh()
            return
        starter = getattr(editor, "start_precision_subtitle_refinement", None)
        if callable(starter):
            starter()
        else:
            show_message(
                self.window() or self,
                "정밀 작업",
                "정밀 자막 작업을 시작할 수 없습니다.",
                icon=QMessageBox.Icon.Warning,
            )
        self.refresh()

    def _click_start(self):
        if normalize_work_mode(getattr(self.main_window, "_current_work_mode", EDITOR_MODE)) == ROUGHCUT_MODE:
            roughcut = getattr(self.main_window, "_roughcut_widget", None)
            if roughcut is not None and hasattr(roughcut, "run_main_action"):
                roughcut.run_main_action()
            self.refresh()
            return
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

    def _create_quick_shell(self):
        if not scenegraph_enabled("general"):
            return None
        qml_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "qml", "global_menu_bar.qml"))
        if not os.path.exists(qml_path):
            return None
        try:
            from PyQt6.QtQuickWidgets import QQuickWidget
        except Exception:
            return None
        try:
            shell = QQuickWidget(self)
            shell.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
            shell.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            shell.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            shell.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            shell.setClearColor(QColor(0, 0, 0, 0))
            shell.setSource(QUrl.fromLocalFile(qml_path))
            if shell.status() == QQuickWidget.Status.Error:
                shell.deleteLater()
                return None
            root = shell.rootObject()
            if root is not None and hasattr(root, "actionTriggered"):
                root.actionTriggered.connect(self._handle_quick_action)
            shell.setGeometry(self.rect())
            shell.show()
            shell.raise_()
            return shell
        except Exception:
            return None

    def _handle_quick_action(self, action_id: str):
        button = self._quick_action_buttons.get(str(action_id or ""))
        if button is not None and button.isEnabled():
            QTimer.singleShot(0, button.click)

    def automation_trigger_action(self, action_id: str) -> dict:
        normalized = str(action_id or "").strip()
        button = self._quick_action_buttons.get(normalized)
        if button is None:
            raise ValueError("global_menu_action_missing")
        if not button.isEnabled():
            raise ValueError("global_menu_action_disabled")
        text = str(button.text() or "")
        if normalized == "center_save":
            editor = self._active_editor()
            save_handler = getattr(editor, "_on_save", None) if editor is not None else None
            if callable(save_handler):
                save_handler(skip_auto_next=True, queue_learning=False, auto_export=False)
            else:
                button.click()
        else:
            button.click()
        self.refresh()
        return {
            "action_id": normalized,
            "text": text,
            "enabled": True,
        }

    def automation_action_snapshot(self) -> dict:
        actions = []
        for action_id, button in sorted(getattr(self, "_quick_action_buttons", {}).items()):
            try:
                text = str(button.text() or "")
            except Exception:
                text = ""
            try:
                enabled = bool(button.isEnabled())
            except Exception:
                enabled = False
            actions.append(
                {
                    "action_id": str(action_id or ""),
                    "text": text,
                    "enabled": enabled,
                }
            )
        return {
            "action_count": len(actions),
            "actions": actions,
        }

    def _qml_button_payload(self, btn) -> dict:
        return {
            "id": str(btn.property("qmlActionId") or ""),
            "text": str(btn.text() or ""),
            "badge": str(btn.property("qmlBadge") or ""),
            "accent": str(btn.property("qmlAccent") or "#A9B0B7"),
            "enabled": bool(btn.isEnabled()),
            "kind": str(btn.property("qmlKind") or "toolbar"),
        }

    def _sync_quick_shell(self):
        shell = getattr(self, "_quick_shell", None)
        if shell is None:
            return
        try:
            root = shell.rootObject()
            if root is None:
                return
            root.setProperty("leftItems", [self._qml_button_payload(btn) for btn in self._left_qml_buttons])
            root.setProperty("centerItems", [self._qml_button_payload(btn) for btn in self._center_qml_buttons])
            root.setProperty("rightItems", [self._qml_button_payload(btn) for btn in self._right_qml_buttons])
        except Exception:
            pass
