from __future__ import annotations

import os
import threading
import time
from typing import Any

from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QApplication

from core.automation.app_command_protocol import build_command_result, normalize_command_payload
from core.media_queue_order import media_entry_allowed, ordered_media_files
from core.mode_policy import normalize_mode
from core.project.project_runtime_capture import count_editor_project_aux_state
from core.runtime import config
from core.runtime.logger import get_logger
from core.settings import load_settings, save_settings
from core.settings_simplifier import apply_simple_operation_mode

_STATUS_SNAPSHOT_CACHE_TTL_SEC = 0.35
_STATUS_SNAPSHOT_CACHE_LOCK = threading.Lock()
_STATUS_SNAPSHOT_CACHE: dict[int, tuple[float, dict[str, Any]]] = {}
_STAGE_LOG_TOKENS = (
    "오디오 추출",
    "오토 오디오",
    "ClearVoice",
    "컷 경계",
    "러프컷",
    "자막 생성 중",
    "자막 생성 완료",
    "자막 LLM",
    "저장 준비 중",
    "STT",
    "stt",
    "Whisper",
    "whisper",
    "단어 타임태그",
)
_STAGE_LOG_TOKENS_LOWER = tuple(str(token).lower() for token in _STAGE_LOG_TOKENS)


def _noop(*_args: Any, **_kwargs: Any) -> None:
    return None


def _normalize_path(value: Any) -> str:
    path = os.path.abspath(str(value or "").strip()) if str(value or "").strip() else ""
    return path


def _existing_file(path: str) -> bool:
    return bool(path) and os.path.isfile(path)


def _existing_dir(path: str) -> bool:
    return bool(path) and os.path.isdir(path)


def _normalized_existing_media_paths(values: list[Any] | tuple[Any, ...] | None) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in list(values or []):
        path = _normalize_path(raw)
        if not _existing_file(path) or not media_entry_allowed(path) or path in seen:
            continue
        ordered.append(path)
        seen.add(path)
    return ordered


def _normalize_multiclip_reuse_policy(value: Any) -> str:
    text = str(value or "ask").strip().lower()
    aliases = {
        "": "ask",
        "ask": "ask",
        "prompt": "ask",
        "yes": "yes",
        "y": "yes",
        "true": "yes",
        "1": "yes",
        "reuse": "yes",
        "no": "no",
        "n": "no",
        "false": "no",
        "0": "no",
        "fresh": "no",
    }
    return aliases.get(text, "")


def _resolve_multiclip_files(command_payload: dict[str, Any]) -> tuple[list[str], str]:
    folder = _normalize_path(command_payload.get("folder"))
    path = _normalize_path(command_payload.get("path"))
    files = _normalized_existing_media_paths(command_payload.get("paths", []))
    if not folder and path and _existing_dir(path):
        folder = path
    if folder and not _existing_dir(folder):
        return [], ""
    if folder and not files:
        files = ordered_media_files(folder)
    if not folder and len(files) > 1:
        parents = {os.path.dirname(path) for path in files}
        if len(parents) == 1:
            folder = parents.pop()
    return files, folder


def _multiclip_existing_srt_candidates(files: list[str]) -> list[str]:
    candidates: list[str] = []
    for path in list(files or []):
        base, _ext = os.path.splitext(path)
        srt_path = f"{base}.srt"
        if os.path.isfile(srt_path):
            candidates.append(path)
    return candidates


def _apply_automation_mode_override(owner: Any, mode: str) -> dict[str, Any]:
    settings = apply_simple_operation_mode(load_settings(), normalize_mode(mode))
    saver = getattr(owner, "_apply_ai_settings", None)
    if callable(saver):
        saver(settings)
    else:
        save_settings(settings)
    try:
        owner.settings = dict(settings)
    except Exception:
        pass
    editor = getattr(owner, "_editor_widget", None)
    if editor is not None:
        try:
            editor.settings = dict(settings)
        except Exception:
            pass
    return settings


def _wait_for_editor(owner: Any, media_path: str, *, timeout_sec: float = 5.0):
    target = _normalize_path(media_path)
    app = QApplication.instance()
    deadline = time.monotonic() + max(0.1, float(timeout_sec or 5.0))
    while time.monotonic() < deadline:
        if app is not None:
            _bridge_best_effort("automation process events", app.processEvents, default=None)
        editor = getattr(owner, "_editor_widget", None)
        current_path = _normalize_path(getattr(editor, "media_path", "") or "") if editor is not None else ""
        if editor is not None and (not target or current_path == target):
            return editor
        time.sleep(0.03)
    return None


def _auto_start_editor(editor: Any) -> bool:
    starter = getattr(editor, "_on_start_clicked", None)
    if not callable(starter):
        return False
    starter()
    return True


def _is_deleted_qt_runtime_error(exc: BaseException) -> bool:
    text = str(exc or "")
    return "wrapped C/C++ object" in text and "has been deleted" in text


def _log_bridge_nonfatal(step: str, exc: BaseException) -> None:
    if _is_deleted_qt_runtime_error(exc):
        return
    get_logger().log(
        f"⚠️ 앱 자동화 실패 [{step}]: {exc}",
        level="WARN",
        stage="automation",
    )


def _bridge_best_effort(step: str, callback, *, default=None):
    try:
        return callback()
    except RuntimeError as exc:
        if _is_deleted_qt_runtime_error(exc):
            return default
        _log_bridge_nonfatal(step, exc)
        return default
    except Exception as exc:
        _log_bridge_nonfatal(step, exc)
        return default


def _snapshot_output_path(command_payload: dict[str, Any]) -> str:
    filename = f"snapshot_{os.getpid()}_{threading.get_ident()}_{int(time.time() * 1000)}.png"
    raw_path = _normalize_path(command_payload.get("path"))
    if raw_path:
        if os.path.isdir(raw_path):
            return os.path.join(raw_path, filename)
        root, ext = os.path.splitext(raw_path)
        return raw_path if ext.lower() == ".png" else f"{root}.png"
    output_dir = os.path.join(str(config.OUTPUT_DIR or ""), "app_snapshots")
    os.makedirs(output_dir, exist_ok=True)
    return os.path.join(output_dir, filename)


def _capture_window_snapshot(owner: Any, command_payload: dict[str, Any]) -> dict[str, Any]:
    path = _snapshot_output_path(command_payload)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _bring_to_front(owner)
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    pixmap = owner.grab()
    if pixmap is None or getattr(pixmap, "isNull", lambda: True)():
        return {"ok": False, "error": "snapshot_unavailable", "message": path}
    if not bool(pixmap.save(path, "PNG")):
        return {"ok": False, "error": "snapshot_save_failed", "message": path}
    return {
        "ok": True,
        "data": {
            "path": path,
            "width": int(getattr(pixmap, "width", lambda: 0)() or 0),
            "height": int(getattr(pixmap, "height", lambda: 0)() or 0),
            "bytes": int(os.path.getsize(path)) if os.path.isfile(path) else 0,
        },
    }


def _queue_window_snapshot(owner: Any, command_payload: dict[str, Any]) -> dict[str, Any]:
    path = _snapshot_output_path(command_payload)
    queue_capture = getattr(owner, "_automation_request_async_snapshot_capture", None)
    if not callable(queue_capture):
        return {"ok": False, "error": "snapshot_queue_unavailable", "message": path}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    queued = dict(queue_capture(path) or {})
    return {
        "ok": True,
        "queued": True,
        "data": {
            "path": path,
            "requested_at": float(queued.get("requested_at", 0.0) or 0.0),
        },
    }


def _bring_to_front(owner: Any) -> None:
    if owner is None:
        return
    minimized = bool(
        _bridge_best_effort(
            "window minimized state",
            lambda: getattr(owner, "isMinimized", lambda: False)(),
            default=False,
        )
    )
    if minimized:
        _bridge_best_effort(
            "window showNormal",
            lambda: getattr(owner, "showNormal", lambda: None)(),
            default=None,
        )
    else:
        _bridge_best_effort(
            "window show",
            lambda: getattr(owner, "show", lambda: None)(),
            default=None,
        )
    _bridge_best_effort("window raise", lambda: getattr(owner, "raise_", lambda: None)(), default=None)
    _bridge_best_effort(
        "window activate",
        lambda: getattr(owner, "activateWindow", lambda: None)(),
        default=None,
    )


def _recent_logs_snapshot(limit: int = 40) -> list[str]:
    logger = get_logger()
    getter = getattr(logger, "recent_lines", None)
    if not callable(getter):
        return []
    return _bridge_best_effort(
        "recent log snapshot",
        lambda: [str(line or "") for line in list(getter(limit)) if str(line or "")],
        default=[],
    )


def _is_stage_log_line(line: str) -> bool:
    text = str(line or "").strip()
    if not text:
        return False
    lowered = text.lower()
    return any(token in lowered for token in _STAGE_LOG_TOKENS_LOWER)


def _recent_stage_logs_snapshot(limit: int = 20) -> list[str]:
    matched = [line for line in _recent_logs_snapshot(160) if _is_stage_log_line(line)]
    size = max(1, int(limit or 20))
    return matched[-size:]


def _recent_log_payload(
    *,
    recent_limit: int = 40,
    stage_scan_limit: int = 160,
    stage_limit: int = 20,
) -> tuple[list[str], list[str]]:
    logger = get_logger()
    getter = getattr(logger, "recent_lines_and_filtered", None)
    if callable(getter):
        def _snapshot() -> tuple[list[str], list[str]]:
            recent, stage = getter(
                recent_limit=recent_limit,
                filtered_scan_limit=stage_scan_limit,
                filtered_limit=stage_limit,
                predicate=_is_stage_log_line,
            )
            return (
                [str(line or "") for line in recent if str(line or "")],
                [str(line or "") for line in stage if str(line or "")],
            )

        return _bridge_best_effort(
            "recent log payload snapshot",
            _snapshot,
            default=([], []),
        )
    scan_size = max(1, max(int(recent_limit or 40), int(stage_scan_limit or 160)))
    lines = _recent_logs_snapshot(scan_size)
    recent_size = max(1, int(recent_limit or 40))
    stage_size = max(1, int(stage_limit or 20))
    matched = [line for line in lines if _is_stage_log_line(line)]
    return lines[-recent_size:], matched[-stage_size:]


def _runtime_resource_snapshot(owner: Any) -> dict[str, Any]:
    snapshot = getattr(owner, "_runtime_resource_snapshot", None)
    return dict(snapshot or {}) if isinstance(snapshot, dict) else {}


def _queue_runtime_snapshot(owner: Any) -> dict[str, Any]:
    completion_fn = getattr(owner, "queue_completion_state", None)
    probe_fn = getattr(owner, "queue_status_probe_parts", None)
    row_snapshot_fn = getattr(owner, "queue_row_snapshot", None)
    payload: dict[str, Any] = {}
    if callable(completion_fn):
        completion_payload = _bridge_best_effort(
            "queue completion snapshot",
            lambda: dict(completion_fn() or {}),
            default={},
        )
        payload.update(completion_payload)
    if callable(probe_fn):
        parts = _bridge_best_effort(
            "queue probe snapshot",
            lambda: [str(part or "") for part in list(probe_fn()) if str(part or "")],
            default=[],
        )
        if parts:
            payload["active_probe_parts"] = parts
            payload["active_probe_text"] = " | ".join(parts)
    rows = []
    row_count = int(payload.get("row_count", 0) or 0)
    if callable(row_snapshot_fn) and row_count > 0:
        for row in range(min(row_count, 3)):
            snap = _bridge_best_effort(
                f"queue row snapshot #{row}",
                lambda row=row: dict(row_snapshot_fn(row) or {}),
                default={},
            )
            if snap:
                rows.append(
                    {
                        "row": int(snap.get("row", row) or row),
                        "status": str(snap.get("status", "") or ""),
                        "file": str(snap.get("file", "") or ""),
                        "info": str(snap.get("info", "") or ""),
                        "eta": str(snap.get("eta", "") or ""),
                    }
                )
    payload["rows"] = rows
    return payload


def _editor_runtime_snapshot(editor: Any) -> dict[str, Any]:
    if editor is None:
        return {}
    snapshotter = getattr(editor, "automation_editor_state_snapshot", None)
    if not callable(snapshotter):
        return {}
    return _bridge_best_effort(
        "editor automation state snapshot",
        lambda: dict(snapshotter() or {}),
        default={},
    )


def _editor_aux_counts(editor: Any) -> dict[str, int]:
    empty = {
        "stt_preview_segment_count": 0,
        "voice_activity_segment_count": 0,
        "provisional_cut_boundary_count": 0,
    }
    if editor is None:
        return empty
    return _bridge_best_effort(
        "editor auxiliary count snapshot",
        lambda: dict(count_editor_project_aux_state(editor) or {}),
        default=empty,
    )


def _command_option_bool(options: dict[str, Any], key: str, default: bool = False) -> bool:
    value = options.get(key, default)
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _command_option_float(options: dict[str, Any], key: str) -> float | None:
    try:
        if options.get(key) in (None, ""):
            return None
        return float(options.get(key))
    except Exception:
        return None


def _command_option_int(options: dict[str, Any], key: str) -> int | None:
    try:
        if options.get(key) in (None, ""):
            return None
        return int(options.get(key))
    except Exception:
        return None


def _select_editor_segment_from_options(editor: Any, options: dict[str, Any]) -> dict[str, Any] | None:
    selector = getattr(editor, "automation_select_segment", None)
    if not callable(selector):
        return None
    line = _command_option_int(options, "line")
    start_sec = _command_option_float(options, "start_sec")
    at_playhead = _command_option_bool(options, "at_playhead", default=False)
    if line is None and start_sec is None and not at_playhead:
        return None
    return selector(
        line=line,
        start_sec=start_sec,
        at_playhead=at_playhead,
        center=_command_option_bool(options, "center", default=False),
        sync_playhead=_command_option_bool(options, "sync_playhead", default=False),
    )


def _status_snapshot(owner: Any) -> dict[str, Any]:
    editor = getattr(owner, "_editor_widget", None)
    state = _bridge_best_effort(
        "editor state snapshot",
        lambda: str(getattr(getattr(editor, "sm", None), "state", "") or ""),
        default="",
    )
    guided_state = {}
    guided_getter = getattr(owner, "_automation_guided_snapshot_state_payload", None)
    if callable(guided_getter):
        guided_state = _bridge_best_effort(
            "guided snapshot state",
            lambda: dict(guided_getter() or {}),
            default={},
        )
    recent_logs, recent_stage_logs = _recent_log_payload()
    return {
        "editor_open": bool(editor is not None),
        "editor_media_path": str(getattr(editor, "media_path", "") or "") if editor is not None else "",
        "editor_state": state,
        "current_project_path": str(getattr(owner, "_current_project_path", "") or ""),
        "current_work_mode": str(getattr(owner, "_current_work_mode", "") or ""),
        "backend_active": bool(getattr(getattr(owner, "backend", None), "_active", False)),
        "auto_processing_active": bool(getattr(owner, "_auto_processing_active", False)),
        "editor_runtime": _editor_runtime_snapshot(editor),
        "editor_aux_counts": _editor_aux_counts(editor),
        "guided_snapshot_run": guided_state,
        "queue_runtime": _queue_runtime_snapshot(owner),
        "runtime_resource": _runtime_resource_snapshot(owner),
        "recent_logs": recent_logs,
        "recent_stage_logs": recent_stage_logs,
    }


def _cached_status_snapshot(owner: Any) -> dict[str, Any]:
    now = time.monotonic()
    owner_key = id(owner)
    with _STATUS_SNAPSHOT_CACHE_LOCK:
        cached = _STATUS_SNAPSHOT_CACHE.get(owner_key)
        if cached is not None and (now - cached[0]) <= _STATUS_SNAPSHOT_CACHE_TTL_SEC:
            return dict(cached[1])
    snapshot = _status_snapshot(owner)
    with _STATUS_SNAPSHOT_CACHE_LOCK:
        _STATUS_SNAPSHOT_CACHE[owner_key] = (now, dict(snapshot))
    return snapshot


def _clear_status_snapshot_cache(owner: Any | None = None) -> None:
    with _STATUS_SNAPSHOT_CACHE_LOCK:
        if owner is None:
            _STATUS_SNAPSHOT_CACHE.clear()
        else:
            _STATUS_SNAPSHOT_CACHE.pop(id(owner), None)


def _editor_pipeline_start_callback(owner: Any, media_path: str, *, is_auto_start: bool = False):
    normalized_path = _normalize_path(media_path)

    def _start(*_args, **_kwargs):
        backend = getattr(owner, "backend", None)
        starter = getattr(backend, "start_pipeline", None) if backend is not None else None
        if not callable(starter) or not normalized_path:
            return None
        return starter([normalized_path], is_auto_start=bool(is_auto_start))

    return _start


def execute_app_command(owner: Any, payload: dict[str, Any] | None) -> dict[str, Any]:
    command_payload = normalize_command_payload(payload)
    command = command_payload.get("command", "")
    logger = get_logger()

    def ok(*, message: str = "", data: dict[str, Any] | None = None, queued: bool = False) -> dict[str, Any]:
        return build_command_result(command, ok=True, accepted=True, queued=queued, message=message, data=data)

    def fail(error: str, *, message: str = "") -> dict[str, Any]:
        return build_command_result(command, ok=False, accepted=False, error=error, message=message)

    if command == "ping":
        return ok(message="pong", data=_cached_status_snapshot(owner))

    if command == "status":
        return ok(data=_cached_status_snapshot(owner))

    if command == "guided-subtitle-status":
        return ok(data=_cached_status_snapshot(owner))

    _clear_status_snapshot_cache(owner)

    if command == "editor-set-playhead":
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        options = dict(command_payload.get("options") or {})
        sec = _command_option_float(options, "sec")
        if sec is None:
            return fail("invalid_playhead_sec")
        setter = getattr(editor, "automation_set_playhead", None)
        if not callable(setter):
            return fail("editor_automation_unavailable")
        try:
            data = dict(
                setter(
                    sec,
                    center=_command_option_bool(options, "center", default=False),
                    sync_video=_command_option_bool(options, "sync_video", default=True),
                )
                or {}
            )
        except ValueError as exc:
            return fail(str(exc))
        _bring_to_front(owner)
        return ok(message="editor_playhead_set", data=data)

    if command == "editor-pin-shadow-playhead":
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        pinner = getattr(editor, "automation_pin_shadow_playhead", None)
        if not callable(pinner):
            return fail("editor_automation_unavailable")
        options = dict(command_payload.get("options") or {})
        try:
            data = dict(pinner(sec=_command_option_float(options, "sec")) or {})
        except ValueError as exc:
            return fail(str(exc))
        _bring_to_front(owner)
        return ok(message="editor_shadow_playhead_pinned", data=data)

    if command == "editor-clear-shadow-playhead":
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        clearer = getattr(editor, "automation_clear_shadow_playhead", None)
        if not callable(clearer):
            return fail("editor_automation_unavailable")
        try:
            data = dict(clearer() or {})
        except ValueError as exc:
            return fail(str(exc))
        _bring_to_front(owner)
        return ok(message="editor_shadow_playhead_cleared", data=data)

    if command == "editor-zoom-max":
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        zoomer = getattr(editor, "automation_zoom_max", None)
        if not callable(zoomer):
            return fail("editor_automation_unavailable")
        try:
            data = dict(zoomer() or {})
        except ValueError as exc:
            return fail(str(exc))
        _bring_to_front(owner)
        return ok(message="editor_zoom_max_applied", data=data)

    if command == "editor-playback":
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        player = getattr(editor, "automation_set_playback_state", None)
        if not callable(player):
            return fail("editor_automation_unavailable")
        options = dict(command_payload.get("options") or {})
        action = str(options.get("action", "toggle") or "toggle")
        try:
            data = dict(player(action) or {})
        except ValueError as exc:
            return fail(str(exc))
        _bring_to_front(owner)
        return ok(message=f"editor_playback_{action}", data=data)

    if command == "editor-select-segment":
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        selector = getattr(editor, "automation_select_segment", None)
        if not callable(selector):
            return fail("editor_automation_unavailable")
        options = dict(command_payload.get("options") or {})
        try:
            data = dict(
                selector(
                    line=_command_option_int(options, "line"),
                    start_sec=_command_option_float(options, "start_sec"),
                    at_playhead=_command_option_bool(options, "at_playhead", default=False),
                    center=_command_option_bool(options, "center", default=False),
                    sync_playhead=_command_option_bool(options, "sync_playhead", default=False),
                )
                or {}
            )
        except ValueError as exc:
            return fail(str(exc))
        _bring_to_front(owner)
        return ok(message="editor_segment_selected", data=data)

    if command == "editor-begin-smart-split":
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        starter = getattr(editor, "automation_begin_smart_split_at_playhead", None)
        if not callable(starter):
            return fail("editor_automation_unavailable")
        options = dict(command_payload.get("options") or {})
        try:
            data = dict(
                starter(
                    line=_command_option_int(options, "line"),
                    start_sec=_command_option_float(options, "start_sec"),
                    at_playhead=_command_option_bool(options, "at_playhead", default=False),
                )
                or {}
            )
        except ValueError as exc:
            return fail(str(exc))
        _bring_to_front(owner)
        return ok(message="editor_smart_split_mode_started", data=data)

    if command == "editor-set-inline-cursor":
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        mover = getattr(editor, "automation_set_inline_edit_cursor", None)
        if not callable(mover):
            return fail("editor_automation_unavailable")
        options = dict(command_payload.get("options") or {})
        position = _command_option_int(options, "position")
        if position is None:
            return fail("invalid_inline_cursor_position")
        try:
            data = dict(mover(position) or {})
        except ValueError as exc:
            return fail(str(exc))
        _bring_to_front(owner)
        return ok(message="editor_inline_cursor_set", data=data)

    if command == "editor-commit-inline-edit":
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        committer = getattr(editor, "automation_commit_inline_edit", None)
        if not callable(committer):
            return fail("editor_automation_unavailable")
        try:
            data = dict(committer() or {})
        except ValueError as exc:
            return fail(str(exc))
        _bring_to_front(owner)
        return ok(message="editor_inline_edit_committed", data=data)

    if command == "editor-smart-split":
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        splitter = getattr(editor, "automation_smart_split_at_playhead", None)
        if not callable(splitter):
            return fail("editor_automation_unavailable")
        options = dict(command_payload.get("options") or {})
        try:
            selected = _select_editor_segment_from_options(editor, options)
            data = dict(splitter() or {})
            if selected:
                data.setdefault("selected", dict(selected))
        except ValueError as exc:
            return fail(str(exc))
        _bring_to_front(owner)
        return ok(message="editor_smart_split_done", data=data)

    if command in {"editor-move-segment-left", "editor-move-segment-right"}:
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        mover = getattr(editor, "automation_move_segment_boundary_to_playhead", None)
        if not callable(mover):
            return fail("editor_automation_unavailable")
        options = dict(command_payload.get("options") or {})
        edge = "left" if command.endswith("left") else "right"
        try:
            selected = _select_editor_segment_from_options(editor, options)
            data = dict(mover(edge) or {})
            if selected:
                data.setdefault("selected", dict(selected))
        except ValueError as exc:
            return fail(str(exc))
        _bring_to_front(owner)
        return ok(message=f"editor_segment_{edge}_moved", data=data)

    if command == "editor-move-diamond":
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        mover = getattr(editor, "automation_move_diamond_to_playhead", None)
        if not callable(mover):
            return fail("editor_automation_unavailable")
        options = dict(command_payload.get("options") or {})
        try:
            selected = _select_editor_segment_from_options(editor, options)
            data = dict(mover(side=str(options.get("side", "closest") or "closest")) or {})
            if selected:
                data.setdefault("selected", dict(selected))
        except ValueError as exc:
            return fail(str(exc))
        _bring_to_front(owner)
        return ok(message="editor_diamond_moved", data=data)

    if command == "editor-merge-diamond":
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        merger = getattr(editor, "automation_merge_diamond", None)
        if not callable(merger):
            return fail("editor_automation_unavailable")
        options = dict(command_payload.get("options") or {})
        try:
            selected = _select_editor_segment_from_options(editor, options)
            data = dict(merger(side=str(options.get("side", "closest") or "closest")) or {})
            if selected:
                data.setdefault("selected", dict(selected))
        except ValueError as exc:
            return fail(str(exc))
        _bring_to_front(owner)
        return ok(message="editor_diamond_merged", data=data)

    if command in {"capture-snapshot", "snapshot"}:
        logger.log("🤖 자동화 명령 수신: capture-snapshot")
        async_requested = bool(command_payload.get("options", {}).get("async", True))
        has_async_capture = callable(getattr(owner, "_automation_request_async_snapshot_capture", None))
        snapshot_result = (
            _queue_window_snapshot(owner, command_payload)
            if async_requested and has_async_capture
            else _capture_window_snapshot(owner, command_payload)
        )
        if not snapshot_result.get("ok"):
            return fail(str(snapshot_result.get("error", "snapshot_failed")), message=str(snapshot_result.get("message", "")))
        return ok(
            message="snapshot_queued" if snapshot_result.get("queued") else "snapshot_captured",
            data=snapshot_result.get("data"),
            queued=bool(snapshot_result.get("queued", False)),
        )

    if command == "show-home":
        logger.log("🤖 자동화 명령 수신: show-home")
        owner.show_home()
        _bring_to_front(owner)
        return ok(message="home_visible")

    if command == "open-project":
        path = _normalize_path(command_payload.get("path"))
        if not _existing_file(path):
            return fail("project_not_found", message=path)
        opener = getattr(owner, "_open_project_file", None)
        if not callable(opener):
            return fail("project_open_unavailable")
        logger.log(f"🤖 자동화 명령 수신: open-project {os.path.basename(path)}")
        if not bool(opener(path)):
            return fail("project_open_failed", message=path)
        _bring_to_front(owner)
        return ok(message="project_opened", data={"path": path})

    if command == "open-srt":
        path = _normalize_path(command_payload.get("path"))
        if not _existing_file(path):
            return fail("srt_not_found", message=path)
        logger.log(f"🤖 자동화 명령 수신: open-srt {os.path.basename(path)}")
        owner._open_srt_in_editor(path)
        _bring_to_front(owner)
        return ok(message="srt_opened", data={"path": path})

    if command == "open-media":
        path = _normalize_path(command_payload.get("path"))
        if not _existing_file(path):
            return fail("media_not_found", message=path)
        backend = getattr(owner, "backend", None)
        starter = getattr(backend, "start_pipeline", None) if backend is not None else None
        if not callable(starter):
            return fail("pipeline_start_unavailable")
        logger.log(f"🤖 자동화 명령 수신: open-media {os.path.basename(path)}")
        opened = owner.open_editor_for_file_and_wait(
            path,
            _noop,
            _editor_pipeline_start_callback(owner, path, is_auto_start=True),
            _noop,
            _noop,
            False,
        )
        if not opened:
            return fail("media_open_failed", message=path)
        _bring_to_front(owner)
        return ok(message="media_opened", data={"path": path})

    if command == "start-multiclip":
        backend = getattr(owner, "backend", None)
        starter = getattr(backend, "start_multiclip_pipeline", None) if backend is not None else None
        if not callable(starter):
            return fail("multiclip_start_unavailable")
        editor = getattr(owner, "_editor_widget", None)
        state = str(getattr(getattr(editor, "sm", None), "state", "") or "") if editor is not None else ""
        if state == "ST_PROC" or bool(getattr(backend, "_active", False)):
            return fail("already_processing")
        files, folder = _resolve_multiclip_files(command_payload)
        if command_payload.get("folder") or (
            command_payload.get("path") and not command_payload.get("paths")
        ):
            requested_folder = _normalize_path(command_payload.get("folder") or command_payload.get("path"))
            if requested_folder and not _existing_dir(requested_folder):
                return fail("queue_folder_missing", message=requested_folder)
        if not files:
            return fail("multiclip_files_missing")
        if len(files) < 2:
            return fail("multiclip_requires_multiple_files", message=str(files[0]))

        options = dict(command_payload.get("options") or {})
        reuse_policy = _normalize_multiclip_reuse_policy(options.get("reuse_existing"))
        if not reuse_policy:
            return fail("invalid_reuse_existing_option", message=str(options.get("reuse_existing", "")))
        existing_candidates = _multiclip_existing_srt_candidates(files)
        if existing_candidates and reuse_policy == "ask":
            names = ", ".join(os.path.basename(path) for path in existing_candidates[:3])
            return fail("existing_subtitles_confirmation_required", message=names)

        mode_value = str(options.get("mode") or "").strip()
        applied_settings = None
        if mode_value:
            try:
                applied_settings = _apply_automation_mode_override(owner, mode_value)
            except Exception as exc:
                return fail("mode_apply_failed", message=str(exc))

        if reuse_policy == "yes":
            setattr(backend, "_force_reuse_existing_multiclip_subtitles_once", True)
            setattr(backend, "_force_no_reuse_once", False)
        elif reuse_policy == "no":
            setattr(backend, "_force_reuse_existing_multiclip_subtitles_once", False)
            setattr(backend, "_force_no_reuse_once", True)
        else:
            setattr(backend, "_force_reuse_existing_multiclip_subtitles_once", False)
            setattr(backend, "_force_no_reuse_once", False)

        try:
            from ui.project.project_session_runtime import set_runtime_multiclip_state

            set_runtime_multiclip_state(
                owner,
                list(files),
                [],
                project_boundary_rows=None,
                emit_boundary_signal=False,
            )
        except Exception as exc:
            return fail("multiclip_runtime_prepare_failed", message=str(exc))

        logger.log(
            f"🤖 자동화 명령 수신: start-multiclip {len(files)}개"
            + (f" / {normalize_mode(mode_value)}" if mode_value else "")
            + f" / reuse={reuse_policy}"
        )
        starter(list(files), folder=folder or None)
        editor = _wait_for_editor(owner, files[0], timeout_sec=5.0)
        if editor is None:
            return fail("multiclip_editor_timeout", message=os.path.basename(files[0]))
        if not _auto_start_editor(editor):
            return fail("pipeline_start_unavailable")
        _bring_to_front(owner)
        data = {
            "count": len(files),
            "files": list(files),
            "folder": folder,
            "reuse_existing": reuse_policy,
            "existing_subtitle_candidates": [os.path.basename(path) for path in existing_candidates],
        }
        if applied_settings:
            data["mode"] = str(applied_settings.get("simple_operation_mode", "") or "")
            data["stt_quality_preset"] = str(applied_settings.get("stt_quality_preset", "") or "")
        return ok(message="multiclip_started", data=data)

    if command == "guided-subtitle-run":
        path = _normalize_path(command_payload.get("path"))
        if not _existing_file(path):
            return fail("media_not_found", message=path)
        backend = getattr(owner, "backend", None)
        pipeline_starter = getattr(backend, "start_pipeline", None) if backend is not None else None
        if not callable(pipeline_starter):
            return fail("pipeline_start_unavailable")
        editor = getattr(owner, "_editor_widget", None)
        state = str(getattr(getattr(editor, "sm", None), "state", "") or "") if editor is not None else ""
        if state == "ST_PROC":
            return fail("already_processing")
        logger.log(f"🤖 자동화 명령 수신: guided-subtitle-run {os.path.basename(path)}")
        opened = owner.open_editor_for_file_and_wait(
            path,
            _noop,
            _editor_pipeline_start_callback(owner, path, is_auto_start=True),
            _noop,
            _noop,
            False,
        )
        if not opened:
            return fail("media_open_failed", message=path)
        begin_run = getattr(owner, "_automation_begin_guided_subtitle_run", None)
        capture_run = getattr(owner, "_automation_capture_guided_snapshot", None)
        snapshot_dir = ""
        snapshots: list[dict[str, Any]] = []
        if callable(begin_run):
            state_payload = begin_run(path, snapshot_dir=str(command_payload.get("options", {}).get("snapshot_dir", "") or ""))
            snapshot_dir = str((state_payload or {}).get("snapshot_dir", "") or "")
        if callable(capture_run):
            opened_snapshot = capture_run("opened", stage_text="opened", force=True)
            if isinstance(opened_snapshot, dict) and opened_snapshot:
                snapshots.append(dict(opened_snapshot))
        editor = getattr(owner, "_editor_widget", None)
        starter = getattr(editor, "_on_start_clicked", None) if editor is not None else None
        if not callable(starter):
            return fail("pipeline_start_unavailable")
        starter()
        if callable(capture_run):
            started_snapshot = capture_run("pipeline-started", stage_text="pipeline_started", force=True)
            if isinstance(started_snapshot, dict) and started_snapshot:
                snapshots.append(dict(started_snapshot))
        _bring_to_front(owner)
        return ok(
            message="guided_subtitle_started",
            data={
                "path": path,
                "snapshot_dir": snapshot_dir,
                "snapshots": snapshots,
                "status": _status_snapshot(owner),
            },
        )

    if command == "queue-files":
        files = [_normalize_path(path) for path in command_payload.get("paths", [])]
        files = [path for path in files if _existing_file(path)]
        if not files:
            return fail("queue_files_missing")
        folder = os.path.dirname(files[0])
        logger.log(f"🤖 자동화 명령 수신: queue-files {len(files)}개")
        owner._start_queue_mode(files, folder=folder, source="automation")
        _bring_to_front(owner)
        return ok(message="queue_started", data={"count": len(files), "folder": folder})

    if command == "queue-folder":
        folder = _normalize_path(command_payload.get("folder") or command_payload.get("path"))
        if not folder or not os.path.isdir(folder):
            return fail("queue_folder_missing", message=folder)
        files = ordered_media_files(folder)
        if not files:
            return fail("queue_folder_empty", message=folder)
        logger.log(f"🤖 자동화 명령 수신: queue-folder {os.path.basename(folder)} / {len(files)}개")
        owner._start_queue_mode(files, folder=folder, source="automation")
        _bring_to_front(owner)
        return ok(message="queue_started", data={"count": len(files), "folder": folder})

    if command == "save-project":
        logger.log("🤖 자동화 명령 수신: save-project")
        project_path = str(getattr(owner, "_current_project_path", "") or "")
        if project_path:
            saver = getattr(owner, "_save_current_project", None)
            if not callable(saver):
                return fail("project_save_unavailable")
            saver()
            return ok(message="project_saved", data={"path": project_path})
        editor = getattr(owner, "_editor_widget", None)
        save_handler = getattr(editor, "_on_save", None) if editor is not None else None
        if not callable(save_handler):
            return fail("nothing_to_save")
        try:
            saved = bool(save_handler(skip_auto_next=True))
        except TypeError:
            saved = bool(save_handler())
        if not saved:
            return fail("save_declined")
        return ok(message="editor_saved")

    if command == "start-current-pipeline":
        logger.log("🤖 자동화 명령 수신: start-current-pipeline")
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        state = str(getattr(getattr(editor, "sm", None), "state", "") or "")
        if state == "ST_PROC":
            return fail("already_processing")
        starter = getattr(editor, "_on_start_clicked", None)
        if not callable(starter):
            return fail("pipeline_start_unavailable")
        starter()
        _bring_to_front(owner)
        return ok(message="pipeline_started", data={"state_before": state})

    if command == "start-current-roughcut":
        logger.log("🤖 자동화 명령 수신: start-current-roughcut")
        editor = getattr(owner, "_editor_widget", None)
        if editor is None:
            return fail("editor_missing")
        state = str(getattr(getattr(editor, "sm", None), "state", "") or "")
        if state == "ST_PROC":
            return fail("already_processing")
        starter = getattr(editor, "_schedule_post_generation_roughcut_draft", None)
        if not callable(starter):
            return fail("roughcut_start_unavailable")
        starter(force=True)
        _bring_to_front(owner)
        return ok(
            message="roughcut_started",
            data={
                "state_before": state,
                "media_path": str(getattr(editor, "media_path", "") or ""),
            },
        )

    return fail("unknown_command", message=command)


def _signal_state_result(reply_state: Any) -> dict[str, Any] | None:
    if isinstance(reply_state, dict):
        result = reply_state.get("result")
        if isinstance(result, dict):
            return result
    return None


def handle_app_command_signal(owner: Any, payload: dict[str, Any], reply_state: Any = None) -> None:
    try:
        result = execute_app_command(owner, payload)
    except Exception as exc:
        _log_bridge_nonfatal(f"command dispatch {normalize_command_payload(payload).get('command', '')}", exc)
        result = build_command_result(
            normalize_command_payload(payload).get("command", ""),
            ok=False,
            accepted=False,
            error="execution_exception",
            message=str(exc),
        )
    if isinstance(reply_state, dict):
        reply_state["result"] = result
        event = reply_state.get("event")
        if hasattr(event, "set"):
            try:
                event.set()
            except Exception:
                pass


def dispatch_app_command(owner: Any, payload: dict[str, Any], *, timeout_sec: float = 12.0) -> dict[str, Any]:
    app = QApplication.instance()
    if app is not None and QThread.currentThread() == app.thread():
        return execute_app_command(owner, payload)
    state: dict[str, Any] = {"event": threading.Event()}
    owner._sig_external_app_command.emit(dict(payload or {}), state)
    timeout = max(0.1, float(timeout_sec or 12.0))
    if state["event"].wait(timeout):
        result = _signal_state_result(state)
        if result is not None:
            return result
    return build_command_result(
        normalize_command_payload(payload).get("command", ""),
        ok=False,
        accepted=False,
        error="command_timeout",
    )
