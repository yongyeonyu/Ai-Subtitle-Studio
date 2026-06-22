# Project State

## Current purpose

현재 저장소 기준 `AI Subtitle Studio`는 macOS Apple Silicon 우선의 Python/PyQt6 데스크톱 자막 제작 도구입니다. `doc/README.md`, `main.py`, `core/runtime/config.py`, `ui/editor/`, `core/engine/`를 기준으로 보면 다음 흐름이 실제 구현 범위에 포함됩니다.

- 비디오/오디오 입력 처리
- 자막 생성 파이프라인
- 편집기와 타임라인 기반 수동 보정
- 프로젝트 저장/재열기
- 러프컷 초안 생성과 후속 편집
- STT/VAD/LLM 기반 후처리와 품질 보조

정확한 품질 수준이나 모델 성능 수치는 저장소만으로 확정할 수 없으므로 여기서는 기능 존재 여부만 문서화합니다.

## Implemented areas

저장소에서 직접 확인되는 구현 영역은 아래와 같습니다.

- 앱 부트스트랩과 메인 윈도우: `main.py`, `ui/main/`
- 편집기 UI와 타임라인: `ui/editor/`, `ui/timeline/`
- 비디오 플레이어 통합: `ui/editor/video_player_*`, `ui/video_controls.py`
- 자막 생성/보정 엔진: `core/engine/`, `core/pipeline/`, `core/subtitle_quality/`
- STT/VAD/오디오 전처리: `core/audio/`, `core/stt_mode/`
- LLM provider와 자막 후처리: `core/llm/`
- 프로젝트 포맷/저장/복원: `core/project/`, `ui/project/`
- 러프컷/PHASE2 관련 모듈: `core/roughcut/`, `ui/roughcut/`
- 설정/모드/개인화: `ui/settings/`, `core/personalization/`, `core/settings.py`
- 검증 스위트와 수동 검증 도구: `tests/`, `tools/qa_suite_runner.py`, `tools/verify_full_media_pipeline.py`

## Current development direction

현재 문서와 디렉터리 배치를 보면 개발 방향은 다음과 같이 읽힙니다.

- 정확도 우선 자막 생성과 후처리 품질 유지
- 편집기/타임라인 UX 안정화
- 프로젝트 저장/재열기/렌더링 회귀 방지
- 러프컷 초안 생성과 PHASE2 편집 흐름 보강
- 기존 Python/PyQt6 source app 유지와 실제 앱 검증 중심 진행

`core/roughcut/`, `ui/roughcut/`, `doc/releases/RELEASE_v04.00.15.md`, `doc/ACTION_ITEMS.md`를 보면 러프컷/PHASE2 흐름은 계획이 아니라 이미 진행 중인 작업 축으로 보입니다. 다만 세부 사용자 플로우는 일부가 문서 추론일 수 있습니다.

현재 운영 방향상 저장소는 Python/PyQt6 source app을 기준으로 유지합니다. 이전 Xcode/Swift migration 패키지와 실험용 자산은 정리되었으며, owner가 다시 명시하지 않는 한 새 native migration 전개를 기본 작업으로 취급하지 않습니다.

## Known constraints

- `core/runtime/config.py` 기준으로 현재 지원 타깃은 macOS이며 Apple Silicon 우선 정책이 강합니다.
- UI 주 경로는 PyQt6 Widgets/QPainter 계열입니다.
- 저장소에는 `ui/qml/`이 있지만, 현재 운영 문서와 기존 작업 규칙은 QML/SceneGraph/OpenGL/Metal UI를 기본 경로로 삼지 않도록 요구합니다.
- STT/VAD/Whisper/LLM 계층은 여러 provider와 보조 엔진이 함께 있으므로, 한 파일만 보고 동작을 단순화하면 회귀 위험이 큽니다.
- 자막 품질 관련 규칙은 속도보다 정확도를 우선하는 방향으로 관리됩니다.

## Must not break

현재 코드와 운영 문서 기준으로 특히 깨지면 안 되는 축은 아래와 같습니다.

- 앱 실행과 메인 윈도우 부팅
- 프로젝트 열기/저장/재열기
- 자막 생성 기본 파이프라인
- 편집기 타임라인 렌더링과 seek/playhead 동기화
- SRT 및 프로젝트 자산 입출력
- 러프컷 초안 생성과 편집기 연결
- 설정/모드 전환 후 회귀 없는 재실행
- 기존 검증 스위트가 커버하는 비치명적 예외 처리 경로

## Version/release notes

- 현재 코드에서 확인되는 앱 버전 상수는 `04.00.15`입니다. (`core/runtime/config.py`)
- 릴리스 노트는 `doc/releases/RELEASE_v04.00.07.md`부터 `doc/releases/RELEASE_v04.00.15.md`까지 유지합니다.
- 최신 릴리스 문서(`doc/releases/RELEASE_v04.00.15.md`)는 새 제품 기능보다 안정화, 소유권 정리, 회귀 방지 성격이 강합니다.
- `doc/README.md`와 릴리스 문서 기준 공식 검증 흐름은 `tools/qa_suite_runner.py`와 pytest, `compileall`, `git diff --check`, source-app smoke를 조합하는 방식입니다.
- DMG/패키징은 저장소에 관련 디렉터리가 있어도 기본 작업이 아니라 요청 시 별도 검증 대상으로 취급해야 합니다.

## Open action items

`doc/ACTION_ITEMS.md` 기준 현재 상단 활성 큐는 편집기 사후 처리 안정화와 실제 앱 검증 중심입니다. 문서에서 직접 확인되는 핵심 축은 다음과 같습니다.

- 자막 생성 이후 편집기 준비 상태와 UI 응답성 검증
- 편집기/타임라인 수동 검증 결과를 기준으로 한 회귀 방지
- 프로젝트 열기/저장/재로드 경로의 안정성 유지
- 실앱 증빙을 남긴 뒤에만 다음 UX 트림으로 이동

세부 우선순위는 `doc/ACTION_ITEMS.md`가 단일 소스 오브 트루스이므로, 새 세션에서는 반드시 그 파일의 최신 체크 상태를 다시 읽어야 합니다.

## Unverified assumptions

- 저장소 이름과 디렉터리 구조상 다중 STT/provider, 정밀 후처리, 개인화 규칙이 존재하는 것은 확인되지만, 각 조합이 기본 활성인지까지는 실행 없이 확정할 수 없습니다.
- `ui/qml/` 디렉터리가 존재하므로 일부 실험성 UI 경로가 있을 수 있으나, 기본 편집기 경로인지 여부는 운영 문서상 부정적입니다.
- 러프컷/PHASE2 사용자 플로우의 완성도는 파일 구조상 구현된 것으로 보이지만, 최신 제품 기본 화면에서 항상 노출되는지는 런타임 확인이 필요합니다.
