import json
import subprocess
import sys
from pathlib import Path

from core.runtime import config
from tools import audit_app_store_readiness
from tools.audit_app_store_readiness import NON_CODE_SUBMISSION_ITEMS
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
    assert {item["status"] for item in package["owner_input_matrix"]} == {"owner_input_required"}
    assert package["forbidden_claim_scan"]["status"] == "pass"
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
    assert package["readiness_snapshot"]["blocker_count"] == 8
    assert package["owner_input_complete"] is False
    assert package["source_readiness_snapshot"]["signing_identity_summary"]["apple_distribution_present"] is True
    assert package["source_readiness_snapshot"]["signing_identity_summary"]["installer_distribution_present"] is True
    assert all(row["blocker"].startswith("non_code_submission_item_pending:") for row in package["submission_blockers"])


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
    assert "source_readiness_snapshot.json" in written_names

    payload = json.loads((output_dir / "app_store_metadata_owner_input_package.json").read_text(encoding="utf-8"))
    scan = json.loads((output_dir / "forbidden_claim_scan.json").read_text(encoding="utf-8"))
    summary = (output_dir / "app_store_metadata_owner_input_package.md").read_text(encoding="utf-8")

    assert payload["not_submission_proof"] is True
    assert payload["owner_input_complete"] is False
    assert scan["status"] == "pass"
    assert "not packaging, upload, validation, or submission proof" in summary
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
