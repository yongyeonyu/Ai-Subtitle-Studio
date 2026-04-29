<!--
Document-Version: 03.00.43
Phase: PHASE2
Last-Updated: 2026-04-29
Updated-By: Codex with 대표님
Previous-Content: v03.00.42 사이드바 자동처리 카드 화살표 제거
This-Update: v03.00.43 자동설정 저장 후 작업 화면 유지
Copilot-Handoff: v03.00.43 개발 기준 릴리즈 노트입니다. 다음 구현은 RC-D1 러프컷 상세 패널입니다.
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

## 문서 / 액션아이템 정리
- `check_list.md`를 추가해 미완료 체크리스트와 대표님 확인 체크포인트를 별도 문서로 분리했습니다.
- `ACTION_ITEMS.md`에서는 완료 항목과 중복 체크포인트를 제거하고, 구현 예정 항목/버그 중심으로 정리했습니다.
- 새 액션아이템을 추가할 때 `봐야 할 파일`과 `봐야 할 함수/클래스` 후보를 함께 적도록 운영 규칙을 추가했습니다.
- 기능, `def` 함수, `class`, 공용 helper, UI action, signal/slot 등을 삭제할 경우 `RELEASE_v03.00.00.md`에 삭제 대상/사유/영향 범위를 기록하도록 `AGENTS.md`에 명시했습니다.
- ACTION_ITEMS와 AGENTS의 역할을 분리하기 위한 후속 문서 정리 항목을 추가했습니다.
- 현재 남은 주요 UI/UX 후속 항목은 전체 레이아웃 패널화, 사이드바/상태 표시 정리, 글로벌 캔버스 줌 컨트롤, 분석/컷 안전도 트랙, 화자 설정 compact UI, SVG 아이콘 자산화입니다.

## 다음 작업
- BUG-STT1 생성 중 STT Mode 전환 확인/재시작
- RC-D1 러프컷 상세 패널
