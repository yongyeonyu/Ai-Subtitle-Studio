# Version: 03.10.02
# Phase: PHASE2

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QSize, Qt, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QFont, QBrush
from core.runtime import config


class _SnapshotBlockUserData:
    def __init__(self, meta: dict):
        self.spk_id = str(meta.get("spk_id", "00") or "00")
        self.start_sec = float(meta.get("start_sec", 0.0) or 0.0)
        self.end_sec = meta.get("end_sec")
        self.is_gap = bool(meta.get("is_gap", False))


class TimestampArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setMouseTracking(True)
        self.ts_font = QFont("Menlo", 11)
        self.delete_font = QFont("Arial", 9, QFont.Weight.Bold)
        self._drag_start_line = -1 
        self._drag_current_y = -1
        self._drag_spk_color = None
        self._hovered_line = -1 
        self._hovered_delete_line = -1

    def sizeHint(self) -> QSize:
        return QSize(150, 0)

    def wheelEvent(self, event):
        handler = getattr(self.editor, "apply_wheel_scroll_event", None)
        if callable(handler) and handler(event):
            return
        self.editor.wheelEvent(event)
        
    def _get_first_line_geom(self, block, top, height):
        """💡 [핵심] 블록 내 텍스트의 '첫 번째 줄'의 정확한 Y좌표와 높이만 추출합니다."""
        layout = block.layout()
        if layout.lineCount() > 0:
            line_rect = layout.lineAt(0).rect()
            return top + line_rect.y(), line_rect.height()
        return top, height

    def _content_probe_point(self, y: int) -> QPoint:
        margin_left = 0
        try:
            margin_left = int(self.editor.viewportMargins().left())
        except Exception:
            margin_left = 0
        return QPoint(max(0, margin_left + 8), max(0, int(y or 0)))

    def _block_top(self, block) -> float:
        geom = self.editor.document().documentLayout().blockBoundingRect(block)
        return self._block_top_from_geom(geom)

    def _block_top_from_geom(self, geom) -> float:
        return geom.top() - self.editor.verticalScrollBar().value() + self.editor.viewportMargins().top()

    def _block_at_y(self, y: int):
        try:
            cur = self.editor.cursorForPosition(self._content_probe_point(y))
            block = cur.block()
        except Exception:
            block = self.editor.document().begin()
        if not block.isValid():
            return block
        prev_block = block.previous()
        if prev_block.isValid():
            try:
                prev_geom = self.editor.document().documentLayout().blockBoundingRect(prev_block)
                prev_top = self._block_top_from_geom(prev_geom)
                if prev_top <= y <= prev_top + prev_geom.height():
                    return prev_block
            except Exception:
                pass
        return block

    def _visible_start_block_for_y(self, y: int):
        block = self._block_at_y(max(0, int(y or 0)))
        if block.isValid() and block.previous().isValid():
            return block.previous()
        return block if block.isValid() else self.editor.document().begin()

    def _visible_start_block(self):
        return self._visible_start_block_for_y(0)

    def _block_user_data(self, block):
        ud = block.userData()
        try:
            getattr(ud, "start_sec")
            canonical_snapshot = getattr(self.editor, "_canonical_timestamp_block_meta_snapshot", None)
            canonical_text_snapshot = getattr(self.editor, "_canonical_timestamp_block_text_snapshot", None)
            meta = canonical_snapshot.get(int(block.blockNumber())) if isinstance(canonical_snapshot, dict) else None
            if isinstance(meta, dict):
                expected = canonical_text_snapshot.get(int(block.blockNumber())) if isinstance(canonical_text_snapshot, dict) else None
                normalized_block = " ".join(str(block.text() or "").replace("\u2028", "\n").split())
                normalized_expected = " ".join(str(expected or "").replace("\u2028", "\n").split())
                if not normalized_expected or normalized_block == normalized_expected:
                    try:
                        current_start = float(getattr(ud, "start_sec", 0.0) or 0.0)
                        canonical_start = float(meta.get("start_sec", 0.0) or 0.0)
                        current_gap = bool(getattr(ud, "is_gap", False))
                        canonical_gap = bool(meta.get("is_gap", False))
                        if abs(current_start - canonical_start) > 0.01 or current_gap != canonical_gap:
                            return _SnapshotBlockUserData(meta)
                    except Exception:
                        return _SnapshotBlockUserData(meta)
            return ud
        except Exception:
            pass
        try:
            canonical_snapshot = getattr(self.editor, "_canonical_timestamp_block_meta_snapshot", None)
            canonical_text_snapshot = getattr(self.editor, "_canonical_timestamp_block_text_snapshot", None)
            meta = canonical_snapshot.get(int(block.blockNumber())) if isinstance(canonical_snapshot, dict) else None
            if isinstance(meta, dict):
                expected = canonical_text_snapshot.get(int(block.blockNumber())) if isinstance(canonical_text_snapshot, dict) else None
                normalized_block = " ".join(str(block.text() or "").replace("\u2028", "\n").split())
                normalized_expected = " ".join(str(expected or "").replace("\u2028", "\n").split())
                if not normalized_expected or normalized_block == normalized_expected:
                    return _SnapshotBlockUserData(meta)
        except Exception:
            pass
        try:
            snapshot = getattr(self.editor, "_timestamp_block_meta_snapshot", None)
            meta = snapshot.get(int(block.blockNumber())) if isinstance(snapshot, dict) else None
            if isinstance(meta, dict):
                return _SnapshotBlockUserData(meta)
            if meta is not None:
                getattr(meta, "start_sec")
                return meta
        except Exception:
            pass
        try:
            parent = getattr(self.editor, "_parent_widget", None)
            if parent is not None:
                line_num = int(block.blockNumber())
                line_map = getattr(parent, "_cached_line_map", None)
                if not isinstance(line_map, dict):
                    refresher = getattr(parent, "_refresh_cached_line_map", None)
                    line_map = refresher() if callable(refresher) else {}
                if not isinstance(line_map, dict) or line_num not in line_map:
                    timeline_restore = getattr(parent, "_timestamp_restore_line_map_from_timeline", None)
                    timeline_line_map = timeline_restore() if callable(timeline_restore) else {}
                    if isinstance(timeline_line_map, dict) and timeline_line_map:
                        merged_line_map = dict(timeline_line_map)
                        if isinstance(line_map, dict):
                            merged_line_map.update(line_map)
                        line_map = merged_line_map
                seg = line_map.get(line_num) if isinstance(line_map, dict) else None
                if isinstance(seg, dict):
                    matcher = getattr(parent, "_segment_matches_block_text", None)
                    if callable(matcher) and not matcher(seg, block.text()):
                        return ud
                    start_sec = float(seg.get("start", 0.0) or 0.0)
                    end_sec = seg.get("end")
                    try:
                        end_sec = float(end_sec) if end_sec is not None else None
                    except Exception:
                        end_sec = None
                    return _SnapshotBlockUserData(
                        {
                            "spk_id": seg.get("speaker", seg.get("spk", "00")),
                            "start_sec": start_sec,
                            "end_sec": end_sec,
                            "is_gap": bool(seg.get("is_gap", False)),
                        }
                    )
        except Exception:
            pass
        return ud

    def _line_update_rect(self, line_num: int, *, pad_y: int = 6) -> QRect:
        try:
            block = self.editor.document().findBlockByNumber(int(line_num))
        except Exception:
            return QRect()
        if not block.isValid():
            return QRect()
        try:
            geom = self.editor.document().documentLayout().blockBoundingRect(block)
            top = int(self._block_top_from_geom(geom)) - int(pad_y)
            height = int(max(1.0, geom.height())) + int(pad_y) * 2
            return QRect(0, top, max(1, int(self.width())), height).intersected(self.rect())
        except Exception:
            return QRect()

    def _update_lines(self, *line_nums: int):
        dirty = QRect()
        requested = False
        for line_num in line_nums:
            try:
                line_key = int(line_num)
            except Exception:
                continue
            if line_key < 0:
                continue
            requested = True
            rect = self._line_update_rect(line_key)
            if rect.isValid() and not rect.isEmpty():
                dirty = rect if dirty.isNull() else dirty.united(rect)
        if dirty.isValid() and not dirty.isEmpty():
            self.update(dirty)
        elif not requested:
            self.update()

    def _drag_ghost_rect(self, y: int) -> QRect:
        try:
            y = int(y)
        except Exception:
            return QRect()
        if y < -24:
            return QRect()
        return QRect(114, y - 16, 30, 32).intersected(self.rect())

    def _update_drag_ghost(self, old_y: int, new_y: int):
        dirty = QRect()
        for y in (old_y, new_y):
            rect = self._drag_ghost_rect(y)
            if rect.isValid() and not rect.isEmpty():
                dirty = rect if dirty.isNull() else dirty.united(rect)
        if dirty.isValid() and not dirty.isEmpty():
            self.update(dirty)

    def mousePressEvent(self, event):
        if hasattr(self.editor, "is_selection_locked") and self.editor.is_selection_locked():
            event.accept()
            return
        y, x = event.pos().y(), event.pos().x()
        block = self._block_at_y(y)
        if not block.isValid():
            return
        geom = self.editor.document().documentLayout().blockBoundingRect(block)
        top = self._block_top_from_geom(geom)
        if not (top <= y <= top + geom.height()):
            return
        ud = self._block_user_data(block)
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
                    self._update_lines(line_num)
                else:
                    self.editor.timestamp_clicked.emit(line_num, ud.start_sec)
                event.accept()
            elif event.button() == Qt.MouseButton.RightButton:
                if is_first_line_area:
                    spk_id = getattr(ud, 'spk_id', '00')
                    gpos = self.mapToGlobal(event.pos())
                    self.editor.speaker_circle_clicked.emit(line_num, spk_id, gpos)
                    event.accept()

    def mouseMoveEvent(self, event):
        if hasattr(self.editor, "is_selection_locked") and self.editor.is_selection_locked():
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        y, x = event.pos().y(), event.pos().x()

        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_start_line >= 0:
            old_y = self._drag_current_y
            self._drag_current_y = y
            self._update_drag_ghost(old_y, y)
            return

        hovering, h_line, h_del_line = False, -1, -1
        block = self._block_at_y(y)
        if block.isValid():
            geom = self.editor.document().documentLayout().blockBoundingRect(block)
            top = self._block_top_from_geom(geom)
            if top <= y <= top + geom.height():
                ud = self._block_user_data(block)
                if hasattr(ud, 'start_sec') and not getattr(ud, 'is_gap', False):
                    first_line_top, first_line_height = self._get_first_line_geom(block, top, geom.height())
                    is_first_line_area = (first_line_top - 5 <= y <= first_line_top + first_line_height + 5)

                    if is_first_line_area:
                        if 5 <= x <= 25:
                            hovering = True
                            h_del_line = block.blockNumber()
                        elif x <= 120:
                            hovering = True
                            h_line = block.blockNumber()
                    else:
                        if 25 < x < 100:
                            hovering = True
                            h_line = block.blockNumber()
            
        self.setCursor(Qt.CursorShape.PointingHandCursor if hovering else Qt.CursorShape.ArrowCursor)
        if self._hovered_line != h_line or self._hovered_delete_line != h_del_line:
            old_line = self._hovered_line
            old_del_line = self._hovered_delete_line
            self._hovered_line, self._hovered_delete_line = h_line, h_del_line
            self._update_lines(old_line, old_del_line, h_line, h_del_line)

    def mouseReleaseEvent(self, event):
        if hasattr(self.editor, "is_selection_locked") and self.editor.is_selection_locked():
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_line >= 0:
            y = event.pos().y()
            drop_line = -1
            block = self._block_at_y(y)
            if block.isValid():
                geom = self.editor.document().documentLayout().blockBoundingRect(block)
                top = self._block_top_from_geom(geom)
                if top <= y <= top + geom.height():
                    drop_line = block.blockNumber()
                
            if drop_line >= 0 and drop_line != self._drag_start_line:
                self.editor.speaker_circle_dropped.emit(self._drag_start_line, drop_line)
            old_line = self._drag_start_line
            old_y = self._drag_current_y
            self._drag_start_line = -1
            self._drag_current_y = -1
            self._update_drag_ghost(old_y, -1)
            self._update_lines(old_line, drop_line)

    def leaveEvent(self, event):
        old_line = self._hovered_line
        old_del_line = self._hovered_delete_line
        self._hovered_line = -1
        self._hovered_delete_line = -1
        self._update_lines(old_line, old_del_line)
        super().leaveEvent(event)

    def paintEvent(self, event):
        if bool(getattr(self, "_shutdown_in_progress", False) or getattr(self.editor, "_shutdown_in_progress", False)):
            return
        painter = QPainter(self)
        if not painter.isActive():
            return
        paint_rect = event.rect()
        painter.fillRect(paint_rect, QColor("#11181C"))
        
        _pw = getattr(self.editor, '_parent_widget', None)
        speaker_colors = _pw._highlighter.speaker_colors if _pw and hasattr(_pw, '_highlighter') else {}
        current_line = self.editor.textCursor().blockNumber()
        block = self._visible_start_block_for_y(paint_rect.top())
        paint_bottom = paint_rect.bottom()
        doc = self.editor.document()
        layout = doc.documentLayout()
        scroll_y = self.editor.verticalScrollBar().value()
        margin_top = self.editor.viewportMargins().top()
        ts_font = self.ts_font
        delete_font = self.delete_font
        hovered_line = self._hovered_line
        hovered_delete_line = self._hovered_delete_line
        accent = config.ACCENT
        painter.setFont(ts_font)
        
        while block.isValid():
            geom = layout.blockBoundingRect(block)
            top = geom.top() - scroll_y + margin_top
            height = geom.height()
            if top > paint_bottom: break
                
            if top + height >= 0:
                ud = self._block_user_data(block)
                if hasattr(ud, 'start_sec'):
                    idx = block.blockNumber()
                    is_active = (idx == current_line or hovered_line == idx or hovered_delete_line == idx)
                    spk_color = speaker_colors.get(getattr(ud, "spk_id", "00"), accent)
                    
                    # 💡 [해결] 전체 높이(height) 대신, 첫 번째 줄의 중심 Y좌표를 계산하여 UI를 그립니다.
                    first_line_top, first_line_height = self._get_first_line_geom(block, top, height)
                    center_y = int(first_line_top + first_line_height / 2)
                    
                    # 1. [x] 버튼 그리기
                    if not getattr(ud, 'is_gap', False) and is_active:
                        is_del_h = (hovered_delete_line == idx)
                        btn_rect = QRect(5, center_y - 8, 16, 16)
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                        painter.setBrush(QBrush(QColor("#FF4444" if is_del_h else "#442222")))
                        painter.setPen(Qt.PenStyle.NoPen); painter.drawRoundedRect(btn_rect, 4, 4)
                        painter.setFont(delete_font)
                        painter.setPen(QColor("#FFFFFF" if is_del_h else "#FF8888"))
                        painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, "✕")
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                    
                    # 2. 타임태그 텍스트 그리기
                    painter.setFont(ts_font)
                    draw_ts = True
                    prev_b = block.previous()
                    if prev_b.isValid():
                        prev_ud = self._block_user_data(prev_b)
                        if (hasattr(prev_ud, 'start_sec')
                                and prev_ud.start_sec == ud.start_sec
                                and not getattr(ud, 'is_gap', False)):
                            draw_ts = False
                    if draw_ts:
                        mins, secs = int(ud.start_sec) // 60, ud.start_sec % 60
                        ts_str = f"[{mins:02d}:{secs:05.2f}]"
                        painter.setPen(QColor(spk_color if is_active else ("#555555" if getattr(ud, 'is_gap', False) else accent)))
                        painter.drawText(QRect(28, int(first_line_top), 96, int(first_line_height)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, ts_str)

                    # 3. 화자 동그라미 그리기
                    if not getattr(ud, 'is_gap', False):
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(QBrush(QColor(spk_color if is_active else "#444444")))
                        painter.drawEllipse(QPoint(128, center_y), 5 if is_active else 3, 5 if is_active else 3)
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            block = block.next()

        # 4. 드롭 중인 고스트 서클 그리기
        if self._drag_start_line >= 0 and self._drag_spk_color:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QBrush(QColor(self._drag_spk_color))); painter.setPen(QColor(255, 255, 255, 180))
            painter.drawEllipse(QPoint(128, self._drag_current_y), 6, 6)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
