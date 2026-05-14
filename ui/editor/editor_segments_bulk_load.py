"""Bulk editor document loading helpers.

This mixin keeps the heavy project/SRT restore path out of
``editor_segments.py`` while preserving the existing Swift preparation route.
"""

from __future__ import annotations

import hashlib
import json

from PyQt6.QtGui import QTextCursor

from ui.editor.editor_segments_bulk_prepare import EditorSegmentsBulkPrepareMixin
from ui.editor.subtitle_text_edit import subtitle_block_data_to_meta


class EditorSegmentsBulkLoadMixin(EditorSegmentsBulkPrepareMixin):
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

    def _segment_document_quality_kwargs(
        self,
        seg: dict,
        *,
        start_sec: float,
        end_sec: float,
        text: str,
        speaker: str,
    ) -> dict:
        return self._quality_kwargs_from_segment(
            seg,
            signature=self._segment_quality_signature(
                {
                    "start": start_sec,
                    "end": end_sec,
                    "text": text,
                    "speaker": speaker,
                }
            ),
        )

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
        block_texts, block_meta, display_rows = self._bulk_collect_document_payloads(rows)
        context = self._bulk_load_document_context(text_edit, doc)
        load_state = self._bulk_begin_document_replace(text_edit, doc, context=context)
        try:
            self._bulk_write_document_payload(text_edit, doc, block_texts=block_texts, block_meta=block_meta)
        finally:
            self._bulk_end_document_replace(text_edit, doc, context=context, load_state=load_state)
        self._bulk_refresh_loaded_document(text_edit, context=context)
        self._bulk_finalize_loaded_segments(preserve_view=preserve_view)
        return display_rows

    def _bulk_load_document_context(self, text_edit, doc) -> dict:
        highlighter = getattr(self, "_highlighter", None)
        timestamp_area = getattr(text_edit, "timestampArea", None)
        return {
            "highlighter": highlighter,
            "timestamp_area": timestamp_area,
        }

    def _bulk_begin_document_replace(self, text_edit, doc, *, context: dict) -> dict:
        highlighter = context.get("highlighter")
        timestamp_area = context.get("timestamp_area")
        state = {
            "prev_text_signals": False,
            "prev_doc_signals": False,
            "prev_undo": True,
            "prev_updates": True,
            "prev_timestamp_updates": True,
            "detached_highlighter": False,
        }
        setattr(text_edit, "_bulk_segment_load_active", True)
        if hasattr(text_edit, "updatesEnabled") and hasattr(text_edit, "setUpdatesEnabled"):
            state["prev_updates"] = bool(text_edit.updatesEnabled())
            text_edit.setUpdatesEnabled(False)
        if timestamp_area is not None and hasattr(timestamp_area, "updatesEnabled") and hasattr(timestamp_area, "setUpdatesEnabled"):
            state["prev_timestamp_updates"] = bool(timestamp_area.updatesEnabled())
            timestamp_area.setUpdatesEnabled(False)
        if highlighter is not None and hasattr(highlighter, "setDocument"):
            try:
                if highlighter.document() is doc:
                    highlighter.setDocument(None)
                    state["detached_highlighter"] = True
            except Exception:
                state["detached_highlighter"] = False
        state["prev_text_signals"] = bool(text_edit.blockSignals(True))
        state["prev_doc_signals"] = bool(doc.blockSignals(True))
        if hasattr(text_edit, "isUndoRedoEnabled") and hasattr(text_edit, "setUndoRedoEnabled"):
            state["prev_undo"] = bool(text_edit.isUndoRedoEnabled())
            text_edit.setUndoRedoEnabled(False)
        return state

    def _bulk_write_document_payload(self, text_edit, doc, *, block_texts: list[str], block_meta: list) -> None:
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

    def _bulk_end_document_replace(self, text_edit, doc, *, context: dict, load_state: dict) -> None:
        highlighter = context.get("highlighter")
        timestamp_area = context.get("timestamp_area")
        try:
            if hasattr(text_edit, "setUndoRedoEnabled"):
                text_edit.setUndoRedoEnabled(load_state.get("prev_undo", True))
        except Exception:
            pass
        try:
            doc.blockSignals(bool(load_state.get("prev_doc_signals", False)))
        except Exception:
            pass
        try:
            text_edit.blockSignals(bool(load_state.get("prev_text_signals", False)))
        except Exception:
            pass
        try:
            if bool(load_state.get("detached_highlighter", False)) and highlighter is not None and hasattr(highlighter, "setDocument"):
                highlighter.setDocument(doc)
        except Exception:
            pass
        try:
            if timestamp_area is not None and hasattr(timestamp_area, "setUpdatesEnabled"):
                timestamp_area.setUpdatesEnabled(bool(load_state.get("prev_timestamp_updates", True)))
        except Exception:
            pass
        try:
            if hasattr(text_edit, "setUpdatesEnabled"):
                text_edit.setUpdatesEnabled(bool(load_state.get("prev_updates", True)))
        except Exception:
            pass
        try:
            setattr(text_edit, "_bulk_segment_load_active", False)
        except Exception:
            pass

    def _bulk_refresh_loaded_document(self, text_edit, *, context: dict) -> None:
        timestamp_area = context.get("timestamp_area")
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

    def _bulk_finalize_loaded_segments(self, *, preserve_view: bool) -> None:
        self._segment_queue.clear()
        self._is_initial_load = False
        if preserve_view:
            return
        try:
            if hasattr(self, "timeline"):
                self.timeline.set_playhead(0.0)
                self.timeline.center_to_sec(0.0, smooth=True)
            if hasattr(self, "video_player"):
                self.video_player.seek(0.0)
        except Exception:
            pass
