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
