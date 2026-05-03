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
                self.ready.emit(downs[:total_px].astype(np.float32), float(dur))
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

                base_name = os.path.splitext(os.path.basename(clip_file))[0]
                cleaned_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}_cleaned.wav")
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
