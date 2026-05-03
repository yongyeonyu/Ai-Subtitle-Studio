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

- `config.py`
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

- 현재 릴리즈 버전: `v03.13.00`
- 다음 코드 수정 버전: `v03.13.01`
