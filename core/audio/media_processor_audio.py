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
from copy import deepcopy

from core.audio.runtime_cleanup import clear_audio_model_memory_caches
from core.audio.audio_runtime_services import plan_audio_route_workers
from core.llm.secure_keys import get_api_key
from core.media_fingerprint import media_fingerprint_snapshot
from core.media_info import probe_media
from core.performance import (
    bounded_worker_count,
)
from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs, rnnoise_binary, subprocess_env
from core.runtime import config
from core.runtime.logger import get_logger
from core.runtime.subprocess_utils import run_subprocess_capture
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
            result = run_subprocess_capture(
                cmd,
                timeout=timeout,
                env=env,
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
            result = run_subprocess_capture(
                cmd,
                timeout=timeout,
                env=env,
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
        if VideoProcessorAudioHelpersMixin._settings_bool(data, "audio_chunk_routing_benchmark_locked", False):
            return False
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

    @staticmethod
    def _audio_route_int_setting(settings: dict | None, key: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(float(dict(settings or {}).get(key, default)))
        except Exception:
            value = int(default)
        return max(int(minimum), min(int(maximum), value))

    def _audio_route_profile_sample_count(self, settings: dict | None = None) -> int:
        return self._audio_route_int_setting(settings, "audio_chunk_route_profile_samples", 3, 1, 5)

    def _audio_route_profile_window_sec(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_profile_window_sec", 8.0, 2.0, 20.0)

    def _audio_route_candidate_limit(self, settings: dict | None = None) -> int:
        return self._audio_route_int_setting(settings, "audio_chunk_route_candidate_limit", 3, 1, 4)

    def _audio_route_preview_enabled(self, settings: dict | None = None) -> bool:
        return self._settings_bool(settings, "audio_chunk_route_preview_enabled", True)

    def _audio_route_preview_min_confidence(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_preview_min_confidence", 0.76, 0.0, 1.0)

    def _audio_route_preview_gap_max(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_preview_gap_max", 0.08, 0.0, 0.5)

    def _audio_route_hysteresis_margin(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_hysteresis_margin", 0.05, 0.0, 0.5)

    def _audio_route_profile_memory_enabled(self, settings: dict | None = None) -> bool:
        return self._settings_bool(settings, "audio_chunk_route_profile_memory_enabled", True)

    def _audio_route_profile_memory_margin(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_profile_memory_margin", 0.04, 0.0, 0.5)

    def _audio_route_profile_memory_min_confidence(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_profile_memory_min_confidence", 0.64, 0.0, 1.0)

    def _audio_route_switch_confirmation_enabled(self, settings: dict | None = None) -> bool:
        return self._settings_bool(settings, "audio_chunk_route_switch_confirmation_enabled", True)

    def _audio_route_switch_confirmation_margin(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_switch_confirmation_margin", 0.04, 0.0, 0.5)

    def _audio_route_switch_confirmation_strong_margin(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_switch_confirmation_strong_margin", 0.11, 0.0, 0.5)

    def _audio_route_switch_confirmation_min_streak(self, settings: dict | None = None) -> int:
        return self._audio_route_int_setting(settings, "audio_chunk_route_switch_confirmation_min_streak", 2, 1, 4)

    def _audio_route_precision_threshold(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_precision_threshold", 0.74, 0.0, 1.0)

    def _audio_route_secondary_recheck_threshold(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_secondary_recheck_threshold", 0.68, 0.0, 1.0)

    def _audio_route_low_confidence_threshold(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_low_confidence_threshold", 0.58, 0.0, 1.0)

    def _audio_route_baseline_guard_enabled(self, settings: dict | None = None) -> bool:
        return self._settings_bool(settings, "audio_chunk_route_baseline_guard_enabled", True)

    def _audio_route_baseline_margin(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_baseline_margin", 0.04, 0.0, 0.5)

    def _audio_route_baseline_non_none_extra_margin(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_baseline_non_none_extra_margin", 0.03, 0.0, 0.5)

    def _audio_route_baseline_noisy_voice_extra_margin(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_baseline_noisy_voice_extra_margin", 0.05, 0.0, 0.5)

    @staticmethod
    def _audio_route_is_specialist_strategy(strategy: str | None) -> bool:
        return str(strategy or "").strip().lower() in {"noisy_voice", "low_rumble", "fast_noise_gate"}

    @staticmethod
    def _audio_route_is_challenging_profile(profile: dict | None) -> bool:
        data = dict(profile or {})
        noise = str(data.get("noise_level") or "low").strip().lower()
        environment = str(data.get("environment") or "").strip().lower()
        clean_dialog = bool(data.get("clean_dialog"))
        roomy_dialog = bool(data.get("roomy_dialog"))
        driving_noise = bool(data.get("driving_noise"))
        volatile_scene = bool(data.get("volatile_scene"))
        mic_present = bool(data.get("mic_present", True))
        if driving_noise or roomy_dialog:
            return True
        if noise == "high":
            return True
        if noise == "medium" and not clean_dialog and (volatile_scene or not mic_present or environment == "outdoor"):
            return True
        return bool(volatile_scene and not clean_dialog)

    def _audio_route_split_enabled(self, settings: dict | None = None) -> bool:
        return self._settings_bool(settings, "audio_chunk_route_split_enabled", False)

    def _audio_route_max_span_sec(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_max_span_sec", 0.0, 0.0, 240.0)

    def _audio_route_split_confidence_threshold(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_split_confidence_threshold", 0.8, 0.0, 1.0)

    def _audio_route_split_candidate_gap_max(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_split_candidate_gap_max", 0.06, 0.0, 0.5)

    def _audio_route_split_preview_divergence_min(self, settings: dict | None = None) -> float:
        return self._float_setting(settings, "audio_chunk_route_split_preview_divergence_min", 0.08, 0.0, 0.5)

    @staticmethod
    def _audio_route_score_gap(rows: list[dict] | None) -> float:
        scores = []
        for row in list(rows or []):
            try:
                scores.append(float(row.get("score", 0.0) or 0.0))
            except Exception:
                continue
        if not scores:
            return 0.0
        scores.sort(reverse=True)
        if len(scores) == 1:
            return max(0.0, scores[0])
        return max(0.0, scores[0] - scores[1])

    def _audio_route_preview_divergence(self, route: dict) -> float:
        feature_conf = None
        self_score = None
        try:
            feature_conf = float(route.get("feature_confidence", 0.0) or 0.0)
        except Exception:
            feature_conf = None
        try:
            self_score = float(route.get("self_score", 0.0) or 0.0)
        except Exception:
            self_score = None
        if feature_conf is not None and self_score is not None:
            return abs(self_score - feature_conf)
        preview_gap = self._audio_route_score_gap(route.get("preview_scores"))
        feature_gap = self._audio_route_score_gap(route.get("candidate_scores"))
        return abs(preview_gap - feature_gap)

    def _maybe_expand_grouped_chunks_for_audio_route(self, grouped: list[dict], settings: dict | None = None) -> list[dict]:
        items = [dict(item) for item in list(grouped or []) if isinstance(item, dict)]
        if not items or not self._audio_route_split_enabled(settings):
            return items
        max_span = self._audio_route_max_span_sec(settings)
        if max_span <= 0.0:
            return items

        overlap_sec = max(0.0, min(self._chunk_overlap_sec(settings), max_span / 2.0))
        expanded: list[dict] = []
        changed = False
        for item in items:
            start = max(0.0, float(item.get("start", 0.0) or 0.0))
            end = max(start, float(item.get("end", start) or start))
            if end - start <= max_span + 0.001:
                expanded.append({"start": round(start, 3), "end": round(end, 3)})
                continue
            sub_ranges = self._split_range_with_overlap(start, end, max_span, overlap_sec)
            if len(sub_ranges) > 1:
                changed = True
                expanded.extend(sub_ranges)
            else:
                expanded.append({"start": round(start, 3), "end": round(end, 3)})

        if changed:
            try:
                _runtime_get_logger().log(
                    f"  ✂️ [오디오 라우팅] adaptive route 청크 {len(items)}개 → {len(expanded)}개 세분화 "
                    f"(max {max_span:.1f}s, overlap {overlap_sec:.1f}s)"
                )
            except Exception:
                pass
        return expanded

    def _should_split_audio_route_segment(self, seg: dict, route: dict, settings: dict | None = None) -> bool:
        if not self._audio_route_split_enabled(settings):
            return False
        start = max(0.0, float(seg.get("start", 0.0) or 0.0))
        end = max(start, float(seg.get("end", start) or start))
        duration = end - start
        max_span = self._audio_route_max_span_sec(settings)
        if max_span <= 0.0 or duration <= max_span + 0.001:
            return False

        profile = dict(route.get("audio_profile") or {})
        strategy = str(route.get("audio_strategy") or "").strip().lower()
        score = self._route_effective_score(route)
        threshold = self._audio_route_split_confidence_threshold(settings)
        challenging = self._audio_route_is_challenging_profile(profile)
        specialist = self._audio_route_is_specialist_strategy(strategy)
        volatile = bool(profile.get("volatile_scene"))
        noise = str(profile.get("noise_level") or "low").strip().lower()
        fallback_like = strategy in {"benchmark_locked_baseline", "clip_fallback"}
        candidate_gap = self._audio_route_score_gap(route.get("candidate_scores"))
        preview_gap = self._audio_route_score_gap(route.get("preview_scores"))
        gap_limit = self._audio_route_split_candidate_gap_max(settings)
        preview_divergence = self._audio_route_preview_divergence(route)
        preview_switch = bool(route.get("preview_route_switched"))
        baseline_guard = bool(route.get("baseline_guard_applied"))
        low_confidence = score < threshold

        # Split only when the long chunk is both difficult and route selection
        # looks ambiguous enough that a finer-grained probe may legitimately win.
        if fallback_like and challenging and (low_confidence or candidate_gap <= gap_limit + 0.03):
            return True
        if baseline_guard and (
            preview_switch
            or preview_divergence >= self._audio_route_split_preview_divergence_min(settings)
            or candidate_gap <= gap_limit + 0.02
        ):
            return True
        if preview_switch and preview_divergence >= self._audio_route_split_preview_divergence_min(settings):
            return True
        if challenging and volatile and low_confidence and (
            candidate_gap <= gap_limit or preview_gap <= gap_limit
        ):
            return True
        if specialist and volatile and low_confidence and preview_divergence >= max(0.04, gap_limit):
            return True
        if noise == "high" and volatile and low_confidence and candidate_gap <= gap_limit:
            return True
        return False

    def _selective_expand_grouped_chunks_for_audio_route(
        self,
        grouped: list[dict],
        route_logs: dict[int, dict],
        settings: dict | None = None,
    ) -> list[dict]:
        items = [dict(item) for item in list(grouped or []) if isinstance(item, dict)]
        if not items or not route_logs or not self._audio_route_split_enabled(settings):
            return items

        max_span = self._audio_route_max_span_sec(settings)
        if max_span <= 0.0:
            return items

        overlap_sec = max(0.0, min(self._chunk_overlap_sec(settings), max_span / 2.0))
        expanded: list[dict] = []
        changed = False
        split_count = 0
        for idx, item in enumerate(items):
            route = dict(route_logs.get(idx) or {})
            start = max(0.0, float(item.get("start", 0.0) or 0.0))
            end = max(start, float(item.get("end", start) or start))
            if not self._should_split_audio_route_segment(item, route, settings):
                expanded.append({"start": round(start, 3), "end": round(end, 3)})
                continue
            sub_ranges = self._split_range_with_overlap(start, end, max_span, overlap_sec)
            if len(sub_ranges) > 1:
                changed = True
                split_count += 1
                expanded.extend(sub_ranges)
            else:
                expanded.append({"start": round(start, 3), "end": round(end, 3)})

        if changed:
            try:
                _runtime_get_logger().log(
                    f"  ✂️ [오디오 라우팅] 변화 큰 청크 {split_count}개만 {len(items)}→{len(expanded)} 세분화 "
                    f"(max {max_span:.1f}s, overlap {overlap_sec:.1f}s)"
                )
            except Exception:
                pass
        return expanded

    @staticmethod
    def _audio_route_settings_signature(settings: dict | None = None) -> tuple:
        data = dict(settings or {})

        def _norm(key: str, default: str = "") -> str:
            return str(data.get(key, default) or default).strip().lower()

        def _flt(key: str) -> float | None:
            try:
                return round(float(data.get(key)), 4)
            except Exception:
                return None

        return (
            _norm("selected_audio_ai", "none"),
            _norm("selected_vad", "none"),
            VideoProcessorAudioHelpersMixin._settings_bool(data, "use_basic_filter", True),
            _flt("ff_hp"),
            _flt("ff_lp"),
            _flt("ff_nf"),
            _flt("ff_dynaudnorm_m"),
            _flt("ff_dynaudnorm_p"),
            _flt("ff_treble_boost"),
            _flt("vad_threshold"),
            _flt("ten_vad_threshold"),
        )

    def _audio_route_candidate_row_for_settings(
        self,
        candidate_scores: list[dict],
        route_settings: dict,
        *,
        fallback_id: str,
        fallback_label: str,
        fallback_score: float,
    ) -> dict:
        from core.audio.preset_auto_classifier import candidate_settings_for_id

        target_signature = self._audio_route_settings_signature(route_settings)
        for row in list(candidate_scores or []):
            candidate_id = str(row.get("id") or "")
            candidate_signature = self._audio_route_settings_signature(candidate_settings_for_id(candidate_id))
            if candidate_signature == target_signature:
                matched = dict(row)
                matched["signature"] = target_signature
                return matched
        return {
            "id": fallback_id,
            "label": fallback_label,
            "score": round(float(fallback_score or 0.0), 4),
            "signature": target_signature,
        }

    def _audio_route_baseline_settings(self, settings: dict | None = None) -> dict:
        from core.audio.audio_presets import auto_audio_settings_only

        data = dict(settings or {})
        baseline = auto_audio_settings_only(data)
        for key in (
            "selected_vad",
            "vad_threshold",
            "ten_vad_threshold",
            "vad_min_speech",
            "vad_min_silence",
            "vad_speech_pad",
            "vad_window_size",
            "vad_post_stt_align_enabled",
        ):
            if key in data:
                baseline[key] = deepcopy(data[key])
        return baseline

    def _score_audio_route_preview_candidate(
        self,
        *,
        candidate_row: dict,
        candidate_settings: dict,
        raw_features: dict,
        raw_profile: dict,
        preview_features: dict,
        preview_profile: dict,
    ) -> tuple[float, dict]:
        base = max(0.0, min(1.0, float(candidate_row.get("score", 0.0) or 0.0)))
        raw_speech = max(0.0, min(1.0, float(raw_profile.get("speech_confidence", 0.0) or 0.0)))
        speech = max(0.0, min(1.0, float(preview_profile.get("speech_confidence", 0.0) or 0.0)))
        speech_drop = max(0.0, raw_speech - speech)
        raw_noise = float(raw_features.get("high_band_ratio", 0.0) or 0.0) + max(
            0.0, float(raw_features.get("low_band_ratio", 0.0) or 0.0) - 0.45
        )
        preview_noise = float(preview_features.get("high_band_ratio", 0.0) or 0.0) + max(
            0.0, float(preview_features.get("low_band_ratio", 0.0) or 0.0) - 0.45
        )
        noise_gain = max(-0.3, min(0.3, raw_noise - preview_noise))
        silence_drift = abs(
            float(preview_features.get("silence_ratio", 0.0) or 0.0)
            - float(raw_features.get("silence_ratio", 0.0) or 0.0)
        )
        rms_drift = abs(
            float(preview_features.get("rms_mean", 0.0) or 0.0)
            - float(raw_features.get("rms_mean", 0.0) or 0.0)
        )
        stability = max(0.0, min(1.0, 1.0 - (silence_drift * 1.4) - (rms_drift * 8.0)))
        vad = str(candidate_settings.get("selected_vad", "none") or "none").strip().lower()
        noise_level = str(raw_profile.get("noise_level") or "low").strip().lower()
        volatile = bool(raw_profile.get("volatile_scene"))
        vad_bonus = 0.0
        if vad == "ten_vad" and noise_level == "high":
            vad_bonus += 0.04
        elif vad == "silero" and noise_level == "low":
            vad_bonus += 0.02
        if volatile and str(candidate_settings.get("selected_audio_ai", "none") or "none").strip().lower() != "none":
            vad_bonus += 0.02
        preview_quiet = bool(preview_profile.get("quiet"))
        quiet_penalty = 0.0
        if preview_quiet and not bool(raw_profile.get("quiet")):
            quiet_penalty += 0.06
        if speech_drop >= 0.16 and str(candidate_settings.get("selected_audio_ai", "none") or "none").strip().lower() != "none":
            quiet_penalty += 0.04
        speech_penalty = min(0.22, speech_drop * 0.42)

        total = (
            (base * 0.34)
            + (speech * 0.30)
            + ((0.5 + noise_gain) * 0.16)
            + (stability * 0.20)
            + vad_bonus
            - speech_penalty
            - quiet_penalty
        )
        total = max(0.0, min(0.99, total))
        details = {
            "base_score": round(base, 4),
            "raw_speech_score": round(raw_speech, 4),
            "speech_score": round(speech, 4),
            "speech_drop": round(speech_drop, 4),
            "noise_gain": round(noise_gain, 4),
            "stability_score": round(stability, 4),
            "vad_bonus": round(vad_bonus, 4),
            "speech_penalty": round(speech_penalty, 4),
            "quiet_penalty": round(quiet_penalty, 4),
            "preview_quiet": preview_quiet,
            "volatile_scene": volatile,
        }
        return total, details

    def _write_adaptive_preview_sample(
        self,
        sample_path: str,
        out_path: str,
        settings: dict,
        *,
        tmpdir: str,
        label: str,
    ) -> bool:
        audio_ai = str(settings.get("selected_audio_ai", "none") or "none").lower()
        use_basic = bool(settings.get("use_basic_filter", True))
        master_filter = self._build_ffmpeg_preprocess_filter(settings)
        active_filter = self._build_audio_cleanup_filter(audio_ai, settings)

        if self._can_fuse_ffmpeg_preprocess(audio_ai, settings):
            fused_filter = self._build_fused_ffmpeg_filter(audio_ai, settings, use_basic=use_basic)
            cmd = [
                ffmpeg_binary(), "-y", "-nostdin", "-loglevel", "error",
                *self._ffmpeg_parallel_args(settings),
                "-i", sample_path,
                "-ac", "1", "-ar", "16000",
                "-af", fused_filter,
                "-acodec", "pcm_s16le",
                out_path,
            ]
            return (
                self._run_media_command_no_progress(cmd, label=label)
                and os.path.exists(out_path)
                and os.path.getsize(out_path) > 0
            )

        raw_wav = os.path.join(tmpdir, f"{os.path.basename(out_path)}.raw.wav")
        base_cmd = [
            ffmpeg_binary(), "-y", "-nostdin", "-loglevel", "error",
            *self._ffmpeg_parallel_args(settings),
            "-i", sample_path,
            "-ac", "1", "-ar", str(self._audio_processing_sample_rate(audio_ai, settings)),
        ]
        if use_basic:
            base_cmd.extend(["-af", master_filter])
        base_cmd.extend(["-acodec", "pcm_s16le", raw_wav])
        if not self._run_media_command_no_progress(base_cmd, label=f"{label}-base"):
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
            self._run_media_command_no_progress(final_cmd, label=f"{label}-final")
            and os.path.exists(out_path)
            and os.path.getsize(out_path) > 0
        )

    def _preview_chunk_audio_route(
        self,
        sample_path: str,
        *,
        route_features: dict,
        route_profile: dict,
        candidate_scores: list[dict],
        settings: dict,
        tmpdir: str,
        force: bool = False,
    ) -> tuple[dict | None, list[dict]]:
        from core.audio.preset_auto_classifier import (
            build_audio_profile,
            build_chunk_route_features,
            candidate_settings_for_id,
        )

        if not candidate_scores or not self._audio_route_preview_enabled(settings):
            return None, []

        top_score = float(candidate_scores[0].get("score", 0.0) or 0.0)
        second_score = float(candidate_scores[1].get("score", 0.0) or 0.0) if len(candidate_scores) > 1 else -1.0
        gap = top_score - second_score if second_score >= 0.0 else top_score
        if (
            not force
            and
            top_score >= self._audio_route_preview_min_confidence(settings)
            and gap >= self._audio_route_preview_gap_max(settings)
            and not bool(route_profile.get("volatile_scene"))
        ):
            return None, []

        preview_rows: list[dict] = []
        best: dict | None = None
        profile_sample_count = self._audio_route_profile_sample_count(settings)
        profile_window_sec = self._audio_route_profile_window_sec(settings)
        for idx, candidate_row in enumerate(candidate_scores[: self._audio_route_candidate_limit(settings)], start=1):
            candidate_id = str(candidate_row.get("id") or "")
            candidate_settings = dict(settings)
            candidate_settings.update(candidate_settings_for_id(candidate_id))
            preview_path = os.path.join(tmpdir, f"preview_{idx:02d}_{candidate_id}.wav")
            if not self._write_adaptive_preview_sample(
                sample_path,
                preview_path,
                candidate_settings,
                tmpdir=tmpdir,
                label=f"오디오 라우팅 프리뷰 {candidate_id}",
            ):
                preview_rows.append(
                    {
                        "id": candidate_id,
                        "label": str(candidate_row.get("label") or candidate_id),
                        "preview_ok": False,
                        "score": 0.0,
                    }
                )
                continue

            preview_features = build_chunk_route_features(
                preview_path,
                sample_count=profile_sample_count,
                window_sec=profile_window_sec,
            )
            preview_profile = build_audio_profile(preview_features)
            preview_score, details = self._score_audio_route_preview_candidate(
                candidate_row=candidate_row,
                candidate_settings=candidate_settings,
                raw_features=route_features,
                raw_profile=route_profile,
                preview_features=preview_features,
                preview_profile=preview_profile,
            )
            row = {
                "id": candidate_id,
                "label": str(candidate_row.get("label") or candidate_id),
                "preview_ok": True,
                "score": round(preview_score, 4),
                "signature": candidate_row.get("signature"),
                "settings": candidate_settings,
                "details": details,
                "preview_profile": preview_profile,
            }
            preview_rows.append(row)
            if best is None or float(row.get("score", 0.0) or 0.0) > float(best.get("score", 0.0) or 0.0):
                best = row
        preview_rows.sort(key=lambda row: float(row.get("score", 0.0) or 0.0), reverse=True)
        return best, preview_rows

    def _maybe_apply_audio_route_baseline_guard(
        self,
        sample_path: str,
        *,
        route_features: dict,
        route_profile: dict,
        candidate_scores: list[dict],
        selected_strategy: str,
        selected_label: str,
        selected_confidence: float,
        selected_settings: dict,
        preview_self_score: float | None,
        settings: dict,
        tmpdir: str,
    ) -> dict | None:
        from core.audio.audio_presets import auto_audio_settings_only

        if not self._audio_route_baseline_guard_enabled(settings):
            return None

        baseline_settings = self._audio_route_baseline_settings(settings)
        baseline_signature = self._audio_route_settings_signature(baseline_settings)
        selected_signature = self._audio_route_settings_signature(selected_settings)
        if baseline_signature == selected_signature:
            return None

        baseline_seed = max(
            0.42,
            min(
                0.82,
                float(route_profile.get("speech_confidence", 0.0) or 0.0)
                + (0.06 if str(baseline_settings.get("selected_audio_ai", "none") or "none").strip().lower() == "none" else 0.02),
            ),
        )
        selected_seed = max(0.35, min(0.95, float(selected_confidence or 0.0)))
        selected_candidate = self._audio_route_candidate_row_for_settings(
            candidate_scores,
            selected_settings,
            fallback_id=str(selected_strategy or "adaptive_selected"),
            fallback_label=str(selected_label or selected_strategy or "Adaptive Selected"),
            fallback_score=selected_seed,
        )
        baseline_candidate = self._audio_route_candidate_row_for_settings(
            candidate_scores,
            baseline_settings,
            fallback_id="benchmark_locked_baseline",
            fallback_label="기본 High 유지",
            fallback_score=baseline_seed,
        )
        compare_candidates = [selected_candidate]
        if dict(baseline_candidate) != dict(selected_candidate):
            compare_candidates.append(baseline_candidate)

        _best, compare_scores = self._preview_chunk_audio_route(
            sample_path,
            route_features=route_features,
            route_profile=route_profile,
            candidate_scores=compare_candidates,
            settings=settings,
            tmpdir=tmpdir,
            force=True,
        )
        if not compare_scores:
            return None

        def _find_row(target: dict) -> dict | None:
            target_signature = target.get("signature")
            target_id = str(target.get("id") or "")
            for row in compare_scores:
                if row.get("signature") == target_signature:
                    return row
            for row in compare_scores:
                if str(row.get("id") or "") == target_id:
                    return row
            return None

        selected_preview = _find_row(selected_candidate)
        baseline_preview = _find_row(baseline_candidate)
        if not baseline_preview or not baseline_preview.get("preview_ok"):
            return None

        selected_guard_score = float(preview_self_score if preview_self_score is not None else selected_confidence or 0.0)
        if selected_preview and selected_preview.get("preview_ok"):
            selected_guard_score = float(selected_preview.get("score", selected_guard_score) or selected_guard_score)

        margin = self._audio_route_baseline_margin(settings)
        if str(selected_settings.get("selected_audio_ai", "none") or "none").strip().lower() != "none":
            margin += self._audio_route_baseline_non_none_extra_margin(settings)
        if str(selected_strategy or "").strip().lower() == "noisy_voice":
            margin += self._audio_route_baseline_noisy_voice_extra_margin(settings)
        if bool(route_profile.get("volatile_scene")):
            margin += 0.02

        baseline_score = float(baseline_preview.get("score", 0.0) or 0.0)
        adaptive_gain = selected_guard_score - baseline_score
        challenging_profile = self._audio_route_is_challenging_profile(route_profile)
        specialist_strategy = self._audio_route_is_specialist_strategy(selected_strategy)
        if challenging_profile and specialist_strategy:
            margin = max(self._audio_route_baseline_margin(settings), margin - 0.05)
            if adaptive_gain >= max(0.08, margin + 0.01):
                return {
                    "applied": False,
                    "margin": round(margin, 4),
                    "selected_preview_score": round(selected_guard_score, 4),
                    "baseline_preview_score": round(baseline_score, 4),
                    "compare_scores": compare_scores,
                    "reason": (
                        f"도전적 오디오 프로파일에서 {selected_strategy} self-score 우위 "
                        f"{adaptive_gain:.2f}가 커 adaptive route 유지"
                    ),
                }
        if baseline_score + margin < selected_guard_score:
            return {
                "applied": False,
                "margin": round(margin, 4),
                "selected_preview_score": round(selected_guard_score, 4),
                "baseline_preview_score": round(baseline_score, 4),
                "compare_scores": compare_scores,
            }

        return {
            "applied": True,
            "margin": round(margin, 4),
            "selected_preview_score": round(selected_guard_score, 4),
            "baseline_preview_score": round(baseline_score, 4),
            "compare_scores": compare_scores,
            "settings": baseline_settings,
            "audio_strategy": "benchmark_locked_baseline",
            "audio_strategy_label": "기본 High 유지",
            "confidence": round(baseline_score, 4),
            "reason": (
                f"adaptive 후보 self-score {selected_guard_score:.2f} 대비 "
                f"기본 High self-score {baseline_score:.2f}가 margin {margin:.2f} 안이라 기본값 유지"
            ),
        }

    def _route_risk_level(self, confidence: float, profile: dict, settings: dict | None = None) -> str:
        volatile = bool((profile or {}).get("volatile_scene"))
        noise = str((profile or {}).get("noise_level") or "low").strip().lower()
        low_threshold = self._audio_route_low_confidence_threshold(settings)
        secondary_threshold = self._audio_route_secondary_recheck_threshold(settings)
        if confidence <= low_threshold or (volatile and confidence <= secondary_threshold) or noise == "high":
            return "high"
        if confidence <= self._audio_route_precision_threshold(settings) or volatile:
            return "medium"
        return "low"

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
            build_audio_profile,
            build_chunk_route_features,
            rank_audio_candidates,
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
            features = build_chunk_route_features(
                sample_path,
                sample_count=self._audio_route_profile_sample_count(settings),
                window_sec=self._audio_route_profile_window_sec(settings),
            )
            features.update({
                "sample_duration_sec": sample_dur,
                "total_scanned_sec": sample_dur,
                "media_duration_sec": max(0.0, end - start),
            })
            profile = build_audio_profile(features)
            result = select_audio_candidate(profile, features, use_lora_prior=True)
            candidate_scores = rank_audio_candidates(profile, features, use_lora_prior=True)
            feature_strategy = str(result.get("id") or "clean_voice")
            feature_label = str(result.get("label") or "")
            feature_confidence = float(result.get("score", 0.0) or 0.0)
            selected_strategy = feature_strategy
            selected_label = feature_label
            selected_confidence = feature_confidence
            tune = auto_audio_settings_only(result.get("settings") or {})
            preview_best, preview_scores = self._preview_chunk_audio_route(
                sample_path,
                route_features=features,
                route_profile=profile,
                candidate_scores=candidate_scores,
                settings=settings,
                tmpdir=tmpdir,
            )
            decision_source = "feature_classifier"
            preview_self_score = None
            preview_strategy = feature_strategy
            preview_route_switched = False
            route_reason = str(result.get("reason") or "")
            if preview_best and preview_best.get("preview_ok"):
                decision_source = "feature_plus_preview"
                preview_strategy = str(preview_best.get("id") or selected_strategy)
                preview_route_switched = preview_strategy != feature_strategy
                selected_strategy = preview_strategy
                selected_label = str(preview_best.get("label") or selected_label)
                selected_confidence = float(preview_best.get("score", selected_confidence) or selected_confidence)
                preview_self_score = float(preview_best.get("score", 0.0) or 0.0)
                tune = auto_audio_settings_only(preview_best.get("settings") or tune)
                route_reason = (
                    f"{route_reason}; 프리뷰 self-score {preview_self_score:.2f}로 "
                    f"{selected_label or selected_strategy} 유지/선택"
                ).strip("; ")
            baseline_guard = self._maybe_apply_audio_route_baseline_guard(
                sample_path,
                route_features=features,
                route_profile=profile,
                candidate_scores=candidate_scores,
                selected_strategy=selected_strategy,
                selected_label=selected_label,
                selected_confidence=selected_confidence,
                selected_settings=tune,
                preview_self_score=preview_self_score,
                settings=settings,
                tmpdir=tmpdir,
            )
            if baseline_guard and baseline_guard.get("applied"):
                decision_source = f"{decision_source}_baseline_guard"
                selected_strategy = str(baseline_guard.get("audio_strategy") or selected_strategy)
                selected_label = str(baseline_guard.get("audio_strategy_label") or selected_label)
                selected_confidence = float(baseline_guard.get("confidence", selected_confidence) or selected_confidence)
                tune = auto_audio_settings_only(baseline_guard.get("settings") or tune)
                preview_self_score = float(baseline_guard.get("baseline_preview_score", selected_confidence) or selected_confidence)
                route_reason = (
                    f"{route_reason}; {str(baseline_guard.get('reason') or '').strip()}"
                ).strip("; ")
            risk_level = self._route_risk_level(selected_confidence, profile, settings)
            return {
                "audio_strategy": selected_strategy,
                "audio_strategy_label": selected_label,
                "audio_tune_reason": route_reason,
                "confidence": selected_confidence,
                "feature_confidence": feature_confidence,
                "feature_audio_strategy": feature_strategy,
                "preview_audio_strategy": preview_strategy,
                "preview_route_switched": preview_route_switched,
                "self_score": preview_self_score,
                "settings": tune,
                "audio_profile": profile,
                "features": features,
                "candidate_scores": list(candidate_scores or result.get("candidate_scores") or []),
                "preview_scores": preview_scores,
                "decision_source": decision_source,
                "risk_level": risk_level,
                "precision_review": selected_confidence <= self._audio_route_precision_threshold(settings) or risk_level != "low",
                "secondary_recheck_hint": selected_confidence <= self._audio_route_secondary_recheck_threshold(settings) or risk_level == "high",
                "baseline_guard_applied": bool(baseline_guard and baseline_guard.get("applied")),
                "baseline_guard_margin": None if not baseline_guard else baseline_guard.get("margin"),
                "baseline_guard_scores": [] if not baseline_guard else list(baseline_guard.get("compare_scores") or []),
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

    def _apply_audio_route_hysteresis(self, grouped: list[dict], routes: list[dict], settings: dict) -> list[dict]:
        if not routes:
            return routes
        if not self._settings_bool(settings, "audio_chunk_route_hysteresis_enabled", True):
            return routes

        margin = self._audio_route_hysteresis_margin(settings)
        stabilized: list[dict] = []
        previous: dict | None = None
        for idx, route in enumerate(routes):
            current = dict(route or {})
            current_settings = dict(current.get("settings") or current.get("audio_tune_settings") or {})
            current_strategy = str(current.get("audio_strategy") or "")
            current_conf = float(
                current.get("self_score", current.get("confidence", current.get("feature_confidence", 0.0))) or 0.0
            )
            profile = dict(current.get("audio_profile") or {})
            dynamic_margin = margin + (0.03 if bool(profile.get("volatile_scene")) else 0.0)
            if previous is not None:
                prev_strategy = str(previous.get("audio_strategy") or "")
                prev_conf = float(
                    previous.get("self_score", previous.get("confidence", previous.get("feature_confidence", 0.0))) or 0.0
                )
                if current_strategy and prev_strategy and current_strategy != prev_strategy:
                    baseline_guard_locked = bool(current.get("baseline_guard_applied")) and current_strategy == "benchmark_locked_baseline"
                    if baseline_guard_locked:
                        stabilized.append(current)
                        previous = current
                        continue
                    if current_conf < prev_conf + dynamic_margin:
                        current["hysteresis_applied"] = True
                        current["hysteresis_margin"] = round(dynamic_margin, 4)
                        current["hysteresis_original_strategy"] = current_strategy
                        current["hysteresis_original_settings"] = current_settings
                        current["audio_strategy"] = prev_strategy
                        current["audio_strategy_label"] = str(previous.get("audio_strategy_label") or prev_strategy)
                        kept_settings = dict(previous.get("settings") or previous.get("audio_tune_settings") or {})
                        current["settings"] = kept_settings
                        current["audio_tune_settings"] = kept_settings
                        current["selected_vad"] = str(
                            kept_settings.get("selected_vad", current_settings.get("selected_vad", ""))
                        )
                        current["confidence"] = round(max(current_conf, prev_conf - (dynamic_margin / 2.0)), 4)
                        current["precision_review"] = bool(previous.get("precision_review") or current.get("precision_review"))
                        current["secondary_recheck_hint"] = bool(
                            previous.get("secondary_recheck_hint") or current.get("secondary_recheck_hint")
                        )
            stabilized.append(current)
            previous = current
        return stabilized

    @staticmethod
    def _route_effective_score(route: dict | None) -> float:
        row = dict(route or {})
        return float(
            row.get("self_score", row.get("confidence", row.get("feature_confidence", 0.0))) or 0.0
        )

    def _apply_audio_route_profile_memory(self, grouped: list[dict], routes: list[dict], settings: dict) -> list[dict]:
        _ = grouped
        if not routes:
            return routes
        if not self._audio_route_profile_memory_enabled(settings):
            return routes

        from core.audio.preset_auto_classifier import build_audio_route_bucket

        margin = self._audio_route_profile_memory_margin(settings)
        min_confidence = self._audio_route_profile_memory_min_confidence(settings)
        stabilized: list[dict] = []
        bucket_memory: dict[str, dict] = {}

        for idx, route in enumerate(routes):
            current = dict(route or {})
            current_settings = dict(current.get("settings") or current.get("audio_tune_settings") or {})
            current_strategy = str(current.get("audio_strategy") or "")
            current_score = self._route_effective_score(current)
            profile = dict(current.get("audio_profile") or {})
            bucket = build_audio_route_bucket(profile)
            current["profile_bucket"] = bucket

            remembered = bucket_memory.get(bucket)
            baseline_guard_locked = bool(current.get("baseline_guard_applied")) and current_strategy == "benchmark_locked_baseline"
            current_is_fallback = current_strategy == "clip_fallback"

            if remembered and not baseline_guard_locked:
                remembered_strategy = str(remembered.get("audio_strategy") or "")
                remembered_score = float(remembered.get("score", 0.0) or 0.0)
                remembered_settings = dict(remembered.get("settings") or {})
                remembered_label = str(remembered.get("audio_strategy_label") or remembered_strategy)
                remembered_reusable = (
                    remembered_strategy
                    and remembered_strategy != "clip_fallback"
                    and remembered_score >= min_confidence
                )
                confidence_gap_small = current_score < remembered_score + margin
                current_is_ambiguous = current_score < min_confidence
                if (
                    remembered_reusable
                    and remembered_strategy != current_strategy
                    and (current_is_fallback or current_is_ambiguous or confidence_gap_small)
                ):
                    adopted_score = round(max(current_score, remembered_score - (margin / 2.0)), 4)
                    current["profile_memory_applied"] = True
                    current["profile_memory_bucket"] = bucket
                    current["profile_memory_margin"] = round(margin, 4)
                    current["profile_memory_original_strategy"] = current_strategy
                    current["profile_memory_original_settings"] = current_settings
                    current["profile_memory_reason"] = (
                        f"유사 오디오 프로파일({bucket})에서 직전 안정 route {remembered_strategy} 재사용"
                    )
                    current["audio_strategy"] = remembered_strategy
                    current["audio_strategy_label"] = remembered_label
                    current["settings"] = remembered_settings
                    current["audio_tune_settings"] = remembered_settings
                    current["confidence"] = adopted_score
                    current["self_score"] = adopted_score
                    current_strategy = remembered_strategy
                    current_settings = remembered_settings
                    current_score = adopted_score

            stabilized.append(current)

            final_strategy = str(current.get("audio_strategy") or "")
            final_score = self._route_effective_score(current)
            final_settings = dict(current.get("settings") or current.get("audio_tune_settings") or {})
            if final_strategy and final_strategy != "clip_fallback" and final_score >= min_confidence:
                existing = bucket_memory.get(bucket)
                existing_score = float((existing or {}).get("score", 0.0) or 0.0)
                existing_strategy = str((existing or {}).get("audio_strategy") or "")
                if existing is None or existing_strategy == final_strategy or final_score > existing_score + margin:
                    bucket_memory[bucket] = {
                        "index": idx,
                        "audio_strategy": final_strategy,
                        "audio_strategy_label": str(current.get("audio_strategy_label") or final_strategy),
                        "settings": final_settings,
                        "score": round(final_score, 4),
                    }

        return stabilized

    def _apply_audio_route_switch_confirmation(self, grouped: list[dict], routes: list[dict], settings: dict) -> list[dict]:
        _ = grouped
        if not routes:
            return routes
        if not self._audio_route_switch_confirmation_enabled(settings):
            return routes

        min_streak = self._audio_route_switch_confirmation_min_streak(settings)
        margin = self._audio_route_switch_confirmation_margin(settings)
        strong_margin = max(margin, self._audio_route_switch_confirmation_strong_margin(settings))
        stabilized: list[dict] = []
        stable_route: dict | None = None
        pending_strategy = ""
        pending_bucket = ""
        pending_streak = 0
        pending_best_score = 0.0

        for current_idx, route in enumerate(routes):
            current = dict(route or {})
            current_settings = dict(current.get("settings") or current.get("audio_tune_settings") or {})
            current_strategy = str(current.get("audio_strategy") or "")
            current_score = self._route_effective_score(current)
            profile = dict(current.get("audio_profile") or {})
            bucket = str(current.get("profile_bucket") or profile.get("profile_bucket") or "").strip()
            if not bucket:
                from core.audio.preset_auto_classifier import build_audio_route_bucket

                bucket = build_audio_route_bucket(profile)
                current["profile_bucket"] = bucket
            baseline_guard_locked = bool(current.get("baseline_guard_applied")) and current_strategy == "benchmark_locked_baseline"

            if stable_route is None or not current_strategy:
                stabilized.append(current)
                stable_route = current
                pending_strategy = ""
                pending_bucket = ""
                pending_streak = 0
                pending_best_score = 0.0
                continue

            stable_strategy = str(stable_route.get("audio_strategy") or "")
            stable_score = self._route_effective_score(stable_route)
            stable_settings = dict(stable_route.get("settings") or stable_route.get("audio_tune_settings") or {})
            stable_label = str(stable_route.get("audio_strategy_label") or stable_strategy)

            if baseline_guard_locked or current_strategy == stable_strategy:
                stabilized.append(current)
                stable_route = current
                pending_strategy = ""
                pending_bucket = ""
                pending_streak = 0
                pending_best_score = 0.0
                continue

            dynamic_margin = margin + (0.02 if bool(profile.get("volatile_scene")) else 0.0)
            dynamic_strong_margin = strong_margin + (0.03 if bool(profile.get("volatile_scene")) else 0.0)

            if current_score >= stable_score + dynamic_strong_margin:
                current["switch_confirmation_bypassed"] = True
                current["switch_confirmation_margin"] = round(dynamic_strong_margin, 4)
                current["switch_confirmation_reason"] = (
                    f"새 route {current_strategy} self-score {current_score:.2f}가 "
                    f"이전 안정 route {stable_strategy} {stable_score:.2f}보다 충분히 높아 즉시 전환"
                )
                stabilized.append(current)
                stable_route = current
                pending_strategy = ""
                pending_bucket = ""
                pending_streak = 0
                pending_best_score = 0.0
                continue

            if pending_strategy == current_strategy and pending_bucket == bucket:
                pending_streak += 1
                pending_best_score = max(pending_best_score, current_score)
            else:
                pending_strategy = current_strategy
                pending_bucket = bucket
                pending_streak = 1
                pending_best_score = current_score

            if pending_streak >= min_streak and pending_best_score >= stable_score + dynamic_margin:
                current["switch_confirmation_approved"] = True
                current["switch_confirmation_margin"] = round(dynamic_margin, 4)
                current["switch_confirmation_streak"] = pending_streak
                current["switch_confirmation_reason"] = (
                    f"새 route {current_strategy}가 유사 구간 {pending_streak}개 연속 확인되어 전환"
                )
                stabilized.append(current)
                stable_route = current
                pending_strategy = ""
                pending_bucket = ""
                pending_streak = 0
                pending_best_score = 0.0
                continue

            adopted_score = round(max(current_score, stable_score - (dynamic_margin / 2.0)), 4)
            current["switch_confirmation_applied"] = True
            current["switch_confirmation_original_strategy"] = current_strategy
            current["switch_confirmation_original_settings"] = current_settings
            current["switch_confirmation_margin"] = round(dynamic_margin, 4)
            current["switch_confirmation_streak"] = pending_streak
            current["switch_confirmation_reason"] = (
                f"새 route {current_strategy} 전환 전 확인 중({pending_streak}/{min_streak})이라 "
                f"이전 안정 route {stable_strategy} 유지"
            )
            current["audio_strategy"] = stable_strategy
            current["audio_strategy_label"] = stable_label
            current["settings"] = stable_settings
            current["audio_tune_settings"] = stable_settings
            current["confidence"] = adopted_score
            current["self_score"] = adopted_score
            current["precision_review"] = bool(
                stable_route.get("precision_review") or current.get("precision_review")
            )
            current["secondary_recheck_hint"] = bool(
                stable_route.get("secondary_recheck_hint") or current.get("secondary_recheck_hint")
            )
            stabilized.append(current)

        return stabilized

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
        worker_plan = plan_audio_route_workers(
            settings=settings,
            requested=getattr(self, "io_workers", None),
            workload=workload,
        )
        max_workers = worker_plan.max_workers
        reductions = worker_plan.reductions_label
        if max_workers > 1:
            suffix = f" ({reductions})" if reductions else ""
            _runtime_get_logger().log(f"  🧵 [오디오 라우팅] 청크 라우팅 병렬 워커 {max_workers}개{suffix}")

        progress_lock = threading.Lock()
        done_count = 0
        next_log_pct = 0
        progress_total = max(1, len(grouped))

        def _mark_progress():
            nonlocal done_count, next_log_pct, progress_total
            with progress_lock:
                done_count += 1
                pct = min(100, int(round((done_count / progress_total) * 100)))
                if pct >= next_log_pct or done_count == progress_total:
                    next_log_pct = min(100, pct + 10)
                    self._notify_stage(f"⏳ [오디오] 청크별 오디오 라우팅 중 {pct}%")
                    _runtime_get_logger().log(
                        f"  └ [오디오 라우팅] 청크 처리 진행률 {pct}% ({done_count}/{progress_total})"
                    )

        def _classify_one(idx_seg):
            idx, seg = idx_seg
            route = self._classify_chunk_audio_route(media_path, seg, settings, index=idx, tmpdir=tmpdir)
            return idx, route

        def _classify_grouped(items: list[dict]) -> tuple[dict[int, dict], int]:
            local_logs: dict[int, dict] = {}
            local_failures = 0
            if max_workers <= 1:
                for item in enumerate(items):
                    try:
                        idx, route = _classify_one(item)
                        local_logs[idx] = route
                    except Exception as exc:
                        local_failures += 1
                        _runtime_get_logger().log(f"  ⚠️ [오디오 라우팅] 청크 처리 실패: {exc}")
            else:
                with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="audio-route") as executor:
                    futures = [executor.submit(_classify_one, item) for item in enumerate(items)]
                    for future in futures:
                        try:
                            idx, route = future.result()
                            local_logs[idx] = route
                        except Exception as exc:
                            local_failures += 1
                            _runtime_get_logger().log(f"  ⚠️ [오디오 라우팅] 청크 처리 실패: {exc}")
            return local_logs, local_failures

        def _render_one(idx_seg_route):
            idx, seg, route = idx_seg_route
            start = max(0.0, float(seg.get("start", 0.0) or 0.0))
            out = os.path.join(chunk_dir, f"vad_{idx:03d}_{start:.3f}.wav")
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
                "feature_confidence": route.get("feature_confidence"),
                "self_score": route.get("self_score"),
                "audio_profile": route.get("audio_profile"),
                "audio_tune_settings": dict(route.get("settings") or {}),
                "candidate_scores": list(route.get("candidate_scores") or []),
                "preview_scores": list(route.get("preview_scores") or []),
                "decision_source": route.get("decision_source"),
                "risk_level": route.get("risk_level"),
                "precision_review": bool(route.get("precision_review")),
                "secondary_recheck_hint": bool(route.get("secondary_recheck_hint")),
                "baseline_guard_applied": bool(route.get("baseline_guard_applied")),
                "baseline_guard_margin": route.get("baseline_guard_margin"),
                "baseline_guard_scores": list(route.get("baseline_guard_scores") or []),
                "profile_bucket": route.get("profile_bucket"),
                "profile_memory_applied": bool(route.get("profile_memory_applied")),
                "profile_memory_bucket": route.get("profile_memory_bucket"),
                "profile_memory_margin": route.get("profile_memory_margin"),
                "profile_memory_original_strategy": route.get("profile_memory_original_strategy"),
                "profile_memory_reason": route.get("profile_memory_reason"),
                "switch_confirmation_applied": bool(route.get("switch_confirmation_applied")),
                "switch_confirmation_approved": bool(route.get("switch_confirmation_approved")),
                "switch_confirmation_bypassed": bool(route.get("switch_confirmation_bypassed")),
                "switch_confirmation_original_strategy": route.get("switch_confirmation_original_strategy"),
                "switch_confirmation_margin": route.get("switch_confirmation_margin"),
                "switch_confirmation_streak": route.get("switch_confirmation_streak"),
                "switch_confirmation_reason": route.get("switch_confirmation_reason"),
                "hysteresis_applied": bool(route.get("hysteresis_applied")),
                "hysteresis_original_strategy": route.get("hysteresis_original_strategy"),
                "hysteresis_margin": route.get("hysteresis_margin"),
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
            working_grouped = [dict(seg) for seg in grouped]
            route_logs, classify_failures = _classify_grouped(working_grouped)
            failures += classify_failures
            if failures:
                _runtime_get_logger().log(f"  ⚠️ [오디오 라우팅] 분류 실패 {failures}개: 기존 청크 생성 경로로 재시도합니다")
                return False

            expanded_grouped = self._selective_expand_grouped_chunks_for_audio_route(
                working_grouped,
                route_logs,
                settings,
            )
            if len(expanded_grouped) != len(working_grouped) or any(
                dict(a) != dict(b) for a, b in zip(expanded_grouped, working_grouped)
            ):
                working_grouped = expanded_grouped
                progress_total = max(1, len(working_grouped))
                route_logs, classify_failures = _classify_grouped(working_grouped)
                failures += classify_failures
                if failures:
                    _runtime_get_logger().log(
                        f"  ⚠️ [오디오 라우팅] 세분화 후 재분류 실패 {failures}개: 기존 청크 생성 경로로 재시도합니다"
                    )
                    return False

            profile_memory_route_list = self._apply_audio_route_profile_memory(
                working_grouped,
                [route_logs[idx] for idx in sorted(route_logs)],
                settings,
            )
            confirmed_route_list = self._apply_audio_route_switch_confirmation(
                working_grouped,
                profile_memory_route_list,
                settings,
            )
            stabilized_route_list = self._apply_audio_route_hysteresis(
                working_grouped,
                confirmed_route_list,
                settings,
            )
            route_logs = {
                idx: dict(route)
                for idx, route in enumerate(stabilized_route_list)
            }

            for idx in sorted(route_logs):
                _runtime_get_logger().log(self._route_log_line(idx, working_grouped[idx], route_logs[idx]))

            if max_workers <= 1:
                for idx, seg in enumerate(working_grouped):
                    _store_result(_render_one((idx, seg, route_logs[idx])))
                    _mark_progress()
            else:
                with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="audio-route-render") as executor:
                    futures = [
                        executor.submit(_render_one, (idx, seg, route_logs[idx]))
                        for idx, seg in enumerate(working_grouped)
                    ]
                    for future in futures:
                        try:
                            _store_result(future.result())
                        except Exception as exc:
                            failures += 1
                            _runtime_get_logger().log(f"  ⚠️ [오디오 라우팅] 청크 생성 실패: {exc}")
                        finally:
                            _mark_progress()

            reuse_precomputed_vad = route_vad_enabled and bool(precomputed_vad_segments)
            if reuse_precomputed_vad:
                route_vad_segments = [
                    dict(row)
                    for row in list(precomputed_vad_segments or [])
                    if isinstance(row, dict)
                ]
                for idx, seg in enumerate(working_grouped):
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
        _runtime_get_logger().log(f"  ✅ [오디오 라우팅] 청크별 오디오 라우팅 완료 ({max(1, len(routes))}개)")
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
            snapshot = media_fingerprint_snapshot(
                video_path,
                sample_bytes=512 * 1024,
                include_samples=True,
                missing_digest="",
            )
            source_size = int(snapshot.get("size", 0) or 0)
            source_mtime_ns = int(snapshot.get("mtime_ns", 0) or 0)
            source_fingerprint = str(snapshot.get("fingerprint", source) or source)
            source_fingerprint_digest = str(snapshot.get("fingerprint_digest", "") or "")
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
            snapshot = media_fingerprint_snapshot(
                source,
                sample_bytes=512 * 1024,
                include_samples=True,
            )
            source_size = int(snapshot.get("size", 0) or 0)
            source_mtime_ns = int(snapshot.get("mtime_ns", 0) or 0)
            source_fingerprint = str(snapshot.get("fingerprint", source) or source)
            source_digest = str(snapshot.get("fingerprint_digest", "") or "")
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
