<!--
Document-Version: 03.00.27
Phase: PHASE2
Last-Updated: 2026-04-29
Updated-By: Codex with 대표님
Previous-Content: v03.00.26 프로젝트 JSON 단일/멀티클립/러프컷 통합 저장·로드
This-Update: v03.00.27 메인 도움말 창 추가 및 UI 아이콘 캐시 성능 보강
Copilot-Handoff: v03.00.27 기준. 현재 앱 버전은 config.py APP_VERSION 03.00.27입니다. 메인 하단 메뉴의 도움말 버튼은 `ui/help` 탭형 도움말 창을 엽니다. 다음 우선순위는 RC-D1 러프컷 상세 패널입니다.
-->
# AI Subtitle Studio — 액션아이템
# 최종 수정: 2026-04-29
# App Version: 03.00.27

================================================================================
  현재 작업 기준
================================================================================

- 현재 개발 버전: v03.00.27
- 다음 코드 수정 버전: v03.00.28
- 현재 phase: PHASE2
- 현재 큰 흐름: 러프컷 편집 기능 고도화 준비
- create_all 방식 원칙 유지
- 프로젝트 루트에 `_backup*`, `create_all*.py`, `STRUCTURE.txt`, `requirements.txt` 남기지 않기
- requirements는 `requirements-mac.txt` / `requirements-windows.txt` 2개만 운영
- 커밋은 대표님이 명시적으로 요청할 때만 진행
- 문서 4개는 커밋 직전 최종 업데이트:
  - `AGENTS.md`
  - `ACTION_ITEMS.md`
  - `File_structure.txt`
  - `RELEASE_v03.00.00.md`

================================================================================
  완료 체크리스트
================================================================================

[PHASE2 러프컷 엔진]

  [x] P2-RC1  roughcut 데이터 모델
       | - `core/roughcut/models.py`
       | - Subtitle/RoughCut/Storyboard/EDL dataclass 기반 모델

  [x] P2-RC2  gap detector
       | - `core/roughcut/gap_detector.py`
       | - 자막 없는 구간 탐지

  [x] P2-RC3  transcript packing
       | - `core/roughcut/transcript_packer.py`
       | - 자막 행을 phrase 단위로 압축하고 LLM/분석 입력 문자열 생성

  [x] P2-RC4  visual/scene 기반 helper
       | - `core/roughcut/frame_sampler.py`
       | - `core/roughcut/scene_change_detector.py`
       | - 프레임 timestamp sampling, ffmpeg frame command, 픽셀 차이 기반 scene change 감지

  [x] P2-RC5  topic/semantic chunker
       | - `core/roughcut/topic_detector.py`
       | - `core/roughcut/semantic_chunker.py`
       | - 키워드/topic shift와 phrase 기반 chapter seed 생성

  [x] P2-RC6  story mapper
       | - `core/roughcut/story_mapper.py`
       | - 챕터 순서를 바꾸지 않고 기/승/전/결 story role과 이동 검토 힌트 생성

  [x] P2-RC7  cut safety / edit decision engine
       | - `core/roughcut/edit_decision_engine.py`
       | - gap/phrase boundary 기반 컷 안전도와 keep/trim/remove/highlight/move 판단

  [x] P2-RC8  EDL JSON generator
       | - `core/roughcut/edl_generator.py`
       | - edit decision을 EDL segment와 JSON schema로 변환

  [x] P2-RC9  Markdown guide writer
       | - `core/roughcut/guide_writer.py`
       | - 전체 요약, 추천 흐름, 챕터 표, 편집 판단, 위험 컷 검토 목록 생성

  [x] P2-RC10 run_roughcut_pipeline 단일 진입점
       | - `core/roughcut/pipeline.py`
       | - pack → chunk → story role → decision → EDL → guide 순서 통합

  [x] P2-RC11 renderer skeleton / executor / subtitle retimer
       | - `core/roughcut/renderer_skeleton.py`
       | - `core/roughcut/render_executor.py`
       | - `core/roughcut/subtitle_retimer.py`
       | - ffmpeg concat plan, dry-run executor, EDL 기준 retimed SRT 생성

  [x] P2-RC12 roughcut unittest
       | - `tests/test_roughcut_engine1.py`
       | - roughcut core/pipeline 최소 검증

[러프컷 UI / 프로젝트 연동]

  [x] P2-U1  중앙 러프컷 화면
       | - `ui/roughcut/roughcut_widget.py`
       | - 왼쪽 메뉴 `러프컷 편집 도우미`에서 중앙 stack으로 전환

  [x] P2-U2  러프컷 테이블/가이드/출력
       | - 챕터 표, 상태/판단/안전/출력 시간 표시
       | - EDL JSON, Markdown 가이드, retimed SRT, 렌더 계획 저장

  [x] P2-U3  러프컷 구간 preview
       | - 행 hover/click 기반 구간 미리보기
       | - 멀티클립 전역 시간 → clip-local context 재생

  [x] P2-PROJ1  editor_state / roughcut_state 분리
       | - `core/project/project_context.py`
       | - 프로젝트 JSON 안에서 단일/멀티클립 편집 상태와 러프컷 상태 분리
       | - 단일/멀티클립 → 러프컷 이동 시 서로 상태를 덮어쓰지 않음

  [x] P2-PROJ2  러프컷 최신 자막 반영
       | - 러프컷 진입 시 현재 에디터 자막 signature 기준 재분석
       | - 단일/멀티클립 에디터에서 자막/화자 수정 후 러프컷 재진입 시 반영

  [x] P2-PROJ3  프로젝트 JSON 통합 저장/로드
       | - 단일클립/멀티클립 editor_state와 roughcut_state를 같은 프로젝트 파일에서 저장/복원
       | - 프로젝트 로드 시 저장된 active_work_mode가 roughcut이면 러프컷 화면으로 복귀
       | - 멀티클립 러프컷 EDL을 원본 파일별 source_path와 clip-local time으로 매핑

  [x] P2-RC-REF1  러프컷 UI 기능 세분화
       | - `ui/roughcut/roughcut_state.py`
       | - `ui/roughcut/roughcut_table.py`
       | - `ui/roughcut/roughcut_preview.py`
       | - `ui/roughcut/roughcut_export.py`
       | - `ui/roughcut/roughcut_format.py`

[자막 생성 / STT 품질]

  [x] P2-STT-PRESET1  자막 정확도 프리셋
       | - `core/audio/stt_quality_presets.py`
       | - 빠른/균형/정밀 프리셋과 AI 설정창 연동

  [x] P2-STT-OVERLAP1  Whisper chunk overlap
       | - `core/audio/media_processor.py`
       | - 긴 청크 overlap 생성과 word timestamp 기반 중복 제거

  [x] P2-STT-WORD1  word timestamp 기반 재분할
       | - `core/engine/word_resegmenter.py`
       | - 최대 글자 수, duration, CPS, 문장부호, 무음 gap 기준 재분할

  [x] P2-LLM-CORRECT1  LLM 보정 원칙 강화
       | - `core/engine/llm_correction_guard.py`
       | - 원문 대비 단어 추가/삭제, 타임코드 출력 감지 시 LLM 결과 차단

[UI/UX 보정]

  [x] UI-01  프로젝트 정보 패널
       | - 기본 접힘
       | - 펼침 시 메뉴 버튼 위 overlay 방식
       | - 펼침/닫힘 후 편집 화면 유지

  [x] UI-02  비디오 자막 overlay
       | - 생성 직후 바로 재생해도 현재 자막 provider 동기화

  [x] UI-03  상태/모드 버튼
       | - 진행 단계: 검토/VAD, 인식/Whisper, 생성, 교정/LLM, 완료
       | - 현재 모드: 자막생성/편집/STT/러프컷/숏폼

  [x] UI-04  하단 메뉴 아이콘/텍스트
       | - 시작/처리중/재시작 아이콘
       | - Undo/Redo 명칭과 아이콘
       | - STT ON/OFF 색상 표시
       | - 전원 종료 아이콘

  [x] UI-05  비디오 패널
       | - 확대/축소 화살표 기능 제거
       | - 현재 높이 기준 16:9 폭 고정

  [x] UI-06  타임라인 핸들/선택 테두리
       | - 다이아몬드 버튼을 자막 세그먼트 경계 하단으로 이동
       | - 하단 미니맵 노란 선택선 표시
       | - 상단/화살표 쪽 노란 테두리 제거
       | - paintEvent SIGABRT 방지

  [x] UI-HELP1  메인 도움말 창
       | - 하단 전역 메뉴에 도움말 버튼 추가
       | - `ui/help` 패키지에 도움말 콘텐츠/다이얼로그 분리
       | - 기능별 탭, 사용 방법, 예시, 특정 상황 설명, 추후 스크린샷 공간 제공
       | - `line_icon` 캐시로 반복 아이콘 생성 비용 절감

================================================================================
  다음 구현 체크리스트
================================================================================

[러프컷 세부 기능 고도화]

  [ ] RC-D1  러프컷 상세 패널
       | - 선택 챕터 상세 정보
       | - 컷 근거, 위험도, story role, 사용 자막 범위 표시

  [ ] RC-D2  컷 후보 세부 조정
       | - 챕터별 keep/trim/remove/highlight/move 수동 변경
       | - trim in/out 직접 조정
       | - 변경 사항 `roughcut_state.user_edits`에 저장

  [ ] RC-D3  컷 안전도 시각화
       | - ideal/acceptable/risky 색상/필터
       | - gap boundary / phrase boundary / inside phrase 이유 표시

  [ ] RC-D4  러프컷 preview 고도화
       | - 현재 챕터 반복 재생
       | - 이전/다음 컷 후보 이동
       | - 멀티클립 clip 전환 시 source clip 표시

  [ ] RC-D5  렌더 실행 UI
       | - 현재는 렌더 계획 JSON 저장까지 완료
       | - 다음 단계에서 dry-run/실행/로그/실패 복구 UI 연결

  [ ] RC-D6  러프컷 결과 버전 관리
       | - 같은 프로젝트 안에 여러 roughcut candidate 저장
       | - 후보 비교/선택 기반 마련

[공통 / 인프라]

  [ ] R3  AI 모델 관리 시스템
       | - `model_registry.json`
       | - 모델 install / uninstall UI
       | - OS별 모델 필터링
       | - 첫 실행 시 필수 모델 자동 체크

  [ ] R4  Windows 전기능 연동
       | - faster-whisper CUDA 연동
       | - PyQt6 DLL 충돌 없음
       | - 한글/공백 경로 파일 처리 안정화

  [ ] R13  전체 프로젝트 리팩토링 / 리네이밍 / 기능 분할
       | - 500줄 이상 파일은 기능 분할 후보
       | - 800줄 이상 파일은 우선 분할 대상
       | - SRT 저장/백업/경로 계산, LLM provider 호출, 멀티클립 context/video sync 중복 통합
       | - 기능 삭제 금지
       | - UX 변경은 대표님 확인 체크포인트로 분리

[PHASE3 / iPad]

  [ ] P3-SF1  숏폼 제작기 UI/프로젝트 구조
  [ ] P3-SF2  하이라이트 자동 추출 및 세로 영상 구성
  [ ] P3-SF3  숏폼 자막 스타일/템플릿 출력
  [ ] P3-API1 앱 내장 REST API 서버
  [ ] P3-API2 UI 버튼 인덱싱
  [ ] P3-API3 파일/폴더 리스트 API
  [ ] P3-API4 파이프라인 실행 API
  [ ] P3-API5 Open-WebUI 도구 연동
  [ ] iPad-1  자막 에디터 UI
  [ ] iPad-2  음성 STT 입력 모드
  [ ] iPad-3  LLM 오탈자 자동 추천
  [ ] iPad-4  멀티클립 기능
  [ ] iPad-5  AirDrop/iCloud 연동
  [ ] iPad-6  프로젝트 양방향 동기화
  [ ] iPad-7  유료 과금

================================================================================
  대표님 확인 체크포인트 테스트
================================================================================

  [ ] CP-01 | 첫 화면 UI
       | - 앱 실행 후 첫 화면에서 왼쪽 메뉴 텍스트가 잘리지 않아야 함
       | - `프로젝트 정보`는 기본 접힘 상태여야 함
       | - `프로젝트 정보` 클릭 시 펼쳐지고 다시 클릭 시 접혀야 함
       | - 하단 메뉴 배경이 흰색으로 깨지지 않아야 함

  [ ] CP-02 | 비디오 자막 overlay
       | - 파일 열기 → 자막 처음부터 생성 → 바로 재생
       | - 플레이헤드를 직접 클릭하지 않아도 비디오 위에 현재 자막이 표시되어야 함
       | - 재생 중 자막 경계가 바뀌면 overlay도 따라 바뀌어야 함

  [ ] CP-03 | 기존 SRT 로드
       | - 영상과 같은 이름의 SRT가 있는 파일을 열기
       | - 기존 자막 사용 후 재생하면 비디오 overlay에 자막이 표시되어야 함
       | - `재시작` 시 기존 자막 백업 후 에디터/세그먼트가 초기화되어야 함

  [ ] CP-04 | 멀티클립 전환/재생/offset
       | - 단일클립에서 영상 추가 후 멀티클립으로 전환
       | - 클립 2 또는 클립 3 구간을 클릭 후 재생
       | - 비디오 time과 전체 타임라인 playhead가 올바른 offset으로 동기화되어야 함
       | - 클립 삭제 후 자막이 중복 append 되지 않아야 함

  [ ] CP-05 | 멀티클립 STT/LLM 병렬 처리
       | - 3개 이상 멀티클립으로 자막 생성
       | - 클립1 Whisper 완료 후 클립1 LLM 처리 중 클립2 Whisper가 시작되어야 함
       | - 에디터 append 순서는 클립1 → 클립2 → 클립3 순서가 유지되어야 함

  [ ] CP-06 | STEP 6 재시작
       | - MOV 렌더링/iCloud 백업 중 `재시작` 클릭
       | - 메인 화면으로 빠지지 않고 현재 파일/클립 재시작 흐름으로 남아야 함
       | - 늦게 도착한 렌더링 완료 콜백이 화면 상태를 덮어쓰지 않아야 함

  [ ] CP-07 | 멀티클립 저장 규칙
       | - 개별 자막은 각 영상 파일명과 같은 위치에 저장되어야 함
       | - 통합 자막은 첫 번째 영상 파일명 기준 `_통합.srt`로 저장되어야 함
       | - `_통합.srt`는 기존 자막 사용 후보에서 제외되어야 함

  [ ] CP-08 | STT 모드
       | - `STT` 버튼 ON/OFF 상태가 자동모드처럼 명확히 보여야 함
       | - STT ON 상태에서 `시작` 시 VAD-only 빨간 STT 세그먼트가 생성되어야 함
       | - STT 세그먼트는 프로젝트 파일에는 저장되지만 완료 전 SRT에는 포함되지 않아야 함

  [ ] CP-09 | 화자 세그먼트
       | - 화자 세그먼트 클릭 시 사용 가능한 화자 목록과 색상이 표시되어야 함
       | - 화자 선택 시 해당 세그먼트 화자가 변경되어야 함
       | - 우클릭 시 `음성으로 화자 학습` 기능이 실행되어야 함

  [ ] CP-10 | 설정창 UI
       | - AI/상세/화자/간격/출력/자동설정 창 버튼 높이와 줄맞춤이 일관되어야 함
       | - 텍스트가 잘리거나 버튼 크기가 과도하게 커지지 않아야 함
       | - 시뮬레이터 창의 슬라이더/블록/버튼 줄맞춤이 깨지지 않아야 함

  [ ] CP-11 | 반응형 메뉴
       | - 창 폭을 절반 이하로 줄이면 하단 메뉴 텍스트가 숨고 아이콘만 남아야 함
       | - 자동/터미널/종료 버튼이 잘리지 않고 접근 가능해야 함

  [ ] CP-12 | 러프컷 상태 분리/반영
       | - 단일클립 → 러프컷 이동 시 프로젝트의 단일 편집 상태와 러프컷 상태가 분리되어야 함
       | - 멀티클립 → 러프컷 이동 시 editor_state와 roughcut_state가 서로 덮어쓰지 않아야 함
       | - 러프컷에서 에디터로 돌아가 자막/화자 수정 후 다시 러프컷 진입 시 수정 내용이 반영되어야 함
