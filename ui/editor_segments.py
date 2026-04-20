# Version: 01.00.05
"""
ui/editor_segments.py
EditorWidget의 자막 에디터 조작, 큐 처리, 세그먼트 I/O 메서드 모음.
[수정] core 폴더 이동에 따른 데이터 매니저 경로 및 상대 경로 최적화 완료
"""
import re, os, threading
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QTextCursor

from logger import get_logger

# 💡 [경로 수정] editor_data_manager -> core.data_manager
from core.data_manager import save_correction as _dm_save_correction

# 수정 — 절대 import로 통일 (editor_widget.py, editor_timeline_video.py와 동일)
from ui.subtitle_text_edit import SubtitleBlockData
from ui.editor_helpers import get_sub_block_indices

class EditorSegmentsMixin:
    """자막 에디터 조작 / 큐 처리 / 세그먼트 I/O"""
    # ---------------------------------------------------------
    # Common Helpers (여러 Mixin에서 공용)
    # ---------------------------------------------------------
    def _mark_dirty(self):
        if hasattr(self, "sm"):
            self.sm.is_dirty = True
        else:
            self._is_dirty = True

    def _finalize_edit(self):
        self.text_edit.update_margins()
        if hasattr(self.text_edit, 'timestampArea'):
            self.text_edit.timestampArea.update()
        self._schedule_timeline()

    # ---------------------------------------------------------
    # Segment Queue
    # ---------------------------------------------------------
    def append_segments(self, segments: list[dict]):
        try: self.status_lbl.text()
        except RuntimeError: return
        if threading.current_thread() is not threading.main_thread():
            QTimer.singleShot(0, lambda s=list(segments): self.append_segments(s))
            return
        self._segment_queue.extend(segments)
        if not self._queue_timer.isActive():
            self._queue_timer.start(80)

    def _flush_queue(self):
        try: self.text_edit.toPlainText()
        except RuntimeError: return

        if not self._segment_queue:
            return

        cont_thresh = float(self.settings.get("continuous_threshold", 2.0))
        pull_rate = float(self.settings.get("gap_pull_rate", 0.3))
        push_rate = float(self.settings.get("gap_push_rate", 0.7))
        single_ext = float(self.settings.get("single_subtitle_end", 0.2))
        is_initial = getattr(self, '_is_initial_load', False)

        doc = self.text_edit.document()
        orig_cursor = self.text_edit.textCursor()
        is_at_bottom = (orig_cursor.position() >= doc.characterCount() - 5)

        cur = QTextCursor(doc)
        cur.beginEditBlock()
        cur.movePosition(QTextCursor.MoveOperation.End)

        # 💡 1. [핵심 버그 수정] 꼬리(Gap)를 지우기 전에 이전 자막의 끝 시간을 미리 확보!
        prev_end_orig = -1.0
        has_prev_gap = False
        
        if not is_initial and doc.blockCount() > 0:
            lb = doc.lastBlock()
            ud = lb.userData()
            # 마지막 줄이 빈 줄(Gap)이라면 순수한 끝 시간을 기억합니다.
            if not lb.text().strip() and isinstance(ud, SubtitleBlockData) and ud.is_gap:
                has_prev_gap = True
                prev_end_orig = max(0.0, ud.start_sec - single_ext)

        # 💡 2. 꼬리 지우기 (여기서 기존 Gap 블록이 화면에서 정리됨)
        while doc.blockCount() > 0:
            last_block = doc.lastBlock(); last_text = last_block.text()
            if not last_text.strip():
                cur.setPosition(last_block.position())
                cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                cur.removeSelectedText()
                if doc.blockCount() > 1: cur.deletePreviousChar()
                else: break
            else: break

        cur.movePosition(QTextCursor.MoveOperation.End)

        # 💡 3. [핵심 로직 복구] 삭제된 Gap 정보를 바탕으로 대표님이 설정한 미루기/당기기 비율 적용!
        if has_prev_gap and self._segment_queue and not is_initial:
            curr_start = self._segment_queue[0]['start']
            gap = curr_start - prev_end_orig
            
            if 0 < gap <= cont_thresh:
                new_prev_end = prev_end_orig + gap * push_rate
                # 🎯 드디어 대표님이 설정한 '당기기' 비율만큼 자막 시작 시간이 앞당겨집니다!
                self._segment_queue[0]['start'] = prev_end_orig + gap - (gap * pull_rate)
                
                # 당기고 남은 빈 공간이 있다면 다시 Gap 블록 재생성
                if self._segment_queue[0]['start'] > new_prev_end + 0.05:
                    if doc.lastBlock().text().strip(): cur.insertText("\n")
                    cur.insertText("\n")
                    cur.block().setUserData(SubtitleBlockData("00", round(new_prev_end, 2), is_gap=True))
                    cur.insertText("\n") # 다음 자막이 쓸 줄 확보
                    
            elif gap > cont_thresh:
                new_prev_end = prev_end_orig + single_ext
                self._segment_queue[0]['start'] = max(0.0, curr_start - single_ext)
                if self._segment_queue[0]['start'] > new_prev_end + 0.05:
                    if doc.lastBlock().text().strip(): cur.insertText("\n")
                    cur.insertText("\n")
                    cur.block().setUserData(SubtitleBlockData("00", round(new_prev_end, 2), is_gap=True))
                    cur.insertText("\n")

        # 💡 4. 내부 청크들 간의 간격 연산
        last_end = -1.0
        for i in range(len(self._segment_queue)):
            curr = self._segment_queue[i]
            
            if not is_initial:
                if curr['start'] < last_end: curr['start'] = last_end
                
                if i + 1 < len(self._segment_queue):
                    nxt = self._segment_queue[i+1]
                    gap = nxt['start'] - curr['end']
                    if 0 < gap <= cont_thresh:
                        curr['end'] += gap * push_rate
                        nxt['start'] -= gap * pull_rate
                    elif gap > cont_thresh:
                        curr['end'] += min(single_ext, gap / 2.0)
                        nxt['start'] -= min(single_ext, gap / 2.0)
                else: 
                    curr['end'] += single_ext
                    
            last_end = curr['end']

        if doc.lastBlock().text().strip(): cur.insertText("\n")
        added_end = self._segment_queue[-1]['end'] if self._segment_queue else 0.0

        # 💡 [여기서부터 수정: 화자 분리 로직]
        spk1_id = self.settings.get("spk1_id", "00")
        spk2_id = self.settings.get("spk2_id", "01")

        for i in range(len(self._segment_queue)):
            seg = self._segment_queue[i]; text = seg.get("text", "")
            spk_list = seg.get("speaker_list", [spk1_id])
            
            text = self._JUNK_TS_RE.sub('', text)
            text = self._JUNK_NO_BRACKET_3PART.sub('', text)
            text = self._JUNK_NO_BRACKET_3PART_END.sub('', text)
            text = self._JUNK_START_RE.sub('', text).strip()
            text = text.replace('\r', '')
            # ✅ HTML 태그 제거
            text = re.sub(r'<[^>]+>', '', text)

            parts = [re.sub(r'\s+', ' ', p).strip() for p in text.split('\n')]
            parts = [p for p in parts if p]
            if not parts: continue
            
            start_sec = round(max(0, seg.get("start", 0)), 2)
            
            # 💡 첫 번째 줄 삽입
            current_spk = spk_list[0] if len(spk_list) > 0 else spk1_id
            cur.insertText(parts[0])
            cur.block().setUserData(SubtitleBlockData(current_spk, start_sec))
            
            # 💡 두 번째 줄부터의 처리 (- 기호 유무로 완벽 통제)
            for p_idx in range(1, len(parts)):
                line_text = parts[p_idx]
                
                if line_text.startswith('-'):
                    # 🚨 '-' 기호가 있으면: 진짜 엔터(\n)를 쳐서 블록을 나누고 화자를 교체합니다.
                    current_spk = spk2_id if current_spk == spk1_id else spk1_id
                    cur.insertText("\n" + line_text)
                    cur.block().setUserData(SubtitleBlockData(current_spk, start_sec))
                else:
                    # 🚨 '-' 기호가 없으면: 화자를 유지하고 소프트 줄바꿈(\u2028)만 삽입하여 1개의 블록으로 묶습니다.
                    cur.insertText("\u2028" + line_text)
            
            if i + 1 < len(self._segment_queue):
                nxt = self._segment_queue[i+1]
                if seg['end'] < nxt['start'] - 0.05:
                    gap_start = round(seg['end'], 2)
                    cur.insertText("\n") 
                    cur.block().setUserData(SubtitleBlockData("00", gap_start, is_gap=True))
                    # 💡 [핵심 해결] 무음 블록(빈 줄)을 확보했으니, 다음 자막이 쓸 새로운 줄을 한 번 더 만들어 줍니다!
                    cur.insertText("\n") 
                else:
                    cur.insertText("\n")
            else:
                gap_start = round(seg['end'], 2)
                cur.insertText("\n")
                cur.block().setUserData(SubtitleBlockData("00", gap_start, is_gap=True))

        self._segment_queue.clear()
        self.text_edit.update_margins()
        cur.endEditBlock()

        self._sync_lock = True
        if is_at_bottom: self.text_edit.setTextCursor(cur)
        else: self.text_edit.setTextCursor(orig_cursor)
        self._sync_lock = False

        self._schedule_timeline()

        if is_initial:
            self._is_initial_load = False
            if hasattr(self, 'timeline'):
                self.timeline.set_playhead(0.0); self.timeline.center_to_sec(0.0, smooth=True)
            if hasattr(self, 'video_player'):
                self.video_player.seek(0.0)
        elif added_end > 0.0:
            if hasattr(self, 'timeline'):
                self.timeline.set_playhead(added_end); self.timeline.center_to_sec(added_end, smooth=True)
            if hasattr(self, 'video_player'):
                self.video_player.seek(added_end)

    # ---------------------------------------------------------
    # Segment I/O
    # ---------------------------------------------------------

    def _get_current_segments(self) -> list[dict]:
        segments = []
        block = self.text_edit.document().begin()
        line_idx = 0
        
        while block.isValid():
            data = block.userData()
            text = block.text().strip()
            is_gap = getattr(data, 'is_gap', False) if data else False
            
            # ✅ [#1 핵심 수정] 갭 블록도 포함 — 무음구간이 End Time 계산에 반영됩니다
            if data is not None and (text or is_gap):
                # ✅ 갭 블록은 절대 이전 세그먼트에 병합하지 않음 (갭↔자막 병합 방지)
                if (not is_gap
                    and segments
                    and not segments[-1].get("is_gap")
                    and abs(segments[-1]["start"] - data.start_sec) < 0.05):
                    segments[-1]["text"] += "\n" + text
                else:
                    segments.append({
                        "line": line_idx,
                        "start": data.start_sec,
                        "end": getattr(data, 'end_sec', None),
                        "text": text,
                        "is_gap": is_gap,
                        "spk": getattr(data, 'spk_id', 'SPEAKER_00')
                    })
            
            block = block.next()
            line_idx += 1

        # 2. 끝 시간(End Time) 계산
        for i, seg in enumerate(segments):
            is_last = (i + 1 == len(segments))
            
            if is_last:
                if hasattr(self, 'video_player') and getattr(self.video_player, 'total_time', 0) > seg["start"]:
                    next_start = self.video_player.total_time if seg.get("is_gap") else min(seg["start"] + 3.0, self.video_player.total_time)
                else:
                    next_start = seg["start"] + 3.0
            else:
                next_start = segments[i+1]["start"]
                
            c_end = seg.get("end") 
            if c_end is not None and seg["start"] < c_end <= next_start + 0.05:
                seg["end"] = c_end
            else:
                seg["end"] = next_start
                
        return segments

    # ---------------------------------------------------------
    # Text Editor Event Handlers
    # ---------------------------------------------------------
    def _trigger_editor_popup(self, word, anchor, end_c, gpos):
        self.editor_popup.trigger(word, anchor, end_c, gpos)

    def _on_selection_changed(self):
        if not self.text_edit.textCursor().hasSelection():
            if self.editor_popup.is_visible(): self.editor_popup.close_popup()

    def _save_correction(self, old_word, new_word):
        _dm_save_correction(self.corrections, old_word, new_word)
        get_logger().log(f"🔄 교정 사전 등록 및 저장: {old_word} -> {new_word}")

    def _on_enter_pressed(self, last_word: str, line_num: int):
        self._undo_mgr.push() # 💡 실행취소 스냅샷 추가
        try: from utils import add_split_rule; add_split_rule(last_word)
        except Exception: pass
        self._schedule_timeline()

    def _on_backspace_merged(self, removed_word: str):
        self._undo_mgr.push() # 💡 실행취소 스냅샷 추가
        try: from utils import remove_split_rule; remove_split_rule(removed_word)
        except Exception: pass
        self._schedule_timeline()

    def _on_cursor_moved(self):
        if self._sync_lock: return
        line_num = self.text_edit.textCursor().blockNumber()
        # [크PD] 캐시 사용 — 커서 이동마다 전체 문서 재파싱 방지
        segs = getattr(self, '_cached_segs', None) or self._get_current_segments()
        for seg in reversed(segs):
            if seg["line"] <= line_num:
                if self._active_seg_start != seg["start"]:
                    if hasattr(self, 'video_player'): self.video_player.pause_video()
                    self._active_seg_start = seg["start"]
                    self.timeline.set_active(seg["start"])
                    self.timeline.center_to_sec((seg["start"] + seg["end"]) / 2, smooth=True)
                    self._highlighter.set_current_line(line_num)
                    if hasattr(self, 'video_player'): self.video_player.seek(seg["start"])
                break

    def _on_esc_pressed(self):
        if hasattr(self.timeline, 'canvas'): self.timeline.canvas.update()

    # ---------------------------------------------------------
    # Timeline Schedule
    # ---------------------------------------------------------
    def _redraw_timeline(self):
        segs = self._get_current_segments()
        self._cached_segs = segs  # [크PD] 캐시 저장
        total_dur = segs[-1]["end"] if segs else 0.0
        if hasattr(self, 'video_player') and self.video_player.total_time > 0.0:
            total_dur = max(total_dur, self.video_player.total_time)
        self.timeline.update_segments(segs, self._active_seg_start, total_dur)
        if hasattr(self, 'video_player'): self.video_player.segments = segs

    def _schedule_timeline(self):
        if getattr(self, '_inline_updating', False): return
        if not self._timeline_timer.isActive(): self._timeline_timer.start(150)  # [크PD] 300→150ms 실시간성 개선

    def _on_drag_started(self): 
        # 💡 드래그를 시작하기 직전의 전체 뷰 스냅샷 저장!
        self._undo_mgr.push_immediate()
        
        self._drag_cursor = QTextCursor(self.text_edit.document())
        self._drag_cursor.beginEditBlock()
        
    def _on_drag_finished(self): 
        if hasattr(self, '_drag_cursor') and self._drag_cursor:
            self._drag_cursor.endEditBlock()
            self._drag_cursor = None
        self._schedule_timeline()

    # 💡 [신규] 특정 시간대의 블록을 지우고 새 자막으로 교체하는 외과 수술 로직
    # 💡 1. 선제적 삭제 및 위치 기억 (버튼 누르자마자 즉시 실행)
    def clear_segments_in_range(self, target_start: float, target_end: float):
        self._undo_mgr.push_immediate()
        doc = self.text_edit.document()
        cur = QTextCursor(doc)
        
        start_block, end_block = None, None
        for i in range(doc.blockCount()):
            b = doc.findBlockByNumber(i)
            ud = b.userData()
            if ud and hasattr(ud, 'start_sec'):
                if ud.start_sec >= target_start and start_block is None:
                    start_block = b
                if ud.start_sec >= target_end and start_block is not None:
                    end_block = b; break
        
        cur.beginEditBlock()
        if start_block:
            # 🚨 [쓰레기 자막 방지] 삭제 후 뒤로 밀려날 블록의 고유 시간 데이터를 백업합니다.
            end_ud = end_block.userData() if end_block else None
            
            cur.setPosition(start_block.position())
            if end_block: cur.setPosition(end_block.position(), QTextCursor.MoveMode.KeepAnchor)
            else: cur.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
            
            cur.removeSelectedText()
            
            # 단면이 붙지 않게 빈 줄(방화벽) 생성 후 백업 데이터 복구
            if end_block:
                cur.insertText("\n")
                if end_ud:
                    cur.block().setUserData(SubtitleBlockData(end_ud.spk_id, end_ud.start_sec, end_ud.is_gap))
                cur.movePosition(QTextCursor.MoveOperation.PreviousBlock)
            else:
                while cur.block().text().strip() == "" and doc.blockCount() > 1:
                    cur.deletePreviousChar()
            
            # 삽입될 '절대 위치' 기억
            self._partial_insert_pos = cur.position() 
        else:
            cur.movePosition(QTextCursor.MoveOperation.End)
            if not cur.atBlockStart(): cur.insertText("\n")
            self._partial_insert_pos = cur.position()
            
        self.text_edit.update_margins()
        cur.endEditBlock()
        self._schedule_timeline()
    
    # 💡 2. 기억된 위치에 정밀 삽입 (자동저장 차단)
    # [ui/editor_segments.py] insert_partial_segments 함수 교체
    def insert_partial_segments(self, new_segments: list[dict]):
        try:
            self._undo_mgr.push_immediate()
            doc = self.text_edit.document()
            cur = QTextCursor(doc)
            if hasattr(self, '_partial_insert_pos'): cur.setPosition(self._partial_insert_pos)
            else: cur.movePosition(QTextCursor.MoveOperation.End)
                
            cur.beginEditBlock()
            spk1_id = self.settings.get("spk1_id", "00")
            spk2_id = self.settings.get("spk2_id", "01")
            from ui.subtitle_text_edit import SubtitleBlockData
            
            for i, seg in enumerate(new_segments):
                if not cur.atBlockStart(): cur.insertBlock()
                text = seg.get("text", "").replace("\r", "")
                parts = [p.strip() for p in text.split('\n') if p.strip()]
                if not parts: continue
                
                start_sec = round(seg.get("start", 0), 2)
                current_spk = seg.get("speaker_list", [spk1_id])[0] if seg.get("speaker_list") else spk1_id
                
                cur.insertText(parts[0])
                cur.block().setUserData(SubtitleBlockData(current_spk, start_sec))
                
                # 💡 [복구] 줄바꿈 및 화자 분리 로직 완벽 구현
                for p_idx in range(1, len(parts)):
                    line_text = parts[p_idx]
                    if line_text.startswith('-'):
                        current_spk = spk2_id if current_spk == spk1_id else spk1_id
                        cur.insertBlock() 
                        cur.insertText(line_text)
                        cur.block().setUserData(SubtitleBlockData(current_spk, start_sec))
                    else:
                        cur.insertText("\u2028" + line_text) 
                
                # Gap 처리
                gap_start = round(seg['end'], 2)
                if i + 1 < len(new_segments):
                    if seg['end'] < new_segments[i+1]['start'] - 0.05:
                        cur.insertBlock()
                        cur.block().setUserData(SubtitleBlockData("00", gap_start, is_gap=True))
                else:
                    cur.insertBlock()
                    cur.block().setUserData(SubtitleBlockData("00", gap_start, is_gap=True))

            # 💡 [핵심 수정] 상태 머신의 더티 플래그를 활성화합니다!
            self._mark_dirty()
                
            self.text_edit.update_margins()
            cur.endEditBlock()
            self._schedule_timeline()
        except Exception as e:
            from logger import get_logger
            get_logger().log(f"⚠️ 정밀 삽입 오류: {e}")

    
    def split_segment_with_text(self, line_num: int, split_sec: float, cursor: int):
        """
        플레이헤드 시간(split_sec) + 텍스트 커서(cursor) 기준으로
        현재 세그먼트를 2개로 분리한다.

        [v01.00.04]
        - block.text() 직접 사용 (canvas stale 데이터 참조 제거)
        - secondary_block_positions 삭제 로직 제거
          (현재 _get_current_segments()는 블록별 독립 세그먼트로 관리하므로
           같은 start_sec인 인접 블록을 지우면 다른 자막이 삭제되는 버그 발생)
        - '-' 화자 구분자 제거
        """
        doc = self.text_edit.document()
        block = doc.findBlockByNumber(int(line_num))
        if not block.isValid():
            return

        try:
            self._undo_mgr.push_immediate()
        except Exception:
            pass

        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData):
            return

        start_sec = float(ud.start_sec)
        spk_id    = ud.spk_id
        split_sec = float(split_sec)

        # 범위 체크
        try:
            canvas_segs = self.timeline.canvas.segments
            end_map = {s.get("line"): float(s.get("end", 0.0))
                       for s in canvas_segs if s.get("line") is not None}
            end_sec = end_map.get(int(line_num))
            if end_sec is not None:
                if split_sec <= start_sec + 0.05 or split_sec >= end_sec - 0.05:
                    return
            else:
                if split_sec <= start_sec + 0.05:
                    return
        except Exception:
            if split_sec <= start_sec + 0.05:
                return

        # block.text() 직접 사용 (sig_inline_text_changed로 항상 최신 상태 보장)
        full_text = block.text().replace("\u2028", "\n")

        cursor = max(0, min(int(cursor), len(full_text)))
        left  = full_text[:cursor].rstrip()
        right = full_text[cursor:].lstrip()

        # ✅ 수정: right가 비어있으면 "새자막"으로 대체
        if not left:
            return
        if not right:
            right = "새자막"

        def _strip_leading_dash(t: str) -> str:
            lines = [l.strip() for l in t.splitlines() if l.strip()]
            if not lines:
                return ""
            if lines[0].startswith("-"):
                lines[0] = lines[0].lstrip("-").strip()
            return "\n".join(lines)

        left  = _strip_leading_dash(left)
        right = _strip_leading_dash(right)

        # ✅ 수정: right가 비어있으면 "새자막"으로 대체
        if not left:
            return
        if not right:
            right = "새자막"

        left_doc  = left.replace("\n", "\u2028")
        right_doc = right.replace("\n", "\u2028")

        cur = QTextCursor(block)
        cur.beginEditBlock()

        # primary block → left 파트로 교체 (StartOfBlock~EndOfBlock 범위만 선택)
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                         QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        cur.insertText(left_doc)
        cur.block().setUserData(
            SubtitleBlockData(spk_id, round(start_sec, 2), is_gap=False)
        )

        # 새 블록 삽입 → right 파트
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cur.insertBlock()
        cur.insertText(right_doc)
        cur.block().setUserData(
            SubtitleBlockData(spk_id, round(split_sec, 2), is_gap=False)
        )

        cur.endEditBlock()

        # 💡 [타임라인 튕김 완벽 방지] 커서 이동 시 화면이 중앙으로 강제 점프하는 것을 잠급니다.
        self._sync_lock = True  # 자동 센터링 방지 잠금
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        self.text_edit.setTextCursor(cur)
        
        self._active_seg_start = round(split_sec, 2)
        if hasattr(self, 'timeline'):
            self.timeline.set_active(self._active_seg_start)
            # 🎯 자막의 중간이 아니라, 대표님이 우클릭한 그 시점(split_sec)을 중앙으로!
            self.timeline.center_to_sec(split_sec, smooth=True)
        self._sync_lock = False

        self._mark_dirty()
        self._finalize_edit()
