# Version: 01.00.01

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QSize, Qt, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QFont, QTextCursor, QBrush
import config

class TimestampArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setMouseTracking(True)
        self.ts_font = QFont("Menlo", 12)
        self._drag_start_line = -1 
        self._drag_current_y = -1
        self._drag_spk_color = None
        self._hovered_line = -1 
        self._hovered_delete_line = -1

    def sizeHint(self) -> QSize:
        return QSize(125, 0) 

    def wheelEvent(self, event):
        self.editor.wheelEvent(event)
        
    def _get_first_line_geom(self, block, top, height):
        """💡 [핵심] 블록 내 텍스트의 '첫 번째 줄'의 정확한 Y좌표와 높이만 추출합니다."""
        layout = block.layout()
        if layout.lineCount() > 0:
            line_rect = layout.lineAt(0).rect()
            return top + line_rect.y(), line_rect.height()
        return top, height

    def mousePressEvent(self, event):
        y, x = event.pos().y(), event.pos().x()
        block = self.editor.document().begin()
        while block.isValid():
            geom = self.editor.document().documentLayout().blockBoundingRect(block)
            top = geom.top() - self.editor.verticalScrollBar().value() + self.editor.viewportMargins().top()
            if top > self.editor.viewport().height(): break
            
            if top <= y <= top + geom.height():
                ud = block.userData()
                if hasattr(ud, 'start_sec') and not getattr(ud, 'is_gap', False):
                    line_num = block.blockNumber()
                    
                    # 마우스 클릭도 첫 줄 높이에 맞춰서 정밀 타격되도록 보정
                    first_line_top, first_line_height = self._get_first_line_geom(block, top, geom.height())
                    is_first_line_area = (first_line_top - 5 <= y <= first_line_top + first_line_height + 5)
                    
                    if event.button() == Qt.MouseButton.LeftButton:
                        if 5 <= x <= 25 and is_first_line_area: 
                            self.editor.timestamp_deleted.emit(line_num)
                        elif 100 <= x <= 120 and is_first_line_area: 
                            self._drag_start_line = line_num
                            self._drag_current_y = y
                            spk_id = getattr(ud, 'spk_id', '00')
                            _pw = getattr(self.editor, '_parent_widget', None)
                            speaker_colors = _pw._highlighter.speaker_colors if _pw and hasattr(_pw, '_highlighter') else {}
                            self._drag_spk_color = speaker_colors.get(spk_id, config.ACCENT)
                        else: 
                            self.editor.timestamp_clicked.emit(line_num, ud.start_sec)
                        event.accept()
                    elif event.button() == Qt.MouseButton.RightButton:
                        if is_first_line_area:
                            spk_id = getattr(ud, 'spk_id', '00')
                            gpos = self.mapToGlobal(event.pos())
                            self.editor.speaker_circle_clicked.emit(line_num, spk_id, gpos)
                            event.accept()
                break
            block = block.next()

    def mouseMoveEvent(self, event):
        y, x = event.pos().y(), event.pos().x()
        
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_start_line >= 0:
            self._drag_current_y = y; self.update(); return

        block = self.editor.document().begin()
        hovering, h_line, h_del_line = False, -1, -1
        
        while block.isValid():
            geom = self.editor.document().documentLayout().blockBoundingRect(block)
            top = geom.top() - self.editor.verticalScrollBar().value() + self.editor.viewportMargins().top()
            if top > self.editor.viewport().height(): break
            
            if top <= y <= top + geom.height():
                ud = block.userData()
                if hasattr(ud, 'start_sec') and not getattr(ud, 'is_gap', False):
                    first_line_top, first_line_height = self._get_first_line_geom(block, top, geom.height())
                    is_first_line_area = (first_line_top - 5 <= y <= first_line_top + first_line_height + 5)
                    
                    if is_first_line_area:
                        if 5 <= x <= 25: hovering = True; h_del_line = block.blockNumber()
                        elif x <= 120: hovering = True; h_line = block.blockNumber()
                    else:
                        if 25 < x < 100: hovering = True; h_line = block.blockNumber()
                break
            block = block.next()
            
        self.setCursor(Qt.CursorShape.PointingHandCursor if hovering else Qt.CursorShape.ArrowCursor)
        if self._hovered_line != h_line or self._hovered_delete_line != h_del_line:
            self._hovered_line, self._hovered_delete_line = h_line, h_del_line; self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_line >= 0:
            y = event.pos().y(); drop_line = -1
            block = self.editor.document().begin()
            while block.isValid():
                geom = self.editor.document().documentLayout().blockBoundingRect(block)
                top = geom.top() - self.editor.verticalScrollBar().value() + self.editor.viewportMargins().top()
                if top <= y <= top + geom.height(): drop_line = block.blockNumber(); break
                block = block.next()
                
            if drop_line >= 0 and drop_line != self._drag_start_line:
                self.editor.speaker_circle_dropped.emit(self._drag_start_line, drop_line)
            self._drag_start_line = -1; self._drag_current_y = -1; self.update()

    def leaveEvent(self, event):
        self._hovered_line = -1; self._hovered_delete_line = -1; self.update(); super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor(config.BG2)) 
        
        _pw = getattr(self.editor, '_parent_widget', None)
        speaker_colors = _pw._highlighter.speaker_colors if _pw and hasattr(_pw, '_highlighter') else {}
        current_line = self.editor.textCursor().blockNumber()
        block = self.editor.document().begin()
        
        while block.isValid():
            painter.setFont(self.ts_font) 
            
            geom = self.editor.document().documentLayout().blockBoundingRect(block)
            top = geom.top() - self.editor.verticalScrollBar().value() + self.editor.viewportMargins().top()
            height = geom.height()
            if top > self.editor.viewport().height(): break 
                
            if top + height >= 0:
                ud = block.userData()
                if hasattr(ud, 'start_sec'):
                    idx = block.blockNumber()
                    is_active = (idx == current_line or self._hovered_line == idx or self._hovered_delete_line == idx)
                    spk_color = speaker_colors.get(ud.spk_id, config.ACCENT)
                    
                    # 💡 [해결] 전체 높이(height) 대신, 첫 번째 줄의 중심 Y좌표를 계산하여 UI를 그립니다.
                    first_line_top, first_line_height = self._get_first_line_geom(block, top, height)
                    center_y = int(first_line_top + first_line_height / 2)
                    
                    # 1. [x] 버튼 그리기
                    if not getattr(ud, 'is_gap', False) and is_active:
                        is_del_h = (self._hovered_delete_line == idx)
                        btn_rect = QRect(5, center_y - 8, 16, 16)
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                        painter.setBrush(QBrush(QColor("#FF4444" if is_del_h else "#442222")))
                        painter.setPen(Qt.PenStyle.NoPen); painter.drawRoundedRect(btn_rect, 4, 4)
                        painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
                        painter.setPen(QColor("#FFFFFF" if is_del_h else "#FF8888"))
                        painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, "✕")
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                    
                    # 2. 타임태그 텍스트 그리기
                    painter.setFont(self.ts_font)
                    draw_ts = True
                    prev_b = block.previous()
                    if prev_b.isValid():
                        prev_ud = prev_b.userData()
                        if (hasattr(prev_ud, 'start_sec')
                                and prev_ud.start_sec == ud.start_sec
                                and not getattr(ud, 'is_gap', False)):
                            draw_ts = False
                    if draw_ts:
                        mins, secs = int(ud.start_sec) // 60, ud.start_sec % 60
                        ts_str = f"[{mins:02d}:{secs:05.2f}]"
                        painter.setPen(QColor(spk_color if is_active else ("#555555" if getattr(ud, 'is_gap', False) else config.ACCENT)))
                        painter.drawText(QRect(26, int(first_line_top), 80, int(first_line_height)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, ts_str)

                    # 3. 화자 동그라미 그리기
                    if not getattr(ud, 'is_gap', False):
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(QBrush(QColor(spk_color if is_active else "#444444")))
                        painter.drawEllipse(QPoint(108, center_y), 5 if is_active else 3, 5 if is_active else 3)
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            block = block.next()

        # 4. 드롭 중인 고스트 서클 그리기
        if self._drag_start_line >= 0 and self._drag_spk_color:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QBrush(QColor(self._drag_spk_color))); painter.setPen(QColor(255, 255, 255, 180))
            painter.drawEllipse(QPoint(108, self._drag_current_y), 6, 6)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)