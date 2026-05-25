from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "SUBTITLE_GENERATION_DOMAIN_MAP.md"
LONG_FILE_MAP_PATH = ROOT / "LONG_FILE_OWNERSHIP_MAP.md"

REQUIRED_DOMAINS = {
    "subtitle_cut_boundary",
    "subtitle_stt",
    "subtitle_stt1_segments",
    "subtitle_stt2_segments",
    "subtitle_llm",
    "subtitle_deep_learning",
    "subtitle_lora",
    "subtitle_roughcut",
    "subtitle_dictionary",
    "subtitle_timing",
    "subtitle_parallel_manager",
    "subtitle_resource_manager",
    "subtitle_live_sync_manager",
    "subtitle_live_editor_feed",
    "subtitle_segments",
    "subtitle_waveform",
    "subtitle_global_canvas",
    "subtitle_speaker_diarization",
}

REQUIRED_OWNER_PATHS = {
    "core/audio/media_processor.py",
    "core/audio/media_processor_transcribe.py",
    "core/engine/subtitle_cut_boundary.py",
    "core/engine/subtitle_dictionary.py",
    "core/engine/subtitle_engine.py",
    "core/engine/subtitle_global_canvas.py",
    "core/engine/subtitle_live_sync_manager.py",
    "core/engine/subtitle_live_editor_feed.py",
    "core/engine/subtitle_segments.py",
    "core/engine/subtitle_speaker_diarization.py",
    "core/engine/subtitle_stt_segments.py",
    "core/engine/subtitle_timing.py",
    "core/engine/subtitle_timing_contracts.py",
    "core/engine/subtitle_waveform.py",
    "core/pipeline/cut_boundary_helpers.py",
    "core/pipeline/cut_boundary_segment_ops.py",
    "core/pipeline/cut_boundary_snapshot.py",
    "core/pipeline/single_pipeline.py",
    "core/pipeline/subtitle_parallel_manager.py",
    "core/pipeline/pipeline_helpers.py",
    "core/personalization/subtitle_lora_runtime.py",
    "core/roughcut/editor_draft_llm.py",
    "core/subtitle_quality/candidate_generator.py",
    "core/runtime/subtitle_resource_manager.py",
    "core/runtime/subtitle_native_readiness.py",
    "tests/test_subtitle_resource_manager.py",
    "ui/editor/editor_segments_live_preview.py",
    "ui/editor/editor_segments_stt_selection_flow.py",
    "ui/editor/editor_save_manager.py",
    "ui/timeline/timeline_global.py",
    "ui/timeline/timeline_waveform.py",
    "core/native_subtitle_segments.py",
    "core/native_subtitle_stt_segments.py",
    "core/native_subtitle_global_canvas.py",
    "tests/test_subtitle_global_canvas_facade.py",
    "tests/test_subtitle_cut_boundary_facade.py",
    "tests/test_subtitle_dictionary_facade.py",
    "tests/test_subtitle_live_sync_manager.py",
    "tests/test_subtitle_live_editor_feed_facade.py",
    "tests/test_subtitle_speaker_diarization_facade.py",
    "tests/test_subtitle_facade_project_reopen_contracts.py",
    "tests/test_subtitle_parallel_manager.py",
    "tests/test_subtitle_native_readiness.py",
    "tests/test_subtitle_timing_contracts.py",
    "tests/test_subtitle_waveform_facade.py",
    "ui/editor/editor_quality_review.py",
    "ui/editor/editor_scan_cut_project.py",
    "native/macos/AIStudioNative/Sources/AIStudioCore/SubtitleResourcePlan.swift",
    "native/macos/AIStudioNative/Sources/AIStudioCore/SubtitleSTTSegmentsSummary.swift",
    "ui/editor/editor_subtitle_post_llm.py",
    "ui/editor/ux/timeline_input_shadow.py",
    "ui/editor/ux/timeline_live_cut_detection.py",
}


def _map_text() -> str:
    return MAP_PATH.read_text(encoding="utf-8")


def test_domain_map_exists_and_lists_every_action_item_domain():
    text = _map_text()

    for domain in sorted(REQUIRED_DOMAINS):
        assert f"### {domain}" in text


def test_domain_map_covers_current_owner_paths():
    text = _map_text()

    for owner in sorted(REQUIRED_OWNER_PATHS):
        assert owner in text


def test_action_item_points_to_domain_map_progress_artifact():
    action_items = (ROOT / "ACTION_ITEMS.md").read_text(encoding="utf-8")

    assert "SUBTITLE_GENERATION_DOMAIN_MAP.md" in action_items
    assert "LONG_FILE_OWNERSHIP_MAP.md" in action_items
    assert "tests/test_subtitle_generation_domain_map.py" in action_items
    assert "tests/test_subtitle_segments_facade.py" in action_items
    assert "tests/test_subtitle_stt_segments_facade.py" in action_items
    assert "tests/test_subtitle_resource_manager.py" in action_items
    assert "tests/test_subtitle_global_canvas_facade.py" in action_items
    assert "tests/test_subtitle_waveform_facade.py" in action_items
    assert "tests/test_subtitle_timing_contracts.py" in action_items
    assert "tests/test_subtitle_parallel_manager.py" in action_items
    assert "tests/test_subtitle_cut_boundary_facade.py" in action_items
    assert "tests/test_subtitle_dictionary_facade.py" in action_items
    assert "tests/test_subtitle_live_sync_manager.py" in action_items
    assert "tests/test_subtitle_live_editor_feed_facade.py" in action_items
    assert "tests/test_subtitle_speaker_diarization_facade.py" in action_items
    assert "tests/test_subtitle_facade_project_reopen_contracts.py" in action_items
    assert "tests/test_subtitle_native_readiness.py" in action_items


def test_long_file_ownership_map_captures_current_split_owners():
    text = LONG_FILE_MAP_PATH.read_text(encoding="utf-8")

    assert "Runtime Python files should stay below 2000 lines" in text
    for path in (
        "tools/benchmark_subtitle_pipeline_variants.py",
        "core/roughcut/editor_draft.py",
        "core/pipeline/cut_boundary_helpers.py",
        "ui/editor/editor_widget.py",
        "ui/editor/ux/timeline_input.py",
        "core/roughcut/editor_draft_llm.py",
        "core/pipeline/cut_boundary_snapshot.py",
        "ui/editor/editor_quality_review.py",
        "ui/editor/ux/timeline_input_shadow.py",
    ):
        assert path in text
