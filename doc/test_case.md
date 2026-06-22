# QA Test Cases

This document lists current QA entrypoints and fixture rules. It is not a full session log.

## Rules

- Subtitle quality is more important than speed.
- Do not lower model quality, skip STT2, skip LLM, or loosen timing gates as a default optimization.
- Tinyping long-flow is manual-only unless the owner explicitly asks.
- Benchmark artifacts are diagnostic until accepted-target comparison and quote-back fields are reviewed.
- Docs-only work does not require QA runner execution, but it still requires document path and diff checks.

## Fixtures

- Macau quick/smoke: `/Users/u_mo_c/Downloads/마카오테스트`
- X5 accuracy: `/Users/u_mo_c/Downloads/ai_subtitle_studio/test video/X5_시승기_후반.MP4` plus sibling `.srt`
- Tinyping long-flow: `/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.MP4`
- Artifact root: `output/manual_verification/latest/`

## Official QA Runner

```bash
./venv/bin/python tools/qa_suite_runner.py quick
./venv/bin/python tools/qa_suite_runner.py major
./venv/bin/python tools/qa_suite_runner.py full
```

Use `quick` for smoke confidence, `major` for broader app-command and fixture coverage, and `full` for release-level verification.

## Focused Test Bundles

Docs and reference maps:

```bash
./venv/bin/python -m pytest -q tests/test_subtitle_generation_domain_map.py
find doc -maxdepth 4 -type f | sort
for f in doc/idea.md doc/DECISIONS/server_mode_benchmarking.md doc/reference/CODEMAP.md doc/reference/File_structure.txt; do test ! -e "$f" || exit 1; done
```

Runtime error popup:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_runtime_error_popup.py tests/test_main_window_nonfatal.py tests/test_main_file_ops_nonfatal.py
```

Batch queue / nonfatal file processing:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_main_file_ops_nonfatal.py tests/test_project_context.py tests/test_project_segment_reload.py
```

Roughcut:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_*.py tests/test_editor_roughcut_draft.py tests/test_project_segment_reload.py
```

Subtitle recognition accuracy:

```bash
./venv/bin/python -m pytest -q tests/test_subtitle_engine_settings.py tests/test_benchmark_mode_profiles.py
```

Timeline/editor rendering:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py tests/test_video_player_widget.py tests/test_editor_rendering_ownership_audit.py tests/test_timeline_render_cache.py
```

Project save/reload:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py tests/test_project_segment_reload.py tests/test_editor_srt_open_refresh.py tests/test_editor_autosave_cleanup.py
```

## Real-App Evidence Checklist

- Store artifacts under `output/manual_verification/latest/<timestamp_or_slug>/`.
- Capture command, fixture path, app version, mode, output files, and screenshots or logs when UI behavior matters.
- For subtitle quality work, quote back `quality`, `timing_priority_quality`, `timing_mae`, `raw/final`, `word_precision_count`, STT2 selection count, and rollback/source-preservation status when available.
- For editor and roughcut work, confirm save/reopen, seek/playhead, overlay, timeline footer, minimap, and final file list behavior.
- For batch generation, confirm one failed file does not block later files and that the final error summary appears after the batch completes.

## Failure Handling

- If one file fails in a batch, record the filename, error summary, and whether later files completed.
- If a benchmark improves speed but worsens subtitle quality, reject it and add the evidence to `doc/waste_action_item.md`.
- If a diagnosis was misleading or likely to repeat, add a prevention note to `doc/lesson_n_learned.md`.

## Report Fields

- 실행 모드
- 결과: pass / fail / blocked
- 저장 위치
- 원인 후보 또는 수정 요약
- 검증 명령과 결과
- 자막 품질 영향 여부
- 남은 위험 1-3줄
