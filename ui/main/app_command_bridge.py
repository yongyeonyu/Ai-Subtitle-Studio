from __future__ import annotations

import os
import threading
import time
from types import SimpleNamespace
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
from ui.main.app_command_bridge_handlers import handle_command as _handle_bridge_command

_STATUS_SNAPSHOT_CACHE_TTL_SEC = 0.35
_STATUS_BUSY_STALE_REUSE_SEC = 2.5
_STATUS_SNAPSHOT_CACHE_LOCK = threading.Lock()
_STATUS_SNAPSHOT_CACHE: dict[int, tuple[float, dict[str, Any]]] = {}
_STATUS_COMMANDS = {"ping", "status", "guided-subtitle-status"}
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


def _file_result(path: str) -> dict[str, Any]:
    normalized = _normalize_path(path)
    exists = bool(normalized) and os.path.isfile(normalized)
    return {
        "path": normalized,
        "exists": exists,
        "bytes": int(os.path.getsize(normalized)) if exists else 0,
    }


def _saved_srt_outputs(editor: Any) -> list[tuple[str, str]]:
    outputs: list[tuple[str, str]] = []
    for raw in list(getattr(editor, "_last_saved_srt_outputs", []) or []):
        if not isinstance(raw, (list, tuple)) or not raw:
            continue
        srt_path = _normalize_path(raw[0])
        target_file = _normalize_path(raw[1] if len(raw) > 1 else raw[0])
        if not srt_path:
            continue
        outputs.append((srt_path, target_file or srt_path))
    if outputs:
        return outputs
    media_path = _normalize_path(getattr(editor, "media_path", "") or "")
    preferred_single = getattr(editor, "_preferred_single_srt_output_path", None)
    fallback_srt = ""
    if callable(preferred_single):
        try:
            fallback_srt = _normalize_path(preferred_single(media_path or None))
        except TypeError:
            fallback_srt = _normalize_path(preferred_single())
        except Exception:
            fallback_srt = ""
    if not fallback_srt and media_path:
        try:
            from core.path_manager import get_srt_path

            fallback_srt = _normalize_path(get_srt_path(media_path))
        except Exception:
            fallback_srt = ""
    if fallback_srt and os.path.isfile(fallback_srt):
        outputs.append((fallback_srt, media_path or fallback_srt))
    return outputs


def _subtitle_video_output_path(target_file: str) -> str:
    normalized = _normalize_path(target_file)
    if not normalized:
        return ""
    safe_name = os.path.basename(normalized)
    return os.path.join(
        os.path.dirname(normalized),
        f"{os.path.splitext(safe_name)[0]}_자막소스.mov",
    )


def _current_editor_srt_segments(editor: Any) -> list[dict[str, Any]]:
    getter = getattr(editor, "_get_current_segments", None)
    if not callable(getter):
        return []
    segs = list(getter() or [])
    formatter = getattr(editor, "_segments_for_srt_output", None)
    if callable(formatter):
        formatted = formatter(segs)
        return list(formatted or [])
    return segs


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


def _capture_widget_snapshot(widget: Any, command_payload: dict[str, Any]) -> dict[str, Any]:
    path = _snapshot_output_path(command_payload)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if widget is None:
        return {"ok": False, "error": "snapshot_unavailable", "message": path}
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    pixmap = widget.grab()
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


def _set_active_automation_dialog(owner: Any, dialog: Any) -> Any:
    try:
        setattr(owner, "_automation_active_dialog", dialog)
    except Exception:
        pass
    return dialog


def _active_automation_dialog(owner: Any) -> Any:
    for candidate in (
        getattr(owner, "_automation_active_dialog", None),
        getattr(owner, "_correction_dictionary_dialog", None),
    ):
        if candidate is not None and bool(getattr(candidate, "isVisible", lambda: False)()):
            return candidate
    return None


def _show_dialog_nonmodal(owner: Any, dialog: Any) -> Any:
    if dialog is None:
        return None
    _set_active_automation_dialog(owner, dialog)
    _bridge_best_effort("dialog setModal", lambda: getattr(dialog, "setModal", lambda *_: None)(False), default=None)
    _bring_to_front(dialog)
    return dialog


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


def _is_status_command(command: str) -> bool:
    return str(command or "") in _STATUS_COMMANDS


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


def _personalization_scalar_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    scalars: dict[str, Any] = {}
    for key, raw in list(value.items()):
        if isinstance(raw, (str, int, float, bool)) or raw is None:
            scalars[str(key)] = raw
    return scalars


def _personalization_runtime_snapshot(owner: Any) -> dict[str, Any]:
    thread = getattr(owner, "_automation_personalization_idle_thread", None)
    active = bool(thread is not None and thread.is_alive())
    return {
        "foreground_busy_until_ms": int(getattr(owner, "_lora_foreground_busy_until_ms", 0) or 0),
        "foreground_busy_reason": str(getattr(owner, "_lora_foreground_busy_reason", "") or ""),
        "active": active,
        "active_action": str(getattr(owner, "_automation_personalization_idle_active_action", "") or ""),
        "last_action": str(getattr(owner, "_automation_personalization_idle_last_action", "") or ""),
        "last_error": str(getattr(owner, "_automation_personalization_idle_last_error", "") or ""),
        "started_at_ms": int(getattr(owner, "_automation_personalization_idle_started_at_ms", 0) or 0),
        "finished_at_ms": int(getattr(owner, "_automation_personalization_idle_finished_at_ms", 0) or 0),
        "last_result": _personalization_scalar_dict(getattr(owner, "_automation_personalization_idle_last_result", {})),
    }


def _start_background_personalization_action(owner: Any, *, action: str, runner: Any) -> dict[str, Any]:
    thread = getattr(owner, "_automation_personalization_idle_thread", None)
    if thread is not None and thread.is_alive():
        return _personalization_runtime_snapshot(owner)
    setattr(owner, "_automation_personalization_idle_last_action", str(action or ""))
    setattr(owner, "_automation_personalization_idle_active_action", str(action or ""))
    setattr(owner, "_automation_personalization_idle_last_error", "")
    setattr(owner, "_automation_personalization_idle_last_result", {})
    setattr(owner, "_automation_personalization_idle_started_at_ms", int(time.time() * 1000))
    setattr(owner, "_automation_personalization_idle_finished_at_ms", 0)

    def _worker() -> None:
        result: dict[str, Any] = {}
        error = ""
        try:
            result = dict(runner() or {})
        except Exception as exc:
            error = str(exc)
            get_logger().log(f"⚠️ 개인화 idle 자동화 작업 실패 [{action}]: {exc}")
        setattr(owner, "_automation_personalization_idle_last_result", result)
        setattr(owner, "_automation_personalization_idle_last_error", error)
        setattr(owner, "_automation_personalization_idle_finished_at_ms", int(time.time() * 1000))
        setattr(owner, "_automation_personalization_idle_active_action", "")

    worker = threading.Thread(
        target=_worker,
        name=f"automation-personalization-{str(action or 'idle')}",
        daemon=True,
    )
    setattr(owner, "_automation_personalization_idle_thread", worker)
    worker.start()
    return _personalization_runtime_snapshot(owner)


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
    editor_stt = {
        "enabled": bool(getattr(editor, "_stt_mode_enabled", False)) if editor is not None else False,
        "state": str(getattr(editor, "_stt_state", "") or "") if editor is not None else "",
        "recording": bool(getattr(editor, "_stt_recording", False)) if editor is not None else False,
        "vad_running": bool(getattr(editor, "_stt_vad_running", False)) if editor is not None else False,
    }
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
        "editor_stt": editor_stt,
        "guided_snapshot_run": guided_state,
        "queue_runtime": _queue_runtime_snapshot(owner),
        "personalization_runtime": _personalization_runtime_snapshot(owner),
        "runtime_resource": _runtime_resource_snapshot(owner),
        "recent_logs": recent_logs,
        "recent_stage_logs": recent_stage_logs,
    }


def _peek_status_snapshot_cache(owner: Any, *, max_age_sec: float | None = None) -> tuple[float, dict[str, Any]] | None:
    owner_key = id(owner)
    now = time.monotonic()
    with _STATUS_SNAPSHOT_CACHE_LOCK:
        cached = _STATUS_SNAPSHOT_CACHE.get(owner_key)
    if cached is None:
        return None
    cached_at, snapshot = cached
    age = max(0.0, now - float(cached_at or 0.0))
    if max_age_sec is not None and age > max(0.0, float(max_age_sec)):
        return None
    return age, dict(snapshot or {})


def _store_status_snapshot(owner: Any, snapshot: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(snapshot or {})
    with _STATUS_SNAPSHOT_CACHE_LOCK:
        _STATUS_SNAPSHOT_CACHE[id(owner)] = (time.monotonic(), dict(data))
    return data


def _status_result(command: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    message = "pong" if command == "ping" else ""
    return build_command_result(command, ok=True, accepted=True, message=message, data=snapshot)


def _cached_status_snapshot(owner: Any) -> dict[str, Any]:
    cached_entry = _peek_status_snapshot_cache(owner, max_age_sec=_STATUS_SNAPSHOT_CACHE_TTL_SEC)
    if cached_entry is not None:
        _age, snapshot = cached_entry
        return snapshot
    snapshot = _status_snapshot(owner)
    return _store_status_snapshot(owner, snapshot)


def _clear_status_snapshot_cache(owner: Any | None = None) -> None:
    with _STATUS_SNAPSHOT_CACHE_LOCK:
        if owner is None:
            _STATUS_SNAPSHOT_CACHE.clear()
        else:
            _STATUS_SNAPSHOT_CACHE.pop(id(owner), None)


def _status_fallback_snapshot(owner: Any) -> dict[str, Any]:
    # status는 "완벽한 최신성"보다 "절대 timeout 나지 않는 것"이 더 중요하다.
    # 메인 스레드가 바쁘면 마지막 known-good snapshot + cheap fields로 즉시 응답한다.
    cached_entry = _peek_status_snapshot_cache(owner, max_age_sec=None)
    cached_age = None
    snapshot = {}
    if cached_entry is not None:
        cached_age, snapshot = cached_entry
    data = dict(snapshot or {})
    editor = getattr(owner, "_editor_widget", None)
    editor_state = data.get("editor_state", "")
    editor_media_path = data.get("editor_media_path", "")
    try:
        if not editor_state and editor is not None:
            editor_state = str(getattr(getattr(editor, "sm", None), "state", "") or "")
    except Exception:
        pass
    try:
        if not editor_media_path and editor is not None:
            editor_media_path = str(getattr(editor, "media_path", "") or "")
    except Exception:
        pass
    data["editor_open"] = bool(data.get("editor_open", editor is not None))
    data["editor_media_path"] = str(editor_media_path or "")
    data["editor_state"] = str(editor_state or "")
    data["current_project_path"] = str(data.get("current_project_path", getattr(owner, "_current_project_path", "")) or "")
    data["current_work_mode"] = str(data.get("current_work_mode", getattr(owner, "_current_work_mode", "")) or "")
    data["backend_active"] = bool(data.get("backend_active", getattr(getattr(owner, "backend", None), "_active", False)))
    data["auto_processing_active"] = bool(data.get("auto_processing_active", getattr(owner, "_auto_processing_active", False)))
    if not isinstance(data.get("editor_runtime"), dict):
        data["editor_runtime"] = {}
    if not isinstance(data.get("guided_snapshot_run"), dict):
        data["guided_snapshot_run"] = {}
    if not data["guided_snapshot_run"]:
        guided_getter = getattr(owner, "_automation_guided_snapshot_state_payload", None)
        if callable(guided_getter):
            data["guided_snapshot_run"] = _bridge_best_effort(
                "guided snapshot fallback state",
                lambda: dict(guided_getter() or {}),
                default={},
            )
    if not isinstance(data.get("queue_runtime"), dict):
        data["queue_runtime"] = {}
    if not isinstance(data.get("runtime_resource"), dict):
        data["runtime_resource"] = _runtime_resource_snapshot(owner)
    if not isinstance(data.get("editor_aux_counts"), dict):
        data["editor_aux_counts"] = {
            "stt_preview_segment_count": 0,
            "voice_activity_segment_count": 0,
            "provisional_cut_boundary_count": 0,
        }
    if not isinstance(data.get("recent_logs"), list):
        data["recent_logs"] = _recent_logs_snapshot(40)
    if not isinstance(data.get("recent_stage_logs"), list):
        data["recent_stage_logs"] = _recent_stage_logs_snapshot(20)
    data["status_snapshot_fallback"] = True
    if cached_age is not None:
        data["status_snapshot_age_sec"] = round(float(cached_age), 3)
    return data


def _status_signal_should_defer_to_fallback(owner: Any) -> bool:
    editor = getattr(owner, "_editor_widget", None)
    try:
        if str(getattr(getattr(editor, "sm", None), "state", "") or "") == "ST_PROC":
            return True
    except Exception:
        pass
    try:
        if bool(getattr(getattr(owner, "backend", None), "_active", False)):
            return True
    except Exception:
        pass
    try:
        if bool(getattr(owner, "_auto_processing_active", False)):
            return True
    except Exception:
        pass
    runtime_resource = _runtime_resource_snapshot(owner)
    active_labels = [str(label or "").strip().lower() for label in list(runtime_resource.get("active_labels") or [])]
    return any(label in {"pipeline", "editor"} for label in active_labels)


def _fast_status_command_result(owner: Any, payload: dict[str, Any], *, timeout_sec: float = 0.08) -> dict[str, Any]:
    # status/ping은 읽기 전용 진단 경로다.
    # 여기서 일반 명령처럼 UI 스레드를 길게 기다리면 automation 전체가 멈춘 것처럼 보인다.
    command_payload = normalize_command_payload(payload)
    command = command_payload.get("command", "")
    cached_entry = _peek_status_snapshot_cache(owner, max_age_sec=_STATUS_SNAPSHOT_CACHE_TTL_SEC)
    if cached_entry is not None:
        _age, snapshot = cached_entry
        return _status_result(command, snapshot)
    if _status_signal_should_defer_to_fallback(owner):
        stale_entry = _peek_status_snapshot_cache(owner, max_age_sec=_STATUS_BUSY_STALE_REUSE_SEC)
        if stale_entry is not None:
            age, snapshot = stale_entry
            stale_snapshot = dict(snapshot or {})
            stale_snapshot["status_snapshot_fallback"] = True
            stale_snapshot["status_snapshot_age_sec"] = round(float(age), 3)
            return _status_result(command, stale_snapshot)
        fallback = _store_status_snapshot(owner, _status_fallback_snapshot(owner))
        return _status_result(command, fallback)
    signal = getattr(owner, "_sig_external_app_command", None)
    state: dict[str, Any] | None = None
    if hasattr(signal, "emit"):
        state = {"event": threading.Event()}
        try:
            signal.emit(dict(command_payload), state)
        except Exception as exc:
            _log_bridge_nonfatal(f"status signal emit {command}", exc)
            state = None
    quick_timeout = min(0.20, max(0.02, float(timeout_sec or 0.08)))
    if state is not None and state["event"].wait(quick_timeout):
        result = _signal_state_result(state)
        if result is not None:
            if isinstance(result.get("data"), dict):
                _store_status_snapshot(owner, result.get("data"))
            return result
    fallback = _store_status_snapshot(owner, _status_fallback_snapshot(owner))
    return _status_result(command, fallback)


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

    def ok(
        *,
        message: str = "",
        data: dict[str, Any] | None = None,
        queued: bool = False,
        accepted: bool = True,
    ) -> dict[str, Any]:
        return build_command_result(command, ok=True, accepted=accepted, queued=queued, message=message, data=data)

    def fail(
        error: str,
        *,
        message: str = "",
        data: dict[str, Any] | None = None,
        accepted: bool = False,
        queued: bool = False,
    ) -> dict[str, Any]:
        return build_command_result(
            command,
            ok=False,
            accepted=accepted,
            queued=queued,
            error=error,
            message=message,
            data=data,
        )

    if command == "ping":
        return ok(message="pong", data=_cached_status_snapshot(owner))

    if command == "status":
        return ok(data=_cached_status_snapshot(owner))

    if command == "guided-subtitle-status":
        return ok(data=_cached_status_snapshot(owner))

    _clear_status_snapshot_cache(owner)
    helpers = SimpleNamespace(
        active_automation_dialog=_active_automation_dialog,
        apply_automation_mode_override=_apply_automation_mode_override,
        bring_to_front=_bring_to_front,
        bridge_best_effort=_bridge_best_effort,
        capture_widget_snapshot=_capture_widget_snapshot,
        capture_window_snapshot=_capture_window_snapshot,
        command_option_bool=_command_option_bool,
        command_option_float=_command_option_float,
        command_option_int=_command_option_int,
        current_editor_srt_segments=_current_editor_srt_segments,
        editor_pipeline_start_callback=_editor_pipeline_start_callback,
        editor_runtime_snapshot=_editor_runtime_snapshot,
        existing_dir=_existing_dir,
        existing_file=_existing_file,
        file_result=_file_result,
        multiclip_existing_srt_candidates=_multiclip_existing_srt_candidates,
        noop=_noop,
        normalize_mode=normalize_mode,
        normalize_multiclip_reuse_policy=_normalize_multiclip_reuse_policy,
        normalize_path=_normalize_path,
        ordered_media_files=ordered_media_files,
        queue_runtime_snapshot=_queue_runtime_snapshot,
        queue_window_snapshot=_queue_window_snapshot,
        resolve_multiclip_files=_resolve_multiclip_files,
        saved_srt_outputs=_saved_srt_outputs,
        select_editor_segment_from_options=_select_editor_segment_from_options,
        set_active_automation_dialog=_set_active_automation_dialog,
        show_dialog_nonmodal=_show_dialog_nonmodal,
        start_background_personalization_action=_start_background_personalization_action,
        status_snapshot=_status_snapshot,
        store_status_snapshot=_store_status_snapshot,
        subtitle_video_output_path=_subtitle_video_output_path,
    )
    result = _handle_bridge_command(
        owner,
        command_payload,
        command,
        ok=ok,
        fail=fail,
        logger=logger,
        helpers=helpers,
    )
    if result is not None:
        return result
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
    command = normalize_command_payload(payload).get("command", "")
    app = QApplication.instance()
    if app is not None and QThread.currentThread() == app.thread():
        return execute_app_command(owner, payload)
    if _is_status_command(command):
        # 상태 조회만 fast-path를 탄다. 상태 변경 명령까지 여기로 보내면
        # UI/UX 동작 계약이 바뀌므로 분리 유지한다.
        return _fast_status_command_result(owner, payload, timeout_sec=min(float(timeout_sec or 12.0), 0.08))
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
