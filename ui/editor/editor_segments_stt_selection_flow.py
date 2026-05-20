"""STT candidate selection flow and preview redraw helpers."""

from __future__ import annotations

import threading

from PyQt6.QtCore import QTimer

from core.engine.subtitle_timing import align_stt_preview_to_subtitle_segments
from core.native_swift_timeline import apply_subtitle_magnet_via_swift
from core.project.project_srt import strip_whisper_control_tokens
from ui.editor.editor_subtitle_assist import (
    apply_netflix_subtitle_magnet,
    compute_subtitle_magnet_policy,
)


class EditorSegmentsSttSelectionFlowMixin:
    def _combined_timeline_segments_with_live_preview(
        self,
        confirmed_segments: list[dict],
    ) -> tuple[list[dict], list[dict], list[dict], float]:
        confirmed = [seg for seg in list(confirmed_segments or []) if not seg.get("is_gap")]
        preview = align_stt_preview_to_subtitle_segments(
            list(getattr(self, "_live_stt_preview_segments", []) or []),
            confirmed,
        )
        explicit_subtitle_preview = [
            dict(seg)
            for seg in list(getattr(self, "_live_editor_preview_segments", []) or [])
            if isinstance(seg, dict) and not seg.get("is_gap") and str(seg.get("text", "") or "").strip()
        ]
        subtitle_preview: list[dict] = []
        if not bool(getattr(self, "_stt_preview_subtitle_drafts_enabled", True)):
            explicit_subtitle_preview = []
        elif explicit_subtitle_preview:
            subtitle_preview = sorted(
                explicit_subtitle_preview,
                key=lambda seg: (
                    float(seg.get("start", 0.0) or 0.0),
                    float(seg.get("end", 0.0) or 0.0),
                ),
            )
        elif bool(getattr(self, "_stt_preview_subtitle_drafts_enabled", True)):
            subtitle_preview = self._build_live_subtitle_preview_segments(preview, confirmed)
        combined = sorted(
            confirmed + subtitle_preview + preview,
            key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)),
        )
        total_dur = combined[-1]["end"] if combined else 0.0
        if hasattr(self, "video_player") and self.video_player.total_time > 0.0:
            total_dur = max(total_dur, self.video_player.total_time)
        return confirmed, preview, subtitle_preview, total_dur

    def _prune_selected_preview_overlap(
        self,
        *,
        cand_source: str,
        selected_start: float,
        selected_end: float,
    ) -> None:
        existing_preview = [dict(seg) for seg in list(getattr(self, "_live_stt_preview_segments", []) or [])]
        if hasattr(self, "_clamp_segments_to_clip_duration"):
            try:
                existing_preview = self._clamp_segments_to_clip_duration(existing_preview, log_changes=False)
            except Exception:
                pass
        self._live_stt_preview_segments = existing_preview

    def _stt_selection_magnet_policy(self) -> tuple[dict, float]:
        policy_getter = getattr(self, "_subtitle_magnet_policy", None)
        policy: dict | None = None
        if callable(policy_getter):
            try:
                policy = dict(policy_getter(allow_sync_override=False) or {})
            except TypeError:
                try:
                    policy = dict(policy_getter() or {})
                except Exception:
                    policy = None
            except Exception:
                policy = None
        if not isinstance(policy, dict):
            try:
                policy = compute_subtitle_magnet_policy(dict(getattr(self, "settings", {}) or {}))
            except Exception:
                policy = {}
        try:
            threshold_sec = float(
                policy.get("continuous_threshold_sec", policy.get("recommended_threshold_sec", 3.0)) or 3.0
            )
        except Exception:
            threshold_sec = 3.0
        return dict(policy or {}), max(0.05, threshold_sec)

    def _retime_manual_stt_selection_segments(
        self,
        segments: list[dict],
        *,
        selected_segments: list[dict],
    ) -> list[dict]:
        rows = [seg for seg in list(segments or []) if isinstance(seg, dict) and not seg.get("is_gap")]
        if len(rows) < 2 or not selected_segments:
            return [dict(seg) for seg in rows]

        selected_ids = {id(seg) for seg in selected_segments if isinstance(seg, dict)}
        selected_indices = [idx for idx, seg in enumerate(rows) if id(seg) in selected_ids]
        if not selected_indices:
            return [dict(seg) for seg in rows]

        window_start = max(0, min(selected_indices) - 1)
        window_end = min(len(rows) - 1, max(selected_indices) + 1)
        original_window = [dict(seg) for seg in rows[window_start:window_end + 1]]
        window = [dict(seg) for seg in original_window]
        if len(window) < 2:
            return [dict(seg) for seg in rows]
        for line, seg in enumerate(window):
            seg["line"] = line

        policy, threshold_sec = self._stt_selection_magnet_policy()
        timeline = getattr(self, "timeline", None)
        canvas = getattr(timeline, "canvas", None) if timeline is not None else None
        boundary_times = list(getattr(canvas, "boundary_times", []) or [])
        provisional_boundaries = list(getattr(canvas, "scan_boundary_times", []) or [])
        vad_segments = list(getattr(canvas, "vad_segments", []) or [])
        try:
            fps = float(getattr(self, "video_fps", 30.0) or 30.0)
        except Exception:
            fps = 30.0

        native_result = apply_subtitle_magnet_via_swift(
            segments=window,
            threshold_sec=threshold_sec,
            boundary_times=boundary_times,
            provisional_boundaries=provisional_boundaries,
            vad_segments=vad_segments,
            speaker_strict=True,
            fps=fps,
            policy=policy,
            strategy="extend_current",
        )
        merged_window = None
        if isinstance(native_result, dict) and isinstance(native_result.get("segments"), list):
            merged_window = [
                dict(seg)
                for seg in list(native_result.get("segments") or [])
                if isinstance(seg, dict) and not seg.get("is_gap")
            ]
        if merged_window is None:
            merged_window, _ = apply_netflix_subtitle_magnet(
                window,
                threshold_sec=threshold_sec,
                boundary_times=boundary_times,
                provisional_boundaries=provisional_boundaries,
                vad_segments=vad_segments,
                speaker_strict=True,
                fps=fps,
                policy=policy,
            )
        if not isinstance(merged_window, list) or len(merged_window) != len(window):
            return [dict(seg) for seg in rows]

        retimed_window: list[dict] = []
        for before, after in zip(original_window, merged_window):
            updated = dict(before)
            for key in (
                "start",
                "end",
                "start_frame",
                "end_frame",
                "timeline_start_frame",
                "timeline_end_frame",
                "frame_rate",
                "timeline_frame_rate",
                "frame_range",
            ):
                if key in after:
                    updated[key] = after.get(key)
            retimed_window.append(updated)

        merged = [dict(seg) for seg in rows[:window_start]]
        merged.extend(retimed_window)
        merged.extend(dict(seg) for seg in rows[window_end + 1:])
        if hasattr(self, "_clamp_segments_to_clip_duration"):
            try:
                merged = self._clamp_segments_to_clip_duration(merged, log_changes=False)
            except Exception:
                pass
        return merged

    def _selection_payload_for_stt_candidate(
        self,
        candidate: dict,
        current_segments: list[dict],
        *,
        replaced_segments: list[dict],
    ) -> dict:
        payload = self._fit_stt_candidate_to_final_segment_slot(candidate, current_segments)
        if str(payload.get("_stt_placement_mode", "") or "").strip().lower() == "raw":
            payload = self._manual_exact_stt_candidate(candidate, replaced_segments=replaced_segments)
        payload["_stt_original_candidate_start"] = float(candidate.get("start", payload.get("start", 0.0)) or 0.0)
        payload["_stt_original_candidate_end"] = float(
            candidate.get("end", payload.get("end", payload.get("start", 0.0))) or payload.get("start", 0.0) or 0.0
        )
        payload["_stt_replaced_segment_count"] = len(list(replaced_segments or []))
        if "start_frame" in candidate:
            payload["_stt_original_start_frame"] = candidate.get("start_frame")
        if "end_frame" in candidate:
            payload["_stt_original_end_frame"] = candidate.get("end_frame")
        return payload

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

        candidate = dict(candidate)
        cand_text = strip_whisper_control_tokens(str(candidate.get("text", "")))
        candidate["text"] = cand_text
        cand_start = float(candidate.get("start", 0.0) or 0.0)

        cand_source = ""
        if hasattr(self, "_stt_candidate_source"):
            cand_source = self._stt_candidate_source(candidate)
        else:
            cand_source = str(
                candidate.get("stt_preview_source")
                or candidate.get("stt_source")
                or candidate.get("stt_ensemble_source")
                or ""
            ).strip().upper()

        if not cand_text or not cand_source:
            return

        native_plan = self._plan_stt_candidate_selection_native(current, candidate)
        if isinstance(native_plan, dict):
            slot_start_value = native_plan.get("slotStart", native_plan.get("slot_start"))
            slot_end_value = native_plan.get("slotEnd", native_plan.get("slot_end"))
            slot = (
                {
                    "start": float(slot_start_value),
                    "end": float(slot_end_value),
                    "segments": [dict(seg) for seg in list(native_plan.get("replacedSegments", native_plan.get("replaced_segments")) or []) if isinstance(seg, dict)],
                }
                if native_plan.get("usedSlot", native_plan.get("used_slot"))
                and slot_start_value is not None
                and slot_end_value is not None
                else None
            )
            replaced_segments = [
                dict(seg)
                for seg in list(native_plan.get("replacedSegments", native_plan.get("replaced_segments")) or [])
                if isinstance(seg, dict)
            ]
            slot_parts = []
            merged_text_for_slot = ""
            if slot is not None:
                try:
                    slot_parts = self._stt_slot_candidates_for_source(
                        candidate,
                        float(slot.get("start", cand_start) or cand_start),
                        float(slot.get("end", cand_start) or cand_start),
                    )
                except Exception:
                    slot_parts = []
            placed_candidate = self._selection_payload_for_stt_candidate(
                candidate,
                current,
                replaced_segments=replaced_segments,
            )
            if slot is not None and len(replaced_segments) > 1 and len(slot_parts) <= 1:
                placed_candidate["start"] = self._frame_time(float(slot.get("start", cand_start) or cand_start))
                placed_candidate["end"] = self._frame_time(
                    max(
                        float(placed_candidate["start"]) + 0.05,
                        float(slot.get("end", placed_candidate["start"]) or placed_candidate["start"]),
                    )
                )
                placed_candidate["_stt_placement_mode"] = "manual_slot_span_replace"
            selected_segments: list[dict] = []
            replacement_meta = [
                {
                    "start": seg.get("start"),
                    "end": seg.get("end"),
                    "text": seg.get("text"),
                    "line": seg.get("line"),
                }
                for seg in replaced_segments[:8]
            ]
            if not selected_segments:
                selected_seg = self._final_segment_from_stt_candidate(placed_candidate)
                if replacement_meta:
                    selected_seg["manual_stt_selection_replaced_segments"] = list(replacement_meta)
                selected_segments.append(selected_seg)
        else:
            slot = self._stt_selection_slot_for_candidate(current, candidate)
            slot_parts: list[dict] = []
            merged_text_for_slot = ""
            if slot is not None:
                replaced_segments = list(slot.get("segments") or [])
                placed_candidate = self._manual_exact_stt_candidate(candidate, replaced_segments=replaced_segments)
                slot_start = float(slot.get("start") if slot.get("start") is not None else cand_start)
                slot_end = float(slot.get("end") if slot.get("end") is not None else placed_candidate.get("end", slot_start))
                merged_text_for_slot, slot_parts = self._merged_stt_slot_text(candidate, slot_start, slot_end)
                placed_candidate["start"] = self._frame_time(slot_start)
                placed_candidate["end"] = self._frame_time(max(slot_start + 0.05, slot_end))
                placed_candidate["_stt_placement_mode"] = "manual_final_slot_replace"
                placed_candidate["_stt_original_candidate_start"] = float(candidate.get("start", cand_start) or cand_start)
                placed_candidate["_stt_original_candidate_end"] = float(candidate.get("end", slot_end) or slot_end)
                placed_candidate["_stt_replaced_segment_count"] = len(replaced_segments)
                placed_candidate["_stt_slot_candidate_parts"] = [
                    {
                        "source": self._stt_candidate_source(part),
                        "start": part.get("start"),
                        "end": part.get("end"),
                        "text": strip_whisper_control_tokens(str(part.get("text", "") or "")),
                    }
                    for part in slot_parts[:24]
                ]
            else:
                replaced_segments = self._overlapping_final_segments_for_stt_candidate(current, candidate)
                placed_candidate = self._manual_exact_stt_candidate(candidate, replaced_segments=replaced_segments)

        replacement_meta = [
            {
                "start": seg.get("start"),
                "end": seg.get("end"),
                "text": seg.get("text"),
                "line": seg.get("line"),
            }
            for seg in replaced_segments[:8]
        ]
        if not isinstance(native_plan, dict):
            selected_segments = []
            placed_candidate = self._selection_payload_for_stt_candidate(
                candidate,
                current,
                replaced_segments=replaced_segments,
            )
            if slot is not None and len(replaced_segments) > 1 and len(slot_parts) <= 1:
                placed_candidate["start"] = self._frame_time(float(slot.get("start", cand_start) or cand_start))
                placed_candidate["end"] = self._frame_time(
                    max(
                        float(placed_candidate["start"]) + 0.05,
                        float(slot.get("end", placed_candidate["start"]) or placed_candidate["start"]),
                    )
                )
                placed_candidate["_stt_placement_mode"] = "manual_slot_span_replace"
            selected_seg = self._final_segment_from_stt_candidate(placed_candidate)
            if replacement_meta:
                selected_seg["manual_stt_selection_replaced_segments"] = list(replacement_meta)
            selected_segments.append(selected_seg)

        selected_start = min(float(seg.get("start", cand_start) or cand_start) for seg in selected_segments)
        selected_end = max(float(seg.get("end", selected_start) or selected_start) for seg in selected_segments)
        candidate_anchor_sec = selected_start

        multi_part_slot = bool(slot is not None and len(slot_parts) > 1)
        slot_replace_covers_range = bool(
            slot is not None
            and (
                len(replaced_segments) > 1
                or (
                    selected_start <= float(slot.get("start", selected_start) or selected_start) + 0.05
                    and selected_end >= float(slot.get("end", selected_end) or selected_end) - 0.05
                )
            )
        )
        if slot is not None and not multi_part_slot and slot_replace_covers_range:
            slot_start = float(placed_candidate.get("start") if placed_candidate.get("start") is not None else cand_start)
            slot_end = float(placed_candidate.get("end") if placed_candidate.get("end") is not None else slot_start)
            replaced_keys = {
                (
                    round(float(seg.get("start", 0.0) or 0.0), 3),
                    round(float(seg.get("end", 0.0) or 0.0), 3),
                    str(seg.get("text", "") or ""),
                )
                for seg in replaced_segments
            }
            current = [
                dict(seg)
                for seg in current
                if (
                    round(float(seg.get("start", 0.0) or 0.0), 3),
                    round(float(seg.get("end", 0.0) or 0.0), 3),
                    str(seg.get("text", "") or ""),
                ) not in replaced_keys
            ]
            current = [
                seg
                for seg in current
                if not (
                    float(seg.get("start", 0.0) or 0.0) < slot_end - 0.001
                    and float(seg.get("end", seg.get("start", 0.0)) or 0.0) > slot_start + 0.001
                    and any(
                        abs(float(seg.get("start", 0.0) or 0.0) - float(rep.get("start", 0.0) or 0.0)) < 0.05
                        for rep in replaced_segments
                    )
                )
            ]
        else:
            current = self._trim_final_segments_around_candidate(current, placed_candidate)
        current.extend(selected_segments)
        current.sort(key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)))
        current = self._retime_manual_stt_selection_segments(current, selected_segments=selected_segments)
        self._prune_selected_preview_overlap(
            cand_source=cand_source,
            selected_start=selected_start,
            selected_end=selected_end,
        )

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
        confirmed, preview, subtitle_preview, total_dur = self._combined_timeline_segments_with_live_preview(
            confirmed_segments,
        )
        combined = sorted(
            confirmed + subtitle_preview + preview,
            key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)),
        )
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
            confirmed_segments = [seg for seg in self._get_current_segments() if not seg.get("is_gap")]
        except Exception:
            confirmed_segments = list(getattr(self, "_cached_segs", []) or [])
        confirmed, preview, subtitle_preview, total_dur = self._combined_timeline_segments_with_live_preview(
            confirmed_segments,
        )
        if not preview and not subtitle_preview:
            self._redraw_timeline()
            return
        combined = sorted(
            confirmed + subtitle_preview + preview,
            key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)),
        )
        self.timeline.update_segments(combined, self._active_seg_start, total_dur)
        # 실시간 드래프트가 타임라인에만 남지 않도록 같은 window를 비디오 overlay에도 바로 반영한다.
        video_context = getattr(self, "_video_subtitle_live_preview_context", None)
        apply_video_context = getattr(self, "_apply_video_context_segments", None)
        if callable(video_context) and callable(apply_video_context):
            try:
                live_context = video_context()
                if live_context is not None:
                    apply_video_context(live_context)
            except Exception:
                pass
