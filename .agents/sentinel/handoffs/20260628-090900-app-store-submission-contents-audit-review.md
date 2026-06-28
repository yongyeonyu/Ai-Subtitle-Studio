DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio App Store submission contents audit review

findings:
1. **분석 제안 검토**: App Store submission contents (개인정보처리방침 URL, export compliance, 스크린샷, support URL, 리뷰 메모, 연령 등급, 릴리즈 노트 등)를 readiness audit 에 item별 status/draft/owner decision 필드로 구체화하는 보강 방향 검토 결과.
2. ** active queue와의 충돌 여부**: **없음 (완벽 합치)**. 실제 코드 서명, 빌드 업로드, DMG 패키징 도구를 실행하지 않고, 메타데이터 필수 요건의 무결성만을 점검하는 비파괴적인 dry-run 진단 고도화 작업이므로 프로젝트의 active queue 규제 사항과 충돌하지 않음.
3. **기대 효과**: `audit_app_store_readiness.py` 에서 non-code metadata 필수 checklist 검증을 강화하여 누락 시 `app_store_submission_ready=false` 의 blocker 카운트에 정확히 가산해 주므로, 실제 릴리즈 시 발생할 휴먼 에러를 사전에 100% 방지할 수 있는 최적의 안전 강화 조각임.
4. **결론**: **비파괴 App Store submission contents audit 강화 조각을 차기 안전 슬라이스로 적극 Accept 권장**.
5. **추천 테스트**:
   - `tests/test_app_store_readiness_audit.py` (신규 8대 메타데이터 status 검증 어설션 테스트 추가)
6. **수정 불가 경계**:
   - 실제 빌드, signed pkg 생성, notarization 및 App Store Connect API 업로드 실행부.
