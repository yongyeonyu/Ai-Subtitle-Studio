# RELEASE v04.00.04

Release date: 2026-05-13
Phase: MAC_NATIVE_APPSTORE_V4_0_4_RELEASED
Base branch: `codex/mac-native-appstore`
Immediately previous release: `v04.00.03`
Release app version: `04.00.04`

## Summary

v04.00.04 is an editor responsiveness, VAD automation, correction-dictionary runtime, and release-hardening update for the macOS Apple Silicon branch. It keeps the playback and cut-boundary work from v04.00.03, then removes user-facing VAD tuning from the settings surface, locks benchmarked VAD profiles to Fast/Auto/High mode defaults, speeds correction-dictionary lookup with a SQLite-backed runtime index, and fixes several save, idle-learning, Codex CLI, and cut-boundary persistence regressions discovered during real-project use.

The release goal is to make file-open, generation-complete, save, roughcut draft, and frame-accurate cut-boundary editing all feel more predictable without reintroducing heavy hidden background work on the editor screen.

## Changes Since v04.00.03

- Locked VAD model and threshold policy to benchmarked Fast/Auto/High mode defaults based on the canonical `test video/X5_시승기_후반` dialogue-heavy benchmark spans, and removed direct VAD controls from both the simplified AI settings and advanced tuning dialog.
- Kept automatic audio preset detection focused on audio frontend tuning only, so auto audio classification no longer overwrites mode-owned VAD policy.
- Added a SQLite-backed correction-dictionary runtime path with WAL/NORMAL sync, memory-backed temp storage, and indexed candidate gating while keeping `dataset_correction.json` as the editable source of truth.
- Clarified LLM integrity-failure logging, separated true empty output from guard-triggered rollback cases, and preserved rollback safety around unsafe rewrite attempts.
- Fixed Codex CLI roughcut JSON calls for `codex` subscription users by removing incompatible schema forcing from the roughcut JSON path while keeping structured split tasks validated.
- Reduced app startup and editor-open latency by deferring heavy Home/editor follow-up work, delaying interrupted idle-learning recovery, and moving expensive editor personalization lookups off the first paint path.
- Short-circuited no-op editor saves, delayed post-save analysis refresh, and deferred editor-save LoRA idle work so “Save” no longer immediately drags the app back into background learning.
- Promoted manual `<<` / `>>` cut search hits into persistent confirmed cut boundaries, rendered them with a stronger verified style, and made them available to later subtitle magnet timing adjustments.
- Improved visual cut-boundary verification and cancellation behavior so rollback candidates stop cleanly, playhead input unlocks immediately after cancel, and exact-frame landings surface in the terminal/status UI together with frame badges.
- Restored the global minimap bottom lanes into subtitle-versus-silence complementary colors, merged nearby subtitle fragments for readability, and halved the minimap subtitle lane height.
- Hid the legacy status rail when the unified progress card is present so the left sidebar no longer shows duplicated runtime status widgets.
- Hardened exit and quick-exit ordering so forced-process exit scheduling survives runtime pause exceptions instead of trapping the app in a half-closed state.
- Fixed stale project schema/version constants in older save helpers so project writes now consistently use the current shared schema version.

## Code Review Notes

- Reviewed the release-bound VAD change and removed the hidden `selected_vad` preserve path from mode switching so a previously saved manual VAD choice cannot silently override the locked mode profile.
- Reviewed the new correction-dictionary database path and intentionally moved the generated `dataset_correction.sqlite3` sidecar out of release scope by ignoring it in Git; the database is regenerated from JSON at runtime.
- Reviewed project save/version flows and replaced two stale `03.00.26` project schema literals with imports from the shared `project_format` source of truth.
- Reviewed the release regression suite and updated stale tests that still expected the pre-hardening quick-exit callback order or older literal project version strings.

## Compatibility Notes

- `core/runtime/config.py` is the source of truth for `APP_VERSION` and now reports `04.00.04`.
- `core/project/project_format.py` now marks newly saved project payloads as schema version `04.00.04`; helper modules now import that shared constant instead of carrying older literals.
- This branch remains macOS-only and Apple Silicon first.
- The correction dictionary still edits through `dataset/dataset_correction.json`; the SQLite sidecar is a runtime cache, not a hand-edited or source-controlled authority file.
- Fast/Auto/High remain the only user-facing Mode controls; VAD policy is now derived from mode and benchmark defaults rather than a separate settings menu.

## Verification

Completed verification for this release:

- `venv/bin/python -m compileall -q main.py core ui tests`
- `git diff --check -- .`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q`
  - `1680 passed, 5 subtests passed in 93.95s`
- `swift test` in `native/macos/AIStudioNative`
  - `16 tests, 0 failures`
- `packaging/macos/build_beta_dmg.sh`
  - Built, signed, validated, and verified `/Users/u_mo_c/Downloads/ai_subtitle_studio/dist/macos/AI Subtitle Studio-04.00.04-macOS.dmg`
  - Gatekeeper assessment failed as expected for the ad-hoc local test build; notarization was skipped because `NOTARY_KEYCHAIN_PROFILE` was not configured

Additional targeted verification during review:

- `QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/pytest -q tests/test_stt_quality_presets.py tests/test_mode_policy.py tests/test_ai_settings_runtime_apply.py tests/test_preset_auto_classifier.py`
  - `38 passed in 1.49s`
- `QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/pytest -q tests/test_project_context.py::ProjectContextTests::test_save_project_persists_editor_and_roughcut_state_together tests/test_sidebar_terminal_layout.py::SidebarTerminalLayoutTests::test_quick_exit_skips_backup_when_runtime_busy_and_pauses_first`
  - `2 passed in 0.90s`

Known warnings or limits:

- App Store credentialed upload was not attempted in this release pass because no Apple signing or upload credentials were provided in the environment.
- The correction-dictionary SQLite cache is rebuilt locally as needed, so first-use warmup can still happen once per machine or after JSON edits.

## Next Direction

The next risky area is making the VAD benchmark-lock workflow self-refreshing: automatically mine dense dialogue windows from the canonical `test video` assets, re-score Fast/Auto/High VAD profiles, and refresh the locked mode tables only when benchmark evidence stays stable across the reference set.
