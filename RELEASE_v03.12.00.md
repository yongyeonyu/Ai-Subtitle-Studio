# RELEASE v03.12.00

릴리즈일: 2026-05-03  
Phase: PHASE2  
기준 브랜치: `main`  
이전 릴리즈: `v03.11.00`

## 요약

v03.12.00은 컷 경계 기반 작업 흐름을 실제 STT 파이프라인의 절대 기준으로 연결한 PHASE2 릴리즈 체크포인트입니다. 선발대/후발대 컷 탐색, 임시/확정 경계 저장, 주제없음 중분류 placeholder, STT1/STT2 후보 스냅과 수동 선택, 재시작 초기화, 사이드바 상태 표현까지 한 흐름으로 정리했습니다.

## 주요 변경

- 컷 경계 `사용` 시 시작 전에 선발대가 전체 영상을 빠르게 스캔하고, 후발대가 백그라운드에서 검증하는 2단계 컷 경계 파이프라인을 추가했습니다.
- 선발대 임시 경계와 후발대 확정 경계를 모두 프로젝트 파일과 `editor_state`에 저장하고, 단일/멀티클립에서 같은 스키마로 복원합니다.
- 회색 `주제없음` 중분류 세그먼트를 컷 경계 placeholder로 생성하고, 타임라인에는 중분류 세그먼트 안쪽 경계선만 표시하도록 정리했습니다.
- STT1/STT2 preview 후보와 최종 자막은 저장된 임시/확정 컷 경계 근처에서 스냅되고, 확정 컷 경계는 자막이 절대 관통하지 않도록 유지합니다.
- STT1/STT2 후보 수동 선택은 겹치는 최종 자막을 후보 시간대 기준으로 잘라 교체하며, STT1↔STT2 전환도 Undo/Redo 스냅샷에 포함됩니다.
- 재시작 시 회색 중분류 세그먼트, 임시 컷 경계, 확정 컷 경계, 프로젝트 `analysis/editor_state` 컷 데이터까지 모두 비우고 처음 상태로 리셋합니다.
- 사이드바 버튼은 열려 있을 때 초록 아이콘, 닫혀 있을 때 기본 회색 아이콘으로 상태가 드러나도록 조정했습니다.
- Whisper 입력 청크는 확정 컷 경계를 hard cut으로 사용하고, 특히 VAD 없는 fallback 경로에서도 컷 경계에서 청크를 다시 시작하도록 맞췄습니다.

## 영향 범위

- `core/cut_boundary.py`
- `core/audio/media_processor.py`
- `core/pipeline/single_pipeline.py`
- `core/pipeline/multiclip_pipeline.py`
- `core/pipeline/pipeline_helpers.py`
- `core/pipeline/stt_preview_optimizer.py`
- `core/project/project_context.py`
- `core/project/project_manager.py`
- `ui/editor/editor_pipeline.py`
- `ui/editor/editor_segments.py`
- `ui/editor/editor_timeline_video.py`
- `ui/main/main_window.py`
- `ui/main/main_signals.py`
- `ui/menu_bar.py`
- `ui/timeline/*`
- `tests/test_cp03_cp04_status_ui.py`
- `tests/test_media_processor_overlap.py`
- `tests/test_project_context.py`
- `tests/test_project_segment_reload.py`
- `tests/test_stt_preview_optimizer.py`

## 검증

- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s tests`
- Python AST scan
- `QT_QPA_PLATFORM=offscreen venv/bin/python - <<'PY' ... UI smoke ... PY`
- `git diff --check -- . ':(exclude)dataset/video_preview_cache'`
- root forbidden-file scan

## 다음 기준

- 현재 릴리즈 버전: `v03.12.00`
- 다음 코드 수정 버전: `v03.12.01`
