# Version: 03.13.03
# Phase: PHASE2
"""
logger.py - PyQt6 버전 (크PD 변환)
싱글톤 AppLogger: pyqtSignal로 UI 스레드에 안전하게 전달
tkinter root.after() → QObject + pyqtSignal 패턴으로 교체

터미널 출력은 기본 macOS Terminal 기준으로 바로 grep/분석하기 쉽도록
타임스탬프/시퀀스/레벨/스테이지/스레드 정보를 붙여 구조화한다.
UI 위젯과 recent log 버퍼에는 기존 원문을 그대로 유지한다.
"""
from __future__ import annotations

import io
import threading
from collections import deque
from datetime import datetime
from itertools import islice
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal


def _write_internal_error(context: str, exc: BaseException) -> None:
    try:
        import sys

        stream = getattr(sys, "__stderr__", None)
        if stream is None:
            return
        stream.write(f"[AppLogger:{context}] {type(exc).__name__}: {exc}\n")
    except (OSError, RuntimeError, ValueError):
        return


class _LogEmitter(QObject):
    """UI 스레드로 로그를 안전하게 emit하기 위한 QObject"""
    log_signal = pyqtSignal(str)


class _TerminalHeaderStream(io.TextIOBase):
    def __init__(self, logger: "AppLogger", stream, *, default_level: str = "INFO"):
        self._logger = logger
        self._stream = stream
        self._default_level = str(default_level or "INFO").upper()
        self._buffer = ""
        self._lock = threading.Lock()

    @property
    def encoding(self):
        return getattr(self._stream, "encoding", "utf-8")

    def writable(self):
        return True

    def isatty(self):
        return bool(getattr(self._stream, "isatty", lambda: False)())

    def fileno(self):
        return int(getattr(self._stream, "fileno")())

    def write(self, text):
        chunk = str(text or "")
        if not chunk:
            return 0
        with self._lock:
            self._buffer += chunk
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                self._logger._emit_terminal_lines(
                    [line],
                    level=self._default_level,
                    writer=self._stream,
                )
        return len(chunk)

    def flush(self):
        with self._lock:
            if self._buffer:
                self._logger._emit_terminal_lines(
                    [self._buffer],
                    level=self._default_level,
                    writer=self._stream,
                )
                self._buffer = ""
            try:
                self._stream.flush()
            except (OSError, RuntimeError, ValueError) as exc:
                _write_internal_error("stream-flush", exc)


class AppLogger:
    _instance = None
    _lock = threading.Lock()
    _DEFAULT_STAGE = "general"
    _STAGE_PATTERNS = (
        ("automation", ("자동화 명령", "guided-subtitle", "capture-snapshot", "open-project", "open-media", "queue-folder", "queue-files")),
        ("cut-boundary", ("[컷 경계]", "[후발대 진행]", "rollback 검증", "임시선 재배치")),
        ("audio-filter", ("오토 오디오", "음성 필터", "audio filter")),
        ("audio-extract", ("오디오 추출", "audio extract")),
        ("stt1", ("STT1",)),
        ("stt2", ("STT2",)),
        ("vad", ("VAD", "voice activity")),
        ("roughcut-llm", ("러프컷", "roughcut")),
        ("subtitle-llm", ("자막 최적화", "[LLM", "OpenAI", "Codex CLI", "Codex", "LoRA자막", "텍스트 LoRA")),
        ("save", ("저장", "save", "캐시 저장", "프로젝트 저장", "자동 저장")),
        ("project", ("프로젝트", "project")),
        ("runtime", ("AutoPilot", "runtime", "런타임")),
        ("memory", ("메모리 상태", "GPU", "리소스", "idle timer")),
    )
    _STAGE_PATTERNS_LOWER = tuple(
        (stage, tuple(pattern.lower() for pattern in patterns))
        for stage, patterns in _STAGE_PATTERNS
    )

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._emitter = _LogEmitter()
                inst._ui_callback = None
                inst._recent_lines = deque(maxlen=400)
                inst._recent_lock = threading.Lock()
                inst._terminal_lock = threading.Lock()
                inst._terminal_sequence = 0
                inst._terminal_stdout = None
                inst._terminal_stderr = None
                inst._stream_capture_installed = False
                cls._instance = inst
        return cls._instance

    def set_ui_callback(self, callback):
        """MainWindow.append_log 등록. 중복 방지."""
        if self._ui_callback:
            try:
                self._emitter.log_signal.disconnect(self._ui_callback)
            except (RuntimeError, TypeError) as exc:
                _write_internal_error("disconnect-ui-callback", exc)
        self._ui_callback = callback
        self._emitter.log_signal.connect(callback)

    def clear_ui_callback(self):
        if self._ui_callback:
            try:
                self._emitter.log_signal.disconnect(self._ui_callback)
            except (RuntimeError, TypeError) as exc:
                _write_internal_error("clear-ui-callback", exc)
            self._ui_callback = None

    def _now_text(self) -> str:
        now = datetime.now().astimezone()
        return (
            now.strftime("%Y-%m-%d %H:%M:%S.")
            + f"{int(now.microsecond / 1000):03d} "
            + now.strftime("%z")
        )

    def _infer_level(self, line: str) -> str:
        text = str(line or "")
        lowered = text.lower()
        if "traceback" in lowered or "keyboardinterrupt" in lowered:
            return "ERROR"
        if "⚠️" in text or " warning" in lowered or lowered.startswith("warning"):
            return "WARN"
        if "❌" in text or " 실패" in text or text.startswith("실패") or "오류" in text or "exception" in lowered:
            return "ERROR"
        if "✅" in text:
            return "OK"
        if text.lstrip().startswith(("▫️", "🟢", "🧭", "▒")):
            return "DEBUG"
        return "INFO"

    def _infer_stage(self, line: str) -> str:
        text = str(line or "")
        lowered = text.lower()
        for stage, patterns in self._STAGE_PATTERNS_LOWER:
            for pattern in patterns:
                if pattern in lowered:
                    return stage
        return self._DEFAULT_STAGE

    def _split_terminal_lines(self, msg: str) -> list[str]:
        text = str(msg or "")
        lines = [line.rstrip() for line in text.splitlines()]
        return [line for line in lines if line.strip()]

    def _format_terminal_line(self, line: str, *, level: str | None = None, stage: str | None = None) -> str:
        terminal_level = str(level or self._infer_level(line) or "INFO").upper()
        terminal_stage = str(stage or self._infer_stage(line) or self._DEFAULT_STAGE).lower()
        thread_name = threading.current_thread().name or "MainThread"
        return (
            f"{self._now_text()} | #{self._terminal_sequence:05d} | "
            f"{terminal_level:<5} | {terminal_stage:<14} | {thread_name:<24} | {line}"
        )

    def _emit_terminal_lines(self, lines: list[str], *, level: str | None = None, stage: str | None = None, writer=None) -> None:
        if not lines:
            return
        target = writer or self._terminal_stdout
        if target is None:
            import sys

            target = sys.__stdout__
        with self._terminal_lock:
            for line in lines:
                self._terminal_sequence += 1
                try:
                    target.write(self._format_terminal_line(line, level=level, stage=stage) + "\n")
                    target.flush()
                except (OSError, RuntimeError, ValueError) as exc:
                    _write_internal_error("terminal-write", exc)

    def _emit_terminal(self, msg: str, *, level: str | None = None, stage: str | None = None) -> None:
        self._emit_terminal_lines(self._split_terminal_lines(msg), level=level, stage=stage)

    def install_stream_capture(self, *, stdout=None, stderr=None) -> None:
        if self._stream_capture_installed:
            return
        import sys

        base_stdout = stdout or sys.stdout
        base_stderr = stderr or sys.stderr
        self._terminal_stdout = base_stdout
        self._terminal_stderr = base_stderr
        sys.stdout = _TerminalHeaderStream(self, base_stdout, default_level="INFO")
        sys.stderr = _TerminalHeaderStream(self, base_stderr, default_level="ERROR")
        self._stream_capture_installed = True

    def log(self, msg: str, *, level: str | None = None, stage: str | None = None):
        line = str(msg or "")
        with self._recent_lock:
            self._recent_lines.append(line)
        self._emit_terminal(line, level=level, stage=stage)
        try:
            self._emitter.log_signal.emit(line)
        except (RuntimeError, TypeError) as exc:
            _write_internal_error("emit-ui-log", exc)

    def recent_lines(self, limit: int = 40) -> list[str]:
        size = max(1, int(limit or 40))
        with self._recent_lock:
            if size >= len(self._recent_lines):
                return list(self._recent_lines)
            lines = list(islice(reversed(self._recent_lines), size))
        lines.reverse()
        return lines

    def recent_lines_and_filtered(
        self,
        *,
        recent_limit: int = 40,
        filtered_scan_limit: int = 160,
        filtered_limit: int = 20,
        predicate: Callable[[str], bool] | None = None,
    ) -> tuple[list[str], list[str]]:
        recent_size = max(1, int(recent_limit or 40))
        filtered_size = max(1, int(filtered_limit or 20))
        scan_size = max(recent_size, int(filtered_scan_limit or 160), filtered_size)
        recent_lines: list[str] = []
        filtered_lines: list[str] = []
        with self._recent_lock:
            for index, line in enumerate(reversed(self._recent_lines)):
                if index < recent_size:
                    recent_lines.append(line)
                if predicate is not None and index < scan_size and len(filtered_lines) < filtered_size and predicate(line):
                    filtered_lines.append(line)
                if index + 1 >= scan_size:
                    break
        recent_lines.reverse()
        filtered_lines.reverse()
        return recent_lines, filtered_lines

    def clear_recent_lines(self) -> None:
        with self._recent_lock:
            self._recent_lines.clear()

    def info(self, msg: str):
        self.log(msg, level="INFO")

    def error(self, msg: str):
        self.log(msg, level="ERROR")

    def warning(self, msg: str):
        self.log(msg, level="WARN")

    def terminal_debug(self, msg: str, *, stage: str | None = None) -> None:
        self._emit_terminal(str(msg or ""), level="DEBUG", stage=stage or "runtime")

    def log_perf(
        self,
        label: str,
        *,
        event: str | None = None,
        elapsed_ms: float | None = None,
        stage: str | None = None,
        **fields,
    ) -> None:
        parts = [f"⏱️ [perf] {str(label or '').strip() or 'event'}"]
        event_text = str(event or "").strip()
        if event_text:
            parts.append(event_text)
        if elapsed_ms is not None:
            try:
                parts.append(f"{float(elapsed_ms):.1f}ms")
            except Exception:
                parts.append(f"{elapsed_ms}ms")
        for key, value in fields.items():
            if value is None:
                continue
            value_text = str(value).strip() if isinstance(value, str) else str(value)
            if not value_text:
                continue
            parts.append(f"{key}={value_text}")
        self._emit_terminal(" · ".join(parts), level="DEBUG", stage=stage or "runtime")
        try:
            from core.runtime.trace_logger import current_app_trace_logger

            trace = current_app_trace_logger()
            if trace is not None:
                trace.log_event(
                    "perf",
                    stage=stage or "runtime",
                    level="DEBUG",
                    label=str(label or "").strip(),
                    perf_event=event_text,
                    elapsed_ms=elapsed_ms,
                    **fields,
                )
        except Exception:
            pass


def get_logger() -> AppLogger:
    return AppLogger()
