# Version: 03.13.04
# Phase: PHASE2
"""Project persistence helpers for editor scan-cut boundaries."""
import os
from datetime import datetime

from core.cut_boundary import sanitize_cut_boundary_rows, sync_project_cut_boundaries
from ui.project.project_session_runtime import set_project_boundary_rows


class EditorScanCutProjectMixin:
    def _project_file_for_cut_boundary_save(self) -> str:
        """Find the project JSON path connected to the current editor."""
        from core.project.project_manager import is_project_file_path

        candidates = [
            "project_file",
            "project_path",
            "_project_file",
            "_project_path",
            "current_project_file",
            "current_project_path",
        ]

        for obj in (self, self.window() if hasattr(self, "window") else None):
            if obj is None:
                continue
            for attr in candidates:
                try:
                    value = str(getattr(obj, attr, "") or "")
                except Exception:
                    value = ""
                if value and is_project_file_path(value) and os.path.exists(value):
                    return value

        try:
            state = getattr(self, "project_state", None) or getattr(self, "_project_state", None)
            if isinstance(state, dict):
                for key in ("path", "project_file", "project_path"):
                    value = str(state.get(key, "") or "")
                    if value and is_project_file_path(value) and os.path.exists(value):
                        return value
        except Exception:
            pass

        return ""

    def _scan_cut_source_context(self, global_sec: float) -> dict:
        try:
            if hasattr(self, "_scan_get_context_for_global_sec"):
                ctx = self._scan_get_context_for_global_sec(float(global_sec))
                if isinstance(ctx, dict):
                    return dict(ctx)
        except Exception:
            pass
        try:
            if hasattr(self, "_resolve_active_context"):
                ctx = self._resolve_active_context(global_sec=float(global_sec))
                if isinstance(ctx, dict):
                    return dict(ctx)
        except Exception:
            pass
        return {}

    def _build_confirmed_cut_boundary_record(
        self,
        global_sec: float,
        *,
        frame: int | None = None,
        score: float | None = None,
        regions: int | None = None,
        reason: str = "manual_scan",
    ) -> dict:
        try:
            global_sec = self._snap_to_frame(float(global_sec))
        except Exception:
            global_sec = float(global_sec or 0.0)

        try:
            fps = self._current_frame_fps()
        except Exception:
            fps = 30.0

        if frame is None:
            try:
                frame = int(round(global_sec * fps))
            except Exception:
                frame = 0

        ctx = self._scan_cut_source_context(global_sec)
        try:
            source_path = str(ctx.get("clip_file", "") or ctx.get("source_path", "") or "")
            local_sec = float(ctx.get("local_sec", global_sec) or global_sec)
            clip_idx = int(ctx.get("clip_idx", 0) or 0)
        except Exception:
            source_path = ""
            local_sec = global_sec
            clip_idx = 0

        return {
            "schema": "cut_boundary.v1",
            "id": f"cut_{int(frame):08d}",
            "time": global_sec,
            "timeline_sec": global_sec,
            "frame": int(frame),
            "timeline_frame": int(frame),
            "fps": float(fps),
            "clip_idx": clip_idx,
            "clip_local_sec": local_sec,
            "source_path": source_path,
            "score": None if score is None else float(score),
            "confidence": None if score is None else float(score),
            "regions": None if regions is None else int(regions),
            "reason": str(reason or "manual_scan"),
            "status": "confirmed",
            "verified": True,
            "confirmed": True,
            "source": "manual_verified",
            "verified_by": "manual_scan",
            "verified_count": 1,
            "detector": "opencv-gray-pyramid60",
            "line_color": "#7FDBFF",
            "line_style": "solid",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

    def _merge_confirmed_cut_boundary_rows(self, rows, row: dict) -> list[dict]:
        merged: list[dict] = []
        try:
            fps = float(row.get("fps", self._current_frame_fps()) or self._current_frame_fps())
        except Exception:
            fps = 30.0
        tolerance_sec = max(0.020, min(0.080, 2.0 / max(1.0, fps)))
        target_sec = float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0)
        target_frame = int(row.get("timeline_frame", row.get("frame", 0)) or 0)
        replaced = False
        for item in list(rows or []):
            if not isinstance(item, dict):
                try:
                    item = {"timeline_sec": float(item or 0.0), "time": float(item or 0.0)}
                except Exception:
                    continue
            existing = dict(item)
            try:
                sec = float(existing.get("timeline_sec", existing.get("time", 0.0)) or 0.0)
            except Exception:
                sec = 0.0
            try:
                frame = int(existing.get("timeline_frame", existing.get("frame", 0)) or 0)
            except Exception:
                frame = 0
            if abs(sec - target_sec) <= tolerance_sec or abs(frame - target_frame) <= 2:
                verified_count = max(
                    1,
                    int(existing.get("verified_count", 1) or 1),
                    int(row.get("verified_count", 1) or 1),
                ) + 1
                merged.append(
                    {
                        **existing,
                        **row,
                        "verified_count": verified_count,
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                    }
                )
                replaced = True
                continue
            merged.append(existing)
        if not replaced:
            merged.append(dict(row))
        merged.sort(
            key=lambda item: (
                float(item.get("timeline_sec", item.get("time", 0.0)) or 0.0),
                int(item.get("timeline_frame", item.get("frame", 0)) or 0),
            )
        )
        for idx, item in enumerate(merged, start=1):
            item["index"] = idx
        return merged

    def _apply_confirmed_cut_boundary_to_ui(self, row: dict, *, remove_nearby_provisionals: bool = True) -> list[dict]:
        if not isinstance(row, dict):
            return list(getattr(self, "_project_boundary_times", []) or [])

        timeline = getattr(self, "timeline", None)
        current_rows = []
        try:
            current_rows = list(getattr(self, "_project_boundary_times", []) or [])
        except Exception:
            current_rows = []
        if not current_rows:
            try:
                canvas = getattr(timeline, "canvas", None)
                current_rows = list(getattr(canvas, "boundary_times", []) or [])
            except Exception:
                current_rows = []
        merged = self._merge_confirmed_cut_boundary_rows(current_rows, row)
        merged = sanitize_cut_boundary_rows(
            list(merged),
            primary_fps=float(row.get("fps", self._current_frame_fps()) or self._current_frame_fps()),
        )
        set_project_boundary_rows(self, list(merged), emit_boundary_signal=False)

        try:
            owner = self.window() if hasattr(self, "window") else None
        except Exception:
            owner = None
        if owner is not None:
            set_project_boundary_rows(owner, list(merged), emit_boundary_signal=True)

        try:
            if timeline is not None and hasattr(timeline, "set_boundary_times"):
                timeline.set_boundary_times(list(merged))
        except Exception:
            pass

        if remove_nearby_provisionals and hasattr(self, "_set_auto_cut_boundary_scan_lines"):
            try:
                sec = float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0)
                fps = float(row.get("fps", self._current_frame_fps()) or self._current_frame_fps())
                tolerance_sec = max(0.020, min(0.080, 2.0 / max(1.0, fps)))
                provisional_rows = []
                for item in list(getattr(self, "_auto_cut_boundary_scan_lines", []) or []):
                    if not isinstance(item, dict):
                        provisional_rows.append(item)
                        continue
                    item_sec = float(item.get("timeline_sec", item.get("time", item.get("start", 0.0))) or 0.0)
                    if abs(item_sec - sec) <= tolerance_sec:
                        continue
                    provisional_rows.append(item)
                self._set_auto_cut_boundary_scan_lines(provisional_rows)
            except Exception:
                pass

        return list(merged)

    def _save_cut_boundary_to_project(self, global_sec: float, frame: int | None = None, score: float | None = None, regions: int | None = None, reason: str = "manual_scan") -> None:
        """Persist a scan-cut boundary into project analysis.cut_boundaries."""
        record = self._build_confirmed_cut_boundary_record(
            global_sec,
            frame=frame,
            score=score,
            regions=regions,
            reason=reason,
        )
        project_path = self._project_file_for_cut_boundary_save()
        if not project_path:
            try:
                print("⚠️ [scan-cut] 프로젝트 파일 경로를 찾지 못해 컷 경계를 JSON에 저장하지 못했습니다.", flush=True)
            except Exception:
                pass
            self._apply_confirmed_cut_boundary_to_ui(record)
            self._scan_terminal_log("⚠️ 컷 경계 저장 생략 · 프로젝트 경로 없음", key="scan-cut-save-missing", min_interval_sec=1.0)
            return

        global_sec = float(record.get("timeline_sec", record.get("time", 0.0)) or 0.0)
        frame = int(record.get("timeline_frame", record.get("frame", 0)) or 0)
        fps = float(record.get("fps", 30.0) or 30.0)

        try:
            from core.project.project_io import read_project_file, write_project_file

            project = read_project_file(project_path)
        except Exception as exc:
            print(f"⚠️ [scan-cut] 프로젝트 파일 읽기 실패: {exc}", flush=True)
            return

        analysis = project.setdefault("analysis", {})
        analysis["cut_boundary_schema"] = "cut_boundaries.v1"
        boundaries = analysis.setdefault("cut_boundaries", [])

        replaced = False
        for idx, item in enumerate(list(boundaries)):
            try:
                old_frame = int(item.get("timeline_frame", item.get("frame", -999999)) or -999999)
            except Exception:
                old_frame = -999999
            if abs(old_frame - int(frame)) <= 1:
                old = dict(item) if isinstance(item, dict) else {}
                record["verified_count"] = max(
                    1,
                    int(old.get("verified_count", 1) or 1),
                    int(record.get("verified_count", 1) or 1),
                ) + 1
                boundaries[idx] = {**old, **record}
                replaced = True
                break

        if not replaced:
            boundaries.append(record)

        boundaries.sort(key=lambda item: float(item.get("timeline_sec", item.get("time", 0.0)) or 0.0))
        analysis["cut_boundary_settings"] = {
            "enabled": True,
            "detector": "opencv-gray-pyramid60",
            "count": len(boundaries),
            "absolute": True,
            "locked": True,
        }

        try:
            sync_project_cut_boundaries(
                project,
                settings=getattr(self, "settings", {}) or {},
                primary_fps=fps,
            )
        except Exception as exc:
            print(f"⚠️ [scan-cut] 컷 경계 editor_state 동기화 실패: {exc}", flush=True)

        project["updated_at"] = datetime.now().isoformat()

        try:
            write_project_file(project_path, project)
            saved_rows = list((analysis.get("cut_boundaries", []) if isinstance(analysis, dict) else []) or [])
            target_row = None
            for item in saved_rows:
                if not isinstance(item, dict):
                    continue
                try:
                    if abs(int(item.get("timeline_frame", item.get("frame", -999999)) or -999999) - int(frame)) <= 1:
                        target_row = dict(item)
                        break
                except Exception:
                    continue
            self._apply_confirmed_cut_boundary_to_ui(target_row or record)
            print(
                f"💾 [scan-cut] project cut boundary saved frame={frame} time={global_sec:.3f}s count={len(boundaries)}",
                flush=True,
            )
            self._scan_terminal_log(
                f"📌 컷 경계 추가 · {frame}f · {global_sec:.3f}s",
                key="scan-cut-confirmed",
                force=True,
            )
        except Exception as exc:
            print(f"⚠️ [scan-cut] 프로젝트 컷 경계 저장 실패: {exc}", flush=True)
