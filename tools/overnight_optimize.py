#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.media_info import probe_media  # noqa: E402
from core.performance import current_resource_snapshot  # noqa: E402
from core.runtime.memory_manager import process_rss_bytes, runtime_disk_cache_usage  # noqa: E402

LATEST_DIR = ROOT / "output" / "manual_verification" / "latest"
STATE_PATH = ROOT / ".codex_work" / "overnight_state.md"
MACAU_DIR = Path("/Users/u_mo_c/Downloads/마카오테스트")
TINY_PING = Path("/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.MP4")
X5_MEDIA = ROOT / "test video" / "X5_시승기_후반.MP4"
X5_REFERENCE = ROOT / "test video" / "X5_시승기_후반.srt"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_state(line: str) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = STATE_PATH.read_text(encoding="utf-8") if STATE_PATH.exists() else "# Overnight Optimization State\n"
    STATE_PATH.write_text(existing.rstrip() + f"\n- {line}\n", encoding="utf-8")


def _media_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    started = time.perf_counter()
    info = probe_media(str(path))
    return {
        "path": str(path),
        "exists": True,
        "probe_elapsed_sec": round(time.perf_counter() - started, 3),
        "media": dict(info or {}),
    }


def _first_media_in(folder: Path) -> Path | None:
    if not folder.exists():
        return None
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".m4v", ".lrf"}:
            return path
    return None


def capture_baseline(*, include_benchmark: bool = False, duration_sec: float = 60.0) -> dict[str, Any]:
    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    macau = _first_media_in(MACAU_DIR)
    payload: dict[str, Any] = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "process_rss_bytes": process_rss_bytes(),
        "resource": current_resource_snapshot({}),
        "disk_cache": runtime_disk_cache_usage(),
        "media": {
            "macau": _media_summary(macau) if macau is not None else {"path": str(MACAU_DIR), "exists": False},
            "x5": _media_summary(X5_MEDIA),
            "tinyping": _media_summary(TINY_PING),
        },
        "benchmark": {},
    }
    if include_benchmark and X5_MEDIA.exists() and X5_REFERENCE.exists():
        log_path = LATEST_DIR / "baseline_x5_benchmark.log"
        cmd = [
            sys.executable,
            "tools/benchmark_subtitle_pipeline_variants.py",
            "--suite",
            "modes",
            "--media",
            str(X5_MEDIA),
            "--reference-srt",
            str(X5_REFERENCE),
            "--duration-sec",
            str(max(10.0, float(duration_sec or 60.0))),
            "--variants",
            "mode_fast",
            "mode_auto",
            "mode_high",
        ]
        started = time.perf_counter()
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
        log_path.write_text((proc.stdout or "") + ("\nSTDERR:\n" + proc.stderr if proc.stderr else ""), encoding="utf-8")
        payload["benchmark"] = {
            "command": cmd,
            "elapsed_sec": round(time.perf_counter() - started, 3),
            "returncode": int(proc.returncode),
            "log_path": str(log_path),
        }
    _write_json(LATEST_DIR / "baseline_snapshot.json", payload)
    _append_state("completed_batch: 1 baseline_snapshot.json")
    return payload


def run_checks() -> dict[str, Any]:
    commands = [
        ["venv/bin/python", "-m", "pytest", "-q", "tests/test_pipeline_status.py", "tests/test_app_command_bridge.py"],
        ["venv/bin/python", "-m", "compileall", "-q", "main.py", "core", "ui", "tests"],
        ["git", "diff", "--check", "--", "."],
    ]
    results: list[dict[str, Any]] = []
    for index, cmd in enumerate(commands, start=1):
        log_path = LATEST_DIR / f"overnight_check_{index}.log"
        started = time.perf_counter()
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
        log_path.write_text((proc.stdout or "") + ("\nSTDERR:\n" + proc.stderr if proc.stderr else ""), encoding="utf-8")
        results.append(
            {
                "command": cmd,
                "returncode": int(proc.returncode),
                "elapsed_sec": round(time.perf_counter() - started, 3),
                "log_path": str(log_path),
            }
        )
    payload = {"created_at": time.strftime("%Y-%m-%d %H:%M:%S"), "results": results}
    _write_json(LATEST_DIR / "overnight_checks.json", payload)
    _append_state("verification: overnight_checks.json")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run compact overnight optimization baselines and checks.")
    sub = parser.add_subparsers(dest="command", required=True)
    baseline = sub.add_parser("baseline")
    baseline.add_argument("--include-benchmark", action="store_true")
    baseline.add_argument("--duration-sec", type=float, default=60.0)
    sub.add_parser("checks")
    args = parser.parse_args()
    if args.command == "baseline":
        payload = capture_baseline(include_benchmark=bool(args.include_benchmark), duration_sec=float(args.duration_sec))
    else:
        payload = run_checks()
    print(json.dumps({"ok": True, "artifact": str(LATEST_DIR), "keys": sorted(payload.keys())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
