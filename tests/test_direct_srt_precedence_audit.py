from pathlib import Path

from tools.audit_direct_srt_precedence_contract import build_direct_srt_precedence_report


def test_direct_srt_precedence_audit_passes(tmp_path: Path):
    report = build_direct_srt_precedence_report(output_dir=tmp_path)

    assert report["passed"] is True
    assert report["editor_text"] == "latest direct SRT text"
    assert report["nle_text"] == "latest direct SRT text"
    assert report["nle_sync_source"] == "direct_srt_open"
    assert report["storage_clean_of_runtime_nle"] is True
