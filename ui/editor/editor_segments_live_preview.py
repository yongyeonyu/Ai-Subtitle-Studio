"""Live preview and generation-seam helpers for editor subtitle segments."""

from __future__ import annotations

import re

from PyQt6.QtGui import QTextCursor

from core.native_swift_timeline import (
    build_live_subtitle_preview_via_swift,
    plan_stt_candidate_selection_via_swift,
)
from core.project.project_srt import strip_whisper_control_tokens
from core.runtime.logger import get_logger
from ui.editor.subtitle_text_edit import SubtitleBlockData


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
                start = self._frame_time(max(0.0, float(seg.get("start", 0.0) or 0.0)))
                end = self._frame_time(max(start + 0.05, float(seg.get("end", start + 0.5) or start + 0.5)))
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
        for line, draft in enumerate(sorted(drafts, key=lambda item: (
            float(item.get("start", 0.0) or 0.0),
            float(item.get("end", 0.0) or 0.0),
        ))):
            draft["line"] = -2000 - line
        return sorted(drafts, key=lambda item: (
            float(item.get("start", 0.0) or 0.0),
            float(item.get("end", 0.0) or 0.0),
        ))

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
            for line, draft in enumerate(sorted(filtered_drafts, key=lambda seg: (
                float(seg.get("start", 0.0) or 0.0),
                float(seg.get("end", 0.0) or 0.0),
            ))):
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
