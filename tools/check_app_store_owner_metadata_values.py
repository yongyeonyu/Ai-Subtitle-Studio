#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime.config import APP_VERSION


OWNER_VALUES_SCHEMA = "ai_subtitle_studio.app_store_owner_metadata_values.v1"
EXPECTED_APP_NAME = "AI Subtitle Studio"
EXPECTED_BUNDLE_ID = "com.soseolgayumossi.aisubtitlestudio"
OWNER_INPUT_KEYS = (
    "privacy_policy_url",
    "privacy_data_type_answers",
    "export_compliance_answers",
    "mac_app_store_screenshots",
    "support_url",
    "app_review_notes",
    "age_rating_answers",
    "release_notes",
)
APP_STORE_CONNECT_METADATA_KEYS = (
    "app_name",
    "app_subtitle",
    "keywords",
    "description",
    "promotional_text",
    "marketing_url",
    "app_store_connect_record",
    "pricing_and_availability",
)
URL_OWNER_CONTROLLED_KEYS = {"privacy_policy_url", "support_url", "marketing_url"}
OPTIONAL_NOT_APPLICABLE_KEYS = {"marketing_url", "promotional_text"}
FORBIDDEN_COPY_CLAIMS = (
    "App Store ready",
    "Apple-approved",
    "fully native",
    "offline-only",
    "real-time",
    "100% accurate",
    "supports every video format",
    "no data leaves the device",
    "faster than other editors",
    "validated",
    "DMG validation proves Mac App Store submission readiness",
    "commercial NLE replacement",
    "Final Cut Pro-style",
    "full NLE",
    "native NLE",
    "real-time editing",
)


def _template_entry(*, note: str = "", owner_controlled: bool = False, screenshot_binding: bool = False) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "value": "",
        "approved": False,
        "evidence": "",
        "owner_controlled": bool(owner_controlled),
        "not_applicable": False,
        "note": note,
    }
    if screenshot_binding:
        entry["signed_candidate_artifact"] = ""
        entry["submitted_binary_match"] = False
    return entry


def build_owner_metadata_values_template(
    *,
    app_version: str = APP_VERSION,
    bundle_id: str = EXPECTED_BUNDLE_ID,
) -> dict[str, Any]:
    return {
        "schema": OWNER_VALUES_SCHEMA,
        "app_version": str(app_version),
        "bundle_id": str(bundle_id),
        "template_only_not_submission_proof": True,
        "instructions": [
            "Fill every value from owner-approved App Store Connect decisions.",
            "Keep approved=false until explicit owner approval evidence exists.",
            "Set owner_controlled=true only for public URLs controlled by the owner.",
            "Bind screenshots to the exact signed/sandboxed candidate before marking submitted_binary_match=true.",
            "Run tools/check_app_store_owner_metadata_values.py --values-json <path> after editing.",
        ],
        "owner_inputs": {
            "privacy_policy_url": _template_entry(
                note="Final public https privacy policy URL.",
                owner_controlled=False,
            ),
            "privacy_data_type_answers": _template_entry(
                note="Owner-approved App Privacy answers for files, audio/STT, optional model/network paths, diagnostics, analytics, and crash collection."
            ),
            "export_compliance_answers": _template_entry(
                note="Owner-approved Export Compliance answers for the shipped networking/encryption behavior."
            ),
            "mac_app_store_screenshots": _template_entry(
                note="Owner-approved screenshot manifest captured from the exact signed/sandboxed App Store candidate.",
                screenshot_binding=True,
            ),
            "support_url": _template_entry(
                note="Final public https support URL.",
                owner_controlled=False,
            ),
            "app_review_notes": _template_entry(
                note="Owner-approved App Review notes matching the exact submitted build behavior."
            ),
            "age_rating_answers": _template_entry(
                note="Owner-approved App Store age-rating questionnaire answers."
            ),
            "release_notes": _template_entry(
                note="Owner-approved release notes for this submitted version."
            ),
        },
        "app_store_connect_metadata": {
            "app_name": _template_entry(
                note=f"Must match {EXPECTED_APP_NAME!r} unless the app identity changes."
            ),
            "app_subtitle": _template_entry(
                note="Final App Store subtitle; avoid unsupported speed/readiness claims."
            ),
            "keywords": _template_entry(
                note="Owner-approved searchable keywords matching shipped behavior."
            ),
            "description": _template_entry(
                note="Final product description; forbidden-copy scan must pass."
            ),
            "promotional_text": _template_entry(
                note="Optional promotional text. If not used, set not_applicable=true and provide approval evidence."
            ),
            "marketing_url": _template_entry(
                note="Optional public https marketing URL. If not used, set not_applicable=true and provide approval evidence.",
                owner_controlled=False,
            ),
            "app_store_connect_record": _template_entry(
                note=f"Include team/app record/SKU/primary locale and bundle ID {bundle_id}."
            ),
            "pricing_and_availability": _template_entry(
                note="Owner-approved price tier, free/paid status, countries/regions, and release timing."
            ),
        },
    }


def _load_json(path: Path) -> tuple[dict[str, Any], str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, "owner_metadata_values_file_missing"
    except json.JSONDecodeError as exc:
        return {}, f"owner_metadata_values_json_invalid:{exc.msg}"
    if not isinstance(payload, dict):
        return {}, "owner_metadata_values_root_not_object"
    return payload, ""


def _section(payload: dict[str, Any], mapping_key: str, rows_key: str) -> dict[str, dict[str, Any]]:
    value = payload.get(mapping_key)
    if isinstance(value, dict):
        return {str(key): _entry_from_value(item) for key, item in value.items()}

    rows = payload.get(rows_key)
    if isinstance(rows, list):
        result: dict[str, dict[str, Any]] = {}
        for item in rows:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or item.get("id") or "")
            if key:
                result[key] = _entry_from_value(item)
        return result
    return {}


def _entry_from_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "value": str(value.get("value") or value.get("owner_value") or "").strip(),
            "approved": value.get("approved") is True,
            "evidence": str(value.get("evidence") or value.get("approval_evidence") or "").strip(),
            "owner_controlled": value.get("owner_controlled") is True,
            "not_applicable": value.get("not_applicable") is True,
            "signed_candidate_artifact": str(value.get("signed_candidate_artifact") or "").strip(),
            "submitted_binary_match": value.get("submitted_binary_match") is True,
        }
    return {
        "value": str(value or "").strip(),
        "approved": False,
        "evidence": "",
        "owner_controlled": False,
        "not_applicable": False,
        "signed_candidate_artifact": "",
        "submitted_binary_match": False,
    }


def _forbidden_matches(key: str, text: str) -> list[dict[str, str]]:
    lowered = text.lower()
    return [
        {"key": key, "claim": claim}
        for claim in FORBIDDEN_COPY_CLAIMS
        if claim.lower() in lowered
    ]


def _validate_entry(
    *,
    section: str,
    key: str,
    entry: dict[str, Any] | None,
    bundle_id: str,
) -> tuple[dict[str, Any], list[str], list[dict[str, str]]]:
    issues: list[str] = []
    matches: list[dict[str, str]] = []
    if entry is None:
        entry = _entry_from_value({})
        issues.append(f"{section}:{key}:missing")

    value = str(entry.get("value") or "").strip()
    not_applicable = bool(entry.get("not_applicable"))
    optional_not_applicable = key in OPTIONAL_NOT_APPLICABLE_KEYS and not_applicable

    if entry.get("approved") is not True:
        issues.append(f"{section}:{key}:owner_approval_missing")
    if not value and not optional_not_applicable:
        issues.append(f"{section}:{key}:value_missing")
    if not str(entry.get("evidence") or "").strip():
        issues.append(f"{section}:{key}:approval_evidence_missing")

    if key in URL_OWNER_CONTROLLED_KEYS and not optional_not_applicable:
        if not value.startswith("https://"):
            issues.append(f"{section}:{key}:https_url_required")
        if entry.get("owner_controlled") is not True:
            issues.append(f"{section}:{key}:owner_controlled_confirmation_missing")

    if key == "mac_app_store_screenshots":
        if not str(entry.get("signed_candidate_artifact") or "").strip():
            issues.append(f"{section}:{key}:signed_candidate_artifact_missing")
        if entry.get("submitted_binary_match") is not True:
            issues.append(f"{section}:{key}:submitted_binary_match_missing")

    if key == "app_store_connect_record":
        combined = f"{value}\n{entry.get('evidence') or ''}"
        if bundle_id not in combined:
            issues.append(f"{section}:{key}:bundle_id_binding_missing")
    if key == "app_name" and value != EXPECTED_APP_NAME:
        issues.append(f"{section}:{key}:app_name_mismatch")

    matches.extend(_forbidden_matches(f"{section}:{key}", value))
    normalized = {
        "key": key,
        "status": "ready" if not issues else "owner_input_required",
        "validation_errors": list(issues),
        "value": value,
        "approved": bool(entry.get("approved")),
        "evidence": str(entry.get("evidence") or "").strip(),
        "owner_controlled": bool(entry.get("owner_controlled")),
        "not_applicable": not_applicable,
        "signed_candidate_artifact": str(entry.get("signed_candidate_artifact") or "").strip(),
        "submitted_binary_match": bool(entry.get("submitted_binary_match")),
        "blocking": bool(issues),
    }
    return normalized, issues, matches


def check_owner_metadata_values(
    *,
    values_json: Path | None,
    app_version: str = APP_VERSION,
    bundle_id: str = EXPECTED_BUNDLE_ID,
) -> dict[str, Any]:
    issues: list[str] = []
    forbidden_matches: list[dict[str, str]] = []
    payload: dict[str, Any] = {}
    source_path = ""

    if values_json is None:
        issues.append("owner_metadata_values_path_missing")
    else:
        values_json = values_json.expanduser()
        source_path = str(values_json)
        payload, error = _load_json(values_json)
        if error:
            issues.append(error)

    if payload:
        if payload.get("schema") != OWNER_VALUES_SCHEMA:
            issues.append("owner_metadata_values_schema_mismatch")
        if str(payload.get("app_version") or "") != str(app_version):
            issues.append("owner_metadata_values_app_version_mismatch")

    owner_input_values = _section(payload, "owner_inputs", "owner_input_matrix")
    metadata_values = _section(payload, "app_store_connect_metadata", "app_store_connect_metadata_fill")
    normalized_owner_inputs: dict[str, dict[str, Any]] = {}
    normalized_metadata: dict[str, dict[str, Any]] = {}

    for key in OWNER_INPUT_KEYS:
        normalized, entry_issues, matches = _validate_entry(
            section="owner_inputs",
            key=key,
            entry=owner_input_values.get(key),
            bundle_id=bundle_id,
        )
        normalized_owner_inputs[key] = normalized
        issues.extend(entry_issues)
        forbidden_matches.extend(matches)

    for key in APP_STORE_CONNECT_METADATA_KEYS:
        normalized, entry_issues, matches = _validate_entry(
            section="app_store_connect_metadata",
            key=key,
            entry=metadata_values.get(key),
            bundle_id=bundle_id,
        )
        normalized_metadata[key] = normalized
        issues.extend(entry_issues)
        forbidden_matches.extend(matches)

    for match in forbidden_matches:
        issues.append(f"forbidden_claim:{match['key']}:{match['claim']}")

    missing_owner_inputs = [
        key for key, entry in normalized_owner_inputs.items() if entry.get("status") != "ready"
    ]
    missing_metadata = [
        key for key, entry in normalized_metadata.items() if entry.get("status") != "ready"
    ]

    return {
        "schema": "ai_subtitle_studio.app_store_owner_metadata_preflight.v1",
        "owner_values_schema": OWNER_VALUES_SCHEMA,
        "source_path": source_path,
        "provided": bool(source_path),
        "ready": not issues,
        "issue_count": len(issues),
        "issues": issues,
        "forbidden_claim_scan": {
            "status": "pass" if not forbidden_matches else "fail",
            "match_count": len(forbidden_matches),
            "matches": forbidden_matches,
        },
        "owner_input_ready_count": len(OWNER_INPUT_KEYS) - len(missing_owner_inputs),
        "owner_input_total": len(OWNER_INPUT_KEYS),
        "app_store_connect_metadata_ready_count": len(APP_STORE_CONNECT_METADATA_KEYS) - len(missing_metadata),
        "app_store_connect_metadata_total": len(APP_STORE_CONNECT_METADATA_KEYS),
        "missing_owner_input_keys": missing_owner_inputs,
        "missing_app_store_connect_metadata_keys": missing_metadata,
        "normalized_owner_inputs": normalized_owner_inputs,
        "normalized_app_store_connect_metadata": normalized_metadata,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate owner-approved Mac App Store metadata values.")
    parser.add_argument("--values-json", default="")
    parser.add_argument("--write-template", default="")
    parser.add_argument("--app-version", default=APP_VERSION)
    parser.add_argument("--bundle-id", default=EXPECTED_BUNDLE_ID)
    args = parser.parse_args()

    if args.write_template:
        template_path = Path(args.write_template).expanduser()
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_text(
            json.dumps(
                build_owner_metadata_values_template(
                    app_version=args.app_version,
                    bundle_id=args.bundle_id,
                ),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"template": str(template_path), "schema": OWNER_VALUES_SCHEMA}, ensure_ascii=False))
        return 0

    if not args.values_json:
        parser.error("--values-json is required unless --write-template is used")

    result = check_owner_metadata_values(
        values_json=Path(args.values_json),
        app_version=args.app_version,
        bundle_id=args.bundle_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ready"] else 65


if __name__ == "__main__":
    raise SystemExit(main())
