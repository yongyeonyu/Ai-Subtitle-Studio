# Version: 03.01.05
# Phase: PHASE1-B
"""
EditorWidget 화자 메뉴 / 화자 드래그 조작 Mixin.
"""
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QTextCursor

from core.speaker_profile_settings import normalize_speaker_id, visible_speaker_slots
from ui.dialogs.qml_popup import show_context_menu
from ui.editor.subtitle_text_edit import SubtitleBlockData
from ui.editor.editor_helpers import get_sub_block_indices
from ui.timeline.speaker_labels import current_speaker_settings
from ui.style import COLORS


class EditorSpeakerOpsMixin:
    def _show_speaker_circle_menu(self, line_num: int, current_spk_id: str, gpos: QPoint):
        current_spk_id = normalize_speaker_id(current_spk_id)
        settings = current_speaker_settings(getattr(self, "settings", {}) or {})
        slot_map = {
            normalize_speaker_id(row.get("id", "00")): row
            for row in visible_speaker_slots(settings)
        }
        items = []
        for spk, row in slot_map.items():
            if spk == current_spk_id:
                continue
            color_hex = str(row.get("color", COLORS["warning"]) or COLORS["warning"])
            spk_name = str(row.get("name", "") or "화자")
            items.append(
                {
                    "id": spk,
                    "label": f"{spk_name}로 변경",
                    "accent": color_hex,
                }
            )
        chosen = show_context_menu(self, gpos, items)
        if chosen:
            self._change_speaker_for_line(line_num, chosen)

    def _change_speaker_for_line(self, line_num: int, new_spk_id: str):
        self._undo_mgr.push_immediate()
        doc = self.text_edit.document()
        block = doc.findBlockByNumber(line_num)
        if not block.isValid():
            return
        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData):
            return
        if self._try_nle_change_speaker_for_line_commit(line_num, new_spk_id, ud):
            return

        ud.spk_id = new_spk_id
        for idx in get_sub_block_indices(doc, line_num, ud.start_sec)[1:]:
            u = doc.findBlockByNumber(idx).userData()
            if isinstance(u, SubtitleBlockData):
                u.spk_id = new_spk_id

        self._highlighter.rehighlight()
        self._finalize_edit()

    def _try_nle_change_speaker_for_line_commit(self, line_num: int, new_spk_id: str, ud: SubtitleBlockData) -> bool:
        nle_text_edit = getattr(self, "_nle_live_editor_caption_text_edit_result", None)
        reloader = getattr(self, "_reload_segments_from_list", None)
        if not callable(nle_text_edit) or not callable(reloader):
            return False
        if bool(
            getattr(ud, "is_gap", False)
            or getattr(ud, "stt_pending", False)
            or getattr(ud, "stt_mode", False)
            or getattr(ud, "live_preview", False)
        ):
            return False
        doc = self.text_edit.document()
        try:
            sub_indices = list(get_sub_block_indices(doc, int(line_num), float(getattr(ud, "start_sec"))))
        except Exception:
            return False
        if len(sub_indices) != 1 or int(sub_indices[0]) != int(line_num):
            return False
        block = doc.findBlockByNumber(int(line_num))
        if not block.isValid():
            return False
        raw_text = block.text()
        if "\u2028" in raw_text:
            return False
        text = raw_text.replace("\u2028", "\n").strip()
        if not text:
            return False
        try:
            start_sec = float(getattr(ud, "start_sec"))
        except Exception:
            return False
        end_sec = getattr(ud, "end_sec", None)
        try:
            end_sec = float(end_sec) if end_sec is not None else None
        except Exception:
            end_sec = None
        try:
            current_segments = list(self._get_current_segments(force_rebuild=True))
        except Exception:
            return False
        if end_sec is None or end_sec <= start_sec:
            for seg in current_segments:
                if not isinstance(seg, dict):
                    continue
                try:
                    if int(seg.get("line", -1)) != int(line_num):
                        continue
                    if abs(float(seg.get("start", 0.0) or 0.0) - start_sec) >= 0.05:
                        continue
                    end_sec = float(seg.get("end", start_sec) or start_sec)
                    text = str(seg.get("text", text) or text).replace("\u2028", "\n").strip()
                    break
                except Exception:
                    continue
        if end_sec is None or end_sec <= start_sec or not text:
            return False
        speaker = str(new_spk_id or "").strip()
        if not speaker:
            return False
        nle_result = nle_text_edit(
            current_segments=current_segments,
            line_num=int(line_num),
            start_sec=float(start_sec),
            end_sec=float(end_sec),
            new_text=text,
            new_speaker=speaker,
            new_speaker_list=[speaker],
            commit_source="timeline_speaker_change",
        )
        if nle_result is None:
            return False

        self._last_nle_live_editor_operation = nle_result.operation.to_dict()
        self._last_nle_live_editor_projection = nle_result.after_projection.to_dict()
        reloader(list(nle_result.projected_rows), preserve_view=True, mark_dirty=True)
        finalizer = getattr(self, "_finalize_manual_edit_snapshot", None)
        if callable(finalizer):
            finalizer(allow_revision_drift=True)
        else:
            self._finalize_edit()
        return True

    def _speaker_drop_group_bounds(self, from_line: int, to_line: int):
        doc = self.text_edit.document()

        def _block_timing(line: int):
            block = doc.findBlockByNumber(int(line))
            if not block.isValid():
                return None
            ud = block.userData()
            if not isinstance(ud, SubtitleBlockData) or bool(getattr(ud, "is_gap", False)):
                return None
            try:
                start = float(getattr(ud, "start_sec"))
            except Exception:
                return None
            end = getattr(ud, "end_sec", None)
            try:
                end_value = float(end) if end is not None else start
            except Exception:
                end_value = start
            return start, end_value

        anchor = _block_timing(from_line)
        target = _block_timing(to_line)
        if anchor is None or target is None:
            return None
        if abs(anchor[0] - target[0]) >= 0.05 or abs(anchor[1] - target[1]) >= 0.05:
            return None

        group_start = int(from_line)
        while group_start > 0:
            prev = _block_timing(group_start - 1)
            if prev is None or abs(prev[0] - anchor[0]) >= 0.05 or abs(prev[1] - anchor[1]) >= 0.05:
                break
            group_start -= 1

        group_end = int(from_line)
        while group_end + 1 < doc.blockCount():
            nxt = _block_timing(group_end + 1)
            if nxt is None or abs(nxt[0] - anchor[0]) >= 0.05 or abs(nxt[1] - anchor[1]) >= 0.05:
                break
            group_end += 1

        if not (group_start <= int(to_line) <= group_end):
            return None
        return group_start, group_end, anchor[0], anchor[1]

    def _try_nle_speaker_drop_commit(self, from_line: int, to_line: int) -> bool:
        nle_text_edit = getattr(self, "_nle_live_editor_caption_text_edit_result", None)
        reloader = getattr(self, "_reload_segments_from_list", None)
        if not callable(nle_text_edit) or not callable(reloader):
            return False
        group = self._speaker_drop_group_bounds(from_line, to_line)
        if group is None:
            return False
        group_start, group_end, start_sec, end_sec = group
        doc = self.text_edit.document()
        payloads = []
        for idx in range(group_start, group_end + 1):
            block = doc.findBlockByNumber(idx)
            ud = block.userData() if block.isValid() else None
            if not isinstance(ud, SubtitleBlockData) or bool(getattr(ud, "is_gap", False)):
                return False
            payloads.append(
                {
                    "text": block.text().replace("\u2028", "\n"),
                    "speaker": str(getattr(ud, "spk_id", "") or ""),
                }
            )

        rel_from = int(from_line) - group_start
        rel_to = int(to_line) - group_start
        if not (0 <= rel_from < len(payloads) and 0 <= rel_to < len(payloads)):
            return False
        moved = payloads.pop(rel_from)
        payloads.insert(rel_to, moved)
        new_text = "\n".join(str(item.get("text", "") or "") for item in payloads).strip()
        speakers = []
        for item in payloads:
            speaker = str(item.get("speaker", "") or "").strip()
            if speaker and speaker not in speakers:
                speakers.append(speaker)
        if not new_text or not speakers:
            return False

        try:
            current_segments = list(self._get_current_segments(force_rebuild=True))
        except Exception:
            return False
        nle_result = nle_text_edit(
            current_segments=current_segments,
            line_num=int(group_start),
            start_sec=float(start_sec),
            end_sec=float(end_sec),
            new_text=new_text,
            new_speaker=speakers[0],
            new_speaker_list=speakers,
            commit_source="timeline_speaker_drop",
        )
        if nle_result is None:
            return False

        self._last_nle_live_editor_operation = nle_result.operation.to_dict()
        self._last_nle_live_editor_projection = nle_result.after_projection.to_dict()
        reloader(list(nle_result.projected_rows), preserve_view=True, mark_dirty=True)
        finalizer = getattr(self, "_finalize_manual_edit_snapshot", None)
        if callable(finalizer):
            finalizer(allow_revision_drift=True)
        else:
            self._finalize_edit()
        return True

    def _on_speaker_circle_dropped(self, from_line: int, to_line: int):
        self._undo_mgr.push_immediate()
        if from_line == to_line:
            return
        if self._try_nle_speaker_drop_commit(from_line, to_line):
            return
        doc = self.text_edit.document()
        start_idx = min(from_line, to_line)
        end_idx = max(from_line, to_line)
        blocks_data = []
        for i in range(start_idx, end_idx + 1):
            b = doc.findBlockByNumber(i)
            ud = b.userData()
            new_ud = SubtitleBlockData(
                ud.spk_id,
                ud.start_sec,
                ud.is_gap,
                end_sec=getattr(ud, "end_sec", None),
            ) if ud else None
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
