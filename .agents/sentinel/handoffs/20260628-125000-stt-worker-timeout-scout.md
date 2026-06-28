DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio STT worker timeout diagnostic scout

findings:
1. **STT Worker Timeout 최적 대응안 검토**:
   - **현재 이슈**: HeyDealer benchmark `20260628_123336` 에서 STT1/Fast-STT2/word precision WhisperKit worker timeout (150s/150s/30s) 및 subprocess deadlock 위협 발생.
   - **안전성 판정**: **안전함 (Accept 권장)**. 모델 크기를 무단 축소하거나 STT2를 생략하는 방식이 아닌, timeout 발생 시의 process state 및 stack traceback을 비파괴적으로 수집·기록(diagnostics)하는 안전 보강 조각이므로 적절함.
2. **추천 다음 액션아이템**:
   - **추천 항목**: **"STT Worker Process Isolation Check & Timeout Trace Audit Tooling"**
3. **진단 대상 파일 (Owner Files)**:
   - `core/audio/media_processor_transcribe_run.py` (timeout 예외 발생 지점)
   - `core/audio/whisperkit_persistent.py` (persistent worker daemon state 관리)
   - `core/runtime/trace_logger.py` (timeout 이벤트를 trace bundle에 비동기로 기록)
4. **추천 테스트 (Tests)**:
   - `tests/test_startup_diagnostics.py` (persistent worker의 process isolation 및 deadlock 감지 로직 단위 테스트)
5. **아티팩트 감사 (Artifact Audit)**:
   - `tools/summarize_stage_variance.py` 가 `benchmark_results.json` 의 timeout traceback 및 memory pressure 경향성을 올바르게 parsing해 덤프하는지 확인.

defer:
- **모델 크기 축소 (예: large-v3-turbo -> base 등)**: 자막 품질의 Parity를 훼손하므로 Defer 함.
- **STT2 구동 생략 혹은 word precision 범위 축소**: Defer 함.
- **품질 게이트(invalid_duration, overlap 등) 완화**: Defer 함.
- **stt_primary_collect_cache 기본값 True promotion**: Defer 함.
- **일체 UI/QML 및 App Store 관련 빌드 작업**: Defer 함.
