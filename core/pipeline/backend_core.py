# Version: 03.14.33
# Phase: PHASE1-B
"""
core/pipeline/backend_core.py
CoreBackend — 메인 백엔드 클래스 (초기화 · 시작 · 정지 · ETA 사전계산)
Mixin 상속: PipelineHelpersMixin, SinglePipelineMixin, MulticlipPipelineMixin
"""
import os
import threading

from core.autopilot_policy import compact_progress_event, stage_prewarm_decision
from core.performance import mark_runtime_scheduler_start
from core.runtime.logger import get_logger
from core.audio.media_processor import VideoProcessor
from core.personalization.runtime_personalization import merged_runtime_override
from core.time_history import get_expected_time
from core.settings import (
    clear_runtime_settings_override,
    get_model_key,
    load_settings,
    set_runtime_settings_override,
)
from core.media_info import probe_media_many

from core.pipeline.pipeline_helpers import PipelineHelpersMixin
from core.pipeline.single_pipeline import SinglePipelineMixin
from core.pipeline.multiclip_pipeline import MulticlipPipelineMixin


class CoreBackend(PipelineHelpersMixin, SinglePipelineMixin, MulticlipPipelineMixin):
    """AI Subtitle Studio 핵심 백엔드 — STT 파이프라인 총괄."""

    def __init__(self, main_window):
        self.ui = main_window
        self.files_to_process = []
        self.current_folder = None
        self.min_speakers = 1
        self.max_speakers = 1
        self._active = False
        self._speaker_map = []
        get_logger().set_ui_callback(main_window.append_log)
        self.video_processor = VideoProcessor()
        self._pipeline_thread = None

        self.total_expected_time = 0.0
        self.pipeline_start_time = 0.0
        self.is_first_start = True
        self._individual_queue_mode = False

        self._prefetch_cache = {}
        self._prefetch_threads = {}
        self._prefetch_generation = 0
        self._prefetch_lock = threading.Lock()
        self._current_personalization_runtime_override = {}

    def _apply_personalization_runtime_override_for_file(self, target_file: str) -> dict:
        base_override = dict(getattr(self.ui, "_runtime_settings_override", None) or {})
        merged = merged_runtime_override(base_override, str(target_file or ""))
        self._current_personalization_runtime_override = dict(merged)
        set_runtime_settings_override(merged)
        target_name = os.path.basename(str(target_file or "")) or "-"
        if merged:
            detail_keys = (
                "selected_audio_ai",
                "selected_whisper_model",
                "stt_quality_preset",
                "stt_ensemble_enabled",
                "split_length_threshold",
                "sub_max_cps",
                "sub_gap_break_sec",
                "selected_model",
                "selected_llm_provider",
            )
            details = []
            for key in detail_keys:
                if key not in merged:
                    continue
                value = merged[key]
                if key == "selected_whisper_model":
                    try:
                        value = os.path.basename(str(value).rstrip("/\\")) or value
                    except Exception:
                        pass
                details.append(f"{key}={value}")
            if not details:
                details = [f"{key}={value}" for key, value in list(merged.items())[:6]]
            get_logger().log(f"🧠 [개인화] {target_name} 적용: {', '.join(details)}")
        else:
            get_logger().log(f"🧠 [개인화] {target_name} 적용 데이터 없음, 기본 설정 유지")
        return merged

    def _reset_ui_individual_clip_context(self, *, clear_project: bool = True):
        ui = getattr(self, "ui", None)
        if ui is None:
            return
        reset = getattr(ui, "_reset_transient_multiclip_state", None)
        if callable(reset):
            try:
                reset()
            except Exception:
                pass
        else:
            for attr, value in (
                ("_multiclip_files", []),
                ("_multiclip_boundaries", []),
                ("_accumulated_vad", []),
                ("_project_boundary_times", []),
                ("_reuse_clip_indices", set()),
            ):
                try:
                    setattr(ui, attr, value.copy() if hasattr(value, "copy") else value)
                except Exception:
                    pass
        if clear_project:
            try:
                ui._current_project_path = None
            except Exception:
                pass
        for attr, value in (
            ("_editor_roughcut_result", None),
            ("_stored_roughcut_result", None),
            ("_auto_cut_boundary_scan_lines", []),
            ("_cut_boundary_topicless_middle_segments", []),
        ):
            try:
                setattr(ui, attr, value.copy() if hasattr(value, "copy") else value)
            except Exception:
                pass
        try:
            if hasattr(ui, "_sig_update_project_boundary_times"):
                ui._sig_update_project_boundary_times.emit([])
        except Exception:
            pass

    def _reset_backend_individual_clip_context(self, *, invalidate_prefetch: bool = True):
        self._speaker_map = []
        self._reuse_existing_single_subtitle = False
        self._reuse_existing_multiclip_subtitles = False
        self._reuse_clip_indices = set()
        for attr, value in (
            ("_cut_boundary_pipeline_cache", None),
            ("_cut_boundary_provisional_rows", []),
            ("_cut_boundary_sidebar_last_key", None),
            ("_cut_boundary_topicless_logged_keys", []),
            ("_auto_audio_tune_cache", {}),
        ):
            try:
                setattr(self, attr, value.copy() if hasattr(value, "copy") else value)
            except Exception:
                pass
        vp = getattr(self, "video_processor", None)
        if vp is not None:
            for method_name in ("clear_fast_mode_overrides", "clear_auto_audio_tune_overrides"):
                method = getattr(vp, method_name, None)
                if callable(method):
                    try:
                        method()
                    except Exception:
                        pass
            try:
                vp.stage_callback = None
            except Exception:
                pass
            try:
                vp.hard_cut_boundaries = []
            except Exception:
                pass
        if invalidate_prefetch:
            try:
                with self._prefetch_lock:
                    self._prefetch_generation += 1
                    self._prefetch_cache.clear()
                    self._prefetch_threads.clear()
            except Exception:
                pass

    # ─── 파이프라인 시작 ─────────────────────────────────
    def start_pipeline(self, files, folder=None, is_icloud=False, is_auto_start=False):
        pause_lora = getattr(self.ui, "_pause_personalization_for_foreground_activity", None)
        if callable(pause_lora):
            pause_lora("pipeline_start")
        self._active = True
        set_runtime_settings_override(getattr(self.ui, "_runtime_settings_override", None))
        try:
            loaded_settings = load_settings()
            ramp_meta = mark_runtime_scheduler_start(loaded_settings)
            if ramp_meta.get("enabled"):
                get_logger().log(
                    "🐢 [리소스] 시작 램프업: 1개 워커로 예열 후 "
                    f"{int(float(ramp_meta.get('step_sec', 60) or 60))}초마다 단계적으로 증설"
                )
            progress = compact_progress_event(
                stage="diagnostic",
                lane="auto",
                reason="AutoPilot",
                next_stage="audio_extract",
                resource_state="ramp warmup",
            )
            get_logger().log(f"🧭 [AutoPilot] {progress['label']}")
            try:
                self._ui_emit("_sig_editor_processing_stage", f"🧭 {progress['label']}")
            except Exception:
                pass
            prewarm = stage_prewarm_decision("diagnostic", 0.8, loaded_settings)
            self._autopilot_next_prewarm = prewarm
        except Exception:
            pass
        self.files_to_process = list(files)
        self.current_folder = folder
        self.is_icloud = bool(is_icloud)
        self.is_auto_start = is_auto_start
        self._individual_queue_mode = bool(folder or is_icloud or is_auto_start)
        self._show_queue_for_current_run = bool(self.files_to_process)
        self._reuse_existing_single_subtitle = False

        if self._individual_queue_mode:
            self._reset_backend_individual_clip_context(invalidate_prefetch=True)
            self._reset_ui_individual_clip_context(clear_project=True)

        self.total_expected_time = 0.0
        self.pipeline_start_time = 0.0
        self.is_first_start = True

        with self._prefetch_lock:
            self._prefetch_generation += 1
            self._prefetch_cache = {}
            self._prefetch_threads = {}

        if not self.files_to_process:
            self._active = False
            clear_runtime_settings_override()
            if hasattr(self.ui, "_clear_runtime_quality_override"):
                self.ui._clear_runtime_quality_override()
            return

        if len(self.files_to_process) == 1 and not is_auto_start:
            self._reuse_existing_single_subtitle = self._ask_single_existing_subtitle(
                self.files_to_process[0]
            )

        if self._show_queue_for_current_run and hasattr(self.ui, "init_queue_list"):
            self.ui.init_queue_list(self.files_to_process)

        self._video_durations = {}
        self._eta_thread = threading.Thread(
            target=self._precalculate_etas, daemon=True, name="eta-calculator"
        )
        self._eta_thread.start()

        get_logger().log(f"🚀 총 {len(self.files_to_process)}개 파일 처리 시작!")
        try:
            refresher = getattr(self.ui, "_poll_runtime_resource_coordinator", None)
            if callable(refresher):
                refresher()
        except Exception:
            pass
        self._pipeline_thread = threading.Thread(
            target=self._run_all, daemon=True, name="pipeline-main"
        )
        self._pipeline_thread.start()

    # ─── 재시작 ──────────────────────────────────────────
    def restart_current_file(self):
        if hasattr(self, "_action_state"):
            self._action_state[0] = "restart"
        if hasattr(self, "_edit_event"):
            self._edit_event.set()
        self._speaker_map = []

    # ─── 정지 ────────────────────────────────────────────
    def stop(self, *, log_context: str = "파이프라인 중단", unload_llm: bool = True):
        self._active = False

        try:
            if hasattr(self, "video_processor"):
                self.video_processor.stop_transcribe()
        except Exception as e:
            get_logger().log(f"⚠️ stop_transcribe 실패: {e}")

        if unload_llm:
            try:
                settings = load_settings()
                llm_models = [
                    settings.get("selected_model", ""),
                    settings.get("roughcut_llm_model", ""),
                    settings.get("selected_roughcut_llm_model", ""),
                ]
                from core.llm.ollama_provider import shutdown_local_ollama_runtime_async

                shutdown_local_ollama_runtime_async(
                    llm_models,
                    logger=get_logger(),
                    log_context=str(log_context or "파이프라인 중단"),
                    timeout_sec=0.6,
                )
            except Exception as e:
                get_logger().log(f"⚠️ LLM 모델 종료 요청 실패: {e}")

        try:
            with self._prefetch_lock:
                self._prefetch_generation += 1
                self._prefetch_cache.clear()
                self._prefetch_threads.clear()
        except Exception:
            pass

        if hasattr(self, "_edit_event"):
            self._edit_event.set()
        if hasattr(self, "_start_event"):
            self._start_event.set()
        try:
            refresher = getattr(self.ui, "_poll_runtime_resource_coordinator", None)
            if callable(refresher):
                refresher()
        except Exception:
            pass

    # ─── ETA 사전 계산 ───────────────────────────────────
    def _precalculate_etas(self):
        total_expected_time = 0.0
        s = load_settings()
        model_key = "QUALITY:" + get_model_key(s)

        media_infos = probe_media_many(self.files_to_process)
        for i, target_file in enumerate(self.files_to_process):
            try:
                info = media_infos[i] if i < len(media_infos) else {}
                duration_sec = info["duration"]
                info_txt = info["info_txt"]
                len_txt = info["len_txt"]

                self._video_durations[target_file] = duration_sec

                expected_time = get_expected_time(model_key, duration_sec)
                if expected_time > 0:
                    total_expected_time += expected_time

                if self._show_queue_for_current_run and hasattr(self.ui, "_sig_update_queue"):
                    self.ui._sig_update_queue.emit(
                        i, "대기 중", str(expected_time), info_txt, len_txt
                    )
            except Exception as e:
                get_logger().log(
                    f"⚠️ ETA 계산 실패: {os.path.basename(target_file)} / {e}"
                )
                if self._show_queue_for_current_run and hasattr(self.ui, "_sig_update_queue"):
                    self.ui._sig_update_queue.emit(
                        i, "대기 중", "예상불가", "오류", "-"
                    )

        self.total_expected_time = total_expected_time

        if (
            self._show_queue_for_current_run
            and total_expected_time > 0
            and hasattr(self.ui, "_sig_update_queue_header")
        ):
            t_mins, t_secs = int(total_expected_time // 60), int(
                total_expected_time % 60
            )
            t_hours = t_mins // 60
            if t_hours > 0:
                t_mins = t_mins % 60
                total_str = f"{t_hours}시간 {t_mins}분 {t_secs}초"
            else:
                total_str = f"{t_mins}분 {t_secs}초"
            current = max(1, int(getattr(self.ui, "_current_file_idx", 1) or 1))
            pct = max(0, int(getattr(self.ui, "_real_pct", 0) or 0))
            self.ui._sig_update_queue_header.emit(
                current, len(self.files_to_process), pct, total_str
            )
