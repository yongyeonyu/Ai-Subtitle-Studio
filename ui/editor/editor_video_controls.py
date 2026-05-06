# Version: 03.09.09
# Phase: PHASE1-C
"""
EditorWidget 비디오 제어 / 재생 단축키 Mixin.
"""
import os

from PyQt6.QtCore import QTimer, QSettings, QPoint
from PyQt6.QtGui import QTextCursor
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import QMenu

from core.media_info import probe_media
from core.frame_time import normalize_fps
from ui.editor.subtitle_text_edit import SubtitleBlockData
from ui.editor.editor_helpers import get_sub_block_indices, insert_gap_after


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

    def _load_video(self, path: str, *, load_waveform: bool = True):
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
        if load_waveform and hasattr(self.timeline, 'load_waveform') and not is_multiclip:
            self.timeline.load_waveform(path)

        info = probe_media(path)
        self.video_fps = normalize_fps(info.get("fps", 0.0) or 30.0)
        if hasattr(self, "timeline") and hasattr(self.timeline, "set_frame_rate"):
            self.timeline.set_frame_rate(self.video_fps)
        if (
            hasattr(self, "timeline")
            and hasattr(self.timeline, "_apply_single_media_duration")
            and not is_multiclip
        ):
            self.timeline._apply_single_media_duration(float(info.get("duration", 0.0) or 0.0))
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

    def _load_queue_clip_media_staged(self, path: str, *, auto_start: bool = False):
        """Queue mode startup: show the new clip waveform first, then video thumbnail."""
        path = str(path or "")
        if not path:
            return

        token = object()
        self._queue_media_stage_token = token
        self._queue_media_stage_video_loaded = False

        def same_token():
            return getattr(self, "_queue_media_stage_token", None) is token

        def maybe_auto_start():
            if not same_token() or not auto_start:
                return
            btn = getattr(self, "btn_start", None)
            if btn is None:
                return
            try:
                if btn.isEnabled():
                    btn.click()
            except RuntimeError:
                pass

        def load_video_after_waveform():
            if not same_token() or getattr(self, "_queue_media_stage_video_loaded", False):
                return
            self._queue_media_stage_video_loaded = True
            self._load_video(path, load_waveform=False)
            QTimer.singleShot(350, maybe_auto_start)

        timeline = getattr(self, "timeline", None)
        if timeline is None or not hasattr(timeline, "load_waveform"):
            load_video_after_waveform()
            return

        def on_waveform_ready(ready_path, _duration):
            try:
                same_path = ready_path and path and os.path.normpath(str(ready_path)) == os.path.normpath(path)
            except Exception:
                same_path = False
            if same_token() and same_path:
                try:
                    timeline.waveform_ready.disconnect(on_waveform_ready)
                except Exception:
                    pass
                QTimer.singleShot(0, load_video_after_waveform)

        try:
            if hasattr(timeline, "waveform_ready"):
                timeline.waveform_ready.connect(on_waveform_ready)
            timeline.load_waveform(path, force=True)
            QTimer.singleShot(1400, load_video_after_waveform)
        except Exception:
            load_video_after_waveform()

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
        manually_confirmed = bool(quality.get("manual_confirmed")) or "manual_confirmed" in flags
        return (
            bool(quality)
            and (
                manually_confirmed
                or label in {"red", "gray"}
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
        quality = dict(seg.get("quality") or {})
        flags = set(str(flag) for flag in (quality.get("flags") or ()))
        manually_confirmed = bool(quality.get("manual_confirmed")) or "manual_confirmed" in flags
        primary_action = menu.addAction("임시자막" if manually_confirmed else "자막 확정")
        delete_action = menu.addAction("자막 삭제")
        chosen = menu.exec(gpos)
        line = int(seg.get("line", -1))
        if chosen is primary_action:
            if manually_confirmed:
                self._mark_review_segment_temporary(line)
            else:
                self._confirm_review_segment(line)
        elif chosen is delete_action:
            self._delete_review_segment(line)

    def _set_review_segment_quality(self, line: int, quality: dict, history: list[dict]):
        block = self.text_edit.document().findBlockByNumber(int(line))
        if not block.isValid():
            return
        data = block.userData()
        if not isinstance(data, SubtitleBlockData) or data.is_gap:
            return
        current_seg = self._segment_for_line(int(line)) if hasattr(self, "_segment_for_line") else {}
        block.setUserData(
            SubtitleBlockData(
                data.spk_id,
                data.start_sec,
                data.is_gap,
                stt_mode=getattr(data, "stt_mode", False),
                stt_pending=getattr(data, "stt_pending", False),
                original_text=getattr(data, "original_text", ""),
                dictated_text=getattr(data, "dictated_text", ""),
                stt_selected_source=getattr(data, "stt_selected_source", ""),
                stt_ensemble_llm_selected_source=getattr(data, "stt_ensemble_llm_selected_source", ""),
                stt_candidates=list(getattr(data, "stt_candidates", []) or []),
                stt_ensemble_source=getattr(data, "stt_ensemble_source", ""),
                stt_ensemble_llm_selected_label=getattr(data, "stt_ensemble_llm_selected_label", ""),
                stt_ensemble_similarity=getattr(data, "stt_ensemble_similarity", None),
                stt_ensemble_needs_llm_review=getattr(data, "stt_ensemble_needs_llm_review", False),
                stt_ensemble_inserted_from_stt2=getattr(data, "stt_ensemble_inserted_from_stt2", False),
                stt_ensemble_word_rover=dict(getattr(data, "stt_ensemble_word_rover", {}) or {}),
                score=getattr(data, "score", None),
                stt_score=getattr(data, "stt_score", None),
                score_color=getattr(data, "score_color", ""),
                stt_score_color=getattr(data, "stt_score_color", ""),
                stt_score_label=getattr(data, "stt_score_label", ""),
                stt_score_flags=list(getattr(data, "stt_score_flags", []) or []),
                stt_score_components=dict(getattr(data, "stt_score_components", {}) or {}),
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

    def _segment_for_lora_confirmation(self, line: int, data: SubtitleBlockData, quality: dict) -> dict:
        current_seg = self._segment_for_line(int(line)) if hasattr(self, "_segment_for_line") else {}
        seg = dict(current_seg or {})
        text = self.text_edit.document().findBlockByNumber(int(line)).text().replace("\u2028", "\n").strip()
        seg.update(
            {
                "line": int(line),
                "start": float(getattr(data, "start_sec", seg.get("start", 0.0)) or 0.0),
                "end": float(seg.get("end", getattr(data, "start_sec", 0.0)) or getattr(data, "start_sec", 0.0)),
                "text": text,
                "speaker": str(getattr(data, "spk_id", seg.get("speaker", seg.get("spk", "00"))) or "00"),
                "quality": dict(quality or {}),
                "stt_candidates": list(getattr(data, "stt_candidates", []) or seg.get("stt_candidates") or []),
                "stt_selected_source": str(getattr(data, "stt_selected_source", "") or seg.get("stt_selected_source", "") or ""),
                "stt_ensemble_llm_selected_source": str(getattr(data, "stt_ensemble_llm_selected_source", "") or seg.get("stt_ensemble_llm_selected_source", "") or ""),
                "stt_ensemble_source": str(getattr(data, "stt_ensemble_source", "") or seg.get("stt_ensemble_source", "") or ""),
                "score": getattr(data, "score", seg.get("score", None)),
                "stt_score": getattr(data, "stt_score", seg.get("stt_score", None)),
            }
        )
        if not (seg.get("stt_selected_source") or seg.get("stt_ensemble_llm_selected_source") or seg.get("stt_ensemble_source")):
            candidates = [
                item for item in list(seg.get("stt_candidates") or [])
                if str(item.get("source", "") or "").strip()
            ]
            if candidates:
                def _candidate_score(item):
                    try:
                        return float(item.get("stt_score", item.get("score", 0.0)) or 0.0)
                    except Exception:
                        return 0.0
                best = max(candidates, key=_candidate_score)
                seg["stt_selected_source"] = str(best.get("source", "") or "").strip().upper()
        return seg

    def _accumulate_confirmed_segment_lora(self, line: int, data: SubtitleBlockData, quality: dict):
        try:
            from core.personalization.deferred_editor_learning import enqueue_deferred_editor_learning
            from core.runtime.logger import get_logger

            seg = self._segment_for_lora_confirmation(line, data, quality)
            if not (
                seg.get("stt_selected_source")
                or seg.get("stt_ensemble_llm_selected_source")
                or seg.get("stt_ensemble_source")
                or list(seg.get("stt_candidates") or [])
            ):
                return
            main_w = self.window() if hasattr(self, "window") else None
            settings = dict(getattr(self, "settings", {}) or {})
            queued = enqueue_deferred_editor_learning(
                [seg],
                media_path=str(getattr(self, "media_path", "") or ""),
                subtitle_path="",
                project_path=str(getattr(main_w, "_current_project_path", "") or ""),
                trigger="manual_confirm_segment",
                settings=settings,
            )
            if queued.get("queued"):
                get_logger().log("🧠 [텍스트 LoRA] 자막 확정 학습은 Home-idle 큐로 넘겼습니다.")
        except Exception as exc:
            try:
                from core.runtime.logger import get_logger

                get_logger().log(f"⚠️ 자막 확정 LoRA 큐 등록 실패: {exc}")
            except Exception:
                pass

    def _adjacent_gap_block_for_review_segment(self, line: int):
        block = self.text_edit.document().findBlockByNumber(int(line))
        if not block.isValid():
            return None
        data = block.userData()
        if not isinstance(data, SubtitleBlockData) or data.is_gap:
            return None
        sub_indices = get_sub_block_indices(self.text_edit.document(), int(line), float(data.start_sec))
        last_idx = sub_indices[-1] if sub_indices else int(line)
        next_block = self.text_edit.document().findBlockByNumber(last_idx).next()
        if not next_block.isValid():
            return None
        next_data = next_block.userData()
        if isinstance(next_data, SubtitleBlockData) and next_data.is_gap:
            return next_block
        return None

    def _set_adjacent_silence_confirmed(self, line: int, confirmed: bool):
        gap_block = self._adjacent_gap_block_for_review_segment(line)
        if gap_block is None or not gap_block.isValid():
            return
        gap_data = gap_block.userData()
        if not isinstance(gap_data, SubtitleBlockData) or not gap_data.is_gap:
            return
        quality = dict(getattr(gap_data, "quality", {}) or {})
        flags = [str(flag) for flag in (quality.get("flags") or [])]
        if confirmed:
            for flag in ("manual_confirmed", "linked_silence"):
                if flag not in flags:
                    flags.append(flag)
            quality["flags"] = flags
            quality["confidence_label"] = "green"
            quality["confidence_reason"] = "linked_silence_confirmed"
            quality["manual_confirmed"] = True
            quality["linked_silence"] = True
        else:
            flags = [
                flag for flag in flags
                if flag not in {"manual_confirmed", "linked_silence"}
            ]
            quality["flags"] = flags
            quality["manual_confirmed"] = False
            quality["linked_silence"] = False
            if quality.get("confidence_reason") == "linked_silence_confirmed":
                quality["confidence_reason"] = "manual_temporary"
            if quality.get("confidence_label") == "green":
                quality["confidence_label"] = "yellow"
        gap_data.quality = quality
        try:
            gap_data.linked_silence_for_line = int(line)
        except Exception:
            pass

    def _confirm_review_segment(self, line: int):
        block = self.text_edit.document().findBlockByNumber(int(line))
        if not block.isValid():
            return
        data = block.userData()
        if not isinstance(data, SubtitleBlockData) or data.is_gap:
            return
        if hasattr(self, "_undo_mgr"):
            self._undo_mgr.push_immediate()
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
        self._accumulate_confirmed_segment_lora(line, data, quality)
        self._set_adjacent_silence_confirmed(line, True)
        self._set_review_segment_quality(line, quality, history)

    def _mark_review_segment_temporary(self, line: int):
        block = self.text_edit.document().findBlockByNumber(int(line))
        if not block.isValid():
            return
        data = block.userData()
        if not isinstance(data, SubtitleBlockData) or data.is_gap:
            return
        if hasattr(self, "_undo_mgr"):
            self._undo_mgr.push_immediate()
        quality = dict(getattr(data, "quality", {}) or {})
        history = list(getattr(data, "quality_history", []) or [])
        if quality:
            history.append(dict(quality))
        flags = [
            str(flag)
            for flag in (quality.get("flags") or [])
            if str(flag) != "manual_confirmed"
        ]
        if "manual_temporary" not in flags:
            flags.append("manual_temporary")
        quality["flags"] = flags
        quality["confidence_label"] = "yellow"
        quality["confidence_reason"] = "manual_temporary"
        quality["manual_confirmed"] = False
        quality["manual_temporary"] = True
        self._set_adjacent_silence_confirmed(line, False)
        self._set_review_segment_quality(line, quality, history)

    def _delete_review_segment(self, line: int):
        if int(line) < 0:
            return
        if hasattr(self, "_on_seg_to_gap"):
            self._on_seg_to_gap(int(line))
