# Version: 03.13.05
# Phase: PHASE2
"""Post-generation roughcut draft helpers for the subtitle editor."""

from __future__ import annotations

import os
import threading
import time

from PyQt6.QtCore import QTimer

from core.runtime.logger import get_logger
from ui.project.project_session_runtime import attach_project_session
from ui.queue.queue_dispatch import dispatch_queue_status, find_queue_row_for_media, sync_saved_queue_state


class EditorRoughcutDraftMixin:
    def _cut_boundary_runtime_settled_for_roughcut(self) -> bool:
        if bool(getattr(self, "_auto_cut_boundary_scan_active", False)):
            return False
        try:
            main_w = self.window()
        except Exception:
            main_w = None
        for backend in (
            getattr(main_w, "backend", None),
            getattr(main_w, "backend_fast", None),
        ):
            if backend is None:
                continue
            try:
                prescan = getattr(backend, "_cut_boundary_prescan_thread", None)
                follower = getattr(backend, "_cut_boundary_follower_thread", None)
                if (prescan is not None and prescan.is_alive()) or (follower is not None and follower.is_alive()):
                    return False
            except Exception:
                continue
        runtime_rows = [
            dict(row)
            for row in list(getattr(self, "_auto_cut_boundary_scan_lines", []) or [])
            if isinstance(row, dict)
            and str(row.get("reason", "") or "") != "manual_roughcut_middle_right_click"
        ]
        if runtime_rows:
            return False
        try:
            project_path = str(getattr(main_w, "_current_project_path", "") or "")
        except Exception:
            project_path = ""
        if not project_path or not os.path.exists(project_path):
            return True
        try:
            from core.project.project_io import read_project_file

            project = read_project_file(project_path)
            analysis = project.get("analysis", {}) if isinstance(project.get("analysis"), dict) else {}
            provisional_rows = list(analysis.get("cut_boundary_provisional_boundaries") or [])
            return not bool(provisional_rows)
        except Exception:
            return True

    def _draft_reference_major_segments(self) -> list[dict]:
        try:
            window_owner = self.window()
        except Exception:
            window_owner = None
        preferred_rows = []
        fallback_rows = []
        for owner in (self, window_owner):
            if owner is None:
                continue
            for attr in (
                "_cut_boundary_topicless_middle_segments",
                "cut_boundary_topicless_middle_segments",
            ):
                raw = getattr(owner, attr, None)
                if isinstance(raw, list) and raw:
                    preferred_rows = [dict(row) for row in raw if isinstance(row, dict)]
                    if preferred_rows:
                        return preferred_rows
            for attr in (
                "_middle_segments",
                "middle_segments",
                "_roughcut_segments",
                "roughcut_segments",
            ):
                raw = getattr(owner, attr, None)
                if isinstance(raw, list) and raw:
                    fallback_rows = [dict(row) for row in raw if isinstance(row, dict)]
                    if fallback_rows:
                        break
        try:
            main_w = self.window()
            project_path = str(getattr(main_w, "_current_project_path", "") or "")
        except Exception:
            project_path = ""
        if not project_path:
            return []
        try:
            from core.project.project_io import read_project_file

            project = read_project_file(project_path)
            analysis = project.get("analysis", {}) if isinstance(project.get("analysis"), dict) else {}
            for key in (
                "cut_boundary_topicless_middle_segments",
                "topicless_middle_segments",
                "roughcut_topicless_segments",
            ):
                rows = analysis.get(key, [])
                if isinstance(rows, list) and rows:
                    return [dict(row) for row in rows if isinstance(row, dict)]
            rows = analysis.get("middle_segments", [])
            if isinstance(rows, list) and rows:
                return [dict(row) for row in rows if isinstance(row, dict)]
            rows = project.get("middle_segments", [])
            if isinstance(rows, list) and rows:
                return [dict(row) for row in rows if isinstance(row, dict)]
        except Exception:
            pass
        if fallback_rows:
            return fallback_rows
        return []

    def _draft_reviewed_cut_boundaries(self) -> list[dict]:
        try:
            window_owner = self.window()
        except Exception:
            window_owner = None
        for owner in (self, window_owner):
            if owner is None:
                continue
            for attr in (
                "_cut_boundary_reviewed_rows",
                "cut_boundary_reviewed_rows",
            ):
                raw = getattr(owner, attr, None)
                if isinstance(raw, list) and raw:
                    rows = [dict(row) for row in raw if isinstance(row, dict)]
                    if rows:
                        return rows
        try:
            main_w = self.window()
            project_path = str(getattr(main_w, "_current_project_path", "") or "")
        except Exception:
            project_path = ""
        if not project_path or not os.path.exists(project_path):
            return [dict(row) for row in list(getattr(self, "_auto_cut_boundary_scan_lines", []) or []) if isinstance(row, dict)]
        try:
            from core.project.project_io import read_project_file

            project = read_project_file(project_path)
            analysis = project.get("analysis", {}) if isinstance(project.get("analysis"), dict) else {}
            rows = list(
                analysis.get("cut_boundary_reviewed_rows")
                or analysis.get("cut_boundaries")
                or analysis.get("cut_boundary_provisional_boundaries")
                or []
            )
            return [dict(row) for row in rows if isinstance(row, dict)]
        except Exception:
            rows = list(getattr(self, "_cut_boundary_provisional_rows", []) or [])
            if not rows:
                rows = list(getattr(self, "_auto_cut_boundary_scan_lines", []) or [])
            return [dict(row) for row in rows if isinstance(row, dict)]

    def _apply_roughcut_middle_segments_to_ui(self, rows: list[dict], result) -> None:
        rows = [dict(row) for row in list(rows or []) if isinstance(row, dict)]
        preliminary_rows = [
            dict(row)
            for row in list(getattr(self, "_pending_preliminary_middle_segments", []) or [])
            if isinstance(row, dict)
        ]
        try:
            main_w = self.window()
        except Exception:
            main_w = None
        timeline = getattr(self, "timeline", None)
        canvas = getattr(timeline, "canvas", None) if timeline is not None else None
        global_canvas = getattr(timeline, "global_canvas", None) if timeline is not None else None
        row_attrs = (
            "_middle_segments",
            "middle_segments",
            "_roughcut_segments",
            "roughcut_segments",
            "_chapter_segments",
            "chapter_segments",
            "_roughcut_draft_segments",
        )
        result_attrs = ("_roughcut_result", "roughcut_result", "_roughcut_draft_result")
        for obj in (self, main_w, timeline, canvas, global_canvas):
            if obj is None:
                continue
            for attr in ("_preliminary_middle_segments", "preliminary_middle_segments"):
                try:
                    setattr(obj, attr, list(preliminary_rows))
                except Exception:
                    pass
            for attr in row_attrs:
                try:
                    setattr(obj, attr, list(rows))
                except Exception:
                    pass
            for attr in result_attrs:
                try:
                    setattr(obj, attr, result)
                except Exception:
                    pass
            try:
                invalidator = getattr(obj, "_invalidate_marker_caches", None)
                if callable(invalidator):
                    invalidator()
                static_invalidator = getattr(obj, "_invalidate_static_cache", None)
                if callable(static_invalidator):
                    static_invalidator()
                if hasattr(obj, "_roughcut_major_cache_key"):
                    obj._roughcut_major_cache_key = None
                    obj._roughcut_major_cache = []
                if hasattr(obj, "_analysis_markers_cache_key"):
                    obj._analysis_markers_cache_key = None
                if hasattr(obj, "_visible_analysis_markers_cache_key"):
                    obj._visible_analysis_markers_cache_key = None
                if hasattr(obj, "_paint_index_cache"):
                    obj._paint_index_cache.pop("roughcut_major_markers", None)
                if hasattr(obj, "_render_epoch"):
                    obj._render_epoch = int(getattr(obj, "_render_epoch", 0) or 0) + 1
            except Exception:
                pass
            try:
                obj.update()
            except Exception:
                pass

    def _post_generation_local_llm_release_requested(self, settings: dict, segments: list[dict]) -> bool:
        if not bool(getattr(self, "_post_generation_models_release_requested", False)) and not bool(
            getattr(self, "_post_generation_models_released", False)
        ):
            try:
                main_w = self.window()
                if not bool(getattr(main_w, "_editor_ai_runtime_release_requested_for_editor_mode", False)):
                    return False
            except Exception:
                return False
        try:
            from core.llm.openai_provider import is_openai_model
            from core.roughcut.roughcut_llm_config import resolve_roughcut_llm_config

            llm_config = resolve_roughcut_llm_config(settings, subtitle_rows=list(segments or []))
            provider = str(llm_config.provider or "").strip().lower()
            model = str(llm_config.model or "").strip()
            if not llm_config.enabled or not model or "사용 안함" in model or provider == "none":
                return False
            if provider in {"openai", "google", "gemini"} or is_openai_model(model) or "gemini" in model.lower():
                return False
            return True
        except Exception:
            provider = str(settings.get("selected_llm_provider") or settings.get("roughcut_llm_provider") or "ollama")
            return provider.strip().lower() not in {"openai", "google", "gemini", "none"}

    def _schedule_post_roughcut_model_release(self):
        if bool(getattr(self, "_post_generation_models_release_requested", False)) or bool(
            getattr(self, "_post_generation_models_released", False)
        ):
            return
        release = getattr(self, "_release_ai_models_after_roughcut_draft", None)
        if callable(release):
            try:
                QTimer.singleShot(0, release)
                return
            except RuntimeError:
                return
            except Exception:
                pass
        try:
            main_w = self.window()
        except RuntimeError:
            return
        except Exception:
            return
        release = getattr(main_w, "_release_ai_models_for_editor_mode", None)
        if callable(release):
            try:
                QTimer.singleShot(0, lambda: release(force=True, preserve_roughcut_status=True))
            except RuntimeError:
                return
            except Exception:
                pass

    def _draft_settings_snapshot(self) -> dict:
        settings = dict(getattr(self, "settings", {}) or {})
        try:
            from core.settings import load_settings

            settings.update(load_settings())
        except Exception:
            pass
        return settings

    def _roughcut_draft_runtime_enabled(self) -> bool:
        try:
            from core.roughcut import editor_roughcut_draft_enabled

            return editor_roughcut_draft_enabled(self._draft_settings_snapshot())
        except Exception:
            return False

    def _roughcut_draft_post_generation_autorun_enabled(self) -> bool:
        settings = self._draft_settings_snapshot()
        try:
            from core.roughcut.editor_draft import editor_roughcut_draft_autorun_enabled

            return bool(editor_roughcut_draft_autorun_enabled(settings))
        except Exception:
            value = settings.get("roughcut_run_after_subtitle_generation", None)
            if isinstance(value, str):
                enabled = value.strip().lower() not in {"0", "false", "off", "no", "사용 안함", "끔"}
            elif value is None:
                enabled = None
            else:
                enabled = bool(value)
            llm_enabled = bool(settings.get("roughcut_llm_enabled", False))
            if not llm_enabled:
                return False
            if enabled is True:
                return True
            if self._roughcut_draft_runtime_enabled():
                return True
            return bool(enabled)

    def _roughcut_playback_active(self) -> bool:
        try:
            player = getattr(getattr(self, "video_player", None), "media_player", None)
            return bool(player and player.playbackState() == player.PlaybackState.PlayingState)
        except Exception:
            return False

    def _set_roughcut_draft_status(self, status: str, count: int | None = None):
        self._roughcut_draft_status = str(status or "idle")
        if count is not None:
            self._last_roughcut_draft_major_count = int(count)
        if threading.current_thread() is not threading.main_thread():
            return
        try:
            main_w = self.window()
            if hasattr(main_w, "_refresh_saved_status_label"):
                main_w._refresh_saved_status_label()
        except Exception:
            pass

    def _roughcut_queue_row(self) -> int | None:
        try:
            main_w = self.window()
        except Exception:
            return None
        if main_w is None:
            return None
        current_row_hint = None
        current_row_getter = getattr(main_w, "queue_active_row_index", None)
        if callable(current_row_getter):
            try:
                current_row_hint = int(current_row_getter())
            except Exception:
                current_row_hint = None
        return find_queue_row_for_media(
            main_w,
            media_path=getattr(self, "media_path", ""),
            current_row_hint=current_row_hint,
        )

    def _ensure_roughcut_queue_row(self) -> int | None:
        row = self._roughcut_queue_row()
        if row is not None:
            return row
        try:
            main_w = self.window()
        except Exception:
            return None
        if main_w is None:
            return None
        media_path = str(getattr(self, "media_path", "") or "")
        if not media_path:
            return None
        row_count_getter = getattr(main_w, "queue_row_count", None)
        row_count = 0
        if callable(row_count_getter):
            try:
                row_count = max(0, int(row_count_getter() or 0))
            except Exception:
                row_count = 0
        if row_count > 0:
            return None
        initializer = getattr(main_w, "init_queue_list", None)
        if not callable(initializer):
            return None
        try:
            initializer([media_path])
        except Exception:
            return None
        return self._roughcut_queue_row()

    def _roughcut_queue_expected_text(
        self,
        row: int | None = None,
        *,
        fallback_seconds: float | None = None,
    ) -> str:
        if row is None:
            row = self._ensure_roughcut_queue_row()
        if row is None:
            if fallback_seconds and fallback_seconds > 0.0:
                return str(max(1, int(round(float(fallback_seconds)))))
            return ""
        try:
            main_w = self.window()
        except Exception:
            main_w = None
        expected_getter = getattr(main_w, "queue_row_expected_seconds", None) if main_w is not None else None
        expected_seconds = 0.0
        if callable(expected_getter):
            try:
                expected_seconds = float(expected_getter(int(row)) or 0.0)
            except Exception:
                expected_seconds = 0.0
        if expected_seconds <= 0.0:
            if fallback_seconds and fallback_seconds > 0.0:
                return str(max(1, int(round(float(fallback_seconds)))))
            return ""
        metrics_getter = getattr(main_w, "queue_row_metrics", None) if main_w is not None else None
        if not callable(metrics_getter):
            return str(max(1, int(round(expected_seconds))))
        try:
            metrics = dict(metrics_getter(int(row)) or {})
        except Exception:
            return str(max(1, int(round(expected_seconds))))
        return str(metrics.get("expected_label", "") or "")

    def _mark_roughcut_queue_active(self, status_text: str, *, expected_seconds: float | None = None) -> None:
        row = self._ensure_roughcut_queue_row()
        if row is None:
            return
        try:
            main_w = self.window()
        except Exception:
            return
        dispatch_queue_status(
            main_w,
            row,
            status_text,
            self._roughcut_queue_expected_text(row, fallback_seconds=expected_seconds),
        )

    def _mark_roughcut_queue_done(self, *, note: str = "") -> None:
        row = self._ensure_roughcut_queue_row()
        if row is None:
            return
        try:
            main_w = self.window()
        except Exception:
            return
        if note:
            dispatch_queue_status(
                main_w,
                row,
                f"✅ 완료 · {note}",
                self._roughcut_queue_expected_text(row),
            )
            return
        sync_saved_queue_state(
            main_w,
            media_path=getattr(self, "media_path", ""),
            current_row_hint=row,
        )

    def _schedule_post_generation_roughcut_draft(self, force: bool = False):
        if force and not self._roughcut_draft_post_generation_autorun_enabled():
            self._roughcut_draft_pending = False
            self._set_roughcut_draft_status("disabled")
            get_logger().log("⏭️ 러프컷 자동 실행 생략: 생성 완료 후 자동 실행 설정이 꺼져 있습니다.")
            return
        if not self._roughcut_draft_runtime_enabled():
            self._roughcut_draft_pending = False
            self._set_roughcut_draft_status("disabled")
            get_logger().log("⏭️ 러프컷 자동 실행 생략: 컷 경계/러프컷 런타임이 비활성화되어 있습니다.")
            return
        timer = getattr(self, "_roughcut_draft_timer", None)
        if timer is None:
            self._roughcut_draft_pending = False
            return
        if force or not timer.isActive():
            self._roughcut_draft_pending = True
            self._set_roughcut_draft_status("queued")
            self._mark_roughcut_queue_active("⏳ [러프컷 LLM] 후처리 대기")
            get_logger().log("⏳ 러프컷 LLM 후처리 예약: 자막 생성 완료 직후 중분류 초안을 이어서 만듭니다.")
            timer.start(120 if force else 300)

    def _run_post_generation_roughcut_draft(self):
        if not self._roughcut_draft_runtime_enabled():
            self._roughcut_draft_pending = False
            self._set_roughcut_draft_status("disabled")
            return
        if not self._cut_boundary_runtime_settled_for_roughcut():
            timer = getattr(self, "_roughcut_draft_timer", None)
            if timer is not None:
                self._roughcut_draft_pending = True
                self._set_roughcut_draft_status("queued")
                timer.start(900)
            return
        if self._roughcut_playback_active():
            timer = getattr(self, "_roughcut_draft_timer", None)
            if timer is not None:
                self._roughcut_draft_pending = True
                self._set_roughcut_draft_status("queued")
                timer.start(2200)
            return
        thread = getattr(self, "_roughcut_draft_thread", None)
        if thread is not None and thread.is_alive():
            return

        segments = [
            dict(seg)
            for seg in self._get_current_segments()
            if not seg.get("is_gap") and str(seg.get("text", "") or "").strip()
        ]
        if not segments:
            self._roughcut_draft_pending = False
            self._set_roughcut_draft_status("idle")
            self._mark_roughcut_queue_done()
            return
        self._roughcut_draft_pending = True
        self._set_roughcut_draft_status("running")

        settings = self._draft_settings_snapshot()
        try:
            min_count = max(1, int(settings.get("roughcut_major_min_subtitle_count", 5) or 5))
        except Exception:
            min_count = 5
        main_w = self.window()
        media_path = str(getattr(self, "media_path", "") or "")
        media_files = list(getattr(main_w, "_multiclip_files", []) or [])
        if not media_files and media_path:
            media_files = [media_path]
        clip_boundaries = list(getattr(main_w, "_multiclip_boundaries", []) or [])
        confirmed_cut_boundaries = list(getattr(main_w, "_project_boundary_times", []) or [])
        provisional_cut_boundaries = list(getattr(self, "_auto_cut_boundary_scan_lines", []) or [])
        editor_mode = "multiclip" if len(media_files) > 1 else "single"
        media_duration = max((float(seg.get("end", 0.0) or 0.0) for seg in segments), default=0.0)
        try:
            media_duration = max(media_duration, float(getattr(getattr(self, "video_player", None), "total_time", 0.0) or 0.0))
        except Exception:
            pass
        source_media = f"멀티클립 {len(media_files)}개" if len(media_files) > 1 else os.path.basename(media_path or "")
        reference_major_segments = self._draft_reference_major_segments()
        reviewed_cut_boundaries = self._draft_reviewed_cut_boundaries()
        self._roughcut_draft_generation += 1
        generation = int(self._roughcut_draft_generation)

        try:
            from core.roughcut.editor_draft import (
                describe_editor_roughcut_llm_scope,
                estimate_editor_roughcut_llm_runtime_sec,
            )

            roughcut_scope = describe_editor_roughcut_llm_scope(
                segments,
                settings,
                cut_boundaries=confirmed_cut_boundaries,
                provisional_cut_boundaries=provisional_cut_boundaries,
            )
            roughcut_chunk_count = max(1, int(roughcut_scope.get("chunk_count", 1) or 1))
            roughcut_eta_sec = float(estimate_editor_roughcut_llm_runtime_sec(media_duration, settings) or 0.0)
        except Exception:
            roughcut_chunk_count = 1
            roughcut_eta_sec = 0.0
        eta_label = f" · 예상 {roughcut_eta_sec:.0f}s" if roughcut_eta_sec > 0.0 else ""
        self._mark_roughcut_queue_active(
            f"🤖 [러프컷 LLM] 후처리 중 · {roughcut_chunk_count}chunk{eta_label}",
            expected_seconds=roughcut_eta_sec if roughcut_eta_sec > 0.0 else None,
        )
        get_logger().log(
            "🤖 러프컷 LLM 후처리 시작: "
            f"자막 row {len(segments)}개 · chunk {roughcut_chunk_count}개{eta_label}"
        )

        def emit_candidate(llm_payload, refinement_source: str):
            from core.roughcut import build_editor_roughcut_candidate_payload, build_editor_roughcut_draft_result

            result = build_editor_roughcut_draft_result(
                segments,
                media_duration=media_duration,
                source_path=media_path,
                settings=settings,
                llm_payload=llm_payload,
                reference_major_segments=reference_major_segments,
            )
            payload = build_editor_roughcut_candidate_payload(
                result,
                source_segments=segments,
                settings=settings,
                source_path=media_path,
                source_media=source_media,
                media_files=media_files,
                clip_boundaries=clip_boundaries,
                editor_mode=editor_mode,
            )
            payload["_generation"] = generation
            payload["refinement_source"] = refinement_source
            self.sig_roughcut_draft_ready.emit(result, segments, payload)

        try:
            from core.roughcut import resolve_roughcut_llm_config

            llm_config = resolve_roughcut_llm_config(settings, subtitle_rows=list(segments or []))
            roughcut_provider = str(getattr(llm_config, "provider", "") or "").strip().lower()
            roughcut_model = str(getattr(llm_config, "model", "") or "").strip()
            roughcut_llm_ready = (
                bool(getattr(llm_config, "enabled", False))
                and roughcut_provider != "none"
                and roughcut_model
                and "사용 안함" not in roughcut_model
            )
        except Exception:
            roughcut_model = str(settings.get("selected_model", "") or "").strip()
            roughcut_llm_ready = bool(roughcut_model and "사용 안함" not in roughcut_model)
        if len(segments) < min_count or not roughcut_llm_ready:
            try:
                emit_candidate(None, "local_after_generation")
            except Exception as exc:
                self._set_roughcut_draft_status("failed")
                get_logger().log(f"⚠️ 에디터 러프컷 로컬 초안 생성 실패: {exc}")
            return
        if self._post_generation_local_llm_release_requested(settings, segments):
            try:
                self._roughcut_llm_cooldown_until = time.time() + 10.0
                get_logger().log("⏩ 러프컷 LLM: 에디터 모드 모델 정리 요청 상태라 로컬 규칙 초안으로 즉시 대체합니다.")
                emit_candidate(None, "local_after_generation_runtime_released")
            except Exception as exc:
                self._set_roughcut_draft_status("failed")
                get_logger().log(f"⚠️ 에디터 러프컷 로컬 초안 생성 실패: {exc}")
            return
        try:
            from core.roughcut import (
                describe_editor_roughcut_llm_scope,
                editor_roughcut_draft_llm_allowed,
                resolve_roughcut_context_policy,
            )

            scope = describe_editor_roughcut_llm_scope(
                segments,
                settings,
                cut_boundaries=confirmed_cut_boundaries,
                provisional_cut_boundaries=provisional_cut_boundaries,
            )
            if str(scope.get("mode") or "") == "chunked":
                get_logger().log(
                    "✂️ 긴 영상 러프컷: 자막 row "
                    f"{len(segments)}개를 컷 경계 기반 {int(scope.get('chunk_count', 0) or 0)}개 chunk로 나눠 "
                    f"LLM 초안을 순차 생성합니다."
                )

            if not editor_roughcut_draft_llm_allowed(
                segments,
                settings,
                cut_boundaries=confirmed_cut_boundaries,
                provisional_cut_boundaries=provisional_cut_boundaries,
            ):
                policy = resolve_roughcut_context_policy(settings, subtitle_rows=list(segments or []))
                max_rows = int(policy.get("max_context_rows", settings.get("roughcut_llm_max_context_rows", 80)) or 80)
                get_logger().log(
                    "⏩ 긴 영상 러프컷: 자막 row가 "
                    f"{len(segments)}개라 자동 문맥 정책({max_rows}개 제한)으로 LLM 초안을 건너뛰고 로컬 세그먼트를 즉시 생성합니다."
                )
                emit_candidate(None, "local_after_generation_long_video")
                return
        except Exception as exc:
            get_logger().log(f"⚠️ 러프컷 LLM 길이 판단 실패, 로컬 초안으로 진행: {exc}")
            emit_candidate(None, "local_after_generation_length_guard")
            return
        if time.time() < float(getattr(self, "_roughcut_llm_cooldown_until", 0.0) or 0.0):
            try:
                emit_candidate(None, "local_after_generation")
            except Exception as exc:
                self._set_roughcut_draft_status("failed")
                get_logger().log(f"⚠️ 에디터 러프컷 로컬 초안 생성 실패: {exc}")
            return

        def worker():
            try:
                from core.roughcut import run_editor_roughcut_llm_draft

                llm_payload = run_editor_roughcut_llm_draft(
                    segments,
                    settings=settings,
                    cut_boundaries=confirmed_cut_boundaries,
                    provisional_cut_boundaries=provisional_cut_boundaries,
                    reference_major_segments=reference_major_segments,
                    reviewed_cut_boundaries=reviewed_cut_boundaries,
                )
                if llm_payload is None:
                    self._roughcut_llm_cooldown_until = time.time() + 10.0
                    get_logger().log("↩️ 러프컷 LLM 후처리 결과 없음: 로컬 규칙 초안으로 마무리합니다.")
                    emit_candidate(None, "local_after_generation_fallback")
                else:
                    self._roughcut_llm_cooldown_until = 0.0
                    get_logger().log("✅ 러프컷 LLM 응답 수신: 초안 저장 단계로 넘깁니다.")
                    emit_candidate(llm_payload, "llm_refined")
            except Exception as exc:
                self.sig_roughcut_draft_ready.emit(None, [], {"_generation": generation, "refinement_source": "failed"})
                try:
                    get_logger().log(f"⚠️ 에디터 러프컷 초안 생성 실패: {exc}")
                except Exception:
                    pass

        self._roughcut_draft_pending = False
        self._roughcut_draft_thread = threading.Thread(target=worker, daemon=True, name="editor-post-generation-roughcut-draft")
        self._roughcut_draft_thread.start()

    def _apply_post_generation_roughcut_draft(self, result, segments: list, candidate: dict):
        refinement_source = str(candidate.get("refinement_source") or "")
        try:
            if int(candidate.get("_generation", -1)) != int(getattr(self, "_roughcut_draft_generation", 0)):
                return
        except Exception:
            pass
        if refinement_source == "failed":
            self._set_roughcut_draft_status("failed")
            self._roughcut_draft_pending = False
            self._roughcut_draft_thread = None
            self._mark_roughcut_queue_done(note="러프컷 미적용")
            self._schedule_post_roughcut_model_release()
            return
        self._set_roughcut_draft_status("saving")
        self._mark_roughcut_queue_active("💾 [러프컷 LLM] 저장 중")
        try:
            major_count = len(getattr(result, "segments", ()) or ())
            max_major = int(self._draft_settings_snapshot().get("editor_roughcut_draft_max_major_segments", 10) or 10)
            if major_count > max(1, min(26, max_major)):
                from core.roughcut import build_editor_roughcut_candidate_payload, build_editor_roughcut_draft_result

                settings = self._draft_settings_snapshot()
                media_path = str(getattr(self, "media_path", "") or "")
                main_w = self.window()
                media_files = list(getattr(main_w, "_multiclip_files", []) or [])
                if not media_files and media_path:
                    media_files = [media_path]
                result = build_editor_roughcut_draft_result(
                    segments,
                    media_duration=max((float(seg.get("end", 0.0) or 0.0) for seg in segments), default=0.0),
                    source_path=media_path,
                    settings=settings,
                    llm_payload=None,
                    reference_major_segments=self._draft_reference_major_segments(),
                )
                candidate = build_editor_roughcut_candidate_payload(
                    result,
                    source_segments=segments,
                    settings=settings,
                    source_path=media_path,
                    source_media=os.path.basename(media_path or "") or "현재 에디터",
                    media_files=media_files,
                    clip_boundaries=list(getattr(main_w, "_multiclip_boundaries", []) or []),
                    editor_mode="multiclip" if len(media_files) > 1 else "single",
                )
                candidate["refinement_source"] = refinement_source or "local_capped"
        except Exception:
            pass
        main_w = self.window()
        project_path = str(getattr(main_w, "_current_project_path", "") or "")
        if not project_path:
            try:
                from core.path_manager import get_srt_path
                from core.project.project_manager import create_project

                media_path = str(getattr(self, "media_path", "") or "")
                if media_path:
                    project_path = create_project(
                        name=os.path.splitext(os.path.basename(media_path))[0],
                        media_paths=[media_path],
                        srt_path=get_srt_path(media_path),
                        user_settings=dict(getattr(self, "settings", {}) or {}),
                    )
                    attach_project_session(
                        main_w,
                        project_path,
                        None,
                        auto_pipeline=False,
                        clear_multiclip=False,
                        emit_boundary_signal=False,
                    )
            except Exception as exc:
                get_logger().log(f"⚠️ 러프컷 초안 프로젝트 생성 실패: {exc}")
        if not project_path:
            self._set_roughcut_draft_status("failed")
            self._mark_roughcut_queue_done(note="러프컷 미적용")
            self._schedule_post_roughcut_model_release()
            return
        try:
            from core.project.project_manager import save_project
            from core.project.project_io import read_project_file
            from core.roughcut import EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID, merge_editor_roughcut_draft_state
            from core.work_mode import EDITOR_MODE

            existing_state = {}
            if os.path.exists(project_path):
                try:
                    existing_state = read_project_file(project_path).get("roughcut_state", {}) or {}
                except Exception:
                    existing_state = {}
            candidate.pop("_generation", None)
            roughcut_state = merge_editor_roughcut_draft_state(existing_state, candidate)
            save_project(
                project_path,
                segments=segments,
                middle_segments=list(candidate.get("segments", []) or []),
                roughcut_result=candidate,
                preliminary_middle_segments=(
                    list(candidate.get("segments", []) or [])
                    if refinement_source == "llm_refined"
                    else []
                ),
                user_settings=dict(getattr(self, "settings", {}) or {}),
                roughcut_state=roughcut_state,
                active_work_mode=EDITOR_MODE,
                persist_analysis_artifacts=False,
            )
            self._pending_preliminary_middle_segments = (
                list(candidate.get("segments", []) or [])
                if refinement_source == "llm_refined"
                else []
            )
            self._apply_roughcut_middle_segments_to_ui(list(candidate.get("segments", []) or []), result)
            setattr(main_w, "_editor_roughcut_result", result)
            roughcut = getattr(main_w, "_roughcut_widget", None)
            if roughcut is not None:
                try:
                    roughcut._result = result
                    roughcut._source_signature = str(candidate.get("source_signature") or "")
                    roughcut._selected_candidate_id = EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID
                    roughcut._roughcut_candidates = list(roughcut_state.get("candidates", []) or [])
                    if hasattr(roughcut, "_refresh_candidate_combo"):
                        roughcut._refresh_candidate_combo()
                    if hasattr(roughcut, "_populate_result"):
                        roughcut._populate_result()
                except RuntimeError:
                    pass
                except Exception:
                    pass
            self._redraw_timeline()
            count = len(getattr(result, "segments", ()) or ())
            last_count = getattr(self, "_last_roughcut_draft_major_count", None)
            if last_count != count:
                self._last_roughcut_draft_major_count = count
                source_label = "LLM" if refinement_source == "llm_refined" else "로컬"
                get_logger().log(f"✅ 러프컷 후처리 완료: {source_label} 초안 · 중분류 {count}개")
            self._set_roughcut_draft_status("done", count)
            self._mark_roughcut_queue_done()
        except Exception as exc:
            self._set_roughcut_draft_status("failed")
            self._mark_roughcut_queue_done(note="러프컷 미적용")
            get_logger().log(f"⚠️ 러프컷 초안 저장 실패: {exc}")
        finally:
            self._roughcut_draft_pending = False
            try:
                self._pending_preliminary_middle_segments = []
            except Exception:
                pass
            self._schedule_post_roughcut_model_release()
            if refinement_source in {"llm_refined", "local_after_generation_fallback"}:
                self._roughcut_draft_thread = None
