#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.qa_suite_runner import (  # noqa: E402
    DEFAULT_PYTHON,
    LATEST_DIR,
    _macau_editor_project_for_suite,
    _resolve_editor_compact_diamond_command,
    _resolve_editor_compact_playhead,
    _restart_app,
    _run_subprocess,
    _wait_for_file,
    _write_json,
)


def _default_output_dir() -> Path:
    return LATEST_DIR / f"editor_responsiveness_{time.strftime('%Y%m%d_%H%M%S')}"


def _resolve_output_dir(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


def _step(name: str, *command: str, timeout: float = 30.0, delay_sec: float = 0.0, wait_for_path: str = "") -> dict[str, Any]:
    return {
        "name": str(name),
        "command": [str(item) for item in command],
        "timeout": float(timeout),
        "delay_sec": float(delay_sec),
        "wait_for_path": str(wait_for_path or ""),
    }


def build_benchmark_steps(output_dir: Path, project_path: Path) -> list[dict[str, Any]]:
    snapshots_dir = output_dir / "snapshots"
    return [
        _step("open_project", "open-project", str(project_path), timeout=60.0, delay_sec=2.0),
        _step("capture_before", "capture-snapshot", str(snapshots_dir / "before.png"), wait_for_path=str(snapshots_dir / "before.png")),
        _step("set_playhead", "editor-set-playhead", "1.5", "--center", "--no-sync-video", delay_sec=0.2),
        _step("begin_smart_split", "editor-begin-smart-split", "--at-playhead", delay_sec=0.2),
        _step("set_inline_cursor", "editor-set-inline-cursor", "2", delay_sec=0.1),
        _step("commit_inline_edit", "editor-commit-inline-edit", delay_sec=0.2),
        _step("timeline_zoom_in", "editor-timeline-view", "zoom-in", delay_sec=0.1),
        _step("timeline_zoom_out", "editor-timeline-view", "zoom-out", delay_sec=0.1),
        _step("timeline_fit", "editor-timeline-view", "fit", delay_sec=0.1),
        _step("timeline_time_window", "editor-timeline-view", "time-window", delay_sec=0.1),
        _step("timeline_max", "editor-timeline-view", "max", delay_sec=0.1),
        _step("zoom_max", "editor-zoom-max", delay_sec=0.1),
        _step("global_menu_status", "global-menu-status", delay_sec=0.1),
        _step("global_menu_save", "global-menu-action", "save", timeout=60.0, delay_sec=0.2),
        _step("playback_play", "editor-playback", "play", delay_sec=0.2),
        _step("playback_pause", "editor-playback", "pause", delay_sec=0.2),
        _step("move_segment_left", "editor-move-segment-left", "--line", "1", delay_sec=0.1),
        _step("move_segment_right", "editor-move-segment-right", "--line", "1", delay_sec=0.1),
        _step("move_diamond", "editor-move-diamond", "--line", "1", "--side", "right", delay_sec=0.2),
        _step("merge_diamond", "editor-merge-diamond", "--line", "1", "--side", "right", delay_sec=0.4),
        _step("status_probe", "status", timeout=10.0),
        _step("guided_status_probe", "guided-subtitle-status", timeout=10.0),
        _step("capture_after", "capture-snapshot", str(snapshots_dir / "after.png"), wait_for_path=str(snapshots_dir / "after.png")),
    ]


def _file_state(path_text: str) -> dict[str, Any]:
    path = Path(str(path_text or ""))
    exists = path.is_file()
    size = path.stat().st_size if exists else 0
    return {
        "path": str(path),
        "path_exists": bool(exists),
        "path_size": int(size),
    }


def _timed_appctl(
    python_bin: Path,
    command_items: list[str],
    *,
    timeout: float,
    stdout_path: Path,
    stderr_path: Path,
) -> tuple[int, dict[str, Any], float]:
    argv = [
        str(python_bin),
        str(ROOT / "tools" / "appctl.py"),
        "--timeout",
        str(float(timeout)),
        *[str(item) for item in command_items],
    ]
    started = time.monotonic()
    returncode, payload = _run_subprocess(argv, cwd=ROOT, stdout_path=stdout_path, stderr_path=stderr_path)
    return returncode, payload, round(time.monotonic() - started, 6)


def _status_probe(python_bin: Path, logs_dir: Path, *, step_name: str, index: int) -> dict[str, Any]:
    returncode, payload, elapsed = _timed_appctl(
        python_bin,
        ["status"],
        timeout=2.0,
        stdout_path=logs_dir / f"{index:02d}_{step_name}_post_status.stdout",
        stderr_path=logs_dir / f"{index:02d}_{step_name}_post_status.stderr",
    )
    data = dict(payload.get("data") or {})
    return {
        "returncode": returncode,
        "ok": bool(payload.get("ok")),
        "elapsed_sec": elapsed,
        "status_handler_timeout": bool(data.get("status_handler_timeout", False)),
        "status_response_cached": bool(data.get("status_response_cached", False)),
        "status_snapshot_fallback": bool(data.get("status_snapshot_fallback", False)),
        "status_response_truncated": bool(data.get("status_response_truncated", False)),
        "editor_segment_count": int(((data.get("editor_runtime") or {}).get("segment_count") or data.get("subtitle_count") or 0) or 0),
    }


def _resolve_dynamic_command(
    step: dict[str, Any],
    command_items: list[str],
    python_bin: Path,
    run_dir: Path,
) -> list[str]:
    name = str(step.get("name") or "")
    logs_dir = run_dir / "logs"
    if name == "set_playhead":
        resolved_playhead, details = _resolve_editor_compact_playhead(python_bin, output_dir=run_dir)
        _write_json(logs_dir / "set_playhead_resolved.json", details)
        if resolved_playhead is not None:
            return ["editor-set-playhead", str(resolved_playhead), "--center", "--no-sync-video"]
    if name in {"move_diamond", "merge_diamond"}:
        requested_side = "right"
        if "--side" in command_items:
            try:
                requested_side = str(command_items[command_items.index("--side") + 1] or "right")
            except Exception:
                requested_side = "right"
        resolved_command, details = _resolve_editor_compact_diamond_command(
            "editor-move-diamond" if name == "move_diamond" else "editor-merge-diamond",
            requested_side,
            python_bin,
            output_dir=run_dir,
        )
        _write_json(logs_dir / f"{name}_resolved.json", details)
        if resolved_command:
            return [str(item) for item in resolved_command]
    return command_items


def run_benchmark_once(
    *,
    run_index: int,
    python_bin: Path,
    output_dir: Path,
    project_path: Path,
    restart_app: bool = True,
) -> dict[str, Any]:
    run_dir = output_dir / f"run_{run_index:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    restart_result = _restart_app(python_bin, output_dir=run_dir) if restart_app else {"ok": True, "mode": "reuse_app"}
    steps = build_benchmark_steps(run_dir, project_path)
    results: list[dict[str, Any]] = []
    failed_step = ""
    run_started = time.monotonic()

    for index, step in enumerate(steps, start=1):
        name = str(step["name"])
        command_items = _resolve_dynamic_command(step, list(step.get("command") or []), python_bin, run_dir)
        timeout = float(step.get("timeout", 30.0) or 30.0)
        returncode, payload, elapsed = _timed_appctl(
            python_bin,
            command_items,
            timeout=timeout,
            stdout_path=logs_dir / f"{index:02d}_{name}.stdout",
            stderr_path=logs_dir / f"{index:02d}_{name}.stderr",
        )
        wait_path = str(step.get("wait_for_path", "") or "")
        artifact = _file_state(wait_path) if wait_path else {}
        if wait_path:
            _wait_for_file(wait_path, timeout_sec=max(4.0, timeout))
            artifact = _file_state(wait_path)
        status = _status_probe(python_bin, logs_dir, step_name=name, index=index)
        result = {
            "run_index": int(run_index),
            "step_index": int(index),
            "name": name,
            "command": command_items,
            "returncode": int(returncode),
            "ok": bool(payload.get("ok")) and int(returncode) == 0,
            "message": str(payload.get("message", "") or ""),
            "error": str(payload.get("error", "") or ""),
            "command_elapsed_sec": float(elapsed),
            "status": status,
            "artifact": artifact,
        }
        if wait_path and (not artifact.get("path_exists") or int(artifact.get("path_size", 0) or 0) <= 0):
            result["ok"] = False
            result["error"] = result["error"] or "artifact_missing"
        results.append(result)
        if not result["ok"] and not failed_step:
            failed_step = name
            break
        delay_sec = max(0.0, float(step.get("delay_sec", 0.0) or 0.0))
        if delay_sec > 0:
            time.sleep(delay_sec)

    run_result = {
        "run_index": int(run_index),
        "ok": not bool(failed_step) and bool(restart_result.get("ok")),
        "failed_step": failed_step,
        "restart": restart_result,
        "total_elapsed_sec": round(time.monotonic() - run_started, 6),
        "steps": results,
    }
    _write_json(run_dir / "run_result.json", run_result)
    return run_result


def _percentile(values: list[float], percentile: float) -> float | None:
    samples = sorted(float(value) for value in values if value is not None)
    if not samples:
        return None
    if len(samples) == 1:
        return round(samples[0], 6)
    rank = (len(samples) - 1) * max(0.0, min(100.0, float(percentile))) / 100.0
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return round(samples[int(rank)], 6)
    weight = rank - lower
    value = samples[lower] * (1 - weight) + samples[upper] * weight
    return round(value, 6)


def _threshold_for_step(name: str) -> dict[str, float] | None:
    if name in {"status_probe", "guided_status_probe"}:
        return {"p95": 0.15, "max": 0.30}
    if name.startswith("timeline_") or name == "zoom_max":
        return {"p95": 0.20, "max": 0.35}
    if name == "global_menu_status":
        return {"p95": 0.15, "max": 0.30}
    return None


def summarize_results(runs: list[dict[str, Any]]) -> dict[str, Any]:
    by_step: dict[str, list[dict[str, Any]]] = {}
    slow_steps: list[dict[str, Any]] = []
    for run in runs:
        for step in list(run.get("steps") or []):
            by_step.setdefault(str(step.get("name") or ""), []).append(dict(step))
            slow_steps.append(
                {
                    "run_index": int(step.get("run_index", run.get("run_index", 0)) or 0),
                    "name": str(step.get("name") or ""),
                    "command_elapsed_sec": float(step.get("command_elapsed_sec", 0.0) or 0.0),
                    "ok": bool(step.get("ok")),
                    "error": str(step.get("error", "") or ""),
                }
            )
    step_summary: dict[str, dict[str, Any]] = {}
    threshold_failures: list[dict[str, Any]] = []
    for name, steps in by_step.items():
        elapsed = [float(step.get("command_elapsed_sec", 0.0) or 0.0) for step in steps]
        item = {
            "count": len(steps),
            "ok_count": sum(1 for step in steps if bool(step.get("ok"))),
            "fail_count": sum(1 for step in steps if not bool(step.get("ok"))),
            "p50_sec": _percentile(elapsed, 50),
            "p95_sec": _percentile(elapsed, 95),
            "max_sec": round(max(elapsed), 6) if elapsed else None,
        }
        threshold = _threshold_for_step(name)
        if threshold is not None:
            item["threshold"] = threshold
            p95 = float(item["p95_sec"] or 0.0)
            max_value = float(item["max_sec"] or 0.0)
            if p95 > threshold["p95"] or max_value > threshold["max"]:
                threshold_failures.append(
                    {
                        "name": name,
                        "p95_sec": p95,
                        "max_sec": max_value,
                        "threshold": threshold,
                    }
                )
        step_summary[name] = item
    slow_steps.sort(key=lambda item: float(item["command_elapsed_sec"]), reverse=True)
    failed_runs = [run for run in runs if not bool(run.get("ok"))]
    return {
        "schema": "ai_subtitle_studio.editor_responsiveness_benchmark.v1",
        "run_count": len(runs),
        "ok": not failed_runs and not threshold_failures,
        "failed_run_count": len(failed_runs),
        "threshold_failure_count": len(threshold_failures),
        "threshold_failures": threshold_failures,
        "run_elapsed_sec": {
            "p50": _percentile([float(run.get("total_elapsed_sec", 0.0) or 0.0) for run in runs], 50),
            "p95": _percentile([float(run.get("total_elapsed_sec", 0.0) or 0.0) for run in runs], 95),
            "max": round(max([float(run.get("total_elapsed_sec", 0.0) or 0.0) for run in runs] or [0.0]), 6),
        },
        "steps": step_summary,
        "slow_steps": slow_steps[:10],
    }


def render_markdown(summary: dict[str, Any], output_dir: Path) -> str:
    lines = [
        "# Editor Responsiveness Benchmark",
        "",
        f"- status: `{'passed' if summary.get('ok') else 'blocked'}`",
        f"- run_count: `{summary.get('run_count')}`",
        f"- failed_run_count: `{summary.get('failed_run_count')}`",
        f"- threshold_failure_count: `{summary.get('threshold_failure_count')}`",
        f"- output_dir: `{output_dir}`",
        "",
        "## Step Summary",
        "",
        "| Step | Count | OK | p50 | p95 | max | Threshold |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, item in dict(summary.get("steps") or {}).items():
        threshold = item.get("threshold") or {}
        threshold_text = ""
        if threshold:
            threshold_text = f"p95<={threshold.get('p95')} max<={threshold.get('max')}"
        lines.append(
            "| {name} | {count} | {ok_count} | {p50} | {p95} | {max_value} | {threshold} |".format(
                name=name,
                count=item.get("count"),
                ok_count=item.get("ok_count"),
                p50=item.get("p50_sec"),
                p95=item.get("p95_sec"),
                max_value=item.get("max_sec"),
                threshold=threshold_text,
            )
        )
    lines.extend(["", "## Slowest Steps", ""])
    for item in list(summary.get("slow_steps") or []):
        lines.append(
            f"- run `{item.get('run_index')}` / `{item.get('name')}`: `{item.get('command_elapsed_sec')}`s ok=`{item.get('ok')}` error=`{item.get('error')}`"
        )
    if summary.get("threshold_failures"):
        lines.extend(["", "## Threshold Failures", ""])
        for item in list(summary.get("threshold_failures") or []):
            lines.append(f"- `{item.get('name')}` p95=`{item.get('p95_sec')}` max=`{item.get('max_sec')}` threshold=`{item.get('threshold')}`")
    return "\n".join(lines) + "\n"


def run_benchmark(*, runs: int, output_dir: Path, python_bin: Path, restart_each_run: bool) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    project_path = _macau_editor_project_for_suite(output_dir)
    metadata = {
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "runs": int(runs),
        "project_path": str(project_path),
        "python_bin": str(python_bin),
        "restart_each_run": bool(restart_each_run),
        "qa_use_source": str(os.environ.get("AI_SUBTITLE_STUDIO_QA_USE_SOURCE", "") or ""),
    }
    _write_json(output_dir / "metadata.json", metadata)
    run_results = []
    for run_index in range(1, max(1, int(runs or 1)) + 1):
        run_results.append(
            run_benchmark_once(
                run_index=run_index,
                python_bin=python_bin,
                output_dir=output_dir,
                project_path=project_path,
                restart_app=bool(restart_each_run or run_index == 1),
            )
        )
    summary = summarize_results(run_results)
    payload = {
        **metadata,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ok": bool(summary.get("ok")),
        "summary": summary,
        "runs": run_results,
    }
    _write_json(output_dir / "benchmark_results.json", payload)
    _write_json(output_dir / "slow_steps.json", {"slow_steps": summary.get("slow_steps", [])})
    (output_dir / "summary.md").write_text(render_markdown(summary, output_dir), encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark AI Subtitle Studio editor-mode responsiveness.")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--output-dir", default=str(_default_output_dir()))
    parser.add_argument("--python-bin", default=str(DEFAULT_PYTHON))
    parser.add_argument("--reuse-app", action="store_true", help="Restart only for the first run.")
    args = parser.parse_args(argv)

    payload = run_benchmark(
        runs=max(1, int(args.runs or 1)),
        output_dir=_resolve_output_dir(args.output_dir),
        python_bin=Path(args.python_bin).expanduser(),
        restart_each_run=not bool(args.reuse_app),
    )
    print(json.dumps({"ok": bool(payload.get("ok")), "output_dir": str(_resolve_output_dir(args.output_dir))}, ensure_ascii=False, indent=2))
    return 0 if bool(payload.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
