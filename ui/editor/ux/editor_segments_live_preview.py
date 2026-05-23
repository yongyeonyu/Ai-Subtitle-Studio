"""Live preview and generation-seam helpers for editor subtitle segments."""

from __future__ import annotations

import difflib
import os
import re
import threading
import time

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor

from core.engine.subtitle_timing import align_stt_preview_to_subtitle_segments
from core.pipeline_status import is_generation_stage_status
from core.native_swift_timeline import (
    build_live_subtitle_preview_via_swift,
    plan_stt_candidate_selection_via_swift,
)
from core.project.project_srt import strip_whisper_control_tokens
from core.timeline_time import segment_display_time_bounds
from ui.editor.ux.subtitle_text_edit import SubtitleBlockData
from ui.style import COLORS


class EditorSegmentsLivePreviewMixin:
    def _clean_live_editor_preview_text(self, text: str) -> str:
        text = str(text or "")
        for attr in (
            "_JUNK_TS_RE",
            "_JUNK_NO_BRACKET_3PART",
            "_JUNK_NO_BRACKET_3PART_END",
            "_JUNK_START_RE",
        ):
            pattern = getattr(self, attr, None)
            if pattern is not None and hasattr(pattern, "sub"):
                text = pattern.sub("", text)
        text = text.strip()
        text = re.sub(r"<[^>]+>", "", text)
        parts = [re.sub(r"[ \t\f\v]+", " ", part).strip() for part in text.replace("\r", "").split("\n")]
        return "\n".join(part for part in parts if part)

    def _compact_generation_repeat_text(self, text: str) -> str:
        cleaned = strip_whisper_control_tokens(str(text or "")).replace("\u2028", "\n")
        cleaned = re.sub(r"\s+", "", cleaned)
        return cleaned.strip()

    def _drop_repeat_previous_queue_segments_with_context(self, segments: list[dict]) -> tuple[list[dict], int]:
        rows = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
        if not rows:
            return rows, 0
        try:
            from core.engine.subtitle_accuracy_pipeline import annotate_subtitle_context_consistency
        except Exception:
            return rows, 0

        try:
            first_start = min(float(seg.get("start", 0.0) or 0.0) for seg in rows)
        except Exception:
            first_start = 0.0
        try:
            settings = dict(getattr(self, "settings", {}) or {})
            repeat_window = max(0.0, float(settings.get("subtitle_context_repeat_window_sec", 4.0) or 4.0))
        except Exception:
            settings = {}
            repeat_window = 4.0
        context_window = max(1.0, repeat_window + 0.25)

        existing_rows: list[dict] = []
        try:
            current_segments = list(self._get_current_segments() or [])
        except Exception:
            current_segments = list(getattr(self, "_cached_segs", []) or [])
        for seg in current_segments:
            if not isinstance(seg, dict) or seg.get("is_gap"):
                continue
            text_key = self._compact_generation_repeat_text(seg.get("text", ""))
            if not text_key:
                continue
            try:
                seg_end = float(seg.get("end", seg.get("start", 0.0)) or 0.0)
            except Exception:
                seg_end = 0.0
            if seg_end >= first_start - context_window:
                existing_rows.append(dict(seg))
        existing_rows = existing_rows[-8:]

        tokenized_rows: list[dict] = []
        for idx, seg in enumerate(rows):
            row = dict(seg)
            row["_append_queue_repeat_token"] = idx
            tokenized_rows.append(row)
        annotated = annotate_subtitle_context_consistency(existing_rows + tokenized_rows, settings)

        kept_by_token: dict[int, dict] = {}
        dropped = 0
        for row in annotated:
            token = row.get("_append_queue_repeat_token")
            if token is None:
                continue
            policy = dict(row.get("_context_consistency_policy") or {})
            flags = {str(flag) for flag in list(policy.get("flags") or [])}
            if "repeat_previous" in flags and self._compact_generation_repeat_text(row.get("text", "")):
                dropped += 1
                continue
            cleaned = dict(row)
            cleaned.pop("_append_queue_repeat_token", None)
            kept_by_token[int(token)] = cleaned

        kept = [kept_by_token[idx] for idx in range(len(rows)) if idx in kept_by_token]
        return kept, dropped

    def _set_live_preview_status(self, drafts: list[dict], stage_label: str | None = None) -> None:
        if not drafts or not hasattr(self, "set_live_processing_stage"):
            return
        if stage_label:
            self.set_live_processing_stage(f"{str(stage_label).strip()} · {len(drafts)}개 위치 표시 중")
            return
        sources = sorted({
            str(seg.get("stt_preview_source") or seg.get("stt_source") or "STT1").strip().upper()
            for seg in drafts
        })
        label = "/".join(source for source in sources if source) or "STT"
        self.set_live_processing_stage(f"{label} 실시간 자막 드래프트 표시 중 · {len(drafts)}개 추가")

    def _live_editor_preview_follow_focus_enabled(self) -> bool:
        settings = getattr(self, "settings", {}) or {}
        if isinstance(settings, dict) and "editor_live_stt_preview_follow_video_enabled" in settings:
            return bool(settings.get("editor_live_stt_preview_follow_video_enabled"))
        return True

    def _live_editor_preview_view_anchor(self) -> dict:
        text_edit = getattr(self, "text_edit", None)
        if text_edit is None:
            return {}
        state: dict = {}
        try:
            state["cursor_position"] = int(text_edit.textCursor().position())
        except Exception:
            pass
        for name in ("verticalScrollBar", "horizontalScrollBar"):
            try:
                bar = getattr(text_edit, name)()
                state[name] = int(bar.value())
            except Exception:
                pass
        return state

    def _restore_live_editor_preview_view_anchor(self, state: dict | None) -> None:
        if not state or not hasattr(self, "text_edit"):
            return
        text_edit = self.text_edit
        if "cursor_position" in state:
            try:
                doc = text_edit.document()
                cursor = QTextCursor(doc)
                max_pos = max(0, int(doc.characterCount() or 1) - 1)
                cursor.setPosition(max(0, min(int(state.get("cursor_position", 0) or 0), max_pos)))
                text_edit.setTextCursor(cursor)
            except Exception:
                pass
        for name in ("verticalScrollBar", "horizontalScrollBar"):
            if name not in state:
                continue
            try:
                getattr(text_edit, name)().setValue(int(state.get(name, 0) or 0))
            except Exception:
                pass

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
        from ui.timeline.stt_preview_layout import ensure_stt_preview_lane_numbers

        combined_preview = self._clamp_segments_to_clip_duration(
            existing_preview + preview,
            log_changes=False,
        )
        ensure_stt_preview_lane_numbers(combined_preview, mutate=True)
        self._live_stt_preview_segments = self._clamp_segments_to_clip_duration(
            combined_preview,
            log_changes=False,
        )
        self._redraw_timeline_with_live_preview()
        if self._processing_live_editor_preview_enabled():
            subtitle_preview = self._build_live_editor_preview_drafts_from_live_stt()
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
        confirmed = self._current_confirmed_segments_for_live_preview()
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

    def _current_confirmed_segments_for_live_preview(self) -> list[dict]:
        try:
            return [seg for seg in self._get_current_segments() if not seg.get("is_gap")]
        except Exception:
            return list(getattr(self, "_cached_segs", []) or [])

    def _build_live_editor_preview_drafts_from_live_stt(self) -> list[dict]:
        confirmed = self._current_confirmed_segments_for_live_preview()
        aligned_preview = align_stt_preview_to_subtitle_segments(
            list(getattr(self, "_live_stt_preview_segments", []) or []),
            confirmed,
        )
        return [
            dict(seg)
            for seg in list(self._build_live_subtitle_preview_segments(aligned_preview, confirmed) or [])
            if isinstance(seg, dict) and str(seg.get("text", "") or "").strip()
        ]

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
        status_label = getattr(self, "status_lbl", None)
        if status_label is not None:
            try:
                if is_generation_stage_status(str(status_label.text() or "")):
                    return True
            except RuntimeError:
                return False
            except Exception:
                pass
        try:
            main_w = self.window()
        except Exception:
            main_w = None
        if main_w is not None:
            if bool(getattr(main_w, "_auto_processing_active", False)):
                return True
            for backend_name in ("backend_fast", "backend"):
                backend = getattr(main_w, backend_name, None)
                if backend is None:
                    continue
                for attr in ("_active", "is_running", "running"):
                    value = getattr(backend, attr, False)
                    if callable(value):
                        try:
                            value = value()
                        except Exception:
                            value = False
                    if bool(value):
                        return True
        return bool(getattr(self, "_live_editor_preview_pending", False) or getattr(self, "_segment_queue", None))

    def _processing_segment_thumbnail_allowed(self, requested: bool) -> bool:
        if not requested:
            return False
        try:
            if self._processing_live_editor_preview_enabled():
                return False
        except Exception:
            return False
        return True

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
                    segment_display_time_bounds(seg)[0],
                    segment_display_time_bounds(seg)[1],
                ),
            )
            global_sec = self._frame_time(max(0.0, segment_display_time_bounds(latest)[0]))
        except Exception:
            return

        self._sync_processing_segment_view(global_sec, show_thumbnail=False)

    def _sync_processing_segment_view(self, global_sec: float, *, show_thumbnail: bool = True) -> None:
        try:
            global_sec = self._frame_time(max(0.0, float(global_sec or 0.0)))
        except Exception:
            return
        show_thumbnail = self._processing_segment_thumbnail_allowed(show_thumbnail)

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
                try:
                    player.seek_direct(local_sec, show_thumbnail=False)
                except TypeError:
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
        try:
            if self._processing_live_editor_preview_enabled():
                return
        except Exception:
            return
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
            display_start, display_end = segment_display_time_bounds(seg)
            start = round(display_start, 2)
            end = round(display_end, 2)
        except Exception:
            start = end = 0.0
        return (
            str(seg.get("stt_preview_source") or seg.get("stt_source") or "STT1").strip().upper(),
            start,
            end,
            str(seg.get("text", "") or "").strip(),
        )

    def _live_editor_preview_signature(self, segs: list[dict] | None) -> tuple:
        rows = []
        for seg in list(segs or []):
            if not isinstance(seg, dict):
                continue
            ranges = []
            for value in list(seg.get("_live_preview_highlight_ranges") or []):
                if not isinstance(value, (list, tuple)) or len(value) != 2:
                    continue
                try:
                    ranges.append((int(value[0]), int(value[1])))
                except Exception:
                    continue
            rows.append(self._live_editor_preview_key(seg) + (tuple(ranges),))
        return tuple(rows)

    def _live_editor_preview_drafts_match_current(self, drafts: list[dict]) -> bool:
        current = list(getattr(self, "_live_editor_preview_segments", []) or [])
        if not current or len(current) != len(drafts):
            return False
        target_signature = self._live_editor_preview_signature(drafts)
        if self._live_editor_preview_signature(current) != target_signature:
            return False
        rendered_signature = tuple(getattr(self, "_live_editor_preview_rendered_signature", ()) or ())
        return rendered_signature == target_signature

    def _live_editor_preview_match(self, seg: dict, *, same_source_only: bool = True):
        try:
            start, end = segment_display_time_bounds(seg)
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
                        stored_start, stored_end = segment_display_time_bounds(stored)
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
                start, end = segment_display_time_bounds(row)
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
                    old_start, old_end = segment_display_time_bounds(old)
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
            start_sec = self._frame_time(max(0.0, segment_display_time_bounds(seg)[0]))
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
        self._live_editor_preview_rendered_signature = self._live_editor_preview_signature(previews)
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
            start_sec = self._frame_time(max(0.0, segment_display_time_bounds(seg)[0]))
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
        self._live_editor_preview_rendered_signature = self._live_editor_preview_signature(previews)
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
                segment_display_time_bounds(seg)[0],
                segment_display_time_bounds(seg)[1],
            )
        )
        # 첫 실시간 드래프트는 debounce를 기다리지 않고 바로 보여 줘야
        # 사용자가 "생성이 시작됐다"는 피드백을 가장 빨리 받는다.
        immediate_flush = self._should_flush_live_editor_preview_immediately(drafts)
        self._live_editor_preview_queue = drafts
        self._live_editor_preview_stage_label = str(stage_label or "").strip()
        self._live_editor_preview_pending = bool(drafts)
        if immediate_flush:
            self._flush_live_editor_preview_queue()
            return
        timer = getattr(self, "_live_editor_preview_timer", None)
        if timer is not None and hasattr(timer, "start"):
            if not timer.isActive():
                timer.start(self._live_append_reschedule_delay_ms(len(drafts)))
        else:
            self._flush_live_editor_preview_queue()

    def _should_flush_live_editor_preview_immediately(self, drafts: list[dict]) -> bool:
        if not drafts:
            return False
        if not self._processing_live_editor_preview_enabled():
            return False
        if list(getattr(self, "_live_editor_preview_segments", []) or []):
            return False
        pending_queue = [
            seg
            for seg in list(getattr(self, "_live_editor_preview_queue", []) or [])
            if isinstance(seg, dict) and str(seg.get("text", "") or "").strip()
        ]
        return not pending_queue

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
            try:
                show_thumbnail = not self._processing_live_editor_preview_enabled()
            except Exception:
                show_thumbnail = False
            self._sync_processing_segment_view(float(target_start), show_thumbnail=show_thumbnail)
        return True

    def _has_live_editor_preview_overlap(self, seg: dict, *, prefer_primary: bool = False) -> bool:
        try:
            start, end = segment_display_time_bounds(seg)
        except Exception:
            return False
        source = str(seg.get("stt_preview_source") or seg.get("stt_source") or "STT1").strip().upper()
        for existing in list(getattr(self, "_live_editor_preview_segments", []) or []):
            try:
                e_start, e_end = segment_display_time_bounds(existing)
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
            drafts = self._build_live_editor_preview_drafts_from_live_stt()
            if not drafts:
                return
        if self._live_editor_preview_drafts_match_current(drafts):
            self._set_live_preview_status(drafts, stage_label=stage_label or None)
            if self._live_editor_preview_follow_focus_enabled():
                self._focus_editor_block_for_processing_segment(drafts[-1], prefer_last=True)
            return
        follow_focus = self._live_editor_preview_follow_focus_enabled()
        view_anchor = None if follow_focus else self._live_editor_preview_view_anchor()
        self._clear_live_editor_preview_blocks()
        for idx, seg in enumerate(drafts):
            source = self._stt_candidate_source(seg)
            self._insert_live_editor_preview_segment(
                seg,
                source=source,
                focus=follow_focus and idx == len(drafts) - 1,
            )
        self._set_live_preview_status(drafts, stage_label=stage_label or None)
        if not follow_focus:
            self._restore_live_editor_preview_view_anchor(view_anchor)

    def _clear_live_editor_preview_blocks(self) -> bool:
        self._live_editor_preview_queue = []
        self._live_editor_preview_segments = []
        self._live_editor_preview_keys = set()
        self._live_editor_preview_stage_label = ""
        self._live_editor_preview_rendered_signature = ()
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

    def _build_processing_subtitle_preview_segments(
        self,
        preview_segments: list[dict],
        confirmed_segments: list[dict] | None = None,
        *,
        stage_label: str = "",
        source_label: str = "PROC",
    ) -> list[dict]:
        confirmed_segments = [
            dict(seg)
            for seg in list(confirmed_segments or [])
            if isinstance(seg, dict) and not seg.get("is_gap") and not seg.get("_live_subtitle_preview")
        ]
        drafts: list[dict] = []
        for idx, seg in enumerate(list(preview_segments or [])):
            if not isinstance(seg, dict):
                continue
            text = self._clean_live_editor_preview_text(seg.get("text", ""))
            if not text:
                continue
            try:
                display_start, display_end = segment_display_time_bounds(seg)
                start = self._frame_time(max(0.0, display_start))
                end = self._frame_time(max(start + 0.05, display_end))
            except Exception:
                continue
            if end <= start:
                continue
            draft = dict(seg)
            draft["start"] = start
            draft["end"] = end
            draft["text"] = text
            draft["line"] = int(seg.get("line", -2000 - idx) or (-2000 - idx))
            draft["_live_subtitle_preview"] = True
            draft["stt_preview_source"] = str(source_label or "PROC").strip().upper()
            draft["stt_ensemble_source"] = draft["stt_preview_source"]
            draft["live_preview_stage"] = str(stage_label or draft.get("live_preview_stage") or "").strip()
            drafts.append(draft)

        drafts = self._drop_overlapping_preview(
            drafts,
            confirmed_segments,
            same_source_only=False,
        )
        for line, draft in enumerate(sorted(drafts, key=lambda item: segment_display_time_bounds(item))):
            draft["line"] = -2000 - line
        return sorted(drafts, key=lambda item: segment_display_time_bounds(item))

    def _remove_live_editor_preview_overlapping(self, final_segments: list[dict]) -> None:
        if not hasattr(self, "text_edit") or not final_segments:
            return
        ranges = []
        for seg in final_segments:
            try:
                start, end = segment_display_time_bounds(seg)
            except Exception:
                continue
            if end > start:
                ranges.append((start, end))
        if not ranges:
            return
        cover_start = min(start for start, _ in ranges)
        cover_end = max(end for _, end in ranges)

        def _covered(start: float, end: float) -> bool:
            return end > cover_start - 0.12 and start < cover_end + 0.12

        doc = self.text_edit.document()
        to_remove = []
        block = doc.begin()
        while block.isValid():
            data = block.userData()
            if isinstance(data, SubtitleBlockData) and getattr(data, "live_preview", False):
                try:
                    start = float(getattr(data, "start_sec", 0.0) or 0.0)
                except Exception:
                    start = 0.0
                end = start + 0.5
                for preview in list(getattr(self, "_live_editor_preview_segments", []) or []):
                    try:
                        p_start, p_end = segment_display_time_bounds(preview)
                    except Exception:
                        continue
                    if abs(p_start - start) <= 0.03:
                        end = p_end
                        break
                if _covered(start, end):
                    to_remove.append(block.blockNumber())
            block = block.next()
        if not to_remove:
            return

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
            cursor.endEditBlock()
        finally:
            doc.blockSignals(False)
            self._sync_lock = prev_sync
            self._inline_updating = prev_inline

        self._live_editor_preview_segments = [
            dict(seg)
            for seg in list(getattr(self, "_live_editor_preview_segments", []) or [])
            if not _covered(*segment_display_time_bounds(seg))
        ]
        self._live_editor_preview_keys = {
            self._live_editor_preview_key(seg)
            for seg in list(getattr(self, "_live_editor_preview_segments", []) or [])
        }
        self._live_editor_preview_rendered_signature = self._live_editor_preview_signature(
            list(getattr(self, "_live_editor_preview_segments", []) or [])
        )
        try:
            self.text_edit.update_margins()
        except Exception:
            pass
        try:
            if hasattr(self.text_edit, "timestampArea"):
                self.text_edit.timestampArea.update()
        except Exception:
            pass

    def _drop_overlapping_preview(self, preview: list[dict], final_segments: list[dict], *, same_source_only: bool = False) -> list[dict]:
        if not preview or not final_segments:
            return list(preview or [])
        ranges = []
        for seg in final_segments or []:
            try:
                range_start, range_end = segment_display_time_bounds(seg)
                ranges.append((
                    range_start,
                    range_end,
                    str(
                        seg.get("stt_preview_source")
                        or seg.get("stt_source")
                        or seg.get("stt_selected_source")
                        or seg.get("stt_ensemble_llm_selected_source")
                        or seg.get("stt_ensemble_source")
                        or ""
                    ).upper(),
                ))
            except Exception:
                continue
        if not ranges:
            return list(preview or [])

        kept = []
        for seg in preview:
            try:
                start, end = segment_display_time_bounds(seg)
                source = str(
                    seg.get("stt_preview_source")
                    or seg.get("stt_source")
                    or seg.get("stt_selected_source")
                    or seg.get("stt_ensemble_llm_selected_source")
                    or seg.get("stt_ensemble_source")
                    or ""
                ).upper()
            except Exception:
                continue
            overlaps = any(
                (not same_source_only or not r_source or not source or r_source == source)
                and start < r_end + 0.05
                and end > r_start - 0.05
                for r_start, r_end, r_source in ranges
            )
            if not overlaps:
                kept.append(seg)
        return kept

    def _build_live_subtitle_preview_segments_native(
        self,
        preview_segments: list[dict],
        confirmed_segments: list[dict] | None = None,
    ) -> list[dict] | None:
        try:
            fps = float(getattr(self, "video_fps", 30.0) or 30.0)
        except Exception:
            fps = 30.0
        rows = build_live_subtitle_preview_via_swift(
            preview_segments=preview_segments,
            confirmed_segments=confirmed_segments or [],
            fps=fps,
        )
        if not isinstance(rows, list):
            return None
        drafts: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized_row = dict(row)
            if "sttPreviewSource" in normalized_row and "stt_preview_source" not in normalized_row:
                normalized_row["stt_preview_source"] = normalized_row.get("sttPreviewSource")
            if "sttSource" in normalized_row and "stt_source" not in normalized_row:
                normalized_row["stt_source"] = normalized_row.get("sttSource")
            if "sttEnsembleSource" in normalized_row and "stt_ensemble_source" not in normalized_row:
                normalized_row["stt_ensemble_source"] = normalized_row.get("sttEnsembleSource")
            try:
                start = self._frame_time(float(normalized_row.get("start", 0.0) or 0.0))
                end = self._frame_time(float(normalized_row.get("end", start) or start))
            except Exception:
                continue
            text = str(normalized_row.get("text", "") or "").strip()
            if not text or end <= start:
                continue
            source = self._stt_candidate_source(normalized_row)
            try:
                score = float(normalized_row.get("sttScore", normalized_row.get("stt_score", normalized_row.get("score", 98.0))) or 98.0)
            except Exception:
                score = 98.0
            score = max(0.0, min(100.0, score if score > 1.0 else score * 100.0))
            candidate = dict(normalized_row)
            candidate["text"] = text
            candidate["source"] = source
            candidate["score"] = score
            candidate["stt_score"] = score
            draft = dict(normalized_row)
            draft["start"] = start
            draft["end"] = end
            draft["text"] = text
            draft["line"] = int(normalized_row.get("line", -1000 - len(drafts)) or (-1000 - len(drafts)))
            draft["_live_subtitle_preview"] = True
            draft["stt_ensemble_source"] = source
            draft["stt_candidates"] = [candidate]
            draft["score"] = score
            draft["stt_score"] = score
            draft["quality"] = {
                "confidence_label": "yellow",
                "confidence_score": score,
                "confidence_reason": f"{source} 실시간 자막 드래프트",
                "flags": ["live_subtitle_preview"],
            }
            drafts.append(draft)
        return drafts

    def _plan_stt_candidate_selection_native(
        self,
        current_segments: list[dict],
        candidate: dict,
    ) -> dict | None:
        try:
            fps = float(getattr(self, "video_fps", 30.0) or 30.0)
        except Exception:
            fps = 30.0
        return plan_stt_candidate_selection_via_swift(
            current_segments=current_segments,
            live_preview_segments=list(getattr(self, "_live_stt_preview_segments", []) or []),
            candidate=candidate,
            fps=fps,
        )

    def _build_live_subtitle_preview_segments(
        self,
        preview_segments: list[dict],
        confirmed_segments: list[dict] | None = None,
    ) -> list[dict]:
        """Build non-persistent subtitle-lane drafts from live STT candidates."""
        confirmed_segments = [
            dict(seg) for seg in list(confirmed_segments or [])
            if isinstance(seg, dict) and not seg.get("is_gap") and not seg.get("_live_subtitle_preview")
        ]
        native_drafts = self._build_live_subtitle_preview_segments_native(
            preview_segments,
            confirmed_segments,
        )
        if native_drafts is not None:
            filtered_drafts = self._drop_overlapping_preview(
                native_drafts,
                confirmed_segments,
                same_source_only=False,
            )
            for line, draft in enumerate(sorted(filtered_drafts, key=lambda seg: segment_display_time_bounds(seg))):
                draft["line"] = -1000 - line
            return filtered_drafts
        preview_segments = [dict(seg) for seg in list(preview_segments or []) if isinstance(seg, dict)]
        preview_segments = self._drop_overlapping_preview(
            preview_segments,
            confirmed_segments,
            same_source_only=False,
        )
        if not preview_segments:
            return []

        def _source_priority(seg: dict) -> int:
            source = self._stt_candidate_source(seg)
            if source == "STT1":
                return 0
            if source in {"STT", ""}:
                return 1
            if source == "STT2":
                return 2
            return 3

        def _overlaps(left: dict, right: dict) -> bool:
            try:
                l_start, l_end = segment_display_time_bounds(left)
                r_start, r_end = segment_display_time_bounds(right)
            except Exception:
                return False
            return l_start < r_end + 0.05 and l_end > r_start - 0.05

        drafts: list[dict] = []
        ordered = sorted(
            preview_segments,
            key=lambda seg: (
                segment_display_time_bounds(seg)[0],
                _source_priority(seg),
                segment_display_time_bounds(seg)[1],
            ),
        )
        for seg in ordered:
            text = str(seg.get("text", "") or "").strip()
            if not text:
                continue
            display_start, display_end = segment_display_time_bounds(seg)
            start = self._frame_time(max(0.0, display_start))
            end = self._frame_time(max(start + 0.05, display_end))
            source = self._stt_candidate_source(seg)
            try:
                score = float(seg.get("stt_score", seg.get("score", 98.0)) or 98.0)
            except Exception:
                score = 98.0
            score = max(0.0, min(100.0, score if score > 1.0 else score * 100.0))
            candidate = dict(seg)
            candidate["text"] = text
            candidate["source"] = source
            candidate["score"] = score
            candidate["stt_score"] = score
            draft = dict(seg)
            draft.pop("stt_pending", None)
            draft.pop("_live_stt_preview", None)
            draft["start"] = start
            draft["end"] = end
            draft["text"] = text
            draft["line"] = -1000 - len(drafts)
            draft["_live_subtitle_preview"] = True
            draft["stt_ensemble_source"] = source
            draft["stt_candidates"] = [candidate]
            draft["score"] = score
            draft["stt_score"] = score
            draft["quality"] = {
                "confidence_label": "yellow",
                "confidence_score": score,
                "confidence_reason": f"{source} 실시간 자막 드래프트",
                "flags": ["live_subtitle_preview"],
            }

            replace_idx = None
            skip = False
            for idx, existing in enumerate(drafts):
                if not _overlaps(draft, existing):
                    continue
                if _source_priority(draft) < _source_priority(existing):
                    replace_idx = idx
                else:
                    skip = True
                break
            if replace_idx is not None:
                drafts[replace_idx] = draft
            elif not skip:
                drafts.append(draft)

        for line, draft in enumerate(sorted(drafts, key=lambda seg: (seg["start"], seg["end"]))):
            draft["line"] = -1000 - line
        return sorted(drafts, key=lambda seg: (seg["start"], seg["end"]))
