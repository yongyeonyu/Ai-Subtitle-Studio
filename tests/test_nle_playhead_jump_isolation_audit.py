import json
import tempfile
from pathlib import Path

from tools.audit_nle_playhead_jump_isolation import (
    build_nle_playhead_jump_isolation_report,
    write_nle_playhead_jump_isolation_report,
)


def test_nle_playhead_jump_isolation_audit_proves_view_only_contract():
    report = build_nle_playhead_jump_isolation_report()

    assert report["ready"] is True
    assert report["runtime_change_applied"] is False
    assert report["playhead_jump_view_only_contract"] is True
    assert report["model_validation_allowed"] is False
    assert report["project_save_allowed"] is False
    assert report["nle_write_allowed"] is False
    assert report["nas_validation_required"] is False
    assert all(row["method_present"] for row in report["method_contracts"])
    assert all(row["forbidden_call_count"] == 0 for row in report["method_contracts"])
    assert all(row["forbidden_assignment_count"] == 0 for row in report["method_contracts"])
    assert all(row["all_tokens_present"] for row in report["token_contracts"])


def test_nle_playhead_jump_isolation_audit_writes_json_and_markdown_reports():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        report = build_nle_playhead_jump_isolation_report()
        write_nle_playhead_jump_isolation_report(output_dir, report)

        json_path = output_dir / "nle_playhead_jump_isolation.json"
        markdown_path = output_dir / "nle_playhead_jump_isolation.md"
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

    assert saved["schema"] == report["schema"]
    assert markdown.startswith("# NLE Playhead Jump Isolation Audit")
    assert "## Method Contracts" in markdown
    assert "| GlobalCanvas.mousePressEvent | ui/timeline/timeline_global.py | True | 0 | 0 |" in markdown
    assert "| TimelineWidget._on_global_seek | ui/timeline/timeline_widget.py | True | 0 | 0 |" in markdown
    assert "| EditorTimelineVideoMixin._on_scrub | ui/editor/ux/editor_timeline_video.py | True | 0 | 0 |" in markdown
    assert "playhead_jump_must_not_validate_or_rewrite_primary_subtitle_model" in markdown
