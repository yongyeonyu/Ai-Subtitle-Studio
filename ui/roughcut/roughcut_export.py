# Version: 03.00.26
# Phase: PHASE2
from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from core.roughcut import (
    build_concat_render_plan,
    build_ffmpeg_subtitle_burnin_command,
    edl_to_dict,
    retime_subtitles_for_edl,
    save_edl_json,
    save_markdown_guide,
    save_retimed_srt,
)


class RoughcutExportMixin:
    def _default_output_path(self, suffix: str) -> Path:
        media_path = self._media_path()
        if media_path:
            source = Path(media_path)
            return source.with_name(f"{source.stem}{suffix}")
        return Path.cwd() / f"roughcut{suffix}"

    def _ensure_result(self) -> bool:
        if self._result is None:
            self.refresh_from_editor()
        return self._result is not None and bool(self._result.edl_segments)

    def _save_edl(self):
        if not self._ensure_result():
            self.preview_summary_lbl.setText("저장할 EDL 결과가 없습니다.")
            return
        path = self._default_output_path("_roughcut_edl.json")
        save_edl_json(path, self._result.edl_segments, metadata={"source": self._media_path()})
        self.preview_summary_lbl.setText(f"EDL 저장: {path}")

    def _save_guide(self):
        if self._result is None:
            self.refresh_from_editor()
        if self._result is None:
            self.preview_summary_lbl.setText("저장할 가이드가 없습니다.")
            return
        path = self._default_output_path("_roughcut_guide.md")
        save_markdown_guide(path, self._result.guide_markdown)
        self.preview_summary_lbl.setText(f"가이드 저장: {path}")

    def _save_srt(self):
        if not self._ensure_result():
            self.preview_summary_lbl.setText("저장할 SRT 결과가 없습니다.")
            return
        retimed = retime_subtitles_for_edl(self._editor_segments(), self._result.edl_segments)
        path = self._default_output_path("_roughcut.srt")
        save_retimed_srt(path, retimed)
        self.preview_summary_lbl.setText(f"SRT 저장: {path}")

    def _save_render_plan(self):
        if not self._ensure_result():
            self.preview_summary_lbl.setText("저장할 렌더 계획이 없습니다.")
            return
        media_path = self._media_path()
        if not media_path:
            self.preview_summary_lbl.setText("렌더 계획에는 원본 영상 경로가 필요합니다.")
            return
        output_path = self._default_output_path("_roughcut.mp4")
        srt_path = self._default_output_path("_roughcut.srt")
        subtitled_path = self._default_output_path("_roughcut_subtitled.mp4")
        temp_dir = Path(tempfile.gettempdir()) / "ai_subtitle_studio_roughcut"
        plan = build_concat_render_plan(self._result.edl_segments, output_path, temp_dir)
        plan_path = self._default_output_path("_roughcut_render_plan.json")
        payload = {
            "edl": edl_to_dict(self._result.edl_segments, metadata={"source": media_path}),
            "render_plan": asdict(plan),
            "subtitle_burnin_command": build_ffmpeg_subtitle_burnin_command(output_path, srt_path, subtitled_path),
        }
        plan_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.preview_summary_lbl.setText(f"렌더 계획 저장: {plan_path}")
