# Version: 03.14.02
# Phase: PHASE2
"""
ui/editor_popup_qt.py  ─ 단어 교정 팝업
[개편] 타임스탬프 독립 마진 구조에 맞춰 SubtitleBlockData 연동 완비
"""
from PyQt6.QtWidgets import QWidget, QLabel, QLineEdit, QVBoxLayout, QApplication
from PyQt6.QtCore    import Qt
from PyQt6.QtGui     import QTextCursor, QFont

from core.runtime import config

class EditorPopup(QWidget):
    """우클릭 → 즉시 텍스트 입력창 표시 (메뉴 없음)."""

    def __init__(self, owner, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.owner = owner

        self._info   = {}
        self._worker = None   

        self._build_ui()
        self.hide()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.setStyleSheet(
            "EditorPopup { "
            "  background: #222222; "
            f" border: 1px solid {config.ACCENT}; "
            "  border-radius: 0px; "
            "}"
        )

        self._label = QLabel("✏️ 텍스트 변경")
        self._label.setFont(QFont(config.FONT, 11, QFont.Weight.Bold))
        self._label.setStyleSheet(
            f"QLabel {{ color: {config.ACCENT}; background: #222222; padding: 6px 14px 2px 14px; }}"
        )
        lay.addWidget(self._label)

        self._entry = QLineEdit()
        self._entry.setFont(QFont(config.FONT, 13))
        self._entry.setStyleSheet(
            "QLineEdit { background: #333333; color: #FFFFFF; "
            "border: none; padding: 6px 14px; }"
        )
        self._entry.returnPressed.connect(self._on_confirm)
        self._entry.installEventFilter(self)
        lay.addWidget(self._entry)

        self.setMinimumWidth(320)

    def trigger(self, root_word, anchor, end_cur, gpos):
        self._info = {"root": root_word, "anchor": anchor, "end": end_cur}

        self._entry.setText(root_word)
        self._entry.selectAll()

        self.adjustSize()

        screen = QApplication.screenAt(gpos)
        if not screen:
            screen = QApplication.primaryScreen()
        scr = screen.geometry()

        x = min(gpos.x() + 15, scr.right() - self.width() - 4)
        y = min(gpos.y() + 15, scr.bottom() - self.height() - 4)
        
        x = max(scr.left(), x)
        y = max(scr.top(), y)

        self.move(x, y)
        self.show()
        self.raise_()
        self._entry.setFocus()

    def navigate(self, direction):
        pass  

    def confirm(self):
        self._on_confirm()

    def _on_confirm(self):
        new_w = self._entry.text().strip()
        if new_w:
            self._apply(new_w)
        self.close_popup(refocus=True)

    def _apply(self, new_word):
        root   = self._info.get("root", "")
        anchor = self._info.get("anchor")
        end_c  = self._info.get("end")
        te     = self.owner.text_edit

        if not (root and anchor and end_c):
            return

        replace_count = 0
        if hasattr(self.owner, "_replace_text_in_all_subtitles"):
            replace_count = self.owner._replace_text_in_all_subtitles(
                root,
                new_word,
                anchor=anchor,
                end_cursor=end_c,
            )
        else:
            cur = te.textCursor()
            cur.beginEditBlock()
            cur.setPosition(anchor.position())
            cur.setPosition(end_c.position(), QTextCursor.MoveMode.KeepAnchor)
            cur.insertText(new_word)
            cur.endEditBlock()
            te.setTextCursor(cur)
            replace_count = 1

            hl = getattr(self.owner, "_highlighter", None)
            if hl and hasattr(hl, "mark_edited"):
                hl.mark_edited(cur.blockNumber())

        if replace_count and hasattr(self.owner, "_save_correction"):
            self.owner._save_correction(root, new_word)

    def close_popup(self, refocus=False):
        self._info = {}
        self.hide()
        if self._worker:
            self._worker.quit()
            self._worker = None
        if refocus:
            self.owner.text_edit.setFocus()

    def is_visible(self):
        return self.isVisible()

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj == self._entry and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.close_popup(refocus=True)
                return True
                
        return False
