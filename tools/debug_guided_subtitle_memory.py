#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.automation.app_command_protocol import build_command_payload  # noqa: E402
from tools.automation_command_client import send_app_command_with_readiness_retry  # noqa: E402

LATEST_DIR = ROOT / "output" / "manual_verification" / "latest"
RUNTIME_MONITOR_FILE = ROOT / "output" / "runtime_monitor" / "latest.json"
MEMORY_MONITOR_FILE = ROOT / "output" / "memory_monitor" / "subtitle_generation_latest.json"
PROCESS_PATTERNS = ("whisperkit", "mlx", "ollama")
CRITICAL_REUSE_STOP_TEXT = "메모리 critical: STT persistent worker 재사용 중단"


def _readable_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_readable_json(payload) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _snapshot_file(src: Path, dst: Path) -> dict[str, Any] | None:
    if not src.exists():
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src, dst)
        return json.loads(dst.read_text(encoding="utf-8"))
    except Exception:
        return None


def _collect_processes() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "psutil_available": False,
        "matched_processes": [],
        "total_matched": 0,
        "total_rss_bytes": 0,
    }
    try:
        import psutil  # type: ignore
    except Exception:
        return payload
    payload["psutil_available"] = True
    rows: list[dict[str, Any]] = []
    total_rss = 0
    total_matched = 0
    for proc in psutil.process_iter(["pid", "name", "cmdline", "memory_info"]):
        try:
            info = proc.info or {}
            name = str(info.get("name") or "")
            cmd = " ".join(str(item) for item in (info.get("cmdline") or []))
            haystack = f"{name} {cmd}".lower()
            if not any(pattern in haystack for pattern in PROCESS_PATTERNS):
                continue
            rss = int(getattr(info.get("memory_info"), "rss", 0) or 0)
            total_matched += 1
            total_rss += rss
            rows.append(
                {
                    "pid": int(info.get("pid") or 0),
                    "name": name,
                    "cmdline": cmd,
                    "rss_bytes": rss,
                }
            )
        except Exception:
            continue
    payload["matched_processes"] = rows
    payload["total_matched"] = total_matched
    payload["total_rss_bytes"] = total_rss
    return payload


def _send_command(command: str, *, timeout_sec: float, **fields: Any) -> dict[str, Any]:
    payload = build_command_payload(command, **fields)
    return send_app_command_with_readiness_retry(payload, timeout_sec=timeout_sec)


def _status_payload(result: dict[str, Any] | None) -> dict[str, Any]:
    data = result if isinstance(result, dict) else {}
    if isinstance(data.get("data"), dict):
        return dict(data.get("data") or {})
    return dict(data)


def _safe_status_payload(timeout_sec: float) -> dict[str, Any]:
    try:
        return _status_payload(_send_command("guided-subtitle-status", timeout_sec=timeout_sec))
    except (OSError, TimeoutError):
        return {}


def status_is_processing(status_data: dict[str, Any]) -> bool:
    editor_state = str(status_data.get("editor_state", "") or "")
    if editor_state == "ST_PROC":
        return True
    if bool(status_data.get("backend_active", False)):
        return True
    if bool(status_data.get("auto_processing_active", False)):
        return True
    queue_runtime = dict(status_data.get("queue_runtime") or {})
    if bool(queue_runtime.get("all_done", False)):
        return False
    active_probe = str(queue_runtime.get("active_probe_text", "") or "")
    if active_probe:
        return True
    runtime_resource = dict(status_data.get("runtime_resource") or {})
    active_labels = [str(label or "").strip().lower() for label in list(runtime_resource.get("active_labels") or [])]
    if any(label in {"pipeline", "editor"} for label in active_labels):
        return True
    guided_state = dict(status_data.get("guided_snapshot_run") or {})
    return bool(guided_state.get("active", False))


def status_flag_summary(status_data: dict[str, Any]) -> dict[str, Any]:
    recent_logs = [str(line or "") for line in list(status_data.get("recent_logs") or [])]
    recent_stage_logs = [str(line or "") for line in list(status_data.get("recent_stage_logs") or [])]
    combined = recent_stage_logs + recent_logs
    saw_critical_reuse_stop = any(CRITICAL_REUSE_STOP_TEXT in line for line in combined)
    return {
        "saw_critical_reuse_stop": saw_critical_reuse_stop,
        "recent_stage_log_count": len(recent_stage_logs),
        "recent_log_count": len(recent_logs),
    }


def _has_completed_guided_snapshot(snapshot_dir: Path) -> bool:
    if not snapshot_dir.exists():
        return False
    for path in snapshot_dir.glob("*completed*.png"):
        if path.is_file():
            return True
    return False


def _wait_for_processing_start(*, timeout_sec: float, poll_sec: float, status_history_path: Path) -> dict[str, Any]:
    deadline = time.monotonic() + max(1.0, float(timeout_sec or 1.0))
    last_result: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            result = _send_command("guided-subtitle-status", timeout_sec=max(1.0, poll_sec * 2.0))
        except (OSError, TimeoutError) as exc:
            _append_jsonl(
                status_history_path,
                {
                    "captured_at": datetime.now().isoformat(timespec="seconds"),
                    "phase": "wait_processing_start",
                    "error": type(exc).__name__,
                    "message": str(exc),
                },
            )
        else:
            data = _status_payload(result)
            _append_jsonl(
                status_history_path,
                {
                    "captured_at": datetime.now().isoformat(timespec="seconds"),
                    "phase": "wait_processing_start",
                    "status": data,
                },
            )
            last_result = data
            if status_is_processing(data):
                return data
        time.sleep(max(0.1, float(poll_sec or 0.1)))
    raise TimeoutError("processing_start_timeout")


def _wait_for_idle_state(
    *,
    timeout_sec: float,
    poll_sec: float,
    status_history_path: Path,
    phase: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(1.0, float(timeout_sec or 1.0))
    last_result: dict[str, Any] = {}
    idle_started_at: float | None = None
    while time.monotonic() < deadline:
        try:
            result = _send_command("guided-subtitle-status", timeout_sec=max(1.0, poll_sec * 2.0))
        except (OSError, TimeoutError) as exc:
            _append_jsonl(
                status_history_path,
                {
                    "captured_at": datetime.now().isoformat(timespec="seconds"),
                    "phase": phase,
                    "error": type(exc).__name__,
                    "message": str(exc),
                },
            )
        else:
            data = _status_payload(result)
            _append_jsonl(
                status_history_path,
                {
                    "captured_at": datetime.now().isoformat(timespec="seconds"),
                    "phase": phase,
                    "status": data,
                },
            )
            last_result = data
            if status_is_processing(data):
                idle_started_at = None
            else:
                if idle_started_at is None:
                    idle_started_at = time.monotonic()
                elif (time.monotonic() - idle_started_at) >= max(0.5, float(poll_sec or 0.5)):
                    return data
        time.sleep(max(0.1, float(poll_sec or 0.1)))
    return last_result


def _wait_for_processing_done(
    *,
    timeout_sec: float,
    poll_sec: float,
    done_stable_sec: float,
    status_history_path: Path,
    guided_snapshot_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + max(1.0, float(timeout_sec or 1.0))
    idle_started_at: float | None = None
    last_data: dict[str, Any] = {}
    flags = {"saw_critical_reuse_stop": False, "completed_via_snapshot": False}
    while time.monotonic() < deadline:
        try:
            result = _send_command("guided-subtitle-status", timeout_sec=max(1.0, poll_sec * 2.0))
        except (OSError, TimeoutError) as exc:
            _append_jsonl(
                status_history_path,
                {
                    "captured_at": datetime.now().isoformat(timespec="seconds"),
                    "phase": "wait_processing_done",
                    "error": type(exc).__name__,
                    "message": str(exc),
                },
            )
        else:
            data = _status_payload(result)
            flag_data = status_flag_summary(data)
            flags["saw_critical_reuse_stop"] = bool(flags["saw_critical_reuse_stop"] or flag_data["saw_critical_reuse_stop"])
            _append_jsonl(
                status_history_path,
                {
                    "captured_at": datetime.now().isoformat(timespec="seconds"),
                    "phase": "wait_processing_done",
                    "status": data,
                    "flags": flag_data,
                },
            )
            last_data = data
            if status_is_processing(data):
                idle_started_at = None
            else:
                if idle_started_at is None:
                    idle_started_at = time.monotonic()
                elif (time.monotonic() - idle_started_at) >= max(0.5, float(done_stable_sec or 0.5)):
                    return last_data, flags
        if _has_completed_guided_snapshot(guided_snapshot_dir):
            flags["completed_via_snapshot"] = True
            return last_data, flags
        time.sleep(max(0.1, float(poll_sec or 0.1)))
    raise TimeoutError("processing_done_timeout")


def _run_once(
    media_path: Path,
    *,
    run_index: int,
    output_root: Path,
    timeout_sec: float,
    poll_sec: float,
    done_stable_sec: float,
    post_run_settle_sec: float,
) -> dict[str, Any]:
    run_dir = output_root / f"run_{run_index:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    status_history_path = run_dir / "guided_status_history.jsonl"
    before_status = _safe_status_payload(timeout_sec)
    if status_is_processing(before_status):
        before_status = _wait_for_idle_state(
            timeout_sec=max(20.0, timeout_sec * 3.0),
            poll_sec=poll_sec,
            status_history_path=status_history_path,
            phase="wait_pre_run_idle",
        )
    before_process = _collect_processes()
    before_runtime = _snapshot_file(RUNTIME_MONITOR_FILE, run_dir / "runtime_monitor_before.json")
    before_memory = _snapshot_file(MEMORY_MONITOR_FILE, run_dir / "subtitle_generation_monitor_before.json")
    guided_snapshot_dir = run_dir / "guided_snapshots"
    started_at = time.perf_counter()
    started_cmd: dict[str, Any]
    try:
        started_cmd = _send_command(
            "guided-subtitle-run",
            timeout_sec=max(20.0, float(timeout_sec or 0.0)),
            path=str(media_path),
            options={"snapshot_dir": str(guided_snapshot_dir)},
        )
    except (OSError, TimeoutError) as exc:
        # guided-subtitle-run은 앱이 파일을 열고 에디터를 준비하는 동안 ACK가 늦을 수 있다.
        # start 응답이 늦더라도 실제 processing이 올라오면 run은 계속 추적한다.
        started_cmd = {
            "ok": False,
            "accepted": False,
            "queued": False,
            "error": "start_command_timeout",
            "message": str(exc),
            "data": {},
        }
    started_data = _status_payload(started_cmd)
    if status_is_processing(started_data):
        started_processing = dict(started_data)
    else:
        started_processing = _wait_for_processing_start(
            timeout_sec=max(20.0, timeout_sec),
            poll_sec=poll_sec,
            status_history_path=status_history_path,
        )
    done_status, flags = _wait_for_processing_done(
        timeout_sec=max(120.0, timeout_sec * 6.0),
        poll_sec=poll_sec,
        done_stable_sec=done_stable_sec,
        status_history_path=status_history_path,
        guided_snapshot_dir=guided_snapshot_dir,
    )
    immediate_runtime = _snapshot_file(RUNTIME_MONITOR_FILE, run_dir / "runtime_monitor_after.json")
    immediate_memory = _snapshot_file(MEMORY_MONITOR_FILE, run_dir / "subtitle_generation_monitor_after.json")
    immediate_process = _collect_processes()
    if post_run_settle_sec > 0:
        time.sleep(post_run_settle_sec)
    settle_status = _safe_status_payload(timeout_sec)
    settle_runtime = _snapshot_file(RUNTIME_MONITOR_FILE, run_dir / "runtime_monitor_after_settle.json")
    settle_memory = _snapshot_file(MEMORY_MONITOR_FILE, run_dir / "subtitle_generation_monitor_after_settle.json")
    settle_process = _collect_processes()
    payload = {
        "run_index": run_index,
        "media_path": str(media_path),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "total_elapsed_sec": round(time.perf_counter() - started_at, 3),
        "post_run_settle_sec": post_run_settle_sec,
        "start_command": started_cmd,
        "status_before": before_status,
        "status_started": started_data,
        "status_processing_started": started_processing,
        "status_done": done_status,
        "status_after_settle": settle_status,
        "runtime_monitor_before": before_runtime,
        "runtime_monitor_after": immediate_runtime,
        "runtime_monitor_after_settle": settle_runtime,
        "subtitle_generation_monitor_before": before_memory,
        "subtitle_generation_monitor_after": immediate_memory,
        "subtitle_generation_monitor_after_settle": settle_memory,
        "process_snapshot_before": before_process,
        "process_snapshot_after": immediate_process,
        "process_snapshot_after_settle": settle_process,
        "flags": flags,
        "summary": {
            "saw_critical_reuse_stop": bool(flags["saw_critical_reuse_stop"]),
            "completed_via_snapshot": bool(flags.get("completed_via_snapshot")),
            "runtime_pressure_after": str((immediate_runtime or {}).get("pressure_stage", "") or ""),
            "runtime_pressure_after_settle": str((settle_runtime or {}).get("pressure_stage", "") or ""),
            "subtitle_stage_after": str((immediate_memory or {}).get("subtitle_generation_stage", "") or ""),
            "subtitle_stage_after_settle": str((settle_memory or {}).get("subtitle_generation_stage", "") or ""),
            "process_total_after": int(immediate_process.get("total_matched", 0) or 0),
            "process_total_after_settle": int(settle_process.get("total_matched", 0) or 0),
            "process_rss_after_bytes": int(immediate_process.get("total_rss_bytes", 0) or 0),
            "process_rss_after_settle_bytes": int(settle_process.get("total_rss_bytes", 0) or 0),
            "memory_pressure_after": str((immediate_memory or {}).get("pressure_stage", "") or ""),
            "memory_pressure_after_settle": str((settle_memory or {}).get("pressure_stage", "") or ""),
        },
    }
    _write_json(run_dir / "guided_memory_debug.json", payload)
    return payload


def _emit_summary(output_root: Path, runs: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    critical_count = 0
    for item in runs:
        summary = dict(item.get("summary") or {})
        if summary.get("saw_critical_reuse_stop"):
            critical_count += 1
        rows.append(
            {
                "run_index": item.get("run_index"),
                "elapsed_sec": item.get("total_elapsed_sec"),
                "saw_critical_reuse_stop": bool(summary.get("saw_critical_reuse_stop")),
                "completed_via_snapshot": bool(summary.get("completed_via_snapshot")),
                "runtime_pressure_after": summary.get("runtime_pressure_after"),
                "memory_pressure_after": summary.get("memory_pressure_after"),
                "subtitle_stage_after": summary.get("subtitle_stage_after"),
                "process_total_after": summary.get("process_total_after"),
                "process_total_after_settle": summary.get("process_total_after_settle"),
                "process_rss_after_bytes": summary.get("process_rss_after_bytes"),
                "process_rss_after_settle_bytes": summary.get("process_rss_after_settle_bytes"),
            }
        )
    elapsed = [float(row["elapsed_sec"]) for row in rows if isinstance(row.get("elapsed_sec"), (int, float))]
    summary = {
        "schema": "ai_subtitle_studio.guided_memory_debug.v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "run_count": len(runs),
        "critical_reuse_stop_runs": critical_count,
        "elapsed_sec": {
            "list": elapsed,
            "avg": round(sum(elapsed) / len(elapsed), 3) if elapsed else None,
            "min": min(elapsed) if elapsed else None,
            "max": max(elapsed) if elapsed else None,
        },
        "rows": rows,
    }
    _write_json(output_root / "repeat_summary.json", summary)
    csv_lines = [
        "run_index,elapsed_sec,saw_critical_reuse_stop,completed_via_snapshot,runtime_pressure_after,memory_pressure_after,subtitle_stage_after,process_total_after,process_total_after_settle,process_rss_after_bytes,process_rss_after_settle_bytes",
    ]
    for row in rows:
        csv_lines.append(
            ",".join(
                map(
                    str,
                    [
                        row.get("run_index"),
                        row.get("elapsed_sec"),
                        row.get("saw_critical_reuse_stop"),
                        row.get("completed_via_snapshot"),
                        row.get("runtime_pressure_after"),
                        row.get("memory_pressure_after"),
                        row.get("subtitle_stage_after"),
                        row.get("process_total_after"),
                        row.get("process_total_after_settle"),
                        row.get("process_rss_after_bytes"),
                        row.get("process_rss_after_settle_bytes"),
                    ],
                )
            )
        )
    (output_root / "repeat_summary.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Repeat guided subtitle runs in the real app and capture memory/process artifacts.")
    parser.add_argument("--media", required=True)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--output-dir", default=str(LATEST_DIR))
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--poll-sec", type=float, default=1.0)
    parser.add_argument("--done-stable-sec", type=float, default=2.0)
    parser.add_argument("--post-run-settle-sec", type=float, default=2.0)
    args = parser.parse_args()

    media_path = Path(str(args.media)).expanduser()
    if not media_path.exists():
        raise SystemExit(f"media not found: {media_path}")
    output_root = Path(str(args.output_dir)).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)
    runs = []
    for run_index in range(1, max(1, int(args.repeat or 1)) + 1):
        payload = _run_once(
            media_path,
            run_index=run_index,
            output_root=output_root,
            timeout_sec=float(args.timeout or 8.0),
            poll_sec=float(args.poll_sec or 1.0),
            done_stable_sec=float(args.done_stable_sec or 2.0),
            post_run_settle_sec=float(args.post_run_settle_sec or 2.0),
        )
        runs.append(payload)
    summary = _emit_summary(output_root, runs)
    print(json.dumps({"ok": True, **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
