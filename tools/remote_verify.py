#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.automation.app_command_protocol import build_command_payload
from tools.automation_command_client import send_app_command_with_readiness_retry


def _default_output_dir(label: str) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return ROOT / "output" / "manual_verification" / f"{label}_{stamp}"


def _safe_slug(text: str) -> str:
    raw = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(text or "").strip().lower())
    return raw.strip("-") or "step"


def _send(command: str, *, timeout: float, path: str = "", options: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = build_command_payload(command, path=path, options=dict(options or {}))
    return send_app_command_with_readiness_retry(payload, timeout_sec=float(timeout))


def _wait_for_snapshot(path: str, *, timeout_sec: float = 6.0) -> bool:
    target = str(path or "").strip()
    if not target:
        return False
    deadline = time.monotonic() + max(0.2, float(timeout_sec or 6.0))
    while time.monotonic() < deadline:
        if os.path.isfile(target) and os.path.getsize(target) > 0:
            return True
        time.sleep(0.1)
    return os.path.isfile(target)


def _capture_status(timeout: float) -> dict[str, Any]:
    try:
        return _send("status", timeout=timeout)
    except OSError as exc:
        return {"ok": False, "error": "app_unreachable", "message": str(exc), "data": {}}


def _capture_snapshot(output_dir: Path, label: str, *, timeout: float) -> dict[str, Any]:
    filename = f"{label}.png"
    target = output_dir / filename
    try:
        result = _send("capture-snapshot", timeout=timeout, path=str(target))
    except OSError as exc:
        return {"ok": False, "error": "app_unreachable", "message": str(exc), "path": str(target)}
    data = dict(result.get("data") or {})
    snapshot_path = str(data.get("path", target))
    if result.get("ok") and (result.get("queued") or result.get("message") == "snapshot_queued"):
        _wait_for_snapshot(snapshot_path, timeout_sec=max(4.0, timeout))
    return {
        "ok": bool(result.get("ok")),
        "error": str(result.get("error", "") or ""),
        "message": str(result.get("message", "") or ""),
        "path": snapshot_path,
    }


def _record_step(
    report: dict[str, Any],
    output_dir: Path,
    step_name: str,
    *,
    timeout: float,
    snapshot: bool,
    command: str | None = None,
    path: str = "",
    options: dict[str, Any] | None = None,
) -> None:
    entry: dict[str, Any] = {
        "name": step_name,
        "command": command or "",
        "path": path,
        "options": dict(options or {}),
    }
    if command:
        # 편집 명령은 UI 상태를 바꾸므로 재시도하지 않는다.
        # 대신 직전에 status fast-path로 app bridge 준비 상태를 확인해 중복 실행 위험을 피한다.
        entry["preflight_status"] = _capture_status(max(1.0, min(float(timeout or 1.0), 4.0)))
        try:
            entry["result"] = _send(command, timeout=timeout, path=path, options=options)
        except OSError as exc:
            entry["result"] = {"ok": False, "error": "app_unreachable", "message": str(exc), "data": {}}
    else:
        entry["result"] = {"ok": True, "message": "record_only", "data": {}}
    entry["status"] = _capture_status(timeout)
    if snapshot:
        entry["snapshot"] = _capture_snapshot(output_dir, _safe_slug(step_name), timeout=timeout)
    report.setdefault("steps", []).append(entry)


def _selection_options(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "line": args.select_line,
        "start_sec": args.select_start_sec,
        "at_playhead": bool(args.select_at_playhead),
        "center": bool(args.select_center),
        "sync_playhead": bool(args.select_sync_playhead),
    }


def _action_snapshot_path(output_dir: Path, action: str) -> str:
    return str(output_dir / f"{_safe_slug(action)}.png")


def _editor_action_spec(
    action: str,
    args: argparse.Namespace,
    selection: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any] | None:
    if action == "snapshot":
        return {"command": "", "options": {}, "snapshot": True, "path": ""}
    selection_commands = {
        "smart-split": "editor-smart-split",
        "begin-smart-split": "editor-begin-smart-split",
        "move-segment-left": "editor-move-segment-left",
        "move-segment-right": "editor-move-segment-right",
    }
    if action in selection_commands:
        return {"command": selection_commands[action], "options": dict(selection), "snapshot": False, "path": ""}
    if action == "set-inline-cursor":
        return {"command": "editor-set-inline-cursor", "options": {"position": args.cursor_pos}, "snapshot": False, "path": ""}
    if action == "commit-inline-edit":
        return {"command": "editor-commit-inline-edit", "options": {}, "snapshot": False, "path": ""}
    if action in {"play", "playback-play"}:
        return {"command": "editor-playback", "options": {"action": "play"}, "snapshot": False, "path": ""}
    if action in {"pause", "playback-pause"}:
        return {"command": "editor-playback", "options": {"action": "pause"}, "snapshot": False, "path": ""}
    if action in {"save", "save-project"}:
        return {"command": "save-project", "options": {}, "snapshot": False, "path": ""}
    if action in {"video-show", "video-hide", "video-toggle"}:
        return {
            "command": "editor-video",
            "options": {"action": action.split("-", 1)[1]},
            "snapshot": False,
            "path": "",
        }
    if action in {"stt-enable", "stt-disable", "stt-toggle"}:
        return {
            "command": "editor-stt-mode",
            "options": {"action": action.split("-", 1)[1]},
            "snapshot": False,
            "path": "",
        }
    if action in {"open-dictionary", "open-settings", "open-speaker-settings", "close-active-dialog"}:
        return {"command": action, "options": {}, "snapshot": False, "path": ""}
    if action == "capture-active-dialog":
        return {
            # 팝업 증거는 전체 창 스냅샷과 분리해 단계별 PNG를 남긴다.
            "command": "capture-active-dialog",
            "options": {},
            "snapshot": False,
            "path": _action_snapshot_path(output_dir, action),
        }
    if action in {"capture-dictionary", "capture-dictionary-snapshot"}:
        return {
            "command": "capture-dictionary-snapshot",
            "options": {},
            "snapshot": False,
            "path": _action_snapshot_path(output_dir, "capture-dictionary"),
        }
    if action in {"lora-run-now", "lora-pause", "lora-resume"}:
        return {
            "command": "personalization-idle",
            "options": {"action": action.split("-", 1)[1]},
            "snapshot": False,
            "path": "",
        }
    if action in {"move-diamond", "merge-diamond"}:
        options = dict(selection)
        options["side"] = str(args.diamond_side or "closest")
        command = "editor-move-diamond" if action == "move-diamond" else "editor-merge-diamond"
        return {"command": command, "options": options, "snapshot": False, "path": ""}
    return None


def _record_editor_action(
    report: dict[str, Any],
    output_dir: Path,
    action: str,
    *,
    args: argparse.Namespace,
    selection: dict[str, Any],
) -> None:
    spec = _editor_action_spec(action, args, selection, output_dir)
    if spec is None:
        report.setdefault("steps", []).append(
            {
                "name": action,
                "command": "",
                "result": {"ok": False, "error": "unknown_action", "message": action, "data": {}},
            }
        )
        return
    if bool(spec.get("snapshot")):
        _record_step(report, output_dir, action, timeout=args.timeout, snapshot=True)
        return
    _record_step(
        report,
        output_dir,
        action,
        timeout=args.timeout,
        snapshot=args.snapshot_each_step,
        command=str(spec.get("command", "") or ""),
        path=str(spec.get("path", "") or ""),
        options=dict(spec.get("options") or {}),
    )


def _write_report_files(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report.json"
    md_path = output_dir / "report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Remote Verify Report",
        "",
        f"- started_at: {report.get('started_at', '')}",
        f"- output_dir: {output_dir}",
        "",
    ]
    final_status = dict(report.get("final_status") or {})
    runtime = dict((final_status.get("data") or {}).get("editor_runtime") or {})
    if runtime:
        lines.extend(
            [
                "## Final Runtime",
                "",
                f"- playhead_sec: {runtime.get('playhead_sec')}",
                f"- active_seg_line: {runtime.get('active_seg_line')}",
                f"- active_seg_start: {runtime.get('active_seg_start')}",
                f"- segment_count: {runtime.get('segment_count')}",
                "",
            ]
        )
    lines.append("## Steps")
    lines.append("")
    for step in list(report.get("steps") or []):
        result = dict(step.get("result") or {})
        snapshot = dict(step.get("snapshot") or {})
        lines.append(f"- {step.get('name')}: ok={result.get('ok')} command={step.get('command')}")
        if snapshot:
            lines.append(f"  snapshot: {snapshot.get('path')}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_editor_sequence(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir).resolve() if args.output_dir else _default_output_dir(args.label or "remote_verify")
    output_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "output_dir": str(output_dir),
        "steps": [],
    }

    open_target = ""
    open_command = ""
    if args.open_media:
        open_command, open_target = "open-media", str(Path(args.open_media).resolve())
    elif args.open_srt:
        open_command, open_target = "open-srt", str(Path(args.open_srt).resolve())
    elif args.open_project:
        open_command, open_target = "open-project", str(Path(args.open_project).resolve())

    if open_command:
        _record_step(
            report,
            output_dir,
            "open",
            timeout=args.timeout,
            snapshot=args.snapshot_each_step,
            command=open_command,
            path=open_target,
        )
        time.sleep(max(0.0, float(args.settle_sec or 0.0)))

    _record_step(report, output_dir, "initial", timeout=args.timeout, snapshot=args.snapshot_each_step)

    if args.playhead_sec is not None:
        _record_step(
            report,
            output_dir,
            "set-playhead",
            timeout=args.timeout,
            snapshot=args.snapshot_each_step,
            command="editor-set-playhead",
            options={
                "sec": float(args.playhead_sec),
                "center": bool(args.playhead_center),
                "sync_video": not bool(args.no_sync_video),
            },
        )

    selection = _selection_options(args)
    if selection.get("line") is not None or selection.get("start_sec") is not None or selection.get("at_playhead"):
        _record_step(
            report,
            output_dir,
            "select-segment",
            timeout=args.timeout,
            snapshot=args.snapshot_each_step,
            command="editor-select-segment",
            options=selection,
        )

    for raw_action in list(args.actions or []):
        action = str(raw_action or "").strip().lower()
        if not action:
            continue
        _record_editor_action(report, output_dir, action, args=args, selection=selection)

    report["final_status"] = _capture_status(args.timeout)
    _write_report_files(output_dir, report)
    print(json.dumps({"ok": True, "output_dir": str(output_dir), "report_path": str(output_dir / "report.json")}, ensure_ascii=False, indent=2))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run remote app verification scenarios and save report artifacts.")
    parser.add_argument("--timeout", type=float, default=8.0)
    sub = parser.add_subparsers(dest="command", required=True)

    capture = sub.add_parser("capture")
    capture.add_argument("--label", default="capture")
    capture.add_argument("--output-dir", default="")

    editor = sub.add_parser("editor-sequence")
    editor.add_argument("--label", default="editor_sequence")
    editor.add_argument("--output-dir", default="")
    editor.add_argument("--open-media", default="")
    editor.add_argument("--open-srt", default="")
    editor.add_argument("--open-project", default="")
    editor.add_argument("--settle-sec", type=float, default=0.35)
    editor.add_argument("--playhead-sec", type=float, default=None)
    editor.add_argument("--playhead-center", action="store_true")
    editor.add_argument("--no-sync-video", action="store_true")
    editor.add_argument("--select-line", type=int, default=None)
    editor.add_argument("--select-start-sec", type=float, default=None)
    editor.add_argument("--select-at-playhead", action="store_true")
    editor.add_argument("--select-center", action="store_true")
    editor.add_argument("--select-sync-playhead", action="store_true")
    editor.add_argument("--cursor-pos", type=int, default=None)
    editor.add_argument("--diamond-side", choices=["left", "right", "closest"], default="closest")
    editor.add_argument(
        "--actions",
        nargs="*",
        default=[],
        help="Supported: begin-smart-split set-inline-cursor commit-inline-edit smart-split play pause save-project move-segment-left move-segment-right move-diamond merge-diamond video-show video-hide video-toggle stt-enable stt-disable stt-toggle open-dictionary open-settings open-speaker-settings capture-active-dialog capture-dictionary close-active-dialog lora-run-now lora-pause lora-resume snapshot",
    )
    editor.add_argument("--snapshot-each-step", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "capture":
        output_dir = Path(args.output_dir).resolve() if args.output_dir else _default_output_dir(args.label or "capture")
        output_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "output_dir": str(output_dir),
            "status": _capture_status(args.timeout),
            "snapshot": _capture_snapshot(output_dir, _safe_slug(args.label), timeout=args.timeout),
        }
        _write_report_files(output_dir, {"started_at": report["started_at"], "steps": [], "final_status": report["status"]})
        (output_dir / "capture.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": True, "output_dir": str(output_dir), "capture_path": str(output_dir / "capture.json")}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "editor-sequence":
        return _run_editor_sequence(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
