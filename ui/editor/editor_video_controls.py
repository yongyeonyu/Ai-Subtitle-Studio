# Version: 03.09.09
# Phase: PHASE1-C
"""
EditorWidget 비디오 제어 / 재생 단축키 Mixin.
"""
from PyQt6.QtCore import QTimer, QSettings, QPoint
from PyQt6.QtGui import QTextCursor
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import QMenu

from core.media_info import probe_media
from core.frame_time import normalize_fps
from ui.editor.subtitle_text_edit import SubtitleBlockData
from ui.editor.editor_helpers import insert_gap_after


class EditorVideoControlsMixin:
    _REVIEW_FLAGS = {
        "non_speech_hallucination_risk",
        "high_no_speech_prob",
        "outside_vad_speech",
        "high_cps",
        "quality_stale",
    }

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
            self.splitter.setSizes([6500, 3500])
        if hasattr(self, "_position_video_expand_button"):
            QTimer.singleShot(0, self._position_video_expand_button)
            QTimer.singleShot(120, self._position_video_expand_button)

    def _load_video(self, path: str):
        segs = self._get_current_segments()
        is_multiclip = bool(getattr(self.window(), "_multiclip_boundaries", []))
        if is_multiclip and hasattr(self, '_build_local_segments_for_clip'):
            clip_idx = int(getattr(self.timeline.canvas, '_active_clip_idx', getattr(self.window(), '_active_clip_idx', 0)) or 0)
            segs = self._build_local_segments_for_clip(clip_idx, segs)
        self.video_player.load(path, segs)
        if hasattr(self, "_position_video_expand_button"):
            QTimer.singleShot(400, self._position_video_expand_button)
            QTimer.singleShot(1200, self._position_video_expand_button)

        is_multiclip = bool(getattr(self.window(), "_multiclip_boundaries", []))
        if hasattr(self.timeline, 'load_waveform') and not is_multiclip:
            self.timeline.load_waveform(path)

        info = probe_media(path)
        self.video_fps = normalize_fps(info.get("fps", 0.0) or 30.0)
        if hasattr(self, "timeline") and hasattr(self.timeline, "set_frame_rate"):
            self.timeline.set_frame_rate(self.video_fps)
        if hasattr(self, "video_player") and hasattr(self.video_player, "set_frame_rate"):
            self.video_player.set_frame_rate(self.video_fps)
        width = int(info.get("width", 0) or 0)
        height = int(info.get("height", 0) or 0)
        raw_aspect = (width / height) if width > 0 and height > 0 else 16 / 9
        self._video_preview_aspect = (16 / 9) if raw_aspect >= 1.25 else 1.0

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
                        self.video_player.seek(self._global_to_local_sec(last_pos))
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
        sec = self._snap_to_frame(getattr(self.timeline.canvas, 'playhead_sec', getattr(self.video_player, 'current_time', 0.0)))
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
        sec = self._snap_to_frame(getattr(self.timeline.canvas, 'playhead_sec', getattr(self.video_player, 'current_time', 0.0)))
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
                insert_gap_after(prev_block, orig_start)

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
        sec = self._snap_to_frame(getattr(self.timeline.canvas, 'playhead_sec', getattr(self.video_player, 'current_time', 0.0)))
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
            insert_gap_after(last_block, sec)

        cur.endEditBlock()
        self.text_edit.update_margins()
        if hasattr(self.text_edit, 'timestampArea'):
            self.text_edit.timestampArea.update()
        self._redraw_timeline()


    def _on_timeline_seg_right_clicked(self, start_sec: float, gpos: QPoint):
        seg = self._segment_for_start_sec(start_sec)
        if not seg or not self._segment_needs_manual_review(seg):
            return
        self._show_timeline_review_menu(seg, gpos)

    def _segment_for_start_sec(self, start_sec: float) -> dict | None:
        try:
            target = float(start_sec)
        except Exception:
            return None
        for seg in self._get_current_segments():
            if seg.get("is_gap"):
                continue
            try:
                if abs(float(seg.get("start", 0.0) or 0.0) - target) < 0.05:
                    return seg
            except Exception:
                continue
        return None

    def _segment_needs_manual_review(self, seg: dict) -> bool:
        quality = dict(seg.get("quality") or {})
        label = str(quality.get("confidence_label") or "")
        flags = set(str(flag) for flag in (quality.get("flags") or ()))
        return (
            bool(quality)
            and (
                label in {"red", "gray"}
                or bool(flags.intersection(self._REVIEW_FLAGS))
                or bool(seg.get("quality_stale"))
            )
        )

    def _show_timeline_review_menu(self, seg: dict, gpos: QPoint):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background:#151C20; color:#F5F7FA; border:1px solid #2D3942; border-radius:6px; }"
            "QMenu::item { padding:7px 22px 7px 12px; border-radius:4px; }"
            "QMenu::item:selected { background-color:#1F3A56; }"
        )
        confirm_action = menu.addAction("자막 확정")
        delete_action = menu.addAction("자막 삭제")
        chosen = menu.exec(gpos)
        line = int(seg.get("line", -1) or -1)
        if chosen is confirm_action:
            self._confirm_review_segment(line)
        elif chosen is delete_action:
            self._delete_review_segment(line)

    def _confirm_review_segment(self, line: int):
        block = self.text_edit.document().findBlockByNumber(int(line))
        if not block.isValid():
            return
        data = block.userData()
        if not isinstance(data, SubtitleBlockData) or data.is_gap:
            return
        if hasattr(self, "_undo_mgr"):
            self._undo_mgr.push_immediate()
        current_seg = self._segment_for_line(int(line)) if hasattr(self, "_segment_for_line") else {}
        quality = dict(getattr(data, "quality", {}) or {})
        history = list(getattr(data, "quality_history", []) or [])
        if quality:
            history.append(dict(quality))
        flags = [
            str(flag)
            for flag in (quality.get("flags") or [])
            if str(flag) not in self._REVIEW_FLAGS
        ]
        if "manual_confirmed" not in flags:
            flags.append("manual_confirmed")
        quality["flags"] = flags
        quality["confidence_label"] = "green"
        quality["confidence_reason"] = "manual_confirmed"
        quality["manual_confirmed"] = True
        block.setUserData(
            SubtitleBlockData(
                data.spk_id,
                data.start_sec,
                data.is_gap,
                stt_mode=getattr(data, "stt_mode", False),
                stt_pending=getattr(data, "stt_pending", False),
                original_text=getattr(data, "original_text", ""),
                dictated_text=getattr(data, "dictated_text", ""),
                quality=quality,
                quality_history=history,
                quality_candidates=list(getattr(data, "quality_candidates", []) or []),
                quality_signature=self._segment_quality_signature({
                    "start": data.start_sec,
                    "end": (current_seg or {}).get("end", data.start_sec),
                    "text": block.text(),
                    "speaker": data.spk_id,
                }) if hasattr(self, "_segment_quality_signature") else getattr(data, "quality_signature", ""),
                clip_idx=getattr(data, "clip_idx", None),
                clip_file=getattr(data, "clip_file", ""),
            )
        )
        self._mark_dirty()
        self._finalize_edit()
        if hasattr(self, "_refresh_video_subtitle_context"):
            self._refresh_video_subtitle_context()

    def _delete_review_segment(self, line: int):
        if int(line) < 0:
            return
        if hasattr(self, "_on_seg_to_gap"):
            self._on_seg_to_gap(int(line))
