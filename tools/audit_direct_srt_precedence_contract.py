#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.native_json import dumps_json_bytes
from core.project.nle_project_state import NLE_PROJECT_STATE_RUNTIME_KEY
from core.project.project_io import read_project_storage_payload, write_project_file
from ui.editor import editor_project_open_native as project_open_native

SCHEMA = "ai_subtitle_studio.direct_srt_precedence_contract.v1"


class _Timeline:
    def __init__(self) -> None:
        self.auto_gap_segments_enabled = None
        self.waveform_paths: list[tuple[str, bool]] = []

    def _reset_single_media_context(self, *, clear_duration: bool = False) -> None:
        self.clear_duration = bool(clear_duration)

    def set_auto_gap_segments_enabled(self, enabled: bool) -> None:
        self.auto_gap_segments_enabled = bool(enabled)

    def load_waveform(self, path: str, preserve_view: bool = True) -> None:
        self.waveform_paths.append((str(path), bool(preserve_view)))


class _Editor:
    def __init__(self) -> None:
        self.timeline = _Timeline()
        self._cached_segs: list[dict[str, Any]] = []
        self._live_stt_preview_segments: list[dict[str, Any]] = []
        self.scheduled = False

    def apply_loaded_canvas_state(
        self,
        segments: list[dict[str, Any]],
        *,
        auto_gap_segments_enabled: bool,
        boundary_times: list[float] | None = None,
        provisional_boundaries: list[dict[str, Any]] | None = None,
        voice_activity_segments: list[dict[str, Any]] | None = None,
        stt_preview_segments: list[dict[str, Any]] | None = None,
        stt_preview_subtitle_drafts: bool | None = None,
        mark_dirty: bool = False,
    ) -> None:
        self._cached_segs = [dict(row) for row in list(segments or []) if isinstance(row, dict)]
        self.timeline.set_auto_gap_segments_enabled(auto_gap_segments_enabled)

    def _schedule_timeline(self) -> None:
        self.scheduled = True

    def _rebuild_subtitle_memory_cache(self, segments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        self._cached_segs = [dict(row) for row in list(segments or self._cached_segs or []) if isinstance(row, dict)]
        return {}

    def _refresh_editor_timestamp_metadata(self, *, full: bool = False) -> int:
        return len(self._cached_segs)

    def _refresh_video_subtitle_context(self) -> None:
        return None


class _Owner:
    def __init__(self, editor: _Editor) -> None:
        self._editor_widget = editor
        self._project_boundary_times: list[float] = []
        self.init_args: tuple[str, bool] | None = None

    def _init_editor(self, target_file: str, is_batch: bool = False) -> None:
        self.init_args = (str(target_file), bool(is_batch))

    def _refresh_opened_editor_runtime(self, editor: _Editor) -> None:
        editor._rebuild_subtitle_memory_cache()

    def _schedule_opened_editor_runtime_refresh(self, editor: _Editor) -> None:
        self._refresh_opened_editor_runtime(editor)

    def _resume_cut_boundary_prescan_for_open_project(
        self,
        filepath: str,
        project: dict[str, Any],
        media: list[str],
    ) -> None:
        return None


def _project(media_path: Path) -> dict[str, Any]:
    return {
        "project_name": "direct_srt_precedence",
        "video": {"duration_sec": 4.0, "primary_fps": 30.0},
        "timeline": {
            "total_duration": 4.0,
            "timebase": {"primary_fps": 30.0},
            "tracks": [{"clips": [{"source_path": str(media_path), "fps": 30.0}]}],
        },
        "media": [{"path": str(media_path), "duration": 4.0, "offset": 0.0}],
        "subtitles": {
            "segments": [
                {
                    "id": "project-old",
                    "start": 0.0,
                    "end": 1.0,
                    "text": "linked project old text",
                    "speaker": "09",
                }
            ]
        },
    }


def build_direct_srt_precedence_report(*, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aiss-direct-srt-precedence-") as tmp:
        root = Path(tmp)
        media_path = root / "media.mp4"
        media_path.write_bytes(b"video")
        project_path = root / "linked.aissproj"
        srt_path = root / "linked.assets" / "subtitles" / "final.srt"
        srt_path.parent.mkdir(parents=True, exist_ok=True)
        srt_path.write_text(
            "1\n00:00:01,200 --> 00:00:02,400\nlatest direct SRT text\n\n",
            encoding="utf-8",
        )
        project = _project(media_path)
        srt_rows = [
            {
                "id": "srt-new",
                "start": 1.2,
                "end": 2.4,
                "start_frame": 36,
                "end_frame": 72,
                "timeline_start_frame": 36,
                "timeline_end_frame": 72,
                "text": "latest direct SRT text",
                "speaker": "00",
            }
        ]
        project_rows = [
            {
                "id": "project-old",
                "start": 0.0,
                "end": 1.0,
                "start_frame": 0,
                "end_frame": 30,
                "timeline_start_frame": 0,
                "timeline_end_frame": 30,
                "text": "linked project old text",
                "speaker": "09",
                "quality": {"confidence_label": "yellow"},
            }
        ]
        merged = project_open_native.merge_srt_segments_with_project_metadata(srt_rows, project_rows)
        editor = _Editor()
        owner = _Owner(editor)
        previous_timer = project_open_native.QTimer.singleShot
        project_open_native.QTimer.singleShot = lambda _delay, callback: callback()
        try:
            opened = project_open_native.open_project_segments_in_editor(
                owner,
                str(project_path),
                project,
                [str(media_path)],
                merged,
                source_srt_path=str(srt_path),
                direct_srt_edit_mode=True,
            )
        finally:
            project_open_native.QTimer.singleShot = previous_timer
        state = project.get(NLE_PROJECT_STATE_RUNTIME_KEY)
        nle_rows = state.editor_rows() if state is not None else []
        write_project_file(str(project_path), project)
        storage = read_project_storage_payload(str(project_path))

    editor_rows = [dict(row) for row in editor._cached_segs]
    report = {
        "schema": SCHEMA,
        "passed": bool(
            opened
            and editor_rows
            and nle_rows
            and editor_rows[0].get("text") == "latest direct SRT text"
            and nle_rows[0].get("text") == "latest direct SRT text"
            and round(float(editor_rows[0].get("start", 0.0) or 0.0), 3) == 1.2
            and round(float(nle_rows[0].get("start", 0.0) or 0.0), 3) == 1.2
            and (state is not None and state.metadata.get("last_editor_sync_source") == "direct_srt_open")
            and NLE_PROJECT_STATE_RUNTIME_KEY not in storage
        ),
        "opened": bool(opened),
        "editor_text": editor_rows[0].get("text") if editor_rows else "",
        "nle_text": nle_rows[0].get("text") if nle_rows else "",
        "editor_start_end": [editor_rows[0].get("start"), editor_rows[0].get("end")] if editor_rows else [],
        "nle_start_end": [nle_rows[0].get("start"), nle_rows[0].get("end")] if nle_rows else [],
        "nle_sync_source": state.metadata.get("last_editor_sync_source") if state is not None else "",
        "nle_precedence_contract": state.metadata.get("direct_srt_precedence_contract") if state is not None else "",
        "project_metadata_restored": bool(editor_rows and editor_rows[0].get("quality", {}).get("confidence_label") == "yellow"),
        "storage_clean_of_runtime_nle": NLE_PROJECT_STATE_RUNTIME_KEY not in storage,
        "blocked_scope": [
            "no_persisted_nle_disk_fields",
            "no_project_text_or_timing_precedence_over_direct_srt",
            "no_ui_layout_or_label_change",
            "no_stt_or_generation_policy_change",
        ],
    }
    (output_dir / "direct_srt_precedence_contract.json").write_bytes(
        dumps_json_bytes(report, sort_keys=True, append_newline=True)
    )
    (output_dir / "direct_srt_precedence_contract.md").write_text(_markdown(report), encoding="utf-8")
    return report


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Direct SRT Precedence Contract Audit",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Passed: `{report['passed']}`",
        f"- Opened: `{report['opened']}`",
        f"- Editor/NLE text: `{report['editor_text']}` / `{report['nle_text']}`",
        f"- Editor start/end: `{report['editor_start_end']}`",
        f"- NLE start/end: `{report['nle_start_end']}`",
        f"- NLE sync source: `{report['nle_sync_source']}`",
        f"- NLE precedence contract: `{report['nle_precedence_contract']}`",
        f"- Project metadata restored: `{report['project_metadata_restored']}`",
        f"- Storage clean of runtime NLE: `{report['storage_clean_of_runtime_nle']}`",
        "",
        "## Blocked Scope",
        "",
        *[f"- `{item}`" for item in report.get("blocked_scope") or []],
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit direct SRT precedence over linked project/NLE metadata.")
    parser.add_argument("--output-dir", default="output/manual_verification/latest/direct_srt_precedence_contract")
    args = parser.parse_args()
    report = build_direct_srt_precedence_report(output_dir=Path(args.output_dir).expanduser())
    print(json.dumps({"passed": report["passed"], "schema": report["schema"]}, ensure_ascii=False))
    return 0 if bool(report.get("passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
