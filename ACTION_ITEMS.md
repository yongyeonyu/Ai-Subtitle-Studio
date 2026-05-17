<!--
Document-Version: 04.00.09-mac-native
Phase: MAC_NATIVE_APPSTORE_V4_0_9_RELEASED
Last-Updated: 2026-05-18
Updated-By: Codex
Purpose: Remaining work queue only.
-->
# ACTION_ITEMS.md - Remaining Work Queue

## Queue Policy

- This file contains only unfinished or parked work.
- Completed items are removed instead of kept as history.
- Release history belongs in `RELEASE_v*.md`.
- Bootstrap and operating rules belong in `AGENTS.md`.
- Native migration details belong in `NATIVE_LIB_PLAN.md`.
- Countable action items are the checked/unchecked rows under **Active Work** only.

## Metadata

```yaml
app_version: "04.00.09"
document_version: "04.00.09-mac-native"
phase: "MAC_NATIVE_APPSTORE_V4_0_9_RELEASED"
next_phase: null
active_item_count: 16
commit_policy: "Commit only when the user explicitly asks."
product_priority: "Accuracy before speed."
native_plan: "NATIVE_LIB_PLAN.md"
```

## Action Execution Rules

- Refactor code when it can be done inside the approved scope without changing behavior.
- After modifying code, perform a code-review pass, fix the review findings, and only then report completion.
- Prefer implementations that improve launch/runtime speed or reduce memory, CPU, disk, or bridge overhead.
- Do not change existing UI, UX, or behavior as part of generic action-item work. If a change appears necessary, leave it as an owner-decision item and ask for approval first.
- When a function-level path can be equal or faster with `.cpp`, `.swift`, `.js`, or another native/runtime language, implement that path with parity tests and a safe Python fallback.
- Store UX-related behavior in separate files under an appropriate `ux/` folder whenever possible so UX scenarios are not accidentally deleted from owner widgets.
- Use real fixtures for action-item verification when execution is required:
  - Macau fixture: `/Users/u_mo_c/Downloads/마카오테스트` for quick UI, UX, playback, restart, and generation smoke checks.
  - Tinyping fixture: `/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.MP4` for long generation, roughcut, ETA, queue, memory, and full-flow checks.
  - Test-video fixture: `/Users/u_mo_c/Downloads/ai_subtitle_studio/test video` for benchmark and regression checks.
  - X5 subtitle fixture: `test video/X5_시승기_후반.MP4` plus its sibling `.srt` for subtitle-accuracy verification slices.
- If the owner asks "how many action items are left?", answer with the number of countable active items that can be executed sequentially in one pass.
- If the owner says "run N items" or "do 5 items", execute the first N unchecked active items in order unless a blocker or owner-decision item is reached.

## Active Work

### P0 - UX And Editor Refactor Boundaries

- [ ] 5. Finish splitting `ui/editor/video_player_widget.py`.
  Scope: transport controls, audio-output recovery, provider adapter, thumbnail/surface handling, and player status widgets.
  Already done: subtitle provider/overlay logic is partially separated.
  Remaining: transport/provider/audio/surface modules plus typed nonfatal logging.
  Verification: Macau playback/audio-output smoke.

- [ ] 6. Split `ui/timeline/timeline_paint.py` into testable paint passes.
  Scope: row layout, final subtitle paint, STT preview paint, helper-line paint, cut-boundary paint, playhead/marker paint, and cache use.
  Success: playback redraw does not leave residues, STT1/STT2 rows remain readable after project open, and each pass is independently testable.
  Verification: Macau playback smoke plus timeline render tests.

- [ ] 7. Create an explicit editor session model for subtitle/STT/preview lanes.
  Scope: canonical segment store, selected STT evidence, final subtitle rows, preview rows, voice activity, and project-save views.
  Success: editor, timeline, video overlay, and save pipeline consume lightweight views of one canonical session model.
  Verification: project-open Tinyping `.aissproj` plus unit tests for save/reload.

### P0 - Architecture And Runtime Reliability

- [ ] 8. Create a project session service for open/save/reopen/resume flows.
  Scope: move lifecycle ownership out of UI panels and large project-manager branches.
  Success: project create/open/save/reopen/linked-SRT flows use one session service and dedicated serialization helpers.
  Verification: project-open/save/reopen tests plus Macau project smoke.

- [ ] 9. Replace direct queue widget mutation with a queue state model.
  Scope: queue table, sidebar queue panel, top card, elapsed/ETA/progress, completion state, and backend queue emits.
  Success: producers emit state updates and stop touching `QTableWidget` internals.
  Verification: queue/sidebar tests and Macau smoke.

- [ ] 10. Continue exception hygiene and structured logging burn-down.
  Scope: replace broad silent catches in high-risk UI/runtime/audio/project/cut-boundary paths with typed nonfatal logging.
  Success: no new broad silent exception patterns in touched files; real failures are visible in terminal or app logs.
  Verification: maintenance guard plus targeted tests for touched files.

- [ ] 11. Refactor cut-boundary helper builders into explicit strategy objects.
  Scope: `core/pipeline/cut_boundary_helpers.py`, `core/cut_boundary_auto_scan.py`, `core/cut_boundary_auto_verify.py`, and related FPS/provisional helpers.
  Success: no giant helper-installer functions remain on the active cut-boundary path.
  Verification: cut-boundary unit tests plus Macau visual smoke.

- [ ] 12. Split `core/pipeline/single_pipeline.py` into planner and progress coordinator.
  Scope: separate media-processing decisions from queue/header updates, autosave, project writes, and UI callbacks.
  Success: subtitle generation behavior is unchanged while execution planning becomes testable without UI state.
  Verification: pipeline tests plus Macau generation smoke.

- [ ] 13. Split audio processing into durable services.
  Scope: extraction, chunking, transcription, VAD, cache decisions, worker pooling, retry policy, and resource cleanup.
  Success: common subprocess/worker cleanup policy is shared and persistent worker ownership is explicit.
  Verification: audio/STT tests plus X5 or Tinyping slice when subtitle accuracy can be affected.

### P1 - Performance, Memory, And Tooling

- [ ] 14. Reduce duplicated segment/project state and lazy-hydrate large assets.
  Scope: editor/timeline/STT/save payload duplication, candidate lattices, preview rows, quality payloads, and large text assets.
  Success: project open/save does not eagerly copy large optional tracks until a lane/panel needs them.
  Verification: project load/save tests plus memory snapshot on Tinyping when relevant.

- [ ] 15. Wire maintenance-budget checks into CI or the release checklist.
  Scope: max file/function length, broad silent-exception regression checks, and legacy allowlist burn-down.
  Success: new oversized functions or silent catch regressions fail before release.
  Verification: `venv/bin/python tools/check_maintenance_budget.py --json`.

- [ ] 16. Add dead-code and stale-QML-binding review.
  Scope: high-confidence unused Python functions, stale QML property bindings, duplicate native cut-boundary paths, and dynamic Qt signal wiring.
  Success: removable dead code is deleted only after static and dynamic wiring checks.
  Verification: targeted symbol scan plus QML/offscreen smoke where applicable.

### P1 - Native Library Queue

- [ ] 17. Benchmark native media-info normalization against the current cached Python path.
  Scope: only probe-result normalization and cache-key shaping, not full ffprobe orchestration.
  Success: native path is kept only if it is equal or faster on real project open/save benchmarks.
  Details: see `NATIVE_LIB_PLAN.md`.

- [ ] 18. Prepare cut-boundary scoring/alignment loops for native migration.
  Scope: isolate deterministic numeric loops after the cut-boundary Python refactor lands.
  Success: Swift/C++ path has parity tests and Python fallback before becoming default.
  Details: see `NATIVE_LIB_PLAN.md`.

- [ ] 19. Prepare subtitle candidate scoring and sequence smoothing for native migration.
  Scope: STT candidate scoring, lattice overlap scoring, subtitle timing, and word resegmenting hot loops.
  Success: native path improves or matches accuracy/speed and does not change final subtitle quality.
  Verification: X5 accuracy slice.

- [ ] 20. Split oversized Swift core files before adding more native features.
  Scope: `TimelineEditing.swift`, `NativePolicyEngine.swift`, and `RuntimeETAEstimator.swift`.
  Success: geometry, magnet, undo, serialization, scoring, retrieval, decision, persistence, and prediction responsibilities are separated.
  Verification: `swift test` in `native/macos/AIStudioNative`.

## Parked Work

- [ ] App Store Connect upload remains blocked on owner Apple Developer credentials, signing identities, App Store Connect API key or app-specific password, and team configuration.

- [ ] Future iPadOS reuse remains a design requirement. Keep Swift-native subtitle, LoRA, deep policy, project I/O, timeline, and waveform logic reusable as Apple-platform core modules, with macOS-only UI/process/file-watcher/packaging code at the edges.
