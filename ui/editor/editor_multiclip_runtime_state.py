# Version: 01.00.00
# Phase: PHASE2
from __future__ import annotations

import os

from ui.editor.editor_multiclip_owner_bridge import EditorMulticlipOwnerBridgeMixin
from ui.project.project_session_runtime import set_runtime_multiclip_state


class EditorMulticlipRuntimeStateMixin(EditorMulticlipOwnerBridgeMixin):
    def _normalize_multiclip_segment_order(self, segs):
        ordered = sorted(
            (dict(seg) for seg in (segs or [])),
            key=lambda s: (
                float(s.get("start", 0.0) or 0.0),
                float(s.get("end", 0.0) or 0.0),
            ),
        )
        for i, seg in enumerate(ordered):
            seg["line"] = i
        return ordered

    def _collect_existing_clip_segments(self, file_path, offset, clip_idx=None):
        segs = []
        base = os.path.splitext(file_path)[0]
        srt_path = base + ".srt"
        if os.path.exists(srt_path):
            try:
                from core.srt_parser import parse_srt

                for seg in parse_srt(srt_path):
                    item = {
                        "start": float(seg.get("start", 0.0)) + offset,
                        "end": float(seg.get("end", 0.0)) + offset,
                        "text": seg.get("text", ""),
                        "speaker": seg.get("speaker", "00"),
                        "_clip_file": file_path,
                    }
                    if clip_idx is not None:
                        item["_clip_idx"] = int(clip_idx)
                    segs.append(item)
            except Exception:
                pass
        return self._normalize_multiclip_segment_order(segs)

    def _recompute_multiclip_boundaries(self, files):
        from core.media_info import probe_media

        boundaries = []
        cumulative = 0.0
        for path in files:
            try:
                dur = float(probe_media(path).get("duration", 0.0) or 0.0)
            except Exception:
                dur = 0.0
            boundaries.append({"start": cumulative, "end": cumulative + dur, "file": path, "name": os.path.basename(path)})
            cumulative += dur
        return boundaries

    def _resolve_multiclip_segment_file(self, seg: dict, old_bounds: list[dict]) -> str | None:
        file_path = seg.get("_clip_file")
        if file_path:
            return file_path
        try:
            sec = float(seg.get("start", 0.0))
        except Exception:
            sec = 0.0
        for boundary in old_bounds:
            if boundary["start"] <= sec < boundary["end"] + 0.001:
                return boundary.get("file")
        return None

    def _shift_segment_to_multiclip_offsets(self, seg: dict, *, old_offset: float, new_offset: float, file_path: str) -> dict:
        shifted = dict(seg)
        shifted["start"] = round(float(seg.get("start", 0.0)) - old_offset + new_offset, 3)
        shifted["end"] = round(float(seg.get("end", 0.0)) - old_offset + new_offset, 3)
        shifted["_clip_file"] = file_path
        return shifted

    def _remap_segments_for_multiclip_files(self, new_files):
        owner = self._multiclip_owner()
        old_bounds = self._multiclip_boundaries_from_owner(owner)
        old_by_file = {b.get("file"): b for b in old_bounds}
        new_bounds = self._recompute_multiclip_boundaries(new_files)
        new_by_file = {b.get("file"): b for b in new_bounds}
        current = self._get_current_segments()
        remapped = []
        for seg in current:
            file_path = self._resolve_multiclip_segment_file(seg, old_bounds)
            if not file_path or file_path not in new_by_file or file_path not in old_by_file:
                continue
            remapped.append(
                self._shift_segment_to_multiclip_offsets(
                    seg,
                    old_offset=float(old_by_file[file_path]["start"]),
                    new_offset=float(new_by_file[file_path]["start"]),
                    file_path=file_path,
                )
            )
        return self._normalize_multiclip_segment_order(remapped), new_bounds

    def _multiclip_boxes_from_boundaries(self, boundaries: list[dict]) -> list[dict]:
        boxes = []
        for i, boundary in enumerate(boundaries):
            boxes.append(
                {
                    "start": boundary["start"],
                    "end": boundary["end"],
                    "index": i + 1,
                    "name": boundary.get("name", ""),
                    "file": boundary.get("file", ""),
                }
            )
        return boxes

    def _apply_multiclip_selection_state(self, boxes: list[dict], gc) -> None:
        try:
            if boxes:
                self.timeline._selected_clip_idx = 0
                self.timeline._selected_clip_offset = float(boxes[0].get("start", 0.0))
                self.timeline._selected_clip_duration = max(
                    0.001,
                    float(boxes[0].get("end", 0.0)) - float(boxes[0].get("start", 0.0)),
                )
                self.timeline._selected_clip_label = str(boxes[0].get("index", 1))
                gc.set_clip_label(self.timeline._selected_clip_label)
            else:
                self.timeline._selected_clip_label = ""
                gc.set_clip_label("")
        except Exception:
            pass

    def _apply_multiclip_state_from_owner(self):
        owner = self._multiclip_owner()
        boundaries = self._multiclip_boundaries_from_owner(owner)
        if not owner or not boundaries:
            return
        boxes = self._multiclip_boxes_from_boundaries(boundaries)
        total_dur = self._multiclip_total_duration(owner)
        self.timeline.canvas._multiclip_boxes = boxes
        self.timeline.canvas._active_clip_idx = 0
        project_rows = self._multiclip_project_boundary_rows(owner)
        if hasattr(self.timeline, "set_boundary_times"):
            self.timeline.set_boundary_times(project_rows)
        else:
            self.timeline.canvas.boundary_times = project_rows
        self.timeline.canvas.total_duration = total_dur
        self._set_multiclip_active_clip_idx(0, owner)
        gc = self.timeline.global_canvas
        gc.total_duration = total_dur
        gc._multiclip_boxes = boxes
        gc._active_clip_idx = 0
        self._apply_multiclip_selection_state(boxes, gc)
        self.timeline.canvas.update()
        gc.update()
        try:
            self.timeline.load_multiclip_waveform(boundaries)
        except Exception:
            pass

    def _apply_multiclip_runtime_state(self, owner, files, new_bounds) -> None:
        set_runtime_multiclip_state(
            owner,
            files,
            new_bounds,
            project_boundary_rows=[],
            emit_boundary_signal=True,
        )

    def _reload_apply_and_persist_multiclip(self, remapped: list[dict]) -> None:
        self._reload_segments_from_list(remapped)
        self._apply_multiclip_state_from_owner()
        try:
            self._auto_save_project(self._get_current_segments())
        except Exception:
            pass

    def _added_multiclip_files_with_existing_srts(self, added_files: list[str]) -> tuple[bool, list[str]]:
        candidates = [path for path in added_files if os.path.exists(os.path.splitext(path)[0] + ".srt")]
        return bool(candidates), candidates

    def _append_existing_multiclip_segments(self, remapped: list[dict], new_bounds: list[dict], added_files: list[str]) -> list[dict]:
        for file_path in added_files:
            boundary = next((b for b in new_bounds if b.get("file") == file_path), None)
            if not boundary:
                continue
            clip_idx = next((i for i, b in enumerate(new_bounds) if b.get("file") == file_path), None)
            remapped.extend(self._collect_existing_clip_segments(file_path, float(boundary["start"]), clip_idx))
        return self._normalize_multiclip_segment_order(remapped)
