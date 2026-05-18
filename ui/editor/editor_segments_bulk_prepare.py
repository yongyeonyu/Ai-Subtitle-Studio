"""Prepared row -> QTextDocument payload helpers for bulk editor loading."""

from __future__ import annotations

import re

from core.native_swift_timeline import prepare_editor_segments_for_load_via_swift
from ui.editor.editor_helpers import should_split_multiline_part_into_block
from ui.editor.subtitle_text_edit import SubtitleBlockData


class EditorSegmentsBulkPrepareMixin:
    def _bulk_native_prepared_by_source(self, rows: list[dict]) -> dict[int, dict]:
        native_prepared_rows = None
        try:
            native_prepared_rows = prepare_editor_segments_for_load_via_swift(
                segments=list(rows or []),
                fps=float(getattr(self, "video_fps", 30.0) or 30.0),
            )
        except Exception:
            native_prepared_rows = None

        prepared_by_source: dict[int, dict] = {}
        if isinstance(native_prepared_rows, list):
            for item in native_prepared_rows:
                if not isinstance(item, dict):
                    continue
                try:
                    source_index = int(item.get("sourceIndex", -1))
                except Exception:
                    continue
                if source_index >= 0:
                    prepared_by_source[source_index] = item
        return prepared_by_source

    def _bulk_normalize_segment_text_parts(
        self,
        seg: dict,
        *,
        native_prepared: dict | None = None,
    ) -> tuple[float, float, bool, list[str], str]:
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
            return start_sec, end_sec, is_gap, parts, normalized_text

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
        text = getattr(self, "_JUNK_TS_RE", re.compile(r"(?!)")).sub("", text)
        text = getattr(self, "_JUNK_NO_BRACKET_3PART", re.compile(r"(?!)")).sub("", text)
        text = getattr(self, "_JUNK_NO_BRACKET_3PART_END", re.compile(r"(?!)")).sub("", text)
        text = getattr(self, "_JUNK_START_RE", re.compile(r"(?!)")).sub("", text).strip()
        text = re.sub(r"<[^>]+>", "", text.replace("\r", ""))
        parts = [re.sub(r"[ \t\f\v]+", " ", part).strip() for part in text.split("\n")]
        parts = [part for part in parts if part]
        normalized_text = "\n".join(parts)
        return start_sec, end_sec, is_gap, parts, normalized_text

    def _bulk_segment_stt_kwargs(self, seg: dict) -> dict:
        return {
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

    def _bulk_segment_clip_kwargs(self, seg: dict) -> tuple[int | None, dict]:
        clip_idx = seg.get("_clip_idx")
        try:
            clip_idx = int(clip_idx) if clip_idx is not None else None
        except Exception:
            clip_idx = None
        return clip_idx, {
            "clip_idx": clip_idx,
            "clip_file": str(seg.get("_clip_file", "") or ""),
        }

    def _bulk_append_gap_row_payload(
        self,
        seg: dict,
        *,
        start_sec: float,
        end_sec: float,
        block_texts: list[str],
        block_meta: list[SubtitleBlockData],
        display_rows: list[dict],
    ) -> None:
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

    def _bulk_append_text_row_payload(
        self,
        seg: dict,
        *,
        start_sec: float,
        end_sec: float,
        parts: list[str],
        normalized_text: str,
        block_texts: list[str],
        block_meta: list[SubtitleBlockData],
        display_rows: list[dict],
        spk1_id: str,
        spk2_id: str,
    ) -> None:
        spk_list = list(seg.get("speaker_list", []) or [])
        current_spk = str((spk_list[0] if spk_list else seg.get("speaker", seg.get("spk", spk1_id))) or spk1_id)
        stt_kwargs = self._bulk_segment_stt_kwargs(seg)
        clip_idx, clip_kwargs = self._bulk_segment_clip_kwargs(seg)
        quality_kwargs = self._segment_document_quality_kwargs(
            seg,
            start_sec=start_sec,
            end_sec=end_sec,
            text=parts[0],
            speaker=current_spk,
        )

        first_line = len(block_texts)
        block_texts.append(parts[0])
        block_meta.append(
            SubtitleBlockData(current_spk, start_sec, end_sec=end_sec, **stt_kwargs, **quality_kwargs, **clip_kwargs)
        )
        for part in parts[1:]:
            if should_split_multiline_part_into_block(seg, part):
                current_spk = spk2_id if current_spk == spk1_id else spk1_id
                block_texts.append(part)
                block_meta.append(
                    SubtitleBlockData(current_spk, start_sec, end_sec=end_sec, **stt_kwargs, **quality_kwargs, **clip_kwargs)
                )
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

    def _bulk_collect_document_payloads(self, rows: list[dict]) -> tuple[list[str], list[SubtitleBlockData], list[dict]]:
        prepared_by_source = self._bulk_native_prepared_by_source(rows)
        block_texts: list[str] = []
        block_meta: list[SubtitleBlockData] = []
        display_rows: list[dict] = []
        spk1_id = self.settings.get("spk1_id", "00") if hasattr(self, "settings") else "00"
        spk2_id = self.settings.get("spk2_id", "01") if hasattr(self, "settings") else "01"

        for idx, raw_seg in enumerate(rows):
            if not isinstance(raw_seg, dict):
                continue
            seg = dict(raw_seg)
            start_sec, end_sec, is_gap, parts, normalized_text = self._bulk_normalize_segment_text_parts(
                seg,
                native_prepared=prepared_by_source.get(idx),
            )
            if is_gap:
                self._bulk_append_gap_row_payload(
                    seg,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    block_texts=block_texts,
                    block_meta=block_meta,
                    display_rows=display_rows,
                )
                continue
            if not parts:
                continue
            self._bulk_append_text_row_payload(
                seg,
                start_sec=start_sec,
                end_sec=end_sec,
                parts=parts,
                normalized_text=normalized_text,
                block_texts=block_texts,
                block_meta=block_meta,
                display_rows=display_rows,
                spk1_id=spk1_id,
                spk2_id=spk2_id,
            )
        return block_texts, block_meta, display_rows
