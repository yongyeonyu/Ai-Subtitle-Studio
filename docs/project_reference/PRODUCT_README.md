<div align="center">

# AI Subtitle Studio

Accuracy-first desktop subtitle production for long-form video, rough cuts, speaker-aware editing, and repeatable subtitle workflows.

[![App Version](https://img.shields.io/badge/app-04.01.02-0A84FF?style=for-the-badge)](#)
[![Release](https://img.shields.io/badge/release-v04.01.02-30D158?style=for-the-badge)](../release_notes/RELEASE_v04.01.02.md)
[![Python](https://img.shields.io/badge/python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](#)
[![PyQt6](https://img.shields.io/badge/ui-PyQt6-41CD52?style=for-the-badge)](#)
[![Platform](https://img.shields.io/badge/platform-macOS%20Apple%20Silicon-555?style=for-the-badge)](#)

</div>

## Purpose

AI Subtitle Studio is built for one primary outcome: produce highly accurate subtitles on the first pass, even when that takes longer than a fast draft. The goal is to reduce manual correction time by combining STT, audio preprocessing, VAD, cut-boundary alignment, LLM cleanup, subtitle timing rules, LoRA personalization, and project-aware editing in one desktop workflow.

Current development stays on the existing Python/PyQt6 source app. Active work focuses on accuracy-first subtitle generation, editor/timeline stability, project save/reopen safety, and real-app verification on macOS Apple Silicon. Native `.swift` / `.cpp` assets and packaging scripts may still be used for bounded acceleration or packaging support, but broad native migration is not the default roadmap unless the owner explicitly reopens it.

The macOS packaging scripts under `packaging/macos/` still support local `.app` validation, Swift native helper builds, local updater flows, DMG creation, notarization prep, and App Store packaging. Treat those as opt-in release tooling rather than the default daily development path.

## Core Workflows

- Single-file subtitle generation and editing.
- Folder queue processing, where selected files are listed and processed individually in sequence.
- Multiclip editing when explicitly selected from multiclip flows.
- iCloud and NAS background processing.
- Fast/Auto/High Mode policy shared across single-file, multiclip, folder queue, iCloud, and NAS workflows.
- `core/mode_manager.py` now owns the single user-facing Fast/Auto/High/STT abstraction, while per-mode persistence keeps only user-selected STT1/STT2 and subtitle/roughcut LLM model identities.
- Tiniping benchmark-locked mode defaults now pin STT1/STT2, audio filter, VAD, LoRA bucket, Deep selector, and timing-anchor behavior from the 티니핑 0~3분 sweep plus the later long-window validation runs; High now keeps a 180-second rolling STT window with 8-second overlap and 4-second hysteresis.
- STT model menus now show `[Fast]`, `[Auto]`, and `[High]` tags on the benchmark-winning STT1/STT2 model combinations.
- Subtitle tool stack policy: Fast = LoRA, Auto = LoRA + Deep Learning, High = LoRA + Deep Learning + LLM, STT Mode = VAD + human input + LoRA/Deep/rules.
- STT Mode portable project state: `stt_mode_state` keeps VAD work segments, raw dictation, rolling windows, and final subtitle mirrors separate from the normal vector subtitle canvas.
- STT Mode iPad compatibility scope is intentionally limited to project state and STT LoRA/runtime policy bundles; this repository does not implement an iPad app.
- Stable editor text, video, and timeline render frames default to Qt Widgets/QPainter 2D; OpenGL and Qt Quick/SceneGraph UI layers remain explicit diagnostics only.
- Subtitle generation completion is driven by backend-finalized, saveable subtitle segments rather than STT progress alone, so completion autosave waits and retries instead of saving an empty timeline.
- When subtitle generation completes, the Home sidebar progress card appends the final subtitle self-review score next to elapsed versus expected time so queue review can see a quick quality signal without reopening the editor.
- Editor exit flows ask to save unsaved changes before fast runtime/model cleanup starts.
- Fast editor-mode subtitle movement using line-map caches, dirty-rectangle timeline updates, visible-window video context refreshes, and non-jittery active-segment scrolling.
- Native/OpenCV cut-boundary verification, FFmpeg scene prepass, direct FFmpeg audio extraction, and benchmark-profile backend routing for long media.
- Korean Whisper KomixV2 STT candidates, including alias, Hugging Face original, and MLX variants, are available as clearly labeled STT2 choices.
- Swift WhisperKit persistent STT routes through the Python transcription pipeline as the default macOS STT1 backend; MLX and whisper.cpp remain fallback/native comparison paths.
- The first Swift-native core package now owns the lossless subtitle segment model plus SRT parsing/formatting, with Python kept as a fallback during migration.
- Project JSON I/O now keeps a canonical ordered on-disk layout with the `video` header first for frame/FPS-based reloads; Swift-native validation/read support remains available, while Swift project write is opt-in until it can preserve that ordering contract.
- Timeline waveform peak/downsample generation now has a Swift-native bridge for packaged macOS builds, with NumPy retained as the development fallback.
- Timeline minimap waveform column generation now has a Swift-native bridge so packaged macOS builds avoid Python loops when rebuilding zoom/resize paint caches.
- Subtitle quality scoring now has an adaptive Swift-native batch scorer for large macOS batches, while small edits keep the lower-overhead Python path.
- Common subtitle split/clamp planning now has a Swift-native adaptive planner for large packaged macOS batches, while Python preserves existing row metadata and assembly.
- Production macOS native acceleration is intentionally conservative: STT uses WhisperKit/Core ML/MLX, VAD alignment uses C++ overlap math, LLM macro grouping uses C++, and Swift LoRA/Deep/LLM policy helpers stay behind an explicit experimental gate until benchmarks prove both speed and LoRA ranking parity.
- Word timestamps default to off for fast STT passes, then re-run selectively on low-score, editor-selected, precision-review, or VAD-risk spans.
- ClearVoice can use a native FFmpeg single-pass path instead of waiting on the slower deep-learning enhancer when the quality-safe preset allows it.
- OpenAI Codex ChatGPT CLI can be selected as a subscription-backed LLM provider without requiring an API key or Ollama model preflight.
- Compact popup/menu surfaces use outside-click dismissal, hover/press feedback, and Korean-only bottom/global menu labels.
- Ten-step engine dashboard: cut boundary, preprocessing, audio filter, STT1, STT2, VAD, subtitle LLM, roughcut LLM, LoRA, and deep learning.
- Runtime sidebar display of the current file's automatic audio-filter and VAD choices, backed by chunk-profile memory, preview self-score guards, and conservative switch confirmation so adaptive audio routing can generalize beyond one benchmark video.
- Runtime ETA prediction now uses per-variant history with media/FPS/cache features and recent-run weighting, and the active queue row keeps elapsed-versus-expected time updated even before the full backend pipeline clock is ready.
- Fast/Auto/High now lock benchmarked VAD defaults instead of exposing a separate VAD settings menu; automatic audio preset detection can still retune only the audio frontend stack.
- Correction-dictionary cleanup now has a SQLite-backed indexed runtime path while keeping the JSON dictionary as the editable source of truth.
- The bottom menu now exposes a dedicated correction-dictionary editor so stored replacements can be searched, added, edited, deleted, and kept alphabetized without leaving the app.
- Speaker count is now automatic at runtime: local spans can collapse to one speaker or expand to two or three speakers, and learned `spk1`/`spk2`/`spk3` voice profiles are preferred when diarization confidence supports them.
- Manual `<<` / `>>` cut-boundary hits are persisted as confirmed project cut boundaries for later subtitle magnet alignment.
- Playhead cut-boundary magnet behavior is now an explicit right-click option so normal scrubbing can stay fast while precise automatic cut snapping remains available on demand.
- Live STT previews now stay in timeline/STT preview lanes only; the editor text pane and playback subtitle overlay remain reserved for committed subtitle segments.
- Cut-boundary helper rows can still be saved into project metadata for verification and timing work, but follower-checked provisional lines and terminal helper boundaries are hidden from the normal editor UI after confirmation.
- Roughcut Codex CLI calls now use wider context and longer timeouts, then fall back to local-rule draft generation if the Codex CLI times out.
- Post-generation roughcut save now persists only the roughcut draft/state first, then explicitly returns the editor to an interactive state before heavier follow-up cleanup continues.
- The lower global timeline canvas can now save the current subtitles and rerun only the roughcut LLM from a right-click action, then re-sort the generated middle rows before applying them.
- Process-level project JSON caching plus safe atomic project and settings writes.
- Export-dialog settings, diarization caches, VAD strict metadata, and editor teardown now use typed/logged cleanup paths instead of broad silent exception swallowing, so save/export/cleanup failures stay diagnosable.
- Project save/load uses frame-quantized subtitle/STT timing, external SRT assets, and project-path-aware hydration so STT1/STT2 and final subtitle lanes reload without tail segments beyond the real video duration.
- STT1/STT2 candidate comparison with persistent project metadata.
- Cut-boundary assisted subtitle timing.
- Accuracy-first audio routing with clip or chunk-level preprocessing decisions.
- Roughcut draft generation from subtitle and scene structure.
- Subtitle video output after subtitle generation.
- Text, voice, multimodal, STT1 adapter, and settings LoRA personalization data management, including idle-only background learning, Full learning controls, detailed learning logs, and automatic gap/bundle/context policies.
- STT LoRA/runtime bundle export writes policy-json bundles with protected terms, VAD boundary policy, dictation resegmentation policy, and manifest/checksum metadata for future desktop/iPad reuse.

All core algorithms should be shared across single-file, multiclip, folder queue, iCloud, and NAS modes.

## Quick Start

macOS:

```bash
python3.11 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-mac.txt
python main.py
```

Required runtime tools:

- Python 3.11
- ffmpeg and ffprobe
- Git
- Sufficient disk space for models, temporary audio, project files, and render output

Optional tools:

- Ollama for local LLM workflows.
- Hugging Face token for some model downloads.
- External LLM API keys when enabled in settings.
- Xcode command line tools or Xcode for Swift native workers and App Store packaging.

Local macOS beta package:

```bash
packaging/macos/build_beta_dmg.sh
```

Build the DMG only when explicitly requested. Even release work should stop at
Swift/Python tests plus app bundle checks unless the user specifically asks for
DMG packaging or validation.

Local update test:

```bash
TARGET_APP="$HOME/Applications/AI Subtitle Studio.app" \
  packaging/macos/install_or_update_app.sh
```

The same flows are available as double-click scripts in `packaging/macos/`.

## One-command QA Runner

The repository now has one official automation entrypoint for repeatable UX verification:

```bash
./venv/bin/python tools/qa_suite_runner.py quick
./venv/bin/python tools/qa_suite_runner.py major
./venv/bin/python tools/qa_suite_runner.py full
```

Profiles:

- `quick`: app bootstrap plus minimal editor smoke.
- `major`: Macau UX regression set.
- `full`: `major` plus X5 3-minute High rolling-window verification.

Artifacts are written under `output/manual_verification/latest/qa_suite_<profile>_*` and include:

- `suite_manifest.json`
- `suite_result.json`
- `suite_result.md`

Current verified baseline:

- `quick`: `qa_suite_quick_20260626_022343`
- `major`: `qa_suite_major_20260521_121601`
- `full`: `qa_suite_full_standard_x5_restored_20260626_0901`

Operational rules:

- `major` and `full` assume the current-code macOS app bundle is available at `dist/macos/AI Subtitle Studio.app`.
- If automation commands or editor automation behavior changed, regenerate the bundle first:

```bash
./packaging/macos/build_app_bundle.sh
```

- `editor_compact_macau` is fixture-adaptive: it resolves playhead and diamond boundaries from live editor status instead of assuming a fixed timestamp.
- `full` parses the final JSON line from `verify_full_media_pipeline.py`, so progress logs in stdout do not invalidate the suite result.
- `full_media` verification fails spoken/non-trivial slices that return zero raw or final subtitles; a fast empty output is not a valid pass.
- The runner treats the bundled Python entrypoint at `dist/macos/AI Subtitle Studio.app/Contents/Resources/app/main.py` as an app process when restarting stale bundles.
- Editor/timeline rendering ownership, QML/SceneGraph opt-in gates, and qwidget-2d paint ordering can be checked without launching the app:

```bash
./venv/bin/python tools/audit_editor_rendering_ownership.py --json
```

- Help chapter QA ownership is tracked in `ui/help/help_content.py::HELP_QA_COVERAGE` and guarded by `tests.test_help_dialog`.

## Project Data

Local runtime data is intentionally not treated as source code.

Typical local data:

- `output/`
- `projects/`
- `projects/프로젝트백업/`
- `dataset/user_settings.json`
- `dataset/folder_settings.json`
- `dataset/video_preview_cache/`
- `dataset/lora_personalization/`

Do not commit private media, generated output, API keys, NAS paths, iCloud paths, or user project data.

Project JSON numbered backups are stored in `projects/프로젝트백업/` next to the active project file. Legacy numbered backups in the project root are moved into that folder during the next save.

## Documentation Map

Use the documents below as the current navigation set for this repository:

| File | Role |
| --- | --- |
| `AGENTS.md` | Root agent bootstrap rules, role split, and guarded working rules. |
| `docs/planning_queue/ACTION_ITEMS.md` | Single source of truth for the active execution queue and hard rules. |
| `docs/README.md` | Documentation index and read order. |
| `docs/PROJECT_STATE.md` | Current product direction, constraints, and verified scope. |
| `docs/HANDOFF.md` | Latest continuation snapshot, open risks, and next step. |
| `docs/project_reference/PRODUCT_README.md` | Setup, product summary, and high-level operational guidance. |
| `docs/release_notes/RELEASE_v*.md` | Release checkpoints kept for recent continuity only. |
| `docs/quality_validation/test_case.md` | Validation expectations and fixture guidance. |
| `docs/quality_validation/test_result.md` | Latest recorded validation outcomes. |
| `docs/workflow_operations/anti_agents.md` | Antigravity and `잼민이` delegation rules. |
| `docs/workflow_operations/cooperation.md` | Cross-project Codex x Antigravity cooperation contract and prompt templates. |
| `docs/planning_queue/idea.md` | Shared scratchpad for ideas that still need `덱스` review before execution. |

Recommended read order for a fresh continuation:

1. `AGENTS.md`
2. `docs/planning_queue/ACTION_ITEMS.md`
3. `docs/README.md`
4. `docs/PROJECT_STATE.md`
5. `docs/HANDOFF.md`
6. Relevant release note, validation doc, or support doc for the exact task

## Current State

| Item | Value |
| --- | --- |
| App version in code | `04.01.02` |
| Latest release checkpoint | `v04.01.02` |
| Handoff document version | `04.01.02-source-app` |
| Active phase | `SOURCE_APP_CONTINUATION_V4_1_0` |
| Next planned phase | None |
| Product priority | Accuracy before speed |
| Supported target platforms | macOS, Apple Silicon first |

## Verification

Common development checks:

```bash
venv/bin/python -m pytest -q
venv/bin/python -m compileall -q main.py core ui tests
git diff --check -- .
```

For UI smoke testing without showing a window:

```bash
QT_QPA_PLATFORM=offscreen venv/bin/python - <<'PY'
import sys
from PyQt6.QtWidgets import QApplication
from ui.main.main_window import MainWindow

app = QApplication(sys.argv)
win = MainWindow()
print("MainWindow OK")
PY
```

## Release Notes

The current release checkpoint is [`RELEASE_v04.01.02.md`](../release_notes/RELEASE_v04.01.02.md). The repository keeps only the most recent release notes needed for handoff continuity, and the five handoff documents should summarize only the current state plus the immediately previous release relationship.

## Security

Never commit:

- API keys
- `.env` secrets
- private media
- private project files
- NAS paths
- personal iCloud paths
- generated subtitle/render output

If a secret is committed, remove it from the provider side and rotate it. Removing it from the latest file is not enough.
