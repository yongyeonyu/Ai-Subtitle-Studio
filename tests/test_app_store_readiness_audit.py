from pathlib import Path

from tools.audit_app_store_readiness import build_readiness_report


def test_app_store_readiness_audit_blocks_without_submission_artifacts():
    root = Path(__file__).resolve().parents[1]

    report = build_readiness_report(root=root)

    assert report["local_packaging_ready"] is True
    assert report["app_store_submission_ready"] is False
    assert "signed_app_bundle_missing" in report["blockers"]
    assert "signed_app_store_pkg_missing" in report["blockers"]
    assert "app_store_connect_validation_missing" in report["blockers"]
    assert report["entitlements"]["temporary_exceptions"] == []


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
