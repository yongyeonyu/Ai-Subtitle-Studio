#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from core.native_json import dumps_json_bytes
from core.runtime.temp_workspace import ensure_temp_workspace, package_workspace_dir, trace_workspace_dir, workspace_usage


def _stable_jsonl_bytes(src: Path) -> bytes:
    data = src.read_bytes()
    if not data or data.endswith(b"\n"):
        return data
    end = data.rfind(b"\n")
    return data[: end + 1] if end >= 0 else b""


def _write_bytes_atomic(dst: Path, data: bytes) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, dst)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _copy_file(src: Path, dst: Path, *, jsonl: bool = False) -> bool:
    try:
        if not src.exists() or not src.is_file():
            return False
        data = _stable_jsonl_bytes(src) if jsonl else src.read_bytes()
        _write_bytes_atomic(dst, data)
        return True
    except OSError:
        return False


def collect_trace_package(
    *,
    root: str | Path | None = None,
    run_id: str = "",
    package_name: str = "",
) -> dict[str, Any]:
    ensure_temp_workspace(root)
    trace_root = trace_workspace_dir(root)
    packages_root = package_workspace_dir(root)
    name = package_name.strip() or f"AISSTrace-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    package_dir = packages_root / name
    package_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    latest = trace_root / "latest.jsonl"
    if _copy_file(latest, package_dir / "latest.jsonl", jsonl=True):
        copied.append("latest.jsonl")

    runs_dir = trace_root / "runs"
    selected_runs: list[Path] = []
    if run_id:
        selected_runs = [runs_dir / run_id]
    elif runs_dir.exists():
        selected_runs = [path for path in sorted(runs_dir.iterdir()) if path.is_dir()]

    for run_dir in selected_runs:
        if not run_dir.exists() or not run_dir.is_dir():
            continue
        target = package_dir / "runs" / run_dir.name
        for filename in ("manifest.json", "events.jsonl"):
            if _copy_file(run_dir / filename, target / filename, jsonl=filename.endswith(".jsonl")):
                copied.append(str(Path("runs") / run_dir.name / filename))

    manifest = {
        "package": name,
        "package_dir": str(package_dir),
        "run_id": run_id,
        "copied": copied,
        "usage": workspace_usage(root),
    }
    (package_dir / "package_manifest.json").write_bytes(
        dumps_json_bytes(manifest, indent=2, sort_keys=True, append_newline=True)
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect AI Subtitle Studio trace logs into a package directory.")
    parser.add_argument("--root", default="", help="Temporary workspace root override.")
    parser.add_argument("--run-id", default="", help="Optional trace run id to package.")
    parser.add_argument("--package-name", default="", help="Optional package directory name.")
    args = parser.parse_args()
    manifest = collect_trace_package(
        root=args.root or None,
        run_id=args.run_id,
        package_name=args.package_name,
    )
    print(dumps_json_bytes(manifest, indent=2, sort_keys=True).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
