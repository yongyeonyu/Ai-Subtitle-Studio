#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PACKAGING_FILES = (
    "AI Subtitle Studio.entitlements",
    "Info.plist.template",
    "build_app_bundle.sh",
    "sign_app_bundle.sh",
    "validate_app_bundle.sh",
    "build_app_store_pkg.sh",
    "upload_app_store_build.sh",
)

REQUIRED_ENTITLEMENTS = {
    "com.apple.security.app-sandbox": True,
    "com.apple.security.files.user-selected.read-write": True,
    "com.apple.security.files.bookmarks.app-scope": True,
    "com.apple.security.network.client": True,
    "com.apple.security.device.audio-input": True,
}

EXPECTED_INFO_VALUES = {
    "CFBundleIdentifier": "com.soseolgayumossi.aisubtitlestudio",
    "CFBundleDisplayName": "AI Subtitle Studio",
    "CFBundleExecutable": "AI Subtitle Studio",
    "CFBundleName": "AI Subtitle Studio",
    "CFBundlePackageType": "APPL",
    "LSApplicationCategoryType": "public.app-category.video",
    "LSMinimumSystemVersion": "14.0",
}

REQUIRED_INFO_KEYS = (
    "CFBundleShortVersionString",
    "CFBundleVersion",
    "NSDocumentsFolderUsageDescription",
    "NSMicrophoneUsageDescription",
)

NON_CODE_SUBMISSION_ITEMS = (
    "privacy_policy_url",
    "privacy_data_type_answers",
    "export_compliance_answers",
    "mac_app_store_screenshots",
    "support_url",
    "app_review_notes",
    "age_rating_answers",
    "release_notes",
)

SUBMISSION_CONTENT_DRAFTS = {
    "privacy_policy_url": {
        "draft": "Pending owner-provided public privacy policy URL.",
        "owner_decision": "Provide the final public URL to enter in App Store Connect.",
        "acceptance_gate": "URL is owner-approved and reachable before submission metadata entry.",
    },
    "privacy_data_type_answers": {
        "draft": (
            "AI Subtitle Studio handles user-selected media, subtitle, audio, and project files; "
            "supports optional STT/model/network workflows; and writes local diagnostics/trace artifacts. "
            "Owner must confirm analytics, crash-reporting, third-party model, and data-linkage policy."
        ),
        "owner_decision": (
            "Confirm App Store Connect App Privacy answers for files, audio/STT, optional network/model calls, "
            "diagnostics, analytics, and crash collection."
        ),
        "acceptance_gate": "All App Privacy answers are owner-approved and match the shipped sandboxed app behavior.",
    },
    "export_compliance_answers": {
        "draft": "Pending owner/legal confirmation for encryption/export compliance answers.",
        "owner_decision": (
            "Confirm whether the shipped app's networking, TLS use, model downloads, or account/API features "
            "require a specific export compliance answer."
        ),
        "acceptance_gate": "Export compliance answers are owner-approved before App Store Connect submission.",
    },
    "mac_app_store_screenshots": {
        "draft": (
            "Capture screenshots only from the signed/sandboxed App Store candidate, covering generation, "
            "editor timeline, subtitle review/editing, and export/save workflow."
        ),
        "owner_decision": "Approve the final screenshot set and captions/crop after the signed candidate exists.",
        "acceptance_gate": "Screenshot files exist, match the submitted binary UI, and are owner-approved.",
    },
    "support_url": {
        "draft": "Pending owner-provided public support URL.",
        "owner_decision": "Provide the final support URL.",
        "acceptance_gate": "Support URL is owner-approved and reachable before metadata entry.",
    },
    "app_review_notes": {
        "draft": (
            "Explain sandboxed user-selected file access, app-scope bookmarks, audio/STT workflow, optional "
            "local/remote model behavior, network entitlement purpose, and any review fixture or account notes."
        ),
        "owner_decision": "Approve review notes after the signed/sandboxed smoke proves the exact submitted behavior.",
        "acceptance_gate": "Review notes are owner-approved and reference only behavior present in the submitted build.",
    },
    "age_rating_answers": {
        "draft": "Pending owner confirmation for App Store age-rating questionnaire answers.",
        "owner_decision": "Confirm all age-rating answers for the actual submitted feature set.",
        "acceptance_gate": "Age-rating answers are owner-approved before submission.",
    },
    "release_notes": {
        "draft": "Pending owner-approved version copy for the App Store release notes.",
        "owner_decision": "Approve final release notes for the submitted version.",
        "acceptance_gate": "Release notes are owner-approved, match the submitted version, and avoid unsupported performance or quality claims.",
    },
}

SUBMISSION_TARGET = "mac_app_store_pkg"

NON_DESTRUCTIVE_NEXT_STEPS = (
    "Keep the Mac App Store package track separate from the beta DMG track.",
    "Fill owner-provided App Store Connect metadata answers in docs/APP_STORE_SUBMISSION_READINESS.md.",
    "Run this audit again after metadata or packaging-template changes.",
)

OWNER_APPROVAL_REQUIRED_ACTIONS = (
    "packaging/macos/build_app_bundle.sh",
    "packaging/macos/sign_app_bundle.sh",
    "packaging/macos/build_app_store_pkg.sh",
    "packaging/macos/upload_app_store_build.sh validate",
    "packaging/macos/upload_app_store_build.sh upload",
    "packaging/macos/notarize_app_bundle.sh",
    "packaging/macos/notarize_dmg.sh",
    "packaging/macos/build_beta_dmg.sh",
    "packaging/macos/create_dmg.sh",
)

OFFICIAL_REFERENCES = {
    "upload_builds": "https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/",
    "app_privacy": "https://developer.apple.com/help/app-store-connect/manage-app-information/manage-app-privacy",
    "export_compliance": "https://developer.apple.com/help/app-store-connect/manage-app-information/overview-of-export-compliance",
    "screenshots": "https://developer.apple.com/help/app-store-connect/manage-app-information/upload-app-previews-and-screenshots",
    "app_sandbox": "https://developer.apple.com/help/app-store-connect/reference/app-uploads/app-sandbox-information",
}


def _path_status(path: Path) -> dict[str, Any]:
    expanded = path.expanduser()
    exists = expanded.exists()
    return {
        "path": str(expanded),
        "exists": exists,
        "is_file": expanded.is_file() if exists else False,
        "is_dir": expanded.is_dir() if exists else False,
        "is_executable": os.access(expanded, os.X_OK) if exists else False,
    }


def _load_plist(path: Path) -> tuple[dict[str, Any], str]:
    try:
        with path.open("rb") as fh:
            value = plistlib.load(fh)
        if isinstance(value, dict):
            return value, ""
        return {}, "plist root is not a dictionary"
    except Exception as exc:
        return {}, str(exc)


def _read_app_version(root: Path) -> str:
    config_path = root / "core" / "runtime" / "config.py"
    if not config_path.is_file():
        return ""
    match = re.search(r'^APP_VERSION\s*=\s*[\'"]([^\'"]+)[\'"]', config_path.read_text(encoding="utf-8"), re.M)
    return match.group(1) if match else ""


def _check_packaging_files(root: Path) -> dict[str, Any]:
    packaging_dir = root / "packaging" / "macos"
    files: dict[str, Any] = {}
    blockers: list[str] = []
    for name in REQUIRED_PACKAGING_FILES:
        status = _path_status(packaging_dir / name)
        files[name] = status
        if not status["is_file"]:
            blockers.append(f"packaging_file_missing:{name}")
        elif name.endswith(".sh") and not status["is_executable"]:
            blockers.append(f"packaging_script_not_executable:{name}")
    return {"files": files, "blockers": blockers}


def _check_entitlements(root: Path) -> dict[str, Any]:
    path = root / "packaging" / "macos" / "AI Subtitle Studio.entitlements"
    values, error = _load_plist(path)
    blockers: list[str] = []
    required: dict[str, Any] = {}
    for key, expected in REQUIRED_ENTITLEMENTS.items():
        actual = values.get(key)
        ok = actual is expected
        required[key] = {"expected": expected, "actual": actual, "ok": ok}
        if not ok:
            blockers.append(f"entitlement_mismatch:{key}")
    temporary_exceptions = sorted(str(key) for key in values if str(key).startswith("com.apple.security.temporary-exception"))
    if error:
        blockers.append("entitlements_parse_failed")
    return {
        "path": str(path),
        "parse_error": error,
        "required": required,
        "temporary_exceptions": temporary_exceptions,
        "blockers": blockers,
    }


def _check_info_template(root: Path) -> dict[str, Any]:
    path = root / "packaging" / "macos" / "Info.plist.template"
    values, error = _load_plist(path)
    blockers: list[str] = []
    expected_values: dict[str, Any] = {}
    for key, expected in EXPECTED_INFO_VALUES.items():
        actual = values.get(key)
        ok = actual == expected
        expected_values[key] = {"expected": expected, "actual": actual, "ok": ok}
        if not ok:
            blockers.append(f"info_value_mismatch:{key}")
    required_keys: dict[str, Any] = {}
    for key in REQUIRED_INFO_KEYS:
        actual = values.get(key)
        ok = bool(actual)
        required_keys[key] = {"actual": actual, "ok": ok}
        if not ok:
            blockers.append(f"info_key_missing:{key}")
    config_version = _read_app_version(root)
    version_placeholders_ok = (
        values.get("CFBundleShortVersionString") == "__APP_VERSION__"
        and values.get("CFBundleVersion") == "__APP_VERSION__"
        and bool(config_version)
    )
    if not version_placeholders_ok:
        blockers.append("bundle_version_template_not_linked_to_config")
    if error:
        blockers.append("info_plist_template_parse_failed")
    return {
        "path": str(path),
        "parse_error": error,
        "expected_values": expected_values,
        "required_keys": required_keys,
        "config_app_version": config_version,
        "version_placeholders_ok": version_placeholders_ok,
        "blockers": blockers,
    }


def _check_environment() -> dict[str, Any]:
    asc_api_ready = bool(os.environ.get("ASC_API_KEY")) and bool(os.environ.get("ASC_API_ISSUER"))
    asc_password_ready = bool(os.environ.get("ASC_USERNAME")) and bool(os.environ.get("ASC_PASSWORD"))
    return {
        "codesign_identity_configured": bool(os.environ.get("CODESIGN_IDENTITY")),
        "installer_identity_configured": bool(os.environ.get("INSTALLER_IDENTITY")),
        "app_store_connect_auth_configured": asc_api_ready or asc_password_ready,
        "notary_keychain_profile_configured": bool(os.environ.get("NOTARY_KEYCHAIN_PROFILE")),
    }


def _parse_security_identities(output: str) -> list[str]:
    identities: list[str] = []
    for line in output.splitlines():
        match = re.search(r'^\s*\d+\)\s+[0-9A-Fa-f]+\s+"([^"]+)"', line)
        if match:
            identities.append(match.group(1))
    return identities


def _run_security_find_identity(args: list[str]) -> dict[str, Any]:
    security = shutil.which("security")
    if not security:
        return {
            "available": False,
            "returncode": None,
            "stdout": "",
            "stderr": "security command not found",
            "identities": [],
        }
    try:
        result = subprocess.run(
            [security, "find-identity", "-v", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        return {
            "available": True,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "identities": [],
        }
    return {
        "available": True,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "identities": _parse_security_identities(result.stdout),
    }


def _check_local_signing_identities() -> dict[str, Any]:
    codesigning = _run_security_find_identity(["-p", "codesigning"])
    all_identities = _run_security_find_identity([])
    identity_names = sorted(set(codesigning["identities"]) | set(all_identities["identities"]))

    def _has(prefix: str) -> bool:
        return any(name.startswith(prefix) for name in identity_names)

    return {
        "security_command_available": bool(codesigning["available"] or all_identities["available"]),
        "codesigning_identities": codesigning["identities"],
        "all_identities": all_identities["identities"],
        "identity_names": identity_names,
        "apple_development_present": _has("Apple Development:"),
        "apple_distribution_present": _has("Apple Distribution:"),
        "installer_distribution_present": _has("3rd Party Mac Developer Installer:"),
        "raw": {
            "codesigning": codesigning,
            "all": all_identities,
        },
    }


def _check_artifacts(app_path: Path, pkg_path: Path, output_dir: Path) -> dict[str, Any]:
    app_status = _path_status(app_path)
    pkg_status = _path_status(pkg_path)
    sandbox_smoke = output_dir / "sandbox_smoke_result.json"
    asc_validation = output_dir / "app_store_connect_validation.xml"
    return {
        "app_bundle": app_status,
        "app_store_pkg": pkg_status,
        "sandbox_smoke": _path_status(sandbox_smoke),
        "app_store_connect_validation": _path_status(asc_validation),
    }


def _submission_content_items(root: Path) -> dict[str, dict[str, Any]]:
    doc_path = root / "docs" / "APP_STORE_SUBMISSION_READINESS.md"
    doc_status = _path_status(doc_path)
    items: dict[str, dict[str, Any]] = {}
    for name in NON_CODE_SUBMISSION_ITEMS:
        draft = dict(SUBMISSION_CONTENT_DRAFTS.get(name) or {})
        items[name] = {
            "status": "owner_input_required",
            "source_doc": str(doc_path),
            "source_doc_exists": bool(doc_status["is_file"]),
            "draft_available": bool(str(draft.get("draft") or "").strip()),
            "draft": draft.get("draft", ""),
            "owner_decision_required": draft.get("owner_decision", "Owner confirmation required."),
            "acceptance_gate": draft.get("acceptance_gate", "Owner-approved value is required before submission."),
        }
    return items


def _submission_content_summary(items: dict[str, dict[str, Any]]) -> dict[str, Any]:
    pending = [name for name, item in items.items() if item.get("status") != "ready"]
    return {
        "status": "blocked" if pending else "ready",
        "item_count": len(items),
        "pending_owner_input_count": len(pending),
        "draft_available_count": sum(1 for item in items.values() if item.get("draft_available")),
        "pending_items": pending,
    }


def _distribution_tracks(*, app_store_submission_ready: bool, pkg_path: Path) -> dict[str, Any]:
    return {
        "mac_app_store_pkg": {
            "target_role": "primary_submission_target",
            "status": "ready" if app_store_submission_ready else "blocked",
            "artifact_path": str(pkg_path.expanduser()),
            "requires_owner_approval_before_build": True,
            "requires": [
                "signed_app_bundle",
                "strict_codesign_verification",
                "signed_app_store_pkg",
                "pkg_signature_verification",
                "sandbox_smoke",
                "app_store_connect_validation",
                "non_code_submission_metadata",
            ],
        },
        "developer_id_beta_dmg": {
            "target_role": "separate_opt_in_beta_distribution",
            "status": "opt_in_hold",
            "artifact_path": "dist/macos/AI Subtitle Studio.dmg",
            "requires_owner_approval_before_build": True,
            "not_submission_evidence": True,
            "note": "A beta DMG is useful for Developer ID distribution, but it is not Mac App Store submission proof.",
        },
    }


def build_readiness_report(
    *,
    root: Path = ROOT,
    app_path: Path | None = None,
    pkg_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    app_path = app_path or (root / "dist" / "macos" / "AI Subtitle Studio.app")
    pkg_path = pkg_path or (root / "dist" / "macos" / "AI Subtitle Studio.pkg")
    output_dir = output_dir or (root / "output" / "manual_verification" / "latest" / "app_store_readiness_audit")

    packaging = _check_packaging_files(root)
    entitlements = _check_entitlements(root)
    info = _check_info_template(root)
    environment = _check_environment()
    signing_identities = _check_local_signing_identities()
    artifacts = _check_artifacts(app_path, pkg_path, output_dir)

    blockers: list[str] = []
    blockers.extend(packaging["blockers"])
    blockers.extend(entitlements["blockers"])
    blockers.extend(info["blockers"])

    if not artifacts["app_bundle"]["is_dir"]:
        blockers.append("signed_app_bundle_missing")
    if not artifacts["app_store_pkg"]["is_file"]:
        blockers.append("signed_app_store_pkg_missing")
    if not artifacts["sandbox_smoke"]["is_file"]:
        blockers.append("sandbox_smoke_missing")
    if not artifacts["app_store_connect_validation"]["is_file"]:
        blockers.append("app_store_connect_validation_missing")
    if not environment["codesign_identity_configured"]:
        blockers.append("apple_distribution_codesign_identity_not_configured")
    if not environment["installer_identity_configured"]:
        blockers.append("installer_identity_not_configured")
    if not signing_identities["apple_distribution_present"]:
        blockers.append("apple_distribution_identity_missing_from_keychain")
    if not signing_identities["installer_distribution_present"]:
        blockers.append("installer_identity_missing_from_keychain")
    if not environment["app_store_connect_auth_configured"]:
        blockers.append("app_store_connect_auth_not_configured")

    non_code = _submission_content_items(root)
    submission_content = _submission_content_summary(non_code)
    blockers.extend(f"non_code_submission_item_pending:{name}" for name in NON_CODE_SUBMISSION_ITEMS)

    local_packaging_ready = not (
        packaging["blockers"]
        or entitlements["blockers"]
        or info["blockers"]
    )
    app_store_submission_ready = not blockers
    return {
        "schema": "ai_subtitle_studio.app_store_readiness.v1",
        "root": str(root),
        "submission_target": SUBMISSION_TARGET,
        "local_packaging_ready": local_packaging_ready,
        "app_store_submission_ready": app_store_submission_ready,
        "status": "ready" if app_store_submission_ready else "blocked",
        "blockers": blockers,
        "distribution_tracks": _distribution_tracks(
            app_store_submission_ready=app_store_submission_ready,
            pkg_path=pkg_path,
        ),
        "packaging": packaging,
        "entitlements": entitlements,
        "info_plist_template": info,
        "environment": environment,
        "signing_identities": signing_identities,
        "artifacts": artifacts,
        "submission_content_audit": submission_content,
        "non_code_submission_items": non_code,
        "non_destructive_next_steps": list(NON_DESTRUCTIVE_NEXT_STEPS),
        "owner_approval_required_actions": list(OWNER_APPROVAL_REQUIRED_ACTIONS),
        "official_references": OFFICIAL_REFERENCES,
        "next_owner_approved_commands": [
            "CODESIGN_IDENTITY='Apple Distribution: ...' packaging/macos/build_app_bundle.sh",
            "CODESIGN_IDENTITY='Apple Distribution: ...' packaging/macos/sign_app_bundle.sh",
            "packaging/macos/validate_app_bundle.sh",
            "INSTALLER_IDENTITY='3rd Party Mac Developer Installer: ...' packaging/macos/build_app_store_pkg.sh",
            "ASC_API_KEY=... ASC_API_ISSUER=... packaging/macos/upload_app_store_build.sh validate",
        ],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _markdown_report(payload: dict[str, Any]) -> str:
    blockers = list(payload.get("blockers") or [])
    artifacts = payload.get("artifacts") or {}
    environment = payload.get("environment") or {}
    signing_identities = payload.get("signing_identities") or {}
    entitlements = payload.get("entitlements") or {}
    tracks = payload.get("distribution_tracks") or {}
    non_code = payload.get("non_code_submission_items") or {}
    submission_content = payload.get("submission_content_audit") or {}
    lines = [
        "# Mac App Store Readiness Audit",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Submission target: `{payload.get('submission_target')}`",
        f"- Local packaging ready: `{bool(payload.get('local_packaging_ready'))}`",
        f"- App Store submission ready: `{bool(payload.get('app_store_submission_ready'))}`",
        f"- Blocker count: `{len(blockers)}`",
        "",
        "## Distribution Track Boundaries",
        "",
    ]
    for name, track in tracks.items():
        lines.append(
            f"- `{name}`: role `{track.get('target_role')}`, status `{track.get('status')}`, artifact `{track.get('artifact_path')}`"
        )
        if track.get("not_submission_evidence"):
            lines.append("- DMG track is not Mac App Store submission evidence.")
    lines.extend(
        [
            "",
            "## Non-Destructive Next Steps",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in payload.get("non_destructive_next_steps") or [])
    lines.extend(
        [
            "",
            "## Non-Code Submission Items",
            "",
        ]
    )
    lines.extend(
        [
            f"- Submission content status: `{submission_content.get('status')}`",
            f"- Pending owner-input items: `{submission_content.get('pending_owner_input_count')}` / `{submission_content.get('item_count')}`",
            f"- Drafted item count: `{submission_content.get('draft_available_count')}`",
            "",
        ]
    )
    for key, value in sorted(non_code.items()):
        lines.extend(
            [
                f"### {key}",
                "",
                f"- Status: `{value.get('status')}`",
                f"- Draft available: `{bool(value.get('draft_available'))}`",
                f"- Draft: {value.get('draft')}",
                f"- Owner decision required: {value.get('owner_decision_required')}",
                f"- Acceptance gate: {value.get('acceptance_gate')}",
                "",
            ]
        )
    lines.extend(
        [
            "",
            "## Artifact Gate",
            "",
            f"- App bundle: `{(artifacts.get('app_bundle') or {}).get('path')}` / exists `{(artifacts.get('app_bundle') or {}).get('is_dir')}`",
            f"- App Store pkg: `{(artifacts.get('app_store_pkg') or {}).get('path')}` / exists `{(artifacts.get('app_store_pkg') or {}).get('is_file')}`",
            f"- Sandbox smoke: exists `{(artifacts.get('sandbox_smoke') or {}).get('is_file')}`",
            f"- App Store Connect validation: exists `{(artifacts.get('app_store_connect_validation') or {}).get('is_file')}`",
            "",
            "## Signing And Auth Gate",
            "",
            f"- `CODESIGN_IDENTITY`: configured `{bool(environment.get('codesign_identity_configured'))}`",
            f"- `INSTALLER_IDENTITY`: configured `{bool(environment.get('installer_identity_configured'))}`",
            f"- App Store Connect auth: configured `{bool(environment.get('app_store_connect_auth_configured'))}`",
            f"- Apple Development identity present: `{bool(signing_identities.get('apple_development_present'))}`",
            f"- Apple Distribution identity present: `{bool(signing_identities.get('apple_distribution_present'))}`",
            f"- Installer identity present: `{bool(signing_identities.get('installer_distribution_present'))}`",
            "",
            "### Local Keychain Identities",
            "",
            f"- security command available: `{bool(signing_identities.get('security_command_available'))}`",
        ]
    )
    identity_names = list(signing_identities.get("identity_names") or [])
    if identity_names:
        lines.extend(f"- `{name}`" for name in identity_names)
    else:
        lines.append("- `none`")
    lines.extend(
        [
            "",
            "## Entitlements",
            "",
            f"- Temporary exception entitlements: `{', '.join(entitlements.get('temporary_exceptions') or []) or 'none'}`",
        ]
    )
    for key, item in sorted((entitlements.get("required") or {}).items()):
        lines.append(f"- `{key}`: `{item.get('actual')}`")
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- `{blocker}`" for blocker in blockers)
    lines.extend(
        [
            "",
            "## Official References",
            "",
            "- App Store Connect build upload: <https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/>",
            "- App privacy: <https://developer.apple.com/help/app-store-connect/manage-app-information/manage-app-privacy>",
            "- Export compliance: <https://developer.apple.com/help/app-store-connect/manage-app-information/overview-of-export-compliance>",
            "- Screenshots and previews: <https://developer.apple.com/help/app-store-connect/manage-app-information/upload-app-previews-and-screenshots>",
            "- App Sandbox information: <https://developer.apple.com/help/app-store-connect/reference/app-uploads/app-sandbox-information>",
            "",
            "## Next Owner-Approved Commands",
            "",
            "These commands are intentionally not executed by this audit.",
            "",
            "Owner approval is required before these actions:",
            "",
        ]
    )
    lines.extend(f"- `{item}`" for item in payload.get("owner_approval_required_actions") or [])
    lines.extend(
        [
            "",
            "```bash",
        ]
    )
    lines.extend(str(item) for item in payload.get("next_owner_approved_commands") or [])
    lines.extend(["```", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Mac App Store submission readiness without building or uploading.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--app-path", default="")
    parser.add_argument("--pkg-path", default="")
    parser.add_argument("--output-dir", default="output/manual_verification/latest/app_store_readiness_audit_20260627")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser()
    root = Path(args.root).expanduser()
    payload = build_readiness_report(
        root=root,
        app_path=Path(args.app_path).expanduser() if args.app_path else None,
        pkg_path=Path(args.pkg_path).expanduser() if args.pkg_path else None,
        output_dir=output_dir,
    )
    _write_json(output_dir / "app_store_readiness_audit.json", payload)
    _write_text(output_dir / "app_store_readiness_audit.md", _markdown_report(payload))
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
