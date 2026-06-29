# Project State

## Current Purpose

`AI Subtitle Studio` is a macOS Apple Silicon first Python/PyQt6 desktop app for
accuracy-first subtitle generation, editing, project save/reopen, roughcut
drafting, and repeatable validation.

Primary implementation surfaces:

- App bootstrap and main window: `main.py`, `ui/main/`
- Editor and timeline: `ui/editor/`, `ui/timeline/`
- Video player integration: `ui/editor/video_player_*`, `ui/video_controls.py`
- Subtitle generation and postprocess: `core/engine/`, `core/pipeline/`, `core/subtitle_quality/`
- STT/VAD/audio preprocessing: `core/audio/`, `core/stt_mode/`
- LLM provider and roughcut flow: `core/llm/`, `core/roughcut/`, `ui/roughcut/`
- Project format/save/reopen: `core/project/`, `ui/project/`
- Validation tooling: `tests/`, `tools/qa_suite_runner.py`, `tools/verify_full_media_pipeline.py`

## Current Direction

- Continue the existing Python/PyQt6 source app.
- Keep subtitle quality ahead of speed.
- Keep editor/timeline behavior stable unless the owner explicitly scopes UI/UX changes.
- Keep QML/SceneGraph/OpenGL/Metal-backed UI surfaces out of the default editor path.
- Keep native migration, Swift rewrite, per-pixel NLE writes, and DMG work opt-in. Owner approval exists for the Mac App Store packaging/signing/upload/metadata lane, but signed package, validation, upload, and metadata proof are still required.
- Treat Taption as a reference for subtitle editing rules only; this repo remains `AI Subtitle Studio`.

## Documentation Layout

- Root development doc: `AGENTS.md`
- Docs hub: `docs/README.md`
- Active groups: `docs/planning_queue/ACTION_ITEMS.md`
- Completed archive: `docs/planning_queue/COMPLETED_ACTION_ITEMS.md`
- Product README: `docs/project_reference/PRODUCT_README.md`
- Release notes: `docs/release_notes/RELEASE_v04.00.07.md` and newer
- Validation results: `docs/quality_validation/test_result.md`
- Validation expectations: `docs/quality_validation/test_case.md`
- NLE plan: `docs/nle_engine/NLE_Action.md`
- App Store readiness: `docs/APP_STORE_SUBMISSION_READINESS.md`

The repository root intentionally keeps no active development docs other than
`AGENTS.md`.

## Version / Release

- App version: `04.01.26` from `core/runtime/config.py`
- Project schema version: `04.01.26` from `core/project/project_format.py`
- Latest source-app checkpoint: `docs/release_notes/RELEASE_v04.01.26.md`
- Latest source quick QA artifact: `output/manual_verification/latest/qa_suite_quick_v040117_20260629_0929`
- Latest NLE canonical load-owner rollback-boundary audit: `output/manual_verification/latest/nle_load_owner_rollback_boundary_v040124_20260629_1138/nle_persistence_cutover_audit.md`
- Previous NLE canonical load-owner gate matrix audit: `output/manual_verification/latest/nle_canonical_load_owner_gate_matrix_v040123_20260629_1115/nle_persistence_cutover_audit.md`
- Latest top-level NLE gap projection coverage audit: `output/manual_verification/latest/nle_top_level_gap_projection_v040121_20260629_1041/nle_persistence_cutover_audit.md`
- Latest NLE canonical load-owner review packet: `output/manual_verification/latest/nle_canonical_load_owner_review_packet_v040119_20260629_095907/nle_canonical_load_owner_review_packet.md`
- Latest STT cache default review packet: `output/manual_verification/latest/stt_cache_default_review_packet_v040118_20260629_094703/stt_cache_default_review_packet.md`
- Latest App Store readiness audit: `output/manual_verification/latest/app_store_owner_metadata_values_preflight_v040126_20260629_1228/app_store_readiness_audit.md`
- Latest App Store metadata owner-input package: `output/manual_verification/latest/app_store_metadata_owner_input_package_v040126_20260629_1228/app_store_metadata_owner_input_package.md`

`v04.01.26` is a G0 owner metadata values preflight/import guard checkpoint. It
keeps owner approval separate from upload/submission readiness, requires explicit
owner values JSON before owner metadata can become ready, scans imported owner
copy for forbidden claims, keeps screenshot proof bound to the signed/sandboxed
candidate, and refreshes the owner-input package for the current version. It is
not package creation, signing, validation, upload, submission, UI/UX change, or
owner metadata completion proof.

## Active Groups

The active queue is `docs/planning_queue/ACTION_ITEMS.md`.

- `G0. Mac App Store Launch Program`: close owner metadata, sandbox, signing, package, App Store Connect validation, upload/submission, review, and release gates. Current state remains blocked with `app_store_submission_ready=false`.
- `G1. STT2 / Word Precision Generation Latency Profiling And Accuracy-Preserving Trim`: reduce generation latency only with same-fixture proof and no quality/timing/final-surface regression. Collect-cache defaults remain off until owner approval.
- `G2. Source-App NLE / Taption Editing Continuity`: monitor and preserve the current source-app NLE/Taption editing contracts while keeping full persisted NLE disk-format cutover and native migration gated. Owner-approved `nle_snapshot` and top-level `nle` shadow metadata remain compatibility metadata only until separate proof promotes them.
- `G3. Realtime NLE STT/VAD Track Visibility And Resource-Balanced Scheduling`: runtime lane owner-map, compact live status/feed, scheduler-budget telemetry, live runtime observability proof-harness, strong-evidence gate, representative real-media runtime/status proof, final-overlap deferred-save retry guard, final save/export micro-overlap repair, same-media benchmark acceptance, editor-sequence guard, direct-SRT app-command save/reopen/export, open-media generation active-worker status/cancel/close/quit responsiveness, and active global-canvas responsiveness slices are complete; continue with any additional active-worker final-surface gates only in bounded slices without weakening final authority, slowing generation, mixing final surfaces, or changing UI defaults without owner-approved proof.

## Completed Evidence Policy

Completed proof history should not be duplicated in the active queue. Use these
locations instead:

- `docs/planning_queue/COMPLETED_ACTION_ITEMS.md`
- `docs/quality_validation/test_result.md`
- `docs/release_notes/`
- `output/manual_verification/latest/`
- `.agents/sentinel/handoffs/`

High-value completed evidence families include Taption subtitle segment parity,
final/preview isolation, voice-silence magnet parity, neighbor-collision guard,
NLE runtime/session mutation adoption, save/reopen compatibility, render/export
parity, trace-bundle retention, `v04.01.19` NLE canonical load-owner review proof,
`v04.01.20` top-level NLE compatibility projection proof, `v04.01.21`
top-level NLE gap projection coverage proof, `v04.01.22` App Store blocker
matrix proof, `v04.01.23` NLE canonical load-owner gate matrix proof,
`v04.01.24` NLE canonical load-owner rollback-boundary proof, `v04.01.25`
App Store upload preflight guard proof, and `v04.01.26` owner metadata values
preflight guard proof.

## Must Not Break

- App launch and main-window bootstrap.
- Project open/save/reopen.
- Subtitle generation and final subtitle stability.
- STT1/STT2 candidate separation from final subtitle surfaces.
- Editor timeline rendering, seek, playhead, magnet, split/merge/delete/edit flows.
- SRT/project import/export.
- Roughcut draft generation and sidecar compatibility.
- Existing source-app quick QA and focused tests.

## App Store State

Current target: Mac App Store signed `.pkg` from a sandboxed signed `.app`.

Current blockers:

- Signed `.pkg`, strict App Store-candidate codesign output, package signature output.
- Sandboxed workflow smoke.
- App Store Connect validation.
- Apple Distribution and installer signing identity proof.
- Owner metadata: privacy answers, export compliance, screenshots, support URL, review notes, age rating, release-note copy.

Latest G0 state: `local_packaging_ready=true`, `app_store_submission_ready=false`,
overall stoplight `red`, blocker count `17`. Version lock and packaging template
are green; signed-artifact proof, sandbox smoke, App Store Connect validation,
signing identities, and owner metadata are still red.

Developer ID beta `.dmg` remains a separate opt-in distribution track and must
not be counted as Mac App Store submission proof.

## Next Session Rule

Start from `AGENTS.md`, then `docs/planning_queue/ACTION_ITEMS.md`, then
`docs/README.md`, `docs/HANDOFF.md`, and the specific doc for the requested
group. Do not rely on old root document paths.
