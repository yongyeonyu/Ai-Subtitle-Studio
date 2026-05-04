from __future__ import annotations

import math
import os
import tempfile
import time
import wave
from collections import deque

import numpy as np
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices

from core.settings import load_settings


def pcm16_samples_from_bytes(data: bytes) -> np.ndarray:
    if not data:
        return np.zeros(0, dtype=np.float32)
    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    if samples.size <= 0:
        return np.zeros(0, dtype=np.float32)
    return samples / 32768.0


def normalized_audio_level(samples: np.ndarray) -> float:
    if samples is None or len(samples) <= 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(samples), dtype=np.float32)))
    peak = float(np.max(np.abs(samples)))
    return max(0.0, min(1.0, max(rms * 4.5, peak * 0.9)))


def append_waveform_preview(existing: list[float], samples: np.ndarray, *, max_points: int = 1536) -> list[float]:
    if samples is None or len(samples) <= 0:
        return list(existing or [])
    target = max(16, int(max_points))
    step = max(1, int(math.ceil(len(samples) / 96.0)))
    chunk = samples[::step].tolist()
    merged = list(existing or [])
    merged.extend(float(max(-1.0, min(1.0, value))) for value in chunk)
    if len(merged) > target:
        merged = merged[-target:]
    return merged


class LiveMicrophoneSession(QObject):
    waveform_changed = pyqtSignal(object)
    finished = pyqtSignal(str, bool, str, float)

    def __init__(self, parent: QObject | None = None, *, settings: dict | None = None):
        super().__init__(parent)
        self.settings = dict(settings or load_settings() or {})
        self.sample_rate = 16000
        self.channel_count = 1
        self.timeout_sec = float(self.settings.get("live_stt_timeout", 10.0) or 10.0)
        self.phrase_time_limit = float(self.settings.get("live_stt_phrase_time_limit", 30.0) or 30.0)
        self.pause_threshold = float(self.settings.get("live_stt_pause_threshold", 0.65) or 0.65)
        self.non_speaking_duration = float(self.settings.get("live_stt_non_speaking_duration", 0.25) or 0.25)
        self.level_threshold = float(self.settings.get("live_stt_level_threshold", 0.018) or 0.018)
        self._audio_source: QAudioSource | None = None
        self._audio_io = None
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(60)
        self._watch_timer.timeout.connect(self._poll_stop)
        self._pcm_chunks: list[bytes] = []
        self._waveform_points: list[float] = []
        self._started_at = 0.0
        self._last_voice_at = 0.0
        self._heard_voice = False
        self._finished = False

    def start(self) -> bool:
        device = QMediaDevices.defaultAudioInput()
        if hasattr(device, "isNull") and device.isNull():
            self.finished.emit("", False, "사용 가능한 마이크 입력 장치가 없습니다.", 0.0)
            return False

        fmt = QAudioFormat()
        fmt.setSampleRate(self.sample_rate)
        fmt.setChannelCount(self.channel_count)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)

        self._audio_source = QAudioSource(device, fmt, self)
        self._audio_source.setBufferSize(8192)
        self._audio_io = self._audio_source.start()
        if self._audio_io is None:
            self.finished.emit("", False, "마이크 입력 스트림을 열지 못했습니다.", 0.0)
            return False

        self._started_at = time.monotonic()
        self._last_voice_at = self._started_at
        try:
            self._audio_io.readyRead.connect(self._drain_audio)
        except Exception:
            pass
        self._watch_timer.start()
        return True

    def stop(self):
        self._finalize("")

    def _poll_stop(self):
        if self._finished:
            return
        now = time.monotonic()
        elapsed = now - self._started_at
        if not self._heard_voice and elapsed >= self.timeout_sec:
            self._finalize("마이크 입력 대기 시간이 초과되었습니다.")
            return
        if elapsed >= self.phrase_time_limit:
            self._finalize("")
            return
        silence_stop = max(self.pause_threshold, self.non_speaking_duration)
        if self._heard_voice and (now - self._last_voice_at) >= silence_stop:
            self._finalize("")

    def _drain_audio(self):
        if self._finished or self._audio_io is None:
            return
        try:
            data = bytes(self._audio_io.readAll())
        except Exception:
            data = b""
        if not data:
            return
        self._pcm_chunks.append(data)
        samples = pcm16_samples_from_bytes(data)
        if samples.size <= 0:
            return
        level = normalized_audio_level(samples)
        now = time.monotonic()
        if level >= self.level_threshold:
            self._heard_voice = True
            self._last_voice_at = now
        self._waveform_points = append_waveform_preview(self._waveform_points, samples)
        self.waveform_changed.emit(list(self._waveform_points))

    def _finalize(self, error_text: str):
        if self._finished:
            return
        self._finished = True
        self._watch_timer.stop()
        if self._audio_source is not None:
            try:
                self._audio_source.stop()
            except Exception:
                pass
        elapsed = max(0.0, time.monotonic() - float(self._started_at or time.monotonic()))
        pcm_bytes = b"".join(self._pcm_chunks)
        duration_sec = len(pcm_bytes) / float(self.sample_rate * self.channel_count * 2)
        has_audio = duration_sec >= 0.12
        wav_path = ""
        if has_audio:
            fd, wav_path = tempfile.mkstemp(prefix="ai_subtitle_live_mic_", suffix=".wav")
            os.close(fd)
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(self.channel_count)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(pcm_bytes)
        self.finished.emit(wav_path, has_audio, error_text if not has_audio else "", elapsed)
