<!--
Document-Version: 04.00.05-mac-native
Phase: MAC_NATIVE_APPSTORE_V4_0_5_RELEASED
Last-Updated: 2026-05-14
Updated-By: Codex
Purpose: Agent bootstrap and handoff rules only.
-->
# AGENTS.md - Agent Bootstrap Guide

This file is the first document an assistant should read when continuing work on AI Subtitle Studio. It should stay short, current, and operational. Historical release details belong in `RELEASE_v*.md`; task backlog belongs in `ACTION_ITEMS.md`; product overview belongs in `README.md`; the actual tree belongs in `File_structure.txt`.

## Bootstrap Contract

If this file is the only file uploaded into a new chat, the assistant must locate the project root and read the rest of the handoff set automatically.

Required discovery order:

1. Read `AGENTS.md`.
2. Find and read `ACTION_ITEMS.md`.
3. Find and read `File_structure.txt`.
4. Find the latest `RELEASE_v*.md` by version number and read only that release note first.
5. Read `README.md`.

Filename matching must be tolerant of case and spacing hints from the user:

- `agents.md` maps to `AGENTS.md`.
- `action_items.md` maps to `ACTION_ITEMS.md`.
- `File_Structure.txt` maps to `File_structure.txt`.
- `Release_Vxx.xx.xx.md` maps to the latest actual `RELEASE_v*.md`.
- `Read.me` maps to `README.md`.

Do not ask the user to upload the other four documents if they exist in the repository.

## Handoff File Roles

Keep these five files non-overlapping:

- `AGENTS.md`: assistant operating rules, bootstrap rules, release-handoff rules, and current continuation facts.
- `ACTION_ITEMS.md`: remaining work queue only, ordered by execution priority.
- `File_structure.txt`: actual filesystem tree only, with no review notes or speculative cleanup notes.
- `README.md`: product purpose, installation, usage direction, and concise current-state summary.
- `RELEASE_v*.md`: versioned release note for one release, based only on the immediately previous release.

## Release Handoff Rules

When the user asks to release, update the five handoff documents so a future chat can continue without old context.

Release workflow:

1. Determine the current app version from `core/runtime/config.py`.
2. Determine the latest existing `RELEASE_v*.md`.
3. Use only the immediately previous release note as historical reference.
4. Create or refresh the current release note without copying older cumulative history.
5. Refresh `AGENTS.md`, `ACTION_ITEMS.md`, `File_structure.txt`, and `README.md`.
6. Keep the five documents in English, except for unavoidable source data such as real filenames or Korean subtitle-rule tokens.
7. Remove stale release history, obsolete review notes, and duplicated summaries from the handoff files.
8. Do not update unrelated documents during release unless the user explicitly asks.

If the release changes the app version, update `core/runtime/config.py` as the source of truth. The handoff set is still the five documents listed above.

## Current Continuation Facts

- Project path: `/Users/u_mo_c/Downloads/ai_subtitle_studio`
- Real benchmark fixtures: `/Users/u_mo_c/Downloads/ai_subtitle_studio/test video` contains the canonical local video/SRT pair for 3-minute subtitle pipeline benchmarks. Use this folder before larger ad-hoc media when comparing STT order, LoRA/Deep/LLM gating, timing, and cut-boundary variants.
- Current app version in code: `04.00.05`
- Current handoff document version: `04.00.05-mac-native`
- Latest release checkpoint: `v04.00.05`
- Current phase: `MAC_NATIVE_APPSTORE_V4_0_5_RELEASED`
- Next planned phase: none.
- Product priority: generate highly accurate subtitles with the fewest necessary user settings, while keeping generation startup, cut-boundary scanning, playback, and editor-mode subtitle edits responsive.
- Shared pipeline rule: core subtitle algorithms must work across single-file, multiclip, folder queue, iCloud, and NAS workflows.
- Platform rule: this branch is macOS-only and Apple Silicon first. Do not add Windows/Linux fallback work unless the user explicitly asks to restart cross-platform development. However, most reusable business logic should be shaped as Apple-platform Swift core code that can later move to iPadOS with minimal changes.
- Release state: Fast, Auto, and High are now the single user-facing Mode controls. Fast runs LoRA-only subtitle post-processing, Auto runs LoRA + Deep, and High runs LoRA + Deep + chunked LLM. Legacy `balanced`, `normal`, `보통`, and `균형` settings map to Auto; legacy `fast` and `precise` settings are preserved as Fast and High when no explicit `subtitle_mode` exists.
- Completion state: subtitle generation, editor save, quality review, and cleanup paths clear foreground busy UI before deferred learning starts; editor-save truth/text LoRA work is queued for Home-idle processing.
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
- Runtime stability state: user, folder, custom-default, and project JSON writes use safe atomic replacement; settings load can recover from `.bak` backups after partial-write JSON errors. Project writes now default to the canonical ordered JSON writer so the top-level `video` header remains first for frame-based reloads; Swift project read/validation remains available and Swift project write is opt-in through `AI_SUBTITLE_STUDIO_SWIFT_PROJECT_WRITE`.
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
- App Store packaging state: macOS packaging scripts can build the `.app` payload, copy Swift WhisperKit and native helpers, sign locally, validate bundle layout, create/validate a local beta DMG, run double-click `.command` build/update flows for this Mac, prepare Developer ID notarization, build a signed App Store `.pkg`, and validate/upload that package when the user supplies Apple credentials.
- Packaging rule: do not rebuild DMG files during ordinary refactor or optimization work. Run DMG packaging only when the user explicitly asks for a release, beta package, installer, distribution build, or DMG validation.
- Benchmark state: macOS native benchmark tools report STT backend readiness, optional real-audio STT WER comparisons, and adopt/fallback decisions for WhisperKit, direct ClearVoice audio, and native cut-boundary routing.
- Swift migration state: `native/macos/AIStudioNative` is the first Swift-native core package. It now owns the subtitle segment model, SRT parser/formatter, project JSON validation/atomic write helpers, timeline waveform peak/downsample and minimap column engines, runtime ETA estimation, startup diagnostic shaping, cut-boundary cache planning, an opt-in subtitle quality batch scorer, adaptive common split planner, CLI bridge, packaged-app integration, and Python fallback hooks. New macOS-native work should prefer this package when behavior can match or exceed Python, and should keep core algorithms separated from macOS-only UI/process APIs so they can be reused by a future iPad app.
- Popup/UI state: QML context menus and message dialogs have compact Apple-style sizing, hover/press feedback, outside-click dismissal, and Korean-only global menu labels.
- STT ensemble state: parallel STT1/STT2 runs clone chunk directories per worker and clean them afterward so one worker cannot delete audio chunks still needed by the other.
- Refactor state: the longest subtitle/project/editor/runtime modules were split by responsibility into `core.audio.transcribe_worker_io`, `core.engine.subtitle_segment_filter`, `core.engine.subtitle_accuracy_utils`, `core.pipeline.cut_boundary_cache`, and `ui.editor.editor_segments_bulk_load` so future native migration work has smaller seams.
- Verification state: `v04.00.05` release verification passed with the full Python suite, Swift package tests, `compileall`, `git diff --check`, local beta DMG build/validation, and refreshed release handoff files. Full release verification details are in `RELEASE_v04.00.05.md`.
- Latest regression checkpoint: on 2026-05-14, `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q`, `venv/bin/python -m compileall -q main.py core ui tests`, `git diff --check -- .`, `swift test` in `native/macos/AIStudioNative`, and `packaging/macos/build_beta_dmg.sh` all passed for `v04.00.05`.

## Collaboration Rules

- Reply to the user in Korean unless they explicitly request another language.
- Use formal, respectful Korean honorifics when replying to the user.
- Keep repository documentation written in English unless the file is source data or user-visible Korean copy.
- Implement requested changes directly when the request is clear.
- Preserve existing user changes. Do not revert unrelated dirty files.
- Do not commit, push, or publish unless the user explicitly asks.
- Use `rg` for search whenever possible.
- Use `apply_patch` for manual file edits.
- Keep edits scoped to the request and follow existing project patterns.

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
