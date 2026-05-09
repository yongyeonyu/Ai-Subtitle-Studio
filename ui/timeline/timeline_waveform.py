# Version: 03.06.17
# Phase: PHASE2
"""
ui/timeline_waveform.py
Timeline waveform workers
"""
import json
import os
import subprocess
import tempfile

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from core.media_fingerprint import media_fingerprint_digest


WAVEFORM_CACHE_SCHEMA = "ai_subtitle_studio.waveform_cache.v1"
WAVEFORM_SAMPLE_RATE = 2000
WAVEFORM_POINTS_PER_SECOND = 100


def _safe_media_base_name(path: str) -> str:
    base_name = os.path.splitext(os.path.basename(str(path or "")))[0]
    safe = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in base_name).strip(" ._")
    return (safe or "media")[:96]


def _waveform_cache_root() -> str:
    try:
        from core.runtime import config

        root = os.path.join(config.OUTPUT_DIR, "waveform_cache")
    except Exception:
        root = os.path.join(tempfile.gettempdir(), "ai_subtitle_studio_waveform_cache")
    os.makedirs(root, exist_ok=True)
    return root


def waveform_cache_path(path: str, *, sample_rate: int = WAVEFORM_SAMPLE_RATE) -> str:
    digest = media_fingerprint_digest(path, sample_bytes=512 * 1024, include_samples=True)[:24]
    return os.path.join(_waveform_cache_root(), f"{_safe_media_base_name(path)}_{digest}_{int(sample_rate)}hz.npz")


def fingerprint_cleaned_wav_path(path: str) -> str:
    try:
        from core.runtime import config

        base_name = _safe_media_base_name(path)
        digest = media_fingerprint_digest(path, sample_bytes=512 * 1024, include_samples=True)[:20]
        return os.path.join(config.OUTPUT_DIR, "_audio_fingerprint", f"{base_name}_{digest}", f"{base_name}_cleaned.wav")
    except Exception:
        return ""


def load_waveform_cache(path: str) -> tuple[np.ndarray, float] | None:
    try:
        cache_path = waveform_cache_path(path)
        if not os.path.exists(cache_path):
            return None
        with np.load(cache_path, allow_pickle=False) as payload:
            schema = str(payload["schema"].tolist()) if "schema" in payload.files else ""
            if schema != WAVEFORM_CACHE_SCHEMA:
                return None
            waveform = payload["waveform"].astype(np.float32)
            duration = float(payload["duration"].tolist())
        if waveform.size <= 0 or duration <= 0:
            return None
        return waveform, duration
    except Exception:
        return None


def save_waveform_cache(path: str, waveform: np.ndarray, duration: float) -> None:
    try:
        if waveform is None or len(waveform) <= 0 or float(duration or 0.0) <= 0:
            return
        cache_path = waveform_cache_path(path)
        fd, tmp_path = tempfile.mkstemp(prefix=os.path.basename(cache_path), suffix=".tmp", dir=os.path.dirname(cache_path))
        os.close(fd)
        try:
            with open(tmp_path, "wb") as handle:
                np.savez_compressed(
                    handle,
                    schema=np.array(WAVEFORM_CACHE_SCHEMA),
                    waveform=np.asarray(waveform, dtype=np.float32),
                    duration=np.array(float(duration or 0.0), dtype=np.float64),
                )
            os.replace(tmp_path, cache_path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
    except Exception:
        pass


def _decode_f32le_samples(raw: bytes | bytearray | memoryview | None) -> np.ndarray:
    if not raw:
        return np.array([], dtype=np.float32)
    return np.frombuffer(raw, dtype=np.float32).copy()


def _downsample_waveform_samples(samples: np.ndarray, *, duration: float | None = None) -> tuple[np.ndarray, float]:
    samples = np.asarray(samples, dtype=np.float32)
    if samples.size < 2:
        return np.array([], dtype=np.float32), 0.0

    dur = float(duration or 0.0)
    if dur <= 0.0:
        dur = samples.size / float(WAVEFORM_SAMPLE_RATE)
    total_px = max(1, int(dur * WAVEFORM_POINTS_PER_SECOND))
    chunk = max(1, samples.size // total_px)
    trim = (samples.size // chunk) * chunk
    downs = np.abs(samples[:trim].reshape(-1, chunk)).max(axis=1)

    mx = float(downs.max()) if downs.size else 0.0
    if mx > 1e-6:
        downs = downs / mx

    return downs[:total_px].astype(np.float32), float(dur)


def _downsample_waveform_raw(raw: bytes | bytearray | memoryview | None, *, duration: float | None = None) -> tuple[np.ndarray, float]:
    try:
        from core.native_cut_boundary import waveform_peaks_f32le

        native = waveform_peaks_f32le(
            raw,
            sample_rate=WAVEFORM_SAMPLE_RATE,
            points_per_second=WAVEFORM_POINTS_PER_SECOND,
            duration=duration,
        )
        if native is not None:
            return native
    except Exception:
        pass
    try:
        from core.native_swift_waveform import downsample_f32le_via_swift

        native = downsample_f32le_via_swift(
            raw,
            sample_rate=WAVEFORM_SAMPLE_RATE,
            points_per_second=WAVEFORM_POINTS_PER_SECOND,
            duration=duration,
        )
        if native is not None:
            return native
    except Exception:
        pass
    samples = _decode_f32le_samples(raw)
    return _downsample_waveform_samples(samples, duration=duration)


def patch_waveform_buffer(
    target: np.ndarray | None,
    *,
    start_px: int,
    total_px: int,
    values: np.ndarray | bytes | bytearray | memoryview | list[float] | tuple[float, ...] | None,
) -> np.ndarray:
    total = max(1, int(total_px or 0))
    start = max(0, int(start_px or 0))
    if isinstance(values, np.ndarray):
        chunk = np.asarray(values, dtype=np.float32)
    else:
        chunk = np.asarray(values or [], dtype=np.float32)
    if target is None or not isinstance(target, np.ndarray) or target.dtype != np.float32 or len(target) != total:
        base = np.zeros(total, dtype=np.float32)
        if isinstance(target, np.ndarray) and target.size > 0:
            keep = min(len(target), total)
            base[:keep] = np.asarray(target[:keep], dtype=np.float32)
        target = base
    if chunk.size <= 0 or start >= total:
        return target
    end = min(total, start + int(chunk.size))
    target[start:end] = chunk[: max(0, end - start)]
    return target


def _ffmpeg_waveform_cmd(path: str) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-i",
        path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(WAVEFORM_SAMPLE_RATE),
        "-f",
        "f32le",
        "-loglevel",
        "error",
        "pipe:1",
    ]


class WaveformWorker(QThread):
    ready = pyqtSignal(np.ndarray, float)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path
        self._proc = None

    def stop(self):
        self.requestInterruption()
        proc = getattr(self, "_proc", None)
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=0.8)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _run_cmd(self, cmd: list[str], *, timeout: float):
        if self.isInterruptionRequested():
            return None
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=False)
        self._proc = proc
        try:
            out, _err = proc.communicate(timeout=timeout)
            if self.isInterruptionRequested() or proc.returncode not in (0, None):
                return None
            return out
        except subprocess.TimeoutExpired:
            self.stop()
            return None
        finally:
            if self._proc is proc:
                self._proc = None

    def _get_duration(self) -> float:
        try:
            out = self._run_cmd(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", self._path],
                timeout=10,
            )
            if not out:
                return 0.0
            return float(json.loads(out.decode("utf-8", errors="ignore")).get("format", {}).get("duration", 0))
        except Exception:
            return 0.0

    def run(self):
        try:
            cached = load_waveform_cache(self._path)
            if cached is not None and not self.isInterruptionRequested():
                self.ready.emit(cached[0], cached[1])
                return

            duration = self._get_duration()
            if self.isInterruptionRequested():
                return
            timeout = max(60, min(600, int(duration * 0.5) + 30))

            cleaned_wav = fingerprint_cleaned_wav_path(self._path)
            source_path = cleaned_wav if cleaned_wav and os.path.exists(cleaned_wav) else self._path
            raw = self._run_cmd(_ffmpeg_waveform_cmd(source_path), timeout=timeout)
            if self.isInterruptionRequested():
                return
            ready, dur = _downsample_waveform_raw(raw)
            raw = None
            if ready.size <= 0:
                return

            if not self.isInterruptionRequested():
                save_waveform_cache(self._path, ready, float(dur))
                self.ready.emit(ready, float(dur))
        except Exception:
            pass

class MultiClipWaveformWorker(QThread):
    clip_ready = pyqtSignal(int, int, int, object)
    all_ready = pyqtSignal(np.ndarray, float)

    def __init__(self, clip_boundaries, parent=None):
        super().__init__(parent)
        self._clips = clip_boundaries
        self._proc = None

    def stop(self):
        self.requestInterruption()
        proc = getattr(self, "_proc", None)
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=0.8)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _run_cmd(self, cmd: list[str], *, timeout: float):
        if self.isInterruptionRequested():
            return None
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=False)
        self._proc = proc
        try:
            out, _err = proc.communicate(timeout=timeout)
            if self.isInterruptionRequested() or proc.returncode not in (0, None):
                return None
            return out
        except subprocess.TimeoutExpired:
            self.stop()
            return None
        finally:
            if self._proc is proc:
                self._proc = None

    def run(self):
        if not self._clips:
            return

        total_dur = self._clips[-1]["end"]
        total_px = max(1, int(total_dur * WAVEFORM_POINTS_PER_SECOND))
        combined = np.zeros(total_px, dtype=np.float32)

        for idx, clip in enumerate(self._clips):
            if self.isInterruptionRequested():
                return
            try:
                clip_file = clip["file"]
                clip_start = clip["start"]
                clip_dur = clip["end"] - clip["start"]

                cached = load_waveform_cache(clip_file)
                if cached is not None:
                    downs, _dur = cached
                    clip_px = max(1, int(clip_dur * WAVEFORM_POINTS_PER_SECOND))
                    start_px = int(clip_start * WAVEFORM_POINTS_PER_SECOND)
                    end_px = min(start_px + min(len(downs), clip_px), total_px)
                    combined[start_px:end_px] = downs[: end_px - start_px]
                    if not self.isInterruptionRequested():
                        self.clip_ready.emit(idx, start_px, total_px, np.asarray(combined[start_px:end_px], dtype=np.float32).copy())
                    continue

                cleaned_wav = fingerprint_cleaned_wav_path(clip_file)
                src = cleaned_wav if os.path.exists(cleaned_wav) else clip_file

                raw = self._run_cmd(_ffmpeg_waveform_cmd(src), timeout=max(60, int(clip_dur * 0.5) + 30))
                if self.isInterruptionRequested():
                    return
                downs, _dur = _downsample_waveform_raw(raw, duration=clip_dur)
                raw = None
                if downs.size <= 0:
                    continue

                save_waveform_cache(clip_file, downs[: max(1, int(clip_dur * WAVEFORM_POINTS_PER_SECOND))], float(clip_dur))

                start_px = int(clip_start * WAVEFORM_POINTS_PER_SECOND)
                end_px = min(start_px + len(downs), total_px)
                combined[start_px:end_px] = downs[: end_px - start_px]

                if not self.isInterruptionRequested():
                    self.clip_ready.emit(idx, start_px, total_px, np.asarray(combined[start_px:end_px], dtype=np.float32).copy())

            except Exception:
                pass

        if not self.isInterruptionRequested():
            self.all_ready.emit(combined, total_dur)
