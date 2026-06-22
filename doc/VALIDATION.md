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

기능별로는 owner 주변의 좁은 pytest를 먼저 사용합니다. 예시는 아래와 같습니다.

```bash
./venv/bin/python -m pytest -q tests/test_main_window_nonfatal.py tests/test_runtime_error_popup.py
./venv/bin/python -m pytest -q tests/test_editor_srt_open_refresh.py tests/test_project_segment_reload.py
./venv/bin/python -m pytest -q tests/test_timeline_*.py
./venv/bin/python -m pytest -q tests/test_roughcut_*.py
```

## Subtitle recognition accuracy validation

자막 인식 정확도 아이디어는 실행 전 `doc/ACTION_ITEMS.md`의
`Subtitle Recognition Accuracy Guardrails`, `doc/waste_action_item.md`,
`doc/lesson_n_learned.md`를 먼저 확인합니다.

정확도 후보를 결과로 보고할 때는 최소한 아래 필드를 함께 quote-back합니다.

- `quality`
- `timing_priority_quality`
- `timing_mae`
- `raw/final`
- `stt2_selected_count`
- `word_precision_count` 또는 `word_precision_applied_count`
- `rollback` / `source_preservation` 발생 여부
- accepted artifact인지 diagnostic-only artifact인지

정확도 후보는 다음 조건을 만족하기 전까지 기본값으로 승격하지 않습니다.

- 대표 fixture에서 accepted target보다 품질과 타이밍이 모두 나빠지지 않을 것
- raw/final segment count가 설명 없이 흔들리지 않을 것
- broad threshold, timeout, padding, filter relaxation이 아닐 것
- one-shot fast 결과라면 sequential repeat 안정성을 추가로 확인할 것

owner 파일을 건드렸다면 주변 pytest를 먼저 고르고, benchmark artifact가 필요한
경우에는 `tools/server_mode_runner.py`와
`tools/benchmark_subtitle_pipeline_variants.py`의 현재 help/accepted target을
확인한 뒤 명령을 고정합니다. 새 명령을 문서화할 때는 실제 실행 가능한
subcommand와 artifact 경로만 남깁니다.

## PyQt / offscreen UI validation

PyQt UI 회귀는 화면 서버에 의존하지 않는 경로를 우선 사용합니다.

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_video_player_widget.py tests/test_timeline_playhead_fit.py
```

실행 중 앱 확인이 필요하면 저장소 도구를 사용합니다.

```bash
./venv/bin/python tools/appctl.py status
```

실제 미디어 기반 smoke 또는 수동 검증은 요청 범위가 클 때만 사용합니다.

```bash
./venv/bin/python tools/verify_full_media_pipeline.py --help
```

## Docs validation

문서 작업 후에는 링크와 필수 문서 존재 여부를 최소한 확인합니다.

```bash
find doc -maxdepth 4 -type f | sort
rg -n "^# AI Subtitle Studio Docs|^## Read Order|^## Document Map|^## Maintenance Rules" doc/README.md
rg -n "^# Project State|^# Feature Registry|^# Architecture|^# Validation Guide|^# Handoff" doc/*.md
for f in doc/idea.md doc/DECISIONS/server_mode_benchmarking.md doc/reference/CODEMAP.md doc/reference/File_structure.txt; do test ! -e "$f" || exit 1; done
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

- `doc/HANDOFF.md`가 이번 세션 상태를 반영하는지
- 변경으로 인해 `doc/PROJECT_STATE.md`, `doc/FEATURE_REGISTRY.md`, `doc/ARCHITECTURE.md`, `doc/VALIDATION.md` 중 갱신이 필요한 파일이 빠지지 않았는지
- `doc/ACTION_ITEMS.md`와 현재 작업 상태가 충돌하지 않는지

## Minimum validation before claiming completion

문서 전용 작업의 최소 완료선은 아래입니다.

- `git status --short` 확인
- `git diff --stat` 확인
- `git diff` 확인
- `git diff --check -- .` 통과 확인
- `doc/README.md`에서 새 문서들이 read order와 역할 설명에 연결되어 있는지 확인
- 통합 삭제된 문서(`doc/idea.md`, `doc/DECISIONS/server_mode_benchmarking.md`, `doc/reference/CODEMAP.md`, `doc/reference/File_structure.txt`)가 다시 생기지 않았는지 확인
- `doc/HANDOFF.md`가 업데이트되었는지 확인
- 코드 파일을 건드렸다면 안전한 syntax/import 검증을 추가 실행

코드 변경이 포함된 작업이라면 위 최소선에 더해 owner 기능의 targeted pytest 또는 QA runner를 반드시 붙여야 합니다.
