from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.runtime.config import APP_VERSION
from tools.audit_app_store_readiness import EXPECTED_INFO_VALUES, NON_CODE_SUBMISSION_ITEMS
from tools.check_app_store_owner_metadata_values import (
    APP_STORE_CONNECT_METADATA_KEYS,
    OWNER_VALUES_SCHEMA,
    build_owner_metadata_values_template,
    check_owner_metadata_values,
)

ROOT = Path(__file__).resolve().parents[1]


def _approved(value: str, *, owner_controlled: bool = False, **extra):
    payload = {
        "value": value,
        "approved": True,
        "evidence": "owner approval 2026-06-29",
        "owner_controlled": owner_controlled,
    }
    payload.update(extra)
    return payload


def _complete_values_payload() -> dict:
    return {
        "schema": OWNER_VALUES_SCHEMA,
        "app_version": APP_VERSION,
        "owner_inputs": {
            "privacy_policy_url": _approved("https://example.com/privacy", owner_controlled=True),
            "privacy_data_type_answers": _approved("User-selected media, optional STT, diagnostics, no unsupported claims."),
            "export_compliance_answers": _approved("Uses standard TLS/network behavior as configured by the submitted app."),
            "mac_app_store_screenshots": _approved(
                "Approved screenshot manifest for the signed sandboxed candidate.",
                signed_candidate_artifact="dist/macos/AI Subtitle Studio.app",
                submitted_binary_match=True,
            ),
            "support_url": _approved("https://example.com/support", owner_controlled=True),
            "app_review_notes": _approved("Sandboxed user-selected file access and optional STT/model workflow notes."),
            "age_rating_answers": _approved("Owner-approved age rating answers for the submitted feature set."),
            "release_notes": _approved("Owner-approved release notes for the submitted version."),
        },
        "app_store_connect_metadata": {
            "app_name": _approved(EXPECTED_INFO_VALUES["CFBundleDisplayName"]),
            "app_subtitle": _approved("Subtitle generation and editing for macOS."),
            "keywords": _approved("subtitles, captions, video, editor"),
            "description": _approved("Create, review, save, reopen, and export subtitles for user-selected media."),
            "promotional_text": _approved("", not_applicable=True),
            "marketing_url": _approved("", not_applicable=True),
            "app_store_connect_record": _approved(
                f"Bundle ID {EXPECTED_INFO_VALUES['CFBundleIdentifier']}, SKU owner-approved, primary locale en-US."
            ),
            "pricing_and_availability": _approved("Owner-approved price tier and availability."),
        },
    }


def _write_values(tmp_path, payload: dict):
    path = tmp_path / "owner_values.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_owner_metadata_values_preflight_blocks_missing_values_file(tmp_path):
    result = check_owner_metadata_values(values_json=tmp_path / "missing.json")

    assert result["ready"] is False
    assert "owner_metadata_values_file_missing" in result["issues"]
    assert result["owner_input_ready_count"] == 0
    assert result["app_store_connect_metadata_ready_count"] == 0
    assert result["missing_owner_input_keys"] == list(NON_CODE_SUBMISSION_ITEMS)
    assert result["missing_app_store_connect_metadata_keys"] == list(APP_STORE_CONNECT_METADATA_KEYS)


def test_owner_metadata_values_template_is_not_ready_until_owner_values_are_filled(tmp_path):
    template = build_owner_metadata_values_template()
    values_path = _write_values(tmp_path, template)

    result = check_owner_metadata_values(values_json=values_path)

    assert template["schema"] == OWNER_VALUES_SCHEMA
    assert template["template_only_not_submission_proof"] is True
    assert set(template["owner_inputs"]) == set(NON_CODE_SUBMISSION_ITEMS)
    assert set(template["app_store_connect_metadata"]) == set(APP_STORE_CONNECT_METADATA_KEYS)
    assert result["ready"] is False
    assert result["owner_input_ready_count"] == 0
    assert result["app_store_connect_metadata_ready_count"] == 0
    assert "owner_inputs:privacy_policy_url:owner_approval_missing" in result["issues"]
    assert "app_store_connect_metadata:app_name:value_missing" in result["issues"]


def test_owner_metadata_values_template_cli_writes_blocked_template(tmp_path):
    values_path = tmp_path / "owner_metadata_values_template.json"
    write_result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/check_app_store_owner_metadata_values.py"),
            "--write-template",
            str(values_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert write_result.returncode == 0, write_result.stderr
    assert values_path.is_file()
    write_payload = json.loads(write_result.stdout)
    assert write_payload["template"] == str(values_path)
    assert write_payload["schema"] == OWNER_VALUES_SCHEMA

    check_result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/check_app_store_owner_metadata_values.py"),
            "--values-json",
            str(values_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    check_payload = json.loads(check_result.stdout)

    assert check_result.returncode == 65
    assert check_payload["ready"] is False
    assert check_payload["owner_input_ready_count"] == 0
    assert check_payload["app_store_connect_metadata_ready_count"] == 0
    assert "owner_inputs:privacy_policy_url:owner_approval_missing" in check_payload["issues"]
    assert "app_store_connect_metadata:app_name:value_missing" in check_payload["issues"]


def test_owner_metadata_values_preflight_rejects_approval_without_values(tmp_path):
    payload = {
        "schema": OWNER_VALUES_SCHEMA,
        "app_version": APP_VERSION,
        "owner_inputs": {key: {"approved": True, "evidence": "owner approval"} for key in NON_CODE_SUBMISSION_ITEMS},
        "app_store_connect_metadata": {
            key: {"approved": True, "evidence": "owner approval"} for key in APP_STORE_CONNECT_METADATA_KEYS
        },
    }
    result = check_owner_metadata_values(values_json=_write_values(tmp_path, payload))

    assert result["ready"] is False
    assert any(issue.endswith(":value_missing") for issue in result["issues"])
    assert result["owner_input_ready_count"] < result["owner_input_total"]
    assert result["app_store_connect_metadata_ready_count"] < result["app_store_connect_metadata_total"]


def test_owner_metadata_values_preflight_accepts_complete_values(tmp_path):
    result = check_owner_metadata_values(values_json=_write_values(tmp_path, _complete_values_payload()))

    assert result["ready"] is True
    assert result["issues"] == []
    assert result["owner_input_ready_count"] == result["owner_input_total"]
    assert result["app_store_connect_metadata_ready_count"] == result["app_store_connect_metadata_total"]
    assert result["forbidden_claim_scan"]["status"] == "pass"


def test_owner_metadata_values_preflight_scans_imported_owner_copy(tmp_path):
    payload = _complete_values_payload()
    payload["app_store_connect_metadata"]["description"]["value"] = "App Store ready commercial NLE replacement."

    result = check_owner_metadata_values(values_json=_write_values(tmp_path, payload))

    assert result["ready"] is False
    assert result["forbidden_claim_scan"]["status"] == "fail"
    assert any("forbidden_claim:app_store_connect_metadata:description" in issue for issue in result["issues"])


def test_owner_metadata_values_preflight_requires_screenshot_candidate_binding(tmp_path):
    payload = _complete_values_payload()
    payload["owner_inputs"]["mac_app_store_screenshots"].pop("signed_candidate_artifact")
    payload["owner_inputs"]["mac_app_store_screenshots"]["submitted_binary_match"] = False

    result = check_owner_metadata_values(values_json=_write_values(tmp_path, payload))

    assert result["ready"] is False
    assert "owner_inputs:mac_app_store_screenshots:signed_candidate_artifact_missing" in result["issues"]
    assert "owner_inputs:mac_app_store_screenshots:submitted_binary_match_missing" in result["issues"]
