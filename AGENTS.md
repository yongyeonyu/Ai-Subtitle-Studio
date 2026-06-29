삭제 금지: 대표님 명시 지시 없이 이 첫 줄, 삭제 금지 블록, 존댓말 규칙, 에이전트 역할 정의를 수정하거나 삭제하지 말 것.
<!-- 수정/삭제 금지: owner-requested behavioral guidelines. Keep this protected block at the very top of AGENTS.md. -->
# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 0. Owner Communication And Agent Roles

**The owner is the representative. Agents are staff. Use respectful Korean honorifics. Never use casual speech with the owner.**

- Address the owner respectfully as `대표님` when context calls for direct address.
- Reply to the owner in polite Korean honorifics by default.
- Do not use 반말, jokingly familiar tone, or peer-to-peer phrasing with the owner.
- If an agent accidentally uses casual speech, acknowledge it briefly, correct the tone immediately, and continue the work.

Protected agent roles:

- `덱스`: head operator and implementation owner on the Codex side. Reads `AGENTS.md` and `ACTION_ITEMS.md`, protects dirty worktree boundaries, applies narrow patches, runs verification, and leaves concise Korean reports for the owner.
- `한결`: senior developer reviewer on the Antigravity side. Reviews architecture boundaries, maintainability, rollback safety, Apple Silicon/macOS realities, state ownership, resource lifetime, and whether a change risks subtitle quality.
- `서린`: strict QE reviewer on the Antigravity side. Assumes the implementation may be wrong, demands real fixture evidence, checks subtitle count/final segment count, save/reload, seek/playhead, overlay, gutter, minimap, memory pressure, and misleading test confidence.
- `유진`: editor workflow reviewer on the Antigravity side. Reviews whether real subtitle editing flows are efficient, understandable, and safe for the user's work, without proposing UI/UX changes beyond the owner's explicit scope.
- `잼민이`: utility delegate for owner-directed chores. Handles simple repetitive work, lightweight file reads, doc sync, narrow code search, bounded refactoring prep, and other clearly scoped support tasks before escalating to the specialist viewpoints above when needed.

Role ownership default:

- Codex owns `덱스` implementation work.
- Antigravity owns the `한결`, `서린`, and `유진` review, QE/QA, and workflow-review viewpoints.
- `잼민이` may assist Antigravity with prep work, evidence gathering, and owner-directed chores.
- At suitable checkpoints, `덱스` may explicitly assign file-scoped code review to Antigravity for one or more named files, then fold that feedback back into the final implementation or rollback decision.
- When the active steering queue becomes crowded, or when `덱스` judges a task to be bounded, low-risk, and reviewable, `덱스` may proactively delegate that slice to `잼민이` without waiting for separate owner wording, then supervise the result before adoption.
- As a default working style, when the owner assigns a non-trivial task to `덱스`, `덱스` should look for at least one bounded support slice that `잼민이` can handle in parallel such as file reading, candidate scouting, targeted review, doc sync, or validation prep, unless the task is too small, too urgent, or too risky to split safely.
- Strengthened default: `덱스` should not keep simple, repetitive, or low-risk support work on the Codex side when `잼민이` can take it safely. Simple chores, narrow searches, file reading, shortlist building, doc cleanup, handoff drafting, status summarization, targeted review prep, and validation prep should default to `잼민이` first.
- Before starting or continuing any non-trivial implementation slice, `덱스` should check whether there is at least one bounded support task that can be delegated immediately. If so, hand that slice to `잼민이` instead of doing all support work alone.
- If `잼민이` appears idle while `덱스` is still working on a larger task, `덱스` should queue the next safe simple slice for `잼민이` right away unless no such slice exists.
- When `잼민이` reports that a delegated task is done, `덱스` should treat that as a review checkpoint: pull the result immediately, inspect it before assigning more work, and decide accept / revise / defer before the next batch continues.
- If `덱스` creates an explicit `잼민이` queue in `ACTION_ITEMS.md` or sends an equivalent ordered queue message, `잼민이` may consume that queue top-to-bottom without waiting between items only when every queued item is simple, bounded, and draft/review/doc/prep-only. In that mode, `잼민이` should still label each item result with `DEX_REVIEW_READY`, but may continue to the next queued simple item unless the owner or `덱스` says stop.
- If the owner says `잼민이 멈춰`, treat that as an immediate stop order for the current Antigravity task. `잼민이` should stop the in-flight work, avoid starting follow-up work, and leave at most a three-line status note before waiting.
- If the owner says `잼민이 하던 일 모두 취소`, treat that as a broader cancel order: stop the current task, cancel queued follow-up batches or auto-continuation, and remain idle until the next explicit owner or `덱스` instruction.

When planning meaningful app changes, Dex should still gather the `한결`, `서린`, and `유진` viewpoints before giving the owner a recommendation, but those review passes should default to the Antigravity side unless the owner explicitly asks otherwise.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
<!-- 삭제 금지 끝: owner-requested behavioral guidelines. -->

<!--
Document-Version: 04.01.29-source-app
Phase: SOURCE_APP_CONTINUATION_V4_1_0
Last-Updated: 2026-06-29
Updated-By: Codex
Purpose: Agent bootstrap, operating rules, documentation map, and new-chat continuation prompt.
-->
# AGENTS.md - Agent Bootstrap Guide

## Project

- Path: `/Users/u_mo_c/Downloads/ai_subtitle_studio`
- App version in code: `04.01.29`
- Latest release checkpoint: `v04.01.29`
- Platform: macOS, Apple Silicon first.
- Product priority: subtitle quality before speed; optimize runtime only with behavior-preserving tests.
- UI/UX rule: do not change UI, UX, labels, layout, colors, shortcuts, menus, or popup behavior unless the owner explicitly asks.
- Current product direction: continue the existing Python/PyQt6 source app. Do not reopen native migration planning unless the owner explicitly asks.
- Root documentation rule: keep `AGENTS.md` as the only development-documentation file at the repository root. All other development docs live under `docs/`.
- Release note retention: keep `docs/release_notes/RELEASE_v04.00.07.md` and newer only. Older release notes and `check_list.md` were intentionally deleted.

## Bootstrap Order

Read these first when continuing work:

1. `AGENTS.md`
2. `docs/planning_queue/ACTION_ITEMS.md`
3. `docs/planning_queue/COMPLETED_ACTION_ITEMS.md`
4. `docs/README.md`
5. `docs/PROJECT_STATE.md`
6. `docs/FEATURE_REGISTRY.md`
7. `docs/ARCHITECTURE.md`
8. `docs/VALIDATION.md`
9. `docs/HANDOFF.md`
10. `docs/project_reference/File_structure.txt`
11. `docs/project_reference/CODEMAP.md` if present
12. Latest `docs/release_notes/RELEASE_v*.md`
13. `docs/project_reference/PRODUCT_README.md`
14. `docs/quality_validation/test_case.md`
15. `docs/quality_validation/test_result.md`
16. `docs/planning_queue/waste_action_item.md`
17. `docs/planning_queue/lesson_n_learned.md`
18. `check_list.md` only if a historical local copy is present; do not recreate it.

## Jammini Communication Check

Before relying on `잼민이` for non-trivial support work, verify the local Antigravity route with the repo-local Taption-derived helpers:

```bash
tools/jammini_watchdog.sh --status
tools/jammini_watchdog.sh --handoff-probe
```

Every Jammini packet sent from this repo must name the project as `AI Subtitle Studio` and the repo root as `/Users/u_mo_c/Downloads/ai_subtitle_studio`. Taption and Taption Encoder are reference projects only; do not label this lane, delegated scope, artifact path, or proof target as Taption/Taption Encoder unless explicitly comparing against those source references.

`--queue-status` is kept as an alias for `--status` for older handoff notes. The reliable source of truth is the physical handoff path:

- `.agents/sentinel/handoffs/*.md`
- `.agents/sentinel/handoff.md`
- `.agents/sentinel/agents/*.md` for stable 한결/서린/유진 role cards adapted from Taption's Jammini communication pack
- `.agents/sentinel/BRIEFING.md` for compact current-state orientation only; `docs/planning_queue/ACTION_ITEMS.md` and `docs/HANDOFF.md` remain authoritative

Chat `ACK` / `WORKING` messages are diagnostic only. Treat a Jammini result as delivered only after `덱스` directly reads the handoff file and classifies it as accept, revise, defer, or reject.

Taption's `docs/agent_communication` Jammini pack is mapped locally in `docs/agent_communication/README.md`. Do not move physical handoffs under `docs/agent_communication`; this repo's reliable handoff store remains `.agents/sentinel/`.

When validating the current release baseline, also read:

- `output/manual_verification/latest/qa_suite_full_20260522_081710/suite_result.md`

Former standalone handoff/planning files have been consolidated:

- `idea_item.md` -> merged into `docs/planning_queue/ACTION_ITEMS.md`
- `NATIVE_LIB_PLAN.md` -> merged into `docs/planning_queue/ACTION_ITEMS.md`
- `NEW_CHAT_PROMPT.md` -> merged into this file

Do not recreate those files unless the owner explicitly asks.

## Document Roles

- `AGENTS.md`: this root bootstrap, operating-rule, documentation-map, and new-chat continuation file.
- `docs/planning_queue/ACTION_ITEMS.md`: single source of truth for active ideas, action/native work, execution order, QA gates, rollback rules, and parked candidates.
- `docs/planning_queue/COMPLETED_ACTION_ITEMS.md`: owner-requested archive for completed action-item history that should not remain in the active queue.
- `docs/README.md`: docs entrypoint and AI navigation order.
- `docs/PROJECT_STATE.md`: current product state and high-level guardrails snapshot.
- `docs/FEATURE_REGISTRY.md`: feature owner map and safe validation entrypoints.
- `docs/ARCHITECTURE.md`: repo structure and boundary map.
- `docs/VALIDATION.md`: standard validation commands and completion bar.
- `docs/HANDOFF.md`: rolling next-session handoff; update before finishing meaningful work.
- `docs/agent_communication/README.md`: Taption Jammini pack mapping for this repo; points to `.agents/sentinel` as the physical handoff store.
- `docs/workflow_operations/cooperation.md`: Dex/Jammini collaboration contract, role boundaries, route proof, NLE parallel packet protocol, and unknown-cause debugging protocol.
- `.agents/sentinel/BRIEFING.md`: compact Jammini orientation file for the current mission, constraints, artifact index, and source-of-truth pointers. Do not use it as a second queue.
- `docs/planning_queue/waste_action_item.md`: rejected or ineffective experiments. Check it before proposing or repeating optimization ideas.
- `docs/planning_queue/lesson_n_learned.md`: repeat-prevention lessons for bad diagnoses, ineffective optimizations, and risky shortcuts.
- `docs/project_reference/PRODUCT_README.md`: product overview and current user-facing workflow.
- `docs/quality_validation/test_case.md`: QA rules, fixture registry, and one-command QA expectations.
- `docs/quality_validation/test_result.md`: latest QA evidence and artifact references.
- `docs/release_notes/RELEASE_v*.md`: release notes from `v04.00.07` onward.

Completed item rule:

- When an item in `docs/planning_queue/ACTION_ITEMS.md` is completed normally, remove it from the active queue and move the completed action-item summary to `docs/planning_queue/COMPLETED_ACTION_ITEMS.md`.
- Preserve detailed completion evidence in release notes, `docs/quality_validation/test_result.md`, `output/manual_verification/latest/`, `docs/planning_queue/waste_action_item.md`, or `docs/planning_queue/lesson_n_learned.md` only when it is needed for future decisions.

## Development Documentation Organization

- Use Taption-style role folders under `docs/` as canonical development-documentation locations.
- Do not create new root development docs. If a new doc is needed, place it under the matching `docs/` role folder and update `docs/README.md`.
- Put new development docs in the matching role folder: `planning_queue/`, `workflow_operations/`, `project_reference/`, `quality_validation/`, `product_behavior/`, `nle_engine/`, `speech_stt/`, `validation_evidence/`, `release_notes/`, `archive_legacy/`, or `DECISIONS/`.
- `docs/README.md` is the development-documentation hub. Update it when adding a new document category or changing canonical pointers.
- `docs/planning_queue/ACTION_ITEMS.md` must stay active-only: remaining work, current acceptance gates, rollback rules, and short archive pointers. Completed slices must move to `docs/planning_queue/COMPLETED_ACTION_ITEMS.md`.
- Docs, handoffs, and review packets are not behavior proof by themselves. Pair behavior claims with tests, runtime artifacts, generated evidence, or release validation.
- Physical Jammini handoff files remain authoritative. Chat `ACK` / `WORKING` messages are diagnostic only until `덱스` reads and classifies the handoff file.
- Clean-room reference rule: Taption docs and AGENTS may inform local structure, but do not copy external prompts/scripts/code or label this repo, delegated scope, artifact path, or proof target as Taption.

## Current Continuation State

- One-command QA runner is the official real-app test entrypoint:
  - `./venv/bin/python tools/qa_suite_runner.py quick`
  - `./venv/bin/python tools/qa_suite_runner.py major`
  - `./venv/bin/python tools/qa_suite_runner.py full`
- Latest known one-command full QA pass:
  - `output/manual_verification/latest/qa_suite_full_standard_x5_restored_20260626_0901`
  - command: `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py full --output-dir output/manual_verification/latest/qa_suite_full_standard_x5_restored_20260626_0901`
  - result: pass, `failed_count=0`
  - scenarios: `editor_compact_macau`, `video_menu_macau`, `save_export_macau`, `menu_stt_lora_macau`, `roughcut_reopen_macau`, `roughcut_interaction_macau`, `roughcut_candidate_macau`, `roughcut_release_audit_macau`, `x5_high_rolling_180s`
  - note: the default X5 path `test video/X5_시승기_후반.MP4` was restored as an ignored local fixture from the existing X5 video-only `.mov` plus the real X5 raw WAV; no `AI_SUBTITLE_STUDIO_QA_X5_MEDIA` override was used.
- Latest source-app quick smoke for the current release line:
  - `output/manual_verification/latest/qa_suite_quick_v040117_20260629_0929`
  - command: `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/qa_suite_runner.py quick --output-dir output/manual_verification/latest/qa_suite_quick_v040117_20260629_0929`
  - result: pass, `profile=quick`, `scenario_count=1`, `passed=1`, `failed_count=0`, scenario `editor_compact_macau`
  - scope note: source-app editor workflow baseline only; not signed package, sandbox smoke, App Store validation/upload/submission, owner metadata, full QA, real-media STT quality, or roughcut proof.
- Latest release checkpoint scope:
  - `v04.01.29` - G2 owner-approved runtime `_nle_project_state` persistence opt-in proof, tied only to explicit standalone `nle_snapshot` canonical load-source policy. This writes and reloads `_nle_project_state` as a supplemental approved runtime-state payload, preserves legacy `editor_state` rollback rows, keeps default project load/save/export authority unchanged, bumps version/schema to `04.01.29`, refreshes the NLE cutover audit, and leaves full disk-format cutover blocked. It does not replace legacy `editor_state`, change Direct SRT precedence, change roughcut sidecars, declare final NLE disk-format cutover, change UI/UX, or provide App Store submission proof.
- Current NLE action source:
  - `docs/nle_engine/NLE_Action.md`
  - status: bounded runtime/session NLE mutation ownership is adopted for covered release-commit paths. Owner-approved top-level `nle` canonical load opt-in is available only when paired with matching `nle_snapshot`; owner-approved standalone `nle_snapshot` load-source opt-in is available only under the explicit snapshot policy payload; and owner-approved `_nle_project_state` persistence is available only as a supplemental runtime-state payload tied to that standalone snapshot policy. Legacy disk-shape replacement and final cutover remain gated.
  - fixed fixture for next cut-boundary proof: `/Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT/내 프로젝트 (3).MP4`, target transitions `2765 -> 2766` and `2675 -> 2676`.
- Latest focused guard set for `v04.01.29`:
  - G2 runtime-state persistence opt-in policy: `_nle_project_state` can persist only as an approved supplemental runtime-state payload when the explicit standalone `nle_snapshot` canonical-load policy is present. Compatibility-only, forged, empty, ambiguous, and policy-incomplete payloads still fail closed to legacy/snapshot-approved paths.
  - G2 runtime-state persistence audit: `output/manual_verification/latest/nle_runtime_state_persistence_v040129_20260629_140053/nle_persistence_cutover_audit.md` -> `status=blocked`, `app_version=04.01.29`, `prep_ready=true`, `persistence_cutover_ready=false`, matrix `overall_stoplight=red`, ready/blocked gates `10/2`, current canonical owner `nle_snapshot`, `nle_snapshot_canonical_load_source_allowed=ready`, and `runtime_project_state_persistence_allowed=ready`.
  - Runtime-state opt-in proof: loaded/runtime/reloaded/storage snapshot/runtime first caption text stays `runtime persisted snapshot first`; cache-hit read/resave hydrates runtime state; legacy `editor_state` first caption text after resave remains `first` for rollback; storage after resave has `_nle_project_state` only for the explicit approved payload and no top-level `nle`, readback report, or quarantine.
  - Remaining blocked gates: `legacy_disk_shape_replacement_allowed` and `final_cutover_ready`.
  - Compile check: `./venv/bin/python -m py_compile core/project/nle_persistence_guard.py core/project/nle_project_state.py core/project/project_io.py core/project/project_format.py tools/audit_nle_persistence_cutover.py tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py core/runtime/config.py` -> pass.
  - Focused NLE guard: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py tests/test_nle_persistence_cutover_audit.py tests/test_macos_bundle_runtime_paths.py` -> `30 passed`.
  - Audit generation: `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_runtime_state_persistence_v040129_20260629_140053` -> `status=blocked`, ready/blocked gates `10/2`, blockers `legacy_disk_shape_replacement_allowed`, `final_cutover_ready`.
  - project/status guard: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_cp03_cp04_status_ui.py -k "schema or version or project_file_roundtrip or status"` -> `66 passed, 80 deselected`
  - cancel proof: `output/manual_verification/latest/g3_open_media_generation_responsiveness_v040113_cancel_20260629_083050/report.md` -> `open-media`/`start-current-pipeline` ok, active `ST_PROC/backend_active=true`, status/guided-status command elapsed samples below `0.01s`, cancel returned `current_pipeline_cancel_requested`, and post-cancel status was `ST_IDLE/backend_active=false`
  - close proof: `output/manual_verification/latest/g3_open_media_generation_responsiveness_v040113_close_20260629_083123/report.json` -> `app-close-request` returned while active in `0.009954s`, then bridge became `app_unreachable` after app exit
  - quit proof: `output/manual_verification/latest/g3_open_media_generation_responsiveness_v040113_quit_20260629_083225/report.json` -> `app-quit-request` returned while active in `0.001577s`, then bridge became `app_unreachable` after app exit
  - Direct SRT focused guard: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "direct_srt_rows_to_runtime_nle_state or direct_srt_readback_drift_without_overwriting_srt_rows" tests/test_editor_autosave_cleanup.py -k "direct_srt_mode or direct_srt_micro_overlap"` -> `2 passed, 140 deselected`
  - direct version assertion: `APP_VERSION=04.01.29`, `PROJECT_SCHEMA_VERSION=04.01.29`
  - `git diff --check -- .` -> pass
  - active global-canvas proof: `output/manual_verification/latest/g3_global_canvas_responsiveness_v040114_20260629_084817/report.md` -> `open-media`/`start-current-pipeline` ok, active `ST_PROC/backend_active=true`, timeline zoom/fit/time-window/max plus zoom-max/play/pause/status/guided-status all `ok=true`, max command elapsed `0.267435s`, `19` nonzero snapshots, final track count stayed `0`, cancel returned to `backend_active=false`
  - prior physical Jammini probe remains `.agents/sentinel/handoffs/20260629-070211-watchdog-handoff-probe.md` -> `DEX_REVIEW_READY`; current `--handoff-probe` packet did not produce a fresh physical handoff file, so do not overclaim a new physical route proof from it.
  - three sub-agent reviews converged on keeping this G2 slice opt-in-only and non-cutover: `_nle_project_state` must remain supplemental to the explicit `nle_snapshot` policy, default project authority must remain unchanged, Direct SRT precedence and roughcut sidecars must not drift, and `legacy_disk_shape_replacement_allowed` / `final_cutover_ready` must remain blocked.
- Latest full QA X5 rolling summary:
  - artifact: `output/manual_verification/latest/qa_suite_full_standard_x5_restored_20260626_0901/x5_high_rolling_180s`
  - `total_elapsed_sec=48.511`
  - `pipeline_elapsed_sec=48.327`
  - `peak_rss_bytes=765329408`
  - `final/raw=55/56`
  - note: this used the default X5 MP4 path without explicit override.
- Recent live-app STT recovery check:
  - artifact: `output/manual_verification/latest/20260522_stt_zero_result_fallback_live`
  - `snapshot_after_early_stt.png` shows subtitles appearing from `00:00.000` while generation is still in progress.
  - log evidence confirmed early STT preview, rolling STT, and Fast-STT2 activity.
- Current active queue source: `docs/planning_queue/ACTION_ITEMS.md`, section `Active Execution Groups`.
- Current active groups: `G0 Mac App Store`, `G1 STT2 / Word Precision`, `G2 Source-App NLE`, and `G3 Realtime NLE STT/VAD`.
- Latest completed action-item slice: `v04.01.29 G2 Runtime _nle_project_state Persistence Opt-In Proof`.
- Current G0 App Store evidence snapshot:
  - latest blocker matrix audit: `output/manual_verification/latest/app_store_owner_metadata_values_preflight_v040126_20260629_1228/app_store_readiness_audit.md`
  - latest metadata owner-input package: `output/manual_verification/latest/app_store_metadata_owner_input_package_v040126_20260629_1228/app_store_metadata_owner_input_package.md`
  - current readiness state: `local_packaging_ready=true`, `app_store_submission_ready=false`, overall stoplight `red`, blocker count `25`; version lock and packaging template gates are green, signed-artifact proof/sandbox/App Store Connect validation/signing identities/owner metadata are red, pending owner-input metadata remains `8/8`, and pending App Store Connect metadata remains `8`.
  - owner approval for App Store packaging/signing/upload/metadata execution exists, but exact signed `.pkg`, strict App Store-candidate `codesign`, `pkgutil --check-signature`, sandbox workflow smoke, App Store Connect validation, upload/submission proof, and owner metadata values JSON are still missing.
- Current G2 NLE evidence snapshot:
  - latest NLE runtime-state persistence opt-in audit: `output/manual_verification/latest/nle_runtime_state_persistence_v040129_20260629_140053/nle_persistence_cutover_audit.md`
  - gate matrix state: `status=blocked`, `overall_stoplight=red`, ready/blocked gates `10/2`, current canonical owner is `nle_snapshot` only under explicit opt-in policy, `nle_snapshot_canonical_load_source_allowed=ready`, `runtime_project_state_persistence_allowed=ready`, and legacy-shape/final-cutover gates remain blocked.
  - opt-in state: loaded/runtime/reloaded/storage snapshot/runtime first caption text stays `runtime persisted snapshot first`; legacy `editor_state` first caption text after resave remains `first`; cache-hit read/resave hydrates runtime state; default project authority remains unchanged; no top-level/readback/quarantine payload persists.
  - previous NLE snapshot standalone canonical load opt-in audit: `output/manual_verification/latest/nle_snapshot_canonical_load_source_v040128_20260629_1325/nle_persistence_cutover_audit.md`
  - previous canonical load-owner rollback-boundary audit: `output/manual_verification/latest/nle_load_owner_rollback_boundary_v040124_20260629_1138/nle_persistence_cutover_audit.md`
  - previous canonical load-owner gate matrix audit: `output/manual_verification/latest/nle_canonical_load_owner_gate_matrix_v040123_20260629_1115/nle_persistence_cutover_audit.md`
  - latest top-level NLE gap projection coverage audit: `output/manual_verification/latest/nle_top_level_gap_projection_v040121_20260629_1041/nle_persistence_cutover_audit.md`
  - compatibility projection state: `gap_projection_coverage_ready_blocked`, `not_runtime_change=true`, default project load still uses `legacy_editor_state`, explicit top-level `nle` projection includes the legacy gap row as non-caption gap metadata, explicit/default row-caption-gap counts are both `3/2/1`, `gap_coverage_ready=true`, and canonical load-owner / disk-format cutover remain disallowed.
  - previous top-level NLE compatibility projection audit: `output/manual_verification/latest/nle_top_level_compatibility_projection_v040120_20260629_1018/nle_persistence_cutover_audit.md`
  - latest NLE canonical load-owner review packet: `output/manual_verification/latest/nle_canonical_load_owner_review_packet_v040119_20260629_095907/nle_canonical_load_owner_review_packet.md`
  - review packet state: `owner_review_required_blocked`, `canonical_load_owner_unchanged=true`, current canonical owner `legacy_editor_state`, `canonical_load_owner_change_allowed=false`, `disk_format_cutover_allowed=false`; top-level `nle` and `nle_snapshot` remain compatibility/shadow metadata and full NLE disk-format cutover remains blocked.
- Current G1 latency evidence snapshot:
  - latest STT collect-cache default review packet: `output/manual_verification/latest/stt_cache_default_review_packet_v040118_20260629_094703/stt_cache_default_review_packet.md`
  - review packet state: `owner_review_required`, `production_defaults_unchanged=true`, `default_promotion_allowed=false`, current defaults `stt_primary_collect_cache_enabled=false` and `stt_recheck_collect_cache_enabled=false`; STT1, STT2 recheck, and word precision cache default changes remain owner-approval-required, one-cache-at-a-time, and rollback-boundary gated.
  - latest generated-video direct validation evidence: `output/manual_verification/latest/generated_video_subtitle_validation_20260628_latest/validation_report.md`
  - strict duration-bound follow-up: `output/manual_verification/latest/generated_video_strict_duration_validation_20260628/strict_duration_report.md`
  - strict acceptance gate follow-up: `output/manual_verification/latest/generated_video_strict_acceptance_gate_20260628/reference_benchmark_acceptance.md`
  - tail-collapse fix evidence: `output/manual_verification/latest/generated_video_tail_collapse_fix_20260628/tail_collapse_fix_report.md`
  - NAS-off owner fallback run `20260628_010403`: Dex-generated 180s Korean fixture, elapsed `44.968s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, generated SRT rows `54`, SRT invalid/non-monotonic/overlap `0/0/0`, save/reopen stable `true`, global max active `1`, legacy `accepted=true`; stricter direct SRT/media validation fails because generated last end is `182.032s` against `180.584s` media duration, with `17` rows beyond duration, `16` sub-0.3s rows, and one `59.792s` tail row.
  - current acceptance behavior: `tools/evaluate_reference_benchmark_acceptance.py` rejects the old benchmark as `accepted=false` with reason `final_last_end_beyond_duration_bound`.
  - fixed fallback run `20260628_013224`: elapsed `44.307s`, raw/final/reference `54/54/54`, quality/text/timing `93.411/91.676/0.1391s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.12/180.584`, short/long `0/0`, strict `accepted=true`.
  - latest STT1 primary collect diagnostics evidence: `output/manual_verification/latest/stt_primary_collect_diagnostics_20260628/stt_primary_collect_report.md`
  - generated-fixture run `20260628_001645`: elapsed `49.380s`, raw/final/reference `54/54/54`, accepted `true`; STT1 total `20.135353s`, setup `0.046327s`, collect `19.986159s`, backend `whisperkit_persistent`, chunks `2`, worker count `2`, worker cache hit `false`. No behavior-preserving STT1 trim was accepted from this evidence.
  - latest STT1 primary collect cache evidence: `output/manual_verification/latest/stt_primary_collect_cache_20260628/primary_collect_cache_report.md`
  - generated 3-minute fixture first/second High-mode runs both accepted; STT1 collect `17.717081s -> 0.0s`, STT1 parent elapsed `17.855735s -> 0.049428s`, elapsed `51.964s -> 37.715s`, backend/model diagnostics preserved as `whisperkit_persistent` / `whisperkit-persistent:large-v3-v20240930_turbo_632MB`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`. The cache remains opt-in with default `stt_primary_collect_cache_enabled=false` until real-media backfill is accepted.
  - latest macro proofread response cache evidence: `output/manual_verification/latest/macro_response_cache_20260627/macro_response_cache_report.md`
  - generated 3-minute fixture first/second High-mode runs both accepted; proofread elapsed `30.731199s -> 0.545337s`, macro cache hit/write/provider groups `1/0/0`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`.
  - latest STT2/word collect cache evidence: `output/manual_verification/latest/stt_recheck_collect_cache_20260627/collect_cache_report.md`
  - generated 3-minute fixture first/second High-mode runs both accepted; STT2 collect `14.284272s -> 0.0s`, word precision collect `10.930693s -> 0.0s`, elapsed `46.498s -> 20.105s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`. The cache remains opt-in with default `stt_recheck_collect_cache_enabled=false` until real-media backfill is accepted.
  - latest combined collect cache evidence: `output/manual_verification/latest/combined_collect_cache_20260628/combined_collect_cache_report.md`
  - generated 3-minute fixture first/second High-mode runs both accepted with STT1, STT2, word precision, and macro proofread caches enabled together. First write run `20260628_004231`: elapsed `72.570s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, STT1/STT2/word collect `17.752132s/14.261639s/10.621729s`, macro proofread `28.907253s`. Second cache-hit run `20260628_004504`: elapsed `4.449s`, same quality/final gates, STT1/STT2/word collect all `0.0s` with provider calls `false`, macro provider group `0`, generated final SRT block count `54`, SRT invalid/non-monotonic/overlap `0/0/0`.
  - latest macro cache warmup-skip evidence: `output/manual_verification/latest/macro_cache_warmup_skip_20260628/macro_cache_warmup_skip_report.md`
  - generated 3-minute fixture cache-hit run `20260628_005314` accepted with elapsed `1.312s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, STT1/STT2/word collect all `0.0s`, macro proofread `0.400186s`, macro hit/write/provider groups `1/0/0`, generated final SRT block count `54`, SRT invalid/non-monotonic/overlap `0/0/0`. This skips LLM resolution/Ollama warmup only when every macro LLM group is already response-cache hit.
  - rejected prepared-clip reuse evidence: `output/manual_verification/latest/recheck_prepared_clip_reuse_rejected_20260628/recheck_prepared_clip_reuse_rejection_report.md`; no code/tests from that candidate remain.
  - latest NAS-off stage/memory variance evidence: `output/manual_verification/latest/stt_latency_stage_variance_20260628/stage_variance_summary.md`
  - analysis tool: `tools/summarize_stage_variance.py` reads existing `benchmark_results.json` artifacts and summarizes elapsed variance, stage totals, cache hit/provider-call flags, memory-pressure distribution, final gates, and duration-bound failures without changing runtime behavior.
  - latest variance result over 10 generated/cache artifacts: elapsed avg/min/max/range `41.66/1.312/82.433/81.121s`; stage ranges STT1 `20.134950s`, STT2 `15.939524s`, word precision `20.271760s`, subtitle postprocess `30.410655s`; worst memory pressure counts `unknown=4`, `normal=4`, `critical=2`; old tail-collapse generated runs are still flagged as duration-bound failures.
  - Jammini/서린 NAS-off variance review: `.agents/sentinel/handoffs/20260628-025200-stt-latency-nas-off-variance-review.md`; verdict `HOLD` for algorithm/default changes while NAS is unavailable, analysis-only work accepted.
- Other active queue items:
  - `Mac App Store Submission Readiness`; latest blocker matrix is `output/manual_verification/latest/app_store_owner_metadata_values_preflight_v040126_20260629_1228/app_store_readiness_audit.md` with `submission_target=mac_app_store_pkg`, `local_packaging_ready=true`, `app_store_submission_ready=false`, overall stoplight `red`, blocker count `25`, signed-artifact proof/sandbox/App Store Connect validation/signing identities/owner metadata still red, owner-input metadata pending `8/8`, and App Store Connect metadata pending `8`. Owner approval for App Store packaging/signing/upload/metadata execution exists, but signed `.pkg`, strict `codesign`, `pkgutil --check-signature`, sandbox smoke, App Store Connect validation, upload/submission, and owner metadata values JSON remain incomplete. Developer ID beta `.dmg` remains a separate opt-in track.
- Latest post-generation editor readiness closeout:
  - verification index: `output/manual_verification/latest/post_generation_editor_readiness_index_20260627/verification_index.md`
  - focused guard result: `7 passed, 190 deselected`
  - NAS HeyDealer first 180s `mode_high`: elapsed `65.383s`, raw/final `58/56`, quality `81.335`, `stable_for_save_reopen=true`, `stable_for_global_canvas=true`
- Latest cut-boundary generation latency closeout:
  - closeout report: `output/manual_verification/latest/cut_boundary_latency_profile_20260627/latency_profile_report.md`
  - baseline repeat: pipeline elapsed `[63.911, 59.479]`, average `61.695s`, raw/final `58/55`, pass
  - profile diagnostic: cut-boundary top cumulative `0.000602s`, confirmed split/snap `0.000525s`, raw/final `58/55`, pass
  - reference-scored HeyDealer 180s `mode_high`: elapsed `63.617s`, raw/final `58/56`, quality `81.335`, timing MAE `1.5958s`, final `overlap_count=0`, `stable_for_save_reopen=true`, `stable_for_global_canvas=true`
  - result: no cut-boundary runtime trim was applied; the next performance work should measure STT2 rescue, selective word timestamps, LLM gate/skip, common split, VAD/STT consensus, and cleanup pressure.
- Latest STT2/word precision latency profiling slice:
  - closeout report: `output/manual_verification/latest/stt2_word_precision_latency_20260627/latency_profile_report.md`
  - wall-clock stage report: `output/manual_verification/latest/stt2_word_precision_wall_clock_20260627/wall_clock_stage_report.md`
  - verifier change: `tools/verify_full_media_pipeline.py` now exposes STT2/word counts, final invalid/non-monotonic/overlap stability, global canvas max-active stability, memory pressure, reference-quality fields, and generation-owner cProfile summaries.
  - stage-span change: `core/audio/media_processor_transcribe.py`, `core/audio/media_processor_transcribe_recheck.py`, `tools/benchmark_subtitle_pipeline_variants.py`, and `tools/verify_full_media_pipeline.py` now record direct `perf_counter` spans for STT1 primary transcription, selective STT2 rescue, word timestamp precision, VAD/STT consensus, and subtitle postprocess.
  - focused guards: touched Python `py_compile` passed; `tests/test_verify_full_media_pipeline.py tests/test_benchmark_mode_profiles.py` -> `46 passed`; STT focused subset -> `6 passed, 48 deselected`.
  - HeyDealer 180s non-profile repeat: pipeline elapsed `[65.648, 59.402]`, average `62.525s`, raw/final `58/55`, final `overlap_count=0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`, STT2 selected `37`, word precision `14`, memory pressure `critical`.
  - generation profile diagnostic: `stt_primary_transcribe=45.702069s`, `stt2_selective_recheck=27.404475s`, `word_precision=12.976476s`, `llm_refinement=16.734457s`, `subtitle_postprocess=17.731724s`, `cleanup_trim=0.085355s`, cut-boundary top cumulative `0.000572s`; cProfile rows are diagnostic and non-additive.
  - reference-scored HeyDealer 180s `mode_high`: elapsed `62.640s`, raw/final `58/56`, quality `81.335`, text score `94.267`, timing MAE `1.5958s`, final `overlap_count=0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`.
  - wall-clock HeyDealer 180s non-reference probe: elapsed `65.222s`, raw/final `58/55`, final `overlap_count=0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`, STT2 selected `37`, word precision `14`, memory pressure `critical`; stage spans STT1 `18.162010s`, STT2 `14.360250s`, word precision `12.489603s`, VAD/STT consensus `0.000227s`, subtitle postprocess `20.108474s`.
  - wall-clock reference-scored HeyDealer 180s `mode_high`: elapsed `65.824s`, raw/final `58/56`, quality `81.335`, text score `94.267`, timing MAE `1.5958s`, final `overlap_count=0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`; stage spans STT1 `19.519015s`, STT2 `14.229755s`, word precision `12.560951s`, VAD/STT consensus `0.000222s`, subtitle postprocess `19.406983s`.
  - first safe trim report: `output/manual_verification/latest/stt2_word_precision_llm_defer_20260627/llm_defer_report.md`
  - first safe trim behavior: macro LLM mode now defers runtime model resolution and Ollama warmup until `llm_rows > 0`; zero-candidate rows no longer prepare a local LLM that will not be called.
  - post-trim non-profile repeat: pipeline elapsed `[65.317, 61.873]`, average `63.595s`, raw/final `58/55`, final `overlap_count=0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`, STT2 selected `37`, word precision `14`, memory pressure `critical`.
  - post-trim reference-scored HeyDealer 180s `mode_high`: elapsed `66.007s`, raw/final `58/56`, quality `81.335`, text score `94.267`, timing MAE `1.5958s`, final `overlap_count=0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`; subtitle postprocess dropped to `12.518010s`, but word precision rose to `20.851735s`.
  - rejected context-boundary batch candidate: `output/manual_verification/latest/stt2_word_precision_context_batch_20260627/context_batch_rejection_report.md`
  - rejected candidate result: batching two High context-boundary LLM pair checks into one Ollama call lowered subtitle postprocess to `9.879991s`, but reference quality/text/segmentation drifted `81.335/94.267/87.879 -> 81.316/94.241/87.812`; the code/tests for that candidate were reverted.
  - substage timing report: `output/manual_verification/latest/stt2_word_precision_substage_timing_20260627/substage_timing_report.md`
  - substage timing behavior: `stt2_selective_recheck` and `word_precision` spans now expose prepare/collect/annotate/batch elapsed fields. Local 60s reference smoke showed STT2 total `11.258246s` with collect `11.201352s`, and word precision total `4.368781s` with collect `4.304654s`; prepare/annotation were below `0.1s`.
  - collect fallback precision report: `output/manual_verification/latest/stt_collect_fallback_precision_20260627/fallback_precision_report.md`
  - collect fallback behavior: `stt_collect_whisperkit_fallback` spans now expose WhisperKit empty/timeout fallback count, reason, source/fallback model, total/max elapsed, chunk counts, emitted segment count, and word timestamp mode. Local 60s smoke showed fallback count `2`, benchmark fallback total `7.962836s`, verifier fallback total `14.900298s`, final overlap `0`, `stable_for_save_reopen=true`, and global max active `1`.
  - high context-boundary diagnostics report: `output/manual_verification/latest/stt_high_context_diag_x5_audio_20260627/high_context_diag_report.md`
  - high context-boundary diagnostics behavior: `refine_high_contextual_boundaries(...)` now exposes candidate pairs, skipped pairs, LLM calls, failed calls, changed pairs, max pairs, and elapsed time through benchmark/verifier stage spans, summary metrics, repeat JSON/CSV, and compact CLI output.
  - X5 cached-audio 180s measurement: pipeline `74.919s`, raw/final `43/50`, final invalid/non-monotonic/overlap `0/0/0`, `stable_for_save_reopen=true`, global max active `1`, STT2 selected `28`, word precision `9`, memory pressure `critical`; top stage `subtitle_postprocess=32.746457s`, detail top `high_context_boundary=32.230736s`, candidate/call/changed `4/4/0`, failed calls `0`.
  - reference fixture availability preflight: `output/manual_verification/latest/reference_fixture_availability_20260627/reference_fixture_availability.md`
  - preflight result: reference-scored latency-trim acceptance is blocked because the `/Volumes/photo/...` HeyDealer MP4 and matching `.srt` are missing; cached HeyDealer WAV exists and is fallback-only for instrumentation and structural stability.
  - owner-required NAS HeyDealer 3-minute preflight: `output/manual_verification/latest/heydealer_nas_reference_preflight_20260627/reference_fixture_availability.md`
  - latest owner-required NAS HeyDealer 3-minute preflight rerun: `output/manual_verification/latest/heydealer_nas_reference_preflight_20260627_latest/reference_fixture_availability.md`
  - latest NAS HeyDealer 3-minute accepted run: `output/manual_verification/latest/heydealer_nas_reference_180s_20260627_2215/reference_benchmark_report.md`
  - NAS result: pass. `/Volumes/photo` was mounted, exact MP4/SRT preflight passed, `mode_high` first 180s elapsed `60.187s`, raw/final/reference `58/56/89`, quality `81.335`, text `94.267`, timing MAE `1.5958s`, final invalid/non-monotonic/overlap `0/0/0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`, and acceptance returned `accepted=true`.
  - latest STT2/word duration diagnostics: `output/manual_verification/latest/stt_recheck_duration_diagnostics_20260627/diagnostics_report.md`
  - latest NAS diagnostic result: pass. Same NAS HeyDealer first 180s elapsed `59.255s`, raw/final/reference `58/56/89`, quality `81.335`, text `94.267`, timing MAE `1.5958s`, final invalid/non-monotonic/overlap `0/0/0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`, and acceptance returned `accepted=true`.
  - STT2 interpretation: `applied_count=1` is one broad rescue range, not one low-value segment. That span requested `180.096s`, prepared `120.000s`, collected `37` segments, and applied `37` segment-level results. Do not trim STT2/word precision from count fields alone.
  - latest STT2/word reason breakdown diagnostics: `output/manual_verification/latest/stt_recheck_reason_breakdown_20260627/reason_breakdown_report.md`
  - latest reason-breakdown NAS result: pass. Same NAS HeyDealer first 180s elapsed `58.820s`, raw/final/reference `58/56/89`, quality `81.335`, text `94.267`, timing MAE `1.5958s`, final invalid/non-monotonic/overlap `0/0/0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`, and acceptance returned `accepted=true`.
  - reason interpretation: STT2 is a missing-voice rescue path (`missing_voice/route_hint/low_score/empty_text=1/0/0/1`). Word precision chose `25` ranges, but none were editor-selected, precision-review, needs-review, red/yellow, risk, or missing-word forced (`0/0/0/0/0/0/0`). Next speed work should target collect scheduling/cache reuse or a decision-equivalent High context-boundary gate before changing quality policy.
  - latest High context decision diagnostics: `output/manual_verification/latest/high_context_decision_diagnostics_20260627/decision_diagnostics_report.md`
  - latest High context NAS result: pass. Same NAS HeyDealer first 180s elapsed `59.559s`, raw/final/reference `58/56/89`, quality `81.335`, text `94.267`, timing MAE `1.5958s`, final invalid/non-monotonic/overlap `0/0/0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`, and acceptance returned `accepted=true`.
  - High context decision interpretation: candidate/skipped/call/failed/changed/max pairs were `2/55/2/0/0/8`; action counts keep/move/merge/invalid were `2/0/0/0`; correction requested/applied was `0/0`. A future High context speed trim must be a strict decision-equivalent no-change gate, not batching or broad skipping.
  - high context keep-cache candidate: `output/manual_verification/latest/high_context_keep_cache_20260627/keep_cache_report.md`
  - keep-cache result: pass on owner-approved generated 3-minute fixture. NAS was off by owner direction, so Dex generated a 180.583s Korean fixture with 54 reference rows and ran two High-mode scored benchmarks. First write run: elapsed `144.476s`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, High context candidates/calls/cache hit-miss-write `8/8/0-8-8`, accepted `true`. Second cache-hit run: elapsed `83.281s`, same quality/final gates, High context calls/cache hit-miss-write `0/8-0-0`, High context elapsed `0.003326s`, accepted `true`.
  - preflight guards: `tools/verify_reference_fixture_availability.py` plus `tests/test_reference_fixture_availability.py`; focused validation `3 passed`.
  - X5 local reference smoke: `output/manual_verification/latest/x5_local_reference_fixture_20260627/reference_benchmark_report.md`
  - X5 local result: materialized `.codex_work/bench/x5_120_3s_180_3s_reference.json` into a relative SRT and ran `.codex_work/bench/x5_120_3s_180_3s.wav` with `mode_high`; elapsed `29.831s`, raw/final `28/23`, quality `80.914`, timing MAE `0.5608s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`.
  - X5 project-reference 180s smoke: `output/manual_verification/latest/x5_project_reference_180s_20260627/reference_benchmark_report.md`
  - X5 project-reference result: accepted media/SRT pair is cached X5 180s WAV plus `projects/X5_시승기_전반.assets/subtitles/final.srt`; elapsed `70.383s`, raw/final/reference `43/50/67`, quality `76.387`, text `90.767`, timing MAE `1.5457s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`.
  - X5 rejected mismatch: same media with `projects/X5_시승기_후반.assets/subtitles/final.srt` is rejected by `tools/evaluate_reference_benchmark_acceptance.py` because quality/text/timing failed (`23.234`/`4.756`/`3.3362s`).
  - result: first trim is correctness-safe but not a total latency closeout; local X5 60s and project-reference X5 180s smokes remain regression surfaces only. The owner-required NAS HeyDealer 3-minute baseline is now accepted, so the next latency slice must compare against that same fixture before adoption.
- Latest NLE runtime editing adoption slice:
  - report: `output/manual_verification/latest/nle_caption_move_dual_write_20260627/caption_move_dual_write_report.md`
  - behavior: `apply_caption_move_dual_write_pilot(...)` routes final subtitle body moves through runtime `NLEProjectState`, records a `caption_move` `NLEEditorOperation`, and projects back into legacy `editor_state`.
  - Taption rule: neighbor reorder is represented with `taption_reorder`, `reorder_direction`, and `reorder_neighbor_id`; final overlap moves are rejected by the NLE operation projection gate.
  - focused guards: `tests/test_project_nle_dual_write.py` -> `6 passed`; NLE operation/snapshot/roughcut guard -> `30 passed, 4 subtests passed`; Taption reorder UI subset -> `3 passed, 296 deselected`.
- Latest NLE caption resize adoption slice:
  - report: `output/manual_verification/latest/nle_caption_resize_dual_write_20260627/caption_resize_dual_write_report.md`
  - quick QA: `output/manual_verification/latest/qa_suite_quick_nle_caption_resize_20260627`
  - behavior: `apply_caption_resize_dual_write_pilot(...)` routes boundary-handle and diamond-style subtitle resize operations through runtime `NLEProjectState`, records a `caption_resize` `NLEEditorOperation`, trims/deletes affected neighbors including silence gaps before the final-overlap gate, and projects back into legacy `editor_state`.
  - stricter test method: operation metadata, runtime NLE projection rows, legacy editor rows, save/reload storage shape, final `invalid/non_monotonic/overlap/max_active` metrics, existing Taption resize/diamond UI regressions, and source-app quick QA were all checked.
  - focused guards: NLE dual-write -> `10 passed`; NLE operation/snapshot/persistence/runtime/render-export -> `38 passed, 4 subtests passed`; Taption resize/diamond subset -> `23 passed, 126 deselected`; Taption drag/gap/magnet/app-command subset -> `63 passed, 163 deselected`; timeline/feed -> `152 passed`; source-app quick QA -> pass, `failed_count=0`.
- Latest NLE live editor mutation cutover slice:
  - report: `output/manual_verification/latest/nle_live_editor_diamond_cutover_20260627/live_editor_diamond_cutover_report.md`
  - passing quick QA: `output/manual_verification/latest/qa_suite_quick_nle_live_diamond_retry_20260627`
  - behavior: `diamond` shared-boundary subtitle resize in `_on_seg_time_changed(...)` now attempts runtime NLE `caption_resize` dual-write and applies projected rows through `_reload_segments_from_list(..., preserve_view=True, mark_dirty=True)` when safe.
  - fallback: NLE rejection, unsupported runtime shape, and micro rows that collapse on the project floor-frame grid keep the existing legacy Taption/inline-editor path.
  - focused guards: diamond route -> `4 passed, 148 deselected`; resize/diamond -> `26 passed, 126 deselected`; NLE operation/snapshot/persistence/runtime/render-export -> `38 passed, 4 subtests passed`; drag/gap/magnet/app-command -> `63 passed, 163 deselected`; timeline/feed -> `155 passed`; source-app quick QA retry -> pass, `failed_count=0`.
  - QE trace: first quick QA artifact `output/manual_verification/latest/qa_suite_quick_nle_live_diamond_20260627` failed at `merge_diamond`; root cause was a one-frame-ish split row collapsing under project floor-frame normalization, fixed by the micro-row fallback guard.
- Latest NLE live editor boundary resize cutover slice:
  - report: `output/manual_verification/latest/nle_live_editor_boundary_resize_cutover_20260627/boundary_resize_cutover_report.md`
  - behavior: `square_left` and `square_right` subtitle boundary-handle resizes in `_on_seg_time_changed(...)` now attempt runtime NLE `caption_resize` dual-write and apply projected rows through `_reload_segments_from_list(..., preserve_view=True, mark_dirty=True)` when safe.
  - fallback: transient STT/live-preview rows, NLE rejection, unsupported runtime shape, and invalid/collapsing rows keep the existing legacy Taption/source-app timing path.
  - focused guards: boundary/diamond route -> `4 passed, 151 deselected`; resize/diamond/gap/center subset -> `32 passed, 123 deselected`; NLE operation/persistence/runtime/render-export -> `38 passed, 4 subtests passed`; drag/gap/magnet/app-command -> `63 passed, 163 deselected`; timeline/feed -> `158 passed`.
- Latest NLE live editor caption delete cutover slice:
  - report: `output/manual_verification/latest/nle_live_editor_caption_delete_cutover_20260627/caption_delete_cutover_report.md`
  - behavior: live editor segment delete-to-gap now attempts runtime NLE `caption_delete` dual-write, records delete mode `replace_with_silence_gap`, projects the deleted final caption into a silence gap row, and reloads through `_reload_segments_from_list(..., preserve_view=True, mark_dirty=True)` when safe.
  - fallback: live STT preview rows, NLE rejection, missing caption identity, unsupported timeline shape, or invalid rows keep the existing Taption/source-app direct gap conversion path.
  - focused guards: caption delete/gap/resize NLE dual-write -> `9 passed, 3 deselected`; live delete/resize route -> `4 passed, 153 deselected`; Taption gap/delete subset -> `13 passed, 137 deselected`; NLE operation/persistence/runtime/render-export -> `40 passed, 4 subtests passed`; delete/resize/drag subset -> `34 passed, 123 deselected`; timeline/feed -> `160 passed`; drag/gap/magnet/app-command/delete -> `68 passed, 158 deselected`.
- Latest NLE live editor gap-generate cutover slice:
  - report: `output/manual_verification/latest/nle_live_editor_gap_generate_cutover_20260627/gap_generate_cutover_report.md`
  - behavior: live editor gap generation now attempts runtime NLE `gap_generate` dual-write, preserves Taption-style left/right silence gap rows around the generated subtitle, and reloads through `_reload_segments_from_list(..., preserve_view=True, mark_dirty=True)` when safe.
  - fallback: live STT preview rows, NLE rejection, missing gap identity/range, unsupported timeline shape, or invalid rows keep the existing Taption/source-app direct gap generation path.
  - focused guards: gap-generate/delete NLE dual-write -> `7 passed, 7 deselected`; live gap-generate/delete route -> `3 passed, 156 deselected`; Taption gap/delete subset -> `13 passed, 137 deselected`; NLE operation/persistence/runtime/render-export -> `42 passed, 4 subtests passed`; gap/delete/resize subset -> `36 passed, 123 deselected`; timeline/feed -> `162 passed`; drag/gap/magnet/app-command/delete -> `68 passed, 158 deselected`.
- Latest NLE live editor caption-merge cutover slice:
  - report: `output/manual_verification/latest/nle_live_editor_caption_merge_cutover_20260628/caption_merge_cutover_report.md`
  - behavior: diamond merge now attempts runtime NLE `caption_merge` dual-write for stable final caption pairs, records a `caption_merge` operation, and reloads projected rows through `_reload_segments_from_list(..., preserve_view=True, mark_dirty=True)` when safe.
  - fallback: live STT preview rows, NLE rejection, missing caption identity, unsupported timeline shape, or invalid rows keep the existing Taption/source-app QTextDocument merge path.
  - Jammini support slice: delegated review-only check for STT/live-preview isolation, final overlap gates, Taption fallback preservation, and doc/test evidence gaps; expected handoff `.agents/sentinel/handoffs/20260628-015400-nle-caption-merge-support-review.md`.
  - focused guards: caption-merge/delete/gap-generate NLE dual-write -> `6 passed, 10 deselected`; live diamond-merge route/fallback subset -> `4 passed, 158 deselected`; NLE operation/runtime/save-export subset -> `25 passed, 21 deselected`; Taption merge/resize/gap/delete subset -> `45 passed, 267 deselected`; timeline/feed -> `165 passed`; generated-video strict acceptance recheck -> `accepted=true`.
- Latest NLE live editor caption-split cutover slice:
  - report: `output/manual_verification/latest/nle_live_editor_caption_split_cutover_20260628/caption_split_cutover_report.md`
  - behavior: text/smart caption split now attempts runtime NLE `caption_split` dual-write for stable final captions, records a `caption_split` operation, and reloads projected rows through `_reload_segments_from_list(..., preserve_view=True, mark_dirty=True)` when safe.
  - fallback: live STT/subtitle preview rows, NLE rejection, missing caption identity, unsupported timeline shape, or invalid rows keep the existing Taption/source-app QTextDocument split path.
  - Jammini support slice: accepted `.agents/sentinel/handoffs/20260628-021000-nle-caption-split-support-review.md` for STT/live-preview isolation, final overlap gates, Taption fallback preservation, and undo/snapshot focus evidence gaps.
  - focused guards: caption-split NLE dual-write -> `2 passed, 16 deselected`; editor split undo/fallback -> `3 passed`; full NLE dual-write file -> `18 passed`; NLE operation/runtime/save-export subset -> `11 passed, 19 deselected`; app-command smart split -> `7 passed, 69 deselected`; timeline split/gap undo -> `8 passed, 142 deselected`; timeline split/gap/merge -> `20 passed, 142 deselected`; source-app quick QA `output/manual_verification/latest/qa_suite_quick_nle_caption_split_20260628` -> pass, `failed_count=0`.
- Latest NLE live editor candidate-confirm cutover slice:
  - report: `output/manual_verification/latest/nle_live_editor_candidate_confirm_cutover_20260628/candidate_confirm_cutover_report.md`
  - behavior: STT1/STT2 candidate confirmation now attempts runtime NLE `candidate_confirm` dual-write after Taption/source-app placement computes confirmed final rows, records a `candidate_confirm` operation, preserves candidate-lane evidence in the undo snapshot, and records `_last_nle_live_editor_operation` / `_last_nle_live_editor_projection` when accepted.
  - fallback: non-STT1/STT2 sources, live STT/subtitle preview rows, NLE rejection, unsupported rows, and any NLE projection that would alter confirmed source-app rows beyond `0.001s` keep the existing Taption/source-app candidate selection path.
  - Jammini support slice: accepted `.agents/sentinel/handoffs/20260628-023000-nle-candidate-confirm-support-review.md` for STT/live-preview isolation, final overlap gates, fallback preservation, and undo/focus evidence focus; adopted fix made the projection-preservation guard reachable after receiving the NLE result.
  - focused guards: candidate-confirm NLE dual-write -> `2 passed, 18 deselected`; select_stt_candidate -> `15 passed, 73 deselected`; timeline STT candidate -> `6 passed, 144 deselected`; NLE operation/runtime/save-export subset -> `29 passed, 21 deselected`; native/project STT selection subset -> `17 passed, 74 deselected`; feed/preview/final overlay subset -> `12 passed, 153 deselected`; source-app quick QA `output/manual_verification/latest/qa_suite_quick_nle_candidate_confirm_20260628` -> pass, `failed_count=0`.
- Latest NLE global canvas final-projection cutover slice:
  - report: `output/manual_verification/latest/nle_global_canvas_final_projection_20260627/global_canvas_projection_report.md`
  - behavior: `nle_global_canvas_segments_from_editor_rows(...)` gives the global canvas subtitle lane a final-only NLE projection while the main timeline canvas keeps live STT/subtitle preview rows.
  - focused guards: runtime/global projection -> `5 passed, 158 deselected`; global canvas subset -> `9 passed, 151 deselected`; NLE runtime/render/snapshot -> `20 passed, 4 subtests passed`.
- Latest NLE save/export final-projection cutover slice:
  - report: `output/manual_verification/latest/nle_save_export_projection_cutover_20260628/save_export_projection_report.md`
  - behavior: `nle_save_export_segments_from_editor_rows(...)` gives externalized final SRT/cache rows a final-only NLE projection while silence gaps stay in vector-canvas gap metadata and STT1/STT2 reference tracks remain separate.
  - focused guards: save/export projection -> `4 passed, 6 deselected`; NLE runtime/render/export/persistence/dual-write/operation/snapshot -> `44 passed, 4 subtests passed`; external text asset subset -> `1 passed, 84 deselected`.
- Latest NLE final-surface overlap guard slice:
  - report: `output/manual_verification/latest/nle_final_surface_overlap_guard_20260628/final_surface_overlap_guard_report.md`
  - behavior: final overlay/global-canvas/save-export projection now repairs one-frame final micro-overlap to a shared boundary when possible; overlay/global-canvas avoid drawing unfixable overlapped final rows together, and save/export rejects unfixable final overlap before writing final SRT.
  - focused guards: runtime cutover -> `8 passed`; NLE domain/render/persistence/dual-write/operation/snapshot -> `54 passed, 4 subtests passed`; timeline/feed subset -> `21 passed, 144 deselected`; native subtitle segment set -> `7 passed`; project assets subset -> `3 passed, 3 deselected`.
- Latest NLE persistence cutover audit slice:
  - report: `output/manual_verification/latest/nle_persistence_cutover_audit_20260628/nle_persistence_cutover_audit.md`
  - behavior: `tools/audit_nle_persistence_cutover.py` proves runtime `NLEProjectState` hydration, legacy disk cleanliness, future-payload quarantine, and save/reopen roundtrip for all `8` current NLE dual-write operation families while keeping actual persisted NLE format cutover blocked. The matrix separately reports legacy ID renumbering for `gap_generate`, `caption_split`, `caption_merge`, and `candidate_confirm`.
  - focused guards: audit tests -> `4 passed`; persistence/dual-write focused set -> `28 passed`.
- Latest NLE roughcut saved-candidate render-plan cutover slice:
  - report: `output/manual_verification/latest/nle_roughcut_state_render_plan_cutover_20260628/roughcut_state_render_plan_report.md`
  - behavior: saved roughcut candidate `outputs.render_plan` payloads now route through the NLE snapshot adapter path used by roughcut export/render actions, while preserving legacy render command, manifest, and stitched-boundary parity.
  - focused guards: saved/export render-plan route -> `3 passed, 35 deselected`; roughcut snapshot subset -> `3 passed, 16 deselected`; NLE runtime/render/export/persistence/dual-write/operation/snapshot -> `48 passed, 4 subtests passed`; generated-video strict acceptance recheck -> `accepted=true`.
- Latest Taption-derived segment editing parity closeout:
  - quick QA: `output/manual_verification/latest/qa_suite_quick_20260627_141230`
  - focused guards: timeline/feed `150 passed`, drag/gap/app-command `60 passed, 161 deselected`, native/video `87 passed`, project STT preview `32 passed, 56 deselected`
  - behavior: STT1/STT2 candidate lanes remain preserved for review evidence, video subtitle overlay filters preview rows when final rows exist, final `stable_for_save_reopen` now requires `overlap_count=0`, and center segment drag suppresses gap snap candidates when crossing a silence/gap toward a real subtitle boundary.
- Latest Taption segment UI/UX parity checklist slice:
  - checklist: `output/manual_verification/latest/taption_segment_uiux_parity_20260627/checklist.md`
  - focused guards: hit-target parity `10 passed, 138 deselected`, reorder hit-target parity `3 passed, 147 deselected`, reorder commit parity `3 passed, 146 deselected`, extended drag/gap/STT/app-command parity `65 passed, 161 deselected`, playhead/timing feed parity `152 passed`, center reorder/gap subset `5 passed, 144 deselected`
  - behavior: single-gap snap suppression without subtitle target, boundary release from visible snapped boundary, one-gap center move absorption without final overlap, one-word inline-editor up/down retention, and immediate neighbor reorder preview/commit are now explicitly guarded.
- Latest NLE transition planning artifact:
  - owner inventory: `output/manual_verification/latest/nle_owner_inventory_20260627/owner_inventory.md`
  - domain contract: `output/manual_verification/latest/nle_domain_contract_20260627/domain_contract.md`
  - read-only projection parity: `output/manual_verification/latest/nle_read_only_parity_20260627/projection_parity_report.md`
  - operation model: `output/manual_verification/latest/nle_operation_model_20260627/operation_model_report.md`
  - dual-write pilot: `output/manual_verification/latest/nle_dual_write_pilot_20260627/gap_delete_pilot_report.md`
  - save/reload compatibility: `output/manual_verification/latest/nle_save_reload_compat_20260627/save_reload_compat_report.md`
  - render/export parity: `output/manual_verification/latest/nle_render_export_parity_20260627/render_export_parity_report.md`
  - runtime cutover final overlay: `output/manual_verification/latest/nle_runtime_cutover_final_overlay_20260627/final_overlay_cutover_report.md`
  - cleanup gate audit: `output/manual_verification/latest/nle_cleanup_gate_audit_20260627/cleanup_gate_audit.md`
  - release checkpoint parity and rollback proof: `output/manual_verification/latest/nle_release_checkpoint_parity_20260627/release_checkpoint_parity_report.md`
  - phase 11 cleanup/no-op closeout: `output/manual_verification/latest/nle_phase11_cleanup_20260627/cleanup_report.md`
  - latest quick QA for final-overlay cutover: `output/manual_verification/latest/qa_suite_quick_20260627_162641`
  - phase 1 result: current mutable owners mapped for final subtitle rows, gaps, STT candidate lanes, timeline canvas state, video overlay feed, global canvas/minimap, roughcut/cut boundaries, project save/load, export/render, and undo/redo.
  - phase 2 result: internal NLE time domains, entities, projection surfaces, validation checklist, and stop conditions are defined.
  - phase 3 result: read-only projection parity helper and tests now cover timeline, video overlay, global canvas, save/export, and roughcut surfaces with final `overlap_count=0`.
  - phase 4 result: operation/undo transaction contracts now cover caption, gap, candidate-confirm, marker, roughcut-range, and undo snapshot rules without runtime write routing.
  - phase 5 result: `gap_delete` dual-write pilot routes one explicit gap removal through runtime `NLEProjectState` and projects back into legacy `editor_state` while keeping disk payload free of NLE fields.
  - phase 6 result: save/reload guard strips or metadata-quarantines unapproved persisted `nle`, `nle_snapshot`, and disk-shaped `_nle_project_state` payloads while preserving runtime-only `NLEProjectState` hydration and legacy-compatible disk writes.
  - phase 7 result: render/export parity proof compares one final caption frame projection across source subtitles, final overlay, global canvas, roughcut sidecars, and exported asset plans.
  - phase 8 result: the `final_overlay` runtime provider uses the NLE final caption projection, and a later focused slice gives global canvas a final-only NLE projection while preserving timeline live-preview rows. Save/reload, render/export, and persistence ownership remain unchanged.
  - phase 9 result: cleanup deletion is blocked because only one post-cutover quick QA checkpoint exists; the older full QA checkpoint predates final-overlay cutover and cannot count as post-cutover cleanup proof.
  - phase 10 result: two consecutive post-cutover checkpoint bundles passed: each ran focused NLE runtime/save/reload/render/export/editor parity guards with `123 passed, 4 subtests passed` plus source-app quick QA with `failed_count=0`.
  - phase 11 result: no code deletion was performed because final-overlay cutover did not create a proven-dead legacy write path; fallback context helpers remain rollback/active dependencies.

## Current Risks

- High path can pass QA while memory pressure still enters `critical`; do not treat pass/fail alone as enough for performance conclusions.
- Critical pressure may come from system/native pressure, compressed/wired memory, MPS/Metal driver memory, warm STT workers, LLM residency, editor preview, and app process RSS together.
- Long-flow STT1, STT2 rescue, word timestamp precision, and subtitle postprocess still have meaningful wall-clock cost; optimize only by reducing redundant waiting, duplicate cache work, avoidable scheduling serialization, cleanup churn, UI/status hot paths, or safe resource lifetime waste.
- Do not lower X5 quality gates, skip STT2, skip LLM, downgrade models, or loosen subtitle quality policy as a speed optimization.
- Tinyping long-flow is manual-only unless the owner explicitly requests it.
- The completed internal NLE baseline is a source-app domain/adapter layer only. It must not reopen native migration, Swift rewrite, QML migration, or visible Premiere-style UI work without explicit owner approval.
- App Store submission is still blocked despite the local packaging skeleton passing audit; signed `.app`, signed `.pkg`, sandbox smoke, App Store Connect validation, and owner-provided metadata are missing.
- The latest G3 real-media live proof passed as runtime/status observability only. It is not same-media quality/speed, save/reopen, or final export proof.
- The latest G3 live run exposed `nle_save_export_final_overlap` after SRT save. The `v04.01.09` slice stops that nonretryable final-overlap failure from causing repeated deferred-save retries, the `v04.01.10` slice repairs the observed tiny live-SRT quantization overlap for final save/export projection, `v04.01.11` accepts same-media benchmark/timeout proof while hardening the editor-sequence harness, `v04.01.12` proves direct-SRT app-command save/reopen/export without row-count drift, `v04.01.13` proves app-command open/start/status/cancel/close/quit responsiveness while workers are active, and `v04.01.14` proves active global-canvas/timeline responsiveness. Any additional active-worker final-surface proof remains separate if selected by the queue.
- Always re-check `git status` before widening a follow-up patch.

## Narrow Next Item

Use `docs/planning_queue/ACTION_ITEMS.md` as the executable queue. The current narrow implementation target is group `G3. Realtime NLE STT/VAD Track Visibility And Resource-Balanced Scheduling`, next bounded slice:

1. Continue only after reading the G3 current baseline and `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040103-g3-runtime-nle-lane-owner-map--final-authority-guard`.
2. Also read `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040104-g3-compact-live-status-feed`.
3. Also read `docs/planning_queue/COMPLETED_ACTION_ITEMS.md#v040105-g3-live-nle-projection-scheduler-budget-telemetry`.
4. The completed first three G3 slices establish read-only runtime track metadata, final-authority guards, compact status/ping count exposure, and zero-worker live projection budget telemetry. They do not add visible UI strips, actual worker fan-out changes, persisted disk-format cutover, STT2 skipping, or cache default promotion.
5. The real-media runtime/status proof slice is complete at `output/manual_verification/latest/g3_live_nle_real_media_observability_timeout20_20260629/live_nle_runtime_proof.md`, the deferred-save retry churn for nonretryable `nle_save_export_final_overlap` is closed in `v04.01.09`, the observed tiny live-SRT save/export quantization overlap is repaired in `v04.01.10`, same-media benchmark/timeout proof plus editor-sequence harness hardening is complete in `v04.01.11`, direct-SRT app-command save/reopen/export proof is complete in `v04.01.12`, open/start/status/cancel/close/quit active-worker responsiveness is complete in `v04.01.13`, and active global-canvas/timeline responsiveness is complete in `v04.01.14`. Next safe slice is another strictly bounded active-worker final-surface defect if selected by the queue, with no raw status payload leakage, no conversion-time regression, and no final-authority weakening as hard gates.
6. Preserve final authority: VAD/STT runtime rows must not enter final overlay, global canvas final rows, save/export rows, or persisted compatibility rows.
7. If widening into visible timeline/global-canvas UI, require a fresh owner-approved UI scope, screenshots or automation snapshots, and proof that app commands, cancel/quit, save, and close do not starve behind preview updates.
8. G0 App Store remains externally blocked on Distribution/Installer identities, signed `.pkg`, sandbox smoke, App Store Connect validation, and owner metadata. G1 cache/default promotion remains owner-review gated.
9. Do not retry prepared recheck clip metadata reuse for cache-hit runs without new evidence; the 2026-06-28 candidate was rejected because prepare time stayed around `0.50s` and metadata/directory retention added complexity.
10. Use `tools/summarize_stage_variance.py` when comparing existing generated/cache benchmark artifacts; it is analysis-only and must not be used to approve default cache enablement or production speed claims.
11. Identify any further behavior-preserving candidate only from redundant waiting, duplicate cache work, avoidable scheduling serialization, or already-proven cleanup churn in STT1, selective STT2 rescue, word timestamp precision, VAD/STT consensus, or subtitle postprocess. The latest synthetic cache-hit run shows elapsed `1.312s`, STT1/STT2/word collect all `0.0s`, macro provider group `0`, final overlap `0`, generated SRT overlap `0`, and accepted scored quality.
12. The latest STT1 diagnostics show STT1 setup is negligible and collect dominates; the opt-in cache proves exact repeat replay only. Do not skip STT1, downgrade the primary model, shrink windows, or loosen final subtitle stability to gain speed.

QA gate for that item:

- No unrelated UI/UX labels, layout, colors, shortcuts, popup behavior, or visible workflow changes.
- No subtitle quality policy, STT2, LLM, LoRA, VAD, timing, or model-selection changes.
- Do not lose STT1/STT2 candidate-lane evidence while keeping final overlay/global-canvas feeds overlap-free.
- Do not use X5 or fallback cached audio as a substitute for the owner-required NAS HeyDealer 3-minute latency test unless the owner explicitly relaxes that requirement. Latest accepted NAS proof: `output/manual_verification/latest/stt_recheck_reason_breakdown_20260627/reason_breakdown_report.md`.
- Do not use synthetic keep-cache, macro-cache, STT collect-cache, or combined-cache speed deltas as production-wide proof; they are accepted only for the owner-approved generated fixture until a representative real-media backfill passes.
- If the new item touches editor readiness, preserve the completed closeout guarantees: generation completion must return the editor to a trustworthy interactive state, and subtitle time editing, timeline zoom/fit/time-window, subtitle magnet, playback controls, save, and bottom/global menu buttons must stay responsive.

## Fixtures

- Macau quick/smoke: `/Users/u_mo_c/Downloads/마카오테스트`
- X5 accuracy: `/Users/u_mo_c/Downloads/ai_subtitle_studio/test video/X5_시승기_후반.MP4` plus sibling `.srt`
- NAS HeyDealer 3-minute reference: `/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.MP4` plus matching `.srt`; this must be mounted for the next generation-latency acceptance test.
- Tinyping long-flow: `/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.MP4` (manual only; excluded from default QA unless explicitly requested)
- Store verification artifacts under `output/manual_verification/latest/`.

## Operating Rules

- Reply to the owner in Korean.
- If a change alters ownership, architecture, validation, or next-session continuity, update the matching `docs/*.md` file in the same task.
- Keep repository docs in English unless the filename/content is intentionally Korean or user-facing Korean text.
- Preserve dirty worktree changes you did not make. Never revert unrelated files.
- Do not commit, push, tag, release, package, notarize, upload, or build DMG unless the owner explicitly asks.
- Use `rg` for search and `apply_patch` for manual edits.
- Avoid broad rewrites. Keep changes scoped to the requested behavior or document cleanup.
- Add short comments only on hot paths where the reason would otherwise be hard to recover.
- Keep long logs out of chat; write detailed verification artifacts under `output/manual_verification/latest/` and report only key paths and numbers.
- If code changes touch subtitle quality, STT, LLM, VAD, timing, project save/load, queue, app-command, or native paths, run targeted tests plus the relevant real fixture.
- If command surface or editor automation changes, rebuild the app bundle before `major` or `full` QA with `./packaging/macos/build_app_bundle.sh`.

## Persona Rules

- When reviewing, correcting, or executing `docs/planning_queue/ACTION_ITEMS.md`, act as a senior Apple Silicon MacBook developer: prefer macOS-native realities over generic optimization advice, use precise Apple terms such as ANE/Core ML/Metal/MLX/Accelerate, and reject ideas that add bridge cost, memory pressure, or subtitle-quality risk without measured benefit.
- During implementation and code review, first use a meticulous senior developer viewpoint: check architecture boundaries, fallback paths, race conditions, resource lifetime, macOS process behavior, native bridge overhead, and maintainability.
- During QA/test review, switch persona to a strict quality engineer: assume the implementation may be wrong, look for subtitle-quality drift, timing drift, UI/UX drift, flaky automation, fixture drift, memory leaks, stale workers, and misleading benchmark wins.
- Code review and QA review must be separate passes when the change touches performance, native code, STT, LLM, VAD, timing, app-command, project save/load, or queue behavior.

## Idea And Lesson Rules

- Before proposing or executing performance ideas, read `docs/planning_queue/ACTION_ITEMS.md`, `docs/planning_queue/waste_action_item.md`, and `docs/planning_queue/lesson_n_learned.md`.
- Do not re-propose rejected ideas from `docs/planning_queue/waste_action_item.md` unless new measurements clearly invalidate the old rejection.
- If a `docs/planning_queue/ACTION_ITEMS.md` experiment is slower, lower quality, less stable, or only wins on a short fixture while regressing X5, append it to `docs/planning_queue/waste_action_item.md` with hypothesis, change, metrics, quality result, artifact path, and rejection reason.
- Record repeat-prevention lessons in `docs/planning_queue/lesson_n_learned.md` whenever a mistake pattern, false diagnosis, risky shortcut, or ineffective optimization should not be repeated.
- Do not treat short Macau speed gains as sufficient. Check X5 3-minute rolling verification when quality or rolling-window performance can be affected. Run Tinyping only when the owner explicitly requests long-flow validation.
- After a normal successful idea/action/native item completion, remove that completed item from `docs/planning_queue/ACTION_ITEMS.md` so it shows only remaining executable work.

## Release Rules

- Release handoff is allowed only when the owner explicitly asks.
- Use `core/runtime/config.py` as version source of truth.
- Read only the immediately previous release note when drafting a new release note.
- Keep release history out of `docs/planning_queue/ACTION_ITEMS.md` and `AGENTS.md`.
- Mac App Store packaging/signing/upload/metadata execution is owner-approved for the current G0 lane, but signed package, validation, upload, and metadata proof remain required before any submission claim. DMG/Developer ID distribution remains a separate explicit request.

## Report Format

When finishing substantial work, report:

- 실행 모드
- 결과: pass / fail / blocked
- 저장 위치
- 원인 후보 또는 수정 요약
- 검증 명령과 결과
- 자막 품질 영향 여부
- 남은 위험 1-3줄
