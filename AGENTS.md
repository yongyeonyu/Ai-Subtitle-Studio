<!--
Document-Version: 04.00.11-mac-native
Phase: MAC_NATIVE_APPSTORE_V4_0_11_RELEASED
Last-Updated: 2026-05-20
Updated-By: Codex
Purpose: Agent bootstrap, token-efficient navigation, and handoff rules only.
-->
# AGENTS.md - Agent Bootstrap Guide

This file is the first document an assistant should read when continuing work on AI Subtitle Studio. It should stay short, current, and operational. Historical release details belong in `RELEASE_v*.md`; task backlog belongs in `ACTION_ITEMS.md`; product overview belongs in `README.md`; the shallow actual tree belongs in `File_structure.txt`; the responsibility and hot-path map belongs in `CODEMAP.md`.

## Bootstrap Contract

If this file is the only file uploaded into a new chat, the assistant must locate the project root and read the rest of the handoff set automatically.

Required discovery order:

1. Read `AGENTS.md`.
2. Find and read `ACTION_ITEMS.md`.
3. Find and read `File_structure.txt`.
4. If `CODEMAP.md` exists, read it next.
5. Find the latest `RELEASE_v*.md` by version number and read only that release note first.
6. Read `README.md`.

Filename matching must be tolerant of case and spacing hints from the user:

- `agents.md` maps to `AGENTS.md`.
- `action_items.md` maps to `ACTION_ITEMS.md`.
- `File_Structure.txt` maps to `File_structure.txt`.
- `codemap.md` maps to `CODEMAP.md`.
- `Release_Vxx.xx.xx.md` maps to the latest actual `RELEASE_v*.md`.
- `Read.me` maps to `README.md`.

Do not ask the user to upload the other repository handoff documents if they exist in the repository.

## Handoff File Roles

Keep these five files non-overlapping:

- `AGENTS.md`: assistant operating rules, bootstrap rules, release-handoff rules, and current continuation facts.
- `ACTION_ITEMS.md`: remaining work queue only, ordered by execution priority.
- `File_structure.txt`: shallow actual filesystem map only, with no review notes or speculative cleanup notes.
- `README.md`: product purpose, installation, usage direction, and concise current-state summary.
- `RELEASE_v*.md`: versioned release note for one release, based only on the immediately previous release.

Optional support file:

- `CODEMAP.md`: concise responsibility map, hot paths, entry points, and targeted verification map. It is not a full tree and it must not duplicate release history or backlog text.

## Release Handoff Rules

When the user asks to release, update the five handoff documents so a future chat can continue without old context. Refresh `CODEMAP.md` too when hot paths, module ownership, or verification entry points changed.

Release workflow:

1. Determine the current app version from `core/runtime/config.py`.
2. Determine the latest existing `RELEASE_v*.md`.
3. Use only the immediately previous release note as historical reference.
4. Create or refresh the current release note without copying older cumulative history.
5. Refresh `AGENTS.md`, `ACTION_ITEMS.md`, `File_structure.txt`, and `README.md`.
6. Refresh `CODEMAP.md` when it exists or when the edited areas changed the current hot paths.
7. Keep the handoff documents in English, except for unavoidable source data such as real filenames or Korean subtitle-rule tokens.
8. Remove stale release history, obsolete review notes, and duplicated summaries from the handoff files.
9. Do not update unrelated documents during release unless the user explicitly asks.

If the release changes the app version, update `core/runtime/config.py` as the source of truth. The handoff set is still the five documents listed above.

## New Chat Handoff Rule

When the user says `새로운 채팅하자` or equivalent, treat it as a formal handoff request for a fresh chat.

Required workflow:

1. Refresh `AGENTS.md` first if the current chat materially changed durable continuation facts, test rules, fix status, or next steps.
2. Do not rewrite `ACTION_ITEMS.md` unless the remaining priority queue itself changed.
3. Reply to the user in Korean, but keep repository documents in English.
4. Provide a ready-to-paste new-chat prompt plus a compact handoff summary.
5. The handoff summary must be token-efficient but detailed:
   - prefer short declarative lines over prose;
   - include only current facts, verified fixes, active risks, exact test assets, and next actions;
   - avoid praise, repetition, long narrative history, and already-obsolete branches;
   - include concrete file paths, commands, and validation results when they matter.
6. If a restart point or runtime issue was debugged in the current chat, explicitly state:
   - exact root cause;
   - exact files changed;
   - exact tests or real-media checks already run;
   - the next highest-value unresolved check.

## Current Continuation Facts

- Project path: `/Users/u_mo_c/Downloads/ai_subtitle_studio`
- Real benchmark fixtures: `/Users/u_mo_c/Downloads/ai_subtitle_studio/test video` contains the canonical local video/SRT pair for 3-minute subtitle pipeline benchmarks. Use `test video/X5_시승기_후반.MP4` with its sibling `.srt` as the accuracy truth/reference pair when comparing STT order, LoRA/Deep/LLM gating, timing, VAD, and cut-boundary variants.
- Short-video test rule: use `/Users/u_mo_c/Downloads/마카오테스트` for quick smoke tests, short subtitle-generation regressions, and fast UI/runtime verification runs.
- Long-video test rule: use `/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.MP4` for long-running pipeline checks, cache-reset/fresh-run validation, ETA/progress observation, and memory/performance validation on extended media.
- New-chat rule: when handing off to a fresh chat, keep the user-facing handoff in Korean but compress it for token efficiency; prefer exact paths, commands, verified results, and next actions over narrative explanation.
- Current app version in code: `04.00.11`
- Current handoff document version: `04.00.11-mac-native`
- Latest release checkpoint: `v04.00.11`
- Current phase: `MAC_NATIVE_APPSTORE_V4_0_11_RELEASED`
- Next planned phase: none.
- Product priority: generate highly accurate subtitles with the fewest necessary user settings, while keeping generation startup, cut-boundary scanning, playback, and editor-mode subtitle edits responsive.
- Shared pipeline rule: core subtitle algorithms must work across single-file, multiclip, folder queue, iCloud, and NAS workflows.
- Platform rule: this branch is macOS-only and Apple Silicon first. Do not add Windows/Linux fallback work unless the user explicitly asks to restart cross-platform development. However, most reusable business logic should be shaped as Apple-platform Swift core code that can later move to iPadOS with minimal changes.
- Release state: Fast, Auto, and High are now the single user-facing Mode controls. Fast runs LoRA-only subtitle post-processing, Auto runs LoRA + Deep, and High runs LoRA + Deep + chunked LLM. Legacy `balanced`, `normal`, `보통`, and `균형` settings map to Auto; legacy `fast` and `precise` settings are preserved as Fast and High when no explicit `subtitle_mode` exists.
- Speaker state: visible speaker count is now automatic per local span instead of a fixed global setting, and learned `voice_data` speaker profiles (`spk1`/`spk2`/`spk3`) should be preferred when diarization evidence is strong enough.
- Dictionary state: the correction dictionary now has an in-app editor reachable from the bottom menu, while `dataset/dataset_correction.json` remains the editable source of truth and runtime indexed caches stay derived data.
- Mode-manager state: `core/mode_manager.py` is now the central owner for Fast/Auto/High/STT mode policy. Mode-managed routes such as audio preset, VAD, and ensemble gates should not be re-persisted by LoRA autopilot; only user-selectable model identities should flow back into per-mode defaults.
- Tiniping benchmark state: `tools/benchmark_tiniping_mode_search.py` plus `output/manual_verification/latest/tiniping_benchmark_summary.md` now lock Fast/Auto/High defaults from the 티니핑 0~3분 sweep and 0~11분 final run. STT model menus surface `[Fast]`, `[Auto]`, and `[High]` tags on the winning STT1/STT2 models.
- Adaptive audio state: chunk audio routing now has profile-memory reuse, preview self-score guard, and switch-confirmation heuristics in `core/audio/media_processor_audio.py` and `core/audio/preset_auto_classifier.py`; High keeps the conservative benchmark-locked route by default, while adaptive routing remains available for broader runtime use and benchmark suites.
- High timing state: High now keeps `ffmpeg/silero relaxed` plus a 120-second rolling STT window with 8-second overlap and 4-second hysteresis so benchmark-locked timing survives the real transcribe path instead of only the search harness.
- Completion state: subtitle generation, editor save, quality review, and cleanup paths clear foreground busy UI before deferred learning starts; editor-save truth/text LoRA work is queued for Home-idle processing.
- Completion score state: when subtitle generation finishes, the Home sidebar progress card appends the final subtitle self-review score next to elapsed/expected time, rounded to two decimals, so queue review can see quality without reopening the editor.
- Generation completion state: the editor does not mark subtitle generation complete from STT progress alone. Backend finalization waits until saveable subtitle segments exist, retries completion autosave when the timeline is still being populated, and prevents empty-segment auto-save failures.
- Runtime ETA state: queue/startup ETA now records mode, STT pair, LLM/audio/VAD, media length/FPS/resolution, queue/cache state, and recent-history weighting in `time_history.json` through `core.runtime_eta`, while `core.time_history` stays as a compatibility shim.
- STT preview state: live STT1/STT2 previews can surface immediately on timeline lanes through lightweight raw preview rows, but the editor text pane remains reserved for committed subtitle segments only.
- Save recovery state: generation-complete and manual save now rebuild from backend subtitle backups when a transient empty editor state appears just before autosave or project save.
- Exit-save state: both sidebar quick exit and native window close ask whether to save unsaved editor changes before runtime pause, model cleanup, or application quit.
- Project backup state: numbered project JSON backups are archived under a sibling `프로젝트백업/` folder, and legacy root-level numbered backups are moved there on the next project save.
- Direct SRT parity state: opening a subtitle file now searches for a matching sidecar project JSON and rehydrates project subtitle metadata so timestamp tags, speaker circles, quality/stage chips, voice-activity overlays, provisional cut-boundary lines, and cut-boundary placeholder middle segments render like project-open state; pure SRT open still intentionally omits STT1/STT2 preview lanes.
- Editor layout state: the editor text pane, video preview, and timeline are mounted inside stable render frames so Start/status changes do not resize the major editor surfaces.
- Fast quality state: Fast mode stays lightweight but selectively rechecks low-score STT1 spans with the secondary STT model when configured, preserving minimum quality without rerunning the full High stack.
- Playback state: post-generation quality review, roughcut draft work, prefetch, cleanup, and model release are deferred or throttled while video playback is active.
- Playback subtitle state: final subtitle text remains visible in the segment lanes during playback, and the video subtitle overlay now refreshes/reapplies hidden context even when the current subtitle string did not change.
- Roughcut completion state: post-generation roughcut draft persistence now uses `save_project_roughcut_state(...)` for draft metadata plus an explicit editor unlock path, so segment-edge edits, diamond edits, save, and quit do not stay blocked behind a full project re-save.
- Manual roughcut rerun state: the global timeline canvas can now save the current subtitles, rerun only the roughcut LLM, and re-sort middle rows chronologically before applying them, so manual roughcut refresh does not overwrite the editor with a stale local fallback order.
- Layout convergence state: editor video/timeline vertical rebalancing can schedule a few follow-up passes after resize/open so the remaining video-gap converges instead of stopping one pass too early.
- Runtime stability state: user, folder, custom-default, and project JSON writes use safe atomic replacement; settings load can recover from `.bak` backups after partial-write JSON errors. Project writes now default to the canonical ordered JSON writer so the top-level `video` header remains first for frame-based reloads; Swift project read/validation remains available and Swift project write is opt-in through `AI_SUBTITLE_STUDIO_SWIFT_PROJECT_WRITE`.
- Exception hygiene state: editor teardown, export-dialog settings/SRT scratch cleanup, diarization cache I/O, VAD strict metadata persistence, and watch-folder/project data helpers now prefer typed exception handling with logging over silent `except: pass`, so release regressions are diagnosable instead of disappearing during cleanup.
- Dashboard runtime state: automatic audio-filter and VAD choices selected for the current file are surfaced in the sidebar pipeline dashboard with an auto marker and tooltip context.
- GPU state: GPU rendering can be selected by frame or for the whole editor through settings while OpenGL widgets and global Qt OpenGL remain conservative opt-ins; the timeline playhead overlay currently stays QWidget-backed to avoid QQuickWidget compositing hiding the painter canvas.
- Idle learning state: automatic LoRA/personalization learning starts only after Home has been idle for five minutes, ramps from Lite to Heavy, and mouse/key input requests a quick stop. The app indicator blinks blue while learning is active.
- Refactor state: `core.engine.subtitle_macro_chunks` owns 10-15 subtitle LLM macro chunk grouping and execution; `subtitle_engine.py` keeps orchestration and final timing/gap passes.
- Dashboard state: the sidebar engine dashboard shows ten stages: cut boundary, preprocessing, audio filter, STT1, STT2, VAD, subtitle LLM, roughcut LLM, LoRA, and deep learning.
- Editor performance state: subtitle line edits update cached line maps and the affected timeline dirty rectangle instead of rebuilding the full segment lookup; playback/editor sync respects recent manual scrolling and avoids recentering already visible active segments.
- Runtime scheduling state: cut-boundary pioneer/follower workers use topology-aware CPU planning, OpenCV thread caps, progress throttling, optional FFmpeg scene prepass, optional C++ native helper kernels, and optical-flow follower verification for candidate-only rollback checks.
- VAD state: the settings UI no longer exposes direct VAD tuning on this branch; Fast/Auto/High lock benchmarked VAD model/threshold profiles derived from the canonical `test video/X5_시승기_후반` dialogue-dense spans, while automatic audio preset detection can still adjust only the audio frontend stack.
- Cut-boundary contract state: generation start must immediately create one full-range middle segment `A - 주제없음`; audio provisional boundaries render as neon-green 1px solid lines, visual provisional boundaries render as neon-blue 1px solid lines, follower-checked provisional boundaries render as gray dotted lines, and follower-reviewed rows create the first colored A-Z middle-segment draft before the roughcut LLM refines it from subtitles.
- Cut-boundary UI state: follower-checked audio/provisional rows and terminal end-frame boundary helpers remain persisted in project metadata for timing/reference work, but the official timeline UI now hides them after verification so stale helper lines do not survive into normal editor review.
- Backend routing state: STT, VAD, cut-boundary, audio extraction, LLM, and editor rendering paths now default to native policies on this branch, with optional benchmark profile materialization stored outside Git.
- Mac-native acceleration state: production runtime uses benchmark-safe native routes by default: WhisperKit/Core ML/MLX STT, C++ VAD overlap/alignment math, C++ LLM macro grouping, C++ indexed correction-dictionary cleanup, adaptive Swift batch quality scoring, adaptive Swift common split planning, and native macOS input-activity snapshots for fast LoRA stop behavior. Swift LoRA scoring, Swift Deep rerank, and Swift LLM candidate policy remain benchmark-only behind `native_swift_policy_experimental_enabled` or the explicit experimental environment gate because they were slower or changed LoRA ranking parity.
- Apple Silicon scheduling state: runtime worker counts, FFmpeg thread budgets, pioneer/follower cut-boundary concurrency, and GPU/NPU slot use can now be materialized from detected Apple Silicon topology, including M5-specific defaults on the current Mac.
- Audio/video IO state: long-media audio extraction defaults to direct FFmpeg chunk routing with a 1-second native threshold, overlapped native audio preprocessing, fused filter graphs, and native ClearVoice FFmpeg mode when quality-safe; editor playback reuses 720p preview proxies and cut-boundary scanning can reuse existing proxies to avoid repeated 4K decode.
- STT model state: Swift WhisperKit persistent is the default STT1 route on macOS; Korean KomixV2 STT candidates include alias, Hugging Face original, and MLX variants with distinct sidebar labels; whisper.cpp remains an optional native fallback route.
- Word timestamp state: default STT passes keep word timestamps off for speed; low-score, editor-selected, precision-review, and VAD-risk spans are re-run selectively with word timestamps to preserve timing quality.
- LLM state: roughcut/subtitle LLM lists include an OpenAI Codex ChatGPT CLI option that uses the local Codex subscription flow without requiring an API key or Ollama preflight.
- Roughcut Codex state: the Codex roughcut path now uses wider row context, a longer timeout, override-model inheritance fixes, and a clean fallback to local-rule drafts when the Codex CLI times out.
- Automation state: `tools/appctl.py`, `ui/main/app_command_bridge.py`, and `ui/editor/editor_automation.py` now expose deterministic editor actions such as playhead moves, smart split staging/commit, segment-edge movement, diamond movement, shadow-playhead control, current roughcut start, and multiclip start; use these before relying on fragile UI-only interaction when real-app verification is needed.
- Verification artifact state: compact real-app verification output should be written under `output/manual_verification/latest/` first, then optionally copied into a named sibling folder when a preserved archive is useful.
- Restart reliability state: restarting subtitle generation from a completed single-file editor now detects a dead backend pipeline thread and falls back to a fresh `start_pipeline(..., is_auto_start=True)` instead of signaling a dead thread; this was verified with the short Macau fixture after cache reset and app relaunch.
- Restart verification state: after relaunch, `open-media` + `start-current-pipeline` on `/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224203_0075_D.MP4` re-entered cut-boundary, VAD, STT prep, and STT1/STT2 stages; command/status snapshot calls can still time out under heavy main-thread load, so terminal logs remain the primary truth source during active generation.
- Smart split state: normal double-click Enter remains plain inline edit, while smart split is now a right-click split mode that arms the playhead, visually marks the target segment, locks diamond/segment-length editing, and commits on Enter using the current text cursor plus the armed playhead time.
- Timeline assist state: a single shadow playhead can be pinned and is used as a magnetic timing reference for segment handles and diamonds; high-zoom playback follow now uses frame-based centering math so the playhead no longer jitters while the background scrolls.
- Sidebar layout state: runtime resource metrics live in the top progress card under elapsed/expected time, the lower dashboard card no longer duplicates that line, and the sidebar width now follows responsive window sizing instead of manual drag resizing.
- Shutdown state: Home-idle LoRA/background learning uses a cancellable subprocess path and fast-detach shutdown guards, and subtitle-text focus-loss cleanup now tolerates deleted Qt wrappers instead of aborting during quit.
- App Store packaging state: macOS packaging scripts can build the `.app` payload, copy Swift WhisperKit and native helpers, sign locally, validate bundle layout, create/validate a local beta DMG, run double-click `.command` build/update flows for this Mac, prepare Developer ID notarization, build a signed App Store `.pkg`, and validate/upload that package when the user supplies Apple credentials.
- Packaging rule: do not build or rebuild DMG files by default, including normal release work. Run DMG packaging only when the user explicitly asks for a DMG, installer, beta package, distribution build, or DMG validation.
- Benchmark state: macOS native benchmark tools report STT backend readiness, optional real-audio STT WER comparisons, and adopt/fallback decisions for WhisperKit, direct ClearVoice audio, and native cut-boundary routing.
- Swift migration state: `native/macos/AIStudioNative` is the first Swift-native core package. It now owns the subtitle segment model, SRT parser/formatter, project JSON validation/atomic write helpers, timeline waveform peak/downsample and minimap column engines, runtime ETA estimation, startup diagnostic shaping, cut-boundary cache planning, an opt-in subtitle quality batch scorer, adaptive common split planner, CLI bridge, packaged-app integration, and Python fallback hooks. New macOS-native work should prefer this package when behavior can match or exceed Python, and should keep core algorithms separated from macOS-only UI/process APIs so they can be reused by a future iPad app.
- Popup/UI state: QML context menus and message dialogs have compact Apple-style sizing, hover/press feedback, outside-click dismissal, and Korean-only global menu labels.
- STT ensemble state: parallel STT1/STT2 runs clone chunk directories per worker and clean them afterward so one worker cannot delete audio chunks still needed by the other.
- Refactor state: the longest subtitle/project/editor/runtime modules were split by responsibility into `core.audio.transcribe_worker_io`, `core.engine.subtitle_segment_filter`, `core.engine.subtitle_accuracy_utils`, `core.pipeline.cut_boundary_cache`, and `ui.editor.editor_segments_bulk_load` so future native migration work has smaller seams.
- Verification state: `v04.00.11` release verification now covers repeated-generation memory-pressure cleanup, STT/native optimization seams, video subtitle overlay context, `compileall`, `git diff --check`, focused unit sweeps, and a real Macau app snapshot. Full release verification details are in `RELEASE_v04.00.11.md`.
- Latest runtime reliability state: personalization full-learning stop/exit now keeps cancellation responsive through import and index rebuild phases, and current remaining work explicitly tracks the unresolved `QTableWidget` stylesheet parse warning on `MainWindow`-heavy paths.
- Latest regression checkpoint: on 2026-05-20, `./venv/bin/python -m unittest tests.test_video_player_widget tests.test_timeline_playhead_fit tests.test_editor_video_context_window tests.test_project_segment_reload tests.test_runtime_memory_manager tests.test_media_processor_overlap tests.test_action_item_runtime_services tests.test_ollama_provider tests.test_app_command_bridge tests.test_cut_boundary_verify_strategy tests.test_stt_lattice_service tests.test_stt_recheck_service tests.test_timeline_paint_passes tests.test_qml_popup_guard -q`, `./venv/bin/python -m compileall -q core ui tests tools`, `git diff --check -- core ui tests tools ACTION_ITEMS.md NATIVE_LIB_PLAN.md idea_item.md test_case.md waste_action_item.md`, and a live Macau project overlay snapshot were run for `v04.00.11`.

## Collaboration Rules

- Reply to the user in Korean unless they explicitly request another language.
- Use formal, respectful Korean honorifics when replying to the user.
- Keep repository documentation written in English unless the file is source data or user-visible Korean copy.
- Unless the user explicitly asks for detail, keep user-facing replies to one short Korean line focused on outcome only.
- Do not show code, long explanations, or file-by-file breakdowns unless the user explicitly asks for them.
- Implement requested changes directly when the request is clear.
- Preserve existing user changes. Do not revert unrelated dirty files.
- Do not commit, push, or publish unless the user explicitly asks.
- Use `rg` for search whenever possible.
- Use `apply_patch` for manual file edits.
- Keep edits scoped to the request and follow existing project patterns.

## Action Item Execution Rules

- Treat optimization and performance improvement as the top priority for action-item execution and implementation choice, as long as subtitle quality, verified behavior, and required user workflows do not regress.
- Treat each unchecked row in `ACTION_ITEMS.md` under **Active Work** as one countable executable item.
- When the owner asks how many action items remain, answer with the number of countable active items that can be executed sequentially in one pass.
- When the owner asks to run a number of items, such as "5개 수행해", execute the first N unchecked active items in order unless a blocker or owner-decision item is reached.
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

## Token Efficiency Rules

- Prefer `CODEMAP.md` over `File_structure.txt` when deciding where to read or edit code.
- Before widening code reads or refactors, actively ask whether the same result can be reached with a smaller contract, a narrower helper extraction, or a bridge boundary that keeps stable hot-path code out of the main orchestration surface.
- When token reduction matters over repeated chats, prefer structural reductions over reply-length tricks: keep Python/UI orchestration thin, move stable deterministic hot loops behind JSON-in or typed-value-in boundaries, and keep a tested Python fallback when promoting code into Swift, C++, or another external library.
- After the initial bootstrap in a chat, do not re-read unchanged bootstrap documents (`AGENTS.md`, `ACTION_ITEMS.md`, `File_structure.txt`, `CODEMAP.md`, latest `RELEASE_v*.md`, `README.md`) unless:
  - a new chat starts;
  - the user explicitly asks for a re-read; or
  - the file was edited during the current session and must be re-checked.
- Keep `File_structure.txt` shallow: root entries plus selected first-level entries for high-signal directories such as `core/`, `ui/`, `tests/`, and `tools/`.
- Do not maintain exhaustive recursive trees in handoff documents. Use runtime `rg`, `find`, and targeted file reads for detail instead.
- Keep `CODEMAP.md` responsibility-driven: entry points, hot modules, verification targets, and real-media fixtures only.
- For fresh-chat handoffs, prefer changed files, exact commands, validation results, and next actions over restating repository structure.
- Do not paste large JSON payloads, full crash reports, or long terminal logs into the chat unless the user explicitly asks for the full body. Prefer:
  - a short Korean summary in chat;
  - the exact local file path for the full artifact; and
  - only the minimum quoted lines needed to identify the root cause or current state.
- Default to strict token saving in chat: prefer a one-line completion summary unless the user explicitly asks for more detail.
- During long optimization/verification runs, keep user-facing progress to one short Korean line per batch, write full logs/artifacts to `output/manual_verification/latest/`, and keep resumable state in `.codex_work/overnight_state.md`.
- Store real-app verification artifacts under `output/manual_verification/latest/` by default. This includes compact reports, status snapshots, screenshots, and short notes for the most recent verification pass. If a task needs a permanent named archive too, keep `latest/` as the quick pointer and create the named sibling folder separately.
- Final completion reports should default to four compact items only unless the user asks for more detail:
  - root cause or purpose;
  - files changed;
  - verification run;
  - next risk or next action.

## Refactor Rules

- Refactoring is request-driven. Do it when the user explicitly asks.
- Preserve behavior unless the user asks for a behavioral change.
- Before deleting code, verify static references, dynamic imports, subprocess entry points, tests, and macOS paths.
- Remove unused variables or dead paths only after confirming they are not public compatibility hooks or subprocess entry points.
- Large files should be split by responsibility, not by arbitrary line count.

## Runtime And UI Rules

- Audio preset, VAD, preprocessing, Mode, and LLM selection must flow through shared services where possible.
- Keep cut-boundary planning centralized. Prefer `core/cut_boundary_native_plan.py` for placeholder/provisional/middle-segment row rules and `core/native/_native_cut_boundary.cpp` for native rollback/search kernels instead of re-spreading the same logic across UI helpers.
- Mode is user-facing as `Fast`, `Auto`, and `High`; old STT quality keys remain compatibility storage where needed.
- Direct user controls for STT1, STT2, subtitle LLM, roughcut LLM, and the audio model list must remain available. VAD policy is mode-owned on this branch unless a future user request explicitly restores manual VAD controls.
- LoRA or personalization learning must not start on the Editor screen. It should start only after the Home screen has been idle long enough, and user mouse or keyboard input should stop it quickly.
- Project save/load logic must use shared project I/O helpers so STT1/STT2, subtitle segments, timeline metadata, and model settings persist consistently.
- Folder queue processing must enqueue individual files for sequential processing. Folder selection must not silently become multiclip editing.
- iCloud and NAS are the only background-watch processing modes.
- PyQt persistent widgets must be detached before layouts are replaced. If a Qt C++ object may have been deleted, guard wrapper access and recreate the widget.

## Temporary Files

- Do not create root-level temporary files.
- `.codex_work/` is local Codex scratch memory only and must not be committed.
- Do not touch `dataset/video_preview_cache/` unless the user asks for cache cleanup.
- Runtime output belongs in ignored output/cache/project locations, not in the source tree.

## Verification Baseline

For code changes, choose verification proportional to risk. Common checks:

```bash
venv/bin/python -m pytest -q
venv/bin/python -m compileall -q main.py core ui tests
git diff --check -- .
```

For documentation-only changes, `git diff --check` is normally enough.
