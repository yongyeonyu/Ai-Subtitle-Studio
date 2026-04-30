<!--
Document-Version: 03.01.14
Phase: PHASE2
Last-Updated: 2026-04-30
Updated-By: Codex with 대표님
Previous-Content: v03.01.13 RC-D4 러프컷 preview 고도화
This-Update: v03.01.14 RC-D5 렌더 실행 UI
Copilot-Handoff: v03.01.14 개발 기준 릴리즈 노트입니다. 러프컷 렌더 검증/실행/복구/로그 UI를 연결했습니다.
-->
# RELEASE v03.00.00

## 핵심 변경
- PHASE2 러프컷 편집을 위한 `core/roughcut` 패키지를 신설했습니다.
- 기존 자막 생성/편집 파이프라인에 영향을 주지 않는 순수 함수 중심의 로컬 분석 엔진으로 시작했습니다.

## 러프컷 엔진 1~2단계
- `models.py`: Subtitle/RoughCut/Timeline/Storyboard/EDL dataclass 모델을 추가했습니다.
- `gap_detector.py`: 자막 없는 구간을 탐지하는 helper를 추가했습니다.
- `transcript_packer.py`: 자막 행을 LLM 입력용 phrase 단위로 압축합니다.
- `scene_change_detector.py`: 외부 의존성 없이 픽셀 차이 평균으로 scene cut 후보를 감지합니다.
- `frame_sampler.py`: 세그먼트 대표 프레임 timestamp와 저해상도 ffmpeg frame command helper를 제공합니다.
- `topic_detector.py`: 표준 라이브러리 기반 keyword/topic shift detector를 추가했습니다.
- `semantic_chunker.py`: phrase를 semantic chunk로 묶고 chapter metadata seed를 생성합니다.
- `story_mapper.py`: 챕터 위치와 텍스트 힌트 기반으로 기/승/전/결 story role을 부여하고, 순서 변경 없이 이동 검토 메타데이터만 남깁니다.
- `models.py`: `ChapterMetadata`에 `story_role`, `story_reason`, `move_recommendation`, `role_confidence`를 추가했습니다.
- `edit_decision_engine.py`: gap/phrase boundary 기반 cut safety를 분류하고 keep/trim/remove/highlight/move edit decision을 생성합니다.
- `edl_generator.py`: keep/highlight/trim/move 결과를 EDL segment와 JSON으로 변환하고 remove 구간은 제외합니다.
- `guide_writer.py`: 전체 요약, 추천 스토리 흐름, 챕터 표, 편집 판단, 위험 컷 검토 목록을 Markdown으로 생성합니다.
- `pipeline.py`: subtitle_segments 입력을 pack → chunk → story role → decision → EDL → guide 순서로 실행하고 `RoughCutResult`를 반환합니다.
- `renderer_skeleton.py`: 원본 덮어쓰기 방지, ffmpeg concat command plan, 마지막 단계 subtitle burn-in command 생성을 제공합니다.
- `render_executor.py`: EDL 기반 ffmpeg segment 추출/concat 실행 경로와 dry-run 검증 경로를 제공합니다.
- `subtitle_retimer.py`: EDL output time 기준으로 자막을 clip/retime하고 SRT를 생성합니다.

## 테스트
- `tests/test_roughcut_engine1.py`를 추가해 transcript packing, gap 탐지, scene change, frame sampling, topic shift, semantic chunk, story mapper, edit decision, EDL, guide, pipeline, renderer skeleton/executor, subtitle retime/SRT를 검증합니다.

## UI 보정
- 첫 화면 사이드바 메뉴가 눌려 보이는 문제를 줄이기 위해 메뉴 높이와 아이콘 행을 고정했습니다.
- 하단 전역 메뉴의 일부 배경이 밝게 깨지는 문제를 방지하도록 메뉴바/그룹 배경 스타일을 명시했습니다.
- 완료된 Phase2 엔진 항목은 `ACTION_ITEMS.md` 본문에서 제거하고, 대표님 확인용 CHECKPOINT만 남겼습니다.
- 비디오 preview를 `QGraphicsVideoItem` 기반으로 전환해 재생 중 자막 overlay가 영상 위에 표시되도록 보강했습니다.
- 프로젝트 정보 펼침은 사이드바 레이아웃을 밀지 않는 overlay 방식으로 변경했고, 토글 시 편집 화면을 유지합니다.
- 왼쪽 상단 상태 레일을 진행 단계 1버튼 + 현재 모드 1버튼으로 정리했습니다.
- 시작/처리중/재시작, STT, 종료, 비디오 폭 토글 아이콘과 동작을 보정했습니다.
- 비디오 폭 버튼이 현재 폭이 영상 맞춤 폭보다 클 때 오른쪽 화살표를 표시하고, 클릭 시 영상 폭에 맞춰 줄어들도록 보정했습니다.
- 하단 실행 버튼 명칭을 `Undo` / `Redo`로 변경하고 아이콘 의미를 맞췄습니다.
- 종료 버튼 전원 아이콘을 전자제품 전원 기호에 가깝게 보정했습니다.
- 왼쪽 상단 상태/모드 버튼 폭을 사이드바 폭에 맞게 확장했습니다.
- 비디오 폭 토글 버튼을 에디터/비디오 경계선 정중앙으로 옮기고, 영상 로드 시간과 무관하게 클릭되도록 했습니다.
- 디테일 타임라인 다이아몬드 핸들을 자막 세그먼트 하단 경계로 이동하고, 캔버스 선택 시 하단 노란 테두리가 보이도록 보정했습니다.
- 비디오 폭 토글 버튼 아래 위젯이 마우스 클릭을 가져가는 경우에도 축소/확대가 실행되도록 클릭 이벤트 경로를 보강했습니다.
- 1:1 영상에서 비디오 패널 최소 폭 때문에 축소가 막히던 문제를 보정하고, 기본 폭 복귀 기준이 잘못 저장되지 않도록 했습니다.
- 대표님 요청에 따라 비디오 확대/축소 화살표와 토글 기능을 제거하고, 비디오 패널 폭을 현재 높이 기준 16:9로 자동 고정했습니다.
- `ui/roughcut/roughcut_widget.py`를 추가해 기존 중앙 stack 안에서 러프컷 분석 결과 요약, 챕터 표, Markdown 가이드를 표시합니다.
- 왼쪽 사이드바 `러프컷` 버튼은 새 창 없이 중앙 러프컷 화면으로 전환합니다.
- 러프컷 테이블에 타임태그, 대표 프레임 시각, 기존 자막, 수정 가능한 챕터 주제/태그, 상태, 판단/안전/출력 시간을 표시합니다.
- 러프컷 행 hover 시 3~5초 muted preview loop를 시도하고, 클릭/버튼으로 해당 구간만 에디터 플레이어에서 재생합니다.
- 러프컷 화면에서 EDL JSON, Markdown 가이드, retimed SRT, 렌더 계획 JSON을 저장할 수 있으며, 렌더 계획에는 선택형 subtitle burn-in 마지막 단계가 포함됩니다.
- AI 설정창에 `빠른 인식` / `균형` / `정밀 인식` 자막 정확도 프리셋을 추가했습니다.
- `core/audio/stt_quality_presets.py`에서 프리셋별 Whisper 모델, LLM 사용 여부, 디코딩 민감도, 청크 크기, 병렬도를 한 번에 적용합니다.
- `core/audio/media_processor.py`에서 긴 VAD/강제 분할 청크에 실제 overlap을 적용하고, overlap으로 중복 인식된 앞부분은 word timestamp 기준으로 제거합니다.
- 빠른/균형/정밀 프리셋에 `whisper_chunk_overlap_sec` 값을 추가해 모드별 문맥 보존 정도를 다르게 적용합니다.
- `core/engine/word_resegmenter.py`를 추가해 최대 글자 수, 최대 duration, CPS, 문장부호, 무음 gap 기준으로 word timestamp 재분할을 수행합니다.
- 자막 간격 설정창에 `최대 자막 길이` 슬라이더를 추가하고, `optimize_segments` 마지막 단계에서 재분할을 적용합니다.
- `core/engine/llm_correction_guard.py`를 추가해 LLM 보정 결과가 원문 대비 단어를 추가/삭제하거나 타임코드를 포함하면 해당 결과를 차단합니다.
- LLM 프롬프트 절대 규칙에 의미 변경 금지, 구어체 유지, 불확실한 단어 원문 유지, 타임코드 출력 금지를 명시했습니다.
- 타임라인 선택 상태의 상단 노란 테두리를 제거하고, 하단 미니맵 영역에는 노란 하단선이 보이도록 보정했습니다.
- 하단 미니맵 포커스 표시 중 paintEvent 예외가 PyQt SIGABRT로 이어지지 않도록 포커스 탐색을 안전하게 제한했습니다.
- 프로젝트 JSON에 `editor_state`와 `roughcut_state`를 분리 저장해 단일클립/멀티클립/러프컷 이동 시 서로 상태를 덮어쓰지 않도록 보강했습니다.
- 프로젝트 로드 시 저장된 자막/화자 세그먼트를 에디터로 복원하고, 단일클립에서 미디어 추가 시 멀티클립 상태로 전환되도록 보강했습니다.
- 러프컷 진입 시 현재 에디터 자막 signature를 기준으로 재분석하고, 단일/멀티클립 에디터에서 수정한 자막이 러프컷에 반영되도록 했습니다.
- 러프컷 UI 기능을 화면 조립, 상태 저장, 챕터 테이블, 구간 프리뷰, 출력 저장, 포맷 공통 모듈로 분리했습니다.
- 프로젝트 JSON 저장 경로가 `editor_state`, `roughcut_state`, `active_work_mode`를 함께 보존하도록 보강했습니다.
- 프로젝트 로드 시 단일클립/멀티클립 에디터 상태를 복원하고, 마지막 작업 화면이 러프컷이면 러프컷 화면으로 돌아오도록 연결했습니다.
- 멀티클립 러프컷 EDL은 clip boundary 기준으로 실제 원본 `source_path`와 clip-local source time을 저장하고, 자막 retime은 global timeline range 기준으로 계산합니다.
- 비디오 자막 overlay provider는 전체 자막 signature를 비교해 중간 자막/화자 수정도 즉시 반영되도록 보강했습니다.
- 하단 전역 메뉴에 `도움말` 버튼을 추가하고, 탭형 도움말 창에서 기능별 사용법/예시/특정 상황/스크린샷 자리를 제공합니다.
- 도움말 기능을 `ui/help` 패키지의 content/dialog 모듈로 분리했습니다.
- `line_icon` 결과 캐시를 추가해 전역 메뉴와 설정창에서 반복되는 아이콘 생성 비용을 줄였습니다.
- 타임라인 선택 표시에서 디테일 캔버스 내부/하단 노란 테두리를 제거하고, 타임라인 상단 경계선만 노란색으로 표시하도록 보정했습니다.
- 자막 동영상 출력 창 하단 버튼 줄 높이/폭을 맞추고, `적용` 버튼으로 현재 설정을 비디오 플레이어 overlay에 즉시 반영하도록 했습니다.
- 비디오 플레이어 overlay는 FHD/UHD 출력 가로폭 기준 비율로 글자 크기, 줄간격, 배경, 그림자, 테두리를 스케일링합니다.
- 비디오 플레이어 상단의 미리보기 제목/맞춤/캡처/더보기 헤더를 제거하고, 제거된 높이만큼 영상 컨테이너를 확장했습니다.
- 영상 컨테이너 높이가 커진 만큼 에디터 split 비율의 16:9 가로 폭도 자동으로 늘어나도록 보정했습니다.
- 왼쪽 프로젝트 사이드바 iCloud/NAS 자동처리 카드의 상태 텍스트를 제목 아래 별도 줄로 분리하고, 화살표 접기/펼치기를 추가했습니다.
- 왼쪽 사이드바 저장 상태 원을 editor dirty 상태와 연결해 저장안됨은 빨간색, 저장됨은 초록색으로 표시하도록 했습니다.
- 오른쪽 하단 VAD/음성/STT/LLM 현재 설정 정보를 하단 메뉴에서 제거하고, 왼쪽 프로젝트 사이드바 하단 상태/설정 카드로 이동했습니다.
- 러프컷 상단 헤더/요약/프리뷰 조작 UI를 하단 오른쪽 러프컷 테이블 패널로 이동하고, 하단 오른쪽 영역을 큐 테이블/러프컷 테이블 스택으로 분리했습니다.
- Undo/Redo 아이콘을 대표님 첨부 레퍼런스처럼 굵은 반원형 화살표 스타일로 보정했습니다.
- 종료 버튼 전원 아이콘을 대표님 첨부 레퍼런스처럼 굵은 빨간 전원 기호 스타일로 보정했습니다.
- AI 설정창과 설정 공용 하단 버튼의 높이를 동일하게 맞춰 선택 버튼/주요 버튼만 튀어 보이지 않도록 보정했습니다.
- 왼쪽 사이드바 `자막 편집`을 `에디터`로, `러프컷 편집 도우미`를 `러프컷`으로 바꾸고, 편집 중 두 화면을 버튼으로 왕복하며 현재 화면만 하이라이트되도록 보정했습니다.
- 왼쪽 사이드바 메뉴 버튼을 첨부 UI처럼 아이콘 타일, 더 큰 행 높이, 활성 배경/파란 테두리 기준으로 통일했습니다.
- 자막 트랙 끝에 클립 추가 `+` 세그먼트를 항상 표시하고, STT 모드에서도 기존 클립 추가 동작으로 연결되도록 복구했습니다.
- 타임라인 선택/포커스 노란 테두리를 상/하/좌/우 4선 사각형으로 정확히 보이도록 보정했습니다.
- iCloud/NAS 자동처리 카드의 화살표 접기/펼치기 기능을 제거하고, 프로젝트 정보 화살표는 20% 작게 보이도록 보정했습니다.
- 편집 모드에서 자동설정 저장 후 홈 화면으로 돌아가지 않고 현재 에디터 화면을 유지하도록 보정했습니다.
- 자동 감지로 자막 생성이 시작되면 작업 완료 전까지 Watchdog 표시를 `Watchdog 대기중`으로 바꾸고, 완료/실패/취소 후에만 감시 상태를 재개하도록 보정했습니다.
- 자막 생성 중 STT 버튼을 누르면 `STT모드를 시작하시겠습니까?` 확인 후 기존 작업을 중단하고 STT Mode를 시작하도록 연결했습니다.
- 타임라인 플레이헤드 클릭/이동 직후에도 비디오 자막 overlay provider를 강제 갱신해 재생 버튼을 누르지 않아도 현재 자막이 즉시 표시되도록 보강했습니다.
- 비디오 자막 overlay는 플레이어 전체 폭이 아니라 실제 영상 표시 rect 기준으로 배치/스케일되어 세로/1:1/가로 영상의 검은 여백에 영향을 받지 않도록 했습니다.
- 캐시 삭제와 자동처리 폴더 팝업 복귀 시 홈으로 강제 이동하지 않고 현재 에디터/러프컷/숏폼 작업 화면을 유지하도록 보정했습니다.
- 종료 버튼은 `_quick_exit` 경로에서 현재 에디터 저장을 먼저 시도하고 프로젝트 JSON을 `프로젝트백업` 폴더에 복사한 뒤 빠르게 종료하도록 보강했습니다.
- 홈 화면 복귀 시 멀티클립 임시 파일/경계/재사용 상태를 초기화해 이후 단일 파일에서 클립 추가 시 이전 멀티클립 기록이 남지 않도록 했습니다.
- 왼쪽 상단 상태 rail은 `에디터 | 검토`처럼 한 줄 상태로 통합하고, hover로 스타일/동작이 바뀌지 않게 하며 실제 상태 변경 시 200ms 간격으로 3회 깜빡이도록 했습니다.
- 하단 `자동` 버튼은 ON일 때 초록색, OFF일 때 회색 자동화 아이콘으로 표시하도록 보정했습니다.
- 터미널 로그 텍스트 토글 UI를 비활성화하고, 하단 `터미널` 버튼만 로그 표시/숨김을 제어하도록 정리했습니다.
- 글로벌 캔버스 우측 상단에 `+`, `-`, `ㅁ` 줌 컨트롤을 추가해 확대/축소/화면 너비 맞춤을 바로 실행할 수 있게 했습니다.
- 러프컷 멀티클립 EDL은 프로젝트 JSON의 clip boundary를 fallback으로 읽어 실제 원본 `source_path`와 clip-local time 매핑을 유지하도록 보정했습니다.
- 러프컷 테이블에서 수정한 제목/태그가 `roughcut_state`, Markdown guide, EDL/SRT/render plan 저장 흐름에 반영되도록 보강했습니다.
- 삭제/비활성화 기록: 러프컷 상단 `에디터` 버튼을 제거했습니다. 화면 전환은 왼쪽 사이드바 `에디터`/`러프컷` 버튼으로 대체됩니다.
- 삭제/비활성화 기록: 사이드바 `STT 모드` 항목을 제거했습니다. STT Mode는 하단 전역 메뉴 버튼으로 유지됩니다.
- 삭제/비활성화 기록: `터미널 로그 보기/숨기기` 텍스트 토글을 제거했습니다. 하단 `터미널` 버튼이 대체 경로입니다.
- 자막 동영상 출력 창 하단에 `기본값 저장`과 `기본값 불러오기` 버튼을 추가했습니다.
- 기존 `저장`은 현재 설정을 `dataset/user_settings.json`의 `export_dialog`에 저장하고, `기본값 저장`은 별도 `export_dialog_defaults` 슬롯에 저장합니다.
- `기본값 불러오기`는 저장된 기본값을 현재 출력 창 컨트롤에 적용하고 미리보기를 즉시 갱신합니다.
- 자동 홈 복귀 600초 타이머는 자막 생성 중에는 동작하지 않고, `EditorPipeline`의 `자막 생성 완료` 시점 이후부터 시작되도록 변경했습니다.
- 마우스 클릭/이동, 휠, 키보드, 터치 이벤트가 감지되면 완료 후 idle 타이머를 다시 600초로 리셋해 사용자가 편집 중인 상황에서 홈으로 복귀하지 않도록 했습니다.
- 완료 후 600초 동안 입력이 없으면 backend의 편집 대기 `edit_event`를 `exit` 상태로 풀어 파이프라인을 정리하고 홈으로 복귀하도록 했습니다.
- 앱 전체 큰 구역을 사이드바, 작업영역, 하단 메뉴, 터미널/큐 패널 기준으로 2px 간격과 둥근 테두리 패널 스타일에 맞춰 정렬했습니다.
- `ui/style.py`에 objectName scoped 패널 스타일 helper를 추가해 자식 위젯 스타일을 건드리지 않고 큰 영역만 패널화할 수 있게 했습니다.
- 사이드바 shell, 메인 workspace stack, 터미널 로그, 큐 테이블, 러프컷 하단 테이블 host, 하단 작업 패널을 각각 독립 QWidget 파일로 분리했습니다.
- 삭제/비활성화 기록: `MainWindow._build_bottom_queue_table()`과 `MainWindow._build_bottom_roughcut_table()`을 제거했습니다. 동일 UI는 `QueuePanelWidget`과 `RoughcutTablePanel`이 담당하며, 기존 mixin 호환을 위해 `MainWindow.queue_table`, `queue_header_lbl`, `roughcut_bottom_host_layout` alias는 유지됩니다.
- 왼쪽 상단 상태 rail은 에디터/STT/러프컷/숏폼 화면에 맞춰 `대기`, `파일열기`, `자막로드`, `VAD검토`, `Whisper`, `LLM교정`, `세그먼트`, `저장중`, `저장완료`, `렌더중`, `러프컷검토`, `러프컷완료` 등 짧은 단계 라벨을 표시합니다.
- 상태 rail은 실제 라벨이 바뀔 때만 기존 200ms 간격 3회 깜빡임 피드백을 유지하고, hover만으로 상태가 바뀌지 않도록 유지했습니다.
- 화자 설정 창을 compact 행 구성으로 정리하고, 화자명 박스를 클릭하면 화자 이름을 변경할 수 있게 했습니다.
- 화자명 변경 시 `voice_data/spk{번호}_*.wav` 학습 파일명을 안전한 이름으로 변경하고, 실패 시 이미 변경된 파일을 되돌리도록 보강했습니다.
- 변경된 화자명은 메인 화자 위젯, 타임라인 화자 표시, 화자 메뉴, diarize 학습 reference 파일 선택 흐름에 반영됩니다.
- 하단 디테일 타임라인의 `오디오` 파형 트랙을 `분석` 트랙으로 전환해 VAD 음성 구간, 무음 구간, STT 대기, 짧은 자막, CPS 위험, 장문 자막을 색상 블록으로 표시합니다.
- 러프컷 결과가 있는 경우 분석 트랙은 keep/trim/remove/highlight/move 판단과 ideal/acceptable/risky cut safety를 우선 표시합니다.
- `ui/timeline/timeline_analysis.py`를 추가해 디테일 캔버스와 글로벌 미니맵이 같은 분석 marker 계산을 공유하도록 했습니다.
- 글로벌 미니맵은 기존 파형 가독성을 유지하면서 분석/컷 안전도 marker를 배경 overlay로 표시해 전체 구간 위험도를 빠르게 훑을 수 있게 했습니다.
- 중앙 메인 빈 작업 화면의 quick action을 `파일`, `폴더`, `프로젝트` 3개 버튼으로 구성했습니다.
- 삭제/비활성화 기록: 왼쪽 사이드바의 `프로젝트` 열기 버튼을 제거했습니다. 동일 기능은 중앙 메인 위젯의 `프로젝트` quick action 버튼으로 대체됩니다.
- 공용 UI 아이콘을 직접 수정 가능한 `assets/icons/ui/*.svg` 자산으로 분리했습니다.
- `assets/icons/README.md`에 아이콘 파일명, `24x24` viewBox, `currentColor` 색상 규칙, alias 관리 규칙을 정리했습니다.
- `ui/style.py`의 `line_icon()`은 SVG 파일을 먼저 렌더링하고, SVG 누락/오류 시 기존 QPainter 아이콘으로 fallback 하도록 보강했습니다.
- 러프컷 테이블 상단 패널을 액션/요약 1줄과 선택 구간 상세 1줄로 재구성해 하단 패널 공간 효율을 높였습니다.
- 러프컷 선택 구간 상세에 판단, 안전도, Trim 범위, story role, 컷 근거, 출력 범위를 표시하도록 보강했습니다.
- 러프컷 상단 컨트롤에 이전/다음 후보 이동, 구간 재생, 정지, 렌더 상태 표시를 추가하고 기존 분석/EDL/가이드/SRT/렌더계획 저장 기능은 유지했습니다.
- `ui/roughcut/roughcut_detail.py`를 추가해 선택 챕터 상세 정보, 사용 자막 범위, story role/신뢰도, 이동 권고, 위험도, 컷 근거를 별도 패널로 표시합니다.
- 러프컷 상세 패널에 `keep/trim/remove/highlight/move` action 선택과 Trim In/Out 직접 입력, 적용 버튼을 추가했습니다.
- 컷 조정 적용 시 `roughcut_state.user_edits`에 action/trim/status/reason을 저장하고, decision/EDL/Markdown guide를 다시 계산하도록 보강했습니다.
- 러프컷 테이블과 프리뷰/상세 패널에 `ideal`, `acceptable`, `risky` 컷 안전도 색상 표시와 필터를 추가했습니다.
- 컷 근거의 `gap boundary`, `phrase boundary`, `inside phrase` 정보를 사람이 읽기 쉬운 라벨로 표시해 위험 컷 판단 이유를 바로 확인할 수 있게 했습니다.
- 러프컷 프리뷰에 `반복` 토글을 추가해 현재 챕터 구간을 반복 재생할 수 있게 했습니다.
- `이전`/`다음` 후보 이동은 현재 안전도 필터에서 보이는 행만 대상으로 이동하고 즉시 구간 프리뷰를 재생하도록 보강했습니다.
- 멀티클립 EDL의 `clip_index`와 `source_path`를 프리뷰 배지에 표시해 현재 재생 후보가 어떤 원본 clip에서 오는지 확인할 수 있게 했습니다.
- 러프컷 하단 패널에 `검증`, `렌더`, `복구` 버튼을 추가해 dry-run 검증, QThread 기반 실제 렌더 실행, 실패한 렌더 plan 재시도를 연결했습니다.
- 렌더 진행/성공/실패 상태는 기존 `render_status_lbl`에 표시하고, 명령 수/return code/오류 메시지는 러프컷 로그로 표시합니다.

## 문서 / 액션아이템 정리
- GitHub 첫 화면에서 프로젝트를 바로 확인할 수 있도록 한글 `README.md`를 추가했습니다.
- README에는 프로젝트 설명, 주요 기능, macOS/Windows 요구사항, 설치 방법, 실행 방법, 검증 명령, 주요 문서 안내를 정리했습니다.
- `check_list.md`를 추가해 미완료 체크리스트와 대표님 확인 체크포인트를 별도 문서로 분리했습니다.
- `ACTION_ITEMS.md`에서는 완료 항목과 중복 체크포인트를 제거하고, 구현 예정 항목/버그 중심으로 정리했습니다.
- 새 액션아이템을 추가할 때 `봐야 할 파일`과 `봐야 할 함수/클래스` 후보를 함께 적도록 운영 규칙을 추가했습니다.
- 기능, `def` 함수, `class`, 공용 helper, UI action, signal/slot 등을 삭제할 경우 `RELEASE_v03.00.00.md`에 삭제 대상/사유/영향 범위를 기록하도록 `AGENTS.md`에 명시했습니다.
- ACTION_ITEMS와 AGENTS의 역할을 분리하기 위한 후속 문서 정리 항목을 추가했습니다.
- 다음 채팅에서 바로 이어갈 수 있도록 `AGENTS.md`에 v03.01.14 기준 시작 프롬프트와 필수 참고 파일/검증 명령을 추가했습니다.
- 현재 남은 주요 UI/UX 후속 항목은 전체 레이아웃 패널화, 사이드바/상태 표시 정리, 러프컷 결과 버전 관리입니다.

## 다음 작업
- RC-D6 러프컷 결과 후보 버전 관리
- DOC-ORG1 ACTION_ITEMS / AGENTS 문서 책임 분리
