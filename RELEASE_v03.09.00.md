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

## v03.09.01 Ollama 자동 시작 핫픽스
- 앱 실행 시 Ollama 서버가 꺼져 있으면 `ollama serve` 또는 macOS Ollama.app을 자동으로 시작합니다.
- 자동 시작 후 짧게 재확인하고, 성공 시 `AI 엔진(Ollama) 자동 시작 완료` 로그를 표시합니다.
- 실행 파일을 찾지 못하거나 시작 확인에 실패한 경우에만 설치 상태 확인 안내를 표시합니다.

## v03.09.02 홈/종료 런타임 정리 핫픽스
- 홈 이동과 앱 종료가 같은 runtime cleanup 루틴을 사용하도록 통합했습니다.
- 홈 이동/종료 시 editor timer, video player, waveform worker, pipeline/backend thread, STT/LLM runtime, 앱 소유 child process를 정리합니다.
- 홈 이동으로 Ollama를 정리한 뒤 같은 앱 세션에서 다시 LLM 작업을 시작해도 요청 직전에 Ollama 서버를 자동 시작합니다.
- 정리 후 `gc.collect()`를 호출해 Python 객체 메모리 회수를 즉시 요청합니다.

## v03.09.03 재생 플레이헤드 중앙 고정 핫픽스
- 재생 중에는 타임라인 플레이헤드 오버레이를 viewport 중앙에 고정하고, GPU 가속 타임라인 캔버스만 부드럽게 스크롤합니다.
- 클릭/선택/줌/수동 이동 같은 기존 편집 동작에서는 중앙 고정을 자동 해제해 기존 조작 흐름을 유지합니다.
- 비디오 frame-map 기준 재생 동기화는 새 `follow_playhead_centered()` 경로를 우선 사용합니다.

## v03.09.04 타임라인 STT2 레인 / 슬라이더 제거 핫픽스
- 타임라인 하단 가로 스크롤바를 화면에서 숨기고, 기존 휠/미니맵/재생 자동 스크롤은 내부 스크롤 값으로 유지합니다.
- STT2 병렬 인식 사용 시 STT2 청크 preview callback도 UI로 전달합니다.
- STT1과 STT2 preview가 같은 시간대에 겹쳐도 서로 지우지 않고, STT2 세그먼트는 STT1 아래 별도 레인에 표시합니다.
- STT2 레인을 위해 타임라인 캔버스 높이를 확장했으며 기존 GPU-capable canvas 렌더링 경로를 그대로 사용합니다.

## v03.09.05 STT 앙상블 독립 스레드 핫픽스
- STT2 선택 시 STT1/STT2 인식을 전용 `ThreadPoolExecutor(max_workers=2)`에서 독립 스레드로 병렬 실행합니다.
- STT1/STT2 결과 버퍼와 오류 기록은 lock으로 보호하고, child processor 목록도 thread-safe하게 관리합니다.
- preview callback은 STT1/STT2별로 분리된 복사본을 전달해 한쪽 preview mutation이 다른 쪽 작업을 방해하지 않도록 했습니다.
- 로그에 `STT1/STT2 독립 스레드 병렬 처리`를 표시해 실행 경로를 확인할 수 있습니다.

## v03.09.06 재생 시작 중앙 정렬 핫픽스
- 재생 시작 시 플레이헤드가 viewport 중앙 밖에 있으면 먼저 해당 위치를 중앙으로 즉시 맞춥니다.
- 중앙 정렬이 끝난 뒤부터 플레이헤드 중앙 고정과 GPU-backed 타임라인 캔버스 smooth follow를 시작합니다.
- 이미 중앙 고정 재생 중인 경우에는 기존처럼 캔버스가 자연스럽게 흐르도록 유지합니다.

## v03.09.07 첫 재생 자막 오버레이 스타일 핫픽스
- GPU/scene subtitle overlay가 생성 시점부터 `dataset/user_settings.json`의 `export_dialog` 스타일을 읽도록 수정했습니다.
- 첫 재생 전에 export dialog를 열지 않아도 저장된 폰트/크기/해상도 설정이 비디오 preview 자막에 적용됩니다.
- 스타일을 읽지 못하는 fallback의 기본 글자 크기도 preview용 `22`로 낮춰 첫 표시에서 과대 렌더링되지 않게 했습니다.

## v03.09.08 러프컷 완료 상태 핫픽스
- 자막 생성 완료 직후 `AI/STT/LLM` 메모리 정리 경로가 러프컷 초안 예약을 건너뛰던 문제를 수정했습니다.
- 러프컷 초안이 예약/생성/저장 중이면 모델 정리를 대기하고, 초안 처리가 끝난 뒤 러프컷 상태를 보존한 채 런타임을 정리합니다.
- 사이드바 큐 리스트에 상태 칸을 추가해 항목별 `완료` 표시가 헤더 100% 완료와 함께 보이도록 했습니다.

## v03.09.09 확인 필요 자막 우클릭 메뉴 핫픽스
- 품질 검사에서 확인이 필요한 자막 세그먼트는 타임라인에서 우클릭하면 `자막 확정` / `자막 삭제` 메뉴를 표시합니다.
- `자막 확정`은 해당 세그먼트의 품질 상태를 수동 확정(`green`, `manual_confirmed`)으로 바꾸고 확인 필요 플래그를 제거합니다.
- `자막 삭제`는 기존 자막 삭제 흐름과 동일하게 해당 줄을 무음 gap으로 전환해 타임라인/텍스트 편집 상태를 동기화합니다.

## v03.09.10 시작 시 Ollama 정리/재시작 순서 핫픽스
- 앱 초기 홈 화면 구성 중에는 idle backend가 있다는 이유만으로 홈 이동 runtime cleanup을 실행하지 않도록 수정했습니다.
- 시작 직후 `홈 이동` 정리 로그가 찍히고 Ollama를 다시 자동 시작/언로드하는 불필요한 순서를 제거했습니다.
- 실제 홈 이동, 종료, 작업 중단처럼 에디터나 backend가 활성 상태일 때의 runtime cleanup은 유지합니다.

## v03.09.11 AI 메뉴 설정 항목 복구
- `AI` 탭에 Google/OpenAI API Key와 Hugging Face Token 입력창을 다시 직접 노출했습니다.
- `AI` 탭에서 STT1/STT2 Whisper 모델 선택을 바로 확인할 수 있게 했습니다.
- LLM 다운로드와 Whisper/필수 모델 설치/삭제/필수 확인 메뉴를 같은 `AI` 탭에 표시해 모델 준비 상태를 한 곳에서 관리합니다.

## v03.09.12 재생 플레이헤드 자연 고정 핫픽스
- 재생 시작 시 플레이헤드를 즉시 중앙으로 점프시키던 center-lock 초기 획득 로직을 수정했습니다.
- 플레이헤드가 화면 중앙보다 앞쪽에 있으면 현재 위치에서 그대로 흐르다가 중앙에 도달한 뒤 고정됩니다.
- 플레이헤드가 중앙보다 뒤쪽에 있을 때도 스크롤이 부드럽게 따라간 뒤 center-lock으로 전환됩니다.

## v03.09.13 ClearVoice 진행 상태 표시 핫픽스
- ClearVoice 음성 향상 모델 실행 중 5초 간격으로 경과시간 heartbeat 로그를 표시합니다.
- 외부 모델 호출이 자체 퍼센트 진행률을 제공하지 않는 구간에서도 앱이 살아있는지 확인할 수 있습니다.
- ClearVoice 완료 뒤 이어지는 FFMPEG 16k 변환/음량 평탄화 퍼센트 진행률은 기존대로 유지합니다.

## v03.09.14 Resemble Enhance 진행 상태 표시 핫픽스
- Resemble Enhance 음성 향상 모델 실행 중 5초 간격으로 경과시간 heartbeat 로그를 표시합니다.
- 외부 모델 호출이 자체 퍼센트 진행률을 제공하지 않는 구간에서도 앱이 살아있는지 확인할 수 있습니다.
- Resemble Enhance 완료 뒤 이어지는 FFMPEG 16k 변환/음량 평탄화 퍼센트 진행률은 기존대로 유지합니다.

## v03.09.15 STT 후보 자막 선택 핫픽스
- 타임라인을 `자막 / STT1 / STT2` 레인으로 분리해 최종 자막과 STT 후보가 섞이지 않게 했습니다.
- STT1/STT2 후보는 최종 자막 생성 뒤에도 유지되며, 후보를 클릭하면 같은 시간대 최종 자막 세그먼트로 수동 확정됩니다.
- 후보 세그먼트는 핸들 드래그, 화자 선택, 갭 생성 같은 최종 자막 편집 동작을 방해하지 않도록 입력 히트 타깃에서 분리했습니다.

## v03.09.16 STT 후보 레인 선택 전용 핫픽스
- STT1/STT2 후보 레인은 더블클릭, F2, 중앙 드래그, 다이아몬드 병합/조정 같은 자막 편집 기능에서 제외했습니다.
- LLM 후보 판정이 STT1/STT2 중 어느 쪽을 골랐는지 자막 메타데이터에 보존하고, 해당 후보 레인에 `LLM` 배지로 표시합니다.
- LLM 분할/강제분할 이후에도 STT 후보 선택 출처 메타데이터가 사라지지 않도록 최적화 결과에 함께 전파합니다.

## v03.09.17 STT 후보 선택 하이라이트 핫픽스
- STT1/STT2 후보를 왼쪽 클릭하면 후보 프리뷰를 지우지 않고 즉시 최종 자막 세그먼트에 반영합니다.
- 선택된 후보는 후보 레인에 `선택` 배지와 밝은 테두리로 하이라이트하고, 같은 구간에서 선택받지 못한 후보는 회색 음영으로 표시합니다.
- 수동 선택과 LLM 선택 상태를 같은 판정 경로에서 처리해 STT 후보 비교 상태가 타임라인에 남도록 했습니다.

## v03.09.18 음성 감지 세그먼트 저장 핫픽스
- 타임라인 `음성 감지` 레인에 음성/무음/노이즈/STT대기/VAD외/확인 상태를 겹치지 않는 세그먼트로 표시합니다.
- VAD, 무음 gap, STT 품질 플래그를 합산한 뒤 우선순위 기반으로 겹침을 해소해 한 시간 구간에는 하나의 음성 감지 상태만 남깁니다.
- 프로젝트 `analysis.voice_activity_segments`와 `editor_state.analysis.voice_activity_segments`에 시작/종료 프레임, frame_range, 프레임레이트를 함께 저장하고 재열기 때 복원합니다.

## v03.09.19 타임라인 휠 스크롤 핫픽스
- 타임라인/캔버스/글로벌 미니맵 휠 입력을 공통 수동 스크롤 경로로 통합했습니다.
- 휠로 좌우 이동하는 동안 재생 플레이헤드 center-lock과 smooth-scroll timer를 잠깐 해제해 스크롤바와 자동 추적이 서로 되돌리는 떨림을 막았습니다.
- 휠 입력 직후에도 플레이헤드 위치는 계속 갱신하되, 짧은 수동 조작 구간에서는 캔버스 자동 중앙 추적을 양보합니다.

## v03.09.20 STT 후보 LLM 1차 선택 핫픽스
- STT1/STT2 후보가 2개 있는 구간은 기존 STT1 primary lock 여부와 관계없이 LLM 후보 판정을 먼저 시도합니다.
- 후보 판정 프롬프트에 앞/뒤 자막 문맥을 함께 넣어 LLM이 문맥상 더 자연스러운 STT1 또는 STT2를 고르게 했습니다.
- LLM 판정이 실패하면 기존 STT 점수/ROVER 병합 결과를 유지하고, 필터가 앙상블 후보 세그먼트를 모두 제거한 경우에는 원본 앙상블 결과로 최종 자막을 복구합니다.

## v03.09.21 STT 후보 선택 trim 핫픽스
- STT1/STT2 후보를 수동 선택할 때 기존 최종 자막을 통째로 교체하지 않고, 선택 후보와 겹치는 시간 구간만 잘라냅니다.
- 기존 최종 자막의 앞/뒤 잔여 구간이 충분히 길면 자동으로 split해 유지하므로, 인접한 다음 STT 후보를 이어서 선택할 수 있습니다.
- STT 후보 선택 후 선택 출처 메타데이터와 후보 하이라이트 상태는 그대로 유지합니다.

## v03.09.22 STT 후보/최종 자막 표시 순서 핫픽스
- STT 앙상블 모드에서 STT1/STT2 후보 미리보기는 생성되는 즉시 타임라인 후보 레인에 표시합니다.
- 최종 자막 세그먼트는 중간 chunk 단위로 flush하지 않고, STT 병합과 LLM 분석이 끝난 뒤 최종 버퍼에서 반영합니다.
- 로그에 STT 후보 즉시 표시와 최종 자막 지연 반영 흐름을 명시해 멈춘 상태인지 분석 중인지 구분할 수 있게 했습니다.

## v03.09.23 멀티클립 STT 후보 저장/복원 핫픽스
- 멀티클립 STT1/STT2 후보 preview와 최종 자막의 STT 선택/후보 메타데이터를 프로젝트 `editor_state.stt.preview_segments`와 subtitle segment metadata에 저장합니다.
- 두 번째 클립 이후 STT 후보의 start/end/word timestamp도 클립 offset을 반영한 글로벌 타임라인 기준으로 보정합니다.
- 프로젝트 재열기 시 저장된 STT1/STT2 후보 레인과 선택 메타데이터를 에디터 타임라인에 복원합니다.

## v03.09.24 긴 영상 러프컷 초안 생성 핫픽스
- 자막 row 수가 `roughcut_llm_max_context_rows`를 넘는 긴 영상은 에디터 러프컷 초안 LLM 요청을 건너뜁니다.
- LLM 대기/타임아웃에 묶이지 않고 로컬 러프컷 중분류 세그먼트를 즉시 생성해 타임라인 러프컷 레인과 프로젝트 roughcut_state에 반영합니다.
- 로그에 긴 영상 LLM 생략 사유와 row 제한을 표시해 멈춘 상태와 로컬 fallback 진행을 구분할 수 있게 했습니다.

## v03.09.25 사용하지 않는 Whisper 모델 제거 핫픽스
- AI 설정 STT1/STT2 드롭다운에서 사용하지 않는 Core ML, medium.en, small, base, tiny 계열 Whisper 모델을 제거했습니다.
- HuggingFace 캐시에 해당 모델 폴더가 남아 있어도 설정창 목록에 다시 붙지 않도록 공통 필터를 적용했습니다.
- Whisper/필수 모델 설치 레지스트리에서도 동일한 항목을 제거해 설치 대상으로 표시되지 않게 했습니다.

## v03.09.26 음성 감지/분석 레인 클릭 이동 방지 핫픽스
- 타임라인의 `음성 감지`와 `분석/분석대기` 레인을 읽기 전용 정보 레인으로 분리했습니다.
- 해당 레인을 클릭하거나 더블클릭해도 플레이헤드 이동, 화면 스크롤, 자막 선택, 세그먼트 드래그가 발생하지 않도록 입력을 흡수합니다.
- hover 상태도 이 레인에서는 해제해 자막 조정 커서나 선택 상태가 잘못 표시되지 않게 했습니다.

## v03.09.27 STT 후보 자막 규칙/LLM 적용 핫픽스
- STT1/STT2 후보 미리보기 전용 optimizer를 추가해 후보 레인도 최종 자막과 같은 `optimize_segments()` 규칙/LLM 경로를 거친 뒤 표시합니다.
- STT worker를 직접 막지 않도록 단일/멀티클립 파이프라인에 후보 후처리 전용 background queue/thread를 추가했습니다.
- 멀티클립 후보는 LLM/규칙 처리 뒤에도 clip offset, clip index, clip file metadata를 유지합니다.

## v03.09.28 타임라인 시작 화면 맞춤/줌 저장 제거 핫픽스
- 앱/프로젝트 진입 시 타임라인 캔버스가 항상 `fit_to_view()`로 시작되도록 복원 경로를 정리했습니다.
- 프로젝트 workspace와 editor_state 저장 시 `zoom_pps`, `pps`, `scroll_position`, `scroll_x` 계열 값을 저장하지 않도록 공통 sanitizer를 추가했습니다.
- 기존 프로젝트 JSON에 남아 있는 확대/스크롤 값은 읽더라도 복원하지 않고 무시합니다.

## v03.09.29 자막감지 레인 핫픽스
- 타임라인의 `음성 감지` 표시를 `자막감지`로 바꾸고, 음성/무음 중심 표시 대신 자막 판정 정보를 표시합니다.
- STT1/STT2 후보와 최종 자막 메타데이터를 바탕으로 LLM 선택 완료, 수동 선택, 자막 점수, 선택 필요 상태를 표시합니다.
- 자막 점수는 100점 초록색부터 50점 노랑, 0점 빨강까지 단계적으로 보이고, 선택이 필요한 상태는 회색으로 표시합니다.
- 프로젝트 저장 시 기존 `voice_activity_segments` 호환 키를 유지하되 schema를 `subtitle_detection.v1`로 기록하고 score/selection_state를 함께 보존합니다.

## v03.09.30 최종 자막 간격 설정 핫픽스
- 최종 자막세그먼트에 `간격` 설정의 자막간격 조정, 연속자막 기준, 단일자막 유지 값을 적용하는 마지막 timing pass를 추가했습니다.
- 단일 품질모드, 멀티클립 품질모드, 빠른모드가 STT/LLM/VAD/화자 처리를 끝낸 뒤 같은 최종 간격 패스를 거쳐 에디터에 자막을 반영합니다.
- 이미 최종 간격 패스를 지난 세그먼트는 에디터 큐의 기존 간격 조정이 다시 내부 적용되지 않도록 표시해 중복 당기기/미루기를 막았습니다.
- 멀티클립은 클립 경계를 timing scope로 보존해 서로 다른 클립의 자막이 간격 조정으로 침범하지 않게 했습니다.

## v03.09.31 STT 후보 선택 Undo/Redo 핫픽스
- STT1/STT2 후보를 클릭해 최종 자막세그먼트로 선택하는 작업이 Undo/Redo 스냅샷에 포함되도록 UndoManager를 확장했습니다.
- Undo 스냅샷이 텍스트/화자/시작시간만 저장하던 한계를 보완해 STT 선택 출처, STT 후보 메타데이터, 품질 메타데이터, 클립 메타데이터를 함께 보존합니다.
- Undo/Redo 복원 시 live STT 후보 preview 레인과 cached segment 상태도 함께 복원해 후보 하이라이트/회색 음영 상태가 다시 계산되도록 했습니다.

## 제거 / 영향 범위
- `filter_available_whisper_models` helper를 추가했습니다.
- 사용하지 않는 STT 모델 선택/설치 항목만 제거했으며, 기존 자막 생성/편집 기능은 유지합니다.
- 음성 감지/분석 레인은 표시 전용이며, 향후 무음 구간 삭제 같은 기능은 별도 명시 액션으로 추가할 예정입니다.
- STT1/STT2 후보 레인은 raw Whisper 결과가 아니라 자막 규칙/LLM 처리 결과를 표시합니다. LLM 설정이 느리면 후보 표시도 그만큼 지연될 수 있으나 STT worker 자체는 별도 스레드에서 계속 진행합니다.
- 타임라인 확대/축소 버튼은 유지하되, 확대율과 가로 스크롤 위치는 프로젝트/사용자 설정에 저장하지 않습니다.
- `자막감지` 레인은 기존 음성 감지 저장/복원 경로를 호환 사용하므로 예전 프로젝트의 저장된 표시 데이터도 계속 열 수 있습니다.
- 최종 간격 패스는 자막세그먼트 timing만 조정하며 STT1/STT2 후보 레인과 표시 전용 분석 레인은 편집 가능한 자막세그먼트로 바꾸지 않습니다.
- UndoManager 스냅샷 구조가 확장되었지만 기존 런타임 스택 내부 형식에 대한 호환 restore 경로는 유지합니다.
- `dataset/video_preview_cache/`, `checkpoints/`, `.codex_work/`는 로컬 산출물/작업 메모이며 릴리즈 커밋 대상에서 제외합니다.
- requirements 변경은 없습니다.

## 검증
- `venv/bin/python -m py_compile config.py ui/editor/undo_manager.py ui/editor/editor_segments.py tests/test_project_segment_reload.py`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_project_segment_reload`
  - 9 tests passed
- `venv/bin/python -m py_compile config.py core/engine/subtitle_engine.py core/pipeline/single_pipeline.py core/pipeline/multiclip_pipeline.py core/backend_fast.py ui/editor/editor_segments.py tests/test_subtitle_engine_settings.py`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_subtitle_engine_settings`
  - 8 tests passed
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_subtitle_engine_settings tests.test_stt_ensemble tests.test_project_segment_reload tests.test_timeline_hit_targets tests.test_timeline_segment_colors`
  - 60 tests passed
- `git diff --check -- . ':(exclude)dataset/video_preview_cache' ':(exclude)checkpoints'`
- `venv/bin/python -m py_compile config.py core/pipeline/stt_preview_optimizer.py core/pipeline/single_pipeline.py core/pipeline/multiclip_pipeline.py tests/test_stt_preview_optimizer.py`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_stt_preview_optimizer tests.test_stt_ensemble tests.test_project_segment_reload`
  - 26 tests passed
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_stt_preview_optimizer tests.test_stt_ensemble tests.test_project_segment_reload tests.test_timeline_hit_targets tests.test_timeline_segment_colors`
  - 53 tests passed
- `venv/bin/python -m py_compile config.py core/project/project_context.py core/project/project_manager.py core/project/project_phase1b.py core/project/project_snapshot.py ui/project/workspace_restore.py ui/editor/editor_actions.py ui/editor/editor_lifecycle.py tests/test_cp08_cp10_home_timeline.py tests/test_project_context.py`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_cp08_cp10_home_timeline tests.test_project_context tests.test_timeline_playhead_fit`
  - 42 tests passed
- `venv/bin/python -m py_compile config.py ui/timeline/timeline_analysis.py ui/timeline/timeline_paint.py core/project/project_context.py core/project/project_manager.py tests/test_timeline_segment_colors.py tests/test_project_context.py`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_timeline_segment_colors tests.test_project_context`
  - 25 tests passed
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_timeline_segment_colors tests.test_timeline_hit_targets tests.test_project_context tests.test_project_segment_reload`
  - 52 tests passed
- `git diff --check -- . ':(exclude)dataset/video_preview_cache' ':(exclude)checkpoints'`
- `venv/bin/python -m py_compile config.py ui/timeline/timeline_constants.py ui/timeline/timeline_input.py ui/timeline/timeline_paint.py tests/test_timeline_hit_targets.py`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_timeline_hit_targets`
  - 19 tests passed
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_timeline_hit_targets tests.test_timeline_segment_colors tests.test_timeline_layout_constants tests.test_timeline_playhead_fit`
  - 51 tests passed
- `git diff --check -- . ':(exclude)dataset/video_preview_cache' ':(exclude)checkpoints'`
- `venv/bin/python -m py_compile config.py ui/settings/settings_common.py ui/settings/settings_ai.py tests/test_whisper_model_catalog.py`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_whisper_model_catalog tests.test_roughcut_ui_v2 tests.test_model_manager`
  - 17 tests passed
- `git diff --check -- . ':(exclude)dataset/video_preview_cache' ':(exclude)checkpoints'`
- `venv/bin/python -m py_compile core/roughcut/editor_draft.py core/roughcut/__init__.py ui/editor/editor_segments.py tests/test_editor_roughcut_draft.py`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_editor_roughcut_draft`
  - 12 tests passed
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_editor_roughcut_draft tests.test_project_context tests.test_stt_ensemble tests.test_project_segment_reload tests.test_timeline_hit_targets tests.test_timeline_segment_colors tests.test_timeline_playhead_fit tests.test_subtitle_engine_settings`
  - 103 tests passed
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_editor_roughcut_draft tests.test_roughcut_engine1 tests.test_roughcut_ui_v2 tests.test_timeline_segment_colors`
  - 52 tests passed
- `venv/bin/python -m py_compile config.py core/project/project_context.py core/project/project_manager.py core/pipeline/multiclip_pipeline.py ui/editor/editor_actions.py ui/editor/editor_segments.py ui/editor/subtitle_text_edit.py ui/project/project_panel.py tests/test_project_context.py tests/test_stt_ensemble.py`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_project_context tests.test_stt_ensemble tests.test_project_segment_reload`
  - 38 tests passed
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_project_context tests.test_stt_ensemble tests.test_project_segment_reload tests.test_timeline_hit_targets tests.test_timeline_segment_colors tests.test_project_context tests.test_timeline_playhead_fit tests.test_subtitle_engine_settings tests.test_media_processor_overlap`
  - 129 tests passed
- `venv/bin/python -m py_compile config.py core/pipeline/single_pipeline.py tests/test_stt_ensemble.py`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_stt_ensemble tests.test_project_segment_reload tests.test_timeline_hit_targets`
  - 41 tests passed
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_project_segment_reload tests.test_timeline_hit_targets tests.test_stt_ensemble tests.test_timeline_segment_colors tests.test_project_context tests.test_timeline_playhead_fit tests.test_subtitle_engine_settings`
  - 88 tests passed
- `venv/bin/python -m py_compile main.py config.py ui/main/main_window.py ui/editor/editor_lifecycle.py core/llm/ollama_provider.py core/platform_compat.py tests/test_sidebar_terminal_layout.py tests/test_ollama_provider.py tests/test_windows_platform_compat.py`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_windows_platform_compat tests.test_video_player_widget tests.test_project_segment_reload tests.test_cp03_cp04_status_ui`
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest tests.test_windows_platform_compat tests.test_project_segment_reload tests.test_cp03_cp04_status_ui tests.test_sidebar_terminal_layout tests.test_ollama_provider`
  - 54 tests passed
- `git diff --check -- . ':(exclude)dataset/video_preview_cache' ':(exclude)checkpoints'`
