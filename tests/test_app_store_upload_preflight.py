from __future__ import annotations

import json
from pathlib import Path

from core.runtime.config import APP_VERSION
from tools.check_app_store_upload_preflight import REQUIRED_UPLOAD_GATES, check_upload_preflight


def _ready_payload(pkg: Path) -> dict:
    return {
        "schema": "ai_subtitle_studio.app_store_readiness.v1",
        "root": str(pkg.parent),
        "app_version": APP_VERSION,
        "app_store_submission_ready": True,
        "blockers": [],
        "submission_gate_summary": {gate: True for gate in REQUIRED_UPLOAD_GATES},
        "owner_metadata_values_preflight": {
            "ready": True,
            "owner_input_ready_count": 8,
            "owner_input_total": 8,
            "app_store_connect_metadata_ready_count": 8,
            "app_store_connect_metadata_total": 8,
            "forbidden_claim_scan": {"status": "pass"},
        },
        "artifacts": {
            "app_store_pkg": {
                "path": str(pkg),
                "is_file": True,
            }
        },
    }


def test_upload_preflight_blocks_when_readiness_is_false(tmp_path):
    pkg = tmp_path / "AI Subtitle Studio.pkg"
    pkg.write_text("pkg", encoding="utf-8")
    readiness = tmp_path / "readiness.json"
    payload = _ready_payload(pkg)
    payload["app_store_submission_ready"] = False
    payload["blockers"] = ["owner_metadata_pending"]
    payload["submission_gate_summary"]["owner_metadata_ready"] = False
    payload["submission_gate_summary"]["app_store_submission_ready"] = False
    readiness.write_text(json.dumps(payload), encoding="utf-8")

    result = check_upload_preflight(readiness_json=readiness, pkg_path=pkg)

    assert result["ready"] is False
    assert "readiness_blockers_present" in result["issues"]
    assert "app_store_submission_ready_not_true" in result["issues"]
    assert any(issue.startswith("submission_gates_not_ready:") for issue in result["issues"])


def test_upload_preflight_requires_exact_package_path(tmp_path):
    pkg = tmp_path / "AI Subtitle Studio.pkg"
    other_pkg = tmp_path / "Other.pkg"
    pkg.write_text("pkg", encoding="utf-8")
    other_pkg.write_text("pkg", encoding="utf-8")
    readiness = tmp_path / "readiness.json"
    readiness.write_text(json.dumps(_ready_payload(other_pkg)), encoding="utf-8")

    result = check_upload_preflight(readiness_json=readiness, pkg_path=pkg)

    assert result["ready"] is False
    assert "readiness_pkg_path_mismatch" in result["issues"]


def test_upload_preflight_rejects_minimal_forged_ready_json(tmp_path):
    pkg = tmp_path / "AI Subtitle Studio.pkg"
    pkg.write_text("pkg", encoding="utf-8")
    readiness = tmp_path / "readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "app_store_submission_ready": True,
                "blockers": [],
                "submission_gate_summary": {gate: True for gate in REQUIRED_UPLOAD_GATES},
                "artifacts": {"app_store_pkg": {"path": str(pkg), "is_file": True}},
            }
        ),
        encoding="utf-8",
    )

    result = check_upload_preflight(readiness_json=readiness, pkg_path=pkg)

    assert result["ready"] is False
    assert "readiness_schema_mismatch" in result["issues"]
    assert "readiness_root_missing" in result["issues"]
    assert "owner_metadata_values_preflight_not_ready" in result["issues"]


def test_upload_preflight_accepts_ready_report_for_exact_package(tmp_path):
    pkg = tmp_path / "AI Subtitle Studio.pkg"
    pkg.write_text("pkg", encoding="utf-8")
    readiness = tmp_path / "readiness.json"
    readiness.write_text(json.dumps(_ready_payload(pkg)), encoding="utf-8")

    result = check_upload_preflight(readiness_json=readiness, pkg_path=pkg)

    assert result["ready"] is True
    assert result["issues"] == []
