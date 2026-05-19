#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATHS = ("core", "ui", "tools", "native/macos/AIStudioNative/Sources")
EXCLUDED_PARTS = {"venv", "build", "dist", "output", "projects", "__pycache__", ".build"}
FILE_ALLOWLIST = {
    "core/audio/media_processor.py",
    "core/audio/media_processor_audio.py",
    "core/audio/media_processor_transcribe.py",
    "core/engine/subtitle_engine.py",
    "core/pipeline/single_pipeline.py",
    "core/project/project_manager.py",
    "ui/editor/video_player_widget.py",
    "ui/home_sidebar.py",
    "ui/timeline/timeline_canvas.py",
    "ui/timeline/timeline_paint.py",
}
FUNCTION_ALLOWLIST = {
    "core/audio/media_processor.py:extract_audio",
    "core/audio/media_processor_transcribe.py:transcribe",
    "core/runtime/multi_process.py:apply_apple_m_subtitle_pipeline_plan",
    "core/pipeline/single_pipeline.py:_process_one",
    "core/project/project_manager.py:save_project",
    "ui/main/app_command_bridge.py:execute_app_command",
    "ui/timeline/timeline_paint.py:paintEvent",
}
SILENT_EXCEPTION_ALLOWLIST = {
    "core/media_info.py",
    "core/runtime/memory_manager.py",
    "ui/editor/video_player_widget.py",
    "ui/main/app_command_bridge.py",
}


def _is_source_relpath(path: str) -> bool:
    suffix = Path(path).suffix
    if suffix not in {".py", ".swift", ".cpp", ".h", ".hpp", ".qml"}:
        return False
    parts = set(Path(path).parts)
    return not bool(parts & EXCLUDED_PARTS)


def _iter_source_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        base = (ROOT / raw).resolve()
        if not base.exists():
            continue
        candidates = [base] if base.is_file() else list(base.rglob("*"))
        for path in candidates:
            if path.suffix not in {".py", ".swift", ".cpp", ".h", ".hpp", ".qml"}:
                continue
            rel_parts = set(path.relative_to(ROOT).parts)
            if rel_parts & EXCLUDED_PARTS:
                continue
            files.append(path)
    return sorted(files)


def _changed_source_paths() -> list[str]:
    paths: list[str] = []
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--"],
            cwd=str(ROOT),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return list(DEFAULT_PATHS)
    prefixes = tuple(f"{path}/" for path in DEFAULT_PATHS)
    paths.extend(
        line.strip()
        for line in (proc.stdout or "").splitlines()
        if line.strip()
        and (line.strip().startswith(prefixes) or line.strip() in DEFAULT_PATHS)
        and _is_source_relpath(line.strip())
    )
    try:
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "--", *DEFAULT_PATHS],
            cwd=str(ROOT),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        paths.extend(
            line.strip()
            for line in (untracked.stdout or "").splitlines()
            if line.strip() and _is_source_relpath(line.strip())
        )
    except OSError:
        pass
    return paths or []


_HEAD_TEXT_CACHE: dict[str, str | None] = {}
_HEAD_FUNCTION_LENGTH_CACHE: dict[str, dict[str, int]] = {}
_CHANGED_LINE_CACHE: dict[str, set[int]] = {}


def _head_text(rel: str) -> str | None:
    if rel in _HEAD_TEXT_CACHE:
        return _HEAD_TEXT_CACHE[rel]
    try:
        proc = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=str(ROOT),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except OSError:
        _HEAD_TEXT_CACHE[rel] = None
        return None
    if proc.returncode != 0:
        _HEAD_TEXT_CACHE[rel] = None
        return None
    _HEAD_TEXT_CACHE[rel] = proc.stdout or ""
    return _HEAD_TEXT_CACHE[rel]


def _head_line_count(rel: str) -> int:
    text = _head_text(rel)
    if text is None:
        return 0
    return len(text.splitlines())


def _head_python_function_lengths(rel: str) -> dict[str, int]:
    if rel in _HEAD_FUNCTION_LENGTH_CACHE:
        return _HEAD_FUNCTION_LENGTH_CACHE[rel]
    text = _head_text(rel)
    if text is None:
        _HEAD_FUNCTION_LENGTH_CACHE[rel] = {}
        return {}
    try:
        tree = ast.parse(text)
    except SyntaxError:
        _HEAD_FUNCTION_LENGTH_CACHE[rel] = {}
        return {}
    out: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end_lineno = int(getattr(node, "end_lineno", node.lineno) or node.lineno)
        out[node.name] = max(1, end_lineno - int(node.lineno) + 1)
    _HEAD_FUNCTION_LENGTH_CACHE[rel] = out
    return out


def _changed_lines(rel: str) -> set[int]:
    if rel in _CHANGED_LINE_CACHE:
        return _CHANGED_LINE_CACHE[rel]
    if _head_text(rel) is None:
        path = ROOT / rel
        _CHANGED_LINE_CACHE[rel] = set(range(1, _line_count(path) + 1))
        return _CHANGED_LINE_CACHE[rel]
    try:
        proc = subprocess.run(
            ["git", "diff", "--unified=0", "HEAD", "--", rel],
            cwd=str(ROOT),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except OSError:
        _CHANGED_LINE_CACHE[rel] = set()
        return set()
    changed: set[int] = set()
    hunk_re = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
    for line in (proc.stdout or "").splitlines():
        match = hunk_re.search(line)
        if not match:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        if count <= 0:
            continue
        changed.update(range(start, start + count))
    _CHANGED_LINE_CACHE[rel] = changed
    return changed


def _filter_changed_regressions(
    result: dict[str, Any],
    *,
    max_file_lines: int,
    max_function_lines: int,
) -> dict[str, Any]:
    filtered: list[dict[str, Any]] = []
    for issue in list(result.get("issues") or []):
        rel = str(issue.get("path") or "")
        issue_type = str(issue.get("type") or "")
        if not rel:
            continue
        if _head_text(rel) is None:
            filtered.append(issue)
            continue
        if issue_type == "file_length":
            current_lines = int(issue.get("lines", 0) or 0)
            previous_lines = _head_line_count(rel)
            if previous_lines <= max_file_lines or current_lines > previous_lines:
                filtered.append(issue)
            continue
        if issue_type == "function_length":
            current_lines = int(issue.get("lines", 0) or 0)
            previous_lines = _head_python_function_lengths(rel).get(str(issue.get("name") or ""), 0)
            if previous_lines <= max_function_lines or current_lines > previous_lines:
                filtered.append(issue)
            continue
        if issue_type == "silent_exception":
            try:
                line_no = int(issue.get("line", 0) or 0)
            except (TypeError, ValueError):
                line_no = 0
            if line_no in _changed_lines(rel):
                filtered.append(issue)
            continue
        filtered.append(issue)
    updated = dict(result)
    updated["issues"] = filtered
    updated["issue_count"] = len(filtered)
    updated["ok"] = not filtered
    return updated



def _line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
    except OSError:
        return 0


def _python_function_issues(path: Path, max_function_lines: int) -> list[dict[str, Any]]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return []
    rel = str(path.relative_to(ROOT))
    issues: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end_lineno = int(getattr(node, "end_lineno", node.lineno) or node.lineno)
        length = max(1, end_lineno - int(node.lineno) + 1)
        key = f"{rel}:{node.name}"
        if length > max_function_lines and key not in FUNCTION_ALLOWLIST:
            issues.append(
                {
                    "type": "function_length",
                    "path": rel,
                    "name": node.name,
                    "line": int(node.lineno),
                    "end_line": end_lineno,
                    "lines": length,
                }
            )
    return issues


def _silent_exception_issues(path: Path) -> list[dict[str, Any]]:
    if path.suffix != ".py":
        return []
    rel = str(path.relative_to(ROOT))
    if rel in SILENT_EXCEPTION_ALLOWLIST:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    issues: list[dict[str, Any]] = []
    pattern = re.compile(r"^\s*except(?:\s+Exception(?:\s+as\s+\w+)?)?\s*:\s*(?:pass\s*)?$")
    for index, line in enumerate(lines, start=1):
        if pattern.match(line):
            next_text = lines[index].strip() if index < len(lines) else ""
            if "pass" in line or next_text == "pass":
                issues.append({"type": "silent_exception", "path": rel, "line": index})
    return issues


def run_check(paths: list[str], *, max_file_lines: int, max_function_lines: int) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for path in _iter_source_files(paths):
        rel = str(path.relative_to(ROOT))
        lines = _line_count(path)
        if lines > max_file_lines and rel not in FILE_ALLOWLIST:
            issues.append({"type": "file_length", "path": rel, "lines": lines})
        if path.suffix == ".py":
            issues.extend(_python_function_issues(path, max_function_lines))
            issues.extend(_silent_exception_issues(path))
    return {
        "ok": not issues,
        "issue_count": len(issues),
        "issues": issues,
        "limits": {"max_file_lines": max_file_lines, "max_function_lines": max_function_lines},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard source size and silent exception budget.")
    parser.add_argument("paths", nargs="*", default=[])
    parser.add_argument("--all", action="store_true", help="Scan the full default source tree instead of changed files.")
    parser.add_argument("--max-file-lines", type=int, default=1200)
    parser.add_argument("--max-function-lines", type=int, default=160)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    paths = list(args.paths or [])
    if not paths:
        paths = list(DEFAULT_PATHS) if args.all else _changed_source_paths()
    result = run_check(paths, max_file_lines=args.max_file_lines, max_function_lines=args.max_function_lines)
    if not args.all:
        result = _filter_changed_regressions(
            result,
            max_file_lines=args.max_file_lines,
            max_function_lines=args.max_function_lines,
        )
    result["scope"] = "all" if args.all else "changed"
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"ok={result['ok']} issues={result['issue_count']}")
        for issue in result["issues"][:50]:
            print(issue)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
