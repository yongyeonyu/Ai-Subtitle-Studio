"""Bulk editor document loading helpers.

This mixin keeps the heavy project/SRT restore path out of
``editor_segments.py`` while preserving the existing Swift preparation route.
"""

from __future__ import annotations

import hashlib
import json
import re

from PyQt6.QtGui import QTextCursor

from core.native_swift_timeline import prepare_editor_segments_for_load_via_swift
from ui.editor.subtitle_text_edit import SubtitleBlockData, subtitle_block_data_to_meta


class EditorSegmentsBulkLoadMixin:
    """Fast QTextDocument rewrite path for already-final segment rows."""

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

    def _bulk_load_segments_to_document(self, segments: list[dict], *, preserve_view: bool = False) -> list[dict] | None:
        """Load already-final subtitle/project rows with one QTextDocument rewrite.

        Live generation still uses the queue path because it needs gap push/pull
        behavior. Project/SRT restore is different: rows are already timed, so a
        single document rewrite avoids thousands of per-row insert/layout/undo
        updates on long files.
        """
        text_edit = getattr(self, "text_edit", None)
        if text_edit is None or not hasattr(text_edit, "setPlainText"):
            return None
        doc = text_edit.document() if hasattr(text_edit, "document") else None
        if doc is None:
            return None

        rows = list(segments or [])
        native_prepared_rows = None
        try:
            native_prepared_rows = prepare_editor_segments_for_load_via_swift(
                segments=rows,
                fps=float(getattr(self, "video_fps", 30.0) or 30.0),
            )
        except Exception:
            native_prepared_rows = None
        native_prepared_by_source: dict[int, dict] = {}
        if isinstance(native_prepared_rows, list):
            for item in native_prepared_rows:
                if not isinstance(item, dict):
                    continue
                try:
                    source_index = int(item.get("sourceIndex", -1))
                except Exception:
                    continue
                if source_index >= 0:
                    native_prepared_by_source[source_index] = item
        block_texts: list[str] = []
        block_meta: list[SubtitleBlockData] = []
        display_rows: list[dict] = []
        spk1_id = self.settings.get("spk1_id", "00") if hasattr(self, "settings") else "00"
        spk2_id = self.settings.get("spk2_id", "01") if hasattr(self, "settings") else "01"
        no_match = re.compile(r"(?!)")
        junk_ts = getattr(self, "_JUNK_TS_RE", no_match)
        junk_three = getattr(self, "_JUNK_NO_BRACKET_3PART", no_match)
        junk_three_end = getattr(self, "_JUNK_NO_BRACKET_3PART_END", no_match)
        junk_start = getattr(self, "_JUNK_START_RE", no_match)

        for idx, raw_seg in enumerate(rows):
            if not isinstance(raw_seg, dict):
                continue
            seg = dict(raw_seg)
            native_prepared = native_prepared_by_source.get(idx)
            if isinstance(native_prepared, dict):
                try:
                    start_sec = float(native_prepared.get("start", 0.0) or 0.0)
                except Exception:
                    start_sec = 0.0
                try:
                    end_sec = float(native_prepared.get("end", start_sec) or start_sec)
                except Exception:
                    end_sec = start_sec
                is_gap = bool(native_prepared.get("isGap", seg.get("is_gap", False)))
                parts = [
                    str(part or "")
                    for part in list(native_prepared.get("parts") or [])
                    if str(part or "")
                ]
                normalized_text = str(native_prepared.get("text", "") or "")
            else:
                try:
                    start_sec = self._frame_time(max(0.0, float(seg.get("start", 0.0) or 0.0)))
                except Exception:
                    start_sec = 0.0
                try:
                    end_sec = self._frame_time(max(start_sec, float(seg.get("end", start_sec) or start_sec)))
                except Exception:
                    end_sec = start_sec
                if end_sec <= start_sec:
                    end_sec = self._frame_time(start_sec + 0.5)
                is_gap = bool(seg.get("is_gap"))
                text = str(seg.get("text", "") or "").replace("\u2028", "\n")
                text = junk_ts.sub("", text)
                text = junk_three.sub("", text)
                text = junk_three_end.sub("", text)
                text = junk_start.sub("", text).strip()
                text = re.sub(r"<[^>]+>", "", text.replace("\r", ""))
                parts = [re.sub(r"[ \t\f\v]+", " ", part).strip() for part in text.split("\n")]
                parts = [part for part in parts if part]
                normalized_text = "\n".join(parts)

            if is_gap:
                first_line = len(block_texts)
                block_texts.append("")
                block_meta.append(SubtitleBlockData("00", start_sec, is_gap=True, end_sec=end_sec))
                display = dict(seg)
                display["line"] = first_line
                display["start"] = start_sec
                display["end"] = end_sec
                display["text"] = str(seg.get("text", "") or "")
                display["is_gap"] = True
                display_rows.append(display)
                continue

            if not parts:
                continue

            spk_list = list(seg.get("speaker_list", []) or [])
            current_spk = str((spk_list[0] if spk_list else seg.get("speaker", seg.get("spk", spk1_id))) or spk1_id)
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
            quality_kwargs = self._quality_kwargs_from_segment(
                seg,
                signature=self._segment_quality_signature(
                    {
                        "start": start_sec,
                        "end": end_sec,
                        "text": parts[0],
                        "speaker": current_spk,
                    }
                ),
            )

            first_line = len(block_texts)
            block_texts.append(parts[0])
            block_meta.append(SubtitleBlockData(current_spk, start_sec, end_sec=end_sec, **stt_kwargs, **quality_kwargs, **clip_kwargs))
            for part in parts[1:]:
                if part.startswith("-"):
                    current_spk = spk2_id if current_spk == spk1_id else spk1_id
                    block_texts.append(part)
                    block_meta.append(SubtitleBlockData(current_spk, start_sec, end_sec=end_sec, **stt_kwargs, **quality_kwargs, **clip_kwargs))
                else:
                    block_texts[-1] = block_texts[-1] + "\u2028" + part

            display = dict(seg)
            display["line"] = first_line
            display["start"] = start_sec
            display["end"] = end_sec
            display["text"] = normalized_text
            display["speaker"] = str(seg.get("speaker", seg.get("spk", current_spk)) or current_spk)
            if clip_idx is not None:
                display["_clip_idx"] = clip_idx
            if clip_kwargs["clip_file"]:
                display["_clip_file"] = clip_kwargs["clip_file"]
            display_rows.append(display)

        prev_text_signals = False
        prev_doc_signals = False
        prev_undo = True
        prev_updates = True
        prev_timestamp_updates = True
        highlighter = getattr(self, "_highlighter", None)
        detached_highlighter = False
        timestamp_area = getattr(text_edit, "timestampArea", None)
        try:
            setattr(text_edit, "_bulk_segment_load_active", True)
            if hasattr(text_edit, "updatesEnabled") and hasattr(text_edit, "setUpdatesEnabled"):
                prev_updates = bool(text_edit.updatesEnabled())
                text_edit.setUpdatesEnabled(False)
            if timestamp_area is not None and hasattr(timestamp_area, "updatesEnabled") and hasattr(timestamp_area, "setUpdatesEnabled"):
                prev_timestamp_updates = bool(timestamp_area.updatesEnabled())
                timestamp_area.setUpdatesEnabled(False)
            if highlighter is not None and hasattr(highlighter, "setDocument"):
                try:
                    if highlighter.document() is doc:
                        highlighter.setDocument(None)
                        detached_highlighter = True
                except Exception:
                    detached_highlighter = False
            prev_text_signals = bool(text_edit.blockSignals(True))
            prev_doc_signals = bool(doc.blockSignals(True))
            if hasattr(text_edit, "isUndoRedoEnabled") and hasattr(text_edit, "setUndoRedoEnabled"):
                prev_undo = bool(text_edit.isUndoRedoEnabled())
                text_edit.setUndoRedoEnabled(False)
            text_edit.setPlainText("\n".join(block_texts))
            block = doc.begin()
            snapshot = {}
            for line_idx, meta in enumerate(block_meta):
                if not block.isValid():
                    break
                block.setUserData(meta)
                snapshot[int(line_idx)] = subtitle_block_data_to_meta(meta)
                block = block.next()
            if snapshot:
                setattr(text_edit, "_timestamp_block_meta_snapshot", snapshot)
            cursor = QTextCursor(doc)
            cursor.movePosition(QTextCursor.MoveOperation.End)
            text_edit.setTextCursor(cursor)
        finally:
            try:
                if hasattr(text_edit, "setUndoRedoEnabled"):
                    text_edit.setUndoRedoEnabled(prev_undo)
            except Exception:
                pass
            try:
                doc.blockSignals(prev_doc_signals)
            except Exception:
                pass
            try:
                text_edit.blockSignals(prev_text_signals)
            except Exception:
                pass
            try:
                if detached_highlighter and highlighter is not None and hasattr(highlighter, "setDocument"):
                    highlighter.setDocument(doc)
            except Exception:
                pass
            try:
                if timestamp_area is not None and hasattr(timestamp_area, "setUpdatesEnabled"):
                    timestamp_area.setUpdatesEnabled(prev_timestamp_updates)
            except Exception:
                pass
            try:
                if hasattr(text_edit, "setUpdatesEnabled"):
                    text_edit.setUpdatesEnabled(prev_updates)
            except Exception:
                pass
            try:
                setattr(text_edit, "_bulk_segment_load_active", False)
            except Exception:
                pass

        try:
            if hasattr(text_edit, "update_margins"):
                text_edit.update_margins()
            refresher = getattr(text_edit, "refresh_timestamp_layer", None)
            if callable(refresher):
                refresher()
            elif timestamp_area is not None and hasattr(timestamp_area, "update"):
                timestamp_area.update()
            quick_sync = getattr(text_edit, "_schedule_quick_layer_sync", None)
            if callable(quick_sync):
                quick_sync()
        except Exception:
            pass
        self._segment_queue.clear()
        self._is_initial_load = False
        if not preserve_view:
            try:
                if hasattr(self, "timeline"):
                    self.timeline.set_playhead(0.0)
                    self.timeline.center_to_sec(0.0, smooth=True)
                if hasattr(self, "video_player"):
                    self.video_player.seek(0.0)
            except Exception:
                pass
        return display_rows
