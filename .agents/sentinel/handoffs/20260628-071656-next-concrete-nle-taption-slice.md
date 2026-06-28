DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio next concrete NLE Taption slice after time-window guard 20260628

findings:
1. **차기 concrete NLE/Taption 편집 동작 슬라이스 추천**:
   - **추천 항목**: **"NLE Sequence duration-bound trimming enforcement on segment boundary edit dual-write" (자막 경계 편집 dual-write 시 프로젝트 전체 미디어 duration-bound 초과 자막의 강제 자동 트리밍)**
2. **선정 사유**:
   - **이유**: `core/project/project_context.py` 의 `_trim_segments_to_project_duration` 이 존재하는 데 반해, NLE dual-write 시점(`nle_dual_write.py`)의 `apply_caption_move` 나 `apply_caption_split` 과 같은 runtime 연산 후에는 미디어 duration-bound 체크 및 duration을 초과하는 자막 영역의 자동 트리밍(trimming) 처리가 완벽히 enforce되지 않고 있음. 이로 인해 dual-write 직후 자막이 미디어 길이를 벗어나 benchmark 가 무너지는 리스크가 존재. 이를 강제하는 dual-write level duration-bound trim enforcement 동작(editing behavior delta)을 신설함.
3. **오너 파일 (Owner Files)**:
   - `core/project/nle_dual_write.py` (dual-write 연산 결과 처리부)
   - `core/project/project_context.py` (duration-bound trim logic 제공부)
4. **Actual Behavior Delta (동작 변경점)**:
   - `nle_dual_write.py` 의 각 `apply_..._pilot` 함수 결과로 산출된 `projected_rows` 에 대해 `_trim_segments_to_project_duration` 을 명시적으로 호출 및 결합.
   - 연산 결과로 자막 끝 시각이 미디어 duration을 넘어가면 자동으로 꼬리를 자르고(trim), duration 밖의 자막은 segment representation 에서 drop.
5. **Focused Tests**:
   - `tests/test_nle_dual_write_duration_trim.py` [NEW] : caption move / split 연산 후 end bounds 가 duration-sec (`180.584s` 등)을 넘을 때, tail collapse 나 validation error 없이 안전하게 trim 됨을 검증하는 integration test.
6. **Audit/Proof Artifact Path**:
   - `output/manual_verification/latest/nle_dual_write_duration_trim_proof/trim_proof_report.md`
7. **NAS 필요 여부 (NAS HeyDealer validation)**:
   - **필요 (Yes)**: 자막의 end-bounds 와 segment duration 변동을 초래하는 편집 연산이므로, HeyDealer first-180s real-media fixture (`heydealer_first_180s.mp4`)를 이용한 end-bound 및 SRT generation parity 검증이 필수적임.
8. **Acceptance Gate**:
   - HeyDealer 180s benchmark 실행 결과 `accepted=true`, `final_last_end_beyond_duration_bound=false`, SRT rows 의 타이밍 overlap 및 monotonic 정합성 깨짐 0건 통과.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-071656-next-concrete-nle-taption-slice.md` 파일 내용 및 index 맵핑 상태 점검.
