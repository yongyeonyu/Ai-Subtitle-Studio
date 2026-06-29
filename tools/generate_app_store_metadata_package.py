#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.audit_app_store_readiness import (
    EXPECTED_INFO_VALUES,
    NON_CODE_SUBMISSION_ITEMS,
    OFFICIAL_REFERENCES,
    SUBMISSION_TARGET,
    build_readiness_report,
)
from tools.check_app_store_owner_metadata_values import (
    FORBIDDEN_COPY_CLAIMS,
)


OWNER_INPUT_FIELD_HINTS = {
    "privacy_policy_url": "App Store Connect app privacy policy URL",
    "privacy_data_type_answers": "App Privacy data collection questionnaire",
    "export_compliance_answers": "Export Compliance questionnaire",
    "mac_app_store_screenshots": "Mac App Store screenshots for the exact submitted binary",
    "support_url": "Support URL",
    "app_review_notes": "App Review Notes",
    "age_rating_answers": "Age Rating questionnaire",
    "release_notes": "Version release notes",
}

APP_STORE_CONNECT_METADATA_FIELDS = (
    {
        "key": "app_name",
        "status": "source_known_owner_confirm",
        "field_hint": "App name",
        "draft": EXPECTED_INFO_VALUES["CFBundleDisplayName"],
        "owner_decision_required": "Confirm the final App Store display name.",
        "acceptance_gate": "Owner-approved App Store Connect value matches the submitted binary.",
    },
    {
        "key": "app_subtitle",
        "status": "owner_input_required",
        "field_hint": "App subtitle",
        "draft": "",
        "owner_decision_required": "Provide the final App Store subtitle.",
        "acceptance_gate": "Subtitle is owner-approved and avoids unsupported performance or readiness claims.",
    },
    {
        "key": "keywords",
        "status": "owner_input_required",
        "field_hint": "Keywords",
        "draft": "",
        "owner_decision_required": "Provide final searchable keywords.",
        "acceptance_gate": "Keywords are owner-approved and match verified shipped behavior.",
    },
    {
        "key": "description",
        "status": "owner_input_required",
        "field_hint": "Description",
        "draft": "",
        "owner_decision_required": "Provide or approve the final product description.",
        "acceptance_gate": "Description passes copy guardrails and matches the submitted build.",
    },
    {
        "key": "promotional_text",
        "status": "owner_input_required",
        "field_hint": "Promotional text",
        "draft": "",
        "owner_decision_required": "Provide optional promotional text or mark it not applicable.",
        "acceptance_gate": "Promotional text is owner-approved and contains no forbidden claims.",
    },
    {
        "key": "marketing_url",
        "status": "owner_input_required",
        "field_hint": "Marketing URL",
        "draft": "",
        "owner_decision_required": "Provide the final public marketing URL or mark it not applicable.",
        "acceptance_gate": "URL is owner-approved, reachable, and controlled by the owner.",
    },
    {
        "key": "app_store_connect_record",
        "status": "owner_input_required",
        "field_hint": "App Store Connect team, app record, bundle ID, SKU, and primary locale",
        "draft": f"Bundle ID: {EXPECTED_INFO_VALUES['CFBundleIdentifier']}",
        "owner_decision_required": "Confirm the developer team, app record, SKU, and primary locale.",
        "acceptance_gate": "App Store Connect record exists and matches the submitted bundle ID.",
    },
    {
        "key": "pricing_and_availability",
        "status": "owner_input_required",
        "field_hint": "Pricing, free/paid status, and availability",
        "draft": "",
        "owner_decision_required": "Confirm price tier, free/paid status, countries/regions, and release timing.",
        "acceptance_gate": "Pricing and availability are owner-approved before submission.",
    },
)

SCREENSHOT_SURFACES = (
    "Open user-selected media in the sandboxed app candidate.",
    "Show subtitle generation progress and resulting subtitle rows.",
    "Show the editor timeline with media preview, subtitle review, and safe editing controls.",
    "Show save/reopen or SRT export workflow evidence from the signed candidate.",
)

ALLOWED_COPY_CLAIMS = (
    "macOS subtitle generation and editing for user-selected media",
    "local project, subtitle review, save, reopen, and export workflows when verified for the submitted build",
    "optional local or remote model/network behavior only when it matches the shipped sandboxed candidate",
    "Apple Silicon first macOS support matching the submitted app's minimum OS and entitlement set",
)

SUBMISSION_BLOCKER_EXPLANATIONS = {
    "signed_app_bundle_missing": "No Apple Distribution signed .app candidate is available.",
    "signed_app_store_pkg_missing": "No signed Mac App Store .pkg exists.",
    "strict_codesign_verification_missing": "No strict codesign verification output exists for the exact .app.",
    "pkg_signature_verification_missing": "No pkgutil signature verification output exists for the exact .pkg.",
    "sandbox_smoke_missing": "Sandboxed workflow smoke proof is missing.",
    "app_store_connect_validation_missing": "No App Store Connect validation output exists for the exact .pkg.",
    "apple_distribution_codesign_identity_not_configured": "CODESIGN_IDENTITY is not configured for Apple Distribution signing.",
    "installer_identity_not_configured": "INSTALLER_IDENTITY is not configured for package signing.",
    "apple_distribution_identity_missing_from_keychain": "Local keychain proof does not show an Apple Distribution identity.",
    "installer_identity_missing_from_keychain": "Local keychain proof does not show a 3rd Party Mac Developer Installer identity.",
    "app_store_connect_auth_not_configured": "App Store Connect authentication is not configured for validation/upload.",
}


def _resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return root / path


def _write_json(path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _owner_input_matrix(readiness: dict[str, Any], owner_values: dict[str, Any]) -> list[dict[str, Any]]:
    non_code = readiness.get("non_code_submission_items") or {}
    normalized = owner_values.get("normalized_owner_inputs") or {}
    matrix: list[dict[str, Any]] = []
    source_audit_artifact = str(readiness.get("source_audit_artifact") or "")
    for key in NON_CODE_SUBMISSION_ITEMS:
        item = non_code.get(key) or {}
        owner_entry = normalized.get(key) or {}
        status = str(owner_entry.get("status") or item.get("status") or "owner_input_required")
        matrix.append(
            {
                "id": key,
                "key": key,
                "status": status,
                "app_store_field": OWNER_INPUT_FIELD_HINTS[key],
                "field_hint": OWNER_INPUT_FIELD_HINTS[key],
                "draft": item.get("draft", ""),
                "draft_source": str(item.get("source_doc") or ""),
                "owner_decision_required": item.get("owner_decision_required", "Owner confirmation required."),
                "acceptance_gate": item.get("acceptance_gate", "Owner-approved value is required before submission."),
                "blocking": status != "ready",
                "last_verified_artifact": source_audit_artifact,
                "owner_value": str(owner_entry.get("value") or ""),
                "owner_approval_evidence": str(owner_entry.get("evidence") or ""),
            }
        )
    return matrix


def _blocker_rows(readiness: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for blocker in readiness.get("blockers") or []:
        explanation = SUBMISSION_BLOCKER_EXPLANATIONS.get(blocker)
        if explanation is None and blocker.startswith("non_code_submission_item_pending:"):
            key = blocker.split(":", 1)[1]
            explanation = f"Owner input is still required for {OWNER_INPUT_FIELD_HINTS.get(key, key)}."
        rows.append(
            {
                "blocker": blocker,
                "status": "blocked",
                "explanation": explanation or "Submission readiness blocker remains open.",
            }
        )
    return rows


def _metadata_fill_matrix(owner_values: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = owner_values.get("normalized_app_store_connect_metadata") or {}
    rows: list[dict[str, Any]] = []
    for item in APP_STORE_CONNECT_METADATA_FIELDS:
        owner_entry = normalized.get(item["key"]) or {}
        status = str(owner_entry.get("status") or item["status"])
        rows.append(
            {
                "id": item["key"],
                "key": item["key"],
                "status": status,
                "app_store_field": item["field_hint"],
                "field_hint": item["field_hint"],
                "draft": item["draft"],
                "draft_source": "docs/planning_queue/ACTION_ITEMS.md and docs/APP_STORE_SUBMISSION_READINESS.md",
                "owner_decision_required": item["owner_decision_required"],
                "acceptance_gate": item["acceptance_gate"],
                "blocking": status != "ready",
                "last_verified_artifact": "",
                "owner_value": str(owner_entry.get("value") or ""),
                "owner_approval_evidence": str(owner_entry.get("evidence") or ""),
                "validation_errors": list(owner_entry.get("validation_errors") or []),
            }
        )
    return rows


def _public_readiness_snapshot(readiness: dict[str, Any]) -> dict[str, Any]:
    signing = readiness.get("signing_identities") or {}
    environment = readiness.get("environment") or {}
    submission_content = readiness.get("submission_content_audit") or {}
    return {
        "schema": readiness.get("schema"),
        "app_version": readiness.get("app_version"),
        "submission_target": readiness.get("submission_target"),
        "local_packaging_ready": bool(readiness.get("local_packaging_ready")),
        "app_store_submission_ready": bool(readiness.get("app_store_submission_ready")),
        "status": readiness.get("status"),
        "stoplight": readiness.get("stoplight"),
        "blocker_group_counts": readiness.get("blocker_group_counts"),
        "blockers": list(readiness.get("blockers") or []),
        "blocker_count": len(readiness.get("blockers") or []),
        "submission_content_audit": {
            "status": submission_content.get("status"),
            "item_count": submission_content.get("item_count"),
            "pending_owner_input_count": submission_content.get("pending_owner_input_count"),
            "pending_items": list(submission_content.get("pending_items") or []),
        },
        "signing_identity_summary": {
            "apple_development_present": bool(signing.get("apple_development_present")),
            "apple_distribution_present": bool(signing.get("apple_distribution_present")),
            "installer_distribution_present": bool(signing.get("installer_distribution_present")),
        },
        "environment_summary": {
            "codesign_identity_configured": bool(environment.get("codesign_identity_configured")),
            "installer_identity_configured": bool(environment.get("installer_identity_configured")),
            "app_store_connect_auth_configured": bool(environment.get("app_store_connect_auth_configured")),
        },
        "owner_metadata_values_preflight": {
            "provided": bool((readiness.get("owner_metadata_values_preflight") or {}).get("provided")),
            "ready": bool((readiness.get("owner_metadata_values_preflight") or {}).get("ready")),
            "issue_count": int((readiness.get("owner_metadata_values_preflight") or {}).get("issue_count") or 0),
            "owner_input_ready_count": int(
                (readiness.get("owner_metadata_values_preflight") or {}).get("owner_input_ready_count") or 0
            ),
            "owner_input_total": int(
                (readiness.get("owner_metadata_values_preflight") or {}).get("owner_input_total") or 0
            ),
            "app_store_connect_metadata_ready_count": int(
                (readiness.get("owner_metadata_values_preflight") or {}).get("app_store_connect_metadata_ready_count") or 0
            ),
            "app_store_connect_metadata_total": int(
                (readiness.get("owner_metadata_values_preflight") or {}).get("app_store_connect_metadata_total") or 0
            ),
            "forbidden_claim_scan": (readiness.get("owner_metadata_values_preflight") or {}).get("forbidden_claim_scan"),
        },
        "distribution_tracks": readiness.get("distribution_tracks"),
        "upload_execution_guard": readiness.get("upload_execution_guard"),
    }


def _forbidden_claim_scan(package: dict[str, Any]) -> dict[str, Any]:
    targets: dict[str, str] = {
        "review_notes_draft.body": str((package.get("review_notes_draft") or {}).get("body") or ""),
        "screenshots_plan.surfaces": "\n".join(package.get("screenshots_plan", {}).get("surfaces") or []),
        "copy_guardrails.allowed_claims": "\n".join(package.get("copy_guardrails", {}).get("allowed_claims") or []),
        "owner_input_matrix.drafts": "\n".join(str(item.get("draft") or "") for item in package.get("owner_input_matrix") or []),
        "app_store_connect_metadata_fill.drafts": "\n".join(
            str(item.get("draft") or "") for item in package.get("app_store_connect_metadata_fill") or []
        ),
        "owner_input_matrix.owner_values": "\n".join(
            str(item.get("owner_value") or "") for item in package.get("owner_input_matrix") or []
        ),
        "app_store_connect_metadata_fill.owner_values": "\n".join(
            str(item.get("owner_value") or "") for item in package.get("app_store_connect_metadata_fill") or []
        ),
    }
    matches: list[dict[str, str]] = []
    for field, text in targets.items():
        lowered = text.lower()
        for claim in FORBIDDEN_COPY_CLAIMS:
            if claim.lower() in lowered:
                matches.append({"field": field, "claim": claim})
    return {
        "status": "pass" if not matches else "fail",
        "match_count": len(matches),
        "matches": matches,
        "scanned_fields": sorted(targets),
        "note": "The configured forbidden-claims list itself is not scanned as product copy.",
    }


def build_metadata_package(
    *,
    root: Path = ROOT,
    output_dir: Path | None = None,
    app_path: Path | None = None,
    pkg_path: Path | None = None,
    owner_values_path: Path | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    output_dir = output_dir or root / "output" / "manual_verification" / "latest" / "app_store_metadata_owner_input_package"
    output_dir = _resolve_path(root, output_dir)
    readiness = build_readiness_report(
        root=root,
        app_path=app_path,
        pkg_path=pkg_path,
        output_dir=output_dir,
        owner_values_path=owner_values_path,
    )
    source_audit_artifact = str(output_dir / "source_readiness_snapshot.json")
    readiness["source_audit_artifact"] = source_audit_artifact
    app_version = str((readiness.get("info_plist_template") or {}).get("config_app_version") or "")
    owner_values = readiness.get("owner_metadata_values_preflight") or {}
    owner_inputs = _owner_input_matrix(readiness, owner_values)
    metadata_fill = _metadata_fill_matrix(owner_values)
    blockers = _blocker_rows(readiness)
    pending_owner_input_keys = [item["key"] for item in owner_inputs if item.get("status") != "ready"]
    pending_metadata_keys = [item["key"] for item in metadata_fill if item.get("status") != "ready"]
    package = {
        "schema": "ai_subtitle_studio.app_store_metadata_owner_input_package.v1",
        "root": str(root),
        "output_dir": str(output_dir),
        "source_doc": str(root / "docs" / "APP_STORE_SUBMISSION_READINESS.md"),
        "source_audit_artifact": source_audit_artifact,
        "APP_VERSION": app_version,
        "not_submission_proof": True,
        "owner_input_complete": bool(owner_values.get("ready")),
        "owner_values_preflight": owner_values,
        "app": {
            "name": EXPECTED_INFO_VALUES["CFBundleDisplayName"],
            "bundle_id": EXPECTED_INFO_VALUES["CFBundleIdentifier"],
            "version": app_version,
            "category": EXPECTED_INFO_VALUES["LSApplicationCategoryType"],
            "minimum_macos": EXPECTED_INFO_VALUES["LSMinimumSystemVersion"],
            "submission_target": SUBMISSION_TARGET,
        },
        "readiness_snapshot": {
            "status": readiness.get("status"),
            "local_packaging_ready": bool(readiness.get("local_packaging_ready")),
            "app_store_submission_ready": bool(readiness.get("app_store_submission_ready")),
            "blocker_count": len(readiness.get("blockers") or []),
            "pending_owner_input_count": (readiness.get("submission_content_audit") or {}).get("pending_owner_input_count"),
            "pending_owner_input_total": (readiness.get("submission_content_audit") or {}).get("item_count"),
            "pending_owner_input_keys": pending_owner_input_keys,
            "pending_app_store_connect_metadata_count": len(pending_metadata_keys),
            "pending_app_store_connect_metadata_keys": pending_metadata_keys,
            "distribution_tracks": readiness.get("distribution_tracks"),
            "upload_execution_guard": readiness.get("upload_execution_guard"),
        },
        "owner_input_matrix": owner_inputs,
        "app_store_connect_metadata_fill": metadata_fill,
        "review_notes_draft": {
            "status": "draft_owner_review_required",
            "body": (
                "AI Subtitle Studio uses sandboxed user-selected file access, app-scope bookmarks, "
                "audio input for STT workflows, optional local or remote model behavior, and a network "
                "client entitlement for configured model/network paths. Final review notes must be "
                "approved only after the signed/sandboxed smoke proves the exact submitted behavior."
            ),
        },
        "screenshots_plan": {
            "status": "blocked_until_signed_sandboxed_candidate",
            "capture_after": "signed_sandboxed_app_store_candidate",
            "surfaces": list(SCREENSHOT_SURFACES),
        },
        "copy_guardrails": {
            "allowed_claims": list(ALLOWED_COPY_CLAIMS),
            "forbidden_claims": list(FORBIDDEN_COPY_CLAIMS),
        },
        "submission_blockers": blockers,
        "official_references": OFFICIAL_REFERENCES,
        "source_readiness_snapshot": _public_readiness_snapshot(readiness),
    }
    package["forbidden_claim_scan"] = _forbidden_claim_scan(package)
    return package


def _metadata_checklist_md(package: dict[str, Any]) -> str:
    app = package["app"]
    readiness = package["readiness_snapshot"]
    lines = [
        "# App Store Metadata Checklist",
        "",
        f"- Status: `{readiness['status']}`",
        f"- Owner input complete: `{package['owner_input_complete']}`",
        f"- App Store submission ready: `{readiness['app_store_submission_ready']}`",
        f"- Local packaging ready: `{readiness['local_packaging_ready']}`",
        f"- Blocker count: `{readiness['blocker_count']}`",
        f"- Owner-input metadata pending: `{readiness['pending_owner_input_count']}` / `{readiness['pending_owner_input_total']}`",
        f"- App Store Connect metadata pending: `{readiness['pending_app_store_connect_metadata_count']}`",
        "",
        "## App Identity",
        "",
        f"- App name: `{app['name']}`",
        f"- Bundle ID: `{app['bundle_id']}`",
        f"- Version: `{app['version']}`",
        f"- Category: `{app['category']}`",
        f"- Minimum macOS: `{app['minimum_macos']}`",
        f"- Submission target: `{app['submission_target']}`",
        "",
        "## Owner Inputs Required",
        "",
    ]
    for item in package["owner_input_matrix"]:
        lines.append(f"- `{item['key']}`: `{item['status']}` - {item['field_hint']}")
    lines.extend(["", "## App Store Connect Metadata Fill", ""])
    for item in package["app_store_connect_metadata_fill"]:
        lines.append(f"- `{item['key']}`: `{item['status']}` - {item['field_hint']}")
    lines.extend(
        [
            "",
            "## Gate",
            "",
            "This package is an owner-input work packet. It is not App Store submission proof.",
            "Do not submit until signed package, sandbox smoke, App Store Connect validation, and owner-approved metadata all exist.",
            "",
        ]
    )
    return "\n".join(lines)


def _matrix_md(title: str, rows: list[dict[str, Any]]) -> str:
    lines = [
        f"# {title}",
        "",
        "| Key | Status | Field | Owner Decision Required | Acceptance Gate |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in rows:
        lines.append(
            "| {key} | `{status}` | {field} | {decision} | {gate} |".format(
                key=item["key"],
                status=item["status"],
                field=item["field_hint"],
                decision=str(item["owner_decision_required"]).replace("\n", " "),
                gate=str(item["acceptance_gate"]).replace("\n", " "),
            )
        )
    lines.append("")
    return "\n".join(lines)


def _owner_input_matrix_md(package: dict[str, Any]) -> str:
    return _matrix_md("Owner Input Matrix", package["owner_input_matrix"])


def _metadata_fill_matrix_md(package: dict[str, Any]) -> str:
    return _matrix_md("App Store Connect Metadata Fill Matrix", package["app_store_connect_metadata_fill"])


def _review_notes_md(package: dict[str, Any]) -> str:
    draft = package["review_notes_draft"]
    return "\n".join(
        [
            "# Review Notes Draft",
            "",
            f"- Status: `{draft['status']}`",
            "",
            draft["body"],
            "",
            "## Owner Approval Gate",
            "",
            "- Approve only after the signed/sandboxed candidate has passed workflow smoke.",
            "- Reference only behavior present in the submitted build.",
            "- Keep test account, fixture, or reviewer instructions concrete if Apple Review needs them.",
            "",
        ]
    )


def _screenshots_plan_md(package: dict[str, Any]) -> str:
    plan = package["screenshots_plan"]
    lines = [
        "# Screenshots Plan",
        "",
        f"- Status: `{plan['status']}`",
        f"- Capture after: `{plan['capture_after']}`",
        "",
        "## Required Surfaces",
        "",
    ]
    lines.extend(f"- {surface}" for surface in plan["surfaces"])
    lines.extend(
        [
            "",
            "## Gate",
            "",
            "Screenshots must come from the signed/sandboxed App Store candidate and match the submitted binary UI.",
            "",
        ]
    )
    return "\n".join(lines)


def _copy_guardrails_md(package: dict[str, Any]) -> str:
    guardrails = package["copy_guardrails"]
    lines = ["# Copy Guardrails", "", "## Allowed Claims", ""]
    lines.extend(f"- {claim}" for claim in guardrails["allowed_claims"])
    lines.extend(["", "## Forbidden Claims", ""])
    lines.extend(f"- {claim}" for claim in guardrails["forbidden_claims"])
    lines.extend(["", "Use the forbidden list as a rejection checklist for App Store copy before submission.", ""])
    return "\n".join(lines)


def _submission_blockers_md(package: dict[str, Any]) -> str:
    lines = [
        "# Submission Blockers",
        "",
        "These blockers must stay open until the exact proof surface exists.",
        "",
    ]
    for row in package["submission_blockers"]:
        lines.append(f"- `{row['blocker']}`: `{row['status']}` - {row['explanation']}")
    lines.append("")
    return "\n".join(lines)


def _package_summary_md(package: dict[str, Any]) -> str:
    readiness = package["readiness_snapshot"]
    scan = package["forbidden_claim_scan"]
    return "\n".join(
        [
            "# App Store Metadata Owner-Input Package",
            "",
            "This is an owner-input work packet. It is not packaging, upload, validation, or submission proof.",
            "",
            f"- Not submission proof: `{package['not_submission_proof']}`",
            f"- Status: `{readiness['status']}`",
            f"- Owner input complete: `{package['owner_input_complete']}`",
            f"- App Store submission ready: `{readiness['app_store_submission_ready']}`",
            f"- Submission target: `{package['app']['submission_target']}`",
            f"- App version: `{package['APP_VERSION']}`",
            f"- Pending owner-input items: `{readiness['pending_owner_input_count']}` / `{readiness['pending_owner_input_total']}`",
            f"- App Store Connect metadata pending: `{readiness['pending_app_store_connect_metadata_count']}`",
            f"- Forbidden claim scan: `{scan['status']}` with `{scan['match_count']}` matches",
            f"- Owner values preflight: `{(package.get('owner_values_preflight') or {}).get('ready')}` with `{(package.get('owner_values_preflight') or {}).get('issue_count')}` issues",
            f"- Upload confirmation required: `{bool((readiness.get('upload_execution_guard') or {}).get('upload_confirmation_required'))}`",
            f"- Upload confirmation env: `{(readiness.get('upload_execution_guard') or {}).get('upload_confirmation_env_var')}`",
            "",
            "## Required Next Proof",
            "",
            "- Apple Distribution signed app candidate",
            "- 3rd Party Mac Developer Installer signed package",
            "- Sandboxed workflow smoke",
            "- App Store Connect validation for the exact package",
            "- Owner-approved metadata, privacy, export compliance, screenshots, review notes, age rating, and release notes",
            "",
        ]
    )


def write_metadata_package(package: dict[str, Any], output_dir: Path | None = None) -> list[Path]:
    destination = output_dir or Path(package["output_dir"])
    destination.mkdir(parents=True, exist_ok=True)
    files = {
        "app_store_metadata_owner_input_package.json": package,
        "metadata_package.json": package,
        "owner_input_matrix.json": package["owner_input_matrix"],
        "app_store_connect_metadata_fill.json": package["app_store_connect_metadata_fill"],
        "owner_values_preflight.json": package["owner_values_preflight"],
        "forbidden_claim_scan.json": package["forbidden_claim_scan"],
        "source_readiness_snapshot.json": package["source_readiness_snapshot"],
    }
    text_files = {
        "app_store_metadata_owner_input_package.md": _package_summary_md(package),
        "metadata_checklist.md": _metadata_checklist_md(package),
        "owner_input_matrix.md": _owner_input_matrix_md(package),
        "app_store_connect_metadata_fill.md": _metadata_fill_matrix_md(package),
        "review_notes_draft.md": _review_notes_md(package),
        "screenshots_plan.md": _screenshots_plan_md(package),
        "copy_guardrails.md": _copy_guardrails_md(package),
        "submission_blockers.md": _submission_blockers_md(package),
    }
    written: list[Path] = []
    for name, payload in files.items():
        path = destination / name
        _write_json(path, payload)
        written.append(path)
    for name, text in text_files.items():
        path = destination / name
        _write_text(path, text)
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the owner-input package for Mac App Store metadata.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument(
        "--output-dir",
        default="output/manual_verification/latest/app_store_metadata_owner_input_package",
    )
    parser.add_argument("--app-path", default="")
    parser.add_argument("--pkg-path", default="")
    parser.add_argument("--owner-values-json", default=os.environ.get("APP_STORE_OWNER_METADATA_JSON", ""))
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    output_dir = _resolve_path(root, args.output_dir)
    package = build_metadata_package(
        root=root,
        output_dir=output_dir,
        app_path=Path(args.app_path).expanduser() if args.app_path else None,
        pkg_path=Path(args.pkg_path).expanduser() if args.pkg_path else None,
        owner_values_path=Path(args.owner_values_json).expanduser() if args.owner_values_json else None,
    )
    written = write_metadata_package(package, output_dir)
    print(json.dumps({"output_dir": str(output_dir), "files": [str(path) for path in written]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
