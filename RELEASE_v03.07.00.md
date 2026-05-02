<!--
Document-Version: 03.07.00
Phase: PHASE2
Last-Updated: 2026-05-02
Updated-By: Codex with 대표님
Previous-Release: v03.06.00
-->
# RELEASE v03.07.00

## 핵심 요약
- v03.06.01부터 v03.06.22까지의 편집기 안정화, 프레임 기준 동기화, GPU 렌더링 경로, 비디오 재생 안정화 묶음을 v03.07.00 릴리즈로 고정했습니다.
- 자막 편집/재생/저장 기준을 초 단위 보조값이 아니라 영상 FPS 기반 프레임 번호 중심으로 정리했습니다.
- 타임라인, 글로벌 캔버스, 자막 에디터 viewport, 비디오 자막 overlay가 GPU/OpenGL-backed surface를 사용할 수 있도록 렌더링 경로를 재구성했습니다.
- 비디오 재생 중 불필요한 자막 overlay scene update와 subtitle provider polling을 줄여 재생 끊김을 완화했습니다.

## 프레임 기준 편집 / 프로젝트 저장
- 비디오 frame map을 기준으로 playback time, playhead, scrub, frame-step, segment boundary, subtitle editor selection이 같은 프레임에 맞춰 움직이도록 보강했습니다.
- 프로젝트 JSON에는 `canonical_unit: frame`, clip/frame rate metadata, subtitle `start_frame`/`end_frame`을 저장하고, 재오픈 시 frame number를 우선 복원합니다.
- SRT 출력과 비디오 재생 API처럼 초 단위가 필요한 경로에서는 프레임 정보를 초로 변환해 사용합니다.
- 긴 영상 재생 중에도 비디오 시간과 플레이헤드가 점점 벌어지지 않도록 probed frame-time map 기준으로 동기화했습니다.

## 타임라인 / 캔버스 / 편집 UX
- 새 파일 로드 직후 사이드바 단계표는 실제 로그가 나오기 전까지 모두 미실행 상태로 유지합니다.
- 자막 세그먼트 색상은 확대/축소 후에도 같은 품질/종류 색이 유지되도록 공통 계산 경로로 통합했습니다.
- 재생 중 타임라인이 플레이헤드를 따라가고, 자막 에디터 현재 줄도 세그먼트 전환과 함께 늦지 않게 이동합니다.
- 화자 변경 메뉴는 화자 lane 전체가 아니라 중앙 화자 라벨 hit target에서만 열리도록 바꿨습니다.
- 무음 gap 우클릭 메뉴에 `여기까지 생성`, `여기부터 생성`을 추가해 플레이헤드 기준 새 자막 세그먼트를 만들 수 있게 했습니다.
- 새 자막 placeholder인 `새자막`은 편집하지 않으면 그대로 저장되고, 더블클릭/Enter 등으로 편집을 시작하면 즉시 비워집니다.
- Shift+Enter soft line break는 저장 후 재오픈해도 같은 자막 안 줄바꿈으로 복원됩니다.
- 자막 이동 중 선택 음영은 line identity 기준으로 칠해져 옆 자막까지 번지지 않도록 수정했습니다.

## 비디오 / GPU 렌더링
- 비디오 preview에는 이전/다음 1프레임 이동 버튼을 추가했고, preview proxy는 720p와 원본 FPS를 유지하도록 생성합니다.
- frame-step은 같은 clip 안에서는 thumbnail/context reload 없이 active video surface에서 빠르게 seek합니다.
- 타임라인/글로벌 캔버스는 GPU 가능 환경에서 OpenGL-backed canvas를 사용하고, offscreen/test 환경에서는 QWidget fallback을 유지합니다.
- 자막 에디터는 QTextEdit 기능을 유지하면서 OpenGL viewport를 사용할 수 있도록 했습니다.
- 비디오 자막 overlay는 별도 QLabel overlay가 아니라 QGraphicsScene 내부 item으로 이동해 비디오 GL viewport와 같은 렌더 경로에서 그립니다.
- 재생 중 같은 자막이 유지되는 구간에서는 overlay scene과 숨김 label을 다시 갱신하지 않고, subtitle provider는 재생 중 반복 polling하지 않습니다.

## 실행 안정성 / 메모리
- 재시작 시 에디터 텍스트, 타임라인/글로벌 캔버스, gap/VAD/edit/drag state, video pending segments를 초기화합니다.
- 홈 이동은 active backend/STT worker와 local Ollama LLM unload 요청을 수행하고, 늦게 끝난 roughcut draft callback이 화면에 붙지 않도록 막습니다.
- 에디터 모드 진입 시 idle STT/Whisper worker와 local LLM 모델을 종료해 메모리를 회수합니다.
- 단, backend/pipeline이 실제로 실행 중일 때는 에디터 모드 모델 회수를 차단해 생성 작업이 중간에 끊기지 않도록 했습니다.
- timeline waveform worker와 ffmpeg subprocess는 에디터 닫기/종료 경로에서 정리되어 `QThread: Destroyed while thread is still running` 위험을 줄였습니다.

## 제거 / 영향 범위
- 이번 릴리즈에서 공개 `def`, `class`, UI action, signal, slot을 삭제한 변경은 없습니다.
- `dataset/video_preview_cache/`는 기존 no-touch 규칙에 따라 로컬 캐시로 유지되며 릴리즈 커밋 대상에서 제외합니다.
- `.codex_work/`와 `checkpoints/`는 로컬 작업/모델 산출물이며 릴리즈 커밋 대상이 아닙니다.

## 검증
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s tests`
  - exit code 0
- module-by-module unittest sweep
  - `MODULE_SWEEP_OK`
- Python AST 검사
  - `AST OK: 228 files`
- offscreen UI smoke
  - `UI smoke OK`
- `git diff --check -- . ':(exclude)dataset/video_preview_cache'`
  - exit code 0
- `python3.11 -m pip check`
  - `No broken requirements found.`
- 루트 금지 파일 검사
  - 금지 파일 없음
