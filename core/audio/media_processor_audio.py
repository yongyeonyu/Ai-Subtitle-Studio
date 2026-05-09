# Version: 03.14.33
# Phase: PHASE2
"""Audio command, preprocessing, cache, and chunk helpers for VideoProcessor."""

from __future__ import annotations

import importlib.util
import contextlib
import gc
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tempfile
import warnings
import wave
from concurrent.futures import ThreadPoolExecutor

from core.audio.runtime_cleanup import clear_audio_model_memory_caches
from core.llm.secure_keys import get_api_key
from core.media_fingerprint import media_file_fingerprint, media_fingerprint_digest
from core.media_info import probe_media
from core.performance import (
    bounded_worker_count,
)
from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs, rnnoise_binary, subprocess_env
from core.runtime import config
from core.runtime.logger import get_logger
from core.runtime.multi_process import runtime_parallel_worker_plan
from core.subtitle_quality.vad_alignment_checker import apply_review_vad_settings, review_vad_config

_VAD_CACHE_VERSION = 3
_AUDIO_CACHE_VERSION = 7


def _runtime_get_logger():
    owner = sys.modules.get("core.audio.media_processor")
    return getattr(owner, "get_logger", get_logger)()


def _runtime_get_api_key(service: str) -> str:
    owner = sys.modules.get("core.audio.media_processor")
    return getattr(owner, "get_api_key", get_api_key)(service)


def _media_command_error_summary(returncode: int, summary: str) -> str:
    summary = str(summary or "").strip()
    if summary:
        return summary
    if int(returncode or 0) == 255:
        return "외부 중단 신호로 프로세스가 종료되었습니다. 처리 중 홈/앱 종료 정리 루틴이 실행되었는지 확인하세요."
    return "오류 출력 없음"


class VideoProcessorAudioHelpersMixin:
    def _notify_stage(self, status: str):
        callback = getattr(self, "stage_callback", None)
        if not callable(callback):
            return
        try:
            callback(str(status or ""))
        except Exception:
            pass

    @staticmethod
    def _vad_segment_intersects_range(segment: dict, start_sec: float, end_sec: float) -> bool:
        try:
            seg_start = float(segment.get("start", 0.0) or 0.0)
            seg_end = float(segment.get("end", 0.0) or 0.0)
        except Exception:
            return False
        return seg_end > float(start_sec or 0.0) and seg_start < float(end_sec or 0.0)

    def _run_media_command(self, cmd: list[str], *, label: str, timeout: float | None = None, env: dict | None = None) -> bool:
        if self._should_run_ffmpeg_with_progress(cmd):
            return self._run_ffmpeg_with_progress(cmd, label=label, timeout=timeout, env=env)

        try:
            subprocess_kwargs = hidden_subprocess_kwargs()
            if env is not None:
                subprocess_kwargs["env"] = env
            result = subprocess.run(
                [str(x) for x in cmd],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                **subprocess_kwargs,
            )
        except FileNotFoundError as e:
            _runtime_get_logger().log(f"  ❌ {label} 실행 파일을 찾을 수 없습니다: {e}")
            return False
        except Exception as e:
            _runtime_get_logger().log(f"  ❌ {label} 실행 오류: {e}")
            return False

        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            lines = [line.strip() for line in err.splitlines() if line.strip()]
            summary = "\n".join(lines[-10:]) if lines else err
            summary = _media_command_error_summary(result.returncode, summary)
            _runtime_get_logger().log(f"  ❌ {label} 실패: {summary[:1200]}")
            return False
        return True

    @staticmethod
    def _should_run_ffmpeg_with_progress(cmd: list[str]) -> bool:
        if not cmd:
            return False
        binary = os.path.basename(str(cmd[0] or "")).lower()
        return binary.startswith("ffmpeg") and "-progress" not in [str(x) for x in cmd]

    @staticmethod
    def _first_ffmpeg_input(cmd: list[str]) -> str:
        items = [str(x) for x in cmd]
        for idx, item in enumerate(items[:-1]):
            if item == "-i":
                return items[idx + 1]
        return ""

    @staticmethod
    def _ffmpeg_progress_command(cmd: list[str]) -> list[str]:
        items = [str(x) for x in cmd]
        insert_at = 1
        for marker in ("-nostdin", "-loglevel"):
            if marker in items:
                idx = items.index(marker)
                insert_at = max(insert_at, idx + (2 if marker == "-loglevel" and idx + 1 < len(items) else 1))
        return items[:insert_at] + ["-progress", "pipe:1", "-nostats"] + items[insert_at:]

    def _media_duration_for_progress(self, path: str) -> float:
        if not path:
            return 0.0
        try:
            if path.lower().endswith(".wav"):
                with wave.open(path, "rb") as wf:
                    rate = float(wf.getframerate() or 0)
                    return (wf.getnframes() / rate) if rate > 0 else 0.0
        except Exception:
            pass
        try:
            info = probe_media(path)
            return float(info.get("duration") or 0.0)
        except Exception:
            return 0.0

    def _emit_ffmpeg_progress(self, label: str, ratio: float, *, force: bool = False) -> int:
        pct = max(0, min(100 if force else 99, int(ratio * 100)))
        state = getattr(self, "_ffmpeg_progress_state", {})
        key = str(label or "ffmpeg")
        last_pct, _last_ts = state.get(key, (-1, 0.0))
        if pct <= last_pct:
            return last_pct
        state[key] = (pct, time.monotonic())
        self._ffmpeg_progress_state = state
        text = f"⏳ [전처리] {label} 진행 중 {pct}%"
        self._notify_stage(text)
        _runtime_get_logger().log(f"  └ [전처리] {label} 진행률 {pct}%")
        return pct

    def _emit_vad_progress(self, label: str, phase: str, pct: int, *, force: bool = False, step: int = 10) -> int:
        step = max(1, int(step or 10))
        pct = max(0, min(100, int(pct or 0)))
        if not force and pct < 100:
            pct = (pct // step) * step
        state = getattr(self, "_vad_progress_state", {})
        key = f"{label}:{phase}"
        last_pct = state.get(key, -1)
        if pct <= last_pct:
            return last_pct
        state[key] = pct
        self._vad_progress_state = state
        self._notify_stage(f"⏳ [VAD] {label} {phase} {pct}%")
        _runtime_get_logger().log(f"  └ [VAD 후처리] {label} {phase} 진행률 {pct}%")
        return pct

    def _start_vad_heartbeat(self, label: str, phase: str, *, interval_sec: float = 5.0):
        stop_event = threading.Event()
        interval = max(1.0, float(interval_sec or 5.0))

        def _beat():
            started = time.monotonic()
            while not stop_event.wait(interval):
                elapsed = int(time.monotonic() - started)
                self._notify_stage(f"⏳ [VAD] {label} {phase} 중... {elapsed}초")
                _runtime_get_logger().log(f"  └ [VAD 후처리] {label} {phase} 진행 중... {elapsed}초")

        thread = threading.Thread(target=_beat, name=f"vad-heartbeat-{label}-{phase}", daemon=True)
        thread.start()
        return stop_event, thread

    @staticmethod
    def _stop_vad_heartbeat(handle):
        if not handle:
            return
        stop_event, thread = handle
        try:
            stop_event.set()
            thread.join(timeout=0.2)
        except Exception:
            pass

    def _start_audio_heartbeat(self, label: str, phase: str = "처리", *, interval_sec: float = 5.0):
        stop_event = threading.Event()
        interval = max(1.0, float(interval_sec or 5.0))

        def _beat():
            started = time.monotonic()
            while not stop_event.wait(interval):
                elapsed = int(time.monotonic() - started)
                self._notify_stage(f"⏳ [음성] {label} {phase} 중... {elapsed}초")
                _runtime_get_logger().log(f"  └ [음성] {label} {phase} 진행 중... {elapsed}초")

        thread = threading.Thread(target=_beat, name=f"audio-heartbeat-{label}-{phase}", daemon=True)
        thread.start()
        return stop_event, thread

    @staticmethod
    def _stop_audio_heartbeat(handle):
        if not handle:
            return
        stop_event, thread = handle
        try:
            stop_event.set()
            thread.join(timeout=0.2)
        except Exception:
            pass

    def _run_ffmpeg_with_progress(self, cmd: list[str], *, label: str, timeout: float | None = None, env: dict | None = None) -> bool:
        duration = self._media_duration_for_progress(self._first_ffmpeg_input(cmd))
        if duration <= 0:
            return self._run_media_command_no_progress(cmd, label=label, timeout=timeout, env=env)

        progress_cmd = self._ffmpeg_progress_command(cmd)
        stderr_lines = []
        started_at = time.monotonic()
        last_pct = -1
        try:
            state = getattr(self, "_ffmpeg_progress_state", {})
            state.pop(str(label or "ffmpeg"), None)
            self._ffmpeg_progress_state = state
            subprocess_kwargs = hidden_subprocess_kwargs()
            if env is not None:
                subprocess_kwargs["env"] = env
            proc = subprocess.Popen(
                progress_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                **subprocess_kwargs,
            )
            self._emit_ffmpeg_progress(label, 0.0, force=True)
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                if timeout and time.monotonic() - started_at > timeout:
                    proc.kill()
                    _runtime_get_logger().log(f"  ❌ {label} 실행 오류: timeout")
                    return False
                line = raw_line.strip()
                if not (line.startswith("out_time_ms=") or line.startswith("out_time_us=")):
                    if line and not line.startswith((
                        "frame=", "fps=", "stream_", "progress=", "bitrate=", "total_size=",
                        "out_time=", "out_time_us=", "speed=", "dup_frames=", "drop_frames="
                    )):
                        stderr_lines.append(line)
                        stderr_lines = stderr_lines[-12:]
                    continue
                try:
                    raw_value = float(line.split("=", 1)[1])
                    out_sec = raw_value / 1_000_000.0
                except Exception:
                    continue
                last_pct = self._emit_ffmpeg_progress(label, out_sec / duration)
            proc.wait(timeout=1)
        except FileNotFoundError as e:
            _runtime_get_logger().log(f"  ❌ {label} 실행 파일을 찾을 수 없습니다: {e}")
            return False
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass
            _runtime_get_logger().log(f"  ❌ {label} 실행 오류: timeout")
            return False
        except Exception as e:
            _runtime_get_logger().log(f"  ❌ {label} 실행 오류: {e}")
            return False

        if proc.returncode != 0:
            summary = "\n".join(stderr_lines[-10:])
            summary = _media_command_error_summary(proc.returncode, summary)
            _runtime_get_logger().log(f"  ❌ {label} 실패(rc={proc.returncode}): {summary[:1200]}")
            return False
        if last_pct < 100:
            self._emit_ffmpeg_progress(label, 1.0, force=True)
        _runtime_get_logger().log(f"  └ [전처리] {label} 완료")
        return True

    def _run_media_command_no_progress(self, cmd: list[str], *, label: str, timeout: float | None = None, env: dict | None = None) -> bool:
        try:
            subprocess_kwargs = hidden_subprocess_kwargs()
            if env is not None:
                subprocess_kwargs["env"] = env
            result = subprocess.run(
                [str(x) for x in cmd],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                **subprocess_kwargs,
            )
        except FileNotFoundError as e:
            _runtime_get_logger().log(f"  ❌ {label} 실행 파일을 찾을 수 없습니다: {e}")
            return False
        except Exception as e:
            _runtime_get_logger().log(f"  ❌ {label} 실행 오류: {e}")
            return False

        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            lines = [line.strip() for line in err.splitlines() if line.strip()]
            summary = "\n".join(lines[-10:]) if lines else err
            summary = _media_command_error_summary(result.returncode, summary)
            _runtime_get_logger().log(f"  ❌ {label} 실패: {summary[:1200]}")
            return False
        return True

    def _huggingface_env(self) -> dict:
        env = subprocess_env()
        token = env.get("HF_TOKEN") or env.get("HUGGINGFACE_HUB_TOKEN") or _runtime_get_api_key("huggingface")
        if token:
            env.setdefault("HF_TOKEN", token)
            env.setdefault("HUGGINGFACE_HUB_TOKEN", token)
        return env

    def _resolve_python_cli(self, name: str, env_var: str | None = None) -> str:
        exe_name = f"{name}.exe" if getattr(config, "IS_WINDOWS", False) and not name.endswith(".exe") else name
        isolated_tool_path = ""
        if name == "resemble-enhance":
            scripts_dir = "Scripts" if getattr(config, "IS_WINDOWS", False) else "bin"
            isolated_tool_path = os.path.join(config.BASE_DIR, ".codex_work", "resemble_enhance", scripts_dir, exe_name)
        candidates = [
            os.environ.get(env_var, "") if env_var else "",
            shutil.which(name),
            os.path.join(os.path.dirname(sys.executable), exe_name) if sys.executable else "",
            os.path.join(config.BASE_DIR, "bin", exe_name),
            os.path.join(config.BASE_DIR, "tools", exe_name),
            isolated_tool_path,
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate
        return exe_name

    @staticmethod
    def _resemble_enhance_device() -> str:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=r".*pynvml package is deprecated.*",
                    category=FutureWarning,
                )
                import torch

            if getattr(getattr(torch, "backends", None), "mps", None) and torch.backends.mps.is_available():
                return "mps"
            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"

    def _resemble_enhance_command(self, cli: str, in_dir: str, out_dir: str, device: str) -> list[str]:
        runner = os.path.join(config.BASE_DIR, "core", "audio", "resemble_enhance_runner.py")
        cli_dir = os.path.dirname(os.path.abspath(cli or ""))
        python_name = "python.exe" if getattr(config, "IS_WINDOWS", False) else "python"
        isolated_python = os.path.join(cli_dir, python_name)
        if os.path.exists(runner) and os.path.exists(isolated_python):
            return [isolated_python, runner, in_dir, out_dir, "--denoise_only", "--device", device]
        return [cli, in_dir, out_dir, "--denoise_only", "--device", device]

    def _apply_rnnoise(self, source_wav: str, target_wav: str) -> bool:
        ffmpeg = ffmpeg_binary()
        rnnoise = rnnoise_binary()
        raw_in = f"{target_wav}.rnnoise.in.raw"
        raw_out = f"{target_wav}.rnnoise.out.raw"
        try:
            if not self._run_media_command(
                [
                    ffmpeg, "-y", "-nostdin", "-loglevel", "error",
                    "-i", source_wav,
                    "-ac", "1", "-ar", "48000",
                    "-f", "s16le",
                    raw_in,
                ],
                label="RNNoise 입력 변환",
            ):
                return False
            if not self._run_media_command([rnnoise, raw_in, raw_out], label="RNNoise 노이즈 제거"):
                _runtime_get_logger().log("  ⚠️ RNNoise 실행 실패 또는 미설치: FFMPEG 정제로 계속 진행합니다")
                return False
            return self._run_media_command(
                [
                    ffmpeg, "-y", "-nostdin", "-loglevel", "error",
                    "-f", "s16le", "-ar", "48000", "-ac", "1",
                    "-i", raw_out,
                    "-acodec", "pcm_s16le",
                    target_wav,
                ],
                label="RNNoise WAV 변환",
            )
        finally:
            for path in (raw_in, raw_out):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass

    def _copy_first_wav_from_dir(self, source_dir: str, target_wav: str) -> bool:
        for root, _dirs, files in os.walk(source_dir):
            for name in files:
                if name.lower().endswith(".wav"):
                    shutil.copy2(os.path.join(root, name), target_wav)
                    return os.path.exists(target_wav)
        return False

    def _apply_resemble_enhance(self, source_wav: str, target_wav: str) -> bool:
        cli = self._resolve_python_cli("resemble-enhance", env_var="RESEMBLE_ENHANCE_BINARY")
        device = self._resemble_enhance_device()
        work_dir = f"{target_wav}.resemble_tmp"
        in_dir = os.path.join(work_dir, "input")
        out_dir = os.path.join(work_dir, "output")
        try:
            os.makedirs(in_dir, exist_ok=True)
            os.makedirs(out_dir, exist_ok=True)
            shutil.copy2(source_wav, os.path.join(in_dir, "input.wav"))
            heartbeat = self._start_audio_heartbeat("Resemble Enhance", "음성 향상", interval_sec=5.0)
            try:
                if not self._run_media_command(
                    self._resemble_enhance_command(cli, in_dir, out_dir, device),
                    label="Resemble Enhance 음성 향상",
                    timeout=900,
                    env=self._huggingface_env(),
                ):
                    _runtime_get_logger().log("  ⚠️ Resemble Enhance 실행 실패 또는 미설치: FFMPEG 정제로 계속 진행합니다")
                    return False
            finally:
                self._stop_audio_heartbeat(heartbeat)
            return self._copy_first_wav_from_dir(out_dir, target_wav)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
            clear_audio_model_memory_caches(include_gpu=True)

    @staticmethod
    def _clearvoice_supported_models() -> tuple[str, ...]:
        return (
            "MossFormerGAN_SE_16K",
            "FRCRN_SE_16K",
            "MossFormer2_SE_48K",
        )

    def _clearvoice_effective_settings(self) -> dict:
        data = getattr(self, "_clearvoice_runtime_settings", None)
        return dict(data or {})

    def _clearvoice_model_name(self, settings: dict | None = None) -> str:
        data = dict(settings or self._clearvoice_effective_settings() or {})
        requested = str(
            os.environ.get(
                "AI_SUBTITLE_CLEARVOICE_MODEL",
                data.get("clearvoice_model_name", ""),
            )
            or ""
        ).strip()
        if requested in self._clearvoice_supported_models():
            return requested
        # STT 최종 입력이 16k mono 이므로 기본 ClearVoice도 16k 경로로 고정합니다.
        return "MossFormerGAN_SE_16K"

    def _clearvoice_input_sample_rate(self, settings: dict | None = None) -> int:
        model_name = self._clearvoice_model_name(settings)
        return 16000 if model_name.endswith("16K") else 48000

    def _audio_processing_sample_rate(self, audio_ai: str, settings: dict | None = None) -> int:
        if str(audio_ai or "none").strip().lower() == "clearvoice":
            return self._clearvoice_input_sample_rate(settings)
        return 48000

    def _audio_ai_variant(self, audio_ai: str, settings: dict | None = None) -> str:
        audio_kind = str(audio_ai or "none").strip().lower()
        if audio_kind != "none" and self._macos_native_fast_audio_flatten_enabled(settings):
            return "macos_native_fast_audio_flatten_v1"
        if audio_kind == "clearvoice":
            if self._clearvoice_native_ffmpeg_enabled(settings):
                return "native_ffmpeg_v1"
            return self._clearvoice_model_name(settings)
        return ""

    @staticmethod
    def _clearvoice_native_ffmpeg_enabled(settings: dict | None = None) -> bool:
        env_value = os.environ.get("AI_SUBTITLE_CLEARVOICE_NATIVE_FFMPEG")
        if env_value is not None:
            text = str(env_value or "").strip().lower()
            if text in {"1", "true", "yes", "on", "enabled", "enable"}:
                return True
            if text in {"0", "false", "no", "off", "disabled", "disable", "끄기", "끔"}:
                return False
        return VideoProcessorAudioHelpersMixin._settings_bool(settings, "clearvoice_native_ffmpeg_enabled", True)

    @staticmethod
    def _macos_native_fast_audio_flatten_enabled(settings: dict | None = None) -> bool:
        env_value = os.environ.get("AI_SUBTITLE_STUDIO_FAST_AUDIO_FLATTEN")
        if env_value is not None:
            text = str(env_value or "").strip().lower()
            if text in {"1", "true", "yes", "on", "enabled", "enable"}:
                return True
            if text in {"0", "false", "no", "off", "disabled", "disable", "끄기", "끔"}:
                return False
        if not getattr(config, "IS_MAC", False):
            return False
        return VideoProcessorAudioHelpersMixin._settings_bool(
            settings,
            "macos_native_fast_audio_flatten_enabled",
            True,
        )

    def _clearvoice_engine_handle(self, model_name: str):
        cache = getattr(self, "_clearvoice_engine_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._clearvoice_engine_cache = cache
        locks = getattr(self, "_clearvoice_engine_locks", None)
        if not isinstance(locks, dict):
            locks = {}
            self._clearvoice_engine_locks = locks
        cache_lock = getattr(self, "_clearvoice_engine_cache_lock", None)
        if cache_lock is None:
            cache_lock = threading.Lock()
            self._clearvoice_engine_cache_lock = cache_lock

        with cache_lock:
            if model_name not in cache:
                from clearvoice import ClearVoice

                quiet = io.StringIO()
                with contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
                    cache[model_name] = ClearVoice(
                        task="speech_enhancement",
                        model_names=[model_name],
                    )
            if model_name not in locks:
                locks[model_name] = threading.Lock()
            return cache[model_name], locks[model_name]

    def _apply_clearvoice_subprocess(self, source_wav: str, target_wav: str, *, model_name: str) -> bool:
        script = (
            "import gc\n"
            "import sys\n"
            "from clearvoice import ClearVoice\n"
            "source, target, model_name = sys.argv[1], sys.argv[2], sys.argv[3]\n"
            "engine = None\n"
            "audio = None\n"
            "try:\n"
            "    engine = ClearVoice(task='speech_enhancement', model_names=[model_name])\n"
            "    audio = engine(input_path=source, online_write=False)\n"
            "    engine.write(audio, output_path=target)\n"
            "finally:\n"
            "    del audio\n"
            "    del engine\n"
            "    gc.collect()\n"
            "    try:\n"
            "        from core.audio.torch_acceleration import trim_torch_memory_caches\n"
            "        trim_torch_memory_caches(include_sync=True)\n"
            "    except Exception:\n"
            "        pass\n"
        )
        return self._run_media_command(
            [sys.executable, "-c", script, source_wav, target_wav, model_name],
            label="ClearVoice 음성 향상",
            timeout=900,
            env=self._huggingface_env(),
        )

    def _apply_clearvoice_native_ffmpeg(self, source_wav: str, target_wav: str, settings: dict | None = None) -> bool:
        filter_chain = self._build_audio_cleanup_filter("clearvoice", dict(settings or {}))
        _runtime_get_logger().log(
            "  ⚙️ ClearVoice Native FFmpeg 경로: 딥러닝 ClearVoice 대신 네이티브 필터로 빠르게 정제합니다"
        )
        return (
            self._run_media_command(
                [
                    ffmpeg_binary(), "-y", "-nostdin", "-loglevel", "error",
                    *self._ffmpeg_parallel_args(dict(settings or {})),
                    "-i", source_wav,
                    "-ac", "1", "-ar", "16000",
                    "-af", filter_chain,
                    "-acodec", "pcm_s16le",
                    target_wav,
                ],
                label="ClearVoice Native FFmpeg",
            )
            and os.path.exists(target_wav)
            and os.path.getsize(target_wav) > 0
        )

    def _apply_clearvoice(self, source_wav: str, target_wav: str) -> bool:
        settings = self._clearvoice_effective_settings()
        if self._clearvoice_native_ffmpeg_enabled(settings):
            return self._apply_clearvoice_native_ffmpeg(source_wav, target_wav, settings)

        if importlib.util.find_spec("clearvoice") is None:
            _runtime_get_logger().log("  ⚠️ ClearVoice 패키지가 설치되어 있지 않습니다: python3.11 -m pip install clearvoice")
            return False
        model_name = self._clearvoice_model_name(settings)
        sample_rate = self._clearvoice_input_sample_rate(settings)
        heartbeat = self._start_audio_heartbeat("ClearVoice", "음성 향상", interval_sec=5.0)
        audio = None
        try:
            _runtime_get_logger().log(
                f"  ⚙️ ClearVoice 최적화 경로: native model={model_name} input={sample_rate}Hz"
            )
            try:
                engine, engine_lock = self._clearvoice_engine_handle(model_name)
                quiet = io.StringIO()
                with engine_lock, contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
                    audio = engine(input_path=source_wav, online_write=False)
                    engine.write(audio, output_path=target_wav)
            except Exception as exc:
                _runtime_get_logger().log(
                    f"  ⚠️ ClearVoice native 경로 실패({exc}): subprocess fallback 으로 재시도합니다"
                )
                if not self._apply_clearvoice_subprocess(source_wav, target_wav, model_name=model_name):
                    _runtime_get_logger().log("  ⚠️ ClearVoice 실행 실패 또는 미설치: FFMPEG 정제로 계속 진행합니다")
                    return False
            if not os.path.exists(target_wav):
                return False
        finally:
            self._stop_audio_heartbeat(heartbeat)
            audio = None
            gc.collect()
            clear_audio_model_memory_caches(include_gpu=True)
        return os.path.exists(target_wav)

    @staticmethod
    def _float_setting(settings: dict, key: str, default: float, min_value: float | None = None, max_value: float | None = None) -> float:
        try:
            value = float(settings.get(key, default))
        except (TypeError, ValueError):
            value = float(default)
        if min_value is not None:
            value = max(min_value, value)
        if max_value is not None:
            value = min(max_value, value)
        return value

    @staticmethod
    def _fmt_filter_num(value: float) -> str:
        return f"{value:g}"

    def _build_ffmpeg_preprocess_filter(self, settings: dict) -> str:
        hp = int(self._float_setting(settings, "ff_hp", settings.get("none_hp", 90), 0, 500))
        lp = int(self._float_setting(settings, "ff_lp", settings.get("none_lp", 3200), 0, 8000))
        nf = self._float_setting(settings, "ff_nf", settings.get("none_nf", -32), -80, 0)
        dyn_m = self._float_setting(settings, "ff_dynaudnorm_m", 10.0, 1.0, 50.0)
        dyn_p = self._float_setting(settings, "ff_dynaudnorm_p", 0.95, 0.5, 1.0)
        treble = self._float_setting(settings, "ff_treble_boost", 0.0, -10.0, 20.0)
        target = self._float_setting(settings, "none_target", -14.0, -40.0, 0.0)

        filters = []
        if hp > 0:
            filters.append(f"highpass=f={hp}")
        if lp > 0:
            filters.append(f"lowpass=f={lp}")
        filters.append(f"afftdn=nf={self._fmt_filter_num(nf)}")
        filters.append(
            "dynaudnorm=f=150:g=9:"
            f"m={self._fmt_filter_num(dyn_m)}:"
            f"p={self._fmt_filter_num(dyn_p)}"
        )
        if abs(treble) >= 0.01:
            filters.append(
                "equalizer=f=3200:width_type=h:width=2200:"
                f"g={self._fmt_filter_num(treble)}"
            )
        filters.append(f"loudnorm=I={self._fmt_filter_num(target)}")
        return ",".join(filters) if filters else "anull"

    def _build_macos_native_fast_audio_flatten_filter(self, settings: dict) -> str:
        hp = int(self._float_setting(settings, "macos_native_fast_audio_flatten_hp", 150, 0, 500))
        lp = int(self._float_setting(settings, "macos_native_fast_audio_flatten_lp", 4600, 1000, 8000))
        comp_th = self._float_setting(settings, "macos_native_fast_audio_flatten_comp_th", -24, -60, 0)
        volume = self._float_setting(settings, "macos_native_fast_audio_flatten_volume", 3.2, 0.5, 8.0)
        limiter = self._float_setting(settings, "macos_native_fast_audio_flatten_limiter", 0.93, 0.1, 1.0)

        filters = []
        if hp > 0:
            filters.append(f"highpass=f={hp}")
        if lp > 0:
            filters.append(f"lowpass=f={lp}")
        filters.append(
            f"acompressor=threshold={self._fmt_filter_num(comp_th)}dB:"
            "ratio=3:attack=5:release=55"
        )
        filters.append(f"volume={self._fmt_filter_num(volume)}")
        filters.append(f"alimiter=limit={self._fmt_filter_num(limiter)}")
        return ",".join(filters)

    def _build_audio_cleanup_filter(self, audio_ai: str, settings: dict) -> str:
        if self._macos_native_fast_audio_flatten_enabled(settings) and str(audio_ai or "none").lower() != "none":
            return self._build_macos_native_fast_audio_flatten_filter(settings)

        df_vol = self._float_setting(settings, "df_vol", 3.5, 0.5, 8.0)

        if audio_ai == "deepfilter":
            hp = int(self._float_setting(settings, "df_hp", 100, 0, 500))
            lp = int(self._float_setting(settings, "df_lp", 8000, 1000, 8000))
            nf = self._float_setting(settings, "df_nf", settings.get("ff_nf", -32), -80, 0)
            eq_gain = self._float_setting(settings, "df_eq_g", 8, -10, 20)
            comp_th = self._float_setting(settings, "df_comp_th", -28, -60, 0)
            return (
                f"highpass=f={hp},lowpass=f={lp},"
                f"afftdn=nf={self._fmt_filter_num(nf)},"
                "equalizer=f=3000:width_type=h:width=2000:"
                f"g={self._fmt_filter_num(eq_gain)},"
                f"acompressor=threshold={self._fmt_filter_num(comp_th)}dB:ratio=4:attack=5:release=50,"
                "speechnorm=e=12:r=0.0001:l=1,"
                f"volume={self._fmt_filter_num(df_vol)},"
                "loudnorm=I=-14:LRA=11:tp=-1.0"
            )

        if audio_ai == "rnnoise":
            hp = int(self._float_setting(settings, "df_hp", 100, 0, 500))
            lp = int(self._float_setting(settings, "df_lp", 8000, 1000, 8000))
            eq_gain = self._float_setting(settings, "df_eq_g", 8, -10, 20)
            comp_th = self._float_setting(settings, "df_comp_th", -28, -60, 0)
            return (
                f"highpass=f={hp},lowpass=f={lp},"
                "equalizer=f=3000:width_type=h:width=2000:"
                f"g={self._fmt_filter_num(eq_gain)},"
                f"acompressor=threshold={self._fmt_filter_num(comp_th)}dB:ratio=3:attack=5:release=60,"
                "speechnorm=e=10:r=0.0001:l=1,"
                f"volume={self._fmt_filter_num(df_vol)},"
                "loudnorm=I=-14:LRA=11:tp=-1.0"
            )

        if audio_ai == "clearvoice":
            hp = int(self._float_setting(settings, "df_hp", settings.get("ff_hp", 150), 0, 500))
            lp = int(self._float_setting(settings, "df_lp", 4600, 1000, 8000))
            nf = self._float_setting(settings, "ff_nf", settings.get("df_nf", -30), -80, 0)
            treble = self._float_setting(settings, "ff_treble_boost", 2.5, -10, 20)
            eq_gain = self._float_setting(settings, "df_eq_g", 6, -10, 20)
            comp_th = self._float_setting(settings, "df_comp_th", -30, -60, 0)
            return (
                f"highpass=f={hp},lowpass=f={lp},"
                f"afftdn=nf={self._fmt_filter_num(nf)},"
                "dynaudnorm=f=150:g=9:m=12:p=0.95,"
                "equalizer=f=3200:width_type=h:width=2200:"
                f"g={self._fmt_filter_num(treble)},"
                "equalizer=f=3000:width_type=h:width=2000:"
                f"g={self._fmt_filter_num(eq_gain)},"
                f"acompressor=threshold={self._fmt_filter_num(comp_th)}dB:ratio=3.5:attack=5:release=55,"
                "speechnorm=e=10:r=0.0001:l=1,"
                "loudnorm=I=-14:LRA=11:tp=-1.0"
            )

        if audio_ai == "resemble_enhance":
            hp = int(self._float_setting(settings, "df_hp", 100, 0, 500))
            lp = int(self._float_setting(settings, "df_lp", 8000, 1000, 8000))
            comp_th = self._float_setting(settings, "df_comp_th", -28, -60, 0)
            return (
                f"highpass=f={hp},lowpass=f={lp},"
                f"acompressor=threshold={self._fmt_filter_num(comp_th)}dB:ratio=2.5:attack=6:release=70,"
                "speechnorm=e=8:r=0.0001:l=1,"
                "loudnorm=I=-14:LRA=11:tp=-1.0"
            )

        if audio_ai == "none":
            return "anull"

        return "anull"

    def _build_deepfilter_fused_ffmpeg_filter(self, settings: dict) -> str:
        ff_hp = int(self._float_setting(settings, "ff_hp", settings.get("none_hp", 90), 0, 500))
        df_hp = int(self._float_setting(settings, "df_hp", 100, 0, 500))
        ff_lp = int(self._float_setting(settings, "ff_lp", settings.get("none_lp", 3200), 0, 8000))
        df_lp = int(self._float_setting(settings, "df_lp", 8000, 1000, 8000))
        ff_nf = self._float_setting(settings, "ff_nf", settings.get("none_nf", -32), -80, 0)
        df_nf = self._float_setting(settings, "df_nf", settings.get("ff_nf", -32), -80, 0)
        dyn_m = self._float_setting(settings, "ff_dynaudnorm_m", 10.0, 1.0, 50.0)
        dyn_p = self._float_setting(settings, "ff_dynaudnorm_p", 0.95, 0.5, 1.0)
        treble = self._float_setting(settings, "ff_treble_boost", 0.0, -10.0, 20.0)
        eq_gain = self._float_setting(settings, "df_eq_g", 8, -10, 20)
        comp_th = self._float_setting(settings, "df_comp_th", -28, -60, 0)
        df_vol = self._float_setting(settings, "df_vol", 3.5, 0.5, 8.0)

        filters = []
        hp = max(ff_hp, df_hp)
        if hp > 0:
            filters.append(f"highpass=f={hp}")
        lp_candidates = [value for value in (ff_lp, df_lp) if value > 0]
        if lp_candidates:
            filters.append(f"lowpass=f={min(lp_candidates)}")
        filters.append(f"afftdn=nf={self._fmt_filter_num(min(ff_nf, df_nf))}")
        filters.append(
            "dynaudnorm=f=150:g=9:"
            f"m={self._fmt_filter_num(dyn_m)}:"
            f"p={self._fmt_filter_num(dyn_p)}"
        )
        if abs(treble) >= 0.01:
            filters.append(
                "equalizer=f=3200:width_type=h:width=2200:"
                f"g={self._fmt_filter_num(treble)}"
            )
        filters.append(
            "equalizer=f=3000:width_type=h:width=2000:"
            f"g={self._fmt_filter_num(eq_gain)}"
        )
        filters.append(
            f"acompressor=threshold={self._fmt_filter_num(comp_th)}dB:"
            "ratio=4:attack=5:release=50"
        )
        filters.append("speechnorm=e=12:r=0.0001:l=1")
        filters.append(f"volume={self._fmt_filter_num(df_vol)}")
        filters.append("loudnorm=I=-14:LRA=11:tp=-1.0")
        return ",".join(filters)

    def _build_fused_ffmpeg_filter(self, audio_ai: str, settings: dict, *, use_basic: bool = True) -> str:
        audio_kind = str(audio_ai or "none").strip().lower()
        if self._macos_native_fast_audio_flatten_enabled(settings):
            return self._build_macos_native_fast_audio_flatten_filter(settings)
        active_filter = self._build_audio_cleanup_filter(audio_kind, settings)
        if not use_basic:
            return active_filter
        if audio_kind == "none":
            return self._build_ffmpeg_preprocess_filter(settings)
        if audio_kind == "deepfilter":
            return self._build_deepfilter_fused_ffmpeg_filter(settings)
        return self._combine_audio_filters(self._build_ffmpeg_preprocess_filter(settings), active_filter)

    @staticmethod
    def _audio_cleanup_label(audio_ai: str, filter_applied: bool = False) -> str:
        if audio_ai in {"rnnoise", "resemble_enhance", "clearvoice"} and not filter_applied:
            return "FFMPEG"
        return {
            "deepfilter": "DeepFilter",
            "rnnoise": "RNNoise",
            "resemble_enhance": "Resemble Enhance",
            "clearvoice": "ClearVoice",
            "none": "미사용",
        }.get(audio_ai, str(audio_ai or "미사용"))

    def _ffmpeg_parallel_args(self, settings: dict) -> list[str]:
        workers = bounded_worker_count(settings.get("ffmpeg_filter_threads", self.io_workers), kind="cpu")
        # `-threads 0` lets codecs choose an efficient default, while
        # `-filter_threads` gives heavier audio filters several cores.
        return ["-threads", "0", "-filter_threads", str(max(1, workers))]

    @staticmethod
    def _ffmpeg_audio_stream_args() -> list[str]:
        # Keep preprocessing on the first audio stream only. GPU video decode does
        # not speed up audio extraction, so avoid touching video/subtitle/data streams.
        return ["-map", "0:a:0", "-vn", "-sn", "-dn"]

    @classmethod
    def _can_fuse_ffmpeg_preprocess(cls, audio_ai: str, settings: dict | None = None) -> bool:
        if cls._macos_native_fast_audio_flatten_enabled(settings):
            return True
        audio_kind = str(audio_ai or "none").lower()
        if audio_kind in {"none", "deepfilter"}:
            return True
        if audio_kind == "clearvoice":
            return cls._clearvoice_native_ffmpeg_enabled(settings)
        return False

    @staticmethod
    def _settings_bool(settings: dict | None, key: str, default: bool = False) -> bool:
        value = dict(settings or {}).get(key, default)
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        if not text:
            return bool(default)
        if text in {"1", "true", "yes", "on", "enabled", "enable"}:
            return True
        if text in {"0", "false", "no", "off", "disabled", "disable", "끄기", "끔"}:
            return False
        return bool(default)

    @staticmethod
    def _combine_audio_filters(*filters: str) -> str:
        chain = []
        for value in filters:
            text = str(value or "").strip()
            if not text or text == "anull":
                continue
            chain.append(text)
        return ",".join(chain) if chain else "anull"

    @staticmethod
    def _adaptive_audio_routing_enabled(settings: dict | None) -> bool:
        data = dict(settings or {})
        if VideoProcessorAudioHelpersMixin._settings_bool(data, "audio_chunk_routing_disabled", False):
            return False
        return VideoProcessorAudioHelpersMixin._settings_bool(data, "audio_chunk_routing_enabled", True)

    def _audio_route_sample_span(self, start: float, end: float, settings: dict | None = None) -> tuple[float, float]:
        start = max(0.0, float(start or 0.0))
        end = max(start, float(end or start))
        duration = max(0.0, end - start)
        if duration <= 0.0:
            return start, 0.0
        try:
            max_sample = float((settings or {}).get("audio_chunk_profile_sec", 30.0) or 30.0)
        except Exception:
            max_sample = 30.0
        sample_dur = min(duration, max(8.0, min(30.0, max_sample)))
        sample_start = start + max(0.0, (duration - sample_dur) / 2.0)
        return round(sample_start, 3), round(sample_dur, 3)

    def _extract_audio_route_sample(
        self,
        media_path: str,
        sample_path: str,
        *,
        start: float,
        duration: float,
        settings: dict,
    ) -> bool:
        if duration <= 0.0:
            return False
        cmd = [
            ffmpeg_binary(), "-y", "-nostdin", "-loglevel", "error",
            *self._ffmpeg_parallel_args(settings),
            "-ss", f"{max(0.0, float(start or 0.0)):.3f}",
            "-t", f"{max(0.05, float(duration or 0.05)):.3f}",
            "-i", media_path,
            *self._ffmpeg_audio_stream_args(),
            "-ac", "1", "-ar", "16000",
            "-sample_fmt", "s16",
            sample_path,
        ]
        return self._run_media_command_no_progress(cmd, label="오디오 라우팅 샘플 추출")

    def _fallback_chunk_audio_route(self, settings: dict, *, reason: str = "clip-level auto preset fallback") -> dict:
        from core.audio.audio_presets import auto_audio_settings_only

        tune = auto_audio_settings_only(settings)
        return {
            "audio_strategy": "clip_fallback",
            "audio_strategy_label": "클립 기준 유지",
            "audio_tune_reason": reason,
            "confidence": 0.5,
            "settings": tune,
            "audio_profile": {},
            "features": {},
            "candidate_scores": [],
        }

    def _classify_chunk_audio_route(
        self,
        media_path: str,
        seg: dict,
        settings: dict,
        *,
        index: int,
        tmpdir: str,
    ) -> dict:
        from core.audio.audio_presets import auto_audio_settings_only
        from core.audio.preset_auto_classifier import (
            analyze_sample_features,
            build_audio_profile,
            select_audio_candidate,
        )

        start = max(0.0, float(seg.get("start", 0.0) or 0.0))
        end = max(start, float(seg.get("end", start) or start))
        sample_start, sample_dur = self._audio_route_sample_span(start, end, settings)
        sample_path = os.path.join(tmpdir, f"route_{index:03d}_{sample_start:.3f}.wav")
        if not self._extract_audio_route_sample(
            media_path,
            sample_path,
            start=sample_start,
            duration=sample_dur,
            settings=settings,
        ):
            return self._fallback_chunk_audio_route(settings, reason="샘플 추출 실패")

        try:
            features = analyze_sample_features(sample_path)
            features.update({
                "sample_count": 1,
                "sample_duration_sec": sample_dur,
                "total_scanned_sec": sample_dur,
                "media_duration_sec": max(0.0, end - start),
            })
            profile = build_audio_profile(features)
            result = select_audio_candidate(profile, features, use_lora_prior=True)
            tune = auto_audio_settings_only(result.get("settings") or {})
            return {
                "audio_strategy": str(result.get("id") or "clean_voice"),
                "audio_strategy_label": str(result.get("label") or ""),
                "audio_tune_reason": str(result.get("reason") or ""),
                "confidence": float(result.get("score", 0.0) or 0.0),
                "settings": tune,
                "audio_profile": profile,
                "features": features,
                "candidate_scores": list(result.get("candidate_scores") or []),
                "sample_start": sample_start,
                "sample_duration": sample_dur,
            }
        except Exception as exc:
            return self._fallback_chunk_audio_route(settings, reason=f"프로파일링 실패: {exc}")

    def _route_log_line(self, idx: int, seg: dict, route: dict) -> str:
        settings = dict(route.get("settings") or {})
        profile = dict(route.get("audio_profile") or {})
        start = float(seg.get("start", 0.0) or 0.0)
        end = float(seg.get("end", start) or start)
        audio_ai = self._audio_cleanup_label(str(settings.get("selected_audio_ai", "none") or "none"), True)
        vad = str(settings.get("selected_vad", "none") or "none")
        confidence = int(round(float(route.get("confidence", 0.0) or 0.0) * 100))
        env = str(profile.get("environment") or "-")
        noise = str(profile.get("noise_level") or "-")
        return (
            f"    · 청크 {idx + 1:02d} {start:.1f}s~{end:.1f}s: "
            f"{audio_ai} / VAD {vad} / {env} / noise {noise} / confidence {confidence}%"
        )

    def _write_adaptive_chunk_from_media(
        self,
        media_path: str,
        out_path: str,
        seg: dict,
        settings: dict,
        *,
        tmpdir: str,
    ) -> bool:
        start = max(0.0, float(seg.get("start", 0.0) or 0.0))
        end = max(start, float(seg.get("end", start) or start))
        duration = max(0.001, end - start)
        audio_ai = str(settings.get("selected_audio_ai", "none") or "none").lower()
        use_basic = bool(settings.get("use_basic_filter", True))
        master_filter = self._build_ffmpeg_preprocess_filter(settings)
        active_filter = self._build_audio_cleanup_filter(audio_ai, settings)

        if self._can_fuse_ffmpeg_preprocess(audio_ai, settings):
            fused_filter = self._build_fused_ffmpeg_filter(audio_ai, settings, use_basic=use_basic)
            cmd = [
                ffmpeg_binary(), "-y", "-nostdin", "-loglevel", "error",
                *self._ffmpeg_parallel_args(settings),
                "-ss", f"{start:.3f}",
                "-t", f"{duration:.3f}",
                "-i", media_path,
                *self._ffmpeg_audio_stream_args(),
                "-ac", "1", "-ar", "16000",
                "-af", fused_filter,
                "-acodec", "pcm_s16le",
                out_path,
            ]
            return (
                self._run_media_command_no_progress(cmd, label="구간별 FFMPEG 청크 추출")
                and os.path.exists(out_path)
                and os.path.getsize(out_path) > 0
            )

        raw_wav = os.path.join(tmpdir, f"{os.path.basename(out_path)}.raw.wav")
        raw_sample_rate = self._audio_processing_sample_rate(audio_ai, settings)
        extract_cmd = [
            ffmpeg_binary(), "-y", "-nostdin", "-loglevel", "error",
            *self._ffmpeg_parallel_args(settings),
            "-ss", f"{start:.3f}",
            "-t", f"{duration:.3f}",
            "-i", media_path,
            *self._ffmpeg_audio_stream_args(),
            "-ac", "1", "-ar", str(raw_sample_rate),
        ]
        if use_basic:
            extract_cmd.extend(["-af", master_filter])
        extract_cmd.extend(["-acodec", "pcm_s16le", raw_wav])
        if not self._run_media_command_no_progress(extract_cmd, label="구간별 FFMPEG 원본 청크 추출"):
            return False

        ai_wav = raw_wav
        if audio_ai == "rnnoise":
            routed_wav = os.path.join(tmpdir, f"{os.path.basename(out_path)}.rnnoise.wav")
            if self._apply_rnnoise(raw_wav, routed_wav) and os.path.exists(routed_wav):
                ai_wav = routed_wav
        elif audio_ai == "resemble_enhance":
            routed_wav = os.path.join(tmpdir, f"{os.path.basename(out_path)}.resemble.wav")
            if self._apply_resemble_enhance(raw_wav, routed_wav) and os.path.exists(routed_wav):
                ai_wav = routed_wav
        elif audio_ai == "clearvoice":
            routed_wav = os.path.join(tmpdir, f"{os.path.basename(out_path)}.clearvoice.wav")
            prev_clearvoice_settings = getattr(self, "_clearvoice_runtime_settings", None)
            self._clearvoice_runtime_settings = dict(settings)
            try:
                if self._apply_clearvoice(raw_wav, routed_wav) and os.path.exists(routed_wav):
                    ai_wav = routed_wav
            finally:
                self._clearvoice_runtime_settings = prev_clearvoice_settings

        final_cmd = [
            ffmpeg_binary(), "-y", "-nostdin", "-loglevel", "error",
            *self._ffmpeg_parallel_args(settings),
            "-i", ai_wav,
            "-ac", "1", "-ar", "16000",
            "-af", active_filter,
            "-acodec", "pcm_s16le",
            out_path,
        ]
        return (
            self._run_media_command_no_progress(final_cmd, label="구간별 음성필터 청크 정제")
            and os.path.exists(out_path)
            and os.path.getsize(out_path) > 0
        )

    def _write_adaptive_grouped_chunks_from_media(
        self,
        media_path: str,
        chunk_dir: str,
        grouped: list[dict],
        settings: dict,
        *,
        precomputed_vad_segments: list[dict] | None = None,
    ) -> bool:
        if not grouped:
            return False
        os.makedirs(chunk_dir, exist_ok=True)
        self._notify_stage("⏳ [오디오] 청크별 오디오 프로파일링/라우팅 중")
        _runtime_get_logger().log(
            f"  🧭 [오디오 라우팅] 정확도 우선: 청크 {len(grouped)}개를 각각 분석해 FFmpeg/음성필터/VAD 후보를 결정합니다"
        )

        routes_by_index: dict[int, dict] = {}
        route_runtime: dict[int, tuple[dict, str, float]] = {}
        route_vad_segments = []
        route_vad_enabled = self._settings_bool(
            settings,
            "audio_chunk_route_vad_enabled",
            self._settings_bool(settings, "vad_post_stt_align_enabled", True),
        )
        failures = 0
        workload = len(grouped)
        max_workers, scheduler = runtime_parallel_worker_plan(
            settings=settings,
            task="io",
            requested=getattr(self, "io_workers", None),
            workload=workload,
            minimum=1,
            maximum=workload,
            reserve_task="io",
        )
        try:
            route_worker_cap = int(float(settings.get("audio_chunk_route_max_workers", 2) or 0))
        except (TypeError, ValueError):
            route_worker_cap = 2
        if route_worker_cap > 0 and max_workers > route_worker_cap:
            max_workers = max(1, min(max_workers, route_worker_cap))
            reductions_list = list(scheduler.get("reductions") or [])
            reductions_list.append("audio_route_cap")
            scheduler["reductions"] = reductions_list
            scheduler["audio_chunk_route_max_workers"] = int(route_worker_cap)
        reductions = ",".join(scheduler.get("reductions") or [])
        if max_workers > 1:
            suffix = f" ({reductions})" if reductions else ""
            _runtime_get_logger().log(f"  🧵 [오디오 라우팅] 청크 라우팅 병렬 워커 {max_workers}개{suffix}")

        progress_lock = threading.Lock()
        done_count = 0
        next_log_pct = 0

        def _mark_progress():
            nonlocal done_count, next_log_pct
            with progress_lock:
                done_count += 1
                pct = min(100, int(round((done_count / len(grouped)) * 100)))
                if pct >= next_log_pct or done_count == len(grouped):
                    next_log_pct = min(100, pct + 10)
                    self._notify_stage(f"⏳ [오디오] 청크별 오디오 라우팅 중 {pct}%")
                    _runtime_get_logger().log(
                        f"  └ [오디오 라우팅] 청크 처리 진행률 {pct}% ({done_count}/{len(grouped)})"
                    )

        def _process_one(idx_seg):
            idx, seg = idx_seg
            start = max(0.0, float(seg.get("start", 0.0) or 0.0))
            out = os.path.join(chunk_dir, f"vad_{idx:03d}_{start:.3f}.wav")
            route = self._classify_chunk_audio_route(media_path, seg, settings, index=idx, tmpdir=tmpdir)
            chunk_settings = dict(settings)
            chunk_settings.update(dict(route.get("settings") or {}))
            ok = self._write_adaptive_chunk_from_media(media_path, out, seg, chunk_settings, tmpdir=tmpdir)
            route_meta = {
                "index": idx,
                "start": round(float(seg.get("start", 0.0) or 0.0), 3),
                "end": round(float(seg.get("end", 0.0) or 0.0), 3),
                "path": out,
                "ok": bool(ok),
                "audio_strategy": route.get("audio_strategy"),
                "audio_strategy_label": route.get("audio_strategy_label"),
                "audio_tune_reason": route.get("audio_tune_reason"),
                "confidence": route.get("confidence"),
                "audio_profile": route.get("audio_profile"),
                "audio_tune_settings": dict(route.get("settings") or {}),
            }
            return idx, route_meta, route, chunk_settings, out, start, bool(ok)

        def _store_result(result):
            nonlocal failures
            idx, route_meta, route, chunk_settings, out, start, ok = result
            routes_by_index[idx] = route_meta
            if ok:
                route_runtime[idx] = (chunk_settings, out, start)
            else:
                failures += 1
                _runtime_get_logger().log(f"  ⚠️ [오디오 라우팅] 청크 {idx + 1} 생성 실패")
            return idx, route

        with tempfile.TemporaryDirectory(prefix="audio_chunk_route_") as tmpdir:
            route_logs: dict[int, dict] = {}
            if max_workers <= 1:
                for item in enumerate(grouped):
                    idx, route = _store_result(_process_one(item))
                    route_logs[idx] = route
                    _mark_progress()
            else:
                with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="audio-route") as executor:
                    futures = [executor.submit(_process_one, item) for item in enumerate(grouped)]
                    for future in futures:
                        try:
                            idx, route = _store_result(future.result())
                            route_logs[idx] = route
                        except Exception as exc:
                            failures += 1
                            _runtime_get_logger().log(f"  ⚠️ [오디오 라우팅] 청크 처리 실패: {exc}")
                        finally:
                            _mark_progress()

            for idx in sorted(route_logs):
                _runtime_get_logger().log(self._route_log_line(idx, grouped[idx], route_logs[idx]))

            reuse_precomputed_vad = route_vad_enabled and bool(precomputed_vad_segments)
            if reuse_precomputed_vad:
                route_vad_segments = [
                    dict(row)
                    for row in list(precomputed_vad_segments or [])
                    if isinstance(row, dict)
                ]
                for idx, seg in enumerate(grouped):
                    start = max(0.0, float(seg.get("start", 0.0) or 0.0))
                    end = max(start, float(seg.get("end", start) or start))
                    vad_count = sum(
                        1
                        for row in route_vad_segments
                        if self._vad_segment_intersects_range(row, start, end)
                    )
                    if idx in routes_by_index:
                        routes_by_index[idx]["vad_segments"] = vad_count
            elif route_vad_enabled:
                for idx in sorted(route_runtime):
                    chunk_settings, out, start = route_runtime[idx]
                    vad_model = str(chunk_settings.get("selected_vad", "none") or "none").lower()
                    if vad_model == "none":
                        continue
                    try:
                        chunk_vad = self._detect_vad_timestamps(
                            out,
                            vad_model,
                            chunk_settings,
                            target_start_sec=0.0,
                            target_end_sec=None,
                            is_single_segment=False,
                            for_post_stt_align=True,
                        )
                    except Exception:
                        chunk_vad = []
                    offset_vad = []
                    for row in chunk_vad or []:
                        try:
                            item = dict(row)
                            item["start"] = round(start + float(item.get("start", 0.0) or 0.0), 3)
                            item["end"] = round(start + float(item.get("end", 0.0) or 0.0), 3)
                            item["source"] = f"chunk_{vad_model}"
                            item["post_stt_align"] = True
                            item["vad_word_filter"] = bool(item.get("vad_word_filter", True))
                            offset_vad.append(item)
                        except Exception:
                            continue
                    if offset_vad:
                        route_vad_segments.extend(offset_vad)
                    if idx in routes_by_index:
                        routes_by_index[idx]["vad_segments"] = len(offset_vad)

        routes = [routes_by_index[idx] for idx in sorted(routes_by_index)]

        try:
            with open(os.path.join(chunk_dir, "audio_routes.json"), "w", encoding="utf-8") as f:
                json.dump(routes, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        if route_vad_segments:
            try:
                route_vad_segments.sort(key=lambda row: (float(row.get("start", 0.0) or 0.0), float(row.get("end", 0.0) or 0.0)))
                with open(os.path.join(chunk_dir, "vad_strict.json"), "w", encoding="utf-8") as f:
                    json.dump(route_vad_segments, f, ensure_ascii=False, indent=2)
                _runtime_get_logger().log(f"  ✅ [오디오 라우팅] 청크별 VAD 후처리 구간 {len(route_vad_segments)}개 생성")
            except Exception:
                pass

        if failures:
            _runtime_get_logger().log(f"  ⚠️ [오디오 라우팅] 실패 {failures}개: 기존 청크 생성 경로로 재시도합니다")
            return False
        _runtime_get_logger().log(f"  ✅ [오디오 라우팅] 청크별 오디오 라우팅 완료 ({len(grouped)}개)")
        return True

    def _grouped_chunks_from_existing_wavs(self, chunk_dir: str) -> list[dict]:
        grouped = []
        try:
            names = sorted(name for name in os.listdir(chunk_dir) if name.lower().endswith(".wav"))
        except Exception:
            return grouped
        for name in names:
            path = os.path.join(chunk_dir, name)
            match = re.search(r"vad_\d+_([\d.]+)\.wav$", name)
            if not match:
                continue
            try:
                start = float(match.group(1))
                with wave.open(path, "r") as wf:
                    duration = wf.getnframes() / float(wf.getframerate())
            except Exception:
                continue
            if duration <= 0:
                continue
            grouped.append({"start": round(start, 3), "end": round(start + duration, 3)})
        return grouped

    def _audio_cache_config(
        self,
        video_path: str,
        settings: dict,
        *,
        audio_ai: str,
        use_basic: bool,
        master_filter: str,
        active_filter: str,
    ) -> dict:
        try:
            source = os.path.abspath(video_path)
            stat = os.stat(video_path)
            source_size = int(stat.st_size)
            source_mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)))
            source_fingerprint = media_file_fingerprint(video_path, sample_bytes=512 * 1024, include_samples=True)
            source_fingerprint_digest = media_fingerprint_digest(video_path, sample_bytes=512 * 1024, include_samples=True)
        except Exception:
            source = os.path.abspath(video_path or "")
            source_size = 0
            source_mtime_ns = 0
            source_fingerprint = source
            source_fingerprint_digest = ""
        return {
            "version": _AUDIO_CACHE_VERSION,
            "source": source,
            "source_size": source_size,
            "source_mtime_ns": source_mtime_ns,
            "source_fingerprint": source_fingerprint,
            "source_fingerprint_digest": source_fingerprint_digest,
            "audio_ai": str(audio_ai or "none"),
            "audio_ai_variant": self._audio_ai_variant(audio_ai, settings),
            "use_basic_filter": bool(use_basic),
            "master_filter": str(master_filter or "anull"),
            "active_filter": str(active_filter or "anull"),
            "sample_rate": 16000,
            "processing_sample_rate": self._audio_processing_sample_rate(audio_ai, settings),
            "channels": 1,
            "pcm": "s16le",
            "ffmpeg_filter_threads": int(max(1, bounded_worker_count(settings.get("ffmpeg_filter_threads", self.io_workers), kind="cpu"))),
            "audio_preprocess_audio_overlap_enabled": self._settings_bool(settings, "audio_preprocess_audio_overlap_enabled", True),
            "audio_preprocess_audio_overlap_chunk_sec": self._float_setting(
                settings,
                "audio_preprocess_audio_overlap_chunk_sec",
                120.0,
                30.0,
                600.0,
            ),
            "audio_preprocess_audio_overlap_workers": str(settings.get("audio_preprocess_audio_overlap_workers", "auto") or "auto"),
            "clearvoice_parallel_chunks_enabled": self._settings_bool(settings, "clearvoice_parallel_chunks_enabled", False),
            "clearvoice_native_ffmpeg_enabled": self._clearvoice_native_ffmpeg_enabled(settings),
            "macos_native_fast_audio_flatten_enabled": self._macos_native_fast_audio_flatten_enabled(settings),
        }

    def _direct_chunk_span(self, video_path: str, target_start_sec=0.0, target_end_sec=None) -> tuple[float, float]:
        total_dur = self._media_duration_for_progress(video_path)
        start = max(0.0, float(target_start_sec or 0.0))
        if target_end_sec is None:
            end = float(total_dur or 0.0)
        else:
            end = max(start, float(target_end_sec or start))
            if total_dur > 0:
                end = min(end, total_dur)
        return start, max(start, end)

    def _hard_cut_boundaries_for_span(self, start: float, end: float) -> tuple[float, ...]:
        """Return hard cut times inside the requested STT span.

        hard_cut_boundaries is injected by the pipeline before audio extraction.
        These boundaries are absolute/local seconds for the current media file.
        STT wav chunks must never cross these cuts.
        """
        try:
            start = float(start or 0.0)
            end = float(end or 0.0)
        except Exception:
            return ()

        cuts = []
        for item in list(getattr(self, "hard_cut_boundaries", []) or []):
            try:
                if isinstance(item, dict):
                    sec = float(item.get("timeline_sec", item.get("time", item.get("start", 0.0))) or 0.0)
                else:
                    sec = float(item)
            except Exception:
                continue

            if start < sec < end:
                cuts.append(round(sec, 3))

        return tuple(sorted(set(cuts)))

    def _chunk_item_span(self, item):
        """Best-effort grouped chunk span reader.

        Supports dict chunks and tuple/list chunks. This is intentionally
        defensive because grouped chunk formats differ between direct ffmpeg,
        VAD, and force split paths.
        """
        if isinstance(item, dict):
            for sk, ek in (("start", "end"), ("start_sec", "end_sec"), ("s", "e")):
                if sk in item and ek in item:
                    try:
                        return float(item[sk]), float(item[ek]), sk, ek, None
                    except Exception:
                        pass
            if "offset" in item and "duration" in item:
                try:
                    s = float(item["offset"])
                    return s, s + float(item["duration"]), "offset", "duration", "duration"
                except Exception:
                    pass

        if isinstance(item, (list, tuple)):
            numeric = []
            for idx, val in enumerate(item):
                try:
                    numeric.append((idx, float(val)))
                except Exception:
                    continue

            # Common forms: (start, end), (idx, start, end), (path, start, end)
            for a, b in ((0, 1), (1, 2)):
                if len(item) > b:
                    try:
                        s = float(item[a])
                        e = float(item[b])
                        if e > s:
                            return s, e, a, b, None
                    except Exception:
                        pass

            if len(numeric) >= 2:
                a, s = numeric[0]
                b, e = numeric[1]
                if e > s:
                    return s, e, a, b, None

        return None

    def _replace_chunk_item_span(self, item, start: float, end: float, sk, ek, mode):
        if isinstance(item, dict):
            row = dict(item)
            if mode == "duration":
                row[sk] = round(start, 3)
                row[ek] = round(max(0.0, end - start), 3)
            else:
                row[sk] = round(start, 3)
                row[ek] = round(end, 3)
            return row

        if isinstance(item, tuple):
            row = list(item)
            row[sk] = round(start, 3)
            row[ek] = round(end, 3)
            return tuple(row)

        if isinstance(item, list):
            row = list(item)
            row[sk] = round(start, 3)
            row[ek] = round(end, 3)
            return row

        return item

    def _split_grouped_chunks_at_hard_cuts(self, grouped, span_start: float | None = None, span_end: float | None = None):
        """Split STT wav extraction chunks at hard visual cuts.

        This is the STT-input-level hard boundary enforcement.
        Final subtitle splitting remains as a second safety layer.
        """
        items = list(grouped or [])
        if not items:
            return grouped

        detected_spans = []
        for item in items:
            span = self._chunk_item_span(item)
            if span is not None:
                detected_spans.append(span)

        if not detected_spans:
            return grouped

        if span_start is None:
            span_start = min(s for s, _, _, _, _ in detected_spans)
        if span_end is None:
            span_end = max(e for _, e, _, _, _ in detected_spans)

        hard_cuts = self._hard_cut_boundaries_for_span(float(span_start), float(span_end))
        if not hard_cuts:
            return grouped

        out = []
        changed = False

        for item in items:
            span = self._chunk_item_span(item)
            if span is None:
                out.append(item)
                continue

            start, end, sk, ek, mode = span
            inner = [c for c in hard_cuts if start < c < end]
            if not inner:
                out.append(item)
                continue

            points = [start] + inner + [end]
            for idx in range(len(points) - 1):
                a = points[idx]
                b = points[idx + 1]
                if b <= a or (b - a) < 0.05:
                    continue
                out.append(self._replace_chunk_item_span(item, a, b, sk, ek, mode))
            changed = True

        if changed:
            try:
                _runtime_get_logger().log(
                    f"  ✂️ [컷 경계] STT 오디오 청크 {len(items)}개 → {len(out)}개 hard split "
                    f"(경계 {len(hard_cuts)}개)"
                )
            except Exception:
                pass

        return out


    def _can_direct_extract_stt_chunks(
        self,
        settings: dict,
        *,
        audio_ai: str,
        vad_model: str,
        vad_pre_split_enabled: bool,
        vad_post_align_enabled: bool,
        span_sec: float,
        is_partial: bool,
    ) -> bool:
        if not bool(settings.get("direct_ffmpeg_chunk_extract", True)):
            return False
        if not self._can_fuse_ffmpeg_preprocess(audio_ai, settings):
            return False
        if vad_pre_split_enabled:
            return False
        if str(vad_model or "none").lower() != "none" and vad_post_align_enabled:
            return False
        try:
            if int(settings.get("max_speakers", 1) or 1) > 1:
                return False
        except Exception:
            return False
        if span_sec <= 0:
            return False
        min_sec = float(settings.get("direct_ffmpeg_chunk_min_sec", 60.0) or 0.0)
        return bool(is_partial or span_sec >= max(0.0, min_sec))

    def _cleaned_audio_cache_valid(self, cleaned_wav: str, meta_path: str, cache_config: dict) -> bool:
        if not os.path.exists(cleaned_wav) or os.path.getsize(cleaned_wav) <= 1024 * 100:
            return False
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            return False
        return payload == cache_config

    def _write_cleaned_audio_cache_meta(self, meta_path: str, cache_config: dict) -> None:
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(cache_config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _vad_detection_cache_enabled(self, settings: dict) -> bool:
        value = dict(settings or {}).get("vad_detection_cache_enabled", dict(settings or {}).get("autopilot_stage_cache_enabled", True))
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "off", "no", "사용 안함", "끔"}
        return bool(value)

    def _vad_timestamps_cache_identity(
        self,
        wav_path: str,
        vad_model: str,
        settings: dict,
        *,
        target_start_sec=0.0,
        target_end_sec=None,
        is_single_segment=False,
        for_post_stt_align: bool = False,
    ) -> dict:
        try:
            source = os.path.abspath(str(wav_path or ""))
            stat = os.stat(source)
            source_size = int(stat.st_size)
            source_mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)))
            source_fingerprint = media_file_fingerprint(source, sample_bytes=512 * 1024, include_samples=True)
            source_digest = media_fingerprint_digest(source, sample_bytes=512 * 1024, include_samples=True)
        except Exception:
            source = os.path.abspath(str(wav_path or ""))
            source_size = 0
            source_mtime_ns = 0
            source_fingerprint = source
            source_digest = hashlib.sha1(source.encode("utf-8", errors="ignore")).hexdigest()
        return {
            "version": _VAD_CACHE_VERSION + 1,
            "source": source,
            "source_size": source_size,
            "source_mtime_ns": source_mtime_ns,
            "source_fingerprint": source_fingerprint,
            "source_fingerprint_digest": source_digest,
            "vad_model": str(vad_model or "none").lower(),
            "vad_cache_config": self._vad_cache_config(settings),
            "target_start_sec": round(float(target_start_sec or 0.0), 3),
            "target_end_sec": None if target_end_sec is None else round(float(target_end_sec or 0.0), 3),
            "is_single_segment": bool(is_single_segment),
            "for_post_stt_align": bool(for_post_stt_align),
            "sample_rate": 16000,
        }

    def _vad_timestamps_cache_path(self, identity: dict) -> str:
        cache_root = os.path.join(config.OUTPUT_DIR, "_analysis_cache", "vad")
        os.makedirs(cache_root, exist_ok=True)
        raw = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        key = hashlib.sha256(raw).hexdigest()[:32]
        return os.path.join(cache_root, f"vad_timestamps_{key}.json")

    def _load_vad_timestamps_cache(
        self,
        wav_path: str,
        vad_model: str,
        settings: dict,
        *,
        target_start_sec=0.0,
        target_end_sec=None,
        is_single_segment=False,
        for_post_stt_align: bool = False,
    ) -> list[dict] | None:
        if not self._vad_detection_cache_enabled(settings):
            return None
        identity = self._vad_timestamps_cache_identity(
            wav_path,
            vad_model,
            settings,
            target_start_sec=target_start_sec,
            target_end_sec=target_end_sec,
            is_single_segment=is_single_segment,
            for_post_stt_align=for_post_stt_align,
        )
        cache_path = self._vad_timestamps_cache_path(identity)
        if not os.path.exists(cache_path):
            return None
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if dict(payload.get("identity") or {}) != identity:
                return None
            rows = [dict(row) for row in list(payload.get("timestamps") or []) if isinstance(row, dict)]
            return rows
        except Exception:
            return None

    def _write_vad_timestamps_cache(
        self,
        wav_path: str,
        vad_model: str,
        settings: dict,
        timestamps: list[dict],
        *,
        target_start_sec=0.0,
        target_end_sec=None,
        is_single_segment=False,
        for_post_stt_align: bool = False,
    ) -> None:
        if not self._vad_detection_cache_enabled(settings):
            return
        try:
            identity = self._vad_timestamps_cache_identity(
                wav_path,
                vad_model,
                settings,
                target_start_sec=target_start_sec,
                target_end_sec=target_end_sec,
                is_single_segment=is_single_segment,
                for_post_stt_align=for_post_stt_align,
            )
            cache_path = self._vad_timestamps_cache_path(identity)
            payload = {
                "schema": "ai_subtitle_studio.vad_timestamps_cache.v1",
                "created_at": time.time(),
                "identity": identity,
                "timestamps": [dict(row) for row in list(timestamps or []) if isinstance(row, dict)],
            }
            tmp_path = f"{cache_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, cache_path)
        except Exception:
            pass

    def _vad_cache_config(self, settings: dict) -> dict:
        effective_s = apply_review_vad_settings(settings)
        return {
            "version": _VAD_CACHE_VERSION,
            "review_vad_config": review_vad_config(settings),
            "vad_threshold": float(effective_s.get("vad_threshold", 0.5)),
            "vad_min_speech": float(effective_s.get("vad_min_speech", 0.25)),
            "vad_min_silence": float(effective_s.get("vad_min_silence", 2.0)),
            "vad_speech_pad": float(effective_s.get("vad_speech_pad", 0.2)),
            "vad_window_size": int(effective_s.get("vad_window_size", 512) or 512),
        }

    # 💡 파라미터에 target_start_sec와 target_end_sec 추가
    # 💡 1. 메인 파이프라인 (불필요한 중복 로직 싹 걷어내고 아주 깔끔해졌습니다)
    # 💡 [STEP 1] 메인 파이프라인 (is_single_segment 파라미터 추가)
