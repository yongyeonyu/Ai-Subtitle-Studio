DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio NLE preview skimming cache-miss UI-thread block prevention prep 20260628

findings:
1. **cache miss가 sync decode/UI 스레드 block으로 돌아가지 않음을 증명할 제안**:
   - **방법**: `tests/test_video_player_widget.py` 에 mock test spy 를 장착. ffmpeg 디코딩 함수(`ensure_preview_frame`) 호출 시 일부러 `time.sleep(0.1)` (100ms) 지연을 주입함.
   - UI thread 에서 `preview_seek` 스크러빙/시킹을 수행했을 때, cache miss 상태임에도 불구하고 메인 스레드가 대기(blocking)하지 않고 즉시 1ms 이내로 제어권을 반환하는지 `time.monotonic()` 시간 차이를 측정하여 단언(assert).
   - 비동기 worker thread 가 완료된 후 시그널(`preview_thumbnail_ready`)을 통해 비로소 surface 렌더를 호출하는 비동기 분기 구조임을 증명함.
2. **추가해야 할 가장 좁은 guard/audit**:
   - `tools/audit_nle_preview_skimming_cache.py` : `ui_thread_decode_allowed=False` 지시어가 로깅 파라미터 및 `video_player_surface.py` 에 하드코딩 형태로 안전하게 고정되어 있는지 코드 파싱 감사 규칙 검증 보강.
   - `thread_concurrency_parity` 검사 : ffmpeg decoder worker thread-id 가 Main UI thread-id와 다르게 스케줄링됨을 runtime logger 에서 확인하는 항목 추가.
3. **문서 업데이트 위치**:
   - `docs/FEATURE_REGISTRY.md` : Skimming preview frame cache 기능의 "UI Thread non-blocking async guarantee" 상세 속성 설명 보강.
   - `docs/ARCHITECTURE.md` : UI/UX thread boundary 란에 ffmpeg daemon worker 와 GUI surface 간의 비동기 시그널 연동 모델 도해/설명 추가.
4. **추천 다음 슬라이스**:
   - **추천 항목**: **"NLE Skimming Cache Miss UI Thread Block-Free Time Assertion" (썸네일 캐시 miss 시 UI 스레드 타임 지연 검증 단언 테스트 보강)**

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-163300-nle-preview-skimming-cache-miss-prep.md` 파일 내용 및 index 맵핑 상태 점검.
