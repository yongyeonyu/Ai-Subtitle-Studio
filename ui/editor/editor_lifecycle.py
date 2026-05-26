# Version: 03.09.28
# Phase: PHASE2
"""
ui/editor_lifecycle.py
MainWindow 에디터 열기/저장/닫기 Mixin
"""
import os
import time
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QTimer

from core.runtime.logger import get_logger
from core.path_manager import get_srt_path
from core.project.project_manager import load_project
from ui.editor.editor_save_manager import backup_subtitle_file_copy
from ui.editor.editor_project_open_native import (
    find_project_for_srt_open as native_find_project_for_srt_open,
    merge_srt_segments_with_project_metadata as native_merge_srt_segments_with_project_metadata,
    normalized_open_path as native_normalized_open_path,
    normalized_segment_text as native_normalized_segment_text,
    open_subtitle_segments_in_editor as native_open_subtitle_segments_in_editor,
    project_matches_opened_srt as native_project_matches_opened_srt,
    project_sidecar_candidates_for_srt as native_project_sidecar_candidates_for_srt,
    refresh_opened_editor_runtime as native_refresh_opened_editor_runtime,
    restore_project_context_for_srt_open as native_restore_project_context_for_srt_open,
    schedule_native_editor_post_open_tasks as native_schedule_native_editor_post_open_tasks,
    schedule_native_open_editor_media as native_schedule_native_open_editor_media,
    schedule_editor_fit_to_view as native_schedule_editor_fit_to_view,
    schedule_opened_editor_runtime_refresh as native_schedule_opened_editor_runtime_refresh,
    segment_metadata_match_score as native_segment_metadata_match_score,
)
from ui.dialogs.message_box import confirm_save_changes
from ui.queue.queue_formatting import build_queue_header_payload, build_queue_status_payload
from ui.project.project_session_runtime import attach_project_session, detach_project_session


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
        return native_normalized_open_path(path)

    def _project_sidecar_candidates_for_srt(self, srt_path: str, media_path: str | None = None) -> list[str]:
        return native_project_sidecar_candidates_for_srt(srt_path, media_path)

    def _project_matches_opened_srt(self, project: dict, srt_path: str, media_path: str | None = None) -> bool:
        return native_project_matches_opened_srt(project, srt_path, media_path)

    def _find_project_for_srt_open(self, srt_path: str, media_path: str | None = None) -> tuple[str, dict | None]:
        return native_find_project_for_srt_open(srt_path, media_path)

    @staticmethod
    def _normalized_segment_text(text: str | None) -> str:
        return native_normalized_segment_text(text)

    def _segment_metadata_match_score(self, srt_seg: dict, project_seg: dict, srt_index: int, project_index: int) -> int:
        return native_segment_metadata_match_score(srt_seg, project_seg, srt_index, project_index)

    def _merge_srt_segments_with_project_metadata(self, srt_segments: list[dict], project_segments: list[dict]) -> list[dict]:
        return native_merge_srt_segments_with_project_metadata(srt_segments, project_segments)

    def _restore_project_context_for_srt_open(self, editor, project_path: str, project: dict | None) -> None:
        native_restore_project_context_for_srt_open(self, editor, project_path, project)

    def _open_subtitle_segments_in_editor(self, srt_path: str, media_path: str, segments: list[dict]) -> bool:
        opened = native_open_subtitle_segments_in_editor(self, srt_path, media_path, segments)
        if opened:
            editor = getattr(self, "_editor_widget", None)
            if editor is not None:
                def _save_and_home(segs=None, path=srt_path):
                    if segs is not None:
                        _save_srt_impl(path, segs)
                    QTimer.singleShot(0, self.show_home)

                try:
                    editor.sig_next.connect(_save_and_home)
                except Exception:
                    pass
        return bool(opened)

    def _schedule_editor_fit_to_view(self, editor, delay_ms: int = 120):
        native_schedule_editor_fit_to_view(editor, delay_ms=delay_ms)

    def _refresh_opened_editor_runtime(self, editor) -> None:
        native_refresh_opened_editor_runtime(editor)

    def _refresh_opened_srt_editor_runtime(self, editor) -> None:
        self._refresh_opened_editor_runtime(editor)

    def _schedule_native_open_editor_media(self, editor, media_path: str | None) -> None:
        project_open = bool(str(getattr(self, "_current_project_path", "") or "").strip())
        is_multiclip = bool(getattr(self, "_multiclip_boundaries", []) or [])
        native_schedule_native_open_editor_media(
            self,
            editor,
            media_path,
            defer_waveform_until_start=not (project_open and not is_multiclip),
        )

    def _schedule_native_editor_post_open_tasks(
        self,
        editor,
        *,
        restore_workspace_callback=None,
        apply_project_ui_callback=None,
        load_multiclip_waveform_callback=None,
        preload_segments_callback=None,
    ) -> None:
        native_schedule_native_editor_post_open_tasks(
            self,
            editor,
            restore_workspace_callback=restore_workspace_callback,
            apply_project_ui_callback=apply_project_ui_callback,
            load_multiclip_waveform_callback=load_multiclip_waveform_callback,
            preload_segments_callback=preload_segments_callback,
        )

    def _schedule_opened_editor_runtime_refresh(self, editor) -> None:
        native_schedule_opened_editor_runtime_refresh(
            editor,
            refresh_callback=self._refresh_opened_editor_runtime,
        )

    def _schedule_opened_srt_editor_runtime_refresh(self, editor) -> None:
        self._schedule_opened_editor_runtime_refresh(editor)

    def _fallback_media_for_srt_open(self, srt_path: str) -> str:
        editor = getattr(self, "_editor_widget", None)
        candidates = [
            getattr(editor, "media_path", ""),
            getattr(self, "_current_media_path", ""),
            getattr(self, "media_path", ""),
        ]
        srt_dir = os.path.dirname(os.path.abspath(str(srt_path or "")))
        srt_stem = os.path.splitext(os.path.basename(str(srt_path or "")))[0].lower()
        for raw in candidates:
            path = str(raw or "").strip()
            if not path or path.lower().endswith(".srt") or not os.path.exists(path):
                continue
            media_stem = os.path.splitext(os.path.basename(path))[0].lower()
            same_dir = os.path.dirname(os.path.abspath(path)) == srt_dir
            related_name = bool(media_stem and (media_stem in srt_stem or srt_stem in media_stem))
            if same_dir or related_name:
                return path
        return ""

    def _open_srt_in_editor(self, srt_path):
        started = time.perf_counter()
        from core.srt_parser import parse_srt
        from core.subtitle_existing import backup_existing_srt, find_media_for_srt, validate_srt_duration
        from core.project.project_context import (
            project_media_files,
        )
        self._current_work_mode = "editor"
        detach_project_session(
            self,
            auto_pipeline=False,
            clear_multiclip=True,
            emit_boundary_signal=False,
        )
        fallback_media_path = self._fallback_media_for_srt_open(srt_path)
        self._remove_old_editor()
        media_path = find_media_for_srt(srt_path) or fallback_media_path or ""
        linked_project_path, linked_project = self._find_project_for_srt_open(srt_path, media_path)
        if linked_project:
            attach_project_session(
                self,
                linked_project_path,
                linked_project,
                auto_pipeline=False,
                clear_multiclip=True,
                emit_boundary_signal=False,
            )
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
        project_segment_opener = getattr(self, "_open_project_segments_in_editor", None)
        if linked_project and callable(project_segment_opener):
            project_media = [path for path in project_media_files(linked_project) if path and os.path.exists(path)]
            if not project_media and media_path and media_path != srt_path and os.path.exists(media_path):
                project_media = [media_path]
            if project_media:
                opened = bool(
                    project_segment_opener(
                        linked_project_path,
                        linked_project,
                        project_media,
                        segments,
                        source_srt_path=srt_path,
                        direct_srt_edit_mode=True,
                    )
                )
                if opened:
                    get_logger().log_perf(
                        "editor.open_srt",
                        event="ready",
                        elapsed_ms=(time.perf_counter() - started) * 1000.0,
                        linked_project=True,
                        project_restore_path=True,
                        segments=len(list(segments or [])),
                        media_found=bool(project_media),
                    )
                    return
        opened = self._open_subtitle_segments_in_editor(srt_path, media_path, segments)
        if opened:
            get_logger().log_perf(
                "editor.open_srt",
                event="ready",
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                linked_project=False,
                project_restore_path=False,
                segments=len(list(segments or [])),
                media_found=bool(media_path and media_path != srt_path),
            )
            return
        get_logger().log_perf(
            "editor.open_srt",
            event="failed",
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            linked_project=False,
            media_found=bool(media_path and media_path != srt_path),
        )

    def _finalize_reuse_completion(self, editor):
        """기존자막 reuse 완료 후 상태 전환"""
        try:
            if hasattr(editor, '_set_process_completed'):
                try:
                    editor._set_process_completed(suppress_post_generation_tasks=True)
                except TypeError:
                    editor._set_process_completed()
            if hasattr(editor, '_redraw_timeline'):
                QTimer.singleShot(0, editor._redraw_timeline)
            self._schedule_editor_fit_to_view(editor, delay_ms=160)
        except Exception as e:
            from core.runtime.logger import get_logger
            get_logger().log(f'⚠️ reuse 완료 상태 전환 실패: {e}')

    def _init_editor(self, target_file, is_batch=False):
        started = time.perf_counter()
        from ui.editor.editor_widget import EditorWidget
        self._current_work_mode = "editor"
        vname = os.path.basename(target_file); self._remove_old_editor()
        editor = EditorWidget(
            video_name=vname,
            segments=[],
            media_path=target_file,
            parent=self,
            defer_media_load=True,
            hydrate_existing_srt_on_empty=False,
        )
        get_logger().log_perf(
            "editor.init",
            event="widget_created",
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            file=vname,
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
            if hasattr(editor.timeline, "set_boundary_times"):
                editor.timeline.set_boundary_times(list(getattr(self, "_project_boundary_times", []) or []))
            else:
                editor.timeline.canvas.boundary_times = list(getattr(self, "_project_boundary_times", []) or [])
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
            def _deferred_multiclip_waveform_load():
                editor.timeline.load_multiclip_waveform(self._multiclip_boundaries)

            def _deferred_preload_existing_multiclip_segments():
                # PHASE1-B: 에디터 진입 직후 기존 자막 사전 로드
                # backend에서만 reuse flag 읽기 (stale self 값 무시)
                _reuse_flag = getattr(getattr(self, 'backend', None), '_reuse_existing_multiclip_subtitles', False)
                if _reuse_flag is not True:
                    return
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
                                if hasattr(self, '_sig_update_queue_payload'):
                                    self._sig_update_queue_payload.emit(
                                        build_queue_status_payload(_ri, '✅기존자막', ' - ', '', '')
                                    )
                        except Exception as _re:
                            get_logger().log(f'  [PRE] 기존 자막 사전 로드 실패: {os.path.basename(_rf)} / {_re}')
                try:
                    _reuse_count = len(getattr(self, '_reuse_clip_indices', set()) or set())
                    _total_count = len(self._multiclip_boundaries)
                    if _total_count > 0 and _reuse_count >= _total_count:
                        if hasattr(self, '_sig_update_queue_header_payload'):
                            self._sig_update_queue_header_payload.emit(
                                build_queue_header_payload(_total_count, _total_count, 100, '')
                            )
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
        if not is_batch:
            def _mark_start_ready(e=editor):
                if getattr(self, "_editor_widget", None) is not e:
                    return
                marker = getattr(e, "_mark_open_media_start_ready", None)
                if callable(marker):
                    marker(reason="editor_open")

            _mark_start_ready()
            QTimer.singleShot(0, _mark_start_ready)
            QTimer.singleShot(90, _mark_start_ready)
        restore_workspace_callback = None
        apply_project_ui_callback = None
        if self._current_project_path:
            if hasattr(self, "_restore_workspace"):
                restore_workspace_callback = lambda e=editor, p=self._current_project_path: self._restore_workspace(e, p)
            try:
                from core.project.project_phase1b import apply_project_ui_state

                apply_project_ui_callback = lambda e=editor, p=self._current_project_path: apply_project_ui_state(self, e, p)
            except Exception:
                apply_project_ui_callback = None
            self._schedule_native_editor_post_open_tasks(
                editor,
                restore_workspace_callback=restore_workspace_callback,
                apply_project_ui_callback=apply_project_ui_callback,
                load_multiclip_waveform_callback=(
                    _deferred_multiclip_waveform_load if hasattr(self, '_multiclip_boundaries') and self._multiclip_boundaries else None
                ),
                preload_segments_callback=(
                    _deferred_preload_existing_multiclip_segments if hasattr(self, '_multiclip_boundaries') and self._multiclip_boundaries else None
                ),
            )
        elif hasattr(self, '_multiclip_boundaries') and self._multiclip_boundaries:
            self._schedule_native_editor_post_open_tasks(
                editor,
                load_multiclip_waveform_callback=_deferred_multiclip_waveform_load,
                preload_segments_callback=_deferred_preload_existing_multiclip_segments,
            )
        if hasattr(self, "_refresh_work_mode_ui"):
            QTimer.singleShot(120, self._refresh_work_mode_ui)
        if hasattr(self, "_release_ai_models_for_editor_mode"):
            QTimer.singleShot(260, self._release_ai_models_for_editor_mode)
        if is_batch and hasattr(editor, "_load_queue_clip_media_staged"):
            QTimer.singleShot(
                0,
                lambda e=editor, p=target_file: e._load_queue_clip_media_staged(
                    p,
                    auto_start=True,
                ),
            )
        else:
            self._schedule_native_open_editor_media(editor, target_file)
        get_logger().log_perf(
            "editor.init",
            event="ready",
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            batch=bool(is_batch),
            multiclip=bool(hasattr(self, "_multiclip_boundaries") and self._multiclip_boundaries),
            project_clips=len(list(getattr(editor, "_project_clips", []) or [])),
        )

    def _remove_old_editor(self):
        old = getattr(self, "_editor_widget", None)
        if not old:
            return
        try:
            flusher = getattr(old, "_flush_deferred_project_save", None)
            if callable(flusher):
                flusher(reason="editor_remove")
        except Exception as exc:
            get_logger().log(f"⚠️ 에디터 교체 전 프로젝트 지연 저장 실패: {exc}")
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
            try:
                old._cleanup()
            except (AttributeError, RuntimeError, TypeError) as exc:
                get_logger().log(f"⚠️ 에디터 정리 중 _cleanup 실패: {exc}")
        if hasattr(old, 'video_player'):
            try:
                vp = old.video_player
                if hasattr(vp, '_ui_timer'):
                    vp._ui_timer.stop()
                if hasattr(vp, 'audio_player'):
                    vp.audio_player.stop()
                if hasattr(vp, '_worker') and getattr(vp, '_worker', None):
                    vp._worker.stop()
                    vp._worker.wait(200)
            except (AttributeError, RuntimeError, TypeError) as exc:
                get_logger().log(f"⚠️ 에디터 정리 중 비디오 플레이어 종료 실패: {exc}")
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

            skip_confirm_once = bool(getattr(self._editor_widget, '_skip_prev_confirm_once', False))
            if skip_confirm_once:
                self._editor_widget._skip_prev_confirm_once = False
                skip_clean = True
                try:
                    dirty_checker = getattr(self._editor_widget, "_has_unsaved_changes", None)
                    skip_clean = not callable(dirty_checker) or not bool(dirty_checker())
                except Exception:
                    skip_clean = True
                if skip_clean:
                    try:
                        flusher = getattr(self._editor_widget, "_flush_deferred_project_save", None)
                        if callable(flusher):
                            flusher(reason="close_clean")
                    except Exception as exc:
                        get_logger().log(f"⚠️ 종료 전 프로젝트 지연 저장 실패: {exc}")
                    event.accept()
                    return

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
                try:
                    flusher = getattr(self._editor_widget, "_flush_deferred_project_save", None)
                    if callable(flusher):
                        flusher(reason="close_clean")
                except Exception as exc:
                    get_logger().log(f"⚠️ 종료 전 프로젝트 지연 저장 실패: {exc}")
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
