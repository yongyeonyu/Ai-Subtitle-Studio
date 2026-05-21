<!--
Document-Version: 04.00.13-mac-native
Phase: MAC_NATIVE_APPSTORE_V4_0_13_RELEASED
Last-Updated: 2026-05-22
Updated-By: Codex
Purpose: Short agent bootstrap and execution rules only.
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
2. `README.md`
3. `test_case.md`
4. `test_result.md`
5. `idea_item.md`
6. `waste_action_item.md`
7. `lesson_n_learned.md`
8. `File_structure.txt`
9. `CODEMAP.md` if present
10. Latest `RELEASE_v*.md`

`ACTION_ITEMS.md` and `NATIVE_LIB_PLAN.md` are now short pointer documents. Do not treat them as separate queues.

## Document Roles

- `AGENTS.md`: this short bootstrap and operating-rule file.
- `idea_item.md`: single source of truth for active ideas, migrated action/native work, execution order, QA gates, rollback rules, and the `아이디어 전부 실행해` plan.
- `waste_action_item.md`: rejected or ineffective experiments. Check it before proposing or repeating optimization ideas.
- `lesson_n_learned.md`: repeat-prevention lessons for bad diagnoses, ineffective optimizations, and risky shortcuts.
- `ACTION_ITEMS.md`: pointer to `idea_item.md` only.
- `NATIVE_LIB_PLAN.md`: pointer to `idea_item.md` only.
- `README.md`: product overview and current user-facing workflow.
- `test_case.md`: QA rules, fixture registry, and one-command QA expectations.
- `test_result.md`: latest QA evidence and artifact references.
- `RELEASE_v*.md`: release notes from `v04.00.07` onward.

Completed item rule:

- When an item in `idea_item.md`, `ACTION_ITEMS.md`, or `NATIVE_LIB_PLAN.md` is completed normally, delete the completed item text from that queue document instead of leaving checked-off history.
- Preserve useful completion evidence in release notes, `test_result.md`, `output/manual_verification/latest/`, `waste_action_item.md`, or `lesson_n_learned.md` only when it is needed for future decisions.

## Current Continuation State

- One-command QA runner is the official real-app test entrypoint:
  - `./venv/bin/python tools/qa_suite_runner.py quick`
  - `./venv/bin/python tools/qa_suite_runner.py major`
  - `./venv/bin/python tools/qa_suite_runner.py full`
- Latest known full QA pass: `output/manual_verification/latest/qa_suite_full_20260521_022256`.
- Current optimization plan: `idea_item.md`, section `2026-05-20 최종 통합 실행 계획: ACTION_ITEMS + NATIVE_LIB_PLAN 전체`.
- When the owner says `아이디어 전부 실행해`, execute that integrated plan in phase order with branch, commits, QA gates, rollback notes, `waste_action_item.md`, and `lesson_n_learned.md`.
- Latest release focus: Apple Silicon selective STT2/runtime override hardening, X5 High regression closure, single-owner 2D timeline rendering, and clean app close handling.

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
- If code changes touch subtitle quality, STT, LLM, VAD, timing, project save/load, queue, app-command, or native paths, run targeted tests plus the relevant real fixture.
- If command surface or editor automation changes, rebuild the app bundle before `major` or `full` QA with `./packaging/macos/build_app_bundle.sh`.

## Persona Rules

- When reviewing, correcting, or executing `idea_item.md`, act as a senior Apple Silicon MacBook developer: prefer macOS-native realities over generic optimization advice, use precise Apple terms such as ANE/Core ML/Metal/MLX/Accelerate, and reject ideas that add bridge cost, memory pressure, or subtitle-quality risk without measured benefit.
- During implementation and code review, first use a meticulous senior developer viewpoint: check architecture boundaries, fallback paths, race conditions, resource lifetime, macOS process behavior, native bridge overhead, and maintainability.
- During QA/test review, switch persona to a strict quality engineer: assume the implementation may be wrong, look for subtitle-quality drift, timing drift, UI/UX drift, flaky automation, fixture drift, memory leaks, stale workers, and misleading benchmark wins.
- Code review and QA review must be separate passes when the change touches performance, native code, STT, LLM, VAD, timing, app-command, project save/load, or queue behavior.

## Idea And Lesson Rules

- Before proposing or executing performance ideas, read `idea_item.md`, `waste_action_item.md`, and `lesson_n_learned.md`.
- Do not re-propose rejected ideas from `waste_action_item.md` unless new measurements clearly invalidate the old rejection.
- If an `idea_item.md` experiment is slower, lower quality, less stable, or only wins on a short fixture while regressing X5, append it to `waste_action_item.md` with hypothesis, change, metrics, quality result, artifact path, and rejection reason.
- Record repeat-prevention lessons in `lesson_n_learned.md` whenever a mistake pattern, false diagnosis, risky shortcut, or ineffective optimization should not be repeated.
- Do not treat short Macau speed gains as sufficient. Check X5 3-minute rolling verification when quality or rolling-window performance can be affected. Run Tinyping only when the owner explicitly requests long-flow validation.
- After a normal successful idea/action/native item completion, remove that completed item from `idea_item.md`, `ACTION_ITEMS.md`, or `NATIVE_LIB_PLAN.md` so those files show only remaining executable work.

## Release Rules

- Release handoff is allowed only when the owner explicitly asks.
- Use `core/runtime/config.py` as version source of truth.
- Read only the immediately previous release note when drafting a new release note.
- Keep release history out of `ACTION_ITEMS.md`, `NATIVE_LIB_PLAN.md`, and `AGENTS.md`.
- DMG/installer/App Store packaging is not part of default release work. Run it only when explicitly requested.
