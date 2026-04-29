# Version: 03.00.26
# Phase: PHASE2
from __future__ import annotations

import json
import os
from dataclasses import asdict, replace

from core.project.project_context import project_media_files, project_mode, project_segments_to_editor, segment_signature
from core.project.project_manager import save_project
from core.roughcut import (
    build_markdown_guide,
    map_edl_segments_to_clip_sources,
    roughcut_result_from_dict,
    run_roughcut_pipeline,
)


class RoughcutStateMixin:
    def _active_editor(self):
        owner = self.owner
        if owner is None:
            return None
        if hasattr(owner, "_active_editor"):
            return owner._active_editor()
        return getattr(owner, "_editor_widget", None)

    def _editor_segments(self) -> list[dict]:
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_get_current_segments"):
            try:
                segs = [seg for seg in editor._get_current_segments() if not seg.get("is_gap")]
                if segs:
                    return segs
            except Exception:
                pass
        for candidate in (
            getattr(editor, "_cached_segs", None) if editor is not None else None,
            getattr(getattr(getattr(editor, "timeline", None), "canvas", None), "segments", None) if editor is not None else None,
        ):
            if candidate:
                return [dict(seg) for seg in candidate if not seg.get("is_gap")]
        return []

    def _project_path(self) -> str:
        owner = self.owner
        return str(getattr(owner, "_current_project_path", "") or "") if owner is not None else ""

    def _ensure_project_file(self, segments: list[dict]) -> str:
        project_path = self._project_path()
        if project_path:
            return project_path
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_auto_save_project"):
            try:
                editor._auto_save_project(segments)
            except Exception:
                pass
        return self._project_path()

    def _load_project_roughcut_state(self, signature: str) -> None:
        project_path = self._project_path()
        self._stored_roughcut_result = None
        if not project_path or not os.path.exists(project_path):
            return None
        try:
            with open(project_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
        state = data.get("roughcut_state", {}) or {}
        if state.get("source_signature") == signature:
            edits = state.get("user_edits", {})
            if isinstance(edits, dict):
                self._user_edits = {
                    str(key): dict(value)
                    for key, value in edits.items()
                    if isinstance(value, dict)
                }
            restored = roughcut_result_from_dict(state)
            if restored.chapters and restored.edl_segments:
                self._stored_roughcut_result = restored
                return restored
            return None
        self._user_edits = {}
        return None

    def _persist_roughcut_state(self) -> None:
        if self._result is None:
            return
        segments = self._editor_segments()
        project_path = self._ensure_project_file(segments)
        if not project_path:
            return
        try:
            save_project(
                project_path,
                segments=segments,
                roughcut_state=self._roughcut_state_payload(),
                active_work_mode="roughcut",
            )
        except Exception:
            pass

    def _roughcut_state_payload(self) -> dict:
        result = self._result
        return {
            "schema": "ai_subtitle_studio.roughcut_state.v1",
            "source_signature": self._source_signature,
            "source_media": self._media_label(),
            "editor_mode": self._project_editor_mode(),
            "media_files": self._project_media_files(),
            "clip_boundaries": self._clip_boundaries(),
            "user_edits": self._user_edits,
            "segments": [asdict(segment) for segment in result.segments],
            "chapters": [asdict(chapter) for chapter in result.chapters],
            "edit_decisions": [asdict(decision) for decision in result.edit_decisions],
            "edl_segments": [asdict(segment) for segment in result.edl_segments],
            "guide_markdown": result.guide_markdown,
            "warnings": list(result.warnings),
        }

    def _media_path(self) -> str:
        editor = self._active_editor()
        return str(getattr(editor, "media_path", "") or getattr(getattr(editor, "sm", None), "current_file", "") or "")

    def _media_label(self) -> str:
        owner = self.owner
        files = list(getattr(owner, "_multiclip_files", []) or []) if owner is not None else []
        if len(files) > 1:
            return f"멀티클립 {len(files)}개"
        media_path = self._media_path()
        return os.path.basename(media_path) if media_path else "현재 에디터"

    def _project_media_files(self) -> list[str]:
        owner = self.owner
        files = list(getattr(owner, "_multiclip_files", []) or []) if owner is not None else []
        if files:
            return files
        project_path = self._project_path()
        if project_path and os.path.exists(project_path):
            try:
                with open(project_path, "r", encoding="utf-8") as f:
                    return project_media_files(json.load(f))
            except Exception:
                pass
        media_path = self._media_path()
        return [media_path] if media_path else []

    def _project_editor_mode(self) -> str:
        project_path = self._project_path()
        if project_path and os.path.exists(project_path):
            try:
                with open(project_path, "r", encoding="utf-8") as f:
                    return project_mode(json.load(f))
            except Exception:
                pass
        return "multiclip" if len(self._project_media_files()) > 1 else "single"

    def _clip_boundaries(self, fallback_duration: float | None = None) -> list[dict]:
        owner = self.owner
        boundaries = list(getattr(owner, "_multiclip_boundaries", []) or []) if owner is not None else []
        if boundaries:
            return boundaries
        media_path = self._media_path()
        if not media_path:
            return []
        duration = float(fallback_duration or 0.0)
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "video_player"):
            duration = max(duration, float(getattr(editor.video_player, "total_time", 0.0) or 0.0))
        if duration <= 0.0 and self._result is not None and self._result.edl_segments:
            duration = max((float(seg.timeline_end or seg.source_end) for seg in self._result.edl_segments), default=0.0)
        return [{"start": 0.0, "end": duration, "file": media_path, "name": os.path.basename(media_path)}] if duration > 0 else []

    def _with_project_edl_mapping(self, result, media_duration: float):
        mapped = map_edl_segments_to_clip_sources(result.edl_segments, self._clip_boundaries(media_duration))
        if not mapped:
            return result
        guide = build_markdown_guide(result.chapters, result.edit_decisions, mapped)
        return replace(result, edl_segments=tuple(mapped), guide_markdown=guide)

    def refresh_from_editor(self, force_reanalyze: bool = False):
        segments = self._editor_segments()
        media_path = self._media_path()
        if not segments:
            project_path = self._project_path()
            if project_path and os.path.exists(project_path):
                try:
                    with open(project_path, "r", encoding="utf-8") as f:
                        segments = project_segments_to_editor(json.load(f))
                except Exception:
                    segments = []
        if not segments:
            self._set_empty_state()
            return

        self._source_signature = segment_signature(segments)
        stored = self._load_project_roughcut_state(self._source_signature)
        if stored is not None and not force_reanalyze:
            self._result = stored
            self.source_lbl.setText(self._media_label())
            self._populate_result()
            self._persist_roughcut_state()
            return

        media_duration = max((float(seg.get("end", 0.0) or 0.0) for seg in segments), default=0.0)
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "video_player"):
            media_duration = max(media_duration, float(getattr(editor.video_player, "total_time", 0.0) or 0.0))
        result = run_roughcut_pipeline(
            segments,
            media_duration=media_duration,
            source_path=media_path,
        )
        self._result = self._with_project_edl_mapping(result, media_duration)
        self.source_lbl.setText(self._media_label())
        self._populate_result()
        self._persist_roughcut_state()
