# Version: 03.14.34
# Phase: PHASE2
"""
core/pipeline/single_pipeline.py
SinglePipelineMixin — 단일 파일 / 배치 파이프라인 (_run_all, _process_one)
"""
import os
import threading
import traceback
import queue
import time

from core.autopilot_policy import speaker_preflight_decision
from core.runtime import config
from core.runtime.logger import get_logger
from core.settings import load_settings, get_model_key
from core.time_history import get_expected_time, add_history
from core.personalization.subtitle_bundle_policy import resolve_subtitle_bundle_policy
from core.pipeline.subtitle_buffer_policy import (
    should_flush_final_subtitle_buffer as _should_flush_final_subtitle_buffer,
    should_flush_live_subtitle_buffer as _should_flush_live_subtitle_buffer,
)
from core.pipeline.startup_diagnostics import (
    attach_expected_processing_time,
    build_startup_diagnostic,
    format_startup_diagnostic_log,
    persist_startup_diagnostic,
)
from core.pipeline.subtitle_memory_guard import (
    create_subtitle_generation_memory_guard,
    subtitle_generation_memory_checkpoint,
)

_SENTINEL = object()


def _is_deleted_qt_error(exc: BaseException) -> bool:
    return "wrapped C/C++ object" in str(exc) and "has been deleted" in str(exc)


class SinglePipelineMixin:
    """단일 / 배치 품질모드 파이프라인."""

    def _emit_processing_stage(self, queue_index: int, status: str) -> None:
        text = str(status or "")
        self._ui_emit("_sig_update_queue", queue_index, text, "", "", "")
        self._ui_emit("_sig_editor_processing_stage", text)

    def _create_subtitle_generation_memory_guard(self, target_file, queue_index: int):
        return create_subtitle_generation_memory_guard(self, target_file, queue_index)

    def _subtitle_generation_memory_checkpoint(
        self,
        guard,
        stage: str,
        *,
        include_gpu: bool = False,
        cleanup: bool = False,
        force: bool = False,
    ) -> dict:
        return subtitle_generation_memory_checkpoint(
            guard,
            stage,
            include_gpu=include_gpu,
            cleanup=cleanup,
            force=force,
        )

    def _append_live_segments_to_editor(self, segments: list[dict]) -> None:
        segments = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
        if not segments:
            return
        if (
            getattr(self, "_individual_queue_mode", False)
            and callable(self._ui_attr("append_segments_to_editor_and_wait"))
        ):
            for seg in segments:
                if not self._active or not self._ui_is_alive():
                    return
                self._ui_call("append_segments_to_editor_and_wait", [seg], timeout_sec=2.0)
                time.sleep(0.04)
            return
        self._ui_emit("_sig_append_segments", segments)

    def _ui_is_alive(self) -> bool:
        try:
            ui = getattr(self, "ui", None)
            if ui is None:
                return False
            try:
                from PyQt6 import sip
                if sip.isdeleted(ui):
                    return False
            except Exception:
                pass
            return True
        except RuntimeError:
            return False

    def _ui_attr(self, name: str, default=None):
        if not self._ui_is_alive():
            self._active = False
            return default
        try:
            return getattr(self.ui, name, default)
        except RuntimeError:
            self._active = False
            return default

    def _ui_object(self):
        if not self._ui_is_alive():
            self._active = False
            return None
        try:
            return self.ui
        except RuntimeError:
            self._active = False
            return None

    def _ui_emit(self, signal_name: str, *args) -> bool:
        signal = self._ui_attr(signal_name)
        if signal is None:
            return False
        try:
            signal.emit(*args)
            return True
        except RuntimeError:
            self._active = False
            return False

    def _ui_call(self, method_name: str, *args, **kwargs):
        method = self._ui_attr(method_name)
        if not callable(method):
            return False
        try:
            method(*args, **kwargs)
            return True
        except RuntimeError:
            self._active = False
            return False

    def _run_all(self):
        total_files = len(self.files_to_process)

        try:
            for i, target_file in enumerate(self.files_to_process):
                if not self._active:
                    return

                self._ui_emit("_sig_update_queue", i, "⏳ 오디오 추출 중", "", "", "")
                self._ui_emit("_sig_update_queue_header", i + 1, total_files, 0, "")

                self._process_one(target_file, i)

            self._ui_emit("_sig_update_queue_header", total_files, total_files, 100, "")

            if bool(self._ui_attr("_is_auto_pipeline", False)):
                self._send_ntfy_notification(
                    title=f"🏆 {config.APP_NAME} 작업 종료",
                    message=f"🎉 {total_files}개 파일 처리 완료!\n아이패드에서 확인해 보세요, 대표님.",
                    tags="checkered_flag,tada",
                )

        except Exception as e:
            if _is_deleted_qt_error(e):
                self._active = False
            elif str(e) not in ("USER_PREV", "USER_EXIT"):
                get_logger().log(f"\n❌ 치명적 에러: {e}")
                get_logger().log(traceback.format_exc())

        finally:
            self._active = False
            try:
                from core.settings import clear_runtime_settings_override

                clear_runtime_settings_override()
                ui = self._ui_object()
                if ui is not None and hasattr(ui, "_clear_runtime_quality_override"):
                    ui._clear_runtime_quality_override()
            except Exception:
                pass
            try:
                ui = self._ui_object()
                if ui is not None and hasattr(ui, "_auto_processing_active"):
                    ui._auto_processing_active = False
                self._ui_call("_tick_home_watchdog_labels")
            except Exception:
                pass

    def _process_one(self, target_file, queue_index):
        memory_guard = self._create_subtitle_generation_memory_guard(target_file, queue_index)
        if getattr(self, "_individual_queue_mode", False):
            self._reset_backend_individual_clip_context(invalidate_prefetch=True)
            self._reset_ui_individual_clip_context(clear_project=True)
        try:
            self._last_generation_final_media_path = str(target_file or "")
            self._last_generation_final_segments = []
        except Exception:
            pass

        # ── STEP 0: 백업 ──
        self._backup_existing(target_file)
        self._subtitle_generation_memory_checkpoint(memory_guard, "backup_done", force=True)

        # ── 이벤트/콜백 ──
        edit_event = threading.Event()
        start_event = threading.Event()
        self._edit_event = edit_event
        self._start_event = start_event
        final_segments = []
        action_state = ["wait"]
        self._action_state = action_state

        def on_save(segs):
            nonlocal final_segments
            final_segments = segs
            action_state[0] = "next"
            start_event.set()
            edit_event.set()

        def on_start():
            if getattr(self, "is_first_start", True):
                self.pipeline_start_time = time.time()
                self.is_first_start = False
            action_state[0] = "start"
            start_event.set()

        def on_prev():
            action_state[0] = "prev"
            start_event.set()
            edit_event.set()

        def on_exit(segs):
            nonlocal final_segments
            final_segments = segs
            action_state[0] = "exit"
            self.stop()
            start_event.set()
            edit_event.set()

        # 변경: 첫 파일은 수동, 이후 파일은 자동 진행
        is_auto_mode = getattr(self, "is_auto_start", False) or (
            queue_index > 0 and len(self.files_to_process) > 1
        )

        open_editor_method = (
            "open_editor_for_file_and_wait"
            if callable(self._ui_attr("open_editor_for_file_and_wait"))
            else "open_editor_for_file"
        )
        if not self._ui_call(
            open_editor_method,
            target_file, on_save, on_start, on_prev, on_exit, is_batch=is_auto_mode
        ):
            raise Exception("USER_EXIT")

        if is_auto_mode and not getattr(self, "_individual_queue_mode", False):
            threading.Timer(0.05, on_start).start()

        start_event.wait()
        if action_state[0] == "prev":
            self._ui_call("request_show_home")
            raise Exception("USER_PREV")
        if action_state[0] == "exit":
            self._ui_call("request_show_home")
            raise Exception("USER_EXIT")
        if action_state[0] == "next":
            return
        if action_state[0] == "restart":
            self._handle_restart(target_file)
            action_state[0] = "start"

        if action_state[0] == "start":
            try:
                ui = self._ui_object()
                project_path = str(getattr(ui, "_current_project_path", "") or "") if ui is not None else ""
                media_files = list(getattr(ui, "_multiclip_files", []) or []) if ui is not None else []
                if not media_files:
                    media_files = [target_file]
                if not project_path and ui is not None and media_files:
                    from core.project.project_manager import create_project
                    from core.path_manager import get_srt_path

                    base_name = os.path.splitext(os.path.basename(media_files[0]))[0]
                    editor = getattr(ui, "_editor_widget", None)
                    editor_settings = dict(getattr(editor, "settings", {}) or {})
                    project_path = create_project(
                        name=base_name,
                        media_paths=media_files,
                        srt_path=get_srt_path(media_files[0]),
                        user_settings=editor_settings,
                    )
                    ui._current_project_path = project_path
                get_logger().log("  🎬 [컷 경계] 시작 전 분석 단계 확인 중...")
                self._subtitle_generation_memory_checkpoint(memory_guard, "cut_prescan_start", force=True)
                self._auto_scan_cut_boundaries_for_start(project_path, media_files)
                self._ui_emit("_sig_refresh_cut_boundary_placeholder")
                self._subtitle_generation_memory_checkpoint(memory_guard, "cut_prescan_ready")
            except Exception as exc:
                get_logger().log(f"  ⚠️ [컷 경계] 시작 전 백그라운드 준비 실패: {exc}")

        # ── STT 파이프라인 루프 ──
        while True:
            self._active = True
            self._speaker_map = []
            edit_event.clear()
            if hasattr(self, "_apply_personalization_runtime_override_for_file"):
                self._apply_personalization_runtime_override_for_file(target_file)
            self._reload_speaker_settings()
            self._subtitle_generation_memory_checkpoint(memory_guard, "pipeline_iteration_start", force=True)
            vname = os.path.basename(target_file)
            fsize = (
                os.path.getsize(target_file) / (1024 * 1024)
                if os.path.exists(target_file)
                else 0
            )

            get_logger().log(
                f"\n{'=' * 44}\n🎬 [{queue_index + 1}/{len(self.files_to_process)}] {vname}"
                f"\n{'=' * 44}\n\n{'─' * 44}\n  📂 파일: {vname} ({fsize:.1f} MB)\n{'─' * 44}"
            )

            # 정확도 우선 파이프라인: legacy batch override가 남아있으면 제거
            if hasattr(self, 'video_processor'):
                self.video_processor.clear_fast_mode_overrides()
                if getattr(self, "_individual_queue_mode", False):
                    self.video_processor.set_auto_audio_tune_overrides(None)
            if hasattr(self, "video_processor"):
                self.video_processor.stage_callback = (
                    lambda status, qi=queue_index: self._emit_processing_stage(qi, status)
                )
            startup_diagnostic = {}
            try:
                # ✅ 순서 고정:
                # 컷 경계/주제없음 중분류가 먼저 확정된 뒤 STT1/STT2가 시작되어야 한다.
                if hasattr(self, "_wait_cut_boundary_prescan_before_stt"):
                    self._subtitle_generation_memory_checkpoint(memory_guard, "cut_prescan_wait")
                    self._wait_cut_boundary_prescan_before_stt()
                    self._subtitle_generation_memory_checkpoint(memory_guard, "cut_prescan_done", cleanup=True)

                cut_boundary_snapshot = (
                    self._cut_boundary_snapshot_for_pipeline()
                    if hasattr(self, "_cut_boundary_snapshot_for_pipeline")
                    else {"cut_boundaries": [], "provisional_cut_boundaries": []}
                )
                pipeline_cut_boundaries = [
                    dict(row) for row in list(cut_boundary_snapshot.get("cut_boundaries", []) or [])
                ]
                pipeline_provisional_cut_boundaries = [
                    dict(row) for row in list(cut_boundary_snapshot.get("provisional_cut_boundaries", []) or [])
                ]

                try:
                    diagnostic_settings = load_settings()
                    startup_diagnostic = build_startup_diagnostic(
                        target_file,
                        settings=diagnostic_settings,
                        cut_boundaries=pipeline_cut_boundaries,
                        provisional_cut_boundaries=pipeline_provisional_cut_boundaries,
                        speaker_count_hint=getattr(self, "max_speakers", None),
                    )
                    diag_duration = float(
                        ((startup_diagnostic.get("media", {}) or {}).get("duration_sec", 0.0))
                        or 0.0
                    )
                    if diag_duration > 0:
                        self._video_durations[target_file] = diag_duration
                    diag_model_key = "QUALITY:" + get_model_key(diagnostic_settings)
                    startup_diagnostic = attach_expected_processing_time(
                        startup_diagnostic,
                        get_expected_time(diag_model_key, diag_duration),
                    )
                    if not hasattr(self, "_startup_diagnostics"):
                        self._startup_diagnostics = {}
                    self._startup_diagnostics[target_file] = dict(startup_diagnostic)
                    for line in format_startup_diagnostic_log(startup_diagnostic):
                        get_logger().log(line)
                    ui_for_diag = self._ui_object()
                    project_path_for_diag = (
                        str(getattr(ui_for_diag, "_current_project_path", "") or "")
                        if ui_for_diag is not None
                        else ""
                    )
                    persist_startup_diagnostic(project_path_for_diag, startup_diagnostic)
                except Exception as exc:
                    startup_diagnostic = {}
                    get_logger().log(f"  ⚠️ [시작 진단] 자동 진단 실패: {exc}")

                # ✅ 컷 경계는 STT 입력 청크의 절대 경계다.
                # media_processor가 오디오 청크를 만들기 전에 hard cut을 주입한다.
                try:
                    if hasattr(self, "video_processor"):
                        hard_cuts = []
                        for row in pipeline_cut_boundaries:
                            try:
                                if isinstance(row, dict):
                                    sec = float(row.get("timeline_sec", row.get("time", row.get("start", 0.0))) or 0.0)
                                else:
                                    sec = float(row)
                                if sec > 0.0:
                                    hard_cuts.append(round(sec, 3))
                            except Exception:
                                continue
                        self.video_processor.hard_cut_boundaries = sorted(set(hard_cuts))
                        if hard_cuts:
                            get_logger().log(f"  ✂️ [컷 경계] STT 청크 hard cut {len(hard_cuts)}개 적용")
                except Exception as exc:
                    get_logger().log(f"  ⚠️ [컷 경계] STT 청크 hard cut 주입 실패: {exc}")

                self._subtitle_generation_memory_checkpoint(memory_guard, "audio_extract_start", force=True)
                res = self._get_audio_extract_result(target_file)
                self._subtitle_generation_memory_checkpoint(
                    memory_guard,
                    "audio_extract_done",
                    include_gpu=True,
                    cleanup=True,
                    force=True,
                )
            finally:
                if hasattr(self, "video_processor"):
                    self.video_processor.stage_callback = None

            try:
                prefetch_ahead = 0 if getattr(self, "_individual_queue_mode", False) else max(1, int(load_settings().get("prefetch_ahead", 3)))
            except Exception:
                prefetch_ahead = 0 if getattr(self, "_individual_queue_mode", False) else 3
            if prefetch_ahead > 0:
                for _pf in self.files_to_process[queue_index + 1: queue_index + 1 + prefetch_ahead]:
                    self._prefetch_audio_for_file(_pf)

            if not res:
                get_logger().log("❌ 오디오 추출 실패")
                self._ui_emit("_sig_update_queue", queue_index, "❌ 오류", "", "", "")

                if action_state[0] == "restart":
                    get_logger().log("\n🔄 재시작합니다...")
                    action_state[0] = "next"
                    continue

                return

            chunk_dir, vad_segs = res
            self._ui_emit("_sig_set_vad_segments", vad_segs)
            try:
                speaker_preflight = speaker_preflight_decision(
                    vad_segs,
                    media_duration_sec=float((startup_diagnostic.get("media", {}) or {}).get("duration_sec", 0.0) or 0.0),
                    settings=load_settings(),
                )
                self._autopilot_speaker_preflight = speaker_preflight
                get_logger().log(
                    "🗣️ [AutoPilot 화자] "
                    f"{speaker_preflight.get('lane')} · "
                    f"{speaker_preflight.get('estimated_speaker_count')}명 예상 · "
                    f"confidence {float(speaker_preflight.get('confidence', 0.0) or 0.0):.2f}"
                )
            except Exception:
                pass
            self._subtitle_generation_memory_checkpoint(memory_guard, "stt_prepare_ready", force=True)

            get_logger().log("\n  [STT] Whisper 인식 → [자막 LLM] 교정/분리 파이프라인 가동...")

            try:
                s = load_settings()
                model_key = "QUALITY:" + get_model_key(s)

                diag_duration = float(
                    ((startup_diagnostic.get("media", {}) or {}).get("duration_sec", 0.0))
                    or 0.0
                )
                if diag_duration > 0:
                    video_duration_sec = diag_duration
                elif target_file in getattr(self, "_video_durations", {}):
                    video_duration_sec = self._video_durations[target_file]
                else:
                    chunks = [f for f in os.listdir(chunk_dir) if f.endswith(".wav")]
                    video_duration_sec = len(chunks) * 30.0

                expected_time = float(startup_diagnostic.get("estimated_processing_sec", 0.0) or 0.0)
                if expected_time <= 0:
                    expected_time = get_expected_time(model_key, video_duration_sec)
                if expected_time > 0:
                    self._ui_emit(
                        "_sig_update_queue",
                        queue_index, "자막 생성 중", str(expected_time), "", "",
                    )
                else:
                    self._ui_emit(
                        "_sig_update_queue",
                        queue_index, "자막 생성 중", "예상불가", "", "",
                    )
                process_start_time = time.time()
            except Exception:
                process_start_time = time.time()
                video_duration_sec = 0.0

            opt_queue = queue.Queue()
            base_name = os.path.splitext(os.path.basename(target_file))[0]

            # Fingerprint-scoped audio paths prevent same-name media collisions.
            cleaned_wav = str(getattr(self.video_processor, "last_cleaned_wav", "") or "")
            raw_wav = str(getattr(self.video_processor, "last_raw_wav", "") or "")
            if (not cleaned_wav or not os.path.exists(cleaned_wav)) and hasattr(self.video_processor, "_audio_work_paths"):
                try:
                    audio_paths = self.video_processor._audio_work_paths(target_file)
                    cleaned_wav = str(audio_paths.get("cleaned_wav") or cleaned_wav)
                    raw_wav = str(audio_paths.get("raw_wav") or raw_wav)
                except Exception:
                    pass
            if not cleaned_wav:
                cleaned_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}_cleaned.wav")
            if not raw_wav:
                raw_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}.wav")
            if os.path.exists(cleaned_wav):
                audio_for_diarization = cleaned_wav
            elif os.path.exists(raw_wav):
                audio_for_diarization = raw_wav
            else:
                audio_for_diarization = target_file

            self._prepare_speaker_map_before_stt(
                audio_for_diarization,
                speaker_preflight=getattr(self, "_autopilot_speaker_preflight", None),
                stage_callback=lambda status, qi=queue_index: self._emit_processing_stage(qi, status),
            )

            auto_collected_segs = []
            preview_opt_queue = queue.Queue()
            preview_opt_sentinel = object()

            def _emit_processed_preview(
                chunk_segs,
                _label="STT",
                _vad_segs=vad_segs,
                _cut_boundaries=pipeline_cut_boundaries,
                _provisional_cut_boundaries=pipeline_provisional_cut_boundaries,
            ):
                from core.pipeline.stt_preview_optimizer import optimize_stt_preview_segments

                preview = optimize_stt_preview_segments(
                    chunk_segs,
                    source_label=str(_label or "STT"),
                    vad_segments=_vad_segs,
                    cut_boundaries=_cut_boundaries,
                    provisional_cut_boundaries=_provisional_cut_boundaries,
                )
                if preview and self._active:
                    self._ui_emit("_sig_preview_stt_segments", preview)

            def _preview_stt_segments(chunk_segs, _label="STT", _preview_opt_queue=preview_opt_queue):
                if not chunk_segs or not self._active:
                    return
                _preview_opt_queue.put(([dict(seg) for seg in chunk_segs or []], str(_label or "STT")))

            def do_preview_optimize(_preview_opt_queue=preview_opt_queue, _preview_opt_sentinel=preview_opt_sentinel):
                while self._active:
                    item = _preview_opt_queue.get()
                    if item is _preview_opt_sentinel:
                        break
                    try:
                        chunk_segs, label = item
                        _emit_processed_preview(chunk_segs, label)
                    except Exception as exc:
                        get_logger().log(f"  ⚠️ STT 후보 자막 후처리 오류: {exc}")

            def do_transcribe(
                _chunk_dir=chunk_dir,
                _opt_queue=opt_queue,
                _preview_opt_queue=preview_opt_queue,
                _preview_opt_sentinel=preview_opt_sentinel,
            ):
                try:
                    self._subtitle_generation_memory_checkpoint(
                        memory_guard,
                        "stt_transcribe_start",
                        force=True,
                    )
                    if hasattr(self, "video_processor"):
                        self.video_processor.stage_callback = (
                            lambda status, qi=queue_index: self._emit_processing_stage(qi, status)
                        )
                    for chunk_segs, c_idx, t_total in self.video_processor.transcribe(
                        _chunk_dir,
                        is_fast_mode=False,
                        preview_callback=_preview_stt_segments,
                    ):
                        if not self._active:
                            break
                        _opt_queue.put((chunk_segs, c_idx, t_total))
                        self._subtitle_generation_memory_checkpoint(
                            memory_guard,
                            f"stt_transcribe_chunk:{c_idx}/{t_total}",
                        )
                finally:
                    if hasattr(self, "video_processor"):
                        self.video_processor.stage_callback = None
                    self._subtitle_generation_memory_checkpoint(
                        memory_guard,
                        "stt_transcribe_done",
                        include_gpu=True,
                        cleanup=True,
                        force=True,
                    )
                    _preview_opt_queue.put(_preview_opt_sentinel)
                    _opt_queue.put(_SENTINEL)

            def _do_optimize_impl(
                _opt_queue=opt_queue,
                _vad_segs=vad_segs,
                _auto_collected_segs=auto_collected_segs,
            ):
                from core.engine.subtitle_engine import apply_final_gap_settings, optimize_segments
                from core.engine.subtitle_timing import align_stt_candidates_to_subtitle_segments

                total_files = len(self.files_to_process)

                try:
                    s = load_settings()
                    bundle_policy = resolve_subtitle_bundle_policy(
                        s,
                        media_duration_sec=video_duration_sec,
                    )
                    chunk_time_limit = int(float(bundle_policy.get("target_sec", s.get("chunk_time_limit", 180)) or 180))
                    stt_ensemble_enabled = bool(s.get("stt_ensemble_enabled", False))
                except Exception:
                    s = {}
                    bundle_policy = resolve_subtitle_bundle_policy({"chunk_time_limit": 180})
                    chunk_time_limit = 180
                    stt_ensemble_enabled = False

                seg_buffer = []
                last_c_idx = 0
                last_t_total = 1
                pending_bundle_policy = {}

                get_logger().log(
                    "  🧠 [자막 묶음] 자동 단위 "
                    f"{int(float(bundle_policy.get('target_sec', chunk_time_limit) or chunk_time_limit))}초 "
                    f"(최대 {int(float(bundle_policy.get('max_sec', 300) or 300))}초, "
                    "컷 경계 우선)"
                )

                if stt_ensemble_enabled:
                    get_logger().log(
                        "  ⏳ [STT 앙상블] STT1/STT2 후보는 즉시 표시하고 "
                        "최종 자막은 병합/LLM 분석 완료 후 반영합니다."
                    )

                def _flush_buffer():
                    nonlocal seg_buffer, pending_bundle_policy
                    if not seg_buffer:
                        return
                    chunk_segs = seg_buffer
                    active_bundle_policy = dict(pending_bundle_policy or {})
                    if not active_bundle_policy:
                        active_bundle_policy = resolve_subtitle_bundle_policy(
                            s,
                            segments=chunk_segs,
                            cut_boundaries=pipeline_cut_boundaries,
                            provisional_cut_boundaries=pipeline_provisional_cut_boundaries,
                            media_duration_sec=video_duration_sec,
                        )
                    seg_buffer = []
                    pending_bundle_policy = {}

                    try:
                        def _llm_progress(payload):
                            self._ui_emit("_sig_set_llm_review_segment", dict(payload or {}))

                        self._emit_processing_stage(queue_index, "⏳ [STT+자막 LLM] 인식 결과 교정/분리 중")
                        self._subtitle_generation_memory_checkpoint(
                            memory_guard,
                            "subtitle_optimize_start",
                            force=True,
                        )
                        opt = optimize_segments(
                            chunk_segs,
                            vad_segments=_vad_segs,
                            llm_progress_callback=_llm_progress,
                        )
                    except Exception as e:
                        get_logger().log(f"  ❌ 최적화 오류: {e}")
                        opt = chunk_segs
                    finally:
                        self._ui_emit("_sig_set_llm_review_segment", {"active": False})
                        self._subtitle_generation_memory_checkpoint(
                            memory_guard,
                            "subtitle_optimize_done",
                            include_gpu=True,
                        )

                    if not self._active or not self._ui_is_alive():
                        return

                    for seg in opt:
                        if seg["start"] < 0.0:
                            seg["start"] = 0.0
                        if seg["end"] <= seg["start"]:
                            seg["end"] = seg["start"] + 0.5

                    opt = self._magnetize_by_saved_cut_boundaries(
                        opt,
                        context="에디터 최종 자막 정식 컷",
                        include_provisional=False,
                    )
                    opt = self._split_by_saved_cut_boundaries(opt, context="에디터 최종 자막")
                    opt = self._align_subtitle_segments_to_vad(opt, _vad_segs, context="에디터")

                    opt = self._apply_speaker_map_to_segments(opt)

                    if opt:
                        opt[0]["_subtitle_bundle_policy"] = {
                            **active_bundle_policy,
                            "output_segment_count": len(opt),
                        }

                    opt = apply_final_gap_settings(opt, force=True)
                    opt = self._magnetize_by_saved_cut_boundaries(
                        opt,
                        context="에디터 최종 자막 임시 컷",
                        include_confirmed=False,
                        include_provisional=True,
                    )
                    opt = self._split_by_saved_cut_boundaries(opt, context="에디터 최종 자막")
                    opt = align_stt_candidates_to_subtitle_segments(opt)
                    _auto_collected_segs.extend([dict(seg) for seg in opt])

                    if not self._active or not self._ui_is_alive():
                        return

                    try:
                        self._append_live_segments_to_editor(opt)
                        self._ui_emit("_sig_update_status", last_c_idx, last_t_total)
                    except Exception:
                        pass

                while self._active:
                    item = _opt_queue.get()
                    if not self._ui_is_alive():
                        self._active = False
                        break
                    if item is _SENTINEL:
                        _flush_buffer()
                        break

                    chunk_segs, c_idx, t_total = item
                    last_c_idx = c_idx
                    last_t_total = t_total

                    if t_total > 0:
                        overall_pct = int(
                            ((queue_index + (c_idx / t_total)) / total_files) * 100
                        )
                    else:
                        overall_pct = int((queue_index / total_files) * 100)

                    self._ui_emit("_sig_update_status", c_idx, t_total)

                    try:
                        self._ui_emit(
                            "_sig_update_queue_header",
                            queue_index + 1, total_files, overall_pct, "",
                        )
                    except Exception:
                        pass

                    if not chunk_segs:
                        try:
                            self._ui_emit("_sig_update_status", c_idx, t_total)
                        except Exception:
                            pass
                        continue

                    seg_buffer.extend(chunk_segs)
                    buffer_start = seg_buffer[0]["start"]
                    buffer_end = seg_buffer[-1]["end"]
                    current_duration = buffer_end - buffer_start

                    flush_policy = resolve_subtitle_bundle_policy(
                        s,
                        segments=seg_buffer,
                        cut_boundaries=pipeline_cut_boundaries,
                        provisional_cut_boundaries=pipeline_provisional_cut_boundaries,
                        current_duration=current_duration,
                        media_duration_sec=video_duration_sec,
                    )
                    if _should_flush_live_subtitle_buffer(
                        current_duration,
                        chunk_time_limit,
                        stt_ensemble_enabled=stt_ensemble_enabled,
                        settings=s,
                        buffer_segments=seg_buffer,
                        cut_boundaries=pipeline_cut_boundaries,
                        provisional_cut_boundaries=pipeline_provisional_cut_boundaries,
                        media_duration_sec=video_duration_sec,
                    ):
                        pending_bundle_policy = dict(flush_policy)
                        get_logger().log(
                            "  🧠 [자막 묶음] "
                            f"{flush_policy.get('reason', 'target')} 기준으로 "
                            f"{flush_policy.get('duration_sec', round(current_duration, 1))}초 묶음 처리"
                        )
                        _flush_buffer()

                self._ui_emit("_sig_update_status", last_t_total, last_t_total)

            def do_optimize():
                try:
                    _do_optimize_impl()
                except Exception as e:
                    if _is_deleted_qt_error(e):
                        self._active = False
                        return
                    get_logger().log(
                        "  ❌ optimizer 스레드 오류: "
                        f"{e}\n{traceback.format_exc()}"
                    )

            t_trans = threading.Thread(
                target=do_transcribe, daemon=True, name="transcriber"
            )
            t_opt = threading.Thread(target=do_optimize, daemon=True, name="optimizer")
            t_preview = threading.Thread(target=do_preview_optimize, daemon=True, name="stt-preview-optimizer")
            t_preview.start()
            t_trans.start()
            t_opt.start()
            t_trans.join()
            t_preview.join()
            t_opt.join()
            try:
                self._last_generation_final_media_path = str(target_file or "")
                self._last_generation_final_segments = [
                    dict(seg) for seg in list(auto_collected_segs or []) if isinstance(seg, dict)
                ]
            except Exception:
                pass
            self._subtitle_generation_memory_checkpoint(
                memory_guard,
                "stt_optimizer_threads_done",
                include_gpu=True,
                cleanup=True,
                force=True,
            )

            # ✅ STT 완료 → 큐 즉시 업데이트
            if not self._active:
                return

            self._ui_emit("_sig_finalize_generation_complete", "stt_optimizer_threads_done")
            self._ui_emit("_sig_update_queue", queue_index, "저장 준비 중", "", "", "")

            try:
                s = load_settings()
                model_key = "QUALITY:" + get_model_key(s)
                proc_time = time.time() - process_start_time
                add_history(model_key, video_duration_sec, proc_time)
            except Exception:
                pass

            if is_auto_mode:
                from core.engine.subtitle_engine import apply_final_gap_settings
                from core.engine.subtitle_timing import align_stt_candidates_to_subtitle_segments

                nonlocal_final = apply_final_gap_settings(auto_collected_segs[:], force=True)
                nonlocal_final = self._magnetize_by_saved_cut_boundaries(
                    nonlocal_final,
                    context="자동모드 최종 자막 임시 컷",
                    include_confirmed=False,
                    include_provisional=True,
                )
                nonlocal_final = self._split_by_saved_cut_boundaries(nonlocal_final, context="자동모드 최종 자막")
                nonlocal_final = align_stt_candidates_to_subtitle_segments(nonlocal_final)

                def _auto_proceed(_final_segments=nonlocal_final):
                    nonlocal final_segments
                    final_segments = _final_segments
                    action_state[0] = "next"
                    edit_event.set()

                auto_delay = 0.35 if getattr(self, "_individual_queue_mode", False) else 0.05
                threading.Timer(auto_delay, _auto_proceed).start()

            edit_event.wait()

            if action_state[0] == "restart":
                self._handle_restart(target_file)
                action_state[0] = "next"
                continue

            if not self._active:
                return
            if action_state[0] == "prev":
                self._ui_call("request_show_home")
                raise Exception("USER_PREV")
            if action_state[0] == "exit":
                self._ui_call("request_show_home")
                raise Exception("USER_EXIT")

            # ── STEP 5~6: 저장 + 내보내기 ──
            if not self._ui_is_alive():
                self._active = False
                return
            self._subtitle_generation_memory_checkpoint(memory_guard, "save_export_start", force=True)
            self._save_and_export(target_file, queue_index, final_segments, is_auto_mode)
            self._subtitle_generation_memory_checkpoint(
                memory_guard,
                "save_export_done",
                include_gpu=True,
                cleanup=True,
                force=True,
            )

            if action_state[0] == "restart":
                self._handle_restart(target_file)
                action_state[0] = "start"
                continue
            break

        if memory_guard is not None:
            try:
                memory_guard.stop()
            except Exception:
                pass

        if action_state[0] == "exit" or not getattr(self, "_active", True):
            try:
                if self._ui_is_alive():
                    self._ui_call("request_show_home")
            except Exception:
                pass
            raise Exception("USER_EXIT")
