DEX_REVIEW_READY

# STT2/Word Precision 정확도 검증 방식 및 게이트 QE 리뷰

본 문서는 strict QE reviewer '서린'의 관점에서 reference-scored fixture 부재/접근불가 상황에서의 검증 해석 가이드라인과 최적화 변경 채택 전 반드시 통과해야 하는 5대 검증 게이트를 정의합니다.

---

## 1. Reference 부재/접근불가 상황에서의 해석 가이드라인

로컬 환경에 reference-scored fixture(예: HeyDealer 최종본 미디어 및 reference SRT)가 없거나 접근이 불가능할 경우, 비-reference 픽스처(예: 로컬 X5 audio run, Macau 테스트)와 기존의 HeyDealer reference artifact를 상호보완적으로 해석해야 합니다.

1. **지표 분리 및 간접 추론**:
   - 직접적인 품질 점수(Quality Score, CER/WER, Timing MAE)는 계산할 수 없으므로, 로컬 픽스처 실행 시 **자막 구조 및 결정 제어 지표**의 변화 여부를 추적합니다.
   - `stt2_selected_count`, `word_precision_count`, `recheck_applied_count`, `llm_gate_skipped_segments` 등의 수치가 기존 HeyDealer reference artifact에 기록된 베이스라인 분포와 비례적 일관성을 유지하는지 확인합니다.

2. **형태적 안정성의 전수 검증**:
   - 오디오만 존재하는 X5 audio run 혹은 로컬 Macau 클립 검증 시에도 생성된 자막 세그먼트의 시간 경계와 순서가 완벽해야 합니다.
   - 단 하나의 자막이라도 시간 범위 오류가 발생하면 텍스트 매칭 여부와 관계없이 즉시 실패(Parity Fail)로 처리합니다.

3. **기존 골든 Artifact의 불변적 대조**:
   - 기존 HeyDealer reference artifact(`benchmark_results.json` 등)는 변경 전의 '골든 기준선'입니다. 변경된 로직을 로컬에서 실행할 때, 결정 로직의 분기가 기존 골든 런의 로직 분기와 일대일 매칭되는지 코드로 대조해야 합니다.

---

## 2. 변경 채택 전 필수 검증 게이트 (Gates)

최적화 및 레이턴시 Trim 변경사항을 기본 설정(default)으로 채택하기 전에 반드시 통과해야 하는 **5대 strict QE 게이트**입니다.

### Gate 1: 자막 데이터 무결성 게이트 (Integrity Gate)
* **목적**: 생성된 자막 구조가 에디터와 재생기에서 오동작을 일으키지 않도록 보장
* **조건**: 모든 검증 run 결과에서 다음 지표를 충족해야 합니다.
  * `invalid_duration_count = 0` (음수 또는 비정상적인 자막 길이 차단)
  * `non_monotonic_count = 0` (역전된 타임스탬프 차단)
  * `overlap_count = 0` (중첩 자막 차단)
  * `stable_for_save_reopen = True` (legacy 및 NLE project load/save 호환성 확보)

### Gate 2: 로직 동치성 게이트 (Logical Parity Gate)
* **목적**: 성능 튜닝이 자막의 최종 텍스트 내용이나 컷 분할 경계를 오염시키지 않는지 검증
* **조건**: 순수 속도/레이턴시 최적화 또는 리소스 해제 패치인 경우, 비-reference 로컬 run(예: Macau) 전후로 다음을 만족해야 합니다.
  * `segment_count_delta = 0` (최종 자막 줄 수가 변경 전후 완벽히 일치)
  * 자막 본문 텍스트가 1글자도 변경되지 않음 (엄격한 캐릭터 수준 parity check 통과)
  * LLM Gate 및 STT2 Recheck 의 판단 대상 row와 결정 결과가 완전히 일치

### Gate 3: 수행 메트릭 일관성 게이트 (Execution Metric Parity Gate)
* **목적**: 알고리즘 스킵 및 모델 축소 등의 불법 지름길 우회 차단
* **조건**: 최적화 후에도 STT1/STT2/Word Precision의 동작 빈도가 설계된 범위를 유지해야 합니다.
  * `stt1_selected_count` 및 `stt2_selected_count` 비율이 골든 베이스라인의 $\pm 0\%$ 내 일치 (결정론적 구간 기준)
  * `word_precision_count`와 `stt2_coverage_ratio`가 베이스라인 수치와 정확히 일치하여, 품질이 희생되지 않았음을 통계적으로 간접 증명

### Gate 4: 통계적 실소요 시간 게이트 (Statistical Wall-Clock Speedup Gate)
* **목적**: 프로파일러 왜곡 제거 및 실제 사용자 체감 성능 개선 증명
* **조건**:
  * cProfile 등의 누적 시간(`cumulative_time_sec`)은 nesting으로 인해 중복 합산되므로 의사결정의 직접적 성능 근거로 사용하지 않습니다.
  * 프로파일러를 끈 상태에서 최소 3회 이상 반복 실행(`--repeat 3`)하여 측정된 실제 pipeline 경과 시간(`pipeline_elapsed_sec`)의 평균(avg) 및 p95 값이 베이스라인 대비 유의미한 수준으로 단축되거나 최소한 동등(no regression)해야 합니다.

### Gate 5: 메모리 및 백그라운드 리소스 공존 게이트 (Resource Coexistence Gate)
* **목적**: ANE/GPU 메모리 누수 방지 및 백그라운드 zombie 프로세스 생성 차단
* **조건**:
  * 생성 파이프라인 수행 중 peak RSS 메모리 사용량이 시스템 물리 한계를 넘지 않아야 하며, 메모리 경보 상태가 `critical`로 전이되지 않아야 합니다.
  * 자막 완성 및 에디터 대기 상태(idle-ready) 진입 시, STT 백그라운드 worker와 Ollama LLM 웜업 인스턴스가 릴리스 정책에 따라 정상 해제/수거되는지 모니터링 로그로 증명해야 합니다.
