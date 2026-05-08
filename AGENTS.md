<!--
Document-Version: 03.25.00
Phase: NATIVE_PERFORMANCE_UI_RELEASED
Last-Updated: 2026-05-09
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
- Current app version in code: `03.25.00`
- Current handoff document version: `03.25.00`
- Latest release checkpoint: `v03.25.00`
- Current phase: `NATIVE_PERFORMANCE_UI_RELEASED`
- Next planned phase: none.
- Product priority: generate highly accurate subtitles with the fewest necessary user settings, while keeping generation startup, cut-boundary scanning, playback, and editor-mode subtitle edits responsive.
- Shared pipeline rule: core subtitle algorithms must work across single-file, multiclip, folder queue, iCloud, and NAS workflows.
- Cross-platform rule: macOS and Windows must remain supported, including Korean paths, spaces, backslashes, subprocess handling, ffmpeg/ffprobe, faster-whisper workers, and PyQt6 runtime behavior.
- Release state: Fast, Auto, and High are now the single user-facing Mode controls. Fast runs LoRA-only subtitle post-processing, Auto runs LoRA + Deep, and High runs LoRA + Deep + chunked LLM. Legacy `balanced`, `normal`, `보통`, and `균형` settings map to Auto; legacy `fast` and `precise` settings are preserved as Fast and High when no explicit `subtitle_mode` exists.
- Completion state: subtitle generation, editor save, quality review, and cleanup paths clear foreground busy UI before deferred learning starts; editor-save truth/text LoRA work is queued for Home-idle processing.
- Editor layout state: the editor text pane, video preview, and timeline are mounted inside stable render frames so Start/status changes do not resize the major editor surfaces.
- Fast quality state: Fast mode stays lightweight but selectively rechecks low-score STT1 spans with the secondary STT model when configured, preserving minimum quality without rerunning the full High stack.
- Playback state: post-generation quality review, roughcut draft work, prefetch, cleanup, and model release are deferred or throttled while video playback is active.
- Runtime stability state: user, folder, custom-default, and project JSON writes use safe atomic replacement; settings load can recover from `.bak` backups after partial-write JSON errors.
- Dashboard runtime state: automatic audio-filter and VAD choices selected for the current file are surfaced in the sidebar pipeline dashboard with an auto marker and tooltip context.
- GPU state: GPU rendering can be selected by frame or for the whole editor through settings while OpenGL widgets and global Qt OpenGL remain conservative opt-ins; the timeline playhead overlay currently stays QWidget-backed to avoid QQuickWidget compositing hiding the painter canvas.
- Idle learning state: automatic LoRA/personalization learning starts only after Home has been idle for five minutes, ramps from Lite to Heavy, and mouse/key input requests a quick stop. The app indicator blinks blue while learning is active.
- Refactor state: `core.engine.subtitle_macro_chunks` owns 10-15 subtitle LLM macro chunk grouping and execution; `subtitle_engine.py` keeps orchestration and final timing/gap passes.
- Dashboard state: the sidebar engine dashboard shows ten stages: cut boundary, preprocessing, audio filter, STT1, STT2, VAD, subtitle LLM, roughcut LLM, LoRA, and deep learning.
- Editor performance state: subtitle line edits update cached line maps and the affected timeline dirty rectangle instead of rebuilding the full segment lookup; playback/editor sync respects recent manual scrolling and avoids recentering already visible active segments.
- Runtime scheduling state: cut-boundary pioneer/follower workers use topology-aware CPU planning, OpenCV thread caps, progress throttling, optional FFmpeg scene prepass, optional C++ native helper kernels, and optical-flow follower verification for candidate-only rollback checks.
- Backend routing state: STT, VAD, cut-boundary, audio extraction, LLM, and editor rendering paths now route through auto/native/fast/legacy policy helpers, with optional benchmark profile materialization stored outside Git.
- Audio/video IO state: long-media audio extraction can use direct FFmpeg chunk routing and fused filter graphs when quality-safe; editor playback reuses 720p preview proxies and cut-boundary scanning can reuse existing proxies to avoid repeated 4K decode.
- STT model state: Korean KomixV2 STT candidates include alias, Hugging Face original, and MLX variants with distinct sidebar labels; Transformers aliases normalize to `seastar105/whisper-medium-komixv2`.
- Popup/UI state: QML context menus and message dialogs have compact Apple-style sizing, hover/press feedback, outside-click dismissal, and Korean-only global menu labels.
- STT ensemble state: parallel STT1/STT2 runs clone chunk directories per worker and clean them afterward so one worker cannot delete audio chunks still needed by the other.
- Verification state: full test suite and static checks passed for this release: `1222 passed, 1 warning, 5 subtests passed`.

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
- Before deleting code, verify static references, dynamic imports, subprocess entry points, tests, macOS paths, and Windows paths.
- Remove unused variables or dead paths only after confirming they are not public compatibility hooks or subprocess entry points.
- Large files should be split by responsibility, not by arbitrary line count.

## Runtime And UI Rules

- Audio preset, VAD, preprocessing, Mode, and LLM selection must flow through shared services where possible.
- Mode is user-facing as `Fast`, `Auto`, and `High`; old STT quality keys remain compatibility storage where needed.
- Direct user controls for STT1, STT2, subtitle LLM, roughcut LLM, audio model list, and VAD model list must remain available.
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
