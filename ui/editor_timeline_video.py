# Version: 01.00.00
"""
ui/editor_timeline_video.py
EditorWidget의 타임라인 동기화, 비디오 제어, 화자 관리, 단축키 액션 메서드 모음.
EditorTimelineVideoMixin으로 EditorWidget에 합성됩니다.
"""
import os, json, subprocess
from PyQt6.QtWidgets import QMenu
from PyQt6.QtCore import Qt, QTimer, QSettings, QPoint  # 💡 QPoint를 이곳(QtCore)으로 이사!
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
        # 💡 [오지랖 삭제] 타임라인 캔버스를 클릭했을 때 억지로 편집 중으로 바꾸는 코드 제거
        self._active_seg_start = start_sec; self.timeline.set_active(start_sec)
        segs = self._get_current_segments()
        for seg in segs:
            if seg["line"] == line_num:
                self.timeline.center_to_sec((seg["start"] + seg["end"]) / 2, smooth=True); break
        
        doc = self.text_edit.document(); block = doc.findBlockByNumber(line_num)
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
        if lock_box and lock_box.isChecked(): return
        
        self._active_seg_start = start_sec
        self.timeline.set_active(start_sec)
        
        if hasattr(self, 'video_player'):
            self.video_player.pause_video()
            self.video_player.seek(start_sec)
            
        # 💡 메인 에디터로 포커스를 뺏지 않고, 타임라인 캔버스의 인라인 에디터를 호출합니다.
        if hasattr(self.timeline, 'canvas') and hasattr(self.timeline.canvas, 'start_inline_edit'):
            self._undo_mgr.push_immediate() # 💡 [핵심] 더블클릭해서 글자를 수정하기 직전의 전체 타임라인 상태를 저장!
            self.timeline.canvas.start_inline_edit(line_num, start_sec)
        # ----------------------------------

    # ---------------------------------------------------------
    # Playhead & Scrub Sync
    # ---------------------------------------------------------
    def _sync_playhead(self):
        import time 
        
        if hasattr(self, 'video_player'):
            actual_sec = self.video_player.current_time
            
            if self._is_video_playing():
                now = time.time()
                if not hasattr(self, '_smooth_playhead_sec'):
                    self._smooth_playhead_sec = actual_sec
                    self._last_sync_time = now
                    
                dt = now - getattr(self, '_last_sync_time', now)
                self._last_sync_time = now
                
                # 시스템 시계로 전진하되 비디오 시간과 지속적으로 싱크를 맞춤
                self._smooth_playhead_sec += dt
                diff = actual_sec - self._smooth_playhead_sec
                
                if abs(diff) > 0.3: 
                    self._smooth_playhead_sec = actual_sec
                else:
                    # 미세하게 당겨주어 비디오 싱크를 유지 (0.05~0.1 사이가 가장 적당함)
                    self._smooth_playhead_sec += diff * 0.08
                    
                sec = self._smooth_playhead_sec
            else:
                sec = actual_sec
                self._smooth_playhead_sec = actual_sec
                self._last_sync_time = time.time()

            self.timeline.set_playhead(sec)
            
            if self._is_video_playing():
                self.timeline.center_to_sec(sec, smooth=True)
                segs = getattr(self, '_cached_segs', [])
                for seg in segs:
                    if seg["start"] <= sec < seg["end"]:
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

    def _on_scrub(self, sec: float):
        if hasattr(self, 'video_player'):
            self.video_player.seek(sec); self.video_player.pause_video()
            if hasattr(self.video_player, 'media_player'):
                self.video_player.media_player.play(); self.video_player.media_player.pause()
        segs = self._get_current_segments()
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
                        self._sync_lock = True; self.text_edit.setTextCursor(cur); self.text_edit.ensureCursorVisible(); self._sync_lock = False
                break

    def _on_step_frame(self, direction: int):
        if not hasattr(self, 'video_player'): return
        fps = getattr(self, 'video_fps', 30.0)
        frame_sec = 1.0 / fps
        new_sec = max(0.0, self.video_player.current_time + (direction * frame_sec))
        if hasattr(self.video_player, 'total_time') and self.video_player.total_time > 0:
            new_sec = min(new_sec, self.video_player.total_time)
        self.video_player.pause_video(); self.video_player.seek(new_sec)
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
                        self._sync_lock = True; self.text_edit.setTextCursor(cur); self.text_edit.ensureCursorVisible(); self._sync_lock = False
                break
        self.timeline.set_playhead(new_sec)
        self.timeline.center_to_sec(new_sec, smooth=False)

    # ---------------------------------------------------------
    # Segment Time Edit
    # ---------------------------------------------------------
    def _on_seg_time_changed(self, line_num: int, new_start: float, new_end: float, edge_type: str = ""):
        doc = self.text_edit.document()
        cur = QTextCursor(doc); cur.beginEditBlock()
        block = doc.findBlockByNumber(line_num)
        if not block.isValid(): cur.endEditBlock(); return
        ud = block.userData()
        if isinstance(ud, SubtitleBlockData):
            old_start = ud.start_sec
            ud.start_sec = round(new_start, 2)
            for i in range(line_num + 1, doc.blockCount()):
                b = doc.findBlockByNumber(i); u = b.userData()
                if isinstance(u, SubtitleBlockData) and abs(u.start_sec - old_start) < 0.05 and not u.is_gap:
                    u.start_sec = ud.start_sec
                else: break
            prev_block = block.previous()
            if prev_block.isValid():
                prev_ud = prev_block.userData()
                if isinstance(prev_ud, SubtitleBlockData):
                    if prev_ud.is_gap:
                        if abs(prev_ud.start_sec - ud.start_sec) < 0.05:
                            c2 = QTextCursor(prev_block)
                            c2.select(QTextCursor.SelectionType.BlockUnderCursor); c2.removeSelectedText()
                            if not c2.atEnd(): c2.deleteChar()
                    else:
                        if edge_type != "diamond" and new_start > old_start + 0.05:
                            c2 = QTextCursor(prev_block)
                            c2.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                            c2.insertText("\n")
                            c2.block().setUserData(SubtitleBlockData("00", old_start, is_gap=True))
            next_block = block.next()
            if next_block.isValid():
                next_ud = next_block.userData()
                if isinstance(next_ud, SubtitleBlockData):
                    # 수정 — 2줄 자막의 두 번째 줄(같은 start_sec)이면 gap 삽입 건너뜀
                    if not next_ud.is_gap:
                        is_same_subtitle = abs(next_ud.start_sec - ud.start_sec) < 0.05  # 같은 자막의 두 번째 줄
                        if not is_same_subtitle and edge_type != "diamond" and new_end < next_ud.start_sec - 0.05:
                            c3 = QTextCursor(block)
                            c3.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                            c3.insertText("\n")
                            c3.block().setUserData(SubtitleBlockData("00", new_end, is_gap=True))
                    else:
                        next_next_block = next_block.next()
                        if next_next_block.isValid():
                            nnu = next_next_block.userData()
                            if isinstance(nnu, SubtitleBlockData) and abs(new_end - nnu.start_sec) < 0.05:
                                c3 = QTextCursor(next_block)
                                c3.select(QTextCursor.SelectionType.BlockUnderCursor); c3.removeSelectedText()
                                if not c3.atEnd(): c3.deleteChar()
                            else: next_ud.start_sec = new_end
                        else: next_ud.start_sec = new_end
        self.text_edit.update_margins(); cur.endEditBlock()
        self.text_edit.timestampArea.update()
        QTimer.singleShot(0, self._redraw_timeline)

    def _on_seg_to_gap(self, line_num: int):
        self._undo_mgr.push_immediate() # 💡 [추가] 자막 삭제 직전에 찰칵!
        doc = self.text_edit.document(); block = doc.findBlockByNumber(line_num)
        if not block.isValid(): return
        cur = QTextCursor(block); cur.beginEditBlock()
        cur.select(QTextCursor.SelectionType.BlockUnderCursor); cur.removeSelectedText()
        if cur.atBlockStart() and cur.atBlockEnd():
            try: cur.deletePreviousChar()
            except Exception: pass
        self.text_edit.update_margins(); cur.endEditBlock()
        self.text_edit.setTextCursor(cur); self._schedule_timeline()

    def _on_gap_activated(self, gap_start: float, gap_end: float):
        self._undo_mgr.push_immediate()
        gap_start = round(gap_start, 2); gap_end = round(gap_end, 2)
        doc = self.text_edit.document(); cur = QTextCursor(doc); cur.beginEditBlock()
        if gap_start <= 0.05:
            first_block = doc.begin(); orig_ud = first_block.userData()
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
                    target_idx = i; break
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
                if doc.lastBlock().text().strip(): cur.insertText("\n")
                cur.insertText("새 자막")
                cur.block().setUserData(SubtitleBlockData(self.settings.get("spk1_id", "00"), gap_start, is_gap=False))
                cur.insertText("\n")
                cur.block().setUserData(SubtitleBlockData("00", gap_end, is_gap=True))
        self.text_edit.update_margins(); cur.endEditBlock()
        self.text_edit.setTextCursor(cur)
        if hasattr(self.text_edit, 'timestampArea'): self.text_edit.timestampArea.update()
        self._schedule_timeline()

    def _on_gap_to_segs(self, gap_start: float, gap_end: float):
        self._undo_mgr.push_immediate() # 💡 [추가] 구간 병합 직전에 찰칵!
        gap_dur = round(gap_end - gap_start, 2)
        pull = float(self.settings.get("gap_pull_rate", 0.3))
        push = float(self.settings.get("gap_push_rate", 0.7))
        left  = max((s for s in self.timeline.canvas.segments if s["end"] <= gap_start + 0.1), key=lambda s: s["end"], default=None)
        right = min((s for s in self.timeline.canvas.segments if s["start"] >= gap_end - 0.1), key=lambda s: s["start"], default=None)
        self.text_edit.textCursor().beginEditBlock()
        if left:
            left["end"] = round(left["end"] + gap_dur * push, 2)
            self._on_seg_time_changed(left.get("line", 0), left["start"], left["end"], "gap")
        if right:
            right["start"] = round(right["start"] - gap_dur * pull, 2)
            self._on_seg_time_changed(right.get("line", 0), right["start"], right["end"], "gap")
        self.text_edit.update_margins(); self.text_edit.textCursor().endEditBlock()
        self._schedule_timeline()

    # ---------------------------------------------------------
    # Video Control
    # ---------------------------------------------------------
    def _is_video_playing(self) -> bool:
        if not hasattr(self, 'video_player'): return False
        if hasattr(self.video_player, 'media_player'):
            return self.video_player.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        if hasattr(self.video_player, '_worker'):
            return getattr(self.video_player._worker, '_play', False)
        return False

    def _on_seg_editing_mode(self, active: bool):
        self.space_shortcut.setEnabled(not active)

    def _on_space_pressed(self):
        self._toggle_video_play()

    def _toggle_video_play(self):
        if hasattr(self, 'video_player'): self.video_player.toggle_play()

    def _toggle_video(self):
        if self.video_player.isVisible():
            self.video_player.hide(); self.splitter.setSizes([1, 0])
        else:
            self.video_player.show(); self.splitter.setSizes([1000, 800])

    def _load_video(self, path: str):
        segs = self._get_current_segments()
        self.video_player.load(path, segs)
        if hasattr(self.timeline, 'load_waveform'): self.timeline.load_waveform(path)
        self.video_fps = 30.0
        try:
            cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=r_frame_rate', '-of', 'json', path]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=3)
            probe = json.loads(res.stdout)
            fps_str = probe.get('streams', [{}])[0].get('r_frame_rate', '30/1')
            if '/' in fps_str:
                n, d = fps_str.split('/')
                self.video_fps = float(n) / float(d) if float(d) != 0 else 30.0
            else:
                self.video_fps = float(fps_str)
        except Exception: pass
        self._vid_wait_cnt = 0
        def init_video():
            self._vid_wait_cnt += 1
            if not hasattr(self, 'video_player') or self.video_player.total_time <= 0.1:
                if self._vid_wait_cnt < 20:
                    QTimer.singleShot(100, init_video); return
            if hasattr(self, 'media_path'):
                settings = QSettings("AI_PD_Studio", "Timeline")
                last_pos = settings.value(f"last_pos_{self.media_path}", 0.0, type=float)
                if last_pos > 0:
                    if hasattr(self, 'video_player'): self.video_player.seek(last_pos)
                    if hasattr(self, 'timeline'):
                        self.timeline.set_playhead(last_pos)
                        self.timeline.center_to_sec(last_pos, smooth=False)
                else:
                    if hasattr(self, 'video_player'): self.video_player.seek(0.0)
            if hasattr(self, 'video_player'): self.video_player.pause_video()
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
            pixmap = QPixmap(24, 24); pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(color_hex)); painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(4, 4, 16, 16); painter.end()
            return QIcon(pixmap)
        added = 0
        for spk in available_spks:
            if spk == current_spk_id: continue
            color_hex = spk_map.get(spk, "#FFFFFF")
            action = menu.addAction(make_circle_icon(color_hex), f"화자 {int(spk)+1}로 변경")
            action.triggered.connect(lambda checked, s=spk: self._change_speaker_for_line(line_num, s))
            added += 1
        if added > 0: menu.exec(gpos)

    def _change_speaker_for_line(self, line_num: int, new_spk_id: str):
        self._undo_mgr.push_immediate() # 💡 [추가] 화자 변경 직전에 찰칵!
        doc = self.text_edit.document(); block = doc.findBlockByNumber(line_num)
        if block.isValid():
            ud = block.userData()
            if isinstance(ud, SubtitleBlockData):
                old_start = ud.start_sec; ud.spk_id = new_spk_id
                for i in range(line_num + 1, doc.blockCount()):
                    b = doc.findBlockByNumber(i); u = b.userData()
                    if isinstance(u, SubtitleBlockData) and abs(u.start_sec - old_start) < 0.05 and not u.is_gap:
                        u.spk_id = new_spk_id
                    else: break
                self._highlighter.rehighlight()
                if hasattr(self.text_edit, 'timestampArea'): self.text_edit.timestampArea.update()
                self._schedule_timeline()

    def _on_speaker_circle_dropped(self, from_line: int, to_line: int):
        self._undo_mgr.push_immediate() # 💡 [추가] 화자 복사 직전에 찰칵!
        if from_line == to_line: return
        doc = self.text_edit.document()
        start_idx = min(from_line, to_line); end_idx = max(from_line, to_line)
        blocks_data = []
        for i in range(start_idx, end_idx + 1):
            b = doc.findBlockByNumber(i); ud = b.userData()
            new_ud = SubtitleBlockData(ud.spk_id, ud.start_sec, ud.is_gap) if ud else None
            blocks_data.append({"text": b.text(), "ud": new_ud})
        if from_line < to_line:
            item = blocks_data.pop(0); blocks_data.append(item)
        else:
            item = blocks_data.pop(); blocks_data.insert(0, item)
        cursor = QTextCursor(doc); cursor.beginEditBlock()
        for i, idx in enumerate(range(start_idx, end_idx + 1)):
            b = doc.findBlockByNumber(idx)
            cursor.setPosition(b.position())
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(blocks_data[i]["text"])
            new_b = doc.findBlockByNumber(idx)
            if blocks_data[i]["ud"]: new_b.setUserData(blocks_data[i]["ud"])
        self.text_edit.update_margins(); cursor.endEditBlock()
        self._highlighter.rehighlight()
        if hasattr(self.text_edit, 'timestampArea'): self.text_edit.timestampArea.update()
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
        self._undo_mgr.push_immediate() # 💡 추가
        cur = self.text_edit.textCursor()
        if cur.hasSelection():
            self.text_edit.cut(); return
        sec = getattr(self.video_player, 'current_time', 0.0)
        block = cur.block(); ud = block.userData()
        spk = ud.spk_id if isinstance(ud, SubtitleBlockData) else "00"
        cur.beginEditBlock()
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cur.insertText("\n새자막")
        cur.block().setUserData(SubtitleBlockData(spk, sec))
        self.text_edit.update_margins(); cur.endEditBlock()
        self._redraw_timeline()

    def _set_segment_start_to_playhead(self):
        sself._undo_mgr.push_immediate() # 💡 추가
        sec = getattr(self.video_player, 'current_time', 0.0)
        cur = self.text_edit.textCursor(); block = cur.block(); ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or ud.is_gap: return
        
        orig_start = ud.start_sec
        cur.beginEditBlock()
        
        # 💡 [버그 수정] 두 줄 이상인 자막의 '첫 번째 줄'을 정확히 찾습니다.
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
                c.movePosition(QTextCursor.MoveOperation.EndOfBlock); c.insertText("\n")
                gap_block = prev_block.next()
                gap_block.setUserData(SubtitleBlockData("00", orig_start, is_gap=True))
                
        # 💡 [핵심] 현재 자막 덩어리에 속한 '모든 줄'의 시작 시간을 한 번에 업데이트!
        b = first_block
        while b.isValid():
            b_ud = b.userData()
            if isinstance(b_ud, SubtitleBlockData) and not b_ud.is_gap and abs(b_ud.start_sec - orig_start) < 0.05:
                b_ud.start_sec = sec
                b = b.next()
            else:
                break
                
        self.text_edit.update_margins(); cur.endEditBlock()
        if hasattr(self.text_edit, 'timestampArea'): self.text_edit.timestampArea.update()
        self._redraw_timeline()

    def _set_segment_end_to_playhead(self):
        self._undo_mgr.push_immediate() # 💡 이제 Cmd+Z로 완벽하게 돌아옵니다.
        sec = getattr(self.video_player, 'current_time', 0.0)
        cur = self.text_edit.textCursor(); block = cur.block(); ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or ud.is_gap: return
        
        orig_start = ud.start_sec
        if sec <= orig_start: return 

        cur.beginEditBlock()
        # 💡 [버그 수정] 이 자막 덩어리의 진짜 '마지막 줄'을 끝까지 추적합니다.
        last_block = block
        while True:
            nxt = last_block.next()
            if nxt.isValid():
                n_ud = nxt.userData()
                if isinstance(n_ud, SubtitleBlockData) and not n_ud.is_gap and abs(n_ud.start_sec - orig_start) < 0.05:
                    last_block = nxt
                else: break
            else: break
                
        next_block = last_block.next()
        if next_block.isValid() and isinstance(next_block.userData(), SubtitleBlockData) and next_block.userData().is_gap:
            next_block.userData().start_sec = sec
        else:
            # 💡 마지막 줄 다음에 정확하게 엔터를 쳐서 다음 자막 밀림을 방지합니다.
            c = QTextCursor(last_block)
            c.movePosition(QTextCursor.MoveOperation.EndOfBlock); c.insertText("\n")
            gap_block = last_block.next()
            gap_block.setUserData(SubtitleBlockData("00", sec, is_gap=True))
            
        cur.endEditBlock()
        self.text_edit.update_margins()
        if hasattr(self.text_edit, 'timestampArea'): self.text_edit.timestampArea.update()
        self._redraw_timeline()

    # [ui/editor_timeline_video.py] EditorTimelineVideoMixin 클래스의 맨 아랫부분에 추가
    # 💡 [신규] 선택된 세그먼트 우클릭 시 분할 처리 핸들러
    def _on_timeline_seg_right_clicked(self, start_sec: float, gpos: QPoint):
        # 1. 우클릭된 세그먼트가 현재 선택된(노란색) 세그먼트인지 확인
        if self._active_seg_start is not None and abs(start_sec - self._active_seg_start) < 0.05:
            # 💡 맞다면, 기존 분할 함수 호출 (내부적으로 Cmd+Z 스냅샷 찍음)
            self._split_at_playhead_or_cut()
            # 마우스 이벤트 전파 방지 (컨텍스트 메뉴 표시 안 함)
            return
            
        # 2. 만약 선택된 세그먼트가 아니라면, Qt의 기본 컨텍스트 메뉴(예: 화자 변경)를 표시하기 위해 이벤트를 전파합니다.
        # 실제 컨텍스트 메뉴 표시는 TimelineCanvas 소관입니다.
        pass