DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio next NLE Taption runtime contract scout after viewport zoom 20260628

findings:
1. **차기 비파괴 NLE/Taption 런타임 규약 슬라이스 추천**:
   - **추천 항목**: **"NLE Timeline single-click playhead jump without model state validation overhead" (타임라인 클릭 재생헤드 점프 시 primary model validation 오버헤드 격리)**
2. **선정 사유**:
   - **이유**: 사용자가 타임라인 빈 공간을 단일 클릭하여 재생헤드를 빠르게 점프(`playhead jump`)시킬 때, 자막 텍스트나 타이밍 정합성을 재검증하는 무거운 backend validation(Ollama, WhisperKit backend check 및 primary model database write)을 완전히 우회하고, 오직 뷰포트의 플레이헤드 위치 속성(`current_time` / `current_frame`)과 오디오 재생 상태만을 즉각 업데이트하도록 Decouple 및 격리 상태를 보장하는 규약(contract) 수립.
3. **오너 파일 (Owner Files)**:
   - `ui/timeline/timeline_global.py` (GlobalCanvasBase 마우스 프레스 이벤트 핸들러)
   - `ui/editor/ux/editor_video_controls.py` (재생헤드 프레임 연동)
4. **Focused Tests**:
   - `tests/test_timeline_playhead_jump_validation_isolation.py` [NEW] : playhead jump 시 target model validation(예: `validate_segments`)이 호출되지 않고 오직 playhead tick 만 갱신됨을 mock assertion으로 증명.
5. **Audit Artifact Path**:
   - `tools/audit_nle_playhead_jump_isolation.py` [NEW] : 정적 코드 흐름 분석을 통해 playhead jump mouse event handler 에서 heavy database validation 함수로의 call-path 가 완전히 차단되었는지 검증하고 `passed=true` markdown 보고서 작성.
6. **NAS 필요 여부**:
   - **불필요 (No)**: 자막 타이밍 모델/STT/VAD 결과물에 어떠한 영향도 미치지 않는 UI 인터랙션 최적화 규약이므로 HeyDealer benchmark validation 이 불필요함.
7. **Acceptance Gate**:
   - 1회 playhead jump mouse press API trigger 시 소요 시간이 메인 GUI 스레드 기준 0.5ms 이하로 즉시 즉각 완료될 것 (`time.monotonic()` delta assertion).

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-165700-next-nle-taption-runtime-contract-scout.md` 파일 내용 및 index 맵핑 상태 점검.
