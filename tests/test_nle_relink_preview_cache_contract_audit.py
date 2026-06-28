import json
import tempfile
from pathlib import Path

from tools.audit_nle_relink_preview_cache_contract import (
    build_nle_relink_preview_cache_report,
    write_nle_relink_preview_cache_report,
)


def test_nle_relink_preview_cache_contract_accepts_same_media_and_blocks_proxy():
    with tempfile.TemporaryDirectory() as tmp:
        report = build_nle_relink_preview_cache_report(output_dir=Path(tmp))

    assert report["ready"] is True
    assert report["runtime_contract_applied"] is True
    assert report["ui_layout_change_applied"] is False
    assert report["persisted_project_schema_change_applied"] is False
    assert report["relink_identity_matches"] is True
    assert report["relink_hit_reuses_original_cache"] is True
    assert report["proxy_identity_blocked"] is True
    assert report["proxy_hit_blocked"] is True
    assert report["cached_still_exists"] is True
    assert report["manifest_relink_reuse_policy"] == "same_media_identity_same_fps_frame_width_only"
    assert report["manifest_proxy_switch_reuse_policy"] == "original_source_cache_only_proxy_switch_keeps_original_path"


def test_nle_relink_preview_cache_contract_writes_reports():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        report = build_nle_relink_preview_cache_report(output_dir=output_dir)
        write_nle_relink_preview_cache_report(output_dir, report)

        json_path = output_dir / "nle_relink_preview_cache_contract.json"
        markdown_path = output_dir / "nle_relink_preview_cache_contract.md"
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

    assert saved["schema"] == report["schema"]
    assert markdown.startswith("# NLE Relink Preview Cache Contract Audit")
    assert "Relink hit reuses original cache: `True`" in markdown
    assert "Proxy hit blocked: `True`" in markdown
    assert "preview_cache_deletion_or_move_not_allowed" in markdown
