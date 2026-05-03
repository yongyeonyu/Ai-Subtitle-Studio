# RELEASE v03.14.00

릴리즈일: 2026-05-04
Phase: PHASE2
기준 브랜치: `main`
이전 릴리즈: `v03.13.00`

## 요약

v03.14.00은 v03.13.x 리팩토링 라인을 마감하는 구조 안정화 릴리즈입니다. 루트 runtime 파일을 `core/runtime`으로 정리하고, 컷 경계/오디오 처리/자막 엔진/프로젝트 저장/러프컷 상태/홈 사이드바/에디터 scan-cut처럼 길어진 모듈을 기능 단위로 분리했습니다. 사용자-visible 동작은 유지하면서 테스트 patch entry point와 기존 public function 이름을 최대한 보존했습니다.

## 주요 변경

- 루트 `config.py`, `logger.py`를 제거하고 `core/runtime/config.py`, `core/runtime/logger.py` 기준으로 전체 import를 정리했습니다.
- `core/cut_boundary.py`의 auto grid/FPS 확장 로직을 `core/cut_boundary_auto*.py`, `core/cut_boundary_fps.py`로 분리하고, 도달 불가능했던 중복 detector/profile 구현을 제거했습니다.
- `core/audio/media_processor.py`를 orchestration 중심으로 줄이고 audio command/cache, VAD, Whisper transcription/ensemble/payload de-dup 로직을 별도 mixin으로 분리했습니다.
- 오디오 프리셋 기본 데이터와 추천 stack 정의를 `core/audio/audio_preset_data.py`로 분리해 `audio_presets.py`가 loader/applier 역할에 집중하게 했습니다.
- `core/project/project_manager.py`에서 frame timebase 증강과 model settings snapshot/restore 로직을 `project_frames.py`, `project_model_settings.py`로 분리했습니다.
- `core/engine/subtitle_engine.py`에서 runtime settings, prompt template, final gap timing/frame-field pass를 `subtitle_settings.py`, `subtitle_prompts.py`, `subtitle_timing.py`로 분리했습니다.
- `ui/roughcut/roughcut_state.py`의 frame-synced topicless placeholder 변환을 `ui/roughcut/roughcut_topicless.py` installer로 정리하고 중복 fallback 구현을 제거했습니다.
- `ui/editor` scan-cut patch 계열, video overlay widgets, editor roughcut draft, `ui/settings/settings_roughcut.py`, `ui/home_sidebar.py`, `core/pipeline/cut_boundary_helpers.py`를 분리해 큰 UI/pipeline 파일의 책임을 낮췄습니다.

## 영향 범위

- `core/runtime/*`
- `core/cut_boundary.py`, `core/cut_boundary_auto*.py`, `core/cut_boundary_fps.py`
- `core/audio/audio_presets.py`, `core/audio/audio_preset_data.py`, `core/audio/media_processor*.py`
- `core/project/project_manager.py`, `core/project/project_frames.py`, `core/project/project_model_settings.py`
- `core/engine/subtitle_engine.py`, `core/engine/subtitle_settings.py`, `core/engine/subtitle_prompts.py`, `core/engine/subtitle_timing.py`
- `core/pipeline/pipeline_helpers.py`, `core/pipeline/cut_boundary_helpers.py`, `core/pipeline/topicless_segments.py`
- `ui/home_ui.py`, `ui/home_sidebar.py`
- `ui/editor/editor_scan_cut_core.py`, `ui/editor/timeline_scan_cut_*.py`, `ui/editor/video_overlay_widgets.py`, `ui/editor/editor_roughcut_draft.py`
- `ui/roughcut/roughcut_state.py`, `ui/roughcut/roughcut_topicless.py`
- `ui/settings/settings_ai.py`, `ui/settings/settings_roughcut.py`
- `.gitignore`
- 관련 unittest

## 제거 / 정리

- 루트 `config.py`, `logger.py` 삭제. 호환 import는 새 `core/runtime` 경로로 갱신했습니다.
- `core/cut_boundary.py` 내부에서 아래 stable detector에 의해 덮어써지던 중복 grid profile/detector 구현을 제거했습니다.
- `ui/roughcut/roughcut_state.py` 내부의 중복 topicless placeholder fallback 구현을 제거하고 frame-synced installer 구현으로 단일화했습니다.
- `dataset/personalization/`은 로컬 학습/개인화 산출물로 `.gitignore`에 추가했습니다.

## 검증

- `python3 -m compileall -q` 대상 모듈별 검증
- `python3 -m compileall -q main.py core ui tests`
- `./venv/bin/python -m pytest -q` 전체 419 passed
- focused pytest:
  - audio preset/STT preset: 27 passed
  - roughcut state/UI: 10 passed
  - project context/multiclip: 23 passed
  - subtitle engine/STT ensemble/word resegmenter: 41 passed
  - cut-boundary/project/UI cache: 29 passed
- `git diff --check -- . ':(exclude)dataset/video_preview_cache'`
- root forbidden-file scan
- Python AST legacy root `config`/`logger` import scan

## 다음 기준

- 현재 릴리즈 버전: `v03.14.00`
- 다음 코드 수정 버전: `v03.14.01`
