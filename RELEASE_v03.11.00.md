# RELEASE v03.11.00

릴리즈일: 2026-05-03  
Phase: PHASE2  
기준 브랜치: `main`  
이전 릴리즈: `v03.10.00`

## 요약

v03.11.00은 v03.10.x 이후의 편집기 안정화, STT preview 최적화, 자막 편집 UX 보정, 타임라인/비디오 동기화 보정, 그리고 1프레임 이동 안정화 작업을 묶은 PHASE2 릴리즈 체크포인트입니다.

## 주요 변경

- 비디오 플레이어의 1프레임 이동 계산을 `현재 시간 + 1/fps` 방식에서 `현재 프레임 번호 ± 1` 방식으로 정리했습니다.
- float 오차로 인해 이전/다음 프레임 이동이 씹히거나 같은 프레임에 머무를 수 있는 문제를 줄였습니다.
- 프레임 이동 버튼/화살표 조작 중 다른 클립으로 자동 진입하지 않도록 클립 경계 정지 정책을 적용했습니다.
- 기존 비디오 재생/seek 흐름은 유지하면서, 같은 소스 안에서는 `frame_step_seek()` 경로를 우선 사용합니다.
- STT preview optimizer, subtitle engine settings, timeline playhead fit, subtitle text edit key handling 관련 테스트 변경을 포함합니다.
- 같은 클립 내부의 픽셀 변화량 기반 hard-cut 정지는 다음 v03.11.x 작업 후보로 분리했습니다.
- `v03.11.16`: 컷 경계 `사용` 시 저장된 화면 분석 컷을 절대 경계로 취급해 최종 자막과 STT1/STT2 후보가 경계를 관통하지 않도록 분할하고, 프로젝트/멀티클립 editor_state에 같은 컷 정보를 동기화합니다.

## 영향 범위

- `ui/editor/editor_timeline_video.py`
- `ui/editor/*`
- `ui/timeline/*`
- `core/audio/*`
- `core/engine/*`
- `core/pipeline/*`
- `core/cut_boundary.py`
- `core/project/*`
- `tests/*`
- `config.py`

## 검증 권장

- `python3 -m py_compile config.py ui/editor/editor_timeline_video.py`
- `python3 -m pytest tests/test_stt_preview_optimizer.py tests/test_subtitle_engine_settings.py tests/test_subtitle_text_edit_keys.py tests/test_timeline_playhead_fit.py`

## 다음 후보 작업

- 같은 클립 내부 hard cut 구간에서 픽셀 변화량을 기준으로 프레임 이동을 멈추는 guard 추가
- scene-change 후보 cache를 프레임 이동 UX와 연결
- 컷 경계 정지 threshold를 AI 설정 또는 개발자 설정으로 노출
