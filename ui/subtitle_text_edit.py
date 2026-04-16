# Version: 01.00.00

import re
import time

from PyQt6.QtWidgets import QTextEdit, QWidget
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QMimeData, QRect, QSize
from PyQt6.QtGui import (
    QTextCursor, QTextCharFormat, QColor, QFont,
    QSyntaxHighlighter, QTextDocument, QKeyEvent, QTextBlockUserData, QPainter, QTextBlockFormat
)
import config
from ui.timestamp_area import TimestampArea

class SubtitleBlockData(QTextBlockUserData):
    def __init__(self, spk_id: str, start_sec: float, is_gap: bool = False):
        super().__init__()
        self.spk_id = spk_id
        self.start_sec = start_sec
        self.is_gap = is_gap

class SubtitleHighlighter(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument):
        super().__init__(document)
        self._edited_lines: set[int] = set()
        self._current_line: int = -1
        self.speaker_colors = {} 

    def mark_edited(self, line: int): 
        self._edited_lines.add(line); self.rehighlight()
        
    def set_current_line(self, line: int):
        if self._current_line != line: 
            self._current_line = line; self.rehighlight()

    def highlightBlock(self, text: str):
        block_num = self.currentBlock().blockNumber()
        if block_num in self._edited_lines:
            fmt = QTextCharFormat(); fmt.setBackground(QColor("#1E4D2B"))
            self.setFormat(0, len(text), fmt)
            
        ud = self.currentBlock().userData()
        spk_color = "#FFFFFF"
        if isinstance(ud, SubtitleBlockData): spk_color = self.speaker_colors.get(ud.spk_id, "#FFFFFF")

        if len(text) > 0:
            cfmt = QTextCharFormat()
            cfmt.setForeground(QColor(spk_color))
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
        self.setFont(QFont(config.FONT, 15))
        self.setStyleSheet(f"QTextEdit {{ background: {config.BG}; color: {config.FG}; border: none; padding: 16px; line-height: 1.5; }}")
        self.setUndoRedoEnabled(True)
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setCursorWidth(3)
        self.timestampArea = TimestampArea(self)
        self.document().documentLayout().documentSizeChanged.connect(self._update_margin)
        self.verticalScrollBar().valueChanged.connect(self.timestampArea.update)
        self.textChanged.connect(self.timestampArea.update)
        self.cursorPositionChanged.connect(self.timestampArea.update)
        
        self._key_press_time = {} 
        self.cursorPositionChanged.connect(self.cursor_moved.emit)
        self._update_margin()

    def focusInEvent(self, event):
        # 💡 [클릭 오지랖 완벽 삭제] 창이 켜지면서 커서가 잡힐 때 상태가 바뀌는 것을 원천 차단!
        # ✅ 수정
        parent = self.parent()
        if hasattr(parent, '_undo_mgr'):
            parent._undo_mgr.push_immediate()
        super().focusInEvent(event)

    # 💡 [추가] 에디터 바깥을 클릭 시 다시 켜기
    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        parent = getattr(self, "_parent_widget", None)
        if parent and hasattr(parent, "space_shortcut"):
            parent.space_shortcut.setEnabled(True)

    def update_margins(self):
        doc = self.document()
        doc.blockSignals(True)  # 💡 [핵심 추가] 여백 조절을 글자 수정으로 오해하지 않게 신호를 차단합니다!
        
        cur = QTextCursor(doc)
        cur.beginEditBlock() 
        block = doc.begin()
        prev_start = -1.0
        
        while block.isValid():
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
                
            if fmt.topMargin() != target_margin:
                fmt.setTopMargin(target_margin)
                cur.setPosition(block.position())
                cur.setBlockFormat(fmt)
                
            block = block.next()
        cur.endEditBlock()
        
        doc.blockSignals(False) # 💡 [신호 복구] 작업이 끝나면 다시 신호를 켭니다.

    def _update_margin(self):
        self.setViewportMargins(self.timestampArea.sizeHint().width(), 0, 0, 0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.timestampArea.setGeometry(QRect(cr.left(), cr.top(), self.timestampArea.sizeHint().width(), cr.height()))
        
        # 💡 [신규] 오버스크롤(Overscroll) 적용: 마지막 줄이 화면 중간에 오도록 하단 여백 추가!
        doc = self.document()
        doc.blockSignals(True)  # 💡 [핵심 추가] 창 크기가 변할 때 '편집 중'으로 넘어가는 오작동 완벽 차단!
        
        root_fmt = doc.rootFrame().frameFormat()
        # 현재 보이는 에디터 화면 높이의 딱 절반( // 2 )만큼 아래쪽에 투명한 쿠션을 깔아줍니다.
        root_fmt.setBottomMargin(self.viewport().height() // 2)
        doc.rootFrame().setFrameFormat(root_fmt)
        
        doc.blockSignals(False) # 💡 [신호 복구]

    def createMimeDataFromSelection(self) -> QMimeData:
        return super().createMimeDataFromSelection()

    def insertFromMimeData(self, source):
        if source.hasText():
            text = source.text()
            text = re.sub(r'[\[［<{\(]\s*\d{1,3}\s*[:.]\s*\d{1,2}\s*(?:[:.]\s*\d+)?\s*[\]］>}\)]\s*', '', text)
            self.insertPlainText(text)

    def mouseMoveEvent(self, event):
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
        self._clear_hover(); super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        # 💡 [수정] 왼쪽 버튼 드래그 후 마우스를 뗄 때 팝업을 띄우던 로직을 완전히 제거했습니다.
        # 이제 드래그만 해서는 아무 일도 일어나지 않습니다.

    def contextMenuEvent(self, event):
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

    def keyPressEvent(self, e: QKeyEvent):
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

        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            import time 
            current_time = time.time()
            if not hasattr(self, '_last_arrow_tap'): self._last_arrow_tap = {}
            last_time = self._last_arrow_tap.get(key, 0)
            if current_time - last_time <= 0.13: 
                if key == Qt.Key.Key_Left: cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                else: cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                self.setTextCursor(cur)
                self._last_arrow_tap[key] = 0 
                return 
            else:
                self._last_arrow_tap[key] = current_time
        
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
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
        self.setTextCursor(cur)
        self.document().contentsChanged.emit()
        
        if parent and hasattr(parent, "_highlighter"): parent._highlighter.rehighlight()
        if hasattr(self, 'timestampArea'): self.timestampArea.update()

    def _handle_simple_break(self):
        """Shift + Enter: 동일 자막 세그먼트 내에서 줄바꿈 (구조적 통일)"""
        cur = self.textCursor()
        cur.beginEditBlock()
        # 💡 핵심: 블록을 쪼개지 않고 소프트 줄바꿈(\u2028)을 삽입합니다.
        # 이렇게 하면 하나의 SubtitleBlockData(시간 정보)를 공유하게 됩니다. 
        cur.insertText("\u2028") 
        cur.endEditBlock()
        
        self.setTextCursor(cur)
        self.document().contentsChanged.emit() # 세그먼트 갱신 신호 발생
        
        # 💡 UndoManager 스냅샷 즉시 저장 
        parent = getattr(self, "_parent_widget", None)
        if parent and hasattr(parent, "_undo_mgr"):
            parent._undo_mgr.push_immediate()

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
        new_sec = round(new_sec, 2)
        
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
        self.setTextCursor(cur)
        
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