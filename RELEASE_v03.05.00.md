<!--
Document-Version: 03.05.00
Phase: PHASE2
Last-Updated: 2026-05-02
Updated-By: Codex with 대표님
Previous-Release: v03.04.00
-->
# RELEASE v03.05.00

## 핵심 요약
- v03.04.01 작업 묶음을 v03.05.00 릴리즈로 고정했습니다.
- 자막 생성 흐름을 `FFmpeg 전처리 -> 음성 필터 -> STT1 -> STT2 -> 앙상블 보강 -> VAD 위치 보정 -> 자막 LLM -> 러프컷 LLM` 순서로 정리했습니다.
- 사이드바 모델/상태 테이블, 큐 리스트, 프로젝트 정보, 하단 메뉴, 타임라인 조작성을 대폭 정리했습니다.
- 글로벌 캔버스와 타임라인은 가시 영역 렌더링, OpenGL/QML 보조 오버레이, 캐시/partial repaint 중심으로 가볍게 만들었습니다.

## STT / 오디오
- STT1/STT2 이중 인식 경로와 `core/audio/stt_ensemble.py`를 추가했습니다.
- STT1 결과를 기준으로 보존하고, STT2는 STT1이 놓친 구간만 보강하는 정책으로 변경했습니다.
- 한국어 최적화 Whisper Transformers worker를 추가하고 macOS/Windows 모델 레지스트리에 Whisper 전체 모델 및 한국어 후보를 확장했습니다.
- STT 선분할 VAD 의존을 줄이고, VAD는 생성 후 음성 구간 검수/위치 보정 역할로 재정의했습니다.
- `dataset/audio_presets.json`의 야외/노이즈 환경 preset을 강화하고, FFmpeg 전처리와 음성 필터가 같은 오디오 preset을 사용하도록 정리했습니다.
- RNNoise를 빠른 노이즈 제거 실험 옵션으로 추가했습니다. `rnnoise_demo` 또는 `RNNOISE_BINARY`가 준비된 환경에서는 RNNoise를 사용하고, 없으면 기존 FFmpeg 정제 흐름으로 계속 진행합니다.

## 러프컷 / 중분류
- 러프컷 초안 생성은 자막 생성 중이 아니라 자막 생성 완료 후 1회 실행하도록 변경했습니다.
- 중분류 코드는 A~Z 범위로 제한하고, 기본 목표를 보통 10개 이하로 맞췄습니다.
- 중분류는 첫 구간 0초부터 마지막 구간 영상 끝까지 공백 없이 이어지도록 보정했습니다.
- 러프컷 LLM prompt는 전체 자막 흐름, 화면 전환, 주제 전환, 장소 전환 중심으로 중분류를 나누도록 수정했습니다.
- 러프컷 LLM 선택에는 `사용 안함`을 추가하고, 전체 자막을 읽고 중분류를 판단할 수 있는 모델만 후보로 남겼습니다.

## 타임라인 / 캔버스
- 타임라인과 글로벌 캔버스 렌더링을 가시 영역 중심으로 줄이고 OpenGL surface/cache/partial repaint를 적용했습니다.
- 플레이헤드 이동과 확대/축소는 현재 플레이헤드 기준으로 동작하도록 보정했습니다.
- 자막 세그먼트 좌우 화살표 hit target, hover 유지, drag 중 미리보기 bar, 색 튐 억제, 다이아몬드 버튼 겹침 문제를 수정했습니다.
- 화자 표시를 세그먼트 중앙에 맞추고, 화자가 2명 이상일 때 여러 줄로 표시할 수 있게 했습니다.
- A~Z 중분류 색상을 서로 다르게 표시하도록 정리했습니다.

## UI / 상태 표시
- 사이드바 상단 상태는 저장 중에만 `저장`이 잠깐 보이고, 저장 완료 뒤에는 `완료`가 우선되도록 변경했습니다.
- 사이드바 단계 테이블은 진행 중 노란색, 완료 초록색을 숫자/단계/모델명에 함께 적용합니다.
- 자막과 러프컷이 모두 완료되면 7단계 `러프컷 LLM`까지 완료 표시가 되도록 수정했습니다.
- 큐 리스트는 `상태 / 파일명 / 예상시간`을 정렬하고, 상태 이모지를 제거했으며 상태 1줄/파일명 2줄 표시로 바꿨습니다.
- 프로젝트 정보 버튼을 하단으로 정렬하고, 프로젝트 정보 패널과 큐 패널에 Qt Quick/Scene Graph 기반 보조 UI를 추가했습니다.
- 설정 메뉴에서 중복 모델 선택 UI를 줄이고, 사이드바 단계 테이블의 모델명을 클릭해 즉시 모델을 선택/저장하도록 정리했습니다.
- `최근작업` 버튼과 관련 UI 흐름을 제거하고 iCloud/NAS 자동 처리 및 큐 리스트를 위로 이동했습니다.

## 재시작 / 프로젝트 저장
- 재시작 시 자막 세그먼트, 러프컷 세그먼트, 큐 상태, 단계 상태가 초기화되도록 동기화했습니다.
- 프로젝트 파일에 사용 모델과 preset 정보를 저장하고, 다시 열 때 해당 설정을 그대로 복원하도록 했습니다.
- 프로젝트 로드 시 pending 자막 큐가 이전 세그먼트와 겹치지 않도록 보정했습니다.

## 제거 / 영향 범위
- 음성 필터에서 `Demucs` 선택/실행/상세 설정/모델 레지스트리 노출을 제거했습니다.
- `core.platform_compat.demucs_binary()` helper를 제거했습니다.
- 영향 범위:
  - Demucs를 직접 선택하던 UI 경로는 더 이상 노출되지 않습니다.
  - 기존 FFmpeg, DeepFilter, RNNoise 실험 경로는 유지됩니다.
  - `Resemble Enhance`, `ClearerVoice-Studio`, `TEN VAD`는 후속 후보 액션아이템으로 남겼습니다.

## 의존성
- macOS/Windows requirements에 Transformers 기반 한국어 Whisper worker용 `transformers`, `accelerate`를 추가했습니다.

## 검증
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s tests`
  - exit code 0
- module-by-module unittest sweep: all `tests/test_*.py` modules passed
- unittest discovery count: 221 tests
- Python AST 검사: 222 files
- offscreen UI smoke: MainWindow / SettingsDialog / AdvancedSettingsDialog / ExportDialog / RoughcutWidget
- `git diff --check -- . ':(exclude)dataset/video_preview_cache'`
- 루트 금지 파일 검사
