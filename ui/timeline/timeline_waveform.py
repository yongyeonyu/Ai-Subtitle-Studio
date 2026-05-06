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
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False)
        self._proc = proc
        try:
            out, err = proc.communicate(timeout=timeout)
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
        tmp = None
        try:
            cached = load_waveform_cache(self._path)
            if cached is not None and not self.isInterruptionRequested():
                self.ready.emit(cached[0], cached[1])
                return

            duration = self._get_duration()
            if self.isInterruptionRequested():
                return
            timeout = max(60, min(600, int(duration * 0.5) + 30))

            fd, tmp = tempfile.mkstemp(suffix=".raw")
            os.close(fd)

            self._run_cmd(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    self._path,
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "2000",
                    "-f",
                    "f32le",
                    "-loglevel",
                    "error",
                    tmp,
                ],
                timeout=timeout,
            )
            if self.isInterruptionRequested():
                return

            if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
                return

            samples = np.fromfile(tmp, dtype=np.float32)
            if len(samples) < 2:
                return

            dur = len(samples) / 2000.0
            total_px = max(1, int(dur * 100))
            chunk = max(1, len(samples) // total_px)
            trim = (len(samples) // chunk) * chunk
            downs = np.abs(samples[:trim].reshape(-1, chunk)).max(axis=1)

            mx = float(downs.max())
            if mx > 1e-6:
                downs = downs / mx

            if not self.isInterruptionRequested():
                ready = downs[:total_px].astype(np.float32)
                save_waveform_cache(self._path, ready, float(dur))
                self.ready.emit(ready, float(dur))
        except Exception:
            pass
        finally:
            if tmp:
                try:
                    os.remove(tmp)
                except Exception:
                    pass

class MultiClipWaveformWorker(QThread):
    clip_ready = pyqtSignal(int, np.ndarray)
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
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False)
        self._proc = proc
        try:
            out, err = proc.communicate(timeout=timeout)
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
        total_px = max(1, int(total_dur * 100))
        combined = np.zeros(total_px, dtype=np.float32)

        from core.runtime import config

        for idx, clip in enumerate(self._clips):
            if self.isInterruptionRequested():
                return
            tmp = None
            try:
                clip_file = clip["file"]
                clip_start = clip["start"]
                clip_dur = clip["end"] - clip["start"]

                cached = load_waveform_cache(clip_file)
                if cached is not None:
                    downs, _dur = cached
                    clip_px = max(1, int(clip_dur * 100))
                    start_px = int(clip_start * 100)
                    end_px = min(start_px + min(len(downs), clip_px), total_px)
                    combined[start_px:end_px] = downs[: end_px - start_px]
                    if not self.isInterruptionRequested():
                        self.clip_ready.emit(idx, combined.copy())
                    continue

                cleaned_wav = fingerprint_cleaned_wav_path(clip_file)
                src = cleaned_wav if os.path.exists(cleaned_wav) else clip_file

                fd, tmp = tempfile.mkstemp(suffix=".raw")
                os.close(fd)

                self._run_cmd(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        src,
                        "-vn",
                        "-ac",
                        "1",
                        "-ar",
                        "2000",
                        "-f",
                        "f32le",
                        "-loglevel",
                        "error",
                        tmp,
                    ],
                    timeout=max(60, int(clip_dur * 0.5) + 30),
                )
                if self.isInterruptionRequested():
                    return

                if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
                    continue

                samples = np.fromfile(tmp, dtype=np.float32)
                if len(samples) < 2:
                    continue

                clip_px = max(1, int(clip_dur * 100))
                chunk = max(1, len(samples) // clip_px)
                trim = (len(samples) // chunk) * chunk
                downs = np.abs(samples[:trim].reshape(-1, chunk)).max(axis=1)

                mx = float(downs.max())
                if mx > 1e-6:
                    downs = downs / mx

                downs = downs.astype(np.float32)
                save_waveform_cache(clip_file, downs[: max(1, int(clip_dur * 100))], float(clip_dur))

                start_px = int(clip_start * 100)
                end_px = min(start_px + len(downs), total_px)
                combined[start_px:end_px] = downs[: end_px - start_px]

                if not self.isInterruptionRequested():
                    self.clip_ready.emit(idx, combined.copy())

            except Exception:
                pass
            finally:
                if tmp:
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass

        if not self.isInterruptionRequested():
            self.all_ready.emit(combined, total_dur)
