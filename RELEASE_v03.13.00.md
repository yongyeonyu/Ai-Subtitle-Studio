# RELEASE v03.13.00

릴리즈일: 2026-05-03
Phase: PHASE2
기준 브랜치: `main`
이전 릴리즈: `v03.12.00`

## 요약

v03.13.00은 컷 경계/프레임 기준 동기화, 자동 오디오/정밀인식 판정, 텍스트 LoRA 개인화 축적, 설정 UI 단순화, 그리고 안전한 구조 분리를 한 번에 묶은 PHASE2 릴리즈 체크포인트입니다. 자막 생성 본선은 정식 컷 경계를 더 엄격하게 따르도록 정리했고, 개인화 데이터는 앱을 사용할수록 누적되도록 바뀌었습니다. 동시에 홈 사이드바와 멀티클립 패널 일부를 분리해 다음 리팩토링을 위한 기반도 깔았습니다.

## 주요 변경

- 정식 컷 경계를 자막/STT의 절대 기준으로 더 강하게 적용하고, 자막 세그먼트 끝점과 시작점이 씬 경계에 프레임 단위로 더 정확히 붙도록 보강했습니다.
- 컷 경계/타임라인/프로젝트 저장 경로를 프레임 우선 기준으로 다시 묶어서, 초 단위 파생값보다 프레임 timebase가 먼저 쓰이도록 정리했습니다.
- 오디오 프리셋을 `실내/실외/차안 x 마이크 유/무` 6종으로 단순화하고, 영상 `1/3` 지점 주변 후보 구간을 비교해 오디오 프리셋과 정밀인식 프리셋을 함께 맞추는 자동 판정 흐름을 추가했습니다.
- 오디오 프리셋을 고르면 컷 경계, 전처리, 음성 필터, STT1/STT2, VAD, 자막 LLM, 러프컷 LLM 추천값까지 같이 적용되도록 연결했습니다.
- 텍스트 LoRA 데이터셋은 교정사전, correction memory, wrong-answer memory뿐 아니라 실제 `STT 선택본 -> 최종 자막` pair를 계속 누적하는 코퍼스로 고도화했습니다.
- 텍스트 LoRA 누적 코퍼스와 별도로 `speaker / clip_path / start_frame / end_frame / text`를 쌓는 음성 LoRA 브리지 manifest 구조를 추가해 이후 음성 LoRA 학습기로 이어질 뼈대를 마련했습니다.
- 설정창은 `에디터 LLM / 러프컷 LLM / AI` 3탭 중심으로 정리했고, 빠른설정/중복 STT2·VAD·음성 AI 항목과 설정창 안 자동 오디오 판정 UI 같은 중복 진입점을 줄였습니다.
- 홈 사이드바 프리셋 동기화 로직을 `ui/home_sidebar_presets.py`로 분리했고, 멀티클립 카드/드래그 UI를 `ui/project/multiclip_cards.py`로 분리해 큰 파일을 줄였습니다.
- 루트에 남아 있던 리팩토링용 `patch_backups/` 산출물은 `.codex_work/refactor_backup_2026-05-03/files/patch_backups/`로 이동하고 제품 트리에서는 제거했습니다.
- Ollama 500 계열 오류에 대한 재시도 복구를 넣고, ffmpeg progress 파서를 `out_time_us`까지 이해하도록 보강해 전처리 실패 오판을 줄였습니다.

## 제거 / 정리

- 설정창 `빠른설정` 탭 제거
- 설정창 `AI` 탭의 사이드바와 중복되는 STT2/VAD/음성 AI 관련 UI 제거
- 설정창 `러프컷 LLM` 탭의 중복 오디오 자동 판정 UI 제거
- 루트 `patch_backups/` 산출물 제거 후 `.codex_work` 백업으로 이동
- 루트 `fix_app_command_use_venv.py`, `cut_boundary_menu_report.txt` 제거

## 영향 범위

- `core/runtime/config.py`
- `core/runtime/logger.py`
- `core/audio/audio_presets.py`
- `core/audio/media_processor.py`
- `core/audio/preset_auto_classifier.py`
- `core/audio/stt_quality_presets.py`
- `core/cut_boundary.py`
- `core/engine/subtitle_engine.py`
- `core/llm/ollama_provider.py`
- `core/performance.py`
- `core/personalization/text_lora_dataset.py`
- `core/personalization/text_lora_runner.py`
- `core/pipeline/*`
- `core/project/project_manager.py`
- `core/state_manager.py`
- `core/subtitle_quality/timestamp_regrouper.py`
- `ui/home_ui.py`
- `ui/home_sidebar_presets.py`
- `ui/menu_bar.py`
- `ui/project/multiclip_cards.py`
- `ui/project/multiclip_panel.py`
- `ui/settings/settings_ai.py`
- `ui/settings/settings_gap.py`
- `ui/settings/settings_personalization.py`
- `ui/main/main_window.py`
- `ui/main/main_signals.py`
- `ui/editor/*`
- `ui/timeline/*`
- `tests/test_audio_presets.py`
- `tests/test_preset_auto_classifier.py`
- `tests/test_text_lora_dataset.py`
- `tests/test_pipeline_cut_boundary_cache.py`
- `tests/test_word_resegmenter.py`

## 검증

- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s tests`
- Python AST scan
- `QT_QPA_PLATFORM=offscreen venv/bin/python - <<'PY' ... UI smoke ... PY`
- `git diff --check -- . ':(exclude)dataset/video_preview_cache'`
- root forbidden-file scan

## 다음 기준

- 현재 릴리즈 버전: `v03.14.00`
- 다음 코드 수정 버전: `v03.14.01`

## v03.13.01 Hotfix Note

- macOS에서 앱 시작 직후 Qt/OpenGL GPU carveout 영역 `SIGSEGV`가 발생할 수 있어, Qt OpenGL/QOpenGLWidget 렌더링 경로를 다시 명시 opt-in으로 전환했습니다.
- 기본 렌더링은 안정적인 QWidget 경로를 사용하고, GPU 렌더링 실험은 `AI_SUBTITLE_GPU_RENDERING=1` 및 `AI_SUBTITLE_EXPERIMENTAL_OPENGL_WIDGETS=1` 또는 `AI_SUBTITLE_FORCE_QT_OPENGL=1`을 명시했을 때만 활성화됩니다.

## v03.13.02 Refactor Note

- 루트 `config.py` / `logger.py`를 `core/runtime/config.py` / `core/runtime/logger.py`로 이동하고 전체 Python import를 새 runtime package 기준으로 갱신했습니다.
- `core/pipeline/pipeline_helpers.py` 하단의 cut-boundary topicless segment patch block을 `core/pipeline/topicless_segments.py`로 분리했습니다.
- `ui/editor/editor_timeline_video.py` 하단의 scan-cut relative/strong-window/resume patch block을 `ui/editor/timeline_scan_cut_patches.py`로 분리했습니다.
- 검증: `python3 -m compileall -q main.py core ui tests`, `./venv/bin/python -m pytest -q` 전체 419개 통과.

## v03.13.03 Refactor Note

- `core/cut_boundary.py` 후반 auto grid cut-boundary scan/provisional verify/5x5 profile installer block을 `core/cut_boundary_auto.py`로, FPS-aware normalize/project sync override block을 `core/cut_boundary_fps.py`로 분리했습니다.
- `core/audio/media_processor.py`의 audio command, preprocessing, cache, heartbeat, hard-cut chunk helper 묶음을 `core/audio/media_processor_audio.py` mixin으로, VAD detection/retry/activity/chunking 묶음을 `core/audio/media_processor_vad.py` mixin으로 분리했습니다.
- `ui/home_ui.py`의 sidebar queue/preset/model/status/settings helper 묶음을 `ui/home_sidebar.py` mixin으로 분리했습니다.
- 기존 테스트/패치 호환성을 위해 `core.audio.media_processor.get_logger` 및 `ui.home_ui.load_settings/save_settings` patch entry point는 새 helper module에서도 유지했습니다.

## v03.13.04 Refactor Note

- `ui/editor/editor_timeline_video.py`의 scan-cut capture/preview/threshold/save/timer core helper 묶음을 `ui/editor/editor_scan_cut_core.py` mixin으로 분리했습니다.
- `ui/editor/video_player_widget.py`의 thumbnail label, graphics video surface, subtitle overlay painting/widget 묶음을 `ui/editor/video_overlay_widgets.py`로 분리했습니다.
- `ui/settings/settings_ai.py`의 roughcut LLM controls와 roughcut setting collection helper를 `ui/settings/settings_roughcut.py` mixin으로 분리했습니다.

## v03.13.05 Refactor Note

- `ui/editor/timeline_scan_cut_patches.py`를 installer orchestrator로 축소하고 relative base/refine/resume 단계를 `timeline_scan_cut_relative_base.py`, `timeline_scan_cut_relative_refine.py`, `timeline_scan_cut_resume.py`로 분리했습니다.
- `ui/editor/editor_segments.py`의 post-generation roughcut draft scheduling, LLM/local fallback, project save, roughcut widget refresh helper 묶음을 `ui/editor/editor_roughcut_draft.py` mixin으로 분리했습니다.

## v03.13.06 Refactor Note

- `core/pipeline/pipeline_helpers.py`의 cut-boundary cache, prescan, topicless placeholder, split, and snap helper 묶음을 `core/pipeline/cut_boundary_helpers.py` mixin으로 분리했습니다.
- `PipelineHelpersMixin`은 VAD alignment, backup/save/render/prefetch 계열 공통 헬퍼에 집중하도록 축소하고, 기존 topicless patch installer 호환 경로는 유지했습니다.

## v03.13.07 Refactor Note

- `core/cut_boundary_auto.py`를 auto grid cut-boundary installer orchestrator로 축소하고 profile, utility, strict verify, pioneer/follower scan helper builder를 별도 모듈로 분리했습니다.
- `install_auto_grid_v3(globals())` 호환 진입점과 기존 namespace export 이름은 유지했습니다.

## v03.13.08 Refactor Note

- `core/audio/media_processor.py`의 Whisper transcription, STT ensemble, low-score recheck, payload parsing, and overlap de-dup helper 묶음을 `core/audio/media_processor_transcribe.py` mixin으로 분리했습니다.
- `VideoProcessor`는 transcription, audio helper, VAD helper mixin을 조립하는 구조를 유지하며 기존 public method 이름은 유지했습니다.

## v03.13.09 Refactor Note

- `core/audio/audio_presets.py`에서 curated/default preset data를 `core/audio/audio_preset_data.py`로 분리했습니다.
- `ui/roughcut/roughcut_state.py`의 frame-synced topicless placeholder installer를 `ui/roughcut/roughcut_topicless.py`로 분리하고 중복 fallback 구현을 제거했습니다.
- `core/project/project_manager.py`에서 frame metadata 증강과 model settings snapshot/restore helper를 `core/project/project_frames.py`, `core/project/project_model_settings.py`로 분리했습니다.
- `core/engine/subtitle_engine.py`에서 settings, prompt, timing helper를 `core/engine/subtitle_settings.py`, `core/engine/subtitle_prompts.py`, `core/engine/subtitle_timing.py`로 분리했습니다.
- `core/cut_boundary.py`에서 최종 stable detector에 의해 덮어써지던 중복 grid profile/detector 구현을 제거했습니다.
