# Documentation Guide

이 폴더는 `AI Subtitle Studio` 저장소를 사람이든 AI 에이전트든 빠르게 안전하게 탐색할 수 있도록 돕는 운영 문서 모음입니다. 내용은 실제 저장소 구조, 현재 커밋에 존재하는 코드, 테스트, 릴리스 문서를 기준으로 정리합니다.

이 프로젝트는 현재 저장소 기준으로 macOS Apple Silicon 우선의 Python/PyQt6 데스크톱 자막 제작 앱입니다. 자막 생성, 편집기/타임라인, 프로젝트 저장, 러프컷, STT/VAD/LLM 보정 계층, 검증 스크립트가 함께 존재합니다. 구체 기능 범위는 과장하지 말고 `docs/PROJECT_STATE.md`와 `docs/FEATURE_REGISTRY.md`에서 다시 확인해야 합니다.

이 문서 폴더의 목적은 다음과 같습니다.

- 현재 제품 상태를 짧게 요약합니다.
- 주요 기능의 소유 파일과 검증 경로를 찾게 합니다.
- 구조 경계와 편집 금지선을 문서화합니다.
- 세션 종료 전 어떤 검증과 handoff가 필요한지 고정합니다.

## AI agent read order

1. `AGENTS.md`
2. `ACTION_ITEMS.md`
3. `check_list.md`
4. `File_structure.txt`
5. `docs/README.md`
6. `docs/PROJECT_STATE.md`
7. `docs/FEATURE_REGISTRY.md`
8. `docs/ARCHITECTURE.md`
9. `docs/VALIDATION.md`
10. `docs/HANDOFF.md`

현재 체크아웃에는 `check_list.md`가 없습니다. 없는 파일은 건너뛰되, 위 순서를 기본 진입 순서로 유지합니다. 위 문서를 다 본 뒤에는 저장소 상황에 따라 `CODEMAP.md`, 최신 `RELEASE_v*.md`, `README.md`, `test_case.md`, `test_result.md`, `waste_action_item.md`, `lesson_n_learned.md`를 추가로 읽는 것이 안전합니다.

## Stable project docs

다음 문서는 저장소 구조와 작업 규칙을 설명하는 안정 문서입니다.

- `README.md`
- `RELEASE_v*.md`
- `docs/PROJECT_STATE.md`
- `docs/FEATURE_REGISTRY.md`
- `docs/ARCHITECTURE.md`
- `docs/VALIDATION.md`
- `docs/DECISIONS/README.md`

다음 문서는 커밋 대상이지만 운영 상태와 세션 연결성이 더 강한 작업 문서입니다.

- `AGENTS.md`
- `ACTION_ITEMS.md`
- `docs/HANDOFF.md`
- `test_case.md`
- `test_result.md`
- `lesson_n_learned.md`

## Internal or temporary files

다음 항목은 로컬 작업 보조물로 취급하고, 의도 없이 커밋하지 않아야 합니다.

- `.codex_work/`
- `output/` 아래 수동 검증 산출물
- 로컬 가상환경, 빌드 산출물, 캐시 파일
- 개인 메모, 비공개 경로, 임시 스크립트

## Before coding

AI 에이전트는 코드를 수정하기 전에 아래 순서를 따라야 합니다.

1. 위 read order 문서를 읽습니다.
2. 수정 대상 기능의 소유 디렉터리와 핵심 owner 파일을 식별합니다.
3. 현재 동작을 문서, 테스트, 필요 시 실제 앱 검증 기준으로 확인합니다.
4. 넓은 리팩터링 대신 요청 범위에 맞는 최소 수정 범위를 정합니다.
5. 편집 전에 어떤 검증을 할지 `docs/VALIDATION.md` 기준으로 정합니다.
6. 의미 있는 작업을 끝내기 전 `docs/HANDOFF.md`를 업데이트합니다.

추가로 아래 규칙을 지켜야 합니다.

- 기존 기능을 추정으로 다시 설계하지 않습니다.
- STT/VAD/Whisper/LLM/타임라인/프로젝트 저장 흐름은 owner 파일을 읽기 전에는 손대지 않습니다.
- 구조 설명이 바뀌면 `docs/ARCHITECTURE.md`를 같이 갱신합니다.
- 검증 명령이 바뀌면 `docs/VALIDATION.md`를 같이 갱신합니다.
- 기능 소유 경계가 바뀌면 `docs/FEATURE_REGISTRY.md`를 같이 갱신합니다.

## Temporary working memory

`.codex_work/`는 로컬 Codex scratch 공간으로 사용할 수 있습니다. 예를 들면 세션 중간 메모, 비교용 임시 출력, 에이전트 전용 체크리스트를 둘 수 있습니다. 다만 이 디렉터리는 영구 산출물이 아니며 커밋 대상이 아닙니다.
