# Version: 02.02.01
# Phase: PHASE1-B
"""
core/pipeline/backend_core.py
CoreBackend — 메인 백엔드 클래스 (초기화 · 시작 · 정지 · ETA 사전계산)
Mixin 상속: PipelineHelpersMixin, SinglePipelineMixin, MulticlipPipelineMixin
"""
import os
import threading
import time

import config
from logger import get_logger
from core.audio.media_processor import VideoProcessor
from core.time_history import get_expected_time
from core.settings import load_settings, get_model_key
from core.media_info import probe_media

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

        self._prefetch_cache = {}
        self._prefetch_threads = {}
        self._prefetch_generation = 0
        self._prefetch_lock = threading.Lock()

    # ─── 파이프라인 시작 ─────────────────────────────────
    def start_pipeline(self, files, folder=None, is_icloud=False, is_auto_start=False):
        self._active = True
        self.files_to_process = list(files)
        self.current_folder = folder
        self.is_auto_start = is_auto_start

        self.total_expected_time = 0.0
        self.pipeline_start_time = 0.0
        self.is_first_start = True

        with self._prefetch_lock:
            self._prefetch_generation += 1
            self._prefetch_cache = {}
            self._prefetch_threads = {}

        if not self.files_to_process:
            return

        if hasattr(self.ui, "init_queue_list"):
            self.ui.init_queue_list(self.files_to_process)

        self._video_durations = {}
        self._eta_thread = threading.Thread(
            target=self._precalculate_etas, daemon=True, name="eta-calculator"
        )
        self._eta_thread.start()

        get_logger().log(f"🚀 총 {len(self.files_to_process)}개 파일 처리 시작!")
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
    def stop(self):
        self._active = False

        try:
            if hasattr(self, "video_processor"):
                self.video_processor.stop_transcribe()
        except Exception as e:
            get_logger().log(f"⚠️ stop_transcribe 실패: {e}")

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

    # ─── ETA 사전 계산 ───────────────────────────────────
    def _precalculate_etas(self):
        total_expected_time = 0.0
        s = load_settings()
        model_key = "QUALITY:" + get_model_key(s)

        for i, target_file in enumerate(self.files_to_process):
            try:
                info = probe_media(target_file)
                duration_sec = info["duration"]
                info_txt = info["info_txt"]
                len_txt = info["len_txt"]

                self._video_durations[target_file] = duration_sec

                expected_time = get_expected_time(model_key, duration_sec)
                if expected_time > 0:
                    total_expected_time += expected_time

                if hasattr(self.ui, "_sig_update_queue"):
                    self.ui._sig_update_queue.emit(
                        i, "⏳ 대기 중", str(expected_time), info_txt, len_txt
                    )
            except Exception as e:
                get_logger().log(
                    f"⚠️ ETA 계산 실패: {os.path.basename(target_file)} / {e}"
                )
                if hasattr(self.ui, "_sig_update_queue"):
                    self.ui._sig_update_queue.emit(
                        i, "⏳ 대기 중", "예상불가", "오류", "-"
                    )

        self.total_expected_time = total_expected_time

        if total_expected_time > 0 and hasattr(self.ui, "_sig_update_queue_header"):
            t_mins, t_secs = int(total_expected_time // 60), int(
                total_expected_time % 60
            )
            t_hours = t_mins // 60
            if t_hours > 0:
                t_mins = t_mins % 60
                total_str = f"{t_hours}시간 {t_mins}분 {t_secs}초"
            else:
                total_str = f"{t_mins}분 {t_secs}초"
            self.ui._sig_update_queue_header.emit(
                1, len(self.files_to_process), 0, total_str
            )
