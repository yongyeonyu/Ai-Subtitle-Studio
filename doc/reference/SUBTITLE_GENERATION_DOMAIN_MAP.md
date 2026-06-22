# Subtitle Generation Domain Map

Generated: 2026-05-24

Purpose: execution artifact for `doc/ACTION_ITEMS.md` item 1. This map records the
current owner files and dependency edges for extracted pure Python facades and
feature-flagged Swift/C++ helper seams.

## Scope Guard

- No UI/UX behavior change is part of this map.
- Subtitle quality gates, STT1/STT2 participation, LLM cleanup, LoRA policy,
  and save/reopen invariants stay unchanged.
- Native helpers are allowed only behind Python parity, feature flags, and real
  fixture verification.
- ANE can only be claimed through Core ML routed work. C++, Metal, MLX, and
  Python loops are GPU/CPU or native-CPU candidates unless a Core ML model is
  actually in the path.

## Current Owner Inventory

- Audio and STT entry: `core/audio/media_processor.py`,
  `core/audio/media_processor_audio.py`,
  `core/audio/media_processor_transcribe.py`,
  `core/audio/media_processor_audio_route.py`,
  `core/audio/media_processor_transcribe_policy.py`,
  `core/audio/media_processor_transcribe_recheck.py`,
  `core/audio/media_processor_transcribe_run.py`,
  `core/audio/media_processor_transcribe_windowed.py`,
  `core/audio/media_processor_vad.py`,
  `core/audio/stt_backend_router.py`, `core/audio/stt_quality_presets.py`,
  `core/audio/stt_lattice_service.py`, `core/audio/stt_recheck_service.py`,
  `core/audio/whisperkit_persistent.py`, `core/audio/whisper_mlx.py`,
  `core/audio/whisper_cpp.py`.
- Subtitle engine and text/timing policy: `core/engine/subtitle_engine.py`,
  `core/engine/subtitle_final_integrity.py`,
  `core/engine/subtitle_llm_runtime.py`,
  `core/engine/subtitle_lora_packaging.py`,
  `core/engine/subtitle_stt_candidate_helpers.py`,
  `core/engine/subtitle_stt_candidate_selection.py`,
  `core/engine/subtitle_cut_boundary.py`,
  `core/engine/subtitle_dictionary.py`,
  `core/engine/subtitle_global_canvas.py`,
  `core/engine/subtitle_live_sync_manager.py`,
  `core/engine/subtitle_live_editor_feed.py`,
  `core/engine/subtitle_segments.py`,
  `core/engine/subtitle_speaker_diarization.py`,
  `core/engine/subtitle_stt_segments.py`,
  `core/engine/subtitle_timing.py`,
  `core/engine/subtitle_timing_contracts.py`,
  `core/engine/subtitle_waveform.py`,
  `core/engine/subtitle_accuracy_pipeline.py`,
  `core/engine/subtitle_accuracy_graph.py`,
  `core/engine/subtitle_prompts.py`,
  `core/engine/subtitle_macro_chunks.py`,
  `core/engine/subtitle_uncertainty.py`,
  `core/engine/srt_writer.py`.
- Pipeline orchestration: `core/pipeline/backend_core.py`,
  `core/pipeline/single_pipeline.py`,
  `core/pipeline/single_pipeline_plan.py`,
  `core/pipeline/subtitle_parallel_manager.py`,
  `core/pipeline/pipeline_helpers.py`,
  `core/pipeline/cut_boundary_helpers.py`,
  `core/pipeline/cut_boundary_segment_ops.py`,
  `core/pipeline/cut_boundary_snapshot.py`,
  `core/pipeline/cut_boundary_strategy.py`,
  `core/pipeline/cut_boundary_cache.py`,
  `core/pipeline/cut_boundary_prescan_policy.py`,
  `core/pipeline/stt_preview_optimizer.py`,
  `core/pipeline/subtitle_buffer_policy.py`,
  `core/pipeline/subtitle_memory_guard.py`,
  `core/pipeline/topicless_segments.py`.
- Native readiness: `core/runtime/subtitle_native_readiness.py`.
- Personalization and correction memory: `core/personalization/runtime_personalization.py`,
  `core/personalization/runtime_lora_context.py`,
  `core/personalization/subtitle_lora_runtime.py`,
  `core/personalization/lora_retrieval_index.py`,
  `core/personalization/lora_retrieval_scoring.py`,
  `core/personalization/lora_gpu_acceleration.py`,
  `core/personalization/lora_trial_scoring.py`,
  `core/personalization/deep_runtime_adaptation.py`,
  `core/personalization/deep_subtitle_policy.py`,
  `core/personalization/user_edit_metrics.py`,
  `core/personalization/deferred_editor_learning.py`.
- Editor/live sync and persistence: `ui/editor/editor_pipeline.py`,
  `ui/editor/editor_pipeline_signal_bridge.py`,
  `ui/editor/editor_pipeline_completion.py`,
  `ui/editor/editor_quality_review.py`,
  `ui/editor/editor_scan_cut_project.py`,
  `ui/editor/editor_segments.py`,
  `ui/editor/editor_segments_live_preview.py`,
  `ui/editor/editor_segments_stt_candidates.py`,
  `ui/editor/editor_segments_stt_selection_flow.py`,
  `ui/editor/editor_segments_timeline_context.py`,
  `ui/editor/editor_save_manager.py`,
  `ui/editor/editor_roughcut_draft.py`,
  `ui/editor/editor_subtitle_post_llm.py`,
  `ui/editor/ux/timeline_input_shadow.py`,
  `ui/editor/ux/timeline_live_cut_detection.py`,
  `ui/editor/video_player_subtitles.py`,
  `ui/editor/video_overlay_widgets.py`.
- Timeline and minimap feed: `ui/timeline/timeline_widget.py`,
  `ui/timeline/timeline_canvas.py`, `ui/timeline/timeline_paint.py`,
  `ui/timeline/timeline_paint_helpers.py`, `ui/timeline/timeline_global.py`,
  `ui/timeline/timeline_waveform.py`, `ui/timeline/timeline_analysis.py`,
  `ui/timeline/stt_preview_layout.py`, `ui/timeline/segment_store.py`.
- Native helper seams already present: `core/native_subtitle_segments.py`,
  `core/native_subtitle_stt_segments.py`, `core/native_subtitle_timing.py`,
  `core/native_subtitle_waveform.py`,
  `core/native_subtitle_global_canvas.py`,
  `core/native_subtitle_resource.py`,
  `core/native_swift_subtitle_segments.py`,
  `core/native_swift_subtitle_stt_segments.py`,
  `core/native_swift_subtitle_timing.py`,
  `core/native_swift_subtitle_waveform.py`,
  `core/native_swift_subtitle_global_canvas.py`,
  `core/native_swift_subtitle_resource.py`,
  `core/native_swift_subtitle_lora_merge.py`,
  `core/native_swift_transcribe_plan.py`,
  `core/native_swift_audio_filter.py`.

## Dependency Flow

```text
media input
  -> subtitle_resource_manager
  -> subtitle_cut_boundary
  -> subtitle_stt
  -> subtitle_stt1_segments
  -> subtitle_stt2_segments
  -> subtitle_llm
  -> subtitle_dictionary
  -> subtitle_lora
  -> subtitle_deep_learning
  -> subtitle_timing
  -> subtitle_segments
  -> subtitle_live_sync_manager
  -> subtitle_live_editor_feed
  -> editor rows / video overlay / saved SRT

subtitle_cut_boundary -> subtitle_roughcut
subtitle_segments -> subtitle_roughcut
subtitle_stt1_segments -> subtitle_global_canvas
subtitle_stt2_segments -> subtitle_global_canvas
subtitle_segments -> subtitle_global_canvas
media input -> subtitle_waveform -> timeline waveform/global canvas
subtitle_speaker_diarization -> subtitle_segments
subtitle_parallel_manager supervises cut/STT/STT2/LLM/roughcut scheduling.
```

## Domain Records

### subtitle_cut_boundary

- Current owners: `core/engine/subtitle_cut_boundary.py`,
  `core/pipeline/cut_boundary_helpers.py`,
  `core/pipeline/cut_boundary_segment_ops.py`,
  `core/pipeline/cut_boundary_snapshot.py`,
  `core/pipeline/cut_boundary_strategy.py`,
  `core/pipeline/cut_boundary_cache.py`,
  `core/pipeline/cut_boundary_prescan_policy.py`,
  `core/roughcut/cut_boundary_placeholder.py`,
  `core/engine/subtitle_timing.py`.
- Inputs: media path, probe metadata, timeline duration, settings, cut-cache
  payload, playhead window.
- Outputs: scene/cut markers, high-confidence boundary evidence, clamp hints
  consumed by timing, roughcut, and editor scan-cut lanes.
- Native candidates: existing native cut-boundary scan/cache helpers, C++ interval
  math, Swift cache-plan payload shaping.
- First facade target: pure boundary evidence and cache-plan module before any
  change to editor scan-cut UI. Initial cache settings/payload facade is now
  `core/engine/subtitle_cut_boundary.py`.
- Extraction status: pipeline project snapshots and saved-boundary segment
  split/snap operations now live in `core/pipeline/cut_boundary_snapshot.py`
  and `core/pipeline/cut_boundary_segment_ops.py` while worker orchestration
  stays in `core/pipeline/cut_boundary_helpers.py`.

### subtitle_stt

- Current owners: `core/audio/media_processor.py`,
  `core/audio/media_processor_transcribe.py`,
  `core/audio/stt_backend_router.py`,
  `core/audio/stt_runtime_policy.py`,
  `core/audio/whisperkit_persistent.py`,
  `core/audio/whisper_mlx.py`, `core/audio/whisper_cpp.py`,
  `core/audio/worker_threads.py`.
- Inputs: grouped audio chunks, backend policy, mode preset, persistent-worker
  state, overlap and word-timestamp settings.
- Outputs: raw transcript rows, word windows, backend diagnostics, partial STT
  progress for the editor.
- Native candidates: WhisperKit/Core ML worker routing, `STTDurationFirstOrder.swift`
  for deterministic duration-first ordering, limited C++ summaries for STT row
  feed validation.
- First facade target: STT orchestration plan and worker lifecycle summary with
  no change to model choice or quality gates.
- Extraction status: long STT orchestration is now split across
  `media_processor_transcribe_policy.py`, `media_processor_transcribe_recheck.py`,
  `media_processor_transcribe_run.py`, and `media_processor_transcribe_windowed.py`;
  final STT candidate selection helpers now live in
  `core/engine/subtitle_stt_candidate_helpers.py` and
  `core/engine/subtitle_stt_candidate_selection.py`.

### subtitle_stt1_segments

- Current owners: `core/pipeline/stt_preview_optimizer.py`,
  `core/engine/subtitle_stt_segments.py`,
  `ui/editor/editor_segments_stt_candidates.py`,
  `ui/editor/editor_segments_stt_selection_flow.py`,
  `ui/editor/editor_segments_live_preview.py`,
  `ui/timeline/stt_preview_layout.py`,
  `ui/timeline/timeline_paint.py`.
- Inputs: STT1 transcript rows, selected candidate metadata, segment timing,
  live-preview stage.
- Outputs: STT1 candidate lane rows, preview counters, timeline feed rows,
  saved candidate-track cache.
- Native candidates: `core/native_subtitle_stt_segments.py`,
  `core/native/_native_subtitle_stt_segments.cpp`,
  `SubtitleSTTSegmentsSummary.swift`.
- First facade target: canonical STT1 lane row schema and timeline feed summary.
- Extraction status: `core/engine/subtitle_stt_segments.py` owns shared STT
  preview timeline row shaping for `core/pipeline/stt_preview_optimizer.py`.

### subtitle_stt2_segments

- Current owners: `core/audio/stt_recheck_service.py`,
  `core/audio/stt_lattice_service.py`,
  `core/engine/subtitle_stt_segments.py`,
  `core/pipeline/stt_preview_optimizer.py`,
  `ui/editor/editor_segments_stt_candidates.py`,
  `ui/timeline/stt_preview_layout.py`,
  `ui/timeline/timeline_paint.py`.
- Inputs: STT2/recheck candidates, lattice matches, word-timestamp windows,
  candidate confidence.
- Outputs: STT2 verification lane rows, selected candidate hints, final segment
  correction evidence.
- Native candidates: `core/native_stt_lattice.py`,
  `core/native_stt_recheck.py`, `core/native_subtitle_stt_segments.py`,
  `SubtitleSTTSegmentsSummary.swift`.
- First facade target: STT2 verification row schema with explicit source and
  timing evidence fields.
- Extraction status: shared STT preview row shaping now uses the same facade as
  STT1 so STT2 lane feed fields stay aligned.

### subtitle_llm

- Current owners: `core/engine/subtitle_engine.py`,
  `core/engine/subtitle_prompts.py`,
  `core/engine/llm_candidate_policy.py`,
  `core/llm/provider_router.py`, `core/llm/provider_registry.py`,
  `core/llm/openai_provider.py`, `core/llm/ollama_provider.py`,
  `core/llm/llama_cpp_provider.py`, `core/engine/subtitle_context_refiner.py`.
- Inputs: STT transcript, candidate windows, prompt settings, provider policy,
  local correction context.
- Outputs: cleaned subtitle text, conservative rewrite decisions, provider
  diagnostics and fallback reason.
- Native candidates: `SubtitleLLMContextPolicy.swift` for deterministic context
  trimming only. Do not move provider calls or prompt policy wholesale.
- First facade target: cleanup request/response envelope and context budget
  calculation.
- Extraction status: LLM runtime wrappers, provider fallback state, verifier
  helpers, and context/annotation utilities now live in
  `core/engine/subtitle_llm_runtime.py`.

### subtitle_deep_learning

- Current owners: `core/personalization/deep_runtime_adaptation.py`,
  `core/personalization/deep_policy_learning.py`,
  `core/personalization/deep_subtitle_policy.py`,
  `core/personalization/golden_regression.py`,
  `core/personalization/user_edit_metrics.py`.
- Inputs: edit metrics, quality history, confidence gates, regression fixture
  outcomes.
- Outputs: runtime policy hints, confidence-gate tuning, learned correction
  decisions.
- Native candidates: none until policy data is isolated and reproducible.
- First facade target: learned-policy payload and reason-code schema.

### subtitle_lora

- Current owners: `core/personalization/subtitle_lora_runtime.py`,
  `core/personalization/runtime_lora_context.py`,
  `core/personalization/lora_retrieval_index.py`,
  `core/personalization/lora_retrieval_scoring.py`,
  `core/personalization/lora_gpu_acceleration.py`,
  `core/personalization/lora_trial_scoring.py`,
  `core/personalization/lora_storage.py`.
- Inputs: subtitle context, speaker/context classification, retrieval index,
  training-plan metadata, runtime settings.
- Outputs: LoRA hints, merge/scoring decisions, retrieval diagnostics,
  personalization bundles.
- Native candidates: `SubtitleLoraSelectiveMerge.swift`, bounded vector scoring
  in Metal/MLX only after parity and package checks.
- First facade target: retrieval result and selective-merge request schema.
- Extraction status: LoRA micro-merge, card packaging, and speaker-line helpers
  now live in `core/engine/subtitle_lora_packaging.py`.

### subtitle_roughcut

- Current owners: `core/roughcut/roughcut_pipeline.py`,
  `core/roughcut/editor_draft.py`,
  `core/roughcut/editor_draft_llm.py`,
  `core/roughcut/editor_draft_chunks.py`,
  `core/roughcut/roughcut_llm.py`, `core/roughcut/major_segmenter.py`,
  `core/roughcut/chapter_segmenter.py`,
  `core/roughcut/subtitle_retimer.py`,
  `ui/editor/editor_roughcut_draft.py`,
  `ui/timeline/timeline_roughcut_paint.py`.
- Inputs: transcript/final subtitle rows, cut markers, topic hints, thumbnail
  cache, roughcut settings.
- Outputs: topic/scene rows, roughcut draft status, EDL/render plans, minimap
  roughcut markers.
- Native candidates: `RoughcutChunkPlanner.swift` for deterministic chunk plan
  shaping only.
- First facade target: roughcut transcript-pack and scene-row payload.
- Extraction status: roughcut LLM provider JSON calls now live in
  `core/roughcut/editor_draft_llm.py`; chunk-boundary planning now lives in
  `core/roughcut/editor_draft_chunks.py`; `core/roughcut/editor_draft.py` keeps
  orchestration and topic/EDL assembly.

### subtitle_dictionary

- Current owners: `core/engine/subtitle_dictionary.py`,
  `core/engine/subtitle_text_policy.py`,
  `core/engine/llm_correction_guard.py`,
  `core/subtitle_quality/candidate_generator.py`,
  `core/personalization/editor_truth_memory.py`,
  `core/personalization/editor_truth_capture.py`,
  `ui/settings/settings_dictionary.py`.
- Inputs: correction dictionary, wrong-answer memory, user edits, LLM cleanup
  before/after pairs.
- Outputs: protected terms, correction candidates, rejected rewrite evidence,
  persisted dictionary updates.
- Native candidates: none. Keep persistence and policy readable in Python until
  the schema stabilizes.
- First facade target: dictionary lookup/update request with immutable before
  and after text.
- Extraction status: `core/engine/subtitle_dictionary.py` now owns immutable
  lookup/update request payloads and wrong-answer phrase removal consumed by
  `core/subtitle_quality/candidate_generator.py`.

### subtitle_timing

- Current owners: `core/engine/subtitle_timing.py`,
  `core/engine/subtitle_timing_contracts.py`,
  `core/engine/subtitle_native_word_split.py`,
  `core/engine/word_resegmenter.py`,
  `core/native_subtitle_timing.py`,
  `ui/editor/ux/timeline_subtitle_segment_editing.py`.
- Inputs: STT word spans, VAD spans, cut-scene bounds, LoRA duration target,
  frame grid, user edit anchors.
- Outputs: adjusted start/end/frame fields, split/merge guards, timing fusion
  diagnostics.
- Native candidates: `core/native/_native_subtitle_timing.cpp`,
  `SubtitleTimingMetrics.swift`, `CommonSplitPlanner.swift`.
- First facade target: timing fusion input/output schema and frame-field
  invariant checks.
- Extraction status: `core/engine/subtitle_timing_contracts.py` now owns pure
  timing bounds, timing scope keys, compact text matching, frame-field payload
  construction, and timing-fusion policy payloads consumed by
  `core/engine/subtitle_timing.py`.

### subtitle_parallel_manager

- Current owners: `core/pipeline/backend_core.py`,
  `core/pipeline/single_pipeline.py`,
  `core/pipeline/single_pipeline_plan.py`,
  `core/pipeline/subtitle_parallel_manager.py`,
  `core/pipeline/pipeline_helpers.py`,
  `core/runtime/multi_process.py`,
  `core/pipeline/subtitle_memory_guard.py`.
- Inputs: file queue, selected mode, hardware profile, worker budgets, stage
  dependencies, cancel/exit signals.
- Outputs: bounded stage execution, worker-count plans, live progress, stop and
  cleanup state.
- Native candidates: deterministic planning summaries only. Keep subprocess,
  model-worker lifetime, and UI callbacks in Python/Qt owners.
- First facade target: stage DAG and budget plan value object.
- Extraction status: `core/pipeline/subtitle_parallel_manager.py` now owns pure
  queue progress, cut-boundary iteration planning, and subtitle stage DAG
  contracts consumed through `core/pipeline/single_pipeline_plan.py`.

### subtitle_resource_manager

- Current owners: `core/runtime/subtitle_resource_manager.py`,
  `core/runtime/multi_process.py`,
  `core/native_resource_allocator.py`,
  `core/native_subtitle_resource.py`,
  `core/native_swift_subtitle_resource.py`,
  `core/runtime/hardware_profile.py`.
- Inputs: hardware topology, settings, memory pressure, active runtime labels,
  accelerator flags.
- Outputs: resource plan, accelerator summary, native/Python fallback labels,
  Apple core/memory pressure hints.
- Native candidates: `core/native/_native_subtitle_resource.cpp` for summaries;
  scheduling ownership stays in Python.
- First facade target: resource-plan request and accelerator summary schema.
- Extraction status: `core/runtime/subtitle_resource_manager.py` now also owns
  accelerator name normalization and mixed accelerator parallelism floor
  decisions consumed by `core/runtime/multi_process.py`.

### subtitle_live_sync_manager

- Current owners: `ui/editor/editor_pipeline_signal_bridge.py`,
  `core/engine/subtitle_live_sync_manager.py`,
  `ui/editor/editor_pipeline_status.py`,
  `ui/editor/editor_pipeline_completion.py`,
  `ui/editor/editor_segments_queue_flush.py`,
  `ui/editor/video_player_subtitles.py`.
- Inputs: backend progress events, stage text, live segment rows, final segment
  completion, save/export status.
- Outputs: editor rows, video overlay context, progress card/sidebar status,
  timeline refresh events.
- Native candidates: none. This is a Qt/Python bridge surface.
- First facade target: event payload normalizer between backend and editor.
- Extraction status: `core/engine/subtitle_live_sync_manager.py` now owns pure
  live progress/status normalization and cut-boundary topicless live payload
  shaping consumed by `ui/editor/editor_pipeline_status.py` and
  `ui/editor/editor_pipeline_signal_bridge.py`.

### subtitle_live_editor_feed

- Current owners: `ui/editor/editor_segments_live_preview.py`,
  `ui/editor/editor_segments_bulk_prepare.py`,
  `ui/editor/editor_segments_bulk_load.py`,
  `ui/editor/editor_segments_stt_selection_flow.py`,
  `ui/editor/editor_segments_runtime_cache.py`,
  `ui/editor/editor_session_model.py`.
- Inputs: in-progress STT/subtitle preview rows, selected candidate rows,
  editor session state.
- Outputs: row insert/update batches, provisional/final row state, undo-safe
  editor session changes.
- Extraction status: `core/engine/subtitle_live_editor_feed.py` now owns the
  immutable confirmed/STT-preview/subtitle-preview feed payload assembled by
  `ui/editor/editor_segments_stt_selection_flow.py`.
- Native candidates: none. Mutable editor state remains Python/Qt.
- First facade target: immutable row batch payload before it touches widgets.

### subtitle_segments

- Current owners: `core/engine/subtitle_engine.py`,
  `core/engine/subtitle_segments.py`,
  `core/engine/srt_writer.py`, `core/native_subtitle_segments.py`,
  `ui/editor/editor_segments.py`,
  `ui/editor/editor_segments_text_ops.py`,
  `ui/editor/editor_segments_manual_edits.py`,
  `ui/editor/editor_segments_reload.py`,
  `ui/editor/editor_save_manager.py`,
  `core/project/project_assets.py`.
- Inputs: cleaned subtitle rows, timing policy output, manual edits, saved
  project/SRT assets.
- Outputs: canonical final rows, merge/split/save/reopen invariants, SRT files,
  project candidate tracks.
- Native candidates: `core/native/_native_subtitle_segments.cpp`,
  `SubtitleSegmentsSummary.swift`, `SubtitleAssemblyPlanner.swift` for summaries
  and deterministic assembly checks.
- First facade target: canonical segment schema with save/reopen invariant tests.
- Extraction status: `core/engine/subtitle_segments.py` now owns the pure
  save/reopen segment preparation facade used by `core/engine/srt_writer.py`.
  Final sequence cleanup, filler/closing/tiny-fragment rules, and STT anchor
  integrity guards now live in `core/engine/subtitle_final_integrity.py`.

### subtitle_waveform

- Current owners: `ui/timeline/timeline_waveform.py`,
  `ui/timeline/timeline_canvas.py`,
  `core/engine/subtitle_waveform.py`,
  `core/native_subtitle_waveform.py`,
  `core/audio/audio_display.py`,
  `core/audio/media_processor_audio.py`.
- Inputs: extracted audio samples, cached waveform arrays, timeline duration and
  zoom range.
- Outputs: downsampled waveform columns, timeline paint feed, minimap waveform
  cache.
- Native candidates: `core/native/_native_subtitle_waveform.cpp`,
  `SubtitleWaveformSummary.swift`, `WaveformPeaks.swift`, vDSP/Accelerate for
  vector reductions.
- First facade target: waveform downsample request and cache key schema.
- Extraction status: `core/engine/subtitle_waveform.py` now owns global-canvas
  waveform column feed calculation for `ui/timeline/timeline_global.py`.

### subtitle_global_canvas

- Current owners: `ui/timeline/timeline_global.py`,
  `core/engine/subtitle_global_canvas.py`,
  `ui/timeline/timeline_analysis.py`,
  `core/native_subtitle_global_canvas.py`,
  `core/native_swift_subtitle_global_canvas.py`,
  `ui/timeline/segment_store.py`.
- Inputs: final subtitle rows, STT1/STT2 rows, roughcut/topicless markers,
  VAD/silence intervals, timeline duration.
- Outputs: minimap lane summaries, merged global-canvas intervals, coverage and
  gap diagnostics.
- Native candidates: `core/native/_native_subtitle_global_canvas.cpp`,
  `SubtitleGlobalCanvasSummary.swift`. This remains a data-summary helper, not
  a QML/SceneGraph UI rewrite.
- First facade target: dense lane summary request using duration, bin count, and
  start/end/lane rows.
- Extraction status: `core/engine/subtitle_global_canvas.py` now owns minimap
  lane row preparation and merge-helper request shaping for
  `ui/timeline/timeline_global.py`.

### subtitle_speaker_diarization

- Current owners: `core/audio/diarize.py`,
  `core/engine/subtitle_speaker_diarization.py`,
  `core/pipeline/pipeline_helpers.py`,
  `core/audio/media_processor_vad.py`,
  `ui/editor/editor_speaker_ops.py`,
  `ui/timeline/speaker_labels.py`,
  `core/speaker_profile_settings.py`.
- Inputs: diarization backend output, VAD ranges, speaker profile settings,
  editor speaker-map edits.
- Outputs: speaker ids, two-speaker row payloads, speaker label paint state,
  saved project speaker metadata.
- Native candidates: none until speaker schema and real fixture parity are
  isolated.
- First facade target: speaker map and row annotation payload.
- Extraction status: `core/engine/subtitle_speaker_diarization.py` now owns
  pure speaker-id normalization, speaker-map segment lookup, inline
  two-speaker dialogue restoration, and runtime row grouping consumed through
  `core/pipeline/pipeline_helpers.py` and `core/audio/diarize.py`.

## First Extraction Order

1. `subtitle_segments`: lock canonical row schema before more native summaries.
2. `subtitle_stt1_segments` and `subtitle_stt2_segments`: stabilize timeline
   feed rows and restore/save candidate-track behavior.
3. `subtitle_resource_manager`: keep resource reporting separate from worker
   execution and UI semantics.
4. `subtitle_global_canvas` and `subtitle_waveform`: summarize data for paint
   without changing the 2D Qt widget renderer.
5. `subtitle_timing`: extract timing fusion contracts only after segment schema
   drift is guarded.
6. `subtitle_parallel_manager`: introduce stage DAG value objects once the
   downstream domains are stable.
7. `subtitle_cut_boundary` and `subtitle_dictionary`: keep pure policy/cache
   payloads separate from worker execution, persistence, and UI dialogs.
8. `subtitle_live_editor_feed`: isolate feed payload assembly while leaving
   QTextEdit, timeline, and video player ownership in Qt/Python.
9. `subtitle_speaker_diarization`: isolate row payload shaping while leaving
   diarization backend/model ownership and speaker UI edits in their existing
   Python owners.

## Verification Anchors

- Long-file ownership guard: `doc/reference/LONG_FILE_OWNERSHIP_MAP.md`.
- Unit guard for this map: `tests/test_subtitle_generation_domain_map.py`.
- First facade guard: `tests/test_subtitle_segments_facade.py`.
- STT feed facade guard: `tests/test_subtitle_stt_segments_facade.py`.
- Global canvas facade guard: `tests/test_subtitle_global_canvas_facade.py`.
- Waveform facade guard: `tests/test_subtitle_waveform_facade.py`.
- Timing contract guard: `tests/test_subtitle_timing_contracts.py`.
- Parallel manager guard: `tests/test_subtitle_parallel_manager.py`.
- Cut-boundary facade guard: `tests/test_subtitle_cut_boundary_facade.py`.
- Dictionary facade guard: `tests/test_subtitle_dictionary_facade.py`.
- Live editor feed facade guard:
  `tests/test_subtitle_live_editor_feed_facade.py`.
- Live sync manager facade guard: `tests/test_subtitle_live_sync_manager.py`.
- Speaker diarization facade guard:
  `tests/test_subtitle_speaker_diarization_facade.py`.
- Project reopen cross-facade guard:
  `tests/test_subtitle_facade_project_reopen_contracts.py`.
- Native readiness/fallback guard: `tests/test_subtitle_native_readiness.py`.
- Existing fast guards:
  `tests/test_native_subtitle_segments.py`,
  `tests/test_native_subtitle_stt_segments.py`,
  `tests/test_native_subtitle_timing.py`,
  `tests/test_native_subtitle_waveform.py`,
  `tests/test_native_subtitle_global_canvas.py`,
  `tests/test_native_subtitle_resource.py`,
  `tests/test_subtitle_resource_manager.py`,
  `tests/test_runtime_multi_process.py`,
  `tests/test_subtitle_engine_settings.py`,
  `tests/test_project_segment_reload.py`,
  `tests/test_timeline_playhead_fit.py`.
- Real-app gate before enabling a native helper by default: High-mode app run on
  the current representative DJI/X5/Macau fixture with terminal logs, timeline,
  editor rows, video overlay, STT1/STT2 rows, global canvas, waveform, and saved
  SRT checked together.
