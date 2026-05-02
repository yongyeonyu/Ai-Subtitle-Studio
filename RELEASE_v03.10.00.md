# RELEASE v03.10.00

릴리즈일: 2026-05-02  
Phase: PHASE2  
기준 브랜치: `main`

## 요약

v03.10.00은 v03.09.x 작업을 묶은 PHASE2 릴리즈 체크포인트입니다. STT1/STT2 후보 표시/선택, 자막감지 레인, 타임라인 재생/스크롤 안정화, AI 설정 복원, 앱 종료/홈 이동 런타임 정리, 러프컷 초안 생성 안정화, 최종 자막 간격 적용을 포함합니다.

## 주요 변경

- STT1/STT2 로그와 Transformers 경고 로그를 분리해 앙상블 실행 상태를 읽기 쉽게 했습니다.
- STT1/STT2 후보 레인을 최종 자막세그먼트와 분리하고, 후보를 클릭하면 최종 자막으로 반영되도록 했습니다.
- STT 후보 선택/LLM 선택/자막 점수/확인 필요 상태를 `자막감지` 레인과 후보 레인에서 구분 표시합니다.
- STT 후보와 선택 메타데이터를 단일클립/멀티클립 프로젝트 파일에 저장하고 재열기 때 복원합니다.
- STT 후보 수동 선택은 Undo/Redo 스냅샷에 포함되어 선택 전/선택 후 상태를 왕복할 수 있습니다.
- 최종 자막세그먼트는 STT/LLM/VAD/화자 처리 뒤 `간격` 설정을 마지막 순서로 반영합니다.
- 음성/분석 표시 레인은 읽기 전용으로 처리해 클릭 시 플레이헤드나 화면이 이동하지 않게 했습니다.
- 타임라인 시작은 항상 화면 맞춤으로 열고, 이전 확대/스크롤 저장값은 복원하지 않습니다.
- 재생 중 플레이헤드는 자연스럽게 중앙에 도달한 뒤 고정되고, 휠 스크롤 시 자동 중앙 고정이 잠깐 양보합니다.
- AI 설정에서 API 키, Hugging Face 토큰, Whisper/LLM 모델 다운로드 진입점을 복원했습니다.
- 앱 시작 시 Ollama 자동 시작, 홈 이동/앱 종료 시 STT/LLM/ffmpeg/Ollama 런타임 정리를 강화했습니다.
- ClearVoice/Resemble Enhance 실행 중 heartbeat 로그를 표시해 장시간 처리 상태를 확인할 수 있게 했습니다.
- 긴 영상 러프컷 초안은 LLM 입력 제한을 넘으면 로컬 러프컷 세그먼트를 즉시 생성합니다.
- 사용하지 않는 Whisper/Core ML 모델 항목을 드롭다운과 설치 레지스트리에서 제거했습니다.

## 영향 범위

- 기존 자막 생성, 편집, 저장, 멀티클립, 러프컷 흐름은 유지합니다.
- `자막감지`는 기존 `voice_activity_segments` 저장 경로와 호환되지만 schema는 `subtitle_detection.v1`로 기록됩니다.
- STT1/STT2 후보 레인은 선택 전용이며 길이 조정/다이아몬드 조작은 최종 자막세그먼트에만 적용됩니다.
- 최종 간격 패스는 자막세그먼트 timing만 조정하며 후보 레인이나 표시 전용 분석 레인은 편집 가능한 자막으로 바꾸지 않습니다.
- 멀티클립 간격 조정은 클립 경계를 침범하지 않도록 clip scope를 유지합니다.
- `dataset/video_preview_cache/`, `checkpoints/`, `.codex_work/`는 로컬 산출물/작업 메모이며 릴리즈 커밋 대상에서 제외합니다.
- requirements 변경은 없습니다.

## 검증

- `venv/bin/python -m py_compile config.py ui/editor/undo_manager.py ui/editor/editor_segments.py tests/test_project_segment_reload.py`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_project_segment_reload`
  - 9 tests passed
- `venv/bin/python -m py_compile config.py core/engine/subtitle_engine.py core/pipeline/single_pipeline.py core/pipeline/multiclip_pipeline.py core/backend_fast.py ui/editor/editor_segments.py tests/test_subtitle_engine_settings.py`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_subtitle_engine_settings tests.test_stt_ensemble tests.test_project_segment_reload tests.test_timeline_hit_targets tests.test_timeline_segment_colors`
  - 60 tests passed
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_project_segment_reload tests.test_timeline_hit_targets tests.test_timeline_segment_colors tests.test_project_context`
  - 53 tests passed
- `venv/bin/python -m py_compile config.py main.py core/engine/subtitle_engine.py core/pipeline/stt_preview_optimizer.py core/pipeline/single_pipeline.py core/pipeline/multiclip_pipeline.py core/backend_fast.py ui/editor/undo_manager.py ui/editor/editor_segments.py ui/timeline/timeline_paint.py ui/timeline/timeline_input.py ui/timeline/timeline_widget.py tests/test_project_segment_reload.py tests/test_subtitle_engine_settings.py tests/test_stt_preview_optimizer.py tests/test_whisper_model_catalog.py`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_project_segment_reload tests.test_timeline_hit_targets tests.test_timeline_segment_colors tests.test_project_context tests.test_subtitle_engine_settings tests.test_stt_ensemble tests.test_stt_preview_optimizer tests.test_whisper_model_catalog`
  - 83 tests passed
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_editor_roughcut_draft tests.test_roughcut_ui_v2 tests.test_sidebar_terminal_layout tests.test_ollama_provider tests.test_video_player_widget tests.test_cp08_cp10_home_timeline tests.test_timeline_playhead_fit tests.test_media_processor_overlap`
  - 109 tests passed
- `git diff --check -- . ':(exclude)dataset/video_preview_cache' ':(exclude)checkpoints'`

## 이전 릴리즈

- `RELEASE_v03.09.00.md`
- `RELEASE_v03.08.00.md`
- `RELEASE_v03.07.00.md`
- `RELEASE_v03.06.00.md`
