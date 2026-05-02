<!--
Document-Version: 03.08.00
Phase: PHASE2
Last-Updated: 2026-05-02
Updated-By: Codex with 대표님
Previous-Release: v03.07.00
-->
# RELEASE v03.08.00

## 핵심 요약
- v03.07.01부터 v03.07.10까지의 안정성, 전처리, 상태 표시, 에디터, 사이드바 핫픽스를 v03.08.00 릴리즈로 고정했습니다.
- macOS 실행 안정성을 위해 공격적인 Qt OpenGL widget 치환은 명시적 opt-in으로 되돌리고, 기본 실행은 안전한 QWidget 경로를 사용합니다.
- 자막 생성 상태 표시와 사이드바 단계표는 공용 parser를 통해 같은 단계명을 사용합니다.
- 대용량 영상 전처리는 오디오 전용 FFMPEG map, 진행률 표시, 단일 패스 정제/cache, 직접 STT chunk 추출 경로를 포함합니다.
- 자막 에디터 상단 toolbar를 제거하고, 사이드바 큐 리스트가 확보된 공간을 더 크게 사용하도록 정리했습니다.

## 실행 안정성
- `Segmentation fault: 11` 위험이 있던 기본 QOpenGLWidget 치환 경로를 기본 비활성화했습니다.
- 전역 Qt OpenGL 강제 설정은 `AI_SUBTITLE_FORCE_QT_OPENGL=1`, custom OpenGL widget 치환은 `AI_SUBTITLE_EXPERIMENTAL_OPENGL_WIDGETS=1`일 때만 활성화됩니다.
- 에디터 모드의 AI/STT/LLM 메모리 회수는 backend나 pipeline이 실제로 실행 중일 때 차단되어 자막 생성 작업을 중간에 끊지 않습니다.

## 상태 표시 / 사이드바
- `core/pipeline_status.py`를 추가해 `전처리`, `음성`, `STT 1`, `STT 2`, `VAD`, `자막 LLM`, `러프컷 LLM` 판정을 공용화했습니다.
- 생성 중 상단 status rail이 `에디터 | VAD`처럼 화면 모드를 앞세우지 않고 `자막 생성 | 전처리/VAD/인식/보정` 흐름을 표시합니다.
- 사이드바 단계표와 StateManager의 진행 상태 보호도 같은 parser를 사용합니다.
- 홈/에디터/러프컷/숏폼 네비게이션 버튼 높이를 줄이고, 큐 리스트 패널의 최대 높이 제한을 제거해 남은 세로 공간을 큐 테이블이 사용합니다.

## 대용량 전처리
- FFMPEG 전처리는 `-map 0:a:0 -vn -sn -dn`으로 첫 번째 오디오 스트림만 명시적으로 읽습니다.
- 긴 영상 전처리 중 `-progress pipe:1` 기반 퍼센트 로그를 표시해 앱이 멈춘 것처럼 보이지 않도록 했습니다.
- 외부 음성 향상 모델이 필요 없는 경로는 `raw.wav -> cleaned.wav` 2패스를 단일 패스 추출/정제로 합쳤습니다.
- 같은 원본/설정이면 검증된 cleaned audio cache를 재사용합니다.
- VAD 후처리와 다중 화자 분석이 필요 없는 긴 단일 화자 작업은 전체 `cleaned.wav` 생성을 건너뛰고 원본에서 STT용 16k mono PCM chunk를 직접 추출할 수 있습니다.

## 에디터 / 비디오
- 원본 영상을 720p proxy mp4로 캐시 인코딩한 뒤 갈아타던 기본 경로를 제거하고, 원본 파일을 그대로 재생하면서 표시 영역만 720p 기준으로 제한합니다.
- 자막 목록 상단 mode/filter/search toolbar를 화면에서 제거해 표 헤더가 바로 보이도록 했습니다.
- toolbar 없이도 품질 검사/자동 교정 경로가 안전하게 동작하도록 자동 교정 체크박스 의존성을 방어했습니다.
- 비디오 subtitle overlay와 provider 갱신은 재생 중 불필요하게 반복되지 않도록 유지합니다.

## 문서 / 운영 규칙
- `File_structure.txt`는 `←` role marker 앞에 최소 탭 2개를 두도록 정렬했습니다.
- 앞으로 `File_structure.txt`에 새로 쓰거나 수정하는 파일 역할 설명은 영어로 작성합니다.
- 대표님이 `전체 리팩토링`을 명시하면, 사용하지 않는 파일/함수/클래스/helper/UI action/signal/slot은 검증 후 `.codex_work/refactor_backup_{YYYY-MM-DD}/`에 백업하고 프로젝트에서는 삭제하는 규칙을 추가했습니다.

## v03.08.01 전처리 진행률 로그 핫픽스
- FFMPEG 전처리 진행률 로그가 같은 퍼센트를 시간 간격에 따라 반복 출력하던 문제를 수정했습니다.
- 진행률은 명령 시작 시 0%를 한 번 출력하고, 이후 실제 퍼센트가 증가할 때만 1% 단위로 출력합니다.
- 같은 라벨의 다음 FFMPEG 명령이 시작되면 진행률 상태를 리셋해 새 명령의 0%부터 다시 표시합니다.

## v03.08.02 VAD 후처리 진행 상태 핫픽스
- VAD 후처리의 모델 준비, 오디오 로드, 오디오 분석, 음성 구간 정리 단계를 로그와 상단 상태에 표시합니다.
- TEN VAD는 오디오 스캔 중 10% 단위 진행률을 표시해 긴 파일에서도 멈춘 것처럼 보이지 않게 했습니다.
- Silero VAD처럼 내부 분석 진행률을 직접 알 수 없는 경로는 분석이 길어질 때 주기적으로 `진행 중... N초` heartbeat를 표시합니다.

## v03.08.03 STT 진행률 로그 분리 핫픽스
- STT 앙상블 병렬 실행 중 같은 `진행 상황` 로그가 섞여 보이던 문제를 줄이기 위해 진행률 로그에 `[STT1]`/`[STT2]` 라벨을 붙였습니다.
- 기존 시작/완료 로그의 STT 라벨과 같은 `log_label`을 진행률에도 재사용해 단일 STT와 STT 앙상블 경로가 같은 형식을 따릅니다.

## v03.08.04 STT worker 경고 로그 분리 핫픽스
- Transformers Whisper worker와 Windows faster-whisper worker의 stderr 경고 로그도 `[STT1]`/`[STT2]` 라벨을 붙여 표시합니다.
- `Whisper did not predict an ending timestamp` 같은 Transformers 경고가 병렬 STT 로그 사이에 섞여도 어느 STT 모델의 경고인지 구분할 수 있습니다.

## v03.08.05 STT 세그먼트 실시간 캔버스 표시 핫픽스
- STT worker가 청크 세그먼트를 확정하는 즉시 타임라인/글로벌 캔버스에 임시 세그먼트를 표시합니다.
- 단일 STT와 멀티클립 STT 모두 같은 라이브 미리보기 신호를 사용하며, STT 앙상블은 STT1 청크를 우선 미리보기로 표시합니다.
- LLM 최종 세그먼트가 도착하면 겹치는 임시 STT 미리보기 세그먼트를 제거하고 기존 확정 자막 append 흐름으로 교체합니다.

## v03.08.06 자막 에디터 헤더 제거 핫픽스
- 자막 편집 영역 위의 고정 표 헤더(`#`, `시작 시간`, `종료 시간`, `화자`, `자막`)를 화면에서 제거했습니다.
- 타임스탬프/화자 조작 영역과 자막 편집 본문은 그대로 유지합니다.

## v03.08.07 macOS Core ML STT 실험 백엔드
- AI 설정의 Whisper 모델 목록에 `coreml:large-v3-v20240930_626MB (실험)` 선택지를 추가했습니다.
- macOS에서 해당 모델을 선택하면 WhisperKit/Core ML CLI 백엔드를 우선 시도합니다.
- WhisperKit CLI가 설치되어 있지 않거나 worker 시작 준비에 실패하면 로그에 fallback 사유를 표시하고 기존 MLX Whisper로 자동 대체합니다.
- Core ML 경로는 아직 실험 옵션이며, 현재 통합은 청크 단위 텍스트 세그먼트 우선입니다. 정밀 word timestamp가 필요한 작업은 기존 MLX/Transformers 경로를 유지하는 것이 안전합니다.

## v03.08.08 Ollama 종료 로그 문맥 분리
- 자막 생성 완료 후 에디터 메모리 정리 루틴에서 Ollama 모델을 언로드할 때 `홈 이동`으로 표시되던 로그 문구를 `에디터 모드`로 분리했습니다.
- 실제 홈 이동으로 작업을 중단하는 경우에는 기존 `홈 이동` 문맥 로그를 유지합니다.

## v03.08.09 로컬 Ollama LLM timeout 완화
- 로컬 Ollama 자막 분할은 기본 최대 2개 worker로 제한해 `gemma4:e4b` 같은 로컬 모델에 요청이 과도하게 몰리는 문제를 줄였습니다.
- API 모델은 기존처럼 1개 worker 안전 모드를 유지합니다.
- 설정값 `local_ollama_llm_max_workers`를 추가했으며 기본값은 `2`입니다.

## v03.08.10 저장 직전 세그먼트 큐 flush / macOS worker 로그 억제
- 자막 생성 완료 직후 저장/완료 판정이 먼저 실행될 때 pending 세그먼트 큐를 즉시 flush해 `저장할 자막 세그먼트가 없습니다`가 뜨는 순간 race를 줄였습니다.
- macOS 자식 Python worker 환경에서 `MallocStackLogging*` 계열 변수를 제거해 `can't turn off malloc stack logging` 잡음이 앱 로그에 반복 표시되지 않게 했습니다.

## v03.08.11 고아 preview ffmpeg 정리 핫픽스
- 앱 시작/종료 시 이전 버전에서 남긴 `dataset/video_preview_cache/*_preview_720p.mp4.tmp.mp4` 대상 ffmpeg 인코더만 골라 종료합니다.
- 일반 렌더링, 전처리, STT용 ffmpeg 작업은 건드리지 않도록 프로젝트 preview cache 경로와 legacy 임시 파일명 패턴을 함께 확인합니다.

## v03.08.12 앱 종료 런타임 정리 강화
- 앱 종료 시 Ollama 실행 모델을 동기적으로 언로드하고, Ollama server/runner 프로세스까지 종료합니다.
- 앱 프로세스의 heavy child process(ffmpeg/ffprobe/STT worker/Ollama runner)도 함께 종료합니다.
- 종료 직전 `aboutToQuit`와 `closeEvent` 양쪽에서 cleanup을 호출해 빠른 `os._exit` 전에 메모리 회수 요청이 끝나도록 했습니다.

## 제거 / 영향 범위
- 이번 릴리즈에서 공개 `def`, `class`, helper, UI action, signal, slot을 삭제한 변경은 없습니다.
- 자막 에디터 상단 toolbar는 화면에서 제거했지만, 관련 품질 검사 경로는 다른 호출 지점에서도 안전하게 유지됩니다.
- `dataset/video_preview_cache/`, `checkpoints/`, `.codex_work/`는 로컬 산출물/작업 메모이며 릴리즈 커밋 대상에서 제외합니다.
- requirements 변경은 없습니다.

## 검증
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s tests`
  - exit code 0
- module-by-module unittest sweep
  - `MODULE_SWEEP_OK: 47 modules`
- Python AST 검사
  - `AST OK: 231 files`
- offscreen UI smoke
  - `UI smoke OK`
- `git diff --check -- . ':(exclude)dataset/video_preview_cache' ':(exclude)checkpoints'`
  - exit code 0
- `python3.11 -m pip check`
  - `No broken requirements found.`
- 루트 금지 파일 검사
  - 금지 파일 없음
