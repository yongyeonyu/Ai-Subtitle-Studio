# Version: 03.09.28
# Phase: PHASE2
"""
ui/editor_lifecycle.py
MainWindow 에디터 열기/저장/닫기 Mixin
"""
import os
import re
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QTimer

from core.runtime.logger import get_logger
from core.path_manager import get_srt_path
from core.project.project_manager import PROJECTS_DIR, get_boundary_times, load_project
from ui.editor.editor_save_manager import backup_subtitle_file_copy
from ui.dialogs.message_box import confirm_save_changes


def _save_srt_impl(srt_path, segments):
    import os
    from core.runtime.logger import get_logger

    if not segments:
        get_logger().log('❌ 빈 세그먼트라 SRT 저장을 건너뜁니다.')
        return

    def _fmt(sec: float) -> str:
        total_ms = int(round(float(sec) * 1000.0))
        h = total_ms // 3600000
        m = (total_ms % 3600000) // 60000
        s = (total_ms % 60000) // 1000
        ms = total_ms % 1000
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    try:
        out_dir = os.path.dirname(srt_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        # 빈 텍스트 / gap 세그먼트 필터링
        filtered = [s for s in segments if not s.get('is_gap') and str(s.get('text', '') or '').strip()]
        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, seg in enumerate(filtered, 1):
                f.write(f"{i}\n")
                f.write(f"{_fmt(seg.get('start', 0.0))} --> {_fmt(seg.get('end', 0.0))}\n")
                f.write(f"{str(seg.get('text', '') or '').strip()}\n\n")
        get_logger().log(f"✅ {os.path.basename(srt_path)} 저장 완료")
    except Exception as e:
        get_logger().log(f"❌ SRT 저장 실패: {e}")


class EditorLifecycleMixin:

    def _normalized_open_path(self, path: str | None) -> str:
        if not path:
            return ""
        try:
            return os.path.normcase(os.path.abspath(os.path.expanduser(str(path))))
        except Exception:
            return ""

    def _project_sidecar_candidates_for_srt(self, srt_path: str, media_path: str | None = None) -> list[str]:
        """Return likely project JSON files for a direct SRT open."""
        candidates: list[str] = []

        def _add(path: str | None):
            if not path:
                return
            normalized = self._normalized_open_path(path)
            if normalized and normalized not in candidates and os.path.exists(normalized):
                candidates.append(normalized)

        srt_abs = self._normalized_open_path(srt_path)
        if srt_abs:
            srt_dir = os.path.dirname(srt_abs)
            srt_stem = os.path.splitext(os.path.basename(srt_abs))[0]
            _add(os.path.join(PROJECTS_DIR, f"{srt_stem}.json"))

            # Externalized project subtitles live in:
            #   <project>.assets/subtitles/final.srt
            # so walking back to <project>.json makes SRT open behave like
            # project open, minus STT1/STT2 preview tracks.
            if os.path.basename(srt_dir) == "subtitles":
                asset_dir = os.path.dirname(srt_dir)
                asset_name = os.path.basename(asset_dir)
                if asset_name.endswith(".assets"):
                    project_name = asset_name[: -len(".assets")]
                    _add(os.path.join(os.path.dirname(asset_dir), f"{project_name}.json"))

        media_abs = self._normalized_open_path(media_path)
        if media_abs and media_abs != srt_abs:
            media_stem = os.path.splitext(os.path.basename(media_abs))[0]
            _add(os.path.join(PROJECTS_DIR, f"{media_stem}.json"))

        try:
            for name in os.listdir(PROJECTS_DIR):
                if not name.lower().endswith(".json"):
                    continue
                _add(os.path.join(PROJECTS_DIR, name))
        except Exception:
            pass

        return candidates

    def _project_matches_opened_srt(self, project: dict, srt_path: str, media_path: str | None = None) -> bool:
        if not isinstance(project, dict):
            return False
        srt_abs = self._normalized_open_path(srt_path)
        media_abs = self._normalized_open_path(media_path)
        try:
            from core.project.project_assets import resolve_project_asset_path
            from core.project.project_context import project_media_files
        except Exception:
            resolve_project_asset_path = None
            project_media_files = None

        raw_srt_paths = [
            project.get("srt_path"),
            (project.get("subtitle", {}) or {}).get("path"),
            (project.get("subtitles", {}) or {}).get("srt_path"),
            ((project.get("editor_state", {}) or {}).get("subtitles", {}) or {}).get("srt_path"),
        ]
        subtitles = project.get("subtitles", {}) if isinstance(project.get("subtitles"), dict) else {}
        external_track = subtitles.get("external_track")
        if isinstance(external_track, dict):
            raw_srt_paths.append(external_track.get("path"))
        external_tracks = subtitles.get("external_tracks")
        if isinstance(external_tracks, dict):
            for track in external_tracks.values():
                if isinstance(track, dict):
                    raw_srt_paths.append(track.get("path"))
        asset_storage = project.get("asset_storage", {}) if isinstance(project.get("asset_storage"), dict) else {}
        tracks = asset_storage.get("tracks", {}) if isinstance(asset_storage.get("tracks"), dict) else {}
        for key, track in tracks.items():
            if str(key) in {"final", "subtitle_final"} and isinstance(track, dict):
                raw_srt_paths.append(track.get("path"))

        for raw in raw_srt_paths:
            if not raw:
                continue
            try:
                resolved = resolve_project_asset_path(project, raw) if callable(resolve_project_asset_path) else str(raw)
            except Exception:
                resolved = str(raw)
            if self._normalized_open_path(resolved) == srt_abs:
                return True

        if media_abs and callable(project_media_files):
            try:
                for path in project_media_files(project):
                    if self._normalized_open_path(path) == media_abs:
                        return True
            except Exception:
                pass
        return False

    def _find_project_for_srt_open(self, srt_path: str, media_path: str | None = None) -> tuple[str, dict | None]:
        for project_path in self._project_sidecar_candidates_for_srt(srt_path, media_path):
            project = load_project(project_path, hydrate_text_assets=True)
            if not isinstance(project, dict):
                continue
            if self._project_matches_opened_srt(project, srt_path, media_path):
                return project_path, project

            srt_abs = self._normalized_open_path(srt_path)
            srt_dir = os.path.dirname(srt_abs)
            if os.path.basename(srt_dir) == "subtitles":
                asset_dir = os.path.dirname(srt_dir)
                asset_name = os.path.basename(asset_dir)
                expected = os.path.join(
                    os.path.dirname(asset_dir),
                    f"{asset_name.removesuffix('.assets')}.json",
                )
                if self._normalized_open_path(project_path) == self._normalized_open_path(expected):
                    return project_path, project
        return "", None

    @staticmethod
    def _normalized_segment_text(text: str | None) -> str:
        return re.sub(r"\s+", " ", str(text or "").strip())

    def _segment_metadata_match_score(self, srt_seg: dict, project_seg: dict, srt_index: int, project_index: int) -> int:
        try:
            start_delta = abs(float(srt_seg.get("start", 0.0) or 0.0) - float(project_seg.get("start", 0.0) or 0.0))
            end_delta = abs(float(srt_seg.get("end", 0.0) or 0.0) - float(project_seg.get("end", 0.0) or 0.0))
        except Exception:
            start_delta = end_delta = 999.0
        srt_text = self._normalized_segment_text(srt_seg.get("text"))
        project_text = self._normalized_segment_text(project_seg.get("text"))
        score = 0
        if start_delta <= 0.05 and end_delta <= 0.05:
            score += 50
        elif start_delta <= 0.25 and end_delta <= 0.25:
            score += 34
        elif start_delta <= 0.6 and end_delta <= 0.6:
            score += 16
        if srt_text and project_text:
            if srt_text == project_text:
                score += 44
            elif srt_text in project_text or project_text in srt_text:
                score += 22
        if srt_index == project_index:
            score += 12
        return score

    def _merge_srt_segments_with_project_metadata(self, srt_segments: list[dict], project_segments: list[dict]) -> list[dict]:
        """Preserve SRT timing/text while restoring project-only UI metadata."""
        if not srt_segments or not project_segments:
            return [dict(seg) for seg in list(srt_segments or []) if isinstance(seg, dict)]
        project_rows = [dict(seg) for seg in list(project_segments or []) if isinstance(seg, dict)]
        native_matches = None
        try:
            from core.native_swift_timeline import match_srt_project_metadata_via_swift

            native_matches = match_srt_project_metadata_via_swift(
                srt_segments=list(srt_segments or []),
                project_segments=project_rows,
            )
        except Exception:
            native_matches = None
        used: set[int] = set()
        merged: list[dict] = []
        timing_keys = {
            "start",
            "end",
            "timeline_start",
            "timeline_end",
            "start_frame",
            "end_frame",
            "timeline_start_frame",
            "timeline_end_frame",
            "frame_range",
        }
        preserve_srt_keys = {"line", "index", "text", "is_gap", *timing_keys}

        for idx, raw_srt in enumerate(list(srt_segments or [])):
            if not isinstance(raw_srt, dict):
                continue
            best_idx = -1
            if isinstance(native_matches, list) and idx < len(native_matches):
                try:
                    native_idx = int(native_matches[idx])
                except Exception:
                    native_idx = -1
                if native_idx >= 0 and native_idx not in used and native_idx < len(project_rows):
                    best_idx = native_idx
            if best_idx < 0:
                best_score = -1
                for project_idx, project_seg in enumerate(project_rows):
                    if project_idx in used:
                        continue
                    score = self._segment_metadata_match_score(raw_srt, project_seg, idx, project_idx)
                    if score > best_score:
                        best_idx = project_idx
                        best_score = score

                if best_score < 30 and len(project_rows) == len(srt_segments) and idx < len(project_rows) and idx not in used:
                    best_idx = idx
                elif best_idx < 0 and idx < len(project_rows) and idx not in used:
                    best_idx = idx

            item = dict(raw_srt)
            item["line"] = idx
            if best_idx >= 0:
                project_seg = project_rows[best_idx]
                used.add(best_idx)
                try:
                    timing_close = (
                        abs(float(item.get("start", 0.0) or 0.0) - float(project_seg.get("start", 0.0) or 0.0)) <= 0.08
                        and abs(float(item.get("end", 0.0) or 0.0) - float(project_seg.get("end", 0.0) or 0.0)) <= 0.08
                    )
                except Exception:
                    timing_close = False
                for key, value in project_seg.items():
                    if key in preserve_srt_keys:
                        continue
                    if key in timing_keys and not timing_close:
                        continue
                    item[key] = value
            merged.append(item)
        return merged

    def _restore_project_context_for_srt_open(self, editor, project_path: str, project: dict | None) -> None:
        if editor is None or not project_path or not isinstance(project, dict):
            return
        try:
            editor._linked_project_path_for_srt = project_path
        except Exception:
            pass
        try:
            if hasattr(self, "_restore_workspace"):
                self._restore_workspace(editor, project_path)
        except Exception:
            pass

        try:
            refresher = getattr(editor, "_refresh_cut_boundary_placeholder_from_project", None)
            if callable(refresher):
                QTimer.singleShot(0, refresher)
                QTimer.singleShot(180, refresher)
        except Exception:
            pass

        try:
            if hasattr(editor, "_schedule_timeline"):
                editor._schedule_timeline()
            elif hasattr(editor, "_redraw_timeline"):
                editor._redraw_timeline()
        except Exception:
            pass

    def _schedule_editor_fit_to_view(self, editor, delay_ms: int = 120):
        if not hasattr(editor, "timeline"):
            return
        timeline = editor.timeline
        delays = (0, delay_ms, max(delay_ms + 160, 300))
        try:
            if hasattr(editor, "_schedule_initial_open_layout"):
                editor._schedule_initial_open_layout(delays=delays)
                return
            if hasattr(timeline, "schedule_time_window_seconds"):
                timeline.schedule_time_window_seconds(
                    10.0,
                    start_sec=0.0,
                    delays=delays,
                )
            elif hasattr(timeline, "schedule_fit_to_view"):
                timeline.schedule_fit_to_view((0, delay_ms, max(delay_ms + 140, 260)))
            elif hasattr(timeline, "fit_to_view"):
                QTimer.singleShot(max(0, int(delay_ms)), timeline.fit_to_view)
        except Exception:
            pass

    def _refresh_opened_editor_runtime(self, editor) -> None:
        """Restore live editor state after SRT/project hydration.

        SRT and project opens both load text before all video/timeline widgets
        have settled, so refresh timestamp metadata and the video subtitle
        provider after the editor is visible.
        """
        if editor is None:
            return
        try:
            cached = getattr(editor, "_cached_segs", None)
            if isinstance(cached, list) and cached:
                editor._rebuild_subtitle_memory_cache(cached)
            else:
                editor._rebuild_subtitle_memory_cache()
        except Exception:
            pass

        try:
            if hasattr(editor, "_refresh_editor_timestamp_metadata"):
                editor._refresh_editor_timestamp_metadata(full=True)
        except Exception:
            pass

        text_edit = getattr(editor, "text_edit", None)
        try:
            if text_edit is not None and hasattr(text_edit, "update_margins"):
                text_edit.update_margins()
            if text_edit is not None and hasattr(text_edit, "refresh_timestamp_layer"):
                text_edit.refresh_timestamp_layer()
        except Exception:
            pass

        try:
            if hasattr(editor, "_refresh_video_subtitle_context"):
                editor._refresh_video_subtitle_context()
            video_player = getattr(editor, "video_player", None)
            provider = getattr(editor, "_video_subtitle_context_for_player", None)
            if video_player is not None and callable(provider):
                if hasattr(video_player, "set_subtitle_provider"):
                    video_player.set_subtitle_provider(provider)
                elif hasattr(video_player, "refresh_subtitle_context"):
                    video_player.refresh_subtitle_context(provider())
                elif hasattr(video_player, "set_context_segments"):
                    video_player.set_context_segments(provider())
            canvas = getattr(getattr(editor, "timeline", None), "canvas", None)
            playhead_sec = float(getattr(canvas, "playhead_sec", 0.0) or 0.0)
            if video_player is not None and hasattr(video_player, "set_subtitle_display_time"):
                local_sec = editor._global_to_local_sec(playhead_sec) if hasattr(editor, "_global_to_local_sec") else playhead_sec
                video_player.set_subtitle_display_time(local_sec)
        except Exception:
            pass

    def _refresh_opened_srt_editor_runtime(self, editor) -> None:
        self._refresh_opened_editor_runtime(editor)

    def _schedule_opened_editor_runtime_refresh(self, editor) -> None:
        for delay_ms in (0, 120, 360, 720):
            QTimer.singleShot(
                delay_ms,
                lambda e=editor: self._refresh_opened_editor_runtime(e),
            )

    def _schedule_opened_srt_editor_runtime_refresh(self, editor) -> None:
        self._schedule_opened_editor_runtime_refresh(editor)

    def _open_srt_in_editor(self, srt_path):
        from core.srt_parser import parse_srt
        from core.subtitle_existing import backup_existing_srt, find_media_for_srt, validate_srt_duration
        from core.project.project_context import (
            project_cut_boundary_provisional_segments,
            project_voice_activity_segments,
        )
        from ui.editor.editor_widget import EditorWidget
        self._current_work_mode = "editor"
        self._current_project_path = None
        self._project_boundary_times = []
        if hasattr(self, "_clear_multiclip_runtime_state"):
            self._clear_multiclip_runtime_state()
        self._remove_old_editor()
        media_path = find_media_for_srt(srt_path) or ""
        linked_project_path, linked_project = self._find_project_for_srt_open(srt_path, media_path)
        if linked_project:
            self._current_project_path = linked_project_path
            try:
                self._project_boundary_times = get_boundary_times(linked_project)
            except Exception:
                self._project_boundary_times = []
            if not media_path or media_path == srt_path or not os.path.exists(media_path):
                try:
                    from core.project.project_context import project_media_files

                    media_files = [path for path in project_media_files(linked_project) if path and os.path.exists(path)]
                    if media_files:
                        media_path = media_files[0]
                except Exception:
                    pass
        media_path = media_path or srt_path
        ok, reason = validate_srt_duration(srt_path, media_path)
        if ok:
            segments = parse_srt(srt_path)
            if linked_project:
                try:
                    from core.project.project_context import project_segments_to_editor

                    project_segments = project_segments_to_editor(linked_project, include_analysis_candidates=True)
                    segments = self._merge_srt_segments_with_project_metadata(segments, project_segments)
                    get_logger().log(
                        f"🔗 SRT 메타데이터 복원: {os.path.basename(linked_project_path)}"
                    )
                except Exception as exc:
                    get_logger().log(f"⚠️ SRT 프로젝트 메타데이터 복원 실패: {exc}")
        else:
            QMessageBox.warning(self, "기존 자막 오류", reason)
            backup_existing_srt(srt_path)
            segments = []
        display_name = os.path.basename(media_path if media_path and media_path != srt_path else srt_path)
        editor = EditorWidget(
            video_name=display_name,
            segments=[],
            media_path=media_path,
            parent=self,
            hydrate_existing_srt_on_empty=False,
        )
        editor._source_srt_path = srt_path
        editor._last_saved_srt_outputs = [(srt_path, media_path)]
        editor._project_clips = None
        editor._direct_srt_edit_mode = True
        provisional_boundaries = (
            project_cut_boundary_provisional_segments(linked_project)
            if linked_project else None
        )
        voice_activity_segments = (
            project_voice_activity_segments(linked_project)
            if linked_project else None
        )
        if hasattr(editor, "apply_loaded_canvas_state"):
            editor.apply_loaded_canvas_state(
                segments,
                auto_gap_segments_enabled=False,
                boundary_times=self._project_boundary_times or [],
                provisional_boundaries=provisional_boundaries,
                voice_activity_segments=voice_activity_segments,
                mark_dirty=False,
            )
        def _save_and_home(segs=None):
            if segs is not None: _save_srt_impl(srt_path, segs)
            QTimer.singleShot(0, self.show_home)
        editor.sig_save.connect(lambda segs, p=srt_path: _save_srt_impl(p, segs)); editor.sig_auto_save.connect(lambda segs, p=srt_path: _save_srt_impl(p, segs)); editor.sig_next.connect(_save_and_home); editor.sig_exit.connect(lambda _: self.close())
        self._editor_widget = editor
        if hasattr(self, "global_menu_bar"):
            self.global_menu_bar.bind_editor(editor)
        if hasattr(self, "_attach_global_menu_to_editor"):
            self._attach_global_menu_to_editor(editor)
        if hasattr(editor, 'set_terminal_visible_layout'): editor.set_terminal_visible_layout(True)
        self.stack.insertWidget(1, editor); self.stack.setCurrentWidget(editor)
        if hasattr(self, "_activate_editor_idle_mode"):
            self._activate_editor_idle_mode(reason="direct_srt_open")
        if linked_project:
            self._restore_project_context_for_srt_open(editor, linked_project_path, linked_project)
        self._schedule_editor_fit_to_view(editor)
        self._schedule_opened_editor_runtime_refresh(editor)
        if hasattr(self, "_refresh_work_mode_ui"):
            QTimer.singleShot(0, self._refresh_work_mode_ui)
        if hasattr(self, "_release_ai_models_for_editor_mode"):
            QTimer.singleShot(0, self._release_ai_models_for_editor_mode)

    def _finalize_reuse_completion(self, editor):
        """기존자막 reuse 완료 후 상태 전환"""
        try:
            if hasattr(editor, '_set_process_completed'):
                editor._set_process_completed()
            if hasattr(editor, '_redraw_timeline'):
                QTimer.singleShot(0, editor._redraw_timeline)
            self._schedule_editor_fit_to_view(editor, delay_ms=160)
        except Exception as e:
            from core.runtime.logger import get_logger
            get_logger().log(f'⚠️ reuse 완료 상태 전환 실패: {e}')

    def _init_editor(self, target_file, is_batch=False):
        from ui.editor.editor_widget import EditorWidget
        self._current_work_mode = "editor"
        vname = os.path.basename(target_file); self._remove_old_editor()
        editor = EditorWidget(
            video_name=vname,
            segments=[],
            media_path=target_file,
            parent=self,
            defer_media_load=bool(is_batch),
            hydrate_existing_srt_on_empty=False,
        )
        editor.is_auto_start = is_batch; self._editor_widget = editor
        editor._queue_mode_fit_view = bool(is_batch)

        editor._project_clips = None
        if self._current_project_path and self.backend:
            n_files = len(getattr(self.backend, 'files_to_process', []))
            if n_files > 1:
                pd = load_project(self._current_project_path, hydrate_text_assets=False)
                if pd and "timeline" in pd:
                    clips = pd["timeline"].get("tracks", [{}])[0].get("clips", [])
                    if len(clips) > 1: editor._project_clips = clips

        if is_batch: editor.sm.init_auto_state()
        else: editor.sm.init_state()
        if hasattr(editor, 'btn_start'): editor.btn_start.setText("시작")
        if hasattr(self, "global_menu_bar"):
            self.global_menu_bar.bind_editor(editor)
        
        # 멀티클립 박스 전달
        if hasattr(self, '_multiclip_boundaries') and self._multiclip_boundaries:

            boxes = []
            for i, bd in enumerate(self._multiclip_boundaries):
                boxes.append({
                    "start": bd["start"],
                    "end": bd["end"],
                    "index": i + 1,
                    "name": bd.get("name", ""),
                    "file": bd.get("file", "")   # ← 추가
                })

            total_dur = self._multiclip_boundaries[-1]["end"]

            # 메인 캔버스
            editor.timeline.canvas._multiclip_boxes = boxes
            editor.timeline.canvas._active_clip_idx = 0
            editor.timeline.canvas.boundary_times = [bd["end"] for bd in self._multiclip_boundaries[:-1]]
            editor.timeline.canvas.total_duration = total_dur

            # 글로벌 캔버스
            gc = editor.timeline.global_canvas
            gc.total_duration = total_dur
            gc._multiclip_boxes = boxes
            gc._active_clip_idx = 0
            gc.segments = []
            try:
                self._active_clip_idx = 0
            except Exception:
                pass
            try:
                if boxes:
                    editor.timeline._selected_clip_idx = 0
                    editor.timeline._selected_clip_offset = float(boxes[0].get('start', 0.0))
                    editor.timeline._selected_clip_duration = max(0.001, float(boxes[0].get('end', 0.0)) - float(boxes[0].get('start', 0.0)))
                    editor.timeline._selected_clip_label = str(boxes[0].get('index', 1))
                    gc.set_clip_label(editor.timeline._selected_clip_label)
                else:
                    editor.timeline._selected_clip_label = ''
                    gc.set_clip_label('')
            except Exception:
                pass
            gc.update()

            editor.timeline.canvas.update()
            editor.timeline.load_multiclip_waveform(self._multiclip_boundaries)

            # PHASE1-B: 에디터 진입 직후 기존 자막 사전 로드
            # backend에서만 reuse flag 읽기 (stale self 값 무시)
            _reuse_flag = getattr(getattr(self, 'backend', None), '_reuse_existing_multiclip_subtitles', False)
            if _reuse_flag is True:
                for _ri, _bd in enumerate(self._multiclip_boundaries):
                    _rf = _bd.get('file', '')
                    _rsrt = os.path.splitext(_rf)[0] + '.srt' if _rf else ''
                    if _rsrt and os.path.exists(_rsrt):
                        try:
                            from core.srt_parser import parse_srt
                            from core.subtitle_existing import backup_existing_srt, validate_srt_duration
                            _ok, _reason = validate_srt_duration(_rsrt, _rf)
                            if not _ok:
                                QMessageBox.warning(self, "기존 자막 오류", _reason)
                                backup_existing_srt(_rsrt)
                                continue
                            _rsegs = parse_srt(_rsrt)
                            if _rsegs:
                                _roff = float(_bd.get('start', 0.0))
                                for _s in _rsegs:
                                    _s['start'] = float(_s.get('start', 0.0)) + _roff
                                    _s['end'] = float(_s.get('end', 0.0)) + _roff
                                    _s['_clip_idx'] = _ri
                                    if 'speaker' not in _s:
                                        _s['speaker'] = _s.get('spk_id', '00')
                                editor.append_segments(_rsegs)
                                try:
                                    _backend = getattr(self, 'backend', None)
                                    if _backend is not None:
                                        if not hasattr(_backend, '_reuse_clip_indices'):
                                            _backend._reuse_clip_indices = set()
                                        _backend._reuse_clip_indices.add(_ri)
                                    if not hasattr(self, '_reuse_clip_indices'):
                                        self._reuse_clip_indices = set()
                                    self._reuse_clip_indices.add(_ri)
                                except Exception:
                                    pass
                                get_logger().log(f'  [PRE] 기존 자막 사전 로드: {os.path.basename(_rf)} ({len(_rsegs)}개)')
                                if hasattr(self, '_sig_update_queue'):
                                    self._sig_update_queue.emit(_ri, '✅기존자막', ' - ', '', '')
                        except Exception as _re:
                            get_logger().log(f'  [PRE] 기존 자막 사전 로드 실패: {os.path.basename(_rf)} / {_re}')
                # reuse 완료 → 완료 상태 전환 (버튼 "재시작"으로)
                try:
                    _reuse_count = len(getattr(self, '_reuse_clip_indices', set()) or set())
                    _total_count = len(self._multiclip_boundaries)
                    if _total_count > 0 and _reuse_count >= _total_count and hasattr(self, '_sig_update_queue_header'):
                        self._sig_update_queue_header.emit(_total_count, _total_count, 100, '')
                except Exception:
                    pass
                QTimer.singleShot(500, lambda: self._finalize_reuse_completion(editor))
            
        def safe_home(*args):
            QTimer.singleShot(0, self.show_home)
        def force_exit_app(*args): self.close()
        def handle_prev(*args):
            if self._on_prev_cb: self._on_prev_cb()
            safe_home()

        if self._on_start_cb: editor.sig_start.connect(self._on_start_cb)
        editor.sig_prev.connect(handle_prev); editor.sig_exit.connect(force_exit_app)
        if self._on_save_cb: editor.sig_next.connect(self._on_save_cb)
        else: editor.sig_next.connect(safe_home)
        srt_save_path = get_srt_path(target_file)
        editor.sig_save.connect(lambda segs, p=srt_save_path: _save_srt_impl(p, segs))
        editor.sig_auto_save.connect(lambda segs, p=srt_save_path: _save_srt_impl(p, segs))
        if hasattr(editor, 'set_terminal_visible_layout'): editor.set_terminal_visible_layout(True)
        self.stack.insertWidget(1, editor)
        if hasattr(editor, 'timeline'): editor.timeline.set_boundary_times(self._project_boundary_times or [])
        self.stack.setCurrentWidget(editor)
        if hasattr(self, "_activate_editor_idle_mode"):
            self._activate_editor_idle_mode(reason="editor_open")
        self._schedule_editor_fit_to_view(editor)
        if hasattr(self, "global_menu_bar"):
            self.global_menu_bar.bind_editor(editor)
        if hasattr(self, "_attach_global_menu_to_editor"):
            self._attach_global_menu_to_editor(editor)
        if self._current_project_path:
            self._restore_workspace(editor, self._current_project_path)
            from core.project.project_phase1b import apply_project_ui_state
            apply_project_ui_state(self, editor, self._current_project_path)
        if hasattr(self, "_refresh_work_mode_ui"):
            QTimer.singleShot(0, self._refresh_work_mode_ui)
        if hasattr(self, "_release_ai_models_for_editor_mode"):
            QTimer.singleShot(0, self._release_ai_models_for_editor_mode)
        if is_batch and hasattr(editor, "_load_queue_clip_media_staged"):
            QTimer.singleShot(
                0,
                lambda e=editor, p=target_file: e._load_queue_clip_media_staged(
                    p,
                    auto_start=True,
                ),
            )

    def _remove_old_editor(self):
        old = getattr(self, "_editor_widget", None)
        if not old:
            return
        try:
            detach = getattr(old, "detach_external_menu_bar", None)
            if callable(detach):
                detach()
            if hasattr(self, "_dock_global_menu_to_workspace"):
                self._dock_global_menu_to_workspace()
        except RuntimeError:
            pass
        try:
            if self.stack.indexOf(old) < 0:
                self._editor_widget = None
                return
        except RuntimeError:
            self._editor_widget = None
            return
        if hasattr(old, '_cleanup'):
            try: old._cleanup()
            except: pass
        if hasattr(old, 'video_player'):
            try:
                vp = old.video_player
                if hasattr(vp, '_ui_timer'): vp._ui_timer.stop()
                if hasattr(vp, 'audio_player'): vp.audio_player.stop()
                if hasattr(vp, '_worker') and getattr(vp, '_worker', None): vp._worker.stop(); vp._worker.wait(200)
            except: pass
        if hasattr(old, 'timeline'):
            try:
                stop_waveform = getattr(old.timeline, "stop_waveform_workers", None)
                if callable(stop_waveform):
                    stop_waveform()
            except Exception:
                pass
        try:
            self.stack.removeWidget(old)
            old.hide()
            if old is getattr(self, "_editor_widget", None) and hasattr(self, "global_menu_bar"):
                self.global_menu_bar.clear_editor()
        except RuntimeError:
            return
        if not hasattr(self, '_trash_bin'):
            self._trash_bin = []
        self._trash_bin.append(old)
        while len(self._trash_bin) > 3:
            widget = self._trash_bin.pop(0)
            try:
                widget.deleteLater()
            except (RuntimeError, AttributeError):
                pass


    def _backup_srt(self, srt_path, segments):
        try:
            backup_subtitle_file_copy(srt_path)
        except Exception as e:
            get_logger().log(f"⚠️ 백업 저장 실패: {e}")

    def closeEvent(self, event):
        if self._editor_widget and self.stack.currentIndex() == 1:
            if hasattr(self._editor_widget, 'sm') and self._editor_widget.sm.is_locked:
                if hasattr(self._editor_widget, '_stop_pipeline'):
                    self._editor_widget._stop_pipeline()

            if getattr(self._editor_widget, '_skip_prev_confirm_once', False):
                self._editor_widget._skip_prev_confirm_once = False
                event.accept()
            else:
                is_dirty = False
                try:
                    dirty_checker = getattr(self._editor_widget, "_has_unsaved_changes", None)
                    if callable(dirty_checker):
                        is_dirty = bool(dirty_checker())
                    elif hasattr(self._editor_widget, 'sm'):
                        is_dirty = bool(self._editor_widget.sm.is_dirty)
                except Exception:
                    pass

                if is_dirty:
                    helper = getattr(self._editor_widget, "_confirm_close_before_exit", None)
                    if callable(helper):
                        if not helper("종료 확인"):
                            event.ignore()
                            return
                        event.accept()
                    else:
                        reply = confirm_save_changes(self, title="종료 확인")
                        if reply == QMessageBox.StandardButton.Yes:
                            if hasattr(self._editor_widget, '_on_save'):
                                self._editor_widget._on_save()
                            event.accept()
                        elif reply == QMessageBox.StandardButton.No:
                            event.accept()
                        else:
                            event.ignore()
                            return
                else:
                    event.accept()
        else:
            event.accept()
            return

        if hasattr(self, "_detach_app_event_filter"):
            self._detach_app_event_filter()
        get_logger().clear_ui_callback()
        self.blockSignals(True)
        try:
            if hasattr(self, "_cleanup_runtime_for_navigation"):
                self._cleanup_runtime_for_navigation(context="앱 종료", timeout_sec=0.8, force=True)
            elif self.backend:
                self.backend.stop()
        except Exception:
            pass
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return
        QTimer.singleShot(100, lambda: os._exit(0))
