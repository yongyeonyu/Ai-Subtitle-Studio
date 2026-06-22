# Handoff

이 문서는 다음 세션이 바로 이어서 작업할 수 있도록 현재 truth surface만 짧게 남기는 용도입니다. 장문의 세션 기록은 여기에 누적하지 않습니다.

## Current Line

- 제품 라인: Python/PyQt6 source app on macOS Apple Silicon
- 코드 버전: `04.00.15`
- 실행 큐 단일 원본: `doc/ACTION_ITEMS.md`
- 문서 루트: `doc/`

## Latest Meaningful Changes

### 1. `.LRF` cut-boundary backend fallback narrowed

- `core/cut_boundary_scan_runtime.py`
  - `.LRF` 입력에서 `AVFoundation` 대신 `FFMPEG`를 우선 선택하도록 자동 backend 결정을 보강했습니다.
- `tests/test_cut_boundary_auto_scan_backend.py`
  - `.LRF` + `avfoundation` 요청 시 `CAP_FFMPEG`로 우회되는 회귀 테스트를 추가했습니다.
- 확인:
  - `./venv/bin/python -m pytest -q tests/test_cut_boundary_auto_scan_backend.py tests/test_lrf_support.py`
  - 결과: `32 passed`

### 2. Local cache / model storage trimmed

- 로컬 캐시 정리와 Ollama/Hugging Face 모델 삭제를 진행해 저장 공간을 줄였습니다.
- 이 변경은 저장소 동작이 아니라 개발 머신 로컬 상태 정리입니다.

### 3. Documentation normalized and compacted in `doc/`

- 루트 문서는 `AGENTS.md`만 남기고 나머지 개발 문서를 `doc/` 아래로 이동했습니다.
- `README`와 문서 인덱스를 `doc/README.md`로 합쳤습니다.
- `anti_agents.md`와 `cooperation.md` 내용은 `doc/cooperation.md`로 통합했습니다.
- 오래된 server-mode carry-over 결정은 별도 `DECISIONS` 문서 대신 `doc/ACTION_ITEMS.md`의 parked candidate로 흡수했습니다.
- `doc/idea.md`, `doc/reference/File_structure.txt`, `doc/reference/CODEMAP.md`는 현재 문서와 중복되어 삭제했습니다.
- 보존 reference map은 `doc/reference/SUBTITLE_GENERATION_DOMAIN_MAP.md`와 `doc/reference/LONG_FILE_OWNERSHIP_MAP.md`이며, `tests/test_subtitle_generation_domain_map.py`가 직접 지킵니다.
- `HANDOFF.md`는 긴 로그 누적본 대신 현재 상태만 남기는 짧은 버전으로 재작성했습니다.

### 4. Xcode / Swift migration temp assets removed

- 저장소에 남아 있던 `native/macos/AIStudioNative`와 `experiments/whisperkit_persistent_worker` 패키지를 제거했습니다.
- `packaging/macos/build_app_bundle.sh`와 `validate_app_bundle.sh`는 더 이상 저장소 내부 Swift worker/CLI를 필수로 기대하지 않습니다.
- `doc/reference/*`와 maintenance budget 기준도 현재 source-app 기준 경로만 가리키도록 정리했습니다.

### 5. Global Korean runtime error popup added

- `main.py`의 전역 예외 훅, 스레드 예외 훅, unraisable hook에서 공통 한글 오류 팝업을 띄우도록 연결했습니다.
- 팝업은 오류 유형, 원인 요약, 영향 가능성, 재시도 안내, 로그 파일 경로를 함께 보여 줍니다.
- offscreen/minimal 테스트나 안전하지 않은 UI 컨텍스트에서는 팝업을 억지로 띄우지 않고 로그만 남깁니다.

### 6. Subtitle recognition accuracy ideas triaged with Jammini

- `doc/ACTION_ITEMS.md`에 자막 인식 정확도 가드레일과 owner map을 추가했습니다.
- `case1_top_gap_owner`의 all-singleton digit common-split skip path는
  `core/engine/subtitle_timing.py`에 좁게 적용되어 있고, 회귀 테스트
  `test_common_split_guard_can_skip_all_singleton_digit_groups`로 잠갔습니다.
- STT, VAD, LLM, model route 기본값은 변경하지 않았습니다.
- Apple Speech는 여전히 benchmark-only challenger로 취급합니다. accepted artifact가 품질/타이밍/segment 안정성/repeat 기준을 넘기 전에는 기본 STT 경로로 승격하지 않습니다.
- 다음 정확도 후보는 `case1_top_gap_owner`, low-confidence review artifact, ground-truth/LoRA candidate hinting 순서로 검토하되, `waste_action_item.md`의 broad threshold/model-route 실패군은 반복하지 않습니다.
- 이번 regression lock은 benchmark accepted artifact 승격이 아닙니다. case1/X5
  비교 benchmark는 별도 증빙으로 남겨야 합니다.

### 7. Jammini communication contract updated from Taption docs

- Taption `AGENTS.md`, `docs/cooperation.md`, `docs/AGENT_HARNESS.md`, `.agents/sentinel/*` 규칙을 확인하고, 현재 저장소에는 통신/물리 handoff 규칙만 clean-room으로 반영했습니다.
- 영구 규칙은 `doc/cooperation.md`에 모았습니다. `AGENTS.md`는 해당 문서를 가리키는 짧은 역할 설명만 보강했습니다.
- Taption/iOS 전용 `ios/Scripts/jammini_*` 명령, connected-device, TestFlight, App Store 문맥은 이 저장소로 가져오지 않았습니다.

### 8. Jammini local route probe added

- `tools/jammini_watchdog.sh --status`를 추가해 conversation id 없이 queue/state/log/sentinel 경로와 `ag-send` 사용 가능 여부를 JSON으로 확인할 수 있게 했습니다.
- `tools/jammini_watchdog.sh --handoff-probe`를 추가해 `.agents/sentinel/handoffs/` 물리 handoff 파일 생성과 `.agents/sentinel/handoff.md` pointer prepend를 검증할 수 있게 했습니다.
- `tools/jammini_watchdog.sh --handoff-list`를 추가해 최신 handoff 파일, index pointer, `DEX_REVIEW_READY` 포함 여부를 JSON으로 확인할 수 있게 했습니다.
- Antigravity `last` cache가 Taption 대화를 가리키는 상태를 확인하고, 현재 repo workspace와 매칭되는 대화 `2aefcd7d-ab16-4cd7-a88a-1a2482046524`로 교정했습니다.
- `tools/jammini_watchdog.sh --conversation-id auto`를 추가해 다음부터는 현재 프로젝트 workspace와 매칭되는 Antigravity 대화를 자동으로 선택할 수 있게 했습니다.
- 이 기능은 로컬 handoff 경로 점검용입니다. Antigravity chat ACK나 worker route 성공 증명은 아닙니다.

### 9. Duplicate subtitle guard added after v04.00.15 release snapshot

- 중복 자막 원인은 주로 STT2 selective recheck replacement 내부의 근접 동일 문장과 output selector source 후보의 micro-merge 후 한 행 반복이 겹친 케이스로 정리했습니다.
- `core/audio/stt_recheck_service.py`는 근접 동일 replacement row를 병합 전에 한 번 dedupe합니다.
- `core/engine/subtitle_engine.py`는 source 후보와 최종 선택 결과 모두 후단 보정을 거치게 했습니다.
- `core/engine/subtitle_final_integrity.py`는 `안 바뀌어요 안 바뀌어요`처럼 같은 토큰 묶음이 정확히 두 번 붙은 한 행 반복을 한 번으로 접습니다.
- 후속 확인 중 X5 accepted output 재적용에서 `11.4` 같은 단독 측정값 행이 shadow drop 또는 이전 continuation row merge로 흔들릴 수 있어, standalone measurement 행은 보존하도록 막았습니다.
- `core/engine/subtitle_accuracy_pipeline.py`는 한 행 내부 self-repeat을 context risk로 세고 annotation flag를 남깁니다.
- 확인: `tests/test_stt_recheck_service.py`, `tests/test_subtitle_engine_settings.py`, `tests/test_subtitle_accuracy_pipeline.py` focused set 통과. 추가 X5 cached replay artifact `output/manual_verification/latest/20260622_233750_duplicate_guard_x5_cached/summary.md`도 pass입니다.
- 주의: 해당 X5 확인은 cached real-X5 artifact replay이며, 원본 `test video/X5_시승기_후반.MP4`가 없어 fresh media benchmark promotion은 아닙니다.

## Active Queue

현재 상단 active queue는 `doc/ACTION_ITEMS.md`의 `Post-Generation Editor Readiness And Verification Index`입니다.

최근 진행:

- 생성 완료 직후 `0ms` 이벤트 턴에 cleanup/waveform bundle이 붙던 경로를 짧은 editor-ready grace 뒤로 미뤘습니다. 목적은 생성 완료 후 첫 클릭, 재생, 타임라인 입력이 heavy cleanup보다 먼저 잡히게 하는 것입니다.
- 확인: `tests/test_editor_autosave_cleanup.py tests/test_editor_roughcut_draft.py` -> `104 passed`; 관련 playback/manual interaction runtime guard 3개도 pass입니다.
- 아직 실제 source-app Macau/X5 화면에서 full-frame shake geometry capture와 첫 상호작용 proof는 남아 있습니다.

가장 좁은 다음 목표:

1. source-app Macau/X5에서 생성 완료 직후 첫 클릭/재생/타임라인 입력과 full-frame shake geometry를 캡처해 offscreen contract가 실제 화면에서도 맞는지 확인
2. Macau / X5 기준으로 playback, playhead, footer, overlay, minimap 정렬 증빙 보강
3. `정밀` 완료 상태의 시각적 distinction 추가 여부를 좁은 범위로 검증
4. 자막 인식 정확도는 코드 변경 전 `doc/ACTION_ITEMS.md`의 `Subtitle Recognition Accuracy Guardrails`와 `doc/VALIDATION.md`의 quote-back 필드 기준으로만 다음 실험을 엽니다.

## Key Verification Anchors

- 최신 full QA baseline:
  - `output/manual_verification/latest/qa_suite_full_20260522_081710`
- 최신 source-app quick smoke:
  - `output/manual_verification/latest/qa_suite_quick_20260525_141648`
- 현재 active queue 관련 proof:
  - `output/manual_verification/latest/20260527_x5_hot_path_trim_proof/`
  - `output/manual_verification/latest/20260526_225507_high_refresh_source_app_proof/verification_summary.md`
  - `output/manual_verification/latest/20260622_233750_duplicate_guard_x5_cached/summary.md`
- 문서 구조 검증 기본:
  - `find doc -maxdepth 4 -type f | sort`
  - `git diff --check -- AGENTS.md doc tools tests ui/help/help_content.py`
  - `for f in doc/idea.md doc/DECISIONS/server_mode_benchmarking.md doc/reference/CODEMAP.md doc/reference/File_structure.txt; do test ! -e "$f" || exit 1; done`
- 자막 인식 정확도 실험 quote-back 기본:
  - `quality`, `timing_priority_quality`, `timing_mae`, `raw/final`, `word_precision_count`, `rollback/source_preservation`, accepted-vs-diagnostic artifact 구분

## Open Risks

- worktree가 이미 많이 dirty하므로, 문서 경로 이동과 무관한 코드 변경은 건드리지 않는 편이 안전합니다.
- 오래된 릴리스 노트에는 당시 검증 명령이 보존될 수 있습니다. 현재 truth surface는 `AGENTS.md`, `doc/README.md`, `doc/ACTION_ITEMS.md`, 실제 코드/테스트 기준으로 봅니다.
- 로컬 모델/캐시 정리는 개발 환경 상태만 바꾸므로, 필요 모델은 다시 다운로드가 필요할 수 있습니다.
- 외부 `WhisperKitPersistentWorker`나 `AIStudioNativeCLI`를 따로 쓰는 개인 실험 흐름이 있었다면, 이제는 저장소 번들 경로가 아니라 외부 바이너리 경로 기준으로만 동작합니다.

## Next Recommended Action

1. `../AGENTS.md`와 `doc/ACTION_ITEMS.md`를 다시 기준으로 잡고 active queue의 editor-ready slice만 좁게 이어갑니다.
2. 문서 관련 후속 작업을 할 때는 `README.md`, `VALIDATION.md`, `cooperation.md`만 현재 규칙 문서로 보고 오래된 로그성 문서 확장을 피합니다.
3. UI/owner 경계 수정이 생기면 `PROJECT_STATE.md`, `FEATURE_REGISTRY.md`, `ARCHITECTURE.md` 중 해당 문서를 같이 갱신합니다.
