# Version: 03.09.31
# Phase: PHASE2
"""
ui/editor/undo_manager.py
[v02.02.01]
- Extend snapshot to include multiclip structure for clip add/delete/reorder undo/redo.
"""
from __future__ import annotations

from dataclasses import dataclass
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QTextCursor
from ui.editor.subtitle_text_edit import SubtitleBlockData


@dataclass
class SnapshotState:
    blocks: list
    canvas_end_map: dict
    cursor_line: int
    multiclip_files: list
    multiclip_boundaries: list
    project_boundary_times: list
    active_clip_idx: int
    live_stt_preview_segments: list
    cached_segments: list


class UndoManager:
    MAX_STACK = 50

    def __init__(self, editor):
        self._editor = editor
        self._undo_stack: list[SnapshotState] = []
        self._redo_stack: list[SnapshotState] = []
        self._is_restoring = False

        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(500)
        self._debounce.timeout.connect(self._do_push)

    def push(self):
        if self._is_restoring:
            return
        self._debounce.start()

    def push_immediate(self):
        if self._is_restoring:
            return
        self._debounce.stop()
        self._do_push()

    def undo(self):
        if not self._undo_stack:
            return
        current = self._capture()
        self._redo_stack.append(current)
        state = self._undo_stack.pop()
        self._restore(state)

    def redo(self):
        if not self._redo_stack:
            return
        current = self._capture()
        self._undo_stack.append(current)
        state = self._redo_stack.pop()
        self._restore(state)

    def _do_push(self):
        if self._is_restoring:
            return
        state = self._capture()
        if self._undo_stack and self._is_same(self._undo_stack[-1], state):
            return
        self._undo_stack.append(state)
        if len(self._undo_stack) > self.MAX_STACK:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _capture(self) -> SnapshotState:
        editor = self._editor
        doc = editor.text_edit.document()
        blocks = []
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            ud = block.userData()
            if isinstance(ud, SubtitleBlockData):
                blocks.append((block.text(), self._block_meta(ud)))
            else:
                blocks.append((block.text(), {"spk_id": "00", "start_sec": 0.0, "is_gap": False}))

        canvas_end_map = {}
        if hasattr(editor, 'timeline') and hasattr(editor.timeline, 'canvas'):
            for seg in editor.timeline.canvas.segments:
                line = seg.get('line', -1)
                if line >= 0 and 'end' in seg:
                    canvas_end_map[line] = seg['end']

        owner = editor.window() if hasattr(editor, 'window') else None
        multiclip_files = list(getattr(owner, '_multiclip_files', []) or []) if owner else []
        multiclip_boundaries = [dict(x) for x in list(getattr(owner, '_multiclip_boundaries', []) or [])] if owner else []
        project_boundary_times = list(getattr(owner, '_project_boundary_times', []) or []) if owner else []
        canvas = getattr(getattr(editor, "timeline", None), "canvas", None)
        active_clip_idx = int(getattr(canvas, '_active_clip_idx', getattr(owner, '_active_clip_idx', 0)) or 0)
        cursor_line = editor.text_edit.textCursor().blockNumber()
        live_stt_preview_segments = [dict(seg) for seg in list(getattr(editor, "_live_stt_preview_segments", []) or [])]
        try:
            cached_segments = [dict(seg) for seg in list(editor._get_current_segments() or [])]
        except Exception:
            cached_segments = [dict(seg) for seg in list(getattr(editor, "_cached_segs", []) or [])]
        return SnapshotState(
            blocks,
            canvas_end_map,
            cursor_line,
            multiclip_files,
            multiclip_boundaries,
            project_boundary_times,
            active_clip_idx,
            live_stt_preview_segments,
            cached_segments,
        )

    def _restore(self, state: SnapshotState):
        self._is_restoring = True
        editor = self._editor
        owner = editor.window() if hasattr(editor, 'window') else None
        doc = editor.text_edit.document()
        doc.blockSignals(True)
        editor.text_edit.blockSignals(True)

        cur = QTextCursor(doc)
        cur.beginEditBlock()
        cur.select(QTextCursor.SelectionType.Document)
        cur.removeSelectedText()
        for i, block_state in enumerate(state.blocks):
            if len(block_state) == 2 and isinstance(block_state[1], dict):
                text, meta = block_state
            else:
                text, spk_id, start_sec, is_gap = block_state
                meta = {"spk_id": spk_id, "start_sec": start_sec, "is_gap": is_gap}
            if i > 0:
                cur.insertText('\n')
            cur.insertText(text)
            cur.block().setUserData(self._userdata_from_meta(meta))
        cur.endEditBlock()

        if owner is not None:
            owner._multiclip_files = list(state.multiclip_files)
            owner._multiclip_boundaries = [dict(x) for x in state.multiclip_boundaries]
            owner._project_boundary_times = list(state.project_boundary_times)
            owner._active_clip_idx = int(state.active_clip_idx)
            if hasattr(editor, '_apply_multiclip_state_from_owner'):
                try:
                    editor._apply_multiclip_state_from_owner()
                except Exception:
                    pass

        cursor_block = doc.findBlockByNumber(state.cursor_line)
        if cursor_block.isValid():
            editor.text_edit.setTextCursor(QTextCursor(cursor_block))

        doc.blockSignals(False)
        editor.text_edit.blockSignals(False)
        if hasattr(editor.text_edit, 'update_margins'):
            editor.text_edit.update_margins()
        if hasattr(editor.text_edit, 'timestampArea'):
            editor.text_edit.timestampArea.update()
        editor._live_stt_preview_segments = [dict(seg) for seg in list(state.live_stt_preview_segments or [])]
        editor._cached_segs = [dict(seg) for seg in list(state.cached_segments or [])]
        if hasattr(editor, "timeline") and hasattr(editor.timeline, "update_segments"):
            confirmed = [dict(seg) for seg in list(state.cached_segments or []) if not seg.get("is_gap")]
            preview = [dict(seg) for seg in list(state.live_stt_preview_segments or [])]
            combined = sorted(
                confirmed + preview,
                key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)),
            )
            total_dur = combined[-1]["end"] if combined else 0.0
            try:
                if hasattr(editor, "video_player") and editor.video_player.total_time > 0.0:
                    total_dur = max(total_dur, editor.video_player.total_time)
            except Exception:
                pass
            try:
                editor.timeline.update_segments(combined, getattr(editor, "_active_seg_start", None), total_dur)
            except Exception:
                pass
        if hasattr(editor, '_schedule_timeline'):
            editor._schedule_timeline()
        self._is_restoring = False

    @staticmethod
    def _is_same(a: SnapshotState, b: SnapshotState) -> bool:
        return (
            a.blocks == b.blocks and
            a.canvas_end_map == b.canvas_end_map and
            a.multiclip_files == b.multiclip_files and
            a.multiclip_boundaries == b.multiclip_boundaries and
            a.project_boundary_times == b.project_boundary_times and
            a.active_clip_idx == b.active_clip_idx and
            a.live_stt_preview_segments == b.live_stt_preview_segments and
            a.cached_segments == b.cached_segments
        )

    @staticmethod
    def _block_meta(ud: SubtitleBlockData) -> dict:
        return {
            "spk_id": ud.spk_id,
            "start_sec": ud.start_sec,
            "is_gap": ud.is_gap,
            "stt_mode": getattr(ud, "stt_mode", False),
            "stt_pending": getattr(ud, "stt_pending", False),
            "original_text": getattr(ud, "original_text", ""),
            "dictated_text": getattr(ud, "dictated_text", ""),
            "quality": dict(getattr(ud, "quality", {}) or {}),
            "quality_history": list(getattr(ud, "quality_history", []) or []),
            "quality_candidates": list(getattr(ud, "quality_candidates", []) or []),
            "quality_signature": getattr(ud, "quality_signature", ""),
            "clip_idx": getattr(ud, "clip_idx", None),
            "clip_file": getattr(ud, "clip_file", ""),
            "stt_selected_source": getattr(ud, "stt_selected_source", ""),
            "stt_ensemble_llm_selected_source": getattr(ud, "stt_ensemble_llm_selected_source", ""),
            "stt_candidates": list(getattr(ud, "stt_candidates", []) or []),
            "stt_ensemble_source": getattr(ud, "stt_ensemble_source", ""),
            "stt_ensemble_llm_selected_label": getattr(ud, "stt_ensemble_llm_selected_label", ""),
            "stt_ensemble_similarity": getattr(ud, "stt_ensemble_similarity", None),
            "stt_ensemble_needs_llm_review": getattr(ud, "stt_ensemble_needs_llm_review", False),
            "stt_ensemble_inserted_from_stt2": getattr(ud, "stt_ensemble_inserted_from_stt2", False),
            "stt_ensemble_word_rover": dict(getattr(ud, "stt_ensemble_word_rover", {}) or {}),
        }

    @staticmethod
    def _userdata_from_meta(meta: dict) -> SubtitleBlockData:
        return SubtitleBlockData(
            meta.get("spk_id", "00"),
            meta.get("start_sec", 0.0),
            meta.get("is_gap", False),
            stt_mode=meta.get("stt_mode", False),
            stt_pending=meta.get("stt_pending", False),
            original_text=meta.get("original_text", ""),
            dictated_text=meta.get("dictated_text", ""),
            quality=dict(meta.get("quality") or {}),
            quality_history=list(meta.get("quality_history") or []),
            quality_candidates=list(meta.get("quality_candidates") or []),
            quality_signature=meta.get("quality_signature", ""),
            clip_idx=meta.get("clip_idx"),
            clip_file=meta.get("clip_file", ""),
            stt_selected_source=meta.get("stt_selected_source", ""),
            stt_ensemble_llm_selected_source=meta.get("stt_ensemble_llm_selected_source", ""),
            stt_candidates=list(meta.get("stt_candidates") or []),
            stt_ensemble_source=meta.get("stt_ensemble_source", ""),
            stt_ensemble_llm_selected_label=meta.get("stt_ensemble_llm_selected_label", ""),
            stt_ensemble_similarity=meta.get("stt_ensemble_similarity"),
            stt_ensemble_needs_llm_review=meta.get("stt_ensemble_needs_llm_review", False),
            stt_ensemble_inserted_from_stt2=meta.get("stt_ensemble_inserted_from_stt2", False),
            stt_ensemble_word_rover=dict(meta.get("stt_ensemble_word_rover") or {}),
        )
