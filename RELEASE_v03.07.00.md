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

## v03.07.01 안정성 핫픽스
- macOS에서 여러 `QOpenGLWidget` 기반 timeline/text/video viewport를 동시에 기본 활성화하면 Qt 멀티미디어 경로와 충돌해 `Segmentation fault: 11`로 종료될 수 있어 기본 실행은 안정적인 QWidget 경로로 되돌렸습니다.
- 전역 Qt OpenGL 강제 설정은 `AI_SUBTITLE_FORCE_QT_OPENGL=1`, 커스텀 OpenGL widget 치환은 `AI_SUBTITLE_EXPERIMENTAL_OPENGL_WIDGETS=1`일 때만 켜집니다.
- 비디오 플레이어 자체의 Qt 멀티미디어/GPU 가속 경로와 frame-map 기반 동기화 코드는 유지합니다.

## v03.07.02 상태 표시 핫픽스
- 자막 생성 중 상단 status rail이 화면 모드인 `에디터`를 우선 표시해 `에디터 | VAD`처럼 보이던 문제를 수정했습니다.
- 생성 중에는 상태 머신의 처리 모드를 우선해 `자막 생성 | VAD/인식/보정`으로 표시합니다.

## v03.07.03 비디오 프리뷰 핫픽스
- 원본 영상을 720p 프록시 mp4로 인코딩해 `dataset/video_preview_cache/`에 저장한 뒤 갈아타던 경로를 기본 실행에서 제거했습니다.
- 비디오 플레이어는 원본 파일을 그대로 재생하고, 프리뷰 표시 영역만 최대 1280x720 기준으로 제한합니다.
- 자막 오버레이도 같은 표시 영역을 기준으로 맞춰져 프록시 준비/전환 대기 없이 바로 편집할 수 있습니다.

## v03.07.04 상태 단계명 핫픽스
- 상단 status rail과 사이드바 단계표가 서로 다른 문자열 판정으로 `자막 생성 | VAD`와 `전처리`를 동시에 표시하던 문제를 수정했습니다.
- `core/pipeline_status.py`를 추가해 mode/stage 판정을 `전처리`, `음성`, `STT 1`, `STT 2`, `VAD`, `자막 LLM`, `러프컷 LLM` 기준으로 공용화했습니다.
- StateManager의 진행 상태 보호 로직도 같은 parser를 사용해 진행률 tick이 현재 단계 문구를 덮어쓰지 않도록 맞췄습니다.

## v03.07.05 대용량 전처리 핫픽스
- 외부 음성 향상 모델이 필요 없는 `none`/`deepfilter` 오디오 경로는 `raw.wav -> cleaned.wav` 2단계 FFMPEG 처리를 단일 패스 추출/정제로 합쳤습니다.
- FFMPEG 전처리 명령에 `-threads 0`과 `-filter_threads`를 적용해 가능한 필터 병렬 처리를 사용합니다.
- 원본 파일 크기/수정시각과 오디오 설정/필터 체인이 같으면 검증된 `cleaned.wav` 캐시를 재사용해 재시작 전처리를 건너뜁니다.
- RNNoise, Resemble Enhance, ClearVoice처럼 외부 음성 향상 모델이 필요한 경로는 중간 wav가 필요하므로 기존 안전 경로를 유지합니다.

## v03.07.06 FFMPEG 오디오 스트림 전처리 핫픽스
- 오디오 전처리 FFMPEG 명령이 `-map 0:a:0 -vn -sn -dn`으로 첫 번째 오디오 스트림만 명시적으로 읽도록 수정했습니다.
- 현재 전처리 병목은 `-vn` 오디오 PCM 추출/필터 경로라 GPU 영상 디코딩보다 오디오 스트림 선택, 단일 패스, 캐시, 필터 스레드가 우선입니다.
- 영상 export/인코딩 단계의 GPU 가속은 별도 경로로 분리해 적용해야 하며, 이번 변경은 자막 생성 전처리 안정성과 대용량 입력 처리량을 우선합니다.

## v03.07.07 긴 영상 전처리 진행률 핫픽스
- FFMPEG 전처리 명령을 실행할 때 `-progress pipe:1`을 사용해 실제 처리된 오디오 시간 기준 진행률을 읽습니다.
- 전처리 단계 로그와 상단 상태에 `ffmpeg ... 진행 중 35%` 형태의 퍼센트 업데이트를 표시해 긴 영상에서도 앱이 동작 중임을 알 수 있게 했습니다.
- 로그 도배를 막기 위해 진행률은 5% 이상 변하거나 일정 시간이 지난 경우에만 갱신하고, 완료 시 100%/완료 로그를 남깁니다.

## v03.07.08 직접 STT 청크 전처리 핫픽스
- VAD 선분할/후처리와 다중 화자 분석이 필요 없는 긴 영상은 전체 `cleaned.wav` 생성을 건너뛰고 원본 미디어에서 STT용 16k mono PCM 청크를 직접 추출합니다.
- 직접 청크 추출 경로도 `-map 0:a:0 -vn -sn -dn`, 단일 필터 체인, 16k mono PCM 출력을 사용합니다.
- VAD, 외부 음성 향상 모델, 다중 화자 분석이 필요한 경우는 정확도와 후처리를 위해 기존 전체 정제 WAV 경로를 유지합니다.

## v03.07.09 자막 에디터 상단 툴바 제거 핫픽스
- 자막 목록 위의 mode/filter/search toolbar를 화면에서 제거해 표 헤더가 바로 보이도록 했습니다.
- 해당 toolbar의 `작성/시간/검수`, `정렬`, `...` 항목은 placeholder 성격이었고, `검사`, `자동 교정`, `품질 필터`, `후보`, `검색`은 기능에 연결돼 있었습니다.
- 화면에서는 제거하되 품질 검사 함수가 다른 경로에서 호출돼도 깨지지 않도록 자동 교정 체크박스 의존성을 방어 처리했습니다.

## v03.07.10 사이드바 공간 최적화 핫픽스
- 통합 사이드바의 홈/에디터/러프컷/숏폼 버튼 높이를 44px에서 36px로 줄이고 내부 여백과 아이콘 박스 크기를 함께 낮췄습니다.
- 사이드바 큐 리스트 패널의 고정 최대 높이를 제거하고 세로 확장 정책으로 바꿔 확보된 공간을 큐 테이블이 사용하도록 했습니다.
- 통합 사이드바 레이아웃에서 큐 패널에 stretch를 부여해 위쪽 버튼 압축으로 생긴 공간이 아래 큐 리스트에 배분되도록 했습니다.

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
