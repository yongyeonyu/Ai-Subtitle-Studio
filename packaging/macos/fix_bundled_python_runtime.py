#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
from pathlib import Path


def parse_python_framework_dependency(otool_output: str) -> str:
    for line in otool_output.splitlines():
        candidate = line.strip().split(" ", 1)[0]
        if "/Python.framework/Versions/" in candidate and candidate.endswith("/Python"):
            return candidate
    raise RuntimeError("Python.framework dependency was not found in bundled Python executable.")


def framework_version_dir(framework_binary: Path) -> Path:
    parts = framework_binary.parts
    try:
        index = parts.index("Versions")
    except ValueError as exc:
        raise RuntimeError(f"Unexpected Python.framework path: {framework_binary}") from exc
    if index + 1 >= len(parts):
        raise RuntimeError(f"Unexpected Python.framework path: {framework_binary}")
    return Path(*parts[: index + 2])


def replace_with_relative_symlink(path: Path, target_name: str) -> None:
    if path.exists() or path.is_symlink():
        path.unlink()
    path.symlink_to(target_name)


def remove_existing(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def copy_file_with_mode(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    shutil.copy2(src, dst)
    mode = dst.stat().st_mode
    dst.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run_install_name_tool(*args: str) -> None:
    subprocess.run(["install_name_tool", *args], check=True)


def fix_runtime(source_venv: Path, bundle_python_dir: Path) -> None:
    source_python = (source_venv / "bin" / "python3.11").resolve()
    if not source_python.exists():
        raise RuntimeError(f"Source Python executable not found: {source_python}")

    otool = subprocess.check_output(["otool", "-L", str(source_python)], text=True)
    source_framework_binary = Path(parse_python_framework_dependency(otool)).resolve()
    source_framework_version = framework_version_dir(source_framework_binary)

    framework_root = bundle_python_dir / "Frameworks" / "Python.framework"
    framework_version = framework_root / "Versions" / source_framework_version.name
    remove_existing(framework_version)
    framework_version.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_framework_version, framework_version, symlinks=True)
    remove_existing(framework_version / "lib" / "python3.11" / "site-packages")

    current_link = framework_root / "Versions" / "Current"
    replace_with_relative_symlink(current_link, source_framework_version.name)
    replace_with_relative_symlink(framework_root / "Python", "Versions/Current/Python")
    if (framework_version / "Resources").exists():
        replace_with_relative_symlink(framework_root / "Resources", "Versions/Current/Resources")
    if (framework_version / "Headers").exists():
        replace_with_relative_symlink(framework_root / "Headers", "Versions/Current/Headers")

    bundled_python = bundle_python_dir / "bin" / "python3.11"
    copy_file_with_mode(source_python, bundled_python)
    replace_with_relative_symlink(bundle_python_dir / "bin" / "python3", "python3.11")
    replace_with_relative_symlink(bundle_python_dir / "bin" / "python", "python3.11")

    bundled_framework_binary = framework_version / "Python"
    internal_dependency = f"@executable_path/../Frameworks/Python.framework/Versions/{source_framework_version.name}/Python"
    run_install_name_tool("-change", str(source_framework_binary), internal_dependency, str(bundled_python))
    framework_bin_python = framework_version / "bin" / "python3.11"
    if framework_bin_python.exists():
        run_install_name_tool("-change", str(source_framework_binary), "@executable_path/../Python", str(framework_bin_python))
    python_app_executable = framework_version / "Resources" / "Python.app" / "Contents" / "MacOS" / "Python"
    if python_app_executable.exists():
        run_install_name_tool(
            "-change",
            str(source_framework_binary),
            "@executable_path/../../../../Python",
            str(python_app_executable),
        )
    run_install_name_tool("-id", f"@rpath/Python.framework/Versions/{source_framework_version.name}/Python", str(bundled_framework_binary))

    pyvenv_cfg = bundle_python_dir / "pyvenv.cfg"
    if pyvenv_cfg.exists():
        pyvenv_cfg.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Make the bundled Python runtime self-contained for macOS signing.")
    parser.add_argument("--source-venv", required=True, type=Path)
    parser.add_argument("--bundle-python-dir", required=True, type=Path)
    args = parser.parse_args()
    fix_runtime(args.source_venv, args.bundle_python_dir)
    print(f"Fixed bundled Python runtime: {args.bundle_python_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
