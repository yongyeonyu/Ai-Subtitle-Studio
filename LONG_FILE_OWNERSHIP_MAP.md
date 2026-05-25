# Long File Ownership Map

Generated: 2026-05-25

Purpose: completion evidence for the `ACTION_ITEMS.md` domain split and native
acceleration queue item. This map records the current long-file owners after the
behavior-preserving split pass.

## Guardrails

- Runtime Python files should stay below 2000 lines unless a temporary migration
  note is added here.
- Subtitle quality policy, STT1/STT2 participation, LLM cleanup, LoRA policy,
  and save/reopen behavior must not be changed by long-file cleanup.
- UI/UX behavior must not be changed by long-file cleanup.
- Native helpers stay behind feature flags and Python fallback until parity is
  proven by the listed guard tests and real fixture evidence.

## Current Long Runtime Owners

Measured with tests, virtualenvs, build outputs, dist outputs, and `.codex_work`
excluded.

| File | Lines | Ownership |
| --- | ---: | --- |
| `ui/editor/ux/timeline_subtitle_segment_editing.py` | 1949 | Inline subtitle segment editing behavior. No UI behavior changes during split work. |
| `core/pipeline/cut_boundary_helpers.py` | 1944 | Pipeline cut-boundary orchestration; project snapshots live in `core/pipeline/cut_boundary_snapshot.py`, saved-boundary segment operations live in `core/pipeline/cut_boundary_segment_ops.py`. |
| `ui/editor/ux/timeline_input.py` | 1918 | Timeline input routing; shadow playhead helpers live in `ui/editor/ux/timeline_input_shadow.py`. |
| `ui/home_sidebar.py` | 1890 | Sidebar shell and status wiring; model menu helpers live in `ui/home_sidebar_model_menu.py`. |
| `ui/timeline/timeline_paint.py` | 1881 | Single-owner 2D timeline paint surface. Keep 2D/QPainter ownership intact; reusable paint helpers live in `ui/timeline/timeline_paint_helpers.py`. |
| `core/project/project_manager.py` | 1873 | Project JSON persistence and migration owner. |
| `ui/timeline/timeline_widget.py` | 1858 | Timeline widget shell; playhead overlay and time-window helpers live in `ui/timeline/timeline_playhead_overlay.py` and `ui/timeline/timeline_time_window.py`. |
| `tools/benchmark_subtitle_pipeline_variants.py` | 1834 | Benchmark CLI orchestration; settings/readability/artifact/scoring helpers live in `tools/subtitle_benchmark_settings.py`, `tools/subtitle_benchmark_readability.py`, `tools/subtitle_benchmark_artifacts.py`, and `tools/subtitle_benchmark_scoring.py`. |
| `core/engine/subtitle_engine.py` | 1831 | Final subtitle assembly orchestration; helper modules own final integrity, LLM runtime, LoRA packaging, STT candidate helpers, and post-LLM payloads. |
| `core/cut_boundary_auto_scan.py` | 1827 | Cut-boundary auto-scan runtime. |
| `ui/editor/editor_scan_cut_core.py` | 1816 | Editor scan-cut runtime; project persistence helpers live in `ui/editor/editor_scan_cut_project.py`. |
| `ui/editor/editor_widget.py` | 1809 | Editor widget shell; quality review actions live in `ui/editor/editor_quality_review.py`. |
| `core/roughcut/editor_draft.py` | 1769 | Roughcut EDL/topic drafting orchestration; LLM provider JSON calls live in `core/roughcut/editor_draft_llm.py`, and chunk-boundary planning lives in `core/roughcut/editor_draft_chunks.py`. |

## Split Modules Added Or Confirmed

- `core/audio/media_processor_audio_route.py`
- `core/audio/media_processor_transcribe_policy.py`
- `core/audio/media_processor_transcribe_recheck.py`
- `core/audio/media_processor_transcribe_run.py`
- `core/audio/media_processor_transcribe_windowed.py`
- `core/engine/subtitle_final_integrity.py`
- `core/engine/subtitle_llm_runtime.py`
- `core/engine/subtitle_lora_packaging.py`
- `core/engine/subtitle_post_llm.py`
- `core/engine/subtitle_stt_candidate_helpers.py`
- `core/engine/subtitle_stt_candidate_selection.py`
- `core/pipeline/cut_boundary_segment_ops.py`
- `core/pipeline/cut_boundary_snapshot.py`
- `core/roughcut/editor_draft_llm.py`
- `core/roughcut/editor_draft_chunks.py`
- `tools/subtitle_benchmark_scoring.py`
- `ui/editor/editor_quality_review.py`
- `ui/editor/editor_scan_cut_project.py`
- `ui/editor/editor_subtitle_post_llm.py`
- `ui/editor/ux/timeline_input_shadow.py`
- `ui/editor/ux/timeline_live_cut_detection.py`
- `ui/home_sidebar_model_menu.py`
- `ui/main/main_automation.py`
- `ui/main/main_personalization.py`
- `ui/timeline/timeline_playhead_overlay.py`
- `ui/timeline/timeline_paint_helpers.py`
- `ui/timeline/timeline_time_window.py`

## Verification Anchors

- Long-file line count:
  `find core ui native tools -path '*/.build/*' -prune -o -type f \( -name '*.py' -o -name '*.swift' -o -name '*.cpp' -o -name '*.hpp' -o -name '*.h' -o -name '*.mm' -o -name '*.m' -o -name '*.qml' \) -print0 | xargs -0 wc -l | sort -nr | head -30`
- Map guard: `tests/test_subtitle_generation_domain_map.py`.
- Long-file split focused guards:
  `tests/test_media_processor_transcribe_split.py`,
  `tests/test_pipeline_cut_boundary_cache.py`,
  `tests/test_timeline_hit_targets.py`,
  `tests/test_editor_roughcut_draft.py`,
  `tests/test_benchmark_mode_profiles.py`,
  `tests/test_timeline_playhead_fit.py`,
  `tests/test_sidebar_terminal_layout.py`.
- Native readiness guard: `tests/test_subtitle_native_readiness.py`.
