from __future__ import annotations

from collections.abc import Sized
from typing import Any

NLE_PERSISTENCE_GUARD_SCHEMA = "ai_subtitle_studio.nle_persistence_guard.v1"
NLE_PERSISTENCE_QUARANTINE_KEY = "_nle_persistence_quarantine"
UNAPPROVED_NLE_PERSISTENCE_KEYS = ("nle", "nle_snapshot", "_nle_project_state")


def _is_runtime_nle_project_state(value: Any) -> bool:
    cls = getattr(value, "__class__", None)
    return (
        getattr(cls, "__name__", "") == "NLEProjectState"
        and callable(getattr(value, "editor_rows", None))
        and hasattr(value, "schema")
    )


def _value_summary(value: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {"type": type(value).__name__}
    if isinstance(value, dict):
        summary["count"] = len(value)
        summary["keys"] = [str(key) for key in list(value.keys())[:8]]
    elif isinstance(value, (list, tuple, set)):
        summary["count"] = len(value)
    elif isinstance(value, Sized) and not isinstance(value, (str, bytes, bytearray)):
        try:
            summary["count"] = len(value)
        except Exception:
            pass
    return summary


def _is_unapproved_nle_payload(key: str, value: Any) -> bool:
    if key not in UNAPPROVED_NLE_PERSISTENCE_KEYS:
        return False
    if key == "_nle_project_state" and _is_runtime_nle_project_state(value):
        return False
    return True


def strip_unapproved_nle_persistence_fields(
    project: dict[str, Any] | None,
    *,
    source: str = "",
) -> dict[str, Any]:
    """Remove future NLE persistence fields until the owner approves the format."""
    if not isinstance(project, dict):
        return {}

    removed: dict[str, dict[str, Any]] = {}
    for key in UNAPPROVED_NLE_PERSISTENCE_KEYS:
        if key not in project:
            continue
        value = project.get(key)
        if not _is_unapproved_nle_payload(key, value):
            continue
        removed[key] = _value_summary(value)
        project.pop(key, None)

    if not removed:
        return {}

    report = {
        "schema": NLE_PERSISTENCE_GUARD_SCHEMA,
        "source": str(source or "unknown"),
        "approved_persistence": False,
        "stripped_keys": list(removed.keys()),
        "stripped_count": len(removed),
        "stripped_payload_summaries": removed,
    }
    project[NLE_PERSISTENCE_QUARANTINE_KEY] = report
    return report


def assert_no_unapproved_nle_persistence_fields(
    project: dict[str, Any] | None,
    *,
    surface: str = "",
) -> None:
    if not isinstance(project, dict):
        return
    blocked = [
        key
        for key in UNAPPROVED_NLE_PERSISTENCE_KEYS
        if key in project and _is_unapproved_nle_payload(key, project.get(key))
    ]
    if blocked:
        label = str(surface or "project")
        raise ValueError(f"unapproved_nle_persistence_fields:{label}:{','.join(blocked)}")


__all__ = [
    "NLE_PERSISTENCE_GUARD_SCHEMA",
    "NLE_PERSISTENCE_QUARANTINE_KEY",
    "UNAPPROVED_NLE_PERSISTENCE_KEYS",
    "assert_no_unapproved_nle_persistence_fields",
    "strip_unapproved_nle_persistence_fields",
]
