<!--
Document-Version: 03.18.00
Phase: PHASE3
Last-Updated: 2026-05-05
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
- Current app version in code: `03.18.00`
- Current handoff document version: `03.18.00`
- Latest release checkpoint: `v03.18.00`
- Current phase: `PHASE3`
- Next planned phase: `PHASE4_iPad`
- Product priority: generate highly accurate subtitles on the first pass, even if processing takes longer.
- Shared pipeline rule: core subtitle algorithms must work across single-file, multiclip, folder queue, iCloud, and NAS workflows.
- Cross-platform rule: macOS and Windows must remain supported, including Korean paths, spaces, backslashes, subprocess handling, ffmpeg/ffprobe, faster-whisper workers, and PyQt6 runtime behavior.
- Queue state: `ACTION_ITEMS.md` is parked-only; no active non-iPad items remain after the GPU/QML, lightweight project, and LoRA voice-data release.

## Collaboration Rules

- Reply to the user in Korean unless they explicitly request another language.
- Use formal, respectful Korean honorific language when replying to the user.
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

- Audio preset, VAD, preprocessing, subtitle quality, and LLM selection must flow through shared services where possible.
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
python3 -m compileall -q main.py core ui tests
git diff --check -- .
```

For documentation-only changes, `git diff --check` is normally enough.
