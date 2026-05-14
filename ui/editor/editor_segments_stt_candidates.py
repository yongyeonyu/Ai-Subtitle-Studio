"""STT candidate selection helpers for editor subtitle segments."""

from __future__ import annotations

from core.project.project_srt import strip_whisper_control_tokens


class EditorSegmentsSttCandidatesMixin:
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

    def _overlapping_final_segments_for_stt_candidate(self, segments: list[dict], candidate: dict) -> list[dict]:
        try:
            cand_start = self._frame_time(float(candidate.get("start", 0.0) or 0.0))
            cand_end = self._frame_time(float(candidate.get("end", cand_start) or cand_start))
        except Exception:
            return []
        overlaps: list[dict] = []
        for seg in segments or []:
            if self._segment_overlaps_time_range(seg, cand_start, cand_end):
                overlaps.append(dict(seg))
        return overlaps

    def _manual_exact_stt_candidate(self, candidate: dict, *, replaced_segments: list[dict]) -> dict:
        exact = dict(candidate or {})
        try:
            raw_start = float(candidate.get("start", 0.0) or 0.0)
            raw_end = float(candidate.get("end", raw_start) or raw_start)
        except Exception:
            raw_start, raw_end = 0.0, 0.0
        exact["start"] = self._frame_time(max(0.0, raw_start))
        exact["end"] = self._frame_time(max(float(exact["start"]) + 0.05, raw_end))
        exact["_stt_placement_mode"] = "manual_exact_candidate_timing"
        exact["_stt_original_candidate_start"] = raw_start
        exact["_stt_original_candidate_end"] = raw_end
        exact["_stt_replaced_segment_count"] = len(list(replaced_segments or []))
        if "start_frame" in candidate:
            exact["_stt_original_start_frame"] = candidate.get("start_frame")
        if "end_frame" in candidate:
            exact["_stt_original_end_frame"] = candidate.get("end_frame")
        return exact

    def _stt_selection_slot_for_candidate(self, segments: list[dict], candidate: dict) -> dict | None:
        target = self._best_final_segment_for_stt_candidate(segments, candidate)
        try:
            cand_start = self._frame_time(float(candidate.get("start", 0.0) or 0.0))
            cand_end = self._frame_time(float(candidate.get("end", cand_start) or cand_start))
        except Exception:
            return None
        if cand_end <= cand_start:
            return None
        fps = max(1.0, float(getattr(self, "video_fps", 30.0) or 30.0))
        edge_tol = max(0.12, min(0.35, 4.0 / fps))
        selected: list[dict] = []
        for seg in segments or []:
            if seg.get("is_gap"):
                continue
            try:
                start = self._frame_time(float(seg.get("start", 0.0) or 0.0))
                end = self._frame_time(float(seg.get("end", start) or start))
            except Exception:
                continue
            if end <= start:
                continue
            overlap = max(0.0, min(end, cand_end) - max(start, cand_start))
            if overlap <= 0.0:
                continue
            same_target = (
                target is not None
                and int(seg.get("line", -999999)) == int(target.get("line", -888888))
                and abs(float(seg.get("start", 0.0) or 0.0) - float(target.get("start", 0.0) or 0.0)) < 0.05
            )
            meaningful = overlap >= min(max(0.001, end - start), max(0.001, cand_end - cand_start)) * 0.35
            if same_target or overlap >= edge_tol or meaningful:
                selected.append(dict(seg))
        if target is not None and not any(
            abs(float(seg.get("start", 0.0) or 0.0) - float(target.get("start", 0.0) or 0.0)) < 0.05
            and abs(float(seg.get("end", 0.0) or 0.0) - float(target.get("end", 0.0) or 0.0)) < 0.05
            for seg in selected
        ):
            selected.append(dict(target))
        if not selected:
            return None
        selected.sort(key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)))
        slot_start = self._frame_time(min(float(seg.get("start", 0.0) or 0.0) for seg in selected))
        slot_end = self._frame_time(max(float(seg.get("end", slot_start) or slot_start) for seg in selected))
        if slot_end <= slot_start:
            return None
        return {"start": slot_start, "end": slot_end, "segments": selected}

    def _stt_slot_candidates_for_source(self, candidate: dict, slot_start: float, slot_end: float) -> list[dict]:
        source = self._stt_candidate_source(candidate)
        rows: list[dict] = []
        for seg in list(getattr(self, "_live_stt_preview_segments", []) or []):
            if not isinstance(seg, dict) or self._stt_candidate_source(seg) != source:
                continue
            try:
                start = float(seg.get("start", 0.0) or 0.0)
                end = float(seg.get("end", start) or start)
            except Exception:
                continue
            if start < slot_end + 0.05 and end > slot_start - 0.05:
                rows.append(dict(seg))
        if not rows:
            rows.append(dict(candidate or {}))
        seen: set[tuple[float, float, str]] = set()
        deduped: list[dict] = []
        for row in sorted(rows, key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0))):
            clean_text = strip_whisper_control_tokens(str(row.get("text", "") or ""))
            if not clean_text:
                continue
            row["text"] = clean_text
            key = (
                round(float(row.get("start", 0.0) or 0.0), 3),
                round(float(row.get("end", 0.0) or 0.0), 3),
                clean_text,
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return deduped

    def _merged_stt_slot_text(self, candidate: dict, slot_start: float, slot_end: float) -> tuple[str, list[dict]]:
        parts = self._stt_slot_candidates_for_source(candidate, slot_start, slot_end)
        texts = [strip_whisper_control_tokens(str(part.get("text", "") or "")) for part in parts]
        texts = [text for text in texts if text]
        if not texts:
            return strip_whisper_control_tokens(str(candidate.get("text", "") or "")), parts
        return " ".join(texts), parts

    def _final_segment_from_stt_candidate(self, candidate: dict) -> dict:
        source = self._stt_candidate_source(candidate)
        start = self._frame_time(max(0.0, float(candidate.get("start", 0.0) or 0.0)))
        end = self._frame_time(max(start + 0.05, float(candidate.get("end", start + 0.5) or start + 0.5)))
        text = strip_whisper_control_tokens(str(candidate.get("text", "") or ""))
        try:
            candidate_score = max(0.0, min(100.0, float(candidate.get("stt_score", candidate.get("score", 98.0)) or 98.0)))
        except Exception:
            candidate_score = 98.0
        candidate_payload = dict(candidate)
        candidate_payload["text"] = text
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
            "score_color": "green",
            "manual_stt_candidate_locked": True,
            "manual_stt_candidate_source": source,
            "manual_stt_candidate_start": start,
            "manual_stt_candidate_end": end,
            "_deep_candidate_selector_policy": {
                "task": "manual_stt_candidate_selection",
                "decision": "user_locked_candidate",
                "source": source,
                "preserve_candidate_timing": True,
                "placement_mode": str(candidate.get("_stt_placement_mode") or ""),
                "replaced_segment_count": int(candidate.get("_stt_replaced_segment_count", 0) or 0),
            },
            "_deep_timing_policy": {
                "task": "manual_stt_candidate_timing_lock",
                "locked_source": source,
                "start": start,
                "end": end,
                "preserve_candidate_timing": True,
            },
            "quality": {
                "confidence_label": "green",
                "confidence_score": max(candidate_score, 98.0),
                "confidence_reason": f"{source} 후보 수동 확정",
                "manual_confirmed": True,
                "flags": ["manual_confirmed", "stt_candidate_selected", "manual_stt_candidate_locked"],
            },
        }
        for key in ("_clip_idx", "_clip_file"):
            if key in candidate:
                seg[key] = candidate[key]
        return seg
