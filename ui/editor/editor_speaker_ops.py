# Version: 03.01.05
# Phase: PHASE1-B
"""
EditorWidget 화자 메뉴 / 화자 드래그 조작 Mixin.
"""
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap, QTextCursor
from PyQt6.QtWidgets import QMenu

from core.runtime import config
from ui.editor.subtitle_text_edit import SubtitleBlockData
from ui.editor.editor_helpers import get_sub_block_indices


class EditorSpeakerOpsMixin:
    def _show_speaker_circle_menu(self, line_num: int, current_spk_id: str, gpos: QPoint):
        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu {{ background-color: {config.BG2}; color: {config.FG}; border: 1px solid {config.BG3}; font-size: 13px; padding: 4px; }} QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }} QMenu::item:selected {{ background-color: #444444; }}")
        max_spk = int(self.settings.get("max_speakers", 1))
        spk_map = {
            "00": self.settings.get("spk1_color", "#FFFFFF"),
            "01": self.settings.get("spk2_color", "#FFFF00"),
            "02": self.settings.get("spk3_color", "#00FFFF")
        }
        available_spks = [f"{i:02d}" for i in range(max_spk)]

        def make_circle_icon(color_hex):
            pixmap = QPixmap(24, 24)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(color_hex))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(4, 4, 16, 16)
            painter.end()
            return QIcon(pixmap)

        added = 0
        for spk in available_spks:
            if spk == current_spk_id:
                continue
            color_hex = spk_map.get(spk, "#FFFFFF")
            spk_idx = int(spk) + 1 if str(spk).isdigit() else 1
            spk_name = str(self.settings.get(f"spk{spk_idx}_name", "") or f"화자 {spk_idx}")
            action = menu.addAction(make_circle_icon(color_hex), f"{spk_name}로 변경")
            action.triggered.connect(lambda checked, s=spk: self._change_speaker_for_line(line_num, s))
            added += 1
        if added > 0:
            menu.exec(gpos)

    def _change_speaker_for_line(self, line_num: int, new_spk_id: str):
        self._undo_mgr.push_immediate()
        doc = self.text_edit.document()
        block = doc.findBlockByNumber(line_num)
        if not block.isValid():
            return
        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData):
            return

        ud.spk_id = new_spk_id
        for idx in get_sub_block_indices(doc, line_num, ud.start_sec)[1:]:
            u = doc.findBlockByNumber(idx).userData()
            if isinstance(u, SubtitleBlockData):
                u.spk_id = new_spk_id

        self._highlighter.rehighlight()
        self._finalize_edit()

    def _on_speaker_circle_dropped(self, from_line: int, to_line: int):
        self._undo_mgr.push_immediate()
        if from_line == to_line:
            return
        doc = self.text_edit.document()
        start_idx = min(from_line, to_line)
        end_idx = max(from_line, to_line)
        blocks_data = []
        for i in range(start_idx, end_idx + 1):
            b = doc.findBlockByNumber(i)
            ud = b.userData()
            new_ud = SubtitleBlockData(ud.spk_id, ud.start_sec, ud.is_gap) if ud else None
            blocks_data.append({"text": b.text(), "ud": new_ud})
        if from_line < to_line:
            item = blocks_data.pop(0)
            blocks_data.append(item)
        else:
            item = blocks_data.pop()
            blocks_data.insert(0, item)
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        for i, idx in enumerate(range(start_idx, end_idx + 1)):
            b = doc.findBlockByNumber(idx)
            cursor.setPosition(b.position())
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(blocks_data[i]["text"])
            new_b = doc.findBlockByNumber(idx)
            if blocks_data[i]["ud"]:
                new_b.setUserData(blocks_data[i]["ud"])

        cursor.endEditBlock()
        self._highlighter.rehighlight()
        self._finalize_edit()
