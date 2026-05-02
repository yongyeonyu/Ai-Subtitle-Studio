<!--
Document-Version: 03.09.00
Phase: PHASE2
Last-Updated: 2026-05-02
Updated-By: Codex with 대표님
Previous-Release: v03.08.00
-->
# RELEASE v03.09.00

## 핵심 요약
- v03.08.01부터 v03.08.12까지의 STT 로그, 실시간 STT preview, Core ML STT 실험, Ollama 안정화, 저장 race, 앱 종료 runtime cleanup 핫픽스를 v03.09.00 릴리즈로 고정했습니다.
- STT1/STT2 병렬 실행 중 진행률과 worker stderr 경고가 어느 STT 경로에서 나온 로그인지 구분됩니다.
- STT 청크가 확정되는 즉시 타임라인/글로벌 캔버스에 임시 자막 세그먼트를 표시합니다.
- 로컬 Ollama 요청 과부하를 줄이고, 앱 종료 시 Ollama/ffmpeg/STT worker가 메모리에 남지 않도록 종료 cleanup을 강화했습니다.

## STT / VAD / 진행률
- FFMPEG 전처리 진행률은 같은 퍼센트를 반복 출력하지 않고 실제 증가한 1% 단위만 표시합니다.
- VAD 후처리는 모델 준비, 오디오 로드, 오디오 분석, 음성 구간 정리 단계와 TEN VAD 10% 단위 진행률, Silero 장시간 heartbeat를 표시합니다.
- STT 앙상블 진행률 로그와 Transformers/faster-whisper worker stderr 경고에 `[STT1]`/`[STT2]` 라벨을 붙였습니다.
- STT worker가 청크 세그먼트를 확정하면 LLM 최종화 전에도 캔버스에 임시 세그먼트를 보여줍니다.

## Core ML STT 실험
- AI 설정에 `coreml:large-v3-v20240930_626MB (실험)` 선택지를 추가했습니다.
- macOS에서 WhisperKit/Core ML CLI를 우선 시도하고, 사용할 수 없으면 기존 MLX Whisper로 자동 fallback합니다.
- Core ML 경로는 실험 옵션이며, 정밀 word timestamp가 필요한 작업은 기존 MLX/Transformers 경로 유지가 안전합니다.

## LLM / Ollama 안정화
- Ollama 종료 로그가 홈 이동과 에디터 모드 메모리 정리를 구분해 표시됩니다.
- 로컬 Ollama 자막 분할 worker를 기본 2개로 제한해 `gemma4:e4b` 같은 로컬 모델의 timeout 반복을 줄였습니다.
- 설정값 `local_ollama_llm_max_workers`를 추가했으며 기본값은 `2`입니다.

## 저장 / 앱 종료 안정성
- 자막 생성 완료 직후 저장/완료 판정이 먼저 실행될 때 pending 세그먼트 큐를 즉시 flush해 `저장할 자막 세그먼트가 없습니다` race를 줄였습니다.
- macOS 자식 Python worker 환경에서 `MallocStackLogging*` 계열 변수를 제거해 worker 로그 잡음을 줄였습니다.
- 앱 시작/종료 시 이전 버전에서 남긴 legacy preview-cache ffmpeg 인코더를 정리합니다.
- 앱 종료 시 Ollama 실행 모델을 언로드하고 Ollama server/runner, 앱 소유 ffmpeg/ffprobe/STT worker를 종료합니다.

## 에디터 UI
- 자막 편집 영역 위 고정 표 헤더(`#`, `시작 시간`, `종료 시간`, `화자`, `자막`)를 화면에서 제거했습니다.
- 타임스탬프/화자 조작 영역과 자막 편집 본문은 유지됩니다.

## 제거 / 영향 범위
- 이번 릴리즈에서 공개 `def`, `class`, helper, UI action, signal, slot을 삭제한 변경은 없습니다.
- `dataset/video_preview_cache/`, `checkpoints/`, `.codex_work/`는 로컬 산출물/작업 메모이며 릴리즈 커밋 대상에서 제외합니다.
- requirements 변경은 없습니다.

## 검증
- `venv/bin/python -m py_compile main.py config.py core/platform_compat.py ui/editor/editor_lifecycle.py tests/test_windows_platform_compat.py`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_windows_platform_compat tests.test_video_player_widget tests.test_project_segment_reload tests.test_cp03_cp04_status_ui`
- `git diff --check -- . ':(exclude)dataset/video_preview_cache' ':(exclude)checkpoints'`
