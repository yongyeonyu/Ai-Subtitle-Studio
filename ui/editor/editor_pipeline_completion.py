from __future__ import annotations

from core.runtime.logger import get_logger


class EditorPipelineCompletionMixin:
    def _pipeline_single_shot(self, delay_ms: int, callback) -> None:
        from ui.editor import editor_pipeline as editor_pipeline_module

        editor_pipeline_module.QTimer.singleShot(int(delay_ms), callback)

    def _generation_completion_window(self):
        try:
            return self.window()
        except Exception:
            return None

    def _safe_generation_completion_step(self, action, *, label: str, warn: str | None = None, default=None):
        try:
            return action()
        except Exception as exc:
            if warn:
                get_logger().log(f"⚠️ {warn}: {exc}")
            elif label:
                get_logger().log(f"⚠️ 생성 완료 {label} 실패: {exc}")
            return default

    def _generation_completion_segments_for_learning(self) -> list[dict]:
        getter = getattr(self, "_get_current_segments", None)
        if not callable(getter):
            return []
        segments = self._safe_generation_completion_step(
            lambda: list(getter() or []),
            label="현재 세그먼트 스냅샷",
            default=[],
        )
        return [dict(seg) for seg in segments if isinstance(seg, dict) and not seg.get("is_gap")]

    def _mark_generation_complete_state(self) -> None:
        if getattr(self, "is_auto_start", False):
            self.sm.complete_auto_mode()
        else:
            self.sm.complete_ai()

    def _sync_generation_complete_ui(self, main_w) -> None:
        force_idle = getattr(main_w, "_force_editor_idle_after_generation", None)
        if callable(force_idle):
            force_idle(self, reason="subtitle_generation_complete")
        sync_menu = getattr(main_w, "sync_menu_from_editor", None)
        if callable(sync_menu):
            sync_menu(self)
        refresh_saved = getattr(main_w, "_refresh_saved_status_label", None)
        if callable(refresh_saved):
            refresh_saved(is_dirty=True)

    def _generation_complete_hold_ms(self) -> int:
        hold_ms = 600_000
        hold_getter = getattr(self, "_deferred_editor_learning_hold_ms", None)
        if callable(hold_getter):
            parsed = self._safe_generation_completion_step(
                lambda: int(hold_getter(trigger="generation_complete") or hold_ms),
                label="개인화 hold 계산",
                default=hold_ms,
            )
            hold_ms = int(parsed or hold_ms)
        return hold_ms

    def _queue_generation_complete_learning(self, main_w) -> None:
        try:
            from core.personalization.deferred_editor_learning import enqueue_deferred_editor_learning
        except Exception as exc:
            get_logger().log(f"⚠️ 개인화 학습 큐 로더 실패(생성완료): {exc}")
            return

        hold_ms = self._generation_complete_hold_ms()
        pause_lora = getattr(main_w, "_pause_personalization_for_foreground_activity", None)
        if callable(pause_lora):
            paused = self._safe_generation_completion_step(
                lambda: pause_lora("subtitle_generation_complete", hold_ms=hold_ms),
                label="개인화 foreground pause",
                default=False,
            )
            if paused is False:
                self._safe_generation_completion_step(
                    lambda: pause_lora("subtitle_generation_complete"),
                    label="개인화 foreground pause fallback",
                    default=False,
                )
        queued = self._safe_generation_completion_step(
            lambda: enqueue_deferred_editor_learning(
                self._generation_completion_segments_for_learning(),
                media_path=str(getattr(self, "media_path", "") or ""),
                subtitle_path="",
                project_path=str(getattr(main_w, "_current_project_path", "") or ""),
                trigger="generation_complete",
                settings=dict(getattr(self, "settings", {}) or {}),
                defer_for_ms=hold_ms,
            ),
            label="개인화 학습 큐 등록",
            warn="개인화 학습 큐 등록 실패(생성완료)",
            default={},
        )
        if isinstance(queued, dict) and queued.get("queued"):
            get_logger().log("🧠 [LoRA] 생성 완료 학습은 Home-idle 큐로 넘겼습니다.")

    def _run_generation_complete_cleanup(self, main_w) -> None:
        cleanup = getattr(main_w, "_post_generation_resource_cleanup", None)
        if callable(cleanup):
            self._safe_generation_completion_step(
                lambda: cleanup(reason="subtitle_generation_complete", editor=self),
                label="후처리 리소스 정리",
            )
        stale_cleanup = getattr(self, "_clear_stale_cut_boundary_scan_after_completion", None)
        if callable(stale_cleanup):
            self._safe_generation_completion_step(
                stale_cleanup,
                label="컷 경계 placeholder 정리",
            )

    def _schedule_generation_complete_followups(self, main_w, *, suppress_post_generation_tasks: bool) -> None:
        if suppress_post_generation_tasks:
            self._pipeline_single_shot(0, self._post_completion_sync)
            return
        start_idle = getattr(main_w, "_start_post_completion_idle_timer", None)
        if callable(start_idle):
            start_idle()
        roughcut = getattr(self, "_schedule_post_generation_roughcut_draft", None)
        if callable(roughcut):
            self._pipeline_single_shot(900, lambda: roughcut(force=True))
        self._pipeline_single_shot(200, self._post_completion_sync)
        self._schedule_generation_completion_autosave(delay_ms=650)
        unlock_sidebar = getattr(main_w, "_unlock_workspace_sidebar_width", None)
        if callable(unlock_sidebar):
            self._pipeline_single_shot(1300, unlock_sidebar)

    def _set_process_completed(self, *, suppress_post_generation_tasks: bool = False):
        if bool(getattr(self, "_process_completed_finalized", False)):
            if not bool(suppress_post_generation_tasks):
                self._schedule_generation_completion_autosave(delay_ms=250)
            return
        self._process_completed_finalized = True
        flusher = getattr(self, "_flush_pending_segment_queue_now", None)
        if callable(flusher):
            self._safe_generation_completion_step(
                flusher,
                label="전 세그먼트 flush",
                warn="생성 완료 전 세그먼트 flush 실패",
            )
        clear_preview = getattr(self, "_clear_live_generation_preview_artifacts", None)
        if callable(clear_preview):
            self._safe_generation_completion_step(
                clear_preview,
                label="preview 정리",
                warn="생성 완료 preview 정리 실패",
            )
        self._safe_generation_completion_step(
            self._mark_generation_complete_state,
            label="상태 전환",
            warn="생성 완료 상태 전환 실패",
        )
        clear_indicators = getattr(self, "_clear_processing_indicators", None)
        if callable(clear_indicators):
            self._safe_generation_completion_step(
                clear_indicators,
                label="processing indicator 정리",
            )
        main_w = self._generation_completion_window()
        if main_w is not None:
            self._safe_generation_completion_step(
                lambda: self._sync_generation_complete_ui(main_w),
                label="메인 윈도우 동기화",
            )
        get_logger().log("✅ 자막 생성 완료 (EditorPipeline 확정)")
        if bool(suppress_post_generation_tasks):
            self._schedule_generation_complete_followups(main_w, suppress_post_generation_tasks=True)
            return
        if main_w is not None:
            self._queue_generation_complete_learning(main_w)
            self._run_generation_complete_cleanup(main_w)
        self._schedule_generation_complete_followups(main_w, suppress_post_generation_tasks=False)
