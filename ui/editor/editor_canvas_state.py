"""
Shared canvas/document state application for editor open flows.

SRT open and project open should both hydrate the editor canvas through the
same helpers so subtitle-only and project-backed loads behave identically
once the segments are in memory.
"""

from __future__ import annotations

from core.frame_time import clamp_segments_to_duration, normalize_fps, normalize_segments_to_frame_grid
from ui.editor.editor_session_model import EditorSessionModel


class EditorCanvasStateMixin:
    def _loaded_canvas_total_duration(self) -> float:
        player = getattr(self, "video_player", None)
        try:
            return max(0.0, float(getattr(player, "total_time", 0.0) or 0.0))
        except Exception:
            return 0.0

    def _loaded_canvas_state_fps(self, segments: list[dict] | None = None) -> float:
        for seg in ([] if segments is None else segments):
            if not isinstance(seg, dict):
                continue
            frame_range = seg.get("frame_range", {}) if isinstance(seg.get("frame_range"), dict) else {}
            for key in (
                "timeline_frame_rate",
                "frame_rate",
            ):
                if seg.get(key) not in (None, ""):
                    return normalize_fps(seg.get(key))
            if frame_range.get("timeline_frame_rate") not in (None, ""):
                return normalize_fps(frame_range.get("timeline_frame_rate"))
        return normalize_fps(getattr(self, "video_fps", 30.0) or 30.0)

    def apply_canvas_aux_state(
        self,
        *,
        boundary_times: list[float] | None = None,
        provisional_boundaries: list[dict] | list[float] | None = None,
        voice_activity_segments: list[dict] | None = None,
        stt_preview_segments: list[dict] | None = None,
        stt_preview_subtitle_drafts: bool | None = None,
        schedule_timeline: bool = True,
    ) -> None:
        timeline = getattr(self, "timeline", None)
        if boundary_times is not None and timeline is not None and hasattr(timeline, "set_boundary_times"):
            timeline.set_boundary_times(list(boundary_times or []))

        if provisional_boundaries is not None:
            if hasattr(self, "_set_auto_cut_boundary_scan_lines"):
                self._set_auto_cut_boundary_scan_lines(list(provisional_boundaries or []))
            elif timeline is not None and hasattr(timeline, "set_scan_boundary_times"):
                timeline.set_scan_boundary_times(list(provisional_boundaries or []))

        if voice_activity_segments is not None and hasattr(self, "set_voice_activity_segments"):
            self.set_voice_activity_segments(list(voice_activity_segments or []))

        if stt_preview_segments is not None:
            from ui.timeline.stt_preview_layout import ensure_stt_preview_lane_numbers

            self._live_stt_preview_segments = [
                dict(seg)
                for seg in stt_preview_segments
                if isinstance(seg, dict)
            ]
            ensure_stt_preview_lane_numbers(self._live_stt_preview_segments, mutate=True)

        if stt_preview_subtitle_drafts is not None:
            self._stt_preview_subtitle_drafts_enabled = bool(stt_preview_subtitle_drafts)

        existing_session = getattr(self, "editor_session_model", None)
        if isinstance(existing_session, EditorSessionModel):
            self.editor_session_model = EditorSessionModel.from_canvas_state(
                final_segments=existing_session.final_segments,
                stt_preview_segments=(
                    existing_session.stt_preview_segments
                    if stt_preview_segments is None
                    else stt_preview_segments
                ),
                voice_activity_segments=(
                    existing_session.voice_activity_segments
                    if voice_activity_segments is None
                    else voice_activity_segments
                ),
                boundary_times=(
                    existing_session.boundary_times if boundary_times is None else boundary_times
                ),
                provisional_boundaries=(
                    existing_session.provisional_boundaries
                    if provisional_boundaries is None
                    else provisional_boundaries
                ),
                stt_preview_subtitle_drafts=(
                    existing_session.stt_preview_subtitle_drafts
                    if stt_preview_subtitle_drafts is None
                    else bool(stt_preview_subtitle_drafts)
                ),
            )

        if schedule_timeline and hasattr(self, "_schedule_timeline"):
            self._schedule_timeline()

    def apply_loaded_canvas_state(
        self,
        segments: list[dict],
        *,
        preserve_view: bool = False,
        mark_dirty: bool = False,
        auto_gap_segments_enabled: bool | None = None,
        boundary_times: list[float] | None = None,
        provisional_boundaries: list[dict] | list[float] | None = None,
        voice_activity_segments: list[dict] | None = None,
        stt_preview_segments: list[dict] | None = None,
        stt_preview_subtitle_drafts: bool | None = None,
    ) -> list[dict]:
        ordered = list([] if segments is None else segments)
        if hasattr(self, "_normalize_multiclip_segment_order"):
            ordered = self._normalize_multiclip_segment_order(ordered)
        else:
            ordered = sorted(
                (dict(seg) for seg in ordered if isinstance(seg, dict)),
                key=lambda seg: (
                    float(seg.get("start", 0.0) or 0.0),
                    float(seg.get("end", seg.get("start", 0.0)) or 0.0),
                ),
            )
            for idx, seg in enumerate(ordered):
                seg["line"] = idx

        ordered = normalize_segments_to_frame_grid(
            ordered,
            self._loaded_canvas_state_fps(ordered),
            min_frames=1,
            collapse_micro_gaps=True,
            max_gap_frames=1,
            preserve_order=True,
        )
        total_duration = self._loaded_canvas_total_duration()
        if total_duration > 0.0:
            ordered = clamp_segments_to_duration(
                ordered,
                total_duration,
                fps=self._loaded_canvas_state_fps(ordered),
                preserve_order=True,
            )
        for idx, seg in enumerate(ordered):
            seg["line"] = idx
        if ordered and not preserve_view:
            # 변경 금지: 프로젝트 오픈은 EditorWidget 생성 시점에는 빈 세그먼트라
            # 초기 뷰 모드가 fit으로 잡히지만, 직후 실제 자막을 로드한다. 이 값을
            # window로 돌려두지 않으면 늦게 실행되는 초기 레이아웃 타이머가 저장된
            # 8초 창/작업 위치를 전체 보기로 덮어 STT1/2 후보가 보이지 않게 된다.
            self._initial_open_view_mode = "window"

        timeline = getattr(self, "timeline", None)
        if (
            auto_gap_segments_enabled is not None
            and timeline is not None
            and hasattr(timeline, "set_auto_gap_segments_enabled")
        ):
            timeline.set_auto_gap_segments_enabled(bool(auto_gap_segments_enabled))

        reloader = getattr(self, "_reload_segments_from_list", None)
        if callable(reloader):
            try:
                reloader(ordered, preserve_view=preserve_view, mark_dirty=mark_dirty)
            except TypeError as exc:
                if "mark_dirty" not in str(exc):
                    raise
                reloader(ordered, preserve_view=preserve_view)
        else:
            fallback_loader = getattr(self, "_bulk_load_segments_to_document", None)
            loaded = fallback_loader(ordered, preserve_view=preserve_view) if callable(fallback_loader) else None
            if loaded is None and hasattr(self, "append_segments"):
                self.append_segments(ordered)

        self.apply_canvas_aux_state(
            boundary_times=boundary_times,
            provisional_boundaries=provisional_boundaries,
            voice_activity_segments=voice_activity_segments,
            stt_preview_segments=stt_preview_segments,
            stt_preview_subtitle_drafts=stt_preview_subtitle_drafts,
            schedule_timeline=True,
        )
        self.editor_session_model = EditorSessionModel.from_canvas_state(
            final_segments=ordered,
            stt_preview_segments=stt_preview_segments,
            voice_activity_segments=voice_activity_segments,
            boundary_times=boundary_times,
            provisional_boundaries=provisional_boundaries,
            stt_preview_subtitle_drafts=stt_preview_subtitle_drafts,
        )
        return ordered
