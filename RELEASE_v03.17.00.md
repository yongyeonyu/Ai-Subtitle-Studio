# RELEASE v03.17.00

Release date: 2026-05-05
Phase: PHASE3
Base branch: `main`
Immediately previous release: `v03.16.00`
Release app version: `03.17.00`

## Summary

v03.17.00 is the Phase 3 personalization release. It moves the project beyond the PHASE2 stabilization focus from v03.16.00 and adds a ground-truth-driven learning workflow: verified media/SRT pairs can now be imported into a dedicated personalization store, subtitle style and line-break rules can be learned from that truth table, settings and prompt variants can be scored against ground truth, and the resulting recommendations can flow back into runtime processing across the shared pipeline.

This release note intentionally references only v03.16.00 as the previous checkpoint. Older cumulative history remains in older `RELEASE_v*.md` files and should not be copied into handoff documents.

## Changes Since v03.16.00

- Added a dedicated `dataset/lora_personalization/` store with manifest, truth-table, excluded-parenthetical, learned-rule, trial, best-settings, queue, and compaction support for persistent Phase 3 learning artifacts.
- Added ground-truth media/SRT discovery and pairing with exact and normalized basename matching, parenthetical exclusion tracking, and import-time truth-table generation.
- Added ambiguous pair resolution so users can choose among competing subtitle candidates instead of losing those assets during preview-only matching.
- Added rule learning from imported truth data, including learned split rules, learned line-break patterns, and a review/apply path for updating the shared subtitle-rule defaults.
- Added settings and prompt optimization scaffolding that scores candidate configurations against truth-table rows and records best-known per-media overrides.
- Added idle training orchestration with queue registration, pause/resume/clear controls, background execution, and automatic idle polling that no longer deadlocks on its own worker thread.
- Added runtime personalization override loading so learned recommendations can be applied for single-file, multiclip, folder queue, iCloud, and NAS processing paths through shared backend helpers.
- Expanded the personalization dialog into a working management surface for pair import, queue inspection, rule relearning, split-rule application review, and non-blocking pending-job execution.
- Updated runtime text/audio personalization paths so text LoRA corpus accumulation, voice bridge outputs, and audio preset LoRA records share the same Phase 3 storage direction more consistently.
- Refined the queue sidebar layout for narrow widths so long filenames, status labels, and elapsed/expected time rows remain readable during active processing.
- Split timeline silence-lane behavior so `여기부터 생성` and `여기까지 생성` operate from the upper silence lane instead of mixing upper/lower silence semantics.
- Hardened personalization idle tracking in the main window so normal mouse and keyboard activity refreshes the idle timer, while post-completion idle countdowns no longer disable the general personalization event filter.
- Added regression coverage for ground-truth import, rule learning, trial scoring, personalization idle runtime behavior, queue/UI interactions, and timeline silence-lane behavior.

## Compatibility Notes

- The shared pipeline requirement still applies to single-file, multiclip, folder queue, iCloud, and NAS modes.
- macOS and Windows remain supported targets. Path handling must continue to cover Korean filenames, spaces, backslashes, subprocess entry points, ffmpeg/ffprobe, faster-whisper workers, and PyQt6 runtime behavior.
- `core/runtime/config.py` remains the source of truth for `APP_VERSION`.
- The handoff set remains `AGENTS.md`, `ACTION_ITEMS.md`, `File_structure.txt`, `README.md`, and the latest `RELEASE_v*.md`.

## Verification

Completed verification for this release:

- `venv/bin/python -m pytest -q --ignore=tests/test_sidebar_terminal_layout.py`
  - `570 passed in 12.23s`
- `venv/bin/python -m pytest -q tests/test_sidebar_terminal_layout.py`
  - `41 passed in 6.54s`
- Combined verified tests: `611 passed`
- `python3 -m compileall -q main.py core ui tests`
- `git diff --check -- .`

The sidebar-terminal UI suite is verified separately in offscreen mode because a single all-in-one PyQt test process can still abort during widget teardown on macOS even after the individual suites pass.

## Next Direction

No active non-iPad backlog remains in `ACTION_ITEMS.md`. The only parked work is `PHASE4_iPad`, and that scope remains excluded until the user explicitly asks to resume it.
