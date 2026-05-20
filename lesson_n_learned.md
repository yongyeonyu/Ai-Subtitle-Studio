# lesson_n_learned.md

이 파일은 반복하면 안 되는 판단, 실험, 진단 실수를 저장한다.

## 사용 규칙

- `idea_item.md` 실행 또는 새 아이디어 발굴 전에 반드시 이 파일과 `waste_action_item.md`를 먼저 확인한다.
- 이미 폐기된 아이디어는 같은 조건에서 다시 제안하거나 실행하지 않는다.
- 같은 아이디어를 재검토하려면 새 하드웨어, 새 모델, 새 benchmark, 새 계측처럼 이전 결론을 뒤집을 근거를 먼저 적는다.
- lesson은 짧게 남기되, 가능하면 원인, 금지할 반복 행동, 다시 해야 할 검증을 함께 적는다.

## Lessons Learned

### 2026-05-20

- 수동 저장 직후 러프컷 LLM이 뜨면 editor 러프컷 타이머만 보지 않는다.
  - 이유: 외부 SRT/프로젝트 없는 상태의 수동 저장은 저장용 프로젝트를 자동 생성하며, `create_project()` 기본 prefill 경로가 러프컷 LLM을 동기 실행할 수 있다.
  - 다음 원칙: 저장 버그는 `_on_save()` 후속 타이머와 함께 `_auto_save_project()` / `create_project(prefill_analysis_artifacts=...)` 호출 인자를 먼저 확인한다.

- STT/LLM 속도 최적화에서 cleanup을 무작정 줄이는 방식은 반복하지 않는다.
  - 이유: `cut_prescan_done cleanup 제거`와 `subtitle_optimize_done warning-stage GPU trim 제거`는 일부 짧은 run에서만 좋아 보였고 X5 평균은 악화됐다.
  - 다음 원칙: cleanup/trim을 줄이기 전에 `stage_trim.elapsed_ms`, process residency, X5/Tinyping 반복 평균을 먼저 확인한다.

- 짧은 Macau 단건 개선만 보고 채택하지 않는다.
  - 이유: Macau는 빠른 smoke에는 좋지만 X5/Tinyping long-flow 병목을 대표하지 못할 수 있다.
  - 다음 원칙: 성능 후보 채택은 Macau + X5 + 가능하면 Tinyping에서 평균, p95, 품질 지표를 함께 본다.

- `Terminated: 15`를 모델 크래시로 바로 단정하지 않는다.
  - 이유: 2026-05-20에는 mlx-whisper 로그 직후 앱 자체 exit watchdog이 Python에 SIGTERM을 보내 `.command` 터미널에 `Terminated: 15`가 찍힌 것이었다.
  - 다음 원칙: crash/termination 로그는 마지막 모델 로그가 아니라 process owner, signal source, app shutdown path를 함께 본다.

- 최적화 중 UI/UX를 같이 손대지 않는다.
  - 이유: 성능 회귀와 UI 변경이 섞이면 원인 분리가 어려워지고 사용자가 명시하지 않은 UX 변경이 된다.
  - 다음 원칙: UI/UX 변경이 필요해 보이면 별도 owner-decision item으로 남기고 승인 전에는 구현하지 않는다.
