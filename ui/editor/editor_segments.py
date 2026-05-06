# Version: 03.14.29
# Phase: PHASE2
"""
ui/editor_segments.py
EditorWidget의 자막 에디터 조작, 큐 처리, 세그먼트 I/O 메서드 모음.
[수정] core 폴더 이동에 따른 데이터 매니저 경로 및 상대 경로 최적화 완료
"""
import hashlib, json, re, threading, time
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QTextCursor

from core.runtime.logger import get_logger
from core.engine.subtitle_timing import align_stt_preview_to_subtitle_segments

# 💡 [경로 수정] editor_data_manager -> core.data_manager
from core.project.data_manager import save_correction as _dm_save_correction

# 수정 — 절대 import로 통일 (editor_widget.py, editor_timeline_video.py와 동일)
from ui.editor.subtitle_text_edit import SubtitleBlockData
from ui.editor.editor_helpers import build_segment_lookup, find_segment_for_line_lookup
from ui.editor.editor_roughcut_draft import EditorRoughcutDraftMixin

class EditorSegmentsMixin(EditorRoughcutDraftMixin):
    """자막 에디터 조작 / 큐 처리 / 세그먼트 I/O"""
    # ---------------------------------------------------------
    # Common Helpers (여러 Mixin에서 공용)
    # ---------------------------------------------------------
    def _frame_time(self, sec: float) -> float:
        if hasattr(self, "_snap_to_frame"):
            return self._snap_to_frame(sec)
        return round(float(sec), 6)

    def _mark_dirty(self):
        if hasattr(self, "_has_unsaved_changes") and not self._has_unsaved_changes():
            return
        started_editing = False
        if hasattr(self, "sm"):
            if hasattr(self.sm, "start_editing") and not getattr(self.sm, "is_locked", False):
                self.sm.start_editing()
                started_editing = True
            else:
                self.sm.is_dirty = True
        else:
            self._is_dirty = True
        if started_editing and hasattr(self, "_note_editor_foreground_activity"):
            self._note_editor_foreground_activity()
        try:
            main_w = self.window()
            if hasattr(main_w, "_refresh_saved_status_label"):
                main_w._refresh_saved_status_label(is_dirty=True)
        except Exception:
            pass

    def _note_editor_foreground_activity(self):
        try:
            main_w = self.window()
            reset_idle = getattr(main_w, "_reset_post_completion_idle_timer", None)
            if callable(reset_idle):
                reset_idle()
            pause_lora = getattr(main_w, "_pause_personalization_for_foreground_activity", None)
            if callable(pause_lora):
                pause_lora("subtitle_editor_edit", hold_ms=300_000)
        except Exception:
            pass

    def _request_editor_mode_runtime_release(self):
        self._note_editor_foreground_activity()

    def _rebuild_subtitle_memory_cache(self, segments: list[dict] | None = None) -> dict:
        segs = list(segments if segments is not None else self._get_current_segments())
        self._cached_segs = segs
        cache = build_segment_lookup(segs)
        self._subtitle_memory_cache = cache
        return cache

    def _subtitle_memory_segments(self) -> list[dict]:
        cache = getattr(self, "_subtitle_memory_cache", None)
        if not isinstance(cache, dict):
            cached = getattr(self, "_cached_segs", None)
            cache = build_segment_lookup(cached) if cached is not None else self._rebuild_subtitle_memory_cache()
            self._subtitle_memory_cache = cache
        return list(cache.get("segments") or [])

    def _subtitle_memory_visible_segments(self) -> list[dict]:
        cache = getattr(self, "_subtitle_memory_cache", None)
        if not isinstance(cache, dict):
            cached = getattr(self, "_cached_segs", None)
            cache = build_segment_lookup(cached) if cached is not None else self._rebuild_subtitle_memory_cache()
            self._subtitle_memory_cache = cache
        return list(cache.get("visible_segments") or [])

    def _update_subtitle_memory_line_text(self, line_num: int, text: str) -> None:
        visible_text = str(text or "").replace("\u2028", "\n")
        for seg in list(getattr(self, "_cached_segs", []) or []):
            if int(seg.get("line", -999999)) == int(line_num):
                seg["text"] = visible_text
                break
        cache = getattr(self, "_subtitle_memory_cache", None)
        if isinstance(cache, dict):
            seg = (cache.get("line_map") or {}).get(int(line_num))
            if isinstance(seg, dict):
                seg["text"] = visible_text
            # Keep visible playback lookup in sync with text becoming empty/non-empty.
            self._subtitle_memory_cache = build_segment_lookup(getattr(self, "_cached_segs", []) or [])

    def _finalize_edit(self):
        self.text_edit.update_margins()
        if hasattr(self.text_edit, 'timestampArea'):
            self.text_edit.timestampArea.update()
        self._schedule_timeline()

    def _segment_quality_signature(self, seg: dict) -> str:
        payload = {
            "start": round(float(seg.get("start", 0.0) or 0.0), 3),
            "end": round(float(seg.get("end", seg.get("start", 0.0)) or 0.0), 3),
            "text": str(seg.get("text", "") or ""),
            "speaker": str(seg.get("speaker", seg.get("spk", "")) or ""),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _quality_kwargs_from_segment(self, seg: dict, *, signature: str | None = None) -> dict:
        quality = dict(seg.get("quality") or {})
        history = list(seg.get("quality_history") or [])
        candidates = list(seg.get("quality_candidates") or [])
        return {
            "quality": quality,
            "quality_history": history,
            "quality_candidates": candidates,
            "quality_signature": signature or str(seg.get("quality_signature", "") or ""),
        }

    def _quality_tooltip(self, seg: dict) -> str:
        quality = dict(seg.get("quality") or {})
        stage_confidence = dict(seg.get("subtitle_stage_confidence") or {})
        if not quality and not stage_confidence:
            return ""
        score = quality.get("confidence_score")
        label = str(quality.get("confidence_label") or "gray")
        reason = str(quality.get("confidence_reason") or "")
        flags = ", ".join(str(flag) for flag in (quality.get("flags") or ())[:6])
        candidates = len(seg.get("quality_candidates") or [])
        stale = " / stale" if seg.get("quality_stale") else ""
        score_text = "-" if score is None else f"{float(score):.1f}"
        lines = [f"품질 {label}{stale} · {score_text}점", f"사유: {reason or flags or 'ok'}", f"후보: {candidates}개"]
        stages = dict(stage_confidence.get("stages") or {})
        if stages:
            names = {"cut": "컷", "stt": "STT", "llm": "LLM", "lora": "LoRA", "final": "최종"}
            stage_bits = []
            for key in list(stage_confidence.get("stage_order") or ["cut", "stt", "llm", "lora", "final"]):
                item = dict(stages.get(key) or {})
                if not item:
                    continue
                stage_score = item.get("score")
                stage_score_text = "-" if stage_score is None else f"{float(stage_score):.0f}"
                stage_bits.append(f"{names.get(key, key)} {item.get('label', 'gray')} {stage_score_text}")
            if stage_bits:
                lines.append("단계 신뢰도: " + " · ".join(stage_bits))
        return "\n".join(lines)

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
            text = str(seg.get("text", "") or "").strip()
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

        existing_preview = list(getattr(self, "_live_stt_preview_segments", []) or [])
        existing_preview = self._drop_overlapping_preview(existing_preview, preview, same_source_only=True)
        self._live_stt_preview_segments = existing_preview + preview
        self._redraw_timeline_with_live_preview()
        self._queue_live_editor_preview_segments(preview)

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

    def _queue_live_editor_preview_segments(self, preview: list[dict]) -> None:
        if not hasattr(self, "text_edit") or not preview:
            return
        queued = getattr(self, "_live_editor_preview_queue", None)
        if queued is None:
            self._live_editor_preview_queue = []
            queued = self._live_editor_preview_queue
        seen = getattr(self, "_live_editor_preview_keys", None)
        if seen is None:
            self._live_editor_preview_keys = set()
            seen = self._live_editor_preview_keys

        for seg in preview:
            key = self._live_editor_preview_key(seg)
            if key in seen:
                continue
            source = key[0]
            if source not in {"STT1", "STT"} and self._has_live_editor_preview_overlap(seg, prefer_primary=True):
                continue
            seen.add(key)
            queued.append(dict(seg))

        if not queued:
            return
        timer = getattr(self, "_live_editor_preview_timer", None)
        if timer is not None:
            try:
                if not timer.isActive():
                    timer.start(320)
                return
            except Exception:
                pass
        self._flush_live_editor_preview_queue()

    def _focus_editor_block_for_processing_segment(self, payload: dict | None, *, prefer_last: bool = False) -> bool:
        if not hasattr(self, "text_edit"):
            return False
        data = dict(payload or {})
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

        try:
            requested_start = float(data.get("start", 0.0) or 0.0)
        except Exception:
            requested_start = 0.0
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
            self._active_seg_start = float(target_start)
            timeline = getattr(self, "timeline", None)
            if timeline is not None and hasattr(timeline, "set_active"):
                try:
                    timeline.set_active(float(target_start))
                except Exception:
                    pass
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
        if not hasattr(self, "text_edit"):
            return
        queue = list(getattr(self, "_live_editor_preview_queue", []) or [])
        self._live_editor_preview_queue = []
        if not queue:
            return

        drafts = []
        for seg in sorted(queue, key=lambda row: (float(row.get("start", 0.0) or 0.0), float(row.get("end", 0.0) or 0.0))):
            if self._has_live_editor_preview_overlap(seg, prefer_primary=True):
                continue
            text = str(seg.get("text", "") or "").replace("\u2028", "\n").strip()
            if not text:
                continue
            draft = dict(seg)
            draft["text"] = text
            drafts.append(draft)
        if not drafts:
            return

        doc = self.text_edit.document()
        if not hasattr(self, "_live_editor_preview_segments"):
            self._live_editor_preview_segments = []
        prev_inline = bool(getattr(self, "_inline_updating", False))
        prev_sync = bool(getattr(self, "_sync_lock", False))
        self._inline_updating = True
        self._sync_lock = True
        focused_payload = None
        doc.blockSignals(True)
        try:
            cursor = QTextCursor(doc)
            cursor.beginEditBlock()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            if doc.blockCount() > 0 and doc.lastBlock().text().strip():
                cursor.insertText("\n")
            spk_id = str(getattr(self, "settings", {}).get("spk1_id", "00") if hasattr(self, "settings") else "00")
            for index, seg in enumerate(drafts):
                if index > 0:
                    cursor.insertText("\n")
                text = self._clean_live_editor_preview_text(seg.get("text", ""))
                if not text:
                    continue
                try:
                    start_sec = self._frame_time(max(0.0, float(seg.get("start", 0.0) or 0.0)))
                except Exception:
                    start_sec = 0.0
                source = str(seg.get("stt_preview_source") or seg.get("stt_source") or "STT1").strip().upper()
                cursor.insertText(text.replace("\n", "\u2028"))
                cursor.block().setUserData(
                    SubtitleBlockData(
                        spk_id,
                        start_sec,
                        stt_pending=True,
                        live_preview=True,
                        live_preview_source=source,
                        live_preview_stage=f"{source} 실시간 드래프트",
                    )
                )
                stored = dict(seg)
                stored["start"] = start_sec
                stored["stt_preview_source"] = source
                self._live_editor_preview_segments.append(stored)
                focused_payload = {
                    "line": cursor.block().blockNumber(),
                    "start": start_sec,
                    "end": stored.get("end", start_sec),
                    "text": text,
                }
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
        self._set_live_preview_status(drafts)
        self._focus_editor_block_for_processing_segment(focused_payload, prefer_last=True)

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

    def _set_live_preview_status(self, drafts: list[dict]) -> None:
        if not drafts or not hasattr(self, "set_live_processing_stage"):
            return
        sources = sorted({
            str(seg.get("stt_preview_source") or seg.get("stt_source") or "STT1").strip().upper()
            for seg in drafts
        })
        label = "/".join(source for source in sources if source) or "STT"
        self.set_live_processing_stage(f"{label} 실시간 자막 드래프트 표시 중 · {len(drafts)}개 추가")

    def _remove_live_editor_preview_overlapping(self, final_segments: list[dict]) -> None:
        if not hasattr(self, "text_edit") or not final_segments:
            return
        ranges = []
        for seg in final_segments:
            try:
                start = float(seg.get("start", 0.0) or 0.0)
                end = float(seg.get("end", start) or start)
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
                        p_start = float(preview.get("start", 0.0) or 0.0)
                    except Exception:
                        continue
                    if abs(p_start - start) <= 0.03:
                        try:
                            end = float(preview.get("end", end) or end)
                        except Exception:
                            pass
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
            if not _covered(float(seg.get("start", 0.0) or 0.0), float(seg.get("end", seg.get("start", 0.0)) or 0.0))
        ]
        self._live_editor_preview_keys = {
            self._live_editor_preview_key(seg)
            for seg in list(getattr(self, "_live_editor_preview_segments", []) or [])
        }
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
                ranges.append((
                    float(seg.get("start", 0.0) or 0.0),
                    float(seg.get("end", 0.0) or 0.0),
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
                start = float(seg.get("start", 0.0) or 0.0)
                end = float(seg.get("end", start) or start)
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

    def _build_live_subtitle_preview_segments(
        self,
        preview_segments: list[dict],
        confirmed_segments: list[dict] | None = None,
    ) -> list[dict]:
        """Build non-persistent subtitle-lane drafts from live STT candidates."""
        preview_segments = [dict(seg) for seg in list(preview_segments or []) if isinstance(seg, dict)]
        confirmed_segments = [
            dict(seg) for seg in list(confirmed_segments or [])
            if isinstance(seg, dict) and not seg.get("is_gap") and not seg.get("_live_subtitle_preview")
        ]
        preview_segments = self._drop_overlapping_preview(
            preview_segments,
            confirmed_segments,
            same_source_only=False,
        )
        if not preview_segments:
            return []

        def _as_float(value, default=0.0):
            try:
                return float(value)
            except Exception:
                return default

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
                l_start = float(left.get("start", 0.0) or 0.0)
                l_end = float(left.get("end", l_start) or l_start)
                r_start = float(right.get("start", 0.0) or 0.0)
                r_end = float(right.get("end", r_start) or r_start)
            except Exception:
                return False
            return l_start < r_end + 0.05 and l_end > r_start - 0.05

        drafts: list[dict] = []
        ordered = sorted(
            preview_segments,
            key=lambda seg: (
                _as_float(seg.get("start")),
                _source_priority(seg),
                _as_float(seg.get("end")),
            ),
        )
        for seg in ordered:
            text = str(seg.get("text", "") or "").strip()
            if not text:
                continue
            start = self._frame_time(max(0.0, _as_float(seg.get("start"))))
            end = self._frame_time(max(start + 0.05, _as_float(seg.get("end"), start + 0.5)))
            source = self._stt_candidate_source(seg)
            try:
                score = float(seg.get("stt_score", seg.get("score", 98.0)) or 98.0)
            except Exception:
                score = 98.0
            score = max(0.0, min(100.0, score if score > 1.0 else score * 100.0))
            candidate = dict(seg)
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

    def _stt_candidate_source(self, seg: dict) -> str:
        source = (
            seg.get("stt_preview_source")
            or seg.get("stt_source")
            or seg.get("stt_ensemble_source")
            or "STT1"
        )
        return str(source or "STT1").strip().upper()

    def _segment_overlap_ratio(self, left: dict, right: dict) -> float:
        try:
            l_start = float(left.get("start", 0.0) or 0.0)
            l_end = float(left.get("end", l_start) or l_start)
            r_start = float(right.get("start", 0.0) or 0.0)
            r_end = float(right.get("end", r_start) or r_start)
        except Exception:
            return 0.0
        overlap = max(0.0, min(l_end, r_end) - max(l_start, r_start))
        base = max(0.001, min(max(0.001, l_end - l_start), max(0.001, r_end - r_start)))
        return overlap / base

    def _segment_overlaps_time_range(self, seg: dict, start: float, end: float, pad: float = 0.001) -> bool:
        try:
            seg_start = float(seg.get("start", 0.0) or 0.0)
            seg_end = float(seg.get("end", seg_start) or seg_start)
        except Exception:
            return False
        return seg_start < end - pad and seg_end > start + pad

    def _best_final_segment_for_stt_candidate(self, segments: list[dict], candidate: dict) -> dict | None:
        try:
            cand_start = float(candidate.get("start", 0.0) or 0.0)
            cand_end = float(candidate.get("end", cand_start) or cand_start)
        except Exception:
            return None
        if cand_end <= cand_start:
            return None
        cand_dur = max(0.001, cand_end - cand_start)
        cand_center = (cand_start + cand_end) / 2.0
        best_seg = None
        best_score = 0.0
        fps = max(1.0, float(getattr(self, "video_fps", 30.0) or 30.0))
        edge_tol = max(0.18, min(0.45, 6.0 / fps))

        for seg in segments or []:
            if seg.get("is_gap"):
                continue
            try:
                start = float(seg.get("start", 0.0) or 0.0)
                end = float(seg.get("end", start) or start)
            except Exception:
                continue
            if end <= start:
                continue
            seg_dur = max(0.001, end - start)
            overlap = max(0.0, min(end, cand_end) - max(start, cand_start))
            center_bonus = 1.0 if start - edge_tol <= cand_center <= end + edge_tol else 0.0
            edge_bonus = 0.0
            if abs(cand_start - start) <= edge_tol:
                edge_bonus += 0.5
            if abs(cand_end - end) <= edge_tol:
                edge_bonus += 0.5
            if overlap <= 0.0 and not center_bonus:
                continue
            score = (overlap / cand_dur) * 0.55 + (overlap / seg_dur) * 0.30 + center_bonus * 0.10 + edge_bonus * 0.05
            if score > best_score:
                best_score = score
                best_seg = seg

        return dict(best_seg) if best_seg is not None and best_score >= 0.35 else None

    def _fit_stt_candidate_to_final_segment_slot(self, candidate: dict, segments: list[dict]) -> dict:
        placed = dict(candidate or {})
        target = self._best_final_segment_for_stt_candidate(segments, placed)
        if not target:
            placed["_stt_placement_mode"] = "raw"
            return placed

        try:
            cand_start = float(placed.get("start", 0.0) or 0.0)
            cand_end = float(placed.get("end", cand_start) or cand_start)
            target_start = float(target.get("start", 0.0) or 0.0)
            target_end = float(target.get("end", target_start) or target_start)
        except Exception:
            placed["_stt_placement_mode"] = "raw"
            return placed
        if cand_end <= cand_start or target_end <= target_start:
            placed["_stt_placement_mode"] = "raw"
            return placed

        cand_dur = max(0.001, cand_end - cand_start)
        target_dur = max(0.001, target_end - target_start)
        overlap = max(0.0, min(target_end, cand_end) - max(target_start, cand_start))
        cand_coverage = overlap / cand_dur
        target_coverage = overlap / target_dur
        fps = max(1.0, float(getattr(self, "video_fps", 30.0) or 30.0))
        edge_tol = max(0.18, min(0.45, 6.0 / fps))
        near_start = abs(cand_start - target_start) <= edge_tol
        near_end = abs(cand_end - target_end) <= edge_tol
        center = (cand_start + cand_end) / 2.0
        center_in_target = target_start - edge_tol <= center <= target_end + edge_tol

        if (
            (cand_coverage >= 0.80 and target_coverage >= 0.70)
            or (cand_coverage >= 0.75 and near_start and near_end)
            or (target_coverage >= 0.82 and center_in_target)
        ):
            placed["start"] = self._frame_time(target_start)
            placed["end"] = self._frame_time(target_end)
            placed["_stt_placement_mode"] = "replace_original_slot"
        elif overlap > 0.0 and center_in_target:
            placed["start"] = self._frame_time(max(cand_start, target_start))
            placed["end"] = self._frame_time(min(cand_end, target_end))
            placed["_stt_placement_mode"] = "clamp_to_original_slot"
        else:
            placed["_stt_placement_mode"] = "raw"

        placed["_stt_target_line"] = target.get("line")
        placed["_stt_target_start"] = target_start
        placed["_stt_target_end"] = target_end
        for key in ("speaker", "spk", "_clip_idx", "_clip_file"):
            if key in target and key not in placed:
                placed[key] = target[key]
        return placed

    def _trim_final_segments_around_candidate(self, segments: list[dict], candidate: dict) -> list[dict]:
        try:
            cand_start = self._frame_time(float(candidate.get("start", 0.0) or 0.0))
            cand_end = self._frame_time(float(candidate.get("end", cand_start) or cand_start))
        except Exception:
            return list(segments or [])
        min_keep = max(0.08, float(getattr(self, "video_fps", 30.0) and (2.0 / max(1.0, float(getattr(self, "video_fps", 30.0) or 30.0)))))
        trimmed: list[dict] = []
        for seg in segments or []:
            try:
                start = self._frame_time(float(seg.get("start", 0.0) or 0.0))
                end = self._frame_time(float(seg.get("end", start) or start))
            except Exception:
                continue
            if not self._segment_overlaps_time_range(seg, cand_start, cand_end):
                trimmed.append(dict(seg))
                continue
            if start < cand_start and cand_start - start >= min_keep:
                left = dict(seg)
                left["start"] = start
                left["end"] = self._frame_time(cand_start)
                trimmed.append(left)
            if cand_end < end and end - cand_end >= min_keep:
                right = dict(seg)
                right["start"] = self._frame_time(cand_end)
                right["end"] = end
                trimmed.append(right)
        return trimmed

    def _final_segment_from_stt_candidate(self, candidate: dict) -> dict:
        source = self._stt_candidate_source(candidate)
        start = self._frame_time(max(0.0, float(candidate.get("start", 0.0) or 0.0)))
        end = self._frame_time(max(start + 0.05, float(candidate.get("end", start + 0.5) or start + 0.5)))
        text = str(candidate.get("text", "") or "").strip()
        try:
            candidate_score = max(0.0, min(100.0, float(candidate.get("stt_score", candidate.get("score", 98.0)) or 98.0)))
        except Exception:
            candidate_score = 98.0
        candidate_payload = dict(candidate)
        candidate_payload["source"] = source
        candidate_payload["score"] = candidate_score
        candidate_payload["stt_score"] = candidate_score
        seg = {
            "start": start,
            "end": end,
            "text": text,
            "speaker": str(candidate.get("speaker", candidate.get("spk", "00")) or "00"),
            "stt_selected_source": source,
            "stt_candidates": [candidate_payload],
            "score": max(candidate_score, 98.0),
            "stt_score": max(candidate_score, 98.0),
            "score_color": str(candidate.get("score_color") or candidate.get("stt_score_color") or ""),
            "quality": {
                "confidence_label": "green",
                "confidence_score": max(candidate_score, 98.0),
                "confidence_reason": f"{source} 후보 수동 확정",
                "manual_confirmed": True,
                "flags": ["manual_confirmed", "stt_candidate_selected"],
            },
        }
        for key in ("_clip_idx", "_clip_file"):
            if key in candidate:
                seg[key] = candidate[key]
        return seg

    def select_stt_candidate_as_subtitle(self, candidate: dict):
        try:
            if hasattr(self, "status_lbl"):
                self.status_lbl.text()
        except RuntimeError:
            return
        if threading.current_thread() is not threading.main_thread():
            QTimer.singleShot(0, lambda c=dict(candidate): self.select_stt_candidate_as_subtitle(c))
            return
        if not candidate:
            return

        # ---------------------------------------------------------
        # 1. 튕김 방지: 현재 스크롤 위치 캡처
        # ---------------------------------------------------------
        saved_h_scroll = None
        saved_v_scroll = 0
        if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
            try:
                saved_h_scroll = int(self.timeline.scroll.horizontalScrollBar().value())
            except Exception:
                saved_h_scroll = None
        if hasattr(self, "text_edit"):
            saved_v_scroll = self.text_edit.verticalScrollBar().value()

        try:
            if hasattr(self, "_undo_mgr"):
                self._undo_mgr.push_immediate()
        except Exception:
            pass

        current = [dict(seg) for seg in self._get_current_segments() if not seg.get("is_gap")]
        
        # ---------------------------------------------------------
        # 2. 클릭한 후보 정보 추출
        # ---------------------------------------------------------
        cand_text = str(candidate.get("text", "")).strip()
        cand_start = float(candidate.get("start", 0.0) or 0.0)
        
        cand_source = ""
        if hasattr(self, "_stt_candidate_source"):
            cand_source = self._stt_candidate_source(candidate)
        else:
            cand_source = str(candidate.get("stt_preview_source") or candidate.get("stt_source") or candidate.get("stt_ensemble_source") or "").strip().upper()

        if not cand_text or not cand_source:
            return

        # ---------------------------------------------------------
        # 3. 겹치는 최종 자막을 후보 경계 기준으로 잘라내고 새 확정 자막 삽입
        # ---------------------------------------------------------
        placed_candidate = self._fit_stt_candidate_to_final_segment_slot(candidate, current)
        selected_seg = self._final_segment_from_stt_candidate(placed_candidate)
        candidate_anchor_sec = float(selected_seg.get("start", cand_start) or cand_start)

        current = self._trim_final_segments_around_candidate(current, placed_candidate)
        current.append(selected_seg)
        current.sort(key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)))
        # Keep preview candidates stable for undo/redo and single-candidate
        # workflows, but if multiple overlapping candidates exist for the same
        # slot then drop only the source the user just selected so the
        # remaining alternative stays selectable without a duplicate highlight.
        existing_preview = [dict(seg) for seg in list(getattr(self, "_live_stt_preview_segments", []) or [])]
        has_alternative_overlap = any(
            float(seg.get("start", 0.0) or 0.0) < float(selected_seg.get("end", 0.0) or 0.0) + 0.05
            and float(seg.get("end", 0.0) or 0.0) > float(selected_seg.get("start", 0.0) or 0.0) - 0.05
            and str(
                seg.get("stt_preview_source")
                or seg.get("stt_source")
                or seg.get("stt_selected_source")
                or seg.get("stt_ensemble_llm_selected_source")
                or seg.get("stt_ensemble_source")
                or ""
            ).strip().upper() != cand_source
            for seg in existing_preview
        )
        if has_alternative_overlap:
            kept_preview = []
            for seg in existing_preview:
                source = str(
                    seg.get("stt_preview_source")
                    or seg.get("stt_source")
                    or seg.get("stt_selected_source")
                    or seg.get("stt_ensemble_llm_selected_source")
                    or seg.get("stt_ensemble_source")
                    or ""
                ).strip().upper()
                overlaps = (
                    float(seg.get("start", 0.0) or 0.0) < float(selected_seg.get("end", 0.0) or 0.0) + 0.05
                    and float(seg.get("end", 0.0) or 0.0) > float(selected_seg.get("start", 0.0) or 0.0) - 0.05
                )
                if overlaps and source == cand_source:
                    continue
                kept_preview.append(seg)
            self._live_stt_preview_segments = kept_preview
        else:
            self._live_stt_preview_segments = existing_preview

        # ---------------------------------------------------------
        # 4. 화면 반영 및 위치 복원
        # ---------------------------------------------------------
        for line, seg in enumerate(current):
            seg["line"] = line
        self._active_seg_start = candidate_anchor_sec

        if hasattr(self, "text_edit"):
            self.text_edit.blockSignals(True)

        if hasattr(self, "_reload_segments_from_list"):
            self._reload_segments_from_list(current, preserve_view=True)
            self._update_timeline_with_confirmed_and_preview(current)
        else:
            self._rebuild_subtitle_memory_cache(current)
            if hasattr(self, "reload_segments"):
                self.reload_segments()

        if hasattr(self, "text_edit"):
            self.text_edit.blockSignals(False)
            self.text_edit.verticalScrollBar().setValue(saved_v_scroll)
        if hasattr(self, "timeline"):
            try:
                if hasattr(self.timeline, "set_active"):
                    self.timeline.set_active(candidate_anchor_sec)
                if hasattr(self.timeline, "set_playhead"):
                    try:
                        self.timeline.set_playhead(candidate_anchor_sec, preserve_center_lock=True)
                    except TypeError:
                        self.timeline.set_playhead(candidate_anchor_sec)
                if saved_h_scroll is not None:
                    self.timeline.scroll.horizontalScrollBar().setValue(int(saved_h_scroll))
            except Exception:
                pass
        if hasattr(self, "video_player") and hasattr(self.video_player, "seek"):
            try:
                local_sec = (
                    self._global_to_local_sec(candidate_anchor_sec)
                    if hasattr(self, "_global_to_local_sec")
                    else candidate_anchor_sec
                )
                self.video_player.seek(local_sec)
            except Exception:
                pass

    def _update_timeline_with_confirmed_and_preview(self, confirmed_segments: list[dict]):
        if not hasattr(self, "timeline"):
            return
        confirmed = [seg for seg in list(confirmed_segments or []) if not seg.get("is_gap")]
        preview = align_stt_preview_to_subtitle_segments(
            list(getattr(self, "_live_stt_preview_segments", []) or []),
            confirmed,
        )
        subtitle_preview = self._build_live_subtitle_preview_segments(preview, confirmed)
        combined = sorted(
            confirmed + subtitle_preview + preview,
            key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)),
        )
        total_dur = combined[-1]["end"] if combined else 0.0
        if hasattr(self, 'video_player') and self.video_player.total_time > 0.0:
            total_dur = max(total_dur, self.video_player.total_time)
        self.timeline.update_segments(combined, self._active_seg_start, total_dur)
        if getattr(self, "_queue_mode_fit_view", False):
            try:
                setattr(self.timeline, "_manual_zoom_since_fit", False)
                if hasattr(self.timeline, "schedule_fit_to_view"):
                    self.timeline.schedule_fit_to_view((0, 120, 260))
                elif hasattr(self.timeline, "fit_to_view"):
                    QTimer.singleShot(0, self.timeline.fit_to_view)
            except Exception:
                pass

    def _redraw_timeline_with_live_preview(self):
        if not hasattr(self, "timeline"):
            return
        try:
            confirmed = [seg for seg in self._get_current_segments() if not seg.get("is_gap")]
        except Exception:
            confirmed = list(getattr(self, "_cached_segs", []) or [])
        preview = align_stt_preview_to_subtitle_segments(
            list(getattr(self, "_live_stt_preview_segments", []) or []),
            confirmed,
        )
        subtitle_preview = self._build_live_subtitle_preview_segments(preview, confirmed)
        if not preview and not subtitle_preview:
            self._redraw_timeline()
            return
        combined = sorted(
            confirmed + subtitle_preview + preview,
            key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)),
        )
        total_dur = combined[-1]["end"] if combined else 0.0
        if hasattr(self, 'video_player') and self.video_player.total_time > 0.0:
            total_dur = max(total_dur, self.video_player.total_time)
        self.timeline.update_segments(combined, self._active_seg_start, total_dur)

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
        self._remove_live_editor_preview_overlapping(self._segment_queue)

        cont_thresh = float(self.settings.get("continuous_threshold", 2.0))
        push_rate = float(self.settings.get("gap_push_rate", 0.7))
        pull_rate = max(0.0, min(1.0, 1.0 - push_rate))
        single_ext = float(self.settings.get("single_subtitle_end", 0.2))
        is_initial = getattr(self, '_is_initial_load', False)
        final_gap_ready = bool(self._segment_queue) and all(
            bool(seg.get("_final_gap_settings_applied")) for seg in self._segment_queue
        )

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
                    cur.block().setUserData(SubtitleBlockData("00", self._frame_time(new_prev_end), is_gap=True))
                    cur.insertText("\n") # 다음 자막이 쓸 줄 확보
                    
            elif gap > cont_thresh:
                new_prev_end = prev_end_orig + single_ext
                self._segment_queue[0]['start'] = max(0.0, curr_start - single_ext)
                if self._segment_queue[0]['start'] > new_prev_end + 0.05:
                    if doc.lastBlock().text().strip(): cur.insertText("\n")
                    cur.insertText("\n")
                    cur.block().setUserData(SubtitleBlockData("00", self._frame_time(new_prev_end), is_gap=True))
                    cur.insertText("\n")

        # 💡 4. 내부 청크들 간의 간격 연산
        last_end = -1.0
        for i in range(len(self._segment_queue)):
            curr = self._segment_queue[i]
            
            if not is_initial and not final_gap_ready:
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
            elif curr['end'] <= curr['start']:
                curr['end'] = curr['start'] + 0.5
                    
            last_end = curr['end']

        if doc.lastBlock().text().strip(): cur.insertText("\n")
        added_end = self._segment_queue[-1]['end'] if self._segment_queue else 0.0
        focused_payload = None

        # 💡 [여기서부터 수정: 화자 분리 로직]
        spk1_id = self.settings.get("spk1_id", "00")
        spk2_id = self.settings.get("spk2_id", "01")

        for i in range(len(self._segment_queue)):
            seg = self._segment_queue[i]; text = str(seg.get("text", "") or "").replace("\u2028", "\n")
            spk_list = seg.get("speaker_list", [spk1_id])
            
            text = self._JUNK_TS_RE.sub('', text)
            text = self._JUNK_NO_BRACKET_3PART.sub('', text)
            text = self._JUNK_NO_BRACKET_3PART_END.sub('', text)
            text = self._JUNK_START_RE.sub('', text).strip()
            text = text.replace('\r', '')
            # ✅ HTML 태그 제거
            text = re.sub(r'<[^>]+>', '', text)

            parts = [re.sub(r'[ \t\f\v]+', ' ', p).strip() for p in text.split('\n')]
            parts = [p for p in parts if p]
            if not parts: continue
            
            start_sec = self._frame_time(max(0, seg.get("start", 0)))
            
            # 💡 첫 번째 줄 삽입
            current_spk = spk_list[0] if len(spk_list) > 0 else spk1_id
            stt_kwargs = {
                "stt_mode": bool(seg.get("stt_mode", False)),
                "stt_pending": bool(seg.get("stt_pending", False)),
                "original_text": str(seg.get("original_text", "") or ""),
                "dictated_text": str(seg.get("dictated_text", "") or ""),
                "stt_selected_source": str(seg.get("stt_selected_source", "") or ""),
                "stt_ensemble_llm_selected_source": str(seg.get("stt_ensemble_llm_selected_source", "") or ""),
                "stt_candidates": list(seg.get("stt_candidates") or []),
                "stt_ensemble_source": str(seg.get("stt_ensemble_source", "") or ""),
                "stt_ensemble_llm_selected_label": str(seg.get("stt_ensemble_llm_selected_label", "") or ""),
                "stt_ensemble_similarity": seg.get("stt_ensemble_similarity"),
                "stt_ensemble_needs_llm_review": bool(seg.get("stt_ensemble_needs_llm_review", False)),
                "stt_ensemble_inserted_from_stt2": bool(seg.get("stt_ensemble_inserted_from_stt2", False)),
                "stt_ensemble_word_rover": dict(seg.get("stt_ensemble_word_rover") or {}),
                "score": seg.get("score"),
                "stt_score": seg.get("stt_score"),
                "score_color": str(seg.get("score_color", "") or ""),
                "stt_score_color": str(seg.get("stt_score_color", "") or ""),
                "stt_score_label": str(seg.get("stt_score_label", "") or ""),
                "stt_score_flags": list(seg.get("stt_score_flags") or []),
                "stt_score_components": dict(seg.get("stt_score_components") or {}),
            }
            clip_idx = seg.get("_clip_idx")
            try:
                clip_idx = int(clip_idx) if clip_idx is not None else None
            except Exception:
                clip_idx = None
            clip_kwargs = {
                "clip_idx": clip_idx,
                "clip_file": str(seg.get("_clip_file", "") or ""),
            }
            quality_kwargs = self._quality_kwargs_from_segment(seg, signature=self._segment_quality_signature({
                "start": start_sec,
                "end": seg.get("end", start_sec),
                "text": parts[0],
                "speaker": current_spk,
            }))
            cur.insertText(parts[0])
            cur.block().setUserData(SubtitleBlockData(current_spk, start_sec, **stt_kwargs, **quality_kwargs, **clip_kwargs))
            focused_payload = {
                "line": cur.block().blockNumber(),
                "start": start_sec,
                "end": seg.get("end", start_sec),
                "text": parts[0],
            }
            
            # 💡 두 번째 줄부터의 처리 (- 기호 유무로 완벽 통제)
            for p_idx in range(1, len(parts)):
                line_text = parts[p_idx]
                
                if line_text.startswith('-'):
                    # 🚨 '-' 기호가 있으면: 진짜 엔터(\n)를 쳐서 블록을 나누고 화자를 교체합니다.
                    current_spk = spk2_id if current_spk == spk1_id else spk1_id
                    cur.insertText("\n" + line_text)
                    cur.block().setUserData(SubtitleBlockData(current_spk, start_sec, **stt_kwargs, **quality_kwargs, **clip_kwargs))
                else:
                    # 🚨 '-' 기호가 없으면: 화자를 유지하고 소프트 줄바꿈(\u2028)만 삽입하여 1개의 블록으로 묶습니다.
                    cur.insertText("\u2028" + line_text)
            
            if i + 1 < len(self._segment_queue):
                nxt = self._segment_queue[i+1]
                if seg['end'] < nxt['start'] - 0.05:
                    gap_start = self._frame_time(seg['end'])
                    cur.insertText("\n") 
                    cur.block().setUserData(SubtitleBlockData("00", gap_start, is_gap=True))
                    # 💡 [핵심 해결] 무음 블록(빈 줄)을 확보했으니, 다음 자막이 쓸 새로운 줄을 한 번 더 만들어 줍니다!
                    cur.insertText("\n") 
                else:
                    cur.insertText("\n")
            else:
                gap_start = self._frame_time(seg['end'])
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
        if getattr(self, "_queue_mode_fit_view", False) and hasattr(self, "timeline"):
            try:
                setattr(self.timeline, "_manual_zoom_since_fit", False)
                if hasattr(self.timeline, "schedule_fit_to_view"):
                    self.timeline.schedule_fit_to_view((0, 120, 260))
                elif hasattr(self.timeline, "fit_to_view"):
                    QTimer.singleShot(0, self.timeline.fit_to_view)
            except Exception:
                pass
        self._refresh_video_subtitle_context()

        suppress_autoseek = bool(getattr(self, "_suspend_append_segments_autoseek", False))

        if is_initial:
            self._is_initial_load = False
            if hasattr(self, 'timeline'):
                self.timeline.set_playhead(0.0); self.timeline.center_to_sec(0.0, smooth=True)
            if hasattr(self, 'video_player'):
                self.video_player.seek(0.0)
        elif added_end > 0.0 and not suppress_autoseek:
            if hasattr(self, 'timeline'):
                self.timeline.set_playhead(added_end); self.timeline.center_to_sec(added_end, smooth=True)
            if hasattr(self, 'video_player'):
                self.video_player.seek(added_end)
            self._focus_editor_block_for_processing_segment(focused_payload, prefer_last=True)
            if self.settings.get("subtitle_quality_auto_check_after_generate") and hasattr(self, "_run_quality_review"):
                QTimer.singleShot(300, lambda: self._run_quality_review(auto_correct=bool(self.settings.get("subtitle_quality_auto_correct_enabled", False))))

    # ---------------------------------------------------------
    # Segment I/O
    # ---------------------------------------------------------

    def _get_current_segments(self) -> list[dict]:
        segments = []
        block = self.text_edit.document().begin()
        line_idx = 0
        
        while block.isValid():
            data = block.userData()
            text = block.text().replace("\u2028", "\n").strip()
            is_gap = getattr(data, 'is_gap', False) if data else False
            
            # ✅ [#1 핵심 수정] 갭 블록도 포함 — 무음구간이 End Time 계산에 반영됩니다
            include_empty_stt = bool(getattr(data, 'stt_pending', False) or getattr(data, 'stt_mode', False))
            if data is not None and getattr(data, "live_preview", False):
                block = block.next()
                line_idx += 1
                continue
            if data is not None and (text or is_gap or include_empty_stt):
                # ✅ 갭 블록은 절대 이전 세그먼트에 병합하지 않음 (갭↔자막 병합 방지)
                if (not is_gap
                    and segments
                    and not segments[-1].get("is_gap")
                    and abs(segments[-1]["start"] - data.start_sec) < 0.05):
                    segments[-1]["text"] += "\n" + text
                else:
                    item = {
                        "line": line_idx,
                        "start": data.start_sec,
                        "end": getattr(data, 'end_sec', None),
                        "text": text,
                        "is_gap": is_gap,
                        "spk": getattr(data, 'spk_id', 'SPEAKER_00'),
                        "stt_mode": bool(getattr(data, 'stt_mode', False)),
                        "stt_pending": bool(getattr(data, 'stt_pending', False)),
                        "original_text": getattr(data, 'original_text', '') or '',
                        "dictated_text": getattr(data, 'dictated_text', '') or '',
                        "stt_selected_source": getattr(data, 'stt_selected_source', '') or '',
                        "stt_ensemble_llm_selected_source": getattr(data, 'stt_ensemble_llm_selected_source', '') or '',
                    }
                    if getattr(data, "stt_candidates", None):
                        item["stt_candidates"] = list(getattr(data, "stt_candidates", []) or [])
                    for attr in (
                        "stt_ensemble_source",
                        "stt_ensemble_llm_selected_label",
                        "stt_ensemble_similarity",
                        "stt_ensemble_needs_llm_review",
                        "stt_ensemble_inserted_from_stt2",
                        "stt_ensemble_word_rover",
                        "score",
                        "stt_score",
                        "score_color",
                        "stt_score_color",
                        "stt_score_label",
                        "stt_score_flags",
                        "stt_score_components",
                    ):
                        value = getattr(data, attr, None)
                        if value not in (None, "", [], {}):
                            item[attr] = value
                    if getattr(data, "clip_idx", None) is not None:
                        item["_clip_idx"] = int(getattr(data, "clip_idx"))
                    if getattr(data, "clip_file", ""):
                        item["_clip_file"] = str(getattr(data, "clip_file", "") or "")
                    if getattr(data, "quality", None):
                        item["quality"] = dict(getattr(data, "quality", {}) or {})
                        item["quality_history"] = list(getattr(data, "quality_history", []) or [])
                        item["quality_candidates"] = list(getattr(data, "quality_candidates", []) or [])
                        signature = self._segment_quality_signature({
                            "start": item["start"],
                            "end": item.get("end") if item.get("end") is not None else item["start"],
                            "text": item["text"],
                            "speaker": item["spk"],
                        })
                        if getattr(data, "quality_signature", "") and signature != getattr(data, "quality_signature", ""):
                            item["quality_stale"] = True
                            quality = dict(item["quality"])
                            flags = list(quality.get("flags") or [])
                            if "quality_stale" not in flags:
                                flags.append("quality_stale")
                            quality["flags"] = flags
                            item["quality"] = quality
                    if getattr(data, "linked_silence_for_line", None) is not None:
                        try:
                            item["linked_silence_for_line"] = int(getattr(data, "linked_silence_for_line"))
                        except Exception:
                            pass
                    segments.append(item)
            
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
            if seg.get("quality") and not seg.get("quality_signature"):
                seg["quality_signature"] = self._segment_quality_signature(seg)
                
        return segments

    # ---------------------------------------------------------
    # Text Editor Event Handlers
    # ---------------------------------------------------------
    def _trigger_editor_popup(self, word, anchor, end_c, gpos):
        self.editor_popup.trigger(word, anchor, end_c, gpos)

    def _replace_text_in_all_subtitles(self, old_text: str, new_text: str, *, anchor=None, end_cursor=None) -> int:
        old_text = str(old_text or "")
        new_text = str(new_text or "")
        if not old_text or old_text == new_text or not hasattr(self, "text_edit"):
            return 0

        doc = self.text_edit.document()
        matches_by_line: dict[int, list[int]] = {}
        block = doc.begin()
        while block.isValid():
            ud = block.userData()
            if isinstance(ud, SubtitleBlockData) and not getattr(ud, "is_gap", False):
                text = block.text()
                positions = []
                start = text.find(old_text)
                while start >= 0:
                    positions.append(start)
                    start = text.find(old_text, start + len(old_text))
                if positions:
                    matches_by_line[int(block.blockNumber())] = positions
            block = block.next()

        replace_count = sum(len(v) for v in matches_by_line.values())
        if replace_count <= 0:
            return 0

        selected_line = -1
        selected_offset = 0
        cursor_ref = anchor if anchor is not None else end_cursor
        if cursor_ref is not None:
            try:
                anchor_block = doc.findBlock(cursor_ref.position())
                if anchor_block.isValid():
                    selected_line = int(anchor_block.blockNumber())
                    selected_offset = int(cursor_ref.position() - anchor_block.position())
            except Exception:
                selected_line = -1

        try:
            if hasattr(self, "_undo_mgr"):
                self._undo_mgr.push_immediate()
        except Exception:
            pass

        prev_inline = bool(getattr(self, "_inline_updating", False))
        self._inline_updating = True
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        try:
            for line_num in sorted(matches_by_line.keys(), reverse=True):
                block = doc.findBlockByNumber(line_num)
                if not block.isValid():
                    continue
                base_pos = int(block.position())
                for offset in sorted(matches_by_line[line_num], reverse=True):
                    cur.setPosition(base_pos + offset)
                    cur.setPosition(base_pos + offset + len(old_text), QTextCursor.MoveMode.KeepAnchor)
                    cur.insertText(new_text)
        finally:
            cur.endEditBlock()
            self._inline_updating = prev_inline

        if selected_line >= 0:
            try:
                selected_block = doc.findBlockByNumber(selected_line)
                if selected_block.isValid():
                    before_selected = sum(1 for offset in matches_by_line.get(selected_line, []) if offset < selected_offset)
                    adjusted_offset = selected_offset + before_selected * (len(new_text) - len(old_text))
                    cur = QTextCursor(selected_block)
                    cur.setPosition(selected_block.position() + max(0, adjusted_offset) + len(new_text))
                    self.text_edit.setTextCursor(cur)
            except Exception:
                pass

        hl = getattr(self, "_highlighter", None)
        if hl and hasattr(hl, "mark_edited"):
            for line_num in matches_by_line:
                hl.mark_edited(line_num)
        if hasattr(self.text_edit, "update_margins"):
            self.text_edit.update_margins()
        if hasattr(self.text_edit, "timestampArea"):
            self.text_edit.timestampArea.update()

        try:
            self._rebuild_subtitle_memory_cache()
        except Exception:
            pass
        if hasattr(self, "_mark_dirty"):
            self._mark_dirty()
        if hasattr(self, "_schedule_timeline"):
            self._schedule_timeline()
        if hasattr(self, "_refresh_video_subtitle_context"):
            self._refresh_video_subtitle_context()
        return replace_count

    def _on_selection_changed(self):
        if hasattr(self, "_timeline_lock_edit_enabled") and self._timeline_lock_edit_enabled():
            cur = self.text_edit.textCursor()
            if cur.hasSelection():
                cur.clearSelection()
                self.text_edit.setTextCursor(cur)
            return
        if self.text_edit.textCursor().hasSelection():
            self._on_cursor_moved()
        elif self.editor_popup.is_visible():
            self.editor_popup.close_popup()

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
        if bool(getattr(self, "_timeline_drag_in_progress", False)):
            return
        if hasattr(self, "_timeline_lock_edit_enabled") and self._timeline_lock_edit_enabled():
            return
        line_num = self.text_edit.textCursor().blockNumber()
        cache = getattr(self, "_subtitle_memory_cache", None)
        if not isinstance(cache, dict):
            cached = getattr(self, "_cached_segs", None)
            cache = build_segment_lookup(cached) if cached is not None else self._rebuild_subtitle_memory_cache()
            self._subtitle_memory_cache = cache
        seg = find_segment_for_line_lookup(cache, line_num)
        if not seg:
            return
        if self._active_seg_start != seg["start"]:
            if hasattr(self, 'video_player'): self.video_player.pause_video()
            self._active_seg_start = seg["start"]
            self.timeline.set_active(seg["start"])
            self.timeline.set_playhead(seg["start"])
            self.timeline.center_to_sec((seg["start"] + seg["end"]) / 2, smooth=True)
            self._highlighter.set_current_line(line_num)
            tip = self._quality_tooltip(seg)
            if tip:
                self.text_edit.setToolTip(tip)
            else:
                self.text_edit.setToolTip("")
            if hasattr(self, 'video_player'): self.video_player.seek(seg["start"])

    def _on_esc_pressed(self):
        if hasattr(self.timeline, 'canvas'): self.timeline.canvas.update()

    # ---------------------------------------------------------
    # Timeline Schedule
    # ---------------------------------------------------------
    def _redraw_timeline(self):
        segs = self._get_current_segments()
        self._rebuild_subtitle_memory_cache(segs)
        timeline_segs = segs
        preview = list(getattr(self, "_live_stt_preview_segments", []) or [])
        if preview:
            confirmed = [seg for seg in segs if not seg.get("is_gap")]
            subtitle_preview = self._build_live_subtitle_preview_segments(preview, confirmed)
            timeline_segs = sorted(
                confirmed + subtitle_preview + preview,
                key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)),
            )
        if hasattr(self, "_highlighter"):
            quality_map = {
                int(seg.get("line", -1)): dict(seg.get("quality") or {})
                for seg in segs
                if seg.get("quality") and int(seg.get("line", -1)) >= 0
            }
            self._highlighter.set_quality_map(quality_map)
        total_dur = timeline_segs[-1]["end"] if timeline_segs else 0.0
        if hasattr(self, 'video_player') and self.video_player.total_time > 0.0:
            total_dur = max(total_dur, self.video_player.total_time)
        self.timeline.update_segments(timeline_segs, self._active_seg_start, total_dur)
        if hasattr(self, 'video_player') and hasattr(self.video_player, "set_context_segments"):
            _canvas = getattr(getattr(self, "timeline", None), "canvas", None)
            _mc_boxes = list(getattr(_canvas, '_multiclip_boxes', []) or []) if _canvas is not None else []
            if _mc_boxes and hasattr(self, '_resolve_active_context'):
                try:
                    _gsec = float(getattr(_canvas, 'playhead_sec', 0.0) or 0.0)
                    _ctx = self._resolve_active_context(global_sec=_gsec)
                    self.video_player.set_context_segments(list(_ctx.get('local_segments', []) or []))
                except Exception:
                    self.video_player.set_context_segments(self._subtitle_memory_visible_segments())
            else:
                self.video_player.set_context_segments(self._subtitle_memory_visible_segments())

        # ✅ 최초 로드 시 화면에 맞춤
        if getattr(self, '_needs_fit_view', False) and segs and hasattr(self.timeline, "fit_to_view"):
            auto_fit = getattr(self.timeline, "auto_fit_to_view", None)
            if callable(auto_fit):
                auto_fit()
            else:
                self.timeline.fit_to_view()
            self._needs_fit_view = False

    def _refresh_video_subtitle_context(self):
        if not hasattr(self, 'video_player'):
            return
        segs = self._video_subtitle_context_for_player()
        try:
            if hasattr(self.video_player, 'refresh_subtitle_context'):
                self.video_player.refresh_subtitle_context(segs)
            else:
                self.video_player.set_context_segments(segs)
        except Exception:
            pass

    def _video_subtitle_context_for_player(self):
        cache = getattr(self, "_subtitle_memory_cache", None)
        if not isinstance(cache, dict):
            cached = getattr(self, "_cached_segs", None)
            cache = build_segment_lookup(cached) if cached is not None else self._rebuild_subtitle_memory_cache()
            self._subtitle_memory_cache = cache
        try:
            _mc_boxes = list(getattr(self.timeline.canvas, '_multiclip_boxes', []) or []) if hasattr(self, 'timeline') else []
            if _mc_boxes and hasattr(self, '_resolve_active_context'):
                _gsec = float(getattr(self.timeline.canvas, 'playhead_sec', 0.0) or 0.0)
                ctx = self._resolve_active_context(global_sec=_gsec)
                if ctx:
                    return list(ctx.get('local_segments', []) or [])
        except Exception:
            pass
        return list(cache.get("visible_segments") or [])

    def _schedule_timeline(self):
        if getattr(self, '_inline_updating', False): return
        if not self._timeline_timer.isActive(): self._timeline_timer.start(150)  # [크PD] 300→150ms 실시간성 개선

    def _on_drag_started(self): 
        # 💡 드래그를 시작하기 직전의 전체 뷰 스냅샷 저장!
        self._timeline_drag_in_progress = True
        self._undo_mgr.push_immediate()
        
        self._drag_cursor = QTextCursor(self.text_edit.document())
        self._drag_cursor.beginEditBlock()
        
    def _on_drag_finished(self): 
        if hasattr(self, '_drag_cursor') and self._drag_cursor:
            self._drag_cursor.endEditBlock()
            self._drag_cursor = None
        self._timeline_drag_in_progress = False
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
            from ui.editor.subtitle_text_edit import SubtitleBlockData
            
            for i, seg in enumerate(new_segments):
                if not cur.atBlockStart(): cur.insertBlock()
                text = seg.get("text", "").replace("\r", "")
                parts = [p.strip() for p in text.split('\n') if p.strip()]
                if not parts: continue
                
                start_sec = self._frame_time(seg.get("start", 0))
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
                gap_start = self._frame_time(seg['end'])
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
            from core.runtime.logger import get_logger
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

        start_sec = self._frame_time(ud.start_sec)
        spk_id    = ud.spk_id
        split_sec = self._frame_time(split_sec)

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
            SubtitleBlockData(spk_id, start_sec, is_gap=False)
        )

        # 새 블록 삽입 → right 파트
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cur.insertBlock()
        cur.insertText(right_doc)
        cur.block().setUserData(
            SubtitleBlockData(spk_id, split_sec, is_gap=False)
        )

        cur.endEditBlock()

        # 💡 [타임라인 튕김 완벽 방지] 커서 이동 시 화면이 중앙으로 강제 점프하는 것을 잠급니다.
        self._sync_lock = True  # 자동 센터링 방지 잠금
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        self.text_edit.setTextCursor(cur)
        
        self._active_seg_start = split_sec
        if hasattr(self, 'timeline'):
            self.timeline.set_active(self._active_seg_start)
            # 🎯 자막의 중간이 아니라, 대표님이 우클릭한 그 시점(split_sec)을 중앙으로!
            self.timeline.center_to_sec(split_sec, smooth=True)
        self._sync_lock = False

        self._mark_dirty()
        self._finalize_edit()
