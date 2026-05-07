# Version: 03.01.31
# Phase: PHASE2
from __future__ import annotations

import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QTabWidget, QTextEdit, QVBoxLayout, QWidget

from ui.settings.qml_panel import attach_qml_tab_bar
from ui.roughcut.roughcut_format import fmt_time
from ui.style import label_style


class RoughcutBottomPanel(QWidget):
    def __init__(self, controls: QWidget, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        root.addWidget(controls)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #2D3942; border-radius: 7px; background: #11181C; } "
            "QTabBar::tab { background: #202A31; color: #A9B0B7; border: 1px solid #2D3942; "
            "border-bottom: none; padding: 7px 12px; min-height: 24px; min-width: 84px; "
            "border-top-left-radius: 7px; border-top-right-radius: 7px; } "
            "QTabBar::tab:selected { background: #151C20; color: #F5F7FA; border-color: #34C759; }"
        )
        self.subtitle_text = self._text_view("자막 세그먼트 없음")
        self.global_text = self._text_view("글로벌 세그먼트 없음")
        self.waveform_text = self._text_view("웨이브폼/세그먼트 바 없음")
        self.edl_text = self._text_view("EDL 없음")
        self.storyboard_text = self._text_view("스토리보드 없음")

        self.tabs.addTab(self.subtitle_text, "자막 세그먼트")
        self.tabs.addTab(self.global_text, "글로벌 세그먼트")
        self.tabs.addTab(self.waveform_text, "웨이브폼")
        self.tabs.addTab(self.edl_text, "EDL")
        self.tabs.addTab(self.storyboard_text, "스토리보드")
        attach_qml_tab_bar(self, root, self.tabs, scope="roughcut", insert_index=1)
        root.addWidget(self.tabs, stretch=1)

    def clear(self) -> None:
        self.subtitle_text.setPlainText("자막 세그먼트 없음")
        self.global_text.setPlainText("글로벌 세그먼트 없음")
        self.waveform_text.setPlainText("웨이브폼/세그먼트 바 없음")
        self.edl_text.setPlainText("EDL 없음")
        self.storyboard_text.setPlainText("스토리보드 없음")
        self.tabs.setTabEnabled(4, False)

    def set_result(self, result, editor_segments: list[dict] | None = None) -> None:
        editor_segments = list(editor_segments or [])
        self.subtitle_text.setPlainText(self._subtitle_lines(editor_segments, result))
        self.global_text.setPlainText(self._global_lines(result))
        self.waveform_text.setPlainText(self._waveform_lines(result))
        self.edl_text.setPlainText(self._edl_json(result))
        storyboard = self._storyboard_lines(result)
        self.storyboard_text.setPlainText(storyboard)
        self.tabs.setTabEnabled(4, bool(storyboard.strip() and storyboard.strip() != "스토리보드 없음"))

    def _text_view(self, placeholder: str) -> QTextEdit:
        text = QTextEdit()
        text.setReadOnly(True)
        text.setMinimumHeight(150)
        text.setPlainText(placeholder)
        text.setStyleSheet(
            "QTextEdit { background: #0F1518; color: #DCE3EA; border: none; "
            "padding: 9px; font-size: 10px; }"
        )
        return text

    def _subtitle_lines(self, editor_segments: list[dict], result) -> str:
        if editor_segments:
            lines = []
            for index, seg in enumerate(editor_segments[:300], start=1):
                start = fmt_time(float(seg.get("start", 0.0) or 0.0))
                end = fmt_time(float(seg.get("end", 0.0) or 0.0))
                text = str(seg.get("text") or "").replace("\n", " ").strip()
                lines.append(f"{index:03d}  {start}-{end}  {text}")
            return "\n".join(lines)
        chapters = tuple(getattr(result, "chapters", ()) or ())
        if not chapters:
            return "자막 세그먼트 없음"
        return "\n".join(
            f"{index:03d}  {fmt_time(chapter.start)}-{fmt_time(chapter.end)}  {chapter.title}"
            for index, chapter in enumerate(chapters, start=1)
        )

    def _global_lines(self, result) -> str:
        segments = tuple(getattr(result, "segments", ()) or ())
        if not segments:
            return "글로벌 세그먼트 없음"
        lines = []
        for segment in segments:
            major = getattr(segment, "major_id", "") or segment.segment_id
            title = getattr(segment, "title", "") or major
            lines.append(f"{major}  {fmt_time(segment.start)}-{fmt_time(segment.end)}  {title}")
            for minor in tuple(getattr(segment, "minor_groups", ()) or ()):
                lines.append(f"  {minor.code}  {fmt_time(minor.start)}-{fmt_time(minor.end)}  {minor.title}")
        return "\n".join(lines)

    def _waveform_lines(self, result) -> str:
        edl = tuple(getattr(result, "edl_segments", ()) or ())
        if not edl:
            return "웨이브폼/세그먼트 바 없음"
        total = max((segment.output_end for segment in edl), default=0.0)
        if total <= 0:
            return "웨이브폼/세그먼트 바 없음"
        lines = ["세그먼트 바 (출력 타임라인 기준)"]
        width = 48
        for segment in edl:
            start = int((segment.output_start / total) * width)
            end = max(start + 1, int((segment.output_end / total) * width))
            bar = "." * start + "#" * max(1, end - start)
            bar = bar[:width].ljust(width, ".")
            lines.append(f"{fmt_time(segment.output_start)} {bar} {fmt_time(segment.output_end)}  {segment.segment_id}")
        return "\n".join(lines)

    def _edl_json(self, result) -> str:
        edl = tuple(getattr(result, "edl_segments", ()) or ())
        if not edl:
            return "EDL 없음"
        payload = [
            {
                "segment_id": segment.segment_id,
                "source_path": segment.source_path,
                "source_start": segment.source_start,
                "source_end": segment.source_end,
                "output_start": segment.output_start,
                "output_end": segment.output_end,
                "action": segment.action,
                "chapter_id": segment.chapter_id,
                "clip_index": segment.clip_index,
            }
            for segment in edl
        ]
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _storyboard_lines(self, result) -> str:
        segments = tuple(getattr(result, "segments", ()) or ())
        rows = []
        for segment in segments:
            if not (getattr(segment, "thumbnail_path", None) or getattr(segment, "summary", None)):
                continue
            rows.append(
                f"{getattr(segment, 'major_id', '') or segment.segment_id}  "
                f"{fmt_time(segment.start)}-{fmt_time(segment.end)}  "
                f"{getattr(segment, 'title', '') or segment.segment_id}\n"
                f"  썸네일: {getattr(segment, 'thumbnail_path', '') or '-'}\n"
                f"  요약: {getattr(segment, 'summary', '') or '-'}"
            )
        return "\n\n".join(rows) if rows else "스토리보드 없음"


def compact_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(label_style("muted", 10, bold=True))
    return label


__all__ = ["RoughcutBottomPanel"]
