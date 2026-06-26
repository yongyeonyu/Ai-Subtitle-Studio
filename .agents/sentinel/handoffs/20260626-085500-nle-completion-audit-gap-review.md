DEX_REVIEW_READY
역할: 서린 (Strict QE Reviewer)
범위: NLE completion audit gap review (NLE Timeline Architecture Plan 1-6)
읽은 파일:
- `ACTION_ITEMS.md`
- `docs/HANDOFF.md`
- `docs/ARCHITECTURE.md`
- `docs/FEATURE_REGISTRY.md`
- `docs/VALIDATION.md`
- `AGENTS.md`
- `tools/qa_suite_runner.py`
- `tests/test_qa_suite_runner.py`
- `tests/test_project_nle_snapshot.py`
- `tests/test_roughcut_ui_v2.py`
- `ui/roughcut/roughcut_export.py`
- `output/manual_verification/latest/qa_suite_full_x5_audio_override_20260626_0849/suite_result.md`
- `output/manual_verification/latest/x5_standard_media_missing_20260626_0848/summary.json`

결론:
원래의 NLE Timeline Architecture Plan 요구사항 1~6 및 검증 게이트 중 read-only 어댑터와 unit-level 정합성은 충족되었으나, 실제 런타임 UI 연동 및 갭(`is_gap`) 데이터 변형 방어가 증명되지 않았습니다. 특히 표준 비디오 피드인 `X5_시승기_후반.MP4`가 유실된 상태에서의 오디오 오버라이드 우회 통과는 GUI 디코딩, 타임라인 비디오 트랙 매핑 및 비디오 자막 합성(FFMPEG burn-in)에 대한 증거력을 갖지 못하므로 **NLE 전환 완료 선언을 보류(Defer)하고 릴리스 게이트를 수정(Revise)해야 합니다.**

findings:

1. X5_시승기_후반.MP4 결손에 따른 QE 판단: **NLE 완료 선언 보류 (Blocker로 확정)**
- **이유**:
  - `x5_standard_media_missing_20260626_0848/summary.json`에서 보듯, 표준 비디오 MP4가 없으면 기본 프리플라이트 상태에서 즉시 `media_missing` 예외를 냅니다.
  - `qa_suite_full_x5_audio_override_20260626_0849/suite_result.md`에서 `x5_high_rolling_180s`가 오디오 오버라이드로 `ok`가 났더라도, 이는 순수 오디오 파이프라인(STT, VAD, LLM)의 작동 정합성을 증명할 뿐입니다.
  - NLE 아키텍처의 최종 목적은 자막뿐 아니라 **비디오 클립과 챕터 스팬 간의 컷 경계 매핑 및 FFMPEG 비디오 합성(burn-in) 렌더링**입니다. 비디오 컨테이너가 없는 상태에서 완료를 선언하면, VFR 비디오 로드 시의 타임라인 오프셋 싱크 드리프트나 GPU/ANE 디코더 락 등의 심각한 런타임 회귀 결함을 감지할 방법이 없습니다.

2. NLE 6대 요구사항별 accept/revise/defer 추천 사항
- **NLE sequence adapter & Parity 검증 (Accept)**:
  - NLE frozen dataclass 모델 및 EDL/Render plan unit-level 정합성 증명(`tests/test_project_nle_snapshot.py`, `tests/test_roughcut_v2_output_compat.py`)은 **수락 (accept)**.
- **NLE 런타임 라우팅 실적 검증 (Defer)**:
  - NLE Snapshot을 실제 내보내기/렌더러 및 GUI와 바인딩하고 가상 갭(`is_gap`) 오염을 방어하는 e2e 검증은 런타임 픽스 적용 전까지 **보류 (defer)**.
- **X5 비디오 Fixture 기반의 source-app proof (Revise)**:
  - 오디오 전용 오버라이드만으로 X5 baseline을 완수했다고 판정하는 기존 릴리스 계획을 **수정 (revise)**하여, mock MP4를 도입하거나 skipped 경고를 명확히 남기도록 게이트를 보완할 것을 지적.

3. 정확한 증거 경로 (Exact Evidence Paths)
- **Macau 실미디어 시나리오 패스 증빙**:
  - [suite_result.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/qa_suite_full_x5_audio_override_20260626_0849/suite_result.md#L16-L23)
- **X5 표준 MP4 결손 프리플라이트 에러 증빙**:
  - [summary.json](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/x5_standard_media_missing_20260626_0848/summary.json#L8-L17)
- **오버라이드 X5 롤링 패스 증빙**:
  - [suite_result.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/qa_suite_full_x5_audio_override_20260626_0849/suite_result.md#L24)

defer:
- 런타임 픽스 및 테스트 구현은 본 QE review 단계에서는 일체 수행하지 않으며, 덱스(Codex) 구현 단계로 위임합니다.

덱스 확인 포인트:
1. X5 MP4 결손을 회피하기 위해, 용량이 극도로 작은 가상 mock 비디오 피드(X5_mock.mp4, AAC 오디오 포함)를 새 fixture로 리포지토리에 추가하는 게이트 보완안을 덱스 단계에서 채택할지 판정해야 합니다.
2. 런타임 저장/재열기 루프에서 snapshot frozen instance가 legacy `is_gap` 가상 세그먼트 속성을 무단 삭제하여 자막 타임라인을 앞쪽으로 뭉개버리는 결함에 대해 덱스 패치 단계에서 strict한 assert를 추가해야 합니다.
