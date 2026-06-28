DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio next NLE Taption runtime contract scout after playhead jump 20260628

findings:
1. **차기 비파괴 NLE/Taption 런타임 규약 슬라이스 추천**:
   - **추천 항목**: **"NLE Subtitle card double-click text editor focus without full timeline re-render" (자막 카드 더블 클릭 시 타임라인 전체 재그리기 차단 및 포커스 격리)**
2. **선정 사유**:
   - **이유**: 타임라인 내 자막 카드 더블클릭 이벤트 발생 시, 텍스트 편집기 포커스 이동(`focus_editor_at_row`)과 텍스트 셀렉션 갱신만 수행하고, 타임라인 캔버스의 full-repaint/re-render(뷰 갱신 오버헤드)를 철저히 억제하여 텍스트 포커싱 반응 속도를 초고속화하는 뷰-격리 규약(contract) 수립.
3. **오너 파일 (Owner Files)**:
   - `ui/timeline/timeline_global.py` (자막 카드 클릭/더블클릭 핸들링)
   - `ui/editor/ux/subtitle_text_edit.py` (텍스트 에디터 포커스 바인딩)
4. **Focused Tests**:
   - `tests/test_timeline_subtitle_double_click_focus_isolation.py` [NEW] : 자막 카드 더블클릭 trigger 시, `timeline_canvas` 의 `update()` (repaint)가 호출되지 않고 오직 `focus_editor_at_row` 가 focus in 으로 발동됨을 mock assertion으로 증명.
5. **Audit Artifact Path**:
   - `tools/audit_nle_subtitle_card_double_click_isolation.py` [NEW] : 정적 분석을 통해 double click callback 에서 canvas force-repaint path 및 model write path 가 차단되어 `passed=true` 임을 검증하는 audit 스크립트.
6. **NAS 필요 여부**:
   - **불필요 (No)**: 자막 타이밍 모델/STT/VAD 결과물에 어떠한 영향도 미치지 않는 GUI view-repaint/focus 최적화 규약이므로 HeyDealer benchmark validation 이 불필요함.
7. **Acceptance Gate**:
   - 1회 double-click focus trigger 시 소요 시간이 메인 GUI 스레드 기준 0.5ms 이하로 즉각 완료될 것 (`time.monotonic()` delta assertion).

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-070859-next-nle-taption-runtime-contract-scout.md` 파일 내용 및 index 맵핑 상태 점검.
