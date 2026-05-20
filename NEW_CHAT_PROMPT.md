# AI Subtitle Studio - New Chat Prompt

아래 상태에서 작업을 이어가 주세요.

작업 경로:
- `/Users/u_mo_c/Downloads/ai_subtitle_studio`

시작할 때 반드시 읽을 문서:
1. `AGENTS.md`
2. `ACTION_ITEMS.md`
3. `CODEMAP.md`
4. `test_case.md`
5. `test_result.md`
6. `README.md`

중요 규칙:
- 답변은 한국어로.
- 임의 UI/UX 수정 금지.
- dirty worktree를 되돌리지 말고 필요한 파일만 좁게 수정.
- 커밋 / 푸시 / 릴리즈는 내가 명시적으로 요청할 때만.
- 긴 로그는 채팅에 붙이지 말고 `output/manual_verification/latest/...` 산출물 경로 중심으로 정리.
- 성능 최적화는 자막 품질을 절대 떨어뜨리지 않는 범위에서만 진행.

현재 확인된 최신 상태:
- 공식 one-command QA runner는 이미 구현 완료 상태입니다.
- 실앱 기준 `quick`, `major`, `full`이 모두 통과했습니다.
  - `output/manual_verification/latest/qa_suite_quick_20260520_174600`
  - `output/manual_verification/latest/qa_suite_major_20260520_183244`
  - `output/manual_verification/latest/qa_suite_full_20260520_193515`
- 최신 bundle-refreshed full 재검증 artifact는 `output/manual_verification/latest/qa_suite_full_20260520_210149` 입니다.
- 현재 신규 핵심 작업은 `ACTION_ITEMS.md` item 28의 도움말-기반 QA 재구성입니다.

runner 운영 규칙:
- automation / app-command / editor command surface가 바뀌었으면 먼저 `./packaging/macos/build_app_bundle.sh`
- 그 다음 `./venv/bin/python tools/qa_suite_runner.py full`
- 실패 시 `suite_result.json` 기준으로 먼저 `app_sequence` / `full_media`를 분리
- 원인 분류는 먼저 `code regression / fixture drift / environment-bundle issue`
- `code regression` 또는 `stale bundle`일 때만 가장 작은 범위로 수정

지금 이 채팅에서 이어가야 할 우선순위:
1. `ACTION_ITEMS.md` item 28 수행 시작
   - UI/UX, 자막 편집기, 캔버스, 세그먼트 편집, 메뉴 owner 파일/함수와 현재 QA coverage를 매트릭스로 정리
   - 초보자용 도움말을 처음부터 다시 설계
   - 각 도움말 장을 `quick / major / full` 중 어느 profile이 책임지는지 연결
2. 현재 runner에 이미 있는 범위와 빠진 범위를 구분
   - 이미 강한 범위: `editor_compact_macau`, `video_menu_macau`, `save_export_macau`, `menu_stt_lora_macau`, `tinyping_fast_60s`, `tinyping_auto_60s`, `tinyping_high_60s`
   - 아직 도움말 기준으로 명시 매핑이 약한 범위: `show-home`, `open-srt`, `open-media`, `start-current-pipeline`, `start-current-roughcut`, `start-multiclip`, `queue-folder`, `queue-files`, `editor-pin-shadow-playhead`, `editor-clear-shadow-playhead`, `editor-zoom-max`, `editor-select-segment`
3. 도움말 작성 전제
   - standalone `help/` 디렉터리는 현재 repo root에 없음
   - 기존 안내는 `README.md`, `test_case.md`, `test_result.md` 등에 분산되어 있음
   - 새 도움말은 기존 문서를 참고만 하고 처음부터 다시 작성
   - 각 장마다 실제 스냅샷 PNG와 관련 QA scenario / fixture / 기대 결과를 함께 적기
4. item 28 이후에 돌아갈 기존 성능 backlog
   - item 12: busy 상태 `ping` / `guided-subtitle-status` 응답성
   - item 15: duplicated segment/project state와 lazy hydrate
   - item 16: warm session `critical` memory pressure
   - item 18: stage trim cost attribution

현재 해석:
- 공식 QA suite 자체는 pass 상태입니다.
- 하지만 “처음 쓰는 사람용 도움말” 기준의 기능 분류, 스냅샷, chapter-to-QA 연결은 아직 완성되지 않았습니다.
- 따라서 다음 채팅의 핵심은 `QA runner 유지`가 아니라 `도움말 구조와 QA coverage를 1:1로 재설계`하는 일입니다.

다음 채팅에서 바로 시작할 추천 작업:
- `ACTION_ITEMS.md` item 28부터 시작
- `CODEMAP.md`, `tools/qa_suite_runner.py`, `tools/appctl.py`, `ui/editor/ux/*`, `ui/timeline/*`, `ui/home_*`, `ui/settings/*` 기준으로 기능 owner/QA 매트릭스 작성
- 도움말 목차 초안 작성
- 누락 scenario를 `quick / major / full`에 어떻게 넣을지 runner 설계
- 이후 실제 스냅샷 캡처와 문서 작성

보고 형식:
- 실행 모드
- 결과: pass / fail / blocked
- 저장 위치
- 실패 항목 요약
- 분류: regression / fixture / environment
- 코드 수정 여부
- 문서 반영 여부
- 남은 위험 1~3줄
