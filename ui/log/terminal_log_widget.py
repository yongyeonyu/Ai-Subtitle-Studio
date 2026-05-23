# Version: 03.01.04
# Phase: PHASE2
"""Terminal log panel widget."""

import sys
import re

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

from ui.style import named_panel_style


_PROGRESS_RE = re.compile(r"(?<!\d)(\d{1,3})(?:\.\d+)?\s*%")
_TIME_PAIR_RE = re.compile(r"(\d{1,3})분\s*(\d{1,2})초\s*/\s*(\d{1,3})분\s*(\d{1,2})초")
_CHUNK_PROGRESS_RE = re.compile(r"chunk\s*(\d+)\s*/\s*(\d+)", re.IGNORECASE)
_CHUNK_TOTAL_RE = re.compile(r"chunk\s*(\d+)(?:개)?", re.IGNORECASE)
_APPLY_COUNT_RE = re.compile(r"(?:누적|일괄)?적용\s*(\d+)회")
_MAJOR_COUNT_RE = re.compile(r"중분류\s*(\d+)개")
_ROW_COUNT_RE = re.compile(r"자막\s*row\s*(\d+)개", re.IGNORECASE)
_ETA_RE = re.compile(r"예상\s*(\d+)s", re.IGNORECASE)
_PROGRESS_ENTRY_CATEGORIES = {
    "preprocess",
    "audio",
    "vad",
    "stt",
    "stt1",
    "stt2",
    "subtitle",
    "subtitle_llm",
    "roughcut",
    "lora",
    "deep_learning",
    "cut_boundary",
    "cleanup",
    "timing",
}
_SUPPLEMENTAL_ENTRY_CATEGORIES = {
    "settings",
    "lora_setup",
    "resource",
    "warning",
    "save",
    "done",
}
_DEFAULT_PROGRESS_DETAILS = {
    "preprocess": "파일 준비",
    "audio": "잡음 정리",
    "vad": "말소리 감지",
    "stt": "음성 인식",
    "stt1": "1차 인식",
    "stt2": "2차 인식",
    "subtitle": "문장 정리",
    "roughcut": "장면 요약",
    "lora": "말투 반영",
    "deep_learning": "규칙 학습",
    "cut_boundary": "장면 탐색",
    "cleanup": "사전 교정",
    "timing": "시간 정렬",
}


def _normalize_log_line(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _extract_progress_percent(text: str) -> int | None:
    match = _PROGRESS_RE.search(str(text or ""))
    if match is None:
        return None
    try:
        value = int(float(match.group(1)))
    except Exception:
        return None
    return max(0, min(100, value))


def _compact_time_pair(text: str) -> str:
    match = _TIME_PAIR_RE.search(str(text or ""))
    if match is None:
        return ""
    start_min, start_sec, total_min, total_sec = (int(part) for part in match.groups())
    return f"{start_min:02d}:{start_sec:02d}/{total_min:02d}:{total_sec:02d}"


def _extract_chunk_progress(text: str) -> str:
    match = _CHUNK_PROGRESS_RE.search(str(text or ""))
    if match is not None:
        return f"{int(match.group(1))}/{int(match.group(2))}chunk"
    return ""


def _extract_chunk_total(text: str) -> str:
    match = _CHUNK_TOTAL_RE.search(str(text or ""))
    if match is not None:
        return f"{int(match.group(1))}chunk"
    return ""


def _extract_apply_count(text: str) -> str:
    match = _APPLY_COUNT_RE.search(str(text or ""))
    if match is not None:
        return f"{int(match.group(1))}회"
    return ""


def _extract_major_count(text: str) -> str:
    match = _MAJOR_COUNT_RE.search(str(text or ""))
    if match is not None:
        return f"중분류 {int(match.group(1))}개"
    return ""


def _extract_row_count(text: str) -> str:
    match = _ROW_COUNT_RE.search(str(text or ""))
    if match is not None:
        return f"{int(match.group(1))}줄"
    return ""


def _extract_eta_seconds(text: str) -> str:
    match = _ETA_RE.search(str(text or ""))
    if match is not None:
        return f"예상{int(match.group(1))}s"
    return ""


def _join_detail(*parts: str) -> str:
    return ", ".join(str(part or "").strip() for part in parts if str(part or "").strip())


def _split_progress_detail(text: str) -> tuple[str, str]:
    body = str(text or "").strip()
    if body.startswith("진행:"):
        body = body.split(":", 1)[1].strip()
    head, _, detail = body.partition(" · ")
    return head.strip(), detail.strip()


def _with_progress(summary: str, percent: int | None, detail: str = "") -> str:
    text = str(summary or "").strip()
    if not text:
        return ""
    if text.startswith("진행:"):
        text = text.split(":", 1)[1].strip()
    suffix = f" · {detail}" if str(detail or "").strip() else ""
    if percent is None:
        return f"진행: {text}{suffix}"
    return f"진행: {text} {int(percent)}%{suffix}"


def _with_progress_category(category: str, summary: str, percent: int | None, detail: str = "") -> str:
    fallback = str(_DEFAULT_PROGRESS_DETAILS.get(str(category or "").strip(), "") or "")
    return _with_progress(summary, percent, detail or fallback)


def _strip_progress_suffix(text: str) -> str:
    return re.sub(r"(?:\s*·)?\s*\d{1,3}%\s*$", "", str(text or "")).strip()


def _compact_progress_stage(text: str) -> tuple[str, str]:
    cleaned = _strip_progress_suffix(_normalize_log_line(text))
    if cleaned.startswith("진행:"):
        cleaned = cleaned.split(":", 1)[1].strip()
    lower = cleaned.lower()
    if not cleaned:
        return "", ""
    if "stt 1/2" in lower or "stt1/stt2" in lower:
        return "stt", "STT"
    if any(token in lower for token in ("[stt1]", "stt1", "stt 1")):
        return "stt1", "STT1"
    if any(token in lower for token in ("[stt2]", "stt2", "stt 2")):
        return "stt2", "STT2"
    if any(token in lower for token in ("[자막 llm]", "subtitle llm", "자막 llm", "최종 llm", "자동교정")):
        return "subtitle", "자막"
    if any(token in lower for token in ("[컷 경계]", "컷 경계", "scan-cut", "cut boundary")):
        return "cut_boundary", "컷"
    if any(token in lower for token in ("[전처리]", "오디오 추출", "ffmpeg 오디오", "ffmpeg")):
        return "preprocess", "준비"
    if any(token in lower for token in ("[음성]", "clearvoice", "deepfilter", "rnnoise", "resemble")):
        return "audio", "음성"
    if any(token in lower for token in ("[vad]", "ten_vad", "ten vad", "silero", "음성 섹터")):
        return "vad", "VAD"
    if any(token in lower for token in ("[lora]", "lora")):
        return "lora", "LoRA"
    if any(token in lower for token in ("[딥러닝]", "deep learning", "deep subtitle")):
        return "deep_learning", "딥"
    if "roughcut" in lower or "러프컷" in cleaned:
        return "roughcut", "러프컷"
    if any(token in lower for token in ("[정제-교정사전]", "교정사전", "교정")):
        return "cleanup", "교정"
    if "word_timestamp" in lower or "단어 정밀" in cleaned:
        return "timing", "타이밍"
    if any(token in lower for token in ("[stt", "whisper", "병렬 인식", "진행 상황", "transcription completed")):
        return "stt", "STT"
    if any(token in cleaned for token in ("[자막 전체 생성]", "자막 생성", "자막")):
        return "subtitle", "자막"
    return "", cleaned


def _friendly_log_entry(raw_line: str) -> tuple[str, str]:
    text = _normalize_log_line(raw_line)
    lower = text.lower()
    percent = _extract_progress_percent(text)
    if not text:
        return "empty", ""

    if "설정 적용:" in text:
        return "settings", "준비: 자막 품질 설정을 적용했어요."
    if "[블록속도 스케줄러]" in text:
        return "settings", "준비: 긴 영상에 맞춰 처리 순서를 조정했어요."
    if "[llm-proaprofile]" in lower or "품질 검사/자동교정 보호" in text:
        return "settings", "준비: 자막 품질 점검 규칙을 불러왔어요."
    if "[텍스트 lora]" in lower or "교정 memory" in lower or "사용자 단어" in text:
        return "lora_setup", "준비: 사용자 말투와 교정 기록을 반영할 준비를 했어요."
    if "리소스 자동 모드" in text or "[lora/deep-전처리]" in lower:
        return "resource", "준비: 컴퓨터 속도에 맞춰 처리 강도를 자동 조절해요."
    if "[stt경계-다듬기판정]" in text or "문체 confidence" in lower:
        return "timing", _with_progress_category("timing", "타이밍", percent)
    if "[정제-교정사전]" in text:
        count = _extract_apply_count(text)
        return "cleanup", _with_progress_category("cleanup", "교정", percent, f"사전 {count}" if count else "사전")

    if any(token in lower for token in ("[컷 경계]", "컷 경계", "scan-cut", "cut boundary")):
        if any(token in lower for token in ("완료", "재사용", "verified", "confirmed", "cache")):
            return "cut_boundary", "완료: 장면 전환 위치를 확인했어요."
        return "cut_boundary", _with_progress_category("cut_boundary", "컷", percent)
    if any(token in lower for token in ("[전처리]", "오디오 추출", "ffmpeg 오디오", "ffmpeg")):
        return "preprocess", _with_progress_category("preprocess", "준비", percent)
    if any(token in lower for token in ("[음성]", "clearvoice", "deepfilter", "rnnoise", "resemble")):
        return "audio", _with_progress_category("audio", "음성", percent)
    if any(token in lower for token in ("[vad]", "ten_vad", "ten vad", "silero", "음성 섹터")):
        return "vad", _with_progress_category("vad", "VAD", percent)
    if any(token in lower for token in ("[stt2]", "stt2", "stt 2")) and "loading weights" in lower:
        return "stt2", _with_progress_category("stt2", "STT2", percent, "모델 준비")
    if "word_timestamp" in lower or "단어 정밀" in text:
        detail = _extract_apply_count(text)
        return "timing", _with_progress_category("timing", "타이밍", percent, detail)
    if "진행 상황" in text:
        time_pair = _compact_time_pair(text)
        if any(token in lower for token in ("[stt1]", "stt1", "stt 1")):
            return "stt1", _with_progress_category("stt1", "STT1", percent, time_pair)
        if any(token in lower for token in ("[stt2]", "stt2", "stt 2")):
            return "stt2", _with_progress_category("stt2", "STT2", percent, time_pair)
        return "stt", _with_progress_category("stt", "STT", percent, time_pair)
    if "persistent worker 유지" in lower and any(token in lower for token in ("[stt1]", "stt1", "stt 1")):
        return "stt1", _with_progress_category("stt1", "STT1", percent, "재사용")
    if "persistent worker 유지" in lower and any(token in lower for token in ("[stt2]", "stt2", "stt 2")):
        return "stt2", _with_progress_category("stt2", "STT2", percent, "재사용")
    if any(token in lower for token in ("[stt1]", "stt1", "stt 1")):
        return "stt1", _with_progress_category("stt1", "STT1", percent)
    if any(token in lower for token in ("[stt2]", "stt2", "stt 2")):
        return "stt2", _with_progress_category("stt2", "STT2", percent)
    if "병렬 인식 시작" in text:
        return "stt", _with_progress_category("stt", "STT", percent, "병렬 시작")
    if any(token in lower for token in ("[stt", "whisper", "병렬 인식", "진행 상황", "transcription completed")):
        return "stt", _with_progress_category("stt", "STT", percent)
    if any(token in lower for token in ("[자막 llm]", "[llm-보정차단]", "최종 llm", "자동교정")):
        detail = ""
        if "자동교정" in text:
            detail = "자동교정"
        elif "무결성 검사" in text:
            detail = "무결성 검사"
        return "subtitle", _with_progress_category("subtitle", "자막", percent, detail)
    if "러프컷 후처리 완료" in text:
        source = "LLM" if "llm" in lower else ("로컬" if "로컬" in text else "")
        major = _extract_major_count(text)
        return "done", f"완료: 러프컷 · {_join_detail(source, major) or '후처리 완료'}"
    if "roughcut" in lower or "러프컷" in text:
        if "응답 수신" in text:
            return "roughcut", _with_progress("러프컷", percent, "응답 수신")
        if "저장 중" in text:
            return "roughcut", _with_progress("러프컷", percent, "저장 중")
        if "후처리 시작" in text:
            return "roughcut", _with_progress(
                "러프컷",
                percent,
                _join_detail(_extract_row_count(text), _extract_chunk_total(text), _extract_eta_seconds(text)),
            )
        chunk_progress = _extract_chunk_progress(text)
        detail = _join_detail(
            chunk_progress,
            "로컬 대체" if "로컬 규칙으로 대체" in text else "",
            "병합 완료" if "chunked 완료" in text else "",
        )
        return "roughcut", _with_progress_category("roughcut", "러프컷", percent, detail)
    if "[lora]" in lower or ("lora" in lower and "text lora" not in lower):
        detail = "학습 반영" if "memory" in lower or "학습" in text else ""
        return "lora", _with_progress_category("lora", "LoRA", percent, detail)
    if "[딥러닝]" in text or "deep learning" in lower or "deep subtitle" in lower:
        return "deep_learning", _with_progress_category("deep_learning", "딥", percent)

    if any(token in text for token in ("프로젝트 저장 완료", "저장 완료:", ".srt 저장 완료", "💾 저장 완료", "📦 프로젝트 저장 완료")):
        return "save", "완료: 자막과 프로젝트를 저장했어요."
    if "자막 생성 완료" in text:
        return "done", "완료: 자막 생성이 끝났어요."
    if any(token in text for token in ("실패", "오류", "중단", "경고", "⚠️")):
        return "warning", "알림: 확인이 필요한 항목이 있어요."

    return "generic", text


class FriendlyTerminalLogTextEdit(QTextEdit):
    """Keep raw logs for internal logic while showing user-friendly summaries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._max_lines = 800
        self._raw_lines: list[str] = []
        self._display_entries: list[tuple[str, str]] = []
        self._progress_snapshot_getter = None
        self._last_render_signature: tuple[str, ...] = ()

    def raw_log_text(self) -> str:
        return "\n".join(self._raw_lines)

    def set_progress_snapshot_getter(self, getter) -> None:
        self._progress_snapshot_getter = getter if callable(getter) else None
        self.refresh_display()

    def refresh_display(self) -> None:
        self._render_display()

    def append(self, text: str) -> None:  # type: ignore[override]
        self._ingest_lines([str(text or "")])
        self._render_display()

    def setPlainText(self, text: str) -> None:  # type: ignore[override]
        lines = str(text or "").splitlines()
        self._raw_lines = []
        self._display_entries = []
        self._ingest_lines(lines)
        self._render_display()

    def clear(self) -> None:  # type: ignore[override]
        self._raw_lines = []
        self._display_entries = []
        self._last_render_signature = ()
        super().clear()

    def _ingest_lines(self, lines: list[str]) -> None:
        for raw_line in list(lines or []):
            line = str(raw_line or "")
            if not line.strip():
                continue
            self._raw_lines.append(line)
            if len(self._raw_lines) > self._max_lines:
                self._raw_lines = self._raw_lines[-self._max_lines:]
            category, summary = _friendly_log_entry(line)
            if not summary:
                continue
            if self._display_entries and self._display_entries[-1][0] == category:
                if self._display_entries[-1][1] == summary:
                    continue
                self._display_entries[-1] = (category, summary)
            else:
                self._display_entries.append((category, summary))
            if len(self._display_entries) > self._max_lines:
                self._display_entries = self._display_entries[-self._max_lines:]

    def _progress_snapshot(self) -> dict:
        getter = self._progress_snapshot_getter
        if not callable(getter):
            return {}
        try:
            payload = getter()
        except Exception:
            return {}
        return dict(payload or {}) if isinstance(payload, dict) else {}

    def _recent_progress_summary(self) -> str:
        for category, text in reversed(self._display_entries):
            if category in _PROGRESS_ENTRY_CATEGORIES:
                summary = _strip_progress_suffix(text)
                if summary:
                    return summary
        return ""

    def _recent_progress_detail(self, category_key: str) -> str:
        wanted = str(category_key or "").strip()
        if not wanted:
            return ""
        for category, text in reversed(self._display_entries):
            if category != wanted:
                continue
            _summary, detail = _split_progress_detail(text)
            if detail:
                return detail
        return ""

    def _progress_headline_entry(self) -> tuple[str, str]:
        snapshot = self._progress_snapshot()
        if not snapshot:
            return "", ""
        try:
            percent = int(round(float(snapshot.get("percentValue", snapshot.get("percent", 0.0)) or 0.0)))
        except Exception:
            percent = 0
        running = bool(snapshot.get("running"))
        if percent <= 0 or percent >= 100 or not running:
            return "", ""
        progress_text = str(snapshot.get("progressText", f"{percent}%") or f"{percent}%").strip()
        title = str(snapshot.get("title", "") or "").strip()
        stage = title.split("|", 1)[1].strip() if "|" in title else title
        if not stage or stage in {"진행 중", "대기", "완료", "저장", "오류"}:
            stage = self._recent_progress_summary()
        category, label = _compact_progress_stage(stage)
        if not label:
            label = "진행"
        return category, _with_progress_category(
            category,
            label,
            _extract_progress_percent(progress_text) or percent,
            self._recent_progress_detail(category),
        )

    def _latest_unique_progress_entries(self, limit: int, *, exclude_categories: set[str] | None = None) -> list[str]:
        seen_categories = set(exclude_categories or set())
        selected: list[str] = []
        for category, text in reversed(self._display_entries):
            if category not in _PROGRESS_ENTRY_CATEGORIES and "%" not in str(text or ""):
                continue
            if category in seen_categories:
                continue
            summary = str(text or "").strip()
            if not summary:
                continue
            seen_categories.add(category)
            selected.append(summary)
            if len(selected) >= max(0, int(limit or 0)):
                break
        selected.reverse()
        return selected

    def _latest_unique_entries(self, predicate, limit: int, *, exclude: set[str] | None = None) -> list[str]:
        seen = set(exclude or set())
        selected: list[str] = []
        for category, text in reversed(self._display_entries):
            if not predicate(category, text):
                continue
            summary = str(text or "").strip()
            if not summary or summary in seen:
                continue
            seen.add(summary)
            selected.append(summary)
            if len(selected) >= max(0, int(limit or 0)):
                break
        selected.reverse()
        return selected

    def _display_lines(self) -> list[str]:
        headline_category, headline = self._progress_headline_entry()
        if not headline:
            return [text for _category, text in self._display_entries[-8:]]
        lines = [headline]
        lines.extend(self._latest_unique_progress_entries(4, exclude_categories={headline_category} if headline_category else set()))
        seen = set(lines)
        seen.update(lines)
        lines.extend(
            self._latest_unique_entries(
                lambda category, _text: category in _SUPPLEMENTAL_ENTRY_CATEGORIES,
                3,
                exclude=seen,
            )
        )
        return lines

    def _render_display(self) -> None:
        display_lines = self._display_lines()
        render_signature = tuple(display_lines)
        if render_signature == self._last_render_signature:
            return
        self._last_render_signature = render_signature
        display_text = "\n".join(display_lines)
        cursor = self.textCursor()
        had_selection = cursor.hasSelection()
        scroll_value = self.verticalScrollBar().value()
        scroll_max = self.verticalScrollBar().maximum()
        stick_to_bottom = scroll_value >= max(0, scroll_max - 4)
        super().setPlainText(display_text)
        if had_selection:
            self.setTextCursor(cursor)
        else:
            self.moveCursor(QTextCursor.MoveOperation.End)
        if not stick_to_bottom:
            self.verticalScrollBar().setValue(scroll_value)


class _NullScrollBar:
    def maximum(self) -> int:
        return 0

    def setValue(self, _value: int) -> None:
        return


class BufferedTerminalLogSink:
    """Non-widget log sink for stdin helper/bootstrap runs."""

    def __init__(self) -> None:
        self._max_lines = 800
        self._raw_lines: list[str] = []
        self._display_entries: list[tuple[str, str]] = []
        self._progress_snapshot_getter = None
        self._scroll_bar = _NullScrollBar()

    def raw_log_text(self) -> str:
        return "\n".join(self._raw_lines)

    def toPlainText(self) -> str:
        return "\n".join(summary for _, summary in self._display_entries)

    def set_progress_snapshot_getter(self, getter) -> None:
        self._progress_snapshot_getter = getter if callable(getter) else None

    def append(self, text: str) -> None:
        line = str(text or "")
        if not line.strip():
            return
        self._raw_lines.append(line)
        if len(self._raw_lines) > self._max_lines:
            self._raw_lines = self._raw_lines[-self._max_lines:]
        category, summary = _friendly_log_entry(line)
        if not summary:
            return
        if self._display_entries and self._display_entries[-1][0] == category:
            if self._display_entries[-1][1] == summary:
                return
            self._display_entries[-1] = (category, summary)
        else:
            self._display_entries.append((category, summary))
        if len(self._display_entries) > self._max_lines:
            self._display_entries = self._display_entries[-self._max_lines:]

    def verticalScrollBar(self) -> _NullScrollBar:
        return self._scroll_bar


def should_use_lightweight_terminal_panel() -> bool:
    argv0 = str((sys.argv or [""])[0] or "").strip()
    return argv0 in {"-", "-c"}


class TerminalLogWidget(QWidget):
    """Terminal log panel that owns the QTextEdit used by MainWindow logging."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TerminalLogPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(named_panel_style("TerminalLogPanel", "surface", radius=7))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        self.log_text = FriendlyTerminalLogTextEdit()
        self.log_text.setReadOnly(True)
        font = QFont()
        font.setPointSize(9)
        self.log_text.setFont(font)
        self.log_text.document().setMaximumBlockCount(800)
        self.log_text.setStyleSheet(
            "background: #151C20; color: #DCE6ED; border: none; padding: 6px 8px; line-height: 140%;"
        )
        layout.addWidget(self.log_text)

    def preferred_panel_height(self, *, min_height: int = 128, max_height: int | None = 188) -> int:
        try:
            lines = [line for line in self.log_text.toPlainText().splitlines() if str(line).strip()]
            line_count = max(1, len(lines))
            line_height = max(14, int(self.log_text.fontMetrics().lineSpacing() or 14))
        except Exception:
            line_count = 1
            line_height = 14
        content_height = 36 + (line_count * line_height) + max(0, line_count - 1) * 2
        target = max(int(min_height), int(content_height))
        if max_height is not None:
            target = min(int(max_height), target)
        return max(0, int(target))


class LightweightTerminalLogPanel(QWidget):
    """stdin helper path should not build the QTextEdit startup tree."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TerminalLogPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(named_panel_style("TerminalLogPanel", "surface", radius=7))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(0)

        label = QLabel("Helper log panel")
        label.setStyleSheet("color: #6D7780; background: transparent; border: none; font-size: 10px;")
        layout.addWidget(label)
        self.log_text = BufferedTerminalLogSink()

    def preferred_panel_height(self, *, min_height: int = 128, max_height: int | None = 188) -> int:
        target = max(0, int(min_height))
        if max_height is not None:
            target = min(int(max_height), target)
        return target
