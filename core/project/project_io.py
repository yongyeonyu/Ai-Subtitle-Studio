# Version: 03.14.28
# Phase: PHASE2
"""Shared project JSON file I/O helpers."""
from __future__ import annotations

import json
import os
from typing import Any


def read_project_file(filepath: str) -> dict[str, Any]:
    """Read a project JSON file with the app-wide encoding/settings."""
    with open(filepath, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def write_project_file(filepath: str, project: dict[str, Any]) -> None:
    """Write a project JSON file with stable UTF-8 formatting."""
    folder = os.path.dirname(os.path.abspath(filepath))
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as handle:
        json.dump(project, handle, ensure_ascii=False, indent=2)
