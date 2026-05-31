# Version: 03.14.00
# Phase: PHASE2
from __future__ import annotations

import os
import tempfile
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

from core.project.project_context import (
    project_clip_boundaries,
    project_media_files,
    project_mode,
    project_segments_to_editor,
    segment_signature,
)
from core.project.project_io import read_project_file
from core.project.project_manager import save_project
from core.settings import load_settings
from core.video_codec import roughcut_render_mode
from core.roughcut import (
    build_edl_segments,
    build_concat_render_plan,
    build_ffmpeg_subtitle_burnin_command,
    build_markdown_guide,
    edl_to_dict,
    format_srt,
    map_edl_segments_to_clip_sources,
    retime_subtitles_for_edl,
    roughcut_result_from_dict,
    run_roughcut_pipeline,
    merge_roughcut_settings,
)

ROUGHCUT_STATE_SCHEMA = "ai_subtitle_studio.roughcut_state.v2"
ROUGHCUT_CANDIDATE_SCHEMA = "ai_subtitle_studio.roughcut_candidate.v2"


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
            data = read_project_file(project_path)
        except Exception:
            return None
        state = data.get("roughcut_state", {}) or {}
        self._roughcut_candidates = self._normalize_roughcut_candidates(state)
        self._selected_candidate_id = str(state.get("selected_candidate_id") or "")
        self._segment_order = list(state.get("segment_order") or [])
        self._chapter_order = list(state.get("chapter_order") or [])
        candidate = self._selected_candidate_for_signature(signature)
        self._refresh_candidate_combo()
        if candidate is not None:
            self._apply_candidate_payload(candidate, persist=False)
            restored = roughcut_result_from_dict(candidate)
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
                user_settings=load_settings(),
                roughcut_state=self._roughcut_state_payload(),
                active_work_mode="roughcut",
            )
        except Exception:
            pass

    def _roughcut_state_payload(self) -> dict:
        result = self._result
        result = self._result_with_user_edits(result)
        current = self._current_candidate_payload(result)
        candidates = self._merged_candidates(current)
        payload = dict(current)
        payload.update({
            "schema": ROUGHCUT_STATE_SCHEMA,
            "schema_version": "roughcut_state.v2",
            "legacy_read_compatible": ("ai_subtitle_studio.roughcut_state.v1",),
            "settings": self._roughcut_settings_payload(),
            "candidates": candidates,
            "selected_candidate_id": self._selected_candidate_id,
            "segment_order": list(getattr(self, "_segment_order", []) or []),
            "chapter_order": list(getattr(self, "_chapter_order", []) or []),
            "candidate_count": len(candidates),
        })
        self._roughcut_candidates = candidates
        self._refresh_candidate_combo()
        return payload

    def _normalize_roughcut_candidates(self, state: dict) -> list[dict]:
        raw = state.get("candidates", [])
        candidates: list[dict] = []
        if isinstance(raw, list):
            for index, item in enumerate(raw, start=1):
                if not isinstance(item, dict):
                    continue
                candidate = dict(item)
                candidate.setdefault("candidate_id", f"roughcut_candidate_{index:03d}")
                candidate.setdefault("name", f"후보 {index}")
                candidate.setdefault("created_at", "")
                candidates.append(candidate)
        if not candidates and (state.get("chapters") or state.get("edl_segments")):
            legacy = dict(state)
            legacy.setdefault("candidate_id", "roughcut_candidate_legacy")
            legacy.setdefault("name", "기존 후보")
            legacy.setdefault("created_at", "")
            candidates.append(legacy)
        return candidates

    def _selected_candidate_for_signature(self, signature: str) -> dict | None:
        candidates = list(getattr(self, "_roughcut_candidates", []) or [])
        selected_id = str(getattr(self, "_selected_candidate_id", "") or "")
        selected = self._candidate_by_id(selected_id)
        if selected is not None and selected.get("source_signature") == signature:
            return selected
        for candidate in candidates:
            if candidate.get("source_signature") == signature:
                self._selected_candidate_id = str(candidate.get("candidate_id") or "")
                return candidate
        # Saved roughcut projects can reopen with an editor signature that no longer
        # exactly matches the candidate source snapshot. In that case, prefer the
        # explicitly selected candidate instead of collapsing back to placeholder UI.
        if selected is not None:
            return selected
        return None

    def _candidate_by_id(self, candidate_id: str) -> dict | None:
        candidate_id = str(candidate_id or "")
        for candidate in list(getattr(self, "_roughcut_candidates", []) or []):
            if str(candidate.get("candidate_id") or "") == candidate_id:
                return candidate
        return None

    def _new_candidate_id(self) -> str:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"roughcut_{stamp}"
        existing = {str(item.get("candidate_id") or "") for item in getattr(self, "_roughcut_candidates", []) or []}
        if base not in existing:
            return base
        index = 2
        while f"{base}_{index}" in existing:
            index += 1
        return f"{base}_{index}"

    def _current_candidate_name(self, candidate_id: str) -> str:
        existing = self._candidate_by_id(candidate_id)
        if existing is not None and existing.get("name"):
            return str(existing.get("name"))
        count = len(getattr(self, "_roughcut_candidates", []) or []) + 1
        return f"후보 {count} · {datetime.now().strftime('%H:%M')}"

    def _current_candidate_payload(self, result) -> dict:
        if result is None:
            return {}
        candidate_id = str(getattr(self, "_selected_candidate_id", "") or "")
        if not candidate_id:
            candidate_id = self._new_candidate_id()
            self._selected_candidate_id = candidate_id
        existing = self._candidate_by_id(candidate_id) or {}
        payload = {
            "candidate_id": candidate_id,
            "name": self._current_candidate_name(candidate_id),
            "created_at": str(existing.get("created_at") or datetime.now().isoformat(timespec="seconds")),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "schema": ROUGHCUT_CANDIDATE_SCHEMA,
            "schema_version": "roughcut_candidate.v2",
            "source_signature": self._source_signature,
            "source_media": self._media_label(),
            "editor_mode": self._project_editor_mode(),
            "media_files": self._project_media_files(),
            "clip_boundaries": self._clip_boundaries(),
            "subtitle_segment_count": len(self._editor_segments()),
            "selected_chapter_id": self._current_selected_chapter_id(),
            "safety_filter": self._current_safety_filter_value(),
            "segment_order": list(getattr(self, "_segment_order", []) or []),
            "chapter_order": list(getattr(self, "_chapter_order", []) or []),
            "user_edits": self._user_edits,
            "segments": [asdict(segment) for segment in result.segments],
            "chapters": [asdict(chapter) for chapter in result.chapters],
            "edit_decisions": [asdict(decision) for decision in result.edit_decisions],
            "edl_segments": [asdict(segment) for segment in result.edl_segments],
            "edl": [asdict(segment) for segment in result.edl_segments],
            "guide_markdown": result.guide_markdown,
            "markdown_guide": result.guide_markdown,
            "video_summary": getattr(result, "video_summary", ""),
            "packed_phrases": [asdict(phrase) for phrase in getattr(result, "packed_phrases", ())],
            "chunks": [asdict(chunk) for chunk in getattr(result, "chunks", ())],
            "cut_points": [asdict(point) for point in getattr(result, "cut_points", ())],
            "title_suggestions": [asdict(item) for item in getattr(result, "title_suggestions", ())],
            "draft_state": asdict(result.draft_state) if getattr(result, "draft_state", None) is not None else None,
            "roughcut_export_style": dict(getattr(self, "_roughcut_export_style", {}) or {}),
            "result_schema_version": getattr(result, "schema_version", "roughcut_result.v1"),
            "warnings": list(result.warnings),
        }
        payload["outputs"] = self._candidate_outputs_payload(result)
        return payload

    def _roughcut_settings_payload(self) -> dict:
        try:
            return merge_roughcut_settings(load_settings())
        except Exception:
            return merge_roughcut_settings({})

    def _candidate_outputs_payload(self, result) -> dict:
        outputs = {
            "guide_markdown": str(getattr(result, "guide_markdown", "") or ""),
            "edl": edl_to_dict(
                result.edl_segments,
                metadata={"source": self._media_path()},
                chapters=result.chapters,
                major_segments=result.segments,
            ),
            "retimed_srt": "",
            "render_plan": None,
            "subtitle_burnin_command": (),
        }
        try:
            retimed = retime_subtitles_for_edl(self._editor_segments(), result.edl_segments, chapters=result.chapters)
            outputs["retimed_srt"] = format_srt(retimed)
        except Exception:
            outputs["retimed_srt"] = ""
        try:
            media_path = self._media_path()
            source_suffix = Path(media_path).suffix if media_path else ".mp4"
            output_path = self._default_output_path(f"_roughcut{source_suffix or '.mp4'}")
            temp_dir = Path(tempfile.gettempdir()) / "ai_subtitle_studio_roughcut"
            plan = build_concat_render_plan(result.edl_segments, output_path, temp_dir, render_mode=roughcut_render_mode())
            srt_path = self._default_output_path("_roughcut.srt")
            subtitled_path = output_path.with_name(f"{output_path.stem}_subtitled{output_path.suffix or '.mp4'}")
            outputs["render_plan"] = asdict(plan)
            outputs["subtitle_burnin_command"] = build_ffmpeg_subtitle_burnin_command(output_path, srt_path, subtitled_path)
        except Exception:
            outputs["render_plan"] = None
        return outputs

    def _merged_candidates(self, current: dict) -> list[dict]:
        candidates = []
        seen = set()
        current_id = str(current.get("candidate_id") or "")
        for item in list(getattr(self, "_roughcut_candidates", []) or []):
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("candidate_id") or "")
            if current_id and item_id == current_id:
                candidates.append(dict(current))
                seen.add(current_id)
            elif item_id and item_id not in seen:
                candidates.append(dict(item))
                seen.add(item_id)
        if current_id and current_id not in seen:
            candidates.append(dict(current))
        return candidates

    def _apply_candidate_payload(self, candidate: dict, persist: bool = True) -> None:
        self._selected_candidate_id = str(candidate.get("candidate_id") or "")
        self._source_signature = str(candidate.get("source_signature") or self._source_signature)
        if hasattr(self, "_set_reorder_summary_label"):
            self._set_reorder_summary_label("재정렬 없음", active=False)
        edits = candidate.get("user_edits", {})
        self._user_edits = {
            str(key): dict(value)
            for key, value in edits.items()
            if isinstance(value, dict)
        } if isinstance(edits, dict) else {}
        self._restored_selected_chapter_id = str(candidate.get("selected_chapter_id") or "")
        self._restored_safety_filter = str(candidate.get("safety_filter") or "전체")
        self._segment_order = list(candidate.get("segment_order") or [])
        self._chapter_order = list(candidate.get("chapter_order") or [])
        restored = roughcut_result_from_dict(candidate)
        if restored.chapters and restored.edl_segments:
            self._result = restored
        style = candidate.get("roughcut_export_style", {})
        if isinstance(style, dict):
            self._roughcut_export_style = dict(style)
            if hasattr(self, "style_panel"):
                self.style_panel.set_style(style)
        if hasattr(self, "source_lbl"):
            self.source_lbl.setText(str(candidate.get("source_media") or self._media_label()))
        self._sync_candidate_state_label(candidate)
        if persist:
            self._populate_result()
            self.render_status_lbl.setText("후보 선택")
            if candidate.get("source_signature") != segment_signature(self._editor_segments()):
                self.preview_summary_lbl.setText("선택한 후보의 기준 자막 상태가 현재 자막과 다릅니다.")
            self._persist_roughcut_state()

    def _refresh_candidate_combo(self) -> None:
        combo = getattr(self, "candidate_combo", None)
        self._refreshing_candidate_combo = True
        if combo is not None:
            combo.blockSignals(True)
            combo.clear()
        candidates = list(getattr(self, "_roughcut_candidates", []) or [])
        if combo is not None:
            if not candidates:
                combo.addItem("후보 없음", "")
            else:
                current_sig = self._current_editor_signature()
                for index, candidate in enumerate(candidates, start=1):
                    name = str(candidate.get("name") or f"후보 {index}")
                    suffix = "현재" if candidate.get("source_signature") == current_sig else "저장된 자막"
                    combo.addItem(f"{name} · {suffix}", str(candidate.get("candidate_id") or ""))
                selected = str(getattr(self, "_selected_candidate_id", "") or "")
                if selected:
                    idx = combo.findData(selected)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
            combo.blockSignals(False)
        self._refreshing_candidate_combo = False
        refresh_frames = getattr(self, "_refresh_candidate_preview_frames", None)
        if callable(refresh_frames):
            refresh_frames()
        self._sync_candidate_state_label()

    def _on_candidate_combo_changed(self, index: int) -> None:
        if getattr(self, "_refreshing_candidate_combo", False):
            return
        combo = getattr(self, "candidate_combo", None)
        if combo is None or index < 0:
            return
        candidate_id = str(combo.itemData(index) or "")
        if not candidate_id:
            self._sync_candidate_state_label(None)
            return
        if candidate_id == getattr(self, "_selected_candidate_id", ""):
            self._sync_candidate_state_label(self._candidate_by_id(candidate_id))
            return
        candidate = self._candidate_by_id(candidate_id)
        if candidate is not None:
            self._apply_candidate_payload(candidate, persist=True)

    def _sync_candidate_state_label(self, candidate: dict | None = None) -> None:
        if not hasattr(self, "_set_candidate_state_label"):
            return
        if candidate is None:
            selected = str(getattr(self, "_selected_candidate_id", "") or "")
            if selected:
                candidate = self._candidate_by_id(selected)
            if candidate is None:
                candidates = list(getattr(self, "_roughcut_candidates", []) or [])
                candidate = candidates[0] if candidates else None
        if not isinstance(candidate, dict):
            self._set_candidate_state_label("none")
            return
        current_sig = self._current_editor_signature()
        candidate_sig = str(candidate.get("source_signature") or "")
        self._set_candidate_state_label("current" if candidate_sig and candidate_sig == current_sig else "stale")

    def _current_editor_signature(self) -> str:
        try:
            current_sig = segment_signature(self._editor_segments())
        except Exception:
            current_sig = ""
        return str(current_sig or getattr(self, "_source_signature", "") or "")

    def _current_selected_chapter_id(self) -> str:
        major_panel = getattr(self, "major_panel", None)
        selected = str(getattr(major_panel, "_selected_chapter_id", "") or "")
        if selected:
            return selected
        restored = str(getattr(self, "_restored_selected_chapter_id", "") or "")
        if restored:
            return restored
        row = int(getattr(self, "_preview_row", -1))
        if row >= 0 and hasattr(self, "_chapter_for_row"):
            chapter = self._chapter_for_row(row)
            if chapter is not None:
                return str(getattr(chapter, "chapter_id", "") or "")
        return ""

    def _current_safety_filter_value(self) -> str:
        combo = getattr(self, "safety_filter_combo", None)
        if combo is None:
            return "전체"
        return str(combo.currentText() or "전체")

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
                return project_media_files(read_project_file(project_path))
            except Exception:
                pass
        media_path = self._media_path()
        return [media_path] if media_path else []

    def _project_editor_mode(self) -> str:
        project_path = self._project_path()
        if project_path and os.path.exists(project_path):
            try:
                return project_mode(read_project_file(project_path))
            except Exception:
                pass
        return "multiclip" if len(self._project_media_files()) > 1 else "single"

    def _clip_boundaries(self, fallback_duration: float | None = None) -> list[dict]:
        owner = self.owner
        boundaries = list(getattr(owner, "_multiclip_boundaries", []) or []) if owner is not None else []
        if boundaries:
            return boundaries
        project_path = self._project_path()
        if project_path and os.path.exists(project_path):
            try:
                boundaries = project_clip_boundaries(read_project_file(project_path))
                if boundaries:
                    return boundaries
            except Exception:
                pass
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

    def _result_with_user_edits(self, result=None):
        result = result or self._result
        if result is None:
            return result
        ordered_segments, ordered_chapters = self._apply_segment_order(result.segments, result.chapters)
        ordered_chapters = self._apply_chapter_order(ordered_chapters)
        chapters = []
        for chapter in ordered_chapters:
            edit = self._user_edits.get(chapter.chapter_id, {})
            title = str(edit.get("title") or chapter.title)
            tags_text = str(edit.get("tags") or "")
            tags = tuple(part.strip() for part in tags_text.split(",") if part.strip()) if tags_text else chapter.tags
            chapters.append(replace(chapter, title=title, tags=tags))
        chapter_index = {chapter.chapter_id: index for index, chapter in enumerate(chapters)}
        decisions = []
        for decision in result.edit_decisions:
            edit = self._user_edits.get(decision.segment_id, {})
            action = str(edit.get("action") or decision.action) if edit else decision.action
            source_start = self._edit_float(edit.get("trim_start"), decision.source_start) if edit else decision.source_start
            source_end = self._edit_float(edit.get("trim_end"), decision.source_end) if edit else decision.source_end
            if source_start is not None and source_end is not None and source_end <= source_start:
                source_end = source_start + 0.05
            reason = str(decision.reason or "")
            edit_reason = str(edit.get("reason") or "") if edit else ""
            if edit_reason and edit_reason not in reason:
                reason = f"{reason}; {edit_reason}" if reason else edit_reason
            target_index = chapter_index.get(decision.segment_id, decision.output_order if decision.output_order is not None else len(chapter_index))
            decisions.append(
                replace(
                    decision,
                    action=action if action in {"keep", "trim", "remove", "highlight", "move"} else decision.action,
                    source_start=source_start,
                    source_end=source_end,
                    reason=reason,
                    output_order=int(target_index),
                )
            )
        base_edl = build_edl_segments(self._media_path(), decisions, chapters)
        mapped_edl = map_edl_segments_to_clip_sources(base_edl, self._clip_boundaries()) or base_edl
        guide = build_markdown_guide(chapters, decisions, mapped_edl)
        return replace(
            result,
            segments=tuple(ordered_segments),
            chapters=tuple(chapters),
            edit_decisions=tuple(decisions),
            edl_segments=tuple(mapped_edl),
            guide_markdown=guide,
        )

    def _apply_segment_order(self, segments, chapters):
        ordered_segments = list(segments or ())
        ordered_chapters = list(chapters or ())
        order = [str(segment_id) for segment_id in list(getattr(self, "_segment_order", []) or []) if str(segment_id or "")]
        if not order:
            self._segment_order = [self._segment_key(segment, index) for index, segment in enumerate(ordered_segments)]
            return tuple(ordered_segments), tuple(ordered_chapters)
        segment_lookup = {
            self._segment_key(segment, index): segment
            for index, segment in enumerate(ordered_segments)
        }
        ordered_segments = [segment_lookup[segment_id] for segment_id in order if segment_id in segment_lookup]
        ordered_segments.extend(
            segment
            for key, segment in segment_lookup.items()
            if key not in order
        )
        major_sequence = [str(getattr(segment, "major_id", "") or self._segment_key(segment, index)) for index, segment in enumerate(ordered_segments)]
        chapter_buckets: dict[str, list] = {}
        for chapter in chapters or ():
            bucket_key = str(getattr(chapter, "major_id", "") or "")
            chapter_buckets.setdefault(bucket_key, []).append(chapter)
        reordered: list = []
        for bucket_key in major_sequence:
            reordered.extend(chapter_buckets.pop(bucket_key, []))
        for remaining in chapter_buckets.values():
            reordered.extend(remaining)
        self._segment_order = [self._segment_key(segment, index) for index, segment in enumerate(ordered_segments)]
        return tuple(ordered_segments), tuple(reordered)

    def _apply_chapter_order(self, chapters):
        ordered_chapters = list(chapters or ())
        order = [str(chapter_id) for chapter_id in list(getattr(self, "_chapter_order", []) or []) if str(chapter_id or "")]
        if not order:
            self._chapter_order = [str(getattr(chapter, "chapter_id", "") or "") for chapter in ordered_chapters if str(getattr(chapter, "chapter_id", "") or "")]
            return tuple(ordered_chapters)
        chapter_lookup = {
            str(getattr(chapter, "chapter_id", "") or ""): chapter
            for chapter in ordered_chapters
            if str(getattr(chapter, "chapter_id", "") or "")
        }
        reordered = [chapter_lookup[chapter_id] for chapter_id in order if chapter_id in chapter_lookup]
        reordered.extend(
            chapter
            for chapter_id, chapter in chapter_lookup.items()
            if chapter_id not in order
        )
        self._chapter_order = [str(getattr(chapter, "chapter_id", "") or "") for chapter in reordered if str(getattr(chapter, "chapter_id", "") or "")]
        return tuple(reordered)

    def _segment_key(self, segment, index: int) -> str:
        return str(getattr(segment, "segment_id", "") or getattr(segment, "major_id", "") or f"segment_{index:04d}")

    def _edit_float(self, value, fallback):
        try:
            if value is None or value == "":
                return fallback
            return float(value)
        except (TypeError, ValueError):
            return fallback


    def _cut_boundary_placeholder_enabled(self) -> bool:
        """
        컷 경계 기반 '주제없음' 중분류 placeholder 사용 여부.
        """
        try:
            settings = load_settings()
        except Exception:
            settings = {}
        return bool(settings.get("cut_boundary_detection_enabled", settings.get("scan_cut_enabled", True)))

    def _load_project_cut_boundaries(self) -> list[dict]:
        """
        프로젝트 JSON의 analysis.cut_boundaries를 읽는다.
        """
        project_path = self._project_path()
        if not project_path or not os.path.exists(project_path):
            return []
        try:
            data = read_project_file(project_path)
        except Exception:
            return []

        analysis = data.get("analysis", {}) or {}
        raw = analysis.get("cut_boundaries", []) or []
        boundaries = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                sec = float(item.get("timeline_sec", item.get("time", 0.0)) or 0.0)
            except Exception:
                continue
            if sec <= 0:
                continue
            row = dict(item)
            row["_sec"] = sec
            boundaries.append(row)

        boundaries.sort(key=lambda item: float(item.get("_sec", 0.0) or 0.0))
        return boundaries

    def _cut_boundary_placeholder_duration(self, segments: list[dict]) -> float:
        """
        placeholder 생성을 위한 총 길이 추정.
        """
        duration = 0.0
        try:
            duration = max(duration, max((float(seg.get("end", seg.get("timeline_end", 0.0)) or 0.0) for seg in segments), default=0.0))
        except Exception:
            pass

        try:
            editor = self._active_editor()
            if editor is not None and hasattr(editor, "video_player"):
                duration = max(duration, float(getattr(editor.video_player, "total_time", 0.0) or 0.0))
        except Exception:
            pass

        try:
            for boundary in self._clip_boundaries(duration):
                duration = max(duration, float(boundary.get("end", 0.0) or 0.0))
        except Exception:
            pass

        return max(0.0, duration)

    def _cut_boundary_major_id(self, index: int) -> str:
        """
        1 -> A, 2 -> B ... 26 -> Z, 27 -> AA.
        """
        index = max(1, int(index))
        letters = ""
        while index:
            index, rem = divmod(index - 1, 26)
            letters = chr(65 + rem) + letters
        return letters

    def _subtitle_ids_for_interval(self, segments: list[dict], start: float, end: float) -> tuple[int, ...]:
        ids = []
        for idx, seg in enumerate(segments, start=1):
            try:
                s = float(seg.get("start", seg.get("timeline_start", 0.0)) or 0.0)
                e = float(seg.get("end", seg.get("timeline_end", s)) or s)
            except Exception:
                continue
            if max(s, start) < min(e, end):
                try:
                    ids.append(int(seg.get("index", seg.get("line", idx)) or idx))
                except Exception:
                    ids.append(idx)
        return tuple(sorted(set(ids)))

    def _build_cut_boundary_topicless_result(self, segments: list[dict]):
        """
        컷 경계 기반 회색 '주제없음' 중분류 결과를 만든다.

        LLM이 아직 중분류 주제/요약을 만들기 전의 임시 상태다.
        """
        if not self._cut_boundary_placeholder_enabled():
            return None

        boundaries = self._load_project_cut_boundaries()
        if not boundaries:
            return None

        duration = self._cut_boundary_placeholder_duration(segments)
        if duration <= 0:
            return None

        from core.roughcut.models import (
            RoughCutResult,
            RoughCutSegment,
            RoughCutMinorGroup,
            ChapterMetadata,
            EditDecision,
            EDLSegment,
            RoughCutDraftState,
        )

        points = [0.0]
        for item in boundaries:
            sec = float(item.get("_sec", 0.0) or 0.0)
            if 0.05 < sec < duration - 0.05:
                points.append(sec)
        points.append(duration)

        # 중복/근접 boundary 정리
        cleaned = []
        for sec in sorted(points):
            if not cleaned or abs(sec - cleaned[-1]) >= 0.05:
                cleaned.append(sec)

        if len(cleaned) < 2:
            return None

        rough_segments = []
        chapters = []
        decisions = []
        edl_segments = []

        source_path = self._media_path()
        output_cursor = 0.0

        for idx, (start, end) in enumerate(zip(cleaned, cleaned[1:]), start=1):
            start = max(0.0, float(start))
            end = max(start, float(end))
            if end <= start + 0.05:
                continue

            major_id = self._cut_boundary_major_id(idx)
            segment_id = f"cut_boundary_major_{major_id}"
            chapter_id = f"cut_boundary_chapter_{major_id}1"
            minor_id = f"cut_boundary_minor_{major_id}1"
            subtitle_ids = self._subtitle_ids_for_interval(segments, start, end)

            minor = RoughCutMinorGroup(
                minor_id=minor_id,
                major_id=major_id,
                code=f"{major_id}1",
                title="주제없음",
                start=start,
                end=end,
                subtitle_ids=subtitle_ids,
                chapter_ids=(chapter_id,),
                summary="컷 경계 기반 임시 소분류입니다.",
                tags=("컷경계", "주제없음"),
                status="provisional",
                safety="acceptable",
                confidence=0.0,
                needs_review=True,
            )

            rough_segments.append(
                RoughCutSegment(
                    segment_id=segment_id,
                    start=start,
                    end=end,
                    subtitle_ids=subtitle_ids,
                    title="주제없음",
                    summary="컷 경계 기반 임시 중분류입니다. LLM 분석 전 상태입니다.",
                    tags=("컷경계", "주제없음", "임시"),
                    story_role="",
                    narrative_function="",
                    importance_score=0.0,
                    can_move=True,
                    can_trim=True,
                    can_remove=True,
                    move_risk="medium",
                    needs_review=True,
                    boundary_confidence=0.0,
                    major_id=major_id,
                    minor_groups=(minor,),
                    status="provisional",
                    safety="acceptable",
                    importance=0.0,
                    llm_summary="주제없음",
                )
            )

            chapters.append(
                ChapterMetadata(
                    chapter_id=chapter_id,
                    title="주제없음",
                    start=start,
                    end=end,
                    summary="컷 경계 기반 임시 챕터입니다. LLM 중분류 결과로 대체 예정입니다.",
                    tags=("컷경계", "주제없음"),
                    segment_ids=(segment_id,),
                    importance_score=0.0,
                    narrative_function="",
                    story_role="",
                    needs_review=True,
                    major_id=major_id,
                    minor_code=f"{major_id}1",
                    confidence=0.0,
                    boundary_status="provisional",
                )
            )

            decisions.append(
                EditDecision(
                    segment_id=segment_id,
                    action="keep",
                    reason="컷 경계 기반 주제없음 임시 중분류",
                    source_start=start,
                    source_end=end,
                    output_order=idx,
                    safety="acceptable",
                    confidence=0.0,
                )
            )

            output_start = output_cursor
            output_end = output_start + (end - start)
            output_cursor = output_end

            edl_segments.append(
                EDLSegment(
                    source_path=source_path,
                    segment_id=segment_id,
                    source_start=start,
                    source_end=end,
                    output_start=output_start,
                    output_end=output_end,
                    action="keep",
                    chapter_id=chapter_id,
                    story_role="",
                    reason="컷 경계 기반 주제없음 임시 중분류",
                    timeline_start=start,
                    timeline_end=end,
                    clip_index=None,
                )
            )

        if not rough_segments:
            return None

        return RoughCutResult(
            segments=tuple(rough_segments),
            chapters=tuple(chapters),
            edit_decisions=tuple(decisions),
            edl_segments=tuple(edl_segments),
            guide_markdown="컷 경계 기반 '주제없음' 임시 중분류입니다. LLM 분석 결과로 대체 예정입니다.",
            warnings=("cut_boundary_topicless_placeholder",),
            video_summary="컷 경계 기반 주제없음 임시 중분류",
            draft_state=RoughCutDraftState(
                draft_id="cut_boundary_topicless",
                status="review",
                selected_major_id=rough_segments[0].major_id if rough_segments else "",
                selected_minor_code=f"{rough_segments[0].major_id}1" if rough_segments else "",
                autosave_enabled=True,
                last_saved_at=datetime.now().isoformat(timespec="seconds"),
                notes="컷 경계 기반 주제없음 placeholder",
            ),
            schema_version="roughcut_result.cut_boundary_placeholder.v1",
        )

    def refresh_from_editor(self, force_reanalyze: bool = False, analyze_if_missing: bool = True):
        segments = self._editor_segments()
        media_path = self._media_path()
        if not segments:
            project_path = self._project_path()
            if project_path and os.path.exists(project_path):
                try:
                    segments = project_segments_to_editor(read_project_file(project_path))
                except Exception:
                    segments = []
        if not segments:
            topicless_result = self._topicless_placeholder_result_from_project()
            if topicless_result is not None:
                self._result = topicless_result
                self.source_lbl.setText(f"{self._media_label()} · 컷 경계 주제없음")
                if hasattr(self, "_set_roughcut_status"):
                    self._set_roughcut_status("컷 경계 기반 주제없음", 100)
                if hasattr(self, "_append_roughcut_log"):
                    self._append_roughcut_log(
                        f"컷 경계 기반 주제없음 중분류 {len(topicless_result.segments)}개를 표시했습니다.",
                        "done",
                    )
                self._populate_result()
                return

            self._set_empty_state()
            return

        self._source_signature = segment_signature(segments)
        if force_reanalyze:
            self._selected_candidate_id = ""
            self._user_edits = {}
            self._segment_order = []
            self._chapter_order = []
        stored = self._load_project_roughcut_state(self._source_signature)
        if force_reanalyze:
            self._selected_candidate_id = ""
            self._user_edits = {}
            self._segment_order = []
            self._chapter_order = []
        if stored is None and not force_reanalyze:
            topicless_result = self._topicless_placeholder_result_from_project()
            if topicless_result is not None:
                self._result = topicless_result
                self.source_lbl.setText(f"{self._media_label()} · 컷 경계 주제없음")
                if hasattr(self, "_set_roughcut_status"):
                    self._set_roughcut_status("컷 경계 기반 주제없음", 100)
                self._populate_result()
                return

        if stored is not None and not force_reanalyze:
            self._result = stored
            self.source_lbl.setText(self._media_label())
            if hasattr(self, "_set_roughcut_status"):
                self._set_roughcut_status("후보 복원", 100)
            if hasattr(self, "_append_roughcut_log"):
                self._append_roughcut_log("저장된 러프컷 후보를 복원했습니다.", "done")
            self._populate_result()
            self._persist_roughcut_state()
            return

        # CUT_BOUNDARY_TOPICLESS_PLACEHOLDER
        # 컷 경계가 사용 중이고 프로젝트에 cut_boundaries가 있으면,
        # LLM 중분류 전 단계로 회색 '주제없음' 중분류를 먼저 구성한다.
        if not force_reanalyze:
            placeholder_result = self._build_cut_boundary_topicless_result(segments)
            if placeholder_result is not None:
                self._result = placeholder_result
                self.source_lbl.setText(f"{self._media_label()} · 컷 경계 주제없음")
                if hasattr(self, "_set_roughcut_status"):
                    self._set_roughcut_status("컷 경계 기반 주제없음", 100)
                if hasattr(self, "_append_roughcut_log"):
                    self._append_roughcut_log(
                        f"컷 경계 기반 주제없음 중분류 {len(placeholder_result.segments)}개를 구성했습니다.",
                        "done",
                    )
                self._populate_result()
                self._persist_roughcut_state()
                return

        if not analyze_if_missing and not force_reanalyze:
            self._result = None
            self._set_empty_state()
            self.source_lbl.setText(f"{self._media_label()} · 분석 대기")
            self.preview_summary_lbl.setText("상단 시작 또는 분석 버튼을 누르면 러프컷 분석을 시작합니다.")
            if hasattr(self, "_set_roughcut_status"):
                self._set_roughcut_status("분석 대기")
            return

        media_duration = max((float(seg.get("end", 0.0) or 0.0) for seg in segments), default=0.0)
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "video_player"):
            media_duration = max(media_duration, float(getattr(editor.video_player, "total_time", 0.0) or 0.0))
        if hasattr(self, "_set_roughcut_status"):
            self._set_roughcut_status("분석 중", 45)
        if hasattr(self, "log_panel"):
            self.log_panel.set_reading_rows(len(segments))
        result = run_roughcut_pipeline(
            segments,
            media_duration=media_duration,
            source_path=media_path,
            use_llm=bool(self._roughcut_settings_payload().get("roughcut_llm_enabled", False)),
            settings=self._roughcut_settings_payload(),
        )
        self._result = self._result_with_user_edits(self._with_project_edl_mapping(result, media_duration))
        self.source_lbl.setText(self._media_label())
        if hasattr(self, "_set_roughcut_status"):
            self._set_roughcut_status("결과 구성", 85)
        if hasattr(self, "_append_roughcut_log"):
            self._append_roughcut_log(
                f"중분류 {len(getattr(self._result, 'segments', ()) or ())}개와 제목 후보 {len(getattr(self._result, 'title_suggestions', ()) or ())}개를 구성했습니다.",
                "done",
            )
        self._populate_result()
        self._persist_roughcut_state()


from ui.roughcut.roughcut_topicless import install_frame_synced_topicless_placeholder

install_frame_synced_topicless_placeholder(RoughcutStateMixin)
