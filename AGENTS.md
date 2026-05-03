<!--
Document-Version: 03.12.00
Phase: PHASE2
Last-Updated: 2026-05-03
Updated-By: Codex with 대표님
Previous-Content: v03.10.00 release checkpoint
This-Update: v03.12.00 release checkpoint for PHASE2 cut-boundary pioneer/follower workflow, project persistence, restart reset, and STT hard-cut alignment
Codex-Handoff: v03.12.00 release committed/pushed to main. ACTION_ITEMS.md currently has no immediate `now` task; PHASE2-D PAGE3B remains deferred.
-->
# AGENTS.md — AI Subtitle Studio Agent Guide

## Read First
- `AGENTS.md`
- `ACTION_ITEMS.md`
- `check_list.md`
- `File_structure.txt`
- `RELEASE_v03.12.00.md`
- `RELEASE_v03.11.00.md`
- `RELEASE_v03.09.00.md`
- `RELEASE_v03.08.00.md`
- `RELEASE_v03.07.00.md`
- `RELEASE_v03.06.00.md`
- `RELEASE_v03.05.00.md`
- `RELEASE_v03.04.00.md`
- `RELEASE_v03.03.00.md`
- `RELEASE_v03.00.00.md`

## Current State
- Project path: `/Users/u_mo_c/Downloads/ai_subtitle_studio`
- App/doc version: `v03.12.00`
- `config.py APP_VERSION`: `03.12.00`
- Next code-change version: `v03.12.01`
- Phase: `PHASE2`
- Latest implemented groups:
  - `v03.01.33`: CP-03/CP-04 saved-state dot, `is_dirty` sync, top status rail
  - `v03.01.34`: CP-05~CP-07 export dialog save/preview/button alignment
  - `v03.01.35`: CP-08~CP-10 auto-home countdown, auto toggle screen retention, global canvas fit default
  - `v03.01.36`: CP-11 multiclip existing SRT offset/ordering fix
  - `v03.01.37`: PERF-01 media probe cache, parallel ffprobe, bounded workers, Qt pixmap cache tuning
  - `v03.02.00`: release checkpoint for PHASE2 CP-03~CP-11, roughcut v2, and PERF-01
  - `v03.02.01`: PHASE2-D PAGE3B roughcut LLM override settings, default prompt, config resolver, settings UI
  - `v03.02.02`: AI settings tabs, editor/roughcut LLM thread split, subtitle quality moved into AI settings
  - `v03.02.03`: optimizer thread exception logging, subtitle engine numeric setting parse guard
  - `v03.02.04`: timeline speaker labels reload current speaker settings before generation/render
  - `v03.02.05`: iCloud/NAS auto-processing labels use waiting/completed video/audio counts
  - `v03.02.06`: subtitle/timeline selection moves playhead; global canvas fit allows long timelines below default zoom
  - `v03.02.07`: timeline segment text colors distinguish `음성` and `무음`
  - `v03.02.08`: timeline segment lanes moved down near global canvas without changing canvas height
  - `v03.02.09`: timeline bottom padding removed and moved into top margin
  - `v03.02.10`: terminal log integrated into sidebar; bottom menu `사이드바` toggles sidebar
  - `v03.02.11`: subtitle editor yellow focus border aligned with timeline focus border
  - `v03.02.12`: completed subtitle generation status synced across status rail/terminal/queue table
  - `v03.02.13`: dirty-state save prompt based on actual subtitle segment signature
  - `v03.02.14`: sidebar terminal widget recreated safely after home layout rebuild
  - `v03.02.15`: editor realtime roughcut draft generation saves shared `roughcut_state`
  - `v03.02.16`: start button no longer flashes the brain emoji
  - `v03.02.17`: editor roughcut draft shows local A/B/C segments immediately, then LLM refines
  - `v03.02.18`: single pipeline guards deleted MainWindow UI updates from background threads
  - `v03.03.00`: release checkpoint for PHASE2 v03.02.x work
  - `v03.03.01`: refactor-only cleanup; legacy core/dataset JSON retained in `.codex_work/`, editor draft helper names clarified
  - `v03.04.00`: release checkpoint for v03.03.01 refactor-only cleanup
  - `v03.05.00`: STT1/STT2 ensemble, post-generation roughcut draft, VAD alignment, sidebar model/status table, queue UI cleanup, timeline/global canvas performance release
  - `v03.05.01`: RNNoise CLI install/use path, experimental Resemble Enhance/ClearVoice audio filters, TEN VAD option, sidebar queue order/color display
  - `v03.05.02`: Hugging Face token secure settings, HF_TOKEN env injection, Transformers dtype warning cleanup
  - `v03.05.03`: ClearVoice/TEN VAD runtime install alignment, dependency bounds, HF token env for audio enhancers
  - `v03.05.04`: STT ensemble word-level ROVER, low-confidence STT1 replacement, protected number/name guard
  - `v03.05.05`: FFMPEG/RNNoise/ClearVoice media command env duplicate fix
  - `v03.05.06`: Full restart clears editor text, timeline/global canvas segments, gaps, VAD, edit/drag state, video pending segments
  - `v03.05.07`: Resemble Enhance resolves isolated local CLI/`RESEMBLE_ENHANCE_BINARY` and passes explicit mps/cuda/cpu device
  - `v03.05.08`: Home navigation stops active backend/STT workers, invalidates roughcut draft callbacks, and unloads local Ollama LLM models
  - `v03.05.09`: Resemble Enhance isolated runner patches torchaudio Path load/save and Git LFS model fetch verified
  - `v03.05.10`: Subtitle timing prioritizes Whisper word timestamps and VAD islands over broad gap settings; LLM splits preserve word timing
  - `v03.06.00`: release checkpoint for audio enhancer/VAD candidates, HF token, word-level STT ensemble, restart/home cleanup, and word/VAD-first subtitle timing
  - `v03.06.01`: Sidebar pipeline table stays fully idle until a real stage log appears; saved/opened editors no longer mark STT pipeline done by state alone
  - `v03.06.02`: Timeline subtitle segment color calculation is shared by compact/expanded zoom rendering so quality/text-kind colors stay stable
  - `v03.06.03`: Playback playhead updates start the smooth timeline follow timer so subtitle segments scroll with playback
  - `v03.06.04`: Video controls add previous/next frame buttons around play; preview proxy is rebuilt as 720p, FPS-preserving cache
  - `v03.06.05`: Subtitle editor left/right arrow fast double-tap no longer jumps to line start/end
  - `v03.06.06`: Speaker change/learn menus open only from the centered speaker label hit target, not the full speaker lane segment
  - `v03.06.07`: Frame-step preview uses the active GPU video surface and skips thumbnail/context reloads inside the same clip
  - `v03.06.08`: Playback segment boundary sync moves the subtitle editor immediately unless the user is actively editing
  - `v03.06.09`: Timeline canvas uses the accelerated widget base where available and canvas click/edit paths repaint only dirty segment regions
  - `v03.06.10`: Shift+Enter soft line breaks normalize to saved newline text and restore as soft line breaks on reopen
  - `v03.06.11`: Video subtitle overlay uses the same smoothed playback display time as timeline/editor so it does not advance early
  - `v03.06.12`: Playback, playhead, scrub, segment edits, and project JSON metadata snap to the active video frame grid
  - `v03.06.13`: Timeline/global canvases use isolated native QWidget rendering to prevent video-frame bleed from OpenGL preview surfaces
  - `v03.06.14`: Silent gap right-click menu can generate a new subtitle from gap start to playhead or playhead to gap end
  - `v03.06.15`: Editor mode releases idle STT/Whisper workers and local LLM models to recover memory
  - `v03.06.16`: Video playback sync uses the probed frame-time map directly and live inline edits avoid full editor document rewrites
  - `v03.06.17`: Project JSON stores/restores subtitle frame numbers and timeline active shading follows stable segment line identity
  - `v03.06.18`: Editor-mode AI memory release is blocked while the generation backend or pipeline thread is active
  - `v03.06.19`: Project JSON declares frame numbers as the canonical timebase and derives seconds only for playback/export compatibility
  - `v03.06.20`: New subtitle placeholders remain saved as `새자막` until edited, then clear immediately when inline editing starts
  - `v03.06.21`: Timeline/global canvases, subtitle editor viewport, and video subtitle overlay use GPU/OpenGL-backed render surfaces when available
  - `v03.06.22`: Video playback skips redundant subtitle overlay updates and provider polling while playing to reduce stutter
  - `v03.07.00`: release checkpoint for frame-based editing, GPU rendering path, playback stability, and editor cleanup fixes
  - `v03.07.01`: macOS launch crash hotfix; aggressive Qt OpenGL and custom QOpenGLWidget surfaces are explicit opt-in
  - `v03.07.02`: Sidebar status rail shows `자막 생성 | 단계` during active subtitle generation instead of `에디터 | 단계`
  - `v03.07.03`: Video preview no longer encodes/stores 720p proxy cache; original source playback is displayed in a capped 720p preview rectangle
  - `v03.07.04`: Status rail and sidebar pipeline table share one canonical mode/stage parser; preprocessing shows `전처리` everywhere
  - `v03.07.05`: Large-file audio preprocessing uses single-pass ffmpeg for internal filters, ffmpeg filter threads, and validated cleaned-audio cache reuse
  - `v03.07.06`: FFMPEG preprocessing maps only the first audio stream and skips video/subtitle/data streams explicitly for large MP4 input
  - `v03.07.07`: Long FFMPEG preprocessing emits percent progress updates from FFmpeg progress output so the app no longer feels stalled
  - `v03.07.08`: Long no-VAD single-speaker preprocessing can skip full cleaned.wav and extract STT chunks directly from source media
  - `v03.07.09`: Subtitle editor no longer shows the top mode/filter/search toolbar above the table header
  - `v03.07.10`: Unified sidebar navigation buttons are shorter and the queue panel expands into the recovered space
  - `v03.08.00`: release checkpoint for v03.07.x crash stability, canonical status parsing, large-file FFMPEG preprocessing, direct STT chunks, editor toolbar cleanup, and sidebar queue expansion
  - `v03.08.01`: FFMPEG preprocessing progress logs print only newly increased 1-percent steps, without duplicate percent spam
  - `v03.08.02`: VAD postprocess shows model/load/analyze/cleanup stages plus TEN VAD percent progress and Silero heartbeat logs
  - `v03.08.03`: STT chunk progress logs include `STT1`/`STT2` labels so ensemble runs are readable when parallel logs interleave
  - `v03.08.04`: Whisper worker stderr warnings are prefixed with the same STT label to keep ensemble logs separated
  - `v03.08.05`: Confirmed STT chunk segments are previewed immediately on timeline canvases before LLM finalization
  - `v03.08.06`: Subtitle editor fixed table header row is no longer shown above the text editor
  - `v03.08.07`: Experimental macOS Core ML/WhisperKit STT backend can be selected with MLX fallback when the CLI is unavailable
  - `v03.08.08`: Ollama unload logs now distinguish home navigation cleanup from editor-mode memory cleanup
  - `v03.08.09`: Local Ollama subtitle splitting is capped to 2 workers by default to reduce repeated timeout fallback
  - `v03.08.10`: Save/complete flush pending subtitle segment queue and child Python workers suppress macOS MallocStackLogging noise
  - `v03.08.11`: Startup/quit cleanup terminates stale legacy preview-cache ffmpeg encoders without touching active render/preprocess jobs
  - `v03.08.12`: App shutdown synchronously unloads Ollama models and terminates Ollama server/runner plus app-owned heavy child processes
  - `v03.09.00`: release checkpoint for v03.08.x/v03.09.00 STT log separation, live STT preview, Core ML STT experiment, Ollama timeout/runtime cleanup, and save queue flush
  - `v03.09.01`: App launch auto-starts Ollama server when it is not already running
  - `v03.09.02`: Home navigation and app quit share synchronous cleanup for timers, threads, STT/LLM runtimes, and memory
  - `v03.09.03`: Playback keeps the playhead centered while the GPU-backed timeline canvas scrolls smoothly
  - `v03.09.04`: Timeline hides the manual slider and shows STT2 live preview below STT1 when ensemble STT is enabled
  - `v03.09.05`: STT ensemble runs STT1/STT2 on independent locked threads with isolated preview callbacks
  - `v03.09.06`: Playback first centers the playhead, then starts smooth GPU-backed timeline follow
  - `v03.09.07`: Video scene subtitle overlay loads saved export style before first playback display
  - `v03.09.08`: Post-generation roughcut draft scheduling runs before editor-mode model release and sidebar queue rows show completion status
  - `v03.09.09`: Timeline right-click menu for review-needed subtitles supports manual confirm/delete
  - `v03.09.10`: Initial home setup no longer runs idle backend cleanup before Ollama startup/model check
  - `v03.09.11`: AI settings tab exposes API/Hugging Face token fields plus LLM and Whisper model download controls
  - `v03.09.12`: Playback playhead flows naturally until it reaches center, then locks while the canvas scrolls
  - `v03.09.13`: ClearVoice audio enhancement emits elapsed heartbeat logs while the model runs
  - `v03.09.14`: Resemble Enhance audio enhancement emits elapsed heartbeat logs while the model runs
  - `v03.09.15`: Timeline separates final subtitles from STT1/STT2 candidate lanes and promotes a clicked candidate into the final subtitle segment
  - `v03.09.16`: STT1/STT2 candidate lanes are selection-only and show an `LLM` badge on the candidate chosen by LLM judging
  - `v03.09.17`: Clicking an STT1/STT2 candidate immediately updates the final subtitle while keeping selected/unselected candidate highlighting visible
  - `v03.09.18`: Voice activity lane displays non-overlapping speech/silence/noise/STT/VAD state segments and persists them with frame metadata
  - `v03.09.19`: Timeline wheel scrolling temporarily releases playback center-lock so horizontal manual scrolling does not jitter
  - `v03.09.20`: STT ensemble candidates are judged by LLM with neighboring context before final subtitle generation, with fallback recovery if filtering removes all candidates
  - `v03.09.21`: Manual STT candidate selection trims only the overlapping final subtitle time range so adjacent candidates remain selectable
  - `v03.09.22`: STT ensemble live previews show STT1/STT2 immediately while final subtitle segments wait for completed merge/LLM analysis
  - `v03.09.23`: STT1/STT2 candidate metadata and live preview lanes persist in project files for single and multiclip projects
  - `v03.09.24`: Long-video editor roughcut drafts skip oversized LLM prompts and create local roughcut segments immediately
  - `v03.09.25`: Unused Whisper/Core ML model entries are removed from STT selection lists, cached HF dropdown recovery, and install catalogs
  - `v03.09.26`: Voice activity and analysis lanes are display-only so clicks do not scrub, select, drag, or move the viewport
  - `v03.09.27`: STT1/STT2 preview candidates are optimized through subtitle rules/LLM in background before display
  - `v03.09.28`: Timeline canvas starts fit-to-view and project workspace no longer persists or restores zoom/scroll state
  - `v03.09.29`: Timeline `자막감지` lane displays STT source, LLM choice, review-needed state, and 100-to-0 score colors
  - `v03.09.30`: Final subtitle segments apply the Gap settings timing pass after LLM/VAD/speaker processing
  - `v03.09.31`: STT1/STT2 manual candidate selection is included in undo/redo snapshots with metadata and preview lanes
  - `v03.10.00`: release checkpoint for v03.09.x STT candidates, subtitle detection, timeline playback/scrolling, AI settings, roughcut, and runtime cleanup
  - `v03.11.00`: release checkpoint for v03.10.x editor stabilization, frame-step cleanup, and STT preview/editor UX fixes
  - `v03.11.16`: cut boundaries become absolute subtitle/STT split references and persist through project/multiclip state
  - `v03.11.17`: provisional/confirmed cut boundaries both persist in project state and snap STT preview/final subtitle segments
  - `v03.11.18`: full restart clears topicless middle segments, provisional lines, confirmed cut boundaries, and stored cut-boundary project state
  - `v03.11.19`: confirmed cut boundaries restart Whisper chunk extraction even on no-VAD fallback paths
  - `v03.12.00`: release checkpoint for cut-boundary pioneer/follower scanning, cut-boundary persistence/snap, restart reset, sidebar state polish, and Whisper hard-cut alignment
- Older version history belongs in the versioned `RELEASE_v*.md` files, not here.

## Communication
- Answer 대표님 in Korean polite speech (`존댓말`).
- Be concise, direct, and implementation-oriented.
- Keep working unless blocked by a real ambiguity.

## Priority Rules
1. Start from the first unfinished item in `ACTION_ITEMS.md`.
2. Current immediate task: none in `ACTION_ITEMS.md` (`now: null`).
3. Do not execute `PHASE3` / `iPad` items during “run all” requests.
4. Refactoring is request-triggered only. Run it only when 대표님 explicitly asks for refactoring.

## Non-Negotiable Rules
- Do not delete existing features.
- Do not revert user-made changes.
- Commit only when 대표님 explicitly asks.
- Do not touch `dataset/video_preview_cache/`.
- Do not leave these in repo root:
  - `create_all*`
  - `_backup*`
  - `STRUCTURE.txt`
  - `requirements.txt`
- Requirements files are only:
  - `requirements-mac.txt`
  - `requirements-windows.txt`
- `.codex_work/` is Codex-only local working memory for faster development and lower token use.
- Use `.codex_work/` to store long user action items, decomposed task files, chat/context notes, important project facts, file maps, test plans, source summaries, URL/open-source notes, and reusable local analysis.
- `ACTION_ITEMS.md` may point to `.codex_work/` files instead of repeating long content.
- `.codex_work/` may preserve useful prior working history across tasks, but it is not product source and must not be committed.
- Clean `.codex_work/` only when its saved context is obsolete or 대표님 asks.
- Do not create root-level temporary files.
- When rebuilding Qt layouts, detach persistent widgets before replacing or orphaning the old layout. Never reuse a PyQt wrapper after its C++ object may have been deleted; guard with `try/except RuntimeError` and recreate the widget if needed.
- Persistent widgets moved between refreshed panels, such as sidebar status/log widgets, must have a recreation helper and a regression test that calls the rebuild path more than once.
- Always consider Windows:
  - Korean paths
  - spaces in paths
  - backslashes
  - subprocess/ffmpeg/ffprobe
  - faster-whisper worker
  - PyQt6 DLL/plugin issues

## Version Rules
- Code behavior changes still require the patch version to advance and `config.py APP_VERSION` to match.
- Do not mass-update every 운영 문서 for each feature/bug fix. For routine code changes, update only the documents that are strictly needed for that change:
  - `ACTION_ITEMS.md` only when the action queue changes.
  - `check_list.md` only when 대표님 direct UX confirmation is needed.
  - the current release note file only when a `def`, `class`, helper, UI action, signal, or slot is removed, or when an important risk/compatibility note must not wait.
  - `AGENTS.md` only when operating rules, handoff facts, or current-state facts change.
  - `File_structure.txt` only when files are added, removed, moved, or their role meaningfully changes.
  - `README.md` only for public-facing usage/install changes that cannot wait for release.
- Batch nonessential updates to `AGENTS.md`, `ACTION_ITEMS.md`, `README.md`, `check_list.md`, `File_structure.txt`, and the new `RELEASE_v{new_release_version}.md` during the release workflow.
- Current next code-change version: `v03.12.01`.
- Document-only cleanup does not require app version bump.
- If deleting a function, class, public helper, UI action, signal, or slot:
  - record reason and impact in the current release note file.

## Refactor Request Rule
- Refactoring is not an `ACTION_ITEMS.md` queue item and must not run during general "run all" requests.
- Start refactoring only when 대표님 explicitly requests refactoring.
- Before refactoring, identify the target scope and preserve all existing user-visible behavior.
- When files appear unused, verify them carefully with static references, dynamic/subprocess entry points, tests, and Windows-specific paths before acting.
- For ordinary or partial refactoring, keep legacy compatibility paths unless 대표님 explicitly approves removal.
- When 대표님 explicitly requests `전체 리팩토링` or project-wide refactoring, unused-code cleanup is authorized after verification:
  - Back up every unused file into `.codex_work/refactor_backup_{YYYY-MM-DD}/files/` with its relative path preserved, then delete it from the project tree.
  - Back up every removed unused `def`, `class`, helper, UI action, signal, or slot into `.codex_work/refactor_backup_{YYYY-MM-DD}/removed_symbols.md` or a similarly named backup file, including source path, symbol name, reason, and the original code block, then delete it from the project source.
  - Do not delete anything that still has static references, dynamic imports, subprocess entry usage, test coverage dependency, Windows-specific usage, or unclear compatibility value.
  - If removal safety is uncertain, keep the item in the project and record the uncertainty in `.codex_work/`.
- If removing any `def`, `class`, helper, UI action, signal, or slot, document the reason and impact range in the current release note file.
- After refactoring, run focused tests for touched modules plus the standard verification baseline when the blast radius is broad.

## Release Trigger Rules
- When 대표님 says `릴리즈하자`, `릴리즈 하자`, or equivalent release intent, run the full release workflow.
- Release version format is `AA.BB.CC`; `BB` is the release version.
- A release increments the middle component automatically and resets the patch component to `00`.
  - Example: `01.00.00` -> `01.01.00`
  - Current example: `03.02.00` -> `03.03.00`
- During release, update:
  - `config.py APP_VERSION`
  - `File_structure.txt`
  - `ACTION_ITEMS.md`
  - `AGENTS.md`
  - `check_list.md`
  - `README.md`
  - a new release note file named `RELEASE_v{new_release_version}.md`
- When the middle release version increases, do not keep appending the release summary only to the previous release note. Create a fresh release note file for the new release version.
  - Example: releasing `03.03.00` creates `RELEASE_v03.03.00.md`.
  - Keep older release note files as history unless 대표님 explicitly asks to consolidate or remove them.
- Add README content for the new release version while keeping the README rule: latest release summary only plus link to the new release note file.
- Update `File_structure.txt` so the latest release note entry points to the new `RELEASE_v{new_release_version}.md`.
- Update `requirements-mac.txt` and/or `requirements-windows.txt` only if dependency changes actually require it.
- Run the standard verification commands before committing.
- For release only, the usual "commit only when explicitly requested" rule is satisfied by the release trigger:
  - commit release changes to `main`
  - sync/push `main` to GitHub so GitHub reflects the release immediately
- After release, write a compact handoff prompt for a fresh chat in the language/format easiest for Codex to understand. It must include:
  - project path
  - current release version and `APP_VERSION`
  - next code-change version
  - phase
  - required read-first files
  - current action queue summary
  - critical rules and verification baseline

## Document Rules
- `ACTION_ITEMS.md`: only unfinished implementation tasks, bugs, and feature work.
- Completed `ACTION_ITEMS.md` entries are removed.
- User-confirmation items stay in `check_list.md`.
- `check_list.md`: Korean only, short UX scenario + `PASS` criterion only.
- `check_list.md`: no implementation notes, no long policy text, no internal code details.
- `File_structure.txt`: structure, file roles, and file versions only.
- `File_structure.txt`: keep at least two tabs before each `←` file-role marker for readability.
- `File_structure.txt`: write new or updated file role descriptions in English from now on.
- `RELEASE_v*.md`: versioned release notes, old version history, removal reasons, implementation summaries.
- `README.md`: keep release-note link and show only the latest release summary.
- Do not put release history into `AGENTS.md`.
- Long user action items should be normalized into `.codex_work/` notes before implementation when that saves tokens.

## Current Action Queue
- `ACTION_ITEMS.md now`: `null`
- Deferred item: `PHASE2-D-PAGE3B`
- Do not start deferred/parking items unless 대표님 asks to continue with them.

## Recent Verification Baseline
Last known passing checks:
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s tests`
  - exit code 0
- module-by-module unittest sweep
  - all `tests/test_*.py` modules passed
- unittest discovery count
  - repository unittest discovery passed
- Python AST scan
  - 224 files passed
- Offscreen UI smoke:
  - `MainWindow`
  - `SettingsDialog`
  - `AdvancedSettingsDialog`
  - `ExportDialog`
  - `RoughcutWidget`
- `git diff --check -- . ':(exclude)dataset/video_preview_cache'`
- root forbidden-file scan

## Standard Verification Commands
```bash
QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s tests

python3 - <<'PY'
import ast
from pathlib import Path
root = Path(".")
exclude_parts = {".git", "venv", ".codex_work", "__pycache__"}
exclude_prefix = Path("dataset/video_preview_cache")
files = []
for path in root.rglob("*.py"):
    if any(part in exclude_parts for part in path.parts):
        continue
    try:
        path.relative_to(exclude_prefix)
        continue
    except ValueError:
        pass
    files.append(path)
for path in files:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
print(f"AST OK: {len(files)} files")
PY

QT_QPA_PLATFORM=offscreen venv/bin/python - <<'PY'
import sys
from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)
from ui.main.main_window import MainWindow
from ui.settings.settings_ai import SettingsDialog
from ui.settings.settings_advanced import AdvancedSettingsDialog
from ui.dialogs.export_dialog import ExportDialog
from ui.roughcut.roughcut_widget import RoughcutWidget
widgets = [
    MainWindow(),
    SettingsDialog({}),
    AdvancedSettingsDialog({}),
    ExportDialog([{"start": 0.0, "end": 1.0, "text": "test"}], "sample.mp4"),
    RoughcutWidget(),
]
for widget in widgets:
    widget.close()
print("UI smoke OK")
PY

git diff --check -- . ':(exclude)dataset/video_preview_cache'
find . -maxdepth 1 \( -name 'create_all*' -o -name '_backup*' -o -name 'STRUCTURE.txt' -o -name 'requirements.txt' \) -print
```

## Worktree Notes
- The worktree is expected to be clean after committed/pushed release checkpoints, except local-only documents and user/generated cache files that are intentionally not part of GitHub.
- `dataset/video_preview_cache/` is an existing untracked cache and must stay untouched.
- Do not commit unless 대표님 asks.

## Handoff Prompt
```text
너는 Codex고, 존댓말로 답해라.

프로젝트 위치:
/Users/u_mo_c/Downloads/ai_subtitle_studio

반드시 먼저 참고할 파일:
- AGENTS.md
- ACTION_ITEMS.md
- check_list.md
- File_structure.txt
- RELEASE_v03.12.00.md
- RELEASE_v03.11.00.md
- RELEASE_v03.09.00.md
- RELEASE_v03.08.00.md
- RELEASE_v03.07.00.md
- RELEASE_v03.06.00.md
- RELEASE_v03.05.00.md

현재 기준:
- 현재 앱/문서 버전: v03.12.00
- config.py APP_VERSION: 03.12.00
- 다음 코드 수정 버전: v03.12.01
- 현재 phase: PHASE2
- 다음 우선순위: ACTION_ITEMS.md의 `now` 항목 확인. 현재는 `now: null`, deferred에 `PHASE2-D-PAGE3B`

작업 원칙:
- 기존 기능 삭제 금지
- 완료한 ACTION_ITEMS.md 항목은 삭제
- 대표님 직접 확인 항목은 check_list.md에 유지
- 코드 동작 수정 시 패치 버전과 config.py APP_VERSION은 맞추되, 운영 문서 전체 갱신은 하지 말고 꼭 필요한 문서만 갱신
- 비필수 문서 동기화는 릴리즈 시 AGENTS/ACTION_ITEMS/README/check_list/File_structure/새 RELEASE_v{릴리즈버전}.md에 일괄 반영
- 삭제한 def/class/helper/UI action/signal/slot은 현재 RELEASE_v*.md에 사유와 영향 범위 기록
- Windows 환경을 항상 고려
- dataset/video_preview_cache/는 건드리지 않기
- 루트에 create_all, _backup, STRUCTURE.txt, requirements.txt 남기지 않기
- requirements는 requirements-mac.txt / requirements-windows.txt만 운영
- 커밋은 대표님이 명시적으로 요청할 때만 진행
- PHASE3 / iPad 항목은 “전체 실행” 요청에서도 제외
- 리팩토링은 ACTION_ITEMS.md 항목이 아니며, 대표님이 리팩토링을 명시 요청했을 때만 진행

이제 ACTION_ITEMS.md를 확인하고 다음 미완료 항목부터 진행해줘.
```
