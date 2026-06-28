#!/usr/bin/env python3
from __future__ import annotations
# ruff: noqa: E402

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.automation.app_command_protocol import build_command_payload
from core.media_queue_order import ordered_media_files
from tools.automation_command_client import (
    command_is_read_only,
    result_is_waiting_for_app,
    send_app_command_with_readiness_retry,
)


def _file_artifact_state(path: str) -> dict[str, Any]:
    target = str(path or "").strip()
    exists = bool(target) and os.path.isfile(target)
    size = int(os.path.getsize(target)) if exists else 0
    return {
        "path": target,
        "path_exists": exists,
        "path_size": size,
    }


def _wait_for_file_artifact(path: str, *, timeout_sec: float) -> dict[str, Any]:
    target = str(path or "").strip()
    deadline = time.monotonic() + max(0.0, float(timeout_sec or 0.0))
    while target and time.monotonic() < deadline:
        state = _file_artifact_state(target)
        if state["path_exists"] and int(state["path_size"] or 0) > 0:
            return state
        time.sleep(0.1)
    return _file_artifact_state(target)


def _snapshot_artifact_path(payload: dict[str, Any], result: dict[str, Any]) -> str:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    return str(data.get("path") or payload.get("path") or "").strip()


def _guided_timeout_evidence(payload: dict[str, Any], status_result: dict[str, Any]) -> dict[str, Any]:
    requested_path = str(payload.get("path") or "").strip()
    data = status_result.get("data") if isinstance(status_result.get("data"), dict) else {}
    guided = data.get("guided_snapshot_run") if isinstance(data.get("guided_snapshot_run"), dict) else {}
    editor_media_path = str(data.get("editor_media_path") or "").strip()
    editor_state = str(data.get("editor_state") or "").strip()
    backend_active = bool(data.get("backend_active", False))
    guided_active = bool(guided.get("active", False))
    matched_path = bool(requested_path and editor_media_path and requested_path == editor_media_path)
    return {
        "requested_path": requested_path,
        "editor_media_path": editor_media_path,
        "matched_path": matched_path,
        "editor_state": editor_state,
        "backend_active": backend_active,
        "guided_active": guided_active,
        "work_may_have_started": bool(matched_path or guided_active or backend_active or editor_state == "ST_PROC"),
    }


def _finalize_appctl_result(
    payload: dict[str, Any],
    result: dict[str, Any],
    *,
    timeout_sec: float,
    sender: Callable[..., dict[str, Any]] = send_app_command_with_readiness_retry,
) -> dict[str, Any]:
    command = str(payload.get("command") or "").strip()
    finalized = dict(result or {})
    data = dict(finalized.get("data") or {}) if isinstance(finalized.get("data"), dict) else {}

    if command in {"capture-snapshot", "snapshot"}:
        artifact_path = _snapshot_artifact_path(payload, finalized)
        if artifact_path:
            if finalized.get("ok") and (finalized.get("queued") or finalized.get("message") == "snapshot_queued"):
                artifact = _wait_for_file_artifact(artifact_path, timeout_sec=max(0.5, min(6.0, float(timeout_sec or 0.0))))
            else:
                artifact = _file_artifact_state(artifact_path)
            data["artifact"] = artifact
            data["artifact_ready"] = bool(artifact["path_exists"] and int(artifact["path_size"] or 0) > 0)
            finalized["data"] = data

    if command == "guided-subtitle-run" and str(finalized.get("error") or "") == "command_timeout":
        status_payload = build_command_payload("guided-subtitle-status")
        try:
            status = sender(status_payload, timeout_sec=max(0.5, min(3.0, float(timeout_sec or 0.0))))
        except OSError as exc:
            status = {"ok": False, "error": "app_unreachable", "message": str(exc), "data": {}}
        data["post_timeout_status"] = status
        data["post_timeout_evidence"] = _guided_timeout_evidence(payload, status)
        finalized["data"] = data

    return finalized


def _add_editor_selection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--line", type=int, default=None)
    parser.add_argument("--start-sec", type=float, default=None)
    parser.add_argument("--at-playhead", action="store_true")
    parser.add_argument("--center", action="store_true")
    parser.add_argument("--sync-playhead", action="store_true")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control the running AI Subtitle Studio app.")
    parser.add_argument("--timeout", type=float, default=8.0, help="UDP response timeout in seconds")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ping")
    sub.add_parser("status")
    sub.add_parser("guided-subtitle-status")
    capture_snapshot = sub.add_parser("capture-snapshot", aliases=["snapshot"])
    capture_snapshot.add_argument("path", nargs="?")
    capture_dictionary_snapshot = sub.add_parser("capture-dictionary-snapshot")
    capture_dictionary_snapshot.add_argument("path", nargs="?")
    sub.add_parser("show-home")
    sub.add_parser("open-roughcut")
    roughcut_select_candidate = sub.add_parser("roughcut-select-candidate")
    roughcut_select_candidate.add_argument("--candidate-id", default="")
    roughcut_select_candidate.add_argument("--index", type=int, default=None)
    roughcut_select = sub.add_parser("roughcut-select-chapter")
    roughcut_select.add_argument("--chapter-id", default="")
    roughcut_select.add_argument("--row", type=int, default=None)
    roughcut_select.add_argument("--autoplay", action="store_true")
    roughcut_move_segment = sub.add_parser("roughcut-move-segment")
    roughcut_move_segment.add_argument("--direction", choices=["up", "down"], default="")
    roughcut_move_segment.add_argument("--delta", type=int, default=None)
    sub.add_parser("roughcut-play-sequence")
    roughcut_move = sub.add_parser("roughcut-move-chapter")
    roughcut_move.add_argument("--direction", choices=["up", "down"], default="")
    roughcut_move.add_argument("--delta", type=int, default=None)
    roughcut_filter = sub.add_parser("roughcut-set-safety-filter")
    roughcut_filter.add_argument("value")
    roughcut_export_srt = sub.add_parser("roughcut-export-srt")
    roughcut_export_srt.add_argument("path", nargs="?")
    roughcut_render_video = sub.add_parser("roughcut-render-video")
    roughcut_render_video.add_argument("path", nargs="?")
    sub.add_parser("open-dictionary")
    sub.add_parser("open-settings")
    sub.add_parser("open-speaker-settings")
    capture_active_dialog = sub.add_parser("capture-active-dialog")
    capture_active_dialog.add_argument("path", nargs="?")
    sub.add_parser("close-active-dialog")
    sub.add_parser("save-project")
    sub.add_parser("save-subtitles")
    export_subtitles = sub.add_parser("export-subtitles")
    export_subtitles.add_argument("path", nargs="?")
    sub.add_parser("export-subtitle-video")
    sub.add_parser("start-current-pipeline")
    sub.add_parser("start-current-roughcut")
    editor_set_playhead = sub.add_parser("editor-set-playhead")
    editor_set_playhead.add_argument("sec", type=float)
    editor_set_playhead.add_argument("--center", action="store_true")
    editor_set_playhead.add_argument("--no-sync-video", action="store_true")

    editor_pin_shadow_playhead = sub.add_parser("editor-pin-shadow-playhead")
    editor_pin_shadow_playhead.add_argument("sec", nargs="?", type=float, default=None)

    sub.add_parser("editor-clear-shadow-playhead")
    sub.add_parser("editor-zoom-max")
    editor_timeline_view = sub.add_parser("editor-timeline-view")
    editor_timeline_view.add_argument("action", choices=["zoom-in", "zoom-out", "fit", "time-window", "max"])
    sub.add_parser("editor-subtitle-magnet")

    editor_playback = sub.add_parser("editor-playback")
    editor_playback.add_argument("action", choices=["play", "pause", "toggle"], nargs="?", default="toggle")

    editor_video = sub.add_parser("editor-video")
    editor_video.add_argument("action", choices=["show", "hide", "toggle"], nargs="?", default="toggle")

    editor_stt_mode = sub.add_parser("editor-stt-mode")
    editor_stt_mode.add_argument("action", choices=["enable", "disable", "toggle"], nargs="?", default="toggle")

    sub.add_parser("global-menu-status")
    global_menu_action = sub.add_parser("global-menu-action")
    global_menu_action.add_argument(
        "action",
        choices=[
            "settings",
            "speaker",
            "dictionary",
            "save",
            "video",
            "stt",
            "center_save",
            "left_설정",
            "left_화자",
            "left_사전",
            "left_비디오",
            "left_음성",
        ],
    )

    editor_select_segment = sub.add_parser("editor-select-segment")
    _add_editor_selection_args(editor_select_segment)

    editor_begin_smart_split = sub.add_parser("editor-begin-smart-split")
    _add_editor_selection_args(editor_begin_smart_split)

    editor_set_inline_cursor = sub.add_parser("editor-set-inline-cursor")
    editor_set_inline_cursor.add_argument("position", type=int)

    sub.add_parser("editor-commit-inline-edit")

    editor_smart_split = sub.add_parser("editor-smart-split")
    _add_editor_selection_args(editor_smart_split)

    editor_move_segment_left = sub.add_parser("editor-move-segment-left")
    _add_editor_selection_args(editor_move_segment_left)

    editor_move_segment_right = sub.add_parser("editor-move-segment-right")
    _add_editor_selection_args(editor_move_segment_right)

    editor_move_diamond = sub.add_parser("editor-move-diamond")
    _add_editor_selection_args(editor_move_diamond)
    editor_move_diamond.add_argument("--side", choices=["left", "right", "closest"], default="closest")

    editor_merge_diamond = sub.add_parser("editor-merge-diamond")
    _add_editor_selection_args(editor_merge_diamond)
    editor_merge_diamond.add_argument("--side", choices=["left", "right", "closest"], default="closest")

    start_multiclip = sub.add_parser("start-multiclip")
    start_multiclip.add_argument("paths", nargs="*")
    start_multiclip.add_argument("--folder", default="")
    start_multiclip.add_argument("--mode", choices=["fast", "auto", "high", "stt"], default="")
    start_multiclip.add_argument(
        "--reuse-existing",
        choices=["ask", "yes", "no"],
        default="no",
        help="Automation default is 'no': move sibling SRTs to 자막백업 and regenerate. Use 'yes' to reuse or 'ask' to require confirmation.",
    )

    open_project = sub.add_parser("open-project")
    open_project.add_argument("path")

    open_srt = sub.add_parser("open-srt")
    open_srt.add_argument("path")

    open_media = sub.add_parser("open-media")
    open_media.add_argument("path")

    guided_run = sub.add_parser("guided-subtitle-run")
    guided_run.add_argument("path")
    guided_run.add_argument("--snapshot-dir", default="")

    queue_folder = sub.add_parser("queue-folder")
    queue_folder.add_argument("path")

    queue_files = sub.add_parser("queue-files")
    queue_files.add_argument("paths", nargs="+")

    personalization_idle = sub.add_parser("personalization-idle")
    personalization_idle.add_argument("action", choices=["run-now", "pause", "resume"], nargs="?", default="run-now")
    return parser


def _editor_selection_options(args: argparse.Namespace) -> dict:
    return {
        "line": getattr(args, "line", None),
        "start_sec": getattr(args, "start_sec", None),
        "at_playhead": bool(getattr(args, "at_playhead", False)),
        "center": bool(getattr(args, "center", False)),
        "sync_playhead": bool(getattr(args, "sync_playhead", False)),
    }


def _resolved_start_multiclip_paths(args: argparse.Namespace) -> list[str]:
    paths = [str(path or "").strip() for path in list(getattr(args, "paths", []) or []) if str(path or "").strip()]
    if paths:
        return paths
    folder = str(getattr(args, "folder", "") or "").strip()
    if not folder:
        return []
    return ordered_media_files(folder)


def _payload_from_args(args: argparse.Namespace) -> dict:
    command = str(args.command or "")
    if command in {
        "open-project",
        "open-srt",
        "open-media",
        "queue-folder",
        "capture-snapshot",
        "snapshot",
        "capture-dictionary-snapshot",
        "capture-active-dialog",
        "export-subtitles",
        "roughcut-export-srt",
        "roughcut-render-video",
    }:
        return build_command_payload(command, path=args.path)
    if command in {
        "open-roughcut",
        "open-dictionary",
        "open-settings",
        "open-speaker-settings",
        "close-active-dialog",
        "save-subtitles",
        "export-subtitle-video",
    }:
        return build_command_payload(command)
    if command == "guided-subtitle-run":
        return build_command_payload(command, path=args.path, options={"snapshot_dir": str(args.snapshot_dir or "")})
    if command == "roughcut-select-chapter":
        return build_command_payload(
            command,
            options={
                "chapter_id": str(args.chapter_id or ""),
                "row": args.row,
                "autoplay": bool(args.autoplay),
            },
        )
    if command == "roughcut-select-candidate":
        return build_command_payload(
            command,
            options={
                "candidate_id": str(args.candidate_id or ""),
                "index": args.index,
            },
        )
    if command == "roughcut-move-segment":
        return build_command_payload(
            command,
            options={
                "direction": str(args.direction or ""),
                "delta": args.delta,
            },
        )
    if command == "roughcut-play-sequence":
        return build_command_payload(command)
    if command == "roughcut-move-chapter":
        return build_command_payload(
            command,
            options={
                "direction": str(args.direction or ""),
                "delta": args.delta,
            },
        )
    if command == "roughcut-set-safety-filter":
        return build_command_payload(command, options={"value": str(args.value or "")})
    if command == "queue-files":
        return build_command_payload(command, paths=list(args.paths or []))
    if command == "editor-set-playhead":
        return build_command_payload(
            command,
            options={
                "sec": float(args.sec),
                "center": bool(args.center),
                "sync_video": not bool(args.no_sync_video),
            },
        )
    if command == "editor-pin-shadow-playhead":
        return build_command_payload(command, options={"sec": args.sec})
    if command == "editor-clear-shadow-playhead":
        return build_command_payload(command)
    if command == "editor-zoom-max":
        return build_command_payload(command)
    if command == "editor-timeline-view":
        return build_command_payload(command, options={"action": str(args.action or "")})
    if command == "editor-subtitle-magnet":
        return build_command_payload(command)
    if command == "editor-playback":
        return build_command_payload(command, options={"action": str(args.action or "toggle")})
    if command == "editor-video":
        return build_command_payload(command, options={"action": str(args.action or "toggle")})
    if command == "editor-stt-mode":
        return build_command_payload(command, options={"action": str(args.action or "toggle")})
    if command == "global-menu-status":
        return build_command_payload(command)
    if command == "global-menu-action":
        return build_command_payload(command, options={"action": str(args.action or "")})
    if command in {
        "editor-select-segment",
        "editor-begin-smart-split",
        "editor-smart-split",
        "editor-move-segment-left",
        "editor-move-segment-right",
    }:
        return build_command_payload(command, options=_editor_selection_options(args))
    if command == "editor-set-inline-cursor":
        return build_command_payload(command, options={"position": int(args.position)})
    if command == "editor-commit-inline-edit":
        return build_command_payload(command)
    if command in {"editor-move-diamond", "editor-merge-diamond"}:
        options = _editor_selection_options(args)
        options["side"] = str(args.side or "closest")
        return build_command_payload(command, options=options)
    if command == "start-multiclip":
        return build_command_payload(
            command,
            folder=str(args.folder or ""),
            paths=_resolved_start_multiclip_paths(args),
            options={
                "mode": str(args.mode or ""),
                "reuse_existing": str(args.reuse_existing or "ask"),
            },
        )
    if command == "personalization-idle":
        return build_command_payload(command, options={"action": str(args.action or "run-now")})
    return build_command_payload(command)


def main() -> int:
    args = _parser().parse_args()
    payload = _payload_from_args(args)
    try:
        result = send_app_command_with_readiness_retry(payload, timeout_sec=float(args.timeout or 8.0))
    except OSError as exc:
        print(json.dumps({"ok": False, "error": "app_unreachable", "message": str(exc)}, ensure_ascii=False))
        return 1
    result = _finalize_appctl_result(payload, result, timeout_sec=float(args.timeout or 8.0))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    command = str(payload.get("command", "") or "")
    if command_is_read_only(command) and result_is_waiting_for_app(result):
        return 1
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
