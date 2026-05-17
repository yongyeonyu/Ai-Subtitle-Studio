"""Processing and generation-completion cleanup helpers for editor pipeline."""

from __future__ import annotations

import os
import threading
import unicodedata

from PyQt6.QtCore import QTimer

from core.runtime.logger import get_logger
from ui.editor.editor_pipeline_safety import EditorPipelineSafetyMixin


class EditorPipelineCleanupMixin(EditorPipelineSafetyMixin):
    @staticmethod
    def _generation_media_paths_match(left_path: str, right_path: str) -> bool:
        left = str(left_path or "").strip()
        right = str(right_path or "").strip()
        if not left or not right:
            return False
        left_nfc = unicodedata.normalize("NFC", left)
        right_nfc = unicodedata.normalize("NFC", right)
        if os.path.normcase(os.path.normpath(left_nfc)) == os.path.normcase(os.path.normpath(right_nfc)):
            return True
        try:
            if os.path.exists(left_nfc) and os.path.exists(right_nfc) and os.path.samefile(left_nfc, right_nfc):
                return True
        except Exception:
            pass
        return False

    def _clear_processing_indicators(self):
        self._last_live_processing_stage = ""
        self._next_live_processing_stage_at = 0.0
        self._pipeline_stop_timer(getattr(self, "_spinner_timer", None), label="spinner timer 정지")

    def _safe_enable_start_btn(self):
        try:
            if hasattr(self, "btn_start") and self.btn_start:
                self.btn_start.setEnabled(True)
        except RuntimeError:
            pass

    def _abort_pending_editor_processing_ui_work(self):
        for timer_name in (
            "_queue_timer",
            "_live_editor_preview_timer",
            "_timeline_timer",
            "_video_context_refresh_timer",
            "_cursor_video_seek_timer",
        ):
            self._pipeline_stop_timer(getattr(self, timer_name, None), label=f"{timer_name} 정지")
        self._pipeline_clear_attr("_segment_queue", label="세그먼트 queue 정리")
        self._pipeline_call_if_callable(
            self,
            "_clear_live_editor_preview_blocks",
            label="live editor preview block 정리",
            log=False,
        )
        self._pipeline_clear_attr("_live_editor_preview_queue", label="live editor preview queue 정리")
        self._pipeline_clear_attr("_live_editor_preview_keys", label="live editor preview key 정리")
        self._pipeline_set_attr("_pending_cursor_video_seek_sec", None, label="cursor seek pending 초기화")
        self._pipeline_set_attr("_live_editor_preview_pending", False, label="live editor preview pending 초기화")

    def _stop_pipeline(self):
        main_w = self._pipeline_window()
        self._pipeline_call_if_callable(
            main_w,
            "_stop_post_completion_idle_timer",
            label="post completion idle timer 정지",
            log=False,
        )
        self._abort_pending_editor_processing_ui_work()
        self.sm.stop_processing("작업이 중지되었습니다.")
        self._clear_processing_indicators()
        active_backend = None
        if hasattr(main_w, "backend_fast") and getattr(main_w.backend_fast, "_active", False):
            active_backend = main_w.backend_fast
        elif hasattr(main_w, "backend") and main_w.backend:
            active_backend = main_w.backend
        if active_backend is not None:
            self._pipeline_best_effort(
                lambda: (
                    setattr(active_backend, "_active", False),
                    active_backend._edit_event.set() if hasattr(active_backend, "_edit_event") else None,
                    active_backend._start_event.set() if hasattr(active_backend, "_start_event") else None,
                ),
                label="backend 중지 신호 설정",
                log=False,
            )
            try:
                from PyQt6.QtCore import QEventLoop
                from PyQt6.QtWidgets import QApplication

                app = QApplication.instance()
                if app is not None:
                    app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
            except Exception as exc:
                self._pipeline_log_nonfatal("backend stop 전 event flush", exc)
            active_backend.stop(log_context="작업 중지")
        self._pipeline_call_if_callable(
            main_w,
            "_unlock_workspace_sidebar_width",
            label="사이드바 폭 잠금 해제",
            log=False,
        )
        QTimer.singleShot(120, self._safe_enable_start_btn)

    def _finalize_generation_from_backend(self, *, reason: str = "backend_done", attempt: int = 0):
        """Backend-side completion safety net for missed final progress signals."""
        if not bool(getattr(self, "_process_completed_finalized", False)):
            if not self._has_saveable_generation_segments():
                recovered = bool(
                    self._pipeline_best_effort(
                        self._recover_generation_segments_from_backend_backup,
                        label="자막 생성 완료 복구",
                        default=False,
                    )
                )
                if recovered:
                    self._pipeline_set_attr("_completion_handled", True, label="completion handled 설정")
                    self._set_process_completed()
                    return
                if int(attempt) < 60:
                    if int(attempt) in {0, 5, 15, 30}:
                        get_logger().log("⏳ 자막 생성 완료 대기: 최종 자막 세그먼트 반영 중")
                    self._pipeline_best_effort(
                        lambda: self.sm.update_progress(0, 1, 0, "⏳ 최종 자막 반영 중..."),
                        label="생성 완료 대기 상태 표시",
                        log=False,
                    )
                    QTimer.singleShot(
                        500,
                        lambda r=str(reason or "backend_done"), a=int(attempt) + 1: self._finalize_generation_from_backend(
                            reason=r,
                            attempt=a,
                        ),
                    )
                    return
                get_logger().log("⚠️ 자막 생성 완료 보류: 저장 가능한 최종 자막 세그먼트를 찾지 못했습니다.")
                self._pipeline_best_effort(
                    lambda: self.sm.update_progress(0, 1, 0, "⚠️ 최종 자막 세그먼트 없음"),
                    label="생성 완료 보류 상태 표시",
                    log=False,
                )
                return
            self._pipeline_set_attr("_completion_handled", True, label="completion handled 설정")
            self._set_process_completed()
            return
        self._schedule_generation_completion_autosave(delay_ms=250)

    def _has_saveable_generation_segments(self) -> bool:
        if getattr(self, "_segment_queue", None) and hasattr(self, "_flush_pending_segment_queue_now"):
            self._pipeline_call_if_callable(
                self,
                "_flush_pending_segment_queue_now",
                label="저장 가능 세그먼트 검사 전 flush",
                log=False,
            )
        segments = self._pipeline_best_effort(
            lambda: list(self._get_current_segments() or []),
            label="현재 세그먼트 조회",
            default=[],
            log=False,
        )
        for seg in segments:
            if not isinstance(seg, dict) or bool(seg.get("is_gap")):
                continue
            if str(seg.get("text", "") or "").strip():
                return True
        return False

    def _recover_generation_segments_from_backend_backup(self) -> bool:
        main_w = self._pipeline_window()
        if main_w is None:
            return False
        editor_media = str(getattr(self, "media_path", "") or "")
        backend = None
        backup_segments: list[dict] = []
        for candidate in (
            getattr(main_w, "backend_fast", None),
            getattr(main_w, "backend", None),
        ):
            if candidate is None:
                continue
            backup_media = str(getattr(candidate, "_last_generation_final_media_path", "") or "")
            if backup_media and editor_media and not self._generation_media_paths_match(backup_media, editor_media):
                continue
            candidate_segments = [
                dict(seg)
                for seg in list(getattr(candidate, "_last_generation_final_segments", []) or [])
                if isinstance(seg, dict)
            ]
            candidate_segments = [
                dict(seg)
                for seg in candidate_segments
                if not bool(seg.get("is_gap")) and str(seg.get("text", "") or "").strip()
            ]
            if not candidate_segments:
                continue
            backend = candidate
            backup_segments = candidate_segments
            break
        if backend is None or not backup_segments:
            return False
        get_logger().log("⚠️ 에디터 최종 자막 누락 감지: 백엔드 결과로 즉시 복구합니다.")
        appender = getattr(self, "append_segments", None)
        if not callable(appender):
            return False
        appender(backup_segments)
        flusher = getattr(self, "_flush_pending_segment_queue_now", None)
        if callable(flusher):
            flusher()
        restored = self._has_saveable_generation_segments()
        if restored:
            self._pipeline_best_effort(
                lambda: setattr(backend, "_last_generation_final_segments", []),
                label="백엔드 최종 세그먼트 백업 초기화",
                log=False,
            )
        return restored

    def _clear_stale_cut_boundary_scan_after_completion(self) -> bool:
        main_w = self._pipeline_window()
        if main_w is None:
            return False
        backend_candidates = [
            getattr(main_w, "backend", None),
            getattr(main_w, "backend_fast", None),
        ]
        scan_busy = False
        for backend in backend_candidates:
            if backend is None:
                continue
            try:
                prescan = getattr(backend, "_cut_boundary_prescan_thread", None)
                follower = getattr(backend, "_cut_boundary_follower_thread", None)
                if (prescan is not None and prescan.is_alive()) or (follower is not None and follower.is_alive()):
                    scan_busy = True
                    break
            except Exception:
                continue
        if scan_busy:
            return False
        self._pipeline_call_if_callable(
            self,
            "_set_auto_cut_boundary_scan_active",
            False,
            label="컷 경계 scan active 초기화",
            log=False,
        )
        self._pipeline_call_if_callable(
            self,
            "_set_auto_cut_boundary_scan_lines",
            [],
            label="컷 경계 scan line 초기화",
            log=False,
        )
        refresher = getattr(self, "_refresh_cut_boundary_placeholder_from_project", None)
        if callable(refresher):
            QTimer.singleShot(0, refresher)
        return True

    def _schedule_generation_completion_autosave(self, *, delay_ms: int = 650, attempt: int = 0) -> None:
        self._generation_completion_autosave_pending = False
        return

    def _run_generation_completion_autosave(self, attempt: int = 0) -> None:
        self._generation_completion_autosave_pending = False
        return

    def _schedule_post_generation_model_release(self):
        """자막 생성 완료 후 남아 있는 AI/STT/LLM 모델 언로드를 예약한다."""
        try:
            if hasattr(self, "_schedule_post_generation_roughcut_draft"):
                self._release_ai_models_after_roughcut_draft()
                return
            main_w = self.window()
        except RuntimeError:
            return
        except Exception:
            return
        release = getattr(main_w, "_release_ai_models_for_editor_mode", None)
        if callable(release):
            release(force=True)

    def _roughcut_draft_cleanup_pending(self) -> bool:
        status = str(getattr(self, "_roughcut_draft_status", "") or "")
        if status in {"queued", "running", "saving"}:
            return True
        try:
            timer = getattr(self, "_roughcut_draft_timer", None)
            if timer is not None and timer.isActive():
                return True
        except RuntimeError:
            return False
        except Exception:
            pass
        try:
            thread = getattr(self, "_roughcut_draft_thread", None)
            if thread is not None and thread.is_alive():
                return True
        except Exception:
            pass
        return bool(getattr(self, "_roughcut_draft_pending", False))

    def _release_ai_models_after_roughcut_draft(self):
        is_busy = self._roughcut_draft_cleanup_pending()

        if not is_busy:
            for worker in threading.enumerate():
                if worker.is_alive() and any(x in worker.name.lower() for x in ["stt", "ensemble", "optimizer", "preview"]):
                    is_busy = True
                    break

        if is_busy:
            QTimer.singleShot(500, self._release_ai_models_after_roughcut_draft)
            return

        try:
            main_w = self.window()
        except RuntimeError:
            return
        release = getattr(main_w, "_release_ai_models_for_editor_mode", None)
        if callable(release):
            release(force=True, preserve_roughcut_status=True)

    def _clear_live_generation_preview_artifacts(self) -> bool:
        """Rebuild the editor from confirmed rows to drop transient live previews."""
        has_preview_state = any(
            bool(getattr(self, attr, None))
            for attr in (
                "_live_editor_preview_segments",
                "_live_editor_preview_queue",
            )
        )
        has_live_blocks = False
        text_edit = getattr(self, "text_edit", None)
        if text_edit is not None and hasattr(text_edit, "document"):
            try:
                block = text_edit.document().begin()
                while block.isValid():
                    data = block.userData()
                    if getattr(data, "live_preview", False):
                        has_live_blocks = True
                        break
                    block = block.next()
            except Exception:
                has_live_blocks = False
        if not has_preview_state and not has_live_blocks:
            return False

        try:
            current = list(self._get_current_segments(force_rebuild=True) or [])
        except TypeError:
            current = list(self._get_current_segments() or [])
        except Exception:
            current = []
        current = [dict(seg) for seg in current if isinstance(seg, dict)]
        confirmed_rows = [
            dict(seg)
            for seg in current
            if not bool(seg.get("is_gap"))
            and (
                str(seg.get("text", "") or "").strip()
                or bool(seg.get("stt_pending"))
                or bool(seg.get("stt_mode"))
            )
        ]
        if confirmed_rows:
            current = confirmed_rows

        try:
            timer = getattr(self, "_live_editor_preview_timer", None)
            if timer is not None and hasattr(timer, "stop"):
                timer.stop()
        except Exception:
            pass
        try:
            if hasattr(self, "_live_editor_preview_queue"):
                self._live_editor_preview_queue = []
        except Exception:
            pass
        try:
            if hasattr(self, "_live_editor_preview_segments"):
                self._live_editor_preview_segments = []
        except Exception:
            pass
        try:
            if hasattr(self, "_live_editor_preview_keys"):
                self._live_editor_preview_keys = set()
        except Exception:
            pass

        reloader = getattr(self, "_reload_segments_from_list", None)
        if callable(reloader):
            reloader(current, preserve_view=True, mark_dirty=False)
        else:
            try:
                self._segment_cache_valid = False
            except Exception:
                pass
            try:
                refresher = getattr(self, "_refresh_video_subtitle_context", None)
                if callable(refresher):
                    refresher()
            except Exception:
                pass
            try:
                redraw = getattr(self, "_redraw_timeline", None)
                if callable(redraw):
                    redraw()
            except Exception:
                pass
        return True

    def _post_completion_sync(self):
        """E fix: 자막 생성 완료 후 타임라인/글로벌 캔버스 재동기화"""
        try:
            timeline = getattr(self, "timeline", None)
            canvas = getattr(timeline, "canvas", None)
            cached = [seg for seg in list(getattr(self, "_cached_segs", []) or []) if not seg.get("is_gap")]
            canvas_segments = list(getattr(canvas, "segments", []) or []) if canvas is not None else []
            timeline_current = bool(cached and len(canvas_segments) == len(cached))
            if timeline_current:
                try:
                    timeline_current = (
                        abs(float(canvas_segments[0].get("start", 0.0) or 0.0) - float(cached[0].get("start", 0.0) or 0.0)) < 0.001
                        and abs(float(canvas_segments[-1].get("end", 0.0) or 0.0) - float(cached[-1].get("end", 0.0) or 0.0)) < 0.001
                    )
                except Exception:
                    timeline_current = False
            if not timeline_current:
                self._redraw_timeline()
        except Exception:
            pass
        try:
            if hasattr(self, "timeline"):
                boxes = list(getattr(self.timeline.canvas, "_multiclip_boxes", []) or [])
                can_auto_fit = not bool(getattr(self.timeline, "_fit_to_view_locked", False)) and not bool(
                    getattr(self.timeline, "_manual_zoom_since_fit", False)
                )
                if boxes:
                    if can_auto_fit:
                        self.timeline.fit_to_view()
                    gc = self.timeline.global_canvas
                    gc.total_duration = self.timeline.canvas.total_duration
                    gc.update()
                    if hasattr(self.timeline.canvas, "_update_viewport_region"):
                        self.timeline.canvas._update_viewport_region()
                    else:
                        self.timeline.canvas.update()
                elif can_auto_fit:
                    self.timeline.fit_to_view()
        except Exception:
            pass
        try:
            if hasattr(self, "_resolve_active_context") and hasattr(self, "_apply_active_context"):
                ctx = self._resolve_active_context()
                self._apply_active_context(ctx, autoplay=False, show_thumbnail=True)
        except Exception:
            pass
