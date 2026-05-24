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

    @staticmethod
    def _post_completion_sync_segment_signature(rows) -> tuple[tuple[float, float, str], ...]:
        signature: list[tuple[float, float, str]] = []
        for raw_seg in list(rows or []):
            if not isinstance(raw_seg, dict):
                continue
            if raw_seg.get("is_gap") or raw_seg.get("stt_pending") or raw_seg.get("_live_stt_preview") or raw_seg.get("_live_subtitle_preview"):
                continue
            text = str(raw_seg.get("text", "") or "").strip()
            if not text:
                continue
            try:
                start = float(raw_seg.get("start", 0.0) or 0.0)
                end = float(raw_seg.get("end", start) or start)
            except Exception:
                continue
            if end <= start:
                continue
            signature.append((round(start, 3), round(end, 3), text))
        return tuple(signature)

    @staticmethod
    def _post_completion_sync_is_transient_stt_row(row: dict) -> bool:
        if not isinstance(row, dict):
            return False
        return bool(
            row.get("stt_pending")
            or row.get("_live_stt_preview")
            or row.get("_live_subtitle_preview")
        )

    def _post_completion_sync_allows_stt_work_rows(self, rows: list[dict] | None = None) -> bool:
        if bool(getattr(self, "_stt_mode_enabled", False)):
            return True
        for row in list(rows or []):
            if isinstance(row, dict) and bool(row.get("stt_mode")):
                return True
        return False

    def _post_completion_sync_confirmed_segments(self) -> list[dict]:
        getter = getattr(self, "_get_current_segments", None)
        rows = []
        if callable(getter):
            try:
                rows = list(getter(force_rebuild=True) or [])
            except TypeError:
                rows = list(getter() or [])
            except Exception:
                rows = []
        if not rows:
            rows = list(getattr(self, "_cached_segs", []) or [])
        allow_stt_work_rows = self._post_completion_sync_allows_stt_work_rows(rows)
        return [
            dict(seg)
            for seg in rows
            if isinstance(seg, dict)
            and not bool(seg.get("is_gap"))
            and (allow_stt_work_rows or not self._post_completion_sync_is_transient_stt_row(seg))
        ]

    def _safe_enable_start_btn(self):
        try:
            if hasattr(self, "btn_start") and self.btn_start:
                self.btn_start.setEnabled(True)
                main_w = self.window()
                sync_menu = getattr(main_w, "sync_menu_from_editor", None)
                if callable(sync_menu):
                    sync_menu(self)
        except RuntimeError:
            pass

    def _mark_open_media_start_ready(self, *, reason: str = "") -> bool:
        try:
            if bool(getattr(self, "_is_ai_processing", False)):
                return False
            sm = getattr(self, "sm", None)
            if str(getattr(sm, "state", "") or "") == "ST_PROC":
                return False
            btn = getattr(self, "btn_start", None)
            if btn is None:
                return False
            clean = getattr(self, "_clean_action_label", None)
            text = clean("시작") if callable(clean) else "시작"
            btn.setText(text)
            btn.setEnabled(True)
            self._last_start_button_signature = (text, True)
            main_w = self.window()
            sync_menu = getattr(main_w, "sync_menu_from_editor", None)
            if callable(sync_menu):
                sync_menu(self)
            if reason:
                get_logger().log_perf("editor.open", event="start_ready", reason=str(reason))
            return True
        except RuntimeError:
            return False

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
        safe_enable = getattr(self, "_safe_enable_start_btn", None)
        if callable(safe_enable):
            QTimer.singleShot(120, safe_enable)

    def _fail_generation_completion_without_segments(self, *, reason: str = "backend_done"):
        """Leave processing mode when backend completion produced no final rows."""
        get_logger().log("⚠️ 자막 생성 완료 보류 해제: 최종 자막 세그먼트가 없어 재시작 대기 상태로 복귀합니다.")
        for attr_name, value in (
            ("_completion_handled", False),
            ("_process_completed_finalized", True),
            ("_generation_completion_autosave_pending", False),
            ("_is_ai_processing", False),
            ("_live_editor_preview_pending", False),
            ("_backend_finished", True),
        ):
            try:
                setattr(self, attr_name, value)
            except Exception:
                pass
        self._abort_pending_editor_processing_ui_work()
        self._clear_processing_indicators()
        try:
            self.sm.stop_processing("⚠️ 최종 자막 세그먼트 없음")
        except Exception as exc:
            self._pipeline_log_nonfatal("최종 자막 없음 상태 전환", exc)
        main_w = self._pipeline_window()
        if main_w is not None:
            for backend in (getattr(main_w, "backend", None), getattr(main_w, "backend_fast", None)):
                if backend is None:
                    continue
                try:
                    setattr(backend, "_active", False)
                except Exception:
                    pass
            self._pipeline_call_if_callable(
                main_w,
                "_unlock_workspace_sidebar_width",
                label="최종 자막 없음 사이드바 잠금 해제",
                log=False,
            )
            self._pipeline_call_if_callable(
                main_w,
                "sync_menu_from_editor",
                self,
                label="최종 자막 없음 메뉴 동기화",
                log=False,
            )
            try:
                setattr(main_w, "_auto_processing_active", False)
            except Exception:
                pass
        safe_enable = getattr(self, "_safe_enable_start_btn", None)
        if callable(safe_enable):
            QTimer.singleShot(120, safe_enable)

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
                self._fail_generation_completion_without_segments(reason=str(reason or "backend_done"))
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
        if bool(getattr(self, "_generation_completion_autosave_done", False)):
            self._generation_completion_autosave_pending = False
            return
        if bool(getattr(self, "_generation_completion_autosave_pending", False)) and int(attempt or 0) <= 0:
            return
        self._generation_completion_autosave_pending = True

        def run_autosave() -> None:
            self._run_generation_completion_autosave(attempt=int(attempt or 0))

        single_shot = getattr(self, "_pipeline_single_shot", None)
        if callable(single_shot):
            single_shot(int(delay_ms), run_autosave)
        else:
            QTimer.singleShot(int(delay_ms), run_autosave)

    def _run_generation_completion_autosave(self, attempt: int = 0) -> None:
        self._generation_completion_autosave_pending = False
        if bool(getattr(self, "_generation_completion_autosave_done", False)):
            return

        if not self._has_saveable_generation_segments():
            recovered = bool(
                self._pipeline_best_effort(
                    self._recover_generation_segments_from_backend_backup,
                    label="생성 완료 autosave 전 최종 자막 복구",
                    default=False,
                    log=False,
                )
            )
            if not recovered and int(attempt or 0) < 20:
                if int(attempt or 0) in {0, 3, 8, 15}:
                    get_logger().log("⏳ 생성 완료 저장 대기: final 자막 세그먼트 반영을 기다립니다.")
                self._schedule_generation_completion_autosave(delay_ms=500, attempt=int(attempt or 0) + 1)
                return
            if not self._has_saveable_generation_segments():
                get_logger().log("⚠️ 생성 완료 저장 보류: 저장 가능한 final 자막 세그먼트가 없습니다.")
                return

        saver = getattr(self, "_on_save", None)
        if not callable(saver):
            return
        try:
            # 생성 완료 autosave는 프로젝트/SRT만 확정하고, 뒤따라오는 러프컷 LLM 예약은 취소하지 않는다.
            saved = bool(
                saver(
                    skip_auto_next=True,
                    schedule_analysis_refresh=False,
                    queue_learning=False,
                    auto_export=False,
                    force=True,
                    cancel_post_generation_roughcut=False,
                )
            )
        except TypeError:
            saved = bool(
                saver(
                    skip_auto_next=True,
                    schedule_analysis_refresh=False,
                    queue_learning=False,
                    auto_export=False,
                )
            )
        except Exception as exc:
            get_logger().log(f"⚠️ 생성 완료 저장 실패: {exc}")
            saved = False
        if saved:
            self._generation_completion_autosave_done = True
            get_logger().log("💾 생성 완료 자막 자동 저장 완료")
            return
        if int(attempt or 0) < 5:
            self._schedule_generation_completion_autosave(delay_ms=800, attempt=int(attempt or 0) + 1)

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
        allow_checker = getattr(self, "_post_completion_sync_allows_stt_work_rows", None)
        if callable(allow_checker):
            allow_stt_work_rows = bool(allow_checker())
        else:
            allow_stt_work_rows = EditorPipelineCleanupMixin._post_completion_sync_allows_stt_work_rows(self)
        has_preview_state = any(
            bool(getattr(self, attr, None))
            for attr in (
                "_live_editor_preview_segments",
                "_live_editor_preview_queue",
            )
        )
        has_live_blocks = False
        has_transient_stt_blocks = False
        text_edit = getattr(self, "text_edit", None)
        if text_edit is not None and hasattr(text_edit, "document"):
            try:
                block = text_edit.document().begin()
                while block.isValid():
                    data = block.userData()
                    if getattr(data, "live_preview", False):
                        has_live_blocks = True
                        break
                    if (
                        not allow_stt_work_rows
                        and getattr(data, "stt_pending", False)
                    ):
                        has_transient_stt_blocks = True
                    block = block.next()
            except Exception:
                has_live_blocks = False
                has_transient_stt_blocks = False
        if not has_preview_state and not has_live_blocks and not has_transient_stt_blocks:
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
            and (allow_stt_work_rows or not self._post_completion_sync_is_transient_stt_row(seg))
            and (
                str(seg.get("text", "") or "").strip()
                or (
                    allow_stt_work_rows
                    and (
                        bool(seg.get("stt_pending"))
                        or bool(seg.get("stt_mode"))
                    )
                )
            )
        ]
        if confirmed_rows or has_preview_state or has_live_blocks or has_transient_stt_blocks:
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
            confirmed = self._post_completion_sync_confirmed_segments()
            canvas_segments = list(getattr(canvas, "segments", []) or []) if canvas is not None else []
            confirmed_signature = self._post_completion_sync_segment_signature(confirmed)
            canvas_signature = self._post_completion_sync_segment_signature(canvas_segments)
            allow_stt_work_rows = self._post_completion_sync_allows_stt_work_rows(confirmed)
            canvas_has_transient = any(
                self._post_completion_sync_is_transient_stt_row(seg)
                for seg in canvas_segments
                if isinstance(seg, dict)
            )
            timeline_current = (
                bool(confirmed_signature)
                and canvas_signature == confirmed_signature
                and (allow_stt_work_rows or not canvas_has_transient)
            )
            if not timeline_current:
                # 변경 금지: 마카오 케이스처럼 저장된 최종 자막/왼쪽 편집문서는 이미
                # 올바른데 타임라인만 예전 경계를 붙잡는 경우가 있었다. 첫/마지막
                # 세그먼트만 비교하면 중간 경계 이동(예: "가자" -> "하나 들고 가시모")
                # 을 놓친다. 또 STT2 임시 row("-")가 final row처럼 남으면 에디터와
                # 타임라인 글자가 달라진다. 완료 시점에는 문서 전체 경계/텍스트와
                # 임시 row 잔존 여부까지 확인하고, 다르면 최신 문서 세그먼트만
                # 캐시에 재주입한 뒤 타임라인을 강제로 다시 그려야 동일한 오차가
                # 재발하지 않는다.
                if not allow_stt_work_rows:
                    # 변경 금지: STT1/2 후보 레인은 final 자막과 별개로 사용자가
                    # 직접 비교/선택하는 원본 증거다. 완료 후 ghost row("-")를
                    # 지운다고 _live_stt_preview_segments까지 비우면 마카오 영상처럼
                    # STT 후보가 사라져 최종 자막 선행/오인식 원인을 확인할 수 없다.
                    # 타임라인 ghost row는 아래 cache 재주입과 redraw로만 제거한다.
                    for attr, value in (
                        ("_live_editor_preview_segments", []),
                        ("_live_editor_preview_queue", []),
                        ("_live_editor_preview_keys", set()),
                    ):
                        try:
                            setattr(self, attr, value.copy() if hasattr(value, "copy") else value)
                        except Exception:
                            pass
                cache_writer = getattr(self, "_cache_current_segments", None)
                if callable(cache_writer):
                    try:
                        cache_writer(confirmed)
                    except Exception:
                        pass
                else:
                    try:
                        self._cached_segs = [dict(seg) for seg in confirmed]
                    except Exception:
                        pass
                self._redraw_timeline()
        except Exception:
            pass
        try:
            if hasattr(self, "timeline"):
                boxes = list(getattr(self.timeline.canvas, "_multiclip_boxes", []) or [])
                # 변경 금지: 자막/러프컷 완료 후처리는 사용자가 보고 있던 8초 창과
                # 스크롤 위치를 옮기면 안 된다. fit_to_view()를 여기서 호출하면
                # 러프컷 LLM 완료 직후 화면이 원복되듯 움직이고, 버튼/포커스 상태도
                # 흔들린다. 완료 후에는 캔버스 데이터만 갱신한다.
                if boxes:
                    gc = self.timeline.global_canvas
                    gc.total_duration = self.timeline.canvas.total_duration
                    gc.update()
                    if hasattr(self.timeline.canvas, "_update_viewport_region"):
                        self.timeline.canvas._update_viewport_region()
                    else:
                        self.timeline.canvas.update()
        except Exception:
            pass
        try:
            if hasattr(self, "_resolve_active_context") and hasattr(self, "_apply_active_context"):
                ctx = self._resolve_active_context()
                self._apply_active_context(ctx, autoplay=False, show_thumbnail=True)
        except Exception:
            pass
