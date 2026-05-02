# Version: 03.08.07
# Phase: PHASE2
"""
media_processor.py  ─  잼민이 PD v25 (VAD 섹터 그룹화 + 무음 로깅 + Whisper 섹터 동기화)
[특징] 
1. VAD가 설정된 무음 간격(기본 2.0초)을 기준으로 통짜 음성 섹터를 구성
2. 무음 세그먼트와 음성 섹터를 앱 로그에 완벽하게 분리하여 출력
3. Whisper는 기본적으로 고정 오버랩 청크를 인식하고, VAD는 검수/선택 선분할 신호로만 사용
"""
import sys
import importlib.util
import os, subprocess, json, re, config, shutil, time, wave, threading, math
from concurrent.futures import ThreadPoolExecutor
from core.audio.audio_presets import apply_audio_preset
from core.media_info import probe_media
from core.performance import bounded_worker_count
from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs, rnnoise_binary
from core.subtitle_quality.candidate_ranker import rank_overlap_candidates
from core.subtitle_quality.hallucination_detector import annotate_segment_hallucination_risk
from core.subtitle_quality.models import attach_asr_metadata
from core.subtitle_quality.vad_alignment_checker import (
    annotate_segment_vad_alignment,
    apply_review_vad_settings,
    review_vad_config,
    review_vad_enabled,
)
from core.llm.secure_keys import get_api_key
from logger import get_logger

_CHUNK_DURATION = 30
_OVERLAP_SEC = 3.0
_VAD_CACHE_VERSION = 3
_AUDIO_CACHE_VERSION = 2


def _parse_worker_json_line(line: str):
    line = (line or "").strip()
    if not line or not line.startswith("{"):
        return None
    try:
        return json.loads(line)
    except Exception as e:
        get_logger().log(f"  ⚠️ JSON 파싱 오류: {e}")
        get_logger().log(f"  ⚠️ raw line: {line[:200] if line else 'empty'}")
        return None


class VideoProcessor:
    # [media_processor.py] __init__ 함수 내부
    
    def __init__(self):
        self.whisper_model = getattr(config, "WHISPER_MODEL", "mlx-community/whisper-large-v3-mlx")
        self.audio_ai = "deepfilter"
        self.vad_model = "silero"
        self.io_workers = bounded_worker_count(kind="io")

        settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    s = json.load(f)
                    self.whisper_model = s.get("selected_whisper_model", self.whisper_model)
                    self.audio_ai = s.get("selected_audio_ai", "deepfilter")
                    self.vad_model = s.get("selected_vad", "silero")
                    self.io_workers = bounded_worker_count(s.get("io_workers", self.io_workers), kind="io")
            except Exception:
                pass

        self.language = getattr(config, "LANGUAGE", "ko")
        self._executor = ThreadPoolExecutor(max_workers=self.io_workers)

        # 런타임 핸들
        self._whisper_proc = None
        self._whisper_runner_proc = None
        self._whisper_lock = threading.Lock()

        self._vad_loaded = False
        self._vad_model = None
        self._vad_utils = None
        self.stage_callback = None

    def _notify_stage(self, status: str):
        callback = getattr(self, "stage_callback", None)
        if not callable(callback):
            return
        try:
            callback(str(status or ""))
        except Exception:
            pass

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
            get_logger().log(f"  ❌ {label} 실행 파일을 찾을 수 없습니다: {e}")
            return False
        except Exception as e:
            get_logger().log(f"  ❌ {label} 실행 오류: {e}")
            return False

        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            lines = [line.strip() for line in err.splitlines() if line.strip()]
            summary = "\n".join(lines[-10:]) if lines else err
            get_logger().log(f"  ❌ {label} 실패: {summary[:1200]}")
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
        get_logger().log(f"  └ [전처리] {label} 진행률 {pct}%")
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
        get_logger().log(f"  └ [VAD 후처리] {label} {phase} 진행률 {pct}%")
        return pct

    def _start_vad_heartbeat(self, label: str, phase: str, *, interval_sec: float = 5.0):
        stop_event = threading.Event()
        interval = max(1.0, float(interval_sec or 5.0))

        def _beat():
            started = time.monotonic()
            while not stop_event.wait(interval):
                elapsed = int(time.monotonic() - started)
                self._notify_stage(f"⏳ [VAD] {label} {phase} 중... {elapsed}초")
                get_logger().log(f"  └ [VAD 후처리] {label} {phase} 진행 중... {elapsed}초")

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
                    get_logger().log(f"  ❌ {label} 실행 오류: timeout")
                    return False
                line = raw_line.strip()
                if not line.startswith("out_time_ms="):
                    if line and not line.startswith(("frame=", "fps=", "stream_", "progress=", "bitrate=", "total_size=", "out_time=")):
                        stderr_lines.append(line)
                        stderr_lines = stderr_lines[-12:]
                    continue
                try:
                    out_sec = float(line.split("=", 1)[1]) / 1_000_000.0
                except Exception:
                    continue
                last_pct = self._emit_ffmpeg_progress(label, out_sec / duration)
            proc.wait(timeout=1)
        except FileNotFoundError as e:
            get_logger().log(f"  ❌ {label} 실행 파일을 찾을 수 없습니다: {e}")
            return False
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass
            get_logger().log(f"  ❌ {label} 실행 오류: timeout")
            return False
        except Exception as e:
            get_logger().log(f"  ❌ {label} 실행 오류: {e}")
            return False

        if proc.returncode != 0:
            summary = "\n".join(stderr_lines[-10:])
            get_logger().log(f"  ❌ {label} 실패: {summary[:1200]}")
            return False
        if last_pct < 100:
            self._emit_ffmpeg_progress(label, 1.0, force=True)
        get_logger().log(f"  └ [전처리] {label} 완료")
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
            get_logger().log(f"  ❌ {label} 실행 파일을 찾을 수 없습니다: {e}")
            return False
        except Exception as e:
            get_logger().log(f"  ❌ {label} 실행 오류: {e}")
            return False

        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            lines = [line.strip() for line in err.splitlines() if line.strip()]
            summary = "\n".join(lines[-10:]) if lines else err
            get_logger().log(f"  ❌ {label} 실패: {summary[:1200]}")
            return False
        return True

    def _huggingface_env(self) -> dict:
        env = dict(os.environ)
        token = env.get("HF_TOKEN") or env.get("HUGGINGFACE_HUB_TOKEN") or get_api_key("huggingface")
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
                get_logger().log("  ⚠️ RNNoise 실행 실패 또는 미설치: FFMPEG 정제로 계속 진행합니다")
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
            if not self._run_media_command(
                self._resemble_enhance_command(cli, in_dir, out_dir, device),
                label="Resemble Enhance 음성 향상",
                timeout=900,
                env=self._huggingface_env(),
            ):
                get_logger().log("  ⚠️ Resemble Enhance 실행 실패 또는 미설치: FFMPEG 정제로 계속 진행합니다")
                return False
            return self._copy_first_wav_from_dir(out_dir, target_wav)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _apply_clearvoice(self, source_wav: str, target_wav: str) -> bool:
        if importlib.util.find_spec("clearvoice") is None:
            get_logger().log("  ⚠️ ClearVoice 패키지가 설치되어 있지 않습니다: python3.11 -m pip install clearvoice")
            return False
        script = (
            "import sys\n"
            "from clearvoice import ClearVoice\n"
            "source, target = sys.argv[1], sys.argv[2]\n"
            "engine = ClearVoice(task='speech_enhancement', model_names=['MossFormer2_SE_48K'])\n"
            "audio = engine(input_path=source, online_write=False)\n"
            "engine.write(audio, output_path=target)\n"
        )
        if not self._run_media_command(
            [sys.executable, "-c", script, source_wav, target_wav],
            label="ClearVoice 음성 향상",
            timeout=900,
            env=self._huggingface_env(),
        ):
            get_logger().log("  ⚠️ ClearVoice 실행 실패 또는 미설치: FFMPEG 정제로 계속 진행합니다")
            return False
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

    def _build_audio_cleanup_filter(self, audio_ai: str, settings: dict) -> str:
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

        if audio_ai in {"resemble_enhance", "clearvoice"}:
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

    @staticmethod
    def _can_fuse_ffmpeg_preprocess(audio_ai: str) -> bool:
        return str(audio_ai or "none").lower() in {"none", "deepfilter"}

    @staticmethod
    def _combine_audio_filters(*filters: str) -> str:
        chain = []
        for value in filters:
            text = str(value or "").strip()
            if not text or text == "anull":
                continue
            chain.append(text)
        return ",".join(chain) if chain else "anull"

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
        except Exception:
            source = os.path.abspath(video_path or "")
            source_size = 0
            source_mtime_ns = 0
        return {
            "version": _AUDIO_CACHE_VERSION,
            "source": source,
            "source_size": source_size,
            "source_mtime_ns": source_mtime_ns,
            "audio_ai": str(audio_ai or "none"),
            "use_basic_filter": bool(use_basic),
            "master_filter": str(master_filter or "anull"),
            "active_filter": str(active_filter or "anull"),
            "sample_rate": 16000,
            "channels": 1,
            "pcm": "s16le",
            "ffmpeg_filter_threads": int(max(1, bounded_worker_count(settings.get("ffmpeg_filter_threads", self.io_workers), kind="cpu"))),
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
        if not self._can_fuse_ffmpeg_preprocess(audio_ai):
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
        min_sec = float(settings.get("direct_ffmpeg_chunk_min_sec", 600.0) or 0.0)
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
    def process_video(self, media_path, ui_callback, min_spk=1, max_spk=1, target_start_sec=0.0, target_end_sec=None, is_single_segment=False):
        import time

        # 오디오 추출 단계로 is_single_segment 전달
        chunk_dir, vad_segments = self.extract_audio(media_path, target_start_sec, target_end_sec, is_single_segment)
        
        if not os.path.exists(chunk_dir) or not os.listdir(chunk_dir):
            yield [], 1, 1; return

        # Whisper 단계로 is_single_segment 및 target_end_sec 전달
        for chunk_segs, idx, total in self.transcribe(chunk_dir, is_fast_mode=False, target_end_sec=target_end_sec, is_single=is_single_segment):
            yield chunk_segs, idx, total

    # 💡 오디오 추출/정제 엔진 (is_single_segment 파라미터 추가)
    def extract_audio(self, video_path: str, target_start_sec=0.0, target_end_sec=None, is_single_segment=False):
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)
        s = self._load_all_settings()
        audio_ai = s.get("selected_audio_ai", "deepfilter")
        use_basic = s.get("use_basic_filter", True)
        vad_model = s.get("selected_vad", "silero")

        master_filter = self._build_ffmpeg_preprocess_filter(s)
        active_filter = self._build_audio_cleanup_filter(audio_ai, s)

        base_name = os.path.splitext(os.path.basename(video_path))[0]
        chunk_dir = os.path.join(config.OUTPUT_DIR, f"{base_name}_chunks")
        raw_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}_raw.wav")
        cleaned_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}_cleaned.wav")
        cleaned_meta = f"{cleaned_wav}.meta.json"
        
        is_partial = target_start_sec > 0.0 or target_end_sec is not None
        cache_config = self._audio_cache_config(
            video_path,
            s,
            audio_ai=audio_ai,
            use_basic=use_basic,
            master_filter=master_filter,
            active_filter=active_filter,
        )
        
        shutil.rmtree(chunk_dir, ignore_errors=True)
        os.makedirs(chunk_dir, exist_ok=True)

        vad_pre_split_enabled = bool(s.get("vad_pre_split_enabled", False))
        vad_post_align_enabled = bool(s.get("vad_post_stt_align_enabled", True))
        direct_start, direct_end = self._direct_chunk_span(video_path, target_start_sec, target_end_sec)
        direct_span = max(0.0, direct_end - direct_start)
        if self._can_direct_extract_stt_chunks(
            s,
            audio_ai=audio_ai,
            vad_model=vad_model,
            vad_pre_split_enabled=vad_pre_split_enabled,
            vad_post_align_enabled=vad_post_align_enabled,
            span_sec=direct_span,
            is_partial=is_partial,
        ):
            chunk_sec = max(10.0, float(s.get("ff_chunk", _CHUNK_DURATION)))
            overlap_sec = self._chunk_overlap_sec(s)
            grouped = self._split_range_with_overlap(direct_start, direct_end, chunk_sec, overlap_sec)
            fused_filter = self._combine_audio_filters(master_filter if use_basic else "anull", active_filter)
            self._notify_stage("⏳ [전처리] FFMPEG 직접 청크 추출 중")
            get_logger().log(
                "  └ [전처리] 전체 WAV 생성을 건너뛰고 원본에서 STT 청크를 직접 추출합니다 "
                f"(청크 {len(grouped)}개, {direct_span:.1f}초)"
            )
            ok = self._write_grouped_chunks_from_media_parallel(video_path, chunk_dir, grouped, fused_filter, s)
            if ok:
                get_logger().log(f"    → Whisper 청크 {len(grouped)}개 직접 생성 완료 (overlap {overlap_sec:.1f}초)")
                return chunk_dir, []
            get_logger().log("  ⚠️ 직접 청크 추출 실패: 기존 cleaned.wav 전처리 경로로 재시도합니다")
            shutil.rmtree(chunk_dir, ignore_errors=True)
            os.makedirs(chunk_dir, exist_ok=True)

        reuse_audio_cache = bool(s.get("reuse_preprocessed_audio_cache", True))
        is_valid_cache = reuse_audio_cache and self._cleaned_audio_cache_valid(cleaned_wav, cleaned_meta, cache_config)

        if is_valid_cache:
            self._notify_stage("♻️ [전처리] FFMPEG 오디오 캐시 재사용")
            get_logger().log("  └ ♻️ [전처리] 원본/설정이 같은 오디오 캐시를 재사용합니다")
        else:
            self._notify_stage("⏳ [전처리] FFMPEG 오디오 추출 및 기본 필터 적용 중")
            get_logger().log("  └ [전처리] FFMPEG 오디오 추출 및 기본 필터 적용 중...")
            ffmpeg = ffmpeg_binary()

            if self._can_fuse_ffmpeg_preprocess(audio_ai):
                fused_filter = self._combine_audio_filters(master_filter if use_basic else "anull", active_filter)
                self._notify_stage("⏳ [전처리] FFMPEG 단일 패스 오디오 추출/정제 중")
                get_logger().log("  └ [전처리] FFMPEG 단일 패스로 오디오 추출/정제를 처리합니다")
                extract_cmd = [
                    ffmpeg, "-y", "-nostdin", "-loglevel", "error",
                    *self._ffmpeg_parallel_args(s),
                    "-i", video_path,
                    *self._ffmpeg_audio_stream_args(),
                    "-ac", "1", "-ar", "16000",
                    "-af", fused_filter,
                    "-acodec", "pcm_s16le",
                    cleaned_wav,
                ]
                if not self._run_media_command(extract_cmd, label="ffmpeg 음량 평탄화"):
                    return chunk_dir, []
                self._write_cleaned_audio_cache_meta(cleaned_meta, cache_config)
                if os.path.exists(raw_wav):
                    try:
                        os.remove(raw_wav)
                    except Exception:
                        pass
                ai_wav = cleaned_wav
                audio_filter_applied = False
            else:
                extract_cmd = [
                    ffmpeg, "-y", "-nostdin", "-loglevel", "error",
                    *self._ffmpeg_parallel_args(s),
                    "-i", video_path,
                    *self._ffmpeg_audio_stream_args(),
                    "-ac", "1", "-ar", "48000",
                ]
                if use_basic:
                    extract_cmd.extend(["-af", master_filter])
                extract_cmd.extend(["-acodec", "pcm_s16le", raw_wav])
                if not self._run_media_command(extract_cmd, label="ffmpeg 오디오 추출"):
                    return chunk_dir, []

                ai_wav = raw_wav
                audio_filter_applied = False
                if audio_ai == "rnnoise":
                    self._notify_stage("⏳ [음성] RNNoise 빠른 노이즈 제거 중")
                    get_logger().log("  └ [음성] RNNoise 빠른 노이즈 제거 중...")
                    rnnoise_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}_rnnoise.wav")
                    if self._apply_rnnoise(raw_wav, rnnoise_wav) and os.path.exists(rnnoise_wav):
                        ai_wav = rnnoise_wav
                        audio_filter_applied = True
                elif audio_ai == "resemble_enhance":
                    self._notify_stage("⏳ [음성] Resemble Enhance 음성 향상 중")
                    get_logger().log("  └ [음성] Resemble Enhance 음성 향상 중...")
                    resemble_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}_resemble.wav")
                    if self._apply_resemble_enhance(raw_wav, resemble_wav) and os.path.exists(resemble_wav):
                        ai_wav = resemble_wav
                        audio_filter_applied = True
                elif audio_ai == "clearvoice":
                    self._notify_stage("⏳ [음성] ClearVoice 음성 향상 중")
                    get_logger().log("  └ [음성] ClearVoice 음성 향상 중...")
                    clearvoice_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}_clearvoice.wav")
                    if self._apply_clearvoice(raw_wav, clearvoice_wav) and os.path.exists(clearvoice_wav):
                        ai_wav = clearvoice_wav
                        audio_filter_applied = True

                audio_label = self._audio_cleanup_label(audio_ai, audio_filter_applied)
                if audio_ai == "none":
                    self._notify_stage("⏳ [음성] 미사용: FFMPEG 16k 포맷 변환 중")
                    get_logger().log("  └ [음성] 미사용: FFMPEG 16k 포맷 변환 중...")
                else:
                    self._notify_stage(f"⏳ [음성] {audio_label} 정제 및 FFMPEG 16k 변환 중")
                    get_logger().log(f"  └ [음성] {audio_label} 정제 및 FFMPEG 16k 변환 중...")
                if not self._run_media_command(
                    [
                        ffmpeg, "-y", "-nostdin", "-loglevel", "error",
                        *self._ffmpeg_parallel_args(s),
                        "-i", ai_wav,
                        "-ac", "1", "-ar", "16000",
                        "-af", active_filter,
                        "-acodec", "pcm_s16le",
                        cleaned_wav,
                    ],
                    label="ffmpeg 음량 평탄화",
                ):
                    return chunk_dir, []
                self._write_cleaned_audio_cache_meta(cleaned_meta, cache_config)
                if os.path.exists(raw_wav): os.remove(raw_wav)

        vad_segments = []
        vad_requested = vad_model != "none" and vad_pre_split_enabled
        vad_empty_or_failed = False
        if vad_model != "none" and not vad_pre_split_enabled:
            if vad_post_align_enabled and os.path.exists(cleaned_wav):
                self._notify_stage(f"⏳ [VAD] {vad_model.upper()} 음성 위치 재계산 준비 중")
                get_logger().log(
                    f"  └ [VAD 후처리] {vad_model.upper()} 음성 위치 재계산 중 "
                    "(STT 선분할에는 사용하지 않음)"
                )
                vad_segments = self._detect_vad_timestamps(
                    cleaned_wav,
                    vad_model,
                    s,
                    target_start_sec=target_start_sec,
                    target_end_sec=target_end_sec,
                    is_single_segment=is_single_segment,
                    for_post_stt_align=True,
                )
                if vad_segments:
                    try:
                        with open(os.path.join(chunk_dir, "vad_strict.json"), "w", encoding="utf-8") as f:
                            json.dump(vad_segments, f)
                    except Exception:
                        pass
                    get_logger().log(f"  └ [VAD 후처리] 음성 위치 {len(vad_segments)}개 확보")
                else:
                    get_logger().log("  └ [VAD 후처리] 유효한 음성 위치를 찾지 못해 타이밍 보정을 건너뜁니다")
            else:
                get_logger().log(
                    f"  └ [VAD] {vad_model.upper()} 후처리 비활성: STT 선분할에는 사용하지 않습니다"
                )
            vad_model = "none"

        if vad_model != "none":
            # ✅ VAD 캐시 경로
            vad_cache_path = os.path.join(
                config.OUTPUT_DIR,
                f"{base_name}_vad_cache.json"
            )

            # ✅ cleaned_wav의 수정 시간 + 크기로 캐시 유효성 판단
            cache_valid = False
            if os.path.exists(vad_cache_path) and os.path.exists(cleaned_wav):
                try:
                    with open(vad_cache_path, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)
                    wav_stat = os.stat(cleaned_wav)
                    cache_config = self._vad_cache_config(s)
                    if (cache_data.get("wav_mtime") == wav_stat.st_mtime
                            and cache_data.get("wav_size") == wav_stat.st_size
                            and cache_data.get("vad_model") == vad_model
                            and cache_data.get("vad_cache_config") == cache_config
                            and not is_partial):
                        cache_valid = True
                except Exception:
                    pass

            if cache_valid:
                self._notify_stage(f"♻️ [VAD] {vad_model.upper()} 캐시 재사용")
                get_logger().log(f"  └ ♻️ [VAD 캐시] 이전 분석 결과를 재사용합니다.")
                vad_segments = cache_data.get("timestamps", [])

                import wave
                with wave.open(cleaned_wav, "r") as w:
                    total_dur = w.getnframes() / float(w.getframerate())

                grouped = self._build_grouped_chunks(vad_segments, total_dur, settings=s)
                self._write_grouped_chunks_parallel(cleaned_wav, chunk_dir, grouped)

                try:
                    with open(os.path.join(chunk_dir, "vad_strict.json"), "w", encoding="utf-8") as f:
                        json.dump(vad_segments, f)
                except Exception:
                    pass

                vad_success = True
                
            else:
                # ✅ VAD 새로 실행
                self._notify_stage(f"⏳ [VAD] {vad_model.upper()} 음성 섹터 스캔 중")
                get_logger().log(f"  └ [VAD 선분할] {vad_model.upper()} 음성 섹터 스캔 중...")
                vad_success, vad_segments = self._split_with_vad(
                    cleaned_wav, chunk_dir, vad_model, s,
                    target_start_sec, target_end_sec, is_single_segment
                )

                # ✅ 캐시 저장
                if vad_success and not is_partial:
                    try:
                        wav_stat = os.stat(cleaned_wav)
                        cache_obj = {
                            "wav_mtime": wav_stat.st_mtime,
                            "wav_size": wav_stat.st_size,
                            "vad_model": vad_model,
                            "vad_cache_config": self._vad_cache_config(s),
                            "timestamps": vad_segments
                        }
                        with open(vad_cache_path, "w", encoding="utf-8") as f:
                            json.dump(cache_obj, f)
                    except Exception:
                        pass

            if not vad_success:
                vad_empty_or_failed = True
                vad_model = "none"

        # VAD=none 또는 VAD 실패 시: 30초 단위 강제 분할
        if vad_model == "none":
            import wave
            existing_chunks = [f for f in os.listdir(chunk_dir) if f.endswith('.wav')]
            if not existing_chunks and os.path.exists(cleaned_wav):
                if vad_requested and vad_empty_or_failed and not s.get("allow_force_split_on_empty_vad", False):
                    stats = self._wav_activity_stats(cleaned_wav)
                    if not self._has_force_split_activity(stats, s):
                        get_logger().log(
                            "  └ [STT 준비] VAD 선분할 결과가 없고 오디오 에너지도 낮아 Whisper 청크 생성을 건너뜁니다 "
                            f"(peak {stats['peak']:.4f}, rms {stats['rms']:.4f}, 총 {stats['duration']:.1f}초)"
                        )
                        return chunk_dir, []
                    get_logger().log(
                        "  └ [STT 준비] VAD 선분할 결과는 없지만 오디오 에너지가 있어 고정 오버랩 청크를 생성합니다 "
                        f"(peak {stats['peak']:.4f}, rms {stats['rms']:.4f}, 총 {stats['duration']:.1f}초)"
                    )
                self._notify_stage("⏳ [STT 준비] Whisper 고정 오버랩 청크 분할 중")
                get_logger().log("  └ [STT 준비] Whisper 고정 오버랩 청크 분할 중...")
                try:
                    with wave.open(cleaned_wav, 'r') as wf:
                        total_dur = wf.getnframes() / float(wf.getframerate())
                    chunk_sec = max(10.0, float(s.get("ff_chunk", _CHUNK_DURATION)))
                    overlap_sec = self._chunk_overlap_sec(s)
                    grouped = self._split_range_with_overlap(0.0, total_dur, chunk_sec, overlap_sec)
                    self._write_grouped_chunks_parallel(cleaned_wav, chunk_dir, grouped)
                    get_logger().log(f"    → Whisper 청크 {len(grouped)}개 생성 완료 (overlap {overlap_sec:.1f}초, 총 {total_dur:.1f}초)")
                except Exception as e:
                    get_logger().log(f"  ⚠️ STT 청크 분할 실패: {e}")

        return chunk_dir, vad_segments

    def _has_force_split_activity(self, stats: dict, settings: dict | None = None) -> bool:
        settings = settings or {}
        try:
            min_peak = float(settings.get("empty_vad_force_split_min_peak", 0.04))
        except (TypeError, ValueError):
            min_peak = 0.04
        try:
            min_rms = float(settings.get("empty_vad_force_split_min_rms", 0.008))
        except (TypeError, ValueError):
            min_rms = 0.008
        peak = float(stats.get("peak", 0.0) or 0.0)
        rms = float(stats.get("rms", 0.0) or 0.0)
        return peak >= max(0.0, min_peak) or rms >= max(0.0, min_rms)

    def _wav_activity_stats(self, wav_path: str) -> dict:
        stats = {"duration": 0.0, "peak": 0.0, "rms": 0.0}
        try:
            from array import array
            with wave.open(wav_path, "rb") as wf:
                sample_width = wf.getsampwidth()
                frame_rate = max(1, int(wf.getframerate() or 1))
                channels = max(1, int(wf.getnchannels() or 1))
                total_frames = max(0, int(wf.getnframes() or 0))
                stats["duration"] = total_frames / float(frame_rate)
                if total_frames <= 0 or sample_width <= 0:
                    return stats

                max_sample = float((1 << (8 * sample_width - 1)) - 1) if sample_width > 1 else 128.0
                max_sample = max(max_sample, 1.0)
                total_samples = 0
                square_sum = 0.0
                peak = 0.0
                frames_per_read = max(1024, min(frame_rate, 65536))

                while True:
                    raw = wf.readframes(frames_per_read)
                    if not raw:
                        break
                    samples = []
                    if sample_width == 2:
                        usable = len(raw) - (len(raw) % 2)
                        values = array("h")
                        values.frombytes(raw[:usable])
                        if sys.byteorder != "little":
                            values.byteswap()
                        samples = values
                    else:
                        usable = len(raw) - (len(raw) % sample_width)
                        signed = sample_width > 1
                        for offset in range(0, usable, sample_width):
                            value = int.from_bytes(raw[offset:offset + sample_width], "little", signed=signed)
                            if sample_width == 1:
                                value -= 128
                            samples.append(value)
                    if not samples:
                        continue
                    total_samples += len(samples)
                    chunk_peak = max(abs(int(v)) for v in samples) / max_sample
                    peak = max(peak, chunk_peak)
                    square_sum += sum(float(v) * float(v) for v in samples) / (max_sample * max_sample)

                if total_samples > 0:
                    stats["rms"] = math.sqrt(square_sum / total_samples)
                stats["peak"] = peak
                if channels > 1:
                    stats["channels"] = channels
        except Exception as e:
            get_logger().log(f"  ⚠️ WAV 활동량 분석 실패: {e}")
        return stats

    def _vad_retry_timestamps_are_usable(self, raw_ts: list, sample_rate: int, total_dur: float) -> bool:
        if not raw_ts:
            return False
        duration = max(0.001, float(total_dur or 0.0))
        spans = []
        for ts in raw_ts:
            try:
                start = max(0.0, float(ts.get("start", 0)) / float(sample_rate))
                end = max(start, float(ts.get("end", 0)) / float(sample_rate))
            except (AttributeError, TypeError, ValueError):
                continue
            if end > start:
                spans.append((start, end))
        if not spans:
            return False

        total_voice = sum(end - start for start, end in spans)
        avg_voice = total_voice / max(1, len(spans))
        coverage = total_voice / duration
        min_total_voice = min(2.0, max(0.35, duration * 0.01))
        too_many_fragments = len(spans) > max(20, int(duration / 1.5))
        mostly_micro_fragments = avg_voice < 0.18

        if total_voice < min_total_voice:
            return False
        if mostly_micro_fragments:
            return False
        if too_many_fragments and avg_voice < 0.45:
            return False
        if coverage > 0.96 and len(spans) > 1:
            return False
        return True

    def _vad_flags_to_segments(
        self,
        flags: list[int],
        *,
        hop_sec: float,
        min_speech_sec: float,
        min_silence_sec: float,
        speech_pad_sec: float,
        source: str,
        for_post_stt_align: bool = False,
    ) -> list[dict]:
        raw: list[tuple[float, float]] = []
        start_idx = None
        for idx, flag in enumerate(flags):
            if flag and start_idx is None:
                start_idx = idx
            elif not flag and start_idx is not None:
                raw.append((start_idx * hop_sec, idx * hop_sec))
                start_idx = None
        if start_idx is not None:
            raw.append((start_idx * hop_sec, len(flags) * hop_sec))

        min_speech = max(0.0, float(min_speech_sec or 0.0))
        min_silence = max(0.0, float(min_silence_sec or 0.0))
        pad = max(0.0, float(speech_pad_sec or 0.0))
        merged: list[list[float]] = []
        for start, end in raw:
            if end - start < min_speech:
                continue
            start = max(0.0, start - pad)
            end = end + pad
            if merged and start - merged[-1][1] <= min_silence:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])

        return [
            {
                "start": round(start, 3),
                "end": round(max(start, end), 3),
                "source": source,
                "post_stt_align": bool(for_post_stt_align),
                "vad_word_filter": not bool(for_post_stt_align),
                "speech_pad_sec": round(pad, 3),
                "min_silence_sec": round(min_silence, 3),
            }
            for start, end in merged
            if end > start
        ]

    def _detect_ten_vad_timestamps(
        self,
        wav_path: str,
        vad_model: str,
        s: dict,
        *,
        for_post_stt_align: bool = False,
    ) -> list[dict]:
        try:
            import numpy as np
            from ten_vad import TenVad

            label = vad_model.upper()
            self._notify_stage(f"⏳ [VAD] {label} 모델 준비 중")
            get_logger().log(f"  └ [VAD 후처리] {label} 모델 준비 중...")
            effective_s = apply_review_vad_settings(s)
            hop_size = int(effective_s.get("ten_vad_hop_size", 256) or 256)
            threshold = float(effective_s.get("ten_vad_threshold", effective_s.get("vad_threshold", 0.5)) or 0.5)
            min_speech = float(effective_s.get("vad_min_speech", 0.25) or 0.25)
            min_silence = float(effective_s.get("vad_min_silence", 2.0) or 2.0)
            speech_pad = float(effective_s.get("vad_speech_pad", 0.2) or 0.2)

            self._notify_stage(f"⏳ [VAD] {label} 오디오 로드 중")
            get_logger().log(f"  └ [VAD 후처리] {label} 오디오 로드 중...")
            with wave.open(wav_path, "rb") as wav:
                sample_rate = wav.getframerate()
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                frames = wav.readframes(wav.getnframes())
            if sample_rate != 16000 or channels != 1 or sample_width != 2:
                get_logger().log(
                    "  ⚠️ TEN VAD는 16kHz mono int16 WAV만 지원합니다. Silero VAD로 계속 진행합니다"
                )
                return []

            audio = np.frombuffer(frames, dtype=np.int16)
            frame_count = len(audio) // hop_size
            if frame_count <= 0:
                return []

            detector = TenVad(hop_size, threshold)
            flags: list[int] = []
            state = getattr(self, "_vad_progress_state", {})
            state.pop(f"{label}:오디오 스캔", None)
            self._vad_progress_state = state
            self._emit_vad_progress(label, "오디오 스캔", 0, force=True)
            for idx in range(frame_count):
                frame = np.ascontiguousarray(audio[idx * hop_size:(idx + 1) * hop_size])
                _probability, flag = detector.process(frame)
                flags.append(int(flag))
                if frame_count >= 10:
                    self._emit_vad_progress(label, "오디오 스캔", int(((idx + 1) / frame_count) * 100), step=10)
            self._emit_vad_progress(label, "오디오 스캔", 100, force=True)
            self._notify_stage(f"⏳ [VAD] {label} 음성 구간 정리 중")
            get_logger().log(f"  └ [VAD 후처리] {label} 음성 구간 정리 중...")
            return self._vad_flags_to_segments(
                flags,
                hop_sec=hop_size / 16000.0,
                min_speech_sec=min_speech,
                min_silence_sec=min_silence,
                speech_pad_sec=speech_pad,
                source=vad_model,
                for_post_stt_align=for_post_stt_align,
            )
        except Exception as e:
            get_logger().log(f"  ⚠️ TEN VAD 실행 실패 또는 미설치: {e}")
            return []

    @staticmethod
    def _filter_vad_timestamps_for_range(
        timestamps: list[dict],
        target_start_sec=0.0,
        target_end_sec=None,
        is_single_segment=False,
    ) -> list[dict]:
        out = list(timestamps or [])
        if target_start_sec > 0.0 or target_end_sec is not None:
            filtered = []
            end_limit = target_end_sec if target_end_sec is not None else 99999.0
            for item in out:
                t = dict(item)
                if t["start"] >= end_limit:
                    continue
                if t["end"] <= target_start_sec:
                    continue
                if is_single_segment:
                    t["start"] = max(target_start_sec, t["start"])
                    t["end"] = min(end_limit, t["end"])
                else:
                    t["start"] = max(target_start_sec, t["start"])
                if t["end"] > t["start"]:
                    filtered.append(t)
            out = filtered
        if out and out[0]["start"] < 3.0:
            out[0]["start"] = 0.0
        return out

    def _detect_vad_timestamps(
        self,
        wav_path: str,
        vad_model: str,
        s: dict,
        target_start_sec=0.0,
        target_end_sec=None,
        is_single_segment=False,
        *,
        for_post_stt_align: bool = False,
    ) -> list[dict]:
        try:
            if vad_model == "ten_vad":
                timestamps = self._detect_ten_vad_timestamps(
                    wav_path,
                    vad_model,
                    s,
                    for_post_stt_align=for_post_stt_align,
                )
                if timestamps:
                    return self._filter_vad_timestamps_for_range(
                        timestamps,
                        target_start_sec,
                        target_end_sec,
                        is_single_segment,
                    )
                get_logger().log("  ⚠️ TEN VAD 결과가 없어 Silero VAD로 재시도합니다")
                vad_model = "silero"

            import torch

            effective_s = apply_review_vad_settings(s)
            label = vad_model.upper()
            if not self._vad_loaded:
                self._notify_stage(f"⏳ [VAD] {label} 모델 준비 중")
                get_logger().log(f"  └ [VAD 후처리] {label} 모델 준비 중...")
                heartbeat = self._start_vad_heartbeat(label, "모델 준비")
                try:
                    self._vad_model, self._vad_utils = torch.hub.load(
                        repo_or_dir="snakers4/silero-vad",
                        model="silero_vad",
                        force_reload=False,
                        onnx=False,
                    )
                finally:
                    self._stop_vad_heartbeat(heartbeat)
                self._vad_loaded = True
                get_logger().log(f"  └ [VAD 후처리] {label} 모델 준비 완료")

            model = self._vad_model
            utils = self._vad_utils
            (get_speech_timestamps, _, read_audio, _, _) = utils
            v_thresh = float(effective_s.get("vad_threshold", 0.5))
            v_min_sp = int(float(effective_s.get("vad_min_speech", 0.25)) * 1000)
            v_min_sil = int(float(effective_s.get("vad_min_silence", 2.0)) * 1000)
            v_pad_ms = int(float(effective_s.get("vad_speech_pad", 0.2)) * 1000)
            v_window = int(effective_s.get("vad_window_size", 512) or 512)

            self._notify_stage(f"⏳ [VAD] {label} 오디오 로드 중")
            get_logger().log(f"  └ [VAD 후처리] {label} 오디오 로드 중...")
            audio_data = read_audio(wav_path)
            get_logger().log(f"  └ [VAD 후처리] {label} 오디오 로드 완료")
            self._notify_stage(f"⏳ [VAD] {label} 오디오 분석 중")
            get_logger().log(f"  └ [VAD 후처리] {label} 오디오 분석 중...")
            heartbeat = self._start_vad_heartbeat(label, "오디오 분석")
            try:
                raw_ts = get_speech_timestamps(
                    audio_data,
                    model,
                    sampling_rate=16000,
                    threshold=v_thresh,
                    min_speech_duration_ms=v_min_sp,
                    min_silence_duration_ms=v_min_sil,
                    speech_pad_ms=v_pad_ms,
                    window_size_samples=v_window,
                )
            finally:
                self._stop_vad_heartbeat(heartbeat)
            stats = None
            if not raw_ts:
                stats = self._wav_activity_stats(wav_path)
                if self._has_force_split_activity(stats, s):
                    retry_profiles = [
                        (
                            max(0.30, min(0.40, v_thresh - 0.12 if v_thresh > 0.45 else v_thresh * 0.82)),
                            max(120, min(v_min_sp, 160)),
                            max(450, min(v_min_sil, 600)),
                            max(v_pad_ms, 200),
                        ),
                        (
                            max(0.24, min(0.34, v_thresh * 0.62)),
                            max(100, min(v_min_sp, 130)),
                            max(320, min(v_min_sil, 450)),
                            max(v_pad_ms, 250),
                        ),
                        (
                            max(0.20, min(0.28, v_thresh * 0.50)),
                            max(90, min(v_min_sp, 110)),
                            max(240, min(v_min_sil, 340)),
                            max(v_pad_ms, 300),
                        ),
                    ]
                    for retry_idx, (retry_thresh, retry_min_sp, retry_min_sil, retry_pad_ms) in enumerate(retry_profiles, 1):
                        self._notify_stage(f"⏳ [VAD] {label} 오디오 분석 재시도 {retry_idx}/3")
                        get_logger().log(f"  └ [VAD 후처리] {label} 오디오 분석 재시도 {retry_idx}/3")
                        heartbeat = self._start_vad_heartbeat(label, f"재시도 {retry_idx}/3")
                        try:
                            raw_ts = get_speech_timestamps(
                                audio_data,
                                model,
                                sampling_rate=16000,
                                threshold=retry_thresh,
                                min_speech_duration_ms=retry_min_sp,
                                min_silence_duration_ms=retry_min_sil,
                                speech_pad_ms=retry_pad_ms,
                                window_size_samples=v_window,
                            )
                        finally:
                            self._stop_vad_heartbeat(heartbeat)
                        if raw_ts and self._vad_retry_timestamps_are_usable(raw_ts, 16000, stats.get("duration", 0.0)):
                            get_logger().log(f"  └ [VAD 후처리] 재시도 {retry_idx}회차로 음성 위치 확보")
                            break
                        raw_ts = []

            self._notify_stage(f"⏳ [VAD] {label} 음성 구간 정리 중")
            get_logger().log(f"  └ [VAD 후처리] {label} 음성 구간 정리 중...")
            timestamps = [
                {
                    "start": t["start"] / 16000.0,
                    "end": t["end"] / 16000.0,
                    "source": vad_model,
                    "post_stt_align": bool(for_post_stt_align),
                    "vad_word_filter": not bool(for_post_stt_align),
                    "speech_pad_sec": round(v_pad_ms / 1000.0, 3),
                    "min_silence_sec": round(v_min_sil / 1000.0, 3),
                }
                for t in raw_ts
            ]

            if target_start_sec > 0.0 or target_end_sec is not None:
                filtered = []
                end_limit = target_end_sec if target_end_sec is not None else 99999.0
                for t in timestamps:
                    if t["start"] >= end_limit:
                        continue
                    if t["end"] <= target_start_sec:
                        continue
                    t = dict(t)
                    if is_single_segment:
                        t["start"] = max(target_start_sec, t["start"])
                        t["end"] = min(end_limit, t["end"])
                    else:
                        t["start"] = max(target_start_sec, t["start"])
                    if t["end"] > t["start"]:
                        filtered.append(t)
                timestamps = filtered

            if timestamps and timestamps[0]["start"] < 3.0:
                timestamps[0]["start"] = 0.0
            return timestamps
        except Exception as e:
            get_logger().log(f"⚠️ VAD 후처리 분석 오류: {e}")
            return []

    # 💡 [STEP 3] VAD 분할기 (들여쓰기 및 8개 인자 완벽 교정)
    # [core/media_processor.py] _split_with_vad 함수 전체 교체
    def _split_with_vad(self, wav_path: str, chunk_dir: str, vad_model: str, s: dict, target_start_sec=0.0, target_end_sec=None, is_single_segment=False):
        try:
            effective_s = apply_review_vad_settings(s)
            vad_cfg = review_vad_config(s)
            if vad_cfg["review_vad_before_stt_enabled"] and vad_cfg["review_vad_strict_mode"]:
                get_logger().log(
                    "  └ 🧪 자막 품질 검수 VAD: "
                    f"pad {vad_cfg['review_vad_speech_pad_sec']:.2f}s / "
                    f"min silence {vad_cfg['review_vad_min_silence_sec']:.2f}s"
                )
            if vad_model == "ten_vad":
                timestamps = self._detect_ten_vad_timestamps(wav_path, vad_model, s)
                if timestamps:
                    timestamps = self._filter_vad_timestamps_for_range(
                        timestamps,
                        target_start_sec,
                        target_end_sec,
                        is_single_segment,
                    )
                    if not timestamps:
                        get_logger().log("⚠️ 해당 구간에서 유효한 TEN VAD 음성 신호를 찾지 못했습니다.")
                        return False, []
                    with wave.open(wav_path, "r") as w:
                        total_dur = w.getnframes() / float(w.getframerate())
                    get_logger().log("📢 [TEN VAD 선분할] 음성 섹터 분리가 완료되었습니다.")
                    for i, ts in enumerate(timestamps):
                        sm, ss = divmod(ts["start"], 60)
                        get_logger().log(f"  [{int(sm):02d}:{ss:05.2f}] 음성섹터{i+1} 확보 완료")
                    grouped = self._build_grouped_chunks(
                        timestamps,
                        total_dur,
                        max_chunk_dur=max(10.0, float(s.get("ff_chunk", _CHUNK_DURATION))),
                        margin=1.0,
                        gap_merge_limit=3.0,
                        settings=s,
                    )
                    self._write_grouped_chunks_parallel(wav_path, chunk_dir, grouped)
                    try:
                        with open(os.path.join(chunk_dir, "vad_strict.json"), "w", encoding="utf-8") as f:
                            json.dump(timestamps, f)
                    except Exception:
                        pass
                    return True, timestamps
                get_logger().log("  ⚠️ TEN VAD 결과가 없어 Silero VAD로 재시도합니다")
                vad_model = "silero"

            import torch
            if not self._vad_loaded:
                self._vad_model, self._vad_utils = torch.hub.load(
                    repo_or_dir="snakers4/silero-vad",
                    model="silero_vad",
                    force_reload=False,
                    onnx=False
                )
                self._vad_loaded = True

            model = self._vad_model
            utils = self._vad_utils
            (get_speech_timestamps, _, read_audio, _, _) = utils
            
            v_thresh = float(effective_s.get("vad_threshold", 0.5))
            v_min_sp = int(float(effective_s.get("vad_min_speech", 0.25)) * 1000)
            v_min_sil = int(float(effective_s.get("vad_min_silence", 2.0)) * 1000)
            v_pad_ms = int(float(effective_s.get("vad_speech_pad", 0.2)) * 1000)
            v_window = int(effective_s.get("vad_window_size", 512) or 512)
            
            audio_data = read_audio(wav_path)
            raw_ts = get_speech_timestamps(
                audio_data, model, sampling_rate=16000, threshold=v_thresh, 
                min_speech_duration_ms=v_min_sp, min_silence_duration_ms=v_min_sil,
                speech_pad_ms=v_pad_ms, window_size_samples=v_window
            )
            stats = None
            if not raw_ts:
                stats = self._wav_activity_stats(wav_path)
                if self._has_force_split_activity(stats, s):
                    retry_profiles = [
                        (
                            max(0.30, min(0.40, v_thresh - 0.12 if v_thresh > 0.45 else v_thresh * 0.82)),
                            max(120, min(v_min_sp, 160)),
                            max(450, min(v_min_sil, 600)),
                            max(v_pad_ms, 200),
                        ),
                        (
                            max(0.24, min(0.34, v_thresh * 0.62)),
                            max(100, min(v_min_sp, 130)),
                            max(320, min(v_min_sil, 450)),
                            max(v_pad_ms, 250),
                        ),
                        (
                            max(0.20, min(0.28, v_thresh * 0.50)),
                            max(90, min(v_min_sp, 110)),
                            max(240, min(v_min_sil, 340)),
                            max(v_pad_ms, 300),
                        ),
                    ]
                    prev_thresh, prev_min_sp, prev_min_sil = v_thresh, v_min_sp, v_min_sil
                    for retry_idx, (retry_thresh, retry_min_sp, retry_min_sil, retry_pad_ms) in enumerate(retry_profiles, 1):
                        get_logger().log(
                            f"  └ 🔁 VAD {retry_idx}차 무검출: 오디오 에너지가 있어 민감도 낮춰 재시도 "
                            f"(threshold {prev_thresh:.2f}→{retry_thresh:.2f}, "
                            f"min speech {prev_min_sp}→{retry_min_sp}ms, "
                            f"min silence {prev_min_sil}→{retry_min_sil}ms, "
                            f"peak {stats['peak']:.4f}, rms {stats['rms']:.4f})"
                        )
                        raw_ts = get_speech_timestamps(
                            audio_data, model, sampling_rate=16000, threshold=retry_thresh,
                            min_speech_duration_ms=retry_min_sp, min_silence_duration_ms=retry_min_sil,
                            speech_pad_ms=retry_pad_ms, window_size_samples=v_window
                        )
                        if raw_ts:
                            if self._vad_retry_timestamps_are_usable(raw_ts, 16000, stats.get("duration", 0.0)):
                                get_logger().log(f"  └ ✅ VAD 재시도 {retry_idx}회차로 음성 섹터 {len(raw_ts)}개 확보")
                                break
                            get_logger().log(
                                f"  └ ⚠️ VAD 재시도 {retry_idx}회차 결과가 너무 잘게 잡혀 폐기합니다 "
                                f"({len(raw_ts)}개 섹터)"
                            )
                            raw_ts = []
                        prev_thresh, prev_min_sp, prev_min_sil = retry_thresh, retry_min_sp, retry_min_sil
                else:
                    get_logger().log(
                        "  └ 🔇 VAD 1차 무검출: 오디오 에너지도 낮아 민감도 재시도를 생략합니다 "
                        f"(threshold {v_thresh:.2f}, peak {stats['peak']:.4f}, rms {stats['rms']:.4f})"
                    )
            timestamps = [
                {
                    "start": t["start"] / 16000.0,
                    "end": t["end"] / 16000.0,
                    "source": vad_model,
                    "review_vad": bool(vad_cfg["review_vad_before_stt_enabled"]),
                    "speech_pad_sec": round(v_pad_ms / 1000.0, 3),
                    "min_silence_sec": round(v_min_sil / 1000.0, 3),
                }
                for t in raw_ts
            ]
            
            # 구간 필터링 및 단일 세그먼트 보호 로직
            if target_start_sec > 0.0 or target_end_sec is not None:
                end_limit_log = target_end_sec if target_end_sec is not None else 99999.0
                get_logger().log(f"\n🎯 [구간 정찰] {target_start_sec:.1f}초 ~ {end_limit_log if end_limit_log < 90000 else '끝'} 구간의 음성을 분석합니다.")
                
                filtered_timestamps = []
                end_limit = target_end_sec if target_end_sec is not None else 99999.0
                for t in timestamps:
                    if t["start"] >= end_limit: continue
                    if t["end"] <= target_start_sec: continue
                    
                    if is_single_segment:
                        t["start"] = max(target_start_sec, t["start"])
                        t["end"] = min(end_limit, t["end"])
                    else:
                        t["start"] = max(target_start_sec, t["start"])
                        
                    filtered_timestamps.append(t)
                timestamps = filtered_timestamps
                
            if not timestamps:
                get_logger().log("⚠️ 해당 구간에서 유효한 음성 신호를 찾지 못했습니다.")
                return False, []

            with wave.open(wav_path, "r") as w: 
                total_dur = w.getnframes() / float(w.getframerate())
                
            if timestamps and timestamps[0]["start"] < 3.0: 
                timestamps[0]["start"] = 0.0

            get_logger().log("📢 [VAD 선분할] 음성 섹터 분리가 완료되었습니다.")
            for i, ts in enumerate(timestamps):
                sm, ss = divmod(ts["start"], 60)
                em, es = divmod(ts["end"], 60)
                get_logger().log(f"  [{int(sm):02d}:{ss:05.2f}] 음성섹터{i+1} 확보 완료")
            
            grouped = self._build_grouped_chunks(
                timestamps,
                total_dur,
                max_chunk_dur=max(10.0, float(s.get("ff_chunk", _CHUNK_DURATION))),
                margin=1.0,
                gap_merge_limit=3.0,
                settings=s
            )
            self._write_grouped_chunks_parallel(wav_path, chunk_dir, grouped)

            try:
                with open(os.path.join(chunk_dir, "vad_strict.json"), "w", encoding="utf-8") as f:
                    json.dump(timestamps, f)
            except: pass

            return True, timestamps

        except Exception as e:
            get_logger().log(f"⚠️ VAD 오류: {e}")
            return False, []

    def __del__(self):
        try: self._executor.shutdown(wait=False)
        except: pass

    def _load_all_settings(self):
        """user_settings.json 로드 (오류 시 로그 남김). fast-mode override 지원."""
        settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")

        data = dict(getattr(config, "DEFAULT_ADV_SETTINGS", {}) or {})
        if not os.path.exists(settings_path):
            pass
        else:
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    get_logger().log("⚠️ user_settings.json 형식 오류: dict 아님")
                    loaded = {}
                data.update(loaded)
            except Exception as e:
                get_logger().log(f"⚠️ user_settings.json 로드 실패: {e}")

        preset_name = str(data.get("audio_preset", "") or "")
        if preset_name:
            try:
                data = apply_audio_preset(data, preset_name)
            except Exception as e:
                get_logger().log(f"⚠️ 오디오 프리셋 적용 실패({preset_name}): {e}")
        # 빠른모드 오버라이드: _fast_mode_overrides가 있으면 적용
        overrides = getattr(self, '_fast_mode_overrides', None)
        if overrides and isinstance(overrides, dict):
            data.update(overrides)
        return data

    def clear_fast_mode_overrides(self):
        """빠른모드 오버라이드 제거 — 품질모드/멀티클립 진입 시 호출"""
        self._fast_mode_overrides = None

    def _collect_transcribe_result(
        self,
        chunk_dir: str,
        model: str,
        target_end_sec: float = None,
        is_single: bool = False,
        label: str = "STT",
        preview_callback=None,
    ) -> list[dict]:
        worker = VideoProcessor()
        worker.language = self.language
        children = getattr(self, "_ensemble_child_processors", None)
        if not isinstance(children, list):
            children = []
            self._ensemble_child_processors = children
        children.append(worker)
        result: list[dict] = []
        try:
            for chunk_segs, _idx, _total in worker.transcribe(
                chunk_dir,
                is_fast_mode=False,
                target_end_sec=target_end_sec,
                is_single=is_single,
                model_override=model,
                cleanup_chunk_dir=False,
                log_label=label,
                preview_callback=preview_callback,
            ):
                result.extend(chunk_segs or [])
        finally:
            worker.stop_transcribe()
            try:
                children.remove(worker)
            except ValueError:
                pass
        return result

    def transcribe_ensemble(
        self,
        chunk_dir: str,
        target_end_sec: float = None,
        is_single: bool = False,
        preview_callback=None,
    ):
        s = self._load_all_settings()
        primary_model = s.get("selected_whisper_model", self.whisper_model)
        secondary_model = s.get("selected_whisper_model_secondary", "")
        if not secondary_model or secondary_model == primary_model:
            yield from self.transcribe(
                chunk_dir,
                is_fast_mode=False,
                target_end_sec=target_end_sec,
                is_single=is_single,
                model_override=primary_model,
                cleanup_chunk_dir=True,
                log_label="STT1",
                preview_callback=preview_callback,
            )
            return

        get_logger().log(
            "\n🎧 [STT 앙상블] STT1/STT2 병렬 인식 시작 "
            f"(STT1: {primary_model.split(chr(47))[-1]}, STT2: {secondary_model.split(chr(47))[-1]})"
        )
        self._notify_stage("⏳ [STT] STT1/STT2 병렬 인식 중")
        results: dict[str, list[dict]] = {"STT1": [], "STT2": []}
        errors: dict[str, BaseException] = {}

        def _run(label: str, model: str):
            try:
                results[label] = self._collect_transcribe_result(
                    chunk_dir,
                    model,
                    target_end_sec=target_end_sec,
                    is_single=is_single,
                    label=label,
                    preview_callback=preview_callback if label == "STT1" else None,
                )
            except BaseException as exc:
                errors[label] = exc

        t1 = threading.Thread(target=_run, args=("STT1", primary_model), daemon=True, name="stt-ensemble-1")
        t2 = threading.Thread(target=_run, args=("STT2", secondary_model), daemon=True, name="stt-ensemble-2")
        try:
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            for label, exc in errors.items():
                get_logger().log(f"  ⚠️ [STT 앙상블] {label} 인식 실패: {exc}")
            if not results["STT1"] and not results["STT2"]:
                raise RuntimeError("STT 앙상블 결과가 비어 있습니다")
            from core.audio.stt_ensemble import merge_stt_outputs

            merged = merge_stt_outputs(results["STT1"], results["STT2"])
            vad_strict = []
            vad_json = os.path.join(chunk_dir, "vad_strict.json")
            if os.path.exists(vad_json):
                try:
                    with open(vad_json, "r", encoding="utf-8") as f:
                        vad_strict = json.load(f)
                except Exception:
                    vad_strict = []
            if vad_strict and bool(s.get("vad_post_stt_align_enabled", True)):
                from core.subtitle_quality.vad_alignment_checker import adjust_segments_to_vad_boundaries

                self._notify_stage("⏳ [VAD] 앙상블 자막 위치 재계산 중")
                merged, adjusted_count = adjust_segments_to_vad_boundaries(
                    merged,
                    vad_strict,
                    max_shift_sec=float(s.get("vad_post_stt_max_shift_sec", 0.7) or 0.7),
                    edge_pad_sec=float(s.get("vad_post_stt_edge_pad_sec", 0.04) or 0.04),
                )
                get_logger().log(f"  🎯 [VAD 후처리] 앙상블 자막 위치 {adjusted_count}개 보정")
            get_logger().log(
                "  ✅ [STT 앙상블] 후보 병합 완료 "
                f"(STT1 {len(results['STT1'])}개 / STT2 {len(results['STT2'])}개 → {len(merged)}개, "
                "단어 단위 ROVER · 저신뢰 STT1 구간 STT2 보강)"
            )
            yield merged, 1, 1
        finally:
            shutil.rmtree(chunk_dir, ignore_errors=True)

    def transcribe(
        self,
        chunk_dir: str,
        is_fast_mode: bool = False,
        target_end_sec: float = None,
        is_single: bool = False,
        model_override: str | None = None,
        cleanup_chunk_dir: bool = True,
        log_label: str = "STT",
        preview_callback=None,
    ):
        chunks = sorted([f for f in os.listdir(chunk_dir) if f.endswith(".wav")])
        if not chunks:
            yield [], 0, 0
            return

        vad_strict = []
        vad_json = os.path.join(chunk_dir, "vad_strict.json")
        if os.path.exists(vad_json):
            try:
                with open(vad_json, "r", encoding="utf-8") as f:
                    vad_strict = json.load(f)
            except Exception:
                pass

        total = len(chunks)
        _s = self._load_all_settings()
        if model_override is None and bool(_s.get("stt_ensemble_enabled", False)):
            yield from self.transcribe_ensemble(
                chunk_dir,
                target_end_sec=target_end_sec,
                is_single=is_single,
                preview_callback=preview_callback,
            )
            return
        target_model = model_override or _s.get("selected_whisper_model", self.whisper_model)
        self._notify_stage(f"⏳ [{log_label}] Whisper 인식 중")
        get_logger().log(f"\n🎯 [{log_label}] Whisper 인식 시작 (총 {total}블록, 모델: {target_model.split(chr(47))[-1]})")

        t_sec = 1.0
        q = []
        for i, cf in enumerate(chunks):
            cp = os.path.join(chunk_dir, cf)
            m = re.search(r'vad_\d+_([\d\.]+)\.wav', cf)
            ov_start = float(m.group(1)) if m else i * 30.0
            q.append({
                "idx": i,
                "input_path": cp,
                "ov_start_offset": ov_start
            })
            if i == len(chunks) - 1:
                try:
                    with wave.open(cp, "r") as w:
                        t_sec = ov_start + (w.getnframes() / float(w.getframerate()))
                except Exception:
                    t_sec = ov_start + 30.0

        safe_paths = [x["input_path"] for x in q]
        s = self._load_all_settings()
        temp_max = float(s.get("w_none_temp_max", 0.4))
        temperature_values = [round(x * 0.2, 1) for x in range(int(temp_max / 0.2) + 1)]
        temperature_tuple = "(" + ", ".join(str(x) for x in temperature_values) + ",)"

        import config as _cfg

        mac_task_id = None
        from core.audio.whisper_coreml import is_coreml_whisper_model
        from core.audio.whisper_transformers import is_transformers_whisper_model

        use_coreml_whisper = is_coreml_whisper_model(target_model)
        use_transformers_whisper = is_transformers_whisper_model(target_model)
        if use_coreml_whisper:
            from core.audio.whisper_coreml import run_whisper
            proc = run_whisper(
                chunk_paths=safe_paths,
                model=target_model,
                language=self.language,
                temperature_tuple=temperature_tuple,
                log_label=log_label,
            )
            if proc is None:
                fallback_model = "mlx-community/whisper-large-v3-turbo"
                get_logger().log(f"  ↩️ [{log_label}] Core ML STT 준비 안 됨 → MLX fallback: {fallback_model}")
                target_model = fallback_model
                use_coreml_whisper = False
        if use_transformers_whisper:
            from core.audio.whisper_transformers import run_whisper
            proc = run_whisper(
                chunk_paths=safe_paths,
                model=target_model,
                language=self.language,
                temperature_tuple=temperature_tuple,
                log_label=log_label,
            )
            if proc is None:
                get_logger().log("❌ Transformers Whisper 백엔드를 실행할 수 없습니다.")
                return
        elif use_coreml_whisper:
            pass
        elif _cfg.IS_MAC:
            from core.audio.whisper_mlx import ensure_worker, submit_task

            with self._whisper_lock:
                self._whisper_runner_proc = ensure_worker(self._whisper_runner_proc)
                proc = self._whisper_runner_proc
                mac_task_id = submit_task(
                    proc=proc,
                    chunk_paths=safe_paths,
                    model=target_model,
                    language=self.language,
                    temperature_values=temperature_values
                )
        else:
            from core.audio.whisper_faster import run_whisper
            proc = run_whisper(
                chunk_paths=safe_paths,
                model=target_model,
                language=self.language,
                temperature_tuple=temperature_tuple,
                log_label=log_label,
            )
            if proc is None:
                get_logger().log("❌ Whisper 백엔드를 실행할 수 없습니다.")
                return

        self._whisper_proc = proc
        prev_end = 0.0
        had_error = False
        processed_count = 0

        try:
            if _cfg.IS_MAC and not use_coreml_whisper and not use_transformers_whisper:
                received = 0
                while received < total:
                    line = proc.stdout.readline()
                    if not line:
                        break

                    data = _parse_worker_json_line(line)
                    if data is None:
                        continue

                    if data.get("task_id") != mac_task_id:
                        continue
                    if data.get("done"):
                        break

                    if data.get("fatal_error") or data.get("error"):
                        had_error = True
                        msg = data.get("fatal_error") or data.get("error") or "unknown whisper worker error"
                        stage = data.get("stage", "worker")
                        get_logger().log(f"  [FAIL] Whisper worker error ({stage}): {msg}")
                        raise RuntimeError(f"whisper_worker_error[{stage}]: {msg}")

                    idx = int(data.get("index", received))
                    item = q[idx]
                    payload = data.get("result") if "result" in data else {"error": data.get("error", "")}
                    if isinstance(payload, dict):
                        payload.setdefault("backend", data.get("backend", "mlx-whisper"))
                        payload.setdefault("language_probability", data.get("language_probability"))
                        payload.setdefault("chunk_path", item.get("input_path"))
                    chunk_segs = self._parse_whisper_payload(
                        payload,
                        item,
                        vad_strict,
                        target_end_sec=target_end_sec,
                        is_single=is_single
                    )
                    chunk_segs = self._dedupe_overlapping_segments(
                        chunk_segs,
                        previous_end=prev_end,
                        dedup_window=float(s.get("sub_dedup_window", 0.5) or 0.5),
                        vad_segments=vad_strict,
                    )

                    if chunk_segs:
                        prev_end = chunk_segs[-1]["end"]
                        if callable(preview_callback):
                            try:
                                preview_callback(chunk_segs, log_label)
                            except Exception:
                                pass

                    pct = min(100, int((prev_end / t_sec) * 100))
                    get_logger().log(self._format_transcribe_progress(log_label, prev_end, t_sec, pct))

                    yield chunk_segs, item["idx"] + 1, total
                    processed_count += 1
                    received += 1

            else:
                for item in q:
                    line = proc.stdout.readline()
                    if not line:
                        break

                    data = _parse_worker_json_line(line)
                    if data is None:
                        continue

                    if data.get("fatal_error") or data.get("error"):
                        had_error = True
                        msg = data.get("fatal_error") or data.get("error") or "unknown whisper worker error"
                        stage = data.get("stage", "worker")
                        get_logger().log(f"  [FAIL] Whisper worker error ({stage}): {msg}")
                        raise RuntimeError(f"whisper_worker_error[{stage}]: {msg}")

                    chunk_segs = self._parse_whisper_payload(
                        data,
                        item,
                        vad_strict,
                        target_end_sec=target_end_sec,
                        is_single=is_single
                    )
                    chunk_segs = self._dedupe_overlapping_segments(
                        chunk_segs,
                        previous_end=prev_end,
                        dedup_window=float(s.get("sub_dedup_window", 0.5) or 0.5),
                        vad_segments=vad_strict,
                    )

                    if chunk_segs:
                        prev_end = chunk_segs[-1]["end"]
                        if callable(preview_callback):
                            try:
                                preview_callback(chunk_segs, log_label)
                            except Exception:
                                pass

                    pct = min(100, int((prev_end / t_sec) * 100))
                    get_logger().log(self._format_transcribe_progress(log_label, prev_end, t_sec, pct))
                    yield chunk_segs, item["idx"] + 1, total
                    processed_count += 1

                proc.wait()
                if proc.returncode not in (0, None):
                    had_error = True
                    raise RuntimeError(f"whisper_worker_exit_code={proc.returncode}")
                if processed_count == 0 and total > 0:
                    had_error = True
                    raise RuntimeError("whisper produced 0 chunks")

        finally:
            self._whisper_proc = None
            if cleanup_chunk_dir:
                shutil.rmtree(chunk_dir, ignore_errors=True)
            if had_error:
                get_logger().log(f"[WARN] {log_label} Whisper transcription aborted due to worker failure")
            else:
                get_logger().log(f"[DONE] {log_label} Whisper transcription completed")

    @staticmethod
    def _format_transcribe_progress(log_label: str, current_sec: float, total_sec: float, pct: int) -> str:
        label = (log_label or "STT").strip() or "STT"
        return (
            f"  ▶ [{label}] 진행 상황: {int(current_sec // 60):02d}분 {int(current_sec % 60):02d}초 / "
            f"{int(total_sec // 60):02d}분 {int(total_sec % 60):02d}초 ({int(pct)}%)"
        )

    def stop_transcribe(self):
        try:
            for child in list(getattr(self, "_ensemble_child_processors", []) or []):
                try:
                    child.stop_transcribe()
                except Exception:
                    pass

            import config as _cfg

            if _cfg.IS_MAC:
                from core.audio.whisper_mlx import stop_worker
                with self._whisper_lock:
                    if self._whisper_runner_proc:
                        stop_worker(self._whisper_runner_proc)
                        self._whisper_runner_proc = None
                    self._whisper_proc = None
                return

            if self._whisper_proc and self._whisper_proc.poll() is None:
                self._whisper_proc.terminate()
                try:
                    self._whisper_proc.wait(timeout=2)
                except Exception:
                    self._whisper_proc.kill()

        except Exception:
            pass
        finally:
            self._whisper_proc = None

    def release_runtime_models(self):
        self.stop_transcribe()
        try:
            for child in list(getattr(self, "_ensemble_child_processors", []) or []):
                try:
                    if hasattr(child, "release_runtime_models"):
                        child.release_runtime_models()
                except Exception:
                    pass
            self._ensemble_child_processors = []
        except Exception:
            pass
        try:
            self._vad_model = None
            self._vad_utils = None
            self._vad_loaded = False
        except Exception:
            pass
        try:
            import gc

            gc.collect()
        except Exception:
            pass
        try:
            import torch

            if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                torch.mps.empty_cache()
            if hasattr(torch, "cuda") and torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass


    def _ffmpeg_trim_to_wav(self, src_wav: str, out_wav: str, start_sec: float, duration_sec: float) -> bool:
        result = subprocess.run(
            [
                ffmpeg_binary(), "-y", "-nostdin", "-loglevel", "error",
                "-ss", str(start_sec),
                "-t", str(duration_sec),
                "-i", src_wav,
                "-acodec", "pcm_s16le",
                out_wav,
            ],
            capture_output=True,
            **hidden_subprocess_kwargs(),
        )
        return result.returncode == 0 and os.path.exists(out_wav) and os.path.getsize(out_wav) > 0
    
    def _chunk_overlap_sec(self, settings: dict | None = None) -> float:
        settings = settings or {}
        try:
            overlap = float(settings.get("whisper_chunk_overlap_sec", _OVERLAP_SEC))
        except (TypeError, ValueError):
            overlap = _OVERLAP_SEC
        if settings.get("subtitle_quality_enabled") or settings.get("subtitle_quality_auto_check_after_generate"):
            overlap = max(overlap, 3.0)
        return max(0.0, min(8.0, overlap))

    def _split_range_with_overlap(self, start: float, end: float, max_chunk_dur: float, overlap_sec: float) -> list[dict]:
        start = max(0.0, float(start or 0.0))
        end = max(start, float(end or start))
        max_chunk_dur = max(1.0, float(max_chunk_dur or _CHUNK_DURATION))
        overlap_sec = max(0.0, min(float(overlap_sec or 0.0), max_chunk_dur / 2.0))
        if end <= start:
            return []
        if end - start <= max_chunk_dur:
            return [{"start": start, "end": end}]

        grouped = []
        cursor = start
        step = max(0.5, max_chunk_dur - overlap_sec)
        while cursor < end:
            chunk_end = min(end, cursor + max_chunk_dur)
            grouped.append({"start": round(cursor, 3), "end": round(chunk_end, 3)})
            if chunk_end >= end:
                break
            cursor = min(end, cursor + step)
        return grouped

    def _build_grouped_chunks(self, timestamps: list[dict], total_dur: float,
                          max_chunk_dur: float = 30.0, margin: float = 1.0,
                          gap_merge_limit: float = 3.0, settings: dict | None = None) -> list[dict]:
        overlap_sec = self._chunk_overlap_sec(settings)
        if review_vad_enabled(settings):
            cfg = review_vad_config(settings)
            margin = min(float(margin), max(0.0, float(cfg["review_vad_speech_pad_sec"])))
            gap_merge_limit = min(float(gap_merge_limit), max(0.1, float(cfg["review_vad_min_silence_sec"])))
        merged_sectors = []
        for ts in timestamps:
            s = max(0.0, ts["start"] - margin)
            e = min(total_dur, ts["end"] + margin)
            if merged_sectors and (s - merged_sectors[-1]["end"]) <= gap_merge_limit:
                merged_sectors[-1]["end"] = e
            else:
                merged_sectors.append({"start": s, "end": e})

        grouped = []
        for seg in merged_sectors:
            grouped.extend(self._split_range_with_overlap(seg["start"], seg["end"], max_chunk_dur, overlap_sec))

        return grouped
    
    def _write_grouped_chunks_parallel(self, wav_path: str, chunk_dir: str, grouped: list[dict]):
        if not grouped:
            return

        max_workers = max(1, min(self.io_workers, len(grouped)))

        def _one(idx_seg):
            idx, seg = idx_seg
            out = os.path.join(chunk_dir, f"vad_{idx:03d}_{seg['start']:.3f}.wav")
            ok = self._ffmpeg_trim_to_wav(
                wav_path,
                out,
                seg["start"],
                seg["end"] - seg["start"]
            )
            return ok, out

        if max_workers == 1:
            for idx, seg in enumerate(grouped):
                _one((idx, seg))
            return

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="chunk-writer") as ex:
            futures = [ex.submit(_one, (idx, seg)) for idx, seg in enumerate(grouped)]
            for fut in futures:
                try:
                    fut.result()
                except Exception as e:
                    get_logger().log(f"⚠️ 청크 생성 실패: {e}")

    def _write_grouped_chunks_from_media_parallel(
        self,
        media_path: str,
        chunk_dir: str,
        grouped: list[dict],
        audio_filter: str,
        settings: dict,
    ) -> bool:
        if not grouped:
            return False

        ffmpeg = ffmpeg_binary()
        max_workers = max(1, min(self.io_workers, len(grouped)))
        progress_lock = threading.Lock()
        done_count = 0
        next_log_pct = 0

        def _one(idx_seg):
            idx, seg = idx_seg
            start = max(0.0, float(seg.get("start", 0.0) or 0.0))
            end = max(start, float(seg.get("end", start) or start))
            out = os.path.join(chunk_dir, f"vad_{idx:03d}_{start:.3f}.wav")
            cmd = [
                ffmpeg, "-y", "-nostdin", "-loglevel", "error",
                *self._ffmpeg_parallel_args(settings),
                "-ss", str(start),
                "-t", str(max(0.001, end - start)),
                "-i", media_path,
                *self._ffmpeg_audio_stream_args(),
                "-ac", "1", "-ar", "16000",
                "-af", audio_filter or "anull",
                "-acodec", "pcm_s16le",
                out,
            ]
            ok = self._run_media_command_no_progress(cmd, label="ffmpeg 직접 청크 추출")
            return ok and os.path.exists(out) and os.path.getsize(out) > 0

        def _mark_progress():
            nonlocal done_count, next_log_pct
            with progress_lock:
                done_count += 1
                pct = min(100, int(round((done_count / len(grouped)) * 100)))
                if pct >= next_log_pct or done_count == len(grouped):
                    next_log_pct = min(100, pct + 10)
                    msg = f"⏳ [전처리] FFMPEG 직접 청크 추출 중 {pct}%"
                    self._notify_stage(msg)
                    get_logger().log(f"  └ [전처리] 직접 청크 추출 진행률 {pct}% ({done_count}/{len(grouped)})")

        failures = 0
        if max_workers == 1:
            for item in enumerate(grouped):
                if not _one(item):
                    failures += 1
                _mark_progress()
        else:
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="direct-chunk-writer") as ex:
                futures = [ex.submit(_one, item) for item in enumerate(grouped)]
                for fut in futures:
                    try:
                        if not fut.result():
                            failures += 1
                    except Exception as e:
                        failures += 1
                        get_logger().log(f"⚠️ 직접 청크 생성 실패: {e}")
                    finally:
                        _mark_progress()
        return failures == 0

    def _parse_whisper_payload(self, data: dict, item: dict, vad_strict: list,
                           target_end_sec: float = None, is_single: bool = False) -> list[dict]:
        chunk_segs = []
        if "segments" not in data:
            if data.get("error"):
                get_logger().log(f"  ⚠️ Whisper 오류: {data.get('error')}")
            return chunk_segs

        offset = item["ov_start_offset"]

        for seg in data["segments"]:
            words = seg.get("words", [])
            exact_start = seg["start"] + offset
            exact_end = seg["end"] + offset
            offset_words = []

            if words:
                valid_words = [
                    w for w in words
                    if "start" in w and "end" in w and w.get("word", "").strip()
                ]

                word_filter_vad = [v for v in vad_strict if v.get("vad_word_filter", True)]
                if word_filter_vad:
                    temp_words = []
                    for w in valid_words:
                        w_start = w["start"] + offset
                        w_end = w["end"] + offset
                        is_valid = False
                        for v in word_filter_vad:
                            if w_start <= v["end"] + 0.5 and w_end >= v["start"] - 0.5:
                                is_valid = True
                                break
                        if is_valid:
                            temp_words.append(w)
                    valid_words = temp_words

                if valid_words:
                    exact_start = valid_words[0]["start"] + offset
                    exact_end = valid_words[-1]["end"] + offset
                    for w in valid_words:
                        word_item = {
                            "word": w.get("word", ""),
                            "start": w["start"] + offset,
                            "end": w["end"] + offset
                        }
                        for conf_key in ("confidence", "probability", "score"):
                            if conf_key in w:
                                word_item[conf_key] = w.get(conf_key)
                        offset_words.append(word_item)

            if words and not offset_words:
                continue

            if is_single and target_end_sec is not None:
                if exact_start >= target_end_sec:
                    continue
                if exact_end > target_end_sec:
                    exact_end = target_end_sec

            segment = {
                "start": exact_start,
                "end": exact_end,
                "text": seg.get("text", "").strip(),
                "words": offset_words,
            }
            for key in (
                "avg_logprob",
                "compression_ratio",
                "no_speech_prob",
                "temperature",
                "tokens",
                "word_confidence",
            ):
                if key in seg:
                    segment[key] = seg.get(key)
            segment = attach_asr_metadata(
                segment,
                backend=data.get("backend"),
                language_probability=data.get("language_probability"),
                chunk_path=data.get("chunk_path") or item.get("input_path"),
            )
            if vad_strict:
                segment = annotate_segment_vad_alignment(segment, vad_strict)
            segment = annotate_segment_hallucination_risk(segment, vad_segments=vad_strict)
            chunk_segs.append(segment)

        return chunk_segs

    def _dedupe_overlapping_segments(
        self,
        chunk_segs: list[dict],
        previous_end: float,
        dedup_window: float = 0.5,
        vad_segments: list[dict] | None = None,
    ) -> list[dict]:
        if not chunk_segs or previous_end <= 0.0:
            return chunk_segs

        boundary = max(0.0, float(previous_end) - min(max(float(dedup_window or 0.0), 0.0), 0.15))
        cleaned = []
        for seg in chunk_segs:
            words = [
                dict(w)
                for w in (seg.get("words") or [])
                if float(w.get("end", 0.0) or 0.0) > boundary
            ]
            if seg.get("words"):
                if not words:
                    continue
                trimmed = dict(seg)
                trimmed["words"] = words
                trimmed["start"] = float(words[0].get("start", seg.get("start", previous_end)) or previous_end)
                trimmed["end"] = float(words[-1].get("end", seg.get("end", previous_end)) or previous_end)
                if words and words != seg.get("words"):
                    text = " ".join(str(w.get("word", "") or "").strip() for w in words).strip()
                    if text:
                        trimmed["text"] = text
                    trimmed = attach_asr_metadata(trimmed, backend=(trimmed.get("asr_metadata") or {}).get("backend"))
                    if vad_segments:
                        trimmed = annotate_segment_vad_alignment(trimmed, vad_segments)
                    trimmed = annotate_segment_hallucination_risk(trimmed, vad_segments=vad_segments or [])

                ranked = rank_overlap_candidates(
                    [
                        {"candidate_id": "original", "segment": seg},
                        {"candidate_id": "trimmed", "segment": trimmed, "score_bonus": 2.0},
                    ],
                    vad_segments=vad_segments or [],
                    previous_end=previous_end,
                )
                selected_id = str(ranked[0].get("candidate_id") or "trimmed")
                selected_score = ranked[0].get("score")
                selected = dict(ranked[0].get("segment") or trimmed)
                if selected.get("start", 0.0) < previous_end and trimmed.get("end", 0.0) > trimmed.get("start", 0.0):
                    selected = trimmed
                    selected_id = "trimmed"
                    for item in ranked:
                        if item.get("candidate_id") == "trimmed":
                            selected_score = item.get("score")
                            break
                asr_metadata = dict(selected.get("asr_metadata") or {})
                asr_metadata["overlap_candidate"] = {
                    "selected": selected_id,
                    "score": selected_score,
                    "boundary": round(boundary, 6),
                }
                selected["asr_metadata"] = asr_metadata
                cleaned.append(selected)
                continue

            exact_end = float(seg.get("end", 0.0) or 0.0)
            if exact_end <= boundary:
                continue
            new_seg = dict(seg)
            new_seg["start"] = max(float(new_seg.get("start", 0.0) or 0.0), previous_end)
            if new_seg["end"] > new_seg["start"]:
                if vad_segments:
                    new_seg = annotate_segment_vad_alignment(new_seg, vad_segments)
                new_seg = annotate_segment_hallucination_risk(new_seg, vad_segments=vad_segments or [])
                cleaned.append(new_seg)

        return cleaned
    
