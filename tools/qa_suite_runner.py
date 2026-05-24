#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LATEST_DIR = ROOT / "output" / "manual_verification" / "latest"
DEFAULT_PYTHON = ROOT / "venv" / "bin" / "python"
APP_MAIN = ROOT / "main.py"
APP_BUNDLE_EXECUTABLE = ROOT / "dist" / "macos" / "AI Subtitle Studio.app" / "Contents" / "MacOS" / "AI Subtitle Studio"
APP_BUNDLE_MAIN = ROOT / "dist" / "macos" / "AI Subtitle Studio.app" / "Contents" / "Resources" / "app" / "main.py"

MACAU_PROJECT = ROOT / "projects" / "DJI_20260217224203_0075_D.aissproj"
X5_MEDIA = ROOT / "test video" / "X5_시승기_후반.MP4"


def _default_output_dir(profile: str) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return LATEST_DIR / f"qa_suite_{profile}_{stamp}"


def _step(
    name: str,
    *command: str,
    timeout: float = 30.0,
    delay_sec: float = 0.0,
    wait_for_path: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "command": list(command),
        "timeout": float(timeout),
        "delay_sec": float(delay_sec),
        "wait_for_path": str(wait_for_path or ""),
    }


def _app_sequence(
    scenario_id: str,
    output_dir: Path,
    *,
    description: str,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "id": scenario_id,
        "type": "app_sequence",
        "description": description,
        "output_dir": output_dir,
        "steps": steps,
    }


def _full_media(
    scenario_id: str,
    output_dir: Path,
    *,
    media: str,
    mode: str,
    duration_sec: float,
    description: str,
) -> dict[str, Any]:
    return {
        "id": scenario_id,
        "type": "full_media",
        "description": description,
        "output_dir": output_dir,
        "media": str(media),
        "mode": str(mode),
        "duration_sec": float(duration_sec),
    }


def build_feature_template_scenario(
    output_root: Path,
    *,
    scenario_id: str = "template_new_feature_macau",
    description: str = "Template scenario for future UX automation expansion.",
    project_path: str | Path = MACAU_PROJECT,
    extra_steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    scenario_dir = output_root / str(scenario_id)
    steps = [
        _step("open_project", "open-project", str(project_path), timeout=60.0, delay_sec=2.0),
        _step(
            "capture_initial",
            "capture-snapshot",
            str(scenario_dir / "snapshots" / "initial.png"),
            wait_for_path=str(scenario_dir / "snapshots" / "initial.png"),
        ),
        *list(extra_steps or []),
        _step(
            "capture_final",
            "capture-snapshot",
            str(scenario_dir / "snapshots" / "final.png"),
            wait_for_path=str(scenario_dir / "snapshots" / "final.png"),
        ),
        _step("final_status", "status", timeout=30.0),
    ]
    return _app_sequence(
        str(scenario_id),
        scenario_dir,
        description=description,
        steps=steps,
    )


def build_scenarios(profile: str, output_root: Path) -> list[dict[str, Any]]:
    normalized = str(profile or "major").strip().lower()
    if normalized not in {"quick", "major", "full"}:
        raise ValueError(f"unsupported profile: {profile}")

    scenarios: list[dict[str, Any]] = []

    editor_dir = output_root / "editor_compact_macau"
    scenarios.append(
        _app_sequence(
            "editor_compact_macau",
            editor_dir,
            description="Compact editor action path on Macau project.",
            steps=[
                _step("open_project", "open-project", str(MACAU_PROJECT), timeout=60.0, delay_sec=2.0),
                _step("capture_initial", "capture-snapshot", str(editor_dir / "snapshots" / "initial.png"), wait_for_path=str(editor_dir / "snapshots" / "initial.png")),
                _step("set_playhead", "editor-set-playhead", "1.5", "--center", delay_sec=1.0),
                _step("begin_smart_split", "editor-begin-smart-split", "--at-playhead", delay_sec=0.5),
                _step("set_inline_cursor", "editor-set-inline-cursor", "2"),
                _step("commit_inline_edit", "editor-commit-inline-edit", delay_sec=0.5),
                _step("move_segment_left", "editor-move-segment-left", "--line", "1", delay_sec=0.2),
                _step("move_segment_right", "editor-move-segment-right", "--line", "1", delay_sec=0.2),
                _step("move_diamond", "editor-move-diamond", "--line", "1", "--side", "right", delay_sec=0.5),
                _step("merge_diamond", "editor-merge-diamond", "--line", "1", "--side", "right", delay_sec=1.0),
                _step("capture_final", "capture-snapshot", str(editor_dir / "snapshots" / "final.png"), wait_for_path=str(editor_dir / "snapshots" / "final.png")),
                _step("save_project", "save-project", timeout=60.0),
                _step("final_status", "status", timeout=30.0),
            ],
        )
    )

    if normalized in {"major", "full"}:
        video_dir = output_root / "video_menu_macau"
        scenarios.append(
            _app_sequence(
                "video_menu_macau",
                video_dir,
                description="Playback and video menu smoke on Macau project.",
                steps=[
                    _step("open_project", "open-project", str(MACAU_PROJECT), timeout=60.0, delay_sec=2.0),
                    _step("play", "editor-playback", "play", delay_sec=0.5),
                    _step("pause", "editor-playback", "pause", delay_sec=0.5),
                    _step("video_hide", "editor-video", "hide", delay_sec=0.5),
                    _step("capture_hidden", "capture-snapshot", str(video_dir / "snapshots" / "video_hidden.png"), wait_for_path=str(video_dir / "snapshots" / "video_hidden.png")),
                    _step("video_show", "editor-video", "show", delay_sec=0.5),
                    _step("capture_shown", "capture-snapshot", str(video_dir / "snapshots" / "video_shown.png"), wait_for_path=str(video_dir / "snapshots" / "video_shown.png")),
                    _step("final_status", "status", timeout=30.0),
                ],
            )
        )

        save_dir = output_root / "save_export_macau"
        scenarios.append(
            _app_sequence(
                "save_export_macau",
                save_dir,
                description="Project save, subtitle save, export, and subtitle video export on Macau project.",
                steps=[
                    _step("open_project", "open-project", str(MACAU_PROJECT), timeout=60.0, delay_sec=2.0),
                    _step("save_project", "save-project", timeout=60.0),
                    _step("save_subtitles", "save-subtitles", timeout=60.0),
                    _step("export_subtitles", "export-subtitles", str(save_dir / "exports" / "manual_export.srt"), timeout=60.0),
                    _step("export_subtitle_video", "export-subtitle-video", timeout=240.0, delay_sec=1.0),
                    _step("capture_final", "capture-snapshot", str(save_dir / "snapshots" / "after_save_export.png"), wait_for_path=str(save_dir / "snapshots" / "after_save_export.png")),
                    _step("final_status", "status", timeout=30.0),
                ],
            )
        )

        menu_dir = output_root / "menu_stt_lora_macau"
        scenarios.append(
            _app_sequence(
                "menu_stt_lora_macau",
                menu_dir,
                description="Settings, speaker, dictionary, STT, and LoRA coverage on Macau project.",
                steps=[
                    _step("open_project", "open-project", str(MACAU_PROJECT), timeout=60.0, delay_sec=2.0),
                    _step("open_settings", "open-settings", delay_sec=0.5),
                    _step("capture_settings", "capture-active-dialog", str(menu_dir / "menu" / "settings_dialog.png"), wait_for_path=str(menu_dir / "menu" / "settings_dialog.png")),
                    _step("close_settings", "close-active-dialog", delay_sec=0.5),
                    _step("open_speaker_settings", "open-speaker-settings", delay_sec=0.5),
                    _step("capture_speaker", "capture-active-dialog", str(menu_dir / "menu" / "speaker_dialog.png"), wait_for_path=str(menu_dir / "menu" / "speaker_dialog.png")),
                    _step("close_speaker", "close-active-dialog", delay_sec=0.5),
                    _step("open_dictionary", "open-dictionary", delay_sec=0.5),
                    _step("capture_dictionary", "capture-dictionary-snapshot", str(menu_dir / "menu" / "dictionary_dialog.png"), wait_for_path=str(menu_dir / "menu" / "dictionary_dialog.png")),
                    _step("stt_enable", "editor-stt-mode", "enable", delay_sec=0.5),
                    _step("status_stt_enabled", "status", timeout=30.0),
                    _step("stt_disable", "editor-stt-mode", "disable", delay_sec=0.5),
                    _step("status_stt_disabled", "status", timeout=30.0),
                    _step("lora_run_now", "personalization-idle", "run-now", delay_sec=1.0),
                    _step("lora_pause", "personalization-idle", "pause", delay_sec=1.0),
                    _step("lora_resume", "personalization-idle", "resume", delay_sec=3.0),
                    _step("final_status", "status", timeout=30.0),
                ],
            )
        )

    if normalized == "full":
        scenarios.append(
            _full_media(
                "x5_high_rolling_180s",
                output_root / "x5_high_rolling_180s",
                media=str(X5_MEDIA),
                mode="high",
                duration_sec=180.0,
                description="X5 high-mode 3-minute rolling-window verification.",
            )
        )

    return scenarios


def _wait_for_file(path_text: str, *, timeout_sec: float = 8.0) -> bool:
    target = str(path_text or "").strip()
    if not target:
        return False
    path = Path(target)
    deadline = time.monotonic() + max(0.2, float(timeout_sec or 8.0))
    while time.monotonic() < deadline:
        if path.is_file() and path.stat().st_size > 0:
            return True
        time.sleep(0.1)
    return path.is_file()


def _parse_json(stdout: str) -> dict[str, Any]:
    text = str(stdout or "").strip()
    if not text:
        return {"ok": False, "error": "empty_stdout", "message": "", "data": {}}
    try:
        return dict(json.loads(text))
    except Exception:
        for line in reversed(text.splitlines()):
            candidate = str(line or "").strip()
            if not candidate.startswith("{") or not candidate.endswith("}"):
                continue
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return dict(parsed)
        return {"ok": False, "error": "invalid_json", "message": text[-300:], "data": {}}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_subprocess(command: list[str], *, cwd: Path, stdout_path: Path, stderr_path: Path) -> tuple[int, dict[str, Any]]:
    result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")
    return int(result.returncode), _parse_json(result.stdout)


def _pid_alive_for_restart(pid: int) -> bool:
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        import psutil  # type: ignore

        proc = psutil.Process(int(pid))
        if proc.status() == psutil.STATUS_ZOMBIE:
            return False
    except Exception as exc:
        _ = exc
    try:
        result = subprocess.run(["ps", "-o", "stat=", "-p", str(int(pid))], capture_output=True, text=True)
        if result.returncode == 0 and "Z" in str(result.stdout or ""):
            return False
    except Exception as exc:
        _ = exc
    return True


def _main_app_pids() -> list[int]:
    # QA hot path: bundled macOS launches appear as Python running
    # Contents/Resources/app/main.py, not as the .app executable itself.
    patterns = [str(APP_BUNDLE_EXECUTABLE), str(APP_BUNDLE_MAIN), str(APP_MAIN), "Python main.py"]
    seen: set[int] = set()
    pids: list[int] = []
    for pattern in patterns:
        result = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
        if result.returncode not in (0, 1):
            continue
        for line in result.stdout.splitlines():
            text = str(line or "").strip()
            if not text:
                continue
            try:
                pid = int(text)
            except Exception:
                continue
            if pid <= 0 or pid == os.getpid() or pid in seen:
                continue
            seen.add(pid)
            pids.append(pid)
    return pids


def _app_launch_command(python_bin: Path) -> list[str]:
    if APP_BUNDLE_EXECUTABLE.is_file():
        return [str(APP_BUNDLE_EXECUTABLE)]
    return [str(python_bin), str(APP_MAIN)]


def _wait_for_pids_exit(pids: list[int], *, timeout_sec: float) -> bool:
    pending = {int(pid) for pid in pids if int(pid) > 0}
    if not pending:
        return True
    deadline = time.monotonic() + max(0.5, float(timeout_sec or 5.0))
    while pending and time.monotonic() < deadline:
        finished: set[int] = set()
        for pid in list(pending):
            # Restart gate hot path: macOS can leave a just-killed bundle Python
            # as a zombie briefly; that must not poison the next clean app run.
            if not _pid_alive_for_restart(pid):
                finished.add(pid)
        pending -= finished
        if pending:
            time.sleep(0.2)
    return not pending


def _app_status(python_bin: Path, *, output_dir: Path, timeout_sec: float = 3.0) -> tuple[int, dict[str, Any]]:
    logs_dir = output_dir / "_suite_logs"
    return _run_subprocess(
        [
            str(python_bin),
            str(ROOT / "tools" / "appctl.py"),
            "--timeout",
            str(timeout_sec),
            "status",
        ],
        cwd=ROOT,
        stdout_path=logs_dir / "app_status.stdout",
        stderr_path=logs_dir / "app_status.stderr",
    )


def _segment_playhead_candidate(segment: dict[str, Any]) -> float | None:
    data = dict(segment or {})
    try:
        start = float(data.get("start"))
        end = float(data.get("end"))
    except Exception:
        return None
    if end <= start:
        return None
    span = end - start
    candidate = start + min(0.4, max(0.05, span * 0.25))
    if candidate >= end:
        candidate = (start + end) / 2.0
    return round(float(candidate), 4)


def _resolve_editor_compact_playhead(python_bin: Path, *, output_dir: Path) -> tuple[float | None, dict[str, Any]]:
    code, payload = _app_status(python_bin, output_dir=output_dir, timeout_sec=3.0)
    runtime = dict((((payload.get("data") or {}).get("editor_runtime")) or {}))
    segments = [
        ("active_segment", dict(runtime.get("active_segment") or {})),
        ("next_segment", dict(runtime.get("next_segment") or {})),
        ("previous_segment", dict(runtime.get("previous_segment") or {})),
    ]
    selected_from = ""
    candidate: float | None = None
    for source, segment in segments:
        candidate = _segment_playhead_candidate(segment)
        if candidate is not None:
            selected_from = source
            break
    details = {
        "status_ok": code == 0 and bool(payload.get("ok")),
        "selected_from": selected_from,
        "candidate_sec": candidate,
        "editor_runtime": runtime,
    }
    return candidate, details


def _resolve_editor_compact_diamond_command(
    command_name: str,
    requested_side: str,
    python_bin: Path,
    *,
    output_dir: Path,
) -> tuple[list[str] | None, dict[str, Any]]:
    code, payload = _app_status(python_bin, output_dir=output_dir, timeout_sec=3.0)
    runtime = dict((((payload.get("data") or {}).get("editor_runtime")) or {}))
    preferred_key = "diamond_right" if str(requested_side or "").strip().lower() == "right" else "diamond_left"
    pair = dict(runtime.get(preferred_key) or {})
    selected_key = preferred_key
    if not pair:
        fallback_key = "diamond_left" if preferred_key == "diamond_right" else "diamond_right"
        pair = dict(runtime.get(fallback_key) or {})
        selected_key = fallback_key if pair else preferred_key
    selected_side = str(pair.get("side") or requested_side or "closest")
    boundary_start = pair.get("boundary_sec", None)
    command: list[str] | None = None
    if pair and boundary_start is not None:
        left = dict(pair.get("left") or {})
        right = dict(pair.get("right") or {})
        # 변경 금지: appctl의 --start-sec는 diamond boundary 시간이 아니라
        # 먼저 선택할 자막 세그먼트의 시작 시간이다. 오른쪽 다이아몬드는
        # 왼쪽 세그먼트를 선택하고 --side right를 보내야 하며, 왼쪽
        # 다이아몬드는 오른쪽 세그먼트를 선택하고 --side left를 보내야 한다.
        # boundary_sec를 그대로 넘기면 오른쪽 세그먼트가 선택되어 merge가
        # 한 칸 밀리고, 이동 직후 `diamond_pair_missing`이 재발한다.
        selected_start = (
            left.get("start")
            if selected_side == "right"
            else right.get("start")
            if selected_side == "left"
            else None
        )
        if selected_start is None:
            selected_start = boundary_start
        command = [command_name, "--start-sec", str(selected_start), "--side", selected_side]
    elif code != 0 or not runtime:
        # automation-4 hot path: status may be intentionally compact/fallback
        # while the app is busy. Drop stale line selection and let the editor
        # choose the active/nearest diamond instead of failing on old metadata.
        command = [command_name, "--side", "closest"]
    details = {
        "status_ok": code == 0 and bool(payload.get("ok")),
        "requested_side": requested_side,
        "selected_key": selected_key,
        "selected_side": selected_side,
        "selected_start": command[2] if command and "--start-sec" in command else None,
        "pair": pair,
        "command": command,
        "editor_runtime": runtime,
    }
    return command, details


def _ensure_app_ready(python_bin: Path, *, output_dir: Path, startup_wait_sec: float = 45.0) -> dict[str, Any]:
    initial_code, initial_payload = _app_status(python_bin, output_dir=output_dir, timeout_sec=2.0)
    if initial_code == 0 and bool(initial_payload.get("ok")):
        return {
            "ok": True,
            "started_app": False,
            "status": initial_payload,
        }

    logs_dir = output_dir / "_suite_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = logs_dir / "app_bootstrap.stdout"
    stderr_path = logs_dir / "app_bootstrap.stderr"
    with stdout_path.open("w", encoding="utf-8") as stdout_file:
        with stderr_path.open("w", encoding="utf-8") as stderr_file:
            proc = subprocess.Popen(
                _app_launch_command(python_bin),
                cwd=str(ROOT),
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
            )
    deadline = time.monotonic() + max(5.0, float(startup_wait_sec or 45.0))
    latest_payload = dict(initial_payload)
    while time.monotonic() < deadline:
        time.sleep(1.0)
        code, payload = _app_status(python_bin, output_dir=output_dir, timeout_sec=2.0)
        latest_payload = dict(payload)
        if code == 0 and bool(payload.get("ok")):
            return {
                "ok": True,
                "started_app": True,
                "pid": int(proc.pid or 0),
                "status": payload,
            }
    return {
        "ok": False,
        "started_app": True,
        "pid": int(proc.pid or 0),
        "status": latest_payload,
    }


def _restart_app(python_bin: Path, *, output_dir: Path, startup_wait_sec: float = 45.0, terminate_wait_sec: float = 15.0) -> dict[str, Any]:
    pids = _main_app_pids()
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except PermissionError:
            continue

    stopped = _wait_for_pids_exit(pids, timeout_sec=terminate_wait_sec)
    if not stopped:
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                continue
            except PermissionError:
                continue
        stopped = _wait_for_pids_exit(pids, timeout_sec=5.0)

    ready = _ensure_app_ready(python_bin, output_dir=output_dir, startup_wait_sec=startup_wait_sec)
    restart_result = {
        "ok": bool(ready.get("ok")) and bool(stopped),
        "terminated_pids": pids,
        "stopped": bool(stopped),
        "started_app": bool(ready.get("started_app")),
        "pid": int(ready.get("pid", 0) or 0),
        "status": dict(ready.get("status") or {}),
    }
    _write_json(output_dir / "_suite_logs" / "app_restart.json", restart_result)
    return restart_result


def _prepare_app_for_scenario(profile: str, spec: dict[str, Any], python_bin: Path) -> dict[str, Any]:
    output_dir = Path(spec["output_dir"])
    scenario_type = str(spec.get("type") or "")
    normalized_profile = str(profile or "").strip().lower()
    if scenario_type != "app_sequence":
        result = {"ok": True, "mode": "skip_non_app_sequence"}
        _write_json(output_dir / "app_prepare.json", result)
        return result
    if normalized_profile == "quick":
        result = {"ok": True, "mode": "reuse_app_quick"}
        _write_json(output_dir / "app_prepare.json", result)
        return result
    result = {
        "mode": "restart_app_per_scenario",
        **_restart_app(python_bin, output_dir=output_dir),
    }
    _write_json(output_dir / "app_prepare.json", result)
    return result


def _run_app_sequence(spec: dict[str, Any], python_bin: Path) -> dict[str, Any]:
    output_dir = Path(spec["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = output_dir / "logs"
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    results: list[dict[str, Any]] = []
    failed_step = ""

    for step in list(spec.get("steps") or []):
        name = str(step["name"])
        command_items = [str(item) for item in list(step.get("command") or [])]
        if spec.get("id") == "editor_compact_macau" and name == "set_playhead":
            resolved_playhead, resolved_details = _resolve_editor_compact_playhead(python_bin, output_dir=output_dir)
            _write_json(logs_dir / "set_playhead_resolved.json", resolved_details)
            if resolved_playhead is not None:
                command_items = ["editor-set-playhead", str(resolved_playhead), "--center"]
        if spec.get("id") == "editor_compact_macau" and name in {"move_diamond", "merge_diamond"}:
            requested_side = "right"
            if "--side" in command_items:
                try:
                    requested_side = str(command_items[command_items.index("--side") + 1] or "right")
                except Exception:
                    requested_side = "right"
            resolved_command, resolved_details = _resolve_editor_compact_diamond_command(
                "editor-move-diamond" if name == "move_diamond" else "editor-merge-diamond",
                requested_side,
                python_bin,
                output_dir=output_dir,
            )
            _write_json(logs_dir / f"{name}_resolved.json", resolved_details)
            if resolved_command:
                command_items = resolved_command
        argv = [
            str(python_bin),
            str(ROOT / "tools" / "appctl.py"),
            "--timeout",
            str(step.get("timeout", 30.0)),
            *command_items,
        ]
        returncode, payload = _run_subprocess(
            argv,
            cwd=ROOT,
            stdout_path=logs_dir / f"{name}.stdout",
            stderr_path=logs_dir / f"{name}.stderr",
        )
        wait_path = str(step.get("wait_for_path", "") or "")
        if wait_path:
            _wait_for_file(wait_path, timeout_sec=max(4.0, float(step.get("timeout", 30.0))))
        step_result = {
            "name": name,
            "argv": argv[2:],
            "returncode": returncode,
            "ok": bool(payload.get("ok")),
            "message": str(payload.get("message", "") or ""),
            "error": str(payload.get("error", "") or ""),
            "data": dict(payload.get("data") or {}),
        }
        results.append(step_result)
        if not step_result["ok"] and not failed_step:
            failed_step = name
            break
        delay_sec = max(0.0, float(step.get("delay_sec", 0.0) or 0.0))
        if delay_sec > 0.0:
            time.sleep(delay_sec)

    scenario_result = {
        "id": spec["id"],
        "type": spec["type"],
        "description": spec.get("description", ""),
        "started_at": started_at,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "output_dir": str(output_dir),
        "ok": not bool(failed_step),
        "failed_step": failed_step,
        "steps": results,
    }
    (output_dir / "summary.json").write_text(json.dumps(scenario_result, ensure_ascii=False, indent=2), encoding="utf-8")
    return scenario_result


def _run_full_media(spec: dict[str, Any], python_bin: Path) -> dict[str, Any]:
    output_dir = Path(spec["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = output_dir / "logs"
    argv = [
        str(python_bin),
        str(ROOT / "tools" / "verify_full_media_pipeline.py"),
        "--media",
        str(spec["media"]),
        "--mode",
        str(spec["mode"]),
        "--output-dir",
        str(output_dir),
        "--duration-sec",
        str(spec["duration_sec"]),
    ]
    returncode, payload = _run_subprocess(
        argv,
        cwd=ROOT,
        stdout_path=logs_dir / "run.stdout",
        stderr_path=logs_dir / "run.stderr",
    )
    scenario_result = {
        "id": spec["id"],
        "type": spec["type"],
        "description": spec.get("description", ""),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "output_dir": str(output_dir),
        "ok": bool(payload.get("ok")) and returncode == 0,
        "failed_step": "" if bool(payload.get("ok")) and returncode == 0 else "full_media",
        "result": payload,
        "command": argv[2:],
    }
    (output_dir / "summary.json").write_text(json.dumps(scenario_result, ensure_ascii=False, indent=2), encoding="utf-8")
    return scenario_result


def _run_scenario(spec: dict[str, Any], python_bin: Path) -> dict[str, Any]:
    if str(spec.get("type")) == "full_media":
        return _run_full_media(spec, python_bin)
    return _run_app_sequence(spec, python_bin)


def _suite_markdown(summary: dict[str, Any]) -> str:
    failed = [item for item in list(summary.get("scenarios") or []) if not bool(item.get("ok"))]
    passed = [item for item in list(summary.get("scenarios") or []) if bool(item.get("ok"))]
    lines = [
        "# QA Suite Runner",
        "",
        f"- profile: `{summary.get('profile')}`",
        f"- started_at: `{summary.get('started_at')}`",
        f"- finished_at: `{summary.get('finished_at')}`",
        f"- output_dir: `{summary.get('output_dir')}`",
        f"- passed: `{summary.get('passed_count')}`",
        f"- failed: `{summary.get('failed_count')}`",
        "",
        "## Failed",
        "",
    ]
    if not failed:
        lines.append("- none")
    for item in failed:
        lines.append(f"- {item.get('id')}: failed_step={item.get('failed_step') or 'scenario'}")
    lines.extend(["", "## Passed", ""])
    if not passed:
        lines.append("- none")
    for item in passed:
        lines.append(f"- {item.get('id')}: ok")
    lines.append("")
    return "\n".join(lines)


def run_suite(profile: str, output_dir: Path, python_bin: Path) -> int:
    scenarios = build_scenarios(profile, output_dir)
    bootstrap = _ensure_app_ready(python_bin, output_dir=output_dir)
    manifest = {
        "profile": str(profile),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "output_dir": str(output_dir),
        "app_bootstrap": bootstrap,
        "app_sequence_policy": "reuse_app_quick" if str(profile).strip().lower() == "quick" else "restart_app_per_scenario",
        "scenario_ids": [str(item["id"]) for item in scenarios],
        "scenarios": [
            {
                "id": str(item["id"]),
                "type": str(item["type"]),
                "description": str(item.get("description", "") or ""),
                "output_dir": str(item["output_dir"]),
            }
            for item in scenarios
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "suite_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if not bool(bootstrap.get("ok")):
        summary = {
            "profile": str(profile),
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "output_dir": str(output_dir),
            "scenario_count": len(scenarios),
            "passed_count": 0,
            "failed_count": len(scenarios),
            "app_bootstrap": bootstrap,
            "scenarios": [],
        }
        (output_dir / "suite_result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / "suite_result.md").write_text(_suite_markdown(summary) + "\n", encoding="utf-8")
        print(json.dumps({"ok": False, "profile": profile, "output_dir": str(output_dir), "failed_count": len(scenarios), "error": "app_bootstrap_failed"}, ensure_ascii=False, indent=2))
        return 1

    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    results: list[dict[str, Any]] = []
    for spec in scenarios:
        prepare_result = _prepare_app_for_scenario(profile, spec, python_bin)
        if not bool(prepare_result.get("ok")):
            scenario_result = {
                "id": spec["id"],
                "type": spec["type"],
                "description": spec.get("description", ""),
                "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "output_dir": str(spec["output_dir"]),
                "ok": False,
                "failed_step": "app_prepare",
                "app_prepare": prepare_result,
                "steps": [],
            }
            _write_json(Path(spec["output_dir"]) / "summary.json", scenario_result)
            results.append(scenario_result)
            continue
        scenario_result = _run_scenario(spec, python_bin)
        scenario_result["app_prepare"] = prepare_result
        _write_json(Path(spec["output_dir"]) / "summary.json", scenario_result)
        results.append(scenario_result)
    failed_count = sum(1 for item in results if not bool(item.get("ok")))
    summary = {
        "profile": str(profile),
        "started_at": started_at,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "output_dir": str(output_dir),
        "scenario_count": len(results),
        "passed_count": len(results) - failed_count,
        "failed_count": failed_count,
        "app_bootstrap": bootstrap,
        "scenarios": results,
    }
    (output_dir / "suite_result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "suite_result.md").write_text(_suite_markdown(summary) + "\n", encoding="utf-8")
    print(json.dumps({"ok": failed_count == 0, "profile": profile, "output_dir": str(output_dir), "failed_count": failed_count}, ensure_ascii=False, indent=2))
    return 0 if failed_count == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one-command QA suites for AI Subtitle Studio.")
    parser.add_argument("profile", choices=["quick", "major", "full"], nargs="?", default="major")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--python-bin", default=str(DEFAULT_PYTHON))
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser() if args.output_dir else _default_output_dir(args.profile)
    python_bin = Path(args.python_bin).expanduser()
    return run_suite(args.profile, output_dir, python_bin)


if __name__ == "__main__":
    raise SystemExit(main())
