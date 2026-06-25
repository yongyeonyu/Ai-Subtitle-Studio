DEX_REVIEW_READY

# NLE Snapshot Roughcut Exact-Join Sidecar Payload Compatibility Risk Review

본 문서는 read-only NLE snapshot의 러프컷 exact-join sidecar payload를 마커(TimelineMarker)로 변환/매핑할 때 수반되는 호환성 및 메타데이터 유실 위험을 분석한 QA 보고서입니다.

---

## Exact-Join Handoff Validation Findings (4가지 잠재적 위험 분석)

### [Finding 1] 중첩된 stitched_cut_boundaries의 다중 로드로 인한 고스트 마커(Ghost Marker) 리스크
- **위험 요소**:
  - `_stitched_rows_from_payload`는 top-level, `outputs`, `edl`, `render_plan` 구조를 다각도로 스캔하여 `exact_join` 데이터를 추출하고, `_build_markers`는 `selected_candidate`와 `outputs` 양측에서 수집한 데이터들을 가산(`+`)하여 병합합니다.
  - 이 과정에서 `round(float(marker.time), 3)`과 전/후 세그먼트 ID의 결합 키값으로만 단순 중복 필터링(`seen_exact`)을 진행합니다.
- **호환성 리스크**:
  - 만약 FFMPEG 디코딩 오차 또는 프레임 눈금 반올림 변이로 인해 동일한 접합 지점의 시간 정보가 한쪽에는 `4.000`초, 다른 한쪽에는 `4.001`초 등으로 아주 미세하게 다르게 쓰여 있을 경우, 중복 제거 로직을 우회하여 타임라인 상에 물리적으로는 동일한 컷 자리에 2개의 중복 마커가 적재되는 오동작(고스트 마커) 리스크가 존재합니다.

### [Finding 2] `roughcut_state.outputs` 구조 마이그레이션 중 Silent Drop 위험
- **위험 요소**:
  - `_stitched_rows_from_payload`는 nested `edl`과 nested `render_plan` 아래의 `stitched_cut_boundaries` 배열을 fallback 형태로 순차 수집합니다.
- **호환성 리스크**:
  - v1~v3 레거시 데이터와의 호환성 유지 중, `outputs` 필드 내부의 스키마 명세가 명확히 버전 게이트웨이(`nle_snapshot.py`)에서 통제되지 않은 상태로 덱스(Dex) 구현부에서 nested 스키마 하위 키의 depth를 변경할 시(예: `outputs.render_plan`을 다른 임시 키로 래핑 등), sidecar reader가 이를 포착하지 못해 exact join 마커 정보가 통째로 누락되는 현상이 발생할 수 있습니다.

### [Finding 3] Output-time Marker와 Clip-span의 혼동에 따른 타임라인 싱크 리스크
- **위험 요소**:
  - `exact_join` 마커는 러프컷을 거쳐 최종 병합 내보내기 된 결과물의 시간축인 **`output_time`** 상의 물리적 좌표를 가집니다.
- **호환성 리스크**:
  - 이 output-time 마커 값을 타임라인 편집기의 sequence-time(`sequence_time`)이나 원본 소스의 local-time(`source_time`)과 명확히 구분하지 않고 UI 캔버스(`timeline_canvas.py` 등)의 클립 시간 스팬(`Clip` span) 연산에 직접 대입하여 혼용할 경우, 사용자가 컷 위치를 드래그하거나 편집할 때 엉뚱한 클립 세그먼트 영역에 자막이 매핑되어 싱크가 뒤틀리는 치명적 오류가 발생할 수 있습니다.

### [Finding 4] 렌더 계획 듀레이션 변이에 의한 Metadata Drift 리스크
- **위험 요소**:
  - `_edl_duration`이나 FFMPEG 렌더링 명령어 플랜에서 EDL 각 세그먼트의 시간 길이를 소수점 연산할 때, 1프레임 미만의 미세한 듀레이션 변이가 생길 수 있습니다.
- **호환성 리스크**:
  - 이 변이로 인해 실제 비디오의 물리 듀레이션과 sidecar metadata(`output_before_end` / `output_after_start`) 상의 끝/시작 눈금이 어긋날 경우, exact_join 마커가 렌더링된 비디오의 실제 길이보다 바깥에 위치하거나 잔상이 남는 불일치(Drift) 리스크가 존재합니다.
