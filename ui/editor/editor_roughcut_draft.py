# Version: 03.13.05
# Phase: PHASE2
"""Post-generation roughcut draft helpers for the subtitle editor."""

from __future__ import annotations

import os
import threading
import time

from PyQt6.QtCore import QTimer

from core.runtime.logger import get_logger


class EditorRoughcutDraftMixin:
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

    def _schedule_post_generation_roughcut_draft(self, force: bool = False):
        if not self._roughcut_draft_runtime_enabled():
            self._set_roughcut_draft_status("disabled")
            return
        timer = getattr(self, "_roughcut_draft_timer", None)
        if timer is None:
            return
        if force or not timer.isActive():
            self._set_roughcut_draft_status("queued")
            timer.start(120 if force else 300)

    def _run_post_generation_roughcut_draft(self):
        if not self._roughcut_draft_runtime_enabled():
            self._set_roughcut_draft_status("disabled")
            return
        if self._roughcut_playback_active():
            timer = getattr(self, "_roughcut_draft_timer", None)
            if timer is not None:
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
            self._set_roughcut_draft_status("idle")
            return
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
        self._roughcut_draft_generation += 1
        generation = int(self._roughcut_draft_generation)

        def emit_candidate(llm_payload, refinement_source: str):
            from core.roughcut import build_editor_roughcut_candidate_payload, build_editor_roughcut_draft_result

            result = build_editor_roughcut_draft_result(
                segments,
                media_duration=media_duration,
                source_path=media_path,
                settings=settings,
                llm_payload=llm_payload,
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

        model = str(settings.get("selected_model", "") or "").strip()
        if len(segments) < min_count or not model or "사용 안함" in model:
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
                )
                if llm_payload is None:
                    self._roughcut_llm_cooldown_until = time.time() + 10.0
                    emit_candidate(None, "local_after_generation_fallback")
                else:
                    self._roughcut_llm_cooldown_until = 0.0
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
            self._roughcut_draft_thread = None
            self._schedule_post_roughcut_model_release()
            return
        self._set_roughcut_draft_status("saving")
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
                    main_w._current_project_path = project_path
            except Exception as exc:
                get_logger().log(f"⚠️ 러프컷 초안 프로젝트 생성 실패: {exc}")
        if not project_path:
            self._set_roughcut_draft_status("failed")
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
                user_settings=dict(getattr(self, "settings", {}) or {}),
                roughcut_state=roughcut_state,
                active_work_mode=EDITOR_MODE,
                persist_analysis_artifacts=False,
            )
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
                get_logger().log(f"자막 생성 후 러프컷 초안 생성: 중분류 {count}개")
            self._set_roughcut_draft_status("done", count)
        except Exception as exc:
            self._set_roughcut_draft_status("failed")
            get_logger().log(f"⚠️ 러프컷 초안 저장 실패: {exc}")
        finally:
            self._schedule_post_roughcut_model_release()
            if refinement_source in {"llm_refined", "local_after_generation_fallback"}:
                self._roughcut_draft_thread = None
