# Architecture

## Entry points

현재 저장소에서 확인되는 대표 진입점은 아래와 같습니다.

- `main.py`: 데스크톱 앱 부트스트랩, 환경 변수 로드, 런타임 예외 로깅, Qt 앱 시작
- `ui/main/main_window.py`: 메인 윈도우와 상위 UI 조립
- `tools/qa_suite_runner.py`: 저장소 표준 검증 진입점
- `tools/appctl.py`: 실행 중 앱 상태/제어 보조 도구

루트 `config.py`는 없고, 앱 기본 런타임 설정의 중심은 `core/runtime/config.py`입니다.

## Top-level layout

- `core/`: 엔진, 파이프라인, 프로젝트, 러프컷, LLM, 오디오, 품질 규칙, 런타임
- `ui/`: 메인 화면, 편집기, 타임라인, 러프컷, 설정, 대화상자, 로그, 프로젝트 화면
- `native/`: Python source app에서 쓰는 C/C++ 네이티브 보조 코드
- `tools/`: QA, 실앱 검증, 유지보수 체크, 앱 제어 스크립트
- `tests/`: 기능별 회귀 테스트
- `packaging/`: 패키징 관련 자산
- `config/`, `assets/`, `doc/`, `output/`: 설정, 리소스, 문서, 산출물

`doc/reference/`는 넓은 scratchpad가 아니라 테스트가 지키는 owner map 보관소입니다. 현재 보존 대상은 `doc/reference/SUBTITLE_GENERATION_DOMAIN_MAP.md`, `doc/reference/LONG_FILE_OWNERSHIP_MAP.md`, 그리고 짧은 인덱스인 `doc/reference/README.md`입니다.

## Core layer

`core/`는 제품 동작의 중심입니다.

- `core/engine/`: 자막 생성과 후처리의 핵심 orchestration
- `core/audio/`: 오디오 전처리, STT/VAD 보조 계층
- `core/stt_mode/`: STT 모드 및 품질 프리셋 계층
- `core/llm/`: provider 래퍼, LLM 호출, 정책/정리 로직
- `core/subtitle_quality/`: 환각/반복/경계/정확도 보조 규칙
- `core/project/`: 프로젝트 포맷, 저장, 자산, 재로드
- `core/roughcut/`: 러프컷 초안 생성과 후속 데이터 구조
- `core/runtime/`: 버전, 플랫폼 정책, 디렉터리, 런타임 기본값
- `core/personalization/`: 사전, LoRA, 사용자 규칙 계층
- `core/native/`: 네이티브 보조 모듈과 Python 브리지

`core/engine/subtitle_engine.py`처럼 크고 많은 책임을 가진 owner 파일이 존재하므로, 수정 전 소유 경계를 더 잘게 확인해야 합니다.

## UI layer

`ui/`는 화면과 상호작용을 담당합니다.

- `ui/main/`: 메인 윈도우, 앱 수준 상태
- `ui/editor/`: 편집기 본체, 저장/로드, 비디오 제어, 프로젝트 연결
- `ui/timeline/`: 타임라인, 글로벌 캔버스, 렌더링, 입력 처리
- `ui/roughcut/`: 러프컷 화면과 제어
- `ui/settings/`: 설정 화면
- `ui/project/`: 프로젝트 관련 UI
- `ui/dialogs/`, `ui/log/`, `ui/help/`, `ui/sidebar/`, `ui/queue/`: 보조 UI

UI는 상태를 보여주고 사용자 입력을 core 호출로 연결해야 하며, STT/VAD/LLM 정책을 UI 내부에서 직접 재구현하면 안 됩니다.

## Data/project layer

프로젝트 저장/복원 경계는 주로 `core/project/`에 있습니다.

- 프로젝트 포맷과 버전: `core/project/project_format.py`
- 프로젝트 디스크 I/O: `core/project/project_io.py` (`.aissproj`는 binary envelope에 project payload를 저장하고, 내부 API는 `read_project_file` / `write_project_file`로 통일)
- 자산 관리와 연결: `core/project/project_assets.py`
- 프로젝트 상태 매니저: `core/project_data_manager.py`
- 관련 UI 진입점: `ui/project/`, `ui/editor/editor_project_*`

프로젝트 포맷은 편집기, 자막, 미디어 자산을 잇는 공통 경계이므로, UI 변경이라도 저장 포맷을 건드리면 회귀 테스트 범위를 넓혀야 합니다.

## LLM/provider boundary

LLM/provider 경계는 `core/llm/`이 owner입니다. 이 계층은 OpenAI, Ollama, 기타 provider 래퍼와 자막 후처리 로직을 모읍니다. `core/engine/`와 `core/roughcut/`는 이 계층을 사용하지만, UI가 provider 세부사항을 직접 알아서는 안 됩니다.

provider 정책이나 fallback을 바꿀 때는 아래를 같이 봐야 합니다.

- 호출 실패 시 복구 경로
- 문맥 제한과 가드 정책
- 자막 split/correction과 품질 규칙의 결합

## STT/subtitle boundary

STT와 자막 엔진 경계는 대체로 아래 조합으로 보입니다.

- 오디오 입력/분석: `core/audio/`
- STT 모드/모델 선택: `core/stt_mode/`
- 자막 생성 orchestration: `core/engine/`
- 품질 및 경계 보정: `core/subtitle_quality/`

UI는 이 결과를 소비하고 편집해야 하며, 알고리즘 정책 자체는 core에 남겨 두는 편이 안전합니다.

## Roughcut boundary

러프컷 경계는 `core/roughcut/`과 `ui/roughcut/`입니다. 파일명과 테스트를 보면 러프컷 초안 생성, LLM 기반 섹션/구조화, 편집기 연결이 이미 구현 범위에 들어와 있습니다. 다만 러프컷 데이터가 곧바로 편집기 프로젝트 상태와 연결될 수 있으므로, 두 경계를 동시에 보는 것이 안전합니다.

## Server-mode benchmark boundary

`tools/server_mode_runner.py`는 UI 없는 benchmark/compare owner입니다. 이 경로는 현재 기본 제품 기능이나 STT runtime route가 아니라, accepted artifact 비교와 hard guardrail 검토를 위한 terminal-only 검증 표면으로 취급합니다.

Server-mode 관련 변경은 아래 경계를 지켜야 합니다.

- Safe prep: benchmark command bundle, artifact compare, rejected-family review, no-patch evidence packet.
- Dex-only: runtime default 변경, STT routing/quality policy 변경, UI 연결, accepted baseline 갱신.
- PyQt 앱 UX와 server-mode benchmark path를 묶는 기능화 작업은 대표님이 별도로 열기 전까지 active direction이 아닙니다.

## Config/settings boundary

설정 경계는 크게 둘입니다.

- 런타임 기본값과 플랫폼 정책: `core/runtime/config.py`
- 사용자 설정과 모드/UI 연결: `core/settings.py`, `core/mode_manager.py`, `ui/settings/`

설정 UI를 수정할 때는 단순 표시 텍스트뿐 아니라 실제 런타임 적용 지점을 확인해야 합니다.

## Import boundaries

현재 구조에서 안전한 기본 원칙은 아래와 같습니다.

- `ui/*`는 `core/*`를 호출할 수 있습니다.
- `core/*`는 가능하면 `ui/*`에 의존하지 않아야 합니다.
- 프로젝트 포맷/저장은 `core/project/*`를 중심으로 유지합니다.
- 테스트는 owner 파일을 직접 겨냥하되, UI 회귀는 `QT_QPA_PLATFORM=offscreen` 경로를 우선 고려합니다.

저장소에 mixin, helper, bridge 파일이 많아서 실제 import coupling은 완전히 느슨하지 않습니다. 그래서 경계를 문서로 먼저 확인하고 최소 범위 수정으로 접근하는 것이 중요합니다.

## Known coupling and risks

- `core/engine/subtitle_engine.py`, `ui/editor/editor_widget.py`, `ui/timeline/*`는 큰 owner 파일과 세부 helper가 함께 있어 수정 반경이 예상보다 커질 수 있습니다.
- Python 경로와 macOS native 보조 모듈이 함께 존재하므로, 한쪽만 보고 “죽은 코드”로 판단하면 위험합니다.
- `ui/qml/` 디렉터리가 존재하지만 현재 운영 규칙은 Qt Widgets 중심 경로를 기본으로 봅니다.
- 편집기, 타임라인, 프로젝트 재로드는 서로 깊게 연결되어 있어 시각 수정도 저장/seek/playhead 회귀로 번질 수 있습니다.
