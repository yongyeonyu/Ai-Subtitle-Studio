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
- Keep native migration, Swift rewrite, per-pixel NLE writes, App Store packaging/upload, and DMG work opt-in.
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

- App version: `04.01.08` from `core/runtime/config.py`
- Project schema version: `04.01.08` from `core/project/project_format.py`
- Latest source-app checkpoint: `docs/release_notes/RELEASE_v04.01.08.md`
- Latest source quick QA artifact: `output/manual_verification/latest/qa_suite_quick_v040100_20260628`
- Latest App Store readiness audit: `output/manual_verification/latest/app_store_v040101_identity_check_20260629_0036/app_store_readiness_audit.md`

`v04.01.08` is a source-app release checkpoint, not App Store submission proof.

## Active Groups

The active queue is `docs/planning_queue/ACTION_ITEMS.md`.

- `G0. Mac App Store Launch Program`: close owner metadata, sandbox, signing, package, App Store Connect validation, upload/submission, review, and release gates. Current state remains blocked with `app_store_submission_ready=false`.
- `G1. STT2 / Word Precision Generation Latency Profiling And Accuracy-Preserving Trim`: reduce generation latency only with same-fixture proof and no quality/timing/final-surface regression. Collect-cache defaults remain off until owner approval.
- `G2. Source-App NLE / Taption Editing Continuity`: monitor and preserve the current source-app NLE/Taption editing contracts while keeping persisted NLE disk fields and native migration gated. The close/deferred-save vector-time boundary blocker is fixed and archived.
- `G3. Realtime NLE STT/VAD Track Visibility And Resource-Balanced Scheduling`: runtime lane owner-map, compact live status/feed, scheduler-budget telemetry, live runtime observability proof-harness, strong-evidence gate, and representative real-media runtime/status proof slices are complete; continue with same-media quality/speed/save-reopen/final-export proof or the observed `nle_save_export_final_overlap` blocker only in bounded slices without weakening final authority, slowing generation, mixing final surfaces, or changing UI defaults without owner-approved proof.

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
parity, trace-bundle retention, and `v04.01.08` source release proof.

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

- Signed `.app`, signed `.pkg`, strict codesign output, package signature output.
- Sandboxed workflow smoke.
- App Store Connect validation.
- Apple Distribution and installer signing identity proof.
- Owner metadata: privacy answers, export compliance, screenshots, support URL, review notes, age rating, release-note copy.

Developer ID beta `.dmg` remains a separate opt-in distribution track and must
not be counted as Mac App Store submission proof.

## Next Session Rule

Start from `AGENTS.md`, then `docs/planning_queue/ACTION_ITEMS.md`, then
`docs/README.md`, `docs/HANDOFF.md`, and the specific doc for the requested
group. Do not rely on old root document paths.
