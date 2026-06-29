import json
from pathlib import Path

from core.runtime.config import APP_VERSION
from tools import audit_app_store_readiness
from tools.audit_app_store_readiness import EXPECTED_INFO_VALUES, NON_CODE_SUBMISSION_ITEMS, build_readiness_report
from tools.check_app_store_owner_metadata_values import OWNER_VALUES_SCHEMA


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


def _owner_values_payload() -> dict:
    return {
        "schema": OWNER_VALUES_SCHEMA,
        "app_version": APP_VERSION,
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
            "description": _approved("Create, review, save, reopen, and export subtitles."),
            "promotional_text": _approved("", not_applicable=True),
            "marketing_url": _approved("", not_applicable=True),
            "app_store_connect_record": _approved(
                f"Bundle ID {EXPECTED_INFO_VALUES['CFBundleIdentifier']}, SKU owner-approved, primary locale en-US."
            ),
            "pricing_and_availability": _approved("Owner-approved price tier and availability."),
        },
    }


def _write_owner_values(tmp_path: Path) -> Path:
    path = tmp_path / "owner_values.json"
    path.write_text(json.dumps(_owner_values_payload()), encoding="utf-8")
    return path


def test_app_store_readiness_audit_blocks_without_submission_artifacts(tmp_path):
    root = Path(__file__).resolve().parents[1]

    report = build_readiness_report(
        root=root,
        app_path=tmp_path / "missing" / "AI Subtitle Studio.app",
        pkg_path=tmp_path / "missing" / "AI Subtitle Studio.pkg",
        output_dir=tmp_path / "audit",
    )

    assert report["local_packaging_ready"] is True
    assert report["app_store_submission_ready"] is False
    assert report["app_version"] == APP_VERSION
    assert "signed_app_bundle_missing" in report["blockers"]
    assert "signed_app_store_pkg_missing" in report["blockers"]
    assert "strict_codesign_verification_missing" in report["blockers"]
    assert "pkg_signature_verification_missing" in report["blockers"]
    assert "app_store_connect_validation_missing" in report["blockers"]
    assert report["stoplight"]["overall"] == "red"
    assert report["entitlements"]["temporary_exceptions"] == []
    upload_guard = report["upload_execution_guard"]
    assert upload_guard["upload_confirmation_required"] is True
    assert upload_guard["upload_confirmation_env_var"] == "AI_SUBTITLE_STUDIO_APP_STORE_UPLOAD_CONFIRMED"
    assert upload_guard["upload_confirmation_required_value"] == "1"
    assert upload_guard["validate_mode_requires_upload_confirmation"] is False
    assert upload_guard["upload_mode_without_confirmation_exits"] == 64
    assert upload_guard["not_submission_proof"] is True
    upload_commands = [command for command in report["next_owner_approved_commands"] if command.endswith("upload_app_store_build.sh upload")]
    assert len(upload_commands) == 1
    assert "AI_SUBTITLE_STUDIO_APP_STORE_UPLOAD_CONFIRMED=1" in upload_commands[0]
    assert "APP_STORE_READINESS_JSON=" in upload_commands[0]


def test_app_store_readiness_audit_checks_required_entitlements():
    root = Path(__file__).resolve().parents[1]

    report = build_readiness_report(root=root)
    required = report["entitlements"]["required"]

    assert required["com.apple.security.app-sandbox"]["ok"] is True
    assert required["com.apple.security.files.user-selected.read-write"]["ok"] is True
    assert required["com.apple.security.files.bookmarks.app-scope"]["ok"] is True
    assert required["com.apple.security.network.client"]["ok"] is True
    assert required["com.apple.security.device.audio-input"]["ok"] is True


def test_app_store_readiness_audit_tracks_non_code_submission_items():
    root = Path(__file__).resolve().parents[1]

    report = build_readiness_report(root=root)

    pending = report["non_code_submission_items"]
    assert pending["privacy_policy_url"]["status"] == "owner_input_required"
    assert pending["privacy_policy_url"]["draft_available"] is True
    assert pending["privacy_policy_url"]["source_doc_exists"] is True
    assert pending["export_compliance_answers"]["status"] == "owner_input_required"
    assert "owner-approved" in pending["release_notes"]["acceptance_gate"]
    assert "non_code_submission_item_pending:mac_app_store_screenshots" in report["blockers"]
    assert report["submission_content_audit"]["status"] == "blocked"
    assert report["submission_content_audit"]["pending_owner_input_count"] == 8
    assert report["submission_content_audit"]["draft_available_count"] == 8


def test_app_store_readiness_audit_separates_app_store_and_dmg_tracks():
    root = Path(__file__).resolve().parents[1]

    report = build_readiness_report(root=root)

    assert report["submission_target"] == "mac_app_store_pkg"
    app_store_track = report["distribution_tracks"]["mac_app_store_pkg"]
    dmg_track = report["distribution_tracks"]["developer_id_beta_dmg"]
    assert app_store_track["target_role"] == "primary_submission_target"
    assert app_store_track["status"] == "blocked"
    assert "signed_app_store_pkg" in app_store_track["requires"]
    assert dmg_track["target_role"] == "separate_opt_in_beta_distribution"
    assert dmg_track["status"] == "opt_in_hold"
    assert dmg_track["not_submission_evidence"] is True
    assert "packaging/macos/build_beta_dmg.sh" in report["owner_approval_required_actions"]
    assert "packaging/macos/upload_app_store_build.sh upload" in report["owner_approval_required_actions"]


def test_app_store_readiness_audit_submission_content_drafts_match_runtime_scope():
    root = Path(__file__).resolve().parents[1]

    report = build_readiness_report(root=root)
    privacy = report["non_code_submission_items"]["privacy_data_type_answers"]
    review_notes = report["non_code_submission_items"]["app_review_notes"]

    assert "user-selected media" in privacy["draft"]
    assert "optional STT/model/network workflows" in privacy["draft"]
    assert "analytics" in privacy["owner_decision_required"]
    assert "app-scope bookmarks" in review_notes["draft"]
    assert "network entitlement purpose" in review_notes["draft"]


def test_app_store_readiness_audit_records_keychain_identity_blockers(monkeypatch):
    root = Path(__file__).resolve().parents[1]

    def fake_security_find_identity(args):
        return {
            "available": True,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "identities": ["Apple Development: owner@example.com (TEAMID)"],
        }

    monkeypatch.setattr(audit_app_store_readiness, "_run_security_find_identity", fake_security_find_identity)

    report = build_readiness_report(root=root)
    identities = report["signing_identities"]

    assert identities["apple_development_present"] is True
    assert identities["apple_distribution_present"] is False
    assert identities["installer_distribution_present"] is False
    assert "apple_distribution_identity_missing_from_keychain" in report["blockers"]
    assert "installer_identity_missing_from_keychain" in report["blockers"]


def test_app_store_readiness_audit_groups_blockers_and_submission_gates(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    for name in ("CODESIGN_IDENTITY", "INSTALLER_IDENTITY", "ASC_API_KEY", "ASC_API_ISSUER", "ASC_USERNAME", "ASC_PASSWORD"):
        monkeypatch.delenv(name, raising=False)

    def fake_security_find_identity(args):
        return {
            "available": True,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "identities": ["Apple Development: owner@example.com (TEAMID)"],
        }

    monkeypatch.setattr(audit_app_store_readiness, "_run_security_find_identity", fake_security_find_identity)

    report = build_readiness_report(
        root=root,
        app_path=tmp_path / "missing" / "AI Subtitle Studio.app",
        pkg_path=tmp_path / "missing" / "AI Subtitle Studio.pkg",
        output_dir=tmp_path / "audit",
    )
    groups = report["blocker_group_summary"]["groups"]
    gates = report["submission_gate_summary"]

    assert report["app_version"] == APP_VERSION
    counts = report["blocker_group_counts"]

    assert sum(counts.values()) == len(report["blockers"])
    assert counts["packaging_template"] == 0
    assert counts["signed_artifacts"] == 4
    assert counts["sandbox_smoke"] == 1
    assert counts["app_store_connect"] == 2
    assert counts["signing_identities"] == 4
    assert counts["owner_metadata"] == 16
    assert groups["packaging_template"]["status"] == "ready"
    assert groups["signed_artifacts"]["count"] == 4
    assert groups["sandbox_smoke"]["count"] == 1
    assert groups["app_store_connect"]["count"] == 2
    assert groups["signing_identities"]["count"] == 4
    assert groups["owner_metadata"]["count"] == 16
    assert report["stoplight"]["overall"] == "red"
    assert report["stoplight"]["groups"]["packaging_template"] == "green"
    assert report["stoplight"]["groups"]["signed_artifacts"] == "red"
    assert gates["version_lock_ready"] is True
    assert gates["packaging_template_ready"] is True
    assert gates["signed_artifacts_ready"] is False
    assert gates["sandbox_smoke_ready"] is False
    assert gates["app_store_connect_validation_ready"] is False
    assert gates["apple_distribution_identity_ready"] is False
    assert gates["installer_identity_ready"] is False
    assert gates["app_store_connect_auth_ready"] is False
    assert gates["owner_metadata_ready"] is False
    assert gates["app_store_submission_ready"] is False


def test_app_store_readiness_audit_metadata_remains_final_gate_when_technical_gates_are_green(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
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

    report = build_readiness_report(
        root=root,
        app_path=app_path,
        pkg_path=pkg_path,
        output_dir=output_dir,
    )
    groups = report["blocker_group_summary"]["groups"]
    gates = report["submission_gate_summary"]

    assert report["local_packaging_ready"] is True
    assert report["app_store_submission_ready"] is False
    assert groups["signed_artifacts"]["count"] == 0
    assert groups["sandbox_smoke"]["count"] == 0
    assert groups["app_store_connect"]["count"] == 0
    assert groups["signing_identities"]["count"] == 0
    assert groups["owner_metadata"]["count"] == 16
    assert gates["signed_artifacts_ready"] is True
    assert gates["strict_codesign_verification_ready"] is True
    assert gates["pkg_signature_verification_ready"] is True
    assert gates["sandbox_smoke_ready"] is True
    assert gates["app_store_connect_validation_ready"] is True
    assert gates["apple_distribution_identity_ready"] is True
    assert gates["installer_identity_ready"] is True
    assert gates["app_store_connect_auth_ready"] is True
    assert gates["owner_metadata_ready"] is False
    assert gates["app_store_submission_ready"] is False


def test_app_store_readiness_audit_owner_values_clear_metadata_gate_only(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    owner_values = _write_owner_values(tmp_path)

    def fake_security_find_identity(args):
        return {
            "available": True,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "identities": ["Apple Development: owner@example.com (TEAMID)"],
        }

    monkeypatch.setattr(audit_app_store_readiness, "_run_security_find_identity", fake_security_find_identity)

    report = build_readiness_report(
        root=root,
        app_path=tmp_path / "missing" / "AI Subtitle Studio.app",
        pkg_path=tmp_path / "missing" / "AI Subtitle Studio.pkg",
        output_dir=tmp_path / "audit",
        owner_values_path=owner_values,
    )

    assert report["owner_metadata_values_preflight"]["ready"] is True
    assert report["submission_content_audit"]["pending_owner_input_count"] == 0
    assert report["blocker_group_counts"]["owner_metadata"] == 0
    assert report["submission_gate_summary"]["owner_metadata_ready"] is True
    assert report["app_store_submission_ready"] is False


def test_app_store_readiness_audit_can_be_ready_with_technical_and_owner_gates_green(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    app_path = tmp_path / "AI Subtitle Studio.app"
    pkg_path = tmp_path / "AI Subtitle Studio.pkg"
    output_dir = tmp_path / "all_green"
    owner_values = _write_owner_values(tmp_path)
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

    report = build_readiness_report(
        root=root,
        app_path=app_path,
        pkg_path=pkg_path,
        output_dir=output_dir,
        owner_values_path=owner_values,
    )

    assert report["blockers"] == []
    assert report["app_store_submission_ready"] is True
    assert report["submission_gate_summary"]["owner_metadata_ready"] is True
    assert report["submission_gate_summary"]["app_store_submission_ready"] is True


def test_app_store_readiness_rejects_proof_bound_only_to_same_basename(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    app_path = tmp_path / "candidate" / "AI Subtitle Studio.app"
    pkg_path = tmp_path / "candidate" / "AI Subtitle Studio.pkg"
    other_app = tmp_path / "other" / "AI Subtitle Studio.app"
    other_pkg = tmp_path / "other" / "AI Subtitle Studio.pkg"
    output_dir = tmp_path / "basename_only"
    app_path.mkdir(parents=True)
    pkg_path.write_text("pkg", encoding="utf-8")
    other_app.mkdir(parents=True)
    other_pkg.write_text("pkg", encoding="utf-8")
    output_dir.mkdir()
    _write_valid_submission_proofs(output_dir, other_app, other_pkg)
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

    report = build_readiness_report(
        root=root,
        app_path=app_path,
        pkg_path=pkg_path,
        output_dir=output_dir,
    )

    assert "strict_codesign_verification_invalid" in report["blockers"]
    assert "pkg_signature_verification_invalid" in report["blockers"]
    assert "app_store_connect_validation_failed" in report["blockers"]


def test_app_store_readiness_rejects_placeholder_submission_proof_files(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    app_path = tmp_path / "AI Subtitle Studio.app"
    pkg_path = tmp_path / "AI Subtitle Studio.pkg"
    output_dir = tmp_path / "placeholder_proofs"
    app_path.mkdir()
    pkg_path.write_text("pkg", encoding="utf-8")
    output_dir.mkdir()
    (output_dir / "app_codesign_verify.txt").write_text("codesign ok", encoding="utf-8")
    (output_dir / "pkgutil_check_signature.txt").write_text("pkg signature ok", encoding="utf-8")
    (output_dir / "sandbox_smoke_result.json").write_text("{}", encoding="utf-8")
    (output_dir / "app_store_connect_validation.xml").write_text("<ok/>", encoding="utf-8")
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

    report = build_readiness_report(
        root=root,
        app_path=app_path,
        pkg_path=pkg_path,
        output_dir=output_dir,
    )
    gates = report["submission_gate_summary"]

    assert report["app_store_submission_ready"] is False
    assert "strict_codesign_verification_invalid" in report["blockers"]
    assert "pkg_signature_verification_invalid" in report["blockers"]
    assert "sandbox_smoke_failed" in report["blockers"]
    assert "app_store_connect_validation_failed" in report["blockers"]
    assert gates["strict_codesign_verification_ready"] is False
    assert gates["pkg_signature_verification_ready"] is False
    assert gates["sandbox_smoke_ready"] is False
    assert gates["app_store_connect_validation_ready"] is False


def test_app_store_readiness_requires_configured_identities_to_match_keychain(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    app_path = tmp_path / "AI Subtitle Studio.app"
    pkg_path = tmp_path / "AI Subtitle Studio.pkg"
    output_dir = tmp_path / "identity_mismatch"
    app_path.mkdir()
    pkg_path.write_text("pkg", encoding="utf-8")
    output_dir.mkdir()
    _write_valid_submission_proofs(output_dir, app_path, pkg_path)
    monkeypatch.setenv("CODESIGN_IDENTITY", "Apple Distribution: Wrong (TEAMID)")
    monkeypatch.setenv("INSTALLER_IDENTITY", "3rd Party Mac Developer Installer: Wrong (TEAMID)")
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

    report = build_readiness_report(
        root=root,
        app_path=app_path,
        pkg_path=pkg_path,
        output_dir=output_dir,
    )
    gates = report["submission_gate_summary"]

    assert "apple_distribution_codesign_identity_not_in_keychain" in report["blockers"]
    assert "installer_identity_not_in_keychain" in report["blockers"]
    assert gates["apple_distribution_identity_ready"] is False
    assert gates["installer_identity_ready"] is False


def test_app_store_readiness_stays_blocked_when_artifacts_exist_but_signature_proof_is_missing(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    app_path = tmp_path / "AI Subtitle Studio.app"
    pkg_path = tmp_path / "AI Subtitle Studio.pkg"
    output_dir = tmp_path / "artifact_only"
    app_path.mkdir()
    pkg_path.write_text("pkg", encoding="utf-8")
    output_dir.mkdir()
    (output_dir / "sandbox_smoke_result.json").write_text("{}", encoding="utf-8")
    (output_dir / "app_store_connect_validation.xml").write_text("<ok/>", encoding="utf-8")
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

    report = build_readiness_report(
        root=root,
        app_path=app_path,
        pkg_path=pkg_path,
        output_dir=output_dir,
    )

    assert report["status"] == "blocked"
    assert report["app_store_submission_ready"] is False
    assert "signed_app_bundle_missing" not in report["blockers"]
    assert "signed_app_store_pkg_missing" not in report["blockers"]
    assert "strict_codesign_verification_missing" in report["blockers"]
    assert "pkg_signature_verification_missing" in report["blockers"]
    assert report["blocker_group_counts"]["signed_artifacts"] == 2
    assert report["submission_gate_summary"]["signed_app_bundle_ready"] is True
    assert report["submission_gate_summary"]["signed_app_store_pkg_ready"] is True
    assert report["submission_gate_summary"]["strict_codesign_verification_ready"] is False
    assert report["submission_gate_summary"]["pkg_signature_verification_ready"] is False
    assert report["submission_gate_summary"]["signed_artifacts_ready"] is False
    assert report["stoplight"]["overall"] == "red"
