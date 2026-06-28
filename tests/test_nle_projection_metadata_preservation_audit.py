import json
import tempfile
from pathlib import Path

from tools.audit_nle_projection_metadata_preservation import (
    build_nle_projection_metadata_preservation_report,
    write_nle_projection_metadata_preservation_report,
)


def test_nle_projection_metadata_preservation_audit_proves_runtime_contract():
    report = build_nle_projection_metadata_preservation_report()

    assert report["ready"] is True
    assert report["runtime_change_applied"] is True
    assert report["ui_change_applied"] is False
    assert report["persisted_nle_fields_changed"] is False
    assert report["stt_or_cache_default_changed"] is False

    checks = {row["case"]: row for row in report["checks"]}
    static = checks["static_projection_deepcopy_contract"]
    assert static["passed"] is True
    assert static["retime_uses_deepcopy"] is True
    assert static["manual_edit_uses_deepcopy"] is True
    assert static["sort_uses_deepcopy"] is True
    assert static["shadow_uses_deepcopy"] is True
    assert static["operation_to_dict_uses_deepcopy"] is True

    move = checks["dynamic_caption_move_metadata_preserved"]
    assert move["passed"] is True
    assert move["legacy_quality_label"] == "high"
    assert move["nle_quality_timing"] == 0.88
    assert move["raw_quality_label"] == "high"
    assert move["fresh_quality_after_payload_mutation"] == 0.93
    assert move["overlap_count"] == 0
    assert move["max_active_segments"] <= 1

    merge = checks["dynamic_caption_merge_metadata_preserved"]
    assert merge["passed"] is True
    assert merge["speaker_list"] == ["00", "host"]
    assert merge["merged_caption_ids"] == ["subtitle_vector_0001", "subtitle_vector_0002"]

    split = checks["dynamic_caption_split_metadata_preserved"]
    assert split["passed"] is True
    assert split["left_speaker_list"] == ["01", "guest"]
    assert split["right_speaker_list"] == ["01", "guest"]
    assert split["left_quality_removed_by_manual_policy"] is True
    assert split["right_quality_removed_by_manual_policy"] is True

    storage = checks["storage_projection_metadata_runtime_fields_clean"]
    assert storage["passed"] is True
    assert storage["storage_has_runtime_nle_state"] is False
    assert storage["storage_has_nle"] is False
    assert storage["storage_has_nle_snapshot"] is False
    assert storage["reopened_quality_label"] == "high"


def test_nle_projection_metadata_preservation_audit_writes_reports():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        report = build_nle_projection_metadata_preservation_report()
        write_nle_projection_metadata_preservation_report(output_dir, report)

        json_path = output_dir / "nle_projection_metadata_preservation.json"
        markdown_path = output_dir / "nle_projection_metadata_preservation.md"
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

    assert saved["schema"] == report["schema"]
    assert markdown.startswith("# NLE Projection Metadata Preservation Audit")
    assert "Runtime change applied: `True`" in markdown
    assert "| dynamic_caption_move_metadata_preserved | True | 0 | 1 |" in markdown
    assert "- Caption split child metadata preserved: `True`" in markdown
