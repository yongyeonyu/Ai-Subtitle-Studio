# Version: 03.14.29
# Phase: PHASE2
"""
ui/editor_segments.py
EditorWidget의 자막 에디터 조작, 큐 처리, 세그먼트 I/O 메서드 모음.
[수정] core 폴더 이동에 따른 데이터 매니저 경로 및 상대 경로 최적화 완료
"""
import os
import re
import threading
import time
import difflib
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor

from core.runtime.logger import get_logger
from core.engine.subtitle_timing import align_stt_preview_to_subtitle_segments
from core.project.project_srt import strip_whisper_control_tokens

# 💡 [경로 수정] editor_data_manager -> core.data_manager
from core.project.data_manager import save_correction as _dm_save_correction

# 수정 — 절대 import로 통일 (editor_widget.py, editor_timeline_video.py와 동일)
from ui.editor.subtitle_text_edit import SubtitleBlockData
from ui.editor.editor_roughcut_draft import EditorRoughcutDraftMixin
from ui.editor.editor_segments_block_surgery import EditorSegmentsBlockSurgeryMixin
from ui.editor.editor_segments_bulk_load import EditorSegmentsBulkLoadMixin
from ui.editor.editor_segments_current_state import EditorSegmentsCurrentStateMixin
from ui.editor.editor_segments_live_preview import EditorSegmentsLivePreviewMixin
from ui.editor.editor_segments_manual_edits import EditorSegmentsManualEditsMixin
from ui.editor.editor_segments_queue_flush import EditorSegmentsQueueFlushMixin
from ui.editor.editor_segments_reload import EditorSegmentsReloadMixin
from ui.editor.editor_segments_runtime_cache import EditorSegmentsRuntimeCacheMixin
from ui.editor.editor_segments_stt_candidates import EditorSegmentsSttCandidatesMixin
from ui.editor.editor_segments_stt_selection_flow import EditorSegmentsSttSelectionFlowMixin
from ui.editor.editor_segments_text_ops import EditorSegmentsTextOpsMixin
from ui.editor.editor_segments_timeline_context import EditorSegmentsTimelineContextMixin
from ui.style import COLORS


class EditorSegmentsMixin(
    EditorSegmentsRuntimeCacheMixin,
    EditorSegmentsBlockSurgeryMixin,
    EditorSegmentsBulkLoadMixin,
    EditorSegmentsCurrentStateMixin,
    EditorSegmentsLivePreviewMixin,
    EditorSegmentsManualEditsMixin,
    EditorSegmentsQueueFlushMixin,
    EditorSegmentsReloadMixin,
    EditorSegmentsSttCandidatesMixin,
    EditorSegmentsSttSelectionFlowMixin,
    EditorSegmentsTextOpsMixin,
    EditorSegmentsTimelineContextMixin,
    EditorRoughcutDraftMixin,
):
    """자막 에디터 조작 / 큐 처리 / 세그먼트 I/O"""
    def _finalize_edit(self):
        self._invalidate_segment_cache()
        self.text_edit.update_margins()
        if hasattr(self.text_edit, 'timestampArea'):
            try:
                self.text_edit._schedule_timestamp_area_update()
            except Exception:
                self.text_edit.timestampArea.update()
        self._schedule_timeline()

    def _schedule_cursor_video_seek(self, sec: float, delay_ms: int = 72) -> None:
        try:
            self._pending_cursor_video_seek_sec = float(sec or 0.0)
        except Exception:
            self._pending_cursor_video_seek_sec = 0.0
        timer = getattr(self, "_cursor_video_seek_timer", None)
        if timer is None:
            self._flush_cursor_video_seek()
            return
        timer.start(max(0, int(delay_ms or 0)))

    def _flush_cursor_video_seek(self) -> None:
        player = getattr(self, "video_player", None)
        if player is None:
            return
        sec = getattr(self, "_pending_cursor_video_seek_sec", None)
        if sec is None:
            return
        self._pending_cursor_video_seek_sec = None
        try:
            player.seek(float(sec))
        except Exception:
            pass

    # ---------------------------------------------------------
    # Segment Queue
    # ---------------------------------------------------------
    def preview_stt_segments(self, segments: list[dict]):
        try:
            if hasattr(self, "status_lbl"):
                self.status_lbl.text()
        except RuntimeError:
            return
        if threading.current_thread() is not threading.main_thread():
            QTimer.singleShot(0, lambda s=list(segments): self.preview_stt_segments(s))
            return

        preview = []
        for seg in segments or []:
            try:
                start = self._frame_time(max(0.0, float(seg.get("start", 0.0) or 0.0)))
                end = self._frame_time(max(start + 0.05, float(seg.get("end", start + 0.5) or start + 0.5)))
            except Exception:
                continue
            text = strip_whisper_control_tokens(str(seg.get("text", "") or ""))
            if not text:
                continue
            item = dict(seg)
            item["start"] = start
            item["end"] = end
            item["text"] = text
            item["stt_preview_source"] = str(
                seg.get("stt_preview_source")
                or seg.get("stt_source")
                or seg.get("stt_ensemble_source")
                or "STT1"
            )
            item["stt_pending"] = True
            item["_live_stt_preview"] = True
            preview.append(item)

        if not preview:
            return

        self._stt_preview_subtitle_drafts_enabled = True
        existing_preview = list(getattr(self, "_live_stt_preview_segments", []) or [])
        existing_preview = self._clamp_segments_to_clip_duration(existing_preview, log_changes=False)
        preview = self._clamp_segments_to_clip_duration(preview, log_changes=False)
        if not preview:
            return
        existing_preview = self._drop_overlapping_preview(existing_preview, preview, same_source_only=True)
        self._live_stt_preview_segments = self._clamp_segments_to_clip_duration(
            existing_preview + preview,
            log_changes=False,
        )
        self._redraw_timeline_with_live_preview()
        if self._processing_live_editor_preview_enabled():
            try:
                confirmed = [seg for seg in self._get_current_segments() if not seg.get("is_gap")]
            except Exception:
                confirmed = list(getattr(self, "_cached_segs", []) or [])
            aligned_preview = align_stt_preview_to_subtitle_segments(
                list(getattr(self, "_live_stt_preview_segments", []) or []),
                confirmed,
            )
            subtitle_preview = self._build_live_subtitle_preview_segments(aligned_preview, confirmed)
            self._queue_live_editor_preview_segments(subtitle_preview)
        else:
            self._clear_live_editor_preview_blocks()
        self._sync_live_preview_playhead_to_video(preview)

    def preview_processing_segments(self, payload):
        try:
            if hasattr(self, "status_lbl"):
                self.status_lbl.text()
        except RuntimeError:
            return
        if threading.current_thread() is not threading.main_thread():
            QTimer.singleShot(0, lambda p=dict(payload or {}): self.preview_processing_segments(p))
            return
        data = dict(payload or {})
        stage_label = str(data.get("stage_label") or data.get("stage") or "자막 후처리").strip()
        rows = [dict(seg) for seg in list(data.get("segments") or []) if isinstance(seg, dict)]
        rows = self._clamp_segments_to_clip_duration(rows, log_changes=False)
        if not rows:
            return
        self._stt_preview_subtitle_drafts_enabled = True
        try:
            confirmed = [seg for seg in self._get_current_segments() if not seg.get("is_gap")]
        except Exception:
            confirmed = list(getattr(self, "_cached_segs", []) or [])
        drafts = self._build_processing_subtitle_preview_segments(
            rows,
            confirmed,
            stage_label=stage_label,
            source_label="PROC",
        )
        if not drafts:
            return
        drafts = self._annotate_live_preview_changed_ranges(drafts)
        self._live_editor_preview_segments = [dict(seg) for seg in drafts]
        self._live_editor_preview_keys = {self._live_editor_preview_key(item) for item in drafts}
        self._redraw_timeline_with_live_preview()
        self._queue_live_editor_preview_segments(drafts, stage_label=stage_label)
        self._sync_live_preview_playhead_to_video(drafts)

    def _processing_live_editor_preview_enabled(self) -> bool:
        try:
            sm = getattr(self, "sm", None)
            if sm is not None:
                if bool(getattr(sm, "is_locked", False)):
                    return True
                if str(getattr(sm, "state", "") or "") == "ST_PROC":
                    return True
        except RuntimeError:
            return False
        except Exception:
            pass
        if bool(getattr(self, "_is_ai_processing", False)):
            return True
        return bool(getattr(self, "_live_editor_preview_pending", False) or getattr(self, "_segment_queue", None))

    def _sync_live_preview_playhead_to_video(self, preview: list[dict]) -> None:
        """Keep the video pane visibly following the newest live STT draft."""
        if not preview:
            return
        settings = getattr(self, "settings", {}) or {}
        follow_enabled = settings.get("editor_live_stt_preview_follow_video_enabled")
        if follow_enabled is None:
            follow_enabled = True
        if not bool(follow_enabled):
            return
        now = time.monotonic()
        try:
            interval = max(
                0.5,
                float(settings.get("editor_live_stt_preview_follow_interval_sec", 2.0) or 2.0),
            )
        except Exception:
            interval = 2.0
        last_at = float(getattr(self, "_last_live_stt_video_follow_at", 0.0) or 0.0)
        if now - last_at < interval:
            return
        self._last_live_stt_video_follow_at = now
        try:
            latest = max(
                preview,
                key=lambda seg: (
                    float(seg.get("start", 0.0) or 0.0),
                    float(seg.get("end", seg.get("start", 0.0)) or 0.0),
                ),
            )
            global_sec = self._frame_time(max(0.0, float(latest.get("start", 0.0) or 0.0)))
        except Exception:
            return

        self._sync_processing_segment_view(global_sec, show_thumbnail=False)

    def _sync_processing_segment_view(self, global_sec: float, *, show_thumbnail: bool = True) -> None:
        try:
            global_sec = self._frame_time(max(0.0, float(global_sec or 0.0)))
        except Exception:
            return

        last_sec = getattr(self, "_last_processing_video_seek_sec", None)
        try:
            if last_sec is not None and abs(float(last_sec) - global_sec) < 0.04:
                return
        except Exception:
            pass
        self._last_processing_video_seek_sec = global_sec
        self._active_seg_start = global_sec

        timeline = getattr(self, "timeline", None)
        if timeline is not None:
            if hasattr(timeline, "set_active"):
                try:
                    timeline.set_active(global_sec)
                except Exception:
                    pass
            if hasattr(timeline, "set_playhead"):
                try:
                    timeline.set_playhead(global_sec, preserve_center_lock=True)
                except TypeError:
                    try:
                        timeline.set_playhead(global_sec)
                    except Exception:
                        pass
                except Exception:
                    pass
            if hasattr(timeline, "center_to_sec"):
                try:
                    timeline.center_to_sec(global_sec, smooth=True)
                except TypeError:
                    try:
                        timeline.center_to_sec(global_sec)
                    except Exception:
                        pass
                except Exception:
                    pass

        local_sec = global_sec
        player = getattr(self, "video_player", None)
        canvas = getattr(timeline, "canvas", None) if timeline is not None else None
        boxes = list(getattr(canvas, "_multiclip_boxes", []) or [])
        if boxes and hasattr(self, "_resolve_active_context") and hasattr(self, "_apply_active_context"):
            try:
                ctx = self._resolve_active_context(global_sec=global_sec)
            except Exception:
                ctx = None
            if ctx:
                clip_file = str(ctx.get("clip_file", "") or "")
                local_sec = float(ctx.get("local_sec", global_sec) or 0.0)
                current_path = str(getattr(player, "_current_source_path", "") or "") if player is not None else ""
                same_source = bool(clip_file and current_path) and os.path.normpath(clip_file) == os.path.normpath(current_path)
                if clip_file and not same_source:
                    try:
                        self._apply_active_context(ctx, autoplay=False, show_thumbnail=show_thumbnail)
                        return
                    except Exception:
                        pass
                if hasattr(canvas, "_active_clip_idx"):
                    try:
                        canvas._active_clip_idx = int(ctx.get("clip_idx", 0) or 0)
                    except Exception:
                        pass
        elif hasattr(self, "_global_to_local_sec"):
            try:
                local_sec = float(self._global_to_local_sec(global_sec))
            except Exception:
                local_sec = global_sec

        if player is None:
            return
        try:
            if hasattr(player, "seek_direct"):
                player.seek_direct(local_sec)
            elif hasattr(player, "frame_step_seek"):
                player.frame_step_seek(local_sec)
            elif hasattr(player, "preview_seek"):
                player.preview_seek(local_sec)
            elif hasattr(player, "seek"):
                player.seek(local_sec)
            if hasattr(player, "set_subtitle_display_time"):
                player.set_subtitle_display_time(local_sec)
            if show_thumbnail:
                self._show_processing_segment_thumbnail(player, local_sec)
        except Exception:
            pass

    def _show_processing_segment_thumbnail(self, player, local_sec: float) -> None:
        extractor = getattr(player, "_extract_and_show_thumbnail_at", None)
        if not callable(extractor):
            return
        source_path = str(getattr(player, "_current_source_path", "") or getattr(self, "media_path", "") or "")
        if not source_path:
            return
        now = time.monotonic()
        last_at = float(getattr(self, "_last_processing_thumbnail_at", 0.0) or 0.0)
        last_sec = getattr(self, "_last_processing_thumbnail_sec", None)
        try:
            same_near_sec = last_sec is not None and abs(float(last_sec) - float(local_sec)) < 0.20
        except Exception:
            same_near_sec = False
        if same_near_sec and now - last_at < 0.80:
            return
        self._last_processing_thumbnail_at = now
        self._last_processing_thumbnail_sec = float(local_sec)
        try:
            extractor(source_path, float(local_sec))
        except Exception:
            pass

    def _live_editor_preview_key(self, seg: dict) -> tuple:
        try:
            start = round(float(seg.get("start", 0.0) or 0.0), 2)
            end = round(float(seg.get("end", start) or start), 2)
        except Exception:
            start = end = 0.0
        return (
            str(seg.get("stt_preview_source") or seg.get("stt_source") or "STT1").strip().upper(),
            start,
            end,
            str(seg.get("text", "") or "").strip(),
        )

    def _live_editor_preview_match(self, seg: dict, *, same_source_only: bool = True):
        try:
            start = float(seg.get("start", 0.0) or 0.0)
            end = float(seg.get("end", start) or start)
        except Exception:
            return None
        source = str(seg.get("stt_preview_source") or seg.get("stt_source") or "STT1").strip().upper()
        best = None
        block = self.text_edit.document().begin() if hasattr(self, "text_edit") else None
        while block is not None and block.isValid():
            data = block.userData()
            if isinstance(data, SubtitleBlockData) and getattr(data, "live_preview", False):
                preview_source = str(getattr(data, "live_preview_source", "") or "STT1").strip().upper()
                if same_source_only and preview_source != source:
                    block = block.next()
                    continue
                try:
                    block_start = float(getattr(data, "start_sec", 0.0) or 0.0)
                except Exception:
                    block_start = 0.0
                block_end = block_start + max(0.3, end - start)
                stored_index = -1
                for idx, stored in enumerate(list(getattr(self, "_live_editor_preview_segments", []) or [])):
                    stored_source = str(stored.get("stt_preview_source") or stored.get("stt_source") or "STT1").strip().upper()
                    if same_source_only and stored_source != preview_source:
                        continue
                    try:
                        stored_start = float(stored.get("start", 0.0) or 0.0)
                        stored_end = float(stored.get("end", stored_start) or stored_start)
                    except Exception:
                        continue
                    if abs(stored_start - block_start) <= 0.08:
                        stored_index = idx
                        block_end = stored_end
                        break
                overlaps = start < block_end + 0.12 and end > block_start - 0.12
                if overlaps:
                    score = abs(block_start - start)
                    if best is None or score < best[0]:
                        best = (score, block, stored_index)
            block = block.next() if block is not None else None
        if best is None:
            return None
        return best[1], int(best[2])

    def _live_preview_base_char_format(self) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setFontItalic(True)
        return fmt

    def _live_preview_changed_char_format(self) -> QTextCharFormat:
        fmt = self._live_preview_base_char_format()
        fmt.setForeground(QColor(COLORS["warning"]))
        return fmt

    def _live_preview_changed_ranges(self, old_text: str, new_text: str) -> list[tuple[int, int]]:
        old_flat = str(old_text or "").replace("\u2028", "\n")
        new_flat = str(new_text or "").replace("\u2028", "\n")
        if not old_flat.strip() or old_flat == new_flat:
            return []

        token_re = re.compile(r"\S+")
        old_tokens = [match.group(0) for match in token_re.finditer(old_flat)]
        new_matches = list(token_re.finditer(new_flat))
        new_tokens = [match.group(0) for match in new_matches]
        if not old_tokens or not new_tokens:
            return [(0, len(new_flat))] if new_flat != old_flat else []

        ranges: list[tuple[int, int]] = []
        matcher = difflib.SequenceMatcher(a=old_tokens, b=new_tokens, autojunk=False)
        for tag, _old_start, _old_end, new_start, new_end in matcher.get_opcodes():
            if tag == "equal" or new_start >= new_end:
                continue
            start = new_matches[new_start].start()
            end = new_matches[new_end - 1].end()
            if end > start:
                ranges.append((start, end))
        return ranges

    def _annotate_live_preview_changed_ranges(self, drafts: list[dict]) -> list[dict]:
        previous = [
            dict(seg)
            for seg in list(getattr(self, "_live_editor_preview_segments", []) or [])
            if isinstance(seg, dict)
        ]
        annotated: list[dict] = []
        for draft in list(drafts or []):
            row = dict(draft)
            try:
                start = float(row.get("start", 0.0) or 0.0)
                end = float(row.get("end", start) or start)
            except Exception:
                start = end = 0.0
            source = str(row.get("stt_preview_source") or row.get("stt_source") or "STT1").strip().upper()
            best_text = ""
            best_score = None
            for old in previous:
                old_source = str(old.get("stt_preview_source") or old.get("stt_source") or "STT1").strip().upper()
                if old_source != source:
                    continue
                try:
                    old_start = float(old.get("start", 0.0) or 0.0)
                    old_end = float(old.get("end", old_start) or old_start)
                except Exception:
                    continue
                if not (start < old_end + 0.12 and end > old_start - 0.12):
                    continue
                score = abs(old_start - start)
                if best_score is None or score < best_score:
                    best_score = score
                    best_text = str(old.get("text", "") or "")
            ranges = self._live_preview_changed_ranges(best_text, str(row.get("text", "") or ""))
            if ranges:
                row["_live_preview_highlight_ranges"] = ranges
            annotated.append(row)
        return annotated

    def _insert_live_preview_formatted_text(
        self,
        cursor: QTextCursor,
        text: str,
        *,
        highlight_ranges: list[tuple[int, int]] | None = None,
    ) -> None:
        display_text = str(text or "").replace("\n", "\u2028")
        ranges = sorted(highlight_ranges or [])
        base_fmt = self._live_preview_base_char_format()
        changed_fmt = self._live_preview_changed_char_format()
        pos = 0
        for start, end in ranges:
            start = max(0, min(int(start), len(display_text)))
            end = max(start, min(int(end), len(display_text)))
            if start > pos:
                cursor.insertText(display_text[pos:start], base_fmt)
            if end > start:
                cursor.insertText(display_text[start:end], changed_fmt)
            pos = end
        if pos < len(display_text):
            cursor.insertText(display_text[pos:], base_fmt)

    def _replace_live_editor_preview_block_text(
        self,
        block,
        text: str,
        *,
        highlight_ranges: list[tuple[int, int]] | None = None,
    ) -> None:
        cursor = QTextCursor(block)
        cursor.setPosition(block.position())
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        self._insert_live_preview_formatted_text(cursor, text, highlight_ranges=highlight_ranges)

    def _update_live_editor_preview_segment(self, seg: dict, *, focus: bool = True) -> bool:
        if not hasattr(self, "text_edit"):
            return False
        text = self._clean_live_editor_preview_text(seg.get("text", ""))
        if not text:
            return False
        match = self._live_editor_preview_match(seg, same_source_only=True)
        if match is None:
            return False
        block, stored_index = match
        if not block.isValid():
            return False
        try:
            start_sec = self._frame_time(max(0.0, float(seg.get("start", 0.0) or 0.0)))
        except Exception:
            start_sec = 0.0
        source = str(seg.get("stt_preview_source") or seg.get("stt_source") or "STT1").strip().upper()
        stage = str(seg.get("live_preview_stage") or f"{source} 실시간 드래프트 갱신").strip()

        prev_inline = bool(getattr(self, "_inline_updating", False))
        prev_sync = bool(getattr(self, "_sync_lock", False))
        doc = self.text_edit.document()
        self._inline_updating = True
        self._sync_lock = True
        doc.blockSignals(True)
        try:
            old_text = str(block.text() or "").replace("\u2028", "\n")
            highlight_ranges = list(seg.get("_live_preview_highlight_ranges") or [])
            if not highlight_ranges:
                highlight_ranges = self._live_preview_changed_ranges(old_text, text)
            self._replace_live_editor_preview_block_text(
                block,
                text,
                highlight_ranges=highlight_ranges,
            )
            data = block.userData()
            spk_id = getattr(data, "spk_id", None) if isinstance(data, SubtitleBlockData) else None
            block.setUserData(
                SubtitleBlockData(
                    str(spk_id or getattr(self, "settings", {}).get("spk1_id", "00") if hasattr(self, "settings") else "00"),
                    start_sec,
                    stt_pending=True,
                    live_preview=True,
                    live_preview_source=source,
                    live_preview_stage=stage,
                )
            )
        finally:
            doc.blockSignals(False)
            self._sync_lock = prev_sync
            self._inline_updating = prev_inline

        updated = dict(seg)
        updated["start"] = start_sec
        updated["text"] = text
        updated["stt_preview_source"] = source
        previews = list(getattr(self, "_live_editor_preview_segments", []) or [])
        if 0 <= stored_index < len(previews):
            previews[stored_index] = updated
        else:
            previews.append(updated)
        self._live_editor_preview_segments = previews
        self._live_editor_preview_keys = {self._live_editor_preview_key(item) for item in previews}
        try:
            self.text_edit.update_margins()
        except Exception:
            pass
        try:
            if hasattr(self.text_edit, "timestampArea"):
                self.text_edit.timestampArea.update()
        except Exception:
            pass
        self._redraw_timeline_with_live_preview()
        if focus:
            self._focus_editor_block_for_processing_segment(
                {
                    "line": block.blockNumber(),
                    "start": start_sec,
                    "end": updated.get("end", start_sec),
                    "text": text,
                }
            )
        return True

    def _insert_live_editor_preview_segment(self, seg: dict, *, source: str | None = None, focus: bool = True) -> bool:
        if not hasattr(self, "text_edit"):
            return False
        text = self._clean_live_editor_preview_text(seg.get("text", ""))
        if not text:
            return False
        if self._update_live_editor_preview_segment(seg, focus=focus):
            return True
        try:
            start_sec = self._frame_time(max(0.0, float(seg.get("start", 0.0) or 0.0)))
        except Exception:
            start_sec = 0.0
        source_label = str(source or seg.get("stt_preview_source") or seg.get("stt_source") or "WORK").strip().upper()
        stage_label = str(seg.get("live_preview_stage") or f"{source_label} 실시간 작업 중").strip()
        prev_inline = bool(getattr(self, "_inline_updating", False))
        prev_sync = bool(getattr(self, "_sync_lock", False))
        doc = self.text_edit.document()
        self._inline_updating = True
        self._sync_lock = True
        doc.blockSignals(True)
        focused_payload = None
        try:
            cursor = QTextCursor(doc)
            cursor.beginEditBlock()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            if doc.blockCount() > 0 and doc.lastBlock().text().strip():
                cursor.insertText("\n")
            self._insert_live_preview_formatted_text(
                cursor,
                text,
                highlight_ranges=list(seg.get("_live_preview_highlight_ranges") or []),
            )
            cursor.block().setUserData(
                SubtitleBlockData(
                    str(getattr(self, "settings", {}).get("spk1_id", "00") if hasattr(self, "settings") else "00"),
                    start_sec,
                    stt_pending=True,
                    live_preview=True,
                    live_preview_source=source_label,
                    live_preview_stage=stage_label,
                )
            )
            focused_payload = {
                "line": cursor.block().blockNumber(),
                "start": start_sec,
                "end": seg.get("end", start_sec),
                "text": text,
            }
            cursor.endEditBlock()
        finally:
            doc.blockSignals(False)
            self._sync_lock = prev_sync
            self._inline_updating = prev_inline
        stored = dict(seg)
        stored["start"] = start_sec
        stored["text"] = text
        stored["stt_preview_source"] = source_label
        previews = list(getattr(self, "_live_editor_preview_segments", []) or [])
        previews.append(stored)
        self._live_editor_preview_segments = previews
        self._live_editor_preview_keys = {self._live_editor_preview_key(item) for item in previews}
        self._redraw_timeline_with_live_preview()
        if focus:
            self._focus_editor_block_for_processing_segment(focused_payload, prefer_last=True)
        return True

    def _queue_live_editor_preview_segments(self, preview: list[dict], stage_label: str | None = None) -> None:
        drafts = [
            dict(seg)
            for seg in list(preview or [])
            if isinstance(seg, dict) and str(seg.get("text", "") or "").strip()
        ]
        drafts.sort(
            key=lambda seg: (
                float(seg.get("start", 0.0) or 0.0),
                float(seg.get("end", seg.get("start", 0.0)) or 0.0),
            )
        )
        self._live_editor_preview_queue = drafts
        self._live_editor_preview_stage_label = str(stage_label or "").strip()
        self._live_editor_preview_pending = bool(drafts)
        timer = getattr(self, "_live_editor_preview_timer", None)
        if timer is not None and hasattr(timer, "start"):
            if not timer.isActive():
                timer.start(self._live_append_reschedule_delay_ms(len(drafts)))
        else:
            self._flush_live_editor_preview_queue()

    def _focus_editor_block_for_processing_segment(self, payload: dict | None, *, prefer_last: bool = False) -> bool:
        data = dict(payload or {})
        try:
            requested_start = float(data.get("start", 0.0) or 0.0)
        except Exception:
            requested_start = 0.0
        if not hasattr(self, "text_edit"):
            self._sync_processing_segment_view(requested_start, show_thumbnail=True)
            return False
        doc = self.text_edit.document()
        target_block = None
        target_start = None
        try:
            line = int(data.get("line", -1))
        except Exception:
            line = -1
        if line >= 0:
            block = doc.findBlockByNumber(line)
            if block.isValid():
                target_block = block

        requested_text = str(data.get("text", "") or "").replace("\u2028", "\n").strip()
        requested_flat = re.sub(r"\s+", " ", requested_text).strip()

        if target_block is None and (requested_start > 0.0 or requested_flat):
            candidates = []
            block = doc.begin()
            while block.isValid():
                block_data = block.userData()
                block_start = None
                if isinstance(block_data, SubtitleBlockData):
                    try:
                        block_start = float(getattr(block_data, "start_sec", 0.0) or 0.0)
                    except Exception:
                        block_start = None
                block_flat = re.sub(r"\s+", " ", str(block.text() or "").replace("\u2028", "\n")).strip()
                time_diff = abs((block_start if block_start is not None else 0.0) - requested_start)
                text_match = bool(requested_flat and block_flat and (block_flat == requested_flat or requested_flat.startswith(block_flat) or block_flat.startswith(requested_flat)))
                if (block_start is not None and time_diff <= 0.18) or text_match:
                    live_bonus = 0 if bool(getattr(block_data, "live_preview", False)) else 1
                    text_bonus = 0 if text_match else 1
                    candidates.append((live_bonus, text_bonus, time_diff, block.blockNumber(), block, block_start))
                block = block.next()
            if candidates:
                candidates.sort(key=lambda item: item[:4])
                _live_bonus, _text_bonus, _time_diff, _line, target_block, target_start = candidates[0]

        if target_block is None and prefer_last:
            target_block = doc.lastBlock()
        if target_block is None or not target_block.isValid():
            self._sync_processing_segment_view(requested_start, show_thumbnail=True)
            return False

        block_data = target_block.userData()
        if target_start is None and isinstance(block_data, SubtitleBlockData):
            try:
                target_start = float(getattr(block_data, "start_sec", 0.0) or 0.0)
            except Exception:
                target_start = None
        if target_start is None:
            target_start = requested_start

        prev_sync = bool(getattr(self, "_sync_lock", False))
        self._sync_lock = True
        try:
            cursor = QTextCursor(target_block)
            self.text_edit.setTextCursor(cursor)
            self.text_edit.ensureCursorVisible()
        finally:
            self._sync_lock = prev_sync

        line_num = target_block.blockNumber()
        highlighter = getattr(self, "_highlighter", None)
        if highlighter is not None and hasattr(highlighter, "set_current_line"):
            try:
                highlighter.set_current_line(line_num)
            except Exception:
                pass
        try:
            self._last_editor_autoscroll_at = time.monotonic()
        except Exception:
            pass
        if target_start is not None:
            self._sync_processing_segment_view(float(target_start), show_thumbnail=True)
        return True

    def _has_live_editor_preview_overlap(self, seg: dict, *, prefer_primary: bool = False) -> bool:
        try:
            start = float(seg.get("start", 0.0) or 0.0)
            end = float(seg.get("end", start) or start)
        except Exception:
            return False
        source = str(seg.get("stt_preview_source") or seg.get("stt_source") or "STT1").strip().upper()
        for existing in list(getattr(self, "_live_editor_preview_segments", []) or []):
            try:
                e_start = float(existing.get("start", 0.0) or 0.0)
                e_end = float(existing.get("end", e_start) or e_start)
            except Exception:
                continue
            if not (start < e_end + 0.05 and end > e_start - 0.05):
                continue
            e_source = str(existing.get("stt_preview_source") or existing.get("stt_source") or "STT1").strip().upper()
            if not prefer_primary or e_source in {"STT1", "STT"} or e_source == source:
                return True
        return False

    def _flush_live_editor_preview_queue(self) -> None:
        processing_enabled = self._processing_live_editor_preview_enabled()
        drafts = [
            dict(seg)
            for seg in list(getattr(self, "_live_editor_preview_queue", []) or [])
            if isinstance(seg, dict) and str(seg.get("text", "") or "").strip()
        ]
        stage_label = str(getattr(self, "_live_editor_preview_stage_label", "") or "").strip()
        self._live_editor_preview_queue = []
        self._live_editor_preview_pending = False
        if not processing_enabled:
            self._clear_live_editor_preview_blocks()
            return
        if not drafts:
            if list(getattr(self, "_live_editor_preview_segments", []) or []):
                return
            live_preview = list(getattr(self, "_live_stt_preview_segments", []) or [])
            if live_preview:
                try:
                    confirmed = [seg for seg in self._get_current_segments() if not seg.get("is_gap")]
                except Exception:
                    confirmed = list(getattr(self, "_cached_segs", []) or [])
                aligned_preview = align_stt_preview_to_subtitle_segments(live_preview, confirmed)
                drafts = [
                    dict(seg)
                    for seg in list(self._build_live_subtitle_preview_segments(aligned_preview, confirmed) or [])
                    if isinstance(seg, dict) and str(seg.get("text", "") or "").strip()
                ]
            if not drafts:
                return
        self._clear_live_editor_preview_blocks()
        for idx, seg in enumerate(drafts):
            source = self._stt_candidate_source(seg)
            self._insert_live_editor_preview_segment(
                seg,
                source=source,
                focus=idx == len(drafts) - 1,
            )
        self._set_live_preview_status(drafts, stage_label=stage_label or None)

    def _clear_live_editor_preview_blocks(self) -> bool:
        self._live_editor_preview_queue = []
        self._live_editor_preview_segments = []
        self._live_editor_preview_keys = set()
        self._live_editor_preview_stage_label = ""
        if not hasattr(self, "text_edit"):
            return False
        doc = self.text_edit.document()
        to_remove = []
        block = doc.begin()
        while block.isValid():
            data = block.userData()
            if isinstance(data, SubtitleBlockData) and getattr(data, "live_preview", False):
                to_remove.append(block.blockNumber())
            block = block.next()
        if not to_remove:
            return False

        prev_inline = bool(getattr(self, "_inline_updating", False))
        prev_sync = bool(getattr(self, "_sync_lock", False))
        self._inline_updating = True
        self._sync_lock = True
        doc.blockSignals(True)
        try:
            cursor = QTextCursor(doc)
            cursor.beginEditBlock()
            for line_num in sorted(to_remove, reverse=True):
                block = doc.findBlockByNumber(line_num)
                if not block.isValid():
                    continue
                cursor.setPosition(block.position())
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
                if block.next().isValid():
                    cursor.deleteChar()
                elif block.previous().isValid():
                    cursor.deletePreviousChar()
                else:
                    block.setUserData(None)
            cursor.endEditBlock()
        finally:
            doc.blockSignals(False)
            self._sync_lock = prev_sync
            self._inline_updating = prev_inline

        try:
            self.text_edit.update_margins()
        except Exception:
            pass
        try:
            if hasattr(self.text_edit, "timestampArea"):
                self.text_edit.timestampArea.update()
        except Exception:
            pass
        return True

    # ---------------------------------------------------------
    # Segment I/O
    # ---------------------------------------------------------

    # ---------------------------------------------------------
    # Text Editor Event Handlers
    # ---------------------------------------------------------
    def _save_correction(self, old_word, new_word):
        _dm_save_correction(self.corrections, old_word, new_word)
        try:
            from core.subtitle_quality.correction_memory import add_correction_memory_item
            add_correction_memory_item(
                old_word,
                new_word,
                source="manual_popup",
                context=self.text_edit.textCursor().block().text()[:500],
            )
        except Exception as exc:
            get_logger().log(f"⚠️ 교정 memory 저장 실패: {exc}")
        get_logger().log(f"🔄 교정 사전 등록 및 저장: {old_word} -> {new_word}")
