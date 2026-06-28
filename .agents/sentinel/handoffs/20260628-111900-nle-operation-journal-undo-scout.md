DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio NLE operation journal undo contract scout

findings:
1. **`NLEEditorOperation` Kind 스키마 적합성**: 12개 dual-write operation 종류가 `NLEEditorOperation` 스키마 및 `NLE_OPERATION_KINDS` 규약에 완전히 매칭되는지 감사.
2. **`NLEUndoSnapshot` 사전 무결성 확보**: NLE 연산 실행 직전에 `build_nle_undo_snapshot`이 캡처하는 editor_rows, candidate_lanes, silence_gaps, markers가 딥카피 규약 하에서 완벽히 격리 저장되는지 검증.
3. **Commit Release 메타데이터 바인딩**: 트랜잭션 완료 릴리즈 커밋 시의 timing 및 text 변경 메타데이터가 journal operation 레코드 내에 정확히 캡처되는지 감사.
4. **NLE Projection 해시 일치 여부**: `undo_snapshot` 내에 기록된 `nle_projection_hash`가 연산 롤백(undo) 복구 후에 100% 동일하게 재현(Parity)되는지 해시 정합성 체크.
5. **자막 겹침 차단 가드 (No Final Overlap)**: `allow_final_overlap=False` 프레임 정책이 undo/redo replay 후에도 엄격하게 작동하여, micro-overlap을 원천 차단하는지 검증.
6. **동시성 락 가드 (Concurrency)**: undo/redo 큐의 비동기적 충돌을 막기 위해 `global_max_active <= 1` 및 lock boundaries 가 정상 결합되는지 검증.

defer:
- **실제 undo/redo UI 및 이벤트 핸들러 변경**: PyQt QTextDocument 내부 실행 스택 단의 undo/redo UI 단축키 라우팅이나 dialog UI 변경은 Defer 함.
- **operation journal 디스크 파일 저장화 (persisted journal)**: NLE operation journal 히스토리를 `.aissproj` 디스크 파일에 직렬화하여 저장하는 것은 디스크 스키마 변경 요건이므로 Defer 함.
- **실시간 드래그 단위 NLE 쓰기 (per-pixel drag write)**: 드래그 중인 미세 픽셀 단위로 NLE 상태에 매번 쓰는 것은 Defer 함.
- **QML/UI 전환**: QML 전환 시도는 일체 Defer 함.
