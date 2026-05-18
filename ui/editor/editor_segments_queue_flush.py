"""Queue append/flush helpers for editor subtitle segments."""

from __future__ import annotations

import re
import threading

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QTextCharFormat, QTextCursor

from core.runtime.logger import get_logger
from ui.editor.editor_helpers import should_split_multiline_part_into_block
from ui.editor.subtitle_text_edit import SubtitleBlockData


class EditorSegmentsQueueFlushMixin:
    def append_segments(self, segments: list[dict]):
        try:
            self.status_lbl.text()
        except RuntimeError:
            return
        if threading.current_thread() is not threading.main_thread():
            QTimer.singleShot(0, lambda s=list(segments): self.append_segments(s))
            return
        self._segment_queue.extend(segments)
        if not self._queue_timer.isActive():
            self._queue_timer.start(self._live_append_reschedule_delay_ms(len(self._segment_queue)))

    def _flush_queue(self):
        try:
            self.text_edit.toPlainText()
        except RuntimeError:
            return

        if not self._normalize_pending_segment_queue():
            return
        remaining_segments, has_more_pending = self._split_segment_queue_batch()
        if not self._segment_queue:
            return

        cont_thresh, push_rate, pull_rate, single_ext, is_initial, final_gap_ready = self._queue_gap_adjustment_policy()
        doc, orig_cursor, is_at_bottom, cur, prev_end_orig, has_prev_gap = self._prepare_flush_document_cursor(
            single_ext=single_ext,
            is_initial=is_initial,
        )
        self._apply_leading_queue_gap_adjustment(
            cur=cur,
            doc=doc,
            has_prev_gap=has_prev_gap,
            prev_end_orig=prev_end_orig,
            cont_thresh=cont_thresh,
            push_rate=push_rate,
            pull_rate=pull_rate,
            single_ext=single_ext,
            is_initial=is_initial,
            final_gap_ready=final_gap_ready,
        )
        self._apply_internal_queue_gap_adjustments(
            cont_thresh=cont_thresh,
            push_rate=push_rate,
            pull_rate=pull_rate,
            single_ext=single_ext,
            is_initial=is_initial,
            final_gap_ready=final_gap_ready,
        )
        self._segment_queue = self._clamp_segments_to_clip_duration(
            self._segment_queue,
            log_changes=False,
        )
        if not self._segment_queue:
            self._queue_post_flush_reschedule_pending(
                remaining_segments=remaining_segments,
                has_more_pending=has_more_pending,
            )
            return
        added_end, focused_payload = self._append_segment_queue_to_document(cur)
        self._finalize_flush_document_cursor(cur=cur, orig_cursor=orig_cursor, is_at_bottom=is_at_bottom)
        self._handle_post_flush_queue(
            added_end=added_end,
            focused_payload=focused_payload,
            has_more_pending=has_more_pending,
            remaining_segments=remaining_segments,
            is_initial=is_initial,
        )

    def _queue_flush_is_final_gap_ready(self, queue: list[dict] | None = None) -> bool:
        rows = list(self._segment_queue if queue is None else queue or [])
        return bool(rows) and all(
            bool(seg.get("_final_gap_settings_applied"))
            for seg in rows
            if isinstance(seg, dict)
        )

    def _normalize_pending_segment_queue(self) -> bool:
        if not self._segment_queue:
            return False
        self._remove_live_editor_preview_overlapping(self._segment_queue)
        queue_final_gap_ready = self._queue_flush_is_final_gap_ready()
        try:
            if not queue_final_gap_ready:
                from core.engine.subtitle_accuracy_pipeline import repair_subtitle_context_consistency

                repaired_queue, repair_decision = repair_subtitle_context_consistency(
                    [dict(seg) for seg in list(self._segment_queue or []) if isinstance(seg, dict)],
                    getattr(self, "settings", {}) or {},
                )
                if repair_decision.get("applied"):
                    dropped_shadow = int(repair_decision.get("dropped_shadow_duplicates", 0) or 0)
                    if dropped_shadow:
                        get_logger().log(f"[자막문맥-자동복구] 에디터 반영 전 부분중복 자막 {dropped_shadow}개 제거")
                    self._segment_queue = list(repaired_queue or [])
        except Exception:
            pass
        if not self._segment_queue:
            return False

        self._segment_queue = [
            seg
            for idx, seg in sorted(
                enumerate(list(self._segment_queue or [])),
                key=lambda pair: (
                    float(pair[1].get("start", 0.0) or 0.0) if isinstance(pair[1], dict) else 0.0,
                    float(pair[1].get("end", pair[1].get("start", 0.0)) or 0.0) if isinstance(pair[1], dict) else 0.0,
                    int(pair[0]),
                ),
            )
            if isinstance(seg, dict)
        ]
        try:
            deduped_queue, dropped_repeat_previous = self._drop_repeat_previous_queue_segments_with_context(
                self._segment_queue
            )
            if dropped_repeat_previous:
                get_logger().log(f"[자막문맥-자동복구] 에디터 경계중복 자막 {dropped_repeat_previous}개 제거")
            self._segment_queue = list(deduped_queue or [])
        except Exception:
            pass
        self._segment_queue = self._clamp_segments_to_clip_duration(
            self._segment_queue,
            log_changes=False,
        )
        return bool(self._segment_queue)

    def _split_segment_queue_batch(self) -> tuple[list[dict], bool]:
        remaining_segments: list[dict] = []
        batch_limit = self._live_append_batch_limit()
        if batch_limit > 0 and len(self._segment_queue) > batch_limit:
            remaining_segments = [dict(seg) for seg in list(self._segment_queue[batch_limit:]) if isinstance(seg, dict)]
            self._segment_queue = [dict(seg) for seg in list(self._segment_queue[:batch_limit]) if isinstance(seg, dict)]
        return remaining_segments, bool(remaining_segments)

    def _queue_gap_adjustment_policy(self) -> tuple[float, float, float, float, bool, bool]:
        cont_thresh = float(self.settings.get("continuous_threshold", 2.0))
        push_rate = float(self.settings.get("gap_push_rate", 0.7))
        pull_rate = max(0.0, min(1.0, 1.0 - push_rate))
        single_ext = float(self.settings.get("single_subtitle_end", 0.2))
        is_initial = bool(getattr(self, "_is_initial_load", False))
        final_gap_ready = self._queue_flush_is_final_gap_ready()
        return cont_thresh, push_rate, pull_rate, single_ext, is_initial, final_gap_ready

    def _prepare_flush_document_cursor(
        self,
        *,
        single_ext: float,
        is_initial: bool,
    ) -> tuple[object, object, bool, QTextCursor, float, bool]:
        doc = self.text_edit.document()
        orig_cursor = self.text_edit.textCursor()
        is_at_bottom = orig_cursor.position() >= doc.characterCount() - 5
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        cur.movePosition(QTextCursor.MoveOperation.End)

        prev_end_orig = -1.0
        has_prev_gap = False
        if not is_initial and doc.blockCount() > 0:
            lb = doc.lastBlock()
            ud = lb.userData()
            if not lb.text().strip() and isinstance(ud, SubtitleBlockData) and ud.is_gap:
                has_prev_gap = True
                prev_end_orig = max(0.0, ud.start_sec - single_ext)

        while doc.blockCount() > 0:
            last_block = doc.lastBlock()
            if last_block.text().strip():
                break
            cur.setPosition(last_block.position())
            cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            cur.removeSelectedText()
            if doc.blockCount() > 1:
                cur.deletePreviousChar()
            else:
                break
        cur.movePosition(QTextCursor.MoveOperation.End)
        return doc, orig_cursor, is_at_bottom, cur, prev_end_orig, has_prev_gap

    def _apply_leading_queue_gap_adjustment(
        self,
        *,
        cur: QTextCursor,
        doc,
        has_prev_gap: bool,
        prev_end_orig: float,
        cont_thresh: float,
        push_rate: float,
        pull_rate: float,
        single_ext: float,
        is_initial: bool,
        final_gap_ready: bool,
    ) -> None:
        if not (has_prev_gap and self._segment_queue and not is_initial and not final_gap_ready):
            return
        curr_start = self._segment_queue[0]["start"]
        gap = curr_start - prev_end_orig
        if 0 < gap <= cont_thresh:
            new_prev_end = prev_end_orig + gap * push_rate
            self._segment_queue[0]["start"] = prev_end_orig + gap - (gap * pull_rate)
            if self._segment_queue[0]["start"] > new_prev_end + 0.05:
                if doc.lastBlock().text().strip():
                    cur.insertText("\n")
                cur.insertText("\n")
                cur.block().setUserData(SubtitleBlockData("00", self._frame_time(new_prev_end), is_gap=True))
                cur.insertText("\n")
        elif gap > cont_thresh:
            new_prev_end = prev_end_orig + single_ext
            self._segment_queue[0]["start"] = max(0.0, curr_start - single_ext)
            if self._segment_queue[0]["start"] > new_prev_end + 0.05:
                if doc.lastBlock().text().strip():
                    cur.insertText("\n")
                cur.insertText("\n")
                cur.block().setUserData(SubtitleBlockData("00", self._frame_time(new_prev_end), is_gap=True))
                cur.insertText("\n")

    def _apply_internal_queue_gap_adjustments(
        self,
        *,
        cont_thresh: float,
        push_rate: float,
        pull_rate: float,
        single_ext: float,
        is_initial: bool,
        final_gap_ready: bool,
    ) -> None:
        last_end = -1.0
        for idx, curr in enumerate(self._segment_queue):
            if not is_initial and not final_gap_ready:
                if curr["start"] < last_end:
                    curr["start"] = last_end
                if idx + 1 < len(self._segment_queue):
                    nxt = self._segment_queue[idx + 1]
                    gap = nxt["start"] - curr["end"]
                    if 0 < gap <= cont_thresh:
                        curr["end"] += gap * push_rate
                        nxt["start"] -= gap * pull_rate
                    elif gap > cont_thresh:
                        curr["end"] += min(single_ext, gap / 2.0)
                        nxt["start"] -= min(single_ext, gap / 2.0)
                else:
                    curr["end"] += single_ext
            elif curr["end"] <= curr["start"]:
                curr["end"] = curr["start"] + 0.5
            last_end = curr["end"]

    def _append_segment_queue_to_document(self, cur: QTextCursor) -> tuple[float, dict | None]:
        doc = self.text_edit.document()
        if doc.lastBlock().text().strip():
            cur.insertText("\n")
        added_end = self._segment_queue[-1]["end"] if self._segment_queue else 0.0
        focused_payload = None
        spk1_id = self.settings.get("spk1_id", "00")
        spk2_id = self.settings.get("spk2_id", "01")

        for idx, seg in enumerate(self._segment_queue):
            payload = self._queue_flush_segment_payload(seg, spk1_id=spk1_id)
            if payload is None:
                continue
            focused_payload = self._queue_flush_write_segment_lines(
                cur,
                payload=payload,
                spk1_id=spk1_id,
                spk2_id=spk2_id,
            )
            next_seg = self._segment_queue[idx + 1] if idx + 1 < len(self._segment_queue) else None
            self._queue_flush_insert_gap_after_segment(cur, seg=seg, next_seg=next_seg)

        self._segment_queue.clear()
        self.text_edit.update_margins()
        return added_end, focused_payload

    def _queue_flush_segment_text_parts(self, seg: dict) -> list[str]:
        text = str(seg.get("text", "") or "").replace("\u2028", "\n")
        text = self._JUNK_TS_RE.sub("", text)
        text = self._JUNK_NO_BRACKET_3PART.sub("", text)
        text = self._JUNK_NO_BRACKET_3PART_END.sub("", text)
        text = self._JUNK_START_RE.sub("", text).strip()
        text = re.sub(r"<[^>]+>", "", text.replace("\r", ""))
        parts = [re.sub(r"[ \t\f\v]+", " ", part).strip() for part in text.split("\n")]
        return [part for part in parts if part]

    def _queue_flush_segment_payload(self, seg: dict, *, spk1_id: str) -> dict | None:
        parts = self._queue_flush_segment_text_parts(seg)
        if not parts:
            return None
        start_sec = self._frame_time(max(0, seg.get("start", 0)))
        end_sec = self._frame_time(max(start_sec, seg.get("end", start_sec)))
        spk_list = list(seg.get("speaker_list", [spk1_id]) or [spk1_id])
        current_spk = spk_list[0] if len(spk_list) > 0 else spk1_id
        _clip_idx, clip_kwargs = self._bulk_segment_clip_kwargs(seg)
        return {
            "source_segment": dict(seg),
            "parts": parts,
            "start_sec": start_sec,
            "end_sec": end_sec,
            "current_spk": current_spk,
            "stt_kwargs": self._bulk_segment_stt_kwargs(seg),
            "clip_kwargs": clip_kwargs,
            "quality_kwargs": self._segment_document_quality_kwargs(
                seg,
                start_sec=start_sec,
                end_sec=end_sec,
                text=parts[0],
                speaker=current_spk,
            ),
        }

    def _queue_flush_write_segment_lines(
        self,
        cur: QTextCursor,
        *,
        payload: dict,
        spk1_id: str,
        spk2_id: str,
    ) -> dict:
        parts = list(payload.get("parts") or [])
        current_spk = str(payload.get("current_spk", spk1_id) or spk1_id)
        source_segment = dict(payload.get("source_segment") or {})
        start_sec = float(payload.get("start_sec", 0.0) or 0.0)
        end_sec = float(payload.get("end_sec", start_sec) or start_sec)
        stt_kwargs = dict(payload.get("stt_kwargs") or {})
        clip_kwargs = dict(payload.get("clip_kwargs") or {})
        quality_kwargs = dict(payload.get("quality_kwargs") or {})

        cur.setCharFormat(QTextCharFormat())
        cur.insertText(parts[0], QTextCharFormat())
        cur.block().setUserData(
            SubtitleBlockData(current_spk, start_sec, end_sec=end_sec, **stt_kwargs, **quality_kwargs, **clip_kwargs)
        )
        focused_payload = {
            "line": cur.block().blockNumber(),
            "start": start_sec,
            "end": end_sec,
            "text": parts[0],
        }
        for line_text in parts[1:]:
            if should_split_multiline_part_into_block(source_segment, line_text):
                current_spk = spk2_id if current_spk == spk1_id else spk1_id
                cur.insertText("\n" + line_text, QTextCharFormat())
                cur.block().setUserData(
                    SubtitleBlockData(current_spk, start_sec, end_sec=end_sec, **stt_kwargs, **quality_kwargs, **clip_kwargs)
                )
            else:
                cur.insertText("\u2028" + line_text, QTextCharFormat())
        return focused_payload

    def _queue_flush_insert_gap_after_segment(self, cur: QTextCursor, *, seg: dict, next_seg: dict | None) -> None:
        if isinstance(next_seg, dict):
            if seg["end"] < next_seg["start"] - 0.05:
                gap_start = self._frame_time(seg["end"])
                cur.insertText("\n")
                cur.block().setUserData(SubtitleBlockData("00", gap_start, is_gap=True))
                cur.insertText("\n")
            else:
                cur.insertText("\n")
            return

        gap_start = self._frame_time(seg["end"])
        cur.insertText("\n")
        cur.block().setUserData(SubtitleBlockData("00", gap_start, is_gap=True))

    def _finalize_flush_document_cursor(self, *, cur: QTextCursor, orig_cursor, is_at_bottom: bool) -> None:
        cur.endEditBlock()
        self._sync_lock = True
        if is_at_bottom:
            self.text_edit.setTextCursor(cur)
        else:
            self.text_edit.setTextCursor(orig_cursor)
        self._sync_lock = False

    def _handle_post_flush_queue(
        self,
        *,
        added_end: float,
        focused_payload: dict | None,
        has_more_pending: bool,
        remaining_segments: list[dict],
        is_initial: bool,
    ) -> None:
        self._queue_post_flush_refresh_views(has_more_pending=has_more_pending)
        suppress_autoseek = self._queue_post_flush_suppress_autoseek(has_more_pending=has_more_pending)
        if is_initial:
            self._queue_post_flush_apply_initial_seek_reset()
        elif added_end > 0.0 and not suppress_autoseek:
            self._queue_post_flush_autoseek_to_added_segment(
                added_end=added_end,
                focused_payload=focused_payload,
            )
        self._queue_post_flush_reschedule_pending(remaining_segments=remaining_segments, has_more_pending=has_more_pending)

    def _queue_post_flush_refresh_views(self, *, has_more_pending: bool) -> None:
        self._schedule_timeline()
        self._queue_post_flush_fit_view_if_needed(has_more_pending=has_more_pending)
        self._queue_post_flush_refresh_video_context(has_more_pending=has_more_pending)

    def _queue_post_flush_fit_view_if_needed(self, *, has_more_pending: bool) -> None:
        if not (getattr(self, "_queue_mode_fit_view", False) and hasattr(self, "timeline")):
            return
        try:
            setattr(self.timeline, "_manual_zoom_since_fit", False)
            if has_more_pending:
                return
            if hasattr(self.timeline, "schedule_fit_to_view"):
                self.timeline.schedule_fit_to_view((0, 120, 260))
            elif hasattr(self.timeline, "fit_to_view"):
                QTimer.singleShot(0, self.timeline.fit_to_view)
        except Exception:
            pass

    def _queue_post_flush_refresh_video_context(self, *, has_more_pending: bool) -> None:
        if has_more_pending:
            timer = getattr(self, "_video_context_refresh_timer", None)
            if timer is not None:
                try:
                    timer.start(90)
                except Exception:
                    pass
            return
        self._refresh_video_subtitle_context()

    def _queue_post_flush_suppress_autoseek(self, *, has_more_pending: bool) -> bool:
        return bool(getattr(self, "_suspend_append_segments_autoseek", False)) or has_more_pending

    def _queue_post_flush_apply_initial_seek_reset(self) -> None:
        self._is_initial_load = False
        if hasattr(self, "timeline"):
            self.timeline.set_playhead(0.0)
            self.timeline.center_to_sec(0.0, smooth=True)
        if hasattr(self, "video_player"):
            self.video_player.seek(0.0)

    def _queue_post_flush_autoseek_to_added_segment(
        self,
        *,
        added_end: float,
        focused_payload: dict | None,
    ) -> None:
        if hasattr(self, "timeline"):
            self.timeline.set_playhead(added_end)
            self.timeline.center_to_sec(added_end, smooth=True)
        if hasattr(self, "video_player"):
            self.video_player.seek(added_end)
        self._focus_editor_block_for_processing_segment(focused_payload, prefer_last=True)
        self._queue_post_flush_schedule_quality_review()

    def _queue_post_flush_schedule_quality_review(self) -> None:
        if not self.settings.get("subtitle_quality_auto_check_after_generate"):
            return
        scheduler = getattr(self, "_schedule_auto_quality_review", None)
        if callable(scheduler):
            scheduler(delay_ms=900)
            return
        if hasattr(self, "_run_quality_review"):
            QTimer.singleShot(
                900,
                lambda: self._run_quality_review(
                    auto_correct=bool(self.settings.get("subtitle_quality_auto_correct_enabled", False))
                ),
            )

    def _queue_post_flush_reschedule_pending(
        self,
        *,
        remaining_segments: list[dict],
        has_more_pending: bool,
    ) -> None:
        if not has_more_pending:
            return
        self._segment_queue = list(remaining_segments)
        try:
            self._queue_timer.start(self._live_append_reschedule_delay_ms(len(self._segment_queue)))
        except Exception:
            self._flush_queue()

    def _live_append_batch_limit(self) -> int:
        try:
            locked = bool(getattr(getattr(self, "sm", None), "is_locked", False))
        except Exception:
            locked = False
        if not locked:
            return 0
        try:
            value = int((getattr(self, "settings", {}) or {}).get("editor_live_append_batch_size", 8) or 8)
        except Exception:
            value = 8
        return max(1, min(24, value))

    def _live_append_reschedule_delay_ms(self, pending_count: int = 0) -> int:
        try:
            locked = bool(getattr(getattr(self, "sm", None), "is_locked", False))
        except Exception:
            locked = False
        if not locked:
            return 80
        backlog = max(0, int(pending_count or 0))
        return 10 if backlog >= 16 else 18
