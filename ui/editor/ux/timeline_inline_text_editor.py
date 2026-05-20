"""Opaque inline editor widget used by the 2D timeline canvas."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QTextOption
from PyQt6.QtWidgets import QFrame, QPlainTextEdit

from core.runtime.logger import get_logger


class TimelineInlineTextEdit(QPlainTextEdit):
    def __init__(self, canvas):
        super().__init__(canvas)
        self._canvas = canvas
        self.setObjectName("timelineInlineTextEdit")
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setProperty("timelineInlineEditorRole", "segment-inline-locked")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setTabChangesFocus(False)
        self.setUndoRedoEnabled(True)
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        if hasattr(Qt.WidgetAttribute, "WA_MacShowFocusRect"):
            self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.viewport().setAutoFillBackground(True)
        self.setAutoFillBackground(True)
        self.setContentsMargins(0, 0, 0, 0)
        self.setViewportMargins(0, 0, 0, 0)
        self.document().setDocumentMargin(0.0)
        self.document().setDefaultFont(canvas._subtitle_segment_font())
        self.setFont(canvas._subtitle_segment_font())
        self._background_color = "#163223"
        self._apply_inline_style()
        self.hide()
        self.textChanged.connect(self._on_text_changed)
        self.cursorPositionChanged.connect(self._on_cursor_changed)

    def _apply_inline_style(self) -> None:
        bg = str(getattr(self, "_background_color", "#163223") or "#163223")
        self.setStyleSheet(
            "QPlainTextEdit#timelineInlineTextEdit {"
            f" background: {bg};"
            " color: #DCE3EA;"
            " border: none;"
            " border-radius: 0px;"
            " padding: 0px;"
            " selection-background-color: rgba(68, 255, 136, 110);"
            " selection-color: #FFFFFF;"
            " }"
            " QPlainTextEdit#timelineInlineTextEdit > QWidget {"
            f" background: {bg};"
            " border: none;"
            " }"
        )

    def set_segment_background(self, color: str) -> None:
        bg = str(color or "#163223")
        if bg == getattr(self, "_background_color", ""):
            return
        self._background_color = bg
        self._apply_inline_style()

    def _on_text_changed(self):
        canvas = self._canvas
        if canvas is not None and getattr(canvas, "_edit_active", False):
            canvas._sync_inline_editor_state_from_widget(text_changed=True)

    def _on_cursor_changed(self):
        canvas = self._canvas
        if canvas is not None and getattr(canvas, "_edit_active", False):
            canvas._sync_inline_editor_state_from_widget(text_changed=False)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        canvas = getattr(self, "_canvas", None)
        if canvas is not None:
            QTimer.singleShot(0, canvas._maybe_commit_inline_edit_from_focus_out)

    def _pause_canvas_playback_for_keyboard_edit(self) -> None:
        canvas = getattr(self, "_canvas", None)
        request = getattr(canvas, "_request_canvas_pause_playback", None)
        if callable(request):
            try:
                request()
            except Exception as exc:
                get_logger().log(
                    f"⚠️ 타임라인 인라인 편집 중 재생 일시정지 요청 실패: {exc}",
                    level="WARN",
                    stage="ui",
                )

    def _should_pause_canvas_playback_for_keypress(self, event) -> bool:
        key = event.key()
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
        if key == Qt.Key.Key_Space and not (event.modifiers() & ~Qt.KeyboardModifier.ShiftModifier):
            return bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        return True

    def keyPressEvent(self, event):
        canvas = self._canvas
        if canvas is None or not getattr(canvas, "_edit_active", False):
            super().keyPressEvent(event)
            return

        if self._should_pause_canvas_playback_for_keypress(event):
            self._pause_canvas_playback_for_keyboard_edit()

        if event.key() == Qt.Key.Key_Space and not (event.modifiers() & ~Qt.KeyboardModifier.ShiftModifier):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                canvas._request_canvas_play_pause_toggle()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Escape:
            canvas._cancel_inline_edit()
            event.accept()
            return

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & (Qt.KeyboardModifier.MetaModifier | Qt.KeyboardModifier.ControlModifier):
                if hasattr(canvas, "_commit_inline_edit_with_speaker_split"):
                    canvas._commit_inline_edit_with_speaker_split()
                else:
                    canvas._commit_inline_edit_or_split()
                event.accept()
                return
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return
            canvas._commit_inline_edit_or_split()
            event.accept()
            return

        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        canvas = self._canvas
        if canvas is None:
            super().contextMenuEvent(event)
            return

        menu = self.createStandardContextMenu()
        menu.addSeparator()
        if bool(getattr(canvas, "_is_listening", False)):
            stop_action = QAction("음성인식 중지", menu)
            stop_action.triggered.connect(canvas._stop_listening)
            menu.addAction(stop_action)
        else:
            quality_action = QAction("음성으로 입력 (고품질)", menu)
            quality_action.triggered.connect(lambda: canvas._start_listening("quality"))
            fast_action = QAction("음성으로 입력 (빠름)", menu)
            fast_action.triggered.connect(lambda: canvas._start_listening("fast"))
            menu.addAction(quality_action)
            menu.addAction(fast_action)

        canvas._inline_editor_context_menu_open = True
        try:
            menu.exec(event.globalPos())
        finally:
            canvas._inline_editor_context_menu_open = False
            menu.deleteLater()
            if getattr(canvas, "_edit_active", False):
                self.setFocus(Qt.FocusReason.OtherFocusReason)


__all__ = ["TimelineInlineTextEdit"]
