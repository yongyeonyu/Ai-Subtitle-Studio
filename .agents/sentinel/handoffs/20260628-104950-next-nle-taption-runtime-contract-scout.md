DEX_READY_FOR_REVIEW
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio next NLE/Taption runtime contract scout after relink parity

findings:
1. **차기 NLE/Taption 런타임 규약/프로젝션 슬라이스 추천**:
   - **추천 항목**: **"NLE playhead seek speed-up and validation bypass" (타임라인 단일 클릭 재생헤드 점프 시 heavy model validation을 우회하고 재생헤드 렌더러 위치 동기화만 초스피드로 완료하는 검증 규약)**
2. **NLE/Taption 발전 기여 이유**:
   - 재생헤드(playhead)를 이동시킬 때 매번 heavy한 subtitle segments validation 및 range checking을 수행하여 frame rate 저하(stuttering)가 생길 우려가 있음. 단순 playhead seek (재생헤드 점프) 시에는 무거운 NLE state validation을 bypass(우회)하고 GUI update만 단행함으로써 seek 응답성을 극대화하는 validation bypass contract 가 필요함.
3. **오너 파일 및 함수 (Owner Files/Functions)**:
   - `ui/timeline/timeline_canvas.py` : `scrub_sec` (마우스 드래그 및 클릭 재생헤드 이동 이벤트 핸들러)
   - `ui/editor/editor_timeline_video.py` : `seek_video_and_update_playhead` (재생헤드 갱신)
4. **Focused Tests to add**:
   - `tests/test_nle_playhead_seek_bypass.py` [NEW] : playhead seek가 발생했을 때, NLE state 의 `validate_segments` 가 호출되지 않고 frame-step 렌더러의 playhead position만 즉각 일치하는지 assert하는 unit test.
5. **Audit Artifact Path**:
   - `tools/audit_nle_playhead_seek.py` [NEW] : static 분석을 통해 playhead seek flow 내에 heavy-weight STT/VAD model validation 호출이 제거 및 우회되어 있는지 정적 감사 보고서 작성.
6. **NAS 필요 여부 (NAS HeyDealer validation)**:
   - **불필요 (No)**: 자막 생성 파이프라인(STT/VAD/Word Precision/Postprocess)에 일체 영향이 없는 재생헤드 이동 속도 최적화 및 우회 검증이므로 HeyDealer benchmark validation 이 불필요함.
7. **Rollback Risk**:
   - **리스크**: seek validation bypass 시점과 실제 자막 편집 시점의 validation sync가 어긋나 에러 상태가 누락될 리스크.
   - **대책**: validation bypass 는 오직 "mouse click/drag seek" 상태에만 한정 적용하며, text edit focus 가 들어오거나 edit commit 이 발생하는 즉시 validation sync 가 full-run 되도록 lock sequence 설계.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-104950-next-nle-taption-runtime-contract-scout.md` 파일 내용 및 index 맵핑 상태 점검.
