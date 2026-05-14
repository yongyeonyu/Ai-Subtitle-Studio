"""Current editor document -> segment serialization helpers."""

from __future__ import annotations

from ui.editor.editor_helpers import build_segment_lookup
from ui.editor.subtitle_text_edit import SubtitleBlockData


class EditorSegmentsCurrentStateMixin:
    def _cached_current_segments_if_fresh(self) -> list[dict] | None:
        cached = getattr(self, "_cached_segs", None)
        if not (bool(getattr(self, "_segment_cache_valid", False)) and isinstance(cached, list)):
            return None
        try:
            block_count = int(self.text_edit.document().blockCount())
        except Exception:
            block_count = int(getattr(self, "_last_segment_cache_block_count", 0) or 0)
        cached_block_count = int(getattr(self, "_last_segment_cache_block_count", block_count) or block_count)
        if block_count != cached_block_count:
            return None
        clamped_cached = self._clamp_segments_to_clip_duration(cached)
        if clamped_cached != cached:
            self._cache_current_segments(clamped_cached)
        return [dict(seg) for seg in clamped_cached]

    def _segment_item_from_block(self, data, text: str, line_idx: int) -> dict | None:
        if data is None:
            return None
        is_gap = bool(getattr(data, "is_gap", False))
        include_empty_stt = bool(getattr(data, "stt_pending", False) or getattr(data, "stt_mode", False))
        if getattr(data, "live_preview", False):
            return None
        if not (text or is_gap or include_empty_stt):
            return None

        item = {
            "line": int(line_idx),
            "start": data.start_sec,
            "end": getattr(data, "end_sec", None),
            "text": text,
            "is_gap": is_gap,
            "spk": getattr(data, "spk_id", "SPEAKER_00"),
            "stt_mode": bool(getattr(data, "stt_mode", False)),
            "stt_pending": bool(getattr(data, "stt_pending", False)),
            "original_text": getattr(data, "original_text", "") or "",
            "dictated_text": getattr(data, "dictated_text", "") or "",
            "stt_selected_source": getattr(data, "stt_selected_source", "") or "",
            "stt_ensemble_llm_selected_source": getattr(data, "stt_ensemble_llm_selected_source", "") or "",
        }
        for attr in (
            "stt_segment_id",
            "stt_mode_status",
            "vad_confidence",
            "vad_confidence_label",
            "vad_decision",
            "vad_sources",
            "start_frame",
            "end_frame",
            "timeline_start_frame",
            "timeline_end_frame",
            "frame_rate",
            "timeline_frame_rate",
            "frame_range",
            "playback",
        ):
            value = getattr(data, attr, None)
            if value not in (None, "", [], {}):
                item[attr] = value
        if item.get("stt_segment_id") and not item.get("id"):
            item["id"] = str(item["stt_segment_id"])
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
        return item

    def _append_block_segment_item(self, segments: list[dict], item: dict) -> None:
        same_group = False
        if segments:
            last = segments[-1]
            if not item.get("is_gap") and not last.get("is_gap"):
                same_start = abs(float(last["start"]) - float(item["start"])) < 0.05
                last_end = last.get("end")
                item_end = item.get("end")
                same_end = (
                    last_end is None
                    or item_end is None
                    or abs(float(last_end) - float(item_end)) < 0.05
                )
                same_group = same_start and same_end
        if (
            same_group
        ):
            segments[-1]["text"] += "\n" + str(item.get("text", "") or "")
            return
        segments.append(item)

    def _finalize_current_segment_end_times(self, segments: list[dict]) -> list[dict]:
        rows = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
        for idx, seg in enumerate(rows):
            is_last = idx + 1 == len(rows)
            if is_last:
                if hasattr(self, "video_player") and getattr(self.video_player, "total_time", 0) > seg["start"]:
                    next_start = self.video_player.total_time if seg.get("is_gap") else min(seg["start"] + 3.0, self.video_player.total_time)
                else:
                    next_start = seg["start"] + 3.0
            else:
                next_start = rows[idx + 1]["start"]

            current_end = seg.get("end")
            if current_end is not None and seg["start"] < current_end <= next_start + 0.05:
                seg["end"] = current_end
            else:
                seg["end"] = next_start
            if seg.get("quality") and not seg.get("quality_signature"):
                seg["quality_signature"] = self._segment_quality_signature(seg)
        return rows

    def _cache_current_segments(self, segments: list[dict]) -> list[dict]:
        self._cached_segs = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
        self._refresh_cached_line_map()
        self._subtitle_memory_cache = build_segment_lookup(self._cached_segs)
        self._segment_cache_valid = True
        try:
            self._last_segment_cache_block_count = int(self.text_edit.document().blockCount())
        except Exception:
            pass
        return [dict(seg) for seg in self._cached_segs]

    def _get_current_segments(self, force_rebuild: bool = False) -> list[dict]:
        if not force_rebuild:
            cached = self._cached_current_segments_if_fresh()
            if cached is not None:
                return cached

        segments: list[dict] = []
        block = self.text_edit.document().begin()
        line_idx = 0
        while block.isValid():
            data = block.userData()
            text = block.text().replace("\u2028", "\n").strip()
            item = self._segment_item_from_block(data, text, line_idx)
            if item is not None:
                self._append_block_segment_item(segments, item)
            block = block.next()
            line_idx += 1

        finalized = self._finalize_current_segment_end_times(segments)
        clamped = self._clamp_segments_to_clip_duration(finalized)
        return self._cache_current_segments(clamped)
