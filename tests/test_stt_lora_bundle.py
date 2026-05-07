from core.stt_mode.lora_bundle import export_stt_lora_bundle, validate_stt_lora_bundle


def test_export_and_validate_policy_json_bundle(tmp_path):
    result = export_stt_lora_bundle(
        output_dir=str(tmp_path),
        bundle_id="bundle_test",
        size_tier="100MB",
        protected_terms=["서스펜션"],
    )
    validation = validate_stt_lora_bundle(result["bundle_dir"])

    assert validation["valid"] is True
    assert validation["manifest"]["schema"] == "ai_subtitle_studio.stt_lora_bundle.v1"
    assert validation["manifest"]["size_tier"] == "100MB"
