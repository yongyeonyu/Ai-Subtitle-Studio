DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio next NLE Taption runtime contract scout after preview cache miss 20260628

findings:
1. **차기 비파괴 NLE/Taption 런타임 규약 슬라이스 추천**:
   - **추천 항목**: **"NLE Timeline wheel-zoom event decoupling from primary model direct write" (휠 스크롤/줌 시 primary subtitle model 직접 쓰기 차단 및 뷰포트 스케일 격리 무결성 검증)**
2. **선정 사유**:
   - **이유**: `ui/timeline/timeline_widget.py` 및 `timeline_global.py` 의 `wheelEvent`가 휠 스크롤/줌 액션을 취할 때, primary subtitle model 이나 database sequence 에 불필요한 write/sync 를 일으키지 않고, 오직 렌더링용 viewport horizontal scale (`h_scale` / `zoom_factor`)만 뷰-바운디드하게 변경하도록 Decouple 및 격리 상태를 보장하는 규약(contract) 수립.
3. **오너 파일 (Owner Files)**:
   - `ui/timeline/timeline_widget.py` (TimelineWidget 휠 줌/스크롤 제어)
   - `ui/timeline/timeline_global.py` (GlobalCanvasBase 글로벌 뷰 줌 제어)
4. **Focused Tests**:
   - `tests/test_timeline_wheel_zoom_decoupling.py` [NEW] : 휠 줌 이벤트 mock 발생 시, primary subtitle model 의 `segments` 나 NLEState 에 write/dirty flag가 세팅되지 않고 `h_scale` 뷰 속성만 일방향 업데이트됨을 증명.
5. **Audit Artifact**:
   - `tools/audit_nle_viewport_zoom_decoupling.py` [NEW] : static code 분석을 통해 timeline wheel event handler 가 model-writing API(예: `update_segment`, `save_project` 등)를 호출하지 않는지 정적 검증하는 audit 스크립트.
6. **NAS HeyDealer Validation 필요 여부**:
   - **불필요 (No)**: 자막 생성 파이프라인(STT/VAD/Word Precision/Postprocess)에 일체 영향이 없는 순수 GUI view-scale 격리 작업이므로 NAS HeyDealer benchmark validation 대상이 아님.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-164700-next-nle-taption-runtime-contract-scout.md` 파일 내용 및 index 맵핑 상태 점검.
