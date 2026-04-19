# Version: 01.00.02
"""
ui/editor_timeline_video.py
[v01.00.02] 리팩토링 + 버그 수정
- _on_seg_time_changed: square_left/square_right 드래그 시 Gap 생성 보장
- 코드 정리 (불필요 주석 제거, 일관성 개선)
"""
import os, json, subprocess
from PyQt6.QtWidgets import QMenu
from PyQt6.QtCore import Qt, QTimer, QSettings, QPoint
from PyQt6.QtGui import QTextCursor, QColor, QIcon, QPixmap, QPainter
from PyQt6.QtMultimedia import QMediaPlayer

import config
from ui.subtitle_text_edit import SubtitleBlockData


class EditorTimelineVideoMixin:
    """타임라인/비디오 동기화 / 화자 관리 / 단축키 액션"""

    # ---------------------------------------------------------
    # Timeline Segment Events
    # ---------------------------------------------------------
    def _on_timeline_seg_clicked(self, line_num: int, start_sec: float):
        self._active_seg_start = start_sec
        self.timeline.set_active(start_sec)
        segs = self._get_current_segments()
        for seg in segs:
            if seg["line"] == line_num:
                self.timeline.center_to_sec((seg["start"] + seg["end"]) / 2, smooth=True)
                break

        doc = self.text_edit.document()
        block = doc.findBlockByNumber(line_num)
        if block.isValid():
            cur = QTextCursor(block)
            self._sync_lock = True
            self.text_edit.setTextCursor(cur)
            self.text_edit.ensureCursorVisible()
            self._sync_lock = False
            self._highlighter.set_current_line(line_num)
            self.text_edit.setFocus()

        if hasattr(self, 'video_player'):
            self.video_player.pause_video()
            self.video_player.seek(start_sec)

        self._redraw_timeline()

    def _on_timeline_seg_double_clicked(self, line_num: int, start_sec: float):
        lock_box = getattr(self.timeline, 'lock_chk', getattr(self.timeline, 'lock_cb', None))
        if lock_box and lock_box.isChecked():
            return

        self._active_seg_start = start_sec
        self.timeline.set_active(start_sec)

        if hasattr(self, 'video_player'):
            self.video_player.pause_video()
            self.video_player.seek(start_sec)

        if hasattr(self.timeline, 'canvas') and hasattr(self.timeline.canvas, 'start_inline_edit'):
            self._undo_mgr.push_immediate()
            self.timeline.canvas.start_inline_edit(line_num, start_sec)

    # ---------------------------------------------------------
    # Playhead & Scrub Sync
    # ---------------------------------------------------------

    def _sync_playhead(self):
        if not hasattr(self, 'video_player') or not hasattr(self, 'timeline'):
            return

        player = self.video_player.media_player
        if player.playbackState() != player.PlaybackState.PlayingState:
            return

        pos_ms = player.position()
        dur_ms = player.duration()
        if dur_ms <= 0:
            return

        current_sec = pos_ms / 1000.0
        self.timeline.set_playhead(current_sec)

        canvas = self.timeline.canvas
        viewport_w = self.timeline.scroll.viewport().width()
        center_x = int(current_sec * canvas.pps) - (viewport_w // 2)
        center_x = max(0, center_x)

        self.timeline._target_scroll_x = float(center_x)
        self.timeline._current_scroll_x = float(center_x)
        self.timeline.scroll.horizontalScrollBar().setValue(center_x)

        # ✅ [#7] 재생 중 텍스트 에디터도 현재 세그먼트에 맞춰 커서 이동
        segs = getattr(self, '_cached_segs', None) or self._get_current_segments()
        for seg in segs:
            if seg.get("is_gap"):
                continue
            if seg["start"] <= current_sec < seg["end"]:
                if self._active_seg_start != seg["start"]:
                    self._active_seg_start = seg["start"]
                    self.timeline.set_active(seg["start"])
                    line_num = seg.get("line", 0)
                    self._highlighter.set_current_line(line_num)
                    block = self.text_edit.document().findBlockByNumber(line_num)
                    if block.isValid():
                        self._sync_lock = True
                        cur = QTextCursor(block)
                        self.text_edit.setTextCursor(cur)
                        self.text_edit.ensureCursorVisible()
                        self._sync_lock = False
                break

    def _on_scrub(self, sec: float):
        self.timeline.set_playhead(sec)
        if hasattr(self, 'video_player'):
            self.video_player.seek(sec)
            self.video_player.pause_video()
            if hasattr(self.video_player, 'media_player'):
                self.video_player.media_player.play()
                self.video_player.media_player.pause()

        segs = getattr(self, '_cached_segs', None) or self._get_current_segments()
        for seg in segs:
            if seg["start"] <= sec < seg["end"]:
                if self._active_seg_start != seg["start"]:
                    self._active_seg_start = seg["start"]
                    self.timeline.set_active(seg["start"])
                    self.timeline.center_to_sec(sec, smooth=True)
                    line_num = seg.get("line", 0)
                    self._highlighter.set_current_line(line_num)
                    block = self.text_edit.document().findBlockByNumber(line_num)
                    if block.isValid():
                        cur = QTextCursor(block)
                        self._sync_lock = True
                        self.text_edit.setTextCursor(cur)
                        self.text_edit.ensureCursorVisible()
                        self._sync_lock = False
                break

    def _on_step_frame(self, direction: int):
        if not hasattr(self, 'video_player'):
            return
        fps = getattr(self, 'video_fps', 30.0)
        frame_sec = 1.0 / fps
        new_sec = max(0.0, self.video_player.current_time + (direction * frame_sec))
        if hasattr(self.video_player, 'total_time') and self.video_player.total_time > 0:
            new_sec = min(new_sec, self.video_player.total_time)
        self.video_player.pause_video()
        self.video_player.seek(new_sec)

        segs = self._get_current_segments()
        for seg in segs:
            if seg["start"] <= new_sec < seg["end"]:
                if self._active_seg_start != seg["start"]:
                    self._active_seg_start = seg["start"]
                    self.timeline.set_active(seg["start"])
                    line_num = seg.get("line", 0)
                    self._highlighter.set_current_line(line_num)
                    block = self.text_edit.document().findBlockByNumber(line_num)
                    if block.isValid():
                        cur = QTextCursor(block)
                        self._sync_lock = True
                        self.text_edit.setTextCursor(cur)
                        self.text_edit.ensureCursorVisible()
                        self._sync_lock = False
                break
        self.timeline.set_playhead(new_sec)
        self.timeline.center_to_sec(new_sec, smooth=False)

    # ---------------------------------------------------------
    # Segment Time Edit (✅ 버그1 수정: Gap 생성 보장)
    # ---------------------------------------------------------
    def _on_seg_time_changed(self, line_num: int, new_start: float, new_end: float, edge_type: str = ""):
        doc = self.text_edit.document()
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        block = doc.findBlockByNumber(line_num)
        if not block.isValid():
            cur.endEditBlock()
            return

        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData):
            cur.endEditBlock()
            return

        old_start = ud.start_sec
        ud.start_sec = round(new_start, 2)

        # 같은 자막 덩어리의 하위 줄도 시작 시간 동기화
        for i in range(line_num + 1, doc.blockCount()):
            b = doc.findBlockByNumber(i)
            u = b.userData()
            if isinstance(u, SubtitleBlockData) and abs(u.start_sec - old_start) < 0.05 and not u.is_gap:
                u.start_sec = ud.start_sec
            else:
                break

        # ── 앞쪽 Gap 처리 ──
        prev_block = block.previous()
        if prev_block.isValid():
            prev_ud = prev_block.userData()
            if isinstance(prev_ud, SubtitleBlockData):
                if prev_ud.is_gap:
                    # 기존 Gap이 현재 자막과 겹치면 제거
                    if abs(prev_ud.start_sec - ud.start_sec) < 0.05:
                        c2 = QTextCursor(prev_block)
                        c2.select(QTextCursor.SelectionType.BlockUnderCursor)
                        c2.removeSelectedText()
                        if not c2.atEnd():
                            c2.deleteChar()
                else:
                    # ✅ 버그1 수정: 앞으로 당길 때 (start가 뒤로 이동) Gap 생성
                    if edge_type not in ("diamond", "gap") and new_start > old_start + 0.05:
                        c2 = QTextCursor(prev_block)
                        c2.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                        c2.insertText("\n")
                        c2.block().setUserData(SubtitleBlockData("00", old_start, is_gap=True))

        # ── 뒤쪽 Gap 처리 ──
        # 블록 인덱스가 변경되었을 수 있으므로 다시 탐색
        block = doc.findBlockByNumber(line_num)
        if not block.isValid():
            cur.endEditBlock()
            return

        # 같은 자막 덩어리의 마지막 줄 찾기
        last_block = block
        while True:
            nxt = last_block.next()
            if nxt.isValid():
                n_ud = nxt.userData()
                if isinstance(n_ud, SubtitleBlockData) and not n_ud.is_gap and abs(n_ud.start_sec - ud.start_sec) < 0.05:
                    last_block = nxt
                else:
                    break
            else:
                break

        next_block = last_block.next()
        if next_block.isValid():
            next_ud = next_block.userData()
            if isinstance(next_ud, SubtitleBlockData):
                if not next_ud.is_gap:
                    is_same_subtitle = abs(next_ud.start_sec - ud.start_sec) < 0.05
                    # ✅ 버그1 수정: 뒤로 당길 때 (end가 앞으로 이동) Gap 생성
                    if not is_same_subtitle and edge_type not in ("diamond", "gap") and new_end < next_ud.start_sec - 0.05:
                        c3 = QTextCursor(last_block)
                        c3.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                        c3.insertText("\n")
                        c3.block().setUserData(SubtitleBlockData("00", new_end, is_gap=True))
                else:
                    # 기존 Gap 시간 업데이트 또는 제거
                    next_next_block = next_block.next()
                    if next_next_block.isValid():
                        nnu = next_next_block.userData()
                        if isinstance(nnu, SubtitleBlockData) and abs(new_end - nnu.start_sec) < 0.05:
                            # Gap이 불필요해짐 → 제거
                            c3 = QTextCursor(next_block)
                            c3.select(QTextCursor.SelectionType.BlockUnderCursor)
                            c3.removeSelectedText()
                            if not c3.atEnd():
                                c3.deleteChar()
                        else:
                            next_ud.start_sec = new_end
                    else:
                        next_ud.start_sec = new_end

        self.text_edit.update_margins()
        cur.endEditBlock()
        if hasattr(self.text_edit, 'timestampArea'):
            self.text_edit.timestampArea.update()
        QTimer.singleShot(0, self._redraw_timeline)

    def _on_seg_to_gap(self, line_num: int):
        """자막 세그먼트 → 무음구간(Gap)으로 변환 (블록 삭제 X, Gap 변환 O)"""
        self._undo_mgr.push_immediate()
        doc = self.text_edit.document()
        block = doc.findBlockByNumber(line_num)
        if not block.isValid():
            return

        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or ud.is_gap:
            return

        seg_start = ud.start_sec

        cur = QTextCursor(doc)
        cur.beginEditBlock()

        # ── 1) 같은 start_sec인 하위 블록(화자 분리 등) 수집 ──
        sub_indices = [line_num]
        for i in range(line_num + 1, doc.blockCount()):
            b = doc.findBlockByNumber(i)
            b_ud = b.userData()
            if (isinstance(b_ud, SubtitleBlockData)
                    and not b_ud.is_gap
                    and abs(b_ud.start_sec - seg_start) < 0.05):
                sub_indices.append(i)
            else:
                break

        # ── 2) 하위 블록 삭제 (첫 번째만 남김, 뒤에서부터) ──
        for idx in reversed(sub_indices[1:]):
            b = doc.findBlockByNumber(idx)
            c = QTextCursor(b)
            c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            c.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                            QTextCursor.MoveMode.KeepAnchor)
            c.removeSelectedText()
            c.deletePreviousChar()

        # ── 3) 첫 번째 블록: 텍스트만 비우고 Gap으로 변환 ──
        block = doc.findBlockByNumber(line_num)
        cur.setPosition(block.position())
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                          QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        block.setUserData(SubtitleBlockData("00", round(seg_start, 2), is_gap=True))

        # ── 4) 인접 Gap 병합 (연속 Gap 방지) ──
        current_line = block.blockNumber()

        # 뒤쪽 Gap 흡수
        next_b = block.next()
        if next_b.isValid():
            n_ud = next_b.userData()
            if isinstance(n_ud, SubtitleBlockData) and n_ud.is_gap:
                c2 = QTextCursor(next_b)
                c2.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                c2.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                                QTextCursor.MoveMode.KeepAnchor)
                c2.removeSelectedText()
                # 기존 (버그): c2.deleteChar()
                #   → 다음 블록(자막)이 Gap 블록에 병합 → userData 소멸!
                # 수정: deletePreviousChar → 빈 Gap을 이전 블록에 병합 (다음 블록 무관)
                c2.deletePreviousChar()

        # 앞쪽 Gap 흡수 (앞 Gap의 start가 더 빠르므로 현재 블록을 삭제)
        block = doc.findBlockByNumber(current_line)
        prev_b = block.previous()
        if prev_b.isValid():
            p_ud = prev_b.userData()
            if isinstance(p_ud, SubtitleBlockData) and p_ud.is_gap:
                c3 = QTextCursor(block)
                c3.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                c3.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                                QTextCursor.MoveMode.KeepAnchor)
                c3.removeSelectedText()
                c3.deletePreviousChar()

        self.text_edit.update_margins()
        cur.endEditBlock()
        self.text_edit.setTextCursor(cur)
        self._schedule_timeline()

    def _on_gap_activated(self, gap_start: float, gap_end: float):
        self._undo_mgr.push_immediate()
        gap_start = round(gap_start, 2)
        gap_end = round(gap_end, 2)
        doc = self.text_edit.document()
        cur = QTextCursor(doc)
        cur.beginEditBlock()

        if gap_start <= 0.05:
            first_block = doc.begin()
            orig_ud = first_block.userData()
            orig_time = orig_ud.start_sec if isinstance(orig_ud, SubtitleBlockData) else gap_end
            orig_spk = orig_ud.spk_id if isinstance(orig_ud, SubtitleBlockData) else self.settings.get("spk1_id", "00")
            if not first_block.text().strip() or (isinstance(orig_ud, SubtitleBlockData) and orig_ud.is_gap):
                cur.setPosition(first_block.position())
                cur.select(QTextCursor.SelectionType.LineUnderCursor)
                cur.insertText("새 자막")
                first_block.setUserData(SubtitleBlockData(self.settings.get("spk1_id", "00"), 0.0, is_gap=False))
            else:
                cur.movePosition(QTextCursor.MoveOperation.Start)
                cur.insertText("새 자막\n")
                doc.findBlockByNumber(0).setUserData(SubtitleBlockData(self.settings.get("spk1_id", "00"), 0.0, is_gap=False))
                doc.findBlockByNumber(1).setUserData(SubtitleBlockData(orig_spk, orig_time, is_gap=False))
                if orig_time > gap_end + 0.05:
                    cur.setPosition(doc.findBlockByNumber(1).position())
                    cur.insertText("\n")
                    doc.findBlockByNumber(1).setUserData(SubtitleBlockData("00", gap_end, is_gap=True))
                    doc.findBlockByNumber(2).setUserData(SubtitleBlockData(orig_spk, orig_time, is_gap=False))
        else:
            target_idx = None
            for i in range(doc.blockCount()):
                ud = doc.findBlockByNumber(i).userData()
                if isinstance(ud, SubtitleBlockData) and abs(ud.start_sec - gap_start) < 0.05:
                    target_idx = i
                    break
            if target_idx is not None:
                block = doc.findBlockByNumber(target_idx)
                cur.setPosition(block.position())
                cur.select(QTextCursor.SelectionType.LineUnderCursor)
                cur.insertText("새 자막")
                block.setUserData(SubtitleBlockData(self.settings.get("spk1_id", "00"), gap_start, is_gap=False))
                next_b = block.next()
                if not next_b.isValid() or (isinstance(next_b.userData(), SubtitleBlockData) and next_b.userData().start_sec > gap_end + 0.05):
                    cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                    cur.insertText("\n")
                    cur.block().setUserData(SubtitleBlockData("00", gap_end, is_gap=True))
            else:
                cur.movePosition(QTextCursor.MoveOperation.End)
                if doc.lastBlock().text().strip():
                    cur.insertText("\n")
                cur.insertText("새 자막")
                cur.block().setUserData(SubtitleBlockData(self.settings.get("spk1_id", "00"), gap_start, is_gap=False))
                cur.insertText("\n")
                cur.block().setUserData(SubtitleBlockData("00", gap_end, is_gap=True))

        self.text_edit.update_margins()
        cur.endEditBlock()
        self.text_edit.setTextCursor(cur)
        if hasattr(self.text_edit, 'timestampArea'):
            self.text_edit.timestampArea.update()
        self._schedule_timeline()

    def _on_gap_to_segs(self, gap_start: float, gap_end: float):
        self._undo_mgr.push_immediate()
        gap_dur = round(gap_end - gap_start, 2)
        pull = float(self.settings.get("gap_pull_rate", 0.3))
        push = float(self.settings.get("gap_push_rate", 0.7))
        left = max((s for s in self.timeline.canvas.segments if s["end"] <= gap_start + 0.1), key=lambda s: s["end"], default=None)
        right = min((s for s in self.timeline.canvas.segments if s["start"] >= gap_end - 0.1), key=lambda s: s["start"], default=None)
        self.text_edit.textCursor().beginEditBlock()
        if left:
            left["end"] = round(left["end"] + gap_dur * push, 2)
            self._on_seg_time_changed(left.get("line", 0), left["start"], left["end"], "gap")
        if right:
            right["start"] = round(right["start"] - gap_dur * pull, 2)
            self._on_seg_time_changed(right.get("line", 0), right["start"], right["end"], "gap")
        self.text_edit.update_margins()
        self.text_edit.textCursor().endEditBlock()
        self._schedule_timeline()

    def _on_diamond_merge(self, left_line: int, right_line: int):
        """다이아몬드 더블클릭: 좌우 자막 세그먼트 1쌍만 병합 (선택+교체 방식)"""
        self._undo_mgr.push_immediate()
        doc = self.text_edit.document()

        left_block = doc.findBlockByNumber(left_line)
        right_block = doc.findBlockByNumber(right_line)
        if not left_block.isValid() or not right_block.isValid():
            return

        left_ud = left_block.userData()
        right_ud = right_block.userData()
        if not isinstance(left_ud, SubtitleBlockData) or not isinstance(right_ud, SubtitleBlockData):
            return
        if left_ud.is_gap or right_ud.is_gap:
            return

        left_start = left_ud.start_sec
        right_start = right_ud.start_sec

        # ── 1) 왼쪽 세그먼트의 마지막 블록 ──
        left_last = left_line
        for i in range(left_line + 1, doc.blockCount()):
            b = doc.findBlockByNumber(i)
            b_ud = b.userData()
            if (isinstance(b_ud, SubtitleBlockData)
                    and not b_ud.is_gap
                    and abs(b_ud.start_sec - left_start) < 0.05):
                left_last = i
            else:
                break

        # ── 2) 오른쪽 세그먼트의 마지막 블록 (딱 1개 세그먼트만) ──
        right_last = right_line
        for i in range(right_line + 1, doc.blockCount()):
            b = doc.findBlockByNumber(i)
            b_ud = b.userData()
            if (isinstance(b_ud, SubtitleBlockData)
                    and not b_ud.is_gap
                    and abs(b_ud.start_sec - right_start) < 0.05):
                right_last = i
            else:
                break

        # ── 3) 오른쪽 텍스트 수집 ──
        right_texts = []
        for i in range(right_line, right_last + 1):
            b = doc.findBlockByNumber(i)
            t = b.text()
            if t.strip():
                right_texts.append(t)
        if not right_texts:
            return

        cur = QTextCursor(doc)
        cur.beginEditBlock()

        # ── 4) 핵심: "왼쪽 끝 ~ 오른쪽 끝" 범위를 선택 후 소프트 줄바꿈으로 교체 ──
        #    이 방식은 오른쪽 블록을 별도로 삭제하지 않으므로
        #    자막3(오른쪽 다음 블록)을 절대 건드리지 않습니다.
        left_last_block = doc.findBlockByNumber(left_last)
        right_last_block = doc.findBlockByNumber(right_last)

        # 왼쪽 마지막 블록 끝에서 시작
        cur.setPosition(left_last_block.position())
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)

        # 오른쪽 마지막 블록 끝까지 선택
        right_end = QTextCursor(right_last_block)
        right_end.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cur.setPosition(right_end.position(), QTextCursor.MoveMode.KeepAnchor)

        # 선택 영역을 소프트 줄바꿈 텍스트로 교체
        replacement = "\u2028".join(right_texts)
        cur.insertText("\u2028" + replacement)

        cur.endEditBlock()

        if hasattr(self, "sm"):
            self.sm.is_dirty = True
        else:
            self._is_dirty = True

        self.text_edit.update_margins()
        if hasattr(self.text_edit, 'timestampArea'):
            self.text_edit.timestampArea.update()
        self._schedule_timeline()

    def _on_smart_split(self, line_num: int, split_sec: float, new_on_left: bool):
        """
        ✅ [#6, #10] 스마트 자막 분할
        - new_on_left=True  → 플레이헤드가 중간 왼쪽: 왼쪽에 "새자막", 기존자막은 오른쪽
        - new_on_left=False → 플레이헤드가 중간 오른쪽: 기존자막은 왼쪽, 오른쪽에 "새자막"
        """
        self._undo_mgr.push_immediate()
        doc = self.text_edit.document()
        block = doc.findBlockByNumber(int(line_num))
        if not block.isValid():
            return

        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or ud.is_gap:
            return

        seg_start = float(ud.start_sec)
        spk_id = ud.spk_id
        split_sec = float(split_sec)

        # 범위 체크
        if split_sec <= seg_start + 0.05:
            return

        # 기존 텍스트 수집 (같은 start_sec 블록 전부)
        full_lines = []
        sub_indices = [block.blockNumber()]
        full_lines.append(block.text())
        for i in range(block.blockNumber() + 1, doc.blockCount()):
            b = doc.findBlockByNumber(i)
            b_ud = b.userData()
            if (isinstance(b_ud, SubtitleBlockData)
                    and not b_ud.is_gap
                    and abs(b_ud.start_sec - seg_start) < 0.05):
                sub_indices.append(i)
                full_lines.append(b.text())
            else:
                break

        original_text = "\u2028".join(full_lines)

        cur = QTextCursor(doc)
        cur.beginEditBlock()

        # ── 하위 블록 삭제 (뒤에서부터, 첫 번째만 남김) ──
        for idx in reversed(sub_indices[1:]):
            b = doc.findBlockByNumber(idx)
            c = QTextCursor(b)
            c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            c.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                            QTextCursor.MoveMode.KeepAnchor)
            c.removeSelectedText()
            if doc.blockCount() > 1:
                c.deletePreviousChar()

        # ── 첫 번째 블록 텍스트 교체 + 새 블록 삽입 ──
        block = doc.findBlockByNumber(sub_indices[0])
        cur.setPosition(block.position())
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                          QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()

        if new_on_left:
            # 왼쪽 = "새자막" (seg_start ~ split_sec)
            # 오른쪽 = 기존 텍스트 (split_sec ~ 원래 end)
            cur.insertText("새자막")
            cur.block().setUserData(
                SubtitleBlockData(spk_id, round(seg_start, 2), is_gap=False))

            cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            cur.insertBlock()
            cur.insertText(original_text)
            cur.block().setUserData(
                SubtitleBlockData(spk_id, round(split_sec, 2), is_gap=False))
        else:
            # 왼쪽 = 기존 텍스트 (seg_start ~ split_sec)
            # 오른쪽 = "새자막" (split_sec ~ 원래 end)
            cur.insertText(original_text)
            cur.block().setUserData(
                SubtitleBlockData(spk_id, round(seg_start, 2), is_gap=False))

            cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            cur.insertBlock()
            cur.insertText("새자막")
            cur.block().setUserData(
                SubtitleBlockData(spk_id, round(split_sec, 2), is_gap=False))

        cur.endEditBlock()

        # ✅ 타임라인 튕김 방지
        self._sync_lock = True
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        self.text_edit.setTextCursor(cur)
        self._active_seg_start = round(split_sec, 2)
        if hasattr(self, 'timeline'):
            self.timeline.set_active(self._active_seg_start)
            self.timeline.center_to_sec(split_sec, smooth=True)
        self._sync_lock = False

        if hasattr(self, "sm"):
            self.sm.is_dirty = True
        else:
            self._is_dirty = True

        self.text_edit.update_margins()
        if hasattr(self.text_edit, 'timestampArea'):
            self.text_edit.timestampArea.update()
        self._schedule_timeline()

    # ---------------------------------------------------------
    # Video Control
    # ---------------------------------------------------------
    def _is_video_playing(self):
        if not hasattr(self, 'video_player'):
            return False
        if hasattr(self.video_player, 'media_player'):
            return self.video_player.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        return False

    def _on_seg_editing_mode(self, active: bool):
        self.space_shortcut.setEnabled(not active)

    def _on_space_pressed(self):
        self._toggle_video_play()

    def _toggle_video_play(self):
        if hasattr(self, 'video_player'):
            self.video_player.toggle_play()

    def _toggle_video(self):
        if self.video_player.isVisible():
            self.video_player.hide()
            self.splitter.setSizes([1, 0])
        else:
            self.video_player.show()
            self.splitter.setSizes([1000, 800])

    def _load_video(self, path: str):
        segs = self._get_current_segments()
        self.video_player.load(path, segs)
        if hasattr(self.timeline, 'load_waveform'):
            self.timeline.load_waveform(path)
        self.video_fps = 30.0
        try:
            cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                   '-show_entries', 'stream=r_frame_rate', '-of', 'json', path]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
            probe = json.loads(res.stdout)
            fps_str = probe.get('streams', [{}])[0].get('r_frame_rate', '30/1')
            if '/' in fps_str:
                n, d = fps_str.split('/')
                self.video_fps = float(n) / float(d) if float(d) != 0 else 30.0
            else:
                self.video_fps = float(fps_str)
        except Exception:
            pass

        self._vid_wait_cnt = 0
        def init_video():
            self._vid_wait_cnt += 1
            if not hasattr(self, 'video_player') or self.video_player.total_time <= 0.1:
                if self._vid_wait_cnt < 20:
                    QTimer.singleShot(100, init_video)
                    return
            if hasattr(self, 'media_path'):
                settings = QSettings("AI_PD_Studio", "Timeline")
                last_pos = settings.value(f"last_pos_{self.media_path}", 0.0, type=float)
                if last_pos > 0:
                    if hasattr(self, 'video_player'):
                        self.video_player.seek(last_pos)
                    if hasattr(self, 'timeline'):
                        self.timeline.set_playhead(last_pos)
                        self.timeline.center_to_sec(last_pos, smooth=False)
                else:
                    if hasattr(self, 'video_player'):
                        self.video_player.seek(0.0)
            if hasattr(self, 'video_player'):
                self.video_player.pause_video()
            self._schedule_timeline()
        QTimer.singleShot(100, init_video)

    # ---------------------------------------------------------
    # Speaker Management
    # ---------------------------------------------------------
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
            action = menu.addAction(make_circle_icon(color_hex), f"화자 {int(spk)+1}로 변경")
            action.triggered.connect(lambda checked, s=spk: self._change_speaker_for_line(line_num, s))
            added += 1
        if added > 0:
            menu.exec(gpos)

    def _change_speaker_for_line(self, line_num: int, new_spk_id: str):
        self._undo_mgr.push_immediate()
        doc = self.text_edit.document()
        block = doc.findBlockByNumber(line_num)
        if block.isValid():
            ud = block.userData()
            if isinstance(ud, SubtitleBlockData):
                old_start = ud.start_sec
                ud.spk_id = new_spk_id
                for i in range(line_num + 1, doc.blockCount()):
                    b = doc.findBlockByNumber(i)
                    u = b.userData()
                    if isinstance(u, SubtitleBlockData) and abs(u.start_sec - old_start) < 0.05 and not u.is_gap:
                        u.spk_id = new_spk_id
                    else:
                        break
                self._highlighter.rehighlight()
                if hasattr(self.text_edit, 'timestampArea'):
                    self.text_edit.timestampArea.update()
                self._schedule_timeline()

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
        self.text_edit.update_margins()
        cursor.endEditBlock()
        self._highlighter.rehighlight()
        if hasattr(self.text_edit, 'timestampArea'):
            self.text_edit.timestampArea.update()
        self._schedule_timeline()

    # ---------------------------------------------------------
    # Shortcut Actions
    # ---------------------------------------------------------
    def _trigger_magnet(self):
        if hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
            self.timeline.canvas._snap_closest_diamond()

    def _toggle_focus(self):
        if self.timeline.hasFocus() or self.timeline.canvas.hasFocus() or self.timeline.global_canvas.hasFocus() or self.timeline.scroll.hasFocus():
            self.text_edit.setFocus()
        elif self.text_edit.hasFocus():
            lock_box = getattr(self.timeline, 'lock_chk', getattr(self.timeline, 'lock_cb', None))
            if not lock_box or not lock_box.isChecked():
                self.timeline.canvas.setFocus()
        else:
            self.timeline.canvas.setFocus()

    def _split_at_playhead_or_cut(self):
        self._undo_mgr.push_immediate()
        cur = self.text_edit.textCursor()
        if cur.hasSelection():
            self.text_edit.cut()
            return
        sec = getattr(self.video_player, 'current_time', 0.0)
        block = cur.block()
        ud = block.userData()
        spk = ud.spk_id if isinstance(ud, SubtitleBlockData) else "00"
        cur.beginEditBlock()
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cur.insertText("\n새자막")
        cur.block().setUserData(SubtitleBlockData(spk, sec))
        self.text_edit.update_margins()
        cur.endEditBlock()
        self._redraw_timeline()

    def _set_segment_start_to_playhead(self):
        self._undo_mgr.push_immediate()
        sec = getattr(self.video_player, 'current_time', 0.0)
        cur = self.text_edit.textCursor()
        block = cur.block()
        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or ud.is_gap:
            return

        orig_start = ud.start_sec
        cur.beginEditBlock()

        first_block = block
        while first_block.previous().isValid():
            p_ud = first_block.previous().userData()
            if isinstance(p_ud, SubtitleBlockData) and not p_ud.is_gap and abs(p_ud.start_sec - orig_start) < 0.05:
                first_block = first_block.previous()
            else:
                break

        prev_block = first_block.previous()
        if sec > orig_start and prev_block.isValid():
            prev_ud = prev_block.userData()
            if isinstance(prev_ud, SubtitleBlockData) and not prev_ud.is_gap:
                c = QTextCursor(prev_block)
                c.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                c.insertText("\n")
                gap_block = prev_block.next()
                gap_block.setUserData(SubtitleBlockData("00", orig_start, is_gap=True))

        b = first_block
        while b.isValid():
            b_ud = b.userData()
            if isinstance(b_ud, SubtitleBlockData) and not b_ud.is_gap and abs(b_ud.start_sec - orig_start) < 0.05:
                b_ud.start_sec = sec
                b = b.next()
            else:
                break

        self.text_edit.update_margins()
        cur.endEditBlock()
        if hasattr(self.text_edit, 'timestampArea'):
            self.text_edit.timestampArea.update()
        self._redraw_timeline()

    def _set_segment_end_to_playhead(self):
        self._undo_mgr.push_immediate()
        sec = getattr(self.video_player, 'current_time', 0.0)
        cur = self.text_edit.textCursor()
        block = cur.block()
        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or ud.is_gap:
            return

        orig_start = ud.start_sec
        if sec <= orig_start:
            return

        cur.beginEditBlock()

        last_block = block
        while True:
            nxt = last_block.next()
            if nxt.isValid():
                n_ud = nxt.userData()
                if isinstance(n_ud, SubtitleBlockData) and not n_ud.is_gap and abs(n_ud.start_sec - orig_start) < 0.05:
                    last_block = nxt
                else:
                    break
            else:
                break

        next_block = last_block.next()
        if next_block.isValid() and isinstance(next_block.userData(), SubtitleBlockData) and next_block.userData().is_gap:
            next_block.userData().start_sec = sec
        else:
            c = QTextCursor(last_block)
            c.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            c.insertText("\n")
            gap_block = last_block.next()
            gap_block.setUserData(SubtitleBlockData("00", sec, is_gap=True))

        cur.endEditBlock()
        self.text_edit.update_margins()
        if hasattr(self.text_edit, 'timestampArea'):
            self.text_edit.timestampArea.update()
        self._redraw_timeline()

    def _on_timeline_seg_right_clicked(self, start_sec: float, gpos: QPoint):
        if self._active_seg_start is not None and abs(start_sec - self._active_seg_start) < 0.05:
            self._split_at_playhead_or_cut()
            return