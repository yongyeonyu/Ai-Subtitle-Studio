<!--
Document-Version: 04.00.13-mac-native
Phase: MAC_NATIVE_APPSTORE_V4_0_13_RELEASED
Last-Updated: 2026-05-22
Updated-By: Codex
Purpose: Agent bootstrap, operating rules, and new-chat continuation prompt.
-->
# AGENTS.md - Agent Bootstrap Guide

## Project

- Path: `/Users/u_mo_c/Downloads/ai_subtitle_studio`
- App version in code: `04.00.13`
- Latest release checkpoint: `v04.00.13`
- Platform: macOS, Apple Silicon first.
- Product priority: subtitle quality before speed; optimize runtime only with behavior-preserving tests.
- UI/UX rule: do not change UI, UX, labels, layout, colors, shortcuts, menus, or popup behavior unless the owner explicitly asks.
- Release note retention: keep `RELEASE_v04.00.07.md` and newer only. Older release notes and `check_list.md` were intentionally deleted.

## Bootstrap Order

Read these first when continuing work:

1. `AGENTS.md`
2. `ACTION_ITEMS.md`
3. `README.md`
4. `test_case.md`
5. `test_result.md`
6. `waste_action_item.md`
7. `lesson_n_learned.md`
8. `File_structure.txt`
9. `CODEMAP.md` if present
10. Latest `RELEASE_v*.md`

When validating the current release baseline, also read:

- `output/manual_verification/latest/qa_suite_full_20260522_081710/suite_result.md`

Former standalone handoff/planning files have been consolidated:

- `idea_item.md` -> merged into `ACTION_ITEMS.md`
- `NATIVE_LIB_PLAN.md` -> merged into `ACTION_ITEMS.md`
- `NEW_CHAT_PROMPT.md` -> merged into this file

Do not recreate those files unless the owner explicitly asks.

## Document Roles

- `AGENTS.md`: this bootstrap, operating-rule, and new-chat continuation file.
- `ACTION_ITEMS.md`: single source of truth for active ideas, action/native work, execution order, QA gates, rollback rules, and parked candidates.
- `waste_action_item.md`: rejected or ineffective experiments. Check it before proposing or repeating optimization ideas.
- `lesson_n_learned.md`: repeat-prevention lessons for bad diagnoses, ineffective optimizations, and risky shortcuts.
- `README.md`: product overview and current user-facing workflow.
- `test_case.md`: QA rules, fixture registry, and one-command QA expectations.
- `test_result.md`: latest QA evidence and artifact references.
- `RELEASE_v*.md`: release notes from `v04.00.07` onward.

Completed item rule:

- When an item in `ACTION_ITEMS.md` is completed normally, delete the completed item text from that queue document instead of leaving checked-off history.
- Preserve useful completion evidence in release notes, `test_result.md`, `output/manual_verification/latest/`, `waste_action_item.md`, or `lesson_n_learned.md` only when it is needed for future decisions.

## Current Continuation State

- One-command QA runner is the official real-app test entrypoint:
  - `./venv/bin/python tools/qa_suite_runner.py quick`
  - `./venv/bin/python tools/qa_suite_runner.py major`
  - `./venv/bin/python tools/qa_suite_runner.py full`
- Latest known one-command full QA pass:
  - `output/manual_verification/latest/qa_suite_full_20260522_081710`
  - command: `./venv/bin/python tools/qa_suite_runner.py full`
  - result: pass, `failed_count=0`
  - scenarios: `editor_compact_macau`, `video_menu_macau`, `save_export_macau`, `menu_stt_lora_macau`, `x5_high_rolling_180s`
- Latest full QA X5 rolling summary:
  - artifact: `output/manual_verification/latest/qa_suite_full_20260522_081710/x5_high_rolling_180s`
  - `total_elapsed_sec=61.142`
  - `pipeline_elapsed_sec=61.027`
  - `peak_rss_bytes=2154872832`
  - `final/raw=54/52`
  - STT pressure transitions: `['critical', 'critical']`
- Recent live-app STT recovery check:
  - artifact: `output/manual_verification/latest/20260522_stt_zero_result_fallback_live`
  - `snapshot_after_early_stt.png` shows subtitles appearing from `00:00.000` while generation is still in progress.
  - log evidence confirmed early STT preview, rolling STT, and Fast-STT2 activity.
- Current active queue source: `ACTION_ITEMS.md`, section `Active Execution Queue`.
- Current active item: X5 High post-STT UI/status hot path trim.

## Current Risks

- High path can pass QA while memory pressure still enters `critical`; do not treat pass/fail alone as enough for performance conclusions.
- Critical pressure may come from system/native pressure, compressed/wired memory, MPS/Metal driver memory, warm STT workers, LLM residency, editor preview, and app process RSS together.
- Long-flow STT2 rescue and word timestamp precision still have meaningful wall-clock cost; optimize only by reducing waiting, cleanup churn, UI/status hot paths, or safe resource lifetime waste.
- Do not lower X5 quality gates, skip STT2, skip LLM, downgrade models, or loosen subtitle quality policy as a speed optimization.
- Tinyping long-flow is manual-only unless the owner explicitly requests it.

## Narrow Next Item

Use `ACTION_ITEMS.md` as the executable queue. The current narrow target is:

1. Prevent STT live preview from synchronously generating 4K seek thumbnails through `ffmpeg` during backend processing. Keep text live updates.
2. Make `guided-subtitle-status` expose compact current fields even when full status is busy/truncated: `generation_stage`, `last_stage_key`, subtitle count, roughcut state, runtime timestamp.
3. Add resource active labels for `subtitle_optimize`/subtitle LLM and a short pressure gate before roughcut LLM if `stt_transcribe_done` leaves pressure at `critical`.

QA gate for that item:

- X5 High real-app run must keep final subtitle count and roughcut LLM completion behavior equivalent.
- `output/memory_monitor/subtitle_generation_latest.json` must show pressure evidence without subtitle quality policy changes.
- If app-command, automation, or bundle-facing surface changes, rebuild the app bundle before `major` or `full` QA with `./packaging/macos/build_app_bundle.sh`.

## Fixtures

- Macau quick/smoke: `/Users/u_mo_c/Downloads/마카오테스트`
- X5 accuracy: `/Users/u_mo_c/Downloads/ai_subtitle_studio/test video/X5_시승기_후반.MP4` plus sibling `.srt`
- Tinyping long-flow: `/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.MP4` (manual only; excluded from default QA unless explicitly requested)
- Store verification artifacts under `output/manual_verification/latest/`.

## Operating Rules

- Reply to the owner in Korean.
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

- When reviewing, correcting, or executing `ACTION_ITEMS.md`, act as a senior Apple Silicon MacBook developer: prefer macOS-native realities over generic optimization advice, use precise Apple terms such as ANE/Core ML/Metal/MLX/Accelerate, and reject ideas that add bridge cost, memory pressure, or subtitle-quality risk without measured benefit.
- During implementation and code review, first use a meticulous senior developer viewpoint: check architecture boundaries, fallback paths, race conditions, resource lifetime, macOS process behavior, native bridge overhead, and maintainability.
- During QA/test review, switch persona to a strict quality engineer: assume the implementation may be wrong, look for subtitle-quality drift, timing drift, UI/UX drift, flaky automation, fixture drift, memory leaks, stale workers, and misleading benchmark wins.
- Code review and QA review must be separate passes when the change touches performance, native code, STT, LLM, VAD, timing, app-command, project save/load, or queue behavior.

## Idea And Lesson Rules

- Before proposing or executing performance ideas, read `ACTION_ITEMS.md`, `waste_action_item.md`, and `lesson_n_learned.md`.
- Do not re-propose rejected ideas from `waste_action_item.md` unless new measurements clearly invalidate the old rejection.
- If an `ACTION_ITEMS.md` experiment is slower, lower quality, less stable, or only wins on a short fixture while regressing X5, append it to `waste_action_item.md` with hypothesis, change, metrics, quality result, artifact path, and rejection reason.
- Record repeat-prevention lessons in `lesson_n_learned.md` whenever a mistake pattern, false diagnosis, risky shortcut, or ineffective optimization should not be repeated.
- Do not treat short Macau speed gains as sufficient. Check X5 3-minute rolling verification when quality or rolling-window performance can be affected. Run Tinyping only when the owner explicitly requests long-flow validation.
- After a normal successful idea/action/native item completion, remove that completed item from `ACTION_ITEMS.md` so it shows only remaining executable work.

## Release Rules

- Release handoff is allowed only when the owner explicitly asks.
- Use `core/runtime/config.py` as version source of truth.
- Read only the immediately previous release note when drafting a new release note.
- Keep release history out of `ACTION_ITEMS.md` and `AGENTS.md`.
- DMG/installer/App Store packaging is not part of default release work. Run it only when explicitly requested.

## Report Format

When finishing substantial work, report:

- 실행 모드
- 결과: pass / fail / blocked
- 저장 위치
- 원인 후보 또는 수정 요약
- 검증 명령과 결과
- 자막 품질 영향 여부
- 남은 위험 1-3줄
