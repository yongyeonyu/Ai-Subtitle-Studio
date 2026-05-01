# Version: 03.02.06
# Phase: PHASE1-B
"""
ui/editor_timeline_video.py
[v01.01.00] 리팩토링: editor_helpers 통합 + probe_media 적용
- Gap 헬퍼 → editor_helpers.py로 완전 이관
- ffprobe 직호출 → core.media_info.probe_media() 통합
- find_segment_at / get_sub_block_indices / _sync_cursor_to_seg 적용
- _mark_dirty / _finalize_edit 공용 메서드 활용
"""

import time
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QTextCursor

from ui.editor.subtitle_text_edit import SubtitleBlockData
from ui.editor.editor_helpers import (
    find_segment_at, get_sub_block_indices,
    make_gap_ud, delete_block_safely, insert_gap_after,
    merge_adjacent_gaps_around
)



class EditorTimelineVideoMixin:
    """타임라인/비디오 동기화 / 화자 관리 / 단축키 액션"""

    def _reset_playhead_smoothing(self, sec: float | None = None):
        base_sec = float(sec if sec is not None else getattr(self.timeline.canvas, "playhead_sec", 0.0) or 0.0)
        self._playhead_display_sec = max(0.0, base_sec)
        self._playhead_anchor_global_sec = max(0.0, base_sec)
        self._playhead_anchor_mono = time.monotonic()

    def _smooth_playhead_sec(self, raw_global_sec: float, now_mono: float, dur_sec: float) -> float:
        raw_global_sec = max(0.0, float(raw_global_sec or 0.0))
        dur_sec = max(0.0, float(dur_sec or 0.0))
        display = getattr(self, "_playhead_display_sec", None)
        anchor_sec = getattr(self, "_playhead_anchor_global_sec", None)
        anchor_mono = getattr(self, "_playhead_anchor_mono", None)
        if display is None or anchor_sec is None or anchor_mono is None:
            self._reset_playhead_smoothing(raw_global_sec)
            return raw_global_sec

        predicted = float(anchor_sec) + max(0.0, now_mono - float(anchor_mono))
        if dur_sec > 0:
            predicted = min(predicted, dur_sec + self._multiclip_active_offset())

        drift = raw_global_sec - predicted
        if abs(drift) >= 0.35:
            smoothed = raw_global_sec
        elif drift >= 0.0:
            smoothed = predicted + drift * 0.35
        else:
            smoothed = predicted + drift * 0.08

        previous = float(display)
        max_step = max(0.018, min(0.08, now_mono - float(getattr(self, "_last_playhead_smooth_tick", now_mono) or now_mono) + 0.018))
        if smoothed < previous and previous - smoothed < 0.18:
            smoothed = previous
        elif smoothed > previous + max_step:
            smoothed = previous + max_step

        self._last_playhead_smooth_tick = now_mono
        self._playhead_display_sec = max(0.0, smoothed)
        self._playhead_anchor_global_sec = raw_global_sec
        self._playhead_anchor_mono = now_mono
        return self._playhead_display_sec

    def _multiclip_active_offset(self) -> float:
        owner = self.window()
        bounds = list(getattr(owner, '_multiclip_boundaries', []) or [])
        if not bounds:
            return 0.0
        clip_idx = int(getattr(self.timeline.canvas, '_active_clip_idx', getattr(owner, '_active_clip_idx', 0)) or 0)
        clip_idx = max(0, min(clip_idx, len(bounds) - 1))
        return float(bounds[clip_idx].get('start', 0.0))

    def _global_to_local_sec(self, sec: float) -> float:
        return max(0.0, float(sec) - self._multiclip_active_offset())

    def _local_to_global_sec(self, sec: float) -> float:
        return max(0.0, float(sec) + self._multiclip_active_offset())


    # ---------------------------------------------------------
    # Common: Cursor ↔ Block Sync
    # ---------------------------------------------------------
    def _sync_cursor_to_seg(self, seg, ensure_visible=True, move_cursor=True):
        """커서↔블록 동기화: active/하이라이트 + (옵션) 커서 이동"""
        self._active_seg_start = seg["start"]
        # 재생 중에는 set_active()가 내부 smooth scroll을 유발하므로 canvas만 직접 갱신
        player = getattr(getattr(self, 'video_player', None), 'media_player', None)
        is_playing = bool(player and player.playbackState() == player.PlaybackState.PlayingState)
        if is_playing and hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
            self.timeline.canvas.set_active(seg["start"])
        else:
            self.timeline.set_active(seg["start"])
        if (not is_playing) and hasattr(self, 'timeline') and hasattr(self.timeline, 'set_playhead'):
            self._reset_playhead_smoothing(seg["start"])
            self.timeline.set_playhead(seg["start"])
        line_num = seg.get("line", 0)
        self._highlighter.set_current_line(line_num)
        if not move_cursor:
            return
        block = self.text_edit.document().findBlockByNumber(line_num)
        if block.isValid():
            self._sync_lock = True
            cur = QTextCursor(block)
            self.text_edit.setTextCursor(cur)
            if ensure_visible:
                self.text_edit.ensureCursorVisible()
            self._sync_lock = False

    # ---------------------------------------------------------
    # Timeline Segment Events
    # ---------------------------------------------------------

    def _on_timeline_seg_clicked(self, line_num, start_sec):
        segs = self._get_current_segments()
        seg = next((s for s in segs if s["line"] == line_num), None)
        if seg:
            self._sync_cursor_to_seg(seg)
            self.timeline.center_to_sec((seg["start"] + seg["end"]) / 2, smooth=True)
            if hasattr(self, '_resolve_active_context') and hasattr(self, '_apply_active_context'):
                ctx = self._resolve_active_context(global_sec=float(start_sec))
                self._apply_active_context(ctx, autoplay=False, show_thumbnail=True)
            elif hasattr(self, 'video_player'):
                self.video_player.pause_video()
                self.video_player.seek_direct(float(start_sec))
        self.text_edit.setFocus()
        self._redraw_timeline()


    def _on_timeline_seg_double_clicked(self, line_num, start_sec):
        lock_box = getattr(self.timeline, 'lock_chk', getattr(self.timeline, 'lock_cb', None))
        if lock_box and lock_box.isChecked():
            return
        self._active_seg_start = start_sec
        self.timeline.set_active(start_sec)
        if hasattr(self, '_resolve_active_context') and hasattr(self, '_apply_active_context'):
            ctx = self._resolve_active_context(global_sec=float(start_sec))
            self._apply_active_context(ctx, autoplay=False, show_thumbnail=True)
        elif hasattr(self, 'video_player'):
            self.video_player.pause_video()
            self.video_player.seek_direct(float(start_sec))
        if hasattr(self.timeline, 'canvas') and hasattr(self.timeline.canvas, 'start_inline_edit'):
            self._undo_mgr.push_immediate()
            self.timeline.canvas.start_inline_edit(line_num, start_sec)

    def _sync_playhead(self):
        if not hasattr(self, 'video_player') or not hasattr(self, 'timeline'):
            return
        player = self.video_player.media_player
        if player.playbackState() != player.PlaybackState.PlayingState:
            self._reset_playhead_smoothing(getattr(self.timeline.canvas, "playhead_sec", 0.0))
            return
        pos_ms = player.position()
        dur_ms = player.duration()
        if dur_ms <= 0:
            return

        now_mono = time.monotonic()
        raw_sec = self._local_to_global_sec(pos_ms / 1000.0)
        current_sec = self._smooth_playhead_sec(raw_sec, now_mono, dur_ms / 1000.0)
        self.timeline.set_playhead(current_sec)

        # Context sync: skip resolve if within cached clip bounds (C fix v2)
        if hasattr(self, '_resolve_active_context') and hasattr(self, 'video_player'):
            _mc_boxes = list(getattr(self.timeline.canvas, '_multiclip_boxes', []) or []) if hasattr(self, 'timeline') else []
            if _mc_boxes:
                _cb = getattr(self, '_cached_clip_bounds', None)
                last_ctx_at = float(getattr(self, '_last_play_context_sync_at', 0.0) or 0.0)
                if not (_cb and _cb[0] <= current_sec < _cb[1]) and (now_mono - last_ctx_at) >= 0.25:
                    self._last_play_context_sync_at = now_mono
                    ctx = self._resolve_active_context(global_sec=current_sec)
                    _cidx = int(ctx.get('clip_idx', 0))
                    self._cached_clip_bounds = (float(ctx.get('clip_start', 0.0)), float(ctx.get('clip_end', 0.0)))
                    if _cidx != getattr(self, '_last_sync_clip_idx', -1):
                        self._last_sync_clip_idx = _cidx
                        self.video_player.set_context_segments(list(ctx.get('local_segments', []) or []))

        canvas = self.timeline.canvas
        viewport_w = self.timeline.scroll.viewport().width()
        center_x = max(0, int(current_sec * canvas.pps) - (viewport_w // 2))
        # 재생 중 direct setValue 금지: smooth target만 갱신 + 작은 변화는 무시
        last_scroll_at = float(getattr(self, '_last_play_scroll_sync_at', 0.0) or 0.0)
        if (now_mono - last_scroll_at) >= 0.10 and abs(float(center_x) - float(getattr(self.timeline, '_target_scroll_x', 0.0))) >= 24.0:
            self._last_play_scroll_sync_at = now_mono
            self.timeline._target_scroll_x = float(center_x)

        segs = getattr(self, '_cached_segs', None) or self._get_current_segments()
        seg = find_segment_at(segs, current_sec, skip_gap=True)
        if seg and self._active_seg_start != seg["start"]:
            # 재생 중에는 세그먼트 경계에서만 가볍게 하이라이트를 갱신한다.
            last_cursor_at = float(getattr(self, '_last_play_cursor_sync_at', 0.0) or 0.0)
            if (now_mono - last_cursor_at) >= 0.20:
                self._last_play_cursor_sync_at = now_mono
                self._sync_cursor_to_seg(seg, ensure_visible=False, move_cursor=False)
        if seg:
            last_scroll_at = float(getattr(self, '_last_editor_autoscroll_at', 0.0) or 0.0)
            editing_active = bool(getattr(self.timeline.canvas, '_edit_active', False)) if hasattr(self.timeline, 'canvas') else False
            if (not self.text_edit.hasFocus()) and (not editing_active) and (now_mono - last_scroll_at) >= 0.85:
                self._last_editor_autoscroll_at = now_mono
                self._sync_cursor_to_seg(seg, ensure_visible=True, move_cursor=True)
        if hasattr(self.video_player, 'refresh_subtitle_context'):
            self.video_player.refresh_subtitle_context()


    def _on_scrub(self, sec):
        self._reset_playhead_smoothing(sec)
        self.timeline.set_playhead(sec)
        if hasattr(self, '_resolve_active_context') and hasattr(self, '_apply_active_context'):
            ctx = self._resolve_active_context(global_sec=float(sec))
            self._apply_active_context(ctx, autoplay=False, show_thumbnail=True)
        elif hasattr(self, 'video_player'):
            self.video_player.pause_video()
            self.video_player.seek_direct(float(sec))
        segs = getattr(self, '_cached_segs', None) or self._get_current_segments()
        seg = find_segment_at(segs, sec, skip_gap=False)
        if seg and self._active_seg_start != seg["start"]:
            self._sync_cursor_to_seg(seg)
            self.timeline.center_to_sec(sec, smooth=True)


    def _on_step_frame(self, direction):
        if not hasattr(self, 'video_player'):
            return
        fps = getattr(self, 'video_fps', 30.0)
        frame_sec = 1.0 / fps
        current_global = float(getattr(self.timeline.canvas, 'playhead_sec', 0.0) or 0.0)
        new_global = max(0.0, current_global + (direction * frame_sec))
        if hasattr(self, '_resolve_active_context') and hasattr(self, '_apply_active_context'):
            ctx = self._resolve_active_context(global_sec=new_global)
            self._apply_active_context(ctx, autoplay=False, show_thumbnail=True)
        else:
            self.video_player.pause_video()
            self.video_player.seek_direct(new_global)
        segs = self._get_current_segments()
        seg = find_segment_at(segs, new_global, skip_gap=False)
        if seg and self._active_seg_start != seg["start"]:
            self._sync_cursor_to_seg(seg)
        self._reset_playhead_smoothing(new_global)
        self.timeline.set_playhead(new_global)
        self.timeline.center_to_sec(new_global, smooth=False)

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

        old_start = float(ud.start_sec)
        ud.start_sec = round(float(new_start), 2)

        for idx in get_sub_block_indices(doc, line_num, old_start)[1:]:
            u = doc.findBlockByNumber(idx).userData()
            if isinstance(u, SubtitleBlockData):
                u.start_sec = ud.start_sec

        sub_now = get_sub_block_indices(doc, line_num, ud.start_sec)
        last_idx = sub_now[-1] if sub_now else line_num
        last_block = doc.findBlockByNumber(last_idx)

        # ── 앞쪽 Gap 처리 ──
        prev_block = block.previous()
        if prev_block.isValid():
            prev_ud = prev_block.userData()
            if isinstance(prev_ud, SubtitleBlockData):
                if prev_ud.is_gap:
                    if abs(float(prev_ud.start_sec) - float(ud.start_sec)) < 0.05:
                        delete_block_safely(prev_block)
                else:
                    if edge_type not in ("diamond", "gap") and float(new_start) > old_start + 0.05:
                        insert_gap_after(prev_block, old_start)

        # ── 뒤쪽 Gap 처리 ──
        next_block = last_block.next()
        if next_block.isValid():
            next_ud = next_block.userData()
            if isinstance(next_ud, SubtitleBlockData):
                if not next_ud.is_gap:
                    is_same = abs(float(next_ud.start_sec) - float(ud.start_sec)) < 0.05
                    if (not is_same
                            and edge_type not in ("diamond", "gap")
                            and float(new_end) < float(next_ud.start_sec) - 0.05):
                        insert_gap_after(last_block, float(new_end))
                else:
                    next_next = next_block.next()
                    if next_next.isValid():
                        nnu = next_next.userData()
                        if isinstance(nnu, SubtitleBlockData) and abs(float(new_end) - float(nnu.start_sec)) < 0.05:
                            delete_block_safely(next_block)
                        else:
                            next_ud.start_sec = round(float(new_end), 2)
                    else:
                        next_ud.start_sec = round(float(new_end), 2)

        self.text_edit.update_margins()
        cur.endEditBlock()
        if hasattr(self.text_edit, 'timestampArea'):
            self.text_edit.timestampArea.update()
        QTimer.singleShot(0, self._redraw_timeline)

    def _on_seg_to_gap(self, line_num: int):
        """자막 세그먼트 → 무음구간(Gap)으로 변환"""
        self._undo_mgr.push_immediate()
        doc = self.text_edit.document()
        block = doc.findBlockByNumber(line_num)
        if not block.isValid():
            return

        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or ud.is_gap:
            return

        seg_start = float(ud.start_sec)
        sub_indices = get_sub_block_indices(doc, line_num, seg_start)

        cur = QTextCursor(doc)
        cur.beginEditBlock()

        # 하위 블록 삭제 (첫 번째만 남김)
        for idx in reversed(sub_indices[1:]):
            delete_block_safely(doc.findBlockByNumber(idx))

        # 첫 블록: 텍스트 제거 + Gap 변환
        block = doc.findBlockByNumber(line_num)
        cur.setPosition(block.position())
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        block.setUserData(make_gap_ud(seg_start))

        # 인접 Gap 병합
        merge_adjacent_gaps_around(block)

        cur.endEditBlock()
        self.text_edit.setTextCursor(cur)
        self._finalize_edit()

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
                    doc.findBlockByNumber(1).setUserData(make_gap_ud(gap_end))
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
                    cur.block().setUserData(make_gap_ud(gap_end))
            else:
                cur.movePosition(QTextCursor.MoveOperation.End)
                if doc.lastBlock().text().strip():
                    cur.insertText("\n")
                cur.insertText("새 자막")
                cur.block().setUserData(SubtitleBlockData(self.settings.get("spk1_id", "00"), gap_start, is_gap=False))
                cur.insertText("\n")
                cur.block().setUserData(make_gap_ud(gap_end))

        cur.endEditBlock()
        self.text_edit.setTextCursor(cur)
        self._finalize_edit()

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

        self.text_edit.textCursor().endEditBlock()
        self._finalize_edit()

    def _on_diamond_merge(self, left_line: int, right_line: int):
        """다이아몬드 더블클릭: 좌우 자막 세그먼트 1쌍만 병합"""
        self._undo_mgr.push_immediate()
        doc = self.text_edit.document()

        left_block = doc.findBlockByNumber(left_line)
        right_block = doc.findBlockByNumber(right_line)
        if not left_block.isValid() or not right_block.isValid(): return

        left_ud = left_block.userData()
        right_ud = right_block.userData()
        if not isinstance(left_ud, SubtitleBlockData) or not isinstance(right_ud, SubtitleBlockData): return
        if left_ud.is_gap or right_ud.is_gap: return

        left_last = get_sub_block_indices(doc, left_line, left_ud.start_sec)[-1]
        right_last = get_sub_block_indices(doc, right_line, right_ud.start_sec)[-1]

        right_texts = []
        for i in range(right_line, right_last + 1):
            t = doc.findBlockByNumber(i).text()
            if t.strip(): right_texts.append(t)
        if not right_texts: return

        cur = QTextCursor(doc)
        cur.beginEditBlock()

        left_last_block = doc.findBlockByNumber(left_last)
        right_last_block = doc.findBlockByNumber(right_last)

        cur.setPosition(left_last_block.position())
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        right_end = QTextCursor(right_last_block)
        right_end.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cur.setPosition(right_end.position(), QTextCursor.MoveMode.KeepAnchor)

        cur.insertText(" " + " ".join(right_texts))
        cur.endEditBlock()

        self._mark_dirty()
        self._finalize_edit()

    def _on_smart_split(self, line_num: int, split_sec: float, new_on_left: bool):
        """스마트 자막 분할"""
        self._undo_mgr.push_immediate()
        doc = self.text_edit.document()
        block = doc.findBlockByNumber(int(line_num))
        if not block.isValid(): return

        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData) or ud.is_gap: return

        seg_start = float(ud.start_sec)
        spk_id = ud.spk_id
        split_sec = float(split_sec)
        if split_sec <= seg_start + 0.05: return

        sub_indices = get_sub_block_indices(doc, block.blockNumber(), seg_start)
        full_lines = [doc.findBlockByNumber(idx).text() for idx in sub_indices]
        original_text = "\u2028".join(full_lines)

        cur = QTextCursor(doc)
        cur.beginEditBlock()

        for idx in reversed(sub_indices[1:]):
            b = doc.findBlockByNumber(idx)
            c = QTextCursor(b)
            c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            c.removeSelectedText()
            if doc.blockCount() > 1: c.deletePreviousChar()

        block = doc.findBlockByNumber(sub_indices[0])
        cur.setPosition(block.position())
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()

        if new_on_left:
            cur.insertText("새자막")
            cur.block().setUserData(SubtitleBlockData(spk_id, round(seg_start, 2), is_gap=False))
            cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            cur.insertBlock()
            cur.insertText(original_text)
            cur.block().setUserData(SubtitleBlockData(spk_id, round(split_sec, 2), is_gap=False))
        else:
            cur.insertText(original_text)
            cur.block().setUserData(SubtitleBlockData(spk_id, round(seg_start, 2), is_gap=False))
            cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            cur.insertBlock()
            cur.insertText("새자막")
            cur.block().setUserData(SubtitleBlockData(spk_id, round(split_sec, 2), is_gap=False))

        cur.endEditBlock()

        self._sync_lock = True
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        self.text_edit.setTextCursor(cur)
        self._active_seg_start = round(split_sec, 2)
        if hasattr(self, 'timeline'):
            self.timeline.set_active(self._active_seg_start)
            self.timeline.center_to_sec(split_sec, smooth=True)
        self._sync_lock = False

        self._mark_dirty()
        self._finalize_edit()
