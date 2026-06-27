# Project State

## Current purpose

현재 저장소 기준 `AI Subtitle Studio`는 macOS Apple Silicon 우선의 Python/PyQt6 데스크톱 자막 제작 도구입니다. `README.md`, `main.py`, `core/runtime/config.py`, `ui/editor/`, `core/engine/`를 기준으로 보면 다음 흐름이 실제 구현 범위에 포함됩니다.

- 비디오/오디오 입력 처리
- 자막 생성 파이프라인
- 편집기와 타임라인 기반 수동 보정
- 프로젝트 저장/재열기
- 러프컷 초안 생성과 후속 편집
- STT/VAD/LLM 기반 후처리와 품질 보조

정확한 품질 수준이나 모델 성능 수치는 저장소만으로 확정할 수 없으므로 여기서는 기능 존재 여부만 문서화합니다.

## Implemented areas

저장소에서 직접 확인되는 구현 영역은 아래와 같습니다.

- 앱 부트스트랩과 메인 윈도우: `main.py`, `ui/main/`
- 편집기 UI와 타임라인: `ui/editor/`, `ui/timeline/`
- 비디오 플레이어 통합: `ui/editor/video_player_*`, `ui/video_controls.py`
- 자막 생성/보정 엔진: `core/engine/`, `core/pipeline/`, `core/subtitle_quality/`
- STT/VAD/오디오 전처리: `core/audio/`, `core/stt_mode/`
- LLM provider와 자막 후처리: `core/llm/`
- 프로젝트 포맷/저장/복원: `core/project/`, `ui/project/`
- 러프컷/PHASE2 관련 모듈: `core/roughcut/`, `ui/roughcut/`
- 설정/모드/개인화: `ui/settings/`, `core/personalization/`, `core/settings.py`
- 검증 스위트와 수동 검증 도구: `tests/`, `tools/qa_suite_runner.py`, `tools/verify_full_media_pipeline.py`

## Current development direction

현재 문서와 디렉터리 배치를 보면 개발 방향은 다음과 같이 읽힙니다.

- 정확도 우선 자막 생성과 후처리 품질 유지
- 편집기/타임라인 UX 안정화
- 프로젝트 저장/재열기/렌더링 회귀 방지
- 러프컷 초안 생성과 PHASE2 편집 흐름 보강
- 기존 Python/PyQt6 source app 유지와 실제 앱 검증 중심 진행

`core/roughcut/`, `ui/roughcut/`, `RELEASE_v04.00.18.md`, `ACTION_ITEMS.md`를 보면 러프컷/PHASE2 흐름과 source-app internal NLE domain baseline은 현재 구조 기준선으로 반영되어 있습니다. NLE는 read-only snapshot baseline 위에 runtime-only mutable save-owner pilot, save/reload persistence guard, render/export parity proof, final-overlay runtime cutover, cleanup gate audit, release checkpoint parity proof, phase 11 no-op cleanup closeout, caption-move dual-write adoption, caption-resize dual-write adoption, caption-delete dual-write adoption, gap-generate dual-write adoption, caption-merge dual-write adoption, caption-split dual-write adoption, candidate-confirm dual-write adoption, live-editor diamond resize cutover, live-editor boundary-handle resize cutover, live-editor delete-to-gap cutover, live-editor gap-generate cutover, live-editor diamond merge cutover, live-editor text/smart split cutover, live-editor STT1/STT2 candidate-confirm cutover, final-surface overlap guard, and persistence cutover readiness audit가 추가되었고, persisted NLE project fields are still not approved. 2026-06-27/2026-06-28 기준 post-generation editor readiness closeout, Taption-derived segment editing parity patch, Taption subtitle segment UI/UX parity completion, Full NLE Transition phases 1-11, cut-boundary generation latency profile closeout, NLE caption-move/Taption reorder dual-write slice, NLE caption-resize slice, live editor diamond/square resize cutover, live editor delete-to-gap cutover, live editor gap-generate cutover, roughcut saved-candidate render-plan cutover, live editor caption-merge cutover, live editor caption-split cutover, live editor candidate-confirm cutover, NLE final-surface overlap guard, and NLE persistence cutover audit가 완료되었습니다. 현재 active queue는 STT2 / word precision generation latency profiling and Mac App Store submission readiness입니다. 다만 세부 사용자 플로우는 일부가 문서 추론일 수 있습니다.

현재 운영 방향상 `native/` 디렉터리와 관련 실험 흔적은 저장소 참고 자료로 남아 있을 수 있지만, active roadmap은 아닙니다. owner가 다시 명시하지 않는 한 새 native migration 전개를 기본 작업으로 취급하지 않습니다.

## Known constraints

- `core/runtime/config.py` 기준으로 현재 지원 타깃은 macOS이며 Apple Silicon 우선 정책이 강합니다.
- UI 주 경로는 PyQt6 Widgets/QPainter 계열입니다.
- 저장소에는 `ui/qml/`이 있지만, 현재 운영 문서와 기존 작업 규칙은 QML/SceneGraph/OpenGL/Metal UI를 기본 경로로 삼지 않도록 요구합니다.
- STT/VAD/Whisper/LLM 계층은 여러 provider와 보조 엔진이 함께 있으므로, 한 파일만 보고 동작을 단순화하면 회귀 위험이 큽니다.
- 자막 품질 관련 규칙은 속도보다 정확도를 우선하는 방향으로 관리됩니다.

## Must not break

현재 코드와 운영 문서 기준으로 특히 깨지면 안 되는 축은 아래와 같습니다.

- 앱 실행과 메인 윈도우 부팅
- 프로젝트 열기/저장/재열기
- 자막 생성 기본 파이프라인
- 편집기 타임라인 렌더링과 seek/playhead 동기화
- SRT 및 프로젝트 자산 입출력
- 러프컷 초안 생성과 편집기 연결
- 설정/모드 전환 후 회귀 없는 재실행
- 기존 검증 스위트가 커버하는 비치명적 예외 처리 경로

## Version/release notes

- 현재 코드에서 확인되는 앱 버전 상수는 `04.00.18`입니다. (`core/runtime/config.py`)
- 루트에는 `RELEASE_v04.00.07.md`부터 `RELEASE_v04.00.18.md`까지 릴리스 노트가 존재합니다.
- 최신 릴리스 문서(`RELEASE_v04.00.18.md`)는 VAD/STT timing consensus, confirmed cut-boundary split/snap, source-fps pioneer scout enablement, and the `NLE_Action.md` execution plan을 묶는 체크포인트 성격이 강합니다.
- `README.md`와 릴리스 문서 기준 공식 검증 흐름은 `tools/qa_suite_runner.py`와 pytest, `compileall`, `git diff --check`, source-app smoke를 조합하는 방식입니다.
- DMG/패키징은 저장소에 관련 디렉터리가 있어도 기본 작업이 아니라 요청 시 별도 검증 대상으로 취급해야 합니다.

## Open action items

`ACTION_ITEMS.md` 기준 현재 active execution queue는 아래 두 축입니다.

- `STT2 / Word Precision Generation Latency Profiling And Accuracy-Preserving Trim`: 컷 경계가 병목이 아니라는 HeyDealer 180s evidence 이후, STT2 rescue, selective word timestamp precision, LLM gate/skip, common split, VAD/STT consensus, cleanup pressure를 품질 보존 방식으로 계측합니다.
- `Mac App Store Submission Readiness`: 현재 source app을 Mac App Store 제출 후보로 올리기 위한 signing, sandbox, package, validation, metadata 준비 계획입니다. 비파괴 readiness audit은 `output/manual_verification/latest/app_store_readiness_audit_20260627/app_store_readiness_audit.md`에 있으며 `local_packaging_ready=true`, `app_store_submission_ready=false`입니다. Packaging/upload/notarization/DMG 작업은 owner 명시 승인 전에는 실행하지 않습니다.

완료된 NLE caption move / Taption reorder dual-write evidence는 `output/manual_verification/latest/nle_caption_move_dual_write_20260627/caption_move_dual_write_report.md`에 남아 있습니다.

완료된 NLE caption resize dual-write evidence는 `output/manual_verification/latest/nle_caption_resize_dual_write_20260627/caption_resize_dual_write_report.md`에 남아 있습니다.

완료된 NLE live editor diamond cutover evidence는 `output/manual_verification/latest/nle_live_editor_diamond_cutover_20260627/live_editor_diamond_cutover_report.md`에 남아 있습니다.

완료된 NLE live editor boundary-handle resize cutover evidence는 `output/manual_verification/latest/nle_live_editor_boundary_resize_cutover_20260627/boundary_resize_cutover_report.md`에 남아 있습니다.
완료된 NLE live editor caption-delete cutover evidence는 `output/manual_verification/latest/nle_live_editor_caption_delete_cutover_20260627/caption_delete_cutover_report.md`에 남아 있습니다.
완료된 NLE live editor gap-generate cutover evidence는 `output/manual_verification/latest/nle_live_editor_gap_generate_cutover_20260627/gap_generate_cutover_report.md`에 남아 있습니다.
완료된 NLE live editor caption-merge cutover evidence는 `output/manual_verification/latest/nle_live_editor_caption_merge_cutover_20260628/caption_merge_cutover_report.md`에 남아 있습니다.
완료된 NLE live editor caption-split cutover evidence는 `output/manual_verification/latest/nle_live_editor_caption_split_cutover_20260628/caption_split_cutover_report.md`에 남아 있습니다.
완료된 NLE live editor candidate-confirm cutover evidence는 `output/manual_verification/latest/nle_live_editor_candidate_confirm_cutover_20260628/candidate_confirm_cutover_report.md`에 남아 있습니다.

완료된 NLE final-surface overlap guard evidence는 `output/manual_verification/latest/nle_final_surface_overlap_guard_20260628/final_surface_overlap_guard_report.md`에 남아 있습니다.

완료된 NLE persistence cutover audit evidence는 `output/manual_verification/latest/nle_persistence_cutover_audit_20260628/nle_persistence_cutover_audit.md`에 남아 있습니다. 최신 감사는 8개 NLE dual-write operation family의 save/reopen semantic roundtrip을 증명하지만, `gap_generate`, `caption_split`, `caption_merge`, `candidate_confirm`의 legacy ID renumbering을 별도 risk flag로 남깁니다.

완료된 cut-boundary latency evidence는 `output/manual_verification/latest/cut_boundary_latency_profile_20260627/latency_profile_report.md`에 남아 있습니다.

완료된 `Full NLE Transition Plan` evidence는 아래 위치에 남아 있습니다.

완료된 Taption subtitle segment UI/UX parity evidence는 `test_result.md`와 `output/manual_verification/latest/taption_segment_uiux_parity_20260627/checklist.md`에 남아 있습니다.

최근 완료된 Taption-derived segment editing parity patch와 Taption subtitle segment UI/UX parity completion은 final subtitle overlay와 STT1/STT2 candidate lane 표시를 분리하고, final segment stability가 overlap `0`을 요구하도록 보강했으며, gap snap, boundary release, one-gap overwrite, one-word edit retention, immediate neighbor reorder preview/commit을 focused guards로 고정했습니다. 증거는 아래 위치에 있습니다.

- `test_result.md`
- `docs/HANDOFF.md`
- `output/manual_verification/latest/qa_suite_quick_20260627_141230`
- `output/manual_verification/latest/taption_segment_uiux_parity_20260627/checklist.md`
- `output/manual_verification/latest/nle_domain_contract_20260627/domain_contract.md`
- `output/manual_verification/latest/nle_read_only_parity_20260627/projection_parity_report.md`
- `output/manual_verification/latest/nle_operation_model_20260627/operation_model_report.md`
- `output/manual_verification/latest/nle_dual_write_pilot_20260627/gap_delete_pilot_report.md`
- `output/manual_verification/latest/nle_save_reload_compat_20260627/save_reload_compat_report.md`
- `output/manual_verification/latest/nle_render_export_parity_20260627/render_export_parity_report.md`
- `output/manual_verification/latest/nle_runtime_cutover_final_overlay_20260627/final_overlay_cutover_report.md`
- `output/manual_verification/latest/nle_cleanup_gate_audit_20260627/cleanup_gate_audit.md`
- `output/manual_verification/latest/nle_release_checkpoint_parity_20260627/release_checkpoint_parity_report.md`
- `output/manual_verification/latest/nle_phase11_cleanup_20260627/cleanup_report.md`

이전 `Post-Generation Editor Readiness And Verification Index` closeout 증거는 아래 위치에 남아 있습니다.

- `output/manual_verification/latest/post_generation_editor_readiness_index_20260627/verification_index.md`

세부 우선순위는 여전히 `ACTION_ITEMS.md`가 단일 소스 오브 트루스이므로, 새 세션에서는 반드시 그 파일의 최신 상태를 다시 읽어야 합니다.

## Unverified assumptions

- 저장소 이름과 디렉터리 구조상 다중 STT/provider, 정밀 후처리, 개인화 규칙이 존재하는 것은 확인되지만, 각 조합이 기본 활성인지까지는 실행 없이 확정할 수 없습니다.
- `ui/qml/` 디렉터리가 존재하므로 일부 실험성 UI 경로가 있을 수 있으나, 기본 편집기 경로인지 여부는 운영 문서상 부정적입니다.
- 러프컷/PHASE2 사용자 플로우의 완성도는 파일 구조상 구현된 것으로 보이지만, 최신 제품 기본 화면에서 항상 노출되는지는 런타임 확인이 필요합니다.
