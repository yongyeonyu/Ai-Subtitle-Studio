# Version: 02.02.00
# Phase: PHASE1-B
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

    def _get_duration(self) -> float:
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "json",
                    self._path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return float(json.loads(result.stdout).get("format", {}).get("duration", 0))
        except Exception:
            return 0.0

    def run(self):
        tmp = None
        try:
            duration = self._get_duration()
            timeout = max(60, min(600, int(duration * 0.5) + 30))

            fd, tmp = tempfile.mkstemp(suffix=".raw")
            os.close(fd)

            subprocess.run(
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
                capture_output=True,
                timeout=timeout,
            )

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

    def run(self):
        if not self._clips:
            return

        total_dur = self._clips[-1]["end"]
        total_px = max(1, int(total_dur * 100))
        combined = np.zeros(total_px, dtype=np.float32)

        import config

        for idx, clip in enumerate(self._clips):
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

                subprocess.run(
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
                    capture_output=True,
                    timeout=max(60, int(clip_dur * 0.5) + 30),
                )

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

                self.clip_ready.emit(idx, combined.copy())

            except Exception:
                pass
            finally:
                if tmp:
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass

        self.all_ready.emit(combined, total_dur)