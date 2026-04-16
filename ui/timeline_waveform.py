# Version: 01.00.00
"""
ui/timeline_waveform.py
ffmpeg를 이용한 오디오 파형 추출 백그라운드 스레드
"""
import subprocess, os, tempfile
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

class WaveformWorker(QThread):
    ready = pyqtSignal(np.ndarray, float)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path

    def run(self):
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(suffix=".raw")
            os.close(fd)
            subprocess.run(
                ["ffmpeg", "-y", "-i", self._path, "-vn", "-ac", "1", "-ar", "2000", "-f", "f32le", "-loglevel", "error", tmp], 
                capture_output=True, timeout=60
            )
            if not os.path.exists(tmp) or os.path.getsize(tmp) == 0: return
            
            samples = np.fromfile(tmp, dtype=np.float32)
            if len(samples) < 2: return
            
            duration  = len(samples) / 2000.0
            total_px  = max(1, int(duration * 100)) 
            chunk     = max(1, len(samples) // total_px)
            trim      = (len(samples) // chunk) * chunk
            downs     = np.abs(samples[:trim].reshape(-1, chunk)).max(axis=1)
            
            mx = float(downs.max())
            if mx > 1e-6: downs = downs / mx
            
            self.ready.emit(downs[:total_px].astype(np.float32), float(duration))
        except Exception: pass
        finally:
            if tmp:
                try: os.remove(tmp)
                except: pass