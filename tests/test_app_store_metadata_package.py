import json
import subprocess
import sys
from pathlib import Path

from core.runtime import config
from tools import audit_app_store_readiness
from tools.audit_app_store_readiness import EXPECTED_INFO_VALUES, NON_CODE_SUBMISSION_ITEMS
from tools.check_app_store_owner_metadata_values import OWNER_VALUES_SCHEMA
from tools.generate_app_store_metadata_package import build_metadata_package, write_metadata_package


ROOT = Path(__file__).resolve().parents[1]


def _write_valid_submission_proofs(output_dir: Path, app_path: Path, pkg_path: Path) -> None:
    (output_dir / "app_codesign_verify.txt").write_text(
        f"{app_path}: valid on disk\n{app_path}: satisfies its Designated Requirement\n",
        encoding="utf-8",
    )
    (output_dir / "pkgutil_check_signature.txt").write_text(
        f"Package \"{pkg_path}\":\n   Status: signed by a certificate trusted by Mac OS X\n",
        encoding="utf-8",
    )
    (output_dir / "sandbox_smoke_result.json").write_text('{"status":"passed"}', encoding="utf-8")
    (output_dir / "app_store_connect_validation.xml").write_text(
        f"No errors validating {pkg_path}\n",
        encoding="utf-8",
    )


def _approved(value: str, *, owner_controlled: bool = False, **extra):
    payload = {
        "value": value,
        "approved": True,
        "evidence": "owner approval 2026-06-29",
        "owner_controlled": owner_controlled,
    }
    payload.update(extra)
    return payload


def _owner_values_payload(description: str = "Create, review, save, reopen, and export subtitles.") -> dict:
    return {
        "schema": OWNER_VALUES_SCHEMA,
        "app_version": config.APP_VERSION,
        "owner_inputs": {
            "privacy_policy_url": _approved("https://example.com/privacy", owner_controlled=True),
            "privacy_data_type_answers": _approved("User-selected media, optional STT, diagnostics."),
            "export_compliance_answers": _approved("Standard TLS/network behavior as configured."),
            "mac_app_store_screenshots": _approved(
                "Approved screenshot manifest for the signed sandboxed candidate.",
                signed_candidate_artifact="dist/macos/AI Subtitle Studio.app",
                submitted_binary_match=True,
            ),
            "support_url": _approved("https://example.com/support", owner_controlled=True),
            "app_review_notes": _approved("Sandboxed user-selected file access and optional STT/model workflow notes."),
            "age_rating_answers": _approved("Owner-approved age rating answers."),
            "release_notes": _approved("Owner-approved release notes."),
        },
        "app_store_connect_metadata": {
            "app_name": _approved(EXPECTED_INFO_VALUES["CFBundleDisplayName"]),
            "app_subtitle": _approved("Subtitle generation and editing for macOS."),
            "keywords": _approved("subtitles, captions, video, editor"),
            "description": _approved(description),
            "promotional_text": _approved("", not_applicable=True),
            "marketing_url": _approved("", not_applicable=True),
            "app_store_connect_record": _approved(
                f"Bundle ID {EXPECTED_INFO_VALUES['CFBundleIdentifier']}, SKU owner-approved, primary locale en-US."
            ),
            "pricing_and_availability": _approved("Owner-approved price tier and availability."),
        },
    }


def _write_owner_values(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "owner_values.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_metadata_package_tracks_owner_inputs_without_submission_claim(tmp_path):
    package = build_metadata_package(root=ROOT, output_dir=tmp_path / "metadata_package")

    assert package["schema"] == "ai_subtitle_studio.app_store_metadata_owner_input_package.v1"
    assert package["APP_VERSION"] == config.APP_VERSION
    assert package["app"]["submission_target"] == "mac_app_store_pkg"
    assert package["not_submission_proof"] is True
    assert package["owner_input_complete"] is False
    assert package["readiness_snapshot"]["app_store_submission_ready"] is False
    assert package["readiness_snapshot"]["pending_owner_input_count"] == 8
    assert package["readiness_snapshot"]["pending_owner_input_keys"] == list(NON_CODE_SUBMISSION_ITEMS)
    assert package["readiness_snapshot"]["pending_app_store_connect_metadata_count"] == 8
    assert {item["status"] for item in package["owner_input_matrix"]} == {"owner_input_required"}
    assert package["owner_values_preflight"]["ready"] is False
    assert package["owner_values_preflight"]["provided"] is False
    assert package["forbidden_claim_scan"]["status"] == "pass"
    assert "owner_input_matrix.owner_values" in package["forbidden_claim_scan"]["scanned_fields"]
    assert "app_store_connect_metadata_fill.owner_values" in package["forbidden_claim_scan"]["scanned_fields"]
    assert package["readiness_snapshot"]["upload_execution_guard"]["upload_confirmation_required"] is True
    assert (
        package["readiness_snapshot"]["upload_execution_guard"]["upload_confirmation_env_var"]
        == "AI_SUBTITLE_STUDIO_APP_STORE_UPLOAD_CONFIRMED"
    )
    assert package["source_readiness_snapshot"]["upload_execution_guard"]["upload_mode_without_confirmation_exits"] == 64
    assert package["source_readiness_snapshot"]["signing_identity_summary"].keys() == {
        "apple_development_present",
        "apple_distribution_present",
        "installer_distribution_present",
    }
    assert package["owner_metadata_values_template"]["schema"] == OWNER_VALUES_SCHEMA
    assert package["owner_metadata_values_template"]["template_only_not_submission_proof"] is True
    assert "identity_names" not in package["source_readiness_snapshot"]
    assert "raw" not in package["source_readiness_snapshot"]


def test_metadata_package_stays_blocked_when_technical_gates_are_green(tmp_path, monkeypatch):
    app_path = tmp_path / "AI Subtitle Studio.app"
    pkg_path = tmp_path / "AI Subtitle Studio.pkg"
    output_dir = tmp_path / "green_technical_gates"
    app_path.mkdir()
    pkg_path.write_text("pkg", encoding="utf-8")
    output_dir.mkdir()
    _write_valid_submission_proofs(output_dir, app_path, pkg_path)
    monkeypatch.setenv("CODESIGN_IDENTITY", "Apple Distribution: Example (TEAMID)")
    monkeypatch.setenv("INSTALLER_IDENTITY", "3rd Party Mac Developer Installer: Example (TEAMID)")
    monkeypatch.setenv("ASC_API_KEY", "KEY")
    monkeypatch.setenv("ASC_API_ISSUER", "ISSUER")

    def fake_security_find_identity(args):
        return {
            "available": True,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "identities": [
                "Apple Distribution: Example (TEAMID)",
                "3rd Party Mac Developer Installer: Example (TEAMID)",
            ],
        }

    monkeypatch.setattr(audit_app_store_readiness, "_run_security_find_identity", fake_security_find_identity)

    package = build_metadata_package(root=ROOT, output_dir=output_dir, app_path=app_path, pkg_path=pkg_path)

    assert package["readiness_snapshot"]["local_packaging_ready"] is True
    assert package["readiness_snapshot"]["app_store_submission_ready"] is False
    assert package["readiness_snapshot"]["pending_owner_input_count"] == 8
    assert package["readiness_snapshot"]["pending_app_store_connect_metadata_count"] == 8
    assert package["readiness_snapshot"]["blocker_count"] == 16
    assert package["owner_input_complete"] is False
    assert package["source_readiness_snapshot"]["signing_identity_summary"]["apple_distribution_present"] is True
    assert package["source_readiness_snapshot"]["signing_identity_summary"]["installer_distribution_present"] is True
    assert all(
        row["blocker"].startswith(("non_code_submission_item_pending:", "app_store_connect_metadata_item_pending:"))
        for row in package["submission_blockers"]
    )


def test_metadata_package_accepts_complete_owner_values_without_claiming_submission_ready(tmp_path):
    owner_values = _write_owner_values(tmp_path, _owner_values_payload())
    package = build_metadata_package(
        root=ROOT,
        output_dir=tmp_path / "owner_values_package",
        owner_values_path=owner_values,
    )

    assert package["owner_input_complete"] is True
    assert package["owner_values_preflight"]["ready"] is True
    assert package["readiness_snapshot"]["pending_owner_input_count"] == 0
    assert package["readiness_snapshot"]["pending_app_store_connect_metadata_count"] == 0
    assert package["readiness_snapshot"]["app_store_submission_ready"] is False
    assert package["not_submission_proof"] is True


def test_metadata_package_scans_imported_owner_values_for_forbidden_claims(tmp_path):
    owner_values = _write_owner_values(
        tmp_path,
        _owner_values_payload(description="App Store ready commercial NLE replacement."),
    )
    package = build_metadata_package(
        root=ROOT,
        output_dir=tmp_path / "forbidden_owner_values",
        owner_values_path=owner_values,
    )

    assert package["owner_input_complete"] is False
    assert package["owner_values_preflight"]["forbidden_claim_scan"]["status"] == "fail"
    assert package["forbidden_claim_scan"]["status"] == "fail"


def test_metadata_package_writes_expected_artifacts(tmp_path):
    output_dir = tmp_path / "metadata_package"
    package = build_metadata_package(root=ROOT, output_dir=output_dir)
    written = write_metadata_package(package, output_dir)
    written_names = {path.name for path in written}

    assert "app_store_metadata_owner_input_package.json" in written_names
    assert "app_store_metadata_owner_input_package.md" in written_names
    assert "forbidden_claim_scan.json" in written_names
    assert "owner_input_matrix.json" in written_names
    assert "app_store_connect_metadata_fill.json" in written_names
    assert "owner_values_preflight.json" in written_names
    assert "owner_metadata_values_template.json" in written_names
    assert "source_readiness_snapshot.json" in written_names

    payload = json.loads((output_dir / "app_store_metadata_owner_input_package.json").read_text(encoding="utf-8"))
    scan = json.loads((output_dir / "forbidden_claim_scan.json").read_text(encoding="utf-8"))
    summary = (output_dir / "app_store_metadata_owner_input_package.md").read_text(encoding="utf-8")

    assert payload["not_submission_proof"] is True
    assert payload["owner_input_complete"] is False
    assert scan["status"] == "pass"
    assert "not packaging, upload, validation, or submission proof" in summary
    assert "owner_metadata_values_template.json" in summary
    assert "Upload confirmation required" in summary
    assert "App Store ready" not in summary
    assert "Apple-approved" not in summary
    assert "fully native" not in summary
    assert "offline-only" not in summary
    assert "validated" not in summary


def test_metadata_package_cli_writes_summary(tmp_path):
    output_dir = tmp_path / "cli_metadata_package"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/generate_app_store_metadata_package.py"),
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["output_dir"] == str(output_dir)
    assert (output_dir / "app_store_metadata_owner_input_package.md").is_file()
    assert (output_dir / "forbidden_claim_scan.json").is_file()
    assert (output_dir / "owner_metadata_values_template.json").is_file()
    template = json.loads((output_dir / "owner_metadata_values_template.json").read_text(encoding="utf-8"))
    assert template["schema"] == OWNER_VALUES_SCHEMA
    assert template["template_only_not_submission_proof"] is True
    assert set(template["owner_inputs"]) == set(NON_CODE_SUBMISSION_ITEMS)
    assert set(template["app_store_connect_metadata"]) == {
        "app_name",
        "app_subtitle",
        "keywords",
        "description",
        "promotional_text",
        "marketing_url",
        "app_store_connect_record",
        "pricing_and_availability",
    }
