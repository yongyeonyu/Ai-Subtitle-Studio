#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_UPLOAD_GATES = (
    "version_lock_ready",
    "packaging_template_ready",
    "signed_app_bundle_ready",
    "signed_app_store_pkg_ready",
    "strict_codesign_verification_ready",
    "pkg_signature_verification_ready",
    "signed_artifacts_ready",
    "sandbox_smoke_ready",
    "app_store_connect_validation_ready",
    "apple_distribution_identity_ready",
    "installer_identity_ready",
    "app_store_connect_auth_ready",
    "owner_metadata_ready",
    "app_store_submission_ready",
)


def _same_path(left: str | Path, right: str | Path) -> bool:
    return Path(left).expanduser().resolve(strict=False) == Path(right).expanduser().resolve(strict=False)


def check_upload_preflight(*, readiness_json: Path, pkg_path: Path) -> dict[str, Any]:
    issues: list[str] = []
    readiness_json = readiness_json.expanduser()
    pkg_path = pkg_path.expanduser()

    if not readiness_json.is_file():
        issues.append("readiness_json_missing")
        payload: dict[str, Any] = {}
    else:
        try:
            payload = json.loads(readiness_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            payload = {}
            issues.append(f"readiness_json_invalid:{exc.msg}")

    if not pkg_path.is_file():
        issues.append("pkg_path_missing")

    blockers = list(payload.get("blockers") or [])
    if blockers:
        issues.append("readiness_blockers_present")

    if payload.get("app_store_submission_ready") is not True:
        issues.append("app_store_submission_ready_not_true")

    gates = payload.get("submission_gate_summary") if isinstance(payload.get("submission_gate_summary"), dict) else {}
    missing_gates = [gate for gate in REQUIRED_UPLOAD_GATES if gates.get(gate) is not True]
    if missing_gates:
        issues.append("submission_gates_not_ready:" + ",".join(missing_gates))

    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    report_pkg = artifacts.get("app_store_pkg") if isinstance(artifacts.get("app_store_pkg"), dict) else {}
    report_pkg_path = str(report_pkg.get("path") or "")
    if not report_pkg_path:
        issues.append("readiness_pkg_path_missing")
    elif not _same_path(report_pkg_path, pkg_path):
        issues.append("readiness_pkg_path_mismatch")

    if report_pkg and report_pkg.get("is_file") is not True:
        issues.append("readiness_pkg_not_marked_file")

    return {
        "schema": "ai_subtitle_studio.app_store_upload_preflight.v1",
        "ready": not issues,
        "issues": issues,
        "readiness_json": str(readiness_json),
        "pkg_path": str(pkg_path),
        "app_store_submission_ready": bool(payload.get("app_store_submission_ready")),
        "blocker_count": len(blockers),
        "required_gates": list(REQUIRED_UPLOAD_GATES),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate that an App Store upload has exact readiness proof.")
    parser.add_argument("--readiness-json", required=True)
    parser.add_argument("--pkg-path", required=True)
    args = parser.parse_args()

    result = check_upload_preflight(
        readiness_json=Path(args.readiness_json),
        pkg_path=Path(args.pkg_path),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if not result["ready"]:
        print("App Store upload preflight failed: " + ", ".join(result["issues"]), file=sys.stderr)
        return 65
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
