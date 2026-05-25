# Version: 03.14.29
# Phase: PHASE1-B
"""Project cut-boundary snapshot helpers for pipeline generation."""
import json
import os

from core.project.project_io import read_project_file, write_project_file
from core.runtime.logger import get_logger


class PipelineCutBoundarySnapshotMixin:
    def _finalized_cut_boundary_rows(self, rows: list[dict] | None) -> list[dict]:
        """Return rows that may survive after follower verification completes."""
        final_rows: list[dict] = []
        for row in list(rows or []):
            if not isinstance(row, dict):
                continue
            status = str(row.get("status", "") or "").strip().lower()
            source = str(row.get("source", "") or "").strip().lower()
            reason = str(row.get("reason", "") or "").strip().lower()
            detector_stage = str(row.get("detector_stage", "") or "").strip().lower()
            strict = bool(row.get("verified") or row.get("confirmed")) or status in {
                "verified",
                "confirmed",
                "accepted",
                "done",
            }
            manual = source == "manual_verified" or reason.startswith("manual_") or reason.startswith("relative_")
            if manual:
                final_rows.append(dict(row))
                continue
            if bool(row.get("visual_verify_skipped")) and not bool(row.get("confirmed")) and status not in {
                "confirmed",
                "accepted",
                "done",
            }:
                continue
            provisional_like = (
                (bool(row.get("scan_checked")) and not strict)
                or (bool(row.get("follower_relocated")) and not strict)
                or (bool(row.get("rollback_relocated")) and not strict)
                or (status in {"provisional", "checked", "checking", "verifying", "reviewed"} and not strict)
                or "provisional" in source
                or (detector_stage in {"pioneer", "follower", "follower_checked", "audio_pioneer"} and not strict)
            )
            if provisional_like:
                continue
            if strict:
                final_rows.append(dict(row))
                continue
            final_rows.append(dict(row))
        return final_rows

    def _cut_boundary_snapshot_for_pipeline(self, *, force_reload: bool = False) -> dict:
        """Return cached cut-boundary/provisional rows for the current project."""
        provisional_fallback = [dict(item) for item in list(getattr(self, "_cut_boundary_provisional_rows", []) or [])]
        try:
            provisional_signature = json.dumps(
                provisional_fallback,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except Exception:
            provisional_signature = str(len(provisional_fallback))

        ui = getattr(self, "ui", None)
        project_path = str(getattr(ui, "_current_project_path", "") or "")
        mtime_ns = None
        if project_path and os.path.exists(project_path):
            try:
                st = os.stat(project_path)
                mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)))
            except Exception:
                mtime_ns = None

        cache = getattr(self, "_cut_boundary_pipeline_cache", None)
        if (
            not force_reload
            and isinstance(cache, dict)
            and cache.get("project_path") == project_path
            and cache.get("mtime_ns") == mtime_ns
            and cache.get("provisional_signature") == provisional_signature
        ):
            return {
                "cut_boundaries": [dict(item) for item in list(cache.get("cut_boundaries", []) or [])],
                "provisional_cut_boundaries": [dict(item) for item in list(cache.get("provisional_cut_boundaries", []) or [])],
            }

        cut_rows: list[dict] = []
        provisional_rows: list[dict] = provisional_fallback
        try:
            from core.cut_boundary import project_cut_boundaries, project_cut_provisional_boundaries

            if project_path and os.path.exists(project_path):
                project = read_project_file(project_path)
                cut_rows = [dict(item) for item in list(project_cut_boundaries(project) or [])]
                project_provisional = [dict(item) for item in list(project_cut_provisional_boundaries(project) or [])]
                if project_provisional:
                    provisional_rows = project_provisional
        except Exception:
            cut_rows = []
            provisional_rows = provisional_fallback

        snapshot = {
            "project_path": project_path,
            "mtime_ns": mtime_ns,
            "provisional_signature": provisional_signature,
            "cut_boundaries": [dict(item) for item in cut_rows],
            "provisional_cut_boundaries": [dict(item) for item in provisional_rows],
        }
        self._cut_boundary_pipeline_cache = snapshot
        return {
            "cut_boundaries": [dict(item) for item in cut_rows],
            "provisional_cut_boundaries": [dict(item) for item in provisional_rows],
        }

    def _project_cut_boundaries_for_pipeline(self) -> list[dict]:
        """Return saved visual cut boundaries from the current project file."""
        try:
            return list(self._cut_boundary_snapshot_for_pipeline().get("cut_boundaries", []) or [])
        except Exception:
            return []

    def _project_provisional_cut_boundaries_for_pipeline(self) -> list[dict]:
        try:
            return list(self._cut_boundary_snapshot_for_pipeline().get("provisional_cut_boundaries", []) or [])
        except Exception:
            return [dict(item) for item in list(getattr(self, "_cut_boundary_provisional_rows", []) or [])]

    def _project_cut_provisional_boundaries_for_pipeline(self) -> list[dict]:
        """Backward-compatible alias for provisional cut-boundary rows."""
        return self._project_provisional_cut_boundaries_for_pipeline()

    def _clear_completed_cut_boundary_provisionals(
        self,
        project_path: str = "",
        *,
        settings: dict | None = None,
        detected: list[dict] | None = None,
        reviewed_rows: list[dict] | None = None,
        emit: bool = True,
    ) -> None:
        """Remove temporary cut-boundary rows after follower verification finishes."""
        try:
            self._cut_boundary_provisional_rows = []
        except Exception:
            pass
        try:
            self._cut_boundary_pipeline_cache = None
        except Exception:
            pass
        if emit:
            try:
                self._ui_emit("_sig_preview_cut_boundary_scan_lines", [])
            except Exception:
                pass

        path = str(project_path or getattr(getattr(self, "ui", None), "_current_project_path", "") or "")
        if not path or not os.path.exists(path):
            return

        try:
            from core.cut_boundary import normalize_cut_boundaries, sync_project_cut_boundaries

            final_detected = self._finalized_cut_boundary_rows(list(detected or [])) if detected is not None else None
            project = read_project_file(path)
            analysis = project.setdefault("analysis", {})
            if detected is not None:
                analysis["cut_boundaries"] = normalize_cut_boundaries(list(final_detected or []))
            if reviewed_rows is not None:
                analysis["cut_boundary_reviewed_rows"] = normalize_cut_boundaries(list(reviewed_rows or []))
            analysis["cut_boundary_provisional_boundaries"] = []
            sync_project_cut_boundaries(
                project,
                settings=settings if settings is not None else project.get("user_settings", {}),
                provisional_boundaries=[],
            )
            write_project_file(path, project)
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] 완료 임시선 정리 저장 실패: {exc}")
