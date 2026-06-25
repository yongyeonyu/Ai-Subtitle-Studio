# Version: 03.01.32
# Phase: PHASE2
from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from core.roughcut import (
    build_concat_render_plan,
    build_ffmpeg_subtitle_burnin_command,
    edl_to_dict,
    retime_subtitles_for_edl,
    run_render_plan,
    save_edl_json,
    save_markdown_guide,
    save_retimed_srt,
)
from core.video_codec import roughcut_render_mode


class _RoughcutRenderWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, plan, dry_run: bool):
        super().__init__()
        self.plan = plan
        self.dry_run = bool(dry_run)

    def run(self) -> None:
        try:
            result = run_render_plan(self.plan, dry_run=self.dry_run)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)


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
        result = self._result_with_user_edits(self._result)
        save_edl_json(
            path,
            result.edl_segments,
            metadata={"source": self._media_path()},
            chapters=result.chapters,
            major_segments=result.segments,
        )
        self.preview_summary_lbl.setText(f"EDL 저장: {path}")
        self.render_status_lbl.setText("EDL 저장")

    def _save_guide(self):
        if self._result is None:
            self.refresh_from_editor()
        if self._result is None:
            self.preview_summary_lbl.setText("저장할 가이드가 없습니다.")
            return
        path = self._default_output_path("_roughcut_guide.md")
        result = self._result_with_user_edits(self._result)
        save_markdown_guide(path, result.guide_markdown)
        self.preview_summary_lbl.setText(f"가이드 저장: {path}")
        self.render_status_lbl.setText("가이드 저장")

    def _save_srt(self):
        if not self._ensure_result():
            self.preview_summary_lbl.setText("저장할 SRT 결과가 없습니다.")
            return
        export = self.export_roughcut_srt_to_path(str(self._default_output_path("_roughcut.srt")))
        self.preview_summary_lbl.setText(f"SRT 저장: {export['path']}")
        self.render_status_lbl.setText("SRT 저장")

    def export_roughcut_srt_to_path(self, path: str):
        if not self._ensure_result():
            raise ValueError("roughcut_srt_missing")
        result = self._result_with_user_edits(self._result)
        retimed = retime_subtitles_for_edl(self._editor_segments(), result.edl_segments, chapters=result.chapters)
        target = Path(path or "")
        if not str(target):
            target = self._default_output_path("_roughcut.srt")
        target.parent.mkdir(parents=True, exist_ok=True)
        save_retimed_srt(target, retimed)
        sidecar_data = self._write_exact_join_sidecars_for_exported_srt(target, result)
        self.preview_summary_lbl.setText(f"SRT 저장: {target}")
        self.render_status_lbl.setText("SRT 저장")
        return {
            "path": str(target),
            "subtitle_count": len(list(retimed or [])),
            **sidecar_data,
        }

    def _save_render_plan(self):
        plan = self._build_render_plan_for_ui()
        if plan is None:
            return
        result = self._result_with_user_edits(self._result)
        plan_path = self._default_output_path("_roughcut_render_plan.json")
        plan_path.write_text(json.dumps(self._render_plan_payload(plan, result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.preview_summary_lbl.setText(f"렌더 계획 저장: {plan_path}")
        self.render_status_lbl.setText("계획 저장")
        self._append_render_log(f"렌더 계획 저장: {plan_path}")

    def _build_render_plan_for_ui(self):
        if not self._ensure_result():
            self.preview_summary_lbl.setText("저장할 렌더 계획이 없습니다.")
            self.render_status_lbl.setText("계획 없음")
            return None
        result = self._result_with_user_edits(self._result)
        try:
            plan = self._build_render_plan_for_srt_target(self._default_output_path("_roughcut.srt"), result)
        except Exception as exc:
            self.preview_summary_lbl.setText(f"렌더 계획 생성 실패: {exc}")
            self.render_status_lbl.setText("계획 실패")
            self._append_render_log(f"렌더 계획 생성 실패: {exc}")
            return None
        self._last_render_plan = plan
        return plan

    def _render_output_path_for_srt_target(self, target_srt_path: Path, result) -> Path:
        candidate = Path(target_srt_path or self._default_output_path("_roughcut.srt"))
        first_source = next(
            (Path(getattr(segment, "source_path", "") or "") for segment in getattr(result, "edl_segments", ()) if getattr(segment, "source_path", "")),
            None,
        )
        source_suffix = (first_source.suffix if first_source is not None else "") or (Path(self._media_path() or "").suffix) or ".mp4"
        output_path = candidate.with_suffix(source_suffix)
        source_paths = {
            str(Path(getattr(segment, "source_path", "") or "").expanduser())
            for segment in getattr(result, "edl_segments", ()) or ()
            if getattr(segment, "source_path", "")
        }
        if str(output_path.expanduser()) in source_paths:
            output_path = candidate.with_name(f"{candidate.stem}_roughcut{source_suffix}")
        return output_path

    def _build_render_plan_for_srt_target(self, target_srt_path: Path, result):
        output_path = self._render_output_path_for_srt_target(Path(target_srt_path), result)
        temp_dir = Path(tempfile.gettempdir()) / "ai_subtitle_studio_roughcut"
        return build_concat_render_plan(
            result.edl_segments,
            output_path,
            temp_dir,
            render_mode=roughcut_render_mode(),
        )

    def _write_exact_join_sidecars_for_exported_srt(self, target: Path, result) -> dict:
        plan = self._build_render_plan_for_srt_target(target, result)
        render_plan_path = target.with_name(f"{target.stem}_render_plan.json")
        edl_path = target.with_name(f"{target.stem}_edl.json")
        render_plan_path.write_text(
            json.dumps(self._render_plan_payload(plan, result, srt_path=target), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        save_edl_json(
            edl_path,
            result.edl_segments,
            metadata={"source": self._media_path(), "source_srt": str(target)},
            chapters=result.chapters,
            major_segments=result.segments,
        )
        stitched_rows = list(getattr(plan, "stitched_cut_boundaries", ()) or ())
        self._append_render_log(f"러프컷 SRT sidecar 저장: {render_plan_path}")
        self._append_render_log(f"러프컷 EDL sidecar 저장: {edl_path}")
        return {
            "render_plan_path": str(render_plan_path),
            "edl_path": str(edl_path),
            "stitched_cut_boundary_count": len(stitched_rows),
        }

    def _render_plan_payload(self, plan, result, *, srt_path: str | Path | None = None) -> dict:
        media_path = self._media_path()
        output_path = Path(getattr(plan, "output_path", "") or self._default_output_path("_roughcut.mp4"))
        srt_path = Path(srt_path) if srt_path is not None else self._default_output_path("_roughcut.srt")
        subtitled_path = output_path.with_name(f"{output_path.stem}_subtitled{output_path.suffix or '.mp4'}")
        return {
            "stitched_cut_boundaries": list(getattr(plan, "stitched_cut_boundaries", ()) or ()),
            "edl": edl_to_dict(
                result.edl_segments,
                metadata={"source": media_path},
                chapters=result.chapters,
                major_segments=result.segments,
            ),
            "render_plan": asdict(plan),
            "subtitle_burnin_command": build_ffmpeg_subtitle_burnin_command(output_path, srt_path, subtitled_path),
            "render_mode": getattr(plan, "render_mode", roughcut_render_mode()),
            "roughcut_export_style": dict(getattr(self, "_roughcut_export_style", {}) or {}),
        }

    def _dry_run_render_plan(self):
        plan = self._build_render_plan_for_ui()
        if plan is not None:
            self._start_render_worker(plan, dry_run=True)

    def _execute_render_plan(self):
        plan = self._build_render_plan_for_ui()
        if plan is not None:
            self._start_render_worker(plan, dry_run=False)

    def _retry_failed_render(self):
        plan = getattr(self, "_last_failed_render_plan", None)
        if plan is None:
            plan = getattr(self, "_last_render_plan", None)
        if plan is None:
            self.preview_summary_lbl.setText("복구할 렌더 계획이 없습니다.")
            self.render_status_lbl.setText("복구 없음")
            return
        self._start_render_worker(plan, dry_run=False, retry=True)

    def _start_render_worker(self, plan, dry_run: bool = False, retry: bool = False) -> None:
        if getattr(self, "_render_thread", None) is not None:
            self.preview_summary_lbl.setText("렌더 작업이 이미 실행 중입니다.")
            return
        self._last_render_plan = plan
        self._set_render_buttons_enabled(False)
        mode = "검증" if dry_run else ("복구" if retry else "렌더")
        self.render_status_lbl.setText(f"{mode} 중")
        self.preview_summary_lbl.setText(f"러프컷 {mode} 실행 중")
        self._append_render_log(
            f"{mode} 시작: {len(plan.extract_commands)}개 추출 + concat "
            f"(mode={getattr(plan, 'render_mode', 'copy')})"
        )
        for warning in getattr(plan, "warnings", ()) or ():
            self._append_render_log(f"주의: {warning}")

        thread = QThread(self)
        worker = _RoughcutRenderWorker(plan, dry_run=dry_run)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda result: self._on_render_finished(result, dry_run))
        worker.failed.connect(lambda message: self._on_render_failed(message, plan))
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(lambda: self._clear_render_worker(thread))
        thread.finished.connect(thread.deleteLater)
        self._render_thread = thread
        self._render_worker = worker
        thread.start()

    def _on_render_finished(self, result, dry_run: bool) -> None:
        status = "검증 완료" if dry_run else "렌더 완료"
        self.render_status_lbl.setText(status)
        self.preview_summary_lbl.setText(f"{status}: {result.output_path}")
        self._append_render_log(f"{status}: {result.output_path}")
        self._append_render_log(f"실행 명령: {len(result.executed_commands)}개 / return codes: {list(result.return_codes)}")
        if hasattr(self, "btn_render_retry"):
            self.btn_render_retry.setEnabled(False)
        self._last_failed_render_plan = None

    def _on_render_failed(self, message: str, plan) -> None:
        self._last_failed_render_plan = plan
        self.render_status_lbl.setText("렌더 실패")
        self.preview_summary_lbl.setText(f"렌더 실패: {message}")
        self._append_render_log(f"렌더 실패: {message}")
        if hasattr(self, "btn_render_retry"):
            self.btn_render_retry.setEnabled(True)

    def _clear_render_worker(self, thread) -> None:
        if getattr(self, "_render_thread", None) is thread:
            self._render_thread = None
            self._render_worker = None
        self._set_render_buttons_enabled(True)

    def _set_render_buttons_enabled(self, enabled: bool) -> None:
        for name in ("btn_render_dry_run", "btn_render_execute"):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(bool(enabled))
        retry = getattr(self, "btn_render_retry", None)
        if retry is not None:
            retry.setEnabled(bool(enabled) and getattr(self, "_last_failed_render_plan", None) is not None)

    def _append_render_log(self, message: str) -> None:
        line = str(message or "").strip()
        if not line:
            return
        lines = list(getattr(self, "_render_log_lines", []) or [])
        lines.append(line)
        self._render_log_lines = lines[-80:]
        if hasattr(self, "guide_text"):
            self.guide_text.setPlainText("러프컷 렌더 로그\n\n" + "\n".join(self._render_log_lines))
