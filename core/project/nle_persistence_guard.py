from __future__ import annotations

from collections.abc import Sized
from typing import Any

NLE_PERSISTENCE_GUARD_SCHEMA = "ai_subtitle_studio.nle_persistence_guard.v1"
NLE_PERSISTENCE_QUARANTINE_KEY = "_nle_persistence_quarantine"
NLE_SNAPSHOT_PERSISTENCE_APPROVAL_SCHEMA = "ai_subtitle_studio.nle_snapshot_persistence_approval.v1"
NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID = "owner_approved_20260628"
UNAPPROVED_NLE_PERSISTENCE_KEYS = ("nle", "nle_snapshot", "_nle_project_state")


def _is_runtime_nle_project_state(value: Any) -> bool:
    cls = getattr(value, "__class__", None)
    return (
        getattr(cls, "__name__", "") == "NLEProjectState"
        and callable(getattr(value, "editor_rows", None))
        and hasattr(value, "schema")
    )


def approved_nle_snapshot_persistence_requested(project: dict[str, Any] | None) -> bool:
    if not isinstance(project, dict):
        return False
    policy = project.get("nle_persistence")
    if not isinstance(policy, dict):
        return False
    return (
        bool(policy.get("persist_snapshot"))
        and str(policy.get("approval") or "") == NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID
    )


def nle_snapshot_persistence_approval_payload(*, source: str = "") -> dict[str, Any]:
    return {
        "schema": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_SCHEMA,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
        "source": str(source or "project_storage"),
        "persist_snapshot": True,
        "legacy_editor_state_remains_canonical": True,
        "runtime_project_state_persisted": False,
    }


def _is_approved_nle_snapshot_payload(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if str(value.get("schema") or "") != "ai_subtitle_studio.nle_snapshot.v1":
        return False
    approval = value.get("persistence")
    if not isinstance(approval, dict):
        return False
    return (
        str(approval.get("schema") or "") == NLE_SNAPSHOT_PERSISTENCE_APPROVAL_SCHEMA
        and str(approval.get("approval") or "") == NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID
        and bool(approval.get("persist_snapshot"))
        and bool(approval.get("legacy_editor_state_remains_canonical"))
        and not bool(approval.get("runtime_project_state_persisted"))
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
    if key == "nle_snapshot" and _is_approved_nle_snapshot_payload(value):
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
    "NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID",
    "NLE_SNAPSHOT_PERSISTENCE_APPROVAL_SCHEMA",
    "UNAPPROVED_NLE_PERSISTENCE_KEYS",
    "approved_nle_snapshot_persistence_requested",
    "assert_no_unapproved_nle_persistence_fields",
    "nle_snapshot_persistence_approval_payload",
    "strip_unapproved_nle_persistence_fields",
]
