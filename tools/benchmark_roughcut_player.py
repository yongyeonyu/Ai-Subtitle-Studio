#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

from core.roughcut.models import ChapterMetadata, EDLSegment, EditDecision, RoughCutResult, RoughCutSegment  # noqa: E402
from ui.roughcut.roughcut_widget import RoughcutWidget  # noqa: E402


LATEST_DIR = ROOT / "output" / "manual_verification" / "latest"


class _FakeMediaPlayer:
    def __init__(self):
        self._position = 0
        self.playing = False

    def setPosition(self, value):
        self._position = int(value)

    def position(self):
        return self._position

    def play(self):
        self.playing = True

    def pause(self):
        self.playing = False


class _FakeVideoPlayer:
    def __init__(self):
        self.media_player = _FakeMediaPlayer()
        self.current_time = 0.0
        self.applied_styles: list[dict] = []
        self.seek_calls: list[float] = []
        self.sub_label = SimpleNamespace(_export_style={"font": "Editor Font", "size": 52, "align": "center"})

    def restore_after_navigation(self):
        return None

    def apply_export_subtitle_style(self, style):
        payload = dict(style or {})
        self.sub_label._export_style = payload
        self.applied_styles.append(payload)

    def seek_direct(self, sec):
        self.current_time = float(sec)
        self.seek_calls.append(float(sec))
        self.media_player.setPosition(int(float(sec) * 1000.0))


class _FakeEditor:
    def __init__(self, owned_frame):
        self._owned_frame = owned_frame
        self.video_player = _FakeVideoPlayer()

    def detach_video_frame_for_external_host(self):
        return self._owned_frame

    def restore_video_frame_from_external_host(self, restored_frame=None):
        self._owned_frame = restored_frame or self._owned_frame


def _default_output_dir() -> Path:
    return LATEST_DIR / f"roughcut_player_responsiveness_{time.strftime('%Y%m%d_%H%M%S')}"


def _resolve_output_dir(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


def _fixture_result() -> RoughCutResult:
    return RoughCutResult(
        segments=(RoughCutSegment("major_A", 0.0, 8.0, title="첫 장면", major_id="A"),),
        chapters=(
            ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
            ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
        ),
        edit_decisions=(
            EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
            EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
        ),
        edl_segments=(
            EDLSegment("/tmp/source.mov", "chapter_0001", 0.0, 4.0, 0.0, 4.0, chapter_id="chapter_0001"),
            EDLSegment("/tmp/source.mov", "chapter_0002", 4.0, 8.0, 4.0, 8.0, chapter_id="chapter_0002"),
        ),
        guide_markdown="# guide",
        schema_version="roughcut_result.v2",
    )


def run_benchmark(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    widget = RoughcutWidget()
    frame = QWidget()
    editor = _FakeEditor(frame)
    widget.owner = SimpleNamespace(_active_editor=lambda: editor)
    widget._editor_segments = lambda: [
        {"start": 0.0, "end": 4.0, "text": "에디터 생성 자막", "speaker": "00"},
        {"start": 4.0, "end": 8.0, "text": "둘째 자막", "speaker": "00"},
    ]
    try:
        widget.resize(1280, 760)
        widget.show()
        QTest.qWait(80)
        app.processEvents()
        attached = widget.attach_editor_video_frame(editor)
        widget._result = _fixture_result()
        widget._populate_result()

        play_started = time.perf_counter()
        play_ok = bool(widget._start_roughcut_video_playback())
        play_elapsed_ms = round((time.perf_counter() - play_started) * 1000.0, 3)
        editor_style_adopted = bool(editor.video_player.applied_styles) and editor.video_player.applied_styles[-1].get("font") == "Editor Font"
        adopted_style_label = widget.roughcut_video_style_lbl.text()

        style_started = time.perf_counter()
        widget._save_roughcut_export_style(
            {
                "font_family": "Apple SD Gothic Neo",
                "font_size": 64,
                "position": "top_center",
            }
        )
        style_elapsed_ms = round((time.perf_counter() - style_started) * 1000.0, 3)

        splitter = widget.right_frame_splitter
        handle = splitter.handle(1)
        move_events: list[dict] = []
        resize_start = None

        def _on_moved(pos, index):
            now = time.perf_counter()
            move_events.append(
                {
                    "elapsed_ms": round((now - resize_start) * 1000.0, 3) if resize_start is not None else None,
                    "pos": int(pos),
                    "index": int(index),
                    "sizes": [int(item) for item in splitter.sizes()],
                    "playing": bool(editor.video_player.media_player.playing),
                }
            )

        before_sizes = [int(item) for item in splitter.sizes()]
        splitter.splitterMoved.connect(_on_moved)
        center = handle.rect().center()
        resize_start = time.perf_counter()
        QTest.mousePress(handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center)
        QTest.qWait(5)
        QTest.mouseMove(handle, center + QPoint(0, 80), delay=1)
        app.processEvents()
        during_sizes = [int(item) for item in splitter.sizes()]
        QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center + QPoint(0, 80))
        resize_elapsed_ms = round((time.perf_counter() - resize_start) * 1000.0, 3)
        splitter.splitterMoved.disconnect(_on_moved)

        subtitle_visible = "에디터 생성 자막" in widget.roughcut_subtitle_preview_lbl.text()
        style_applied = bool(editor.video_player.applied_styles) and editor.video_player.applied_styles[-1].get("font_size") == 64
        resized_while_playing = bool(move_events) and before_sizes != during_sizes and all(bool(event.get("playing")) for event in move_events)
        ok = (
            attached
            and play_ok
            and bool(editor.video_player.media_player.playing)
            and play_elapsed_ms <= 35.0
            and editor_style_adopted
            and subtitle_visible
            and style_applied
            and resized_while_playing
        )
        return {
            "schema": "ai_subtitle_studio.roughcut_player_responsiveness.v1",
            "ok": bool(ok),
            "attached": bool(attached),
            "play_ok": bool(play_ok),
            "play_elapsed_ms": play_elapsed_ms,
            "style_elapsed_ms": style_elapsed_ms,
            "resize_elapsed_ms": resize_elapsed_ms,
            "resize_first_event_ms": move_events[0]["elapsed_ms"] if move_events else None,
            "before_sizes": before_sizes,
            "during_sizes": during_sizes,
            "move_events": move_events,
            "subtitle_visible": bool(subtitle_visible),
            "editor_style_adopted": bool(editor_style_adopted),
            "adopted_style_label": adopted_style_label,
            "style_applied": bool(style_applied),
            "resized_while_playing": bool(resized_while_playing),
            "video_state": widget.roughcut_video_state_lbl.text(),
            "style_label": widget.roughcut_video_style_lbl.text(),
            "subtitle_text": widget.roughcut_subtitle_preview_lbl.text(),
            "output_dir": str(output_dir),
        }
    finally:
        widget.close()


def render_markdown(payload: dict) -> str:
    return "\n".join(
        [
            "# Roughcut Player Responsiveness",
            "",
            f"- status: `{'passed' if payload.get('ok') else 'blocked'}`",
            f"- play_elapsed_ms: `{payload.get('play_elapsed_ms')}`",
            f"- style_elapsed_ms: `{payload.get('style_elapsed_ms')}`",
            f"- resize_first_event_ms: `{payload.get('resize_first_event_ms')}`",
            f"- resized_while_playing: `{payload.get('resized_while_playing')}`",
            f"- subtitle_visible: `{payload.get('subtitle_visible')}`",
            f"- style_applied: `{payload.get('style_applied')}`",
            f"- before_sizes: `{payload.get('before_sizes')}`",
            f"- during_sizes: `{payload.get('during_sizes')}`",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark roughcut video-box playback responsiveness.")
    parser.add_argument("--output-dir", default=str(_default_output_dir()))
    args = parser.parse_args(argv)

    output_dir = _resolve_output_dir(args.output_dir)
    payload = run_benchmark(output_dir)
    (output_dir / "benchmark_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "summary.md").write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps({"ok": bool(payload.get("ok")), "output_dir": str(output_dir)}, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
