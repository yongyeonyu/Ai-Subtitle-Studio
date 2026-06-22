# AI Subtitle Studio Docs

이 디렉터리는 이 저장소의 개발 문서를 한곳에 모아 둔 정식 문서 루트입니다. 루트에는 `AGENTS.md`만 남기고, 실행 큐·구조 설명·검증 기준·릴리스 노트·협업 문서를 모두 `doc/` 아래로 정리했습니다.

## Project Snapshot

- 제품 라인: macOS Apple Silicon 우선 Python/PyQt6 source app
- 현재 코드 버전: `04.00.15`
- 현재 기본 방향: 자막 품질 우선, Python/PyQt6 유지, 검증 가능한 범위에서만 가속
- 최근 정리 원칙: 오래된 세션 로그와 Xcode migration 산출물은 줄이고, 현재 truth surface만 유지

## Read Order

새 세션 또는 새 에이전트는 아래 순서로 읽는 것을 기본으로 합니다.

1. `../AGENTS.md`
2. `README.md`
3. `ACTION_ITEMS.md`
4. `PROJECT_STATE.md`
5. `FEATURE_REGISTRY.md`
6. `ARCHITECTURE.md`
7. `VALIDATION.md`
8. `HANDOFF.md`
9. `cooperation.md`
10. `reference/README.md`
11. subtitle-domain ownership이 필요하면 `reference/SUBTITLE_GENERATION_DOMAIN_MAP.md`와 `reference/LONG_FILE_OWNERSHIP_MAP.md`
12. 관련 `releases/RELEASE_v*.md`
13. 필요 시 `test_case.md`, `test_result.md`, `waste_action_item.md`, `lesson_n_learned.md`

## Document Map

| File | Role |
| --- | --- |
| `ACTION_ITEMS.md` | 현재 실행 큐와 하드 룰의 단일 진실 원본 |
| `PROJECT_STATE.md` | 현재 제품 방향, 제약, 확인된 범위 |
| `FEATURE_REGISTRY.md` | 기능 owner map과 안전한 진입점 |
| `ARCHITECTURE.md` | 저장소 구조와 경계 설명 |
| `VALIDATION.md` | 기본 검증 명령과 문서 검증 기준 |
| `HANDOFF.md` | 다음 세션용 최신 요약만 남기는 짧은 인수인계 |
| `cooperation.md` | Dex/Jammini 협업 규칙과 위임 템플릿 |
| `test_case.md` | QA 기대치와 fixture 규칙 |
| `test_result.md` | 기록된 검증 결과와 산출물 요약 |
| `waste_action_item.md` | 폐기된 실험과 재시도 금지 근거 |
| `lesson_n_learned.md` | 반복 금지 교훈 |
| `reference/README.md` | 보존 중인 reference map의 짧은 인덱스 |
| `reference/SUBTITLE_GENERATION_DOMAIN_MAP.md` | 자막 도메인 owner map과 guard test 기준 |
| `reference/LONG_FILE_OWNERSHIP_MAP.md` | long-file ownership guard와 분할 증빙 |
| `releases/*` | 최근 릴리스 노트 |

## Quick Start

```bash
python3.11 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-mac.txt
python main.py
```

필수 런타임 도구:

- Python 3.11
- `ffmpeg`, `ffprobe`
- Git
- 모델/임시 오디오/프로젝트용 여유 디스크 공간

선택 도구:

- Ollama
- Hugging Face token
- 외부 LLM API key
- 외부 native helper를 별도 검증할 때만 Xcode command line tools

## QA Entry Points

공식 자동화 진입점:

```bash
./venv/bin/python tools/qa_suite_runner.py quick
./venv/bin/python tools/qa_suite_runner.py major
./venv/bin/python tools/qa_suite_runner.py full
```

보조 검증:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_video_player_widget.py tests/test_timeline_playhead_fit.py
./venv/bin/python tools/appctl.py status
./venv/bin/python tools/verify_full_media_pipeline.py --help
```

## Maintenance Rules

- 구조가 바뀌면 `ARCHITECTURE.md`를 함께 갱신합니다.
- 검증 명령이 바뀌면 `VALIDATION.md`를 함께 갱신합니다.
- 기능 owner 경계가 바뀌면 `FEATURE_REGISTRY.md`를 함께 갱신합니다.
- 의미 있는 작업을 끝내기 전 `HANDOFF.md`를 최신 요약으로 정리합니다.
- 긴 세션 로그는 `HANDOFF.md`에 누적하지 말고 릴리스 노트, 테스트 산출물, 또는 별도 evidence 파일로 보냅니다.
- 문서끼리 충돌하면 `ACTION_ITEMS.md`, 최신 릴리스 노트, 실제 코드/테스트 근거를 우선합니다.
- 통합 삭제된 `idea.md`, `DECISIONS/*`, `reference/File_structure.txt`, `reference/CODEMAP.md`는 대표님이 명시하지 않는 한 다시 만들지 않습니다.
