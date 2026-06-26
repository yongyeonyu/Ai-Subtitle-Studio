# Validation Guide

이 문서는 현재 저장소에서 실제로 확인되는 검증 경로만 정리합니다. 새 인프라를 상정하지 말고, 이미 있는 pytest, QA 스크립트, source-app smoke 흐름을 우선 사용합니다.

## Validation principles

- 수정 범위에 맞는 가장 좁은 검증부터 시작합니다.
- 편집기/타임라인/UI 변경은 가능하면 `QT_QPA_PLATFORM=offscreen` 검증을 포함합니다.
- 릴리스 수준 변경이나 생성 파이프라인 변경은 pytest만으로 끝내지 말고 `tools/qa_suite_runner.py` 또는 실앱 검증 산출물을 남깁니다.
- 문서만 수정했더라도 handoff와 diff 검토는 생략하지 않습니다.

## Syntax / compile validation

코드 파일을 수정했다면 안전한 기본 문법 검사는 아래 중 하나를 사용합니다.

```bash
python -m compileall .
```

가상환경 기준으로 저장소가 자주 사용하는 더 좁은 명령은 아래와 같습니다.

```bash
./venv/bin/python -m compileall -q main.py core ui tests tools
```

문서 전용 작업이라면 코드 파일을 바꾸지 않았는지 먼저 확인하고, 코드 변경이 없으면 compile 단계는 선택적으로 생략할 수 있습니다.

## Import validation

가벼운 import 검증이 필요하면 아래처럼 owner 모듈을 직접 import 합니다.

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python - <<'PY'
from ui.main.main_window import MainWindow
print("import-ok", MainWindow.__name__)
PY
```

편집기 owner를 건드렸다면 `ui.editor.editor_widget`, 타임라인이면 `ui.timeline.timeline_widget`, 프로젝트면 `core.project.project_format` 같은 직접 owner import를 우선 선택합니다.

## Tests

전체 스위트와 빠른 검증 경로가 함께 존재합니다.

빠른 표준 검증:

```bash
./venv/bin/python tools/qa_suite_runner.py quick
```

주요 검증:

```bash
./venv/bin/python tools/qa_suite_runner.py major
```

전체 검증:

```bash
./venv/bin/python tools/qa_suite_runner.py full
```

`full`의 기본 X5 경로는 `test video/X5_시승기_후반.MP4`입니다. 자동 fallback 후보는 오디오 스트림이 있을 때만 선택되며, 표준 MP4가 없으면 X5 시나리오는 `media_missing`으로 실패해야 합니다. 오디오가 있는 외부 X5 소스를 보조 proof로 사용할 때만 아래처럼 명시 override를 사용하고, 결과 보고서에는 표준 MP4 proof와 구분해서 기록합니다.

```bash
AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 AI_SUBTITLE_STUDIO_QA_X5_MEDIA='/path/to/audio-bearing-x5-media' ./venv/bin/python tools/qa_suite_runner.py full
```

기능별로는 owner 주변의 좁은 pytest를 먼저 사용합니다. 예시는 아래와 같습니다.

```bash
./venv/bin/python -m pytest -q tests/test_main_window_nonfatal.py
./venv/bin/python -m pytest -q tests/test_editor_srt_open_refresh.py tests/test_project_segment_reload.py
./venv/bin/python -m pytest -q tests/test_timeline_*.py
./venv/bin/python -m pytest -q tests/test_roughcut_*.py
```

## Trace workspace validation

Trace/temp-workspace changes should first prove syntax, focused trace behavior, then the startup/app-command diagnostic guard.

```bash
./venv/bin/python -m py_compile main.py core/runtime/temp_workspace.py core/runtime/trace_logger.py tools/collect_trace_package.py tests/test_trace_logger.py tests/test_startup_diagnostics.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py tests/test_startup_diagnostics.py tests/test_app_command_bridge.py -k "trace or diagnostic or open_media or open_project"
```

Trace packages are collected with:

```bash
./venv/bin/python tools/collect_trace_package.py --run-id <trace-run-id>
```

## PyQt / offscreen UI validation

PyQt UI 회귀는 화면 서버에 의존하지 않는 경로를 우선 사용합니다.

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_video_player_widget.py tests/test_timeline_playhead_fit.py
```

실행 중 앱 확인이 필요하면 저장소 도구를 사용합니다.

```bash
./venv/bin/python tools/appctl.py status
```

편집기 타임라인 확대/축소/맞춤 자동화 smoke가 필요하면 source app에서 프로젝트를 연 뒤 아래 명령을 사용합니다.

```bash
./venv/bin/python tools/appctl.py editor-timeline-view zoom-in
./venv/bin/python tools/appctl.py editor-timeline-view zoom-out
./venv/bin/python tools/appctl.py editor-timeline-view fit
./venv/bin/python tools/appctl.py editor-timeline-view time-window
./venv/bin/python tools/appctl.py editor-timeline-view max
```

자막자석은 실제 자막 타이밍을 바꿀 수 있으므로 기본 quick smoke에는 넣지 말고, 명시 검증 artifact를 만들 때만 아래 명령을 사용합니다.

```bash
./venv/bin/python tools/appctl.py editor-subtitle-magnet
```

편집기 하단 전역 메뉴 버튼의 안전한 smoke는 아래처럼 확인합니다. `global-menu-status`는 전체 등록 버튼을 조회하고, `global-menu-action`은 설정/화자/사전/저장/비디오/음성처럼 자동화-safe 버튼만 허용합니다.

```bash
./venv/bin/python tools/appctl.py global-menu-status
./venv/bin/python tools/appctl.py global-menu-action settings
./venv/bin/python tools/appctl.py global-menu-action speaker
./venv/bin/python tools/appctl.py global-menu-action dictionary
./venv/bin/python tools/appctl.py global-menu-action save
./venv/bin/python tools/appctl.py global-menu-action video
./venv/bin/python tools/appctl.py global-menu-action stt
```

roughcut 영상 렌더와 exact-join sidecar smoke가 필요하면 source app에서 roughcut 프로젝트를 연 뒤 아래 순서로 확인합니다.

```bash
./venv/bin/python tools/appctl.py open-project projects/codex_live_roughcut_export_chain_20260623.aissproj
./venv/bin/python tools/appctl.py open-roughcut
./venv/bin/python tools/appctl.py roughcut-export-srt output/manual_verification/latest/<artifact>/exports/app_command_render.srt
./venv/bin/python tools/appctl.py roughcut-render-video output/manual_verification/latest/<artifact>/exports/app_command_render.mov
./venv/bin/python tools/appctl.py open-srt output/manual_verification/latest/<artifact>/exports/app_command_render.srt
```

실제 미디어 기반 smoke 또는 수동 검증은 요청 범위가 클 때만 사용합니다.

```bash
./venv/bin/python tools/verify_full_media_pipeline.py --help
```

## Docs validation

문서 작업 후에는 링크와 필수 문서 존재 여부를 최소한 확인합니다.

```bash
find docs -maxdepth 2 -type f | sort
rg -n "## AI agent read order|## Before coding|## Temporary working memory" docs/README.md
rg -n "^# Project State|^# Feature Registry|^# Architecture|^# Validation Guide|^# Handoff" docs/*.md
```

## Git diff review

항상 아래 세 가지를 확인합니다.

```bash
git status --short
git diff --stat
git diff
```

## Whitespace check

텍스트와 코드 모두 trailing whitespace, patch corruption을 막기 위해 아래 검사를 사용합니다.

```bash
git diff --check -- .
```

## Forbidden root-file scan

요청되지 않은 루트 파일 추가를 막기 위해 루트 레벨 파일 변화를 확인합니다.

```bash
find . -maxdepth 1 -type f | sort
git status --short
```

새 루트 파일이 필요했다면 요청과 이 문서에 맞는지 다시 확인합니다.

## Handoff check

의미 있는 작업을 마칠 때는 아래를 확인합니다.

- `docs/HANDOFF.md`가 이번 세션 상태를 반영하는지
- 변경으로 인해 `docs/PROJECT_STATE.md`, `docs/FEATURE_REGISTRY.md`, `docs/ARCHITECTURE.md`, `docs/VALIDATION.md` 중 갱신이 필요한 파일이 빠지지 않았는지
- `ACTION_ITEMS.md`와 현재 작업 상태가 충돌하지 않는지

## Minimum validation before claiming completion

문서 전용 작업의 최소 완료선은 아래입니다.

- `git status --short` 확인
- `git diff --stat` 확인
- `git diff` 확인
- `git diff --check -- .` 통과 확인
- `docs/README.md`에서 새 문서들이 read order와 역할 설명에 연결되어 있는지 확인
- `docs/HANDOFF.md`가 업데이트되었는지 확인
- 코드 파일을 건드렸다면 안전한 syntax/import 검증을 추가 실행

코드 변경이 포함된 작업이라면 위 최소선에 더해 owner 기능의 targeted pytest 또는 QA runner를 반드시 붙여야 합니다.
