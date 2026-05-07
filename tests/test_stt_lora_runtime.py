from pathlib import Path
from unittest.mock import patch

from core.stt_mode.lora_runtime import (
    build_stt_runtime_policy_bundle,
    collect_stt_protected_terms,
    export_stt_runtime_bundle,
)


def test_collect_stt_protected_terms_keeps_distinctive_stt_terms():
    protected = collect_stt_protected_terms(
        settings={"stt_lora_protected_terms": ["VR"]},
        raw_segments=[
            {"text": "안경 쓰신 분들은 VR 말고 2026 전시를 보세요"},
            {"text": "안경 쓰신 분들은 VR 기기를 조심하세요"},
        ],
        final_segments=[{"text": "2026 VR 전시"}],
    )

    assert "VR" in protected
    assert "2026" in protected
    assert "안경" in protected


def test_build_stt_runtime_policy_bundle_exposes_dedicated_stt_lora_sections():
    bundle = build_stt_runtime_policy_bundle(
        settings={
            "stt_quality_preset": "stt",
            "stt_mode_target_chars_per_line": 10,
            "stt_mode_max_lines": 2,
            "stt_mode_vad_models": ["silero", "ten_vad"],
            "stt_lora_protected_terms": ["VR"],
        },
        work_segments=[{"id": "seg_001", "vad_confidence_label": "high"}],
        raw_segments=[{"id": "raw_001", "text": "안경 쓰신 분들은 VR 말고 시뮬레이터를 하세요"}],
        final_segments=[{"id": "final_001", "text": "안경 쓰신 분들은 VR 말고 시뮬레이터를 하세요"}],
        learning_events=[{"id": "evt_001"}],
        bundle_id="demo_stt_lora",
    )

    assert bundle["bundle_id"] == "demo_stt_lora"
    assert bundle["adapter_refs"]["stt_lora_bundle"] == "demo_stt_lora"
    assert bundle["stt_dictation_resegment_policy"]["quality_preset"] == "stt"
    assert bundle["stt_dictation_resegment_policy"]["target_chars_per_line"] == 10
    assert bundle["subtitle_style_policy"]["max_lines"] == 2
    assert bundle["stt_vad_segment_model"]["vad_models"] == ["silero", "ten_vad"]
    assert "VR" in bundle["stt_dictation_resegment_policy"]["protected_terms"]


def test_export_stt_runtime_bundle_writes_separate_stt_lora_bundle(tmp_path):
    output_root = tmp_path / "output"
    output_root.mkdir(parents=True, exist_ok=True)

    with patch("core.stt_mode.lora_runtime.config.OUTPUT_DIR", str(output_root)):
        bundle = export_stt_runtime_bundle(
            project_path="/tmp/demo_project.project.json",
            settings={"stt_lora_bundle_auto_export_enabled": True},
            work_segments=[{"id": "seg_001", "vad_confidence_label": "high"}],
            raw_segments=[{"id": "raw_001", "text": "원문입니다"}],
            final_segments=[{"id": "final_001", "text": "최종입니다"}],
            learning_events=[{"id": "evt_001"}],
        )

    bundle_dir = Path(bundle["bundle_dir"])
    assert bundle["bundle_id"] == "demo_project.project_stt_lora"
    assert bundle["adapter_refs"]["stt_lora_bundle"] == "demo_project.project_stt_lora"
    assert bundle_dir.exists()
    assert (bundle_dir / "manifest.json").exists()
    assert (bundle_dir / "stt_dictation_resegment_policy.json").exists()
