from __future__ import annotations

from collections.abc import Sized
from typing import Any

NLE_PERSISTENCE_GUARD_SCHEMA = "ai_subtitle_studio.nle_persistence_guard.v1"
NLE_PERSISTENCE_QUARANTINE_KEY = "_nle_persistence_quarantine"
NLE_SNAPSHOT_PERSISTENCE_APPROVAL_SCHEMA = "ai_subtitle_studio.nle_snapshot_persistence_approval.v1"
NLE_TOP_LEVEL_PERSISTENCE_APPROVAL_SCHEMA = "ai_subtitle_studio.nle_top_level_persistence_approval.v1"
NLE_RUNTIME_STATE_PERSISTENCE_APPROVAL_SCHEMA = "ai_subtitle_studio.nle_runtime_state_persistence_approval.v1"
NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID = "owner_approved_20260628"
NLE_LEGACY_CANONICAL_LOAD_OWNER = "legacy_editor_state"
NLE_SNAPSHOT_CANONICAL_LOAD_OWNER = "nle_snapshot"
NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER = "top_level_nle_shadow_metadata"
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


def approved_top_level_nle_persistence_requested(project: dict[str, Any] | None) -> bool:
    if not isinstance(project, dict):
        return False
    policy = project.get("nle_persistence")
    if not isinstance(policy, dict):
        return False
    return (
        bool(policy.get("persist_snapshot"))
        and bool(policy.get("persist_top_level_nle"))
        and str(policy.get("approval") or "") == NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID
    )


def approved_nle_snapshot_payload(value: Any) -> bool:
    return _is_approved_nle_snapshot_payload(value)


def approved_top_level_nle_payload(value: Any) -> bool:
    return _is_approved_top_level_nle_payload(value)


def approved_nle_snapshot_canonical_load_requested(project: dict[str, Any] | None) -> bool:
    if not approved_nle_snapshot_persistence_requested(project):
        return False
    policy = project.get("nle_persistence")
    if not isinstance(policy, dict):
        return False
    return (
        str(policy.get("canonical_load_owner") or "") == NLE_SNAPSHOT_CANONICAL_LOAD_OWNER
        and bool(policy.get("canonical_load_owner_change_allowed"))
        and bool(policy.get("nle_snapshot_canonical_load_source_allowed"))
        and bool(policy.get("legacy_editor_state_preserved_for_rollback"))
        and not bool(policy.get("legacy_editor_state_remains_canonical"))
        and not bool(policy.get("persist_top_level_nle"))
        and str(policy.get("approval") or "") == NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID
    )


def approved_runtime_nle_project_state_persistence_requested(project: dict[str, Any] | None) -> bool:
    if not approved_nle_snapshot_canonical_load_requested(project):
        return False
    policy = project.get("nle_persistence")
    if not isinstance(policy, dict):
        return False
    return (
        bool(policy.get("persist_runtime_project_state"))
        and bool(policy.get("runtime_project_state_persistence_allowed"))
        and bool(policy.get("legacy_editor_state_preserved_for_rollback"))
        and bool(policy.get("default_project_authority_unchanged"))
        and not bool(policy.get("legacy_disk_shape_replacement_allowed"))
        and not bool(policy.get("final_cutover_ready"))
        and not bool(policy.get("persist_top_level_nle"))
        and str(policy.get("canonical_load_owner") or "") == NLE_SNAPSHOT_CANONICAL_LOAD_OWNER
        and str(policy.get("approval") or "") == NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID
    )


def approved_top_level_nle_canonical_load_requested(project: dict[str, Any] | None) -> bool:
    if not approved_top_level_nle_persistence_requested(project):
        return False
    policy = project.get("nle_persistence")
    if not isinstance(policy, dict):
        return False
    return (
        str(policy.get("canonical_load_owner") or "") == NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER
        and bool(policy.get("canonical_load_owner_change_allowed"))
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


def nle_snapshot_canonical_load_approval_payload(*, source: str = "") -> dict[str, Any]:
    return {
        "schema": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_SCHEMA,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
        "source": str(source or "project_storage"),
        "persist_snapshot": True,
        "legacy_editor_state_remains_canonical": False,
        "legacy_editor_state_preserved_for_rollback": True,
        "runtime_project_state_persisted": False,
        "canonical_load_owner": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
        "canonical_load_owner_change_allowed": True,
        "nle_snapshot_canonical_load_source_allowed": True,
    }


def nle_runtime_state_persistence_approval_payload(*, source: str = "") -> dict[str, Any]:
    return {
        "schema": NLE_RUNTIME_STATE_PERSISTENCE_APPROVAL_SCHEMA,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
        "source": str(source or "project_storage"),
        "persist_runtime_project_state": True,
        "runtime_project_state_persistence_allowed": True,
        "runtime_project_state_schema": "ai_subtitle_studio.nle_project_state.v1",
        "canonical_load_owner": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
        "legacy_editor_state_preserved_for_rollback": True,
        "default_project_authority_unchanged": True,
        "legacy_disk_shape_replacement_allowed": False,
        "final_cutover_ready": False,
    }


def nle_top_level_persistence_approval_payload(*, source: str = "") -> dict[str, Any]:
    return {
        "schema": NLE_TOP_LEVEL_PERSISTENCE_APPROVAL_SCHEMA,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
        "source": str(source or "project_storage"),
        "persist_top_level_nle": True,
        "legacy_editor_state_remains_canonical": True,
        "runtime_project_state_persisted": False,
        "canonical_load_owner": NLE_LEGACY_CANONICAL_LOAD_OWNER,
    }


def nle_top_level_canonical_load_approval_payload(*, source: str = "") -> dict[str, Any]:
    return {
        "schema": NLE_TOP_LEVEL_PERSISTENCE_APPROVAL_SCHEMA,
        "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
        "source": str(source or "project_storage"),
        "persist_top_level_nle": True,
        "legacy_editor_state_remains_canonical": False,
        "legacy_editor_state_preserved_for_rollback": True,
        "runtime_project_state_persisted": False,
        "canonical_load_owner": NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER,
        "canonical_load_owner_change_allowed": True,
    }


def _is_approved_nle_snapshot_payload(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if str(value.get("schema") or "") != "ai_subtitle_studio.nle_snapshot.v1":
        return False
    approval = value.get("persistence")
    if not isinstance(approval, dict):
        return False
    base_ok = (
        str(approval.get("schema") or "") == NLE_SNAPSHOT_PERSISTENCE_APPROVAL_SCHEMA
        and str(approval.get("approval") or "") == NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID
        and bool(approval.get("persist_snapshot"))
        and not bool(approval.get("runtime_project_state_persisted"))
    )
    if not base_ok:
        return False
    if str(approval.get("canonical_load_owner") or "") == NLE_SNAPSHOT_CANONICAL_LOAD_OWNER:
        metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        return (
            not bool(approval.get("legacy_editor_state_remains_canonical"))
            and bool(approval.get("legacy_editor_state_preserved_for_rollback"))
            and bool(approval.get("canonical_load_owner_change_allowed"))
            and bool(approval.get("nle_snapshot_canonical_load_source_allowed"))
            and not bool(metadata.get("read_only"))
            and bool(metadata.get("owner_approved_canonical_load_opt_in"))
        )
    return (
        bool(approval.get("legacy_editor_state_remains_canonical"))
        and not bool(approval.get("canonical_load_owner_change_allowed"))
        and not bool(approval.get("nle_snapshot_canonical_load_source_allowed"))
    )


def _is_approved_top_level_nle_payload(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if str(value.get("schema") or "") != "ai_subtitle_studio.nle_shadow_project.v1":
        return False
    canonical_owner = str(value.get("canonical_load_owner") or "")
    if canonical_owner not in {NLE_LEGACY_CANONICAL_LOAD_OWNER, NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER}:
        return False
    if bool(value.get("runtime_project_state_persisted")):
        return False
    approval = value.get("persistence")
    if not isinstance(approval, dict):
        return False
    base_ok = (
        str(approval.get("schema") or "") == NLE_TOP_LEVEL_PERSISTENCE_APPROVAL_SCHEMA
        and str(approval.get("approval") or "") == NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID
        and bool(approval.get("persist_top_level_nle"))
        and not bool(approval.get("runtime_project_state_persisted"))
        and str(approval.get("canonical_load_owner") or "") == canonical_owner
    )
    if not base_ok:
        return False
    if canonical_owner == NLE_LEGACY_CANONICAL_LOAD_OWNER:
        return (
            str(value.get("role") or "") == "shadow_metadata"
            and bool(approval.get("legacy_editor_state_remains_canonical"))
            and not bool(approval.get("canonical_load_owner_change_allowed"))
        )
    return (
        str(value.get("role") or "") == "canonical_load_owner"
        and not bool(approval.get("legacy_editor_state_remains_canonical"))
        and bool(approval.get("legacy_editor_state_preserved_for_rollback"))
        and bool(approval.get("canonical_load_owner_change_allowed"))
    )


def _is_approved_runtime_nle_project_state_payload(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if str(value.get("schema") or "") != "ai_subtitle_studio.nle_project_state.v1":
        return False
    approval = value.get("persistence")
    if not isinstance(approval, dict):
        return False
    if not (
        str(approval.get("schema") or "") == NLE_RUNTIME_STATE_PERSISTENCE_APPROVAL_SCHEMA
        and str(approval.get("approval") or "") == NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID
        and bool(approval.get("persist_runtime_project_state"))
        and bool(approval.get("runtime_project_state_persistence_allowed"))
        and str(approval.get("runtime_project_state_schema") or "") == "ai_subtitle_studio.nle_project_state.v1"
        and str(approval.get("canonical_load_owner") or "") == NLE_SNAPSHOT_CANONICAL_LOAD_OWNER
        and bool(approval.get("legacy_editor_state_preserved_for_rollback"))
        and bool(approval.get("default_project_authority_unchanged"))
        and not bool(approval.get("legacy_disk_shape_replacement_allowed"))
        and not bool(approval.get("final_cutover_ready"))
    ):
        return False
    rows = value.get("editor_rows")
    journal = value.get("operation_journal")
    metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
    return (
        isinstance(rows, list)
        and int(value.get("editor_row_count") or 0) == len(rows)
        and isinstance(journal, list)
        and bool(metadata.get("persisted_runtime_state"))
        and bool(metadata.get("default_project_authority_unchanged"))
    )


def approved_runtime_nle_project_state_payload(value: Any) -> bool:
    return _is_approved_runtime_nle_project_state_payload(value)


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


def _is_unapproved_nle_payload(key: str, value: Any, *, project: dict[str, Any] | None = None) -> bool:
    if key not in UNAPPROVED_NLE_PERSISTENCE_KEYS:
        return False
    if key == "nle" and _is_approved_top_level_nle_payload(value):
        return False
    if key == "nle_snapshot" and _is_approved_nle_snapshot_payload(value):
        return False
    if key == "_nle_project_state" and _is_runtime_nle_project_state(value):
        return False
    if (
        key == "_nle_project_state"
        and approved_runtime_nle_project_state_persistence_requested(project)
        and _is_approved_runtime_nle_project_state_payload(value)
    ):
        return False
    return True


def _approved_top_level_nle_companion_missing(project: dict[str, Any]) -> bool:
    return (
        "nle" in project
        and _is_approved_top_level_nle_payload(project.get("nle"))
        and not _is_approved_nle_snapshot_payload(project.get("nle_snapshot"))
    )


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
        if not _is_unapproved_nle_payload(key, value, project=project):
            continue
        removed[key] = _value_summary(value)
        project.pop(key, None)
    if _approved_top_level_nle_companion_missing(project):
        removed["nle"] = _value_summary(project.get("nle"))
        project.pop("nle", None)

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
        if key in project and _is_unapproved_nle_payload(key, project.get(key), project=project)
    ]
    if _approved_top_level_nle_companion_missing(project):
        blocked.append("nle")
    if blocked:
        label = str(surface or "project")
        raise ValueError(f"unapproved_nle_persistence_fields:{label}:{','.join(blocked)}")


__all__ = [
    "NLE_PERSISTENCE_GUARD_SCHEMA",
    "NLE_PERSISTENCE_QUARANTINE_KEY",
    "NLE_LEGACY_CANONICAL_LOAD_OWNER",
    "NLE_RUNTIME_STATE_PERSISTENCE_APPROVAL_SCHEMA",
    "NLE_SNAPSHOT_CANONICAL_LOAD_OWNER",
    "NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID",
    "NLE_SNAPSHOT_PERSISTENCE_APPROVAL_SCHEMA",
    "NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER",
    "NLE_TOP_LEVEL_PERSISTENCE_APPROVAL_SCHEMA",
    "UNAPPROVED_NLE_PERSISTENCE_KEYS",
    "approved_runtime_nle_project_state_payload",
    "approved_runtime_nle_project_state_persistence_requested",
    "approved_nle_snapshot_persistence_requested",
    "approved_nle_snapshot_canonical_load_requested",
    "approved_nle_snapshot_payload",
    "approved_top_level_nle_payload",
    "approved_top_level_nle_canonical_load_requested",
    "approved_top_level_nle_persistence_requested",
    "assert_no_unapproved_nle_persistence_fields",
    "nle_runtime_state_persistence_approval_payload",
    "nle_snapshot_canonical_load_approval_payload",
    "nle_snapshot_persistence_approval_payload",
    "nle_top_level_canonical_load_approval_payload",
    "nle_top_level_persistence_approval_payload",
    "strip_unapproved_nle_persistence_fields",
]
