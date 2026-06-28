DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio benchmark tail-bound projection scout

findings:
1. **Benchmark Projection Clamp 안전성 검토**:
   - **안전성 판정**: **안전함 (Accept 권장)**.
   - **근거**: core 엔진 코드 수정 없이 벤치마크 평가단(`tools/benchmark_subtitle_pipeline_variants.py`) 내에서 hypothesis 자막 행을 reference와 동일하게 window 범위(`start_sec` ~ `end_sec`)로 투영/클램프하는 것이므로, 실 자막 품질을 해치지 않고 평가 Parity만 확보하는 완벽히 안전한 비파괴적 개선임.
2. **반드시 확인해야 할 Regression/Test Point**:
   - **부작용 경계 (Edge Case)**: `clip_reference` 또는 clamp 연산으로 인해 구간 경계에 걸친 자막이 잘리면서 duration이 0.3초 미만으로 극도로 짧아져 `invalid_duration_count` 가 오접수되거나 overlap이 유도되는지 확인해야 함.
   - **테스트 스위트**: `tests/test_benchmark_mode_profiles.py`를 실행하여 벤치마크 variants 점수 산출 및 파이프라인 verification이 정상 작동하는지 점검.
3. **결론**: 평가단 projection clamp 도입을 적극 권장하며, clamp 직후 duration-bound 와 invalid segment count 간의 경계 무결성을 최우선 검증해야 함.
