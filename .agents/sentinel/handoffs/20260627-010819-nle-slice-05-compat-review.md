DEX_REVIEW_READY
역할: 서린 (Strict QE Reviewer)
범위: NLE Slice 0.5 compatibility characterization review
읽은 파일:
- [NLE_Action.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/NLE_Action.md)
- [tests/test_project_nle_snapshot.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_project_nle_snapshot.py)
- [tests/test_editor_srt_open_refresh.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_editor_srt_open_refresh.py)

결론:
Slice 0.5 호환성 특성화 테스트에서 탐지하지 못하거나 누락된 6가지 핵심 Acceptance Risk(Gap) 요소를 도출하였습니다. 특히 float 오차로 인한 frame jitter, 비정상적 사이드카/SRT 매칭 에러, 누락된 rational FPS(59.94fps) 기반 프레임 양자화 테스트 등이 주된 취약점입니다.

findings:
### 1. Frame-Quantized Fields & Rational FPS (59.94fps) 정밀도 누락
* **현황**: `test_project_nle_snapshot.py` 내부 테스트 케이스들은 모두 30.0fps 또는 24.0fps와 같은 단순 정수형 FPS만을 다루고 있습니다.
* **Risk**: 실제 프로덕션 환경이나 fixed fixture인 `59.94fps` (`60000/1001` fps) 비디오 환경에서 float 연산 시 미세한 시간 편차(예: `1/59.94 = 16.68ms`)로 인해 프레임 경계 값이 소수점 하향/상향 조정되어 `2676` vs `2677` 프레임 매칭에 실패하는 오차가 발생할 수 있습니다. NLE projection이 exact rational FPS를 바탕으로 프레임 양자화 필드를 올바르게 변환하고 보존하는지 검증하는 테스트 케이스가 부재합니다.

### 2. Custom Metadata 라운드트립 검증의 불완전성
* **현황**: `test_project_file_roundtrip...` 테스트는 `proxy_path`, `cache_key`, `relink` 등 특정 asset 메타데이터만 복원되는지 검사하고 있습니다.
* **Risk**: `editor_state` 하위 세그먼트 수준의 `quality.confidence_label`, 화자 정보(`speaker`), `subtitle_stage_confidence` 등 세부 custom metadata가 NLESnapshot sequence/caption 엔티티로 투영되고 다시 프로젝트 파일로 직렬화(serialization)될 때 특정 필드가 누락되거나 기본값으로 덮어씌워지는 경우(lossy projection)를 전수 검증하는 단언문(Assertion)이 누락되었습니다.

### 3. Direct SRT와 Project Metadata 병합 시 불일치(Mismatch) 예외 처리 누락
* **현황**: `test_direct_srt_metadata_merge...`에서 SRT 텍스트 우선(precedence) 및 프로젝트 메타데이터 병합을 성공 시나리오로만 검증합니다.
* **Risk**: SRT 파일에 일부 세그먼트가 유실되었거나, 프로젝트 파일의 세그먼트 수와 로드한 SRT 파일의 세그먼트 수가 서로 일치하지 않는 경우(Mismatch), 병합 모듈이 임의로 데이터를 매칭하여 엉뚱한 세그먼트에 메타데이터가 입혀지거나 로딩이 실패(Exception)할 수 있습니다. 비정상 포맷의 SRT나 세그먼트 불일치 시나리오에 대한 precedence lock 안전 테스트가 없습니다.

### 4. Roughcut Sidecar & Rendered Roughcut Reopen Boundary 누락
* **현황**: sidecar 파일이 정상 구조일 때 top-level이 nested보다 이기는(win) 시나리오만 검사합니다.
* **Risk**: 
  * sidecar 파일(EDL JSON)이 문법적으로 손상되었거나 빈 파일일 때 NLE Snapshot이 강건하게 fall back하는지 테스트가 없습니다.
  * 렌더링된 roughcut reopen 시 비디오 인코딩 지연 등으로 비디오 실제 길이와 sidecar의 duration이 상이(미세 불일치)할 때 timing offset이 누적되거나 timeline playhead 범위를 벗어나 UI 렌더링 크래시를 유발할 수 있는 risk가 테스트되지 않았습니다.

### 5. Gap Rows 처리 경계 조건 누락
* **현황**: `test_legacy_gap_rows...`는 단일 gap의 보존 및 sequence duration 유지만 확인합니다.
* **Risk**: 
  * 0.0초(최초) 시작 시점 또는 타임라인 마지막(최종) 시점에 존재하는 gap이 sequence duration에 미치는 왜곡 현상이 검사되지 않았습니다.
  * 연속된 여러 개의 gap row가 밀접하게 존재할 때 프레임 정렬이나 자막 스냅 연산 중 gap이 유실되거나 인접 자막에 병합(magnet snap)되어 유실되는 한계 영역 검증이 없습니다.

### 6. Output Duration Clamping 검증 부족
* **현황**: EDL 및 Render Plan에 기록된 duration이 타임라인 상의 실제 자막 마지막 시간과 다를 때 NLESnapshot이 강제로 클램핑(clamping)하거나 경고를 뱉는지 검증하지 않습니다.

defer: 없음
덱스 확인 포인트:
1. `tests/test_project_nle_snapshot.py`에 `60000/1001` rational FPS 프레임 정밀도 및 누락된 custom metadata 필드 유실 검사 추가 여부.
2. 손상된 사이드카 및 SRT 세그먼트 개수 불일치 시의 병합 로깅/안전 동작 검증 필요성.
