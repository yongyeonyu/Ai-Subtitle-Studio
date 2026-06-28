"""
Native-leaning helpers for project/SRT editor open flows.

These helpers centralize the fast editor hydration path used when opening a
project, opening an SRT that is linked to a project, or opening a subtitle-only
SRT. The actual subtitle document load still goes through the editor's shared
canvas loader, which in turn already uses the Swift/native preparation path
when available.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QTimer

from core.cut_boundary import normalize_cut_boundaries
from core.project.project_manager import (
    PROJECTS_DIR,
    is_project_file_path,
    load_project,
    project_file_path_for_name,
)
from core.runtime.logger import get_logger
from ui.project.project_session_runtime import (
    apply_project_multiclip_runtime,
    attach_project_session,
)


def schedule_native_open_editor_media(
    owner,
    editor,
    media_path: str | None,
    *,
    primary_delay_ms: int = 72,
    waveform_delay_ms: int = 260,
    prefer_fast_first_paint: bool = True,
    defer_waveform_until_start: bool = True,
) -> None:
    """Show the editor shell first, then hydrate media in a staged way."""
    path = str(media_path or "").strip()
    if editor is None or not path:
        return

    token = object()
    try:
        setattr(editor, "_native_open_media_token", token)
    except Exception:
        pass

    def _is_current_target() -> bool:
        current = getattr(owner, "_editor_widget", None)
        return current is editor and getattr(editor, "_native_open_media_token", None) is token

    def _load_waveform() -> None:
        if not _is_current_target():
            return
        try:
            if bool(getattr(owner, "_multiclip_boundaries", []) or []):
                return
            timeline = getattr(editor, "timeline", None)
            loader = getattr(timeline, "load_waveform", None)
            if callable(loader):
                loader(path)
        except Exception as exc:
            get_logger().log(f"⚠️ 에디터 지연 파형 로드 실패: {exc}")

    def _load_primary() -> None:
        if not _is_current_target():
            return
        loader = getattr(editor, "_load_video", None)
        if not callable(loader):
            return
        try:
            loader(
                path,
                load_waveform=not prefer_fast_first_paint,
                defer_media_probe=bool(prefer_fast_first_paint),
            )
        except TypeError:
            try:
                loader(path, load_waveform=not prefer_fast_first_paint)
            except TypeError:
                loader(path)
            return
        except Exception as exc:
            get_logger().log(f"⚠️ 에디터 지연 미디어 로드 실패: {exc}")
            return
        if prefer_fast_first_paint and not defer_waveform_until_start:
            QTimer.singleShot(max(0, int(waveform_delay_ms)), _load_waveform)
        elif prefer_fast_first_paint:
            # Waveform is editor convenience data; keep media-open snappy and load it after Start.
            try:
                setattr(editor, "_deferred_open_waveform_path", path)
                setattr(editor, "_deferred_open_waveform_loaded", False)
            except Exception:
                pass

    QTimer.singleShot(max(0, int(primary_delay_ms)), _load_primary)


def schedule_native_editor_post_open_tasks(
    owner,
    editor,
    *,
    restore_workspace_callback: Callable[[], None] | None = None,
    apply_project_ui_callback: Callable[[], None] | None = None,
    load_multiclip_waveform_callback: Callable[[], None] | None = None,
    preload_segments_callback: Callable[[], None] | None = None,
) -> None:
    """Defer non-critical editor-open work until after the first paint."""
    if owner is None or editor is None:
        return

    token = object()
    try:
        setattr(editor, "_native_open_postload_token", token)
    except Exception:
        pass

    def _is_current_target() -> bool:
        current = getattr(owner, "_editor_widget", None)
        return current is editor and getattr(editor, "_native_open_postload_token", None) is token

    def _schedule(delay_ms: int, callback: Callable[[], None] | None) -> None:
        if not callable(callback):
            return

        def _run() -> None:
            if not _is_current_target():
                return
            try:
                callback()
            except Exception as exc:
                get_logger().log(f"⚠️ 에디터 지연 초기화 실패: {exc}")

        QTimer.singleShot(max(0, int(delay_ms)), _run)

    _schedule(180, restore_workspace_callback)
    _schedule(280, apply_project_ui_callback)
    _schedule(440, load_multiclip_waveform_callback)
    _schedule(680, preload_segments_callback)


def _is_subtitle_path(path: str | None) -> bool:
    return str(path or "").strip().lower().endswith((".srt", ".vtt", ".ass", ".ssa"))


def _can_load_waveform_for_direct_srt(media_path: str | None, srt_path: str | None = None) -> bool:
    media = normalized_open_path(media_path)
    if not media or _is_subtitle_path(media):
        return False
    subtitle = normalized_open_path(srt_path)
    return not subtitle or media != subtitle


def schedule_direct_srt_waveform_load(
    owner,
    editor,
    media_path: str | None,
    srt_path: str | None = None,
    *,
    delay_ms: int = 420,
) -> None:
    """Subtitle-only edit mode has no generation start event, so load its waveform after first paint."""
    if owner is None or editor is None or not _can_load_waveform_for_direct_srt(media_path, srt_path):
        return
    path = str(media_path or "").strip()
    token = getattr(editor, "_native_open_media_token", None)

    try:
        if not str(getattr(editor, "_deferred_open_waveform_path", "") or "").strip():
            setattr(editor, "_deferred_open_waveform_path", path)
        setattr(editor, "_deferred_open_waveform_loaded", bool(getattr(editor, "_deferred_open_waveform_loaded", False)))
    except Exception:
        pass

    def _load() -> None:
        current = getattr(owner, "_editor_widget", None)
        if current is not editor:
            return
        if token is not None and getattr(editor, "_native_open_media_token", None) is not token:
            return
        try:
            window_getter = getattr(editor, "window", None)
            scope = window_getter() if callable(window_getter) else owner
        except RuntimeError:
            return
        except Exception:
            scope = owner
        if bool(getattr(scope, "_multiclip_boundaries", []) or []):
            return
        if bool(getattr(editor, "_deferred_open_waveform_loaded", False)):
            return
        deferred_loader = getattr(editor, "_load_deferred_open_waveform", None)
        if callable(deferred_loader):
            try:
                if deferred_loader(reason="direct_srt_open"):
                    return
            except TypeError:
                try:
                    if deferred_loader():
                        return
                except Exception:
                    pass
            except Exception:
                pass
        timeline = getattr(editor, "timeline", None)
        loader = getattr(timeline, "load_waveform", None) if timeline is not None else None
        if not callable(loader):
            return
        try:
            setattr(editor, "_deferred_open_waveform_loaded", True)
            try:
                loader(path, force=True)
            except TypeError:
                loader(path)
        except Exception as exc:
            try:
                setattr(editor, "_deferred_open_waveform_loaded", False)
            except Exception:
                pass
            get_logger().log(f"⚠️ 자막 편집 파형 로드 실패: {exc}")

    QTimer.singleShot(max(0, int(delay_ms)), _load)


def schedule_direct_srt_media_finalize(
    owner,
    editor,
    media_path: str | None,
    srt_path: str | None = None,
    *,
    delay_ms: int = 180,
) -> None:
    """Subtitle-only edit mode should finish media probe/bootstrap without waiting for Start."""
    if owner is None or editor is None or not _can_load_waveform_for_direct_srt(media_path, srt_path):
        return
    path = str(media_path or "").strip()
    token = getattr(editor, "_native_open_media_token", None)

    def _is_current_target() -> bool:
        current = getattr(owner, "_editor_widget", None)
        if current is not editor:
            return False
        if token is not None and getattr(editor, "_native_open_media_token", None) is not token:
            return False
        return True

    def _finalize() -> None:
        if not _is_current_target():
            return
        player = getattr(editor, "video_player", None)
        try:
            total_time = float(getattr(player, "total_time", 0.0) or 0.0)
        except Exception:
            total_time = 0.0
        try:
            source_status = str(getattr(player, "_source_info_status_text", "") or "").strip()
        except Exception:
            source_status = ""
        needs_sync_probe = total_time <= 0.1 or source_status in {
            "영상 정보를 불러오는 중...",
            "영상을 불러오는 중...",
            "메타데이터 준비 중",
        }
        if needs_sync_probe and not bool(getattr(editor, "_direct_srt_media_finalize_forced", False)):
            loader = getattr(editor, "_load_video", None)
            if callable(loader):
                try:
                    setattr(editor, "_direct_srt_media_finalize_forced", True)
                except Exception:
                    pass
                try:
                    loader(
                        path,
                        load_waveform=False,
                        defer_media_probe=False,
                    )
                except TypeError:
                    try:
                        loader(path, load_waveform=False)
                    except TypeError:
                        loader(path)
                except Exception as exc:
                    get_logger().log(f"⚠️ 자막 편집 미디어 최종화 실패: {exc}")
        runtime_refresh = getattr(owner, "_refresh_opened_editor_runtime", None)
        if callable(runtime_refresh):
            try:
                runtime_refresh(editor)
            except Exception:
                pass

    QTimer.singleShot(max(0, int(delay_ms)), _finalize)


def normalized_open_path(path: str | None) -> str:
    if not path:
        return ""
    try:
        return os.path.normcase(os.path.abspath(os.path.expanduser(str(path))))
    except Exception:
        return ""


def project_sidecar_candidates_for_srt(srt_path: str, media_path: str | None = None) -> list[str]:
    """Return likely project JSON files for a direct SRT open."""
    candidates: list[str] = []

    def _add(path: str | None) -> None:
        if not path:
            return
        normalized = normalized_open_path(path)
        if normalized and normalized not in candidates and os.path.exists(normalized):
            candidates.append(normalized)

    srt_abs = normalized_open_path(srt_path)
    if srt_abs:
        srt_dir = os.path.dirname(srt_abs)
        srt_stem = os.path.splitext(os.path.basename(srt_abs))[0]
        _add(project_file_path_for_name(srt_stem))
        _add(os.path.join(PROJECTS_DIR, f"{srt_stem}.json"))

        if os.path.basename(srt_dir) == "subtitles":
            asset_dir = os.path.dirname(srt_dir)
            asset_name = os.path.basename(asset_dir)
            if asset_name.endswith(".assets"):
                project_name = asset_name[: -len(".assets")]
                project_folder = os.path.dirname(asset_dir)
                _add(project_file_path_for_name(project_name, folder=project_folder))
                _add(os.path.join(project_folder, f"{project_name}.json"))

    media_abs = normalized_open_path(media_path)
    if media_abs and media_abs != srt_abs:
        media_stem = os.path.splitext(os.path.basename(media_abs))[0]
        _add(project_file_path_for_name(media_stem))
        _add(os.path.join(PROJECTS_DIR, f"{media_stem}.json"))

    try:
        for name in os.listdir(PROJECTS_DIR):
            if not is_project_file_path(name):
                continue
            _add(os.path.join(PROJECTS_DIR, name))
    except Exception:
        pass

    return candidates


def stitched_cut_boundary_sidecar_candidates_for_srt(srt_path: str, media_path: str | None = None) -> list[str]:
    """Return roughcut export sidecars that may carry exact stitched joins."""
    candidates: list[str] = []

    def _add(path: str | None) -> None:
        if not path:
            return
        normalized = normalized_open_path(path)
        if normalized and normalized not in candidates and os.path.exists(normalized):
            candidates.append(normalized)

    seen_pairs: set[tuple[str, str]] = set()
    for raw in (srt_path, media_path):
        absolute = normalized_open_path(raw)
        if not absolute:
            continue
        folder = os.path.dirname(absolute)
        stem = os.path.splitext(os.path.basename(absolute))[0]
        pair = (folder, stem)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        for suffix in ("_edl.json", "_render_plan.json", "_roughcut_edl.json", "_roughcut_render_plan.json"):
            _add(os.path.join(folder, f"{stem}{suffix}"))
    return candidates


def load_stitched_cut_boundaries_for_srt_open(srt_path: str, media_path: str | None = None) -> tuple[list[dict], str]:
    """Load exact stitched cut boundaries from adjacent roughcut export artifacts."""
    for sidecar_path in stitched_cut_boundary_sidecar_candidates_for_srt(srt_path, media_path):
        try:
            payload = json.loads(Path(sidecar_path).read_text(encoding="utf-8"))
        except Exception:
            continue
        rows = payload.get("stitched_cut_boundaries") if isinstance(payload, dict) else None
        if not rows and isinstance(payload, dict):
            edl_payload = payload.get("edl")
            if isinstance(edl_payload, dict):
                rows = edl_payload.get("stitched_cut_boundaries")
        if not rows and isinstance(payload, dict):
            render_plan = payload.get("render_plan")
            if isinstance(render_plan, dict):
                rows = render_plan.get("stitched_cut_boundaries")
        normalized = normalize_cut_boundaries(list(rows or []))
        if normalized:
            return normalized, sidecar_path
    return [], ""


def project_matches_opened_srt(project: dict, srt_path: str, media_path: str | None = None) -> bool:
    if not isinstance(project, dict):
        return False
    srt_abs = normalized_open_path(srt_path)
    media_abs = normalized_open_path(media_path)
    try:
        from core.project.project_assets import resolve_project_asset_path
        from core.project.project_context import project_media_files
    except Exception:
        resolve_project_asset_path = None
        project_media_files = None

    raw_srt_paths = [
        project.get("srt_path"),
        (project.get("subtitle", {}) or {}).get("path"),
        (project.get("subtitles", {}) or {}).get("srt_path"),
        ((project.get("editor_state", {}) or {}).get("subtitles", {}) or {}).get("srt_path"),
    ]
    subtitles = project.get("subtitles", {}) if isinstance(project.get("subtitles"), dict) else {}
    external_track = subtitles.get("external_track")
    if isinstance(external_track, dict):
        raw_srt_paths.append(external_track.get("path"))
    external_tracks = subtitles.get("external_tracks")
    if isinstance(external_tracks, dict):
        for track in external_tracks.values():
            if isinstance(track, dict):
                raw_srt_paths.append(track.get("path"))
    asset_storage = project.get("asset_storage", {}) if isinstance(project.get("asset_storage"), dict) else {}
    tracks = asset_storage.get("tracks", {}) if isinstance(asset_storage.get("tracks"), dict) else {}
    for key, track in tracks.items():
        if str(key) in {"final", "subtitle_final"} and isinstance(track, dict):
            raw_srt_paths.append(track.get("path"))

    for raw in raw_srt_paths:
        if not raw:
            continue
        try:
            resolved = resolve_project_asset_path(project, raw) if callable(resolve_project_asset_path) else str(raw)
        except Exception:
            resolved = str(raw)
        if normalized_open_path(resolved) == srt_abs:
            return True

    if media_abs and callable(project_media_files):
        try:
            for path in project_media_files(project):
                if normalized_open_path(path) == media_abs:
                    return True
        except Exception:
            pass
    return False


def find_project_for_srt_open(srt_path: str, media_path: str | None = None) -> tuple[str, dict | None]:
    for project_path in project_sidecar_candidates_for_srt(srt_path, media_path):
        project = load_project(project_path, hydrate_text_assets=True)
        if not isinstance(project, dict):
            continue
        if project_matches_opened_srt(project, srt_path, media_path):
            return project_path, project

        srt_abs = normalized_open_path(srt_path)
        srt_dir = os.path.dirname(srt_abs)
        if os.path.basename(srt_dir) == "subtitles":
            asset_dir = os.path.dirname(srt_dir)
            asset_name = os.path.basename(asset_dir)
            expected = project_file_path_for_name(
                asset_name.removesuffix(".assets"),
                folder=os.path.dirname(asset_dir),
            )
            expected_json = os.path.splitext(expected)[0] + ".json"
            if normalized_open_path(project_path) in {
                normalized_open_path(expected),
                normalized_open_path(expected_json),
            }:
                return project_path, project
    return "", None


def normalized_segment_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def segment_metadata_match_score(srt_seg: dict, project_seg: dict, srt_index: int, project_index: int) -> int:
    try:
        start_delta = abs(float(srt_seg.get("start", 0.0) or 0.0) - float(project_seg.get("start", 0.0) or 0.0))
        end_delta = abs(float(srt_seg.get("end", 0.0) or 0.0) - float(project_seg.get("end", 0.0) or 0.0))
    except Exception:
        start_delta = end_delta = 999.0
    srt_text = normalized_segment_text(srt_seg.get("text"))
    project_text = normalized_segment_text(project_seg.get("text"))
    score = 0
    if start_delta <= 0.05 and end_delta <= 0.05:
        score += 50
    elif start_delta <= 0.25 and end_delta <= 0.25:
        score += 34
    elif start_delta <= 0.6 and end_delta <= 0.6:
        score += 16
    if srt_text and project_text:
        if srt_text == project_text:
            score += 44
        elif srt_text in project_text or project_text in srt_text:
            score += 22
    if srt_index == project_index:
        score += 12
    return score


def merge_srt_segments_with_project_metadata(srt_segments: list[dict], project_segments: list[dict]) -> list[dict]:
    """Preserve SRT timing/text while restoring project-only UI metadata."""
    if not srt_segments or not project_segments:
        return [dict(seg) for seg in list(srt_segments or []) if isinstance(seg, dict)]
    project_rows = [dict(seg) for seg in list(project_segments or []) if isinstance(seg, dict)]
    native_matches = None
    try:
        from core.native_swift_timeline import match_srt_project_metadata_via_swift

        native_matches = match_srt_project_metadata_via_swift(
            srt_segments=list(srt_segments or []),
            project_segments=project_rows,
        )
    except Exception:
        native_matches = None
    used: set[int] = set()
    merged: list[dict] = []
    timing_keys = {
        "start",
        "end",
        "timeline_start",
        "timeline_end",
        "start_frame",
        "end_frame",
        "timeline_start_frame",
        "timeline_end_frame",
        "frame_range",
    }
    preserve_srt_keys = {"line", "index", "text", "is_gap", *timing_keys}

    for idx, raw_srt in enumerate(list(srt_segments or [])):
        if not isinstance(raw_srt, dict):
            continue
        best_idx = -1
        if isinstance(native_matches, list) and idx < len(native_matches):
            try:
                native_idx = int(native_matches[idx])
            except Exception:
                native_idx = -1
            if native_idx >= 0 and native_idx not in used and native_idx < len(project_rows):
                best_idx = native_idx
        if best_idx < 0:
            best_score = -1
            for project_idx, project_seg in enumerate(project_rows):
                if project_idx in used:
                    continue
                score = segment_metadata_match_score(raw_srt, project_seg, idx, project_idx)
                if score > best_score:
                    best_idx = project_idx
                    best_score = score

            if best_score < 30 and len(project_rows) == len(srt_segments) and idx < len(project_rows) and idx not in used:
                best_idx = idx
            elif best_idx < 0 and idx < len(project_rows) and idx not in used:
                best_idx = idx

        item = dict(raw_srt)
        item["line"] = idx
        if best_idx >= 0:
            project_seg = project_rows[best_idx]
            used.add(best_idx)
            try:
                timing_close = (
                    abs(float(item.get("start", 0.0) or 0.0) - float(project_seg.get("start", 0.0) or 0.0)) <= 0.08
                    and abs(float(item.get("end", 0.0) or 0.0) - float(project_seg.get("end", 0.0) or 0.0)) <= 0.08
                )
            except Exception:
                timing_close = False
            for key, value in project_seg.items():
                if key in preserve_srt_keys:
                    continue
                if key in timing_keys and not timing_close:
                    continue
                item[key] = value
        merged.append(item)
    return merged


def restore_project_context_for_srt_open(owner, editor, project_path: str, project: dict | None) -> None:
    if editor is None or not project_path or not isinstance(project, dict):
        return
    try:
        editor._linked_project_path_for_srt = project_path
    except Exception:
        pass

    try:
        refresher = getattr(editor, "_refresh_cut_boundary_placeholder_from_project", None)
        if callable(refresher):
            QTimer.singleShot(0, refresher)
            QTimer.singleShot(180, refresher)
    except Exception:
        pass

    try:
        if hasattr(editor, "_schedule_timeline"):
            editor._schedule_timeline()
        elif hasattr(editor, "_redraw_timeline"):
            editor._redraw_timeline()
    except Exception:
        pass

    schedule_native_editor_post_open_tasks(
        owner,
        editor,
        restore_workspace_callback=(
            (lambda o=owner, e=editor, p=project_path: o._restore_workspace(e, p))
            if hasattr(owner, "_restore_workspace")
            else None
        ),
    )


def schedule_editor_fit_to_view(editor, delay_ms: int = 120) -> None:
    if not hasattr(editor, "timeline"):
        return
    timeline = editor.timeline
    try:
        preferred_seconds = (
            timeline.preferred_edit_window_seconds()
            if hasattr(timeline, "preferred_edit_window_seconds")
            else float(getattr(timeline, "_preferred_edit_window_seconds", 10.0) or 10.0)
        )
    except Exception:
        preferred_seconds = 10.0
    first_delay = max(80, int(delay_ms * 0.66))
    delays = (first_delay, max(delay_ms, first_delay + 60), max(delay_ms + 180, 340))
    try:
        if hasattr(editor, "_schedule_initial_open_layout"):
            editor._schedule_initial_open_layout(delays=delays)
            return
        if hasattr(timeline, "schedule_initial_open_view"):
            timeline.schedule_initial_open_view(
                delays=delays,
                seconds=preferred_seconds,
                start_sec=0.0,
            )
        elif hasattr(timeline, "schedule_time_window_seconds"):
            timeline.schedule_time_window_seconds(
                preferred_seconds,
                start_sec=0.0,
                delays=delays,
            )
        elif hasattr(timeline, "schedule_fit_to_view"):
            timeline.schedule_fit_to_view((0, delay_ms, max(delay_ms + 140, 260)))
        elif hasattr(timeline, "fit_to_view"):
            QTimer.singleShot(max(0, int(delay_ms)), timeline.fit_to_view)
    except Exception:
        pass


def refresh_opened_editor_runtime(editor) -> None:
    """Restore live editor state after SRT/project hydration."""
    if editor is None:
        return
    try:
        cached = getattr(editor, "_cached_segs", None)
        if isinstance(cached, list) and cached:
            editor._rebuild_subtitle_memory_cache(cached)
        else:
            editor._rebuild_subtitle_memory_cache()
    except Exception:
        pass

    try:
        if hasattr(editor, "_refresh_editor_timestamp_metadata"):
            editor._refresh_editor_timestamp_metadata(full=True)
    except Exception:
        pass

    text_edit = getattr(editor, "text_edit", None)
    try:
        if text_edit is not None and hasattr(text_edit, "update_margins"):
            text_edit.update_margins()
        if text_edit is not None and hasattr(text_edit, "refresh_timestamp_layer"):
            text_edit.refresh_timestamp_layer()
    except Exception:
        pass

    try:
        if hasattr(editor, "_refresh_video_subtitle_context"):
            editor._refresh_video_subtitle_context()
        video_player = getattr(editor, "video_player", None)
        provider = getattr(editor, "_video_subtitle_context_for_player", None)
        if video_player is not None and callable(provider):
            if hasattr(video_player, "set_subtitle_provider"):
                video_player.set_subtitle_provider(provider)
            elif hasattr(video_player, "refresh_subtitle_context"):
                video_player.refresh_subtitle_context(provider())
            elif hasattr(video_player, "set_context_segments"):
                video_player.set_context_segments(provider())
        canvas = getattr(getattr(editor, "timeline", None), "canvas", None)
        playhead_sec = float(getattr(canvas, "playhead_sec", 0.0) or 0.0)
        if video_player is not None and hasattr(video_player, "set_subtitle_display_time"):
            local_sec = editor._global_to_local_sec(playhead_sec) if hasattr(editor, "_global_to_local_sec") else playhead_sec
            video_player.set_subtitle_display_time(local_sec)
    except Exception:
        pass


def schedule_opened_editor_runtime_refresh(
    editor,
    *,
    refresh_callback: Callable[[object], None] | None = None,
) -> None:
    callback = refresh_callback or refresh_opened_editor_runtime
    for delay_ms in (120, 320, 640, 1080):
        QTimer.singleShot(
            delay_ms,
            lambda e=editor, cb=callback: cb(e),
        )


def _apply_loaded_editor_segments(
    editor,
    segments: list[dict],
    *,
    auto_gap_segments_enabled: bool,
    boundary_times: list[float] | None = None,
    provisional_boundaries: list[dict] | list[float] | None = None,
    voice_activity_segments: list[dict] | None = None,
    stt_preview_segments: list[dict] | None = None,
    stt_preview_subtitle_drafts: bool | None = None,
    mark_dirty: bool = False,
) -> None:
    if hasattr(editor, "apply_loaded_canvas_state"):
        editor.apply_loaded_canvas_state(
            segments,
            auto_gap_segments_enabled=auto_gap_segments_enabled,
            boundary_times=boundary_times,
            provisional_boundaries=provisional_boundaries,
            voice_activity_segments=voice_activity_segments,
            stt_preview_segments=stt_preview_segments,
            stt_preview_subtitle_drafts=stt_preview_subtitle_drafts,
            mark_dirty=mark_dirty,
        )
        return
    if hasattr(editor, "_reload_segments_from_list"):
        try:
            editor._reload_segments_from_list(segments, mark_dirty=mark_dirty)
        except TypeError as exc:
            if "mark_dirty" not in str(exc):
                raise
            editor._reload_segments_from_list(segments)
        return
    editor.append_segments(segments)


def _clear_project_only_editor_state(owner, editor) -> None:
    """Drop project-only aux rows while preserving normal editor controls."""
    timeline = getattr(editor, "timeline", None)
    canvas = getattr(timeline, "canvas", None) if timeline is not None else None
    global_canvas = getattr(timeline, "global_canvas", None) if timeline is not None else None
    for obj in (owner, editor, timeline, canvas, global_canvas):
        if obj is None:
            continue
        for attr in (
            "_middle_segments",
            "middle_segments",
            "_roughcut_segments",
            "roughcut_segments",
            "_chapter_segments",
            "chapter_segments",
            "_roughcut_draft_segments",
            "_preliminary_middle_segments",
            "preliminary_middle_segments",
        ):
            try:
                setattr(obj, attr, [])
            except Exception:
                pass
        for attr in ("_roughcut_result", "roughcut_result", "_roughcut_draft_result"):
            try:
                setattr(obj, attr, None)
            except Exception:
                pass


def open_subtitle_segments_in_editor(
    owner,
    srt_path: str,
    media_path: str,
    segments: list[dict],
) -> bool:
    """Open a subtitle-only SRT through the same editor shell as project open."""
    target_media = str(media_path or srt_path or "").strip()
    if not target_media:
        return False

    owner._on_save_cb = None
    owner._on_start_cb = None
    owner._on_prev_cb = None
    owner._on_exit_cb = None
    owner._init_editor(target_media, is_batch=False)

    editor = getattr(owner, "_editor_widget", None)
    if editor is None:
        return False

    try:
        editor._source_srt_path = str(srt_path or "")
        editor._last_saved_srt_outputs = [(str(srt_path or ""), target_media)] if srt_path else []
        editor._project_clips = None
        editor._direct_srt_edit_mode = True
        editor._linked_project_path_for_srt = ""
    except Exception:
        pass

    timeline = getattr(editor, "timeline", None)
    if timeline is not None:
        try:
            reset_single = getattr(timeline, "_reset_single_media_context", None)
            if callable(reset_single):
                reset_single(clear_duration=True)
            else:
                canvas = getattr(timeline, "canvas", None)
                global_canvas = getattr(timeline, "global_canvas", None)
                if canvas is not None:
                    canvas.total_duration = 0.0
                    canvas._segments_content_duration = 0.0
                if global_canvas is not None:
                    global_canvas.total_duration = 0.0
        except Exception:
            pass
        if hasattr(timeline, "set_auto_gap_segments_enabled"):
            timeline.set_auto_gap_segments_enabled(True)

    try:
        editor._live_stt_preview_segments = []
    except Exception:
        pass
    _clear_project_only_editor_state(owner, editor)

    _apply_loaded_editor_segments(
        editor,
        segments,
        auto_gap_segments_enabled=True,
        boundary_times=list(getattr(owner, "_project_boundary_times", []) or []),
        provisional_boundaries=[],
        voice_activity_segments=[],
        stt_preview_segments=[],
        stt_preview_subtitle_drafts=False,
        mark_dirty=False,
    )
    if hasattr(editor, "_schedule_timeline"):
        editor._schedule_timeline()

    runtime_refresh = getattr(owner, "_refresh_opened_editor_runtime", None)
    if callable(runtime_refresh):
        runtime_refresh(editor)
    schedule_runtime_refresh = getattr(owner, "_schedule_opened_editor_runtime_refresh", None)
    if callable(schedule_runtime_refresh):
        schedule_runtime_refresh(editor)
    schedule_direct_srt_waveform_load(owner, editor, target_media, srt_path)
    schedule_direct_srt_media_finalize(owner, editor, target_media, srt_path)
    return True


def open_project_segments_in_editor(
    owner,
    filepath: str,
    project: dict,
    media: list[str],
    segments: list[dict],
    *,
    source_srt_path: str | None = None,
    direct_srt_edit_mode: bool = False,
) -> bool:
    if not media:
        return False

    from core.project.project_context import (
        project_cut_boundary_provisional_segments,
        project_stt_preview_segments,
        project_voice_activity_segments,
    )
    from core.project.project_format import project_primary_fps
    from core.project.project_roughcut_store import hydrate_project_roughcut_payload

    attach_project_session(
        owner,
        filepath,
        project,
        auto_pipeline=False,
        clear_multiclip=False,
        emit_boundary_signal=False,
    )
    apply_project_multiclip_runtime(owner, media, project)
    analysis = project.get("analysis", {}) if isinstance(project.get("analysis"), dict) else {}
    middle_segments = [
        dict(row)
        for row in list(
            analysis.get("middle_segments")
            or project.get("middle_segments")
            or []
        )
        if isinstance(row, dict)
    ]
    preliminary_middle_segments = [
        dict(row)
        for row in list(
            analysis.get("preliminary_middle_segments")
            or project.get("preliminary_middle_segments")
            or []
        )
        if isinstance(row, dict)
    ]
    roughcut_result = (
        analysis.get("roughcut_result")
        if isinstance(analysis.get("roughcut_result"), dict)
        else project.get("roughcut_result")
    )
    roughcut_result = dict(roughcut_result) if isinstance(roughcut_result, dict) else None
    owner._on_save_cb = None
    owner._on_start_cb = None
    owner._on_prev_cb = None
    owner._on_exit_cb = None
    owner._init_editor(media[0], is_batch=False)

    editor = getattr(owner, "_editor_widget", None)
    if editor is None:
        return False
    source_srt_path = str(source_srt_path or "").strip()
    try:
        if source_srt_path:
            try:
                editor._source_srt_path = source_srt_path
                editor._last_saved_srt_outputs = [(source_srt_path, media[0])]
                editor._linked_project_path_for_srt = filepath
            except Exception:
                pass
        if direct_srt_edit_mode:
            try:
                editor._direct_srt_edit_mode = True
            except Exception:
                pass
        primary_fps = float(project_primary_fps(project) or 30.0)
        hydrate_project_roughcut_payload(project, primary_fps=primary_fps)
        analysis = project.get("analysis", {}) if isinstance(project.get("analysis"), dict) else {}
        middle_segments = [
            dict(row)
            for row in list(
                analysis.get("middle_segments")
                or project.get("middle_segments")
                or []
            )
            if isinstance(row, dict)
        ]
        preliminary_middle_segments = [
            dict(row)
            for row in list(
                analysis.get("preliminary_middle_segments")
                or project.get("preliminary_middle_segments")
                or []
            )
            if isinstance(row, dict)
        ]
        roughcut_result = (
            analysis.get("roughcut_result")
            if isinstance(analysis.get("roughcut_result"), dict)
            else project.get("roughcut_result")
        )
        roughcut_result = dict(roughcut_result) if isinstance(roughcut_result, dict) else None
        try:
            setattr(editor, "video_fps", primary_fps)
        except Exception:
            pass
        timeline = getattr(editor, "timeline", None)
        if timeline is not None:
            try:
                reset_single = getattr(timeline, "_reset_single_media_context", None)
                if callable(reset_single) and len(media) <= 1:
                    reset_single(clear_duration=True)
                else:
                    canvas = getattr(timeline, "canvas", None)
                    global_canvas = getattr(timeline, "global_canvas", None)
                    if canvas is not None:
                        canvas.total_duration = 0.0
                        canvas._segments_content_duration = 0.0
                    if global_canvas is not None:
                        global_canvas.total_duration = 0.0
            except Exception:
                pass
        try:
            setattr(editor, "_live_stt_preview_segments", [])
        except Exception:
            pass
        provisional_boundaries = project_cut_boundary_provisional_segments(project)
        voice_activity = project_voice_activity_segments(project)
        canvas = getattr(timeline, "canvas", None) if timeline is not None else None
        global_canvas = getattr(timeline, "global_canvas", None) if timeline is not None else None
        if timeline is not None and hasattr(timeline, "set_auto_gap_segments_enabled"):
            timeline.set_auto_gap_segments_enabled(True)

        _apply_loaded_editor_segments(
            editor,
            segments,
            auto_gap_segments_enabled=True,
            boundary_times=owner._project_boundary_times or [],
            provisional_boundaries=provisional_boundaries,
            voice_activity_segments=voice_activity,
            stt_preview_segments=[],
            stt_preview_subtitle_drafts=False,
            mark_dirty=False,
        )
        if direct_srt_edit_mode:
            try:
                from core.project.nle_project_state import (
                    assert_nle_editor_rows_consistent,
                    sync_project_nle_state_from_editor_rows,
                )
                from core.project.nle_snapshot import (
                    NLE_SNAPSHOT_READBACK_PARITY_KEY,
                    build_nle_snapshot_readback_parity_report_for_editor_rows,
                )

                direct_srt_rows = [dict(row) for row in list(segments or []) if isinstance(row, dict)]
                nle_state = sync_project_nle_state_from_editor_rows(
                    project,
                    direct_srt_rows,
                    project_path=filepath,
                    sync_source="direct_srt_open",
                )
                nle_state.metadata = {
                    **dict(nle_state.metadata or {}),
                    "direct_srt_precedence_contract": "srt_timing_text_wins",
                    "direct_srt_source_basename": os.path.basename(str(source_srt_path or "")),
                }
                assert_nle_editor_rows_consistent(
                    direct_srt_rows,
                    nle_state.editor_rows(),
                    primary_fps=primary_fps,
                )
                parity_report = build_nle_snapshot_readback_parity_report_for_editor_rows(
                    project,
                    direct_srt_rows,
                    project_path=filepath,
                    surface="direct_srt_open",
                )
                if parity_report.get("checked"):
                    project[NLE_SNAPSHOT_READBACK_PARITY_KEY] = parity_report
                else:
                    project.pop(NLE_SNAPSHOT_READBACK_PARITY_KEY, None)
            except Exception as sync_exc:
                get_logger().log(f"⚠️ direct SRT NLE runtime sync skipped: {sync_exc}")
        for obj in (owner, editor, timeline, canvas, global_canvas):
            if obj is None:
                continue
            for attr in (
                "_middle_segments",
                "middle_segments",
                "_roughcut_segments",
                "roughcut_segments",
                "_chapter_segments",
                "chapter_segments",
                "_roughcut_draft_segments",
            ):
                try:
                    setattr(obj, attr, list(middle_segments))
                except Exception:
                    pass
            for attr in ("_preliminary_middle_segments", "preliminary_middle_segments"):
                try:
                    setattr(obj, attr, list(preliminary_middle_segments))
                except Exception:
                    pass
            for attr in ("_roughcut_result", "roughcut_result", "_roughcut_draft_result"):
                try:
                    setattr(obj, attr, dict(roughcut_result) if isinstance(roughcut_result, dict) else None)
                except Exception:
                    pass
        if len(media) > 1 and hasattr(editor, "_apply_multiclip_state_from_owner"):
            editor._apply_multiclip_state_from_owner()
        if hasattr(editor, "_schedule_timeline"):
            editor._schedule_timeline()
        runtime_refresh = getattr(owner, "_refresh_opened_editor_runtime", None)
        if callable(runtime_refresh):
            runtime_refresh(editor)

        def _restore_deferred_state() -> None:
            try:
                stt_preview = project_stt_preview_segments(project)
                if hasattr(editor, "apply_canvas_aux_state"):
                    editor.apply_canvas_aux_state(
                        stt_preview_segments=stt_preview,
                        stt_preview_subtitle_drafts=False,
                        schedule_timeline=bool(stt_preview),
                    )
                runtime_refresh = getattr(owner, "_refresh_opened_editor_runtime", None)
                if callable(runtime_refresh):
                    runtime_refresh(editor)
                elif hasattr(editor, "_refresh_video_subtitle_context"):
                    editor._refresh_video_subtitle_context()
                QTimer.singleShot(
                    320,
                    lambda fp=filepath, pr=project, md=list(media or []): owner._resume_cut_boundary_prescan_for_open_project(fp, pr, md),
                )
            except Exception as inner_exc:
                get_logger().log(f"⚠️ 프로젝트 지연 상태 복원 실패: {inner_exc}")

        QTimer.singleShot(120, _restore_deferred_state)
        schedule_runtime_refresh = getattr(owner, "_schedule_opened_editor_runtime_refresh", None)
        if callable(schedule_runtime_refresh):
            schedule_runtime_refresh(editor)
        if direct_srt_edit_mode:
            schedule_direct_srt_waveform_load(owner, editor, media[0] if media else "", source_srt_path)
            schedule_direct_srt_media_finalize(owner, editor, media[0] if media else "", source_srt_path)
    except Exception as exc:
        get_logger().log(f"⚠️ 프로젝트 자막 복원 실패: {exc}")
    return True


__all__ = [
    "find_project_for_srt_open",
    "load_stitched_cut_boundaries_for_srt_open",
    "merge_srt_segments_with_project_metadata",
    "normalized_open_path",
    "schedule_native_editor_post_open_tasks",
    "schedule_native_open_editor_media",
    "normalized_segment_text",
    "open_project_segments_in_editor",
    "open_subtitle_segments_in_editor",
    "project_matches_opened_srt",
    "project_sidecar_candidates_for_srt",
    "refresh_opened_editor_runtime",
    "restore_project_context_for_srt_open",
    "schedule_direct_srt_media_finalize",
    "schedule_direct_srt_waveform_load",
    "schedule_editor_fit_to_view",
    "schedule_opened_editor_runtime_refresh",
    "segment_metadata_match_score",
    "stitched_cut_boundary_sidecar_candidates_for_srt",
]
