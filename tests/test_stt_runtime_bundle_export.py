from core.stt_mode.lora_bundle import export_stt_lora_bundle, validate_stt_lora_bundle


def test_runtime_bundle_export_supports_300mb_tier(tmp_path):
    result = export_stt_lora_bundle(output_dir=str(tmp_path), bundle_id="bundle_300", size_tier="300MB")
    validation = validate_stt_lora_bundle(result["bundle_dir"])

    assert validation["valid"]
    assert validation["manifest"]["max_size_bytes"] == 300 * 1024 * 1024
