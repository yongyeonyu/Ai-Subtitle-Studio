DEX_REVIEW_READY
역할: 잼민이 (QE 및 하위 호환성 검토)
범위: QA runner fixture repair risk review (Macau fallback, X5 media, editor_compact playhead)
읽은 파일:
- `tools/qa_suite_runner.py`
- `tests/test_qa_suite_runner.py`

결론:
현재 제공되는 QA runner의 각종 fallback 및 dynamic command fallback 메커니즘은 로컬 환경 제약(미디어/프로젝트 부재 및 타이밍 락) 하에서도 테스트가 성공(Green)하도록 유도하지만, 이로 인해 legacy project, direct SRT, roughcut QA의 본질적인 검증 의미를 상실하게 만드는 상당한 'Hidden Compatibility Risk'와 'Test Gap'을 내포하고 있습니다. 특히 에러 없이 통과되는 'Silent Success' 현상으로 인해 실제 배포 시 치명적인 호환성 크래시가 마스킹될 우려가 높습니다.

findings:

1. Clean Macau Fallback Project 리스크
- **유형**: Fixture 가상화로 인한 실데이터 검증 차단
- **상세**: `_fallback_macau_srt`는 단 2줄의 극소량 자막("마카오 검증 자막", "편집 자동화 확인")만을 생성하여 프로젝트를 신규 빌드합니다.
- **리스크**:
  - 실제 Macau 프로젝트(`DJI_20260217224203_0075_D.aissproj`)가 가진 다량의 세그먼트, 특수 문자, 화자 태그 파싱 오류를 전혀 검증하지 못합니다.
  - VAD/STT 및 LoRA 학습 파이프라인(`Personalization`) 테스트가 임시 가짜 오디오/자막 컨텍스트에 가려져 실제 Macau 미디어의 STT 정확도 회귀를 잡아내지 못하고 통과됩니다.
  - `prefill_analysis_artifacts=False`로 빌드되므로, 신규 프로젝트 생성 시 동반되는 백그라운드 분석 엔진의 부하와 레이스 컨디션이 QA에서 원천 생략됩니다.

2. X5 Media Fallback (.MP4 vs .mov) 리스크
- **유형**: 컨테이너 포맷 차이로 인한 프레임 연산 왜곡
- **상세**: `_x5_media_for_suite`는 `.MP4`가 없을 경우 `.mov`를 폴백으로 선택합니다.
- **리스크**:
  - MP4와 MOV 컨테이너 간의 오디오 디코딩 지연(VAD alignment offset) 차이나 FFMPEG 프레임 레이트 처리 편차가 존재할 수 있습니다.
  - 프레임 단위 Quantization 및 cut boundary 연산 시 미세한 타임 오차로 인해 FFMPEG 렌더링 락 또는 오디오 싱크 드리프트가 발생할 위험이 있으나, 이 포맷 이원화가 그러한 에러를 격리 검증하지 못하고 혼용되게 만듭니다.

3. editor_compact line/start-sec 및 playhead 선택 리스크
- **유형**: Dynamic Command의 관대화로 인한 regression 탐지 누락 (Silent Success)
- **상세**: `_resolve_editor_compact_diamond_command`는 `app_status` 조회 실패(`code != 0`) 혹은 `diamond`가 비어있을 때 `["editor-move-diamond", "--side", "closest"]`로 자동 폴백합니다.
- **리스크**:
  - 원래 시나리오가 검증하고자 한 특정 다이아몬드 경계(좌/우 컷 포인트 병합 등)가 정밀하게 타겟팅되지 않고, 가장 가까운 아무 영역이나 병합/이동되고도 테스트는 통과(Green) 처리됩니다.
  - 이는 타임라인 오프셋 정합성 훼손이나 timeline playhead fit의 미세 픽셀 어긋남으로 인한 hit target 미스 등의 치명적 UI 오작동을 'closest' 폴백이 전부 덮어버리는 문제를 초래합니다.
  - 비동기 런타임 락이나 UI 성능 저하로 인해 status 응답이 지연될 때, 이를 성능 경고(Fail)로 인지하지 않고 `--side closest`로 우회 성공시킴으로써 락 검출 성능을 약화시킵니다.

defer:
- Macau/X5 실제 미디어 및 오리지널 `.aissproj` 파일이 QA 실행 경로에 완전히 존재할 때만 Promotion을 승인하는 '엄격한 Fixture 검증 모드(Strict Fixture Mode)' 추가 도입 필요.
- dynamic fallback 발생 시 단순히 `ok=True`로 흘려보내지 않고, summary 메타데이터에 `warning_fallback_applied: true` 플래그를 심어 QA 리포트에 노출하도록 보완.

덱스 확인 포인트:
1. `qa_suite_runner.py`의 `_resolve_editor_compact_diamond_command` 최하단 기본 폴백 지정(`--side closest`) 코드를 남겨둘 경우, UI 오작동으로 인한 다이아몬드 실종 버그를 QA가 잡아낼 수 없음을 인지하고 엄격한 assert나 warning 마킹 적용 여부를 판정해야 합니다.
2. clean fallback project 생성 시 자막 fixture의 최소 라인 수를 2줄이 아닌 실제 multi-segment 및 timing 오프셋을 갖춘 mock 데이터셋으로 교체할 것인지 논의가 필요합니다.
