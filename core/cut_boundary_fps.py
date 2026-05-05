# Version: 03.13.03
# Phase: PHASE2
"""FPS-aware cut-boundary normalization overrides."""

from __future__ import annotations

import os
from typing import Any

from core.frame_time import frame_to_sec, normalize_fps, sec_to_frame
from core.media_info import probe_media


def install_fps_normalizers(namespace: dict) -> None:
    CUT_BOUNDARY_SCHEMA = namespace["CUT_BOUNDARY_SCHEMA"]
    CUT_BOUNDARY_PROVISIONAL_SCHEMA = namespace["CUT_BOUNDARY_PROVISIONAL_SCHEMA"]
    cut_boundary_enabled = namespace["cut_boundary_enabled"]

    # === FRAME FPS NORMALIZE PATCH START ===

    def _cut_boundary_row_fps(row, fallback: float = 30.0) -> float:
        """
        컷 경계 row의 fps를 우선 사용한다.
        중요:
        - frame=1950, fps=59.94이면 32.532초가 맞다.
        - frame=1950을 fallback 30fps로 계산하면 65초가 되어 시간이 2배로 밀린다.
        """
        try:
            fallback = normalize_fps(float(fallback or 30.0))
        except Exception:
            fallback = 30.0

        if isinstance(row, dict):
            for key in ("fps", "frame_rate", "timeline_frame_rate"):
                try:
                    value = float(row.get(key) or 0.0)
                    if value > 1.0:
                        return normalize_fps(value)
                except Exception:
                    pass

        return fallback


    # === VIDEO FPS NORMALIZE OVERRIDE START ===

    def _cut_boundary_video_paths_from_obj(obj) -> list[str]:
        paths: list[str] = []
        video_exts = (".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm")

        def walk(x):
            if isinstance(x, dict):
                for value in x.values():
                    walk(value)
            elif isinstance(x, list):
                for value in x:
                    walk(value)
            elif isinstance(x, str):
                raw = x.strip()
                if raw.lower().endswith(video_exts) and os.path.exists(raw):
                    paths.append(raw)

        walk(obj)
        return paths


    def _cut_boundary_probe_fps(path: str) -> float | None:
        try:
            if not path or not os.path.exists(path):
                return None
            info = probe_media(path)
            fps = float(info.get("fps", 0.0) or 0.0)
            if fps > 1.0:
                return normalize_fps(fps)
        except Exception:
            pass
        return None


    def _cut_boundary_fps_from_row(row, fallback: float = 30.0) -> float:
        try:
            fallback = normalize_fps(float(fallback or 30.0))
        except Exception:
            fallback = 30.0

        if not isinstance(row, dict):
            return fallback

        # 1) row 자체 fps 우선
        for key in ("fps", "frame_rate", "timeline_frame_rate", "source_fps", "video_fps"):
            try:
                value = float(row.get(key) or 0.0)
                if value > 1.0:
                    return normalize_fps(value)
            except Exception:
                pass

        # 2) row의 source_path 실제 영상 fps
        for key in ("source_path", "clip_file", "file", "media_path", "path"):
            try:
                path = str(row.get(key) or "")
            except Exception:
                path = ""
            fps = _cut_boundary_probe_fps(path)
            if fps:
                return fps

        return fallback


    def _cut_boundary_infer_fps(rows=None, project=None, fallback: float = 30.0) -> float:
        try:
            fallback = normalize_fps(float(fallback or 30.0))
        except Exception:
            fallback = 30.0

        rows = list(rows or [])

        # 1) row fps/source_path
        for row in rows:
            fps = _cut_boundary_fps_from_row(row, fallback)
            if abs(float(fps) - float(fallback)) > 0.001 or fps > 30.1:
                return normalize_fps(fps)

        # 2) project timebase
        if isinstance(project, dict):
            for path in (
                ("timeline", "timebase", "primary_fps"),
                ("frame_timebase", "primary_fps"),
                ("timebase", "primary_fps"),
                ("timeline", "fps"),
                ("fps",),
                ("video_fps",),
            ):
                cur = project
                try:
                    for key in path:
                        cur = cur.get(key, {})
                    value = float(cur or 0.0)
                    if value > 1.0:
                        return normalize_fps(value)
                except Exception:
                    pass

            # 3) project 내부 영상 파일 probe
            for video_path in _cut_boundary_video_paths_from_obj(project):
                fps = _cut_boundary_probe_fps(video_path)
                if fps:
                    return fps

        return fallback


    def normalize_cut_boundaries(
        boundaries: list[dict[str, Any]] | None,
        *,
        primary_fps: float = 30.0,
    ) -> list[dict[str, Any]]:
        """
        컷 경계 정규화.

        Canonical:
        - frame/timeline_frame이 있으면 frame이 기준.
        - seconds는 frame / fps에서 파생.
        - fps는 row.fps 또는 실제 source_path 영상 fps를 우선.
        """
        try:
            base_fps = normalize_fps(primary_fps or 30.0)
        except Exception:
            base_fps = 30.0

        out: list[dict[str, Any]] = []
        seen: set[tuple[int, int]] = set()

        for idx, item in enumerate(boundaries or []):
            if not isinstance(item, dict):
                continue

            row = dict(item)
            fps = _cut_boundary_fps_from_row(row, base_fps)

            frame = None
            for key in ("timeline_frame", "frame", "start_frame", "timeline_start_frame"):
                try:
                    value = row.get(key)
                    if value is not None:
                        frame = int(round(float(value)))
                        break
                except Exception:
                    pass

            if frame is None:
                sec = None
                for key in ("timeline_sec", "time", "start", "timeline_start"):
                    try:
                        value = row.get(key)
                        if value is not None:
                            sec = float(value)
                            break
                    except Exception:
                        pass

                if sec is None:
                    continue

                try:
                    frame = sec_to_frame(sec, fps)
                except Exception:
                    continue

            frame = int(frame)
            if frame <= 0:
                continue

            try:
                sec = frame_to_sec(frame, fps)
            except Exception:
                sec = frame / float(fps or 30.0)

            if sec <= 0.0:
                continue

            seen_key = (frame, int(round(float(fps) * 1000)))
            if seen_key in seen:
                continue
            seen.add(seen_key)

            row.update(
                {
                    "schema": "cut_boundary.v1",
                    "id": str(row.get("id") or f"cut_{frame:08d}"),
                    "time": sec,
                    "timeline_sec": sec,
                    "frame": frame,
                    "timeline_frame": frame,
                    "fps": fps,
                    "frame_rate": fps,
                    "timeline_frame_rate": fps,
                    "absolute": True,
                    "locked": True,
                    "source": str(row.get("source") or "visual"),
                }
            )
            row.setdefault("detector", "opencv-gray-pyramid60")
            row.setdefault("reason", "visual_cut_boundary")
            row.setdefault("index", idx + 1)

            out.append(row)

        out.sort(
            key=lambda item: (
                int(item.get("timeline_frame", item.get("frame", 0)) or 0),
                float(item.get("timeline_sec", 0.0) or 0.0),
            )
        )

        for idx, item in enumerate(out, start=1):
            item["index"] = idx

        return out


    def project_cut_boundaries(project: dict[str, Any] | None, *, primary_fps: float | None = None) -> list[dict[str, Any]]:
        if not isinstance(project, dict):
            return []

        analysis = project.get("analysis", {}) or {}
        raw = analysis.get("cut_boundaries")

        if not isinstance(raw, list):
            raw = ((project.get("editor_state", {}) or {}).get("multiclip", {}) or {}).get("cut_boundaries")

        if not isinstance(raw, list):
            raw = []

        fps = _cut_boundary_infer_fps(raw, project, primary_fps or 30.0)
        return normalize_cut_boundaries(raw, primary_fps=fps)


    def project_cut_provisional_boundaries(
        project: dict[str, Any] | None,
        *,
        primary_fps: float | None = None,
    ) -> list[dict[str, Any]]:
        if not isinstance(project, dict):
            return []

        analysis = project.get("analysis", {}) or {}
        raw = analysis.get("cut_boundary_provisional_boundaries")
        if not isinstance(raw, list):
            raw = ((project.get("editor_state", {}) or {}).get("analysis", {}) or {}).get("cut_boundary_provisional_boundaries")
        if not isinstance(raw, list):
            raw = ((project.get("editor_state", {}) or {}).get("multiclip", {}) or {}).get("cut_boundary_provisional_boundaries")
        if not isinstance(raw, list):
            raw = []

        fps = _cut_boundary_infer_fps(raw, project, primary_fps or 30.0)
        rows = normalize_cut_boundaries(raw, primary_fps=fps)
        for idx, row in enumerate(rows, start=1):
            row.setdefault("status", "provisional")
            row.setdefault("detector_stage", "pioneer")
            row["index"] = idx
        return rows


    def sync_project_cut_boundaries(
        project: dict[str, Any],
        *,
        settings: dict[str, Any] | None = None,
        primary_fps: float = 30.0,
        provisional_boundaries: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if not isinstance(project, dict):
            return []

        analysis = project.setdefault("analysis", {})
        raw = analysis.get("cut_boundaries", [])

        fps = _cut_boundary_infer_fps(raw if isinstance(raw, list) else [], project, primary_fps or 30.0)
        boundaries = project_cut_boundaries(project, primary_fps=fps)
        if provisional_boundaries is None:
            provisional_rows = project_cut_provisional_boundaries(project, primary_fps=fps)
        else:
            provisional_rows = normalize_cut_boundaries(provisional_boundaries, primary_fps=fps)
            for idx, row in enumerate(provisional_rows, start=1):
                row.setdefault("status", "provisional")
                row.setdefault("detector_stage", "pioneer")
                row["index"] = idx

        analysis["cut_boundary_schema"] = CUT_BOUNDARY_SCHEMA
        analysis["cut_boundaries"] = boundaries
        analysis["cut_boundary_provisional_schema"] = CUT_BOUNDARY_PROVISIONAL_SCHEMA
        analysis["cut_boundary_provisional_boundaries"] = list(provisional_rows)
        analysis["cut_boundary_settings"] = {
            "enabled": cut_boundary_enabled(settings if settings is not None else project.get("user_settings")),
            "detector": "opencv-gray-pyramid60",
            "count": len(boundaries),
            "provisional_count": len(provisional_rows),
            "absolute": True,
            "locked": True,
            "fps": fps,
        }

        editor_state = project.get("editor_state")
        if isinstance(editor_state, dict):
            editor_state.setdefault("analysis", {})
            editor_state["analysis"]["cut_boundary_schema"] = CUT_BOUNDARY_SCHEMA
            editor_state["analysis"]["cut_boundaries"] = list(boundaries)
            editor_state["analysis"]["cut_boundary_provisional_schema"] = CUT_BOUNDARY_PROVISIONAL_SCHEMA
            editor_state["analysis"]["cut_boundary_provisional_boundaries"] = list(provisional_rows)
            multiclip = editor_state.setdefault("multiclip", {})
            multiclip["cut_boundary_schema"] = CUT_BOUNDARY_SCHEMA
            multiclip["cut_boundaries"] = list(boundaries)
            multiclip["cut_boundary_provisional_schema"] = CUT_BOUNDARY_PROVISIONAL_SCHEMA
            multiclip["cut_boundary_provisional_boundaries"] = list(provisional_rows)

        return boundaries

    # === VIDEO FPS NORMALIZE OVERRIDE END ===


    namespace.update({
        "_cut_boundary_row_fps": _cut_boundary_row_fps,
        "normalize_cut_boundaries": normalize_cut_boundaries,
        "_cut_boundary_video_paths_from_obj": _cut_boundary_video_paths_from_obj,
        "_cut_boundary_probe_fps": _cut_boundary_probe_fps,
        "_cut_boundary_fps_from_row": _cut_boundary_fps_from_row,
        "_cut_boundary_infer_fps": _cut_boundary_infer_fps,
        "project_cut_boundaries": project_cut_boundaries,
        "project_cut_provisional_boundaries": project_cut_provisional_boundaries,
        "sync_project_cut_boundaries": sync_project_cut_boundaries,
    })
